"""The README's illustrations, drawn in code (no photos of real people): python docs/illustrations.py

  docs/hero.png   an episode goes in, clips in three styles come out (chill, bold, meme)
  docs/how.png    the four steps
"""
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "..", "assets", "fonts")
S = 2  # supersampling: drawn at 2x, saved at 1x of the design size (which is already retina-sized)

BG = (18, 18, 21)
CARD = (30, 30, 35)
LINE = (52, 52, 58)
WHITE = (250, 250, 250)
GREY = (150, 150, 158)
AMBER = (255, 197, 61)
INK = (14, 14, 16)


def F(name, size):
    from PIL import ImageFont
    return ImageFont.truetype(os.path.join(FONTS, name), int(size * S))


def canvas(w, h):
    im = Image.new("RGBA", (w * S, h * S), BG + (255,))
    rnd = random.Random(3)
    d = ImageDraw.Draw(im)
    for _ in range(w * h // 260):  # a little texture so the dark isn't flat
        x, y = rnd.randrange(w * S), rnd.randrange(h * S)
        c = rnd.randrange(20, 30)
        d.point((x, y), fill=(c, c, c + 3, 255))
    return im


def save(im, name):
    w, h = im.width // S, im.height // S
    im.resize((w, h), Image.LANCZOS).convert("RGB").save(os.path.join(HERE, name), optimize=True)
    print("wrote docs/" + name, f"{w}x{h}")


def P(*xs):
    return [x * S for x in xs]


def text(d, xy, s, font, fill=WHITE, anchor="la", stroke=0, stroke_fill=INK):
    d.text(P(*xy), s, font=font, fill=fill, anchor=anchor, stroke_width=stroke * S, stroke_fill=stroke_fill)


# ---- people: flat, friendly, nobody in particular

def person(d, cx, cy, r, skin, hair, shirt, look="short", phones=False, mouth="smile", glasses=False):
    """a host at head-and-shoulders: head centre (cx, cy), head radius r"""
    sw = r * 2.9
    d.rounded_rectangle(P(cx - sw / 2, cy + r * 1.05, cx + sw / 2, cy + r * 4.2), radius=int(r * 1.0 * S), fill=shirt)
    d.rectangle(P(cx - r * 0.32, cy + r * 0.6, cx + r * 0.32, cy + r * 1.25), fill=tuple(int(c * 0.88) for c in skin))
    if look == "long":
        d.rounded_rectangle(P(cx - r * 1.15, cy - r * 0.9, cx + r * 1.15, cy + r * 1.6), radius=int(r * S), fill=hair)
    d.ellipse(P(cx - r, cy - r, cx + r, cy + r), fill=skin)
    if look in ("short", "long"):
        d.chord(P(cx - r * 1.04, cy - r * 1.12, cx + r * 1.04, cy + r * 0.62), 180, 360, fill=hair)
    elif look == "bun":
        d.ellipse(P(cx - r * 0.45, cy - r * 1.75, cx + r * 0.45, cy - r * 0.85), fill=hair)
        d.chord(P(cx - r * 1.02, cy - r * 1.05, cx + r * 1.02, cy + r * 0.5), 180, 360, fill=hair)
    elif look == "curly":
        for a in range(200, 345, 18):
            x, y = cx + math.cos(math.radians(a)) * r * 0.86, cy + math.sin(math.radians(a)) * r * 0.86
            d.ellipse(P(x - r * 0.36, y - r * 0.36, x + r * 0.36, y + r * 0.36), fill=hair)
    ey = cy + r * 0.05
    for sx in (-1, 1):
        d.ellipse(P(cx + sx * r * 0.36 - r * 0.09, ey - r * 0.12, cx + sx * r * 0.36 + r * 0.09, ey + r * 0.12), fill=INK)
    if glasses:
        for sx in (-1, 1):
            d.rounded_rectangle(P(cx + sx * r * 0.36 - r * 0.26, ey - r * 0.2, cx + sx * r * 0.36 + r * 0.26, ey + r * 0.2),
                                radius=int(r * 0.08 * S), outline=INK, width=max(2, int(r * 0.07 * S)))
        d.line(P(cx - r * 0.1, ey, cx + r * 0.1, ey), fill=INK, width=max(2, int(r * 0.06 * S)))
    my = cy + r * 0.45
    if mouth == "smile":
        d.arc(P(cx - r * 0.3, my - r * 0.2, cx + r * 0.3, my + r * 0.16), 15, 165, fill=INK, width=max(2, int(r * 0.08 * S)))
    elif mouth == "open":
        d.ellipse(P(cx - r * 0.16, my - r * 0.1, cx + r * 0.16, my + r * 0.2), fill=(120, 40, 50))
    if phones:
        d.arc(P(cx - r * 1.12, cy - r * 1.18, cx + r * 1.12, cy + r * 1.0), 185, 355, fill=(40, 40, 46),
              width=max(3, int(r * 0.16 * S)))
        for sx in (-1, 1):
            d.rounded_rectangle(P(cx + sx * r * 1.02 - r * 0.2, cy - r * 0.2, cx + sx * r * 1.02 + r * 0.2, cy + r * 0.45),
                                radius=int(r * 0.12 * S), fill=(40, 40, 46))


def mic(d, x, y, s, side=-1):
    """a podcast mic in front of the chin, capsule at (x, y), its arm running down and out to `side`"""
    d.line(P(x, y + s * 0.4, x + side * s * 2.2, y + s * 3.4), fill=(60, 60, 66), width=int(s * 0.2 * S))
    d.rounded_rectangle(P(x - s * 0.34, y - s * 0.7, x + s * 0.34, y + s * 0.6), radius=int(s * 0.32 * S), fill=(34, 34, 38))
    for k in range(4):
        yy = y - s * 0.45 + k * s * 0.22
        d.line(P(x - s * 0.22, yy, x + s * 0.22, yy), fill=(70, 70, 78), width=max(1, int(s * 0.05 * S)))


def studio(d, box, wall=(44, 52, 66), seed=0):
    """a studio backdrop: a wall, a shelf, a plant, a warm lamp glow"""
    x0, y0, x1, y1 = box
    d.rectangle(P(x0, y0, x1, y1), fill=wall)
    w, h = x1 - x0, y1 - y0
    d.rectangle(P(x0, y0 + h * 0.72, x1, y1), fill=tuple(int(c * 0.75) for c in wall))
    d.rectangle(P(x0 + w * 0.08, y0 + h * 0.3, x0 + w * 0.42, y0 + h * 0.32), fill=(92, 72, 58))
    for i, c in enumerate([(200, 90, 80), (90, 140, 200), (230, 200, 120), (120, 180, 140)]):
        bx = x0 + w * (0.1 + i * 0.07)
        d.rectangle(P(bx, y0 + h * (0.2 + (i % 2) * 0.03), bx + w * 0.05, y0 + h * 0.3), fill=c)
    px, py = x1 - w * 0.12, y0 + h * 0.62
    for a in (-50, -20, 10, 40, 70):
        lx, ly = px + math.cos(math.radians(a - 90)) * h * 0.14, py + math.sin(math.radians(a - 90)) * h * 0.14
        d.ellipse(P(lx - h * 0.05, ly - h * 0.03, lx + h * 0.05, ly + h * 0.03), fill=(70, 140, 90))
    d.rounded_rectangle(P(px - h * 0.05, py, px + h * 0.05, py + h * 0.1), radius=6 * S, fill=(150, 100, 70))


# ---- phones

def phone(im, x, y, w, h, draw_screen, label, sub):
    d = ImageDraw.Draw(im)
    sh = Image.new("RGBA", im.size)
    ImageDraw.Draw(sh).rounded_rectangle(P(x + 10, y + 24, x + w + 10, y + h + 24), radius=int(46 * S), fill=(0, 0, 0, 150))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18 * S)))
    d.rounded_rectangle(P(x, y, x + w, y + h), radius=int(46 * S), fill=(8, 8, 10))
    pad = 12
    scr = Image.new("RGBA", ((w - 2 * pad) * S, (h - 2 * pad) * S))
    draw_screen(scr, w - 2 * pad, h - 2 * pad)
    mask = Image.new("L", scr.size)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, scr.width - 1, scr.height - 1), radius=int(36 * S), fill=255)
    im.paste(scr, P(x + pad, y + pad), mask)
    d.rounded_rectangle(P(x + w / 2 - 44, y + pad + 12, x + w / 2 + 44, y + pad + 34), radius=int(11 * S), fill=(8, 8, 10))
    text(d, (x + w / 2, y + h + 58), label, F("Inter-Black.ttf", 40), anchor="ma")
    text(d, (x + w / 2, y + h + 110), sub, F("JetBrainsMono-Regular.ttf", 22), GREY, anchor="ma")


