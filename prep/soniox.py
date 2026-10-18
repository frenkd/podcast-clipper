"""Soniox speech-to-text: upload, transcribe, words with timings and diarized speakers. Long episodes go as
overlapping chunks in parallel and are stitched back at real pauses, with speaker ids kept consistent."""
import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

from .config import SONIOX_MODEL, require_key

API = "https://api.soniox.com/v1"


def _api(path, method="GET", body=None, headers=None):
    req = urllib.request.Request(API + path, data=body, method=method,
                                 headers={"Authorization": f"Bearer {require_key('SONIOX_API_KEY')}", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            data = r.read()
            return json.loads(data) if data else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Soniox {method} {path} -> {e.code}: {e.read().decode(errors='replace')[:500]}") from None


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


# One request per episode keeps the diarized speaker ids consistent from start to end (Soniox numbers speakers per
# request; stitching chunks had to guess who was who at every seam and sometimes swapped them). Only recordings longer
# than SINGLE_MAX are split.
SINGLE_MAX = 4 * 3600
CHUNK_S, OVERLAP_S, CONCURRENCY = 3600, 60, 4


def transcribe_long(audio, duration, ctx, extract, on_status=None, parts_path=None):
    """Transcribe a long recording as overlapping chunks in parallel, then stitch() them.
    extract(start_s, dur_s, out_path) cuts a chunk of the audio. parts_path: keep the raw chunk results there, so the
    stitching can be checked or redone without transcribing again."""
    say = on_status or (lambda m, p=None: None)
    if duration <= SINGLE_MAX:
        return tokens_to_words(transcribe_file(audio, ctx, lambda m: say(m)))
    step = CHUNK_S - OVERLAP_S
    starts = []
    s = 0.0
    while s < duration - OVERLAP_S:
        starts.append(s)
        s += step
    say(f"transcribing {len(starts)} parts in parallel", 0.1)
    done = [0]

    def part(k):
        start = starts[k]
        out = f"{os.path.splitext(audio)[0]}.part{k}{os.path.splitext(audio)[1]}"
        extract(start, min(CHUNK_S, duration - start), out)
        try:
            words = tokens_to_words(transcribe_file(out, ctx), round(start * 1000))
        finally:
            if os.path.exists(out):
                os.remove(out)
        done[0] += 1
        say(f"transcribed {done[0]}/{len(starts)} parts", 0.1 + 0.85 * done[0] / len(starts))
        return words

    with ThreadPoolExecutor(CONCURRENCY) as ex:
        results = list(ex.map(part, range(len(starts))))
    if parts_path:
        with open(parts_path, "w", encoding="utf-8") as fh:
            json.dump({"starts": starts, "overlap": OVERLAP_S, "parts": results}, fh, ensure_ascii=False)
    return stitch(results, [round(s * 1000) for s in starts], OVERLAP_S * 1000)


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
