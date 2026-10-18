"""Motion and effects for the louder end of the range: zoom punches, shakes, slow push-ins, mono and deep-fried looks,
flashes, meme captions and stickers. All are plain functions of time, so a clip stays a pure draw(t) and renders the
same every time.

  zoom = 1.1 * punch(t, BEATS) * push(t, 20, 23, 1.0, 1.3)       crop(fr, face, W, H, zoom=zoom, dx=sx, dy=sy)
  sx, sy = shake(t, DROP_T)                                     a hit that settles
  c = mono(c, k); c = deep_fry(c, k); flash(c, t, DROP_T)       looks for a beat (k: 0..1)
  place(c, meme_text("SIGMA RULE #47"), W / 2, 400, pop(t, T))  the classic white-caps-black-stroke line
  place(c, sticker("NO WAY"), x, y, pop(t, T), rot=-8)          a tilted label
  zoom *= snap(t, PUNCH_T); red_vignette(c)                     the dramatic zoom on the punchline
  c = faded(c); place(c, credits_card("Directed by", "…"), …)   the "directed by" ending

Use them on purpose: one drop per clip reads as a joke, five read as noise."""
import functools, io, math
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from . import state
from .draw import back_out, clamp01, ease_in_out, ease_out, text_block, text_line
from .project import ACCENT, F_BLACK, H, INK, ON_ACCENT, W
from .style import radial


# ---- camera moves: multiply or add these into crop()'s zoom / dx / dy

def deliberate(t0, t1):
    """tell QA the framing moves on purpose between t0 and t1 (the moves below do it themselves)"""
    state.MOVES.add((round(t0 - 0.05, 2), round(t1 + 0.05, 2)))


def punch(t, beats, amount=0.09, d=0.28):
    """zoom factor that kicks in by `amount` at each time in `beats` and eases back over d seconds"""
    z = 1.0
    for b in beats:
        deliberate(b, b + d)
        k = (t - b) / d
        if 0 <= k < 1:
            z = max(z, 1 + amount * (1 - ease_out(k)))
    return z


def push(t, t0, t1, z0=1.0, z1=1.25):
    """a slow push-in (or pull-out with z1 < z0) between t0 and t1, holding after"""
    return z0 + (z1 - z0) * ease_in_out(clamp01((t - t0) / max(1e-6, t1 - t0)))


def shake(t, t0, d=0.4, amp=0.025, seed=0):
    """(dx, dy) of a hit at t0 that settles over d seconds, as fractions of the picture (what crop()'s dx/dy take):
    amp 0.025 moves the frame by up to 2.5 %"""
    deliberate(t0, t0 + d)
    k = (t - t0) / d
    if k < 0 or k >= 1:
        return 0.0, 0.0
    e = (1 - k) ** 2 * amp
    r = np.random.default_rng(seed + int(t * 60))
    return float(r.uniform(-1, 1) * e), float(r.uniform(-1, 1) * e)


# ---- looks: full-frame treatments, k blends from none (0) to full (1)

def mono(im, k=1.0, contrast=1.25):
    """black and white with a bit more contrast (the "it's over" / flashback look)"""
    k = clamp01(k)
    if k <= 0:
        return im
    im = im.convert("RGBA")
    g = ImageEnhance.Contrast(im.convert("L").convert("RGBA")).enhance(contrast)
    g.putalpha(im.split()[3])
    return Image.blend(im, g, k)


