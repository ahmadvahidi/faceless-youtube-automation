#!/usr/bin/env python
"""Ad-hoc: measure LIVE motion for a list of video ids (fresh fragments)."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/opt/data/workspace/faceless-youtube")
from send_to_group import _load_env  # noqa
_load_env()
from verify_video import motion_score  # noqa

SCRATCH = Path("/opt/data/cache/scratch/live_motion")
SCRATCH.mkdir(parents=True, exist_ok=True)
PY = "/opt/data/skills/.venv/bin/python"


def measure(vid):
    for p in SCRATCH.glob(vid + ".*"):
        p.unlink()
    subprocess.run([PY, "-m", "yt_dlp", "-f", "bv*[height<=480]/b[height<=480]",
                    "--download-sections", "*15-45",
                    "-o", str(SCRATCH / (vid + ".%(ext)s")),
                    "https://www.youtube.com/watch?v=" + vid],
                   capture_output=True, text=True)
    frag = next(SCRATCH.glob(vid + ".*"), None)
    if frag is None:
        return None
    m = motion_score(frag)
    if m is not None and m < 0:
        for p in SCRATCH.glob(vid + ".*"):
            p.unlink()
        subprocess.run([PY, "-m", "yt_dlp", "-f", "bv*[height<=480]/b[height<=480]",
                        "-o", str(SCRATCH / (vid + "_full.%(ext)s")),
                        "https://www.youtube.com/watch?v=" + vid],
                       capture_output=True, text=True)
        full = next(SCRATCH.glob(vid + "_full.*"), None)
        if full is not None:
            m = motion_score(full)
    return m


if __name__ == "__main__":
    for vid in sys.argv[1:]:
        m = measure(vid)
        verdict = "UNMEASURED" if m is None or m < 0 else ("STATIC" if m < 4.0 else "ok")
        print(f"{vid}  motion={'None' if m is None else round(m, 2)}  {verdict}", flush=True)
