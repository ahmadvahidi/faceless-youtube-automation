#!/usr/bin/env python
"""Where is the motion? Print a per-time-window motion profile of a video.

Decodes a small grayscale stream (graphic area only, captions excluded) and prints,
for every 2 s, the % of pixels that changed by >12 levels between that frame and the
one 2 s later — the same metric verify_video.motion_score takes the median of, but
shown across the timeline so a static stretch is visible.

Usage: python _motion_profile.py <video>
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

path = sys.argv[1]
W = 270
raw = Path(tempfile.mkdtemp()) / "g.raw"
subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf",
                f"crop=iw:ih*0.70:0:0,scale={W}:-2,fps=4,format=gray",
                "-f", "rawvideo", str(raw)], check=True)
buf = np.frombuffer(raw.read_bytes(), dtype=np.uint8)
# rows = height: total/(W) frames of W*H; H unknown -> derive from aspect 16:9 crop
H = int(round(W * 0.70 * 9 / 16))
n = len(buf) // (W * H)
frames = buf[:n * W * H].reshape(n, H, W).astype(np.int16)
print(f"{path}: {n} frames @4fps ({n/4:.0f}s), {W}x{H}")
step = 8  # 2 s at 4 fps
vals = []
for i in range(0, n - step, step):
    d = (np.abs(frames[i + step] - frames[i]) > 12).mean() * 100
    vals.append((i / 4.0, d))
    print(f"  t={i/4.0:7.2f}s  motion {d:5.2f}%")
if vals:
    arr = np.array([v for _, v in vals])
    print(f"median {np.median(arr):.2f}%  min {arr.min():.2f}%  max {arr.max():.2f}%")
