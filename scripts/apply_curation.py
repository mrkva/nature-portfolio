#!/usr/bin/env python3
"""Apply data/curation.json to iNaturalist: remove the Portfolio tag from every
observation listed under "remove" that still carries it.

Hidden photos ("hide") need no iNaturalist change — the build strips them.

  INAT_API_TOKEN='<token from https://www.inaturalist.org/users/api_token>' python3 scripts/apply_curation.py --dry-run
  INAT_API_TOKEN='…' python3 scripts/apply_curation.py
"""
import json, os, sys, time, urllib.request, urllib.parse

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
    ids = {int(x) for x in cur.get("remove", [])}
    hidden = {int(x) for x in cur.get("hide", [])}
    # an observation whose every photo is hidden counts as removed
    if hidden:
        q = "https://api.inaturalist.org/v1/observations?user_login=%s&q=%s&search_on=tags&per_page=200&order_by=id&order=asc&id_above=%d"
        id_above, fully_hidden = 0, set()
        while True:
            res = api("GET", q % (bi.USER, urllib.parse.quote(TAG), id_above))["results"]
            if not res:
                break
            for o in res:
                pids = [p["id"] for p in (o.get("photos") or [])]
                if pids and all(p in hidden for p in pids):
                    fully_hidden.add(o["id"])
            id_above = res[-1]["id"]
            time.sleep(0.5)
        if fully_hidden:
            print(f"{len(fully_hidden)} observations have every photo hidden -> treated as removed")
        ids |= fully_hidden
    ids = sorted(ids)
    print(f"{len(ids)} observations to untag, {len(hidden)} photos hidden (build-only)")
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
