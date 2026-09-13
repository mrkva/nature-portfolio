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

  By default only observations NEWER than the last real run are considered
  (data/tag_state.json remembers the highest observation ID processed), so
  observations you have untagged by hand on iNaturalist are never re-tagged.
  --all considers every observation again (this WOULD re-tag curated-out ones).
"""
import json, os, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_index as bi  # noqa: E402

TOKEN = os.environ.get("INAT_API_TOKEN")
DRY = "--dry-run" in sys.argv
REMOVE = "--remove" in sys.argv
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
ALL = "--all" in sys.argv
STATE = os.path.join(bi.DATA, "tag_state.json")
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
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    last = state.get("last_max_id", 0)
    if not ALL and not REMOVE:
        ids = [i for i in ids if i > last]
        print(f"only observations newer than id {last} (last run); pass --all to reconsider everything")
    if LIMIT:
        ids = ids[:LIMIT]
    makes = {}
    for oid in ids:
        c = cams.get(str(oid), {})
        makes[c.get("make") or "(manual)"] = makes.get(c.get("make") or "(manual)", 0) + 1
    print(f"{len(ids)} candidate observations to {'untag' if REMOVE else 'tag'} with '{TAG_WRITE}' "
          f"(cameras harvested: {len(cams)}); by make: {makes}")
    changed = skipped = failed = low_res = deleted = 0
    for i, oid in enumerate(ids, 1):
        try:
            res = api("GET", f"https://api.inaturalist.org/v1/observations/{oid}")["results"]
        except Exception as e:
            print(f"  {oid}: fetch failed: {e}"); failed += 1; continue
        if not res:
            deleted += 1; continue   # observation no longer exists on iNaturalist (e.g. duplicate removed)
        cur = res[0]
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
            # ignore_photos MUST be top-level: without it iNaturalist removes every photo
            # that is not part of the request (this once stripped photos from hundreds
            # of observations). Verified after the call that the photo count is unchanged.
            before = len(cur.get("photos") or [])
            api("PUT", f"https://api.inaturalist.org/v1/observations/{oid}",
                {"ignore_photos": True, "observation": {"tag_list": ",".join(new)}})
            after = api("GET", f"https://api.inaturalist.org/v1/observations/{oid}")["results"][0]
            if len(after.get("photos") or []) != before:
                raise SystemExit(f"ABORT: photo count changed on {oid} ({before} -> {len(after.get('photos') or [])}); stopping.")
            changed += 1
        except Exception as e:
            print(f"    failed: {e}"); failed += 1
        time.sleep(1.0)  # be polite: iNat asks for ≤ 1 write/sec
    if not DRY and not REMOVE and not LIMIT and ids:
        json.dump({"last_max_id": max(ids), "updated": time.strftime("%Y-%m-%d")}, open(STATE, "w"))
    print(f"done: {changed} changed, {skipped} already ok, {low_res} skipped as low-res, {deleted} deleted on iNat, {failed} failed{' (dry run)' if DRY else ''}")


if __name__ == "__main__":
    main()
