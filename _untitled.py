#!/usr/bin/env python
"""List DOPEAK uploads with empty/'untitled' titles."""
import json
import re
import sys
import urllib.request

sys.path.insert(0, "/opt/data/workspace/faceless-youtube")
from send_to_group import _load_env  # noqa

_load_env()
from yt_uploader import get_access_token  # noqa


def _get(tok, url):
    return json.load(urllib.request.urlopen(urllib.request.Request(
        url, headers={"Authorization": "Bearer " + tok})))


def secs(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    h, mi, s = (int(x) if x else 0 for x in m.groups()) if m else (0, 0, 0)
    return h * 3600 + mi * 60 + s


tok = get_access_token()
ch = _get(tok, "https://www.googleapis.com/youtube/v3/channels?part=contentDetails"
               "&mine=true")["items"][0]
up = ch["contentDetails"]["relatedPlaylists"]["uploads"]
items, page = [], ""
while True:
    d = _get(tok, "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet,"
                  "contentDetails&maxResults=50&playlistId=%s&pageToken=%s" % (up, page))
    items += d.get("items", [])
    page = d.get("nextPageToken", "")
    if not page:
        break
ids = [i["contentDetails"]["videoId"] for i in items]
vids = {}
for k in range(0, len(ids), 50):
    d = _get(tok, "https://www.googleapis.com/youtube/v3/videos?part=snippet,"
                  "contentDetails,status,statistics&id=" + ",".join(ids[k:k + 50]))
    for v in d["items"]:
        vids[v["id"]] = v
for v in sorted(vids.values(), key=lambda v: v["snippet"]["publishedAt"]):
    t = (v["snippet"]["title"] or "").strip()
    if t.lower() in ("", "untitled"):
        print("%s | %s | %5ds | priv=%s | views=%s | file=%r" % (
            v["id"], v["snippet"]["publishedAt"][:10],
            secs(v["contentDetails"]["duration"]), v["status"]["privacyStatus"],
            v["statistics"].get("viewCount", "?"),
            (v["snippet"].get("title") or "")))