def deep_fry(im, k=1.0, seed=0):
    """the deep-fried meme look: crushed JPEG, blown-out saturation and contrast, oversharpened, a warm cast"""
    k = clamp01(k)
    if k <= 0:
        return im
    rgb = im.convert("RGB")
    fried = ImageEnhance.Color(rgb).enhance(1 + 2.2 * k)
    fried = ImageEnhance.Contrast(fried).enhance(1 + 0.8 * k)
    fried = fried.filter(ImageFilter.UnsharpMask(radius=2, percent=int(250 * k), threshold=0))
    small = fried.resize((W // 3, H // 3), Image.BILINEAR)
    buf = io.BytesIO()
    small.save(buf, "JPEG", quality=max(4, int(40 - 34 * k)))
    fried = Image.open(io.BytesIO(buf.getvalue())).convert("RGB").resize(rgb.size, Image.NEAREST)
    warm = Image.new("RGB", rgb.size, (255, 120, 0))
    fried = Image.blend(fried, warm, 0.08 * k)
    out = Image.blend(rgb, fried, k).convert("RGBA")
    return out


@functools.lru_cache(4)
def _vignette(strength):
    return radial(W, H, 0.0, strength)


def vignette(c, strength=0.75):
    """dark corners on canvas c (in place)"""
    c.alpha_composite(_vignette(round(strength, 2)))
    return c


def flash(c, t, t0, d=0.16, color=(255, 255, 255)):
    """a flash at t0 that fades over d seconds (in place)"""
    k = (t - t0) / d
    if 0 <= k < 1:
        c.alpha_composite(Image.new("RGBA", c.size, tuple(color[:3]) + (int(230 * (1 - k)),)))
    return c


def letterbox(c, k=1.0, bar=220):
    """cinematic black bars sliding in from top and bottom (in place)"""
    h = int(bar * ease_out(clamp01(k)))
    if h > 0:
        d = ImageDraw.Draw(c)
        d.rectangle((0, 0, W, h), fill=INK + (255,))
        d.rectangle((0, H - h, W, H), fill=INK + (255,))
    return c


# ---- text for the loud formats

@functools.lru_cache(256)
def meme_text(text, size=110, max_w=940, color=(255, 255, 255), stroke=None):
    """the classic meme line: heavy caps, white, thick black outline"""
    return text_block(text.upper(), F_BLACK, size, color, max_w=max_w, leading=1.02, align="center",
                      stroke=stroke or max(6, size // 10))


@functools.lru_cache(256)
def sticker(text, size=64, fill=None, color=None, border=(255, 255, 255)):
    """a tilted-label sticker: a solid plate in the accent colour, a white border, a hard drop shadow
    (rotate it with place(..., rot=-8))"""
    fill = fill or ACCENT
    t = text_line(text.upper(), F_BLACK, size, color or ON_ACCENT)
    px, py, b = int(size * 0.45), int(size * 0.22), max(5, size // 9)
    w, h = t.width + 2 * px + 2 * b, t.height + 2 * py + 2 * b
    out = Image.new("RGBA", (w + 14, h + 14))
    d = ImageDraw.Draw(out)
    d.rounded_rectangle((14, 14, w + 13, h + 13), 12, fill=(0, 0, 0, 200))
    d.rounded_rectangle((0, 0, w - 1, h - 1), 12, fill=tuple(border[:3]) + (255,))
    d.rounded_rectangle((b, b, w - 1 - b, h - 1 - b), 8, fill=tuple(fill[:3]) + (255,))
    out.alpha_composite(t, (b + px, b + py))
    return out


def wobble(t, t0, amp=4.0, hz=1.3):
    """a gentle rotation in degrees for a sticker that's been up since t0 (alive, not bouncing)"""
    return amp * math.sin(2 * math.pi * hz * max(0.0, t - t0))


def slam(t, t0, d=0.22, big=1.8):
    """scale for text that slams in at t0: starts big, lands at 1 with a small overshoot"""
    k = clamp01((t - t0) / d)
    return big - (big - 1) * back_out(k, 1.4)


def faded(im, k=1.0, seed=0):
    """a warm, faded film look (the freeze frame before the credits, the documentary grade): softer contrast and
    colour, a sepia cast, some grain. k: 0..1. Colour, contrast and tint are one 3x4 matrix (cv2.transform) and the
    grain is two saturating adds, so it costs a few ms a frame."""
    import cv2
    k = clamp01(k)
    if k <= 0:
        return im
    a = np.asarray(im.convert("RGB"))
    s_, c_ = 0.55 * k, 1 - 0.15 * k                                   # how much colour goes, contrast kept
    lum = np.array([0.299, 0.587, 0.114], np.float32)
    m = (1 - s_) * np.eye(3, dtype=np.float32) + s_ * np.tile(lum, (3, 1))
    tint = 1 + k * np.array([0.06, -0.02, -0.16], np.float32)
    M = np.zeros((3, 4), np.float32)
    M[:, :3] = (tint[:, None] * c_) * m
    M[:, 3] = tint * 128 * (1 - c_) + k * np.array([14, 8, 0], np.float32)
    x = cv2.transform(a, M)
    up, down = _grain(a.shape[0], a.shape[1], seed % 6, round(k, 1))
    x = cv2.subtract(cv2.add(x, up), down)
    out = Image.fromarray(x).convert("RGBA")
    if im.mode == "RGBA":
        out.putalpha(im.split()[3])
    return out


@functools.lru_cache(24)
def _grain(h, w, i, k=1.0):
    """six pre-made film-grain frames as (add, subtract) uint8 planes (a fresh one per frame was most of the cost)"""
    g = np.random.default_rng(100 + i).normal(0, 7 * k, (h, w)).astype(np.float32)
    up = np.clip(g, 0, 255).astype(np.uint8)
    down = np.clip(-g, 0, 255).astype(np.uint8)
    return np.dstack([up] * 3), np.dstack([down] * 3)


@functools.lru_cache(64)
def credits_card(small, big, size=64):
    """the "directed by" card: a small line over a big name, plain white, centred"""
    from .project import F_BOLD, F_REG
    top = text_line(small, F_REG, int(size * 0.62), (255, 255, 255), 4)
    name = text_block(big.upper(), F_BOLD, size, (255, 255, 255), max_w=900, leading=1.05, stroke=4)
    out = Image.new("RGBA", (max(top.width, name.width), top.height + int(size * 0.35) + name.height))
    out.alpha_composite(top, ((out.width - top.width) // 2, 0))
    out.alpha_composite(name, ((out.width - name.width) // 2, top.height + int(size * 0.35)))
    return out


@functools.lru_cache(8)
def _red(strength):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / math.sqrt(2)
    a = np.clip((r - 0.35) / 0.65, 0, 1) ** 1.6 * strength * 255  # only the edges: the face stays clear
    arr = np.zeros((H, W, 4), np.uint8)
    arr[..., 0], arr[..., 3] = 120, np.clip(a, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def red_vignette(c, strength=0.7):
    """red-tinted dark corners for the dramatic zoom (in place)"""
    c.alpha_composite(_red(round(strength, 2)))
    return c


def snap(t, t0, z0=1.0, z1=1.9, d=0.12):
    """the dramatic zoom: from z0 to z1 in d seconds at t0, then holding (multiply into crop()'s zoom)"""
    deliberate(t0, t0 + d)
    return z0 + (z1 - z0) * ease_out(clamp01((t - t0) / d))


# ---- documentary, news, rewind

def typed(text, k):
    """the first part of text, as if typed out (k: 0..1)"""
    return text[:int(round(len(text) * clamp01(k)))]


@functools.lru_cache(128)
def doc_card(top, line, size=60):
    """a documentary caption: a small spaced-out label over a quiet serif-less line, left-aligned, no box"""
    from .project import F_MED, F_MONO_B
    a = text_line(top.upper(), F_MONO_B, int(size * 0.7), (230, 225, 210), 3)
    b = text_block(line, F_MED, size, (255, 255, 255), max_w=860, align="left", leading=1.15, stroke=3) if line else None
    w = max(a.width, b.width if b else 0)
    out = Image.new("RGBA", (w, a.height + (int(size * 0.35) + b.height if b else 0)))
    out.alpha_composite(a, (0, 0))
    if b:
        out.alpha_composite(b, (0, a.height + int(size * 0.35)))
    return out


def news_banner(c, headline, t, t0=0.3, label="BREAKING", y=None, red=(205, 25, 30)):
    """the breaking-news lower third (in place): a red label tab and a white bar with the headline, sliding in"""
    from .project import F_BLACK, F_XBOLD
    k = ease_out(clamp01((t - t0) / 0.35))
    if k <= 0:
        return c
    y = y or int(H * 0.60)
    lab = text_line(label, F_BLACK, 44, (255, 255, 255))
    head = text_block(headline.upper(), F_XBOLD, 46, (14, 14, 16), max_w=W - 120, align="left", leading=1.05)
    bar_h = head.height + 36
    d = ImageDraw.Draw(c)
    x0 = int(-W * (1 - k))
    d.rectangle((x0, y, x0 + lab.width + 48, y + lab.height + 24), fill=red + (255,))
    c.alpha_composite(lab, (x0 + 24, y + 12))
    d.rectangle((x0, y + lab.height + 24, x0 + W, y + lab.height + 24 + bar_h), fill=(250, 250, 250, 255))
    c.alpha_composite(head, (x0 + 28, y + lab.height + 24 + 18))
    return c


def ticker(c, items, t, y=None, speed=180, t0=0.6):
    """a scrolling news ticker along the bottom of the banner (in place): items separated by blocks"""
    if t < t0 or not items:
        return c
    y = y or int(H * 0.60) + 230
    strip = _ticker_strip(tuple(items))
    h = strip.height + 16
    ImageDraw.Draw(c).rectangle((0, y, W, y + h), fill=(14, 14, 16, 235))
    off = int((t - t0) * speed) % strip.width
    for x in (-off, strip.width - off):
        if x < W:
            c.alpha_composite(strip.crop((max(0, -x), 0, min(strip.width, W - x), strip.height)), (max(0, x), y + 8))
    return c


@functools.lru_cache(16)
def _ticker_strip(items):
    from .project import F_BOLD
    parts = []
    for it in items:
        parts += [text_line(it.upper(), F_BOLD, 34, (255, 255, 255)), Image.new("RGBA", (60, 1))]
    w = sum(p.width for p in parts)
    out = Image.new("RGBA", (max(W, w), max(p.height for p in parts)))
    x = 0
    for p in parts:
        if p.height > 1:
            out.alpha_composite(p, (x, 0))
            ImageDraw.Draw(out).rectangle((x + p.width + 22, out.height // 2 - 6, x + p.width + 34, out.height // 2 + 6),
                                          fill=(205, 25, 30, 255))
        x += p.width
    return out


def vhs(im, k=1.0, seed=0, osd=None):
    """a VHS look: soft, colour fringes, scanlines, a rolling noise band, and an on-screen label like "◀◀ REWIND"
    (k: strength 0..1)"""
    from .project import F_MONO_B
    k = clamp01(k)
    rgb = im.convert("RGB")
    small = rgb.resize((W // 3, H // 3), Image.BILINEAR).resize(rgb.size, Image.BILINEAR)
    a = np.asarray(small).astype(np.int16)
    s = int(10 * k)
    if s:
        a[:, s:, 0] = a[:, :-s, 0]
        a[:, :-s, 2] = a[:, s:, 2]
    a[::4] = (a[::4] * (1 - 0.25 * k)).astype(np.int16)
    rng = np.random.default_rng(seed)
    y = int(rng.integers(0, H - 80))
    a[y:y + 60] = np.clip(a[y:y + 60] + rng.normal(0, 60 * k, (60, W, 1)), 0, 255).astype(np.int16)
    out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGBA")
    if osd:
        lab = text_line(osd, F_MONO_B, 64, (255, 255, 255), 4)
        out.alpha_composite(lab, (70, 300))
    return out
