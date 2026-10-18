"""Where each app's own UI sits over a 1080x1920 clip (organic posts, phone, 2026), so nothing important goes under it.

Numbers are deliberately a little conservative and cover the common case, not every device. Sources: Meta's Reels /
Stories safe-zone guidance (14% top; its 35% bottom is for ads with a CTA, organic Reels need less), TikTok's ad-spec
overlay (540x960: 126 top, 60 left, 120 right rail, 320 bottom incl. ad card), third-party measurements of X's
immersive viewer (~400 px bottom, ~140 px right rail) and LinkedIn's vertical player (~12% top, ~20% bottom).
Update the table when an app changes its layout.

  danger(platforms)       -> [(x0, y0, x1, y1, platform, what)] rectangles covered by UI
  safe_box(), safe_width(y0, y1)   -> the clear area; the widest centred element for a band of rows
  unsafe(box, platforms)  -> platforms whose UI covers a meaningful part of box (orange: a note, judge it)
  at_edge(box)            -> True if box reaches into the thin band round the screen edge (red: always wrong)
  mock(frame, platform)   -> the frame with that app's UI sketched over it (for review sheets)
"""
from PIL import Image, ImageDraw

W, H = 1080, 1920

# top bar, bottom text block (username, caption, audio), side margins, right action rail (x from, y from)
PLATFORMS = {
    "instagram": {"top": 220, "bottom": 400, "side": 40, "rail": (950, 1020), "label": "Instagram Reels"},
    "x":         {"top": 190, "bottom": 400, "side": 40, "rail": (960, 1040), "label": "X"},
    "linkedin":  {"top": 230, "bottom": 390, "side": 40, "rail": (950, 1020), "label": "LinkedIn"},
    "tiktok":    {"top": 250, "bottom": 480, "side": 60, "rail": (860, 820), "label": "TikTok"},
    "shorts":    {"top": 200, "bottom": 460, "side": 40, "rail": (910, 900), "label": "YouTube Shorts"},
}
PRIMARY = ("instagram", "x", "linkedin")
# red: the thin band round the whole screen (notch / status bar, home bar, rounded corners, the edge itself) where
# nothing of ours may go on any app; everything else in danger() is orange, worth a look but sometimes fine
EDGE = {"side": 32, "top": 110, "bottom": 90}


def at_edge(box, px=400):
    """box (x0, y0, x1, y1) reaches into the red band round the screen by more than px pixels"""
    x0, y0, x1, y1 = box[:4]
    inner = (EDGE["side"], EDGE["top"], W - EDGE["side"], H - EDGE["bottom"])
    area = (x1 - x0) * (y1 - y0)
    ix = max(0, min(x1, inner[2]) - max(x0, inner[0])) * max(0, min(y1, inner[3]) - max(y0, inner[1]))
    return area - ix > px


def danger(platforms=PRIMARY):
    out = []
    for name in platforms:
        p = PLATFORMS[name]
        out += [(0, 0, W, p["top"], name, "top bar"),
                (0, H - p["bottom"], W, H, name, "caption + username"),
                (0, 0, p["side"], H, name, "edge"), (W - p["side"], 0, W, H, name, "edge"),
                (p["rail"][0], p["rail"][1], W, H, name, "action rail")]
    return out


def safe_box(platforms=PRIMARY):
    """the rectangle free of every listed app's UI, ignoring the right rail: (x0, y0, x1, y1)"""
    ps = [PLATFORMS[n] for n in platforms]
    return (max(p["side"] for p in ps), max(p["top"] for p in ps), W - max(p["side"] for p in ps),
            H - max(p["bottom"] for p in ps))


def safe_width(y0, y1, platforms=PRIMARY, margin=16):
    """widest element, centred on the frame, that spans y0..y1 without going under any listed app's rail or edge"""
    ps = [PLATFORMS[n] for n in platforms]
    right = min([p["rail"][0] for p in ps if y1 > p["rail"][1]] + [W - p["side"] for p in ps])
    left = max(p["side"] for p in ps)
    return int(2 * min(W / 2 - left, right - W / 2) - 2 * margin)


def unsafe(box, platforms=PRIMARY, frac=0.12, px=1500):
    """platforms whose UI covers part of box: more than `frac` of it under a top/bottom bar, or any real overlap
    (> px pixels) with the action rail or the screen edge"""
    x0, y0, x1, y1 = box[:4]
    area = max(1, (x1 - x0) * (y1 - y0))
    hits = set()
    for rx0, ry0, rx1, ry1, name, what in danger(platforms):
        ix = max(0, min(x1, rx1) - max(x0, rx0)) * max(0, min(y1, ry1) - max(y0, ry0))
        if ix > px and (ix > frac * area or what in ("action rail", "edge")):
            hits.add(name)
    return sorted(hits)


