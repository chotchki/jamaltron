"""G.7: the title overlay and the end card, in Titillium Web read from the install.

The COPY is player copy in Jamal's voice (the README's register: apologetic, jubilant, third
person by name, the honorific never drops) plus the credits in plain type. The credit lines
are not decoration, each is owed:
  * "3D model copyright Pig Scales Studio via RenderHub" - the model licence's own credit line
  * the unofficial non-commercial DCC fan-work line - the quotes rest on that fair-use call
  * "Factorio by Wube Software · factorio.com" - every sound and pixel is the game's, and
    Wube's press kit asks videos to link the site
Change them in one place, here; tests pin the exact strings chotchki signed off.

THE LOOK: Factorio's own UI type and colours (core style.lua): caption {255, 230, 192} for
the heads, gui orange {0.98, 0.66, 0.22} = (250, 168, 56) for his voice lines, on dark - the
dist research's font_card_sample.png. The title sits in the TOP THIRD of the live opening, so
frame 0 doubles as the poster; the end card sits over the last frame, dimmed and blurred.
"""

from __future__ import annotations

import dataclasses
import functools
from typing import Literal

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from video.captions import Fonts, wrap
from video.timeline import Geometry

CAPTION_RGB = (255, 230, 192)       # style.lua gui_color.caption: window titles
ORANGE_RGB = (250, 168, 56)         # style.lua orange {0.98, 0.66, 0.22}
CREDIT_RGB = (222, 212, 196)        # the caption colour, a step quieter
SHADOW_RGBA = (0, 0, 0, 170)

TITLE = "JAMALTRON"
TITLE_LINE = "Jamal is so very sorry. Jamal must jump!"
# Rows are the intended breaks (a row still wraps if a small test frame cannot fit it): the
# end line pauses on "Mr. Engineer." before the sorries, and the DCC line breaks at its
# sentence instead of orphaning "Not".
END_ROWS = ("Jamal must give his thanks, Mr. Engineer.", "And his sorries. All of them.")
CREDIT_ROWS = (
    ("3D model copyright Pig Scales Studio via RenderHub",),
    ("Unofficial, non-commercial fan work of Matt Dinniman's Dungeon Crawler Carl.",
     "Not affiliated with or endorsed by Dinniman, his publishers or Soundbooth Theater."),
    ("Factorio 2.1 mod, Space Age optional \u00b7 github.com/chotchki/jamaltron",),
    ("Factorio by Wube Software \u00b7 factorio.com",),
)
END_LINE = " ".join(END_ROWS)
CREDITS = tuple(" ".join(rows) for rows in CREDIT_ROWS)

# px at 1080p. CREDIT_PX >= 28: below that the small print blurs out at 720p playback.
TITLE_PX, TITLE_LINE_PX = 150, 54
END_TITLE_PX, END_LINE_PX = 132, 50
CREDIT_PX = 30
END_WRAP_PX, CREDIT_WRAP_PX = 1500, 1560

DIM = 0.34                          # the end card's backdrop brightness
BLUR_PX = 14                        # and its blur radius
CARD_FADE_S = 0.6                   # freeze frame -> end card crossfade
OVERLAY_FADE_OUT_S = 0.5            # the title leaves over this much of its window
OVERLAY_FADE_IN_S = 0.3             # and arrives over this, unless it starts on frame 0 (the
                                    # poster frame must carry the title at full strength)

Mode = Literal["overlay", "card"]


def scaled_lut(k: float) -> list[int]:
    """A 256-entry point() table multiplying one band by k."""
    return [round(v * k) for v in range(256)]


