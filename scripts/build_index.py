#!/usr/bin/env python3
"""Build data/index.json — a static index of portfolio observations from iNaturalist.

Selection rules (union):
  * observations tagged TAG on iNaturalist (default "Portfolio") — the source of truth, and
  * observation IDs listed in data/selection.json (manual additions, optional), and
  * only with USE_CAMERAS=1: observations whose camera in data/cameras*.json is accepted
    (that list feeds scripts/tag_good_photos.py; the website itself follows the tags).
Observation IDs listed in data/exclude.json are always dropped.

Categories are derived from taxonomy, with lichens split out of Fungi by
ancestry (lichenized classes/orders/genera), so the Fungi filter never shows
lichens and vice versa. Tags "lichen"/"lišajník" force Lichen; "nolichen"
forces Fungi. Run with no network by passing --cache <dir> (dev only).
"""
import json, os, re, sys, time, urllib.request, urllib.parse, datetime

USER = os.environ.get("INAT_USER", "jonasgruska")
TAG = os.environ.get("PORTFOLIO_TAG", "Portfolio").lower()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
API = "https://api.inaturalist.org/v1/observations"
UA = "nature-portfolio-build (github pages; +https://www.inaturalist.org/people/%s)" % USER

# iNaturalist taxon IDs of lichenized fungi groups.
LICHEN_TAXA = {
    54743,   # class Lecanoromycetes (the bulk of lichens)
    152028,  # class Arthoniomycetes
    152030,  # class Lichinomycetes
    152550,  # order Candelariales
    117869,  # order Verrucariales (Eurotiomycetes)
    117881,  # order Pyrenulales (Eurotiomycetes)
    152541,  # order Trypetheliales (Dothideomycetes)
    791622,  # order Monoblastiales (Dothideomycetes)
    791201,  # order Collemopsidiales (Dothideomycetes)
    118252,  # genus Lichenomphalia (basidiolichen)
    175541,  # genus Multiclavula (basidiolichen)
    128050,  # genus Dictyonema (basidiolichen)
}
# Some lichen genera are only placed at "Fungi" or "Ascomycota" level on iNat
# (e.g. Lepraria). Add names here if they show up as Fungi by mistake.
LICHEN_GENERA_BY_NAME = {"Lepraria", "Leprocaulon", "Lichenothelia"}

ICONIC_CAT = {
    "Insecta": "Insects", "Aves": "Birds", "Protozoa": "Slime molds",
}   # everything else (plants, molluscs, reptiles, amphibians, mammals, …) is "Other"
ARANEAE = 47118  # order Araneae: "Spiders" means true spiders only, not mites/harvestmen (also Arachnida)
CAT_ORDER = ["Fungi", "Lichen", "Slime molds", "Insects", "Spiders", "Birds", "Other"]
MYXO = 47684  # class Myxomycetes
FALLBACK_N = 60
# Camera makes that are NOT portfolio material (case-insensitive substring match).
EXCLUDED_MAKES = ("apple", "olympus", "om digital")
# iNaturalist stores photos at most 2048 px on the long edge; anything smaller was
# uploaded small or cropped hard. Automatic (camera-based) selection skips those.
# Explicitly tagged observations are never filtered by size.
MIN_LONG_EDGE = int(os.environ.get("MIN_LONG_EDGE", "2048"))


def long_edge(o):
    d = (o.get("photos") or [{}])[0].get("original_dimensions") or {}
    return max(d.get("width") or 0, d.get("height") or 0)


# Photos with no camera metadata at all are mostly focus stacks exported without
# EXIF, so they count as accepted; INCLUDE_UNKNOWN_MAKE=0 excludes them.
INCLUDE_UNKNOWN_MAKE = os.environ.get("INCLUDE_UNKNOWN_MAKE", "1") != "0"


def camera_ok(make, model=""):
    name = f"{make} {model}".lower().strip()
    if not name:
        return INCLUDE_UNKNOWN_MAKE
    return not any(x in name for x in EXCLUDED_MAKES)


def load_cameras():
    """Merge every data/cameras*.json: {"<observation id>": {"make": "...", "model": "..."}} (see scripts/harvest_cameras.js)."""
    cams = {}
    for name in sorted(os.listdir(DATA)) if os.path.isdir(DATA) else []:
        if name.startswith("cameras") and name.endswith(".json"):
            for oid, c in json.load(open(os.path.join(DATA, name))).items():
                if c.get("make") is not None and c.get("status") is None:
                    cams[str(oid)] = c
    return cams


def select_from_cameras():
    """Observation IDs whose first photo came from an accepted camera (no size check here)."""
    return {int(oid) for oid, c in load_cameras().items() if camera_ok(c.get("make") or "", c.get("model") or "")}


