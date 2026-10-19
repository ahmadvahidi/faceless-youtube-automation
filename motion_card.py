#!/usr/bin/env python3
"""
motion_card.py — kinetic-type hook cards for DOPEAK shorts, rendered with the
motionmaxxing runtime (HTML/CSS/GSAP -> headless Chrome -> ffmpeg).

Why: the shorts open on a Manim chart with a karaoke caption. The first two
seconds decide retention, and a chart is not a hook. This renders a designed
type card for the FIRST beat only — same duration as that beat, so the
narration stays in perfect sync (no audio is touched).

Rules it obeys (PLAYBOOK §2/§8):
  * no brand mark, logo or watermark on the video
  * 1080x1920 for shorts, 30 fps, h264 yuv420p (matches the other scenes
    exactly so the concat demuxer stays happy)
  * German/English only (the caller passes the narration's own sentence)

Usage:
    from motion_card import render_hook_card
    render_hook_card("Why your savings quietly lose money", 3.4, out.mp4)
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import ImageFont

SKILL = Path("/opt/data/workspace/motionmaxxing")
RUNTIME = SKILL / "runtime"
RENDER = SKILL / "scripts" / "render.mjs"
CHROME = SKILL / "chrome-nosandbox.sh"
FONT_MEASURE = RUNTIME / "hero3d" / "fonts" / "Inter-Bold-Latin.ttf"

HERE = Path(__file__).resolve().parent
CACHE = HERE / "motion_cache"

ACCENT = "#FFB020"
GROUND = "#0B0D10"


def _measure(text: str, size: int) -> float:
    return ImageFont.truetype(str(FONT_MEASURE), size).getlength(text)


def _wrap(words: list[str], size: int, max_w: float) -> list[str]:
    lines, cur = [], ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if _measure(cand, size) <= max_w or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_text(text: str, width: int, height: int) -> tuple[int, list[str]]:
    """Largest font size (px) whose wrapped lines fit the safe area."""
    words = text.split()
    max_w = width * 0.84
    # Aim for full lines, not one word per line: a 4-word hook should read as two
    # lines of two, not a stack of four. Cap the line count by the word count.
    cap_lines = 5 if height > width else 3
    max_lines = max(2, min(cap_lines, -(-len(words) // 2)))  # ceil(words/2)
    lo, hi = (60 if height > width else 72), (150 if height > width else 176)
    best = (lo, _wrap(words, lo, max_w))
    for size in range(hi, lo - 1, -2):
        lines = _wrap(words, size, max_w)
        widest = max(_measure(l, size) for l in lines)
        if len(lines) <= max_lines and widest <= max_w:
            best = (size, lines)
            break
    return best


def _html(text: str, dur: float, width: int, height: int, accent: str) -> str:
    size, lines = fit_text(text, width, height)
    leading = round(size * 1.06)
    block_h = leading * len(lines)
    top = round((height - block_h) / 2 - height * 0.03)
    pad = round(width * 0.08)

    rows = []
    for i, line in enumerate(lines):
        rows.append(
            f'<div id="l{i}" class="line" style="top:{top + i * leading}px">{line}</div>'
        )
    rows_html = "\n      ".join(rows)

    # words land on a speech-like cadence: first line at frame 3 (hook is on
    # screen in the first 100 ms), each next line ~6 frames after the previous
    words_in_line = max(1, len(lines[0].split()))
    step = 2 if words_in_line > 4 else 3
    starts = []
    at = 3
    for i, line in enumerate(lines):
        starts.append(at)
        at += max(6, len(line.split()) * step)

    js_words = []
    for i, at_frame in enumerate(starts):
        accent_opt = ""
        if i == len(lines) - 1:
            accent_opt = f", accent:{{ color:'{accent}', word:-1, frames:{max(30, int(dur*30))} }}"
        js_words.append(
            f"M.words('#l{i}', {{ at:{at_frame}, mech:'rise', dist:86, frames:13, "
            f"ease:'snapSettle', smear:true{accent_opt} }});"
        )
    js_words = "\n".join(js_words)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><title>hook</title>
<meta name="viewport" content="width={width}, height={height}">
<link rel="stylesheet" href="file://{RUNTIME}/fonts.css">
<style>
:root {{ --accent:{accent}; --font:"Inter", system-ui, sans-serif; }}
* {{ box-sizing:border-box }}
html,body {{ margin:0; width:{width}px; height:{height}px; overflow:hidden; background:#000 }}
#main {{ position:absolute; left:0; top:0; width:{width}px; height:{height}px; overflow:hidden;
  background:radial-gradient(120% 85% at 50% 42%, #14171C 0%, {GROUND} 62%, #07080A 100%);
  color:#F7F4EE; font-family:var(--font); font-weight:600 }}
#cam {{ position:absolute; inset:0 }}
#glow {{ position:absolute; left:{round(-width*0.45)}px; top:{round(height*0.18)}px;
  width:{round(width*1.9)}px; height:{round(width*1.9)}px; border-radius:50%;
  background:radial-gradient(circle at 50% 50%, rgba(255,176,32,.16) 0%, rgba(255,176,32,.045) 40%, rgba(11,13,16,0) 68%) }}
#vig {{ position:absolute; inset:0;
  background:radial-gradient(130% 95% at 50% 45%, rgba(0,0,0,0) 38%, rgba(0,0,0,.62) 100%) }}
.line {{ position:absolute; left:{pad}px; width:{width - 2*pad}px; white-space:pre;
  font-size:{size}px; line-height:{leading}px; letter-spacing:-.035em }}
</style>
</head>
<body>
<div id="main">
  <div id="cam">
    <div id="glow"></div>
    <div class="scene">
      {rows_html}
    </div>
    <div id="vig"></div>
  </div>
</div>
<script src="file://{RUNTIME}/vendor/gsap.min.js"></script>
<script src="file://{RUNTIME}/motion.js"></script>
<script>
const M = Motion.film({{ fps:30, duration:{dur:.3f}, width:{width}, height:{height}, clock:'smooth' }});
{js_words}
M.drift('#cam', {{ prop:'scale', from:1, to:1.045, start:0, end:{max(6, int(dur*30))} }});
M.drift('#glow', {{ prop:'x', from:-40, to:60, start:0, end:{max(6, int(dur*30))} }});
window.__ready = Motion.loaded();
</script>
</body>
</html>
"""


