import json
import os
import tempfile
import threading
import time
import unittest

os.environ.setdefault("CLIPPER_DATA_DIR", tempfile.mkdtemp(prefix="clip-test-"))

from prep.fixes import fix_text, fix_words, parse_fix  # noqa: E402
from prep.media import Budget  # noqa: E402
from prep.soniox import tokens_to_words  # noqa: E402
from prep.stt import stitch, words_to_cues  # noqa: E402
from prep.store import create_project, find_project, project_dir, slugify, update_project  # noqa: E402
from prep.subtitles import parse_subtitles, to_srt  # noqa: E402


def w(t, s, e, sp=None):
    return {"t": t, "s": s, "e": e, **({"sp": sp} if sp else {})}


class Transcripts(unittest.TestCase):
    def test_tokens_merge_into_words_and_punctuation_sticks(self):
        words = tokens_to_words([{"text": "Lepo", "start_ms": 0, "end_ms": 200, "speaker": "1"},
                                 {"text": " poz", "start_ms": 250, "end_ms": 400, "speaker": "1"},
                                 {"text": "dravljeni", "start_ms": 400, "end_ms": 700, "speaker": "1"},
                                 {"text": ".", "start_ms": 700, "end_ms": 710, "speaker": "1"}])
        self.assertEqual([x["t"] for x in words], ["Lepo", "pozdravljeni."])
        self.assertEqual(words[1]["e"], 710)

    def test_stitch_cuts_at_a_shared_pause_and_remaps_speakers(self):
        a = [w("ena", 8000, 8400, "1"), w("dva", 9000, 9400, "1"), w("tri", 13000, 13400, "2"),
             w("štiri", 15500, 15900, "2"), w("pet", 18000, 18400, "1")]
        b = [w("tri", 13000, 13400, "1"), w("štiri", 15500, 15900, "1"), w("pet", 18000, 18400, "2"),
             w("šest", 22000, 22400, "2")]
        out = stitch([a, b], [0, 10000], 10000)
        self.assertEqual([x["t"] for x in out], ["ena", "dva", "tri", "štiri", "pet", "šest"])
        self.assertEqual(next(x for x in out if x["t"] == "šest")["sp"], "1")

    def test_cues_split_on_speaker_change(self):
        self.assertEqual(len(words_to_cues([w("Ja.", 0, 300, "1"), w("Točno", 400, 700, "2"), w("tako.", 700, 1000, "2")])), 2)

    def test_srt_parsing_drops_exact_duplicates(self):
        srt = ("1\n00:00:00,000 --> 00:00:02,000\nprvi\n\n2\n00:00:00,000 --> 00:00:02,000\nprvi popravljen\n\n"
               "3\n00:00:03,000 --> 00:00:04,500\ndrugi\n")
        self.assertEqual([c["text"] for c in parse_subtitles(srt)], ["prvi popravljen", "drugi"])

    def test_srt_output_splits_long_cues_and_keeps_short_ones_readable(self):
        srt = to_srt([{"i": 0, "s": 1000, "e": 1200, "text": "OK."}, {"i": 1, "s": 1600, "e": 3000, "text": "Naprej."}])
        self.assertIn("00:00:01,000 --> 00:00:01,560", srt)
        long = to_srt([{"i": 0, "s": 0, "e": 9000, "text": " ".join(["beseda"] * 30)}])
        self.assertTrue(all(len(l) <= 84 for l in long.splitlines()))


class Glued(unittest.TestCase):
    def test_missing_spaces_after_punctuation_are_split(self):
        from prep.soniox import split_glued
        ws = [{"t": t, "s": 0, "e": 1000} for t in ("resources,right?", 'like"tiny', "1,5", "U.S.", "Hello.")]
        self.assertEqual([w["t"] for w in split_glued(ws)], ["resources,", "right?", "like", '"tiny', "1,5", "U.S.", "Hello."])


