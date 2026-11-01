"""Finance graphics — PREMIUM animated charts for finance videos.

Design language (the "cool" look):
  - deep navy background with a soft radial glow
  - NEON glowing curves (layered strokes: wide+faint -> thin+bright)
  - animated count-up numbers for the key figure
  - clean mono typography, NO watermark (see PLAYBOOK section 2: watermarked
    content is de-prioritised; the brand rides on title/thumbnail only)
All rendered with Manim (fully original, monetization-safe).
"""
import math
import os
from manim import *

# Watermark OFF by default (PLAYBOOK §2). Set DOPEAK_WATERMARK=1 to bring the
# corner brand mark back for a one-off render.
SHOW_WATERMARK = os.environ.get("DOPEAK_WATERMARK", "").strip().lower() in ("1", "true", "yes")

# --- Variation engine -------------------------------------------------------
# Each render picks a palette from SCENE_SEED, so the SAME chart type never
# looks identical twice (the pipeline sets SCENE_SEED per video).
_PALETTES = [
    dict(bg="#0E1020", halo1="#243056", halo2="#2E3C6E", blue="#4FC3F7",
         green="#57F287", yellow="#FFD54F", red="#FF5C6C", purple="#B388FF"),
    dict(bg="#0B1A14", halo1="#12382A", halo2="#1C5A40", blue="#6FE7FF",
         green="#7CFF9E", yellow="#FFE082", red="#FF7A7A", purple="#C7A6FF"),
    dict(bg="#170F22", halo1="#33204A", halo2="#4A2E6B", blue="#82B1FF",
         green="#69F0AE", yellow="#FFD180", red="#FF5252", purple="#EA80FC"),
    dict(bg="#0A1622", halo1="#10304A", halo2="#164A6E", blue="#40C4FF",
         green="#4EE6A8", yellow="#FFCA28", red="#FF6E6E", purple="#B39DFF"),
    dict(bg="#14110C", halo1="#332A18", halo2="#4A3C22", blue="#5BC8FF",
         green="#8BD450", yellow="#FFD24D", red="#FF6B5B", purple="#D0A0FF"),
    dict(bg="#1A0F14", halo1="#3A2030", halo2="#552E45", blue="#7FD8FF",
         green="#5CE1A6", yellow="#FFCF6B", red="#FF5C8A", purple="#C39BFF"),
    # 6/7 added 2026-10-27 (repetition guardian): six palettes return every sixth upload.
    dict(bg="#0C1418", halo1="#123038", halo2="#1B4A55", blue="#67E8F9",
         green="#A3E635", yellow="#FDE047", red="#FB7185", purple="#C4B5FD"),
    dict(bg="#101018", halo1="#282A44", halo2="#3B3F66", blue="#93C5FD",
         green="#6EE7B7", yellow="#FCD34D", red="#F87171", purple="#DDD6FE"),
]
_P = _PALETTES[int(os.environ.get("SCENE_SEED", "0")) % len(_PALETTES)]

BG = _P["bg"]
BLUE = _P["blue"]
GREEN = _P["green"]
YELLOW = _P["yellow"]
RED = _P["red"]
PURPLE = _P["purple"]
HALO1 = _P["halo1"]
HALO2 = _P["halo2"]
WHITE = "#FFFFFF"
GREY = "#8A93B5"
MONO = "DejaVu Sans Mono"
AXIS = "#6C7699"
BRAND = "DOPEAK"


def _bg(scene):
    scene.camera.background_color = BG
    halo = Circle(radius=4.6, color=HALO1, fill_opacity=0.55,
                  stroke_width=0).move_to(UP * 0.2)
    halo2 = Circle(radius=2.6, color=HALO2, fill_opacity=0.5,
                   stroke_width=0).move_to(UP * 0.2)
    scene.add(halo, halo2)


def _brand(scene):
    if not SHOW_WATERMARK:
        return
    wm = Text(BRAND, font_size=22, color=GREY, font=MONO, weight=BOLD)
    wm.to_corner(UR, buff=0.35).set_opacity(0.7)
    scene.add(wm)


def _title(scene, text):
    t = Text(text, font_size=46, color=WHITE, font=MONO, weight=BOLD)
    g = t.copy().set_stroke(color=BLUE, width=14, opacity=0.10)
    scene.add(g)
    scene.play(Write(t), run_time=1.1)
    scene.play(t.animate.to_edge(UP, buff=0.45).scale(0.66),
               g.animate.to_edge(UP, buff=0.45).scale(0.66), run_time=0.7)
    return t


def glow(mob, color, widths=(22, 14, 8), opacities=(0.05, 0.12, 1.0)):
    """Layered strokes to fake a neon glow."""
    grp = VGroup()
    for w, o in zip(widths, opacities):
        c = mob.copy()
        c.set_stroke(color=color, width=w, opacity=o)
        grp.add(c)
    return grp


