"""Video encoding: the best H.264 encoder this machine's ffmpeg can actually use (hardware first, then libx264), the
ffmpeg command for a render, and the size cap that keeps previews shareable (Discord takes 10 MB).

Finals on a hardware encoder go at 12 Mbit/s: on real podcast clips VideoToolbox scored VMAF 98.0-98.3 there, above
libx264 crf 18 (97.6), at almost no CPU. x264 keeps crf 18. Encoders other than VideoToolbox and libx264 couldn't be
benchmarked here: they get the same bitrates, and each is only used after a test encode with these exact arguments
works. CLIP_ENCODER=<name> forces one (see ORDER)."""
import functools, os, shutil, subprocess, sys

ORDER = ["videotoolbox", "nvenc", "qsv", "amf", "vaapi", "x264", "mf", "openh264"]  # best first
CODEC = {"videotoolbox": "h264_videotoolbox", "nvenc": "h264_nvenc", "qsv": "h264_qsv", "amf": "h264_amf",
         "vaapi": "h264_vaapi", "x264": "libx264", "mf": "h264_mf", "openh264": "libopenh264"}
VAAPI_DEVICE = os.environ.get("CLIP_VAAPI_DEVICE", "/dev/dri/renderD128")

FINAL_KBPS, FINAL_PEAK_KBPS = 12000, 20000
PREVIEW_KBPS = 1500                 # previews (540x960, 15 fps) never need more
PREVIEW_MAX_BYTES = 9_500_000       # under Discord's 10 MB, with room for the container
AUDIO_KBPS = {False: 192, True: 128}  # final, preview
GOP = 60


def video_args(name, kbps=None, peak=None, crf=18, preset="medium"):
    """(args before the input, filter that ends the chain, codec args) for one encoder. kbps=None: x264 encodes at
    crf (no cap); every other encoder needs a bitrate. peak caps the bitrate (VBV), so a size budget holds."""
    rate = (["-b:v", f"{kbps}k"] if kbps else []) + (["-maxrate", f"{peak}k", "-bufsize", f"{peak}k"] if peak else [])
    if name == "x264":
        return [], "format=yuv420p", ["-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                                      *(["-maxrate", f"{peak}k", "-bufsize", f"{peak}k"] if peak else []), "-profile:v", "high"]
    if not kbps:
        raise ValueError(f"{name} needs a bitrate")
    return {
        "videotoolbox": ([], "format=yuv420p", ["-c:v", "h264_videotoolbox", *rate, "-profile:v", "high"]),
        "nvenc": ([], "format=yuv420p", ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", *rate, "-profile:v", "high"]),
        "qsv": ([], "format=nv12", ["-c:v", "h264_qsv", "-preset", "slower", *rate, "-profile:v", "high"]),
        "amf": ([], "format=nv12", ["-c:v", "h264_amf", "-quality", "quality", "-rc", "vbr_peak", *rate, "-profile:v", "high"]),
        "vaapi": (["-vaapi_device", VAAPI_DEVICE], "format=nv12,hwupload", ["-c:v", "h264_vaapi", *rate, "-profile:v", "high"]),
        "mf": ([], "format=nv12", ["-c:v", "h264_mf", "-hw_encoding", "1", *rate]),
        "openh264": ([], "format=yuv420p", ["-c:v", "libopenh264", *rate]),
    }[name]


def rates(name, seconds, preview, crf=18):
    """the bitrate settings for a render: finals at full quality; previews also within PREVIEW_MAX_BYTES"""
    if not preview:
        return dict(crf=crf) if name == "x264" else dict(kbps=FINAL_KBPS, peak=FINAL_PEAK_KBPS)
    budget = preview_budget_kbps(seconds)
    if name == "x264":
        return dict(crf=26, preset="ultrafast", peak=budget)
    return dict(kbps=min(PREVIEW_KBPS, budget), peak=budget)


def preview_budget_kbps(seconds, limit=PREVIEW_MAX_BYTES):
    """video bitrate that keeps a preview of this length under `limit` bytes (8% kept for the container)"""
    return max(150, int(limit * 0.92 * 8 / 1000 / max(seconds, 1.0)) - AUDIO_KBPS[True])


def command(path, wav, size, fps, seconds, preview, crf=18, name=None):
    """ffmpeg reading raw RGB frames on stdin plus a wav, writing the clip. RGB -> YUV uses the BT.709 matrix the
    file is tagged with (ffmpeg's default is BT.601, which showed (240, 66, 111) as (252, 84, 109))."""
    name = name or pick()
    pre, tail, venc = video_args(name, **rates(name, seconds, preview, crf))
    vf = ("scale=540:960:flags=bilinear:" if preview else "scale=") + f"out_color_matrix=bt709:out_range=tv,{tail}"
    return ["ffmpeg", "-v", "error", "-y", *pre, "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}",
            "-r", str(fps), "-i", "-", "-i", wav, "-map", "0:v", "-map", "1:a", "-vf", vf, *venc, "-g", str(GOP),
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000", "-c:a", "aac", "-b:a", f"{AUDIO_KBPS[preview]}k",
            "-shortest", "-movflags", "+faststart", path]


def fit(path, seconds, limit=PREVIEW_MAX_BYTES):
    """re-encode the video track of `path` smaller until the file is under `limit` bytes. A safety net: the bitrate
    cap normally keeps previews under it already, but hardware encoders treat it as a hint (VideoToolbox wrote
    32 Mbit/s of noise when asked for 0.5), so this uses libx264, whose cap holds, when there is one. -> final size"""
    name = "x264" if "libx264" in compiled() and works("x264") else pick()
    size = os.path.getsize(path)
    for _ in range(3):
        if size <= limit:
            return size
        kbps = max(100, int(preview_budget_kbps(seconds, limit) * min(1.0, limit / size) * 0.9))
        pre, tail, venc = video_args(name, kbps=kbps, peak=kbps, crf=30, preset="veryfast")
        tmp = path + ".fit.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *pre, "-i", path, "-map", "0", "-vf", tail, *venc, "-g", str(GOP),
                        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-c:a", "copy",
                        "-movflags", "+faststart", tmp], check=True, capture_output=True)
        os.replace(tmp, path)
        size = os.path.getsize(path)
    if size > limit:
        sys.stderr.write(f"warning: {os.path.basename(path)} is {size / 1e6:.1f} MB, over the {limit / 1e6:.1f} MB "
                         f"preview limit even after shrinking\n")
    return size