class Fixes(unittest.TestCase):
    def test_fixes_keep_punctuation_capitals_and_time_span(self):
        words = [w("pač", 0, 200), w("si", 200, 300), w("malo", 300, 500), w("smolil.", 500, 900), w("Čakrš", 1000, 1400)]
        out = fix_words(words, [{"from": "malo smolil", "to": "mel smolo"}, {"from": "čakrš", "to": "Čakarmiš"}])
        self.assertEqual([x["t"] for x in out], ["pač", "si", "mel", "smolo.", "Čakarmiš"])
        self.assertEqual(out[2]["s"], 300)
        self.assertEqual(out[3]["e"], 900)
        self.assertEqual(fix_text("Malo smolil je, rekel Čakrš.", [{"from": "malo smolil", "to": "mel smolo"},
                                                                 {"from": "Čakrš", "to": "Čakarmiš"}]),
                         "Mel smolo je, rekel Čakarmiš.")

    def test_fix_quotes_and_hyphens(self):
        self.assertEqual(parse_fix('pomeni"iterative => pomeni »iterative'), {"from": 'pomeni"iterative', "to": "pomeni »iterative"})
        out = fix_words([w("Miki-ju", 0, 100)], [{"from": "Miki-ju", "to": "Michieju"}])
        self.assertEqual(out[0]["t"], "Michieju")


class CleanupGuard(unittest.TestCase):
    def test_translations_are_rejected_and_corrections_kept(self):
        from prep.steps import faithful
        self.assertFalse(faithful("the workshop on vector embeddings was really nice.",
                                  "da je bila delavnica o vektorskih vdelavah res odlična."))
        self.assertTrue(faithful("in sem mikiju seveda spet pokazal poskuse v medicinskih domenah",
                                 "in sem Michieju seveda spet pokazal poskuse v medicinskih domenah (področjih)."))
        self.assertTrue(faithful("Ja.", "Ja, ja."))


