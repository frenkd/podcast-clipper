"""Soniox speech-to-text (used when SONIOX_API_KEY is set): upload, transcribe, words with timings and diarized
speakers. Episodes go in one request; only very long ones as chunks (stt.chunked)."""
import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid

from .config import SONIOX_MODEL, api_error, require_key
from .stt import chunked

API = "https://api.soniox.com/v1"


def _api(path, method="GET", body=None, headers=None):
    req = urllib.request.Request(API + path, data=body, method=method,
                                 headers={"Authorization": f"Bearer {require_key('SONIOX_API_KEY')}", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            data = r.read()
            return json.loads(data) if data else None
    except urllib.error.HTTPError as e:
        raise api_error("Soniox", "SONIOX_API_KEY", e.code, e.read().decode(errors="replace")[:500]) from None


def _upload(path):
    boundary = uuid.uuid4().hex
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{os.path.basename(path)}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode()
    body = head + open(path, "rb").read() + f"\r\n--{boundary}--\r\n".encode()
    return _api("/files", "POST", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"})


def transcribe_file(path, ctx, on_status=None):
    """upload audio, transcribe -> Soniox tokens; the uploaded file and the transcription are deleted afterwards"""
    (on_status or (lambda m: None))("uploading audio")
    f = _upload(path)
    context = {"general": [{"key": "domain", "value": "Podcast conversation"}]
               + ([{"key": "topic", "value": ctx["topic"]}] if ctx.get("topic") else [])
               + ([{"key": "speakers", "value": ctx["speakers"]}] if ctx.get("speakers") else []),
               "text": (ctx.get("text") or "")[:8000], "terms": (ctx.get("terms") or [])[:300]}
    tr = None
    try:
        tr = _api("/transcriptions", "POST", json.dumps({
            "model": SONIOX_MODEL, "file_id": f["id"], "language_hints": list(dict.fromkeys([ctx.get("language") or "en", "en"])),
            "enable_speaker_diarization": True, "enable_language_identification": True, "context": context,
            "client_reference_id": "podcast-clipper"}).encode(), {"Content-Type": "application/json"})
        (on_status or (lambda m: None))("transcribing")
        for i in range(10 ** 6):
            s = _api(f"/transcriptions/{tr['id']}")
            if s["status"] == "completed":
                break
            if s["status"] == "error":
                raise RuntimeError(f"Soniox: {s.get('error_message')}")
            time.sleep(min(5.0, 1 + i * 0.5))
        return (_api(f"/transcriptions/{tr['id']}/transcript") or {}).get("tokens", [])
    finally:
        for p in ([f"/transcriptions/{tr['id']}"] if tr else []) + [f"/files/{f['id']}"]:
            try:
                _api(p, "DELETE")
            except RuntimeError:
                pass


def _is_punct(t):
    return all(ch in '.,!?;:…"»«)' for ch in t)


def tokens_to_words(tokens, offset_ms=0):
    """Soniox tokens are sub-word pieces; a leading space starts a new word, punctuation sticks to the previous one"""
    words = []
    for tok in tokens:
        t0 = tok.get("start_ms")
        if not tok.get("text") or t0 is None or tok["text"].startswith("<"):
            continue
        text = tok["text"].strip()
        if not text:
            continue
        end = (tok.get("end_ms") if tok.get("end_ms") is not None else t0) + offset_ms
        starts = tok["text"][0].isspace() or not words
        if words and (not starts or _is_punct(text)):
            words[-1]["t"] += text
            words[-1]["e"] = end
            continue
        w = {"t": text, "s": t0 + offset_ms, "e": end}
        if tok.get("speaker") is not None:
            w["sp"] = str(tok["speaker"])
        words.append(w)
    return split_glued(words)


_GLUED = re.compile(r"^(.*?\w[,.!?;:…]+)([\"»«„“]?)(\w.*)$")


def split_glued(words):
    """'resources,right?' / 'like"tiny' -> two words (Soniox sometimes omits the space after punctuation); the time is
    shared out by length. Numbers like 1,5 stay as they are."""
    out = []
    for w in words:
        t = w["t"]
        m = _GLUED.match(t)
        if not m or (m.group(1)[-2:-1].isdigit() and m.group(3)[:1].isdigit()) or len(re.sub(r"\W", "", m.group(3))) < 2:
            q = re.match(r'^(\w[\w-]*)(["»„“])(\w.*)$', t)  # a word glued to an opening quote: like"tiny
            if not q:
                out.append(w)
                continue
            a, b = q.group(1), q.group(2) + q.group(3)
        else:
            a, b = m.group(1), m.group(2) + m.group(3)
        mid = w["s"] + (w["e"] - w["s"]) * len(a) / max(1, len(a) + len(b))
        out += [{**w, "t": a, "e": round(mid)}, {**w, "t": b, "s": round(mid)}]
    return out


# One request per episode keeps the diarized speaker ids consistent from start to end (Soniox numbers speakers per
# request; stitching chunks had to guess who was who at every seam and sometimes swapped them). Only recordings longer
# than SINGLE_MAX are split.
SINGLE_MAX = 4 * 3600
CHUNK_S, OVERLAP_S, CONCURRENCY = 3600, 60, 4


def transcribe_long(audio, duration, ctx, extract, on_status=None, parts_path=None):
    """the whole recording in one request (consistent speaker ids); only past SINGLE_MAX in overlapping chunks"""
    say = on_status or (lambda m, p=None: None)
    if duration <= SINGLE_MAX:
        return tokens_to_words(transcribe_file(audio, ctx, lambda m: say(m)))
    return chunked(audio, duration, extract, lambda path, offset: tokens_to_words(transcribe_file(path, ctx), offset),
                   CHUNK_S, OVERLAP_S, CONCURRENCY, say, parts_path)
