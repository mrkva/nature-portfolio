// Harvest camera make/model for every observation photo.
// iNaturalist strips EXIF from the image files and the API does not expose it;
// the only place it is shown is the photo page (www.inaturalist.org/photos/<id>),
// which sits behind Cloudflare. So this runs *inside your browser*:
//   1. Open https://www.inaturalist.org in Chrome/Safari (any page, logged in or not).
//   2. Open DevTools → Console, paste this whole file, press Enter.
//   3. Wait (≈2 850 photos, a few minutes). A file "cameras.json" is downloaded.
//   4. Save it as data/cameras.json in the repo and run scripts/build_index.py.
(async () => {
  const USER = 'jonasgruska';
  const CONCURRENCY = 6;
  const out = {};
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  // 1. list observations (first photo of each)
  const obs = []; let idAbove = 0;
  while (true) {
    const r = await fetch(`https://api.inaturalist.org/v1/observations?user_login=${USER}&photos=true&per_page=200&order_by=id&order=asc&id_above=${idAbove}&fields=photos.id`);
    const res = (await r.json()).results;
    if (!res.length) break;
    for (const o of res) obs.push({ id: o.id, photo: o.photos[0].id });
    idAbove = res[res.length - 1].id;
    console.log('listed', obs.length);
    await sleep(400);
  }

  // 2. read Make / Model from each photo page's metadata table
  const grab = (html, key) => {
    const m = html.match(new RegExp(`<t[hd][^>]*>\\s*${key}\\s*<\\/t[hd]>\\s*<td[^>]*>([^<]*)<`, 'i'));
    return m ? m[1].trim() : '';
  };
  let done = 0;
  const queue = obs.slice();
  await Promise.all(Array.from({ length: CONCURRENCY }, async () => {
    while (queue.length) {
      const o = queue.shift();
      try {
        const html = await (await fetch(`/photos/${o.photo}`, { credentials: 'include' })).text();
        out[o.id] = { photo: o.photo, make: grab(html, 'Make'), model: grab(html, 'Model') };
      } catch (e) { out[o.id] = { photo: o.photo, error: String(e) }; }
      if (++done % 50 === 0) console.log('photos', done, '/', obs.length);
      await sleep(150);
    }
  }));

  // 3. download the result
  const blob = new Blob([JSON.stringify(out, null, 1)], { type: 'application/json' });
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: 'cameras.json' });
  document.body.appendChild(a); a.click(); a.remove();
  const makes = {}; for (const v of Object.values(out)) makes[v.make || '?'] = (makes[v.make || '?'] || 0) + 1;
  console.table(makes);
  window.__cameras = out;
})();
