#!/usr/bin/env python3
"""
Faceless YouTube pipeline v3 — cinematic motion, FFmpeg-native.

True camera motion via FFmpeg `zoompan` (sub-pixel smooth, eased), xfade
transitions, 60fps minterpolate, and a cinematic teal-orange grade.
Captions rendered as transparent PNGs with PIL and overlaid.

Stages:
  script (LLM) -> tts (edge-tts, sentence boundaries)
  -> per-scene motion video (ffmpeg zoompan) + caption PNG (PIL)
  -> xfade chain + minterpolate + grade (ffmpeg) -> mp4

Usage:
  python pipeline_v3.py --topic "You are not lazy" \
      --voice en-US-GuyNeural --lang en --style cinematic
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

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
OUT = ROOT / "out"
WORK = ROOT / "work"
FONT_BOLD = Path("/opt/data/workspace/iman-logo/fonts/Poppins-Bold.ttf")
FONT_SEMI = Path("/opt/data/workspace/iman-logo/fonts/Poppins-SemiBold.ttf")

W, H = 1920, 1080
FPS = 30

# ----------------------------------------------------------------------------
# LLM
# ----------------------------------------------------------------------------
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://ollama.com/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-v4-pro:0813")


def llm_script(topic: str, lang: str, style: str) -> str:
    lang_name = "Persian (Farsi)" if lang.startswith("fa") else "English"
    prompt = (
        f"Write a 70-90 second faceless YouTube voiceover script in {lang_name} "
        f'about this topic: "{topic}". '
        f"Style: {style}. "
        "Requirements:\n"
        "- Start with a bold, hooky first sentence that stops the scroll.\n"
        "- Use short, punchy sentences that read well when spoken aloud.\n"
        "- End with a memorable closing line.\n"
        "- Plain punctuation only (. ! ?). No emojis, no markdown, no headings.\n"
        "- Return ONLY the narration text."
    )
    def _call():
        body = json.dumps({
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 900,
            "temperature": 0.85,
        }).encode()
        req = urllib.request.Request(
            LLM_BASE_URL.rstrip("/") + "/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {LLM_API_KEY}",
                     "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.load(r)["choices"][0]["message"]

    for attempt in range(4):
        msg = _call()
        content = (msg.get("content") or "").strip()
        if content:
            return content
        time.sleep(1.0 * (attempt + 1))
    return (msg.get("reasoning") or "").strip() or content


# ----------------------------------------------------------------------------
# TTS + boundaries
# ----------------------------------------------------------------------------
async def synth_with_boundaries(text: str, voice: str, out_mp3: Path):
    import edge_tts
    comm = edge_tts.Communicate(text, voice)
    boundaries = []
    audio_bytes = bytearray()
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            audio_bytes.extend(chunk["data"])
        elif chunk["type"] == "SentenceBoundary":
            boundaries.append({
                "text": chunk["text"],
                "start": chunk["offset"] / 1e7,
                "end": (chunk["offset"] + chunk["duration"]) / 1e7,
            })
    out_mp3.write_bytes(bytes(audio_bytes))
    return out_mp3, boundaries


# ----------------------------------------------------------------------------
# Visuals
# ----------------------------------------------------------------------------
def fetch_images(n: int, out_dir: Path, seed: int = 0) -> list[Path]:
    paths = []
    for i in range(n):
        p = out_dir / f"img_{i:02d}.jpg"
        url = f"https://picsum.photos/seed/faceless{seed}_{i}/1920/1080"
        urllib.request.urlretrieve(url, str(p))
        paths.append(p)
    return paths


def probe_duration(path: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "json", str(path)]
    return float(json.loads(subprocess.check_output(cmd))["format"]["duration"])


# ----------------------------------------------------------------------------
# Caption PNG (PIL) — readable white text on soft dark gradient
# ----------------------------------------------------------------------------
def render_caption_png(text: str, out_png: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

    font = ImageFont.truetype(str(FONT_BOLD), 66)
    max_w = int(W * 0.82)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    words = text.split()
    lines, cur = [], ""
    for w_ in words:
        test = (cur + " " + w_).strip()
        if probe.textbbox((0, 0), test, font=font)[2] <= max_w:
            cur = test
        else:
            lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)

    line_h = int(font.size * 1.35)
    pad = 34
    txt_h = line_h * len(lines)
    widest = max(probe.textbbox((0, 0), l, font=font)[2] for l in lines)
    box_w = widest + pad * 2
    box_h = txt_h + pad * 2

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    band = Image.new("RGBA", (W, box_h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    for y in range(box_h):
        a = int(150 * (1 - abs(y - box_h / 2) / (box_h / 2)))
        bd.line([(0, y), (W, y)], fill=(0, 0, 0, a))
    band = band.filter(ImageFilter.GaussianBlur(6))
    img.paste(band, (0, int(H * 0.66)), band)

    d = ImageDraw.Draw(img)
    y0 = int(H * 0.66) + pad
    for l in lines:
        bb = d.textbbox((0, 0), l, font=font)
        tw = bb[2] - bb[0]
        x = (W - tw) // 2
        d.text((x, y0), l, font=font, fill="white",
               stroke_width=3, stroke_fill="black")
        y0 += line_h

    img.save(out_png)
    return out_png


# ----------------------------------------------------------------------------
# Per-scene motion video via FFmpeg zoompan
# ----------------------------------------------------------------------------
def render_scene_ffmpeg(img_path: Path, caption_png, dur: float,
                        out_path: Path, motion_idx: int) -> Path:
    mode = motion_idx % 4
    frames = max(1, int(dur * FPS))

    if mode == 0:      # zoom in
        z_expr = f"1.08 + 0.14*on/{frames}"
        x_expr, y_expr = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif mode == 1:    # zoom out
        z_expr = f"1.22 - 0.14*on/{frames}"
        x_expr, y_expr = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif mode == 2:    # pan left -> right
        z_expr = "1.16"
        x_expr = f"(iw-iw/zoom)*on/{frames}"
        y_expr = "ih/2-(ih/zoom/2)"
    else:              # pan bottom -> top
        z_expr = "1.16"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = f"(ih-ih/zoom)*(1-on/{frames})"

    fc = (f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':"
          f"d={frames}:s={W}x{H}:fps={FPS}")

    inputs = ["-loop", "1", "-i", str(img_path)]
    fchain = [f"[0:v]{fc}[v]"]
    maps = ["-map", "[v]"]

    if caption_png is not None:
        inputs += ["-i", str(caption_png)]
        fchain.append("[1:v]format=rgba[cap]")
        fchain.append("[v][cap]overlay=0:0:format=auto[vo]")
        maps = ["-map", "[vo]"]

    cmd = (["ffmpeg", "-y"] + inputs
           + ["-filter_complex", ";".join(fchain)]
           + maps
           + ["-t", f"{dur:.3f}", "-r", str(FPS),
              "-c:v", "libx264", "-preset", "fast", "-crf", "19",
              "-pix_fmt", "yuv420p", str(out_path)])

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"render_scene failed (idx {motion_idx}):",
              r.stderr[-1500:], file=sys.stderr)
        raise SystemExit(1)
    return out_path


# ----------------------------------------------------------------------------
# Final assemble: xfade + minterpolate + grade
# ----------------------------------------------------------------------------
def assemble_final(scene_paths: list[Path], narration_mp3: Path,
                   out_path: Path, t_dur: float = 0.6) -> Path:
    # Use the concat DEMUXER (single sequential input, ~1 decoder in RAM)
    # instead of the concat FILTER (N simultaneous inputs). The filter held 45
    # 1080p decoders + a grade graph at once and got OOM-killed on a 7.7GB,
    # swap-less box. The demuxer streams scenes one after another, so memory
    # stays flat regardless of scene count.
    listfile = out_path.with_suffix(".concat.txt")
    # Absolute paths: the concat demuxer resolves entries relative to the
    # listfile's own directory, not the cwd.
    listfile.write_text("\n".join(f"file '{p.resolve()}'" for p in scene_paths))

    grade = (
        "eq=contrast=1.06:saturation=1.12:brightness=-0.01,"
        "colorbalance=rs=.06:gs=.02:bs=-.06:rm=.02:bm=-.01,"
        "vignette=PI/5"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(listfile),
        "-i", str(narration_mp3),
        "-filter_complex", f"[0:v]{grade}[gv]",
        "-map", "[gv]", "-r", "30", "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
        "-map", "1:a", "-c:a", "aac", "-b:a", "160k", "-shortest",
        "-movflags", "+faststart", str(out_path),
    ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("assemble_final failed:", r.stderr[-2500:], file=sys.stderr)
        raise SystemExit(1)
    return out_path


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True)
    ap.add_argument("--voice", default="en-US-GuyNeural")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--style", default="cinematic, dramatic, introspective")
    ap.add_argument("--images", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    ASSETS.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    WORK.mkdir(exist_ok=True)

    script = llm_script(args.topic, args.lang, args.style)
    print("[script]", len(script), "chars")

    # cache script+boundaries for reproducibility / re-render
    cache = WORK / "state.json"
    if cache.exists():
        try:
            state = json.loads(cache.read_text())
            if state.get("topic") == args.topic:
                script = state["script"]
                boundaries = state["boundaries"]
                print("[cache] reused script + boundaries")
                total = probe_duration(ASSETS / "narration.mp3")
            else:
                raise ValueError("cache topic mismatch")
        except Exception:
            cache.unlink(missing_ok=True)

    if not cache.exists():
        mp3 = ASSETS / "narration.mp3"
        mp3, boundaries = asyncio.run(synth_with_boundaries(script, args.voice, mp3))
        total = probe_duration(mp3)
        cache.write_text(json.dumps({
            "topic": args.topic, "script": script, "boundaries": boundaries,
        }, ensure_ascii=False))
        print(f"[tts] {len(boundaries)} boundaries, {total:.1f}s")

    images = fetch_images(args.images, ASSETS, args.seed)
    print(f"[visuals] {len(images)} images")

    beats = []
    for i, b in enumerate(boundaries):
        start = max(0.0, b["start"] - 0.08)
        end = b["end"] if b["end"] > start else start + 1.0
        if i < len(boundaries) - 1:
            end = min(end, boundaries[i + 1]["start"])
        beats.append({"text": b["text"].strip(), "start": start, "end": end})
    if beats:
        beats[-1]["end"] = max(beats[-1]["end"], total)

    scene_paths = []
    for i, beat in enumerate(beats):
        dur = beat["end"] - beat["start"]
        if dur <= 0.05:
            continue
        img = images[i % len(images)]
        cap_png = None
        if beat["text"]:
            cap_png = WORK / f"cap_{i:03d}.png"
            render_caption_png(beat["text"], cap_png)
        sp = WORK / f"scene_{i:03d}.mp4"
        render_scene_ffmpeg(img, cap_png, dur, sp, i)
        scene_paths.append(sp)
    print(f"[motion] {len(scene_paths)} scenes rendered")

    safe = args.topic[:50].replace(" ", "_").replace("/", "_")
    out_path = OUT / f"{safe}_v3.mp4"
    assemble_final(scene_paths, mp3, out_path)
    print(f"[done] {out_path}")


if __name__ == "__main__":
    main()
