"""Measure the remaining unmeasured DOPEAK uploads: typographic-hyphen shorts + the 7 long-forms.

The ASCII filter in sweep_unmeasured_2026_11_05.py skipped 24 real shorts (their titles use
U+2011 / U+2019), and the long-forms were never measured on the LIVE file.
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
OUT = ROOT / "live_motion_sweep2_2026-11-05.json"

FARSI = re.compile(r"[\u0600-\u06FF]")


def get(u, tok):
    return json.load(urllib.request.urlopen(
        urllib.request.Request(u, headers={"Authorization": "Bearer " + tok})))


def secs(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def measure(vid, dur):
    frag = next((p for p in SCRATCH.glob(vid + ".*") if "_full" not in p.name), None)
    if frag is not None and dur < 50:
        try:
            r = subprocess.run(["/usr/local/bin/ffprobe", "-v", "error", "-show_entries",
                                "format=duration", "-of", "default=nw=1:nk=1", str(frag)],
                               capture_output=True, text=True)
            if float(r.stdout.strip() or 0) < 6:
                for p in SCRATCH.glob(vid + ".*"):
                    p.unlink()
                frag = None
        except Exception:
            pass
    if frag is None:
        args = ["--download-sections", "*15-45"] if dur >= 50 else []
        subprocess.run([PY, "-m", "yt_dlp", "-f", "bv*[height<=480]/b[height<=480]"] + args +
                       ["-o", str(SCRATCH / (vid + ".%(ext)s")),
                        "https://www.youtube.com/watch?v=" + vid],
                       capture_output=True, text=True)
        frag = next((p for p in SCRATCH.glob(vid + ".*") if "_full" not in p.name), None)
    if frag is None:
        return None
    m = motion_score(frag)
    if m is not None and m < 0 and dur >= 50:
        subprocess.run([PY, "-m", "yt_dlp", "-f", "bv*[height<=480]/b[height<=480]",
                        "-o", str(SCRATCH / (vid + "_full.%(ext)s")),
                        "https://www.youtube.com/watch?v=" + vid],
                       capture_output=True, text=True)
        for p in SCRATCH.glob(vid + "_full.*"):
            m = motion_score(p)
            break
    return m


def main():
    seen = set(json.load(open(ROOT / "live_motion_audit_2026-11-04.json")))
    seen |= set(json.load(open(ROOT / "live_motion_sweep_2026-11-05.json")))
    tok = get_access_token()
    ch = get("https://www.googleapis.com/youtube/v3/channels?part=contentDetails&mine=true",
             tok)["items"][0]
    up = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    items, page = [], ""
    while True:
        d = get("https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50"
                "&playlistId=%s&pageToken=%s" % (up, page), tok)
        items += d.get("items", [])
        page = d.get("nextPageToken", "")
        if not page:
            break
    ids = [i["snippet"]["resourceId"]["videoId"] for i in items]
    vids = {}
    for k in range(0, len(ids), 50):
        d = get("https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails,status"
                "&id=" + ",".join(ids[k:k + 50]), tok)
        for v in d["items"]:
            vids[v["id"]] = v
    todo = []
    for vid, v in vids.items():
        if vid in seen or v["status"]["privacyStatus"] != "public":
            continue
        t = v["snippet"]["title"]
        if FARSI.search(t):
            continue                      # Ahmad's own Persian uploads
        dur = secs(v["contentDetails"]["duration"])
        if dur < 12:
            continue
        todo.append((vid, t, dur, v["snippet"]["publishedAt"][:10]))
    todo.sort(key=lambda r: r[3], reverse=True)
    print("measuring", len(todo), flush=True)
    rows = {}
    for vid, t, dur, pub in todo:
        m = measure(vid, dur)
        verdict = "?" if m is None else ("STATIC" if m < 4.0 else "ok")
        rows[vid] = {"title": t, "dur": dur, "published": pub,
                     "motion": None if m is None else round(m, 2), "verdict": verdict}
        print("%-6s %7s %4ss %s %s %s" % (verdict, rows[vid]["motion"], dur, pub, vid, t[:58]),
              flush=True)
        OUT.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    print("wrote", OUT, len(rows), flush=True)


if __name__ == "__main__":
    main()
