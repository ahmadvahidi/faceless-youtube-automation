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
import urllib.parse
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

# Delivery loudness for every assembled video. YouTube normalises playback to -14 LUFS and
# never boosts a quieter upload, so a mix mastered below it simply plays softer than the whole
# feed. TP_DB is the true-peak ceiling loudnorm limits to.
TARGET_LUFS = -14.0
TP_DB = -1.5

# ----------------------------------------------------------------------------
# LLM
# ----------------------------------------------------------------------------
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://ollama.com/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-v4.1-flash")


def llm_script(topic: str, lang: str, style: str) -> str:
    lang_name = "Persian (Farsi)" if lang.startswith("fa") else "English"
    prompt = (
        f"Write a 25-40 second faceless YouTube SHORT voiceover script in {lang_name} "
        f'about this topic: "{topic}". '
        f"Style: {style}. "
        "Requirements:\n"
        "- 5 to 8 short sentences total. The narration must NOT run past 40 seconds.\n"
        "- Start with a bold, hooky first sentence that stops the scroll (it is shown as a type card, so keep it under 14 words).\n"
        "- Use short, punchy sentences that read well when spoken aloud.\n"
        "- End with a memorable closing line.\n"
        "- Plain punctuation only (. ! ?). No emojis, no markdown, no headings.\n"
        "- Return ONLY the narration text."
    )
    # Multi-provider fallback (Groq -> Ollama -> Mistral), so a quota or rate
    # limit on any one provider cannot kill the run.
    from llm_client import chat
    return chat(prompt, max_tokens=900, temperature=0.85, model=LLM_MODEL)


# ----------------------------------------------------------------------------
# TTS + boundaries
# ----------------------------------------------------------------------------
PIPER_VOICES = {
    "en": "/opt/data/workspace/tts-offline/voices/en_US-lessac-medium.onnx",
    "de": "/opt/data/workspace/tts-offline/voices/de_DE-thorsten-medium.onnx",
}
PIPER_BIN = "/opt/data/skills/.venv/bin/piper"


def _piper_fallback(text: str, out_mp3: Path, lang: str = "en"):
    """Guaranteed-offline TTS fallback (Piper). Never hits the network, so it
    cannot be rate-limited like edge-tts. Piper gives no word boundaries, so
    sentence timings are estimated proportional to sentence length."""
    import re
    import subprocess
    model = PIPER_VOICES.get(lang, PIPER_VOICES["en"])
    wav = out_mp3.with_suffix(".piper.wav")
    p = subprocess.run([PIPER_BIN, "--model", model, "--output_file", str(wav)],
                       input=text.encode(), capture_output=True, timeout=900)
    if p.returncode != 0 or not wav.exists():
        raise RuntimeError(f"piper failed: {p.stderr[-300:]!r}")
    subprocess.run(["ffmpeg", "-y", "-i", str(wav), "-ar", "48000", "-ac", "2",
                    "-b:a", "160k", str(out_mp3)],
                   capture_output=True, check=True)
    dur = probe_duration(out_mp3)
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()] or [text]
    total = sum(len(s) for s in sents) or 1
    boundaries, t = [], 0.0
    for s in sents:
        d = dur * len(s) / total
        boundaries.append({"text": s, "start": t, "end": t + d})
        t += d
    print(f"[tts] used Piper fallback ({lang}) — {len(sents)} sentences", flush=True)
    return out_mp3, boundaries


