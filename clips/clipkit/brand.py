"""The frame of every clip: the opening headline (with the accent bar), captions (the spoken word in the accent
colour) and the end card. Colours, fonts, logo and the end card's text come from the theme (theme.py)."""
import functools
import re
from PIL import Image, ImageDraw, ImageFilter

from . import state
from .draw import asset, clamp01, ease_out, place, text_block, text_line
from .project import ACCENT, EPISODE, EPISODE_TITLE, F_BLACK, F_MONO, F_MONO_B, F_XBOLD, GUEST, H, LAYOUT, ON_ACCENT, TEXT, THEME, W
from .style import GAP, MUTED, bar, fade_in, tag
from .video import BAND, face_out, face_rect
from .words import active, clean_word

from .safezones import PLATFORMS, PRIMARY, safe_box, safe_width
SAFE_TOP = safe_box()[1]           # below every primary app's top bar (safezones.py)
CAPTION_Y = 1400                   # captions centred here, clear of the apps' caption/username block at the bottom,
CAPTION_TOP = CAPTION_Y - 120      # taking up to two lines from here down,
CAPTION_W = safe_width(1300, 1500) # and narrow enough to stay off the like/comment rail
HOOK_TEXT_W = CAPTION_W - 170      # headline text width when it sits low: the whole headline is then CAPTION_W wide
RAIL_TOP = min(PLATFORMS[p]["rail"][1] for p in PRIMARY)   # the apps' right-hand buttons start here
HOOK_PAD = 40                      # transparent margin around brand_hook() (room for its soft shade)
CAPTION_DROP = 90                  # how far captions move down while a board shares the screen (captions(split=1))
BOARD_TOP = BAND + 24              # split layout: boards go from here down to BOARD_BOTTOM
BOARD_BOTTOM = CAPTION_TOP + CAPTION_DROP - 24   # (overlay layout: boards sit on the video, bottom at BOARD_BOTTOM)


def board_y(h, layout=None):
    """centre y for a board h px tall: under the video band (split layout), or resting just above the captions on
    top of the video (overlay layout, the default: the shot stays whole and visible). layout: for this clip."""
    return BOARD_TOP + h / 2 if (layout or LAYOUT) == "split" else BOARD_BOTTOM - h / 2


def speaker():
    """the name to show for this clip: whoever speaks most in it (set by render()), else the episode's main guest"""
    return state.CLIP_SPEAKER or GUEST


def hook_speaker():
    """the name under the headline: whoever talks while it's up (the person on screen), else speaker()"""
    return state.HOOK_SPEAKER or speaker()


@functools.lru_cache(64)
def _hook_parts(text, size, who, max_w):
    parts = [text_block(text, F_XBOLD, size, TEXT, max_w=max_w, leading=1.12, align="left")]
    if who:
        parts.append(text_line(who, F_MONO_B, int(size * 0.5), ACCENT))
    return parts


def brand_hook(text, size=74, name=True, max_w=800, shade=0.45, k=1.0):
    """The opening headline: the accent bar on the left, the line beside it, who's speaking under it. Put it on
    screen with intro() (or place_hook()). k (0..1) animates the way in: the bar grows, then the text comes into
    focus. name: show who's speaking (True), a given name (str) or nothing (False)."""
    who = (hook_speaker() if name is True else name) or ""
    return _brand_hook(text, size, who, max_w, shade, round(clamp01(k), 2))


