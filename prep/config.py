"""Settings: the repo's .env, where episodes live, models, ffmpeg."""
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env(path=os.path.join(ROOT, ".env")):
    """KEY=value lines from .env into os.environ (values already set in the environment win)"""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.split(" #")[0].strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)


load_env()

DATA_DIR = os.path.abspath(os.path.join(ROOT, os.environ.get("CLIPPER_DATA_DIR", "projects")))
MODELS = {"smart": os.environ.get("OPENAI_MODEL_SMART", "gpt-6.1-sol"),
          "fast": os.environ.get("OPENAI_MODEL_FAST", "gpt-6-luna")}
SONIOX_MODEL = os.environ.get("SONIOX_MODEL", "stt-async-v5")
HOST = os.environ.get("CLIPPER_HOST", "")


def _ffmpeg():
    for c in (os.environ.get("FFMPEG_PATH"), "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
              "/usr/local/opt/ffmpeg-full/bin/ffmpeg"):
        if c and os.path.exists(c):
            return c
    return shutil.which("ffmpeg") or "ffmpeg"


FFMPEG = _ffmpeg()
FFPROBE = FFMPEG[:-len("ffmpeg")] + "ffprobe" if FFMPEG.endswith("ffmpeg") else "ffprobe"
CPU_CORES = max(1, int(os.environ.get("MAX_CORES", (os.cpu_count() or 4) - 2)))  # leave two cores for the machine


def require_key(name):
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"{name} is missing: add it to .env")
    return v


class ServiceError(RuntimeError):
    """an outside service said no (bad key, no credit, rate limit…): shown as one plain line, without a traceback"""


def api_error(service, key, code, body):
    """an API's HTTP error in words a newcomer can act on (the raw message stays at the end)"""
    low = (body or "").lower()
    if code in (401, 403) or "invalid_api_key" in low or "invalid api key" in low:
        what = f"{service} didn't accept the key: check {key} in .env (pasted whole, no spaces, still active)"
    elif code == 402 or "insufficient_quota" in low or ("quota" in low and code == 429) or "out of credit" in low:
        what = f"{service} says the account is out of credit or over its plan: top it up on their site"
    elif code == 429:
        what = f"{service} is rate-limiting this account: wait a minute and run it again"
    elif code == 413:
        what = f"{service} says the file is too big"
    elif code >= 500:
        what = f"{service} had a server error: run it again in a bit"
    else:
        what = f"{service} refused the request ({code})"
    detail = " ".join((body or "").split())[:240]
    return ServiceError(f"{what}. [{code}: {detail}]")
