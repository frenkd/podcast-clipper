"""render(): audio mix, headline placement, cover frame, the frame loop with the QA checks (qa.py), encode, and the
review files written next to every preview: <name>.qa.txt, .events.jpg, .grid.jpg, .zones.jpg, .cover.jpg (for finals
they go to work/render/final/, so final/ holds only the videos)."""
import math, os, subprocess, time
import numpy as np
from PIL import Image, ImageDraw

from . import encode, qa, state
from .audio import Mix, edit_audio, sfx_outro
from .safezones import app_ui, sheet as zones_sheet
from .brand import _hook_slot
from .draw import font
from .poster import best_poster
from .project import THEME, F_MENLO, FPS, H, PREVIEW, PROJECT_DIR, SH, STEP, SW, W, WORK
from .video import frames, full_frame, track_edit

EVENT_OFFSETS = [-0.1, 0.0, 0.07, 0.13, 0.2, 0.33, 0.6, 1.2, 2.4]
THUMB = (160, 284)


def render(name, edit, draw, sound=None, tail=1.8, bed=None, bed_gain=0.2, duck=0.35, voice_gain=1.0, crf=18,
           poster_t=0.35, outro_sound=None, outro_t=None):
    """Render a clip. draw(t, frame, face) -> 1080x1920 PIL image for output time t (t >= edit.dur is the tail:
    the last frame repeats, draw the end card there). sound(mix) adds effects; bed(total_seconds) -> music bed.
    poster_t: time whose overlays go on the cover frame (None = no cover). outro_sound: the chime under the end card (default: the theme's outro_chime;
    t=outro_t, default edit.dur). Platforms replay clips in a loop, so the
    end card stays short (tail) and the audio ends on silence. Previews (PREVIEW=1) go to
    projects/<id>/preview/, finals to projects/<id>/final/ (just the .mp4; checks in work/render/final/)."""
    t_start = time.time()
    outdir = os.path.join(PROJECT_DIR, os.environ.get("CLIP_OUTDIR") or ("preview" if PREVIEW else "final"))
    scratch = os.path.join(WORK, "render")
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(scratch, exist_ok=True)
    base = os.path.join(outdir, name)
    rdir = outdir if PREVIEW else os.path.join(scratch, "final")  # finals: only the video in final/, checks aside
    os.makedirs(rdir, exist_ok=True)
    rbase = os.path.join(rdir, name)
    total = edit.dur + tail

    mix = Mix(total, duck)
    mix.add(0, edit_audio(edit), track="voice")
    if bed is not None:
        mix.add(0, bed(total), track="bed")
    if THEME["outro_chime"] if outro_sound is None else outro_sound:  # no intro jingle: the clip starts on the voice
        mix.add(edit.dur if outro_t is None else outro_t, sfx_outro(), 0.5)
    if sound:
        sound(mix)
    wav = os.path.join(scratch, f"{name}.wav")
    mix.write(wav, voice_gain=voice_gain, bed_gain=bed_gain)

    state.CLIP_SPEAKER = _speaker_name(edit)
    state.HOOK_SPEAKER = _speaker_name(edit, until=2.6)
    track_edit(edit)  # the shots, checked against whose mouth moves: the names follow who's on screen
    state.CLIP_SPEAKER = _on_screen_name() or state.CLIP_SPEAKER
    state.HOOK_SPEAKER = _on_screen_name(until=2.6) or state.HOOK_SPEAKER
    # dry run over the first seconds: where is the face while the hook is up? (fixes the hook's spot once)
    tr = track_edit(edit)[0]
    state.PROBE, state.HOOK_SLOTS, state.CAPTIONS_AFTER = {}, {}, 0.0
    dummy = np.zeros((SH, SW, 3), np.uint8)
    for tp in np.arange(0, min(edit.dur, 4.0), 0.2):
        try:
            draw(float(tp), dummy, tuple(tr[min(int(tp * FPS), len(tr) - 1)]))
        except Exception:
            pass
    probe, state.PROBE = state.PROBE, None
    state.HOOK_SLOTS = {k: _hook_slot(v["rects"], v["h"]) for k, v in probe.items()}

    poster = None
    state.COVER = poster_t is not None
    if poster_t is not None:
        ps = best_poster(edit)
        poster = draw(poster_t, full_frame(ps), tuple(tr[min(len(tr) - 1, int(round((edit.out_t(ps) or 0) * FPS)))]))
        poster.convert("RGB").save(rbase + ".cover.jpg", quality=92)
        if not _same_angle(ps, edit.pieces[0][0]):  # frame one only if it's the opening shot's camera: else it
            poster = None                          # flashes another shot for a frame (the .cover.jpg stays)
            state.COVER = False

    # review captures, taken from the frames as they're written (no seeking afterwards)
    events = _events(draw, edit.dur)
    want = {}
    for r, (_, e) in enumerate(events):
        for c, o in enumerate(EVENT_OFFSETS):
            want.setdefault(int(round(max(0.0, e + o) * FPS / STEP)), []).append((r, c))
    strip = Image.new("RGB", (THUMB[0] * len(EVENT_OFFSETS) + 150, (THUMB[1] + 6) * len(events)), (30, 30, 30))
    grid = []
    zone_at = {int(edit.dur * f * FPS / STEP): f for f in (0.25, 0.5, 0.75)}
    zone_frames = []

    enc = subprocess.Popen(encode.command(base + ".mp4", wav, (W, H), FPS / STEP, total, PREVIEW, crf), stdin=subprocess.PIPE)
    k = 0

    mock_ui = app_ui(os.environ["CLIP_MOCK"]) if os.environ.get("CLIP_MOCK") else None

    def write(img):
        nonlocal k
        if mock_ui is not None:  # a test render with the app's UI baked in
            img = img.convert("RGBA")
            img.alpha_composite(mock_ui)
        rgb = img.convert("RGB")
        try:
            enc.stdin.write(rgb.tobytes())
        except BrokenPipeError:  # ffmpeg died; its own error is printed above
            raise SystemExit(f"{name}: ffmpeg ({encode.pick()}) stopped while encoding {base}.mp4")
        if k in zone_at:
            zone_frames.append(rgb)
        if k in want or k % (FPS // STEP) == 0:
            th = rgb.resize(THUMB, Image.BILINEAR)
            for r, c in want.get(k, []):
                strip.paste(th, (150 + c * THUMB[0], r * (THUMB[1] + 6)))
            if k % (FPS // STEP) == 0:
                grid.append(th)
        k += 1

    check, last = qa.start(), None
    for n_frame, (t, fr, face) in enumerate(frames(edit)):
        last = (fr, face)
        check.before_draw(t, fr)
        img = draw(t, fr, face)
        out = poster if (poster is not None and n_frame < max(1, 3 // STEP)) else img  # frame one = the cover
        check.after_draw(t, face, out)
        write(out)
    summary = check.report(rbase + ".qa.txt")
    for j in range(0, int(round(tail * FPS)), STEP):
        write(draw(edit.dur + j / FPS, *last))
    enc.stdin.close()
    if enc.wait():
        raise SystemExit(f"{name}: ffmpeg ({encode.pick()}) failed writing {base}.mp4")
    if PREVIEW:  # previews stay shareable (Discord takes 10 MB)
        encode.fit(base + ".mp4", total)

    _label_strip(strip, events)
    strip.save(rbase + ".events.jpg", quality=80)
    _save_grid(grid, rbase + ".grid.jpg")
    if zone_frames:
        rows = [zones_sheet(f, width=240) for f in zone_frames]
        z = Image.new("RGB", (rows[0].width, sum(r.height for r in rows) + 8 * (len(rows) - 1)), (30, 30, 30))
        for i, r in enumerate(rows):
            z.paste(r, (0, i * (r.height + 8)))
        z.save(rbase + ".zones.jpg", quality=80)
    print(f"{name}: {total:.1f}s clip in {time.time() - t_start:.0f}s -> {base}.mp4\n  QA: {summary}")
    return base + ".mp4"


def _speaker_name(edit, until=None):
    """name of whoever talks most in the edit (or its first `until` seconds; or the edit's focus): prep's speaker map,
    else the angle analysis"""
    from .project import SPEAKER_NAMES
    names = dict(SPEAKER_NAMES)
    try:
        from .angles import load
        names = {**{k: v["name"] for k, v in load()["speakers"].items()}, **names}
    except Exception:
        pass
    if edit.focus is not None:
        f = str(edit.focus)
        return names.get(f) or next((n for n in names.values() if f.lower() in n.lower()), f)
    talk = {}
    for w in edit.words():
        if until is not None and w["s"] > until:
            break
        talk[str(w["sp"])] = talk.get(str(w["sp"]), 0) + w["e"] - w["s"]
    sp = max(talk, key=talk.get) if talk else None
    name = names.get(sp) or (sp if sp and not sp.isdigit() else "")  # Edit(who=…) gives names directly
    return "" if not name or name.startswith("speaker ") or name in ("host", "Unknown") else name


def _same_angle(a, b):
    """whether source times a and b show the same camera angle (angles.py)"""
    import cv2
    from .angles import classify, fingerprint, load
    try:
        data = load()
        ids = [(classify(data, [fingerprint(cv2.resize(cv2.cvtColor(full_frame(t), cv2.COLOR_RGB2GRAY), (64, 36),
                                                      interpolation=cv2.INTER_AREA))]) or {}).get("id") for t in (a, b)]
    except Exception:
        return False
    return ids[0] is not None and ids[0] == ids[1]


def _on_screen_name(until=None):
    """the name of whoever is shown talking most (track_edit's shots, mode "on"), in the first `until` seconds"""
    from .project import SPEAKER_NAMES
    names = dict(SPEAKER_NAMES)
    try:
        from .angles import load
        names = {**{k: v["name"] for k, v in load()["speakers"].items()}, **names}
    except Exception:
        pass
    count = {}
    for i, info in (state.SHOT_INFO or {}).items():
        if (until is None or i < until * FPS) and info.get("mode") == "on" and info.get("speaker"):
            count[str(info["speaker"])] = count.get(str(info["speaker"]), 0) + 1
    if not count:
        return ""
    sp = max(count, key=count.get)
    name = names.get(sp) or (sp if not sp.isdigit() else "")
    return "" if not name or name.startswith("speaker ") or name in ("host", "Unknown") else name


def _events(draw, dur):
    """[(name, t)] for every *_T number in the clip script, plus the start"""
    g = getattr(draw, "__globals__", {})
    ev = {round(float(v), 2): k for k, v in g.items() if k.endswith("_T") and isinstance(v, (int, float)) and 0 < v < dur}
    return [("start", 0.0)] + sorted(((n, t) for t, n in ev.items()), key=lambda x: x[1])


def _label_strip(strip, events):
    d = ImageDraw.Draw(strip)
    for r, (n, e) in enumerate(events):
        y = r * (THUMB[1] + 6)
        d.text((8, y + 8), f"{n}\n{e:.2f}s", font=font(F_MENLO, 18), fill=(255, 255, 255))
        for c, o in enumerate(EVENT_OFFSETS):
            d.text((150 + c * THUMB[0] + 4, y + 2), f"{o:+.2f}", font=font(F_MENLO, 16), fill=(255, 230, 0))


def _save_grid(thumbs, path, cols=8):
    """one frame per second, labelled"""
    if not thumbs:
        return
    tw, th = THUMB
    im = Image.new("RGB", (cols * tw, math.ceil(len(thumbs) / cols) * (th + 22)), (40, 40, 40))
    d = ImageDraw.Draw(im)
    for i, t in enumerate(thumbs):
        x, y = (i % cols) * tw, (i // cols) * (th + 22)
        im.paste(t, (x, y + 22))
        d.text((x + 4, y + 2), f"{i}s", font=font(F_MENLO, 16), fill=(255, 255, 255))
    im.save(path, quality=80)