async def synth_with_boundaries(text: str, voice: str, out_mp3: Path, attempts: int = 5):
    """Synthesize narration and sentence boundaries.

    edge-tts intermittently returns HTTP 403 from Microsoft's endpoint (rate
    limiting / stale Sec-MS-GEC token). Retry with exponential backoff so one
    transient 403 does not kill the whole video pipeline.
    """
    import edge_tts
    last_err = None
    for attempt in range(attempts):
        boundaries = []
        audio_bytes = bytearray()
        try:
            comm = edge_tts.Communicate(text, voice)
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    audio_bytes.extend(chunk["data"])
                elif chunk["type"] == "SentenceBoundary":
                    boundaries.append({
                        "text": chunk["text"],
                        "start": chunk["offset"] / 1e7,
                        "end": (chunk["offset"] + chunk["duration"]) / 1e7,
                    })
            if not audio_bytes:
                raise RuntimeError("edge-tts returned no audio")
            out_mp3.write_bytes(bytes(audio_bytes))
            return out_mp3, boundaries
        except Exception as e:  # noqa: BLE001 - retry on any transient failure
            last_err = e
            wait = min(30, 3 * (2 ** attempt))
            print(f"[tts] attempt {attempt + 1}/{attempts} failed "
                  f"({type(e).__name__}: {str(e)[:80]}); retrying in {wait}s",
                  flush=True)
            await asyncio.sleep(wait)
    # edge-tts exhausted its retries — fall back to the offline Piper voice so a
    # video build NEVER dies on TTS (the 403s are transient but recurring).
    print(f"[tts] edge-tts failed after {attempts} attempts ({last_err!r}); "
          f"falling back to Piper", flush=True)
    lang = "de" if voice.lower().startswith("de") else "en"
    return _piper_fallback(text, out_mp3, lang)


# ----------------------------------------------------------------------------
# Visuals
# ----------------------------------------------------------------------------
def _normalize_image(path: Path) -> Path:
    """Downscale + re-encode to 1920x1080 JPEG (quality 82) via ffmpeg.

    Flickr/original sources can be 4000px+ and heavy; ffmpeg's zoompan then
    produces bloated output that busts Telegram's 50MB cap (HTTP 413). A fixed
    1080p canvas keeps every scene light and the final video uploadable.
    """
    tmp = path.with_suffix(".norm.jpg")
    cmd = ["ffmpeg", "-y", "-i", str(path),
           "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                  "pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
           "-q:v", "2", str(tmp)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0 and tmp.exists():
        tmp.replace(path)
    return path


def fetch_images(n: int, out_dir: Path, seed: int = 0) -> list[Path]:
    paths = []
    for i in range(n):
        p = out_dir / f"img_{i:02d}.jpg"
        url = f"https://picsum.photos/seed/faceless{seed}_{i}/1920/1080"
        urllib.request.urlretrieve(url, str(p))
        paths.append(p)
    return paths


def fetch_wikimedia_images(query: str, count: int, out_dir: Path,
                           seed: int = 0) -> list[Path]:
    """Topical images from Wikimedia Commons — free, keyless, keyword-matched.

    Good for concrete subjects (one-word queries). Abstract/multi-word queries
    return poor matches, so Openverse is preferred; this stays as a fallback.
    """
    params = urllib.parse.urlencode({
        "action": "query",
        "generator": "search",
        # filetype:bitmap filters out PDFs/docs that match the text search;
        # multi-word queries otherwise return book scans, not photos.
        "gsrsearch": f"{query} filetype:bitmap",
        "gsrnamespace": "6",          # File: namespace only
        "gsrlimit": str(count * 3),   # over-fetch then filter
        "prop": "imageinfo",
        "iiprop": "url|size|mime",
        "iiurlwidth": "1920",
        "format": "json",
    })
    url = f"https://commons.wikimedia.org/w/api.php?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "FacelessVideoBot/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)

    pages = (data.get("query") or {}).get("pages", {})
    paths = []
    for _pid, page in pages.items():
        info = (page.get("imageinfo") or [{}])[0]
        mime = info.get("mime", "")
        if mime not in ("image/jpeg", "image/png"):
            continue
        w, h = info.get("width", 0), info.get("height", 0)
        if not w or not h or w < h:      # landscape only
            continue
        thumb = info.get("thumburl")
        if not thumb:
            continue
        p = out_dir / f"topical_{seed}_{len(paths):03d}.jpg"
        try:
            urllib.request.urlretrieve(thumb, str(p))
            paths.append(p)
        except Exception:
            continue
        if len(paths) >= count:
            break
    return paths


