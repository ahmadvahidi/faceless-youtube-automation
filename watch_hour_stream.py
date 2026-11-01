#!/usr/bin/env python3
"""WATCH-HOUR STREAM — turn the channel's OWN library into a 24/7 live "study stream".

WHY THIS EXISTS (measured 2026-10-16, lens: monetization)
---------------------------------------------------------
Both channels are stuck on the ONE gate Shorts can never fill. DOPEAK: 3 subs, 673 views,
49 uploads — and YouTube counts ZERO watch hours from the Shorts feed ("any qualified watch
hours from Shorts views in the Shorts Feed won't count towards the 4,000 qualified public
watch hours threshold"). ALGORHYTHM: 0 subs, 0 views. AIR Media-Tech's 2026 study of 300
monetized channels puts Shorts at <2% of total revenue and needs 11,000-34,000 Shorts views
to match 1,000 long-form views. Meanwhile 10-20 concurrent viewers on a 24/7 stream is
120-240 watch hours PER DAY (Gyre/SubSub case data) — against a channel that currently has
0.1% of the 4,000-hour threshold. A stream is the only machine in this repo that can
accumulate the gate while nobody watches.

THE TWO RULES THAT MAKE OR BREAK IT (both owner/infra facts, not code):
  1. Live watch hours count ONLY if the stream is ARCHIVED AS A PUBLIC VOD. In YouTube
     Studio -> Settings -> Channel -> Advanced, "Automatically archive my live streams"
     must be ON. A 24/7 stream that is never converted to VOD burns its own watch time.
  2. A bare loop of 3 files is the shape YouTube's inauthentic/reused-content policy was
     written to reject. This script streams the channel's real, OWNED library (every file
     was rendered by this pipeline) in a running order that changes, with a live-only layer
     (clock, "live" state, progress) the VODs never had, and it is meant to be fed a NEW
     render weekly. Curation is the defence, and it is not optional.

OWNER ACTION TO GO LIVE (the agent cannot do any of it):
  * Studio -> Create -> Go live -> Stream -> copy the stream key.
  * Studio -> Settings -> Channel -> Advanced -> enable auto-archive to VOD.
  * Put the key in the channel's .env as YT_STREAM_KEY_DOPEAK (or _ALGORHYTHM). Never in code.

usage
  python watch_hour_stream.py --check                  # verify prerequisites, no stream
  python watch_hour_stream.py --to-file 20 out.flv     # PROOF encode (no key needed)
  python watch_hour_stream.py --list                   # the running order + total runtime
  python watch_hour_stream.py --push                   # go live (needs the key)
"""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
W, H, FPS = 1080, 1920, 30
BRAND = "DOPEAK"
CHANNEL_TAIL = "MATHS STUDY"

# Libraries this stream may draw from: every entry is OWN content rendered by this repo.
LIBRARIES = {
    "dopeak": ["/opt/data/workspace/math-videos/out",
               "/opt/data/workspace/trend-radar/out"],
    "algorhythm": ["/opt/data/workspace/cs-videos/out"],
}


def _load_env() -> None:
    """Project .env first (like every other entrypoint here), then the gateway copy."""
    for p in (HERE / ".env", Path("/opt/data/.env")):
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height,duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        w, h, d = r.stdout.strip().split(",")
        return {"w": int(w), "h": int(h), "dur": float(d)}
    except Exception:  # noqa: BLE001 — a broken file is skipped, never fatal
        return {}


def collect(libs: list[str], min_dur: float = 20.0, limit: int = 40) -> list[Path]:
    """Own, playable, non-test clips — newest first, then de-duplicated by size."""
    seen, out = set(), []
    for d in libs:
        for f in sorted(glob.glob(os.path.join(d, "*.mp4")),
                        key=lambda p: -os.path.getmtime(p)):
            p = Path(f)
            # test/debug renders must never reach the live feed
            low = p.stem.lower()
            if low.startswith(("test", "motion_probe", "_", "debug")) or any(
                    t in low for t in ("_mtest", "_mboost", "_test", "_probe", "_dry")):
                continue
            if p.stat().st_size < 200_000 or p.stat().st_size in seen:
                continue
            info = probe(p)
            if not info or info.get("dur", 0) < min_dur:
                continue
            seen.add(p.stat().st_size)
            out.append(p)
            if len(out) >= limit:
                return out
    return out


def write_list(clips: list[Path], dest: Path) -> float:
    """CONCAT DEMUXER list file. Every path ABSOLUTE (the demuxer resolves relative to
    the LISTFILE's directory) and every clip re-wrapped to the stream's own timebase."""
    lines, total = [], 0.0
    for p in clips:
        info = probe(p)
        lines.append(f"file '{p.resolve()}'")
        total += info.get("dur", 0)
    dest.write_text("\n".join(lines) + "\n")
    return total