def host_shot(scr, w, h, who, wall, seed=0):
    d = ImageDraw.Draw(scr)
    studio(d, (0, 0, w, h), wall, seed)
    skin, hair, shirt, look, glasses = who
    r = w * 0.17
    person(d, w * 0.5, h * 0.36, r, skin, hair, shirt, look, phones=True, mouth="open", glasses=glasses)
    mic(d, w * 0.5 - r * 0.62, h * 0.36 + r * 1.35, r * 0.42, -1)
    return d


ALEX = ((236, 188, 160), (60, 40, 32), (70, 110, 200), "short", True)
SAM = ((150, 100, 72), (28, 22, 20), (220, 90, 80), "curly", False)
RIO = ((214, 160, 120), (120, 60, 40), (60, 160, 130), "bun", False)


def caption(d, w, y, words, hot, style, size):
    """one caption line, centred, shrunk until it fits the screen with a margin"""
    while True:
        f = F("Inter-Black.ttf", size)
        gap, padx = size * 0.26, size * 0.18
        widths = [d.textlength(x, font=f) / S for x in words]
        total = sum(widths) + gap * (len(words) - 1) + (2 * padx if style == "bold" else 0)
        if total <= w - 48 or size <= 16:
            break
        size -= 2
    x = (w - total) / 2
    for i, (wd, ww) in enumerate(zip(words, widths)):
        if style == "bold" and i == hot:
            d.rounded_rectangle(P(x, y - size * 0.06, x + ww + 2 * padx, y + size * 1.1), radius=int(size * 0.16 * S),
                                fill=AMBER)
            text(d, (x + padx, y), wd, f, INK)
            x += ww + 2 * padx + gap
            continue
        text(d, (x, y), wd, f, AMBER if (i == hot and style == "clean") else WHITE, stroke=max(3, size // 12))
        x += ww + gap


def chill(scr, w, h):
    d = host_shot(scr, w, h, ALEX, (52, 62, 78))
    bh = 92
    d.rounded_rectangle(P(48, h * 0.62, 56, h * 0.62 + bh), radius=4 * S, fill=AMBER)
    text(d, (74, h * 0.62 + 4), "Will AI take", F("Inter-ExtraBold.ttf", 36))
    text(d, (74, h * 0.62 + 46), "my job?", F("Inter-ExtraBold.ttf", 36))
    text(d, (76, h * 0.62 + bh + 4), "Alex Rivera", F("JetBrainsMono-Bold.ttf", 17), AMBER)
    caption(d, w, h * 0.8, ["the", "short", "answer"], 1, "clean", 42)


def bold(scr, w, h):
    d = host_shot(scr, w, h, SAM, (78, 58, 70))
    st = Image.new("RGBA", (220 * S, 84 * S))
    sd = ImageDraw.Draw(st)
    sd.rounded_rectangle((6 * S, 6 * S, 214 * S, 78 * S), radius=12 * S, fill=WHITE)
    sd.rounded_rectangle((14 * S, 14 * S, 206 * S, 70 * S), radius=8 * S, fill=AMBER)
    sd.text((110 * S, 42 * S), "NO WAY", font=F("Inter-Black.ttf", 32), fill=INK, anchor="mm")
    st = st.rotate(-8, expand=True, resample=Image.BICUBIC)
    scr.alpha_composite(st, (int((w - 236) * S), int(h * 0.15 * S)))
    caption(d, w, h * 0.8, ["THIS", "CHANGED", "IT"], 1, "bold", 40)


def meme(scr, w, h):
    host_shot(scr, w, h, RIO, (60, 60, 70))
    g = scr.convert("L").convert("RGBA")
    vig = Image.new("L", scr.size, 0)
    ImageDraw.Draw(vig).ellipse((-scr.width * 0.25, -scr.height * 0.1, scr.width * 1.25, scr.height * 1.1), fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(60 * S))
    dark = Image.new("RGBA", scr.size, (0, 0, 0, 255))
    g = Image.composite(g, dark, vig)
    scr.paste(g)
    d = ImageDraw.Draw(scr)
    f = F("Inter-Black.ttf", 52)
    text(d, (w / 2, h * 0.08), "SIGMA RULE", f, anchor="ma", stroke=6)
    text(d, (w / 2, h * 0.08 + 58), "#47", f, anchor="ma", stroke=6)
    text(d, (w / 2, h * 0.79), "LITERALLY", F("Inter-Black.ttf", 58), anchor="ma", stroke=7)


def episode_card(im, x, y, w, h):
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(P(x, y, x + w, y + h), radius=int(26 * S), fill=CARD, outline=LINE, width=2 * S)
    sx0, sy0, sx1, sy1 = x + 22, y + 22, x + w - 22, y + h * 0.66
    vid = Image.new("RGBA", (int((sx1 - sx0) * S), int((sy1 - sy0) * S)))
    vd = ImageDraw.Draw(vid)
    vw, vh = sx1 - sx0, sy1 - sy0
    studio(vd, (0, 0, vw, vh), (52, 62, 78))
    for cx, who in ((vw * 0.3, ALEX), (vw * 0.7, SAM)):
        skin, hair, shirt, look, gl = who
        person(vd, cx, vh * 0.42, vh * 0.16, skin, hair, shirt, look, phones=True, glasses=gl,
               mouth="open" if who is SAM else "smile")
        side = 1 if who is ALEX else -1
        mic(vd, cx + side * vh * 0.1, vh * 0.42 + vh * 0.21, vh * 0.065, side)
    mask = Image.new("L", vid.size)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, vid.width - 1, vid.height - 1), radius=14 * S, fill=255)
    im.paste(vid, P(sx0, sy0), mask)
    rnd = random.Random(7)
    wy = y + h * 0.66 + 56
    for i in range(int((w - 44) / 9)):
        a = abs(math.sin(i * 0.37) * 0.6 + rnd.random() * 0.5) * 34 + 4
        hot = 44 <= i <= 62
        d.rounded_rectangle(P(x + 22 + i * 9, wy - a / 2, x + 27 + i * 9, wy + a / 2), radius=2 * S,
                            fill=AMBER if hot else (90, 90, 100))
    text(d, (x + 22, y + h - 52), "episode.mp4", F("JetBrainsMono-Bold.ttf", 24))
    text(d, (x + w - 22, y + h - 52), "1:04:32", F("JetBrainsMono-Regular.ttf", 24), GREY, anchor="ra")


