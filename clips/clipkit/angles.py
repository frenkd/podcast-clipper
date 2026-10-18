"""Camera angles and who sits where, for the whole episode.

analyse() samples the video about once a second (keyframes only, so it's quick), groups the samples into camera
angles by picture structure, finds the face "slots" of each angle and matches every slot to a diarized speaker by
mouth movement while that speaker talks. Result: work/angles.json (+ angles.npz with the angle fingerprints) and
work/angles.jpg, a labelled contact sheet the agent checks once per episode. Wrong guesses are fixed by editing
angles.json (a slot's "speaker", an angle's "skip"); the engine reads it back and never overwrites hand edits.

Typical podcast: 2-3 angles (a close-up per person, a wide two-shot), 2-3 speakers. Up to ~8 angles and 4 speakers
are handled; anything that appears less than 1% of the time (titles, B-roll) is ignored.
"""
import itertools, json, os, re, subprocess
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

from .project import CACHE, F_MENLO, GUEST, GUESTS, HOST, PROJECT, SH, SW, VIDEO, WORK, WORDS_JSON

JSON = os.path.join(WORK, "angles.json")
NPZ = os.path.join(WORK, "angles.npz")
SHEET = os.path.join(WORK, "angles.jpg")
SAME_ANGLE = 0.62   # fingerprint similarity above which two samples are the same camera angle
MIN_SHARE = 0.01


# ---- fingerprints: the structure (edges) of a 64x36 grey thumbnail; lighting and small movement barely change it
def fingerprint(thumb):
    g = cv2.GaussianBlur(thumb.astype(np.float32), (3, 3), 0)
    e = np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1))
    e = e - e.mean()
    return (e / (np.linalg.norm(e) + 1e-6)).ravel()


