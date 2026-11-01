#!/usr/bin/env python
"""Print snippet/description/status for given video ids on DOPEAK."""
import json
import sys
import urllib.request

sys.path.insert(0, "/opt/data/workspace/faceless-youtube")
from send_to_group import _load_env  # noqa

_load_env()
from yt_uploader import get_access_token  # noqa

tok = get_access_token()
url = ("https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails,"
       "statistics,status&id=" + ",".join(sys.argv[1:]))
d = json.load(urllib.request.urlopen(urllib.request.Request(
    url, headers={"Authorization": "Bearer " + tok})))
for v in d.get("items", []):
    s = v["snippet"]
    print("%s | %s | %s | views=%s | tags=%s" % (
        v["id"], v["contentDetails"]["duration"], s["publishedAt"][:10],
        v["statistics"].get("viewCount"), (s.get("tags") or [])[:5]))
    print("   TITLE:", s["title"])
    print("   DESC :", s["description"][:200].replace("\n", " / "))
    print("   PRIV :", v["status"]["privacyStatus"], "| dur", v["contentDetails"]["duration"])
