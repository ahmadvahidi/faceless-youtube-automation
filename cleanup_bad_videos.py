#!/usr/bin/env python3
"""Delete the stock-photo finance videos (bad images) + the pi test video.
Keeps all chart-based (longform) and Manim math videos."""
import sys
sys.path.insert(0, "/opt/data/workspace/faceless-youtube")
import yt_uploader as y
import urllib.request, urllib.error

# stock-photo finance videos (bad images -> delete) + the [TEST] video
DELETE = [
    "w2Yj4sBpKV4",  # credit card wealth (Oct 8)
    "JVdY7jKju2I",  # renting costlier (Oct 9)
    "bPG0-sJP7RE",  # tiny daily savings (Oct 9)
    "wPhHd32SX_8",  # hidden taxes (Oct 9)
    "uDqhg7y5kJs",  # high-interest savings (Oct 9)
    "eYKPl_KNItA",  # 30-day pause (Oct 10)
    "VtgKVmyNcTg",  # commodities (Oct 10)
    "uASm1AJMPDs",  # dollar-cost averaging (Oct 10)
    "f_LtoetfdU4",  # inflation's hidden bite (Oct 12)
    "RyvY16AEEeU",  # sunk cost trap (Oct 12)
    "r0C6WtmDAKc",  # pi [TEST] video
]

tok = y.get_access_token()
for vid in DELETE:
    req = urllib.request.Request(
        f"https://www.googleapis.com/youtube/v3/videos?id={vid}", method="DELETE")
    req.add_header("Authorization", "Bearer " + tok)
    try:
        urllib.request.urlopen(req)
        print(f"deleted {vid}")
    except urllib.error.HTTPError as e:
        print(f"{vid}: http {e.code} {e.read().decode()[:120]}")
