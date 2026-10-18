"""`./clip …`: the one command for this repo. Run it without arguments for help."""
import argparse
import os
import subprocess
import sys

from prep.config import DATA_DIR, HOST, ROOT
from prep.files import add_file
from prep.fixes import add_fixes, parse_fix
from prep.steps import auto_run, clean_path, step_clean, step_context, step_speakers, step_transcribe
from prep.store import create_project, find_project, get_project, list_projects, project_dir, read_json, update_project
from prep.subtitles import fmt_clock, to_srt

HELP = f"""./clip: podcast episode -> short vertical clips

prepare an episode
  new <video> [notes.md subs.srt …] [--slug name] [--go]   new episode folder (--go: run all steps)
  add <episode> <files…>                  add notes, a script, subtitles…
  go <episode>                            run the steps not done yet: context -> transcribe -> clean
  step <episode> context|transcribe|clean [--audio|--subs]   re-run one step (--audio: from the audio, not subtitles)
  step <episode> speakers                 re-diarize only (keeps words and timings), e.g. after a speaker mix-up
  ls | show <episode>                     list episodes | status of one
  meta <episode> [--title …] [--episode S05E07] [--guest "First Last"] [--episode-title "…"] [--cuts tight|normal|loose|0.6]
  fix <episode> ["wrong => right" …]      fix names/phrases in transcript + captions (no args: list)
  srt <episode>                           full-episode subtitles -> projects/<episode>/episode/subtitles.srt

make clips
  quick <episode> 12:30-13:05 [--style chill|bold|meme|dramatic|credits|documentary|news|rewind|list|chart|versus] [--headline …]   the fast path: one clip from a template,
                                          rendered as a preview (edit projects/<episode>/scripts/NN_….py after)
  render <episode> [clips…] [--final] [-j N]   render clip scripts (fast previews unless --final) + QA
  angles <episode> [--force]              camera angles + who sits where (work/angles.json, angles.jpg)
  angles <episode> --set A2=3 C1=1        correct it after looking at angles.jpg (angle A, 2nd face from left = speaker 3)
  angles <episode> --who 640 680          who is talking when, by whose mouth moves (check diarization; Edit(who=…))
  transcript <episode>                    the transcript to read: speaker turns with times (also work/transcript.txt)
  gallery <episode>                       a page to watch every preview (and final) side by side, with QA
  review <video.mp4> <out.jpg> [--step 0.25] [--from 12] [--to 16]   frame grid of any video
  zones <video.mp4|image> <out.jpg> [--at 3 12] [--apps instagram x linkedin tiktok]   under each app's UI

publish (optional, publish/: platforms and what their APIs allow are in publish/README.md)
  publish                                 list the platforms
  publish youtube login                   sign in once, pick the channel (the token can only upload)
  publish youtube plan <episode> [--force]   draft projects/<episode>/youtube.json from export/ (then edit it)
  publish youtube check <episode>         validate it: titles, files, vertical, ≤3 min, publish times
  publish youtube upload <episode> [1 3 …]   upload what isn't up yet, scheduled (cover, related video: Studio)
  yt …                                    short for `publish youtube …`

checks
  selftest                                render a generated test clip end to end (~10 s)
  test                                    unit tests

<episode> is the folder name or any unique part of it. Episodes live in {DATA_DIR}"""


def show(p):
    dim = lambda s: f"\x1b[2m{s}\x1b[0m" if sys.stdout.isatty() else s
    print(f"{p['title']}  {dim(p['id'])}" + (f"  {p['episode']}" if p.get("episode") else "")
          + (dim("  " + ", ".join(p["people"])) if p.get("people") else ""))
    if p.get("video"):
        v = p["video"]
        print(dim(f"  {fmt_clock(v['duration'])}, {v['width']}x{v['height']}"))
    for f in p["files"]:
        print(dim(f"    {f['kind']:<9} {f['name']}"))
    steps = [f"{k}: {v.get('status')}" + (f" ({v['error']})" if v.get("error") else "") for k, v in p["steps"].items()]
    if steps:
        print("  " + "   ".join(steps))


