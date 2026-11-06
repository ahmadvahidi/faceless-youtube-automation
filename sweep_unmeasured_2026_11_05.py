"""Measure motion on every never-measured DOPEAK video that could be OURS.

Selection: public, 12-140 s (Shorts + short-form), ASCII title (skips Ahmad's own
Persian uploads), not already in live_motion_audit_2026-11-04.json.
Whole-file download when the clip is under 50 s — a *15-45 section on a short
yields a stub that reads -1.00 (measurement failure, not a static verdict).
"""
import json
import re
import subprocess
import sys
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
OUT = ROOT / "live_motion_sweep_2026-11-05.json"


def api(tok, url):
    import urllib.request
    return json.load(urllib.request.urlopen(
        urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})))


def secs(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
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
                        "published": v["snippet"]["publishedAt"][:10],
                        "dur": secs(v["contentDetails"]["duration"])})
    return out


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
        full = SCRATCH / (vid + "_full.mp4")
        subprocess.run([PY, "-m", "yt_dlp", "-f", "bv*[height<=480]/b[height<=480]",
                        "-o", str(SCRATCH / (vid + "_full.%(ext)s")),
                        "https://www.youtube.com/watch?v=" + vid],
                       capture_output=True, text=True)
        for p in SCRATCH.glob(vid + "_full.*"):
            m = motion_score(p)
            break
    return m


def main():
    aud = json.load(open(ROOT / "live_motion_audit_2026-11-04.json"))
    tok = get_access_token()
    vs = videos(tok)
    todo = []
    for v in vs:
        if v["id"] in aud:
            continue
        if not (12 <= v["dur"] <= 140):
            continue
        if not v["title"].isascii():
            continue
        todo.append(v)
    todo.sort(key=lambda v: (v["published"] > "2026-10-15", v["published"]), reverse=True)
    print("never measured:", len(todo), flush=True)
    rows = {}
    for v in todo:
        m = measure(v["id"], v["dur"])
        verdict = "?" if m is None else ("STATIC" if m < 4.0 else "ok")
        rows[v["id"]] = {**v, "motion": None if m is None else round(m, 2), "verdict": verdict}
        print("%-6s %7s %4ss %s %s %s" % (verdict, rows[v["id"]]["motion"], v["dur"],
                                          v["published"], v["id"], v["title"][:58]), flush=True)
        OUT.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    print("wrote", OUT, len(rows), flush=True)


if __name__ == "__main__":
    main()
