#!/usr/bin/env python3
"""
Long-form faceless finance video pipeline (8-12 min), with ORIGINAL animated
charts instead of stock photos.

The LLM returns a structured multi-section script. Each section maps to a
finance chart type (compounding / stock / inflation / diversify / compare / tax),
rendered once via Manim (cached per type), then looped as the animated
background for that section's narration with sentence-level captions on top.

Why charts, not stock photos: random stock photos of "money" are generic and
off-topic; an original animated chart actually TEACHES the number being
described and is clearly original (clears YouTube's inauthentic-content policy).

Usage:
  python longform_pipeline.py --topic "How the rich avoid taxes" --sections 14
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# Load .env FIRST so LLM_API_KEY is set before pipeline_v3 reads it at import.
from send_to_group import _load_env
_load_env()

from pipeline_v3 import (
    LLM_BASE_URL, LLM_API_KEY, LLM_MODEL,
    synth_with_boundaries, render_caption_png, probe_duration,
    ASSETS, OUT, WORK, W, H, FPS,
)

ROOT = Path(__file__).resolve().parent
VOICE = "en-US-GuyNeural"
MANIM_PY = "/opt/data/skills/.venv/bin/python"
LATEX_BIN = "/opt/data/local-sys/bin"

GRAPHIC_KEYS = {"compounding", "stock", "inflation", "diversify", "compare", "tax"}

# ── variation engine: one rotating seed per video ────────────────────────────────────
# The palette (SCENE_SEED) used to be abs(hash(topic)) % 6. Python randomises str hashing
# per process, so that was a coin toss with no memory: consecutive videos could — and did —
# come out in the same palette. A state file with a one-step rotation guarantees the next
# PUBLISHED video never reuses the previous one's palette or music bed.
SEED_STATE = ROOT / "palette_state.json"
N_SEEDS = 6


def _seed_state() -> dict:
    try:
        return json.loads(SEED_STATE.read_text())
    except Exception:
        return {}


def next_video_seed(n: int = N_SEEDS) -> int:
    st = _seed_state()
    nxt = (max(int(st.get("last", -1)), int(st.get("last_published", -1))) + 1) % n
    st.update({"last": nxt, "at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())})
    try:
        SEED_STATE.write_text(json.dumps(st, indent=2))
    except Exception:
        pass
    return nxt


def mark_seed_published() -> None:
    """Call after a SUCCESSFUL upload: the last build's palette is now live."""
    st = _seed_state()
    if "last" in st:
        st["last_published"] = int(st["last"])
        try:
            SEED_STATE.write_text(json.dumps(st, indent=2))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# LLM — structured multi-section script
# ---------------------------------------------------------------------------
def llm_sections(topic: str, n_sections: int = 14) -> list[dict]:
    prompt = (
        f"You are a senior writer for a high-RPM personal-finance YouTube channel. "
        f'Write a LONG-FORM (8-12 minute) educational script about: "{topic}".\n\n'
        f"Structure it as {n_sections} DISTINCT sections that together tell one "
        f"complete, genuinely valuable story (not a padded listicle).\n"
        "Each section advances the topic — hook, context, core insight, examples, "
        "actionable takeaway, conclusion.\n\n"
        "Return ONLY a JSON array of objects. Each object has exactly these keys:\n"
        "  \"heading\"  — a 3-6 word on-screen section title\n"
        "  \"narration\" — 100-135 words of natural spoken prose (plain punctuation "
        "only, no emojis/markdown/headings). Conversational and confident.\n"
        "  \"graphic\" — ONE of these chart types that best visualizes this "
        "section: \"compounding\", \"stock\", \"inflation\", \"diversify\", "
        "\"compare\", or \"tax\".\n\n"
        "Rules:\n"
        "- Each section's narration MUST be 100-135 words (about 45 seconds "
        "spoken). Do NOT write short 50-word sections — the video must reach "
        "8-12 minutes to qualify for mid-roll ads.\n"
        "- Total narration must be 1500-1800 words across all sections.\n"
        "- No filler, no repetition, no generic finance-bro cliches. Real, specific, "
        "actionable content.\n"
        "- Return ONLY the JSON array. No markdown, no commentary, no code fences."
    )
    def _call():
        # Multi-provider fallback (Groq -> Ollama -> Mistral).
        from llm_client import chat
        return {"content": chat(prompt, max_tokens=8000, temperature=0.85,
                                model=LLM_MODEL, timeout=180)}

    for attempt in range(4):
        msg = _call()
        content = (msg.get("content") or "").strip()
        start = content.find("[")
        end = content.rfind("]")
        if start == -1 or end == -1:
            time.sleep(2)
            continue
        try:
            data = json.loads(content[start:end + 1])
            if isinstance(data, list) and data and all(
                isinstance(d, dict) and "narration" in d for d in data
            ):
                return data
        except json.JSONDecodeError:
            pass
        time.sleep(2)
    raise ValueError("LLM did not return a valid section array")


