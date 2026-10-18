"""Adding source files (video, notes, subtitles) to an episode."""
import os
import re
import shutil

from .media import frame_jpeg, probe
from .store import get_project, now, source_dir, update_project, work_dir

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
SUB_EXT = {".srt", ".vtt"}
NOTE_EXT = {".md", ".txt", ".text", ".markdown", ".html", ".htm", ".csv", ".json", ".rtf"}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg", ".opus", ".aif", ".aiff", ".wma"}


def kind_for(name):
    """video, subtitles or context (notes); anything else is refused with a reason"""
    ext = os.path.splitext(name)[1].lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in SUB_EXT:
        return "subtitles"
    if ext in NOTE_EXT:
        return "context"
    if ext in AUDIO_EXT:
        raise SystemExit(f"{os.path.basename(name)} is audio only: the clips are cut from the episode's video (faces, "
                         "camera angles), so add the video file (.mp4, .mov, .mkv, .webm)")
    raise SystemExit(f"{os.path.basename(name)}: not a video ({', '.join(sorted(VIDEO_EXT))}), subtitles (.srt, .vtt) "
                     "or text notes (.md, .txt, …)")


def safe_name(name):
    return re.sub(r"[^\w.\- ()]+", "_", os.path.basename(name))[:160] or "file"


def add_file(pid, path):
    """copy a file into the episode's source/ (a hard link when possible: instant, no extra disk space)"""
    get_project(pid)
    if not os.path.exists(path):
        raise SystemExit(f"no such file: {path}")
    kind, name = kind_for(path), safe_name(path)
    os.makedirs(source_dir(pid), exist_ok=True)
    dest = os.path.join(source_dir(pid), name)
    if os.path.exists(dest):
        os.remove(dest)
    try:
        os.link(path, dest)
    except OSError:
        shutil.copyfile(path, dest)

    def f(p):
        if kind == "video":  # one video per episode: a new one invalidates everything derived from the old one
            for old in [x for x in p["files"] if x["kind"] == "video" and x["name"] != name]:
                try:
                    os.remove(os.path.join(source_dir(pid), old["name"]))
                except FileNotFoundError:
                    pass
            p["files"] = [x for x in p["files"] if x["kind"] != "video"]
            p["steps"] = {}
        p["files"] = [x for x in p["files"] if x["name"] != name]
        p["files"].append({"name": name, "kind": kind, "size": os.path.getsize(dest), "addedAt": now()})
        if kind != "video":
            p["steps"].pop("context", None)  # new notes: re-read them
    p = update_project(pid, f)
    if kind == "video":
        info = probe(dest)
        try:
            frame_jpeg(dest, min(info["duration"] * 0.3, 600), os.path.join(work_dir(pid), "poster.jpg"))
        except RuntimeError:
            pass

        def g(p):
            p["video"] = {k: info[k] for k in ("duration", "width", "height", "fps")}
            p["steps"]["probe"] = {"status": "done", "finishedAt": now()}
        p = update_project(pid, g)
    return p


def video_path(p):
    v = next((f for f in p["files"] if f["kind"] == "video"), None)
    if not v:
        raise SystemExit("add the episode video first")
    return os.path.join(source_dir(p["id"]), v["name"])
