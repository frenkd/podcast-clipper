"""The prep pipeline: notes -> context (brief, people, glossary) -> transcribe (Soniox, or good subtitles) -> clean
(LLM pass with the glossary). Its output, work/words.json and work/transcript.clean.json, is what clips/ reads."""
import os
import re
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor

from . import prompts
from .files import video_path
from .fixes import apply_fixes
from .llm import arr, integer, llm_json, obj, string
from .media import extract_audio, probe
from . import stt
from .stt import words_to_cues
from .store import get_project, now, read_json, set_step, source_dir, update_project, work_dir, write_json
from .subtitles import cues_for_prompt, parse_subtitles


def transcript_path(pid):
    return os.path.join(work_dir(pid), "transcript.json")


def clean_path(pid):
    return os.path.join(work_dir(pid), "transcript.clean.json")


def run_step(pid, step, fn):
    """run a step, recording status / progress / errors in project.json"""
    set_step(pid, step, status="running", message="starting", progress=0, error=None, startedAt=now(), pid=os.getpid())

    def report(message, progress=None):
        print(f"  {step}: {message}", flush=True)
        set_step(pid, step, message=message, progress=progress)
    try:
        fn(report)
    except BaseException as e:
        set_step(pid, step, status="error", error=str(e) or type(e).__name__, finishedAt=now(), message=None)
        if not isinstance(e, (SystemExit, KeyboardInterrupt)):
            traceback.print_exc(file=sys.stderr)
        raise
    set_step(pid, step, status="done", message=None, progress=1, finishedAt=now())


def is_done(p, step):
    return p["steps"].get(step, {}).get("status") == "done"


