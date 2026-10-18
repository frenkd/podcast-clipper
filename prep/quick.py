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
          "meme": "loud: one-word captions, punches on every line, and the black-and-white 'sigma' drop at the end",
          "dramatic": "the smash zoom: bold captions, then on the last line a zoom into the face, shake, boom, big caption",
          "credits": "the 'directed by' ending: the clip plays out, the last frame freezes and a credits card rolls in",
          "documentary": "nature documentary: letterbox, a warm grade, a typed narrator card, a calm drone",
          "news": "breaking news: a red banner with the headline, a LIVE tag, a ticker of joke headlines, a sting",
          "rewind": "'wait, rewind': a VHS rewind over the punchline, then it plays again",
          "list": "explainer: a card whose items appear as they're said",
          "chart": "explainer: bars that grow when their numbers are said",
          "versus": "explainer: two sides as crowds of figures, one black-and-white beat on the punchline"}
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
    from .llm import arr, integer, llm_json, obj, string as s
    want = {"headline": s("the opening line on screen: at most 7 words, makes you want to hear the rest, in the "
                          "language the clip is spoken in, sentence case, no hashtags or emoji")}
    if style == "bold":
        want["sticker"] = s("one or two words for a sticker at the clip's key moment, in the language the clip is "
                            "spoken in")
        want["sticker_word"] = s("the exact word from the text above at the key moment, where the sticker pops up")
    if style == "dramatic":
        want["drama"] = s("a 1-3 word reaction for the punchline, the 'WAIT WHAT' or 'BRO?!' kind, in the language "
                          "the clip is spoken in")
    if style == "documentary":
        want["doc_label"] = s("a short documentary label, the 'Day 1' or 'Chapter 3' kind, in the language the clip is "
                              "spoken in")
        want["doc_line"] = s("one calm nature-documentary narrator line about the speaker and what they're doing, "
                             "max 12 words, gently funny, in the language the clip is spoken in")
    if style == "news":
        want["ticker"] = arr(s("a made-up joke news line for the ticker, max 8 words, about the clip's topic, in the "
                               "language the clip is spoken in"))
    words_note = "the exact word from the text above where it's first said"
    if style == "list":
        want["list_title"] = s("a 1-4 word title for the list, in the language the clip is spoken in")
        want["items"] = arr(obj(label=s("an item the speaker names, 1-4 words, in the clip's language"), word=s(words_note)))
    if style == "chart":
        want["chart_title"] = s("a 2-5 word title for the chart, in the clip's language")
        want["unit"] = s("the unit after the numbers ('%', ' €', ' h' …), or empty")
        want["bars"] = arr(obj(label=s("what the number is, 1-3 words"), value={"type": "number"}, word=s(words_note)))
        want["bars"]["description"] = ("every number the speaker compares (2-5 bars); just one if the moment has a "
                                       "single striking number (it's shown counting up)")
    if style == "versus":
        want.update(left=s("the first side being compared, 1-3 words"), right=s("the other side, 1-3 words"),
                    left_count=integer(), right_count=integer(),
                    left_word=s(words_note + ", for the first side"), right_word=s(words_note + ", for the other side"),
                    punch_word=s(words_note + ", for the punchline"))
    if style == "meme":
        want["meme"] = s("a short meme caption for the end, the 'SIGMA RULE #N' or 'meanwhile…' kind, max 6 words, "
                         "funny but kind, in the language the clip is spoken in")
    try:
        return llm_json("You write on-screen text for short vertical podcast clips. Be specific to what is said.",
                        f"Language: {language or 'the one the text below is in'}\nWhat is said in the clip:\n{text}", obj(**want), "clip_text", "fast")
    except (SystemExit, OSError, ValueError, KeyError):
        return {}


