#!/usr/bin/env python
"""Rebuild DOPEAK's STATIC long-form videos with the current motion pipeline.

Why this exists: every DOPEAK long-form finance video published on 12-14 Oct
2026 measures 0.00% motion on the LIVE file (verified 2026-10-17 by downloading
a 30 s section with yt-dlp and running verify_video.motion_score on it) — they
predate the camera-motion engine. Ahmad's standard: a static "video" is a
rejected deliverable.

Per candidate, in order:
  1. download a 30 s section of the LIVE file and measure motion (real evidence)
  2. build_longform(topic, n_sections=14) in this video's palette
  3. verify_video.py must PASS (publish() enforces it)  -> upload with
     replace_of=<old id> (the only legal way a same-title upload may pass)
  4. only after the NEW id exists: re-query it, then DELETE the old id
     (standing owner approval: a video just replaced by a rebuilt version of itself)

Usage: python upgrade_longform_motion.py [--limit N] [--dry]
"""
import json
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/opt/data/workspace/faceless-youtube")
sys.path.insert(0, str(ROOT))
from send_to_group import _load_env  # noqa: E402

_load_env()

from longform_pipeline import build_longform, mark_seed_published  # noqa: E402
from verify_video import motion_score  # noqa: E402
from yt_publish import publish  # noqa: E402

STATE = ROOT / "dopeak_upgrade_done.json"
SCRATCH = Path("/opt/data/cache/scratch/live_motion")
SCRATCH.mkdir(parents=True, exist_ok=True)
PY = "/opt/data/skills/.venv/bin/python"


def _get(token, url):
    return json.load(urllib.request.urlopen(
        urllib.request.Request(url, headers={"Authorization": "Bearer " + token})))


def secs(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def live_longforms(token, min_sec=400):
    """[(id, title, description, duration_sec)] for public long videos, newest first."""
    ch = _get(token, "https://www.googleapis.com/youtube/v3/channels?part=contentDetails"
                     "&mine=true")["items"][0]
    up = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    items, page = [], ""
    while True:
        d = _get(token, "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet,"
                        "contentDetails&maxResults=50&playlistId=%s&pageToken=%s" % (up, page))
        items += d.get("items", [])
        page = d.get("nextPageToken", "")
        if not page:
            break
    ids = [i["contentDetails"]["videoId"] for i in items]
    vids = {}
    for k in range(0, len(ids), 50):
        d = _get(token, "https://www.googleapis.com/youtube/v3/videos?part=snippet,"
                        "contentDetails,status&id=" + ",".join(ids[k:k + 50]))
        for v in d["items"]:
            vids[v["id"]] = v
    out = []
    for i in items:
        v = vids[i["contentDetails"]["videoId"]]
        dur = secs(v["contentDetails"]["duration"])
        if dur < min_sec or v["status"]["privacyStatus"] != "public":
            continue
        out.append((v["id"], v["snippet"]["title"], v["snippet"]["description"], dur))
    return out


def live_motion(vid):
    """Motion % of the LIVE published file (30 s section, 2 s frame spacing).

    A fixed *15-45 section is UNMEASURABLE on a video shorter than ~25 s (the
    fragment lands under motion_score's 8 s floor and reads -1.00, which is a
    measurement failure, NOT a static verdict). Fall back to the whole file and
    measure again before anyone queues a rebuild on a -1.00.
    """
    frag = next(SCRATCH.glob(vid + ".*"), None)
    if frag is None or (vid + "_full" not in frag.name and _too_short(frag)):
        for p in SCRATCH.glob(vid + ".*"):
            p.unlink()
        subprocess.run([PY, "-m", "yt_dlp", "-f", "bv*[height<=480]/b[height<=480]",
                        "--download-sections", "*15-45",
                        "-o", str(SCRATCH / (vid + ".%(ext)s")),
                        "https://www.youtube.com/watch?v=" + vid],
                       capture_output=True, text=True)
        frag = next(SCRATCH.glob(vid + ".*"), None)
    if frag is None:
        return None
    m = motion_score(frag)
    if m is not None and m < 0:
        # unmeasurable fragment -> pull the whole file and measure that
        full = next(SCRATCH.glob(vid + "_full.*"), None)
        if full is None:
            subprocess.run([PY, "-m", "yt_dlp", "-f", "bv*[height<=480]/b[height<=480]",
                            "-o", str(SCRATCH / (vid + "_full.%(ext)s")),
                            "https://www.youtube.com/watch?v=" + vid],
                           capture_output=True, text=True)
            full = next(SCRATCH.glob(vid + "_full.*"), None)
        if full is not None:
            m = motion_score(full)
    return m


def _too_short(path, floor=6.0):
    """True when the cached fragment is shorter than the gate can measure."""
    try:
        r = subprocess.run(["/usr/bin/ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of",
                            "default=nw=1:nk=1", str(path)],
                           capture_output=True, text=True)
        return float(r.stdout.strip() or 0) < floor
    except Exception:
        return False


def load_done():
    try:
        return {t.strip().lower() for t in json.loads(STATE.read_text()).get("done", [])}
    except Exception:
        return set()


def mark_done(title):
    d = load_done()
    d.add(title.strip().lower())
    STATE.write_text(json.dumps({"done": sorted(d)}, indent=2, ensure_ascii=False))


def delete_video(token, vid):
    req = urllib.request.Request(
        "https://www.googleapis.com/youtube/v3/videos?id=" + vid, method="DELETE")
    req.add_header("Authorization", "Bearer " + token)
    try:
        urllib.request.urlopen(req)
        return True
    except Exception as e:
        print(f"    [delete] {vid}: {e}", flush=True)
        return False


def id_alive(token, vid):
    try:
        d = _get(token, "https://www.googleapis.com/youtube/v3/videos?part=id&id=" + vid)
        return bool(d.get("items"))
    except Exception:
        return None


def _norm(s):
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())


