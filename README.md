# Nature portfolio

A static portfolio of iNaturalist photographs, hosted on GitHub Pages.
No build tooling in the browser: `index.html` reads `data/index.json`, which a
GitHub Action regenerates daily from the iNaturalist API.

## How photos get in

Observations appear when **either**:

* they carry the tag **`good photos`** on iNaturalist (`PORTFOLIO_TAG` in the workflow), or
* their camera in `data/cameras.json` is not Apple / Olympus, or
* their ID is listed in `data/selection.json` (manual additions).

IDs in `data/exclude.json` are always dropped. Until anything is selected the
site shows a preview of the 60 most-faved research-grade observations and
labels the source link "untagged preview".

## Categories

Derived from taxonomy in `scripts/build_index.py`. Lichens are split out of
Fungi by ancestry (Lecanoromycetes, Arthoniomycetes, Lichinomycetes,
Candelariales, Verrucariales, Pyrenulales, Trypetheliales, basidiolichens…),
so *Fungi* never shows lichens and *Lichen* never shows other fungi. Override
per observation with iNat tags `lichen` / `nolichen`. Slime molds (Myxomycetes,
iconic taxon Protozoa) get their own category; insects, spiders, birds, plants,
molluscs, amphibians, reptiles, mammals each get one; the rest is *Other*.

## Camera detection & tagging

iNaturalist strips EXIF from image files and its API does not expose camera
metadata; it is only shown on each photo's web page, which is behind
Cloudflare. So the harvest runs in your browser:

1. Open any page on **www**.inaturalist.org (progress is stored per origin),
   open DevTools → Console, paste `scripts/harvest_cameras.js`, press Enter.
   It goes one photo page at a time and backs off on rate limits. Whenever it
   stops (done, or a Cloudflare check appeared) it downloads a `cameras-*.json`.
   After passing a Cloudflare check, paste the script again: it resumes.
2. Save every downloaded file into `data/` (all `data/cameras*.json` are
   merged), then `python3 scripts/build_index.py`.
3. To write the `good photos` tag back to iNaturalist, get a token at
   https://www.inaturalist.org/users/api_token and run
   `INAT_API_TOKEN=… python3 scripts/tag_good_photos.py --dry-run`, then
   without `--dry-run`. `--remove` strips the tag again.

## Local development

```bash
python3 scripts/build_index.py --cache .cache   # caches the API download
python3 -m http.server 8765                     # open http://localhost:8765
```

Site text (name, about, e-mail, slideshow interval, preload depth) lives in the
`CONFIG` block at the top of `index.html`.
