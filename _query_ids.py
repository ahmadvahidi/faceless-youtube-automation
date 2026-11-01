#!/usr/bin/env python
"""Query one or more video ids on this project's channel: id -> title/status or GONE."""
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from send_to_group import _load_env  # noqa: E402
_load_env()
from yt_uploader import get_access_token  # noqa: E402

tok = get_access_token()
ids = sys.argv[1:]
d = json.load(urllib.request.urlopen(urllib.request.Request(
    "https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails,status&id="
    + ",".join(ids), headers={"Authorization": "Bearer " + tok})))
found = {v["id"]: v for v in d.get("items", [])}
for vid in ids:
    v = found.get(vid)
    if not v:
        print(f"{vid}: GONE (no item returned)")
    else:
        print(f"{vid}: LIVE | {v['contentDetails']['duration']} | {v['status']['privacyStatus']}"
              f" | {v['snippet']['title'][:60]}")
