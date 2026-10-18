"""`./clip quick <episode> 12:30-13:05 --style chill|bold|meme`: the starter path. It writes a clip script from a
template in clips/templates/ (a normal script you can edit) and renders a preview. With an OpenAI key it also writes
the opening headline (and the sticker or the meme drop's caption); without one it leaves them to you."""
import json
import os
import re
import string

from .config import ROOT
from .store import project_dir, read_json

STYLES = {"chill": "calm: clean captions, a slow push-in, a soft bed",
          "bold": "punchy: caps captions with the word on a plate, zoom punches, a sticker, a beat",
          "meme": "loud: one-word captions, punches on every line, and the black-and-white 'sigma' drop at the end"}
TEMPLATES = os.path.join(ROOT, "clips", "templates")


def parse_range(text):
    """'12:30-13:05', '750-785' or '1:02:03-1:02:40' -> (start, end) in seconds"""
    def sec(x):
        parts = [float(p) for p in x.strip().split(":")]
        v = 0.0
        for p in parts:
            v = v * 60 + p
        return v
    m = re.fullmatch(r"\s*([\d:.]+)\s*[-–]\s*([\d:.]+)\s*", text or "")
    if not m:
        raise SystemExit(f"time range {text!r}? use start-end, e.g. 12:30-13:05 or 750-785")
    a, b = sec(m.group(1)), sec(m.group(2))
    if b <= a:
        raise SystemExit(f"{text}: the end is before the start")
    if b - a > 180:
        raise SystemExit(f"{text}: {b - a:.0f} s is long for a short clip (keep it under 3 minutes)")
    return a, b


def spoken(pid, a, b):
    """the transcript words between a and b (seconds)"""
    words = read_json(os.path.join(project_dir(pid), "work", "words.json")) or []
    return " ".join(w["t"] for w in words if a <= w["s"] / 1000 <= b)


def suggest(text, style, language):
    """headline (and sticker / drop caption) for a moment from the LLM; {} without an OpenAI key"""
    if not os.environ.get("OPENAI_API_KEY"):  # .env is loaded by prep.config
        return {}
    from .llm import llm_json, obj, string as s
    want = {"headline": s("the opening line on screen: at most 7 words, makes you want to hear the rest, in the "
                          "language the clip is spoken in, sentence case, no hashtags or emoji")}
    if style == "bold":
        want["sticker"] = s("one or two words for a sticker at the clip's key moment, in the language the clip is "
                            "spoken in")
    if style == "meme":
        want["meme"] = s("a short meme caption for the end, the 'SIGMA RULE #N' or 'meanwhile…' kind, max 6 words, "
                         "funny but kind, in the language the clip is spoken in")
    try:
        return llm_json("You write on-screen text for short vertical podcast clips. Be specific to what is said.",
                        f"Language: {language or 'the one the text below is in'}\nWhat is said in the clip:\n{text}", obj(**want), "clip_text", "fast")
    except (SystemExit, OSError, ValueError, KeyError):
        return {}


def write_script(pid, a, b, style, headline=None, sticker=None, meme=None, name=None):
    """-> path of the new clip script in projects/<id>/scripts/"""
    if style not in STYLES:
        raise SystemExit(f"--style {style}? one of: {', '.join(STYLES)}")
    scripts = os.path.join(project_dir(pid), "scripts")
    os.makedirs(scripts, exist_ok=True)
    num = 1 + max([int(m.group(1)) for f in os.listdir(scripts) if (m := re.match(r"(\d+)_", f))] or [0])
    text = spoken(pid, a, b)
    if not text:
        raise SystemExit(f"nothing is said between {a:.1f} and {b:.1f} s (is the episode transcribed? `./clip go`)")
    lang = (read_json(os.path.join(project_dir(pid), "project.json")) or {}).get("language")
    if headline is None or (style == "bold" and sticker is None) or (style == "meme" and meme is None):
        got = suggest(text, style, lang)
        headline = got.get("headline") if headline is None else headline
        sticker = got.get("sticker") if sticker is None else sticker
        meme = got.get("meme") if meme is None else meme
    from .store import slugify  # (č -> c, ß -> ss, …)
    words = slugify(name or headline or " ".join(text.split()[:5]), 8).split("-")
    slug = ""
    for w in words:  # whole words, up to ~32 characters
        if slug and len(slug) + 1 + len(w) > 32:
            break
        slug = f"{slug}_{w}" if slug else w
    fname = f"{num:02d}_{slug or 'clip'}"
    with open(os.path.join(TEMPLATES, f"{style}.py"), encoding="utf-8") as f:
        src = string.Template(f.read()).substitute(
            title=headline or fname, style=style, episode=pid, num=f"{num:02d}", name=fname,
            start=f"{a:.2f}", end=f"{b:.2f}", headline=json.dumps(headline, ensure_ascii=False) if headline else "None",
            sticker=json.dumps(sticker, ensure_ascii=False) if sticker else "None",
            meme=json.dumps(meme or f"sigma rule #{int(a) % 89 + 11}", ensure_ascii=False))
    path = os.path.join(scripts, fname + ".py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return path
