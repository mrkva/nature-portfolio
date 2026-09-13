#!/usr/bin/env python3
"""Apply data/curation.json to iNaturalist: remove the Portfolio tag from every
observation listed under "remove" that still carries it.

Hidden photos ("hide") need no iNaturalist change — the build strips them.

  INAT_API_TOKEN='<token from https://www.inaturalist.org/users/api_token>' python3 scripts/apply_curation.py --dry-run
  INAT_API_TOKEN='…' python3 scripts/apply_curation.py
"""
import json, os, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_index as bi  # noqa: E402

TOKEN = os.environ.get("INAT_API_TOKEN")
DRY = "--dry-run" in sys.argv
TAG = bi.TAG


def api(method, url, body=None):
    headers = {"Content-Type": "application/json", "User-Agent": bi.UA}
    if TOKEN:
        headers["Authorization"] = TOKEN
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method, headers=headers), timeout=60) as r:
        return json.load(r)


def main():
    if not TOKEN and not DRY:
        raise SystemExit("Set INAT_API_TOKEN (from https://www.inaturalist.org/users/api_token)")
    cur = json.load(open(os.path.join(bi.DATA, "curation.json")))
    ids = sorted({int(x) for x in cur.get("remove", [])})
    print(f"{len(ids)} observations flagged for removal, {len(cur.get('hide', []))} photos hidden (build-only)")
    changed = skipped = failed = 0
    for i, oid in enumerate(ids, 1):
        try:
            res = api("GET", f"https://api.inaturalist.org/v1/observations/{oid}")["results"]
        except Exception as e:
            print(f"  {oid}: fetch failed: {e}"); failed += 1; continue
        if not res:
            skipped += 1; continue
        o = res[0]
        tags = list(o.get("tags") or [])
        if not any(t.lower() == TAG for t in tags):
            skipped += 1; continue
        new = [t for t in tags if t.lower() != TAG]
        print(f"  [{i}/{len(ids)}] {oid} {o['taxon']['name'] if o.get('taxon') else ''}: {tags} -> {new}")
        if DRY:
            changed += 1; continue
        before = len(o.get("photos") or [])
        try:
            api("PUT", f"https://api.inaturalist.org/v1/observations/{oid}",
                {"ignore_photos": True, "observation": {"tag_list": ",".join(new)}})
            after = api("GET", f"https://api.inaturalist.org/v1/observations/{oid}")["results"][0]
            if len(after.get("photos") or []) != before:
                raise SystemExit(f"ABORT: photo count changed on {oid}; stopping.")
            changed += 1
        except SystemExit:
            raise
        except Exception as e:
            print(f"    failed: {e}"); failed += 1
        time.sleep(1.0)
    print(f"done: {changed} untagged, {skipped} already untagged/deleted, {failed} failed{' (dry run)' if DRY else ''}")


if __name__ == "__main__":
    main()
