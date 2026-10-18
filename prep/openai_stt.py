"""OpenAI speech-to-text (used when there's no Soniox key): no single OpenAI model gives both word timings and
speakers (October 2026), so each chunk goes to two: whisper-1 for the words and their timings, and
gpt-4o-transcribe-diarize for who talks when. Every word gets the speaker whose turn it falls in. The API takes
files up to 25 MB and its diarization relabels people after a few minutes, so episodes go as 3-minute overlapping
chunks in parallel; stt.stitch() keeps the speaker ids consistent across them.
Models: OPENAI_STT_WORDS / OPENAI_STT_SPEAKERS in .env."""
import os
import re

from .config import require_key
from .stt import chunked, detected_language, post_audio

URL = "https://api.openai.com/v1/audio/transcriptions"
WORDS_MODEL = os.environ.get("OPENAI_STT_WORDS", "whisper-1")
SPEAKERS_MODEL = os.environ.get("OPENAI_STT_SPEAKERS", "gpt-4o-transcribe-diarize")
CHUNK_S, OVERLAP_S, CONCURRENCY = 180, 30, 6  # the diarize model relabels speakers after ~3.5 min: shorter chunks, stitch() keeps the ids


def _post(path, fields):
    return post_audio(URL, path, fields, {"Authorization": f"Bearer {require_key('OPENAI_API_KEY')}"},
                      f"OpenAI transcription ({dict(fields).get('model')})", key="OPENAI_API_KEY")


def _norm(t):
    return "".join(ch for ch in t.lower() if ch.isalnum())


def punctuate(words, segments):
    """whisper's word list has no punctuation or casing; its segment text does. Give each word its token from the
    segment text (matched in order, by letters and digits), so captions keep commas, full stops and question marks."""
    tokens = [t for seg in segments for t in (seg.get("text") or "").split()]
    out, j = [], 0
    for w in words:
        n = _norm(w["t"])
        for k in range(j, min(j + 4, len(tokens))):  # a few tokens of slack for words whisper splits or merges
            if _norm(tokens[k]) == n and n:
                out.append({**w, "t": tokens[k]})
                j = k + 1
                break
        else:
            out.append(w)
    return out


def _words(path, offset_ms, ctx):
    fields = [("model", WORDS_MODEL), ("response_format", "verbose_json"), ("timestamp_granularities[]", "word"),
              ("timestamp_granularities[]", "segment")]
    if ctx.get("language"):
        fields.append(("language", ctx["language"]))
    terms = ", ".join((ctx.get("terms") or [])[:60])
    if terms:  # names and terms to spell right (whisper reads up to ~224 tokens of prompt)
        fields.append(("prompt", terms[:800]))
    r = _post(path, fields)
    from . import stt
    if detected_language(r.get("language")):
        stt.DETECTED.setdefault("language", detected_language(r.get("language")))
    words = [{"t": w["word"].strip(), "s": round(w["start"] * 1000) + offset_ms, "e": round(w["end"] * 1000) + offset_ms}
             for w in r.get("words") or [] if w.get("word", "").strip()]
    return punctuate(words, r.get("segments") or [])


def _turns(path, offset_ms, refs=None):
    """[{s, e, sp}] speaker turns. With refs ({id: wav data URL}, from the first chunk) the model labels those voices
    by their id; other voices (and every voice without refs) come back as A, B, … and get the next free ids."""
    fields = [("model", SPEAKERS_MODEL), ("response_format", "diarized_json"), ("chunking_strategy", "auto")]
    for sp, url in (refs or {}).items():
        fields += [("known_speaker_names[]", sp), ("known_speaker_references[]", url)]
    r = _post(path, fields)
    ids, out = {sp: sp for sp in refs or {}}, []
    for seg in r.get("segments") or []:
        label = seg.get("speaker") or "?"
        if label not in ids:
            ids[label] = str(max([0] + [int(v) for v in ids.values() if v.isdigit()]) + 1)
        out.append({"t": seg.get("text") or "", "s": round(seg["start"] * 1000) + offset_ms,
                    "e": round(seg["end"] * 1000) + offset_ms, "sp": ids[label]})
    return out


def references(path, turns, offset_ms=0, most=4):
    """{id: data URL} of a 2-8 s wav clip per voice, from each speaker's longest turn in this chunk (the model takes
    up to four)"""
    import base64, subprocess, tempfile
    from .config import FFMPEG
    best = {}
    for t in turns:
        if t["e"] - t["s"] >= 2500 and (t["sp"] not in best or t["e"] - t["s"] > best[t["sp"]]["e"] - best[t["sp"]]["s"]):
            best[t["sp"]] = t
    out = {}
    for sp, t in sorted(best.items(), key=lambda x: -(x[1]["e"] - x[1]["s"]))[:most]:
        s0 = (t["s"] - offset_ms) / 1000 + 0.3
        dur = min(8.0, (t["e"] - t["s"]) / 1000 - 0.6)
        with tempfile.TemporaryDirectory() as d:  # (a NamedTemporaryFile can't be reopened by ffmpeg on Windows)
            wav = os.path.join(d, "ref.wav")
            subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", f"{s0:.2f}", "-t", f"{dur:.2f}", "-i", path, "-ac", "1",
                            "-ar", "16000", wav], check=True)
            with open(wav, "rb") as f:
                out[sp] = "data:audio/wav;base64," + base64.b64encode(f.read()).decode()
    return out


def assign(words, turns):
    """each word gets the speaker of the turn it overlaps most (or the nearest turn, for a word in a gap)"""
    if not turns:
        return words
    turns = sorted(turns, key=lambda x: x["s"])
    out, k = [], 0
    for w in words:
        while k < len(turns) - 1 and turns[k]["e"] < w["s"]:
            k += 1
        near = turns[max(0, k - 1):k + 3]
        best = max(near, key=lambda x: (min(x["e"], w["e"]) - max(x["s"], w["s"]),
                                        -min(abs(x["s"] - w["e"]), abs(w["s"] - x["e"]))))
        out.append({**w, "sp": best["sp"]})
    return out


def _chunk(path, offset_ms, ctx, refs):
    """words with speakers for one chunk; the first chunk also leaves its voices in refs for the others"""
    from concurrent.futures import ThreadPoolExecutor
    first = not refs
    with ThreadPoolExecutor(2) as ex:  # the two calls for one chunk at the same time
        words, turns = ex.submit(_words, path, offset_ms, ctx), ex.submit(_turns, path, offset_ms, dict(refs))
        words, turns = words.result(), turns.result()
    if first:
        refs.update(references(path, turns, offset_ms))
    return assign(words, turns)


def transcribe_long(audio, duration, ctx, extract, on_status=None, parts_path=None):
    """the recording -> words with timings and speakers (stt.transcribe)"""
    refs = {}
    return chunked(_ogg(audio), duration, extract, lambda p, off: _chunk(p, off, ctx, refs), CHUNK_S, OVERLAP_S,
                   CONCURRENCY, on_status, parts_path, first_alone=True)


def speaker_turns(audio, duration, extract, on_status=None):
    """speaker turns only, for re-diarizing (stt.speakers)"""
    refs = {}

    def one(p, off):
        turns = _turns(p, off, dict(refs))
        if not refs:
            refs.update(references(p, turns, off))
        return turns
    return chunked(_ogg(audio), duration, extract, one, CHUNK_S, OVERLAP_S, CONCURRENCY, on_status, name="speakers",
                   first_alone=True)


def _ogg(audio):
    """chunks are cut next to `audio` with its extension; OpenAI wants .ogg for Ogg Opus (not .opus)"""
    return re.sub(r"\.opus$", ".ogg", audio)