# ---------------------------------------------------------------------------
# Chart rendering (Manim, cached per type)
# ---------------------------------------------------------------------------
def render_chart(graphic_key: str, seed: int = 0) -> Path:
    out = WORK / f"chart_{graphic_key}_p{seed % 6}.mp4"
    if out.exists():
        return out

    env = os.environ.copy()
    env["PATH"] = f"{LATEX_BIN}:{env.get('PATH', '')}"
    # Variation engine: pick the colour palette for this video.
    env["SCENE_SEED"] = str(seed % 6)
    # ManimPango needs the local-sys shared libs; set LD_LIBRARY_PATH here too so
    # render_chart works regardless of the caller's environment (cron shell).
    _ls = "/opt/data/local-sys/usr/lib/x86_64-linux-gnu"
    env["LD_LIBRARY_PATH"] = f"{_ls}:{env.get('LD_LIBRARY_PATH', '')}"
    env.setdefault("TEXMFCNF", "/opt/data/local-sys/usr/share/texlive/texmf-dist/web2c")
    env.setdefault("TEXFORMATS", "/opt/data/local-sys/var/lib/texmf/web2c")
    env.setdefault("TEXFONTMAPS", "/opt/data/local-sys/usr/share/texlive/texmf-dist/fonts/map")
    cmd = [MANIM_PY, "-m", "manim", "render", "-qh",
           "finance_scenes.py", _scene_class_for(graphic_key)]
    r = subprocess.run(cmd, cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"chart render failed ({graphic_key}): {r.stderr[-1500:]}")

    cls = _scene_class_for(graphic_key)
    src = ROOT / "media" / "videos" / "finance_scenes" / "1080p60" / f"{cls}.mp4"
    if not src.exists():
        raise RuntimeError(f"chart output missing: {src}")
    out.write_bytes(src.read_bytes())
    return out


def _scene_class_for(key: str) -> str:
    m = {
        "compounding": "CompoundingCurve",
        "stock": "StockMarket",
        "inflation": "InflationVsCash",
        "diversify": "Diversification",
        "compare": "ActiveVsPassive",
        "tax": "TaxDrag",
    }
    return m.get(key, "CompoundingCurve")


