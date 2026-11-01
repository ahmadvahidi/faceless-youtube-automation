#!/usr/bin/env python3
"""Diagnose an upload 400 by capturing the full response body."""
import json, sys, urllib.request, urllib.error
sys.path.insert(0, "/opt/data/workspace/faceless-youtube")
import yt_uploader as yt

tok = yt.get_access_token()
body = {
    "snippet": {
        "title": "The Two-Week Rule: Trick Your Brain Into Spending Less",
        "description": "test",
        "categoryId": "27",
    },
    "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
}
url = ("https://www.googleapis.com/upload/youtube/v3/videos"
       "?uploadType=resumable&part=snippet,status")
req = urllib.request.Request(url, data=json.dumps(body).encode(),
                             headers={"Authorization": f"Bearer {tok}",
                                      "Content-Type": "application/json",
                                      "X-Upload-Content-Type": "video/mp4"})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print("INIT OK:", r.status)
except urllib.error.HTTPError as e:
    print("HTTP", e.code)
    print(e.read().decode()[:800])
