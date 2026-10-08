#!/usr/bin/env python3
"""
Batch generator: pick N trending topics and produce faceless YouTube videos.

Reuses pipeline_v3.py functions. Outputs a JSON array of
[{title, description, path}] to stdout for the cron agent to deliver.

Usage:
  python daily_videos.py 2
"""

import asyncio
import json
import sys
import time
import urllib.request
from pathlib import Path

from pipeline_v3 import (
    LLM_BASE_URL, LLM_API_KEY, LLM_MODEL,
    llm_script, synth_with_boundaries, fetch_images,
    render_caption_png, render_scene_ffmpeg, assemble_final, probe_duration,
    ASSETS, OUT, WORK,
)

VOICE = "en-US-GuyNeural"
STYLE = "cinematic, dramatic, hook-heavy, keeps the viewer watching to the end"


def _chat(prompt, max_tokens=900, temperature=0.9, model=None):
    body = json.dumps({
        "model": model or LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()
    req = urllib.request.Request(
        LLM_BASE_URL.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {LLM_API_KEY}",
                 "Content-Type": "application/json"},
    )
    msg = None
    for _ in range(6):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                msg = json.load(r)["choices"][0]["message"]
        except Exception:
            time.sleep(2)
            continue
        c = (msg.get("content") or "").strip()
        if c:
            return c
        time.sleep(2)
    return (msg.get("reasoning") or "").strip() if msg else ""


def fetch_google_trends(geo="US", limit=30):
    """Pull real-time trending searches from Google Trends RSS (free, official)."""
    import xml.etree.ElementTree as ET
    url = f"https://trends.google.com/trending/rss?geo={geo}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        tree = ET.fromstring(r.read())
    items = []
    for it in tree.iter("item"):
        title = it.findtext("title")
        traffic = it.findtext("{https://trends.google.com/trending/rss}approx_traffic")
        if title:
            items.append({"term": title, "traffic": traffic})
    return items[:limit]


def pick_topics(n=2):
    """Choose money/finance/investing topics — the highest-RPM YouTube niche.

    Uses Google Trends for a topical hook when available, but the core is a
    curated evergreen finance angle (compounding, investing, wealth habits,
    money psychology) so titles stay click-worthy and never go stale.
    """
    try:
        trends = fetch_google_trends()
        trend_terms = ", ".join(t["term"] for t in trends[:25])
    except Exception as e:
        print(f"[trends] Google Trends failed ({e})", flush=True)
        trend_terms = "(none available)"

    prompt = (
        "You are a YouTube content strategist for a faceless finance/money "
        "channel that earns high ad RPM. "
        f"Current Google search trends (use only as an optional hook): {trend_terms}\n\n"
        f"Choose {n} video topics. They MUST be about money, investing, wealth, "
        "financial independence, money psychology, or economics — never stray "
        "into general news/sports/politics. "
        "Favor evergreen, high-retention angles like: "
        "a surprising money fact, a wealth-building habit, a financial mistake "
        "to avoid, a psychological money trap, or a simple investing principle. "
        "For each return a JSON object with exactly these keys:\n"
        "'topic' (the specific subject), "
        "'title' (a click-worthy, curiosity-driven YouTube title under 70 chars "
        "with a strong hook, no clickbait-y lies), "
        "'description' (2-3 sentence YouTube description with a hook and a "
        "subscribe call-to-action).\n"
        f"Return ONLY a JSON array of {n} objects. No markdown, no commentary, "
        "no code fences."
    )
    raw = _chat(prompt, max_tokens=2000, temperature=0.8,
                model="gpt-oss:20b")
    # strip any reasoning that leaked in front of the JSON
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON array in LLM response: {raw[:400]}")
    data = json.loads(raw[start:end + 1])
    if not isinstance(data, list):
        raise ValueError(f"expected list, got {type(data)}")
    return data[:n]


def generate_video(topic, seed):
    script = llm_script(topic, "en", STYLE)
    mp3 = ASSETS / f"narration_{seed}.mp3"
    mp3, boundaries = asyncio.run(synth_with_boundaries(script, VOICE, mp3))
    total = probe_duration(mp3)

    images = fetch_images(10, ASSETS, seed)

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
        cap = None
        if beat["text"]:
            cap = WORK / f"cap_{seed}_{i:03d}.png"
            render_caption_png(beat["text"], cap)
        sp = WORK / f"scene_{seed}_{i:03d}.mp4"
        render_scene_ffmpeg(img, cap, dur, sp, i)
        scene_paths.append(sp)

    out = OUT / f"video_{seed}.mp4"
    assemble_final(scene_paths, mp3, out)
    return out


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    ASSETS.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    WORK.mkdir(exist_ok=True)

    topics = pick_topics(n)
    results = []
    base = int(time.time())
    for i, t in enumerate(topics):
        seed = base + i * 1000
        try:
            path = generate_video(t["topic"], seed)
            results.append({
                "title": t["title"],
                "description": t["description"],
                "path": str(path),
            })
            print(f"[{i+1}/{n}] done: {path}", flush=True)
        except Exception as e:
            print(f"[{i+1}/{n}] FAILED: {e}", file=sys.stderr, flush=True)

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
