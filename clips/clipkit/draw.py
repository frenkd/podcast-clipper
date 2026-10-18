"""Drawing: text (with emoji), cards, easing, and place() which also feeds the automatic QA."""
import functools, os, re, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import state
from .project import ASSETS, F_EMOJI, F_FALLBACK, H, W

MARGIN = 16  # px: content closer than this to the edge of its card reads as cramped (QA: TIGHT)


# ---- easing (x: 0..1 progress; values outside are clamped)
def clamp01(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def ease_out(x):
    return 1 - (1 - clamp01(x)) ** 3


def ease_in_out(x):
    x = clamp01(x)
    return 3 * x * x - 2 * x * x * x


def back_out(x, s=1.9):
    x = clamp01(x) - 1
    return x * x * ((s + 1) * x + s) + 1


def pop(t, t0, d=0.22):
    """small scale-in for something that appears at t0 (no idle motion afterwards)"""
    return 0.9 + 0.1 * back_out((t - t0) / d)


# ---- text
EMOJI_RE = re.compile("([\U0001F000-\U0001FAFF☀-➿⭐⬆↔-⇿\U0001F1E6-\U0001F1FF]+️?)")


@functools.lru_cache(None)
def font(path, size, index=0):
    return ImageFont.truetype(path, size, index=index)


@functools.lru_cache(None)
def emoji(ch, size):
    """a colour emoji (Apple's; Segoe or Noto elsewhere) as an RGBA image about `size` px tall; blank if there's no
    emoji font"""
    if F_EMOJI is None:
        return Image.new("RGBA", (size, size))
    for px in (160, 109):  # bitmap emoji fonts only come in fixed sizes (Noto: 109)
        try:
            f = font(F_EMOJI, px)
            break
        except OSError:
            continue
    else:
        return Image.new("RGBA", (size, size))
    im = Image.new("RGBA", (220, 220))
    ImageDraw.Draw(im).text((10, 10), ch, font=f, embedded_color=True)
    im = im.crop(im.getbbox() or (0, 0, 1, 1))
    s = size / 150 * 160 / px
    return im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)


def _split_emoji(text, fpath=None, findex=0):
    """("e", emoji) / ("t", text) parts; symbols the font itself has (✓ ✗ ★ in JetBrains Mono) stay text"""
    out = []
    for part in EMOJI_RE.split(text):
        if part and EMOJI_RE.fullmatch(part) and fpath and all(has_glyph(fpath, c, findex) for c in part.replace("️", "")):
            out.append(("t", part.replace("️", "")))
        elif part and EMOJI_RE.fullmatch(part):
            out += [("e", c) for c in re.findall("[\U0001F1E6-\U0001F1FF]{2}|.", part.replace("️", ""))]
        elif part:
            out.append(("t", part))
    return out


@functools.lru_cache(None)
def has_glyph(fpath, ch, findex=0):
    """does the font draw ch (not its empty / .notdef box)? Our brand fonts are subsets: ✓ ✗ ₂ → … may be missing"""
    if ch.isspace():
        return True
    f = font(fpath, 40, findex)
    m = f.getmask(ch)
    return m.getbbox() is not None and bytes(m) != bytes(f.getmask("\U000F0000"))


def _split_glyphs(s, fpath, findex):
    """runs of (has the glyph, text)"""
    out = []
    for ch in s:
        ok = has_glyph(fpath, ch, findex)
        if out and out[-1][0] == ok:
            out[-1][1] += ch
        else:
            out.append([ok, ch])
    return out