def arrow(d, x0, x1, y, label):
    d.line(P(x0, y, x1 - 18, y), fill=AMBER, width=6 * S)
    d.polygon(P(x1, y, x1 - 26, y - 16, x1 - 26, y + 16), fill=AMBER)
    text(d, ((x0 + x1) / 2, y - 52), label, F("JetBrainsMono-Bold.ttf", 26), WHITE, anchor="ma")


def hero():
    W, H = 2400, 1120
    im = canvas(W, H)
    d = ImageDraw.Draw(im)
    episode_card(im, 90, 290, 640, 520)
    arrow(d, 770, 960, 550, "./clip")
    pw, ph, gap = 380, 760, 80
    x = 1010
    for draw_screen, label, sub in ((chill, "chill", "clean captions, slow push-in"),
                                    (bold, "bold", "word plates, punches, sticker"),
                                    (meme, "meme", "the black & white drop")):
        phone(im, x, 110, pw, ph, draw_screen, label, sub)
        x += pw + gap
    save(im, "hero.png")


def how():
    W, H = 2400, 520
    im = canvas(W, H)
    d = ImageDraw.Draw(im)
    steps = [("Transcribe", "every word, timed, with\nwho said it"),
             ("Find moments", "the funny, surprising and\nquotable bits"),
             ("Make clips", "headline, captions, effects,\nend card, in your look"),
             ("You pick", "previews under 10 MB,\nfinals when you're happy")]
    cw, gap = 500, 60
    x = (W - 4 * cw - 3 * gap) / 2
    for i, (title, body) in enumerate(steps):
        d.rounded_rectangle(P(x, 60, x + cw, 460), radius=int(26 * S), fill=CARD, outline=LINE, width=2 * S)
        d.ellipse(P(x + 40, 100, x + 104, 164), fill=AMBER)
        text(d, (x + 72, 132), str(i + 1), F("Inter-Black.ttf", 34), INK, anchor="mm")
        icon(d, i, x + cw - 150, 90)
        text(d, (x + 40, 220), title, F("Inter-ExtraBold.ttf", 48))
        for k, line in enumerate(body.split("\n")):
            text(d, (x + 40, 300 + k * 44), line, F("Inter-Medium.ttf", 30), GREY)
        x += cw + gap
    save(im, "how.png")


