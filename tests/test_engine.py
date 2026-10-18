"""Unit tests for the clip engine's own logic (no video needed: a tiny fake episode is set up first)."""
import json
import os
import sys
import tempfile
import unittest

_tmp = tempfile.mkdtemp(prefix="clipkit-test-")
_proj = os.path.join(_tmp, "projects", "unit")
os.makedirs(os.path.join(_proj, "work"))
os.makedirs(os.path.join(_proj, "source"))
with open(os.path.join(_proj, "project.json"), "w") as _f:
    json.dump({"id": "unit", "title": "Unit", "people": ["Alex Host", "Ana Guest"],
               "files": [{"name": "x.mp4", "kind": "video"}]}, _f)
with open(os.path.join(_proj, "work", "words.json"), "w") as _f:
    json.dump([{"t": "ena", "s": 0, "e": 300, "sp": "1"}], _f)
os.environ.update(CLIPPER_DATA_DIR=os.path.join(_tmp, "projects"), CLIP_PROJECT="unit", CLIPPER_HOST="Alex")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "clips"))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from clipkit import draw, encode, state  # noqa: E402
from clipkit.brand import _hook_slot  # noqa: E402
from clipkit.draw import place  # noqa: E402
from clipkit.project import ASSETS, GUEST, system_font  # noqa: E402
from clipkit.style import bar, gradient, panel, tag  # noqa: E402
from clipkit.words import Edit  # noqa: E402


class Theme(unittest.TestCase):
    def test_defaults_and_overrides(self):
        from clipkit import theme
        t = theme.load(path=os.path.join(_tmp, "none.json"))
        self.assertEqual(t["accent"], (255, 197, 61))
        self.assertTrue(all(os.path.exists(f) for f in t["fonts"].values()))
        path = os.path.join(_tmp, "theme.json")
        with open(path, "w") as f:
            json.dump({"name": "My Show", "accent": "#123", "captions": "bold"}, f)
        t = theme.load({"theme": {"accent": "#FFFFFF"}}, path=path)
        self.assertEqual((t["name"], t["accent"], t["on_accent"], t["captions"]), ("My Show", (255, 255, 255), (12, 12, 12), "bold"))

    def test_mistakes_are_caught(self):
        from clipkit import theme
        for bad in ({"acent": "#fff"}, {"accent": "pinkish"}, {"captions": "wild"}, {"fonts": {"bold": "nope.ttf"}}):
            path = os.path.join(_tmp, "bad.json")
            with open(path, "w") as f:
                json.dump(bad, f)
            self.assertRaises(SystemExit, theme.load, None, path)

    def test_every_caption_style_and_the_headline_render(self):
        from clipkit.brand import brand_hook, cap
        from clipkit.words import chunk_words
        ch = chunk_words([{"t": "hello", "s": 0.0, "e": 0.4, "sp": "1"}, {"t": "world", "s": 0.5, "e": 0.9, "sp": "1"}])[0]
        for style in ("clean", "bold"):
            self.assertTrue(cap(ch, 0.6, style=style).getbbox(), style)
        self.assertTrue(brand_hook("Two lines\nof headline", 72, name="Ana Guest").getbbox())


class Effects(unittest.TestCase):
    def test_moves_settle(self):
        from clipkit import fx
        self.assertEqual(fx.punch(5.0, [1.0]), 1.0)
        self.assertGreater(fx.punch(1.05, [1.0]), 1.0)
        self.assertEqual(fx.shake(2.0, 1.0), (0.0, 0.0))
        self.assertTrue(all(abs(v) <= 0.025 for v in fx.shake(1.01, 1.0)))  # crop() fractions, not pixels
        self.assertAlmostEqual(fx.push(10, 0, 4, 1.0, 1.3), 1.3)
        self.assertAlmostEqual(fx.slam(5, 0), 1.0, places=2)

    def test_looks_keep_the_frame(self):
        from clipkit import fx
        im = Image.new("RGBA", (1080, 1920), (200, 80, 40, 255))
        for out in (fx.mono(im), fx.deep_fry(im), fx.vignette(im.copy())):
            self.assertEqual(out.size, im.size)
        self.assertTrue(fx.meme_text("sigma rule #1").getbbox())
        self.assertTrue(fx.sticker("no way").getbbox())


class Glyphs(unittest.TestCase):
    def test_symbols_never_vanish(self):
        from clipkit.draw import text_line
        from clipkit.project import F_BLACK
        from clipkit.project import F_MONO_XB
        for fpath in (F_MONO_XB, F_BLACK):
            for ch in "✓✗₂→":
                im = text_line(ch, fpath, 60)
                self.assertGreater(im.split()[3].getextrema()[1], 0, f"{ch!r} drew nothing in {fpath}")


