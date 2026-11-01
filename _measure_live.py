#!/usr/bin/env python
"""Measure LIVE motion for a list of video ids (cached fragments reused)."""
import sys
from pathlib import Path

ROOT = "/opt/data/workspace/faceless-youtube"
sys.path.insert(0, ROOT)
from send_to_group import _load_env  # noqa

_load_env()
from upgrade_longform_motion import live_motion  # noqa

ids = sys.argv[1:]
for vid in ids:
    m = live_motion(vid)
    print("%s  motion=%s" % (vid, "UNMEASURABLE" if m is None else "%.2f%%" % m),
          flush=True)