def _openverse_page(query: str, page: int) -> list[dict]:
    params = urllib.parse.urlencode({
        "q": query,
        # Cap at 20 — Openverse returns 401 above that (undocumented limit).
        "page_size": "20",
        "page": str(page),
        "license_type": "all",
    })
    url = f"https://api.openverse.org/v1/images/?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "FacelessVideoBot/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("results", [])


def fetch_openverse_images(query: str, count: int, out_dir: Path,
                           seed: int = 0) -> list[Path]:
    """Topical images from Openverse (keyless, aggregates Flickr/Wikimedia/etc).

    Best keyless source for abstract finance/psychology topics — returns
    keyword-matched, landscape photos. Paginates to reach `count` distinct
    images (20 per page is the hard API cap).
    """
    paths = []
    page = 1
    while len(paths) < count and page <= 4:
        try:
            items = _openverse_page(query, page)
        except Exception as e:
            if page == 1:
                print(f"[images] openverse failed ({e})", flush=True)
            break
        if not items:
            break
        for item in items:
            w, h = item.get("width", 0) or 0, item.get("height", 0) or 0
            if w and h and w < h:        # landscape only
                continue
            src = item.get("url")
            if not src:
                continue
            p = out_dir / f"topical_{seed}_{len(paths):03d}.jpg"
            try:
                urllib.request.urlretrieve(src, str(p))
                _normalize_image(p)
                paths.append(p)
            except Exception:
                continue
            if len(paths) >= count:
                break
        page += 1
        time.sleep(0.5)
    return paths


def fetch_topical_images(query: str, count: int, out_dir: Path,
                         seed: int = 0) -> list[Path]:
    """Fetch *relevant* stock photos for a topic, one distinct image per scene.

    Source order: Pexels API (if PEXELS_API_KEY set) -> Openverse (keyless,
    topical) -> Wikimedia Commons (keyless) -> random picsum (last resort).
    Never cycles a small set of random photos.
    """
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if key:
        paths = _fetch_pexels(query, count, out_dir, seed)
        if paths:
            return paths

    # Try the full query, then progressively broader queries (drop trailing
    # words) so a too-specific query still yields enough distinct images
    # instead of cycling 1-3 photos across 40 scenes.
    words = query.split()
    for keep in range(len(words), 0, -1):
        q = " ".join(words[:keep])
        paths = fetch_openverse_images(q, count, out_dir, seed)
        # Accept if we got ANY (the caller asks for a small count here); the
        # old `max(4, count//2)` threshold wrongly demanded 4 for count=2,
        # forcing everything to fall back to random picsum.
        if len(paths) >= 1:
            print(f"[images] openverse: {len(paths)} topical for '{q}'", flush=True)
            return paths

    paths = fetch_wikimedia_images(query, count, out_dir, seed)
    if paths:
        print(f"[images] wikimedia: {len(paths)} topical for '{query}'", flush=True)
        return paths

    print(f"[images] no topical results for '{query}', fallback picsum", flush=True)
    return fetch_images(count, out_dir, seed)


def _fetch_pexels(query: str, count: int, out_dir: Path, seed: int = 0) -> list[Path]:
    """Pexels search (requires PEXELS_API_KEY). Returns [] on any failure."""
    url = ("https://api.pexels.com/v1/search"
           f"?query={urllib.parse.quote(query)}&per_page={count}&orientation=landscape")
    req = urllib.request.Request(
        url, headers={"Authorization": os.environ["PEXELS_API_KEY"]})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except Exception as e:
        print(f"[images] pexels failed ({e})", flush=True)
        return []

    photos = data.get("photos", [])
    paths = []
    for i, ph in enumerate(photos[:count]):
        src = ph.get("src", {}).get("large2x") or ph.get("src", {}).get("large") \
            or ph.get("src", {}).get("original")
        if not src:
            continue
        p = out_dir / f"topical_{seed}_{i:03d}.jpg"
        try:
            urllib.request.urlretrieve(src, str(p))
            paths.append(p)
        except Exception:
            continue
    if paths:
        print(f"[images] pexels: {len(paths)} topical for '{query}'", flush=True)
    return paths