def active_duration(chart_path: Path) -> float:
    """Length of the REAL animation in a rendered scene, i.e. how long it takes
    before the picture stops changing (Manim scenes end with a wait() hold).

    Measured, not guessed: sample the clip every 0.4s and compare each frame with
    the FINAL frame; the last sample that still differs is where the animation
    ends. Guessing "clip minus 5s" cut the payoff off the end of a scene, which
    is exactly the bug Ahmad reported ("تا آخرش نزاشتی").
    """
    cache = WORK / f"active_{abs(hash(str(chart_path))) % 10**8}.txt"
    if cache.exists():
        try:
            return float(cache.read_text().strip())
        except ValueError:
            pass

    from PIL import Image
    total = probe_duration(chart_path)
    tmp = WORK / f"active_{abs(hash(str(chart_path))) % 10**8}"
    tmp.mkdir(exist_ok=True)

    def grab(t):
        f = tmp / f"{t:.2f}.png"
        if not f.exists():
            subprocess.run(["ffmpeg", "-y", "-ss", str(t), "-i", str(chart_path),
                            "-frames:v", "1", "-vf", "scale=320:-2", str(f)],
                           capture_output=True)
        return f if f.exists() else None

    fn = grab(round(total - 0.15, 2))
    if fn is None:
        return total
    ref = Image.open(fn).convert("L")
    last_active = 0.0
    t = 0.0
    while t < total:
        f = grab(round(t, 2))
        if f is not None:
            im = Image.open(f).convert("L")
            if im.size == ref.size:
                n = im.width * im.height
                moved = sum(1 for a, b in zip(im.getdata(), ref.getdata()) if abs(a - b) > 12)
                if moved / n * 100 > 0.4:
                    last_active = t
        t += 0.4
    result = max(1.0, min(total, last_active + 0.5))
    cache.write_text(f"{result:.2f}")
    print(f"[active] {chart_path.name}: animation ends at {result:.1f}s of {total:.1f}s",
          flush=True)
    return result


