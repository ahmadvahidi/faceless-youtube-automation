#!/usr/bin/env python3
"""Generate a high-CTR YouTube thumbnail (1280x720).

A thumbnail is the single biggest lever on click-through-rate, and CTR is what
tells YouTube's algorithm to push a video. Design: a darkened chart frame as
background + SHORT huge text (2-5 words) with a highlighted key word, plus the
DOPEAK brand. Big, bold, high-contrast, readable at phone size.
"""
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

W, H = 1280, 720
FONT_BOLD = "/opt/data/workspace/iman-logo/fonts/Poppins-Bold.ttf"
FONT_SEMI = "/opt/data/workspace/iman-logo/fonts/Poppins-SemiBold.ttf"
ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"

# words to paint in the accent (yellow) colour
_ACCENT = re.compile(
    r"\b(\d+(?:[.,]\d+)?\s?(?:%|x|k|m|\$|years?|days?|minutes?)?|"
    r"money|wealth|rich|free|never|stop|secret|trap|mistake|hidden|"
    r"compound|inflation|taxes?|debt|save|saving)\b", re.I)


def _font(size):
    return ImageFont.truetype(FONT_BOLD, size)


def _wrap(text, font, max_w, draw):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textbbox((0, 0), t, font=font)[2] <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _bg_from_frame(src_video: Path | None) -> Image.Image:
    if src_video and Path(src_video).exists():
        tmp = WORK / "_thumb_bg.png"
        subprocess.run(["ffmpeg", "-y", "-ss", "12", "-i", str(src_video),
                        "-frames:v", "1", str(tmp)],
                       capture_output=True)
        if tmp.exists():
            img = Image.open(tmp).convert("RGB").resize((W, H))
            img = img.filter(ImageFilter.GaussianBlur(7))
            img = ImageEnhance.Brightness(img).enhance(0.40)
            return img
    # fallback: navy vertical gradient
    img = Image.new("RGB", (W, H), (10, 12, 26))
    d = ImageDraw.Draw(img)
    for y in range(H):
        f = y / H
        d.line([(0, y), (W, y)], fill=(int(10 + 24 * f), int(12 + 30 * f),
                                       int(26 + 46 * f)))
    return img


def make_thumbnail(title: str, out_path: str, src_video: Path | None = None,
                   max_words: int = 5) -> str:
    """Build a 1280x720 thumbnail for `title`. Returns the saved path.

    Delegates to `thumb_variants` (six distinct designs, least-used rotation) unless
    THUMB_VARIETY=0. One design for every upload is what made the channel's thumbnails
    indistinguishable in the feed; the legacy body below is kept as the fallback path.
    """
    import os
    if os.environ.get("THUMB_VARIETY", "1") != "0":
        try:
            import sys
            sys.path.insert(0, str(ROOT))
            import thumb_variants as tv
            path, style = tv.make(title, out_path, src_video=src_video)
            print(f"[thumb] design={style}", flush=True)
            return path
        except Exception as e:      # never lose an upload because the design module broke
            print(f"[thumb] variants failed ({e}); using legacy design", flush=True)
    # shorten: keep the punchiest few words
    short = title.replace("—", "-").replace("|", "-").split("-")[0].strip()
    words = short.split()
    if len(words) > max_words:
        short = " ".join(words[:max_words])

    img = _bg_from_frame(src_video)
    # dark scrim so text always reads
    scrim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(scrim)
    for y in range(H):
        a = int(150 * (1 - y / H) + 40)
        sd.line([(0, y), (W, y)], fill=(0, 0, 0, min(210, a)))
    img = Image.alpha_composite(img.convert("RGBA"), scrim).convert("RGB")

    probe = ImageDraw.Draw(img)
    # auto-fit the biggest font that keeps <= 4 lines
    chosen = None
    for size in range(150, 54, -4):
        f = _font(size)
        lines = _wrap(short.upper(), f, W - 120, probe)
        if len(lines) <= 4 and len(lines) >= 1:
            chosen = (f, lines)
            break
    if chosen is None:
        chosen = (_font(60), _wrap(short.upper(), _font(60), W - 120, probe))
    font, lines = chosen

    line_h = int(font.size * 1.12)
    block_h = line_h * len(lines)
    y0 = (H - block_h) // 2 - 10
    d = ImageDraw.Draw(img)
    for ln in lines:
        bb = d.textbbox((0, 0), ln, font=font)
        tw = bb[2] - bb[0]
        x = (W - tw) // 2
        # highlight accent words in yellow, rest white
        if _ACCENT.search(ln):
            d.text((x, y0), ln, font=font, fill="#FFD54F",
                   stroke_width=6, stroke_fill="black")
        else:
            d.text((x, y0), ln, font=font, fill="white",
                   stroke_width=6, stroke_fill="black")
        y0 += line_h

    # brand bar
    bf = ImageFont.truetype(FONT_SEMI, 34)
    d.text((28, H - 56), "DOPEAK", font=bf, fill="#8A93B5",
           stroke_width=3, stroke_fill="black")
    d.text((W - 210, H - 56), "SUBSCRIBE ▶", font=bf, fill="#FF5C6C",
           stroke_width=3, stroke_fill="black")

    out_path = str(out_path)
    img.save(out_path, "JPEG", quality=90)
    return out_path


if __name__ == "__main__":
    import sys
    print(make_thumbnail(sys.argv[1], sys.argv[2]))
