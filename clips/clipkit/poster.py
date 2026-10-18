"""Choosing the first frame (platforms use it as the preview): a good face of the person speaking."""
import base64, hashlib, json, os, sys, urllib.request
import numpy as np
import cv2

from .project import CACHE, PREVIEW, VIDEO, WORDS_JSON, dotenv, run
from .angles import JSON as ANGLES_JSON, classify, fingerprint, load
from .faces import detect
from .video import full_frame
from .words import all_words

def face_quality(rgb):
    """score a 960x540 frame for the cover: a big, sharp, frontal face with both eyes open (open eyes have dark
    pupils and lashes, so the patch around each eye landmark varies more than closed lids do)"""
    fs = [f for f in detect(rgb) if f["y"] < 0.6 * rgb.shape[0]]
    if not fs:
        return -1.0
    f = fs[0]
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    w = f["size"] / 1.29
    (ex1, ey1), (ex2, ey2) = f["eyes"]
    eye_gap = max(1.0, abs(ex2 - ex1))
    frontal = 1 - min(1.0, abs(f["nose"][0] - (ex1 + ex2) / 2) / (0.5 * eye_gap))
    r = max(3, int(0.12 * w))

    def patch(x, y):
        return g[max(0, int(y) - r):int(y) + r, max(0, int(x) - r):int(x) + r]
    x0, y0 = int(f["x"] - w / 2), int(f["y"] - w / 2)
    face = g[max(0, y0):y0 + int(w), max(0, x0):x0 + int(w)]
    if face.size == 0:
        return -1.0
    eyes = [patch(ex1, ey1), patch(ex2, ey2)]
    openness = min(p.std() for p in eyes if p.size) / (face.std() + 1e-6) if all(p.size for p in eyes) else 0.0
    sharp = cv2.Laplacian(face, cv2.CV_32F).var()
    return 2.0 * frontal + 2.0 * min(openness / 0.6, 1.0) + min(sharp / 150.0, 2.0) + min(w / 110.0, 1.5)


def _close_up_of(g):
    """speaker id whose close-up this 960x540 grey frame is (None for wide shots or unknown angles)"""
    try:
        ang = classify(load(), [fingerprint(cv2.resize(g, (64, 36), interpolation=cv2.INTER_AREA))])
    except Exception:
        return None
    return ang["slots"][0].get("speaker") if ang and len(ang["slots"]) == 1 else None


def best_poster(edit, window=3.0):
    """Source time of the best preview frame, while the clip's opening speaker talks: detectors shortlist frames
    from the first `window` seconds, the vision model picks; if nothing there is good, the whole clip is searched.
    Cached per cut (and transcript and angle analysis), so re-rendering a clip keeps its cover and skips the ~20 s."""
    stamp = [os.path.getmtime(f) if os.path.exists(f) else 0 for f in (WORDS_JSON, ANGLES_JSON)]
    key = hashlib.sha1(json.dumps([edit.pieces, window, PREVIEW, VIDEO, stamp]).encode()).hexdigest()[:16]
    path = os.path.join(CACHE, f"poster_{key}.json")
    if os.path.exists(path):
        return json.load(open(path))["t"]
    t, sure = _best_poster(edit, window)
    if sure:  # a failed vision call isn't remembered: the next render asks again
        json.dump({"t": t}, open(path, "w"))
    return t


def _best_poster(edit, window):
    """-> (source time, whether to remember it)"""
    def scan(limit):
        found = []
        for (a, b), o in zip(edit.pieces, edit.offsets):
            if o >= limit:
                break
            end = min(b, a + (limit - o))
            raw = run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{end - a:.3f}", "-i", VIDEO,
                       "-vf", "fps=10,scale=960:540", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
            for k, f in enumerate(np.frombuffer(raw, np.uint8).reshape(-1, 540, 960, 3)):
                found.append((face_quality(f), a + k / 10, _close_up_of(cv2.cvtColor(f, cv2.COLOR_RGB2GRAY))))
        ws = [w for w in all_words() if any(x - 0.05 <= w["s"] <= y for x, y in edit.pieces)]
        who = str(ws[0]["sp"]) if ws else None
        talk = [(w["s"] - 0.3, w["e"] + 0.3) for w in ws if str(w["sp"]) == who]
        found = [c for c in found if any(x <= c[1] <= y for x, y in talk)] or found
        mine = [c for c in found if c[2] == who]  # a close-up of that speaker, not of the listener
        return [(sc, t) for sc, t, _ in (mine or found)]

    def shortlist(cs):
        out = []
        for sc, t in sorted(cs, reverse=True):
            if sc > 0 and all(abs(t - u) >= 0.4 for _, u in out):
                out.append((sc, t))
        return out[:8]

    cands = scan(window)
    if max([c[0] for c in cands] or [-9]) < 5.0:
        cands = scan(edit.dur)
    short = shortlist(cands)
    if not short:
        return edit.pieces[0][0], True
    if PREVIEW:
        return short[0][1], True  # previews skip the vision call; finals pick properly
    pick, good = _vision_pick([t for _, t in short])
    if pick is not None and not good and window < edit.dur:
        wide = shortlist(scan(edit.dur))
        p2, g2 = _vision_pick([t for _, t in wide]) if wide else (None, False)
        if p2 is not None and g2:
            return wide[p2][1], True
    return short[pick if pick is not None else 0][1], pick is not None


def _vision_pick(times):
    """(index, good) of the best candidate per the vision model; (None, False) if it isn't available"""
    key = dotenv("OPENAI_API_KEY")
    if not key:
        return None, False
    content = [{"type": "input_text", "text": (
        f"These {len(times)} images are candidate first frames (the preview thumbnail) for a vertical podcast clip, "
        "numbered from 0 in order. Pick the one where the person looks best: both eyes clearly open, natural or friendly "
        "expression, mouth closed or a smile (not mid-word), no hand on or near the face and no raised or gesturing hands, "
        "not blurry, not mid-blink. Calm and friendly beats animated.")}]
    for t in times:
        ok, buf = cv2.imencode(".jpg", cv2.cvtColor(cv2.resize(full_frame(t), (768, 432)), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 80])
        content.append({"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()})
    body = {"model": dotenv("OPENAI_MODEL_FAST") or "gpt-6-luna", "reasoning": {"effort": "low"},
            "input": [{"role": "user", "content": content}],
            "text": {"format": {"type": "json_schema", "name": "pick", "strict": True, "schema": {
                "type": "object", "additionalProperties": False, "required": ["index", "good"],
                "properties": {"index": {"type": "integer"}, "good": {"type": "boolean",
                               "description": "true only if the chosen frame really is a nice, calm, eyes-open face"}}}}}}
    try:
        req = urllib.request.Request("https://api.openai.com/v1/responses", data=json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        data = json.load(urllib.request.urlopen(req, timeout=120))
        text = next(c["text"] for o in data["output"] if o["type"] == "message" for c in o["content"] if c["type"] == "output_text")
        out = json.loads(text)
        i = int(out["index"])
        return (i, bool(out["good"])) if 0 <= i < len(times) else (None, False)
    except Exception as e:
        sys.stderr.write(f"cover: vision pick failed ({e}); using the detectors' best\n")
        return None, False