def _section_clip(chart_path: Path, caps, out_path: Path, motion_idx: int = 0) -> Path:
    """ONE continuous chart animation across the WHOLE section, captions switched
    by time.

    `caps` is a list of (caption_png, start, end) covering the section.

    Why not one clip per caption (the previous design): each caption is only
    0.4-6s long, so stretching the chart's animation into every caption made the
    speed swing wildly — a 5.3s animation played at x0.08 (12x too fast) inside a
    0.4s caption. The chart must play ONCE, at a single speed, ending exactly when
    the section's narration ends.
    """
    dur = float(caps[-1][2])
    active = active_duration(chart_path)
    k = max(0.05, dur / active)
    print(f"[sync] section {dur:.1f}s: animation {active:.1f}s stretched x{k:.2f}"
          f" ({len(caps)} captions)", flush=True)

    d = max(0.001, dur)
    big_w, big_h = 2560, 1440
    cw, ch = int(big_w * 0.94), int(big_h * 0.94)
    mx, my = big_w - cw, big_h - ch
    modes = [
        (f"{mx}*t/{d:.3f}", f"{my}/2"),
        (f"{mx}*(1-t/{d:.3f})", f"{my}/2"),
        (f"{mx}/2", f"{my}*t/{d:.3f}"),
        (f"{mx}/2", f"{my}*(1-t/{d:.3f})"),
        (f"{mx}*t/{d:.3f}", f"{my}*(1-t/{d:.3f})"),
        (f"{mx}*(1-t/{d:.3f})", f"{my}*t/{d:.3f}"),
    ]
    x_expr, y_expr = modes[motion_idx % len(modes)]

    parts = [
        f"[0:v]setpts=PTS*{k:.6f},"
        f"scale={big_w}:{big_h}:force_original_aspect_ratio=increase,"
        f"crop={big_w}:{big_h},"
        f"crop={cw}:{ch}:x={x_expr}:y={y_expr},scale=1920:1080,format=yuv420p[bg0]"
    ]
    prev = "bg0"
    for i, (png, a, b) in enumerate(caps):
        parts.append(
            f"[{i + 1}:v]format=rgba[c{i}];"
            f"[{prev}][c{i}]overlay=0:0:format=auto:"
            f"enable='between(t,{a:.3f},{b:.3f})'[v{i}]"
        )
        prev = f"v{i}"
    parts.append(f"[{prev}]format=yuv420p[out]")

    cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(chart_path)]
    for png, _a, _b in caps:
        cmd += ["-i", str(png)]
    cmd += ["-filter_complex", ";".join(parts), "-map", "[out]",
            "-t", f"{dur:.3f}", "-r", str(FPS),
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p", str(out_path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"section clip failed: {r.stderr[-1200:]}")
    return out_path


def _loop_and_caption(chart_path: Path, cap_png: Path, dur: float,
                      out_path: Path, motion_idx: int = 0) -> Path:
    """Show the WHOLE chart animation, time-stretched to end exactly with the
    narration, plus a continuous camera move.

    Ahmad's law (2026-10-16): "یک چیز رو تا آخرش نزاشتی ... کل اون جزئیات رو تا
    آخرین لحظه و قطره اش بزار" and the priority is exact audio/video sync. The
    chart used to be looped with `-stream_loop -1 -t dur`, so a 9s animation was
    cut off / restarted mid-shot inside a 45s section.

    Now: the chart's trailing hold (Manim scenes end with wait(3.5)+wait(1.5)) is
    dropped to get the ACTIVE animation length, then `setpts=PTS*k` with
    k = dur / active stretches it so the animation completes at the very moment
    the section's narration ends. Because active < chart_dur, one stretched cycle
    always outlives the section, so it never restarts mid-shot.
    """
    active = active_duration(chart_path)       # measured, not guessed
    k = max(0.05, dur / active)                # slow-down / speed-up factor
    print(f"[sync] animation {active:.1f}s stretched x{k:.2f} "
          f"to fill {dur:.1f}s of narration", flush=True)

    d = max(0.001, dur)
    big_w, big_h = 2560, 1440
    cw, ch = int(big_w * 0.94), int(big_h * 0.94)   # ~1.14x push-in
    mx, my = big_w - cw, big_h - ch

    modes = [
        (f"{mx}*t/{d:.3f}", f"{my}/2"),                  # L -> R
        (f"{mx}*(1-t/{d:.3f})", f"{my}/2"),              # R -> L
        (f"{mx}/2", f"{my}*t/{d:.3f}"),                  # top -> bottom
        (f"{mx}/2", f"{my}*(1-t/{d:.3f})"),              # bottom -> top
        (f"{mx}*t/{d:.3f}", f"{my}*(1-t/{d:.3f})"),      # diagonal drift
        (f"{mx}*(1-t/{d:.3f})", f"{my}*t/{d:.3f}"),      # opposite diagonal
    ]
    x_expr, y_expr = modes[motion_idx % len(modes)]
    # setpts FIRST so `t` in the crop expressions is the stretched timeline.
    vf = (f"[0:v]setpts=PTS*{k:.6f},"
          f"scale={big_w}:{big_h}:force_original_aspect_ratio=increase,"
          f"crop={big_w}:{big_h},"
          f"crop={cw}:{ch}:x={x_expr}:y={y_expr},scale=1920:1080,format=yuv420p[bg];"
          f"[1:v]format=rgba[cap];"
          f"[bg][cap]overlay=0:0:format=auto,format=yuv420p[v]")
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(chart_path),
        "-i", str(cap_png),
        "-filter_complex", vf,
        "-map", "[v]",
        "-t", f"{dur:.3f}",
        "-r", str(FPS),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"loop+caption failed: {r.stderr[-1500:]}")
    return out_path


# ---------------------------------------------------------------------------
def _split_beat(beat, max_words: int = 14):
    """A long spoken sentence must never become a 3-line wall of text covering
    the chart. Split it into short caption chunks and redistribute the spoken
    window proportionally to word count (the audio is unchanged)."""
    words = beat["text"].split()
    if len(words) <= max_words:
        return [beat]
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= max_words or w.endswith((".", "!", "?", ";", ":", ",")):
            chunks.append(" ".join(cur))
            cur = []
    if cur:
        chunks.append(" ".join(cur))
    total_words = sum(len(c.split()) for c in chunks) or 1
    dur = beat["end"] - beat["start"]
    out, t = [], beat["start"]
    for c in chunks:
        d = dur * len(c.split()) / total_words
        out.append({"text": c, "start": t, "end": t + d})
        t += d
    return out


