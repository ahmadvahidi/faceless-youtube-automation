#!/usr/bin/env python
"""List live videos on this project's channel (title, id, duration, publishedAt, views)."""
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


ch = get("https://www.googleapis.com/youtube/v3/channels?part=snippet,contentDetails,statistics&mine=true")["items"][0]
print("CHANNEL:", ch["snippet"]["title"], ch["id"], ch["statistics"])
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
print("N =", len(items))
for i in items:
    v = vids[i["contentDetails"]["videoId"]]
    print("%s | %s | %s | %s | %s | views=%s" % (
        v["snippet"]["publishedAt"], v["id"], v["contentDetails"]["duration"],
        v["status"]["privacyStatus"], v["snippet"]["title"][:70],
        v["statistics"].get("viewCount")))
