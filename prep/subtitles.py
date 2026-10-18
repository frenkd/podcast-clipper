"""Subtitle files in and out: parse SRT/WebVTT, compact transcripts for prompts, full-episode SRT."""
import re

_TS = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})")


def _parse_ts(s):
    m = _TS.search(s)
    if not m:
        return 0
    h, mi, se, ms = m.groups()
    return ((int(h) * 60 + int(mi)) * 60 + int(se)) * 1000 + int(ms.ljust(3, "0"))


def parse_subtitles(text):
    """SRT or WebVTT -> cues [{i, s, e, text}] (ms). Exact duplicate cues collapse into the later one (some exporters
    write each cue twice; the second is usually the corrected one)."""
    text = re.sub(r"^WEBVTT.*\n", "", text.replace("\r", ""))
    cues = []
    for block in re.split(r"\n{2,}", text):
        lines = [l for l in block.split("\n") if l]
        ti = next((k for k, l in enumerate(lines) if "-->" in l), -1)
        if ti < 0:
            continue
        a, z = lines[ti].split("-->", 1)
        body = re.sub(r"<[^>]+>", "", " ".join(lines[ti + 1:])).strip()
        if not body:
            continue
        cue = {"i": len(cues), "s": _parse_ts(a), "e": _parse_ts(z), "text": body}
        if cues and cues[-1]["s"] == cue["s"] and cues[-1]["e"] == cue["e"]:
            cues[-1]["text"] = cue["text"]
            continue
        cues.append(cue)
    return cues


def fmt_clock(sec):
    t = max(0, int(sec))
    h, m, s = t // 3600, t % 3600 // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def cues_for_prompt(cues, speakers=None, with_index=False):
    """compact transcript for prompts: '[12:34] S2: text'"""
    speakers = speakers or {}
    out = []
    for c in cues:
        sp = f" {speakers.get(c['sp'], 'S' + str(c['sp']))}:" if c.get("sp") else ""
        out.append(f"{'#%d ' % c['i'] if with_index else ''}[{fmt_clock(c['s'] / 1000)}]{sp} {c['text']}")
    return "\n".join(out)


def _srt_ts(ms):
    t = max(0, round(ms))
    return f"{t // 3600000:02d}:{t % 3600000 // 60000:02d}:{t % 60000 // 1000:02d},{t % 1000:03d}"


def to_srt(cues):
    """full-episode SRT: long cues split to <= 84 characters (two lines of <= ~42), short ones shown >= ~1 s"""
    out = []
    for c in cues:
        parts = []
        for w in c["text"].split(" "):
            if parts and len(parts[-1] + " " + w) <= 84:
                parts[-1] += " " + w
            else:
                parts.append(w)
        total = sum(len(x) for x in parts) or 1
        t = c["s"]
        for x in parts:
            d = (c["e"] - c["s"]) * len(x) / total
            out.append({"s": t, "e": t + d, "text": x})
            t += d
    blocks = []
    for i, c in enumerate(out):
        nxt = out[i + 1] if i + 1 < len(out) else None
        e = max(c["e"], min(c["s"] + 1000, nxt["s"] - 40 if nxt else c["s"] + 1000))
        text, words = c["text"], c["text"].split(" ")
        if len(text) > 42:
            best = None
            for k in range(1, len(words)):
                a, b = " ".join(words[:k]), " ".join(words[k:])
                if best is None or abs(len(a) - len(b)) < best:
                    best, text = abs(len(a) - len(b)), f"{a}\n{b}"
        blocks.append(f"{i + 1}\n{_srt_ts(c['s'])} --> {_srt_ts(e)}\n{text}\n")
    return "\n".join(blocks)