@functools.lru_cache(4096)
def text_line(text, fpath, size, fill=(255, 255, 255), stroke=0, stroke_fill=(0, 0, 0), findex=0):
    """one line of text (emoji allowed) as a tight RGBA image"""
    f = font(fpath, size, findex)
    fb = font(F_FALLBACK, size)
    asc, desc = f.getmetrics()
    parts = []
    for kind, s in _split_emoji(text, fpath, findex):
        if kind == "e":
            e = emoji(s, int(size * 0.92))
            if e.size != (1, 1):  # Apple has no colour emoji for plain symbols like ✓: draw those as text
                parts.append(e)
                continue
        runs = _split_glyphs(s, fpath, findex)
        im = Image.new("RGBA", (max(1, int(sum((f if ok else fb).getlength(r) for ok, r in runs)) + stroke * 2 + 2),
                                asc + desc + stroke * 2))
        d, x = ImageDraw.Draw(im), stroke + 1
        for ok, r in runs:  # characters the font lacks come from a system font instead of vanishing
            ff = f if ok else fb
            d.text((x, stroke + (0 if ok else asc - fb.getmetrics()[0])), r, font=ff, fill=fill, stroke_width=stroke,
                   stroke_fill=stroke_fill)
            x += ff.getlength(r)
        parts.append(im)
    if not parts:
        return Image.new("RGBA", (1, 1))
    hh = max(p.height for p in parts)
    gap = int(size * 0.12)
    out = Image.new("RGBA", (sum(p.width for p in parts) + gap * (len(parts) - 1), hh))
    x = 0
    for p in parts:
        out.alpha_composite(p, (x, (hh - p.height) // 2))
        x += p.width + gap
    return out


def _wrap(text, fpath, size, max_w, stroke=0):
    lines, cur = [], ""
    for w in text.split(" "):
        cand = (cur + " " + w).strip()
        if cur and text_line(cand, fpath, size, stroke=stroke).width > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    return lines + ([cur] if cur else [])


def text_block(text, fpath, size, fill=(255, 255, 255), stroke=0, stroke_fill=(0, 0, 0), max_w=None,
               align="center", leading=1.05, shadow=None, findex=0):
    """multi-line text: '\\n' breaks lines, max_w wraps; shadow=(radius, alpha, (dx, dy))"""
    if not text.strip():
        return Image.new("RGBA", (1, int(size * 1.2)))
    lines = []
    for para in text.split("\n"):
        lines += _wrap(para, fpath, size, max_w, stroke) if max_w else [para]
    ims = [text_line(l, fpath, size, fill, stroke, stroke_fill, findex) for l in lines]
    lh = int(size * leading)
    w = max(i.width for i in ims)
    out = Image.new("RGBA", (w, lh * (len(ims) - 1) + ims[-1].height))
    for k, i in enumerate(ims):
        x = 0 if align == "left" else (w - i.width) // 2 if align == "center" else w - i.width
        out.alpha_composite(i, (x, k * lh))
    return with_shadow(out, *shadow) if shadow else out


def with_shadow(im, radius=12, alpha=0.6, off=(0, 6)):
    pad = radius * 2
    sh = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2))
    blk = Image.new("RGBA", im.size, (0, 0, 0, 255))
    blk.putalpha(im.split()[3].point(lambda v: int(v * alpha)))
    sh.alpha_composite(blk, (pad + off[0], pad + off[1]))
    sh = sh.filter(ImageFilter.GaussianBlur(radius))
    sh.alpha_composite(im, (pad, pad))
    return sh


def rounded(w, h, r, fill, outline=None, width=0):
    im = Image.new("RGBA", (w, h))
    ImageDraw.Draw(im).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=fill, outline=outline, width=width)
    return im


def boxed(im, pad=(28, 16), r=18, fill=(0, 0, 0, 230), outline=None, width=0):
    """im on a rounded card with padding"""
    b = rounded(im.width + pad[0] * 2, im.height + pad[1] * 2, r, fill, outline, width)
    b.alpha_composite(im, (pad[0], pad[1]))
    return b


@functools.lru_cache(None)
def asset(name, width=None, height=None):
    """an image from assets/, resized by width or height"""
    im = Image.open(os.path.join(ASSETS, name)).convert("RGBA")
    if width:
        return im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
    if height:
        return im.resize((int(im.width * height / im.height), height), Image.LANCZOS)
    return im