def icon(d, i, x, y):
    if i == 0:  # transcript lines
        for k, (wd, hot) in enumerate(((90, False), (70, True), (100, False))):
            d.rounded_rectangle(P(x, y + 14 + k * 26, x + wd, y + 28 + k * 26), radius=6 * S, fill=AMBER if hot else LINE)
    elif i == 1:  # magnifier over a waveform
        for k in range(10):
            a = [10, 22, 34, 18, 40, 28, 14, 30, 20, 12][k]
            d.rounded_rectangle(P(x + k * 11, y + 50 - a / 2, x + k * 11 + 6, y + 50 + a / 2), radius=2 * S, fill=LINE)
        d.ellipse(P(x + 30, y + 14, x + 86, y + 70), outline=AMBER, width=6 * S)
        d.line(P(x + 80, y + 64, x + 104, y + 88), fill=AMBER, width=8 * S)
    elif i == 2:  # a phone with a caption
        d.rounded_rectangle(P(x + 30, y, x + 84, y + 96), radius=10 * S, outline=LINE, width=4 * S)
        d.rounded_rectangle(P(x + 40, y + 62, x + 74, y + 72), radius=4 * S, fill=AMBER)
    else:  # three cards, one picked
        for k in range(3):
            d.rounded_rectangle(P(x + k * 36, y + 10, x + k * 36 + 28, y + 60), radius=6 * S,
                                fill=AMBER if k == 1 else LINE)
        d.line(P(x + 40, y + 80, x + 52, y + 92, x + 76, y + 66), fill=AMBER, width=6 * S)


if __name__ == "__main__":
    hero()
    how()
