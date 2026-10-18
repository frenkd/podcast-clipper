"""Your show's look: theme.json at the repo root (copy theme.example.json), overridden per episode by project.json's
"theme". Every key is optional; without a theme.json you get a clean neutral look.

  name         the show's name, on the end card ("My Podcast")
  accent       "#RRGGBB": the highlight colour (the spoken word in captions, the headline's bar, the end card)
  on_accent    text colour on top of the accent (default: black or white, whichever reads better)
  text         headline and caption colour (default white)
  fonts        {"black", "extrabold", "bold", "medium", "regular", "mono", "mono_bold", "mono_heavy"}: font files,
               relative to the repo (default: Inter and JetBrains Mono in assets/fonts/)
  logo         a PNG for the end card (optional; without one the end card shows the name)
  end_line     the end card's second line, e.g. "Full episode on YouTube" (default: the episode title)
  outro_chime  false turns off the short chime under the end card
  captions     "clean" (the spoken word in the accent colour), "bold" (caps, the spoken word on an accent
               plate) or "meme" (one huge word at a time); a clip can pick its own with captions(..., style=)
"""
import json
import os

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FONTS = os.path.join(_REPO, "assets", "fonts")

DEFAULTS = {
    "name": "",
    "accent": "#FFC53D",
    "on_accent": None,
    "text": "#FFFFFF",
    "fonts": {"black": "assets/fonts/Inter-Black.ttf", "extrabold": "assets/fonts/Inter-ExtraBold.ttf",
              "bold": "assets/fonts/Inter-Bold.ttf", "medium": "assets/fonts/Inter-Medium.ttf",
              "regular": "assets/fonts/Inter-Regular.ttf", "mono": "assets/fonts/JetBrainsMono-Regular.ttf",
              "mono_bold": "assets/fonts/JetBrainsMono-Bold.ttf", "mono_heavy": "assets/fonts/JetBrainsMono-ExtraBold.ttf"},
    "logo": None,
    "end_line": None,
    "outro_chime": True,
    "captions": "clean",
}

CAPTION_STYLES = ("clean", "bold", "meme")


def rgb(value):
    """"#RRGGBB" (or an [r, g, b] list) -> (r, g, b)"""
    if isinstance(value, (list, tuple)):
        return tuple(int(v) for v in value[:3])
    v = str(value).lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        raise SystemExit(f"theme: {value!r} isn't a colour (use \"#RRGGBB\")")
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


def readable_on(c):
    """black or white, whichever reads better on colour c"""
    lum = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    return (12, 12, 12) if lum > 150 else (255, 255, 255)


def load(project=None, path=None):
    """the theme: DEFAULTS <- theme.json <- project.json "theme" (fonts merge key by key)"""
    t = json.loads(json.dumps(DEFAULTS))
    path = path or os.environ.get("CLIP_THEME") or os.path.join(_REPO, "theme.json")
    layers = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            layers.append(json.load(f))
    if project and project.get("theme"):
        layers.append(project["theme"])
    for layer in layers:
        for k, v in layer.items():
            if k.startswith("_"):
                continue
            if k not in DEFAULTS:
                raise SystemExit(f"theme: unknown key {k!r} (keys: {', '.join(DEFAULTS)})")
            t[k] = {**t[k], **v} if k == "fonts" else v
    if t["captions"] not in CAPTION_STYLES:
        raise SystemExit(f"theme: captions {t['captions']!r}? ({', '.join(CAPTION_STYLES)})")
    t["accent"] = rgb(t["accent"])
    t["text"] = rgb(t["text"])
    t["on_accent"] = rgb(t["on_accent"]) if t.get("on_accent") else readable_on(t["accent"])
    for k, f in t["fonts"].items():
        full = f if os.path.isabs(f) else os.path.join(_REPO, f)
        if not os.path.exists(full):
            raise SystemExit(f"theme: font {k} not found: {f}")
        t["fonts"][k] = full
    if t["logo"]:
        t["logo"] = t["logo"] if os.path.isabs(t["logo"]) else os.path.join(_REPO, t["logo"])
        if not os.path.exists(t["logo"]):
            raise SystemExit(f"theme: logo not found: {t['logo']}")
    return t