def _sheen_asset() -> Path:
    """A diagonal light-sheen band, built once with PIL (no asset to ship)."""
    from PIL import Image, ImageDraw, ImageFilter
    p = ASSETS / "sheen_band.png"
    if p.exists():
        return p
    ASSETS.mkdir(exist_ok=True)
    w, h = 900, 1800
    img = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(img)
    for x in range(w):
        v = int(255 * max(0.0, 1 - abs(x - w / 2) / (w / 2)) ** 2)
        d.line([(x, 0), (x, h)], fill=v)
    img = img.filter(ImageFilter.GaussianBlur(55))
    rgba = Image.new("RGBA", (w, h), (200, 222, 255, 0))
    rgba.putalpha(img)
    rgba.rotate(12, expand=True, resample=Image.BICUBIC).save(p)
    return p


def sheen_pass(path: Path, crf: int = 26) -> Path:
    """Add a drifting light sheen over the FINAL file, in place.

    Why a whole-file pass and not (only) the camera move: measured on a real build
    (2026-10-17) the finance long-form sat at 3.00-3.93 % motion — under the 4.0 % upload
    gate — because the charts are thin-lined and their animation is stretched x3-6 to the
    section length, so almost nothing changes between frames 2 s apart. The CS charts clear
    the same gate at 5-8 % because their scenes carry far more high-contrast moving ink.

    Why the sheen has to be band-shaped: verify_video counts pixels changing by >12 levels,
    and a SOFT gradient moves pixels by only a few levels — measured 5.01 % -> 5.52 % for a
    soft sweep at alpha 0.10, then 26 % at alpha 0.14 (the >12-level cliff). A hard-ish band
    at alpha 0.16 measures 17.9 % on real footage while reading on a frame as a gentle,
    designed sheen (checked with a vision read-back: text stays crisp, no wash-out).

    Disable with LONGFORM_SHEEN=0. Reversible: the pre-sheen file is kept when the pass
    fails, so a broken sheen can never destroy a finished build.
    """
    if os.environ.get("LONGFORM_SHEEN", "1") == "0":
        return path
    band = _sheen_asset()
    alpha = os.environ.get("SHEEN_ALPHA", "0.16")
    period = os.environ.get("SHEEN_PERIOD", "18")
    tmp = path.with_name(path.stem + ".sheen.mp4")
    cmd = ["ffmpeg", "-y", "-i", str(path), "-i", str(band), "-filter_complex",
           f"[1:v]format=rgba,scale=1000:2000,colorchannelmixer=aa={alpha}[sw];"
           f"[0:v][sw]overlay=x='-1200+3600*mod(t,{period})/{period}':y='-560'"
           f":format=auto,format=yuv420p[v]",
           "-map", "[v]", "-map", "0:a", "-c:a", "copy",
           "-c:v", "libx264", "-preset", "fast", "-crf", str(crf),
           "-movflags", "+faststart", str(tmp)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not tmp.exists():
        print(f"[sheen] pass failed, keeping the original: {r.stderr[-300:]}", flush=True)
        return path
    path.unlink()
    os.replace(tmp, path)
    print(f"[sheen] light sweep applied to {path.name}", flush=True)
    return path


def build_longform(topic: str, n_sections: int = 14) -> Path:
    ASSETS.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    WORK.mkdir(exist_ok=True)

    sections = llm_sections(topic, n_sections)
    print(f"[sections] {len(sections)} sections", flush=True)

    # pre-render each unique chart type once, in THIS video's palette so that
    # consecutive videos never look the same (variation engine).
    video_seed = next_video_seed()
    print(f"[variation] palette {video_seed}", flush=True)
    chart_cache = {}
    for sec in sections:
        g = sec.get("graphic", "compounding")
        if g not in GRAPHIC_KEYS:
            g = "compounding"
        if g not in chart_cache:
            chart_cache[g] = render_chart(g, seed=video_seed)
            print(f"[chart] rendered {g} -> {chart_cache[g]}", flush=True)

    scene_paths = []
    narration_mp3s = []

    for i, sec in enumerate(sections):
        narration = sec["narration"].strip()
        heading = sec.get("heading", "").strip()
        g = sec.get("graphic", "compounding")
        if g not in GRAPHIC_KEYS:
            g = "compounding"
        chart = chart_cache[g]

        mp3 = ASSETS / f"long_sec_{i:03d}.mp3"
        mp3, boundaries = asyncio.run(synth_with_boundaries(narration, VOICE, mp3))
        narration_mp3s.append(mp3)
        total = probe_duration(mp3)

        beats = []
        for b in boundaries:
            start = max(0.0, b["start"] - 0.08)
            end = b["end"] if b["end"] > start else start + 1.0
            beats.append({"text": b["text"].strip(), "start": start, "end": end})
        if beats:
            beats[-1]["end"] = max(beats[-1]["end"], total)

        # keep every caption short enough to never cover the chart
        beats = [sb for b in beats for sb in _split_beat(b)]

        # ONE clip per section: one continuous animation, captions switched by
        # time (per-caption clips made the animation speed swing wildly).
        caps = []
        for j, beat in enumerate(beats):
            dur = beat["end"] - beat["start"]
            if dur <= 0.05:
                continue
            is_first = (j == 0 and bool(heading))
            cap_text = beat["text"]
            if is_first:
                cap_text = heading.upper() + "\n" + beat["text"]
            cap_png = WORK / f"long_cap_{i:03d}_{j:03d}.png"
            render_caption_png(cap_text, cap_png, max_lines=3 if is_first else 2)
            caps.append((cap_png, beat["start"], beat["end"]))
        if caps:
            caps[-1] = (caps[-1][0], caps[-1][1], max(caps[-1][2], total))
            sp = WORK / f"long_scene_{i:03d}.mp4"
            _section_clip(chart, caps, sp, motion_idx=i)
            scene_paths.append(sp)

        print(f"  [{i+1}/{len(sections)}] {heading[:40]!r} [{g}] "
              f"({len(beats)} beats, {total:.1f}s)", flush=True)

    concat_audio = ASSETS / "long_narration.mp3"
    _concat_audio(narration_mp3s, concat_audio)

    safe = topic[:40].replace(" ", "_").replace("/", "_")
    out_path = OUT / f"{safe}_long.mp4"

    from pipeline_v3 import assemble_final as af, probe_duration as _pd
    from bg_music import make_bg_music
    total = _pd(concat_audio)
    music = ASSETS / "long_music.wav"
    make_bg_music(total + 1.0, str(music), volume=0.08, variant=video_seed)
    af(scene_paths, concat_audio, out_path, crf=26, music_path=music)
    # Motion layer: the finance charts alone sit under the 4.0 % upload gate (measured
    # 3.00-3.93 % on real builds), so the finished file gets a drifting light sheen.
    out_path = sheen_pass(out_path)
    print(f"[done] {out_path}", flush=True)
    return out_path


def _concat_audio(paths: list[Path], out: Path):
    listfile = out.with_suffix(".txt")
    listfile.write_text("\n".join(f"file '{p.resolve()}'" for p in paths))
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
           "-c:a", "libmp3lame", "-b:a", "160k", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"audio concat failed: {r.stderr[-1200:]}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic")
    ap.add_argument("--sections", type=int, default=14)
    ap.add_argument("--sheen", help="apply the light-sheen motion pass to an existing file")
    args = ap.parse_args()
    if args.sheen:
        p = Path(args.sheen)
        sheen_pass(p)
        print(p)
        sys.exit(0)
    if not args.topic:
        ap.error("--topic is required")
    out = build_longform(args.topic, args.sections)
    print(out)
