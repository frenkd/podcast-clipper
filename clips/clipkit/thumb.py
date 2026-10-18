"""Vertical covers for clips: the person cut out of the shot (macOS Vision via clips/tools/cutout.swift; elsewhere
the shot with soft edges) on a dark textured background, a headline with the key words in the accent colour, and the
accent bar.

  cover(src_t, headline, out, layout="frame")   one 1080x1920 cover; headline: "**accent** plain" markup
  layouts: "frame" (headline with the bar, the person below), "quote" (a big quote with the bar, the person below),
           "face" (one big line, a rule under it, a tight face)

Apps crop the cover in their grids (Instagram ~3:4 from the centre), so everything that matters sits between
y ≈ 260 and 1660.
"""
import os
import shutil
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .draw import text_line
from .faces import detect
from .project import ACCENT, CACHE, F_MED, F_MONO_B, F_XBOLD, H, REPO, SH, SW, VIDEO, W
from .style import bar

BG = (27, 25, 26)
WHITE = (245, 245, 245)


def _tool():
    exe = os.path.join(CACHE, "cutout")
    src = os.path.join(REPO, "clips", "tools", "cutout.swift")
    if not os.path.exists(exe) or os.path.getmtime(exe) < os.path.getmtime(src):
        os.makedirs(CACHE, exist_ok=True)
        subprocess.run(["swiftc", "-O", src, "-o", exe], check=True)
    return exe


def _frames(t0, n):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-i", VIDEO, "-frames:v", str(n), "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return list(np.frombuffer(raw, np.uint8).reshape(-1, SH, SW, 3))