def smoothstep(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def _shadowed(d: ImageDraw.ImageDraw, xy: tuple[float, float], text: str,
              font: ImageFont.FreeTypeFont,
              fill: tuple[int, int, int], scale: float, anchor: str = "ms") -> None:
    off = max(1, round(3 * scale))
    d.text((xy[0], xy[1] + off), text, font=font, fill=SHADOW_RGBA, anchor=anchor)
    d.text(xy, text, font=font, fill=fill + (255,), anchor=anchor)


@dataclasses.dataclass(eq=False)       # identity hash: layer() is cached per instance
class Cards:
    geo: Geometry
    fonts: Fonts
    _full: dict[tuple[str, int], Image.Image] = dataclasses.field(default_factory=dict)

    @property
    def s(self) -> float:
        return self.geo.scale

    def _px(self, n: float) -> int:
        return max(1, round(n * self.s))

    @functools.lru_cache(maxsize=8)  # noqa: B019 - one Cards per build
    def layer(self, name: str, mode: Mode) -> Image.Image:
        """The card's text (and its own scrim) as an RGBA the size of the kept frame."""
        if name == "title":
            return self._title()
        if name == "end":
            return self._end(scrim=mode == "overlay")
        raise ValueError(f"no card {name!r}")

    def _title(self) -> Image.Image:
        w, h = self.geo.out_size
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        # A scrim fading down from the top edge: the title must read over grass, water, or
        # a biter, whatever frame 0 turns out to be. Linear to 0 at 45% of the height.
        fade_h = round(h * 0.45)
        ramp = Image.linear_gradient("L").resize((1, fade_h))
        alpha = ramp.point([round((255 - v) * 150 / 255) for v in range(256)])
        scrim = Image.new("RGBA", (w, fade_h), (0, 0, 0, 0))
        scrim.putalpha(alpha.resize((w, fade_h)))
        img.alpha_composite(scrim)
        d = ImageDraw.Draw(img)
        _shadowed(d, (w / 2, self._px(205)), TITLE, self.fonts.get("bold", self._px(TITLE_PX)),
                  CAPTION_RGB, self.s)
        _shadowed(d, (w / 2, self._px(292)), TITLE_LINE,
                  self.fonts.get("semibold", self._px(TITLE_LINE_PX)), ORANGE_RGB, self.s)
        return img

    def _end(self, scrim: bool) -> Image.Image:
        w, h = self.geo.out_size
        img = Image.new("RGBA", (w, h), (0, 0, 0, round(255 * (1 - DIM)) if scrim else 0))
        d = ImageDraw.Draw(img)
        big = self.fonts.get("bold", self._px(END_TITLE_PX))
        line = self.fonts.get("semibold", self._px(END_LINE_PX))
        small = self.fonts.get("regular", self._px(CREDIT_PX))
        line_rows = [r for row in END_ROWS for r in wrap(row, line, END_WRAP_PX * self.s)]
        credit_rows = [[r for row in rows for r in wrap(row, small, CREDIT_WRAP_PX * self.s)]
                       for rows in CREDIT_ROWS]

        # Vertical stack, centred as a block: title, voice line, a short orange rule, credits.
        line_h, credit_h = self._px(END_LINE_PX * 1.25), self._px(CREDIT_PX * 1.3)
        para_gap = self._px(CREDIT_PX * 0.55)
        parts: list[tuple[str, int]] = [("title", self._px(END_TITLE_PX * 0.95)),
                                        ("gap", self._px(30))]
        parts += [("line", line_h)] * len(line_rows)
        parts += [("gap", self._px(34)), ("rule", self._px(4)), ("gap", self._px(40))]
        for k, rows in enumerate(credit_rows):
            parts += [("credit", credit_h)] * len(rows)
            if k < len(credit_rows) - 1:
                parts.append(("gap", para_gap))
        total = sum(hh for _, hh in parts)
        y = (h - total) / 2
        lines, credits = iter(line_rows), iter(r for rows in credit_rows for r in rows)
        for kind, hh in parts:
            if kind == "title":
                _shadowed(d, (w / 2, y + hh), TITLE, big, CAPTION_RGB, self.s)
            elif kind == "line":
                _shadowed(d, (w / 2, y + hh * 0.8), next(lines), line, ORANGE_RGB, self.s)
            elif kind == "rule":
                half = self._px(120)
                d.rectangle((w / 2 - half, y, w / 2 + half, y + hh - 1),
                            fill=ORANGE_RGB + (200,))
            elif kind == "credit":
                d.text((w / 2, y + hh * 0.78), next(credits), font=small,
                       fill=CREDIT_RGB + (255,), anchor="ms")
            y += hh
        return img

    # ------------------------------------------------------------------ compositing

    def overlay(self, frame: Image.Image, name: str, alpha: float) -> Image.Image:
        """`frame` (RGB, the kept size) with card `name` over it at `alpha`. Returns a new
        image; `frame` may be a cached source frame and is never drawn on."""
        layer = self.layer(name, "overlay")
        out = frame.copy()
        if alpha >= 1:
            out.paste(layer, (0, 0), layer)
        elif alpha > 0:
            a = layer.getchannel("A").point(scaled_lut(alpha))
            out.paste(layer.convert("RGB"), (0, 0), a)
        return out

    def overlay_alpha(self, frame: int, start: int, stop: int, fps: int) -> float:
        """Fade in (unless the window opens the video) and fade out, in output frames. Each
        fade takes at most half the window, so a short overlay still reaches full strength."""
        into, left, half = frame - start, stop - frame, max(1.0, (stop - start) / 2)
        a = 1.0
        if start > 0:
            a = min(a, smoothstep((into + 1) / min(half, OVERLAY_FADE_IN_S * fps)))
        return min(a, smoothstep(left / min(half, OVERLAY_FADE_OUT_S * fps)))

    def _card_full(self, name: str, backdrop_key: int, backdrop: Image.Image) -> Image.Image:
        key = (name, backdrop_key)
        if key not in self._full:
            base = backdrop.point(scaled_lut(DIM) * 3)
            base = base.filter(ImageFilter.GaussianBlur(BLUR_PX * self.s))
            layer = self.layer(name, "card")
            base.paste(layer, (0, 0), layer)
            self._full = {key: base}        # one card at a time; a cut has one or two
        return self._full[key]

    def card(self, name: str, backdrop_key: int, backdrop: Image.Image,
             last_shown: Image.Image | None, k: int, fps: int) -> Image.Image:
        """Frame `k` of card `name`: over the last source frame dimmed and blurred, crossfading
        in from `last_shown` (the last composed frame before the card, caption and all)."""
        full = self._card_full(name, backdrop_key, backdrop)
        t = smoothstep((k + 1) / max(1, CARD_FADE_S * fps))
        if last_shown is None or t >= 1:
            return full
        return Image.blend(last_shown, full, t)
