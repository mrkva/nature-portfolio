#!/usr/bin/env python3
"""Re-attach photos that scripts/tag_good_photos.py (old buggy version) stripped from observations.

data/recovery/affected.json lists each observation with the photo IDs it lost.
For each missing photo this script:
  1. tries to re-link the existing iNaturalist photo record to the observation
     (POST /v1/observation_photos with observation_id + photo_id) — this restores
     the very same photo, same ID, same URLs;
  2. if iNaturalist no longer has that photo record, uploads the file saved in
     data/recovery/photos/ (the 2048 px copy downloaded from iNaturalist's storage).

Usage:
  INAT_API_TOKEN='<token from https://www.inaturalist.org/users/api_token>' python3 scripts/restore_photos.py --dry-run
  INAT_API_TOKEN='…' python3 scripts/restore_photos.py            # apply
  Options: --limit N   only the first N observations
"""
import json, os, sys, time, urllib.request, urllib.error, uuid, mimetypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REC = os.path.join(ROOT, "data", "recovery")
TOKEN = os.environ.get("INAT_API_TOKEN")
DRY = "--dry-run" in sys.argv
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
UA = "nature-portfolio-recovery"


def request(method, url, body=None, headers=None):
    h = {"User-Agent": UA}
    if TOKEN:
        h["Authorization"] = TOKEN
    h.update(headers or {})
    data = body
    if isinstance(body, dict):
        data = json.dumps(body).encode(); h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def multipart(fields, file_field, path):
    b = uuid.uuid4().hex.encode()
    out = b""
    for k, v in fields.items():
        out += b"--" + b + b"\r\nContent-Disposition: form-data; name=\"" + k.encode() + b"\"\r\n\r\n" + str(v).encode() + b"\r\n"
    ctype = mimetypes.guess_type(path)[0] or "image/jpeg"
    out += (b"--" + b + b"\r\nContent-Disposition: form-data; name=\"" + file_field.encode() + b"\"; filename=\""
            + os.path.basename(path).encode() + b"\"\r\nContent-Type: " + ctype.encode() + b"\r\n\r\n")
    out += open(path, "rb").read() + b"\r\n--" + b + b"--\r\n"
    return out, {"Content-Type": "multipart/form-data; boundary=" + b.decode()}


def main():
    if not TOKEN and not DRY:
        raise SystemExit("Set INAT_API_TOKEN (from https://www.inaturalist.org/users/api_token)")
    aff = json.load(open(os.path.join(REC, "affected.json")))
    if LIMIT:
        aff = aff[:LIMIT]
    relinked = uploaded = skipped = failed = deleted = 0
    for i, a in enumerate(aff, 1):
        oid = a["id"]
        try:
            res = request("GET", f"https://api.inaturalist.org/v1/observations/{oid}")["results"]
        except urllib.error.HTTPError as e:
            print(f"  [{i}/{len(aff)}] {oid}: fetch failed ({e.code}), skipping"); failed += 1; continue
        if not res:
            print(f"  [{i}/{len(aff)}] {oid}: deleted on iNaturalist, skipping"); deleted += 1; continue
        cur = res[0]
        have = {p["id"] for p in (cur.get("photos") or [])}
        for pid in a["missing"]:
            if pid in have:
                print(f"  [{i}/{len(aff)}] {oid}: photo {pid} already attached"); skipped += 1; continue
            print(f"  [{i}/{len(aff)}] {oid} ({cur['taxon']['name'] if cur.get('taxon') else '?'}): re-attach photo {pid}")
            if DRY:
                continue
            try:
                request("POST", "https://api.inaturalist.org/v1/observation_photos",
                        {"observation_photo": {"observation_id": oid, "photo_id": pid}})
                relinked += 1
                print("      re-linked existing photo record")
            except urllib.error.HTTPError as e:
                msg = e.read().decode(errors="replace")[:200]
                print(f"      re-link failed ({e.code}: {msg}); uploading saved file instead")
                path = next((os.path.join(REC, "photos", f) for f in os.listdir(os.path.join(REC, "photos")) if f.startswith(f"{oid}_{pid}.")), None)
                if not path:
                    print("      no saved file — cannot restore"); failed += 1; continue
                try:
                    body, hdr = multipart({"observation_photo[observation_id]": oid}, "file", path)
                    request("POST", "https://api.inaturalist.org/v1/observation_photos", body, hdr)
                    uploaded += 1
                    print("      uploaded")
                except urllib.error.HTTPError as e2:
                    print(f"      upload failed ({e2.code}: {e2.read().decode(errors='replace')[:200]})"); failed += 1
            time.sleep(1.0)
        # after restoring photos iNaturalist re-evaluates quality grade on its own
    print(f"done: {relinked} re-linked, {uploaded} uploaded, {skipped} already ok, {deleted} deleted on iNat, {failed} failed{' (dry run)' if DRY else ''}")


if __name__ == "__main__":
    main()
