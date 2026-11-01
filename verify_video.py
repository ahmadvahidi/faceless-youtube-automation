#!/usr/bin/env python3
"""Verify a video is YouTube-playable AND alive BEFORE upload.

Four silent-failure modes, all seen in production:

1. Audio must be 44.1/48kHz stereo AAC (edge-tts emits 24kHz mono, which makes
   the YouTube player spin forever while the API still reports `processed`).
2. The `moov` atom must be at the START of the file (`+faststart`); a `-c:v copy`
   remux silently drops it and the player has to fetch the whole file first.
3. MOTION: a static "video" (one still + subtitles) is where viewers swipe away.
   User law: "هیچی حرکت نمیکنه" is a rejection. Median adjacent-frame difference
   must clear MOTION_MIN.
4. Orientation/resolution sanity (landscape long-form vs vertical Short).

Usage: python verify_video.py <path.mp4>
Exit 0 = uploadable, non-zero = broken (prints exactly what's wrong).
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

MOTION_MIN = 4.0          # median % of pixels that move between frames 2s apart
MOTION_SAMPLES = 12       # points spread across the whole video


def ffprobe(path: Path) -> dict:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries",
        "stream=codec_type,codec_name,width,height,sample_rate,channels",
        "-show_entries", "format=duration", "-of", "json", str(path)])
    return json.loads(out)


def motion_score(path: Path) -> float:
    """Median mean-abs pixel difference (%) between frames 3s apart."""
    try:
        from PIL import Image
    except ImportError:
        return -1.0
    dur = float(ffprobe(path)["format"]["duration"])
    if dur < 8:
        return -1.0
    # Sample every 2 SECONDS across the whole video, then take the MEDIAN.
    # A section is ~40s long, so a 2s gap usually sits INSIDE one shot: a real
    # camera move displaces ~10% of the frame there, while a frozen picture
    # gives 0.0% (only the section cuts score high, and the median ignores them).
    starts = [round(3 + i * (dur - 8) / MOTION_SAMPLES, 2) for i in range(MOTION_SAMPLES)]
    pairs = [(t, round(t + 2, 2)) for t in starts]
    tmp = Path(tempfile.mkdtemp(prefix="vgate_", dir="/opt/data/cache/scratch"))
    frames = {}
    for a_t, b_t in pairs:
        for t in (a_t, b_t):
            if t in frames:
                continue
            p = tmp / f"f_{t}.png"
            subprocess.run(["ffmpeg", "-y", "-ss", str(t), "-i", str(path),
                            "-frames:v", "1", "-vf",
                            "crop=iw:ih*0.70:0:0,scale=270:-2", str(p)],
                           capture_output=True)
            frames[t] = p
    diffs = []
    for a_t, b_t in pairs:
        a, b = frames.get(a_t), frames.get(b_t)
        if not (a and b and a.exists() and b.exists()):
            continue
        ia, ib = Image.open(a).convert("L"), Image.open(b).convert("L")
        if ia.size != ib.size:
            ib = ib.resize(ia.size)
        n = ia.width * ia.height
        # FRACTION OF PIXELS THAT MOVED, not mean brightness change: a real
        # camera move displaces most of the frame, while a local counter/ticker
        # on a frozen background only nudges a few percent — the mean-diff
        # metric confused the two and let a static video through.
        moved = sum(1 for x, y in zip(ia.getdata(), ib.getdata()) if abs(x - y) > 12)
        diffs.append(moved / n * 100)
    if not diffs:
        return -1.0
    diffs.sort()
    return diffs[len(diffs) // 2]


def main(path_str: str) -> int:
    path = Path(path_str)
    problems, notes = [], []

    info = ffprobe(path)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)

    # 1. audio
    if a is None:
        problems.append("no audio stream")
    else:
        sr, ch = int(a.get("sample_rate", 0)), int(a.get("channels", 0))
        if sr < 44100:
            problems.append(f"audio sample_rate={sr} (<44100, edge-tts mono trap)")
        if ch < 2:
            problems.append(f"audio channels={ch} (mono — needs stereo)")

    # 2. moov position
    with open(path, "rb") as f:
        data = f.read()
    dur = float(ffprobe(path)["format"]["duration"])
    moov = data.find(b"moov")
    if moov == -1:
        problems.append("no moov atom found")
    elif moov > 100_000:
        problems.append(f"moov at byte {moov} (EOF — faststart missing, will spin)")

    # 3. motion
    m = motion_score(path)
    if m < 0:
        notes.append("motion unmeasured (PIL missing or clip too short)")
    elif m < (MOTION_MIN if dur > 30 else 1.5):
        # Shorts are built from Manim animations that legitimately pause between
        # ideas; 2s-spaced samples then land inside the holds. A STATIC slideshow
        # measures 0.00-0.5%, an animated Short with holds ~1.5-4%, so the floor
        # is lower for clips <=30s rather than rejecting real animation.
        floor = MOTION_MIN if dur > 30 else 1.5
        problems.append(f"MOTION {m:.2f}% (<{floor}% = static; rebuild it)")
    else:
        notes.append(f"motion {m:.2f}%")

    # 4. orientation
    if v:
        w, h = int(v.get("width", 0)), int(v.get("height", 0))
        notes.append(f"{w}x{h}")
        if h > w and w < 700:
            problems.append(f"vertical too small ({w}x{h})")
        if w > h and w < 1200:
            problems.append(f"horizontal too small ({w}x{h})")

    if problems:
        print("BROKEN:", "; ".join(problems))
        return 1
    print("OK: %s %sHz %sch, moov@%d, %s" % (
        a.get("codec_name") if a else "?",
        a.get("sample_rate") if a else "?",
        a.get("channels") if a else "?",
        moov, ", ".join(notes)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