def _samples():
    """(times, 64x36 grey thumbnails) of every keyframe, at most ~1 per second"""
    path = os.path.join(CACHE, "angle_samples.npz")
    if os.path.exists(path):
        d = np.load(path)
        return d["t"], d["th"]
    p = subprocess.run(["ffmpeg", "-hide_banner", "-skip_frame", "nokey", "-i", VIDEO, "-vf",
                        "scale=64:36,format=gray,showinfo", "-fps_mode", "vfr", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                       capture_output=True)
    th = np.frombuffer(p.stdout, np.uint8).reshape(-1, 36, 64)
    t = np.array([float(x) for x in re.findall(r"pts_time:([0-9.]+)", p.stderr.decode(errors="replace"))])[:len(th)]
    th = th[:len(t)]
    keep, last = [], -9.0
    for i, x in enumerate(t):
        if x - last >= 0.9:
            keep.append(i)
            last = x
    t, th = t[keep], th[keep]
    np.savez(path, t=t, th=th)
    return t, th


def _cluster(F):
    """greedy leader clustering + two refinement passes -> labels, centroids (unit vectors)"""
    cents = []
    for f in F:
        if cents and max(float(c @ f) for c in cents) >= SAME_ANGLE:
            continue
        cents.append(f)
    C = np.stack(cents)
    for _ in range(3):
        lab = (F @ C.T).argmax(1)
        C = np.stack([F[lab == k].mean(0) for k in range(len(C)) if (lab == k).any()])
        C /= np.maximum(np.linalg.norm(C, axis=1, keepdims=True), 1e-6)
        # merge angles that turned out to be the same
        keep = []
        for k in range(len(C)):
            if all(float(C[k] @ C[j]) < 0.8 for j in keep):
                keep.append(k)
        C = C[keep]
    lab = (F @ C.T).argmax(1)
    return lab, C


# ---- faces
from .faces import SIZE_SCALE, detect, faces_in  # noqa: E402


def _frame(t, w=None):
    vf = ["-vf", f"scale={w}:-2"] if w else []
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", VIDEO, "-frames:v", "1", *vf,
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    ww = w or SW
    hh = len(raw) // (ww * 3)
    return np.frombuffer(raw, np.uint8).reshape(hh, ww, 3) if hh else None


def _slots(times):
    """face slots of one angle: faces that show up in the same place in at least ~30% of its frames.
    -> (slots, frames) with each slot's look (colour of face + clothes) for matching people across angles"""
    frames = [f for f in (_frame(t) for t in times) if f is not None]
    dets = [faces_in(f) for f in frames]
    pts = [(d, i) for i, ds in enumerate(dets) for d in ds]
    slots = []
    for p, i in sorted(pts, key=lambda q: -q[0][2]):
        for s in slots:
            if abs(p[0] - s["x"]) < 0.7 * s["size"] and abs(p[1] - s["y"]) < 0.7 * s["size"]:
                s["hits"].append((p, i))
                break
        else:
            slots.append({"x": p[0], "y": p[1], "size": p[2], "hits": [(p, i)]})
    out = []
    for s in slots:
        if len(s["hits"]) >= max(2, 0.3 * len(dets)):
            h = np.array([p for p, _ in s["hits"]])
            looks = [_look(frames[i], p) for p, i in s["hits"]]
            out.append({"x": float(np.median(h[:, 0])), "y": float(np.median(h[:, 1])), "size": float(np.median(h[:, 2])),
                        "_look": np.mean([l for l in looks if l is not None], 0) if any(l is not None for l in looks) else None,
                        "_sharp": float(np.median([_sharpness(frames[i], p) for p, i in s["hits"]]))})
    # not faces: anything in the bottom third (hands, mics, knees), or right under a bigger face (a logo on a shirt)
    out = [s for s in out if s["y"] < 0.66 * SH and not any(
        o is not s and o["size"] >= 0.8 * s["size"] and abs(o["x"] - s["x"]) < 0.9 * o["size"] and
        0 < s["y"] - o["y"] < 3.0 * o["size"] for o in out)]
    # not a speaker: a head far softer than the sharpest face in the shot (the out-of-focus foreground shoulder/head)
    top = max([s["_sharp"] for s in out] or [0])
    out = [s for s in out if s["_sharp"] >= 0.25 * top]
    return sorted(out, key=lambda s: s["x"])


def _sharpness(rgb, face):
    x, y, r = face
    g = cv2.cvtColor(rgb[int(max(0, y - r / 2)):int(y + r / 2), int(max(0, x - r / 2)):int(x + r / 2)], cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(cv2.resize(g, (96, 96)), cv2.CV_32F).var()) if g.size else 0.0


def _look(rgb, face):
    """colour signature of a person: hue/saturation histogram of the face and the clothes under it"""
    x, y, r = face
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    parts = []
    for y0, y1, w in ((y - 0.5 * r, y + 0.5 * r, 0.5), (y + 0.9 * r, y + 2.2 * r, 0.9)):
        box = hsv[int(max(0, y0)):int(min(rgb.shape[0], y1)), int(max(0, x - w * r)):int(min(rgb.shape[1], x + w * r))]
        if box.size == 0:
            return None
        hist = cv2.calcHist([box], [0, 1, 2], None, [12, 4, 4], [0, 180, 0, 256, 0, 256]).ravel()
        parts.append(hist / (hist.sum() + 1e-6))
    v = np.concatenate(parts)
    return v / (np.linalg.norm(v) + 1e-6)


# ---- speakers
def _words():
    return [dict(s=w["s"] / 1000, e=w["e"] / 1000, sp=str(w.get("sp"))) for w in json.load(open(WORDS_JSON))]


def _talker(words, t):
    """the only speaker talking around t (None if nobody or several)"""
    near = {w["sp"] for w in words if w["s"] - 0.15 <= t <= w["e"] + 0.15}
    return near.pop() if len(near) == 1 else None


def _clip3(t):
    """three frames, 1/8 s apart, from t (960 px wide)"""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", VIDEO, "-vf", "fps=8,scale=960:-2",
                          "-frames:v", "3", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    h = len(raw) // (960 * 3 * 3)
    return np.frombuffer(raw, np.uint8).reshape(3, h, 960, 3) if h else None


def _mouth_activity(t, slots):
    """for each slot: how much the mouth moves relative to the whole face over 1/4 s (None if that face isn't found).
    Someone talking moves their mouth more than their head; listeners don't."""
    fr = _clip3(t)
    if fr is None:
        return None
    k = 960 / SW
    dets = detect(fr[0])
    g = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY).astype(np.float32) for f in fr]
    diff = np.abs(g[1] - g[0]) + np.abs(g[2] - g[1])
    out = []
    for sl in slots:
        near = [d for d in dets if abs(d["x"] - sl["x"] * k) < 0.7 * sl["size"] * k and abs(d["y"] - sl["y"] * k) < 0.7 * sl["size"] * k]
        if not near:
            out.append(None)
            continue
        d = min(near, key=lambda d: abs(d["x"] - sl["x"] * k) + abs(d["y"] - sl["y"] * k))
        (m1x, m1y), (m2x, m2y) = d["mouth"]
        cx, cy = (m1x + m2x) / 2, (m1y + m2y) / 2
        mw = max(8.0, 1.4 * abs(m2x - m1x))
        mouth = diff[int(max(0, cy - 0.35 * mw)):int(cy + 0.5 * mw), int(max(0, cx - mw / 2)):int(cx + mw / 2)]
        w = d["size"] / SIZE_SCALE
        face = diff[int(max(0, d["y"] - w / 2)):int(d["y"] + w / 2), int(max(0, d["x"] - w / 2)):int(d["x"] + w / 2)]
        out.append(float(mouth.mean() / (face.mean() + 2.0)) if mouth.size and face.size else None)
    return out


