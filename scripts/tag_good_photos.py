#!/usr/bin/env python3
"""Add the portfolio tag ("Portfolio") to the selected observations on iNaturalist.

Selection = data/cameras*.json entries whose make is not Apple/Olympus and whose
            photo is stored at >= MIN_LONG_EDGE px (2048 = full size on iNaturalist)
            ∪ data/selection.json  −  data/exclude.json   (same rules as build_index.py)

Usage:
  1. Log in to iNaturalist and open https://www.inaturalist.org/users/api_token
     — copy the token (valid 24 h).
  2. INAT_API_TOKEN='<token>' python3 scripts/tag_good_photos.py --dry-run
  3. INAT_API_TOKEN='<token>' python3 scripts/tag_good_photos.py            # apply
     Options: --limit N (only first N), --remove (strip the tag instead of adding it)
     MIN_LONG_EDGE=1500 relaxes the size filter.
"""
import json, os, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_index as bi  # noqa: E402

TOKEN = os.environ.get("INAT_API_TOKEN")
DRY = "--dry-run" in sys.argv
REMOVE = "--remove" in sys.argv
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
TAG = bi.TAG                      # lower-case, for matching
TAG_WRITE = os.environ.get("PORTFOLIO_TAG", "Portfolio")  # what gets written


def api(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "User-Agent": bi.UA}
    if TOKEN:
        headers["Authorization"] = TOKEN
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main():
    if not TOKEN and not DRY:
        raise SystemExit("Set INAT_API_TOKEN (from https://www.inaturalist.org/users/api_token)")
    cams = bi.load_cameras()
    manual = bi.load_ids("selection.json")
    ids = sorted((bi.select_from_cameras() | manual) - bi.load_ids("exclude.json"))
    if LIMIT:
        ids = ids[:LIMIT]
    makes = {}
    for oid in ids:
        c = cams.get(str(oid), {})
        makes[c.get("make") or "(manual)"] = makes.get(c.get("make") or "(manual)", 0) + 1
    print(f"{len(ids)} candidate observations to {'untag' if REMOVE else 'tag'} with '{TAG_WRITE}' "
          f"(cameras harvested: {len(cams)}); by make: {makes}")
    changed = skipped = failed = low_res = 0
    for i, oid in enumerate(ids, 1):
        try:
            cur = api("GET", f"https://api.inaturalist.org/v1/observations/{oid}")["results"][0]
        except Exception as e:
            print(f"  {oid}: fetch failed: {e}"); failed += 1; continue
        if not REMOVE and oid not in manual and bi.long_edge(cur) < bi.MIN_LONG_EDGE:
            print(f"  [{i}/{len(ids)}] {oid} {cur['taxon']['name'] if cur.get('taxon') else ''}: skipped, stored at {bi.long_edge(cur)}px")
            low_res += 1; continue
        tags = list(cur.get("tags") or [])
        has = any(t.lower() == TAG for t in tags)
        if (has and not REMOVE) or (not has and REMOVE):
            skipped += 1; continue
        new = [t for t in tags if t.lower() != TAG] if REMOVE else tags + [TAG_WRITE]
        print(f"  [{i}/{len(ids)}] {oid} {cur['taxon']['name'] if cur.get('taxon') else ''}: {tags} -> {new}")
        if DRY:
            changed += 1; continue
        try:
            api("PUT", f"https://api.inaturalist.org/v1/observations/{oid}",
                {"observation": {"tag_list": ",".join(new), "ignore_photos": 1}})
            changed += 1
        except Exception as e:
            print(f"    failed: {e}"); failed += 1
        time.sleep(1.0)  # be polite: iNat asks for ≤ 1 write/sec
    print(f"done: {changed} changed, {skipped} already ok, {low_res} skipped as low-res, {failed} failed{' (dry run)' if DRY else ''}")


if __name__ == "__main__":
    main()