def probe_duration(path: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "json", str(path)]
    return float(json.loads(subprocess.check_output(cmd))["format"]["duration"])


# ----------------------------------------------------------------------------
# Caption PNG (PIL) — readable white text on soft dark gradient
# ----------------------------------------------------------------------------
def render_caption_png(text: str, out_png: Path, max_lines: int = 2) -> Path:
    """Designed on-screen caption (Ahmad, 2026-10-16: "زیرنویس، بصری بودنش، شکلک ها،
    سایه ها ... همش عالی باشه").

    Layered for depth instead of plain white text on a gradient smear:
      * a rounded, semi-opaque glass panel with a 1px light top edge
      * a drop SHADOW under the panel so it sits above the scene
      * a coloured accent bar on the left edge
      * the KEY WORD of the line picked out in the accent colour (the eye lands
        on the meaning instantly, and it reads as designed rather than dumped)
      * text drawn twice: a soft dark shadow offset down-right, then the fill
    Pinned to the bottom of the frame so it never covers the graphic.
    """
    import re
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

    max_w = int(W * 0.80)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    words = text.split()

    size = 50
    for size in (72, 66, 60, 54, 48, 42, 36):
        font = ImageFont.truetype(str(FONT_BOLD), size)
        lines, cur = [], ""
        for w_ in words:
            test = (cur + " " + w_).strip()
            if probe.textbbox((0, 0), test, font=font)[2] <= max_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w_
        if cur:
            lines.append(cur)
        if len(lines) <= max_lines:
            break

    # the key word = the longest non-stopword; highlighted in the accent colour
    stop = {"the", "a", "an", "of", "to", "and", "is", "in", "it", "that", "for",
            "on", "you", "your", "with", "at", "by", "as", "are", "be"}
    cand = [re.sub(r"[^A-Za-z0-9%$.,-]", "", w) for w in words]
    cand = [c for c in cand if c and c.lower() not in stop]
    key = max(cand, key=len) if cand else ""

    line_h = int(size * 1.30)
    pad_x, pad_y = 46, 26
    txt_w = max(probe.textbbox((0, 0), l, font=font)[2] for l in lines)
    box_w = min(W - 40, txt_w + pad_x * 2 + 16)
    box_h = line_h * len(lines) + pad_y * 2
    x0 = (W - box_w) // 2
    y0 = H - box_h - 44

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # --- drop shadow under the panel (depth) ---
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        [x0 + 3, y0 + 7, x0 + box_w + 3, y0 + box_h + 7],
        radius=22, fill=(0, 0, 0, 150))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(9)))

    # --- glass panel ---
    pan = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pan)
    pd.rounded_rectangle([x0, y0, x0 + box_w, y0 + box_h], radius=22,
                         fill=(10, 14, 26, 214), outline=(255, 255, 255, 46), width=2)
    pd.rounded_rectangle([x0 + 2, y0 + 2, x0 + box_w - 2, y0 + 5], radius=3,
                         fill=(255, 255, 255, 34))          # light top edge
    pd.rounded_rectangle([x0 + 9, y0 + 14, x0 + 15, y0 + box_h - 14], radius=3,
                         fill=(255, 214, 79, 235))          # accent bar
    img.alpha_composite(pan)

    # --- text: shadow pass then fill pass, key word in accent colour ---
    d = ImageDraw.Draw(img)
    ty = y0 + pad_y
    for line in lines:
        bb = d.textbbox((0, 0), line, font=font)
        x = x0 + (box_w - (bb[2] - bb[0])) // 2 + 6
        d.text((x + 3, ty + 4), line, font=font, fill=(0, 0, 0, 190))   # shadow
        # draw word by word so the key word can be recoloured
        cx = x
        for tok in line.split(" "):
            clean = re.sub(r"[^A-Za-z0-9%$.,-]", "", tok)
            col = (255, 214, 79, 255) if key and clean == key else (255, 255, 255, 255)
            d.text((cx, ty), tok, font=font, fill=col)
            cx += d.textlength(tok + " ", font=font)
        ty += line_h

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
                   out_path: Path, t_dur: float = 0.6, crf: int = 21,
                   music_path: Path | None = None,
                   music_volume: float = 0.10) -> Path:
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
    RES = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
    # Loudness. Measured on the raw edge-tts narration: -19.9 LUFS / -1.1 dBTP. YouTube
    # normalises playback to -14 LUFS and never boosts anything quieter, so an un-normalised
    # mix is played back ~6 dB below every other video in the feed. The peak already sits at
    # -1.1 dBTP, so the extra level has to come from dynamic gain with true-peak limiting,
    # which is exactly what loudnorm does. Verified on a real assemble: -19.9 -> -14.4 LUFS,
    # true peak -1.5 dBTP, still 48 kHz stereo with `moov` at the head.
    LOUD = f"loudnorm=I={TARGET_LUFS}:TP={TP_DB}:LRA=11,aresample=48000,{RES}"

    if music_path is not None:
        # Mix narration + a music bed inside the SAME complex filtergraph (cannot combine with a
        # bare -af). Kept in step with the cs-videos copy: the bed is GAIN-STAGED from the two
        # stems and ducked by audio_mix.py, never by a hand-set `music_volume` (measured on
        # 2026-10-17: the hand-set gains left the bed 30-53 dB under the voice across the lines).
        try:
            import audio_mix
            leg = audio_mix.mix_audio(1, 2, str(narration_mp3), str(music_path), loud=LOUD)
        except Exception as e:  # noqa: BLE001 — never lose an upload to the mixer helper
            print(f"[audio] audio_mix unavailable ({str(e)[:80]}) — hand-set bed gain", file=sys.stderr)
            leg = (f"[1:a]{RES}[nar];[2:a]volume={music_volume},{RES}[mus];"
                   f"[nar][mus]amix=inputs=2:duration=first:normalize=0,{LOUD}[a]")
        fchain = f"[0:v]{grade}[gv];" + leg
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(listfile),
            "-i", str(narration_mp3),
            "-i", str(music_path),
            "-filter_complex", fchain,
            "-map", "[gv]", "-map", "[a]",
            "-r", "30", "-c:v", "libx264",
            "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart", str(out_path),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(listfile),
            "-i", str(narration_mp3),
            "-filter_complex", f"[0:v]{grade}[gv];[1:a]{RES}[nar];[nar]{LOUD}[a]",
            "-map", "[gv]", "-map", "[a]", "-r", "30", "-c:v", "libx264",
            "-preset", "veryfast", "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
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
                mp3 = ASSETS / "narration.mp3"
                total = probe_duration(mp3)
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

    from motion_card import render_hook_card

    scene_paths = []
    for i, beat in enumerate(beats):
        dur = beat["end"] - beat["start"]
        if dur <= 0.05:
            continue
        # beat 0 = the hook: a designed type card, same duration as the beat
        # (narration untouched), chart as the fallback.
        if i == 0 and beat["text"]:
            hook = WORK / f"scene_{i:03d}.mp4"
            try:
                render_hook_card(beat["text"], dur, hook)
                scene_paths.append(hook)
                continue
            except Exception as e:  # noqa: BLE001
                print(f"[motion] hook card failed ({str(e)[:120]}) — image fallback",
                      file=sys.stderr)
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
