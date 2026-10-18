"""The look as building blocks: tokens (colours, fonts, spacing) and prefabs drawn in code at any size. Colours and
fonts come from your theme (theme.py); these are the shapes. Keep them plain and well spaced: one accent colour,
crisp corners, generous padding, nothing bubbly."""
import functools, math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .project import ACCENT, F_MONO, F_MONO_B, F_MONO_XB, INK, ON_ACCENT, TEXT
from .draw import clamp01, ease_out, font, text_line

# ---- tokens
WHITE = (255, 255, 255)
PAPER = (240, 238, 234)       # light surfaces
GREY = (122, 122, 128)        # secondary text
LINE = (48, 48, 52)           # hairlines on dark
MUTED = (220, 220, 220)       # body text on dark
U = 8                         # spacing unit: everything snaps to multiples of 8
PAD = 5 * U                   # inside a card
GAP = 3 * U                   # between elements
MARGIN = 2 * U                # minimum distance from content to a card edge (QA flags less as TIGHT)
R = 14                        # corner radius

import os as _os
PANEL_ALPHA = int(_os.environ.get("CLIP_PANEL_ALPHA") or 235)   # dark cards: 235 solid; ~170 lets the shot show through


def bar(h, color=None, width=None):
    """the accent bar: a short vertical rule that marks a headline or a tag"""
    w = width or max(4, int(h * 0.09))
    im = Image.new("RGBA", (w, h))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), w // 2, fill=tuple((color or ACCENT)[:3]) + (255,))
    return im


def fade_in(im, k):
    """the way in for any element: it comes into focus and fades up as k goes 0 -> 1 (im unchanged at k >= 1)"""
    k = clamp01(k)
    if k >= 1:
        return im
    e = ease_out(k)
    out = im.filter(ImageFilter.GaussianBlur(10 * (1 - e))) if e < 0.98 else im.copy()
    out.putalpha(out.split()[3].point(lambda v: int(v * e)))
    return out