class Look(unittest.TestCase):
    def test_bar_is_solid_accent(self):
        b = bar(80)
        self.assertEqual(b.height, 80)
        self.assertEqual(b.getpixel((b.width // 2, 40))[:3], (255, 197, 61))

    def test_gradient_is_smooth(self):
        g = np.array(gradient(4, 512, (0, 0, 0, 0), (0, 0, 0, 255)))[:, 0, 3].astype(int)
        self.assertEqual(g[0], 0)
        self.assertEqual(g[-1], 255)
        self.assertLessEqual(np.abs(np.diff(g)).max(), 3)

    def test_tag_keeps_its_width_while_it_animates(self):
        self.assertEqual(tag("Ana Guest", 40, 0.6).size, tag("Ana Guest", 40, 1.0).size)

    def test_guest_is_not_the_host(self):
        self.assertEqual(GUEST, "Ana Guest")


class LayoutQA(unittest.TestCase):
    def setUp(self):
        state.QA = {"boxes": [], "items": [], "clips": set(), "tight": set()}

    def tearDown(self):
        state.QA = None

    def test_tight_content_on_a_card_is_flagged_but_padded_content_is_not(self):
        card = panel(400, 200)
        place(card, Image.new("RGBA", (100, 40), (255, 255, 255, 255)), 6, 80, anchor="tl")
        self.assertEqual(len(state.QA["tight"]), 1)
        state.QA["tight"].clear()
        place(card, Image.new("RGBA", (100, 40), (255, 255, 255, 255)), 40, 80, anchor="tl")
        self.assertEqual(len(state.QA["tight"]), 0)

    def test_transparent_strips_are_not_cards(self):
        strip = Image.new("RGBA", (400, 60))
        place(strip, Image.new("RGBA", (100, 40), (255, 255, 255, 255)), 0, 10, anchor="tl")
        self.assertEqual(len(state.QA["tight"]), 0)

    def test_boxes_use_visible_pixels_not_transparent_margins(self):
        canvas = Image.new("RGBA", (1080, 1920))
        im = Image.new("RGBA", (300, 300))
        im.paste((255, 0, 0, 255), (100, 100, 200, 200))
        place(canvas, im, 540, 960)
        x0, y0, x1, y1, _ = state.QA["items"][0]
        self.assertEqual((x1 - x0, y1 - y0), (100, 100))

    def test_over_marks_deliberate_layering(self):
        canvas = Image.new("RGBA", (1080, 1920))
        place(canvas, Image.new("RGBA", (50, 50), (1, 1, 1, 255)), 100, 100, over=True)
        self.assertEqual(state.QA["items"], [])


class Headline(unittest.TestCase):
    def test_tight_close_up_puts_the_headline_over_the_chest(self):
        y, s, chest = _hook_slot([(200, 200, 880, 1250)], 400)
        self.assertTrue(chest)

    def test_room_under_the_chin_puts_it_just_above_the_captions(self):
        from clipkit.brand import CAPTION_TOP
        y, s, chest = _hook_slot([(300, 300, 780, 800)], 400)
        self.assertFalse(chest)
        self.assertGreater(y, 800)
        self.assertLess(y, CAPTION_TOP)

    def test_room_above_the_head_is_used(self):
        y, s, chest = _hook_slot([(300, 700, 780, 1250)], 400)
        self.assertFalse(chest)
        self.assertLess(y, 700)


class Freeze(unittest.TestCase):
    def test_a_held_frame_or_unchanged_picture_is_flagged(self):
        from clipkit import qa
        from clipkit.project import FPS, STEP
        check = qa.start()
        fr = np.zeros((10, 10, 3), np.uint8)
        still = Image.new("RGB", (1080, 1920), (40, 40, 40))
        for n in range(int(2 * FPS / STEP)):
            t = n * STEP / FPS
            check.before_draw(t, fr)
            check.after_draw(t, (540, 960, 200), still)
        path = os.path.join(_tmp, "qa.txt")
        self.assertIn("FROZEN", check.report(path))

    def test_a_moving_picture_is_fine(self):
        from clipkit import qa
        from clipkit.project import FPS, STEP
        check = qa.start()
        for n in range(int(2 * FPS / STEP)):
            t = n * STEP / FPS
            check.before_draw(t, np.zeros((10, 10, 3), np.uint8))
            check.after_draw(t, (540, 960, 200), Image.new("RGB", (1080, 1920), (n * 7 % 255, 0, 0)))
        self.assertEqual(check.report(os.path.join(_tmp, "qa2.txt")), "OK")


class SafeZones(unittest.TestCase):
    def test_captions_and_boards_fit_between_the_rails(self):
        from clipkit.safezones import safe_width, unsafe
        w = safe_width(1300, 1500)
        self.assertTrue(700 <= w <= 900)
        x0 = (1080 - w) // 2
        self.assertEqual(unsafe((x0, 1300, x0 + w, 1500)), [])

    def test_ui_areas_are_flagged(self):
        from clipkit.safezones import unsafe
        self.assertIn("instagram", unsafe((100, 1700, 900, 1800)))       # the caption/username block
        self.assertIn("instagram", unsafe((900, 1200, 1060, 1300)))      # the like/comment rail
        self.assertIn("x", unsafe((100, 40, 900, 160)))                  # the top bar
        self.assertEqual(unsafe((100, 400, 1000, 900)), [])              # mid-frame, above the rail

    def test_only_the_thin_band_round_the_screen_is_red(self):
        from clipkit.safezones import at_edge
        self.assertTrue(at_edge((0, 600, 300, 800)))                     # touching the left edge
        self.assertTrue(at_edge((200, 1850, 900, 1910)))                 # down by the home bar
        self.assertFalse(at_edge((100, 1600, 900, 1780)))                # deep bottom: under app UI, but only orange


class Edits(unittest.TestCase):
    def test_out_t_maps_across_pieces(self):
        e = Edit([(10, 12), (20, 21.5)], focus="Ana", hold=0.5)
        self.assertAlmostEqual(e.out_t(20.5), 2.5)
        self.assertIsNone(e.out_t(15))
        self.assertAlmostEqual(e.dur, 3.5)
        self.assertEqual((e.focus, e.hold), ("Ana", 0.5))


class Encoding(unittest.TestCase):
    def tearDown(self):
        encode.pick.cache_clear()

    def _machine(self, have, broken=(), forced=""):
        """pretend this ffmpeg has the encoders `have`, of which `broken` fail their test encode"""
        real = encode.compiled, encode.works, os.environ.get("CLIP_ENCODER")
        encode.compiled = lambda: set(have)
        encode.works = lambda n: encode.CODEC[n] in have and encode.CODEC[n] not in broken
        os.environ["CLIP_ENCODER"] = forced
        encode.pick.cache_clear()

        def undo():
            encode.compiled, encode.works = real[0], real[1]
            os.environ.pop("CLIP_ENCODER") if real[2] is None else os.environ.update(CLIP_ENCODER=real[2])
        self.addCleanup(undo)

    def test_picks_the_best_working_encoder(self):
        self._machine({"libx264", "h264_nvenc"})
        self.assertEqual(encode.pick(), "nvenc")
        self._machine({"libx264", "h264_nvenc"}, broken={"h264_nvenc"})  # compiled in, but no GPU behind it
        self.assertEqual(encode.pick(), "x264")
        self._machine({"h264_mf"})  # a Windows build without libx264
        self.assertEqual(encode.pick(), "mf")
        self._machine(set())
        self.assertRaises(SystemExit, encode.pick)

    def test_forced_encoder_must_exist_and_work(self):
        self._machine({"libx264", "h264_videotoolbox"}, forced="x264")
        self.assertEqual(encode.pick(), "x264")
        self._machine({"libx264"}, forced="nvenc")
        self.assertRaises(SystemExit, encode.pick)
        self._machine({"libx264"}, forced="gpu-please")
        self.assertRaises(SystemExit, encode.pick)

    def test_preview_bitrate_fits_discord(self):
        for seconds in (8, 45, 90, 180):
            kbps = encode.rates("videotoolbox", seconds, preview=True)["peak"]
            total = (kbps + encode.AUDIO_KBPS[True]) * 1000 / 8 * seconds
            self.assertLess(total, encode.PREVIEW_MAX_BYTES * 0.95, seconds)
        self.assertEqual(encode.rates("x264", 30, preview=True)["peak"], encode.preview_budget_kbps(30))
        self.assertEqual(encode.rates("nvenc", 30, preview=False)["kbps"], encode.FINAL_KBPS)
        self.assertEqual(encode.rates("x264", 30, preview=False), {"crf": 18})

    def test_every_encoder_gets_valid_arguments(self):
        for n in encode.ORDER:
            for preview in (False, True):
                pre, tail, venc = encode.video_args(n, **encode.rates(n, 40, preview))
                self.assertEqual(venc[:2], ["-c:v", encode.CODEC[n]])
                self.assertTrue(tail.startswith("format="))
        self.assertIn("hwupload", encode.video_args("vaapi", kbps=1000)[1])
        self.assertRaises(ValueError, encode.video_args, "nvenc")  # hardware encoders need a bitrate

    def test_colours_are_converted_as_bt709(self):
        for preview in (False, True):
            cmd = encode.command("o.mp4", "a.wav", (1080, 1920), 30, 20, preview, name="x264")
            vf = cmd[cmd.index("-vf") + 1]
            self.assertIn("out_color_matrix=bt709", vf)
            self.assertEqual("540:960" in vf, preview)
            self.assertEqual(cmd[cmd.index("-colorspace") + 1], "bt709")

    def test_fit_shrinks_an_oversized_preview(self):
        import subprocess
        path = os.path.join(_tmp, "big.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=540x960:r=15:d=6", "-f", "lavfi",
                        "-i", "anoisesrc=d=6", "-vf", "noise=alls=60:allf=t", "-c:v", "mpeg4", "-q:v", "2", "-c:a", "aac",
                        "-shortest", path], check=True)
        self.assertGreater(os.path.getsize(path), 1_500_000)
        self.assertLessEqual(encode.fit(path, 6, limit=1_000_000), 1_000_000)


class Fonts(unittest.TestCase):
    def test_system_font_falls_back_in_order(self):
        here = {"menlo.ttc": "/mac/Menlo.ttc", "dejavusansmono.ttf": "/linux/DejaVuSansMono.ttf"}
        self.assertEqual(system_font("Menlo.ttc", "DejaVuSansMono.ttf", fallback="b", installed=here), "/mac/Menlo.ttc")
        self.assertEqual(system_font("consola.ttf", "DejaVuSansMono.ttf", fallback="b", installed=here),
                         "/linux/DejaVuSansMono.ttf")
        self.assertEqual(system_font("consola.ttf", fallback="bundled.ttf", installed={}), "bundled.ttf")

    def test_no_emoji_font_leaves_a_blank_not_a_crash(self):
        real = draw.F_EMOJI
        draw.F_EMOJI = None
        draw.emoji.cache_clear()
        try:
            self.assertEqual(draw.emoji("🙂", 60).size, (60, 60))
        finally:
            draw.F_EMOJI = real
            draw.emoji.cache_clear()


class Boards(unittest.TestCase):
    def test_boards_keep_their_size_while_they_build(self):
        from clipkit.boards import bar_chart, list_board, versus_board
        items = ["Permits", "Wiring", "The roof"]
        sizes = {list_board("Needs a permit", items, [k, k - 0.5, k - 1]).size for k in (0.2, 1.0, 2.0)}
        self.assertEqual(len(sizes), 1)
        sizes = {versus_board("Agent", "Human", 4, 30, k, k).size for k in (0.0, 0.5, 1.0)}
        self.assertEqual(len(sizes), 1)
        self.assertTrue(bar_chart("Cost", [("agent", 20), ("developer", 2000)], [1, 1], " $").getbbox())
        self.assertTrue(bar_chart("Places", [("jurisdictions", 20000)], [0.5]).getbbox())  # one bar: a counter

    def test_when_said_matches_accents_and_order(self):
        from clipkit.boards import when_said

        class E:
            dur = 5.0

            def words(self):
                return [{"t": "Človek,", "s": 1.0}, {"t": "agent", "s": 2.0}, {"t": "človeka", "s": 3.0}]
        self.assertEqual(when_said(E(), "človek", 0.0), 1.0)
        self.assertEqual(when_said(E(), "clovek", 1.5), 3.0)
        self.assertIsNone(when_said(E(), "robot", 0.0))

    def test_mouth_check_needs_a_clear_majority(self):
        from clipkit import angles, video

        class E:
            def src_t(self, t):
                return 100.0 + t
        slots = [{"x": 100, "y": 100, "size": 50, "speaker": "1"}, {"x": 900, "y": 100, "size": 50, "speaker": "2"}]
        real = angles._mouth_activity
        try:
            for acts, want in (([0.3, 1.4], 1), ([1.2, 1.3], None), ([None, 1.4], None)):
                video._MOUTH.clear()
                angles._mouth_activity = lambda t, s, a=acts: list(a)
                got = video._mouth_check(E(), list(range(90)), slots, slots[0])
                self.assertEqual(got, slots[want] if want is not None else None, acts)
        finally:
            angles._mouth_activity = real
            video._MOUTH.clear()


if __name__ == "__main__":
    unittest.main()