def _read(pid, name):
    try:
        return open(os.path.join(source_dir(pid), name), encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def step_context(pid):
    """read the notes: a short brief, who talks, a glossary of names and terms, the episode code"""
    def go(report):
        p = get_project(pid)
        report("reading notes")
        parts = [f"Project title: {p['title']}"]
        for f in p["files"]:
            if f["kind"] == "video":
                parts.append(f"Video file name: {f['name']}")
            elif f["kind"] == "context":
                parts.append(f"--- {f['name']}\n{_read(pid, f['name'])[:40000]}")
            elif f["kind"] == "subtitles":
                cues = parse_subtitles(_read(pid, f["name"]))
                parts.append(f"--- rough subtitles {f['name']} (first part)\n" + " ".join(c["text"] for c in cues[:120])[:6000])
        out = llm_json(prompts.CONTEXT, "\n\n".join(parts), obj(
            brief=string(), speakers=arr(string()), host=string(), language=string("ISO 639-1 code"),
            glossary=arr(string()), slug=string(),
            episode_code=string("Season/episode code like S05E07 if the notes state it (prefer episode pages/descriptions "
                                "over file names), else empty"),
            episode_title=string("The episode's published title (often 'Guest Name: Topic'), without the code or the "
                                 "show's name, if the notes state it, else empty"),
            subtitles_quality=string("Are the rough subtitles (if any) accurate enough to find clips from? 'rough' if "
                                     "they contain hallucinated/foreign text, duplicated or garbled lines.",
                                     enum=["good", "rough", "none"])), name="context", model="fast")

        def f(p):
            p["brief"] = out["brief"]
            fixed = [f["to"] for f in p.get("fixes") or [] if f["to"][:1].isupper()]  # names from ./clip fix stay
            p["glossary"] = list(dict.fromkeys(s.strip() for s in out["speakers"] + out["glossary"] + fixed if s.strip()))
            host = out["host"] if out["host"] in out["speakers"] else (out["speakers"] or [""])[0]
            p["people"] = [host] + [s for s in out["speakers"] if s != host] if host else out["speakers"]
            p["host"] = host
            p["language"] = out["language"]
            if any(x["kind"] == "subtitles" for x in p["files"]):
                p["subtitlesQuality"] = out["subtitles_quality"]
            if out["episode_title"].strip() and not p.get("episodeTitle"):
                p["episodeTitle"] = out["episode_title"].strip()
            m = re.search(r"S\d{1,2}E\d{1,3}", out["episode_code"], re.I)
            if m and not p.get("episode"):
                p["episode"] = m.group(0).upper()
        update_project(pid, f)
    run_step(pid, "context", go)


def step_transcribe(pid, use_subtitles=None):
    """speech to text (Soniox or OpenAI, stt.py; or the episode's subtitles if they're good) -> work/words.json +
    work/transcript.json"""
    def go(report):
        p = get_project(pid)
        subs = next((f for f in p["files"] if f["kind"] == "subtitles"), None)
        trust = use_subtitles if use_subtitles is not None else p.get("subtitlesQuality") == "good"
        if subs and trust:
            report("reading subtitles")
            cues = parse_subtitles(_read(pid, subs["name"]))
            if len(cues) < 5:
                raise SystemExit("the subtitles file looks empty")
            write_json(transcript_path(pid), {"source": "subtitles", "cues": cues})
            update_project(pid, lambda p: p.update(transcriptSource="subtitles"))
            apply_fixes(pid)
            return
        video = video_path(p)
        audio = os.path.join(work_dir(pid), "audio.opus")
        if not os.path.exists(audio):
            report("extracting audio", 0.05)
            extract_audio(video, audio)
        cached = read_json(os.path.join(work_dir(pid), "words.json"))
        people = p.get("people") or []
        source = stt.provider()
        words = cached or stt.transcribe(
            audio, (p.get("video") or {}).get("duration") or probe(video)["duration"],
            {"topic": p.get("brief") or p["title"], "speakers": ", ".join(people) or None, "text": p.get("brief"),
             "terms": p["glossary"], "language": p.get("language")},
            lambda start, dur, out: extract_audio(audio, out, start, dur), report,
            parts_path=os.path.join(work_dir(pid), f"{source}.parts.json"))
        write_json(os.path.join(work_dir(pid), "words.json"), words)
        write_json(transcript_path(pid), {"source": source, "cues": words_to_cues(words), "words": words})
        update_project(pid, lambda p: p.update(transcriptSource=source))
        apply_fixes(pid)
    run_step(pid, "transcribe", go)


def speaker_stats(words):
    """per diarized speaker: words spoken and questions asked per 1000 words"""
    st = {}
    for w in words:
        sp = str(w.get("sp"))
        d = st.setdefault(sp, {"words": 0, "qs": 0})
        d["words"] += 1
        d["qs"] += "?" in w["t"]
    for d in st.values():
        d["q"] = 1000 * d["qs"] / max(1, d["words"])
    return st


def check_host(names, st, host):
    """The LLM sometimes swaps who is who. In an interview the host asks the questions and talks less: if one speaker
    clearly does that and the map gives the host's name to someone else, swap the two names."""
    main = sorted((sp for sp in st if st[sp]["words"] >= 200), key=lambda sp: -st[sp]["q"])
    if len(main) != 2 or not host:  # only for a two-person interview; in a group chat everyone asks
        return names
    a, b = main[0], main[1]
    clear = st[a]["q"] >= 1.8 * max(st[b]["q"], 0.5) and st[a]["words"] <= 0.75 * st[b]["words"]
    holder = next((sp for sp, n in names.items() if n == host), None)
    if clear and holder and holder != a:
        names = dict(names)
        names[holder], names[a] = names.get(a, "Unknown"), host
    return names


def step_speakers(pid):
    """re-diarize without touching the words: who talks when, fresh from the speech-to-text service, then every
    existing word gets the speaker of what it overlaps (keeps word timings, fixes and clip scripts as they are)"""
    def go(report):
        p = get_project(pid)
        audio = os.path.join(work_dir(pid), "audio.opus")
        if not os.path.exists(audio):
            report("extracting audio")
            extract_audio(video_path(p), audio)
        report("transcribing for speakers")
        ctx = {"topic": p.get("brief") or p["title"], "speakers": ", ".join(p.get("people") or []) or None,
               "text": p.get("brief"), "terms": p["glossary"], "language": p.get("language")}
        fresh = stt.speakers(audio, (p.get("video") or {}).get("duration") or probe(video_path(p))["duration"], ctx,
                             lambda start, dur, out: extract_audio(audio, out, start, dur))
        wp = os.path.join(work_dir(pid), "words.json")
        words = read_json(wp)
        k = 0
        for w in words:
            while k < len(fresh) - 1 and fresh[k]["e"] < w["s"]:
                k += 1
            near = [f for f in fresh[max(0, k - 2):k + 3] if f["s"] < w["e"] + 150 and f["e"] > w["s"] - 150 and f.get("sp")]
            if near:
                w["sp"] = max(near, key=lambda f: min(f["e"], w["e"]) - max(f["s"], w["s"]))["sp"]
        write_json(wp, words)
        tr = read_json(transcript_path(pid))
        if tr and tr.get("source") in stt.PROVIDERS:
            write_json(transcript_path(pid), {**tr, "cues": words_to_cues(words), "words": words})
    run_step(pid, "speakers", go)


CHUNK = 45  # cues per cleanup call: bigger chunks make the model slide text from one cue into the next


def faithful(raw, cleaned):
    """is the cleaned cue still what was said? A translation or a rewrite shares few words with the original;
    corrections (names, punctuation, fillers, an added clarification in parentheses) keep most of them."""
    norm = lambda t: ["".join(ch for ch in w.lower() if ch.isalnum()) for w in t.split()]
    a = [w for w in norm(raw) if len(w) > 2]
    if len(a) < 4:
        return True
    b = set(norm(re.sub(r"\([^)]*\)", "", cleaned)))
    return sum(1 for w in a if w in b) / len(a) >= 0.4


def step_clean(pid):
    """who is who, then the LLM cleanup of the transcript in parallel chunks -> work/transcript.clean.json"""
    def go(report):
        p = get_project(pid)
        tr = read_json(transcript_path(pid))
        if not tr:
            raise SystemExit("no transcript yet")
        people = p.get("people") or []
        if people and any(c.get("sp") for c in tr["cues"]):
            report("identifying speakers", 0.02)
            ids = list(dict.fromkeys(c["sp"] for c in tr["cues"] if c.get("sp")))
            st = speaker_stats(read_json(os.path.join(work_dir(pid), "words.json")) or tr.get("words") or [])
            stats = "\n".join(f"S{i}: {st[i]['words']} words, {st[i]['q']:.1f} questions per 1000 words" for i in ids if i in st)
            who = llm_json(prompts.SPEAKERS,
                           f"People in this episode: {', '.join(people)} (host: {p.get('host') or people[0]})\n"
                           f"Speaker ids: {', '.join('S' + i for i in ids)}\n{stats}\n\n{cues_for_prompt(tr['cues'][:160])}",
                           obj(speakers=arr(obj(id=string("id without the S prefix"), name=string()))),
                           name="speakers", model="fast")
            names = check_host({s["id"].lstrip("S"): s["name"] for s in who["speakers"]}, st, p.get("host") or people[0])
            update_project(pid, lambda p: p.update(speakers=names))
        chunks = [tr["cues"][i:i + CHUNK] for i in range(0, len(tr["cues"]), CHUNK)]
        done = [0]

        def ask(ci, model):
            prev = " ".join(c["text"] for c in chunks[ci - 1][-4:]) if ci else ""
            cues = "\n".join(f"{c['i']}\t{c['text']}" for c in chunks[ci])
            out = llm_json(prompts.CLEAN, f"Episode: {p['title']}\nAbout: {p.get('brief') or ''}\n"
                                          f"Glossary: {', '.join(p['glossary'])}\n\nPrevious context (do not return): "
                                          f"{prev}\n\nCues:\n{cues}",
                           obj(cues=arr(obj(id=integer(), text=string()))), name="clean", model=model)
            by = {c["id"]: c["text"] for c in out["cues"]}
            texts = [(c, (by.get(c["i"]) or c["text"]).strip()) for c in chunks[ci]]
            return texts, sum(1 for c, t in texts if not faithful(c["text"], t))

        def clean(ci):
            texts, bad = ask(ci, "fast")
            if bad > max(2, 0.08 * len(texts)):  # text slid between cues (or got translated): once more, carefully
                texts2, bad2 = ask(ci, "smart")
                if bad2 < bad:
                    texts, bad = texts2, bad2
            done[0] += 1
            report(f"cleaning transcript {done[0]}/{len(chunks)}", done[0] / len(chunks))
            res = []
            for c, new in texts:
                if not faithful(c["text"], new):
                    reverted[0] += 1
                    rejected.append({"i": c["i"], "said": c["text"], "cleaned": new})
                    new = c["text"]
                res.append({**c, "text": new})
            return res

        reverted, rejected = [0], []
        with ThreadPoolExecutor(6) as ex:
            cleaned = [c for part in ex.map(clean, range(len(chunks))) for c in part if c["text"]]
        if reverted[0]:
            report(f"kept the original wording of {reverted[0]} cue(s) the cleanup changed too much (translated?); "
                   "see work/clean.rejected.json")
        write_json(os.path.join(work_dir(pid), "clean.rejected.json"), sorted(rejected, key=lambda r: r["i"]))
        write_json(clean_path(pid), {k: v for k, v in {**tr, "cues": cleaned}.items() if k != "words"})
        apply_fixes(pid)
    run_step(pid, "clean", go)


def auto_run(pid):
    """every step that isn't done yet"""
    video_path(get_project(pid))
    for step, fn in (("context", step_context), ("transcribe", step_transcribe), ("clean", step_clean)):
        if not is_done(get_project(pid), step):
            fn(pid)