def _axes(scene, xr, yr, xlen=9.2, ylen=4.4):
    axes = Axes(x_range=xr, y_range=yr, x_length=xlen, y_length=ylen,
                color=AXIS, axis_config={"stroke_width": 2.5,
                                         "stroke_color": AXIS, "color": AXIS,
                                         "include_tip": True, "tip_width": 0.2,
                                         "tip_height": 0.25})
    axes.add_coordinates(font_size=15, color=GREY)
    axes.shift(UP * 0.85)
    scene.play(Create(axes), run_time=1.2)
    return axes


class CompoundingCurve(Scene):
    def construct(self):
        _bg(self); _brand(self)
        _title(self, "The Power of Compounding")
        axes = _axes(self, [0, 30, 5], [0, 9, 2])

        early = axes.plot(lambda x: 0.5 * (1.1 ** x), color=GREEN,
                          x_range=[0, 30], stroke_width=5)
        late = axes.plot(lambda x: 0.2 * (1.1 ** max(x - 10, 0)) + 0.2,
                         color=YELLOW, x_range=[0, 30], stroke_width=5)
        self.play(Create(glow(early, GREEN)), run_time=2.2)
        self.play(Create(glow(late, YELLOW)), run_time=2.0)
        self.add(axes.get_area(early, x_range=[0, 30], color=GREEN, opacity=0.16))
        self.add(axes.get_area(late, x_range=[0, 30], color=YELLOW, opacity=0.12))

        # animated count-up without LaTeX (DecimalNumber needs LaTeX/dvisvgm)
        tracker = ValueTracker(0)
        counter = always_redraw(lambda: VGroup(
            Text(f"{int(tracker.get_value())}x", color=GREEN, font=MONO,
                 font_size=54, weight=BOLD),
            Text("your money", color=GREY, font=MONO, font_size=26),
        ).arrange(RIGHT, buff=0.18).next_to(axes, DOWN, buff=0.55))
        self.add(tracker, counter)
        self.play(tracker.animate.set_value(17), run_time=2.4)
        lbl = Text("F = P(1+r)^t", color=WHITE, font=MONO, font_size=40
                    ).next_to(axes, UP, buff=0.2).shift(LEFT * 3.2)
        self.play(Write(lbl), run_time=1.0)
        self.wait(3.5)
        self.wait(1.5)


class StockMarket(Scene):
    def construct(self):
        _bg(self); _brand(self)
        _title(self, "The Market Always Rises")
        axes = _axes(self, [0, 20, 5], [0, 10, 2])

        def price(x):
            return 1.5 + 0.4 * x + 1.2 * math.sin(x * 1.7) + 0.6 * math.sin(x * 0.6)
        curve = axes.plot(price, color=GREEN, x_range=[0, 20], stroke_width=5)
        self.play(Create(glow(curve, GREEN)), run_time=2.8)
        self.add(axes.get_area(curve, x_range=[0, 20], color=GREEN, opacity=0.15))
        trend = axes.plot(lambda x: 1.5 + 0.4 * x, color=YELLOW,
                          x_range=[0, 20], stroke_width=4)
        self.play(Create(glow(trend, YELLOW)), run_time=1.8)
        lbl = Text("zoom out: the trend is up", font_size=32, color=WHITE,
                   font=MONO, weight=BOLD).next_to(axes, DOWN, buff=0.5)
        self.play(Write(lbl), run_time=1.2)
        self.wait(4.0)
        self.wait(1.5)


class InflationVsCash(Scene):
    def construct(self):
        _bg(self); _brand(self)
        _title(self, "Inflation Eats Cash")
        axes = _axes(self, [0, 20, 5], [0, 10, 2])

        cash = axes.plot(lambda x: 5, color=YELLOW, x_range=[0, 20], stroke_width=5)
        prices = axes.plot(lambda x: 5 * (1.04 ** x), color=RED,
                           x_range=[0, 20], stroke_width=5)
        self.play(Create(glow(cash, YELLOW)), run_time=1.4)
        self.play(Create(glow(prices, RED)), run_time=2.2)
        self.add(axes.get_area(prices, x_range=[0, 20], color=RED, opacity=0.16))
        cl = Text("cash $5", font_size=27, color=YELLOW, font=MONO, weight=BOLD
                  ).next_to(axes, UP, buff=0.2).shift(RIGHT * 3)
        pl = Text("prices ↑", font_size=27, color=RED, font=MONO, weight=BOLD
                  ).next_to(axes, UP, buff=0.2).shift(LEFT * 3)
        self.play(Write(cl), Write(pl), run_time=0.9)
        gap = Text("buying power ↓", font_size=32, color=WHITE, font=MONO,
                   weight=BOLD).next_to(axes, DOWN, buff=0.5)
        self.play(Write(gap), run_time=1.2)
        self.wait(4.0)
        self.wait(1.5)


