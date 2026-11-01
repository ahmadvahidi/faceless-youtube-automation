#!/usr/bin/env python3
"""
Daily pipeline: build N videos then upload each DIRECTLY to YouTube.

Runs end-to-end with zero human input:
  pick trending topics (dedup against history) -> generate videos
  -> upload to YouTube -> notify group -> record topic in history

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

from daily_videos import pick_topics, generate_video, load_history, save_history
import yt_uploader as yt
from send_to_group import api
from housekeeping import clean_work, prune_keep_newest, OUT, ASSETS, KEEP_VIDEOS, KEEP_ASSETS

GROUP_ID = "-1001821968102"


def notify_group(text: str):
    try:
        api("sendMessage", {"chat_id": GROUP_ID, "text": text})
    except Exception as e:
        print(f"[notify] failed: {e}", flush=True)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2

    topics = pick_topics(n)
    print(f"[topics] {len(topics)} chosen", flush=True)

    report = []
    for i, t in enumerate(topics):
        try:
            path = generate_video(t["topic"], seed=1000 + i,
                                  image_query=t.get("image_query"))
            print(f"[{i+1}/{n}] built {path}", flush=True)

            # upload directly to YouTube (with custom thumbnail + SEO tags)
            from yt_publish import publish, POOLS
            vid_id = publish(
                str(path), t["title"], t["description"],
                tags=t.get("tags", []),
                base_tags=POOLS["finance"],   # this line is finance, not the channel's maths pool
                privacy="public",
            )
            url = f"https://youtube.com/watch?v={vid_id}"
            print(f"[{i+1}/{n}] UPLOADED: {url}", flush=True)

            # notify the group
            notify_group(f"✅ آپلود شد به یوتیوب\n\n🎬 {t['title']}\n🔗 {url}")

            # record this topic so it's never generated again
            history = load_history()
            history.append({"topic": t.get("topic", ""), "title": t.get("title", "")})
            save_history(history)

            report.append({"title": t["title"], "status": "uploaded", "url": url})
        except Exception as e:
            print(f"[{i+1}/{n}] FAILED: {e}", flush=True)
            report.append({"title": t.get("title", "?"), "status": f"error: {e}"})
            # ALWAYS tell the user about a failure — silence looks like success.
            notify_group(f"⚠️ آپلود نشد: {t.get('title', '?')[:50]}\n{e}")

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