def _best_match(score):
    """one-to-one slot -> speaker matching maximising the total score -> [(slot, speaker_index, margin)]"""
    n, m = score.shape
    best, best_v = [], -1e9
    k = min(n, m)
    for slots_i in itertools.permutations(range(n), k):
        for perm in itertools.permutations(range(m), k):
            v = sum(score[i, j] for i, j in zip(slots_i, perm))
            if v > best_v:
                best, best_v = list(zip(slots_i, perm)), v
    return [(i, j, float(score[i, j] - max([score[i, x] for x in range(m) if x != j] or [0]))) for i, j in best]


def _assign(angles, samples, words, speakers):
    """Who is in which slot, from what the picture shows while each person talks:
    - mouth movement: at moments when exactly one person talks, the face whose mouth moves (relative to its own
      head) is probably theirs. Works for close-ups, two-shots and wide shots alike.
    - for a close-up also who talks while it's on screen, relative to how much they talk overall (editors cut to
      whoever speaks).
    Confident slots then lend their look (colour of face + clothes) to label the rest, one-to-one per angle."""
    from concurrent.futures import ThreadPoolExecutor
    total = {sp: 0 for sp in speakers}
    for t in samples:
        sp = _talker(words, t)
        if sp in total:
            total[sp] += 1
    base = {sp: (total[sp] + 1) / (sum(total.values()) + len(speakers)) for sp in speakers}
    for a in angles:
        if a.get("skip") or not a["slots"]:
            continue
        talk = [t for t in a["_times"] if _talker(words, t) in speakers]
        pick = [talk[int(i)] for i in np.linspace(0, len(talk) - 1, min(36, len(talk)))] if talk else []
        with ThreadPoolExecutor(4) as ex:
            acts = list(ex.map(lambda t: _mouth_activity(t, a["slots"]), pick))
        n, m = len(a["slots"]), len(speakers)
        votes, sums, cnt = np.zeros((n, m)), np.zeros((n, m)), np.zeros((n, m))
        for t, act in zip(pick, acts):
            if not act:
                continue
            j = speakers.index(_talker(words, t))
            vals = [(i, v) for i, v in enumerate(act) if v is not None]
            for i, v in vals:
                sums[i, j] += v
                cnt[i, j] += 1
            if len(vals) >= 2:
                vals.sort(key=lambda x: -x[1])
                if vals[0][1] > 1.15 * vals[1][1]:
                    votes[vals[0][0], j] += 1
        mean = sums / np.maximum(cnt, 1)
        rel = np.where(cnt > 0, mean / (mean.sum(1, keepdims=True) / np.maximum((cnt > 0).sum(1, keepdims=True), 1) + 1e-6), 1.0)
        score = np.log(np.maximum(rel, 0.05))                          # mouth moves more when this speaker talks
        if n > 1:
            score += 2.0 * votes / np.maximum(votes.sum(0, keepdims=True), 1)   # ... and more than the other faces
        else:
            c = np.array([sum(1 for t in a["_times"] if _talker(words, t) == sp) for sp in speakers], float)
            lift = (c + 0.5) / (c.sum() + 1) / np.array([base[sp] for sp in speakers])
            score += np.log(lift)[None, :]
        for i, j, margin in _best_match(score):
            a["slots"][i]["speaker"] = speakers[j]
            a["slots"][i]["confidence"] = round(margin, 2)
        a["_score"] = score
    # second pass: the confident slots teach what each person looks like (colour of face + clothes); every slot's
    # score gets that similarity added, so the same person keeps one identity across punch-ins and handheld variants
    refs = {}
    for a in angles:
        for sl in a["slots"]:
            if sl.get("speaker") and sl.get("_look") is not None:
                refs.setdefault(sl["speaker"], []).append((sl.get("confidence", 0), sl["_look"]))
    # each person's look: their confident slots, or at least their single best one
    refs = {sp: np.mean([l for c, l in v if c >= 1.0] or [max(v, key=lambda x: x[0])[1]], 0)
            for sp, v in refs.items() if max(c for c, _ in v) >= 0.25}
    if len(refs) >= 2:
        for a in angles:
            if a.get("skip") or "_score" not in a:
                continue
            look = np.zeros(a["_score"].shape)
            for i, sl in enumerate(a["slots"]):
                if sl.get("_look") is None:
                    continue
                sims = np.array([float(sl["_look"] @ refs[sp]) if sp in refs else np.nan for sp in speakers])
                if np.isfinite(sims).sum() >= 2:
                    look[i] = np.nan_to_num(sims - np.nanmean(sims))
            for i, j, margin in _best_match(a["_score"] + 6.0 * look):
                a["slots"][i]["speaker"] = speakers[j]
                a["slots"][i]["confidence"] = round(margin, 2)
    # propagate: weak slots are matched by look alone
    refs = {}
    for a in angles:
        for sl in a["slots"]:
            if sl.get("speaker") and sl.get("confidence", 0) >= 0.4 and sl.get("_look") is not None:
                refs.setdefault(sl["speaker"], []).append(sl["_look"])
    refs = {sp: np.mean(v, 0) for sp, v in refs.items()}
    if len(refs) >= 2:
        people = list(refs)
        for a in angles:
            weak = [sl for sl in a["slots"] if sl.get("confidence", 0) < 0.4 and sl.get("_look") is not None]
            taken = {sl["speaker"] for sl in a["slots"] if sl not in weak and sl.get("speaker")}
            free = [p for p in people if p not in taken]
            if not weak or not free:
                continue
            sim = np.array([[float(sl["_look"] @ refs[p]) for p in free] for sl in weak])
            for i, j, margin in _best_match(sim):
                weak[i]["speaker"], weak[i]["confidence"] = free[j], round(margin, 2)
                weak[i]["by"] = "look"


