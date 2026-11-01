#!/usr/bin/env python
"""Measure LIVE motion of every public DOPEAK long-form (fresh fragments)."""
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = "/opt/data/workspace/faceless-youtube"
sys.path.insert(0, ROOT)
from send_to_group import _load_env  # noqa

_load_env()
from verify_video import motion_score  # noqa
from yt_uploader import get_access_token  # noqa

SCRATCH = Path("/opt/data/cache/scratch/live_motion")
SCRATCH.mkdir(parents=True, exist_ok=True)
PY = "/opt/data/skills/.venv/bin/python"


def _get(tok, url):
    return json.load(urllib.request.urlopen(urllib.request.Request(
        url, headers={"Authorization": "Bearer " + tok})))


def secs(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


tok = get_access_token()
ch = _get(tok, "https://www.googleapis.com/youtube/v3/channels?part=snippet,"
               "contentDetails,statistics&mine=true")["items"][0]
print("CHANNEL:", ch["snippet"]["title"], ch["id"], ch["statistics"])
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

rows = []
for i in items:
    v = vids[i["contentDetails"]["videoId"]]
    if v["status"]["privacyStatus"] != "public":
        continue
    dur = secs(v["contentDetails"]["duration"])
    if dur < 400:
        continue
    for f in SCRATCH.glob(v["id"] + ".*"):
        f.unlink()
    subprocess.run([PY, "-m", "yt_dlp", "-f", "bv*[height<=480]/b[height<=480]",
                    "--download-sections", "*15-45",
                    "-o", str(SCRATCH / (v["id"] + ".%(ext)s")),
                    "https://www.youtube.com/watch?v=" + v["id"]],
                   capture_output=True, text=True)
    f = next(SCRATCH.glob(v["id"] + ".*"), None)
    m = motion_score(f) if f else None
    rows.append((v["id"], v["snippet"]["title"], dur, m,
                 int(v["statistics"].get("viewCount", 0))))
    print("%s %4ds %6s v=%-4d %s" % (v["id"], dur,
                                     ("%.2f%%" % m) if m is not None else "n/a",
                                     rows[-1][4], v["snippet"]["title"][:55]), flush=True)

print("\nSTATIC long-forms:")
for vid, t, dur, m, vw in rows:
    if m is None or m < 4.0:
        print("  %s %.2f%% %ds v=%d %s" % (vid, m if m is not None else -1, dur, vw, t))
Path(ROOT, "_dopeak_live_longform.json").write_text(json.dumps(
    [{"id": r[0], "title": r[1], "dur": r[2], "motion": r[3], "views": r[4]}
     for r in rows], indent=1, ensure_ascii=False))
