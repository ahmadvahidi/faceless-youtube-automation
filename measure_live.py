#!/usr/bin/env python
"""Measure motion of LIVE videos (per channel, from the API) — the upgrade agent's gate.

Usage: python measure_live.py <channel: cs|dopeak> <video_id> [<video_id> ...]
Downloads a 30 s section (full file when the section is unusable) into
cache/scratch/live_motion and prints motion % per id, appending to _motion_measured.json.
"""
import json
import subprocess
import sys
from pathlib import Path

SCRATCH = Path("/opt/data/cache/scratch/live_motion")
SCRATCH.mkdir(parents=True, exist_ok=True)
PY = "/opt/data/skills/.venv/bin/python"
OUTF = Path("/opt/data/workspace/faceless-youtube/_motion_measured.json")

sys.path.insert(0, "/opt/data/workspace/cs-videos")
from verify_video import motion_score  # noqa: E402


def fetch(vid: str, full: bool):
    tag = vid + ("_full" if full else "")
    frag = next(SCRATCH.glob(tag + ".*"), None)
    if frag is not None and frag.stat().st_size > 20000:
        return frag
    cmd = [PY, "-m", "yt_dlp", "-f", "bv*[height<=480]/b[height<=480]"]
    if not full:
        cmd += ["--download-sections", "*15-45"]
    cmd += ["-o", str(SCRATCH / (tag + ".%(ext)s")), "https://www.youtube.com/watch?v=" + vid]
    subprocess.run(cmd, capture_output=True, text=True)
    return next(SCRATCH.glob(tag + ".*"), None)


def measure(vid: str):
    frag = fetch(vid, False)
    if frag is None:
        return None
    m = motion_score(frag)
    # A stub cut by *15-45 on a <20 s Short is 5-7 s long and reads exactly -1.00:
    # that is an UNMEASURABLE, never a verdict. Delete it and measure the whole file.
    if m is None or m < 0:
        try:
            frag.unlink()
        except Exception:
            pass
        full = fetch(vid, True)
        if full is not None:
            m = motion_score(full)
    return m


def main():
    ids = sys.argv[2:]
    res = {}
    try:
        res = json.loads(OUTF.read_text())
    except Exception:
        res = {}
    for vid in ids:
        m = measure(vid)
        print(f"{vid}  motion={m if m is None else round(m,2)}", flush=True)
        if m is not None:
            res[vid] = round(m, 2)
    OUTF.write_text(json.dumps(res, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
