"""Explainer boards: graphics that build up in sync with what's said. Each one is drawn for a moment in time from a
few settings, so a clip script stays a pure draw(t).

  list_board(title, items, shown)         a list whose items appear as they're said (shown: 0..1 per item)
  bar_chart(title, bars, grown)           bars that grow when their number is spoken (bars: [(label, value)]);
                                          one bar is a big number counting up (counter)
  versus_board(left, right, nl, nr, kl, kr)  two sides as crowds of plain figures that fill in
  when_said(edit, word, after=0.0)        output time of the first word starting like `word` (to time the boards)

  place_board(c, board, face, alpha)      over the video, off the face: one spot per clip, kept

Boards stay under CAPTION_W wide."""
import functools
import math
import re
import unicodedata

from PIL import Image, ImageDraw

from .brand import BOARD_BOTTOM, CAPTION_W, SAFE_TOP
from .draw import back_out, clamp01, ease_out, place, text_block, text_line
from .project import ACCENT, F_BLACK, F_BOLD, F_MONO_B, F_XBOLD, ON_ACCENT, TEXT, W
from .video import face_rect
from .style import GAP, GREY, LINE, PAD, U, on_panel, vstack


def _norm(t):
    t = "".join(ch for ch in unicodedata.normalize("NFD", t.lower()) if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", t)


def when_said(edit, word, after=0.0, default=None):
    """output time of the first word (from `after` on) that starts like `word`'s first word; default if never said"""
    target = _norm((word or "").split()[0]) if (word or "").split() else ""
    if not target:
        return default
    for w in edit.words():
        n = _norm(w["t"])
        if w["s"] >= after and n and (n.startswith(target[:max(4, len(target) - 2)]) or target.startswith(n) and len(n) >= 4):
            return w["s"]
    return default


def timeline(edit, words, start=0.4, spread=None):
    """a time for each trigger word, in order: when it's said, else evenly spaced after the previous one"""
    spread = spread or max(1.0, (edit.dur - start - 2) / max(1, len(words)))
    out, t = [], start
    for w in words:
        t = when_said(edit, w, t, None) or t + spread
        out.append(t)
    return out


_SPOTS = {}
FACE_GAP = 40  # px between a board and the face it avoids


def place_board(c, b, face, alpha=1.0, key="board"):
    """Put a board over the video without covering the face, the way the headline is placed: just above the
    captions if it fits under the chin, else above the head, else in the bigger of the two, scaled down to fit. The
    spot is decided the first time the board is drawn and kept, so it never moves (one key per board)."""
    if alpha <= 0:
        return
    if key not in _SPOTS:
        x0, y0, x1, y1 = face_rect(face)
        h = b.height
        below, above = BOARD_BOTTOM - (y1 + FACE_GAP), (y0 - FACE_GAP) - SAFE_TOP
        if below >= 0.8 * h or (below >= above and above < 0.8 * h):
            s = max(0.7, min(1.0, below / h))
            y = BOARD_BOTTOM - h * s / 2
        else:
            s = max(0.7, min(1.0, above / h))
            y = SAFE_TOP + h * s / 2
        _SPOTS[key] = (y, s)
    y, s = _SPOTS[key]
    place(c, b, W / 2, y, s, alpha)


# ---- the list

@functools.lru_cache(256)
def _item(label, size, k):
    dot = Image.new("RGBA", (size // 2, size // 2))
    ImageDraw.Draw(dot).rounded_rectangle((0, 0, dot.width - 1, dot.height - 1), size // 10, fill=tuple(ACCENT) + (255,))
    t = text_block(label, F_BOLD, size, TEXT, max_w=CAPTION_W - 2 * PAD - size, align="left", leading=1.1)
    out = Image.new("RGBA", (dot.width + GAP + t.width, max(t.height, dot.height)))
    out.alpha_composite(dot, (0, (int(size * 1.2) - dot.height) // 2))
    out.alpha_composite(t, (dot.width + GAP, 0))
    a = ease_out(k)
    if a < 1:
        out.putalpha(out.split()[3].point(lambda v: int(v * a)))
    return out


def list_board(title, items, shown, size=50):
    """a card with a title and the items that have been said so far (shown[i]: 0 hidden .. 1 in)"""
    parts = [text_line(title, F_MONO_B, int(size * 0.62), GREY)] if title else []
    width = max([_item(it, size, 1.0).width for it in items] + [parts[0].width if parts else 0])
    for it, k in zip(items, shown):
        if k <= 0:
            parts.append(Image.new("RGBA", (1, _item(it, size, 1.0).height)))  # the card keeps its size
            continue
        im = _item(it, size, round(clamp01(k), 2))
        slide = Image.new("RGBA", (im.width + 3 * U, im.height))
        slide.alpha_composite(im, (int(3 * U * (1 - ease_out(clamp01(k)))), 0))
        parts.append(slide)
    return on_panel(vstack(parts, GAP), min_w=width + 2 * PAD + 3 * U, align="left")


# ---- the chart

def _fmt(v):
    return f"{v:,.0f}".replace(",", " ") if abs(v) >= 1000 else (f"{v:g}" if v != int(v) else str(int(v)))


def counter(title, label, value, k, unit="", size=150):
    """one big number counting up to value as k goes 0 -> 1, its label under it (a chart with one bar)"""
    k = clamp01(k)
    num = text_line(_fmt(value * ease_out(k)) + unit, F_BLACK, size, ACCENT)
    full = text_line(_fmt(value) + unit, F_BLACK, size, ACCENT)  # the card keeps its final size while it counts
    box = Image.new("RGBA", (full.width, full.height))
    box.alpha_composite(num, ((full.width - num.width) // 2, 0))
    parts = ([text_line(title, F_MONO_B, int(size * 0.2), GREY)] if title else []) + [box]
    if label:
        parts.append(text_block(label, F_BOLD, int(size * 0.32), TEXT, max_w=CAPTION_W - 2 * PAD, leading=1.05))
    return on_panel(vstack(parts, GAP, "center"))


def bar_chart(title, bars, grown, unit="", size=40, height=320):
    """vertical bars on a card; bar i grows to its value as grown[i] goes 0 -> 1 (the biggest in the accent colour).
    One bar is drawn as a big number counting up instead (counter())."""
    if len(bars) == 1:
        return counter(title, bars[0][0], bars[0][1], grown[0] if grown else 1.0, unit)
    n = max(1, len(bars))
    w = min(CAPTION_W, 140 + n * 170)
    plot_w, plot_h = w - 2 * PAD, height
    im = Image.new("RGBA", (plot_w, plot_h + int(size * 2.6)))
    d = ImageDraw.Draw(im)
    top = max([abs(v) for _, v in bars] + [1e-9])
    slot = plot_w / n
    bw = slot * 0.56
    d.line((0, plot_h, plot_w, plot_h), fill=LINE + (255,), width=3)
    biggest = max(range(n), key=lambda i: bars[i][1]) if bars else -1
    for i, ((label, value), k) in enumerate(zip(bars, grown)):
        k = clamp01(k)
        x0 = slot * i + (slot - bw) / 2
        h = (plot_h - size * 1.6) * abs(value) / top * back_out(k, 1.2) if k > 0 else 0
        col = ACCENT if i == biggest else (200, 200, 205)
        if h > 1:
            d.rounded_rectangle((x0, plot_h - h, x0 + bw, plot_h - 2), 8, fill=tuple(col) + (255,))
        if k > 0.4:
            v = text_line(_fmt(value * min(1.0, k / 0.8)) + unit, F_BLACK, size, TEXT)
            im.alpha_composite(v, (int(x0 + bw / 2 - v.width / 2), int(plot_h - h - v.height - 8)))
        lab = text_block(label, F_BOLD, int(size * 0.7), TEXT, max_w=int(slot - 8), leading=1.0)
        im.alpha_composite(lab, (int(x0 + bw / 2 - lab.width / 2), plot_h + 14))
    parts = ([text_line(title, F_MONO_B, int(size * 0.75), GREY)] if title else []) + [im]
    return on_panel(vstack(parts, GAP), align="left")


# ---- versus: two crowds

@functools.lru_cache(8)
def _figure(h, color):
    """a plain little person: a head and a rounded body"""
    w = int(h * 0.62)
    im = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(im)
    r = h * 0.2
    d.ellipse((w / 2 - r, 0, w / 2 + r, 2 * r), fill=tuple(color[:3]) + (255,))
    d.rounded_rectangle((0, 2 * r + h * 0.06, w - 1, h - 1), int(w * 0.38), fill=tuple(color[:3]) + (255,))
    return im


def _crowd(n, k, color, width, fig_h):
    n = max(1, n)
    cols = max(1, min(n, int(width // (fig_h * 0.62 + 6))))
    rows = math.ceil(n / cols)
    f = _figure(fig_h, color)
    im = Image.new("RGBA", (int(cols * (f.width + 6)), int(rows * (fig_h + 8))))
    shown = int(round(n * clamp01(k)))
    for i in range(shown):
        im.alpha_composite(f, (int((i % cols) * (f.width + 6)), int((i // cols) * (fig_h + 8))))
    return im


def versus_board(left, right, nl, nr, kl, kr, size=60, figures_max=60):
    """two columns, a "vs" between them: a name over a crowd of nl / nr plain figures each (more than figures_max
    are drawn as figures_max, the real number under the name), filling in as kl / kr go 0 -> 1"""
    vs = text_line("vs", F_BLACK, int(size * 0.75), GREY)
    col_w = (CAPTION_W - 2 * PAD - vs.width - 4 * GAP) // 2
    sides = []
    for name, n, k, color in ((left, nl, kl, (200, 200, 205)), (right, nr, kr, ACCENT)):
        drawn = min(n, figures_max)
        fig_h = 120 if drawn <= 3 else 92 if drawn <= 6 else 60 if drawn <= 16 else 40 if drawn <= 36 else 30
        head = text_block(name, F_XBOLD, size, TEXT, max_w=col_w, leading=1.05)
        count = text_line(_fmt(n), F_MONO_B, int(size * 0.55), GREY)
        crowd = _crowd(drawn, 1.0, color, col_w, fig_h)  # full size, so the column never changes size as it fills
        shown = _crowd(drawn, k, color, col_w, fig_h)
        sides.append((vstack([head, count, crowd], U * 2, "center"), shown, head.height + count.height + 4 * U))
    h = max(c.height for c, _, _ in sides)
    im = Image.new("RGBA", (CAPTION_W - 2 * PAD, h))
    for (col, shown, top), x in ((sides[0], 0), (sides[1], im.width - col_w)):
        blank = Image.new("RGBA", col.size)
        blank.alpha_composite(col.crop((0, 0, col.width, top)), (0, 0))  # name and count, then the crowd as it is now
        blank.alpha_composite(shown, ((col.width - shown.width) // 2, top))
        im.alpha_composite(blank, (x + (col_w - col.width) // 2, 0))
    im.alpha_composite(vs, ((im.width - vs.width) // 2, int(size * 0.2)))
    return on_panel(im)
