"""Duplicate-title scan on both channels + status of the broken 0s upload."""
import json
import re
import sys
import urllib.request
from pathlib import Path


def run(root):
    root = Path(root)
    sys.path.insert(0, str(root))
    for m in list(sys.modules):
        if m in ("yt_uploader", "send_to_group"):
            del sys.modules[m]
    from send_to_group import _load_env
    _load_env()
    from yt_uploader import get_access_token
    tok = get_access_token()

    def get(u):
        return json.load(urllib.request.urlopen(
            urllib.request.Request(u, headers={"Authorization": "Bearer " + tok})))

    ch = get("https://www.googleapis.com/youtube/v3/channels?part=snippet,contentDetails"
             "&mine=true")["items"][0]
    up = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    items, page = [], ""
    while True:
        d = get("https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50"
                "&playlistId=%s&pageToken=%s" % (up, page))
        items += d.get("items", [])
        page = d.get("nextPageToken", "")
        if not page:
            break
    ids = [i["snippet"]["resourceId"]["videoId"] for i in items]
    vids = {}
    for k in range(0, len(ids), 50):
        d = get("https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails,"
                "status&id=" + ",".join(ids[k:k + 50]))
        for v in d["items"]:
            vids[v["id"]] = v
    print("== channel:", ch["snippet"]["title"], ch["id"], "videos:", len(vids))
    groups = {}
    for vid, v in vids.items():
        if v["status"]["privacyStatus"] != "public":
            continue
        key = re.sub(r"[^a-z0-9]+", " ", v["snippet"]["title"].lower()).strip()
        groups.setdefault(key, []).append((v["snippet"]["publishedAt"], vid,
                                           v["snippet"]["title"]))
    dups = {k: g for k, g in groups.items() if len(g) > 1}
    print("   duplicate normalised titles:", len(dups))
    for k, g in dups.items():
        g.sort()
        print("   DUP:", k)
        for pub, vid, title in g:
            print("       ", vid, pub[:10], title)
    # broken / zero-duration
    for vid, v in vids.items():
        dur = v["contentDetails"]["duration"]
        if dur in ("PT0S", "PT1S", "PT2S"):
            print("   BROKEN-DUR:", vid, dur, v["status"]["privacyStatus"],
                  v["snippet"]["title"][:60])


for r in ("/opt/data/workspace/faceless-youtube", "/opt/data/workspace/cs-videos"):
    try:
        run(r)
    except Exception as e:
        print("!! failed for", r, e)