def frame_at(t, window=0.3):
    """the cleanest still near t: the sharpest frame (on the face) within ±window s, denoised with its neighbours
    (video compression blocks and noise mostly vanish; a cover is shown big and still, so it matters)"""
    path = os.path.join(CACHE, f"thumb_{t:.2f}.v3.png")
    if not os.path.exists(path):
        fr = _frames(max(0.0, t - window), int(window * 2 * 30))
        mid = fr[len(fr) // 2]
        fs = [f for f in detect(mid) if f["score"] > 0.6]
        f = max(fs, key=lambda f: f["size"]) if fs else {"x": SW / 2, "y": SH / 3, "size": SH / 4}
        r = int(f["size"] * 0.6)
        y0, x0 = max(0, int(f["y"]) - r), max(0, int(f["x"]) - r)

        def sharp(a):
            g = cv2.cvtColor(a[y0:int(f["y"]) + r, x0:int(f["x"]) + r], cv2.COLOR_RGB2GRAY)
            return cv2.Laplacian(g, cv2.CV_64F).var()
        k = int(np.argmax([sharp(a) for a in fr[2:-2]])) + 2
        bgr = [np.ascontiguousarray(a[..., ::-1]) for a in fr[k - 2:k + 3]]
        den = cv2.fastNlMeansDenoisingColoredMulti(bgr, 2, 5, None, 2, 2, 5, 15)
        cv2.imwrite(path, cv2.addWeighted(den, 0.6, bgr[2], 0.4, 0))  # keep some real skin texture
    return Image.open(path).convert("RGB")


def person(t, at=None):
    """the person in the source frame at t with the background removed (RGBA, frame size); at=(x, y) in pixels picks
    the one there (their face), so someone else's shoulder in the foreground stays out"""
    path = os.path.join(CACHE, f"thumb_{t:.2f}_{at and int(at[0])}.v3.{'cut' if _vision() else 'soft'}.png")
    if not os.path.exists(path):
        fr = frame_at(t)
        if _vision():
            pt = [f"{at[0] / fr.width:.4f}", f"{at[1] / fr.height:.4f}"] if at else []
            subprocess.run([_tool(), os.path.join(CACHE, f"thumb_{t:.2f}.v3.png"), path, *pt], check=True)
        else:
            _soft_frame(fr, at).save(path)
    return Image.open(path).convert("RGBA")


def _vision():
    """macOS Vision is there (and the Swift compiler for the tool); CLIP_CUTOUT=soft forces the portable fallback"""
    return sys.platform == "darwin" and os.environ.get("CLIP_CUTOUT") != "soft" and bool(shutil.which("swiftc"))


def _soft_frame(fr, at=None):
    """where macOS Vision isn't available: the shot itself around the person at `at` (else the biggest face), fading
    out to the sides and the top. Not a cutout (OpenCV's GrabCut kept sofas and cut hair), but it never looks broken.
    -> RGBA, frame size"""
    a = np.asarray(fr)
    h, w = a.shape[:2]
    fs = [f for f in detect(a) if f["score"] > 0.6]
    fs.sort(key=(lambda f: abs(f["x"] - at[0]) + abs(f["y"] - at[1])) if at else (lambda f: -f["size"]))
    f = fs[0] if fs else {"x": w / 2, "y": h / 3, "size": h / 4}
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx = np.abs(xx - f["x"]) / (1.5 * f["size"])
    side = np.clip((1.15 - dx * 1.5) / 0.45, 0, 1)  # gone by ~1.15 face widths: inside the cover's 1080 px
    top = np.clip((yy - (f["y"] - 1.05 * f["size"])) / (0.45 * f["size"]), 0, 1)
    k = side * top
    alpha = (k * k * (3 - 2 * k) * 255).astype(np.uint8)
    return Image.fromarray(np.dstack([a, alpha]), "RGBA")


def paper(seed=0):
    """the thumbnails' dark, slightly crumpled background"""
    rng = np.random.default_rng(seed)
    low = rng.normal(0, 1, (H // 60, W // 60)).astype(np.float32)
    low = np.asarray(Image.fromarray(((low - low.min()) / np.ptp(low) * 255).astype(np.uint8)).resize((W, H),
                     Image.BICUBIC)).astype(np.float32) / 255
    a = np.zeros((H, W, 3), np.float32) + BG
    a += (low[..., None] - 0.5) * 14 + rng.normal(0, 3.5, (H, W, 1))
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGBA")


def headline(markup, size, max_w, color=WHITE, align="left", leading=1.08):
    """white text with **accent** spans, wrapped to max_w (words keep their colour across lines)"""
    words = []
    hot = False
    for part in markup.replace("\n", " \n ").split("**"):
        for w in part.split(" "):
            if w:
                words.append((w, hot))
        hot = not hot
    lines, cur = [], []
    for w, p in words:
        if w == "\n":
            lines.append(cur)
            cur = []
            continue
        trial = " ".join(x for x, _ in cur + [(w, p)])
        if cur and text_line(trial, F_MED, size).width > max_w:
            lines.append(cur)
            cur = []
        cur.append((w, p))
    lines.append(cur)
    space = int(size * 0.27)
    ims = []
    for ln in lines:
        parts = [text_line(w, F_MED, size, ACCENT if p else color) for w, p in ln]
        gaps = [0] + [0 if w[:1] in ".,:;!?«…" else space for w, _ in ln[1:]]  # punctuation sticks to its word
        im = Image.new("RGBA", (max(1, sum(p.width for p in parts) + sum(gaps)), int(size * 1.25)))
        x = 0
        for p, g in zip(parts, gaps):
            x += g
            im.alpha_composite(p, (x, 0))
            x += p.width
        ims.append(im)
    lh = int(size * leading)
    out = Image.new("RGBA", (max(i.width for i in ims), lh * (len(ims) - 1) + ims[-1].height))
    for i, im in enumerate(ims):
        x = 0 if align == "left" else (out.width - im.width) // 2 if align == "center" else out.width - im.width
        out.alpha_composite(im, (x, i * lh))
    return out


def label(text="podcast"):
    """the thumbnails' small outlined "podcast ×" label"""
    t = text_line(text + " ×", F_MED, 34, WHITE)
    im = Image.new("RGBA", (t.width + 44, t.height + 14))
    ImageDraw.Draw(im).rounded_rectangle((1, 1, im.width - 2, im.height - 2), im.height // 2, outline=WHITE, width=2)
    im.alpha_composite(t, (22, 5))
    return im


def _guided(guide, p, r, eps):
    """He et al.'s guided filter: upsamples a coarse mask along the photo's own edges"""
    mean = lambda x: cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1))
    mi, mp = mean(guide), mean(p)
    a = (mean(guide * p) - mi * mp) / (mean(guide * guide) - mi * mi + eps)
    return mean(a) * guide + mean(mp - a * mi)


def refine(rgba, photo):
    """a better matte than Vision's coarse, stair-stepped one: the edge snapped to the photo with a guided filter
    and tightened, without the deep-navy sofa Vision sometimes counts as part of the person (only fabric darker and
    more saturated than any shirt shadow, in solid patches, so the shirt itself is never cut)"""
    rgb = np.asarray(photo.convert("RGB"))
    al = np.asarray(rgba)[..., 3].astype(np.float32) / 255
    hsv = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2HSV_FULL).astype(np.int16)
    sofa = (hsv[..., 0] > 145) & (hsv[..., 0] < 180) & (hsv[..., 1] > 110) & (hsv[..., 2] < 95)  # deep navy only:
    sofa = cv2.morphologyEx(sofa.astype(np.uint8), cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))   # shirt shadows stay
    al = al * (1 - cv2.GaussianBlur(sofa.astype(np.float32), (0, 0), 1.5))
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    al = np.clip(_guided(g, al, 6, 2e-3), 0, 1)
    al = np.clip((al - 0.35) / 0.35, 0, 1)                   # a crisp but anti-aliased edge, pulled in a touch
    al = cv2.GaussianBlur(al, (0, 0), 0.7)
    n, lab, stats, _ = cv2.connectedComponentsWithStats((al > 0.5).astype(np.uint8))
    if n > 2:  # keep the person, drop crumbs
        keep = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        al = al * cv2.dilate((lab == keep).astype(np.uint8), np.ones((5, 5), np.uint8))
    return Image.fromarray(np.dstack([rgb, (al * 255).astype(np.uint8)]), "RGBA")


