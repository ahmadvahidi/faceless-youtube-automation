#!/usr/bin/env python3
"""Educational video generator for the networking / IT-fundamentals series.

Reuses the render chain from pipeline_v3 (TTS -> topical images -> ffmpeg
scenes -> final assemble) but with an *educational* script prompt instead of
the finance "cinematic hook" style. Supports English and Persian narration.

Usage:
    python networking_videos.py <topic> [en|fa] [seed]
    python networking_videos.py --list                 # print the curriculum
"""

import asyncio
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from send_to_group import _load_env
_load_env()

from pipeline_v3 import (  # noqa: E402
    synth_with_boundaries, fetch_topical_images,
    render_caption_png, render_scene_ffmpeg, assemble_final, probe_duration,
    ASSETS, OUT, WORK,
)
from llm_client import chat  # noqa: E402

VOICES = {"en": "en-US-GuyNeural", "fa": "fa-IR-FaridNeural"}
STYLE = ("educational, clear, beginner-friendly, technically accurate, "
         "with a concrete real-world example")


def educational_script(topic: str, lang: str = "en", seconds: int = 80) -> str:
    """Write a clear teaching narration (no finance framing, no clickbait).

    Enforces a hard word budget: the model overshoots badly when unconstrained
    (one run produced 5.3 minutes for a 80-second target).
    """
    lang_name = "Persian (Farsi)" if lang.startswith("fa") else "English"
    target_words = int(seconds * 2.6)  # ~2.6 spoken words per second
    prompt = (
        f"Write a {seconds}-second educational voice-over script in {lang_name} "
        f'that clearly explains this computer-networking concept: "{topic}".\n'
        f"HARD LENGTH LIMIT: {target_words} words MAXIMUM — never exceed it. "
        "Going over the limit breaks the video timing.\n"
        "This is for a computer-networking / IT-fundamentals course aimed at "
        "beginners.\n"
        "Requirements:\n"
        "- Open by stating, in one plain sentence, what this concept IS.\n"
        "- Then explain it simply but stay technically accurate — no dumbing down "
        "to the point of being wrong.\n"
        "- Include ONE concrete real-world example or analogy.\n"
        "- Short, spoken-friendly sentences.\n"
        "- Plain punctuation only (. ! ?). No emojis, no markdown, no headings, "
        "no bullet points.\n"
        "- Return ONLY the narration text, nothing else."
    )
    text = chat(prompt, max_tokens=1000, temperature=0.7, model=None).strip()
    # Hard safety net: trim back to the budget on a sentence boundary.
    words = text.split()
    if len(words) > target_words:
        head = " ".join(words[:target_words])
        cut = max(head.rfind("."), head.rfind("!"), head.rfind("?"))
        text = head[: cut + 1] if cut > len(head) * 0.5 else head
    return text


def image_query_for(topic: str) -> str:
    """Turn a topic into 2-4 English stock-photo keywords (image search works
    far better in English than Persian). Falls back to a safe generic query
    when the model returns prose instead of keywords."""
    raw = chat(
        "Output ONLY 2-4 simple English stock-photo keywords, space-separated, "
        "no punctuation and no explanation, describing this IT/networking "
        f"topic: {topic}",
        max_tokens=200, temperature=0.2,
    ).strip().strip('"').strip(".")
    words = re.sub(r"[^A-Za-z0-9 ]", " ", raw).split()
    # a real keyword answer is short; anything longer is model prose/reasoning
    if not (1 <= len(words) <= 5):
        return "computer network"
    return " ".join(words)


def make_video(topic: str, lang: str = "en", seed: int | None = None) -> Path:
    seed = seed or int(time.time())
    voice = VOICES.get(lang, VOICES["en"])

    print(f"[1/5] writing {lang} script for: {topic}", flush=True)
    script = educational_script(topic, lang)
    print(f"      script: {len(script)} chars", flush=True)

    print("[2/5] synthesizing narration...", flush=True)
    mp3 = ASSETS / f"narr_{seed}.mp3"
    mp3, boundaries = asyncio.run(synth_with_boundaries(script, voice, mp3))
    total = probe_duration(mp3)

    beats = []
    for i, b in enumerate(boundaries):
        start = max(0.0, b["start"] - 0.08)
        end = b["end"] if b["end"] > start else start + 1.0
        if i < len(boundaries) - 1:
            end = min(end, boundaries[i + 1]["start"])
        beats.append({"text": b["text"].strip(), "start": start, "end": end})
    if beats:
        beats[-1]["end"] = max(beats[-1]["end"], total)
    print(f"      {len(beats)} scenes, {total:.1f}s", flush=True)

    print("[3/5] fetching topical images...", flush=True)
    q = image_query_for(topic)
    print(f"      image query: {q!r}", flush=True)
    images = fetch_topical_images(q, len(beats), ASSETS, seed)

    print("[4/5] rendering scenes...", flush=True)
    scene_paths = []
    for i, beat in enumerate(beats):
        dur = beat["end"] - beat["start"]
        if dur <= 0.05:
            continue
        img = images[i % len(images)]
        cap = None
        if beat["text"]:
            cap = WORK / f"ncap_{seed}_{i:03d}.png"
            render_caption_png(beat["text"], cap)
        sp = WORK / f"nscene_{seed}_{i:03d}.mp4"
        render_scene_ffmpeg(img, cap, dur, sp, i)
        scene_paths.append(sp)

    print("[5/5] assembling final video...", flush=True)
    out = OUT / f"net_{seed}.mp4"
    assemble_final(scene_paths, mp3, out)
    return out


def list_curriculum():
    f = ROOT / "networking_curriculum.md"
    print(f.read_text() if f.exists() else "curriculum file not found")


def main():
    for d in (ASSETS, OUT, WORK):
        d.mkdir(exist_ok=True)
    if "--list" in sys.argv:
        list_curriculum()
        return
    if len(sys.argv) < 2:
        print(__doc__)
        return
    topic = sys.argv[1]
    lang = sys.argv[2] if len(sys.argv) > 2 else "en"
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else None
    path = make_video(topic, lang, seed)
    print(json.dumps({"topic": topic, "lang": lang, "path": str(path)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
