"""What a clip looks like under each app's UI (Instagram, X, LinkedIn, TikTok), side by side.

  ./clip zones <video.mp4 | image.jpg> <out.jpg> [--at 3.5 12 20] [--apps instagram x linkedin tiktok shorts]
"""
import argparse, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image  # noqa: E402

from clipkit.safezones import PLATFORMS, sheet  # noqa: E402

ap = argparse.ArgumentParser(usage=__doc__)
ap.add_argument("src")
ap.add_argument("out")
ap.add_argument("--at", type=float, nargs="*", default=None, help="seconds into the video (default: 25/50/75%%)")
ap.add_argument("--apps", nargs="*", default=["instagram", "x", "linkedin", "tiktok"], choices=list(PLATFORMS))
a = ap.parse_args()

frames = []
if a.src.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
    frames = [Image.open(a.src).convert("RGB")]
else:
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", a.src]))
    for t in a.at or [dur * f for f in (0.25, 0.5, 0.75)]:
        raw = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", a.src, "-frames:v", "1",
                                       "-vf", "scale=1080:1920", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
        frames.append(Image.frombytes("RGB", (1080, 1920), raw))
rows = [sheet(f, a.apps) for f in frames]
out = Image.new("RGB", (rows[0].width, sum(r.height for r in rows) + 8 * (len(rows) - 1)), (30, 30, 30))
for i, r in enumerate(rows):
    out.paste(r, (0, i * (r.height + 8)))
out.save(a.out, quality=85)
print(f"{len(frames)} frame(s) x {len(a.apps)} apps -> {a.out}")
