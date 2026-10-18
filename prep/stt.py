"""Speech to text: which service transcribes (Soniox when its key is set, else OpenAI), long recordings as
overlapping chunks in parallel, stitched back at real pauses with speaker ids kept consistent, and the words grouped
into subtitle-like cues. Words everywhere: {"t": text, "s": start ms, "e": end ms, "sp": speaker id as a string}."""
import json
import os
from concurrent.futures import ThreadPoolExecutor


def provider():
    """"soniox" or "openai": STT in .env if set, else Soniox when its key is there (better names, one request per
    episode), else OpenAI (one key for everything)"""
    forced = (os.environ.get("STT") or "").strip().lower()
    if forced:
        if forced not in ("soniox", "openai"):
            raise SystemExit(f"STT={forced!r}: use soniox or openai")
        return forced
    if os.environ.get("SONIOX_API_KEY"):
        return "soniox"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    raise SystemExit("no transcription key: add OPENAI_API_KEY (or SONIOX_API_KEY) to .env")


def transcribe(audio, duration, ctx, extract, on_status=None, parts_path=None):
    """the whole recording -> words with speakers, from whichever service provider() picks"""
    if provider() == "soniox":
        from .soniox import transcribe_long
        return transcribe_long(audio, duration, ctx, extract, on_status, parts_path)
    from .openai_stt import transcribe_long
    return transcribe_long(audio, duration, ctx, extract, on_status, parts_path)


def speakers(audio, duration, ctx, extract, on_status=None):
    """who talks when, for re-diarizing: words (Soniox) or speaker turns (OpenAI), each with s, e and sp"""
    if provider() == "soniox":
        from .soniox import tokens_to_words, transcribe_file
        return tokens_to_words(transcribe_file(audio, ctx))
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