def tag(text, size=44, k=1.0, fpath=None, color=None, bar_color=None, scrim=False):
    """a short label with the accent bar on its left. k animates it: the bar grows (first 40%), then the text slides
    in beside it. scrim=True puts a dark plate behind it for legibility over busy video."""
    fpath = fpath or F_MONO_B
    t = text_line(text, fpath, size, color or TEXT)
    h = int(t.height * 1.3)
    b = bar(h, bar_color)
    gap = U * 2
    out = Image.new("RGBA", (b.width + gap + t.width, h))
    grow = ease_out(clamp01(k / 0.4))
    if grow > 0:
        bh = max(1, int(h * grow))
        out.alpha_composite(b.crop((0, 0, b.width, bh)), (0, (h - bh) // 2))
    if k > 0.4:
        e = ease_out(clamp01((k - 0.4) / 0.6))
        shown = t.copy()
        shown.putalpha(shown.split()[3].point(lambda v: int(v * e)))
        out.alpha_composite(shown, (b.width + gap - int((1 - e) * U * 3), (h - t.height) // 2))
    if scrim:
        bg = Image.new("RGBA", (out.width + 4 * U, out.height + 2 * U))
        ImageDraw.Draw(bg).rounded_rectangle((0, 0, bg.width - 1, bg.height - 1), R, fill=INK + (190,))
        bg.alpha_composite(out, (2 * U, U))
        return bg
    return out


def label(text, size=30, color=GREY, fpath=None):
    """a short line of monospace text: a field name in a table, a unit, a counter, a credit"""
    return text_line(text, fpath or F_MONO_B, size, color)


def chip(text, size=44, fill=None, color=None, fpath=None, radius=6):
    """a small solid plate for a value or a short word ("51-52 %", "NEW"): crisp corners"""
    from .project import F_BLACK
    t = text_line(text, fpath or F_BLACK, size, color or ON_ACCENT)
    fill = fill or ACCENT
    px, py = int(size * 0.42), int(size * 0.16)
    im = Image.new("RGBA", (t.width + 2 * px, t.height + 2 * py))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius,
                                         fill=tuple(fill[:3]) + (fill[3] if len(fill) > 3 else 255,))
    im.alpha_composite(t, (px, py))
    return im


# ---- surfaces
def panel(w, h, tone="dark", border=True):
    """a card: rounded corners, a hairline border. tone: 'dark' (near-black) or 'light' (paper)."""
    fill = (18, 18, 20, PANEL_ALPHA) if tone == "dark" else PAPER + (255,)
    edge = LINE + (255,) if tone == "dark" else (205, 202, 198, 255)
    im = Image.new("RGBA", (w, h))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), R, fill=fill, outline=edge if border else None, width=2)
    return im


def stamp(text, size=64, color=None):
    """a stamp: heavy mono caps in a double frame (rotate it when placing)"""
    color = color or ACCENT
    t = text_line(text.upper(), F_MONO_XB, size, color)
    p = U * 2
    im = Image.new("RGBA", (t.width + 2 * p + 12, t.height + 2 * p))
    d = ImageDraw.Draw(im)
    d.rectangle((3, 3, im.width - 4, im.height - 4), outline=color, width=6)
    d.rectangle((13, 13, im.width - 14, im.height - 14), outline=color, width=2)
    im.alpha_composite(t, ((im.width - t.width) // 2, (im.height - t.height) // 2))
    return im


# ---- marks: highlight something without the "circled in MS Paint" ellipse
def mark(w, h, kind="under", k=1.0, color=None, weight=None):
    """a mark for a w x h area, drawn in progressively as k goes 0 -> 1. Place it centred on the area.
    kind: 'under' (thick bar under the text), 'strike' (through it), 'box' (corner brackets around it)."""
    color = color or ACCENT
    k = clamp01(k)
    wt = weight or max(4, int(h * 0.12))
    pad = U
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad))
    d = ImageDraw.Draw(im)
    if kind == "under":
        d.rectangle((pad, pad + h - wt // 2, pad + w * k, pad + h + wt // 2), fill=color)
    elif kind == "strike":
        y = pad + h * 0.55
        d.rectangle((pad - 4, y - wt / 2, pad - 4 + (w + 8) * k, y + wt / 2), fill=color)
    elif kind == "box":
        L = min(w, h) * 0.35 * ease_out(k) + 1
        x0, y0, x1, y1 = 2, 2, im.width - 3, im.height - 3
        for (x, y, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            d.line((x, y, x + sx * L, y), fill=color, width=wt)
            d.line((x, y, x, y + sy * L), fill=color, width=wt)
    return im


# ---- gradients and texture, computed (smooth at any size, dithered so 8-bit doesn't band)
def gradient(w, h, c0, c1, axis="y", ease=True, seed=0):
    """RGBA gradient from c0 to c1 (RGBA tuples) along x or y, smoothstep-eased and dithered"""
    return _gradient(w, h, tuple(c0), tuple(c1), axis, ease, seed).copy()


@functools.lru_cache(maxsize=64)  # the same scrim is drawn on most frames; building one costs ~40 ms
def _gradient(w, h, c0, c1, axis, ease, seed):
    n = h if axis == "y" else w
    t = np.linspace(0, 1, n, dtype=np.float32)
    if ease:
        t = t * t * (3 - 2 * t)
    c0, c1 = np.array(c0, np.float32), np.array(c1, np.float32)
    line = c0[None] + (c1 - c0)[None] * t[:, None]
    arr = np.broadcast_to(line[:, None, :] if axis == "y" else line[None, :, :], (h, w, 4)).copy()
    arr += np.random.default_rng(seed).uniform(-0.5, 0.5, arr.shape).astype(np.float32)
    return Image.fromarray(np.clip(arr + 0.5, 0, 255).astype(np.uint8), "RGBA")


def fade(w, h, color=INK, top=0.0, bottom=1.0):
    """a scrim: color fading from alpha `top` to `bottom` (0..1) down the height"""
    return gradient(w, h, tuple(color[:3]) + (255 * top,), tuple(color[:3]) + (255 * bottom,))


def radial(w, h, inner=0.0, outer=0.6, color=(0, 0, 0)):
    """vignette: color with alpha from `inner` at the centre to `outer` at the corners"""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / math.sqrt(2)
    r = r * r * (3 - 2 * r)
    a = (inner + (outer - inner) * r) * 255 + np.random.default_rng(1).uniform(-0.5, 0.5, r.shape)
    arr = np.zeros((h, w, 4), np.uint8)
    arr[..., :3] = color
    arr[..., 3] = np.clip(a, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def grain(im, amount=6, seed=0):
    """subtle film grain on an RGBA image (in place-safe copy); vary seed per frame for live grain"""
    a = np.asarray(im).astype(np.int16)
    n = np.random.default_rng(seed).normal(0, amount, a.shape[:2])[..., None].astype(np.int16)
    a[..., :3] = np.clip(a[..., :3] + n, 0, 255)
    return Image.fromarray(a.astype(np.uint8), "RGBA")


# ---- layout helpers: build boards from parts with consistent spacing instead of hand-placing pixels
def vstack(items, gap=GAP, align="left"):
    """stack images vertically with `gap` between them -> one image (align: left / center / right)"""
    items = [i for i in items if i is not None]
    w = max(i.width for i in items)
    out = Image.new("RGBA", (w, sum(i.height for i in items) + gap * (len(items) - 1)))
    y = 0
    for i in items:
        x = {"left": 0, "center": (w - i.width) // 2, "right": w - i.width}[align]
        out.alpha_composite(i, (x, y))
        y += i.height + gap
    return out


def hstack(items, gap=GAP, align="center"):
    """side by side with `gap` between -> one image (align: top / center / bottom)"""
    items = [i for i in items if i is not None]
    h = max(i.height for i in items)
    out = Image.new("RGBA", (sum(i.width for i in items) + gap * (len(items) - 1), h))
    x = 0
    for i in items:
        y = {"top": 0, "center": (h - i.height) // 2, "bottom": h - i.height}[align]
        out.alpha_composite(i, (x, y))
        x += i.width + gap
    return out


def on_panel(content, tone="dark", pad=PAD, min_w=0, min_h=0, align="center"):
    """content on a panel with `pad` all round. The panel grows to fit the content and never crops it; min_w/min_h
    keep a board the same size while it fills in (align="left" pins the content to the top-left corner)."""
    w = max(min_w, content.width + 2 * pad)
    p = panel(w, max(min_h, content.height + 2 * pad), tone)
    p.alpha_composite(content, (pad if align == "left" else (w - content.width) // 2, pad))
    return p
