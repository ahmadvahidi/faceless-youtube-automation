#!/usr/bin/env python
"""Publish an ALREADY-BUILT replacement and remove the static copy it supersedes.

Use when a build exists on disk but the upload gate refused it for lack of motion and the
motion layer has since been applied. Keeps the standing rule: publish FIRST, and delete the
old id ONLY after the new id exists and resolves.

Usage: python publish_prepared.py <video_path> <old_video_id>
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path("/opt/data/workspace/faceless-youtube")
sys.path.insert(0, str(ROOT))
from send_to_group import _load_env  # noqa: E402

_load_env()
from yt_publish import publish  # noqa: E402
from yt_uploader import get_access_token  # noqa: E402

path = Path(sys.argv[1])
old = sys.argv[2]
token = get_access_token()


def get(url):
    return json.load(urllib.request.urlopen(
        urllib.request.Request(url, headers={"Authorization": "Bearer " + token})))


d = get("https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails&id=" + old)
if not d.get("items"):
    print(f"{old}: not live - nothing to replace")
    sys.exit(1)
sn = d["items"][0]["snippet"]
title, desc = sn["title"], sn["description"]
dur = d["items"][0]["contentDetails"]["duration"]
print(f"replacing {old} ({dur}) :: {title}", flush=True)

new_id = publish(str(path), title, desc, privacy="public", replace_of=old)
print(f"NEW https://youtube.com/watch?v={new_id}", flush=True)

alive = get("https://www.googleapis.com/youtube/v3/videos?part=id&id=" + new_id).get("items")
if not alive:
    print("new id does not resolve yet - NOT deleting the old copy", flush=True)
    sys.exit(2)

req = urllib.request.Request("https://www.googleapis.com/youtube/v3/videos?id=" + old,
                             method="DELETE")
req.add_header("Authorization", "Bearer " + token)
urllib.request.urlopen(req)
gone = True
for _ in range(8):
    time.sleep(5)
    gone = not get("https://www.googleapis.com/youtube/v3/videos?part=id&id=" + old).get("items")
    if gone:
        break
print(f"OLD {old} :: {'GONE' if gone else 'STILL RESOLVING'} | removed {title} ({dur})",
      flush=True)