def mock(frame, platform):
    """frame (RGB/RGBA 1080x1920) with a sketch of the app's UI and its danger zones shaded"""
    p = PLATFORMS[platform]
    im = frame.convert("RGBA").resize((W, H))
    shade = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(shade)
    for x0, y0, x1, y1, name, _ in danger([platform]):
        d.rectangle((x0, y0, x1, y1), fill=(255, 150, 30, 46))                              # orange: app UI
    e = EDGE
    for r in ((0, 0, W, e["top"]), (0, H - e["bottom"], W, H), (0, 0, e["side"], H), (W - e["side"], 0, W, H)):
        d.rectangle(r, fill=(255, 30, 30, 90))                                               # red: screen edge
    ui = (255, 255, 255, 215)
    d.rounded_rectangle((60, 70, 300, 120), 12, fill=ui)                                  # top bar title / tabs
    d.ellipse((W - 130, 60, W - 70, 120), fill=ui)
    rx = (p["rail"][0] + W) // 2
    for k in range(5):                                                                      # action rail icons
        y = p["rail"][1] + 40 + k * 150
        if y < H - 60:
            d.ellipse((rx - 40, y, rx + 40, y + 80), fill=ui)
    y = H - p["bottom"] + 60
    d.ellipse((60, y, 140, y + 80), fill=ui)                                                # avatar + username
    d.rounded_rectangle((160, y + 20, 500, y + 60), 10, fill=ui)
    for k, w in enumerate((760, 640, 420)):                                                 # caption lines + audio
        d.rounded_rectangle((60, y + 120 + k * 60, 60 + w, y + 160 + k * 60), 10, fill=(255, 255, 255, 170))
    im.alpha_composite(shade)
    return im


_UI = {}


def app_ui(platform="instagram", user="yourshow", caption="Full episode: link in bio"):
    """a realistic-ish overlay of the app's own UI (white icons, text, the bottom scrim) to bake into a test render
    and see the clip the way people will (CLIP_MOCK=instagram ./clip render …). Instagram Reels-like for all apps."""
    key = (platform, user, caption)
    if key in _UI:
        return _UI[key]
    from .draw import text_line
    from .project import F_BOLD, F_MED
    p = PLATFORMS[platform]
    ui = Image.new("RGBA", (W, H))
    for k in range(560):  # the dark gradient apps put under their text
        a = int(150 * (k / 560) ** 1.6)
        ImageDraw.Draw(ui).line((0, H - 560 + k, W, H - 560 + k), fill=(0, 0, 0, a))
    d = ImageDraw.Draw(ui)
    white = (255, 255, 255, 240)
    ui.alpha_composite(text_line("Reels", F_BOLD, 52, white), (48, 108))
    d.rounded_rectangle((W - 112, 112, W - 52, 164), 10, outline=white, width=5)              # camera
    d.ellipse((W - 96, 124, W - 68, 152), outline=white, width=5)
    rx, y = (p["rail"][0] + W) // 2 + 6, p["rail"][1] + 30
    for icon, n in (("heart", "1.204"), ("comment", "87"), ("share", "312"), ("more", "")):
        if icon == "heart":
            d.ellipse((rx - 34, y, rx, y + 34), outline=white, width=6)
            d.ellipse((rx, y, rx + 34, y + 34), outline=white, width=6)
            d.polygon([(rx - 33, y + 22), (rx, y + 60), (rx + 33, y + 22)], outline=white, width=6)
        elif icon == "comment":
            d.ellipse((rx - 32, y, rx + 32, y + 60), outline=white, width=6)
        elif icon == "share":
            d.polygon([(rx - 34, y + 6), (rx + 34, y + 24), (rx - 10, y + 56)], outline=white, width=6)
        else:
            for dx in (-22, 0, 22):
                d.ellipse((rx + dx - 6, y + 24, rx + dx + 6, y + 36), fill=white)
        if n:
            t = text_line(n, F_MED, 30, white)
            ui.alpha_composite(t, (rx - t.width // 2, y + 70))
        y += 150
    y = H - p["bottom"] + 70
    d.ellipse((48, y, 128, y + 80), fill=(120, 120, 128, 255))
    ui.alpha_composite(text_line(user, F_BOLD, 40, white), (148, y + 18))
    fx = 148 + text_line(user, F_BOLD, 40).width + 24
    d.rounded_rectangle((fx, y + 12, fx + 150, y + 70), 14, outline=white, width=3)
    ui.alpha_composite(text_line("Follow", F_BOLD, 34, white), (fx + 22, y + 20))
    ui.alpha_composite(text_line(caption, F_MED, 38, white), (48, y + 112))
    ui.alpha_composite(text_line("♫ yourshow  Original audio", F_MED, 34, (255, 255, 255, 220)), (48, y + 176))
    _UI[key] = ui
    return ui


def sheet(frame, platforms=("instagram", "x", "linkedin", "tiktok"), width=360):
    """the frame under each app's UI, side by side"""
    from .draw import text_line
    from .project import F_MENLO
    tiles = []
    for n in platforms:
        t = mock(frame, n).resize((width, int(width * H / W)))
        lab = text_line(PLATFORMS[n]["label"], F_MENLO, 22, (255, 255, 0))
        t.alpha_composite(lab, (8, 4))
        tiles.append(t)
    out = Image.new("RGB", (width * len(tiles) + 8 * (len(tiles) - 1), tiles[0].height), (30, 30, 30))
    for i, t in enumerate(tiles):
        out.paste(t.convert("RGB"), (i * (width + 8), 0))
    return out
