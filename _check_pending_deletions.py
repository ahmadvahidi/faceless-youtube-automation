#!/usr/bin/env python
"""Confirm pending_deletions old ids are really gone; re-delete if a duplicate exists."""
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path("/opt/data/workspace/faceless-youtube")
sys.path.insert(0, str(ROOT))
from send_to_group import _load_env  # noqa

_load_env()
from yt_uploader import get_access_token  # noqa

tok = get_access_token()


def g(url):
    return json.load(urllib.request.urlopen(
        urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})))


def alive(vid):
    d = g("https://www.googleapis.com/youtube/v3/videos?part=id,snippet&id=" + vid)
    return d.get("items", [])


pend = json.loads((ROOT / "pending_deletions.json").read_text())
for p in pend:
    items = alive(p["old_id"])
    if items:
        t = items[0]["snippet"]["title"]
        print("STILL LIVE", p["old_id"], "|", t[:60])
    else:
        print("GONE      ", p["old_id"], "|", p["title"][:55])

# also list duplicate titles on DOPEAK among public videos
ch = g("https://www.googleapis.com/youtube/v3/channels?part=contentDetails&mine=true")["items"][0]
up = ch["contentDetails"]["relatedPlaylists"]["uploads"]
items, page = [], ""
while True:
    d = g("https://www.googleapis.com/youtube/v3/playlistItems?part=snippet,contentDetails"
          "&maxResults=50&playlistId=%s&pageToken=%s" % (up, page))
    items += d.get("items", [])
    page = d.get("nextPageToken", "")
    if not page:
        break
ids = [i["contentDetails"]["videoId"] for i in items]
vids = {}
for k in range(0, len(ids), 50):
    d = g("https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails,status&id="
          + ",".join(ids[k:k + 50]))
    for v in d["items"]:
        vids[v["id"]] = v
import re
norm = lambda s: re.sub(r"[^a-z0-9 ]+", " ", s.lower()).strip()
dups = {}
for i in items:
    v = vids[i["contentDetails"]["videoId"]]
    if v["status"]["privacyStatus"] != "public":
        continue
    dups.setdefault(norm(v["snippet"]["title"]), []).append((v["id"], v["snippet"]["title"],
                                                             v["snippet"]["publishedAt"]))
print("\npublic uploads:", sum(len(v) for v in dups.values()))
found = False
for n, lst in dups.items():
    if len(lst) > 1:
        found = True
        print("DUP:", n)
        for x in lst:
            print("   ", x[0], x[2][:10], x[1][:70])
if not found:
    print("no duplicate titles")
