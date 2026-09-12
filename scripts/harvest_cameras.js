// Harvest camera make/model for every observation photo.
// iNaturalist strips EXIF from the image files and the API does not expose it;
// the only place it is shown is the photo page (www.inaturalist.org/photos/<id>),
// which sits behind Cloudflare. So this runs *inside your browser*:
//   1. Open https://www.inaturalist.org in Chrome/Safari (any page, logged in or not).
//   2. Open DevTools → Console, paste this whole file, press Enter.
//   3. Wait. Photo pages are rate-limited, so this goes one request at a time
//      (~30–50 min for ~2 850 photos). Progress is saved in localStorage, so if
//      the tab is closed or the script is stopped, paste it again and it resumes.
//   4. Whenever it stops (finished, or Cloudflare served a challenge) it downloads
//      a cameras-*.json file. Save every such file into data/ in the repo —
//      build_index.py merges all data/cameras*.json — and run scripts/build_index.py.
// IMPORTANT: run it on https://www.inaturalist.org (with "www"). localStorage is
// per origin, so a console opened on inaturalist.org without www sees no progress.
// If a Cloudflare check appears: pass it in the same tab, come back to a
// www.inaturalist.org page, paste again — it resumes from localStorage.
// To start over from scratch: localStorage.removeItem('inat_cameras')
(async () => {
  const USER = 'jonasgruska';
  const KEY = 'inat_cameras';
  let delay = 1000;                 // ms between photo-page requests (adapts to 429s)
  const MIN_DELAY = 800, MAX_DELAY = 120000;
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  if (location.hostname !== 'www.inaturalist.org') { console.error(`Run this on https://www.inaturalist.org (you are on ${location.hostname}); progress is stored per origin.`); return; }
  const out = Object.assign(JSON.parse(localStorage.getItem(KEY) || '{}'), window.__cameras_seed || {});
  const save = () => localStorage.setItem(KEY, JSON.stringify(out));
  const V = 2;  // bump when the parser changes: older entries get re-fetched
  const isDone = (e) => e && e.v === V && e.status === undefined;
  const download = (suffix) => {
    const n = Object.values(out).filter(isDone).length;
    const blob = new Blob([JSON.stringify(out, null, 1)], { type: 'application/json' });
    const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `cameras-${suffix}-${n}.json` });
    document.body.appendChild(a); a.click(); a.remove();
    console.log(`downloaded cameras-${suffix}-${n}.json (${n} photos with data)`);
  };
  const stopForChallenge = () => {
    save(); download('partial');
    console.error('Cloudflare challenge served. Open https://www.inaturalist.org/photos/' + (obs[0] ? obs[0].photo : '') + ' in THIS tab, pass the check, then paste the script again on a www.inaturalist.org page — it resumes.');
  };

  // 1. list observations (first photo of each)
  const obs = []; let idAbove = 0;
  while (true) {
    const r = await fetch(`https://api.inaturalist.org/v1/observations?user_login=${USER}&photos=true&per_page=200&order_by=id&order=asc&id_above=${idAbove}&fields=photos.id`);
    if (r.status === 429) { console.warn('API 429, waiting 30 s'); await sleep(30000); continue; }
    const res = (await r.json()).results;
    if (!res.length) break;
    for (const o of res) obs.push({ id: o.id, photo: o.photos[0].id });
    idAbove = res[res.length - 1].id;
    await sleep(500);
  }
  const todo = obs.filter(o => !isDone(out[o.id]));
  console.log(`observations: ${obs.length}, already done: ${obs.length - todo.length}, to fetch: ${todo.length}`);

  // 2. read Make / Model from each photo page's metadata table, one at a time
  // The metadata table is <tr><th>Make</th><td class="ui">…markup…</td></tr>; read it via the DOM.
  const parseMeta = (html) => {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const meta = {};
    for (const th of doc.querySelectorAll('th')) {
      const td = th.nextElementSibling;
      if (td && td.tagName === 'TD') meta[th.textContent.trim().toLowerCase()] = td.textContent.replace(/\s+/g, ' ').trim();
    }
    return meta;
  };
  let done = 0, okStreak = 0;
  for (const o of todo) {
    for (let attempt = 0; ; attempt++) {
      let r;
      try { r = await fetch(`/photos/${o.photo}`, { credentials: 'include' }); }
      catch (e) { console.warn('network error, retrying in 10 s', e); await sleep(10000); continue; }
      if (r.status === 429 || r.status === 503) {
        const ra = parseInt(r.headers.get('Retry-After') || '0', 10) * 1000;
        delay = Math.min(MAX_DELAY, Math.max(ra, delay * 2));
        okStreak = 0;
        console.warn(`${r.status} on photo ${o.photo}; backing off, delay now ${delay} ms`);
        await sleep(delay);
        continue;
      }
      const html = await r.text();
      if (r.status === 403 || /Just a moment|challenge-platform|cf-chl/.test(html)) { stopForChallenge(); return; }
      if (r.status !== 200) { out[o.id] = { photo: o.photo, status: r.status }; save(); break; }
      const meta = parseMeta(html);
      out[o.id] = { photo: o.photo, v: V, make: meta['make'] || '', model: meta['model'] || '', software: meta['software'] || '' };
      if (done === 0) console.log('first parsed entry:', out[o.id], 'rows seen:', Object.keys(meta).join(', '));
      save();
      if (++okStreak >= 20) { delay = Math.max(MIN_DELAY, Math.round(delay * 0.85)); okStreak = 0; }
      break;
    }
    if (++done % 25 === 0) console.log(`photos ${done} / ${todo.length} (delay ${delay} ms)`);
    await sleep(delay);
  }
  save();

  // 3. download the result
  download('full');
  const makes = {}; for (const v of Object.values(out)) makes[v.make || '?'] = (makes[v.make || '?'] || 0) + 1;
  console.table(makes);
  console.log('done — also available as window.__cameras');
  window.__cameras = out;
})();
