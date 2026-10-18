"""Word timings, the edit (which source pieces play, back to back) and caption chunks."""
import functools, json, re

from .project import FPS, WORDS_JSON


@functools.lru_cache(None)
def all_words():
    """every word of the episode: t (text), s/e (seconds), sp (speaker id)"""
    return [dict(t=w["t"], s=w["s"] / 1000, e=w["e"] / 1000, sp=w.get("sp")) for w in json.load(open(WORDS_JSON))]


class Edit:
    """Source pieces (start, end) in seconds, played back to back. Maps source time <-> output time."""

    def __init__(self, pieces, focus=None, hold=0.0, who=()):
        """focus: speaker id (as in words.json) or a name to keep on screen; default: whoever is talking. A name also
        matches faces labelled by name in angles.json (people the audio can't tell apart: ./clip angles <id> --set).
        hold: hold the last frame over a cutaway to someone else when it's at most this long (max 1.2 s).
        who: [(src_from, src_to, "Name"), …] corrects who is talking where diarization got it wrong or merged two
        people (the camera follows it; names match faces labelled with ./clip angles <id> --set A2="Name")."""
        self.focus, self.hold, self.who = focus, hold, list(who)
        self.pieces = [(float(a), float(b)) for a, b in pieces]
        self.offsets = []
        t = 0.0
        for a, b in self.pieces:
            self.offsets.append(t)
            t += b - a
        self.dur = t

    def out_t(self, src):
        """output time of a source time (None if that moment was cut)"""
        for (a, b), o in zip(self.pieces, self.offsets):
            if a - 1e-3 <= src <= b + 1e-3:
                return o + src - a
        return None

    def src_t(self, t):
        a, b = self.pieces[self.piece_at(t)]
        return a + t - self.offsets[self.piece_at(t)]

    def piece_at(self, t):
        for i, ((a, b), o) in enumerate(zip(self.pieces, self.offsets)):
            if t < o + (b - a):
                return i
        return len(self.pieces) - 1

    def words(self, fix=None):
        """words inside the edit, in output time. fix: {regex: replacement}; an empty result drops the word"""
        fix = fix or {}
        out = []
        for w in all_words():
            for (a, b), o in zip(self.pieces, self.offsets):
                if w["s"] >= a - 0.08 and w["e"] <= b + 0.25 and w["s"] < b - 0.05:
                    t = w["t"]
                    for k, v in fix.items():
                        t = re.sub(k, v, t)
                    sp = next((n for x, y, n in self.who if x <= w["s"] <= y), w["sp"])
                    if t:
                        out.append(dict(t=t, s=max(0.0, o + w["s"] - a), e=min(o + (b - a), o + w["e"] - a), sp=sp))
                    break
        return out


FILLERS = {"in", "pol", "ja", "ok", "hm", "no", "pa", "zdaj"}


def tight(*ranges, max_gap=None, pad=0.1, skip=(), speakers=None, end_hold=1.0):
    """Source pieces for the words in each (start, end) range, with pauses longer than max_gap cut out and lone filler
    words dropped. max_gap defaults to the episode's setting (./clip meta <id> --cuts tight|normal|loose|0.6, normal =
    0.45 s). skip: (start, end) ranges whose words are left out; speakers: keep only these speaker ids.
    end_hold: the last piece runs on up to this long after the last word (until the next word), so the payoff lands."""
    from .project import MAX_GAP
    max_gap = MAX_GAP if max_gap is None else max_gap
    W = all_words()
    pieces = []
    for a, b in ranges:
        cur = None
        for w in W:
            if not (a <= w["s"] <= b) or any(x <= w["s"] <= y for x, y in skip) or (speakers and w["sp"] not in speakers):
                continue
            if cur and w["s"] - cur[1] <= max_gap:
                cur[1] = w["e"]
            else:
                if cur:
                    pieces.append(cur)
                cur = [w["s"], w["e"]]
        if cur:
            pieces.append(cur)

    def lone_filler(p):
        inside = [w for w in W if p[0] - 1e-3 <= w["s"] and w["e"] <= p[1] + 1e-3]
        return len(inside) == 1 and re.sub(r"\W", "", inside[0]["t"]).lower() in FILLERS
    out = []
    for s, e in (p for p in pieces if not lone_filler(p)):
        s2 = max(s - pad, out[-1][1]) if out else s - pad
        out.append([s2, e + pad])
    if out and end_hold:  # let the payoff land: keep the reaction after the last word, up to the next word
        nxt = min((w["s"] for w in W if w["s"] > out[-1][1] - pad + 0.01), default=out[-1][1] + end_hold)
        out[-1][1] = max(out[-1][1], min(out[-1][1] + end_hold, nxt - 0.15))
    return [(round(s, 3), round(e, 3)) for s, e in out if e - s > 0.08]


def chunk_words(words, max_words=3, max_chars=18, gap=0.45):
    """group words into caption chunks: {words, s, e}"""
    chunks, cur = [], []
    for w in words:
        if cur and (w["s"] - cur[-1]["e"] > gap or len(cur) >= max_words or
                    len(" ".join(x["t"] for x in cur + [w])) > max_chars):
            chunks.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.!?,:;\"»«]$", w["t"]):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    out = []
    for i, c in enumerate(chunks):
        end = chunks[i + 1][0]["s"] if i + 1 < len(chunks) else c[-1]["e"] + 0.4
        out.append(dict(words=c, s=c[0]["s"], e=min(end, c[-1]["e"] + 0.6)))
    return out


def clean_word(t, upper=False):
    t = re.sub(r"[,\"»«“”„]", "", t)
    t = re.sub(r"\.\.\.$|…$", "", t)
    t = re.sub(r"[.;:]$", "", t)
    return t.upper() if upper else t


def active(chunks, t):
    """the caption chunk on screen at time t"""
    return next((c for c in chunks if c["s"] <= t < c["e"]), None)
