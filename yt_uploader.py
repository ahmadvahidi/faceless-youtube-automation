#!/usr/bin/env python3
"""YouTube uploader using stored OAuth refresh token (no interactive OAuth needed).

Uses GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN to get an
access token, then uploads via YouTube Data API v3 videos.insert.
"""
import json
import os
import re
import unicodedata
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENVF = ROOT / ".env"


def _load_env() -> None:
    """Load KEY=VALUE pairs from .env into os.environ without overwriting."""
    if not ENVF.exists():
        return
    for raw in ENVF.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN", "")

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com"


def get_access_token() -> str:
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.load(r)
    if "access_token" not in resp:
        raise RuntimeError(f"token error: {resp}")
    return resp["access_token"]


def _api(access_token: str, path: str, payload: dict = None, method: str = None):
    url = API + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method or ("POST" if data else "GET"),
        headers={"Authorization": f"Bearer {access_token}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise RuntimeError(f"HTTP {e.code}: {body}") from e


def list_channels():
    token = get_access_token()
    return _api(token, "/youtube/v3/channels?part=snippet&mine=true")


def norm_title(t: str) -> str:
    """Case- and punctuation-insensitive title key (same normalisation as the guardian)."""
    return re.sub(r"[^\w]+", " ", unicodedata.normalize("NFKC", t or "").casefold()).strip()


def live_titles(token: str = None) -> dict:
    """{norm_title: (video_id, title)} for EVERY video live on THIS token's channel."""
    token = token or get_access_token()
    up = _api(token, "/youtube/v3/channels?part=contentDetails&mine=true")["items"][0][
        "contentDetails"]["relatedPlaylists"]["uploads"]
    out, page = {}, ""
    while True:
        d = _api(token, "/youtube/v3/playlistItems?part=snippet&maxResults=50"
                        f"&playlistId={up}" + (f"&pageToken={page}" if page else ""))
        for it in d.get("items", []):
            sn = it["snippet"]
            out[norm_title(sn.get("title", ""))] = (sn["resourceId"]["videoId"], sn.get("title", ""))
        page = d.get("nextPageToken") or ""
        if not page:
            break
    return out


def _record_pending_deletion(old_id, new_id, title):
    """A replacement upload leaves the OLD video live until Ahmad approves deleting it."""
    import datetime
    f = ROOT / "pending_deletions.json"
    try:
        items = json.loads(f.read_text()) if f.exists() else []
    except Exception:
        items = []
    items.append({"old_id": old_id, "new_id": new_id, "title": title,
                  "at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    f.write_text(json.dumps(items, indent=2, ensure_ascii=False))


LIVE_TITLE_OVERRIDE = os.environ.get("ALLOW_LIVE_TITLE") == "1"


def enforce_live_title(token, title, replace_of=None):
    """HARD RULE: never publish a title that is already live unless this IS its replacement.

    Returns the id of the live video being replaced (or None). Fails OPEN when the live
    list cannot be fetched (a network hiccup must never cost the day's upload) but fails
    CLOSED as soon as it can SEE a duplicate title.
    """
    if not title or LIVE_TITLE_OVERRIDE:
        return None
    try:
        live = live_titles(token)
    except Exception as e:
        print(f"[title-guard] open (could not list live titles: {str(e)[:120]})", flush=True)
        return None
    hit = live.get(norm_title(title))
    if hit and hit[0] != replace_of:
        raise RuntimeError(
            f"LiveTitleDuplicate: '{title}' is ALREADY live as {hit[0]} "
            f"(https://youtu.be/{hit[0]}). Refusing to publish a second copy - replace "
            f"the old one (replace_of='{hit[0]}') or set ALLOW_LIVE_TITLE=1 to override.")
    print(f"[title-guard] ok: no live copy of '{title[:60]}'", flush=True)
    return hit[0] if hit else None



def upload_video(video_path: str, title: str, description: str,
                 tags: list = None, category_id: str = "27",
                 privacy: str = "public", replace_of: str = None):
    """Upload a video. category 27 = Education. privacy: public/unlisted/private."""
    token = get_access_token()
    video_path = str(video_path)
    replaced = enforce_live_title(token, title, replace_of) if privacy == "public" else None

    # 1. build metadata
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    if tags:
        body["snippet"]["tags"] = tags

    # 2. resumable upload initiation
    url = ("https://www.googleapis.com/upload/youtube/v3/videos"
           "?uploadType=resumable&part=snippet,status")
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json",
                 "X-Upload-Content-Type": "video/mp4"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            upload_url = r.headers["Location"]
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode(errors="replace")
        if "uploadLimitExceeded" in body_txt:
            raise RuntimeError(
                "UploadLimitExceeded: this channel has hit its DAILY upload "
                "quota (normal for a fresh/unverified channel; it resets "
                "daily). Retry the remaining videos tomorrow."
            ) from e
        raise RuntimeError(f"upload init HTTP {e.code}: {body_txt[:400]}") from e

    # 3. stream the file
    total = os.path.getsize(video_path)
    with open(video_path, "rb") as f:
        req = urllib.request.Request(
            upload_url, data=f, method="PUT",
            headers={"Content-Type": "video/mp4",
                     "Content-Length": str(total)})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                result = json.load(r)
        except urllib.error.HTTPError as e:
            # resume from the byte offset in the error Range header
            if e.code == 308:
                range_hdr = e.headers.get("Range", "")
                offset = int(range_hdr.split("-")[-1]) + 1 if range_hdr else 0
                f.seek(offset)
                remaining = total - offset
                req = urllib.request.Request(
                    upload_url, data=f, method="PUT",
                    headers={"Content-Type": "video/mp4",
                             "Content-Length": str(remaining),
                             "Content-Range": f"bytes {offset}-{total-1}/{total}"})
                with urllib.request.urlopen(req, timeout=600) as r2:
                    result = json.load(r2)
            else:
                body = e.read().decode()
                raise RuntimeError(f"upload HTTP {e.code}: {body}") from e

    vid_id = result.get("id")
    if replaced and vid_id:
        _record_pending_deletion(replaced, vid_id, title)
        print("[title-guard] replacement: new " + str(vid_id) + " supersedes live "
              + str(replaced) + " - the OLD video stays live until Ahmad approves "
              "its deletion (pending_deletions.json)", flush=True)
    return vid_id


def set_thumbnail(video_id: str, thumb_path: str):
    """Upload a custom thumbnail (requires a phone-verified channel)."""
    token = get_access_token()
    url = ("https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
           f"?videoId={video_id}")
    with open(thumb_path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "image/jpeg"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"thumbnail HTTP {e.code}: {e.read().decode()[:300]}") from e


def update_video(video_id: str, title: str = None, description: str = None,
                 tags: list = None, category_id: str = "27"):
    """Patch a video's snippet metadata."""
    token = get_access_token()
    payload = {"id": video_id, "snippet": {"categoryId": category_id}}
    if title:
        payload["snippet"]["title"] = title
    if description:
        payload["snippet"]["description"] = description
    if tags:
        payload["snippet"]["tags"] = tags
    return _api(token, "/youtube/v3/videos?part=snippet", payload, method="PUT")


if __name__ == "__main__":
    import sys
    if sys.argv[1] == "channels":
        ch = list_channels()
        for item in ch.get("items", []):
            sn = item["snippet"]
            print(f"channel: {sn['title']}  id={item['id']}")
    elif sys.argv[1] == "thumb":
        # python yt_uploader.py thumb <video_id> <thumb.jpg>
        set_thumbnail(sys.argv[2], sys.argv[3])
        print("thumbnail set")
    else:
        # upload_video(path, title, description)
        vid_id = upload_video(sys.argv[1], sys.argv[2], sys.argv[3])
        print(f"UPLOADED: https://youtube.com/watch?v={vid_id}")
