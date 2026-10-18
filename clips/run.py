"""Render an episode's clips in parallel and print a QA table.

  ./clip render <episode> [clip …] [--final] [-j N]

  <episode>  the episode folder, or any unique part of its name (e.g. interview)
  clip       a script path, or the start of a file name in projects/<id>/scripts/ (e.g. 03);
             default: every script there (files starting with _ are helpers and are skipped)
  --final    full quality (1080x1920, 30 fps, cover chosen by the vision model) into projects/<id>/final/;
             without it you get fast previews in projects/<id>/preview/
  -j N       clips rendered at once (default: about a third of the CPU cores)
"""
import argparse, glob, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(usage=__doc__)
    ap.add_argument("project")
    ap.add_argument("clips", nargs="*")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("-j", type=int, default=max(1, (os.cpu_count() or 3) // 3))
    a = ap.parse_args()

    os.environ["CLIP_PROJECT"] = a.project
    sys.path.insert(0, HERE)
    from clipkit import angles  # camera angles + who sits where: once per episode, before clips render in parallel
    angles.analyse()
    from clipkit.project import PROJECT, PROJECT_DIR, WORK  # validates the episode, words.json and fonts up front
    from clipkit import encode
    os.environ["CLIP_ENCODER"] = encode.pick()  # once for the batch; every clip uses the same encoder

    scripts_dir = os.path.join(PROJECT_DIR, "scripts")
    found = sorted(p for p in glob.glob(os.path.join(scripts_dir, "*.py")) if not os.path.basename(p).startswith("_"))
    todo = []
    for c in a.clips or [None]:
        if c is None:
            todo += found
        elif os.path.isfile(c):
            todo.append(os.path.abspath(c))
        else:
            hits = [p for p in found if os.path.basename(p).startswith(c)]
            if len(hits) != 1:
                raise SystemExit(f"'{c}' matches {[os.path.basename(h) for h in hits] or 'no script'} in {scripts_dir}")
            todo += hits
    if not todo:
        raise SystemExit(f"no clip scripts in {scripts_dir}")

    os.makedirs(os.path.join(WORK, "render"), exist_ok=True)
    mode = "final" if a.final else "preview"
    print(f"{PROJECT['id']}: {len(todo)} clip(s), {mode}, {min(a.j, len(todo))} at a time, {encode.CODEC[os.environ['CLIP_ENCODER']]}")

    def one(path):
        name = os.path.splitext(os.path.basename(path))[0]
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([HERE, os.path.dirname(path)]), PREVIEW="" if a.final else "1")
        t0 = time.time()
        r = subprocess.run([sys.executable, "-W", "ignore", path], env=env, capture_output=True, text=True)
        log = os.path.join(WORK, "render", f"{name}.{mode}.log")
        open(log, "w").write(r.stdout + r.stderr)
        out = next((l.split("-> ", 1)[1] for l in r.stdout.splitlines() if " -> " in l), None)
        qa_lines = r.stdout.split("QA: ", 1)[1].strip() if "QA: " in r.stdout else "?"
        ok = r.returncode == 0 and (qa_lines == "OK" or qa_lines.startswith("notes: "))
        status = "OK" if ok else ("FAILED" if r.returncode else "QA")
        print(f"  {status:6} {name:34} {time.time() - t0:5.0f}s  {out or log}")
        if ok and qa_lines != "OK":  # notes: worth a look, not a failure
            print("         " + qa_lines.replace("\n", "\n         "))
        if not ok:
            print("         " + (qa_lines if r.returncode == 0 else (r.stderr.strip().splitlines() or ["?"])[-1]).replace("\n", "\n         "))
        return ok

    with ThreadPoolExecutor(a.j) as ex:
        results = list(ex.map(one, todo))
    print(f"{sum(results)}/{len(results)} clean" + ("" if all(results) else "  (fix, then run again; logs in work/render/)"))
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
