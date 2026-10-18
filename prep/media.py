"""ffmpeg: probing, audio for speech recognition, a poster frame. Every ffmpeg call takes cores from a shared
budget (CPU_CORES) and is told to use exactly that many threads, so prep never takes over the machine."""
import json
import os
import subprocess
import threading

from .config import CPU_CORES, FFMPEG, FFPROBE


class Budget:
    """weighted semaphore: with budget.take(n): … waits until n units are free (used for CPU cores)"""

    def __init__(self, total):
        self.total, self.used = total, 0
        self.cv = threading.Condition()

    def take(self, n):
        n = max(1, min(n, self.total))
        budget = self

        class _Hold:
            def __enter__(self):
                with budget.cv:
                    budget.cv.wait_for(lambda: budget.used + n <= budget.total)
                    budget.used += n

            def __exit__(self, *a):
                with budget.cv:
                    budget.used -= n
                    budget.cv.notify_all()
        return _Hold()


CPU = Budget(CPU_CORES)


def _cap_threads(cmd, n):
    t = str(n)
    out = [cmd[0], "-filter_threads", t, "-filter_complex_threads", t]
    for i, a in enumerate(cmd[1:], 1):
        if a == "-i":
            out += ["-threads", t]
        if i == len(cmd) - 1:
            out += ["-threads", t]  # encoder threads, right before the output
        out.append(a)
    return out


def run(cmd, threads=1):
    """run a command, return stdout as text; raise with the end of stderr on failure"""
    try:
        if cmd[0] == FFMPEG:
            n = min(threads, CPU_CORES)
            with CPU.take(n):
                r = subprocess.run(_cap_threads(cmd, n), capture_output=True)
        else:
            r = subprocess.run(cmd, capture_output=True)
    except FileNotFoundError:
        raise SystemExit(f"{os.path.basename(cmd[0])} isn't installed (or not on PATH): install ffmpeg, or ask your agent "
                         "for the first-time setup") from None
    if r.returncode:
        tail = "\n".join(r.stderr.decode(errors="replace").splitlines()[-8:])
        raise RuntimeError(f"{cmd[0].split('/')[-1]} failed ({r.returncode}): {tail}")
    return r.stdout.decode(errors="replace")


def probe(path):
    j = json.loads(run([FFPROBE, "-v", "error", "-show_entries",
                        "format=duration:stream=codec_type,width,height,avg_frame_rate", "-of", "json", path]))
    v = next((s for s in j["streams"] if s.get("codec_type") == "video"), {})
    num, _, den = str(v.get("avg_frame_rate", "30/1")).partition("/")
    return {"duration": float(j["format"]["duration"]), "width": v.get("width", 0), "height": v.get("height", 0),
            "fps": float(num) / float(den) if den and float(den) else 30.0,
            "hasAudio": any(s.get("codec_type") == "audio" for s in j["streams"])}


def extract_audio(src, out, start=None, dur=None):
    """mono 16 kHz Opus: tiny uploads, plenty for speech recognition"""
    cmd = [FFMPEG, "-v", "error", "-y"] + (["-ss", f"{start:.3f}"] if start is not None else []) + ["-i", src]
    cmd += (["-t", f"{dur:.3f}"] if dur is not None else []) + ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "libopus",
                                                                  "-b:a", "32k", out]
    run(cmd)


def frame_jpeg(src, at, out, width=640):
    run([FFMPEG, "-v", "error", "-y", "-ss", f"{at:.3f}", "-i", src, "-frames:v", "1", "-vf", f"scale={width}:-2",
         "-q:v", "3", out])
