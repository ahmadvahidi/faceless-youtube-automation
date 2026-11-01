#!/usr/bin/env python
"""Download a short section of each LIVE long-form video and measure its motion.

Gives real, published-file evidence of static vs moving (not a local-build guess).
Usage: python _live_motion.py <videoId> [<videoId> ...]
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/opt/data/workspace/faceless-youtube")
from verify_video import motion_score  # noqa: E402

SCRATCH = Path("/opt/data/cache/scratch/live_motion")
SCRATCH.mkdir(parents=True, exist_ok=True)

for vid in sys.argv[1:]:
    out = SCRATCH / (vid + ".mp4")
    if not out.exists():
        cmd = ["/opt/data/skills/.venv/bin/python", "-m", "yt_dlp",
               "-f", "bv*[height<=480]/b[height<=480]",
               "--download-sections", "*15-45",
               "-o", str(SCRATCH / (vid + ".%(ext)s")),
               "https://www.youtube.com/watch?v=" + vid]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if not out.exists():
            print(f"{vid}: DOWNLOAD FAILED {r.stderr.strip()[-160:]}")
            continue
    m = motion_score(out)
    verdict = "STATIC" if m < 4.0 else "moving"
    print(f"{vid}: motion {m:.2f}%  -> {verdict}", flush=True)
