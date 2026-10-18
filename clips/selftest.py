"""End-to-end check of the clip engine on a generated test video (no episode or API keys needed).

  ./clip selftest
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

CLIP = '''
from clipkit import *

E = Edit(tight((0.2, 5.6)))
CHUNKS = chunk_words(E.words(), 3, 18)
CARD_T = 3.0


def draw(t, fr, face):
    c = Image.fromarray(crop(fr, face, W, H, zoom=1.2, face_y=0.3)).convert("RGBA")
    if t < E.dur:
        if t >= CARD_T:
            k = clamp01((t - CARD_T) / 0.5)
            board = on_panel(tag("it works", 52, k))
            place(c, board, W / 2, 1150, 1, ease_out(k / 0.3))
        intro(c, "Engine self-test", face, t)
        place(c, cap(active(CHUNKS, t), t), W / 2, CAPTION_Y)
    else:
        end_card(t - E.dur, c)
    return c


def sound(mix):
    mix.add(CARD_T, sfx_pop(), 0.6)


render("01_selftest", E, draw, sound, bed=bed_soft, bed_gain=0.1, tail=1.0)
'''


def main():
    tmp = tempfile.mkdtemp(prefix="clipkit-selftest-")
    try:
        proj = os.path.join(tmp, "projects", "selftest")
        for d in ("source", "work", "scripts"):
            os.makedirs(os.path.join(proj, d))
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=6", "-f", "lavfi",
                        "-i", "sine=f=220:d=6", "-shortest", "-c:v", "mpeg4", "-q:v", "3", "-c:a", "aac",  # built into every ffmpeg
                        os.path.join(proj, "source", "test.mp4")], check=True)
        json.dump({"id": "selftest", "title": "Self-test", "episode": "S00E00", "people": ["Host", "Test Guest"],
                   "files": [{"name": "test.mp4", "kind": "video"}], "video": {"width": 1920, "height": 1080, "fps": 30}},
                  open(os.path.join(proj, "project.json"), "w"))
        words = "this is just a test to see that everything works as it should".split()
        json.dump([{"t": w, "s": 300 + i * 450, "e": 300 + i * 450 + 350, "sp": "1"} for i, w in enumerate(words)],
                  open(os.path.join(proj, "work", "words.json"), "w"))
        open(os.path.join(proj, "scripts", "01_selftest.py"), "w").write(CLIP)
        env = dict(os.environ, CLIPPER_DATA_DIR=os.path.join(tmp, "projects"), CLIPPER_HOST="Host")
        r = subprocess.run([sys.executable, os.path.join(HERE, "run.py"), "selftest"], env=env)
        out = os.path.join(proj, "preview", "01_selftest")
        missing = [x for x in (".mp4", ".cover.jpg", ".qa.txt", ".events.jpg", ".grid.jpg") if not os.path.exists(out + x)]
        if r.returncode or missing:
            raise SystemExit(f"self-test FAILED (exit {r.returncode}, missing {missing or 'nothing'})")
        if os.path.getsize(out + ".mp4") > 10_000_000:  # previews must stay shareable (Discord: 10 MB)
            raise SystemExit(f"self-test FAILED: the preview is {os.path.getsize(out + '.mp4') / 1e6:.1f} MB")
        print("self-test passed: the engine renders, checks and reviews clips on this machine")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
