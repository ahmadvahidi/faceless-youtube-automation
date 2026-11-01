#!/usr/bin/env python3
"""Rebuild the deleted stock-photo topics as chart-based videos and upload."""
import sys
sys.path.insert(0, "/opt/data/workspace/faceless-youtube")
from send_to_group import _load_env
_load_env()
from daily_videos import generate_video, load_history, save_history
import yt_uploader as yt

REBUILD = [
    ("Inflation eroding cash purchasing power over decades",
     "Inflation's Hidden Bite: Why $1,000 Today May Be Half in 20 Years",
     "Your cash looks the same every year, but it quietly buys less and less. "
     "This is how inflation silently erodes your savings, and the simple moves "
     "to protect your money. Subscribe for more clear money breakdowns.\n\n"
     "#inflation #personalfinance #money #investing #buyingpower"),
    ("The sunk cost fallacy in investing and holding losing stocks",
     "The Sunk Cost Trap: Stop Clinging to Losing Stocks",
     "Why do we hold losing investments far too long? It is a wiring problem, "
     "not a math problem. Here is how the sunk cost trap works and how to break "
     "it. Subscribe for more money psychology.\n\n"
     "#investing #moneymindset #stocks #personalfinance #psychology"),
    ("Dollar-cost averaging explained simply",
     "The Brain Hack of Dollar-Cost Averaging",
     "Dollar-cost averaging turns market uncertainty into an advantage. This is "
     "why steady automatic investing beats trying to time the market. Subscribe "
     "for more simple investing principles.\n\n"
     "#investing #indexfunds #dollarcostaveraging #money #stocks"),
]

GROUP = "-1001821968102"
from send_to_group import api

ok = []
for i, (topic, title, desc) in enumerate(REBUILD):
    try:
        path = generate_video(topic, seed=8000 + i)
        vid = yt.upload_video(str(path), title, desc,
                              tags=["investing", "personal finance", "money",
                                    "wealth", "index funds"],
                              category_id="27", privacy="public")
        url = f"https://youtube.com/watch?v={vid}"
        print(f"[{i+1}/{len(REBUILD)}] UPLOADED {url}", flush=True)
        ok.append(url)
        try:
            api("sendMessage", {"chat_id": GROUP,
                                "text": f"✅ آپلود شد به یوتیوب\n\n🎬 {title}\n🔗 {url}"})
        except Exception:
            pass
    except Exception as e:
        print(f"[{i+1}/{len(REBUILD)}] FAILED: {e}", flush=True)

print("\n=== DONE ===")
for u in ok:
    print(u)