class Diversification(Scene):
    def construct(self):
        _bg(self); _brand(self)
        _title(self, "Don't Bet On One Thing")
        colors = [BLUE, GREEN, YELLOW, RED, PURPLE, "#FFB74D"]
        sizes = [0.30, 0.25, 0.18, 0.12, 0.09, 0.06]
        start = 0
        sectors = VGroup()
        for sz, col in zip(sizes, colors):
            s = Sector(angle=TAU * sz, start_angle=start, color=col,
                       fill_opacity=0.92, stroke_width=2, stroke_color=BG)
            start += TAU * sz
            sectors.add(s)
        sectors.scale(2.1).shift(UP * 0.35)
        glow_disc = Circle(radius=2.2, color=BLUE, fill_opacity=0.10,
                           stroke_width=0).move_to(UP * 0.35)
        self.add(glow_disc)
        self.play(FadeIn(sectors), run_time=2.2)
        lbl = Text("many small pieces = less risk", font_size=34, color=WHITE,
                   font=MONO, weight=BOLD).next_to(sectors, DOWN, buff=0.4)
        self.play(Write(lbl), run_time=1.2)
        self.wait(4.0)
        self.wait(1.5)


class ActiveVsPassive(Scene):
    def construct(self):
        _bg(self); _brand(self)
        _title(self, "Active vs Passive")
        axes = _axes(self, [0, 3, 1], [0, 10, 2], xlen=7)

        def vbar(x, val, color, w=0.72):
            """A bar whose HEIGHT comes from the data axis, not from scene units."""
            y0, y1 = axes.c2p(0, 0)[1], axes.c2p(0, val)[1]
            r = Rectangle(width=w, height=abs(y1 - y0), color=color, fill_opacity=0.85)
            r.move_to(np.array([axes.c2p(x, 0)[0], (y0 + y1) / 2.0, 0]))
            return r

        active = vbar(1, 3.4, RED)
        passive = vbar(2, 8.2, GREEN)
        self.play(FadeIn(glow(active, RED)), FadeIn(glow(passive, GREEN)), run_time=1.4)
        al = Text("active\n(high fees)", font_size=25, color=RED, font=MONO,
                  weight=BOLD).next_to(active, DOWN, buff=0.25)
        pl = Text("index\n(low fees)", font_size=25, color=GREEN, font=MONO,
                  weight=BOLD).next_to(passive, DOWN, buff=0.25)
        self.play(Write(al), Write(pl), run_time=1.1)
        note = Text("lower fees = more for you", font_size=32, color=WHITE,
                    font=MONO, weight=BOLD).next_to(axes, DOWN, buff=0.45)
        self.play(Write(note), run_time=1.2)
        self.wait(4.0)
        self.wait(1.5)


class TaxDrag(Scene):
    def construct(self):
        _bg(self); _brand(self)
        _title(self, "The Hidden Tax Drag")
        axes = _axes(self, [0, 20, 5], [0, 10, 2])

        taxed = axes.plot(lambda x: 1 * (1.06 ** x), color=RED,
                          x_range=[0, 20], stroke_width=5)
        deferred = axes.plot(lambda x: 1 * (1.08 ** x), color=GREEN,
                             x_range=[0, 20], stroke_width=5)
        self.play(Create(glow(taxed, RED)), run_time=1.8)
        self.play(Create(glow(deferred, GREEN)), run_time=1.8)
        self.add(axes.get_area(deferred, x_range=[0, 20], color=GREEN, opacity=0.13))
        tl = Text("taxed yearly", font_size=27, color=RED, font=MONO, weight=BOLD
                  ).next_to(axes, UP, buff=0.2).shift(RIGHT * 3)
        dl = Text("tax-deferred", font_size=27, color=GREEN, font=MONO, weight=BOLD
                  ).next_to(axes, UP, buff=0.2).shift(LEFT * 3)
        self.play(Write(tl), Write(dl), run_time=0.9)
        note = Text("small % tax = big $ lost", font_size=32, color=WHITE,
                    font=MONO, weight=BOLD).next_to(axes, DOWN, buff=0.5)
        self.play(Write(note), run_time=1.2)
        self.wait(4.0)
        self.wait(1.5)


GRAPHIC_SCENES = {
    "compounding": CompoundingCurve,
    "stock": StockMarket,
    "inflation": InflationVsCash,
    "diversify": Diversification,
    "compare": ActiveVsPassive,
    "tax": TaxDrag,
}