def overlay_chain(brand: str, tail: str, font: str) -> str:
    """The LIVE-ONLY layer: brand, live state, clock and a progress bar that advances
    continuously — the thing a viewer cannot get from the VOD.

    It sits in the BOTTOM 200 px only, deliberately: the top of every one of these Shorts
    is the frame-1 hook band (title + kicker), and the caption band ends at y=1480, so a
    live strip over the top would dim the one element that stops the swipe (verified on a
    read-back: a top bar covered the hook's kicker line). y=1720..1920 is empty plate.
    """
    f = font.replace(":", r"\:")
    top = H - 200
    return (
        # vertical canvas: the library is already 1080x1920; anything else is padded
        f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x0A0E18,setsar=1,fps={FPS},"
        f"drawbox=x=0:y={top}:w={W}:h=200:color=0x0A0E18@0.86:t=fill,"
        f"drawtext=fontfile='{f}':text='LIVE':fontcolor=0xFF4D4D:fontsize=40:x=48:y={top + 22},"
        f"drawtext=fontfile='{f}':text='{brand}  |  {tail}':fontcolor=0xFFFFFF:fontsize=40:"
        f"x=190:y={top + 22},"
        f"drawtext=fontfile='{f}':text='%{{localtime\\:%H\\\\\\:%M\\\\\\:%S}} UTC':"
        f"fontcolor=0xC9D4E6:fontsize=40:x=w-tw-48:y={top + 22},"
        f"drawbox=x=48:y={top + 96}:w=(({W}-96)*mod(t\\,600)/600):h=12:color=0xFFBE3C@0.95:t=fill,"
        f"drawtext=fontfile='{f}':text='every topic is rendered here - no stock footage':"
        f"fontcolor=0x9FB0C8:fontsize=32:x=48:y={top + 128}"
    )


def encode_cmd(listfile: Path, out_target: str, key: str | None, font: str,
               bitrate: str, seconds: float | None, loop: bool) -> list[str]:
    """`-re` is what makes this a LIVE stream rather than a file write: FFmpeg reads the
    playlist in real time, so the encoder runs 1 s of video per 1 s of wall clock."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-re"]
    if loop:
        cmd += ["-stream_loop", "-1"]
    cmd += ["-f", "concat", "-safe", "0", "-i", str(listfile.resolve())]
    if seconds:
        cmd += ["-t", f"{seconds:.2f}"]
    cmd += ["-vf", overlay_chain(BRAND, CHANNEL_TAIL, font),
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
            "-b:v", bitrate, "-maxrate", bitrate, "-bufsize", "6M",
            "-g", str(FPS * 2), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
            "-f", "flv", out_target]
    if key:
        cmd = [c for c in cmd if c != "-hide_banner"]
    return cmd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default="dopeak", choices=sorted(LIBRARIES))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--to-file", nargs=2, metavar=("SECONDS", "PATH"))
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--bitrate", default="2500k")
    ap.add_argument("--font", default="/opt/data/workspace/deutsch-b2-brief/fonts/Poppins-SemiBold.ttf")
    a = ap.parse_args()
    _load_env()
    global BRAND, CHANNEL_TAIL
    BRAND = "DOPEAK" if a.channel == "dopeak" else "ALGORHYTHM"
    CHANNEL_TAIL = "MATHS STUDY" if a.channel == "dopeak" else "CS STUDY"

    clips = collect(LIBRARIES[a.channel])
    total = sum(probe(p).get("dur", 0) for p in clips)
    key = os.environ.get(f"YT_STREAM_KEY_{a.channel.upper()}")
    problems = []
    if not clips:
        problems.append("no source clips (out/ is empty)")
    if total < 600:
        problems.append(f"only {total / 60:.1f} min of material — add renders before going live")
    if not Path(a.font).exists():
        problems.append(f"font missing: {a.font}")
    if not shutil.which("ffmpeg"):
        problems.append("ffmpeg missing")
    if a.push and not key:
        problems.append(f"YT_STREAM_KEY_{a.channel.upper()} not set in .env")
    if a.push and not os.environ.get("YT_STREAM_ARCHIVE_CONFIRMED"):
        problems.append("set YT_STREAM_ARCHIVE_CONFIRMED=1 once auto-archive to VOD is ON "
                        "(without the VOD the watch hours do not count)")

    print(f"[stream] {BRAND} — {len(clips)} clips, {total / 60:.1f} min of OWN material")
    for p in clips[:6]:
        print(f"   {probe(p).get('dur', 0):6.1f}s  {p.name[:64]}")
    if a.check or a.push:
        print("[stream] prerequisites: " + ("OK" if not problems else "BLOCKED"))
        for p in problems:
            print(f"   ! {p}")
        if problems and a.push:
            return 2
    if a.check:
        return 0
    if a.list:
        write_list(clips, HERE / "work/stream_list.txt")
        print(f"[stream] running order -> {HERE / 'work/stream_list.txt'}")
        return 0

    (HERE / "work").mkdir(exist_ok=True)
    listfile = HERE / "work/stream_list.txt"
    write_list(clips, listfile)
    if a.to_file:
        secs, dest = float(a.to_file[0]), a.to_file[1]
        cmd = encode_cmd(listfile, dest, None, a.font, a.bitrate, secs, loop=False)
    elif a.push:
        dest = f"rtmp://a.rtmp.youtube.com/live2/{key}"
        cmd = encode_cmd(listfile, dest, key, a.font, a.bitrate, None, loop=True)
    else:
        print(__doc__)
        return 3
    print("[stream] " + (" ".join(c if not c.startswith('rtmp') else 'rtmp://…/<key>'
                                 for c in cmd[:6])) + " …")
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
