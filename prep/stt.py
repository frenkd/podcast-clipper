"""Speech to text: which service transcribes (Soniox, ElevenLabs or OpenAI, whichever key is set), long recordings as
overlapping chunks in parallel, stitched back at real pauses with speaker ids kept consistent, and the words grouped
into subtitle-like cues. Words everywhere: {"t": text, "s": start ms, "e": end ms, "sp": speaker id as a string}."""
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor


DETECTED = {}  # what the last transcription found out by itself: {"language": "sl"}
_LANGS = {"english": "en", "slovenian": "sl", "slovene": "sl", "german": "de", "french": "fr", "spanish": "es",
          "italian": "it", "portuguese": "pt", "dutch": "nl", "polish": "pl", "croatian": "hr", "serbian": "sr",
          "czech": "cs", "slovak": "sk", "hungarian": "hu", "swedish": "sv", "danish": "da", "norwegian": "no",
          "finnish": "fi", "russian": "ru", "ukrainian": "uk", "japanese": "ja", "chinese": "zh", "korean": "ko",
          "eng": "en", "slv": "sl", "deu": "de", "ger": "de", "fra": "fr", "fre": "fr", "spa": "es", "ita": "it",
          "por": "pt", "nld": "nl", "dut": "nl", "pol": "pl", "hrv": "hr", "srp": "sr", "ces": "cs", "cze": "cs"}


def detected_language(value):
    """a service's language ("slovenian", "slv", "sl") as an ISO 639-1 code, or None"""
    v = (value or "").strip().lower()
    if len(v) == 2:
        return v
    return _LANGS.get(v)


PROVIDERS = {"soniox": "SONIOX_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY", "openai": "OPENAI_API_KEY"}  # preferred first


def provider():
    """"soniox", "elevenlabs" or "openai": STT in .env if set, else the first service in PROVIDERS whose key is there
    (Soniox and ElevenLabs: words and speakers in one request; OpenAI: one key for everything)"""
    forced = (os.environ.get("STT") or "").strip().lower()
    if forced:
        if forced not in PROVIDERS:
            raise SystemExit(f"STT={forced!r}: use one of {', '.join(PROVIDERS)}")
        if not os.environ.get(PROVIDERS[forced]):
            raise SystemExit(f"STT={forced} needs {PROVIDERS[forced]} in .env")
        return forced
    for name, key in PROVIDERS.items():
        if os.environ.get(key):
            return name
    raise SystemExit("no transcription key: add OPENAI_API_KEY (or ELEVENLABS_API_KEY or SONIOX_API_KEY) to .env")


def transcribe(audio, duration, ctx, extract, on_status=None, parts_path=None):
    """the whole recording -> words with speakers, from whichever service provider() picks"""
    if provider() == "soniox":
        from .soniox import transcribe_long
        return transcribe_long(audio, duration, ctx, extract, on_status, parts_path)
    if provider() == "elevenlabs":
        from .elevenlabs_stt import transcribe_long
        return transcribe_long(audio, duration, ctx, extract, on_status, parts_path)
    from .openai_stt import transcribe_long
    return transcribe_long(audio, duration, ctx, extract, on_status, parts_path)


def speakers(audio, duration, ctx, extract, on_status=None):
    """who talks when, for re-diarizing: words (Soniox, ElevenLabs) or speaker turns (OpenAI), each with s, e and sp"""
    if provider() == "soniox":
        from .soniox import tokens_to_words, transcribe_file
        return tokens_to_words(transcribe_file(audio, ctx))
    if provider() == "elevenlabs":
        from .elevenlabs_stt import transcribe_long
        return transcribe_long(audio, duration, ctx, extract, on_status)
    from .openai_stt import speaker_turns
    return speaker_turns(audio, duration, extract, on_status)


def chunked(audio, duration, extract, one, chunk_s, overlap_s, concurrency, on_status=None, parts_path=None,
            name="part", first_alone=False):
    """Run one(path, offset_ms) -> words on overlapping chunks of the recording in parallel and stitch() them.
    extract(start_s, dur_s, out_path) cuts a chunk. first_alone: the first chunk finishes before the others start
    (so one() can learn something from it, like what each voice sounds like). parts_path: keep the raw chunk
    results, so the stitching can be checked or redone without transcribing again."""
    say = on_status or (lambda m, p=None: None)
    starts, s = [], 0.0
    while s < duration - overlap_s or not starts:
        starts.append(s)
        s += chunk_s - overlap_s
    say(f"transcribing {len(starts)} {name}s in parallel" if len(starts) > 1 else "transcribing", 0.1)
    done = [0]
    ext = os.path.splitext(audio)[1]

    def part(k):
        start = starts[k]
        out = f"{os.path.splitext(audio)[0]}.{name}{k}{ext}"
        extract(start, min(chunk_s, duration - start), out)
        try:
            words = one(out, round(start * 1000))
        finally:
            if os.path.exists(out):
                os.remove(out)
        done[0] += 1
        if len(starts) > 1:
            say(f"transcribed {done[0]}/{len(starts)} {name}s", 0.1 + 0.85 * done[0] / len(starts))
        return words

    first = [part(0)] if first_alone else []
    with ThreadPoolExecutor(concurrency) as ex:
        results = first + list(ex.map(part, range(len(first), len(starts))))
    if parts_path:
        with open(parts_path, "w", encoding="utf-8") as fh:
            json.dump({"starts": starts, "overlap": overlap_s, "parts": results}, fh, ensure_ascii=False)
    return stitch(results, [round(s * 1000) for s in starts], overlap_s * 1000)


