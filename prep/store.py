"""Episode folders and project.json: create, find, read, and change it safely (one writer at a time, across
threads and processes)."""
import datetime
import json
import os
import re
import threading
import time
import unicodedata

from .config import DATA_DIR


def project_dir(pid):
    return os.path.join(DATA_DIR, pid)


def source_dir(pid):
    return os.path.join(DATA_DIR, pid, "source")


def work_dir(pid):
    return os.path.join(DATA_DIR, pid, "work")


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


STOP = {"in", "the", "and", "of", "on", "with", "podcast", "episode", "ep", "1080p", "720p", "h264", "final",
        "v1", "v2"}


_LATIN = str.maketrans({"ß": "ss", "æ": "ae", "Æ": "ae", "ø": "o", "Ø": "o", "œ": "oe", "đ": "d", "Đ": "d", "ł": "l",
                        "Ł": "l", "þ": "th", "ð": "d"})  # letters NFD doesn't take apart


def slugify(s, max_words=2):
    s = "".join(ch for ch in unicodedata.normalize("NFD", s.translate(_LATIN)) if not unicodedata.combining(ch)).lower()
    s = re.sub(r"\.[a-z0-9]{2,4}$", "", s)
    words = [w for w in re.sub(r"[^a-z0-9]+", " ", s).split() if w not in STOP and not re.fullmatch(r"s\d+e\d+", w)]
    return "-".join(words[:max_words]) or "episode"


def create_project(title, slug=None):
    os.makedirs(DATA_DIR, exist_ok=True)
    base = f"{datetime.date.today():%Y-%m}-{slugify(slug, 3) if slug else slugify(title)}"
    pid, n = base, 2
    while os.path.exists(project_dir(pid)):
        pid, n = f"{base}-{n}", n + 1
    os.makedirs(source_dir(pid))
    os.makedirs(work_dir(pid))
    p = {"id": pid, "title": re.sub(r"\.[a-z0-9]{2,4}$", "", title, flags=re.I).strip() or pid, "createdAt": now(),
         "updatedAt": now(), "files": [], "steps": {}, "glossary": [], "speakers": {}}
    _write(p)
    return p


def list_projects():
    out = []
    if os.path.isdir(DATA_DIR):
        for name in os.listdir(DATA_DIR):
            f = os.path.join(DATA_DIR, name, "project.json")
            if os.path.exists(f):
                try:
                    out.append(read_json(f))
                except ValueError:
                    pass
    return sorted(out, key=lambda p: p.get("createdAt", ""), reverse=True)


def get_project(pid):
    if not re.fullmatch(r"[\w.-]+", pid):
        raise SystemExit("bad project id")
    f = os.path.join(project_dir(pid), "project.json")
    if not os.path.exists(f):
        raise SystemExit(f"project {pid} not found")
    return read_json(f)


def find_project(q):
    """an episode by folder name or any unique part of it"""
    if not q:
        raise SystemExit("which episode?")
    if os.path.exists(os.path.join(project_dir(q), "project.json")):
        return get_project(q)
    hits = [p for p in list_projects() if q in p["id"]]
    if len(hits) == 1:
        return hits[0]
    raise SystemExit(f'"{q}" matches {", ".join(p["id"] for p in hits)}' if hits else f'no episode matches "{q}"')


def _write(p):
    p["updatedAt"] = now()
    f = os.path.join(project_dir(p["id"]), "project.json")
    tmp = f"{f}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(p, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, f)


_lock = threading.Lock()


class _FileLock:
    """lock file shared by CLI processes so they never interleave writes; a stale one (crash) expires after ~10 s"""

    def __init__(self, path):
        self.path = path

    def __enter__(self):
        for i in range(10 ** 6):
            try:
                os.close(os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return self
            except FileExistsError:
                if i > 400:
                    try:
                        os.remove(self.path)
                    except FileNotFoundError:
                        pass
                time.sleep(0.025)

    def __exit__(self, *a):
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass


def update_project(pid, fn):
    """read-modify-write project.json: fn(project) changes it in place"""
    with _lock, _FileLock(os.path.join(project_dir(pid), ".lock")):
        p = get_project(pid)
        fn(p)
        _write(p)
        return p


def set_step(project_id, step, **patch):
    """merge patch into project.steps[step] (None removes a field)"""
    def f(p):
        p["steps"][step] = {**p["steps"].get(step, {"status": "idle"}), **patch}
        p["steps"][step] = {k: v for k, v in p["steps"][step].items() if v is not None}
    return update_project(project_id, f)


def read_json(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
