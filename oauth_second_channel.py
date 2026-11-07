#!/usr/bin/env python3
"""Authorize a SECOND YouTube channel and store its refresh token.

Usage:
  python oauth_second_channel.py link      # prints the consent URL to open
  python oauth_second_channel.py exchange "<pasted redirect url or code>"
  python oauth_second_channel.py verify    # lists the channel the new token sees

Why the paste step: Google killed the OOB flow in 2022, and this box has no public
HTTPS callback. The loopback redirect therefore fails to load in the browser — that is
expected — and the ?code=... in the address bar is what we exchange here.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ENV = Path("/opt/data/workspace/faceless-youtube/.env")
TOKEN_FILE = Path("/opt/data/workspace/faceless-youtube/token_second_channel.json")
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
REDIRECT = "http://localhost:8765"


def env(key: str) -> str:
    for line in ENV.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def link() -> None:
    q = urllib.parse.urlencode({
        "client_id": env("GOOGLE_CLIENT_ID"),
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    })
    print("https://accounts.google.com/o/oauth2/v2/auth?" + q)


def exchange(raw: str) -> None:
    raw = raw.strip()
    if raw.startswith("http"):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)
        code = (qs.get("code") or [""])[0]
    else:
        code = raw
    if not code:
        print("FAILED: no code found in that string")
        return
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": env("GOOGLE_CLIENT_ID"),
        "client_secret": env("GOOGLE_CLIENT_SECRET"),
        "redirect_uri": REDIRECT,
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=30).read())
    except Exception as exc:  # noqa: BLE001
        print("FAILED: token exchange:", str(exc)[:300])
        return
    rt = d.get("refresh_token")
    if not rt:
        print("FAILED: no refresh_token in response (revoke the app's access and retry with prompt=consent)")
        return
    TOKEN_FILE.write_text(json.dumps({"refresh_token": rt, "scope": d.get("scope", "")}, indent=1))
    os.chmod(TOKEN_FILE, 0o600)
    print("OK refresh token stored in", TOKEN_FILE)
    verify()


def verify() -> None:
    if not TOKEN_FILE.exists():
        print("no token file yet")
        return
    rt = json.loads(TOKEN_FILE.read_text())["refresh_token"]
    data = urllib.parse.urlencode({
        "client_id": env("GOOGLE_CLIENT_ID"),
        "client_secret": env("GOOGLE_CLIENT_SECRET"),
        "refresh_token": rt,
        "grant_type": "refresh_token",
    }).encode()
    d = json.loads(urllib.request.urlopen(
        urllib.request.Request("https://oauth2.googleapis.com/token", data=data), timeout=30).read())
    tok = d["access_token"]
    req = urllib.request.Request("https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
                                 headers={"Authorization": f"Bearer {tok}"})
    ch = json.loads(urllib.request.urlopen(req, timeout=30).read())
    items = ch.get("items") or []
    if not items:
        print("token works but sees NO channel")
    for it in items:
        print("CHANNEL:", it["id"], "|", it["snippet"]["title"])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "link"
    if cmd == "link":
        link()
    elif cmd == "exchange":
        exchange(sys.argv[2] if len(sys.argv) > 2 else "")
    elif cmd == "verify":
        verify()
    else:
        print(__doc__)