def _names(words, speakers):
    """who is who: prep's speaker map (an LLM read the opening of the conversation) if it has one, else a guess:
    the host asks the questions"""
    known = {str(k): v for k, v in (PROJECT.get("speakers") or {}).items() if v and v != "Unknown"}
    if all(s in known for s in speakers):
        return {s: known[s] for s in speakers}
    people = PROJECT.get("people") or []
    guests = list(GUESTS)
    hostname = HOST
    if len(speakers) < 2:
        return {}
    text = [(str(w.get("sp")), w) for w in json.load(open(WORDS_JSON))]
    n = {sp: max(1, sum(1 for s, _ in text if s == sp)) for sp in speakers}
    q = {sp: sum(1 for s, w in text if s == sp and "?" in w["t"]) / n[sp] for sp in speakers}
    share = {sp: n[sp] / sum(n.values()) for sp in speakers}
    hs = max(speakers, key=lambda s: q[s] * 10 + (1 - share[s]))  # asks more, talks less
    out = {hs: hostname or "host"}
    rest = [s for s in speakers if s != hs]
    for s, g in zip(rest, guests or []):
        out[s] = g
    return out


def analyse(force=False):
    """run (or load) the episode's angle analysis -> dict as stored in angles.json"""
    if os.path.exists(JSON) and os.path.exists(NPZ) and not force:
        return load()
    print("angles: sampling the episode (once per episode, a few minutes)…", flush=True)
    t, th = _samples()
    keep = th.reshape(len(th), -1).std(1) > 4  # black frames, fades and flat titles say nothing about the camera
    t, th = t[keep], th[keep]
    F = np.stack([fingerprint(x) for x in th])
    lab, C = _cluster(F)
    words = _words()
    counts = {}
    for w in words:
        counts[w["sp"]] = counts.get(w["sp"], 0) + 1
    speakers = sorted([s for s, c in counts.items() if c >= 0.03 * len(words)], key=lambda s: -counts[s])
    angles = []
    order = sorted(range(len(C)), key=lambda k: -(lab == k).sum())
    for rank, k in enumerate(order):
        share = float((lab == k).mean())
        mt = t[lab == k]
        a = {"id": chr(65 + rank), "share": round(share, 3), "examples": [round(float(x), 1) for x in
             mt[np.linspace(0, len(mt) - 1, min(4, len(mt))).astype(int)]]}
        if share < MIN_SHARE:
            a["skip"] = True
            a["slots"] = []
        else:
            print(f"angles: {a['id']} ({share:.0%} of the episode): finding faces…", flush=True)
            a["slots"] = _slots(mt[np.linspace(0, len(mt) - 1, min(10, len(mt))).astype(int)])
        a["_times"] = mt
        angles.append(a)
    _assign(angles, t, words, speakers)
    for a in angles:
        a.pop("_times", None)
        a.pop("_score", None)
        for s in a["slots"]:
            s.pop("_look", None)
            s.pop("_sharp", None)
    names = _names(words, speakers)
    data = {"speakers": {s: {"name": names.get(s, f"speaker {s}"), "words": counts[s]} for s in speakers},
            "angles": angles}
    np.savez(NPZ, ids=np.array([a["id"] for a in angles]), C=C[order])
    json.dump(data, open(JSON, "w"), indent=1, ensure_ascii=False)
    sheet(data)
    print(f"angles: {len([a for a in angles if not a.get('skip')])} angles, {len(speakers)} speakers -> {JSON}, check {SHEET}")
    return load()


