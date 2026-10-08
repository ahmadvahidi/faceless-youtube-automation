#!/usr/bin/env python3
"""
Send generated videos to the Uploader group with title + description.

The YouTube-uploader bot in the group reads whatever is posted; sending the
video with its title/description as the caption is the contract here.

Usage:
  python send_to_group.py <video_path> <title> <description>
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

TOKEN = None
GROUP = os.environ.get("TELEGRAM_GROUP_ID", "-1001821968102")


def _load_env():
    envf = Path(__file__).resolve().parent / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)
    global TOKEN
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")


def api(method, payload):
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def send_video(path: str, title: str, description: str):
    caption = f"{title}\n\n{description}"
    # Telegram requires multipart for files
    boundary = "----HermesBoundary7MA4YWxk"
    with open(path, "rb") as f:
        video_bytes = f.read()

    body = b""
    def part(name, value, filename=None, ctype=None):
        nonlocal body
        body += f"--{boundary}\r\n".encode()
        disp = f'Content-Disposition: form-data; name="{name}"'
        if filename:
            disp += f'; filename="{filename}"'
            body += (disp + "\r\n").encode()
            body += f"Content-Type: {ctype}\r\n\r\n".encode()
            body += value
            body += b"\r\n"
        else:
            body += (disp + "\r\n\r\n").encode()
            body += value.encode() + b"\r\n"

    part("chat_id", GROUP)
    part("caption", caption)
    part("video", video_bytes, filename=os.path.basename(path),
         ctype="video/mp4")
    body += f"--{boundary}--\r\n".encode()

    url = f"https://api.telegram.org/bot{TOKEN}/sendVideo"
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        res = json.load(r)
    if not res.get("ok"):
        raise RuntimeError(f"sendVideo failed: {res}")
    return res


if __name__ == "__main__":
    _load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    TOKEN = token
    path, title, desc = sys.argv[1], sys.argv[2], sys.argv[3]
    res = send_video(path, title, desc)
    print(json.dumps(res, ensure_ascii=False)[:500])
