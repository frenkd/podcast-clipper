"""Reading the source video: camera-cut detection, face tracking, frames, and the face-following crop."""
import json, os, subprocess
import numpy as np
import cv2

from . import state
from .project import CACHE, FPS, SH, STEP, SW, VIDEO, run

MIN_SHOT = 0.35  # seconds: shorter visual shots look like a glitch, so they're replaced by a hold
MAX_HOLD = 1.2   # seconds: the longest a still frame may stand in for a cutaway (Edit(..., hold=))
BAND = 780        # bottom of the video band in split layouts (frame_canvas); boards go between it and the captions
DET_STEP = 6     # face detections per second
MIN_CONF = 0.2   # angles.json slot confidence below which the engine won't steer the crop by that slot's speaker


def full_frame(src_t):
    """one full-resolution RGB frame of the source"""
    raw = run(["ffmpeg", "-v", "error", "-ss", f"{src_t:.3f}", "-i", VIDEO, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    return np.frombuffer(raw, np.uint8).reshape(SH, SW, 3)


def _sig(a, b):
    """64x36 grayscale thumbnails of every source frame in [a, b) at FPS (cached)"""
    path = os.path.join(CACHE, f"sig_{a:.3f}_{b:.3f}.npy")
    if os.path.exists(path):
        return np.load(path)
    raw = run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", VIDEO,
               "-vf", f"fps={FPS},scale=64:36", "-f", "rawvideo", "-pix_fmt", "gray", "-"])
    s = np.frombuffer(raw, np.uint8).reshape(-1, 36, 64).astype(np.float32)
    np.save(path, s)
    return s


def _edges(x):
    g = cv2.GaussianBlur(x, (3, 3), 0)
    e = np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1))
    e = e - e.mean()
    return e / (np.linalg.norm(e) + 1e-6)


def _is_cut(x, y):
    """camera cut between two thumbnails: the picture's structure changes (motion inside a shot stays ~0.95+)"""
    return float((_edges(x) * _edges(y)).sum()) < 0.8


def _detect(a, b):
    """every face (frontal + profiles), DET_STEP times a second: [[(cx, cy, size), …], …] in source px (cached)"""
    from .faces import faces_in
    path = os.path.join(CACHE, f"yunet_{a:.3f}_{b:.3f}.json")
    if os.path.exists(path):
        return [[tuple(f) for f in d] for d in json.load(open(path))]
    raw = run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", VIDEO,
               "-vf", f"fps={DET_STEP},scale={SW}:{SH}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
    out = [faces_in(f) for f in np.frombuffer(raw, np.uint8).reshape(-1, SH, SW, 3)]
    json.dump(out, open(path, "w"))
    return out


def _focus_timeline(edit, n, data=None):
    """speaker id to keep on screen for each output frame: edit.focus if set, else whoever is talking (interjections
    under 0.8 s don't count)"""
    if edit.focus is not None:
        f = str(edit.focus)
        for sid, v in ((data or {}).get("speakers") or {}).items():
            if f.lower() in v["name"].lower():
                f = sid
        return [f] * n
    sp = [None] * n
    for w in edit.words():
        for i in range(int(w["s"] * FPS), min(n, int(w["e"] * FPS) + 1)):
            sp[i] = str(w["sp"])
    cur = next((x for x in sp if x), None)
    for i in range(n):  # pauses keep the last speaker
        cur = sp[i] = sp[i] or cur
    runs, i = [], 0
    while i < n:
        j = i
        while j < n and sp[j] == sp[i]:
            j += 1
        runs.append([sp[i], i, j])
        i = j
    for k, r in enumerate(runs):
        if r[2] - r[1] < 0.8 * FPS and len(runs) > 1:
            r[0] = runs[k - 1][0] if k else runs[k + 1][0]
    out = []
    for r in runs:
        out += [r[0]] * (r[2] - r[1])
    return out


REFRAME_MIN = 1.5  # s: a wide shot is re-cut onto whoever talks when each part would last at least this long


def _reframe(shots, focus, fps_, data):
    """split wide shots (several people on screen) where the talker changes, so a conversation clip cuts to whoever
    is talking instead of staying on one seat for a whole long wide shot. Each part becomes its own shot."""
    from . import angles
    out, new = np.zeros_like(shots), -1
    for sid in np.unique(shots):
        idx = np.where(shots == sid)[0]
        prints = [angles.fingerprint(fps_[i]) for i in idx[::5] if fps_[i] is not None]
        ang = angles.classify(data, prints) if prints else None
        cuts = []
        if ang and len(ang["slots"]) > 1:
            runs, k = [], 0
            while k < len(idx):
                j = k
                while j < len(idx) and focus[idx[j]] == focus[idx[k]]:
                    j += 1
                runs.append([k, j])
                k = j
            merged = []
            for r in runs:  # a part too short to cut to stays with the one before it
                if merged and (r[1] - r[0] < REFRAME_MIN * FPS or merged[-1][1] - merged[-1][0] < REFRAME_MIN * FPS):
                    merged[-1][1] = r[1]
                else:
                    merged.append(r)
            cuts = [r[0] for r in merged[1:]]
        new += 1
        for n, i in enumerate(idx):
            if n in cuts:
                new += 1
            out[i] = new
    return out


