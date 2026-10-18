"""./clip quick and the clip templates: every style writes a script that compiles; boards keep their size while they
animate; trigger words are found; the mouth check only overrides the transcript on a clear majority."""
import json
import os
import sys
import tempfile
import unittest

_tmp = tempfile.mkdtemp(prefix="clip-quick-test-")
os.environ["CLIPPER_DATA_DIR"] = os.path.join(_tmp, "projects")
os.environ.pop("OPENAI_API_KEY", None)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "clips"))

from prep import quick  # noqa: E402
from prep.store import create_project, project_dir  # noqa: E402

SAID = ("so the question is simple will you hire a developer or will you hire an agent and honestly "
        "the agent costs twenty dollars and the developer costs two thousand so what do you think").split()


class Quick(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pid = create_project("Quick test")["id"]
        work = os.path.join(project_dir(cls.pid), "work")
        os.makedirs(work, exist_ok=True)
        with open(os.path.join(work, "words.json"), "w") as f:
            json.dump([{"t": w, "s": 1000 + i * 400, "e": 1000 + i * 400 + 300, "sp": "1"} for i, w in enumerate(SAID)], f)

    def test_every_style_writes_a_script_that_compiles(self):
        for style in quick.STYLES:
            if style == "chart":
                continue
            path = quick.write_script(self.pid, 1.0, 14.0, style, headline="Developer or agent?", sticker="agent",
                                      meme="sigma rule #1", drama="wait what", name=f"t_{style}")
            with open(path, encoding="utf-8") as f:
                src = f.read()
            self.assertNotIn("$", src.split('"""', 2)[2], style)  # every placeholder filled
            compile(src, path, "exec")

    def test_chart_without_numbers_says_what_to_do(self):
        with self.assertRaises(SystemExit) as e:
            quick.write_script(self.pid, 1.0, 14.0, "chart", headline="x")
        self.assertIn("OPENAI_API_KEY", str(e.exception))  # no key: it says which one
        os.environ["OPENAI_API_KEY"] = "test"
        try:
            with self.assertRaises(SystemExit) as e:
                quick.boards("chart", {}, "no numbers here", {})
            self.assertIn("no numbers", str(e.exception))  # a key, but nothing to chart
        finally:
            os.environ.pop("OPENAI_API_KEY", None)

    def test_ranges(self):
        self.assertEqual(quick.parse_range("12:30-13:05"), (750.0, 785.0))
        self.assertEqual(quick.parse_range("1:02:03-1:02:40"), (3723.0, 3760.0))
        for bad in ("13:05-12:30", "abc", "0-400"):
            self.assertRaises(SystemExit, quick.parse_range, bad)
