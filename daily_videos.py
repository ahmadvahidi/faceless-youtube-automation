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
    fetch_topical_images,
    render_caption_png, render_scene_ffmpeg, assemble_final, probe_duration,
    ASSETS, OUT, WORK,
)

VOICE = "en-US-GuyNeural"
STYLE = "cinematic, dramatic, hook-heavy, keeps the viewer watching to the end"

# topic keywords -> which finance chart best visualizes it (see finance_scenes.py)
_CHART_KEYWORDS = {
    "compounding": ["compound", "interest", "growth", "wealth", "snowball",
                    "retirement", "401k", "dividend", "long-term", "decade"],
    "stock": ["stock", "market", "invest", "share", "equity", "index", "s&p",
              "portfolio", "bull", "bear", "crash", "downturn"],
    "inflation": ["inflation", "prices", "cost of living", "buying power",
                  "purchasing", "erosion"],
    "diversify": ["diversif", "allocation", "asset", "sector", "risk",
                  "portfolio", "spread"],
    "compare": ["vs", "versus", "compare", "active", "passive", "fees",
                "fund", "better"],
    "tax": ["tax", "ira", "deduction", "contribution", "roth", "capital gain"],
}


def charts_for_topic(topic: str, n: int = 3) -> list:
    """Pick the n most relevant finance-chart keys for a topic (always non-empty)."""
    from longform_pipeline import GRAPHIC_KEYS
    t = (topic or "").lower()
    scores = {k: sum(1 for w in kws if w in t) for k, kws in _CHART_KEYWORDS.items()}
    ranked = sorted(GRAPHIC_KEYS, key=lambda k: -scores.get(k, 0))
    picks = [k for k in ranked if scores.get(k, 0) > 0][:n]
    # always include the universal compounding curve
    if "compounding" not in picks:
        picks.append("compounding")
    while len(picks) < n:
        for k in ("stock", "inflation", "diversify", "compare", "tax"):
            if k not in picks:
                picks.append(k)
            if len(picks) >= n:
                break
    return picks[:n]

# Persistent history of every topic ever generated, so we never repeat.
HISTORY_FILE = Path(__file__).resolve().parent / "topic_history.json"


def load_history():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            return []
    return []


def save_history(entries):
    HISTORY_FILE.write_text(json.dumps(entries, indent=2, ensure_ascii=False))


# stopwords so "the / a / to / of" don't inflate similarity
_STOP = set("""a an the to of in on for and or but is are was were be been
this that these those it its as at by from with without about into over
under your you we our my me i he she they how why what when where which
who will can could should would may might must do does did not no just
really very much many more most some any all""".split())


def _tokens(s: str):
    """Lowercased, stopword-filtered word set."""
    import re
    words = re.findall(r"[a-z0-9]+", (s or "").lower())
    return {w for w in words if w not in _STOP}


def _similarity(a: str, b: str) -> float:
    """Jaccard similarity of two strings (0..1)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def is_duplicate(topic: str, title: str, history, threshold=0.22):
    """True if the topic/title is too similar to any previously-made video."""
    for h in history:
        old_topic = h.get("topic", "")
        old_title = h.get("title", "")
        # check topic-vs-topic, title-vs-title, AND cross topic-vs-title
        if _similarity(topic, old_topic) >= threshold:
            return True
        if _similarity(title, old_title) >= threshold:
            return True
        if _similarity(topic, old_title) >= threshold:
            return True
        if _similarity(title, old_topic) >= threshold:
            return True
    return False


def filter_duplicates(candidates, history, threshold=0.22):
    """Drop candidates too similar to history (and to each other)."""
    kept = []
    for c in candidates:
        topic = c.get("topic", "")
        title = c.get("title", "")
        if is_duplicate(topic, title, history, threshold):
            continue
        if is_duplicate(topic, title, kept, threshold):
            continue
        kept.append(c)
    return kept


def _chat(prompt, max_tokens=900, temperature=0.9, model=None):
    """Chat via the shared multi-provider client (Groq -> Ollama -> Mistral)."""
    from llm_client import chat
    return chat(prompt, max_tokens=max_tokens, temperature=temperature, model=model)


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

    Returns EXACTLY n topics that are genuinely new (deduplicated against the
    full history via both prompt-level exclusion and a post-hoc Jaccard
    similarity filter). If the LLM returns near-duplicates, it re-prompts with
    a larger batch until n clean, distinct topics are found.
    """
    try:
        trends = fetch_google_trends()
        trend_terms = ", ".join(t["term"] for t in trends[:25])
    except Exception as e:
        print(f"[trends] Google Trends failed ({e})", flush=True)
        trend_terms = "(none available)"

    history = load_history()
    used_topics = "; ".join(h.get("topic", "") for h in history)
    used_titles = "; ".join(h.get("title", "") for h in history)

    def _prompt(k):
        return (
            "You are a YouTube content strategist for a faceless finance/money "
            "channel that earns high ad RPM. "
            f"Current Google search trends (use only as an optional hook): {trend_terms}\n\n"
            f"Choose {k} video topics. They MUST be about money, investing, wealth, "
            "financial independence, money psychology, or economics — never stray "
            "into general news/sports/politics. "
            "Favor evergreen, high-retention angles like: "
            "a surprising money fact, a wealth-building habit, a financial mistake "
            "to avoid, a psychological money trap, or a simple investing principle. "
            "CRITICAL — DO NOT REPEAT PAST TOPICS. These topics were already made:\n"
            f"  topics: {used_topics or '(none yet)'}\n"
            f"  titles: {used_titles or '(none yet)'}\n"
            "Pick genuinely NEW and DIFFERENT angles — new subject, new framing, "
            "new hook. Do not just reword an old title. Each of the "
            f"{k} topics must be distinct from every other one.\n"
            "For each return a JSON object with exactly these keys:\n"
            "'topic' (the specific subject), "
            "'title' (a click-worthy, curiosity-driven YouTube title under 70 chars "
            "with a strong hook, no clickbait-y lies), "
            "'description' (3-4 sentences and genuinely useful: sentence 1 is a "
            "scroll-stopping hook, sentences 2-3 tell the viewer exactly what they "
            "will learn and why it matters to their money, sentence 4 is a clear "
            "subscribe + follow-for-more call to action, then end with 4-6 "
            "relevant lowercase #hashtags. No generic filler like 'Discover the "
            "simple practice'), "
            "'image_query' (2-4 simple English stock-photo keywords as a single "
            "space-separated string, e.g. \"piggy bank savings\").\n"
            f"Return ONLY a JSON array of {k} objects. No markdown, no commentary, "
            "no code fences."
        )

    def _call(k):
        last_err = None
        # Retry with both models: a transient empty/garbled LLM reply must not
        # kill the whole run (this crashed the longform cron on 2026-10-11).
        for model in ("gpt-oss:20b", "deepseek-v4.1-flash"):
            for _ in range(3):
                try:
                    raw = _chat(_prompt(k), max_tokens=2500, temperature=0.9,
                                model=model)
                    start = raw.find("["); end = raw.rfind("]")
                    if start == -1 or end == -1:
                        last_err = ValueError(
                            f"no JSON array in {model} response: {raw[:200]}")
                        continue
                    data = json.loads(raw[start:end + 1])
                    if not isinstance(data, list):
                        last_err = ValueError(f"expected list, got {type(data)}")
                        continue
                    return data
                except Exception as e:
                    last_err = e
                    time.sleep(1)
        raise ValueError(f"topic LLM failed after retries: {last_err}")

    # Ask for extra, filter, and retry until we have n clean topics.
    final = []
    for attempt in range(4):
        try:
            batch = _call(n + 3)  # over-request to survive filtering
        except Exception as e:
            print(f"[topics] attempt {attempt+1} failed: {e}", flush=True)
            continue
        clean = filter_duplicates(batch, history + final)
        final.extend(clean)
        if len(final) >= n:
            break
        print(f"[topics] attempt {attempt+1}: only {len(final)}/{n} clean, retrying", flush=True)

    return final[:n]


