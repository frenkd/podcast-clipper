import datetime
import json
import os
import tempfile
import unittest

os.environ.setdefault("CLIPPER_DATA_DIR", tempfile.mkdtemp(prefix="clip-test-"))

from publish import youtube as yt  # noqa: E402
from prep.store import create_project, project_dir  # noqa: E402

OPIS = """# Databases vs. spreadsheets

Jane Doe on why her team moved off spreadsheets.

#databases #podcast
Full episode: https://example.com/ep/1
"""
NOW = datetime.datetime(2026, 10, 15, 12, tzinfo=datetime.timezone.utc)


class UploadOnly(unittest.TestCase):
    def test_only_upload_and_thumbnail_calls_get_through(self):
        ok = [("POST", yt.VIDEOS_URL + "?uploadType=resumable&part=snippet,status"),
              ("PUT", yt.VIDEOS_URL + "?uploadType=resumable&part=snippet,status&upload_id=abc"),
              ("POST", yt.THUMBS_URL + "?videoId=abc&uploadType=media"),
              ("POST", yt.TOKEN_URL)]
        blocked = [("DELETE", "https://www.googleapis.com/youtube/v3/videos?id=abc"),
                   ("PUT", "https://www.googleapis.com/youtube/v3/videos?part=snippet"),
                   ("POST", "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet"),
                   ("DELETE", yt.VIDEOS_URL + "?uploadType=resumable&upload_id=abc"),
                   ("POST", "https://oauth2.googleapis.com/revoke")]
        for m, u in ok:
            self.assertTrue(yt._allowed(m, u), (m, u))
        for m, u in blocked:
            self.assertFalse(yt._allowed(m, u), (m, u))
        with self.assertRaises(PermissionError):
            yt._request("DELETE", "https://www.googleapis.com/youtube/v3/videos?id=abc")

    def test_a_token_with_any_other_scope_is_refused(self):
        yt._check_scope(yt.SCOPE)
        for granted in ("", "https://www.googleapis.com/auth/youtube",
                        yt.SCOPE + " https://www.googleapis.com/auth/youtube.force-ssl"):
            with self.assertRaises(SystemExit):
                yt._check_scope(granted)


class Plan(unittest.TestCase):
    def setUp(self):
        self.pid = create_project("YouTube test")["id"]
        d = os.path.join(project_dir(self.pid), "export", "1_databases")
        os.makedirs(d)
        for name, data in (("1_databases.mp4", b"x"), ("thumbnail-1-frame.jpg", b"x"), ("description.md", OPIS.encode())):
            with open(os.path.join(d, name), "wb") as f:
                f.write(data)

    def test_draft_takes_title_variant_one_and_the_episode_link(self):
        s = yt.draft_plan(self.pid)["shorts"][0]
        self.assertEqual(s["title"], "Databases vs. spreadsheets")
        self.assertEqual(s["description"], "Jane Doe on why her team moved off spreadsheets.\n\n#databases #podcast\n"
                                           "Full episode: https://example.com/ep/1")
        self.assertEqual(s["video"], "export/1_databases/1_databases.mp4")
        self.assertNotIn("thumbnail", s)  # YouTube doesn't use it as a Shorts cover
        self.assertIsNone(s["publishAt"])

    def test_problems(self):
        s = yt.draft_plan(self.pid)["shorts"][0]
        vertical = lambda p: (1080, 1920, 45.0)
        self.assertEqual(yt.problems(self.pid, {**s, "publishAt": "2026-10-20T17:00:00+02:00"}, vertical, NOW), [])
        self.assertIn("not vertical", " ".join(yt.problems(self.pid, s, lambda p: (1920, 1080, 45.0), NOW)))
        self.assertIn("3 min", " ".join(yt.problems(self.pid, s, lambda p: (1080, 1920, 200.0), NOW)))
        self.assertIn("past", " ".join(yt.problems(self.pid, {**s, "publishAt": "2026-10-01T17:00:00+02:00"},
                                                   vertical, NOW)))
        self.assertIn("time zone", " ".join(yt.problems(self.pid, {**s, "publishAt": "2026-10-20T17:00:00"},
                                                        vertical, NOW)))
        self.assertIn("private", " ".join(yt.problems(
            self.pid, {**s, "publishAt": "2026-10-20T17:00:00+02:00", "privacy": "public"}, vertical, NOW)))
        self.assertIn("title", " ".join(yt.problems(self.pid, {**s, "title": "x" * 101}, vertical, NOW)))

    def test_body_is_private_and_scheduled_in_utc(self):
        b = yt.video_body({"title": "T", "description": "D", "publishAt": "2026-10-20T17:00:00+02:00"})
        self.assertEqual(b["status"], {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                                       "publishAt": "2026-10-20T15:00:00Z"})
        self.assertEqual(b["snippet"]["defaultAudioLanguage"], "en")
        self.assertEqual(yt.video_body({"title": "T"})["status"]["privacyStatus"], "private")

    def test_uploaded_shorts_are_skipped(self):
        plan = yt.draft_plan(self.pid)
        plan["shorts"][0].update(videoId="abc")
        yt.write_plan(self.pid, plan)
        with open(yt.plan_path(self.pid), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["shorts"][0]["videoId"], "abc")
        yt.upload(self.pid, log=lambda *a: None)  # nothing to do, so no sign-in needed


if __name__ == "__main__":
    unittest.main()
