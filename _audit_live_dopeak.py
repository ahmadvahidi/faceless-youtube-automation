"""Audit every LIVE public DOPEAK video: download a fragment and measure motion.

Writes /opt/data/workspace/faceless-youtube/live_audit.json as it goes (append-safe),
so a timeout never loses the rows already measured.
"""
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path("/opt/data/workspace/faceless-youtube")
sys.path.insert(0, str(ROOT))
from send_to_group import _load_env  # noqa: E402

_load_env()
from yt_uploader import get_access_token  # noqa: E402
from verify_video import motion_score  # noqa: E402

PY = "/opt/data/skills/.venv/bin/python"
SCRATCH = Path("/opt/data/cache/scratch/live_motion")
SCRATCH.mkdir(parents=True, exist_ok=True)
OUTF = ROOT / "live_audit.json"


def api(tok, url):
    return json.load(urllib.request.urlopen(
        urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})))


def secs(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def videos(tok):
    ch = api(tok, "https://www.googleapis.com/youtube/v3/channels?part=contentDetails&mine=true")
    up = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    items, page = [], ""
    while True:
        d = api(tok, "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet,"
                     "contentDetails&maxResults=50&playlistId=%s&pageToken=%s" % (up, page))
        items += d.get("items", [])
        page = d.get("nextPageToken", "")
        if not page:
            break
    ids = [i["contentDetails"]["videoId"] for i in items]
    out = []
    for k in range(0, len(ids), 50):
        d = api(tok, "https://www.googleapis.com/youtube/v3/videos?part=snippet,"
                     "contentDetails,status&id=" + ",".join(ids[k:k + 50]))
        for v in d["items"]:
            if v["status"]["privacyStatus"] != "public":
                continue
            out.append({"id": v["id"], "title": v["snippet"]["title"],
                        "published": v["snippet"]["publishedAt"],
                        "dur": secs(v["contentDetails"]["duration"])})
    return out


def measure(vid, dur):
    frag = next(SCRATCH.glob(vid + ".*"), None)
    if frag is None:
        if dur >= 50:
            args = ["--download-sections", "*15-45"]
        else:
            args = []
        subprocess.run([PY, "-m", "yt_dlp", "-f", "bv*[height<=480]/b[height<=480]"] + args +
                       ["-o", str(SCRATCH / (vid + ".%(ext)s")),
                        "https://www.youtube.com/watch?v=" + vid],
                       capture_output=True, text=True)
        frag = next(SCRATCH.glob(vid + ".*"), None)
    if frag is None:
        return None
    return round(motion_score(frag), 2)


def main():
    tok = get_access_token()
    vs = videos(tok)
    print(f"{len(vs)} public videos", flush=True)
    rows = []
    for v in vs:
        m = measure(v["id"], v["dur"])
        v["motion"] = m
        rows.append(v)
        verdict = "STATIC" if (m is not None and m < 4.0) else ("?" if m is None else "ok")
        print(f"{verdict:6} {m!s:>7} {v['dur']:5}s {v['id']} {v['title'][:60]}", flush=True)
        OUTF.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    print(f"\nwrote {OUTF} ({len(rows)} rows)", flush=True)


if __name__ == "__main__":
    main()