def post_audio(url, path, fields, headers, label, retries=4, timeout=900, key=None):
    """multipart POST of an audio file plus form fields ([(name, value)], repeats allowed) -> parsed JSON; retries
    rate limits, server errors and dropped connections with a growing wait"""
    boundary = uuid.uuid4().hex
    with open(path, "rb") as f:
        audio = f.read()
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields]
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{os.path.basename(path)}"'
                 f'\r\nContent-Type: audio/ogg\r\n\r\n'.encode() + audio + b"\r\n")
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, method="POST", headers={
            **headers, "Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:500]
            if e.code in (429, 500, 502, 503, 504) and attempt < retries and "quota" not in msg.lower():
                time.sleep(2 ** attempt * 3)
                continue
            from .config import api_error
            raise api_error(label, key or "its API key", e.code, msg) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt < retries:
                time.sleep(2 ** attempt * 3)
                continue
            raise


def words_to_cues(words, max_ms=7000, max_chars=90, pause_ms=900):
    """group words into readable subtitle-like cues"""
    cues, cur = [], None
    for w in words:
        split = (cur is None or (w.get("sp") and cur.get("sp") and w["sp"] != cur["sp"])
                 or (w["s"] - cur["e"] >= pause_ms and (len(cur["text"]) > 30 or w["s"] - cur["e"] >= 2 * pause_ms))
                 or w["s"] - cur["s"] >= max_ms or len(cur["text"]) + len(w["t"]) + 1 > max_chars
                 or (cur["text"][-1:] in ".!?" and len(cur["text"]) > 40))
        if split:
            if cur:
                cues.append(cur)
            cur = {"i": len(cues), "s": w["s"], "e": w["e"], "text": w["t"]}
            if w.get("sp"):
                cur["sp"] = w["sp"]
        else:
            cur["text"] += " " + w["t"]
            cur["e"] = w["e"]
    if cur:
        cues.append(cur)
    return cues



def _norm(t):
    return "".join(ch for ch in t.lower() if ch.isalnum())


def stitch(parts, starts_ms, overlap_ms):
    """Merge overlapping chunk transcripts. Speaker ids of each new chunk are remapped to the merged ones by words both
    chunks heard at the same time; each seam is cut at the best pause near the middle of the overlap."""
    merged = list(parts[0] if parts else [])
    for k in range(1, len(parts)):
        b = parts[k] or []
        ov0 = starts_ms[k]
        ov1 = ov0 + overlap_ms
        mid = (ov0 + ov1) / 2
        votes = {}
        for wb in b:
            if wb["s"] > ov1:
                break
            if not wb.get("sp"):
                continue
            wa = next((w for w in merged if w["s"] < wb["e"] and w["e"] > wb["s"] and _norm(w["t"]) == _norm(wb["t"])), None)
            if not wa or not wa.get("sp"):
                continue
            votes.setdefault(wb["sp"], {}).setdefault(wa["sp"], 0)
            votes[wb["sp"]][wa["sp"]] += 1
        used, mp = set(), {}
        ranked = sorted(((bsp, max(m.items(), key=lambda x: x[1])) for bsp, m in votes.items()), key=lambda x: -x[1][1])
        for bsp, (asp, _) in ranked:
            if asp not in used:
                mp[bsp] = asp
                used.add(asp)
        a_count, b_count = {}, {}
        for w in merged:
            if w.get("sp"):
                a_count[w["sp"]] = a_count.get(w["sp"], 0) + 1
        free_a = [sp for sp, _ in sorted(a_count.items(), key=lambda x: -x[1]) if sp not in used]
        for w in b:
            if w.get("sp") and w["sp"] not in mp:
                b_count[w["sp"]] = b_count.get(w["sp"], 0) + 1
        for bsp, _ in sorted(b_count.items(), key=lambda x: -x[1]):  # silent in the overlap: most talkative first
            if free_a:
                mp[bsp] = free_a.pop(0)
        next_id = max([0] + [int(w["sp"]) for w in merged if str(w.get("sp", "")).isdigit()]) + 1
        nb = []
        for w in b:
            if w.get("sp"):
                if w["sp"] not in mp:
                    mp[w["sp"]] = str(next_id)
                    next_id += 1
                w = {**w, "sp": mp[w["sp"]]}
            nb.append(w)
        best, best_score = mid, float("-inf")
        for w, n in zip(merged, merged[1:]):
            if w["e"] < ov0 + overlap_ms * 0.15 or n["s"] > ov1 - overlap_ms * 0.15:
                continue
            t = (w["e"] + n["s"]) / 2
            if any(x["s"] < t < x["e"] for x in nb):
                continue
            score = min(n["s"] - w["e"], 1200) - abs(t - mid) * 0.08 + (250 if w["t"][-1:] in ".!?" else 0)
            if score > best_score:
                best, best_score = t, score
        merged = [w for w in merged if w["e"] <= best] + [w for w in nb if w["s"] >= best]
    return merged
