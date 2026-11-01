#!/usr/bin/env python3
"""Resume the premium rebuild across days (YouTube daily upload cap).

Tracks progress in `premium_done.json` (list of job indices already uploaded as
PREMIUM), so it never confuses an old simple-chart upload with a premium one.
Each run rebuilds+uploads the next not-yet-premium jobs and stops cleanly when
the daily upload cap is hit. Safe to re-run; run daily until it says "complete".
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/opt/data/workspace/faceless-youtube")
from send_to_group import _load_env
_load_env()

import yt_uploader as yt
from yt_publish import publish
from rebuild_premium import JOBS
from send_to_group import api

ROOT = Path("/opt/data/workspace/faceless-youtube")
STATE = ROOT / "premium_done.json"
GROUP = "-1001821968102"


def load_done():
    if STATE.exists():
        try:
            d = json.loads(STATE.read_text())
            return set(d.get("done", []))
        except Exception:
            return set()
    # jobs 0 and 1 already uploaded as premium in the first run
    return {0, 1}


def save_done(done):
    STATE.write_text(json.dumps({"done": sorted(done)}, indent=2))


def notify(t):
    try:
        api("sendMessage", {"chat_id": GROUP, "text": t})
    except Exception as e:
        print(f"[notify] {e}", flush=True)


def delete_video(vid):
    import urllib.request
    req = urllib.request.Request(
        f"https://www.googleapis.com/youtube/v3/videos?id={vid}", method="DELETE")
    req.add_header("Authorization", "Bearer " + yt.get_access_token())
    try:
        urllib.request.urlopen(req)
        return True
    except Exception as e:
        print(f"[delete] {vid}: {e}", flush=True)
        return False


def main():
    done = load_done()
    todo = [(i, j) for i, j in enumerate(JOBS) if i not in done]
    print(f"[pending] {len(todo)} of {len(JOBS)} jobs not yet premium", flush=True)
    if not todo:
        print("nothing to do — channel fully rebuilt", flush=True)
        return

    for n, (idx, (topic, title, desc, old_id, kind)) in enumerate(todo):
        print(f"\n=== [{n+1}/{len(todo)}] {kind} :: {title[:45]} ===", flush=True)
        try:
            if kind == "long":
                from longform_pipeline import build_longform
                path = build_longform(topic, n_sections=14)
            else:
                from daily_videos import generate_video
                path = generate_video(topic, seed=7000 + idx)
        except Exception as e:
            print(f"[build FAILED] {title[:40]}: {e}", flush=True)
            continue

        try:
            vid = publish(str(path), title, desc, privacy="public")
        except RuntimeError as e:
            if "UploadLimitExceeded" in str(e):
                notify(f"⏳ سقف آپلود روزانه پر شد. {len(todo) - n} ویدیو مونده — "
                       f"فردا خودکار آپلود میشن.")
                print("[cap] daily upload cap hit — stopping for today", flush=True)
                return
            print(f"[upload FAILED] {title[:40]}: {e}", flush=True)
            continue

        url = f"https://youtube.com/watch?v={vid}"
        print(f"[uploaded] {url}", flush=True)
        if old_id:
            delete_video(old_id)
        done.add(idx)
        save_done(done)
        notify(f"♻️ بازسازی شد (ظاهر پرمیوم)\n\n🎬 {title}\n🔗 {url}")

    print("\n[pending run complete]", flush=True)


if __name__ == "__main__":
    main()
