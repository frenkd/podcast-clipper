"""Transcript fixes ("malo smolil" => "mel smolo", "Čakrš" => "Čakarmiš"): stored in project.json, applied to the
word timings (so clip captions get them) and to the transcripts, and re-applied whenever those are regenerated."""
import os
import re

from .store import get_project, read_json, update_project, work_dir, write_json


def _norm(t):
    return "".join(ch for ch in t.lower() if ch.isalnum())


def _match_case(orig, rep):
    return rep[:1].upper() + rep[1:] if orig and orig[0] != orig[0].lower() else rep


def _lead(t):
    i = 0
    while i < len(t) and not t[i].isalnum():
        i += 1
    return t[:i]


def _trail(t):
    i = len(t)
    while i > 0 and not t[i - 1].isalnum():
        i -= 1
    return t[i:]


def parse_fix(s):
    """'wrong => right' -> {from, to}"""
    a, sep, b = s.partition("=>")
    if not sep or not a.strip():
        raise SystemExit(f'a fix looks like "wrong => right", got "{s}"')
    return {"from": a.strip(), "to": b.strip()}


def fix_words(words, fixes):
    """replace phrases in a word list; the replaced span's time is shared out over the new words"""
    out = words
    for f in fixes:
        frm = [x for x in (_norm(w) for w in f["from"].split()) if x]
        to = f["to"].split()
        if not frm:
            continue
        nxt, i = [], 0
        while i < len(out):
            span = out[i:i + len(frm)]
            if len(span) == len(frm) and all(_norm(w["t"]) == frm[k] for k, w in enumerate(span)):
                first, last = span[0], span[-1]
                lead, trail = _lead(first["t"]), _trail(last["t"])
                d = (last["e"] - first["s"]) / max(1, len(to))
                for k, t in enumerate(to):
                    text = (lead + _match_case(first["t"][len(lead):], t) if k == 0 else t) + (trail if k == len(to) - 1 else "")
                    w = {"t": text, "s": round(first["s"] + d * k), "e": round(first["s"] + d * (k + 1))}
                    if first.get("sp") is not None:
                        w["sp"] = first["sp"]
                    nxt.append(w)
                i += len(frm)
            else:
                nxt.append(out[i])
                i += 1
        out = nxt
    return out


def fix_text(text, fixes):
    """replace whole-word phrases in running text (case-insensitive, keeps a capital at the start)"""
    for f in fixes:
        body = r"\s+".join(re.escape(w) for w in f["from"].split())
        if body:
            text = re.sub(rf"(?<!\w){body}(?!\w)", lambda m: _match_case(m.group(0), f["to"]), text, flags=re.I)
    return text


def apply_fixes(pid):
    """apply the project's fixes to whatever transcript files exist"""
    fixes = get_project(pid).get("fixes") or []
    if not fixes:
        return
    wp = os.path.join(work_dir(pid), "words.json")
    words = read_json(wp)
    if words:
        write_json(wp, fix_words(words, fixes))
    for name in ("transcript.json", "transcript.clean.json"):
        path = os.path.join(work_dir(pid), name)
        tr = read_json(path)
        if tr is None:
            continue
        tr["cues"] = [{**c, "text": fix_text(c["text"], fixes)} for c in tr["cues"]]
        if tr.get("words"):
            tr["words"] = fix_words(tr["words"], fixes)
        write_json(path, tr)


def add_fixes(pid, fixes):
    """add fixes (names also go into the glossary, so a re-transcription spells them right) and apply them"""
    def f(p):
        p["fixes"] = [x for x in p.get("fixes") or [] if not any(n["from"] == x["from"] for n in fixes)] + fixes
        for x in fixes:
            if x["to"][:1].isupper() and x["to"] not in p["glossary"]:
                p["glossary"].append(x["to"])
    update_project(pid, f)
    apply_fixes(pid)
