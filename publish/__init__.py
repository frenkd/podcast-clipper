"""Publishing finished clips to platforms (optional: nothing in prep/ or clips/ depends on this package).

Per episode and platform there is a plan, projects/<id>/<platform>.json: one item per clip with its text, file and
publish time. `./clip publish <platform> plan` drafts it from export/, you edit it, `check` validates it, `upload`
uploads what isn't up yet and writes each id back right away (so a rerun never posts twice).

A platform is one module in this package with:
  ITEMS                        the plan's list key ("shorts" for YouTube)
  login()                      one-time sign-in (keys in .env; the token stays on this machine)
  draft_plan(pid) -> plan      a first plan from export/ (use exported() below)
  problems(pid, item) -> [...] what's wrong with one item; empty means ready
  status(item) -> str          one line for `check`: uploaded / scheduled / private
  upload(pid, only=None)       upload the items that aren't up yet (only: 1-based numbers)
and an entry in PLATFORMS. README.md says what each platform's API allows."""
import datetime
import glob
import importlib
import json
import os

from prep.config import FFPROBE
from prep.media import run
from prep.store import find_project, project_dir

PLATFORMS = {"youtube": "Shorts with title, description and a publish time; upload-only"}


def get(name):
    if name not in PLATFORMS:
        raise SystemExit(f"no platform {name!r}: {', '.join(PLATFORMS)} (more in publish/README.md)")
    return importlib.import_module(f"publish.{name}")


# the plan: projects/<id>/<platform>.json

def plan_path(pid, name):
    return os.path.join(project_dir(pid), f"{name}.json")


def read_plan(pid, name):
    p = plan_path(pid, name)
    if not os.path.exists(p):
        raise SystemExit(f"no {os.path.relpath(p)} yet: run `./clip publish {name} plan <episode>` and edit it")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write_plan(pid, name, plan):
    p = plan_path(pid, name)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, p)


def _from_markdown(text):
    """export/<clip>/description.md -> (title, description): the first "# " heading, then everything after it"""
    lines = text.strip().splitlines()
    i = next((i for i, x in enumerate(lines) if x.startswith("# ")), None)
    if i is None:
        return "", text.strip()
    return lines[i][2:].strip(), "\n".join(lines[i + 1:]).strip()


def exported(pid):
    """[(video path relative to the episode, title, description)] for every export/<clip>/ with an .mp4; title and
    description come from its description.md when there is one ("# Title", then the description)"""
    root, out = project_dir(pid), []
    for d in sorted(glob.glob(os.path.join(root, "export", "*", ""))):
        video = next(iter(sorted(glob.glob(os.path.join(d, "*.mp4")))), None)
        if not video:
            continue
        title, desc = "", ""
        if os.path.exists(os.path.join(d, "description.md")):
            with open(os.path.join(d, "description.md"), encoding="utf-8") as f:
                title, desc = _from_markdown(f.read())
        out.append((os.path.relpath(video, root), title, desc))
    if not out:
        raise SystemExit(f"no clips in {os.path.relpath(os.path.join(root, 'export'))}/<clip>/*.mp4")
    return out


def probe(path):
    """(width, height, seconds) of a video"""
    out = json.loads(run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", path]))
    s = out["streams"][0]
    return s["width"], s["height"], float(out["format"]["duration"])


def when(s):
    """an ISO time with a time zone -> UTC datetime"""
    t = datetime.datetime.fromisoformat(s)
    if t.tzinfo is None:
        raise ValueError(f"publishAt needs a time zone, e.g. {s}+02:00")
    return t.astimezone(datetime.timezone.utc)


# ./clip publish

USAGE = "./clip publish <platform> login | plan <episode> [--force] | check <episode> | upload <episode> [1 3 …]"


def cli(rest):
    if not rest:
        print("platforms (./clip publish <platform> …):")
        for name, what in PLATFORMS.items():
            print(f"  {name:10} {what}")
        print(f"\n{USAGE}\nWhat other platforms' APIs allow: publish/README.md")
        return 0
    mod, name = get(rest[0]), rest[0]
    sub, pos = (rest[1] if len(rest) > 1 else ""), [x for x in rest[2:] if not x.startswith("--")]
    if sub == "login":
        mod.login()
        return 0
    if sub not in ("plan", "check", "upload"):
        raise SystemExit(USAGE)
    pid = find_project(pos[0] if pos else None)["id"]
    if sub == "plan":
        if os.path.exists(plan_path(pid, name)) and "--force" not in rest:
            raise SystemExit(f"{os.path.relpath(plan_path(pid, name))} exists (--force overwrites it)")
        write_plan(pid, name, mod.draft_plan(pid))
        print(f"{os.path.relpath(plan_path(pid, name))}: check the texts, set the publish times")
    elif sub == "check":
        bad = 0
        for i, item in enumerate(read_plan(pid, name)[mod.ITEMS], 1):
            issues = mod.problems(pid, item)
            bad += bool(issues)
            print(f"{i}. {item.get('title')}  \x1b[2m{mod.status(item)}\x1b[0m")
            for x in issues:
                print(f"   \x1b[31m{x}\x1b[0m")
        return 1 if bad else 0
    else:
        mod.upload(pid, {int(x) for x in pos[1:]} or None)
    return 0