def enlarge(im, k, grain=4.0):
    """scale the cut-out up for a cover without it reading soft: Lanczos, half of OpenCV's edge-preserving
    detail enhancement, a light unsharp mask, and the cover's own grain over it (softness reads as photo, not as
    an upscaled video frame)"""
    a = np.asarray(im)
    big = cv2.resize(a, (int(im.width * k), int(im.height * k)), interpolation=cv2.INTER_LANCZOS4)
    rgb = np.ascontiguousarray(big[..., :3])
    det = cv2.detailEnhance(rgb[..., ::-1].copy(), sigma_s=8, sigma_r=0.1)[..., ::-1]
    f = 0.5 * rgb.astype(np.float32) + 0.5 * det.astype(np.float32)
    f = f + 0.55 * (f - cv2.GaussianBlur(f, (0, 0), 1.4))
    f += np.random.default_rng(1).normal(0, grain, f.shape[:2])[..., None]
    return Image.fromarray(np.dstack([np.clip(f, 0, 255).astype(np.uint8), big[..., 3]]), "RGBA")


def _subject(t, face_w, crop_below=3.6, half_w=1.95):
    """the cut-out person scaled so the face is face_w wide, cropped from above the head to mid-torso and to
    half_w face sizes either side (bits of chair or a neighbour's shoulder stay out)"""
    fr = frame_at(t)
    fs = [f for f in detect(np.asarray(fr)) if f["score"] > 0.6]
    f = max(fs, key=lambda f: f["size"]) if fs else {"x": fr.width / 2, "y": fr.height * 0.3, "size": fr.height * 0.2}
    cut = person(t, (f["x"], f["y"]))
    k = face_w / (f["size"] / 1.29)
    top = max(0, f["y"] - f["size"] * 1.25)
    left = max(0, f["x"] - f["size"] * half_w)
    box = (int(left), int(top), int(min(cut.width, f["x"] + f["size"] * half_w)),
           int(min(cut.height, f["y"] + f["size"] * crop_below)))
    im = enlarge(refine(cut.crop(box), fr.crop(box)) if _vision() else cut.crop(box), k)  # refine() is for cutouts
    a = np.asarray(im.split()[3]).astype(np.float32)
    fadew = max(1, int(im.width * 0.06))  # soften the side crop so it never reads as a hard vertical edge
    ramp = np.ones(im.width, np.float32)
    ramp[:fadew] = np.linspace(0, 1, fadew) if left > 0 else 1
    ramp[-fadew:] = np.linspace(1, 0, fadew) if box[2] < cut.width else 1
    im.putalpha(Image.fromarray((a * ramp[None, :]).astype(np.uint8)))
    return im, ((f["x"] - left) * k, (f["y"] - top) * k)  # face centre inside im


