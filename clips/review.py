"""Frame grid of any video, for a closer look than the automatic <name>.grid.jpg.

  ./clip review <video.mp4> <out.jpg> [--step 0.25] [--from 12] [--to 16]
"""
import argparse, math, os, subprocess
from PIL import Image, ImageDraw, ImageFont

ap = argparse.ArgumentParser(usage=__doc__)
ap.add_argument("video")
ap.add_argument("out")
ap.add_argument("--step", type=float, default=1.0, help="seconds between frames")
ap.add_argument("--from", dest="t0", type=float, default=0.0)
ap.add_argument("--to", dest="t1", type=float, default=None)
ap.add_argument("--width", type=int, default=180)
a = ap.parse_args()

w, h = a.width, int(a.width * 16 / 9)
cmd = ["ffmpeg", "-v", "error", "-ss", str(a.t0)] + (["-t", str(a.t1 - a.t0)] if a.t1 else []) + \
      ["-i", a.video, "-vf", f"fps=1/{a.step},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
raw = subprocess.check_output(cmd)
n, cols = len(raw) // (w * h * 3), 8
im = Image.new("RGB", (cols * w, max(1, math.ceil(n / cols)) * (h + 22)), (40, 40, 40))
d, f = ImageDraw.Draw(im), ImageFont.truetype(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "fonts", "Iosevka-Regular.ttf"), 16)
for i in range(n):
    x, y = (i % cols) * w, (i // cols) * (h + 22)
    im.paste(Image.frombytes("RGB", (w, h), raw[i * w * h * 3:(i + 1) * w * h * 3]), (x, y + 22))
    d.text((x + 4, y + 2), f"{a.t0 + i * a.step:.2f}s", font=f, fill=(255, 255, 255))
im.save(a.out, quality=82)
print(f"{n} frames -> {a.out}")
