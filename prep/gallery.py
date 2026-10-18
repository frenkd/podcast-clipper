"""`./clip gallery <episode>`: an index.html next to the previews (and the finals) to watch them all side by side in
a browser, with each clip's QA result. Open it, or send the folder."""
import glob
import html
import os

from .store import project_dir

PAGE = """<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
  :root{{--bg:#121215;--card:#1e1e23;--line:#34343a;--text:#f4f4f5;--muted:#9a9aa3;--accent:#ffc53d;--bad:#ff6b6b}}
  body{{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,sans-serif;padding:32px 16px}}
  h1{{font-size:26px;margin:0 0 4px}} p{{color:var(--muted);margin:0 0 24px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:20px}}
  figure{{margin:0;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px}}
  video{{width:100%;aspect-ratio:9/16;border-radius:8px;background:#000;display:block}}
  figcaption{{margin-top:10px}} b{{color:var(--accent)}} span{{display:block;color:var(--muted);font-size:14px}}
  span.bad{{color:var(--bad)}}
</style>
<h1>{title}</h1>
<p>{count} clip(s) in {where}. Each card shows the automatic check (QA): OK, or what to look at.</p>
<div class="grid">
{cards}
</div>
</html>
"""


def _qa(base, qa_dir):
    for p in (base + ".qa.txt", os.path.join(qa_dir, os.path.basename(base) + ".qa.txt")):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                lines = [x.strip() for x in f if x.strip()]
            return lines[0] if lines else "OK"
    return ""


def write(pid):
    """-> paths of the index.html files written (preview/ and final/, where there are clips)"""
    root, out = project_dir(pid), []
    for where in ("preview", "final"):
        d = os.path.join(root, where)
        vids = sorted(glob.glob(os.path.join(d, "*.mp4")))
        if not vids:
            continue
        cards = []
        for v in vids:
            base = os.path.splitext(v)[0]
            qa = _qa(base, os.path.join(root, "work", "render", "final"))
            mb = os.path.getsize(v) / 1e6
            note = f'<span class="{"" if qa in ("", "OK") else "bad"}">{html.escape(qa or "no QA file")}</span>'
            cards.append(f'  <figure><video src="{html.escape(os.path.basename(v))}" controls playsinline preload="metadata">'
                         f'</video><figcaption><b>{html.escape(os.path.basename(base))}</b><span>{mb:.1f} MB</span>'
                         f'{note}</figcaption></figure>')
        page = os.path.join(d, "index.html")
        with open(page, "w", encoding="utf-8") as f:
            f.write(PAGE.format(title=html.escape(f"{pid}: {where}"), count=len(vids), where=f"{where}/",
                                cards="\n".join(cards)))
        out.append(page)
    return out
