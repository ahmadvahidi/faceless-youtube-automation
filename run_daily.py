#!/usr/bin/env python3
"""
Daily pipeline: build N videos then send each to the Uploader group.

Runs end-to-end with zero human input:
  pick trending topics -> generate videos -> send to group with title/description

Usage:
  python run_daily.py 2
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Load .env FIRST so module-level constants (LLM_API_KEY) are set at import time.
from send_to_group import _load_env
_load_env()

from daily_videos import pick_topics, generate_video
from send_to_group import send_video
from housekeeping import clean_work, prune_keep_newest, OUT, ASSETS, KEEP_VIDEOS, KEEP_ASSETS


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2

    topics = pick_topics(n)
    print(f"[topics] {len(topics)} chosen", flush=True)

    report = []
    for i, t in enumerate(topics):
        try:
            path = generate_video(t["topic"], seed=1000 + i)
            print(f"[{i+1}/{n}] built {path}", flush=True)

            send_video(str(path), t["title"], t["description"])
            print(f"[{i+1}/{n}] sent to group", flush=True)

            report.append({"title": t["title"], "status": "sent"})
        except Exception as e:
            print(f"[{i+1}/{n}] FAILED: {e}", flush=True)
            report.append({"title": t.get("title", "?"), "status": f"error: {e}"})

    # self-manage: clean intermediates + prune old outputs
    try:
        w = clean_work()
        o = prune_keep_newest(OUT, KEEP_VIDEOS)
        a = prune_keep_newest(ASSETS, KEEP_ASSETS)
        print(f"[housekeeping] work -{w}, out -{o}, assets -{a}", flush=True)
    except Exception as e:
        print(f"[housekeeping] skipped: {e}", flush=True)

    print("\n=== SUMMARY ===")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
