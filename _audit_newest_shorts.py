#!/usr/bin/env python
"""Audit motion of the newest public SHORTS on a channel, from the LIVE files."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
N = int(sys.argv[2]) if len(sys.argv) > 2 else 25
sys.path.insert(0, str(ROOT))
sys.path.insert(0, "/opt/data/workspace/cs-videos")
from verify_video import motion_score  # noqa

inv = json.load(open(ROOT / "_live_inventory.json"))
pub = [v for v in inv if v.get("privacy") == "public" and v.get("dur", 9999) < 180]
pub.sort(key=lambda v: v["published"], reverse=True)
pub = pub[:N]
CACHE = Path("/opt/data/cache/scratch/live_motion")
CACHE.mkdir(parents=True, exist_ok=True)
bad = []
for v in pub:
    frag = next(CACHE.glob(v["id"] + ".mp4"), None)
    if frag is None:
        subprocess.run(["/opt/data/skills/.venv/bin/python", "-m", "yt_dlp",
                        "-f", "bv*[height<=480]/b[height<=480]", "--no-progress",
                        "-o", str(CACHE / (v["id"] + ".%(ext)s")),
                        "https://www.youtube.com/watch?v=" + v["id"]],
                       capture_output=True, text=True)
        frag = next(CACHE.glob(v["id"] + ".mp4"), None)
    if frag is None:
        print(f"?      {v['id']} download failed  {v['title'][:55]}")
        continue
    m = motion_score(frag)
    flag = "STATIC" if (m is not None and m >= 0 and m < 4.0) else "ok"
    if flag == "STATIC":
        bad.append(v)
    val = "None" if m is None else f"{m:.2f}"
    print(f"{flag:6} {v['id']} {v['dur']:>3}s {val:>6}  {v['title'][:60]}", flush=True)
print("STATIC COUNT:", len(bad), "of", len(pub))
for v in bad:
    print("  ->", v["id"], v["dur"], v["title"])
