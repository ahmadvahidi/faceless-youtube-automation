#!/usr/bin/env python3
"""Publish a video to YouTube the RIGHT way for growth:
  upload video -> set a custom thumbnail -> verify.

A custom thumbnail is the biggest CTR lever; CTR is what makes the algorithm
push the video, so EVERY upload goes through here (never a bare upload_video).
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import yt_uploader as yt
from make_thumbnail import make_thumbnail

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"

# ── tag pools: a pool is not decoration, it is which audience YouTube tests you with ──────────
# YouTube uses title + description + tags to decide the TOPIC of a new upload and therefore which
# test audience it gets. A channel that changes niche must move its pool with it, or the wrong
# group is served the video and swipes away — "topic->viewer match" is the fourth trap the
# Shorts-algorithm research names. Measured on the live feed 2026-10-17: every DOPEAK maths /
# science short published since the niche change still carried the retired FINANCE pool merged
# into its tags — the Disney Boo-Bucket short (M1pw-U3OD9w) was tagged "index funds" /
# "investing for beginners" / "how to invest". DOPEAK's live niche is maths+science Shorts, so
# the default is POOLS["maths"]; a caller with a different niche passes base_tags=..., and
# YT_BASE_TAGS (comma-separated) overrides without a code edit.
POOLS = {
    "maths": ["maths", "mathematics", "science", "how things work", "explained",
              "did you know", "everyday science", "curiosity", "numbers",
              "science shorts"],
    "finance": ["personal finance", "investing for beginners", "how to invest", "money",
                "wealth building", "financial freedom", "index funds", "passive income",
                "money tips", "build wealth", "saving money"],
    "cs": ["computer science", "learn programming", "coding for beginners",
           "algorithms explained", "how computers work", "programming basics",
           "computer science course", "learn to code", "software engineering",
           "tech explained", "it fundamentals"],
}
BASE_TAGS = POOLS["maths"]   # DOPEAK's live niche. The finance lines pass POOLS["finance"].


def _base_pool(base_tags=None):
    """The tag pool for this upload: explicit argument > YT_BASE_TAGS > the channel default."""
    if base_tags is not None:
        return list(base_tags)
    env = os.environ.get("YT_BASE_TAGS")
    if env:
        return [t.strip() for t in env.split(",") if t.strip()]
    return BASE_TAGS


# ── session-time lever: point every upload at the channel's OWN library ───────────────────────
# The algorithm rewards a channel whose pieces connect (a Short that leads to another watch keeps
# the session alive). Fail-open in every direction: no network, no API scope or no decent match
# means an empty line, never a lost upload.
_POOL_CACHE_DAYS = 3   # a shorter cache = yesterday's upload can be linked today; 1 call per refresh
_STOP = {"the", "and", "for", "with", "that", "this", "you", "your", "how", "why", "what", "are",
         "its", "from", "into", "they", "them", "than", "then", "there", "here", "really", "much",
         "more", "most", "does", "did", "can", "will", "make", "makes", "made", "one", "two",
         "things", "ways", "signs", "numbers", "stats", "reasons", "about", "behind", "over"}


def _tokens(text):
    return {w for w in re.findall(r"[a-z0-9]+", str(text).lower())
            if len(w) > 2 and w not in _STOP}


def _live_pool():
    """{norm_title: (id, title)} for THIS token's channel, cached for a week.

    Reuses yt_uploader.live_titles() (a single playlistItems call), so the pool is always the
    channel this project's OAuth token belongs to — never another channel's library.
    """
    cache = ROOT / "related_pool.json"
    try:
        if cache.exists() and time.time() - cache.stat().st_mtime < _POOL_CACHE_DAYS * 86400:
            return {k: tuple(v) for k, v in json.loads(cache.read_text()).items()}
        pool = yt.live_titles()
        cache.write_text(json.dumps({k: list(v) for k, v in pool.items()}))
        return pool
    except Exception as e:  # noqa: BLE001 — a bonus line must never break an upload
        print(f"[related] pool unavailable ({str(e)[:80]})", flush=True)
        try:
            return {k: tuple(v) for k, v in json.loads(cache.read_text()).items()}
        except Exception:  # noqa: BLE001
            return {}


def related_line(text, exclude_title=None):
    """'Watch next: <title> -> <url>' for the closest thing already live on THIS channel.

    Keyword overlap only (title vs title + tags): a forced, unrelated link is worse than none,
    so the bar is >= 1 shared content word AND >= 30% of the shorter side. Returns "" when
    nothing matches, when the pool is empty, or on any error.
    """
    try:
        pool = _live_pool()
        want = _tokens(text)
        if not pool or not want:
            return ""
        skip = yt.norm_title(exclude_title) if exclude_title else None
        best = None
        for norm, (vid, title) in pool.items():
            if skip and norm == skip:
                continue
            t = _tokens(title)
            if not t:
                continue
            shared = want & t
            if not shared:
                continue
            score = len(shared) / max(1, min(len(want), len(t)))
            if score >= 0.30 and (best is None or score > best[0]):
                best = (score, vid, title)
        if not best:
            return ""
        return f"Watch next: {best[2]} → https://youtu.be/{best[1]}"
    except Exception as e:  # noqa: BLE001
        print(f"[related] skipped ({str(e)[:80]})", flush=True)
        return ""


def _queue_for_retry(video_path, title, description, tags, privacy):
    """A quota-failed upload must not vanish — queue it for tomorrow."""
    import json
    from datetime import datetime, timezone
    q = ROOT / "pending_uploads.json"
    items = json.loads(q.read_text()) if q.exists() else []
    if any(i.get("title") == title for i in items):
        return
    items.append({"path": str(video_path), "title": title, "description": description,
                  "tags": tags, "privacy": privacy,
                  "at": datetime.now(timezone.utc).isoformat()})
    q.write_text(json.dumps(items, ensure_ascii=False, indent=1))
    print(f"[queue] '{title[:50]}' saved to pending_uploads.json for the next run",
          flush=True)


def _verified_or_die(video_path):
    """Refuse to upload a video that breaks playback or is visually dead."""
    r = subprocess.run([sys.executable, str(ROOT / "verify_video.py"), str(video_path)],
                       capture_output=True, text=True)
    print("  " + (r.stdout.strip() or r.stderr.strip()[-300:]), flush=True)
    if r.returncode != 0:
        raise RuntimeError(f"upload refused for {video_path}: {r.stdout.strip()}")


def publish(video_path, title, description, tags=None, privacy="public",
            thumbnail_src=None, make_thumb=True, replace_of=None,
            base_tags=None, link_related=True):
    """Verify -> upload -> thumbnail -> localise. Returns the video id.

    `replace_of=<old video id>` marks this upload as the DELIBERATE replacement of an
    already-live video with the same title (the only way a duplicate title may pass the
    live-title guard; the old id is then recorded in pending_deletions.json for approval).

    `base_tags` picks the niche tag pool (default: the channel's own, see POOLS above).
    `link_related` appends a "Watch next" pointer to another video on THIS channel — the
    description is the only place a Short can hand a viewer to a second watch, which is what
    session time is made of.
    """
    _verified_or_die(video_path)
    tagset = list(dict.fromkeys((tags or []) + _base_pool(base_tags)))[:30]
    if link_related and "youtu.be" not in (description or ""):
        line = related_line(f"{title} {' '.join(tags or [])}", exclude_title=title)
        if line:
            description = f"{(description or '').rstrip()}\n\n{line}"
            print(f"[related] {line}", flush=True)
    vid = yt.upload_video(str(video_path), title, description,
                          tags=tagset, category_id="27", privacy=privacy,
                          replace_of=replace_of)

    if make_thumb:
        try:
            WORK.mkdir(exist_ok=True)
            tp = WORK / f"thumb_{vid}.jpg"
            make_thumbnail(title, str(tp),
                           thumbnail_src or str(video_path))
            yt.set_thumbnail(vid, str(tp))
            print(f"[thumb] set for {vid}", flush=True)
        except Exception as e:
            # custom thumbnails need a phone-verified channel; never fail the
            # upload over a thumbnail
            print(f"[thumb] skipped for {vid}: {e}", flush=True)

    # Localised metadata: the same upload competes in a second language market, so it doubles
    # the number of feeds it can be recommended in without a second render. Best-effort only —
    # an i18n failure must never cost the upload (or look like one).
    try:
        import localize
        ok, msg = localize.apply_de(vid, title, description, yt_mod=yt)
        print(f"[i18n] de: {msg}", flush=True)
    except Exception as e:
        print(f"[i18n] skipped for {vid}: {str(e)[:120]}", flush=True)

    return vid