@functools.lru_cache(256)
def _brand_hook(text, size, who, max_w, shade, k):
    parts = _hook_parts(text, size, who, max_w)
    gap = int(size * 0.24)
    iw = max(p.width for p in parts)
    ih = sum(p.height for p in parts) + gap * (len(parts) - 1)
    bh = ih + int(size * 0.3)
    b = bar(bh, width=max(6, int(size * 0.11)))
    pad = int(size * 0.4)
    w = b.width + pad + iw
    P = HOOK_PAD
    out = Image.new("RGBA", (w + 2 * P, bh + 2 * P))
    if shade:
        sh = Image.new("RGBA", out.size)
        ImageDraw.Draw(sh).rounded_rectangle((P - 24, P - 16, w + P + 24, bh + P + 16), 40,
                                             fill=(0, 0, 0, int(255 * shade * ease_out(min(1.0, k / 0.4)))))
        out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(28)))
    grow = ease_out(clamp01(k / 0.35))
    if grow > 0:
        gh = max(1, int(bh * grow))
        out.alpha_composite(b.crop((0, 0, b.width, gh)), (P, P + (bh - gh) // 2))
    if k > 0.25:
        body = Image.new("RGBA", (iw, ih))
        y = 0
        for p in parts:
            body.alpha_composite(p, (0, y))
            y += p.height + gap
        out.alpha_composite(fade_in(body, clamp01((k - 0.25) / 0.75)), (P + b.width + pad, P + (bh - ih) // 2))
    return out


def _hook_slot(rects, h):
    """(y, scale, over_captions) for the headline, from the head boxes while it's up: resting just above the captions
    (the middle of the frame, where the eye already is) if it fits under the chin without shrinking much, else above
    the head, else over the chest in the caption zone (captions wait until it's gone). Never a tiny headline squeezed
    under a chin."""
    vis = h - 2 * HOOK_PAD + 40  # the soft shade reaches ~20 px past the text
    top, bot = min(r[1] for r in rects), max(r[3] for r in rects)
    head_top = top + 0.12 * sum(r[3] - r[1] for r in rects) / len(rects)  # face_rect starts a little above the hair
    above = head_top - SAFE_TOP - 16
    below = CAPTION_TOP - bot - 24
    if below >= 0.8 * vis:
        s = min(1.0, below / vis)
        return CAPTION_TOP - 24 - vis * s / 2, s, False
    if above >= 0.6 * vis:
        s = min(1.0, above / vis)
        return SAFE_TOP + 6 + vis * s / 2, s, False
    return CAPTION_Y, min(1.0, 0.92), True


def place_hook(c, im, face, scale=1.0, alpha=1.0, key="hook"):
    """Put the intro headline on screen without covering the face. render() does a dry run first and records where the
    face is during the hook's whole time on screen; the hook gets ONE spot and never moves (see _hook_slot)."""
    if state.PROBE is not None:
        state.PROBE.setdefault(key, {"rects": [], "h": im.height})["rects"].append(face_rect(face))
        return
    if key not in state.HOOK_SLOTS:
        state.HOOK_SLOTS[key] = _hook_slot([face_rect(face)], im.height)
    y, s, _ = state.HOOK_SLOTS[key]
    place(c, im, W / 2, y, s * scale, alpha)


@functools.lru_cache(64)
def _narrow_size(text, size):
    """the largest size <= size at which the headline fits HOOK_TEXT_W in two lines"""
    for sz in range(size, 47, -2):
        line = text_block(text, F_XBOLD, sz, max_w=HOOK_TEXT_W, leading=1.12)
        if line.height <= sz * 1.12 * 2 + sz * 0.6:
            return sz
    return 48


def intro(c, text, face, t, until=2.6, size=72):
    """The standard opening: headline in its one spot, animated in (0.45 s) and out (0.3 s), gone after `until`.
    Above the head it may be wide; lower down (below the chin, or over the chest while captions wait) it is narrowed
    to stay off the apps' like/comment rail, two lines max. Call it every frame."""
    if t >= until + 0.3:
        return
    a = 1 - ease_out((t - until) / 0.3)
    k = t / 0.45
    wide = brand_hook(text, size, k=k)
    narrow = brand_hook(text, _narrow_size(text, size), max_w=HOOK_TEXT_W, k=k)
    if state.PROBE is not None:
        place_hook(c, wide, face, key="hook")
        place_hook(c, narrow, face, key="hook_narrow")
        return
    if "hook" not in state.HOOK_SLOTS:  # no dry run (called outside render): decide from this frame
        state.HOOK_SLOTS["hook"] = _hook_slot([face_rect(face)], wide.height)
        state.HOOK_SLOTS["hook_narrow"] = _hook_slot([face_rect(face)], narrow.height)
    y, _, _ = state.HOOK_SLOTS["hook"]
    above = y + (wide.height - 2 * HOOK_PAD) / 2 < RAIL_TOP
    key, im = ("hook", wide) if above else ("hook_narrow", narrow)
    place_hook(c, im, face, 1.0, a, key=key)
    state.CAPTIONS_AFTER = until + 0.15 if state.HOOK_SLOTS[key][2] else 0.0


@functools.lru_cache(2048)
def _caption_img(words, active_i, size, hot, max_w, style="clean"):
    """one caption chunk: "clean" (the spoken word in `hot`), "bold" (caps, the spoken word on a `hot` plate)"""
    def word(i, w):
        if style == "bold" and i == active_i:
            t = text_line(w, F_BLACK, size, ON_ACCENT)
            px, py = int(size * 0.18), int(size * 0.06)
            im = Image.new("RGBA", (t.width + 2 * px, t.height + 2 * py))
            ImageDraw.Draw(im).rounded_rectangle((0, 0, im.width - 1, im.height - 1), int(size * 0.16),
                                                 fill=tuple(hot[:3]) + (255,))
            im.alpha_composite(t, (px, py))
            return im
        return text_line(w, F_BLACK, size, hot if (i == active_i and style == "clean") else TEXT, 8)
    ims = [word(i, w) for i, w in enumerate(words)]
    space = int(size * (0.22 if style == "bold" else 0.28))
    lines, cur, cw = [], [], 0
    for im in ims:
        if cur and cw + space + im.width > max_w:
            lines.append(cur)
            cur, cw = [], 0
        cw += (space if cur else 0) + im.width
        cur.append(im)
    if cur:
        lines.append(cur)
    lh = int(size * (1.22 if style == "bold" else 1.08))
    widths = [sum(i.width for i in l) + space * (len(l) - 1) for l in lines]
    out = Image.new("RGBA", (max(widths), lh * len(lines) + int(size * 0.4)))
    for li, (l, lw) in enumerate(zip(lines, widths)):
        x = (max(widths) - lw) // 2
        for im in l:
            out.alpha_composite(im, (x, li * lh + (lh - im.height) // 2 + int(size * 0.2)))
            x += im.width + space
    return out


def cap(ch, t, size=84, hot=ACCENT, max_w=CAPTION_W, upper=False, style="clean"):
    """caption image for chunk ch at time t: the theme's text colour with a black outline, the word being said in
    the accent colour (style="bold": caps, the word on an accent plate). None while an intro() headline sits in the
    caption zone."""
    if ch is None or t < state.CAPTIONS_AFTER:
        return None
    ws = [w for w in ch["words"] if clean_word(w["t"])]
    if not ws:
        return None
    ai = max([i for i, w in enumerate(ws) if w["s"] <= t + 0.03] or [0])
    return _caption_img(tuple(clean_word(w["t"], upper or style == "bold") for w in ws), ai, size, hot, max_w, style)


def caption_y(split=0.0):
    return CAPTION_Y + CAPTION_DROP * clamp01(split)


def captions(c, chunks, t, split=0.0, style=None):
    """place the captions for time t on c: a touch smaller and lower while a board shares the screen (split 0..1),
    so the board gets the room. style: "clean", "bold" or "meme" (one huge word at a time, slammed in); default from
    the theme. Most chunks are one line; a second line may dip under the apps' caption text."""
    style = style or THEME["captions"]
    if style == "meme":
        ch = active(chunks, t)
        if ch is None or t < state.CAPTIONS_AFTER:
            return
        ws = [w for w in ch["words"] if clean_word(w["t"]) and w["s"] <= t + 0.03]
        if not ws:
            return
        w = ws[-1]
        from .fx import meme_text, slam
        place(c, meme_text(clean_word(w["t"], True), 116 if split <= 0.5 else 96, CAPTION_W), W / 2, caption_y(split),
              slam(t, w["s"], 0.14, 1.35), ui_frac=0.45)
        return
    big = style == "bold"
    size = (84 if split > 0.5 else 90) if big else (80 if split > 0.5 else 86)
    place(c, cap(active(chunks, t), t, size, style=style), W / 2, caption_y(split), ui_frac=0.45)


def accent(c, text, face, t, t0, dur=1.6, size=76):
    """the one small touch a conversation clip may have: a word or number next to the head for a beat, as a tag (the
    accent bar, then the text), never in the captions' font and colours. Placed by beside_face()."""
    k = t - t0
    if k < 0 or k > dur:
        return
    im = tag(text, size, clamp01(k / 0.45), scrim=True)
    beside_face(c, im, face, 1 - clamp01((k - dur + 0.25) / 0.25))


def beside_face(c, im, face, alpha=1.0):
    """put a small element next to the speaker's head without covering it: beside the face on the side with more
    room, else above the head, else under the chin (above the captions); off the apps' rail"""
    fx, fy, fs = face_out(face) if face is not None else (W / 2, H * 0.35, 200)
    left, right = 56, min(PLATFORMS[p]["rail"][0] for p in PRIMARY) - 16
    room_r, room_l = right - (fx + fs * 0.9), (fx - fs * 0.9) - left
    above = fy - fs * 1.1 - im.height / 2
    if max(room_r, room_l) >= im.width:          # beside the head
        x = fx + fs * 0.9 + im.width / 2 + 8 if room_r >= room_l else fx - fs * 0.9 - im.width / 2 - 8
        y = fy
    elif above >= SAFE_TOP + im.height / 2 + 16:  # above it
        x, y = W / 2, above
    else:                                        # under the chin, above the captions
        x, y = W / 2, min(fy + fs * 1.05 + im.height / 2, CAPTION_TOP - im.height / 2 - 16)
    place(c, im, x, y, 1, alpha)


@functools.lru_cache(1)
def _logo():
    """the theme's logo (560 px wide at most), or the show's name set big when there is no logo"""
    if THEME["logo"]:
        im = Image.open(THEME["logo"]).convert("RGBA")
        k = min(1.0, 560 / im.width, 300 / im.height)
        return im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    if THEME["name"]:
        return text_block(THEME["name"], F_BLACK, 96, TEXT, max_w=CAPTION_W, leading=1.05, align="center")
    return None


def end_card(t, canvas, tagline=None):
    """The outro over whatever is on the canvas (t = seconds into the end card): the logo (or the show's name), then
    the episode (its published title, which usually names the guest; else the speaker's name) and the episode
    code, then the theme's end_line (or `tagline`). render() adds the outro chime."""
    a = ease_out(t / 0.3)
    canvas.alpha_composite(Image.new("RGBA", canvas.size, (12, 12, 12, int(238 * a))))
    logo = _logo()
    y = H * 0.40
    if logo is not None:
        place(canvas, fade_in(logo, clamp01((t - 0.05) / 0.45)), W / 2, y, 1, a)
        y += logo.height / 2 + 70
    if EPISODE_TITLE:
        text = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]", "", EPISODE_TITLE).strip()  # no emoji
        text = text.replace(": ", ":\n", 1)  # "Guest Name:" on its own line
        title = text_block(text, F_XBOLD, 56, TEXT, max_w=CAPTION_W, leading=1.12, align="center")
        place(canvas, title, W / 2, y + title.height / 2, 1, ease_out((t - 0.35) / 0.3))
        y += title.height + 24
    else:
        who = speaker()
        if who:
            place(canvas, text_line(who, F_MONO_B, 50, ACCENT), W / 2, y + 30, 1, ease_out((t - 0.35) / 0.3))
            y += 84
    if EPISODE:
        place(canvas, text_line(EPISODE, F_MONO_B, 44, ACCENT), W / 2, y + 26, 1, ease_out((t - 0.45) / 0.3))
        y += 76
    line = tagline or THEME["end_line"]
    if not (line or logo is not None or EPISODE_TITLE or EPISODE or speaker()):
        line = "Full episode: link in bio"  # never an empty end card (theme.json's end_line replaces this)
    if line:
        place(canvas, text_line(line, F_MONO, 42, MUTED), W / 2, y + 26, 1, ease_out((t - 0.55) / 0.3))