def load():
    data = json.load(open(JSON))
    d = np.load(NPZ)
    fp = dict(zip([str(x) for x in d["ids"]], d["C"]))
    for a in data["angles"]:
        a["fp"] = fp.get(a["id"])
    return data


def classify(data, fps):
    """angle of a shot from its frames' fingerprints (None if it matches nothing well, e.g. a title card)"""
    ok = [a for a in data["angles"] if not a.get("skip") and a.get("fp") is not None]
    if not ok:
        return None
    m = np.mean(fps, 0)
    m /= np.linalg.norm(m) + 1e-6
    sims = [float(a["fp"] @ m) for a in ok]
    i = int(np.argmax(sims))
    return ok[i] if sims[i] >= SAME_ANGLE * 0.85 else None


def sheet(data=None):
    """contact sheet: a row per angle, example frames with the face slots and who the engine thinks they are"""
    data = data or load()
    names = {s: v["name"] for s, v in data["speakers"].items()}
    rows = [a for a in data["angles"] if not a.get("skip")]
    tw, th = 384, 216
    im = Image.new("RGB", (160 + 4 * tw, max(1, len(rows)) * (th + 8)), (24, 24, 24))
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(F_MENLO, 18)
    for r, a in enumerate(rows):
        y = r * (th + 8)
        d.text((8, y + 8), f"angle {a['id']}\n{a['share']:.0%}\n{len(a['slots'])} face(s)", font=f, fill=(255, 255, 255))
        for c, t in enumerate(a["examples"][:4]):
            fr = _frame(t, tw)
            if fr is None:
                continue
            tile = Image.fromarray(fr)
            td = ImageDraw.Draw(tile)
            k = tw / SW
            for s in a["slots"]:
                x, yy, z = s["x"] * k, s["y"] * k, s["size"] * k
                td.rectangle((x - z / 2, yy - z / 2, x + z / 2, yy + z / 2), outline=(255, 197, 61), width=3)
                sp = s.get("speaker")
                conf = s.get("confidence")
                weak = conf is not None and conf < 0.2
                td.text((x - z / 2, yy + z / 2 + 2),
                        (f"{a['slots'].index(s) + 1}: {names.get(sp, sp)}" if sp else f"{a['slots'].index(s) + 1}: ?")
                        + (" (?)" if weak else ""), font=f, fill=(255, 140, 0) if weak or not sp else (255, 255, 0))
            td.text((4, 2), f"{t:.0f}s", font=f, fill=(255, 255, 255))
            im.paste(tile.crop((0, 0, tw, th)), (160 + c * tw, y))
    im.save(SHEET, quality=85)
    return SHEET