def _shadow(im, r=30, a=0.55):
    sh = Image.new("RGBA", (im.width + 4 * r, im.height + 4 * r))
    blk = Image.new("RGBA", im.size, (0, 0, 0, 255))
    blk.putalpha(im.split()[3].point(lambda v: int(v * a)))
    sh.alpha_composite(blk, (2 * r, 2 * r))
    return sh.filter(ImageFilter.GaussianBlur(r))


def _person_to_bottom(c, t, face_w, face_y):
    """the person, face centred at (W/2, face_y), running off the bottom edge like the episode thumbnails"""
    im, (fx, fy) = _subject(t, face_w, crop_below=8)
    x, y = int(W / 2 - fx), int(face_y - fy)
    c.alpha_composite(_shadow(im), (x - 60, y - 40))
    c.alpha_composite(im.crop((0, 0, im.width, max(1, H - y))), (x, y))


def cover(src_t, text, out, layout="frame", name=None, quote=None, label_text=None, face_w=None):
    """one 1080x1920 cover (see the module docstring); text and quote take **accent** markup. face_w: the face's width
    in px (default per layout); smaller for a side-on face, whose box is narrow and whose head reaches up past it"""
    c = paper()
    lab = label(label_text) if label_text else Image.new("RGBA", (1, 1))  # no label by default: simpler
    if layout == "frame":  # headline with the bar beside it, then the person down to the edge
        h = headline(text, 92, W - 180)
        c.alpha_composite(bar(h.height, width=14), (70, 260))
        c.alpha_composite(h, (110, 260))
        c.alpha_composite(lab, (110, 260 + h.height + 28))
        y0 = 260 + h.height + 28 + lab.height + 60
        _person_to_bottom(c, src_t, face_w or 330, y0 + 320)
    elif layout == "quote":  # the line itself with the bar, the person under it
        q = headline(quote, 84, W - 220, leading=1.1)
        c.alpha_composite(bar(q.height, width=14), (70, 280))
        c.alpha_composite(q, (110, 280))
        y = 280 + q.height + 40
        if name:
            n = headline(name, 54, W - 180)
            c.alpha_composite(n, (110, y))
            y += n.height + 20
        c.alpha_composite(lab, (110, y))
        _person_to_bottom(c, src_t, face_w or 330, max(y + lab.height + 260, 1180))
    elif layout == "face":  # one big line, a short rule under it, a tight face
        h = headline(text, 100, W - 140, align="center")
        c.alpha_composite(h, ((W - h.width) // 2, 270))
        rule = Image.new("RGBA", (160, 14), tuple(ACCENT) + (255,))
        c.alpha_composite(rule, ((W - 160) // 2, 270 + h.height + 30))
        c.alpha_composite(lab, ((W - lab.width) // 2, 270 + h.height + 70))
        y0 = 270 + h.height + 70 + lab.height + 70
        _person_to_bottom(c, src_t, face_w or 430, y0 + 380)
    c.convert("RGB").save(out, quality=94)
    return out
