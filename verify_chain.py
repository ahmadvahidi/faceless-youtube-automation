#!/usr/bin/env python3
"""End-to-end smoke test for the faceless-video chain (no YouTube upload).

Verifies: topic picking -> LLM script -> TTS -> image fetch -> render -> mp4.
Exit 0 with VERIFY_OK on success. Safe to re-run; output goes to out/video_9001.mp4.
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from send_to_group import _load_env
_load_env()

import daily_videos as d
from llm_client import providers

t0 = time.time()
print("[0] providers:", [(p[0], p[3]) for p in providers()], flush=True)

print("[1] picking a topic...", flush=True)
topics = d.pick_topics(1)
t = topics[0]
print(f"[2] topic: {t.get('title')}", flush=True)

print("[3] generating video (script -> TTS -> images -> render)...", flush=True)
path = d.generate_video(t["topic"], seed=9001, image_query=t.get("image_query"))
size = os.path.getsize(path)
print(f"[4] GENERATED {path} ({size/1e6:.1f} MB) in {time.time()-t0:.0f}s", flush=True)
print("VERIFY_OK", flush=True)