# ---- placing things (and recording them for QA)
def place(canvas, im, cx, cy, scale=1.0, alpha=1.0, rot=0.0, anchor="c", on_face=False, clip_ok=False, over=False,
          ui_frac=0.12):
    """Paste im on canvas at (cx, cy) with scale / alpha / rotation. anchor: c (centre), tl, tc, bc.
    Feeds the automatic QA (boxes are measured on the visible pixels, not the image's transparent margin):
    on the 1080x1920 canvas anything covering the face, and elements overlapping each other; on a smaller image (a
    card) anything drawn past its edge, or closer to the edge than MARGIN (cramped). Deliberate exceptions:
    on_face=True (sunglasses on the face), clip_ok=True (old chat lines scrolling away), over=True (a stamp or badge
    meant to sit on top of something). ui_frac: how much of it may sit under an app's top/bottom bar before QA says
    UNDER APP UI (captions allow their second line there)."""
    if im is None or alpha <= 0.01 or scale <= 0.01:
        return
    if abs(scale - 1) > 0.005:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BILINEAR)
    if abs(rot) > 0.05:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    if alpha < 0.999:
        im = im.copy()
        im.putalpha(im.split()[3].point(lambda v: int(v * alpha)))
    x, y = {"c": (cx - im.width / 2, cy - im.height / 2), "tl": (cx, cy), "tc": (cx - im.width / 2, cy),
            "bc": (cx - im.width / 2, cy - im.height)}[anchor]
    x, y = int(x), int(y)
    inside = x >= 0 and y >= 0 and x + im.width <= canvas.width and y + im.height <= canvas.height
    if inside:
        canvas.alpha_composite(im, (x, y))
    else:
        l, t = max(0, -x), max(0, -y)
        r, b = min(im.width, canvas.width - x), min(im.height, canvas.height - y)
        if r > l and b > t:
            canvas.alpha_composite(im.crop((l, t, r, b)), (x + l, y + t))
    if state.QA is None:
        return
    bb = im.split()[3].point(lambda v: 255 if v > 40 else 0).getbbox() if im.mode == "RGBA" else (0, 0, im.width, im.height)
    if not bb:
        return
    x0, y0, x1, y1 = x + bb[0], y + bb[1], x + bb[2], y + bb[3]
    if canvas.size == (W, H):
        if alpha > 0.3 and (x1 - x0) * (y1 - y0) < W * H * 0.5:
            who = _caller()
            if not on_face:
                state.QA["boxes"].append((x0, y0, x1, y1, who, ui_frac))
            if not over:
                state.QA["items"].append((x0, y0, x1, y1, who))
    else:
        cw, ch = canvas.size
        if (x0 < -2 or y0 < -2 or x1 > cw + 2 or y1 > ch + 2) and not clip_ok:
            state.QA["clips"].add(_caller())
        elif not clip_ok and not over and (x1 - x0) < 0.9 * cw and (y1 - y0) < 0.9 * ch and _is_card(canvas):
            if any(0 < g < MARGIN for g in (x0, y0, cw - x1, ch - y1)):
                state.QA["tight"].add(_caller())


def _is_card(im):
    """a surface with a visible background at its edges (a card), not a transparent layout strip"""
    if im.mode != "RGBA":
        return True
    w, h = im.size
    a = im.split()[3]
    edges = (a.getpixel((w // 2, min(h - 1, 3))), a.getpixel((w // 2, max(0, h - 4))),
             a.getpixel((min(w - 1, 3), h // 2)), a.getpixel((max(0, w - 4), h // 2)))
    return sum(v >= 128 for v in edges) >= 3


def _caller():
    """file:line of the clip script that called into the engine"""
    here = os.path.dirname(os.path.abspath(__file__))
    f = sys._getframe(2)
    while f and os.path.dirname(os.path.abspath(f.f_code.co_filename)) == here:
        f = f.f_back
    return f"{os.path.basename(f.f_code.co_filename)}:{f.f_lineno} ({f.f_code.co_name})" if f else "?"