def track_edit(edit):
    """(face per output frame [cx, cy, size] in source px, shot id per frame, frames per piece).
    Each shot is matched to one of the episode's camera angles (angles.py) and keeps ONE person for its whole length:
    the one who talks most during it (or edit.focus). In a wide shot the crop sits on that person's seat; in a
    close-up of someone else (a cutaway) the shot is shown as it is. One continuous track per shot, smoothed, snapped
    on real camera cuts; a rolling median drops single bad detections. Per-shot details go to state.SHOT_INFO."""
    from . import angles
    data = angles.analyse()
    nfs, n_done, shot, shots, dets, fps_, prev_last = [], 0, 0, [], [], [], None
    for (a, b), o in zip(edit.pieces, edit.offsets):
        nf = int(round((o + b - a) * FPS)) - n_done
        nfs.append(nf)
        s = _sig(a, b)
        cuts = {i for i in range(1, len(s)) if _is_cut(s[i], s[i - 1])}
        d = _detect(a, b)
        if prev_last is not None and len(s) and _is_cut(s[0], prev_last):
            shot += 1
        for i in range(nf):
            shot += i in cuts
            shots.append(shot)
            j = min(len(d) - 1, int(round(i / FPS * DET_STEP))) if d else -1
            dets.append(d[j] if (d and abs(j / DET_STEP * FPS - i) < 0.5) else None)  # only frames that were sampled
            fps_.append(s[min(i, len(s) - 1)] if len(s) else None)
        if len(s):
            prev_last = s[min(len(s) - 1, nf - 1)]
        n_done += nf
    shots = np.array(shots)
    focus = _focus_timeline(edit, len(shots), data)
    if edit.focus is None:
        shots = _reframe(shots, focus, fps_, data)
    res = np.zeros((len(shots), 3))
    info = {}
    for sid in np.unique(shots):
        idx = np.where(shots == sid)[0]
        prints = [angles.fingerprint(fps_[i]) for i in idx[::5] if fps_[i] is not None]
        ang = angles.classify(data, prints) if prints else None
        votes = [focus[i] for i in idx if focus[i]]
        who = max(set(votes), key=votes.count) if votes else None
        target, mode = None, "unknown"
        if ang and ang["slots"]:
            who_names = {who, (data.get("speakers") or {}).get(who, {}).get("name")} - {None}
            mine = [s for s in ang["slots"] if s.get("speaker") in who_names and s.get("confidence", 1.0) >= MIN_CONF]
            target = mine[0] if mine else max(ang["slots"], key=lambda s: s["size"])
            mode = "on" if mine else "away"
        info[int(sid)] = {"angle": ang["id"] if ang else None, "speaker": who, "mode": mode,
                          "wide": bool(ang and len(ang["slots"]) > 1)}
        pts = []
        for i in idx:
            if not dets[i]:
                continue
            if target:
                near = [f for f in dets[i] if abs(f[0] - target["x"]) < 0.8 * target["size"]
                        and abs(f[1] - target["y"]) < 0.8 * target["size"]]
                if near:
                    pts.append((i, min(near, key=lambda f: abs(f[0] - target["x"]) + abs(f[1] - target["y"]))))
            else:
                upper = [f for f in dets[i] if f[1] < SH * 0.5]
                if upper:
                    pts.append((i, max(upper, key=lambda f: f[2])))
        if not pts:
            if target:
                res[idx] = (target["x"], target["y"], target["size"])
            else:
                res[idx] = res[idx[0] - 1] if idx[0] > 0 else (SW * 0.5, SH * 0.3, SH * 0.2)
            continue
        pi = np.array([p[0] for p in pts], float)
        pv = np.array([p[1] for p in pts], float)
        med = np.array([np.median(pv[max(0, k - 3):k + 4], axis=0) for k in range(len(pv))])  # ~0.7 s median
        full = np.stack([np.interp(idx, pi, med[:, c]) for c in range(3)], 1)
        kk = min(15, len(idx) // 2)  # ~1 s moving average
        if kk > 0:
            pad = np.pad(full, ((kk, kk), (0, 0)), mode="edge")
            ker = np.ones(2 * kk + 1) / (2 * kk + 1)
            full = np.stack([np.convolve(pad[:, c], ker, mode="valid") for c in range(3)], 1)
        full[:, 2] = np.median(pv[:, 2])  # one face size per shot, so size-based zoom never wobbles
        res[idx] = full
    state.SHOT_INFO = {int(i): info[int(shots[i])] for i in range(len(shots))}
    return res, shots, nfs


def frames(edit):
    """Yield (t_out, rgb frame, face) for every rendered output frame (every STEP-th).
    Shots shorter than MIN_SHOT (a jump cut next to a camera cut) are replaced by holding the neighbouring shot,
    so the clip never flashes a few frames of another angle. A cutaway to someone who isn't talking is held only if
    the edit asks for it (Edit(..., hold=s)) and only when it's at most that long (max MAX_HOLD): a frozen picture
    under a running voice reads as a bug, so the default is to show the cutaway."""
    tr, shots, nfs = track_edit(edit)
    total = len(shots)
    edges = [0] + [i for i in range(1, total) if shots[i] != shots[i - 1]] + [total]
    hold = {}
    if len(edges) > 2:
        for x, y in zip(edges[:-1], edges[1:]):
            if y - x < MIN_SHOT * FPS:
                hold.update({i: "prev" if x > 0 else "next" for i in range(x, y)})
    max_hold = min(edit.hold, MAX_HOLD) * FPS
    for x, y in zip(edges[:-1], edges[1:]):
        if x > 0 and state.SHOT_INFO[x]["mode"] == "away" and y - x <= max_hold and \
                state.SHOT_INFO[x - 1]["mode"] == "on":
            hold.update({i: "prev" for i in range(x, y)})
    state.SHOT_BOUNDS = edges[1:-1]
    next_target = None
    if "next" in hold.values():
        first_ok = min(i for i in range(total) if i not in hold)
        pi = next(k for k in range(len(nfs)) if sum(nfs[:k + 1]) > first_ok)
        next_target = (full_frame(edit.pieces[pi][0] + (first_ok - sum(nfs[:pi])) / FPS), tuple(tr[first_ok]))
    n_done, held = 0, None
    for (a, b), nf in zip(edit.pieces, nfs):
        p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-i", VIDEO, "-frames:v", str(nf),
                              "-vf", f"fps={FPS}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        last = None
        for i in range(nf):
            buf = p.stdout.read(SW * SH * 3)
            fr = last if len(buf) < SW * SH * 3 else np.frombuffer(buf, np.uint8).reshape(SH, SW, 3)
            last = fr
            gi = n_done + i
            face = tuple(tr[min(gi, total - 1)])
            if gi in hold:
                fr, face = held if (hold[gi] == "prev" and held) else next_target
            else:
                held = (fr, face)
            if gi % STEP == 0:
                yield gi / FPS, fr, face
        p.stdout.close()
        p.wait()
        n_done += nf


def shot_info(t):
    """what the picture shows at output time t: {angle, speaker, mode ('on' / 'away' / 'unknown'), wide}"""
    return state.SHOT_INFO.get(int(round(t * FPS)), {}) if state.SHOT_INFO else {}


def crop(fr, face, out_w, out_h, zoom=1.0, face_y=0.36, face_x=0.5, dx=0.0, dy=0.0, at=(0, 0), fit=True, max_zoom=2.4):
    """Crop the source so the face lands at (face_x, face_y) of an out_w x out_h picture. zoom > 1 is tighter.
    fit: push in on small faces (a wide shot) so the person reads like a close-up (up to 1.8x, constant per shot).
    at: where you'll paste the result on the canvas (so face checks know where the face ends up). max_zoom: the most
    it pushes in overall (past ~2.4x the picture gets soft; a meme zoom may want that)."""
    sh, sw = fr.shape[:2]
    if fit and face[2] > 0:
        zoom *= min(1.8, max(1.0, 0.2 * sh / face[2]))
        zoom = min(zoom, max_zoom)
    asp = out_w / out_h
    ch = sh / zoom
    cw = ch * asp
    if cw > sw:
        cw, ch = sw, sw / asp
    x0 = min(max(0, face[0] - cw * face_x + dx * cw), sw - cw)
    y0 = min(max(0, face[1] - ch * face_y + dy * ch), sh - ch)
    s = out_w / cw
    state.LAST_MAP = (x0, y0, s, at[0], at[1])
    M = np.array([[s, 0, -x0 * s], [0, out_h / ch, -y0 * out_h / ch]], np.float32)
    return cv2.warpAffine(fr, M, (out_w, out_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def frame_canvas(fr, face, split=0.0, band=BAND, zoom=1.0, face_y=0.36):
    """The usual base of a clip frame: the video full-frame (split=0) easing into a band at the top with a panel below
    (split=1, video bottom at y=band) for a board. The panel is the same shot, blurred and darkened, so the frame never
    looks empty under the board (the apps' captions sit down there anyway). Start full-frame; split only while the
    panel has content. -> RGBA canvas"""
    from PIL import Image, ImageFilter
    from .project import H, LAYOUT, W
    from .style import fade
    if LAYOUT != "split":  # overlay: the shot stays whole; the face eases up a little and the lower part darkens
        c = Image.fromarray(crop(fr, face, W, H, zoom=zoom, face_y=face_y - 0.07 * split)).convert("RGBA")
        if split > 0:
            c.alpha_composite(fade(W, 1000, (10, 10, 12), 0.0, 0.82 * split), (0, H - 1000))
        return c
    full = crop(fr, face, W, H, zoom=zoom, face_y=face_y)
    if split <= 0:
        return Image.fromarray(full).convert("RGBA")
    small = Image.fromarray(full).resize((W // 8, H // 8), Image.BILINEAR).filter(ImageFilter.GaussianBlur(6))
    c = small.resize((W, H), Image.BILINEAR).convert("RGBA")
    c.alpha_composite(Image.new("RGBA", (W, H), (10, 10, 12, int(200 * split))))
    vh = int(H + (band - H) * split)
    v = crop(fr, face, W, vh, zoom=zoom, face_y=face_y + 0.06 * split)
    c.paste(Image.fromarray(v), (0, 0))
    c.alpha_composite(fade(W, 220, (10, 10, 12), 0.0, 0.8 * split), (0, vh - 220))
    return c


def frame_window(fr, face, k=1.0, box=(40, 240, 1000, 560), bg=(10, 10, 12), title=None, face_y=0.4):
    """The video as a window on a dark screen (an IDE, a terminal, a desktop): full-frame at k=0, easing into `box`
    (x, y, w, h) at k=1 with a hairline frame and an optional title bar. For clips where a screen is the stage and
    the speaker sits in a corner of it. -> RGBA canvas"""
    from PIL import Image, ImageDraw
    from .project import H, W
    from .project import F_MONO_B
    from .style import GREY, LINE
    from .draw import text_line
    if k <= 0:
        return Image.fromarray(crop(fr, face, W, H, face_y=0.36)).convert("RGBA")
    e = k * k * (3 - 2 * k)
    x, y, w, h = (int(a + (b - a) * e) for a, b in zip((0, 0, W, H), box))
    c = Image.new("RGBA", (W, H), bg + (255,))
    v = Image.fromarray(crop(fr, face, w, h, face_y=0.36 + (face_y - 0.36) * e, at=(x, y))).convert("RGBA")
    r = int(14 * e)
    if r:
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255)
        v.putalpha(m)
    c.alpha_composite(v, (x, y))
    if e > 0.5:
        d = ImageDraw.Draw(c)
        d.rounded_rectangle((x - 1, y - 1, x + w, y + h), r, outline=LINE + (255,), width=2)
        if title:
            t = text_line(title, F_MONO_B, 28, GREY)
            c.alpha_composite(t, (x + 16, y - t.height - 12))
    return c


def face_out(face):
    """(cx, cy, size) of the tracked face on the canvas, for the most recent crop()"""
    x0, y0, s, ox, oy = state.LAST_MAP
    return (face[0] - x0) * s + ox, (face[1] - y0) * s + oy, face[2] * s


def face_rect(face):
    """head box on the canvas (hair to chin) for the most recent crop()"""
    fx, fy, fs = face_out(face)
    return fx - fs * 0.75, fy - fs * 0.95, fx + fs * 0.75, fy + fs * 0.8


def glitch(arr, amt=1.0, seed=0):
    """RGB split + horizontal slice displacement on an HxWx3 frame (a one-off beat, not a constant effect)"""
    rng = np.random.default_rng(seed)
    out = arr.copy()
    s = int(18 * amt)
    if s:
        out[:, s:, 0] = arr[:, :-s, 0]
        out[:, :-s, 2] = arr[:, s:, 2]
    for _ in range(int(8 * amt)):
        y = rng.integers(0, arr.shape[0] - 40)
        hh = rng.integers(8, 70)
        out[y:y + hh] = np.roll(out[y:y + hh], int(rng.integers(-60, 60) * amt), axis=1)
    return out