def _engine(script, args, episode=None):
    from prep.config import FFMPEG
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([ROOT, os.path.join(ROOT, "clips")]))
    if os.path.isabs(FFMPEG):  # the engine calls plain `ffmpeg`: the one prep found comes first on its PATH
        env["PATH"] = os.path.dirname(FFMPEG) + os.pathsep + env.get("PATH", "")
    if episode:
        env["CLIP_PROJECT"] = episode
    return subprocess.call([sys.executable, *script, *args], env=env)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(HELP)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "render":
        return _engine([os.path.join(ROOT, "clips", "run.py")], rest)
    if cmd == "review":
        return _engine([os.path.join(ROOT, "clips", "review.py")], rest)
    if cmd == "zones":
        return _engine([os.path.join(ROOT, "clips", "zones.py")], rest)
    if cmd == "selftest":
        return _engine([os.path.join(ROOT, "clips", "selftest.py")], rest)
    if cmd == "test":
        return _engine(["-m", "unittest", "discover", "-s", os.path.join(ROOT, "tests"), "-t", ROOT], rest)
    if cmd == "angles":
        p = find_project(rest[0] if rest else None)
        return _engine(["-W", "ignore", "-m", "clipkit.angles"], rest[1:], p["id"])

    if cmd == "quick":
        from prep import quick
        ap = argparse.ArgumentParser(prog="./clip quick", description="the starter path: one clip from a time range")
        ap.add_argument("episode")
        ap.add_argument("range", help="start-end in the episode: 12:30-13:05, 12:30.5-13:04.8 or seconds (750-785)")
        ap.add_argument("--style", default="chill", choices=list(quick.STYLES))
        for opt in ("headline", "sticker", "meme", "drama", "credit", "doc-line", "name"):
            ap.add_argument(f"--{opt}")
        ap.add_argument("--ticker", help='news style: the ticker lines, separated by | ("One|Two|Three")')
        ap.add_argument("--final", action="store_true")
        q = ap.parse_args(rest)
        p = find_project(q.episode)
        a, b = quick.parse_range(q.range)
        path = quick.write_script(p["id"], a, b, q.style, q.headline, q.sticker, q.meme, q.name, q.drama, q.credit, q.doc_line,
                                  [x.strip() for x in q.ticker.split("|") if x.strip()] if q.ticker else None)
        print(f"wrote scripts/{os.path.basename(path)} in {p['id']} ({q.style}: {quick.STYLES[q.style]})\n"
              f"rendering a preview; edit the script and `./clip render {p['id']} {os.path.basename(path)[:2]}` any time", flush=True)
        return _engine([os.path.join(ROOT, "clips", "run.py")], [p["id"], path] + (["--final"] if q.final else []))
    if cmd == "transcript":
        from prep.steps import transcript_text
        p = find_project(rest[0] if rest else None)
        print(transcript_text(p["id"]), end="")
        return 0
    if cmd == "gallery":
        from prep import gallery
        p = find_project(rest[0] if rest else None)
        pages = gallery.write(p["id"])
        if not pages:
            raise SystemExit(f"no clips in {p['id']} yet: ./clip render {p['id']} (or ./clip quick)")
        for page in pages:
            print(f"{page}\n  open it in a browser: file://{page.replace(os.sep, '/')}")
        return 0
    if cmd in ("publish", "yt"):  # yt: short for `publish youtube`
        from publish import cli
        return cli(rest if cmd == "publish" else ["youtube", *rest])

    ap = argparse.ArgumentParser(prog=f"./clip {cmd}", add_help=False)
    ap.add_argument("pos", nargs="*")
    for flag in ("go", "audio", "soniox", "subs"):
        ap.add_argument(f"--{flag}", action="store_true")
    for opt in ("slug", "title", "episode", "episode-title", "guest", "cuts"):
        ap.add_argument(f"--{opt}")
    a = ap.parse_args(rest)
    pos = a.pos

    if cmd == "new":
        files = [os.path.abspath(f) for f in pos]
        from prep.files import kind_for
        for f in files:  # every file checked before an episode folder exists
            if not os.path.exists(f):
                raise SystemExit(f"no such file: {f}")
            kind_for(f)
        if not any(kind_for(f) == "video" for f in files):
            raise SystemExit("./clip new needs the episode's video (plus any notes or subtitles)")
        video = next((f for f in files if os.path.splitext(f)[1].lower() in (".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi")), None)
        p = create_project(a.title or (os.path.basename(video) if video else "New episode"), a.slug)
        for f in files:
            add_file(p["id"], f)
        print(f"created {p['id']} (commands take any unique part of the name, e.g. {p['id'].split('-', 2)[-1]})")
        if a.go:
            auto_run(p["id"])
        show(get_project(p["id"]))
    elif cmd == "add":
        p = find_project(pos[0] if pos else None)
        for f in pos[1:]:
            add_file(p["id"], os.path.abspath(f))
        show(get_project(p["id"]))
    elif cmd == "go":
        p = find_project(pos[0] if pos else None)
        auto_run(p["id"])
        show(get_project(p["id"]))
    elif cmd == "step":
        p = find_project(pos[0] if pos else None)
        step = pos[1] if len(pos) > 1 else ""
        if step == "context":
            step_context(p["id"])
        elif step == "transcribe":
            step_transcribe(p["id"], False if (a.audio or a.soniox) else True if a.subs else None)
        elif step == "clean":
            step_clean(p["id"])
        elif step == "speakers":
            step_speakers(p["id"])
        else:
            raise SystemExit("steps: context, transcribe, clean, speakers")
        show(get_project(p["id"]))
    elif cmd == "ls":
        for p in list_projects():
            print(f"{p['id']:<28} {p['title']}")
    elif cmd == "show":
        show(find_project(pos[0] if pos else None))
    elif cmd == "meta":
        p = find_project(pos[0] if pos else None)

        def f(p):
            if a.title:
                p["title"] = a.title
            if a.episode:
                p["episode"] = a.episode.upper()
            if a.episode_title:  # the end card shows it
                p["episodeTitle"] = a.episode_title
            if a.cuts:  # how hard tight() cuts pauses in this episode's clips
                p["cuts"] = float(a.cuts) if a.cuts.replace(".", "", 1).isdigit() else a.cuts
            if a.guest:
                host = p.get("host") or next((n for n in p.get("people") or [] if HOST.lower() in n.lower()), "")
                p["people"] = ([host] if host else []) + [a.guest]
        before = get_project(p["id"])
        after = update_project(p["id"], f)
        changed = [k for k in ("title", "episode", "episodeTitle", "cuts", "people") if before.get(k) != after.get(k)]
        print("set " + ", ".join(f"{k}: {after.get(k)}" for k in changed) if changed else "nothing changed")
    elif cmd == "fix":
        p = find_project(pos[0] if pos else None)
        if len(pos) > 1:
            add_fixes(p["id"], [parse_fix(x) for x in pos[1:]])
        for x in get_project(p["id"]).get("fixes") or []:
            print(f"  {x['from']}  =>  {x['to']}")
    elif cmd == "srt":
        p = find_project(pos[0] if pos else None)
        from prep.steps import transcript_path
        tr = read_json(clean_path(p["id"])) or read_json(transcript_path(p["id"]))  # raw when there's no cleanup
        if not tr or not tr.get("cues"):
            raise SystemExit(f"no transcript yet: ./clip go {p['id']}")
        d = os.path.join(project_dir(p["id"]), "episode")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "subtitles.srt"), "w", encoding="utf-8") as f:
            f.write(to_srt(tr["cues"]))
        print(os.path.join(d, "subtitles.srt") + ("" if read_json(clean_path(p["id"])) else
                                                 "  (from the raw transcript: no cleanup without OPENAI_API_KEY)"))
    else:
        print(HELP)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except SystemExit as e:
        if isinstance(e.code, str):
            sys.stderr.write(f"\x1b[31m{e.code}\x1b[0m\n" if sys.stderr.isatty() else f"{e.code}\n")
            sys.exit(1)
        raise
