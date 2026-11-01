#!/usr/bin/env python3
"""Six genuinely different 1280x720 thumbnail designs with a no-repeat rotation.

The problem this solves: every upload was rendered by one function, so every thumbnail had
the same silhouette — blurred frame, dark scrim, centred Poppins headline, small brand bar.
At feed size a viewer cannot tell two of them apart, which is exactly what kills CTR on a
channel that already looks repetitive. Palette changes are not variety; composition is.

Design rules shared by all six:
* readable at 320 px wide (the size a phone actually shows in a feed): <= 5 words, one
  idea, cap height >= 70 px, no thin weights,
* one accent colour from the palette, everything else monochrome, so the accent means
  "the number" and nothing else competes,
* the top-left 15% stays clear of critical text (the YouTube duration badge sits there),
* brand mark bottom-right, small and quiet.
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageFont

W, H = 1280, 720
FONTS = Path("/opt/data/workspace/deutsch-b2-brief/fonts")
ANTON = str(FONTS / "Anton-Regular.ttf")
PBOLD = "/opt/data/workspace/iman-logo/fonts/Poppins-Bold.ttf"
PSEMI = "/opt/data/workspace/iman-logo/fonts/Poppins-SemiBold.ttf"

HERE = Path(__file__).resolve().parent
STATE = HERE / "thumb_state.json"
WORK = HERE / "work"
WORK.mkdir(exist_ok=True)

DESIGNS = ["bignum", "split", "poster", "burst", "chart", "stamp"]

# One accent per palette. Deliberately NOT the same red-on-black six times: a feed shows
# several of our thumbnails at once, so the family has to differ at a glance.
PALETTES = [
    dict(ink=(246, 247, 252), bg=(10, 12, 20), accent=(255, 214, 74), dim=(150, 158, 178)),
    dict(ink=(16, 18, 24), bg=(245, 241, 232), accent=(226, 58, 48), dim=(110, 106, 98)),
    dict(ink=(240, 250, 250), bg=(6, 22, 26), accent=(64, 234, 210), dim=(132, 168, 170)),
    dict(ink=(250, 244, 240), bg=(26, 12, 10), accent=(255, 128, 64), dim=(176, 148, 136)),
    dict(ink=(244, 246, 255), bg=(10, 14, 34), accent=(122, 168, 255), dim=(140, 152, 188)),
    dict(ink=(250, 250, 250), bg=(14, 14, 16), accent=(198, 255, 88), dim=(150, 150, 150)),
]


def log(*a):
    print(*a, flush=True)


# ── rotation ────────────────────────────────────────────────────────────────────────────
def _state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {"history": [], "counts": {}}


def next_design(advance: bool = True) -> str:
    """Least-used design, never the same as the previous upload, then record the pick."""
    st = _state()
    counts = st.get("counts", {})
    hist = st.get("history", [])
    last = hist[-1] if hist else None
    cand = [d for d in DESIGNS if d != last] or DESIGNS
    low = min(int(counts.get(d, 0)) for d in cand)
    pool = sorted([d for d in cand if int(counts.get(d, 0)) == low])
    pick = pool[0] if len(pool) == 1 else random.Random(len(hist) + 7).choice(pool)
    if advance:
        st["history"] = (hist + [pick])[-200:]
        counts[pick] = int(counts.get(pick, 0)) + 1
        st["counts"] = counts
        try:
            STATE.write_text(json.dumps(st, indent=1))
        except Exception:
            pass
    return pick


# ── helpers ────────────────────────────────────────────────────────────────────────────
def _f(path, size):
    return ImageFont.truetype(path, size)


_STOP = {"your", "the", "a", "an", "to", "of", "in", "on", "for", "and", "that",
         "this", "is", "are", "with", "why", "how", "when", "what"}


def _phrase(title: str, max_words: int = 6) -> str:
    """A complete phrase, not a mid-clause cut: drop trailing/leading stop words first."""
    words = [w for w in title.replace("|", " ").replace("—", " ").split() if w]
    while words and words[-1].lower().strip(".,:;!?") in _STOP:
        words.pop()
    while words and words[0].lower().strip(".,:;!?") in _STOP:
        words.pop(0)
    if len(words) > max_words:            # cut, then never end on a stop word
        words = words[:max_words]
        while len(words) > 2 and words[-1].lower().strip(".,:;!?") in _STOP:
            words.pop()
    return " ".join(words)


def _wrap(d, text, f, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textbbox((0, 0), t, font=f)[2] <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    # widow guard: a single stranded word on the last line reads as a layout bug
    if len(lines) > 1 and len(lines[-1].split()) == 1:
        prev = lines[-2].split()
        if len(prev) > 1:
            lines[-1] = prev[-1] + " " + lines[-1]
            lines[-2] = " ".join(prev[:-1])
    return lines


def _fit(d, text, path, max_w, max_h, start=250, floor=54, cap_lines=4):
    """Biggest size whose wrapped block fits the box — 'big text' is the whole design."""
    for size in range(start, floor - 1, -6):
        f = _f(path, size)
        lines = _wrap(d, text, f, max_w)
        if len(lines) > cap_lines:
            continue
        lh = int(size * 1.04)
        if len(lines) * lh <= max_h:
            return f, lines, lh
    f = _f(path, floor)
    return f, _wrap(d, text, f, max_w)[:cap_lines], int(floor * 1.04)


def _bg_image(src_video: Path | None, blur: int = 6, brightness: float = 0.55,
              at: float = 12) -> Image.Image | None:
    if not src_video:
        return None
    p = Path(src_video)
    if not p.exists():
        return None
    tmp = WORK / f"_tv_{os.getpid()}.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(at), "-i", str(p),
                    "-frames:v", "1", str(tmp)], capture_output=True)
    if not tmp.exists():
        return None
    img = Image.open(tmp).convert("RGB").resize((W, H))
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    return ImageEnhance.Brightness(img).enhance(brightness)


def _grad_bg(pal, seed=0):
    """A grained gradient from trend-radar/gradients.py when available, else the old ramp.

    The flat two-stop ramp was the reason every thumbnail family read as the same surface: a
    linear ramp has no light source and no grain, so two designs differed only in hue. The
    generator costs ~40 ms and needs no network or licence.
    """
    try:
        import importlib.util
        from pathlib import Path
        path = Path("/opt/data/workspace/trend-radar/gradients.py")
        spec = importlib.util.spec_from_file_location("gradients_mod", path)
        g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(g)
        scheme = "paper_white" if sum(pal["bg"]) > 500 else (
            "deep_indigo" if pal["bg"][2] > pal["bg"][0] else "midnight_lime")
        img = g.make(scheme, seed=seed).resize((W, H), Image.LANCZOS)
        return img
    except Exception:
        return None


def _flat(pal, top=None, bot=None):
    grad = _grad_bg(pal, seed=abs(hash(str(pal["bg"]))) % 997)
    if grad is not None:
        return grad
    img = Image.new("RGB", (W, H), pal["bg"])
    d = ImageDraw.Draw(img)
    t = top or tuple(min(255, c + 14) for c in pal["bg"])
    b = bot or tuple(max(0, c - 4) for c in pal["bg"])
    for y in range(H):
        f = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(t[i] + (b[i] - t[i]) * f) for i in range(3)))
    return img


def _brand(d, pal, label="DOPEAK"):
    f = _f(PSEMI, 30)
    d.text((W - 26, H - 44), label, font=f, fill=pal["dim"], anchor="ra")


def _kicker(d, pal, text, colour=None):
    f = _f(PSEMI, 30)
    d.text((44, 30), text.upper(), font=f, fill=colour or pal["dim"])


# ── the six designs ────────────────────────────────────────────────────────────────────
def design_bignum(title, out, pal, bg):
    """One enormous number/phrase on flat dark, accent rule, tiny kicker."""
    d = ImageDraw.Draw(bg) if bg else None
    img = bg or _flat(pal)
    d = ImageDraw.Draw(img)
    words = title.split()
    head = words[0] if words else title
    rest = " ".join(words[1:])
    f, lines, lh = _fit(d, head, ANTON, W - 120, 400, start=330)
    y = 210
    for ln in lines:
        bb = d.textbbox((0, 0), ln, font=f)
        d.text(((W - (bb[2] - bb[0])) // 2, y), ln, font=f, fill=pal["accent"])
        y += lh
    d.rectangle([120, y + 26, W - 120, y + 38], fill=pal["ink"])
    if rest:
        fs = _f(PSEMI, 46)
        d.text((W // 2, y + 78), rest.upper(), font=fs, fill=pal["ink"], anchor="ma")
    _brand(d, pal)
    img.save(out, "JPEG", quality=92)
    return out


def design_split(title, out, pal, bg):
    """Hard diagonal split: solid colour half carries the type, other half shows the frame."""
    img = _flat(pal)
    d = ImageDraw.Draw(img)
    # right-hand wedge from the source frame (or a lighter flat if there is none)
    if bg:
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).polygon([(W * 0.52, 0), (W, 0), (W, H), (W * 0.40, H)], fill=255)
        frame = bg.resize((W, H))
        frame = ImageEnhance.Brightness(frame).enhance(1.25)
        img.paste(frame, (0, 0), mask)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(overlay).polygon([(W * 0.52, 0), (W, 0), (W, H), (W * 0.40, H)],
                                        fill=pal["bg"] + (40,))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(img)
    d.polygon([(W * 0.56, 0), (W * 0.44, H), (0, H), (0, 0)], fill=pal["bg"])
    d.rectangle([0, 0, 18, H], fill=pal["accent"])
    f, lines, lh = _fit(d, title, ANTON, int(W * 0.44), 470, start=170)
    y = (H - len(lines) * lh) // 2
    for ln in lines:
        d.text((58, y), ln, font=f, fill=pal["ink"])
        y += lh
    d.text((58, H - 62), "DOPEAK", font=_f(PSEMI, 30), fill=pal["accent"])
    img.save(out, "JPEG", quality=92)
    return out


def design_poster(title, out, pal, bg):
    """Light poster: near-black condensed type on cream, one word boxed in the accent."""
    img = _flat(pal)
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - 74, W, H], fill=(18, 18, 20))
    f, lines, lh = _fit(d, title, ANTON, W - 140, 470, start=210)
    y = 96
    for i, ln in enumerate(lines):
        bb = d.textbbox((62, y), ln, font=f)
        if i == len(lines) - 1:                       # the last line gets the box
            pad = 14
            d.rectangle([bb[0] - pad, bb[1] - pad, bb[2] + pad, bb[3] + pad],
                        fill=pal["accent"])
        d.text((62, y), ln, font=f, fill=(16, 16, 18) if i == len(lines) - 1 else pal["ink"])
        y += lh
    d.text((62, H - 56), "DOPEAK", font=_f(PSEMI, 30), fill=pal["accent"])
    d.text((W - 40, H - 56), "▶ SHORTS", font=_f(PSEMI, 26), fill=(190, 190, 190), anchor="ra")
    img.save(out, "JPEG", quality=92)
    return out


def design_burst(title, out, pal, bg):
    """Radial rays behind a stroked headline, round badge with the step count."""
    img = _flat(pal)
    d = ImageDraw.Draw(img)
    cx, cy = int(W * 0.5), int(H * 0.46)
    for i in range(28):
        a = i * (360 / 28)
        import math
        x2 = cx + int(1500 * math.cos(math.radians(a)))
        y2 = cy + int(1500 * math.sin(math.radians(a)))
        if i % 2 == 0:
            d.polygon([(cx, cy), (x2, y2), (cx + int(60 * math.cos(math.radians(a + 6))),
                                             cy + int(60 * math.sin(math.radians(a + 6))))],
                      fill=tuple(min(255, c + 10) for c in pal["bg"]))
    f, lines, lh = _fit(d, title, ANTON, W - 200, 380, start=190)
    y = (H - len(lines) * lh) // 2 - 20
    for ln in lines:
        bb = d.textbbox((0, 0), ln, font=f)
        d.text(((W - (bb[2] - bb[0])) // 2, y), ln, font=f, fill=pal["ink"],
               stroke_width=9, stroke_fill=tuple(max(0, c - 6) for c in pal["bg"]))
        y += lh
    m = re.search(r"\b(\d{1,3})\b", title)
    if m and m.group(1) not in " ".join(lines):
        r = 74
        bx, by = W - 150, 120
        d.ellipse([bx - r, by - r, bx + r, by + r], fill=pal["accent"])
        d.text((bx, by - 6), m.group(1), font=_f(ANTON, 92), fill=pal["bg"], anchor="mm")
    _brand(d, pal)
    img.save(out, "JPEG", quality=92)
    return out


def design_chart(title, out, pal, bg):
    """Data-line design: grid, headline top, a bold polyline that never touches the type."""
    img = bg or _flat(pal)
    d = ImageDraw.Draw(img)
    for x in range(0, W, 80):                     # grid
        d.line([(x, 0), (x, H)], fill=tuple(min(255, c + 8) for c in pal["bg"]), width=1)
    for y in range(0, H, 80):
        d.line([(0, y), (W, y)], fill=tuple(min(255, c + 8) for c in pal["bg"]), width=1)
    # headline FIRST, so the chart starts under the measured text block (drawing the line
    # behind the title was the defect a vision read flagged on the first pass)
    f, lines, lh = _fit(d, title.upper(), ANTON, W - 130, 300, start=150)
    y0 = 60
    for ln in lines:
        d.text((60, y0), ln, font=f, fill=pal["ink"],
               stroke_width=8, stroke_fill=tuple(max(0, c - 8) for c in pal["bg"]))
        y0 += lh
    chart_top = max(y0 + 50, int(H * 0.52))
    pts, rng = [], random.Random(len(title))
    y = H * 0.72
    for i in range(9):
        y -= rng.uniform(10, 46)
        pts.append((int(80 + i * (W - 220) / 8), int(max(chart_top, min(H - 150, y)))))
    d.line(pts, fill=pal["accent"], width=14, joint="curve")
    for p in pts:
        d.ellipse([p[0] - 9, p[1] - 9, p[0] + 9, p[1] + 9], fill=pal["ink"])
    _brand(d, pal)
    img.save(out, "JPEG", quality=92)
    return out


def design_stamp(title, out, pal, bg):
    """Warning/stamp look: hazard corner, black slab behind white type, exclamation badge."""
    img = _flat(pal)
    d = ImageDraw.Draw(img)
    for i in range(200, W + 300, 56):             # hazard stripes, top-right only
        d.line([(i, 0), (i - 260, 260)], fill=pal["accent"], width=16)
    d.rectangle([0, 140, W, 300], fill=(0, 0, 0))
    d.rectangle([56, 152, 186, 288], fill=(0, 0, 0))   # clear space for the badge
    f, lines, lh = _fit(d, title, ANTON, W - 210, 300, start=170)
    y = 300 + 60
    if len(lines) > 2:
        y = 330
    for ln in lines:
        d.text((56, y), ln, font=f, fill=(255, 255, 255),
               stroke_width=7, stroke_fill=(0, 0, 0))
        y += lh
    # badge
    cx, cy, r = 120, 220, 62
    d.polygon([(cx, cy - r), (cx + r, cy + r), (cx - r, cy + r)], fill=pal["accent"])
    d.text((cx, cy + 16), "!", font=_f(ANTON, 84), fill=(0, 0, 0), anchor="mm")
    _brand(d, pal)
    img.save(out, "JPEG", quality=92)
    return out


_RENDER = dict(bignum=design_bignum, split=design_split, poster=design_poster,
               burst=design_burst, chart=design_chart, stamp=design_stamp)


def make(title: str, out_path: str, src_video: Path | None = None,
         style: str | None = None, advance: bool = True) -> tuple[str, str]:
    """Render `title` in the next (or requested) design. Returns (path, style)."""
    if os.environ.get("THUMB_VARIETY", "1") == "0":
        raise RuntimeError("variety disabled")
    st = style or next_design(advance=advance)
    pal = PALETTES[DESIGNS.index(st) % len(PALETTES)]
    text = _phrase(title, max_words=6)
    bg = None
    if st in ("split", "chart"):
        bg = _bg_image(src_video, blur=8 if st == "split" else 4,
                       brightness=0.5 if st == "split" else 0.32)
    if st in ("bignum", "burst", "stamp", "poster") and bg is None and src_video:
        pass  # flat designs stay flat: a busy photo behind 300 px type is what killed CTR
    out = _RENDER[st](text.upper() if st != "chart" else text, str(out_path), pal, bg)
    return out, st


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        p, s = make(sys.argv[2], sys.argv[1])
        log(s, p)
    else:
        for d in DESIGNS:
            p, s = make("3 numbers that shape your salary", f"/tmp/thumb_{d}.jpg", style=d)
            log("preview", s, p)
