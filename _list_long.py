#!/usr/bin/env python
"""Print live long-form videos (>=240s) on this project's channel with ids."""
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from send_to_group import _load_env  # noqa: E402
_load_env()
from yt_uploader import get_access_token  # noqa: E402

tok = get_access_token()


def get(u):
    return json.load(urllib.request.urlopen(
        urllib.request.Request(u, headers={"Authorization": "Bearer " + tok})))


def secs(iso):
    import re
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


ch = get("https://www.googleapis.com/youtube/v3/channels?part=snippet,contentDetails&mine=true")["items"][0]
print("CHANNEL:", ch["snippet"]["title"], ch["id"])
up = ch["contentDetails"]["relatedPlaylists"]["uploads"]
items, page = [], ""
while True:
    d = get("https://www.googleapis.com/youtube/v3/playlistItems?part=snippet,contentDetails"
            "&maxResults=50&playlistId=%s&pageToken=%s" % (up, page))
    items += d.get("items", [])
    page = d.get("nextPageToken", "")
    if not page:
        break
ids = [i["contentDetails"]["videoId"] for i in items]
vids = {}
for k in range(0, len(ids), 50):
    d = get("https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails,"
            "statistics,status&id=" + ",".join(ids[k:k + 50]))
    for v in d["items"]:
        vids[v["id"]] = v
n = 0
for i in items:
    v = vids[i["contentDetails"]["videoId"]]
    dur = secs(v["contentDetails"]["duration"])
    if dur < 240:
        continue
    n += 1
    print("%s | %s | %ss | %s | views=%s" % (
        v["id"], v["contentDetails"]["duration"], dur, v["snippet"]["title"][:70],
        v["statistics"].get("viewCount")))
print("long-form count:", n)
