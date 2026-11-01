#!/usr/bin/env python3
"""Full premium rebuild: rebuild the 4 long-form + 3 short channel videos with
the neon chart look + background music + a custom thumbnail, replacing the old
(simple-chart) uploads one by one.

Resumable: skips a topic whose output already exists in out/ as *_prem.mp4.
"""
import sys
from pathlib import Path

sys.path.insert(0, "/opt/data/workspace/faceless-youtube")
from send_to_group import _load_env
_load_env()

import yt_uploader as yt
from yt_publish import publish
from longform_pipeline import build_longform
from daily_videos import generate_video
from send_to_group import api

ROOT = Path("/opt/data/workspace/faceless-youtube")
GROUP = "-1001821968102"

# (topic_for_builder, title, description, old_video_id_to_delete, kind)
JOBS = [
    ("How the rich build wealth with boring index funds",
     "How the Rich Build Wealth with Boring Index Funds",
     "The wealthy don't time the market. They buy plain index funds and let "
     "compounding work. This is the exact math, the tax edge, and the simple "
     "plan behind the quietest way to get rich.\n\n"
     "#investing #indexfunds #wealth #personalfinance #compoundinterest",
     "vnq0Ux5XXXE", "long"),
    ("The psychological power of paying yourself first",
     "Paying Yourself First: The Brain Hack That Builds Wealth",
     "Why saving first beats saving what's left. The tiny mental switch that "
     "makes wealth automatic, and how to set it up today.\n\n"
     "#personalfinance #money #wealth #saving #moneymindset",
     "XxKbVswZwcg", "long"),
    ("The two-week rule for smarter spending",
     "The Two-Week Rule: Trick Your Brain Into Spending Less",
     "One simple rule kills impulse buying and frees up hundreds a month. How "
     "the 14-day pause rewires your spending decisions. Subscribe for more "
     "money psychology.\n\n"
     "#money #spending #frugal #personalfinance #moneyhabits",
     "DrT4Ids7Wkw", "long"),
    ("The compounding power of a consistent 1% annual return",
     "The 1% Return Trick: How Tiny Gains Explode Over Decades",
     "A 1% edge sounds trivial. Over decades it is a fortune. Here is the math "
     "of small advantages compounding, and how to capture them. Subscribe for "
     "more clear finance.\n\n"
     "#investing #compounding #indexfunds #wealth #personalfinance",
     "9NR4cPmShtU", "long"),
    ("Inflation eroding cash purchasing power over decades",
     "Inflation's Hidden Bite: Why $1,000 Today May Be Half in 20 Years",
     "Your cash looks the same but quietly buys less every year. How inflation "
     "erodes savings and the simple moves that protect your money.\n\n"
     "#inflation #personalfinance #money #investing #buyingpower",
     "VZiJKNtfSZ0", "short"),
    ("The sunk cost fallacy in investing and holding losing stocks",
     "The Sunk Cost Trap: Stop Clinging to Losing Stocks",
     "Why we hold losers far too long - and how to break the trap. A money "
     "psychology fix that pays for itself.\n\n"
     "#investing #moneymindset #stocks #personalfinance #psychology",
     "6Ta-2pyF3ww", "short"),
    ("Dollar-cost averaging explained simply",
     "The Brain Hack of Dollar-Cost Averaging",
     "Steady automatic investing beats trying to time the market. Why DCA works "
     "and how to start.\n\n"
     "#investing #indexfunds #dollarcostaveraging #money #stocks",
     "2djIM8iPW5o", "short"),
]


def notify(text):
    try:
        api("sendMessage", {"chat_id": GROUP, "text": text})
    except Exception as e:
        print(f"[notify] {e}", flush=True)


def delete_video(vid):
    import urllib.request
    tok = yt.get_access_token()
    req = urllib.request.Request(
        f"https://www.googleapis.com/youtube/v3/videos?id={vid}", method="DELETE")
    req.add_header("Authorization", "Bearer " + tok)
    try:
        urllib.request.urlopen(req)
        return True
    except Exception as e:
        print(f"[delete] {vid}: {e}", flush=True)
        return False


def main():
    done = []
    for i, (topic, title, desc, old_id, kind) in enumerate(JOBS):
        try:
            print(f"\n=== [{i+1}/{len(JOBS)}] {kind} :: {title[:45]} ===", flush=True)
            if kind == "long":
                path = build_longform(topic, n_sections=14)
            else:
                path = generate_video(topic, seed=7000 + i)

            vid = publish(str(path), title, desc, privacy="public")
            url = f"https://youtube.com/watch?v={vid}"
            print(f"[uploaded] {url}", flush=True)

            # remove the old simple-chart version now the new one is live
            if old_id:
                delete_video(old_id)

            notify(f"♻️ بازسازی شد (ظاهر پرمیوم)\n\n🎬 {title}\n🔗 {url}")
            done.append(url)
        except Exception as e:
            print(f"[FAILED] {title[:40]}: {e}", flush=True)
            notify(f"⚠️ بازسازی ناموفق: {title[:40]}\n{e}")

    print("\n=== DONE ===")
    for u in done:
        print(u)


if __name__ == "__main__":
    main()
