"""The episode being clipped, output settings, fonts and small shared helpers."""
import functools, json, os, re, subprocess, sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS = os.path.join(REPO, "assets")
DATA_DIR = os.path.abspath(os.path.join(REPO, os.environ.get("CLIPPER_DATA_DIR", "projects")))


def dotenv(key):
    """setting from the environment, else from the repo's .env"""
    if os.environ.get(key):
        return os.environ[key]
    path = os.path.join(REPO, ".env")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].split("#")[0].strip().strip('"') or None
    return None


def find_project(q):
    """project folder by any unique part of its name (like ./clip); the most recently changed one if q is empty"""
    ids = sorted(d for d in os.listdir(DATA_DIR) if os.path.exists(os.path.join(DATA_DIR, d, "project.json"))) \
        if os.path.isdir(DATA_DIR) else []
    if not ids:
        raise SystemExit(f"no projects in {DATA_DIR}; run `./clip new <video> --go` first")
    if q:
        hits = [d for d in ids if d == q] or [d for d in ids if q in d]
        if len(hits) != 1:
            raise SystemExit(f"CLIP_PROJECT={q!r} matches {hits or 'no project'} in {DATA_DIR}")
        return os.path.join(DATA_DIR, hits[0])
    return os.path.join(DATA_DIR, max(ids, key=lambda d: os.path.getmtime(os.path.join(DATA_DIR, d, "project.json"))))


PROJECT_DIR = find_project(os.environ.get("CLIP_PROJECT"))
with open(os.path.join(PROJECT_DIR, "project.json"), encoding="utf-8") as _f:
    PROJECT = json.load(_f)
VIDEO = os.path.join(PROJECT_DIR, "source", next(f["name"] for f in PROJECT["files"] if f["kind"] == "video"))
WORDS_JSON = os.path.join(PROJECT_DIR, "work", "words.json")
WORK = os.path.join(PROJECT_DIR, "work")         # transcripts (from ./clip), plus cache/ and render/ (scratch)
CACHE = os.path.join(WORK, "cache")
os.makedirs(CACHE, exist_ok=True)
if not os.path.exists(WORDS_JSON):
    raise SystemExit(f"{WORDS_JSON} is missing; run `./clip go {PROJECT['id']}` first")

FPS = 30
PREVIEW = os.environ.get("PREVIEW") == "1"  # fast iteration: 15 fps, 540x960, quick encode, no vision call
STEP = 2 if PREVIEW else 1  # every STEP-th source frame is rendered
W, H = 1080, 1920
SR = 48000
_v = PROJECT.get("video") or {}
SW, SH = int(_v.get("width", 1920)), int(_v.get("height", 1080))

from .theme import load as _load_theme
THEME = _load_theme(PROJECT)  # theme.json + the episode's overrides (theme.py)
ACCENT = THEME["accent"]
ON_ACCENT = THEME["on_accent"]
TEXT = THEME["text"]
INK = (12, 12, 12)
LAYOUT = os.environ.get("CLIP_LAYOUT") or PROJECT.get("layout") or "overlay"  # boards over the video, or "split"
EPISODE = PROJECT.get("episode") or ""            # S05E07
EPISODE_TITLE = PROJECT.get("episodeTitle") or ""  # as published (end card)
LANG = PROJECT.get("language") or "en"
_people = PROJECT.get("people") or []
_host = dotenv("CLIPPER_HOST")
HOST = PROJECT.get("host") or (next((n for n in _people if re.search(_host, n, re.I)), "") if _host else "")
GUESTS = [n for n in _people if n != HOST]
GUEST = GUESTS[0] if GUESTS else ""          # the main guest (first after the host)
CUT_PRESETS = {"tight": 0.3, "normal": 0.45, "loose": 0.8}   # longest pause tight() keeps, in seconds
_cuts = PROJECT.get("cuts") or "normal"
MAX_GAP = float(CUT_PRESETS.get(_cuts, _cuts) if not isinstance(_cuts, (int, float)) else _cuts)
SPEAKER_NAMES = {str(k): v for k, v in (PROJECT.get("speakers") or {}).items() if v and v != "Unknown"}  # diarized id -> name