@functools.cache
def pick():
    """name of the best encoder that works here: CLIP_ENCODER if set (it must work), else the first in ORDER that
    this ffmpeg has and that passes a test encode"""
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg isn't installed (or not on PATH)")
    forced = os.environ.get("CLIP_ENCODER", "").strip().lower()
    if forced:
        if forced not in CODEC:
            raise SystemExit(f"CLIP_ENCODER={forced!r}: use one of {', '.join(ORDER)}")
        if not works(forced):
            raise SystemExit(f"CLIP_ENCODER={forced}: {CODEC[forced]} doesn't work with this ffmpeg/machine")
        return forced
    have = compiled()
    for name in ORDER:
        if CODEC[name] in have and works(name):
            return name
    raise SystemExit("this ffmpeg has no working H.264 encoder (install an ffmpeg build with libx264)")


@functools.cache
def compiled():
    """encoder names this ffmpeg was built with"""
    out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    return {l.split()[1] for l in out.splitlines() if len(l.split()) > 1 and l.split()[0].startswith("V")}


def works(name):
    """a 0.2 s test encode with the final and the preview arguments (a GPU encoder can be compiled in but have no
    GPU or driver behind it)"""
    for preview in (False, True):
        pre, tail, venc = video_args(name, **rates(name, 0.2, preview))
        try:
            r = subprocess.run(["ffmpeg", "-v", "error", *pre, "-f", "lavfi", "-i", "color=c=gray:s=1080x1920:r=30:d=0.2",
                                "-vf", f"scale=out_color_matrix=bt709:out_range=tv,{tail}", *venc, "-f", "null", "-"],
                               capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return False
        if r.returncode:
            return False
    return True

