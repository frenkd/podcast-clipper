"""ElevenLabs speech-to-text (Scribe), used when ELEVENLABS_API_KEY is set: one request gives the words with their
timings, punctuation and speakers (up to 32), for files up to 5 GB, so an episode goes in one piece and the speaker
ids stay consistent from start to end. The glossary goes in as keyterms (names and terms spelled right; ElevenLabs
charges 20 % more for those). Model: ELEVENLABS_STT_MODEL in .env (default scribe_v2)."""
import os
import re

from .config import require_key
from .stt import chunked, detected_language, post_audio

URL = "https://api.elevenlabs.io/v1/speech-to-text"
MODEL = os.environ.get("ELEVENLABS_STT_MODEL", "scribe_v2")
SINGLE_MAX = 4 * 3600                       # longer recordings go as overlapping chunks (stt.chunked)
CHUNK_S, OVERLAP_S, CONCURRENCY = 3600, 60, 3
MAX_TERMS = 100                             # more than 100 keyterms makes every request bill at least 20 s


def keyterms(terms):
    """the glossary as ElevenLabs takes it: under 50 characters, at most 5 words, none of < > { } [ ] \\"""
    out = []
    for t in terms or []:
        t = t.strip()
        if t and len(t) < 50 and len(t.split()) <= 5 and not re.search(r"[<>{}\[\]\\]", t) and t not in out:
            out.append(t)
    return out[:MAX_TERMS]


def to_words(response, offset_ms=0):
    """Scribe's words (spacing and audio events dropped) -> {t, s, e, sp}; speaker_0, speaker_1, … -> "1", "2", …"""
    ids, out = {}, []
    for w in response.get("words") or []:
        if w.get("type") != "word" or w.get("start") is None or not (w.get("text") or "").strip():
            continue
        word = {"t": w["text"].strip(), "s": round(w["start"] * 1000) + offset_ms,
                "e": round((w.get("end") if w.get("end") is not None else w["start"]) * 1000) + offset_ms}
        if w.get("speaker_id") is not None:
            word["sp"] = ids.setdefault(w["speaker_id"], str(len(ids) + 1))
        out.append(word)
    return out


def _transcribe(path, ctx, offset_ms=0):
    fields = [("model_id", MODEL), ("diarize", "true"), ("timestamps_granularity", "word"),
              ("tag_audio_events", "false")]
    if ctx.get("language"):
        fields.append(("language_code", ctx["language"]))
    fields += [("keyterms", t) for t in keyterms(ctx.get("terms"))]
    r = post_audio(URL, path, fields, {"xi-api-key": require_key("ELEVENLABS_API_KEY")},
                   f"ElevenLabs transcription ({MODEL})", timeout=3600, key="ELEVENLABS_API_KEY")
    from . import stt
    if detected_language(r.get("language_code")):
        stt.DETECTED.setdefault("language", detected_language(r.get("language_code")))
    return to_words(r, offset_ms)


def transcribe_long(audio, duration, ctx, extract, on_status=None, parts_path=None):
    """the recording -> words with timings and speakers (stt.transcribe): one request up to SINGLE_MAX"""
    say = on_status or (lambda m, p=None: None)
    if duration <= SINGLE_MAX:
        say("transcribing", 0.1)
        return _transcribe(audio, ctx)
    return chunked(re.sub(r"\.opus$", ".ogg", audio), duration, extract, lambda p, off: _transcribe(p, ctx, off),
                   CHUNK_S, OVERLAP_S, CONCURRENCY, say, parts_path)
