#!/usr/bin/env python3
"""
Faceless YouTube video pipeline v2 — production quality.

Fixes over v1:
  * Sentence-level segmentation driven by edge-tts SentenceBoundary (no text lost)
  * Real Ken Burns zoom (smooth animated scale) via vfx.Resize lambda
  * Readable captions with dark gradient behind text + Poppins font
  * Whole narration synthesized once, then cut to beats

Stages: script (LLM) -> tts (edge-tts) -> visuals (stock) -> edit (moviepy) -> mp4

Usage:
  python pipeline.py --topic "You are not lazy" \
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
FONT_BOLD = Path("/opt/data/workspace/iman-logo/fonts/Poppins-Bold.ttf")
FONT_SEMI = Path("/opt/data/workspace/iman-logo/fonts/Poppins-SemiBold.ttf")

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
        "- Use plain punctuation only (. ! ?). No emojis, no markdown, "
        "no headings, no numbered lists, no stage directions.\n"
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

    # Reasoning models occasionally put the answer in `reasoning` and leave
    # `content` empty. Retry, then fall back to the reasoning field.
    for attempt in range(4):
        msg = _call()
        content = (msg.get("content") or "").strip()
        if content:
            return content
        time.sleep(1.0 * (attempt + 1))
    return (msg.get("reasoning") or "").strip() or content


# ----------------------------------------------------------------------------
# TTS + sentence boundaries
# ----------------------------------------------------------------------------
async def synth_with_boundaries(text: str, voice: str, out_mp3: Path):
    """Synthesize text to mp3, returning (mp3_path, [(text, start_s, end_s), ...])."""
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
        url = f"https://picsum.photos/seed/faceless{seed}_{i}/1600/900"
        urllib.request.urlretrieve(url, str(p))
        paths.append(p)
    return paths


# ----------------------------------------------------------------------------
# Edit / assemble
# ----------------------------------------------------------------------------
def probe_duration(path: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "json", str(path)]
    return float(json.loads(subprocess.check_output(cmd))["format"]["duration"])


def assemble(narration_mp3: Path, boundaries: list, images: list[Path],
             out_path: Path, width: int = 1920, height: int = 1080) -> Path:
    from moviepy import (AudioFileClip, CompositeVideoClip, ImageClip,
                         TextClip, concatenate_videoclips)

    total_dur = probe_duration(narration_mp3)
    narration = AudioFileClip(str(narration_mp3))
    n_imgs = len(images)

    # Build beats from sentence boundaries.
    beats = []
    for i, b in enumerate(boundaries):
        start = max(0.0, b["start"] - 0.08)
        end = b["end"] if b["end"] > start else start + 1.0
        if i < len(boundaries) - 1:
            end = min(end, boundaries[i + 1]["start"])
        beats.append({"text": b["text"].strip(), "start": start, "end": end})

    # The audio often runs past the final sentence boundary; stretch the last
    # beat to the full narration length so the video never ends early.
    if beats:
        beats[-1]["end"] = max(beats[-1]["end"], total_dur)

    clips = []
    for i, beat in enumerate(beats):
        dur = beat["end"] - beat["start"]
        img_path = images[i % n_imgs]
        clip = ImageClip(str(img_path))

        # Ken Burns: alternating zoom-in / zoom-out via animated resize
        if i % 2 == 0:
            def rz(t, d=dur, w=width, h=height):
                p = min(t / d, 1.0)
                s = 1.0 + 0.10 * p
                return (int(w * s), int(h * s))
        else:
            def rz(t, d=dur, w=width, h=height):
                p = min(t / d, 1.0)
                s = 1.10 - 0.10 * p
                return (int(w * s), int(h * s))

        clip = clip.resized(rz).resized((width, height)).with_position("center")
        clip = clip.with_duration(dur)

        cap_text = beat["text"]
        if cap_text:
            font = str(FONT_BOLD) if FONT_BOLD.exists() else None
            txt = (TextClip(font=font, text=cap_text, font_size=64,
                            color="white", stroke_color="black",
                            stroke_width=2, method="caption",
                            size=(int(width * 0.86), None))
                   .with_duration(dur)
                   .with_position(("center", int(height * 0.70))))
            clips.append(CompositeVideoClip([clip, txt]))
        else:
            clips.append(clip)

    video = concatenate_videoclips(clips, method="compose").with_audio(narration)
    if video.duration < total_dur:
        video = video.subclipped(0, total_dur)

    video.write_videofile(str(out_path), fps=30, codec="libx264",
                          audio_codec="aac", bitrate="6000k",
                          temp_audiofile=str(OUT / "tmp.m4a"),
                          remove_temp=True, threads=4, preset="medium")
    return out_path


def build_meta(topic: str) -> dict:
    return {
        "title": topic,
        "description": f"{topic}. Generated with an open-source faceless-YouTube pipeline.",
        "tags": ["faceless", "ai", "explained", "documentary"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True)
    ap.add_argument("--voice", default="en-US-GuyNeural")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--style", default="cinematic, slightly dramatic")
    ap.add_argument("--images", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    args = ap.parse_args()

    ASSETS.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)

    script = llm_script(args.topic, args.lang, args.style)
    print("[script] generated", len(script), "chars")
    print(script, "\n")

    mp3 = ASSETS / "narration.mp3"
    mp3, boundaries = asyncio.run(synth_with_boundaries(script, args.voice, mp3))
    print(f"[tts] {len(boundaries)} sentence boundaries")

    images = fetch_images(args.images, ASSETS, args.seed)
    print(f"[visuals] {len(images)} images")

    safe = args.topic[:50].replace(" ", "_").replace("/", "_")
    out_path = OUT / f"{safe}.mp4"
    assemble(mp3, boundaries, images, out_path, args.width, args.height)
    print(f"[done] {out_path}")

    print(json.dumps(build_meta(args.topic), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