def write_script(pid, a, b, style, headline=None, sticker=None, meme=None, name=None, drama=None, credit=None,
                 doc_line=None, ticker=None):
    """-> path of the new clip script in projects/<id>/scripts/"""
    if style not in STYLES:
        raise SystemExit(f"--style {style}? one of: {', '.join(STYLES)}")
    scripts = os.path.join(project_dir(pid), "scripts")
    os.makedirs(scripts, exist_ok=True)
    num = 1 + max([int(m.group(1)) for f in os.listdir(scripts) if (m := re.match(r"(\d+)_", f))] or [0])
    text = spoken(pid, a, b)
    if not text:
        raise SystemExit(f"nothing is said between {a:.1f} and {b:.1f} s (is the episode transcribed? `./clip go`)")
    project = read_json(os.path.join(project_dir(pid), "project.json")) or {}
    lang = project.get("language")
    if headline is None or (style == "bold" and sticker is None) or (style == "meme" and meme is None) or \
            (style == "dramatic" and drama is None) or style in ("documentary", "news", "list", "chart", "versus"):
        got = suggest(text, style, lang)
        headline = got.get("headline") if headline is None else headline
        sticker = got.get("sticker") if sticker is None else sticker
        meme = got.get("meme") if meme is None else meme
        drama = got.get("drama") if drama is None else drama
    else:
        got = {}
    from .store import slugify  # (č -> c, ß -> ss, …)
    words = slugify(name or headline or " ".join(text.split()[:5]), 8).split("-")
    slug = ""
    for w in words:  # whole words, up to ~32 characters
        if slug and len(slug) + 1 + len(w) > 32:
            break
        slug = f"{slug}_{w}" if slug else w
    fname = f"{num:02d}_{slug or 'clip'}"
    board = boards(style, got, text, project)
    with open(os.path.join(TEMPLATES, f"{style}.py"), encoding="utf-8") as f:
        src = string.Template(f.read()).substitute(
            title=headline or fname, style=style, episode=pid, num=f"{num:02d}", name=fname,
            start=f"{a:.2f}", end=f"{b:.2f}", headline=json.dumps(headline, ensure_ascii=False) if headline else "None",
            sticker=json.dumps(sticker, ensure_ascii=False) if sticker else "None",
            meme=json.dumps(meme or f"sigma rule #{int(a) % 89 + 11}", ensure_ascii=False),
            sticker_word=json.dumps(got.get("sticker_word") or sticker or "", ensure_ascii=False),
            drama=json.dumps(drama or "wait what", ensure_ascii=False),
            doc_label=json.dumps(got.get("doc_label") or fallback(lang, "doc_label"), ensure_ascii=False),
            doc_line=json.dumps(doc_line or got.get("doc_line") or fallback(lang, "doc_line"), ensure_ascii=False),
            ticker=json.dumps(ticker or got.get("ticker") or fallback(lang, "ticker"), ensure_ascii=False),
            credit_top=json.dumps(fallback(lang, "credit_top"), ensure_ascii=False),
            **board,
            credit=json.dumps(credit or project.get("host") or (project.get("people") or [None])[0], ensure_ascii=False))
    path = os.path.join(scripts, fname + ".py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    return path


FALLBACK = {  # the templates' stock lines when there's no LLM (or it left one out), per episode language
    "en": dict(credit_top="Directed by", doc_label="Day 1", doc_line="The podcaster, in its natural habitat.",
               ticker=["Local podcast says something", "More at eleven", "Experts: this clip is a clip"],
               left="Me", right="Everyone else"),
    "sl": dict(credit_top="Režija", doc_label="1. dan", doc_line="Podkaster v svojem naravnem okolju.",
               ticker=["Lokalni podkast nekaj reče", "Več ob enajstih", "Strokovnjaki: ta posnetek je posnetek"],
               left="Jaz", right="Vsi ostali"),
    "hr": dict(credit_top="Režija", doc_label="Dan 1.", doc_line="Podcaster u svom prirodnom staništu.",
               ticker=["Lokalni podcast nešto kaže", "Više u jedanaest", "Stručnjaci: ovaj isječak je isječak"],
               left="Ja", right="Svi ostali"),
    "de": dict(credit_top="Regie", doc_label="Tag 1", doc_line="Der Podcaster in seinem natürlichen Lebensraum.",
               ticker=["Lokaler Podcast sagt etwas", "Mehr um elf", "Experten: Dieser Clip ist ein Clip"],
               left="Ich", right="Alle anderen"),
    "es": dict(credit_top="Dirigido por", doc_label="Día 1", doc_line="El podcaster, en su hábitat natural.",
               ticker=["Un pódcast local dice algo", "Más a las once", "Expertos: este clip es un clip"],
               left="Yo", right="Todos los demás"),
    "fr": dict(credit_top="Réalisé par", doc_label="Jour 1", doc_line="Le podcasteur, dans son habitat naturel.",
               ticker=["Un podcast local dit quelque chose", "Plus d'infos à onze heures", "Experts : ce clip est un clip"],
               left="Moi", right="Tous les autres"),
}


def fallback(lang, key):
    """a stock line in the episode's language (English when it isn't in FALLBACK)"""
    return FALLBACK.get((lang or "en")[:2], FALLBACK["en"])[key]


def boards(style, got, text, project):
    """the explainer templates' settings: the LLM's when there is one, else something from the clip itself"""
    j = lambda v: json.dumps(v, ensure_ascii=False)
    spoken = [w.strip(".,!?;:»«\"") for w in text.split()]
    if style == "list":
        items = [[i["label"], i["word"]] for i in got.get("items") or [] if i.get("label")]
        if not items:  # no LLM: the clip's longest words, in the order they're said
            long = sorted({w for w in spoken if len(w) >= 6}, key=lambda w: -len(w))[:4]
            items = [[w, w] for w in sorted(long, key=spoken.index)]
        return dict(list_title=j(got.get("list_title") or ""), items=j(items or [["…", ""]]))
    if style == "chart":
        bars = [[b["label"], b["value"], b["word"]] for b in got.get("bars") or [] if b.get("label")]
        if not bars:
            raise SystemExit("--style chart: no numbers found in this moment (pick one where numbers are said, or "
                             "another style)" if os.environ.get("OPENAI_API_KEY") else
                             "--style chart needs OPENAI_API_KEY to find the numbers in the moment (or start from "
                             "another style and write BARS in the script yourself)")
        return dict(chart_title=j(got.get("chart_title") or ""), unit=j(got.get("unit") or ""), bars=j(bars))
    if style == "versus":
        people = project.get("people") or []
        lang = project.get("language")
        return dict(left=j(got.get("left") or fallback(lang, "left")), right=j(got.get("right") or fallback(lang, "right")),
                    nl=int(got.get("left_count") or 1), nr=int(got.get("right_count") or 30),
                    left_word=j(got.get("left_word") or (spoken[0] if spoken else "")),
                    right_word=j(got.get("right_word") or (spoken[len(spoken) // 3] if spoken else "")),
                    punch_word=j(got.get("punch_word") or (spoken[-3] if len(spoken) > 3 else "")))
    return {}