def generate_video(topic, seed, image_query=None):
    # Normalize image_query: the LLM sometimes returns a JSON list instead of
    # a string. Take the first (most relevant) entry as the query.
    if isinstance(image_query, list):
        image_query = str(image_query[0]) if image_query else None
    if image_query and not isinstance(image_query, str):
        image_query = str(image_query)

    script = llm_script(topic, "en", STYLE)
    mp3 = ASSETS / f"narration_{seed}.mp3"
    mp3, boundaries = asyncio.run(synth_with_boundaries(script, VOICE, mp3))
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

    # Use ORIGINAL animated finance charts (Manim), NOT stock photos.
    # Keyless stock search (Openverse) returns semantically-wrong images for
    # abstract finance topics — a "inflation" query surfaced a toilet photo —
    # so the shorts use the same chart library as the long-form pipeline.
    from longform_pipeline import render_chart, _loop_and_caption
    picks = charts_for_topic(topic)
    chart_cache = {}
    for k in picks:
        chart_cache[k] = render_chart(k, seed=seed % 6)

    from motion_card import render_hook_card

    scene_paths = []
    for i, beat in enumerate(beats):
        dur = beat["end"] - beat["start"]
        if dur <= 0.05:
            continue
        # BEAT 0 = the hook. A chart cannot hook; a designed type card can.
        # Same duration as the beat, so narration stays exactly in sync.
        # Falls back to the chart if the motion render fails — never lose an upload.
        if i == 0 and beat["text"]:
            hook = WORK / f"scene_{seed}_{i:03d}.mp4"
            try:
                render_hook_card(beat["text"], dur, hook)
                scene_paths.append(hook)
                continue
            except Exception as e:  # noqa: BLE001
                print(f"[motion] hook card failed ({str(e)[:120]}) — chart fallback",
                      file=sys.stderr, flush=True)
        # rotate the chart every ~3 beats so the visual stays fresh
        chart_key = picks[(i // 3) % len(picks)]
        chart = chart_cache[chart_key]
        cap = WORK / f"cap_{seed}_{i:03d}.png"
        render_caption_png(beat["text"] or " ", cap)
        sp = WORK / f"scene_{seed}_{i:03d}.mp4"
        _loop_and_caption(chart, cap, dur, sp, motion_idx=i)
        scene_paths.append(sp)

    out = OUT / f"video_{seed}.mp4"
    from bg_music import make_bg_music
    music = ASSETS / f"music_{seed}.wav"
    # variant = the same per-video seed that picks the chart palette, so the music bed rotates
    # with the look instead of being the one A-minor pad on every upload.
    make_bg_music(total + 1.0, str(music), volume=0.08, variant=seed % 6)
    assemble_final(scene_paths, mp3, out, music_path=music)
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
            path = generate_video(t["topic"], seed,
                                  image_query=t.get("image_query"))
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
