#!/usr/bin/env python3
"""
Daily LONG-FORM finance video: pick a fresh topic -> build an 8-12 min
animated-chart video -> VERIFY it is YouTube-playable -> upload direct ->
notify the group -> record topic.

This is the revenue path (long-form finance = high RPM + mid-roll ads).
One video per day keeps a fresh channel under its daily upload cap while
still making the high-value content.

Usage:
  python run_longform_daily.py [n_sections]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from send_to_group import _load_env
_load_env()

from daily_videos import pick_topics, load_history, save_history
from longform_pipeline import build_longform, mark_seed_published
import yt_uploader as yt
from send_to_group import api
from verify_video import main as verify_main

GROUP_ID = "-1001821968102"


def notify_group(text: str):
    try:
        api("sendMessage", {"chat_id": GROUP_ID, "text": text})
    except Exception as e:
        print(f"[notify] failed: {e}", flush=True)


def pick_one_fresh_topic():
    """Get exactly one non-duplicate finance topic (long-form sized)."""
    topics = pick_topics(1)
    if not topics:
        raise RuntimeError("no topic returned")
    return topics[0]


def main():
    n_sections = int(sys.argv[1]) if len(sys.argv) > 1 else 14

    topic = pick_one_fresh_topic()
    title = topic.get("title", topic.get("topic", "Finance"))
    subject = topic.get("topic", title)
    desc = topic.get("description", "")
    print(f"[topic] {subject!r} -> {title!r}", flush=True)

    try:
        # Build the long-form video (animated charts, not stock photos).
        path = build_longform(subject, n_sections=n_sections)
        print(f"[built] {path}", flush=True)

        # VERIFY it will actually play on YouTube before uploading.
        rc = verify_main(str(path))
        if rc != 0:
            raise RuntimeError("video failed playability check — not uploaded")

        # Upload direct to the channel.
        # Upload WITH a custom thumbnail (biggest CTR lever) + SEO tags.
        from yt_publish import publish, POOLS
        vid_id = publish(
            str(path), title, desc,
            tags=["investing", "index funds", "wealth", "personal finance",
                  "money", "stock market"],
            base_tags=POOLS["finance"],   # the finance long-form keeps the finance pool
            privacy="public",
        )
        url = f"https://youtube.com/watch?v={vid_id}"
        print(f"[uploaded] {url}", flush=True)

        notify_group(
            f"✅ ویدیوی لانگ‌فرم آپلود شد به یوتیوب\n\n"
            f"🎬 {title}\n🔗 {url}"
        )

        # Record topic so it is never repeated.
        history = load_history()
        history.append({"topic": subject, "title": title})
        save_history(history)
        # variation engine: pin the palette/music seed this build shipped with, so the next
        # published video cannot reuse this one's look or music bed.
        mark_seed_published()

        print(f"\n=== DONE ===\n{title}\n{url}", flush=True)

    except Exception as e:
        print(f"[FAILED] {e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