class Store(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify("Jürgen Vöß and the database - My Podcast (1080p, h264).mp4"), "jurgen-voss")

    def test_concurrent_updates_never_lose_writes(self):
        p = create_project("Test episode", "test concurrent")

        def bump():
            for _ in range(10):
                update_project(p["id"], lambda q: q.__setitem__("n", q.get("n", 0) + 1))
        ts = [threading.Thread(target=bump) for _ in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(find_project("test-concurrent")["n"], 40)


class CpuBudget(unittest.TestCase):
    def test_budget_never_exceeds_its_total(self):
        b, now, peak, lock = Budget(8), [0], [0], threading.Lock()

        def job(n):
            with b.take(n):
                with lock:
                    now[0] += n
                    peak[0] = max(peak[0], now[0])
                time.sleep(0.01)
                with lock:
                    now[0] -= n
        ts = [threading.Thread(target=job, args=(n,)) for n in (4, 4, 2, 1, 1, 4, 2, 8, 1)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertLessEqual(peak[0], 8)
        self.assertEqual(now[0], 0)


class SpeechToText(unittest.TestCase):
    def test_provider_prefers_soniox_then_openai(self):
        from prep import stt
        keep = {k: os.environ.get(k) for k in ("STT", "SONIOX_API_KEY", "ELEVENLABS_API_KEY", "OPENAI_API_KEY")}
        try:
            for env, want in (({"SONIOX_API_KEY": "x", "OPENAI_API_KEY": "y"}, "soniox"), ({"OPENAI_API_KEY": "y"}, "openai"),
                              ({"ELEVENLABS_API_KEY": "z", "SONIOX_API_KEY": "x"}, "elevenlabs"),
                              ({"SONIOX_API_KEY": "x", "OPENAI_API_KEY": "y", "STT": "openai"}, "openai")):
                for k in keep:
                    os.environ.pop(k, None)
                os.environ.update(env)
                self.assertEqual(stt.provider(), want, env)
            for k in keep:
                os.environ.pop(k, None)
            self.assertRaises(SystemExit, stt.provider)
            os.environ.update(STT="elevenlabs", OPENAI_API_KEY="y")  # named, but its key is missing
            self.assertRaises(SystemExit, stt.provider)
        finally:
            for k, v in keep.items():
                os.environ.pop(k, None) if v is None else os.environ.update({k: v})

    def test_whisper_words_get_their_punctuation_back(self):
        from prep.openai_stt import punctuate
        words = [{"t": t, "s": i * 300, "e": i * 300 + 250} for i, t in enumerate("so is it Python or bash".split())]
        out = punctuate(words, [{"text": " So, is it Python"}, {"text": " or... bash?"}])
        self.assertEqual([w["t"] for w in out], ["So,", "is", "it", "Python", "or...", "bash?"])
        self.assertEqual(punctuate(words[:1], [{"text": "different"}])[0]["t"], "so")  # no match: the word stays

    def test_words_get_the_speaker_of_their_turn(self):
        from prep.openai_stt import assign
        turns = [{"s": 0, "e": 1000, "sp": "1"}, {"s": 1000, "e": 2500, "sp": "2"}, {"s": 3000, "e": 4000, "sp": "1"}]
        words = [{"t": "a", "s": 100, "e": 400}, {"t": "b", "s": 900, "e": 1400}, {"t": "c", "s": 2600, "e": 2800},
                 {"t": "d", "s": 3100, "e": 3300}]
        self.assertEqual([w["sp"] for w in assign(words, turns)], ["1", "2", "2", "1"])


    def test_elevenlabs_words(self):
        from prep.elevenlabs_stt import keyterms, to_words
        r = {"words": [{"text": "Hello,", "type": "word", "start": 0.1, "end": 0.4, "speaker_id": "speaker_0"},
                       {"text": " ", "type": "spacing", "start": 0.4, "end": 0.45, "speaker_id": "speaker_0"},
                       {"text": "(laughs)", "type": "audio_event", "start": 0.5, "end": 0.9, "speaker_id": "speaker_1"},
                       {"text": "hi!", "type": "word", "start": 1.0, "end": 1.2, "speaker_id": "speaker_1"}]}
        self.assertEqual(to_words(r, 1000), [{"t": "Hello,", "s": 1100, "e": 1400, "sp": "1"},
                                             {"t": "hi!", "s": 2000, "e": 2200, "sp": "2"}])
        self.assertEqual(keyterms(["PostgreSQL", "x" * 60, "a b c d e f", "[bad]", "PostgreSQL", " Hugging Face "]),
                         ["PostgreSQL", "Hugging Face"])



class FirstRun(unittest.TestCase):
    def test_api_errors_say_what_to_do(self):
        from prep.config import ServiceError, api_error
        e = api_error("OpenAI", "OPENAI_API_KEY", 401, '{"error": {"code": "invalid_api_key"}}')
        self.assertIsInstance(e, ServiceError)
        self.assertIn("check OPENAI_API_KEY in .env", str(e))
        self.assertIn("out of credit", str(api_error("OpenAI", "K", 429, '{"code": "insufficient_quota"}')))
        self.assertIn("rate-limiting", str(api_error("ElevenLabs", "K", 429, "slow down")))
        self.assertIn("server error", str(api_error("Soniox", "K", 503, "")))

    def test_files_are_refused_with_a_reason(self):
        from prep.files import kind_for
        self.assertEqual((kind_for("ep.MP4"), kind_for("ep.srt"), kind_for("notes.md")), ("video", "subtitles", "context"))
        with self.assertRaises(SystemExit) as e:
            kind_for("episode.mp3")
        self.assertIn("audio only", str(e.exception))
        self.assertRaises(SystemExit, kind_for, "slides.pptx")

    def test_typos_list_the_episodes(self):
        create_project("Typo test")
        with self.assertRaises(SystemExit) as e:
            find_project("no-such-episode-xyz")
        self.assertIn("there are:", str(e.exception))

    def test_languages_from_the_services(self):
        from prep.stt import detected_language
        self.assertEqual([detected_language(x) for x in ("slv", "Slovenian", "en", "", "klingon")],
                         ["sl", "sl", "en", None, None])

    def test_gallery_lists_the_previews_with_qa(self):
        from prep import gallery
        pid = create_project("Gallery test")["id"]
        d = os.path.join(project_dir(pid), "preview")
        os.makedirs(d)
        for name, qa in (("01_a", "OK"), ("02_b", "COVERS FACE  02_b.py:3 (draw): 1.0-2.0s")):
            with open(os.path.join(d, name + ".mp4"), "wb") as f:
                f.write(b"x" * 1000)
            with open(os.path.join(d, name + ".qa.txt"), "w") as f:
                f.write(qa + "\n")
        page = gallery.write(pid)[0]
        with open(page, encoding="utf-8") as f:
            text = f.read()
        self.assertIn('src="01_a.mp4"', text)
        self.assertIn("COVERS FACE", text)


if __name__ == "__main__":
    unittest.main()