def _toks(s):
    stop = {"the", "a", "an", "of", "to", "and", "in", "for", "your", "you", "is",
            "it", "how", "why", "with", "that", "on", "at", "into", "s"}
    return {w for w in _norm(s).split() if len(w) > 2 and w not in stop}


def owns_title(title, known_titles):
    """True if this live title is one of OUR finance videos (topic_history +
    rebuild_premium jobs). Guards against rebuilding Ahmad's old personal uploads
    (e.g. a 10-minute gaming video) just because it is long and static."""
    t = _toks(title)
    for k in known_titles:
        kt = _toks(k)
        if not kt or not t:
            continue
        if len(t & kt) >= max(3, min(len(t), len(kt)) // 2):
            return True
    return False


def main():
    limit = 2
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    dry = "--dry" in sys.argv

    from yt_uploader import get_access_token
    token = get_access_token()
    hist = {h.get("title", "").strip().lower(): h.get("topic", "") for h in
            json.loads((ROOT / "topic_history.json").read_text())}
    try:
        from rebuild_premium import JOBS
        known = list(hist.keys()) + [j[1] for j in JOBS]
    except Exception:
        known = list(hist.keys())
    done_set = load_done()

    rebuilt, failed, skipped = [], [], []
    done = 0
    for vid, title, desc, dur in live_longforms(token):
        if done >= limit:
            break
        if not owns_title(title, known):
            print(f"[skip] not one of our finance long-forms: {title[:55]}", flush=True)
            continue
        if title.strip().lower() in done_set:
            print(f"[skip] already rebuilt: {title[:55]}", flush=True)
            continue
        m = live_motion(vid)
        if m is None:
            print(f"[skip] could not measure live motion: {title[:55]}", flush=True)
            skipped.append(title)
            continue
        state = "STATIC" if m < 4.0 else "moving"
        print(f"\n[{state}] motion {m:.2f}% | {dur}s | {vid} | {title}", flush=True)
        if m >= 4.0:
            mark_done(title)          # already moves - never touch it again
            continue
        if dry:
            continue
        topic = hist.get(title.strip().lower(), title)
        try:
            path = build_longform(topic, n_sections=14)
            print(f"    built -> {path.name}", flush=True)
        except Exception as e:
            print(f"    BUILD FAILED: {str(e)[:250]}", flush=True)
            failed.append((title, "build: " + str(e)[:120]))
            continue
        new_id = None
        for attempt in (1, 2):
            try:
                new_id = publish(str(path), title, desc, privacy="public", replace_of=vid)
                break
            except Exception as e:
                msg = str(e)[:250]
                print(f"    UPLOAD attempt {attempt} FAILED: {msg}", flush=True)
                if attempt == 2:
                    failed.append((title, "upload: " + msg[:120]))
        if not new_id:
            continue
        print(f"    NEW: https://youtube.com/watch?v={new_id}", flush=True)
        mark_done(title)
        mark_seed_published()
        rebuilt.append((title, new_id, vid, dur))
        done += 1          # --limit counts REBUILDS, not loop iterations (was a no-op:
                           # 4 static videos were rebuilt in one run with --limit 1)
        # old copy may only be removed once the replacement EXISTS (id returned)
        alive = id_alive(token, new_id)
        if alive:
            if delete_video(token, vid):
                # the delete returns 204 immediately but the id keeps resolving for a
                # short propagation window, so a single re-query lies ("STILL LIVE" for a
                # video that is already gone). Poll before reporting.
                gone = None
                for _ in range(6):
                    time.sleep(5)
                    gone = id_alive(token, vid)
                    if gone is False:
                        break
                print(f"    OLD {vid} deleted (re-query: "
                      f"{'GONE' if gone is False else 'STILL RESOLVING'})", flush=True)
        else:
            print(f"    [warn] new id not resolvable yet; old copy left in place", flush=True)

    print(f"\n[done] rebuilt {len(rebuilt)} | failed {len(failed)} | skipped {len(skipped)}",
          flush=True)
    for t, n, o, d in rebuilt:
        print(f"  REBUILT {o} -> {n}  {d}s  {t}", flush=True)
    for t, e in failed:
        print(f"  FAILED  {t[:50]} :: {e}", flush=True)
    stamp = datetime.now(timezone.utc).isoformat()
    print(f"[at] {stamp}", flush=True)


if __name__ == "__main__":
    main()
