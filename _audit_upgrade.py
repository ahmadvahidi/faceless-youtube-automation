#!/usr/bin/env python
"""Audit live uploads on a channel: titles, durations, dupes, motion of long-forms."""
import json
import re
import sys
import urllib.request
from collections import Counter

ROOT = "/opt/data/workspace/faceless-youtube"
sys.path.insert(0, ROOT)
from send_to_group import _load_env  # noqa

_load_env()
from yt_uploader import get_access_token  # noqa
from upgrade_longform_motion import secs  # noqa


def _get(tok, url):
    return json.load(urllib.request.urlopen(urllib.request.Request(
        url, headers={"Authorization": "Bearer " + tok})))


def audit(tok, label):
    ch = _get(tok, "https://www.googleapis.com/youtube/v3/channels?part=snippet,"
                   "contentDetails,statistics&mine=true")["items"][0]
    print("=== %s | %s | %s" % (label, ch["snippet"]["title"], ch["id"]))
    print("   stats subs=%s views=%s videos=%s" % (
        ch["statistics"].get("subscriberCount"), ch["statistics"].get("viewCount"),
        ch["statistics"].get("videoCount")))
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
    norm = lambda s: re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).strip()
    rows = []
    for i in items:
        v = vids.get(i["contentDetails"]["videoId"])
        if not v:
            continue
        rows.append((v["id"], v["snippet"]["title"],
                     secs(v["contentDetails"]["duration"]),
                     v["status"]["privacyStatus"],
                     int(v["statistics"].get("viewCount", 0)),
                     v["snippet"]["publishedAt"]))
    public = [r for r in rows if r[3] == "public"]
    print("   uploads=%d public=%d" % (len(rows), len(public)))
    c = Counter(norm(r[1]) for r in public)
    print("   DUP TITLES: %s" % json.dumps({k: n for k, n in c.items() if n > 1},
                                          ensure_ascii=False))
    print("   LONG-FORMS (>=400s) public:")
    for r in sorted(public, key=lambda r: -r[2]):
        if r[2] >= 400:
            print("     %s %5ds v=%-4d %s %s" % (r[0], r[2], r[4], r[5][:10], r[1][:62]))
    print("   shorts(<400s) public=%d" % sum(1 for r in public if r[2] < 400))
    return public


if __name__ == "__main__":
    tok = get_access_token()
    audit(tok, "DOPEAK")