def get(url, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # noqa
            wait = 2 ** i
            print(f"  retry {i+1} after error {e} ({wait}s)", file=sys.stderr)
            time.sleep(wait)
    raise SystemExit("iNaturalist API unreachable")


def fetch_all(locale):
    out, id_above = [], 0
    while True:
        q = urllib.parse.urlencode({
            "user_login": USER, "photos": "true", "per_page": 200,
            "order_by": "id", "order": "asc", "locale": locale, "id_above": id_above,
        })
        res = get(f"{API}?{q}")["results"]
        if not res:
            return out
        out += res
        id_above = res[-1]["id"]
        print(f"  {locale}: {len(out)}", file=sys.stderr)
        time.sleep(0.6)


def load_ids(name):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return set()
    with open(p) as f:
        d = json.load(f)
    return set(int(x) for x in (d if isinstance(d, list) else d.get("ids", [])))


def categorize(o):
    t = o["taxon"]
    tags = [s.lower() for s in (o.get("tags") or [])]
    anc = set(t.get("ancestor_ids") or []) | {t["id"]}
    if "nolichen" in tags:
        return "Fungi"
    if "lichen" in tags or "lišajník" in tags or "lisajnik" in tags:
        return "Lichen"
    if anc & LICHEN_TAXA or t["name"].split(" ")[0] in LICHEN_GENERA_BY_NAME:
        return "Lichen"
    iconic = t.get("iconic_taxon_name")
    if iconic == "Fungi":
        return "Fungi"
    if ARANEAE in anc:
        return "Spiders"
    if MYXO in anc or iconic == "Protozoa" or any(("slime" in s or "slizovk" in s or "myxo" in s) for s in tags):
        return "Slime molds"
    return ICONIC_CAT.get(iconic, "Other")


def clean_place(place):
    """Drop a leading street address or plus code ("Jelenia 3138/10, 811 05 Bratislava, Slovakia"
    -> "811 05 Bratislava, Slovakia"). iNaturalist's place_guess can be house-precise for
    open-geoprivacy observations; the site only needs town-level detail."""
    parts = [x.strip() for x in (place or "").split(",")]
    street = re.compile(r"\d+/\d+|[^\W\d]\S*\s+\d+[a-zA-Z]?$|^[2-9CFGHJMPQRVWX]{4,8}\+[2-9CFGHJMPQRVWX]{2,}")
    while len(parts) > 1 and street.search(parts[0]):
        parts.pop(0)  # "Name 12", "Name 3138/10" or a plus code; "935 03 Town" is kept
    return ", ".join(parts)


def photo_entry(p):
    url = p["url"]  # .../photos/<id>/square.jpg
    base, fname = url.rsplit("/", 1)
    ext = fname.split(".")[-1]
    dims = p.get("original_dimensions") or {}
    return {"id": p["id"], "base": base, "ext": ext, "w": dims.get("width"), "h": dims.get("height")}


def main():
    cache = None
    if "--cache" in sys.argv:
        cache = sys.argv[sys.argv.index("--cache") + 1]
    if cache and os.path.exists(os.path.join(cache, "obs_en.json")):
        en = json.load(open(os.path.join(cache, "obs_en.json")))
        sk = json.load(open(os.path.join(cache, "obs_sk.json")))
    else:
        print("fetching observations…", file=sys.stderr)
        en, sk = fetch_all("en"), fetch_all("sk")
        if cache:
            os.makedirs(cache, exist_ok=True)
            json.dump(en, open(os.path.join(cache, "obs_en.json"), "w"))
            json.dump(sk, open(os.path.join(cache, "obs_sk.json"), "w"))

    sk_names = {o["id"]: (o.get("taxon") or {}).get("preferred_common_name") or "" for o in sk}
    selection, exclude = load_ids("selection.json"), load_ids("exclude.json")
    by_camera = select_from_cameras() if os.environ.get("USE_CAMERAS") == "1" else set()
    usable = [o for o in en if o.get("taxon") and o.get("photos")]
    all_count = len(usable)
    is_tagged = lambda o: TAG in [s.lower() for s in (o.get("tags") or [])]
    low_res = 0
    chosen = []
    for o in usable:
        if o["id"] in exclude:
            continue
        if is_tagged(o) or o["id"] in selection:
            chosen.append(o)
        elif o["id"] in by_camera:
            if long_edge(o) >= MIN_LONG_EDGE:
                chosen.append(o)
            else:
                low_res += 1
    if low_res:
        print(f"skipped {low_res} camera-selected observations below {MIN_LONG_EDGE}px", file=sys.stderr)
    fallback = False
    if not chosen:
        # Nothing selected yet: preview the most-faved research-grade observations.
        fallback = True
        chosen = sorted((o for o in usable if o.get("quality_grade") == "research"),
                        key=lambda o: (o.get("faves_count", 0), o["id"]), reverse=True)[:FALLBACK_N]
    items = []
    for o in chosen:
        tagged = is_tagged(o)
        t = o["taxon"]
        en_name = t.get("preferred_common_name") or ""
        sk_name = sk_names.get(o["id"], "")
        items.append({
            "id": o["id"],
            "cat": categorize(o),
            "photos": [photo_entry(p) for p in o["photos"]],
            "latin": t["name"],
            "rank": t.get("rank"),
            "en": en_name,
            "sk": sk_name if sk_name != en_name else "",
            "place": clean_place(o.get("place_guess")),
            "date": o.get("observed_on") or "",
            "grade": o.get("quality_grade"),
            "faves": o.get("faves_count", 0),
            "tagged": tagged,
        })
    # newest first
    items.sort(key=lambda x: (x["date"], x["id"]), reverse=True)
    counts = {}
    for it in items:
        counts[it["cat"]] = counts.get(it["cat"], 0) + 1
    index = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "user": USER, "tag": TAG,
        "total_observations": all_count,
        "fallback": fallback,
        "count": len(items),
        "categories": [{"name": c, "count": counts[c]} for c in CAT_ORDER if counts.get(c)],
        "items": items,
    }
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "index.json"), "w") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {len(items)} items ({counts}) of {all_count} observations", file=sys.stderr)


if __name__ == "__main__":
    main()