F_BLACK, F_XBOLD, F_BOLD, F_MED, F_REG = (THEME["fonts"][k] for k in ("black", "extrabold", "bold", "medium", "regular"))
F_MONO, F_MONO_B, F_MONO_XB = (THEME["fonts"][k] for k in ("mono", "mono_bold", "mono_heavy"))
FONT_DIRS = [  # macOS, Windows, Linux (missing ones are skipped)
    "/System/Library/Fonts", "/Library/Fonts", "~/Library/Fonts",
    *(os.path.join(os.environ[v], *sub) for v, sub in (("WINDIR", ["Fonts"]), ("LOCALAPPDATA", ["Microsoft", "Windows", "Fonts"]))
      if os.environ.get(v)),
    "/usr/share/fonts", "/usr/local/share/fonts", "~/.local/share/fonts", "~/.fonts"]


@functools.cache
def _installed():
    """lowercase file name -> path of every font in FONT_DIRS and their subfolders (the first one found wins)"""
    found = {}
    for d in FONT_DIRS:
        for root, _, files in os.walk(os.path.expanduser(d)):
            for f in files:
                found.setdefault(f.lower(), os.path.join(root, f))
    return found


def system_font(*names, fallback, installed=None):
    """the first of these font files on this machine, else the bundled `fallback`"""
    installed = _installed() if installed is None else installed
    return next((installed[n.lower()] for n in names if n.lower() in installed), fallback)


# system fonts the gallery and review sheets use, each with stand-ins on Windows / Linux and a bundled fallback
F_MONO_BUNDLED = os.path.join(ASSETS, "fonts", "JetBrainsMono-Regular.ttf")
F_SF = system_font("SFNS.ttf", "segoeui.ttf", "Inter-Regular.ttf", "NotoSans-Regular.ttf", "DejaVuSans.ttf", fallback=F_MED)
F_MENLO = system_font("Menlo.ttc", "consola.ttf", "DejaVuSansMono.ttf", "NotoSansMono-Regular.ttf", fallback=F_MONO_BUNDLED)
F_COURIER = system_font("Courier New Bold.ttf", "courbd.ttf", "LiberationMono-Bold.ttf", "DejaVuSansMono-Bold.ttf",
                        fallback=os.path.join(ASSETS, "fonts", "JetBrainsMono-Bold.ttf"))
F_TIMES = system_font("Times.ttc", "times.ttf", "LiberationSerif-Regular.ttf", "DejaVuSerif.ttf", "NotoSerif-Regular.ttf",
                      fallback=F_MED)
F_EMOJI = system_font("Apple Color Emoji.ttc", "seguiemj.ttf", "NotoColorEmoji.ttf", fallback=None)  # None: no emoji
F_FALLBACK = system_font("Arial Unicode.ttf", "seguisym.ttf", "segoeui.ttf", "DejaVuSans.ttf", "Menlo.ttc",
                         fallback=F_MONO_BUNDLED)  # glyphs the brand fonts lack (✓ ✗ ₂ …)
_missing = [f for f in (F_BLACK, F_XBOLD, F_BOLD, F_MED, F_MONO_BUNDLED) if not os.path.exists(f)]
if _missing:
    raise SystemExit("missing bundled fonts (is the checkout complete?): " + ", ".join(_missing))


def run(cmd, **kw):
    """run a command, return stdout; exit with its stderr on failure"""
    r = subprocess.run(cmd, capture_output=True, **kw)
    if r.returncode:
        sys.stderr.write(" ".join(map(str, cmd)) + "\n" + r.stderr.decode(errors="replace")[-3000:])
        raise SystemExit(1)
    return r.stdout