def render_hook_card(text: str, dur: float, out_path: Path,
                     width: int = 1080, height: int = 1920,
                     accent: str = ACCENT, crf: int = 20) -> Path:
    """Render a hook card of exactly `dur` seconds. Cached by (text, dur, size)."""
    text = " ".join(text.split())
    if not text:
        raise ValueError("empty hook text")
    dur = max(0.8, min(dur, 12.0))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    key = hashlib.sha1(f"{text}|{dur:.2f}|{width}x{height}|{accent}|{crf}".encode()).hexdigest()[:16]
    CACHE.mkdir(exist_ok=True)
    cached = CACHE / f"hook_{key}.mp4"
    if cached.exists() and cached.stat().st_size > 10_000:
        out_path.write_bytes(cached.read_bytes())
        print(f"[motion] hook card (cache) {out_path.name}", flush=True)
        return out_path

    html_path = CACHE / f"hook_{key}.html"
    html_path.write_text(_html(text, dur, width, height, accent), encoding="utf-8")
    tmp = CACHE / f"hook_{key}_render.mp4"

    if not CHROME.exists():
        raise RuntimeError(f"chrome wrapper missing: {CHROME}")
    env = {"CHROME_PATH": str(CHROME), "PATH": "/usr/local/bin:/usr/bin:/bin"}
    cmd = ["node", str(RENDER), str(html_path), str(tmp),
           "--fps", "30", "--width", str(width), "--height", str(height),
           "--duration", f"{dur:.3f}", "--crf", str(crf)]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600)
    if r.returncode != 0 or not tmp.exists():
        raise RuntimeError(f"motion render failed: {r.stderr[-1200:]}")

    cached.write_bytes(tmp.read_bytes())
    tmp.unlink(missing_ok=True)
    out_path.write_bytes(cached.read_bytes())
    print(f"[motion] hook card {out_path.name} ({dur:.2f}s, {width}x{height})", flush=True)
    return out_path


if __name__ == "__main__":
    txt = sys.argv[1] if len(sys.argv) > 1 else "Why your savings quietly lose money"
    d = float(sys.argv[2]) if len(sys.argv) > 2 else 3.5
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else HERE / "motion_cache" / "test.mp4"
    print(render_hook_card(txt, d, out))