def set_speakers(pairs):
    """hand corrections from looking at the sheet: ["A2=3", "C1=1"] -> angle A's 2nd face (left to right) is speaker 3"""
    data = json.load(open(JSON))
    by = {a["id"]: a for a in data["angles"]}
    for pr in pairs:
        key, _, sp = pr.partition("=")
        a, n = by[key[0].upper()], int(key[1:]) - 1
        a["slots"][n]["speaker"] = sp or None
        a["slots"][n]["confidence"] = 9.0  # checked by eye
        a["slots"][n]["by"] = "hand"
    json.dump(data, open(JSON, "w"), indent=1, ensure_ascii=False)
    sheet()


def who(t0, t1, step=0.5):
    """who is talking between t0 and t1 (source seconds), by mouth movement of the faces on screen: one line per
    sample, with the words said then. For checking diarization by eye-free means; Edit(who=…) takes the result."""
    from concurrent.futures import ThreadPoolExecutor
    data = load()
    names = {k: v["name"] for k, v in data["speakers"].items()}
    words = json.load(open(WORDS_JSON))

    def one(t):
        fr = _clip3(t)
        if fr is None:
            return t, None, None
        th = cv2.resize(cv2.cvtColor(fr[0], cv2.COLOR_RGB2GRAY), (64, 36), interpolation=cv2.INTER_AREA)
        a = classify(data, [fingerprint(th)])
        if a is None or not a["slots"]:
            return t, a, None
        return t, a, _mouth_activity(t, a["slots"])
    times = list(np.arange(t0, t1, step))
    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(one, times))
    for t, a, act in rows:
        said = " ".join(f"{w['t']}[{w.get('sp')}]" for w in words if t <= w["s"] / 1000 < t + step)
        if a is None:
            print(f"{t:8.2f}  -  (no known angle)  {said}")
            continue
        label = lambda sl: names.get(str(sl.get("speaker")), sl.get("speaker")) or "?"
        vals = [(v, label(sl)) for v, sl in zip(act or [], a["slots"]) if v is not None]
        if not vals:
            print(f"{t:8.2f}  {a['id']}  (no faces)  {said}")
            continue
        vals.sort(reverse=True)
        sure = len(vals) == 1 or vals[0][0] > 1.4 * vals[1][0]
        rest = ", ".join(f"{n} {v:.2f}" for v, n in vals[1:])
        print(f"{t:8.2f}  {a['id']}  {vals[0][1] + ('' if sure else ' ?'):22} {vals[0][0]:.2f}  ({rest})  {said}")


if __name__ == "__main__":
    import sys
    if "--who" in sys.argv:
        i = sys.argv.index("--who")
        who(float(sys.argv[i + 1]), float(sys.argv[i + 2]), float(sys.argv[i + 3]) if len(sys.argv) > i + 3 else 0.5)
    elif "--set" in sys.argv:
        set_speakers(sys.argv[sys.argv.index("--set") + 1:])
        print(f"angles: updated {JSON}; check {SHEET}")
    else:
        analyse(force="--force" in sys.argv)
