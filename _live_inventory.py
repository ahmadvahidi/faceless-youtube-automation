#!/usr/bin/env python
"""Live inventory of a channel: id, title, dur, views, privacy. Prints duplicate-title pairs."""
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT))
from send_to_group import _load_env  # noqa
_load_env()
from yt_uploader import get_access_token  # noqa


def api(path):
    tok = get_access_token()
    return json.load(urllib.request.urlopen(urllib.request.Request(
        "https://www.googleapis.com/youtube/v3/" + path,
        headers={"Authorization": "Bearer " + tok})))


ch = api("channels?part=contentDetails,snippet&mine=true")["items"][0]
up = ch["contentDetails"]["relatedPlaylists"]["uploads"]
print("CHANNEL:", ch["snippet"]["title"], ch["id"])

vids, page = [], ""
while True:
    d = api(f"playlistItems?part=snippet,contentDetails&maxResults=50&playlistId={up}&pageToken={page}")
    for it in d.get("items", []):
        s = it["snippet"]
        vids.append({"id": s["resourceId"]["videoId"], "title": s["title"],
                     "published": s.get("publishedAt", "")})
    page = d.get("nextPageToken", "")
    if not page:
        break

# durations + views + privacy in chunks of 50
for i in range(0, len(vids), 50):
    chunk = vids[i:i + 50]
    ids = ",".join(v["id"] for v in chunk)
    d = api(f"videos?part=contentDetails,statistics,status&id={ids}")
    by = {x["id"]: x for x in d.get("items", [])}
    for v in chunk:
        x = by.get(v["id"])
        if not x:
            continue
        iso = x["contentDetails"]["duration"]
        m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
        h, mi, s = (int(g or 0) for g in m.groups())
        v["dur"] = h * 3600 + mi * 60 + s
        v["views"] = int(x["statistics"].get("viewCount", 0))
        v["privacy"] = x["status"]["privacyStatus"]

print("TOTAL:", len(vids))


def norm(t):
    t = t.lower().replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


groups = {}
for v in vids:
    groups.setdefault(norm(v["title"]), []).append(v)

dups = {k: g for k, g in groups.items() if len(g) > 1}
print("DUPLICATE TITLES:", len(dups))
for k, g in dups.items():
    print("  DUP:", k)
    for v in sorted(g, key=lambda x: x["published"]):
        print(f"    {v['id']} {v['published'][:10]} {v.get('dur')}s {v.get('views')}v {v.get('privacy')}")

print("---- ALL ----")
for v in sorted(vids, key=lambda x: x["published"]):
    print(f"{v['id']} {v['published'][:10]} {v.get('dur'):>4}s {v.get('views'):>4}v {v.get('privacy')} {v['title'][:80]}")
json.dump(vids, open(str(ROOT / "_live_inventory.json"), "w"), indent=1, ensure_ascii=False)
