"""Shorts to YouTube, upload-only: upload a clip with title, description and a scheduled time.

The Shorts cover and the related video aren't in the API: set them in Studio after the upload (the upload prints the
link). `thumbnail` in the plan is optional; YouTube accepts it but, as of October 2026, doesn't use it as a Short's
cover, so the draft leaves it out.

The token only ever holds the `youtube.upload` scope, which Google allows for videos.insert and thumbnails.set but
not for videos.delete or videos.update. So nothing here can delete or change a video once it's up (fix those in
Studio). On top of that, every request goes through `_request`, which only lets through those two calls.

The plan is `projects/<id>/youtube.json`, one entry per Short (see publish/__init__.py for the plan/check/upload
flow)."""
import base64
import datetime
import hashlib
import http.server
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from prep.config import require_key
from prep.store import get_project, project_dir

from . import exported, probe as _probe, read_plan as _read, when as _when, write_plan as _write

SCOPE = "https://www.googleapis.com/auth/youtube.upload"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
VIDEOS_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
THUMBS_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
TOKEN_PATH = os.path.expanduser(os.environ.get("YOUTUBE_TOKEN", "~/.config/podcast-clipper/youtube-token.json"))
CATEGORY = "28"  # Science & Technology
ITEMS = "shorts"


# guard: the only calls this module makes

def _allowed(method, url):
    u = urllib.parse.urlsplit(url)
    base = f"{u.scheme}://{u.netloc}{u.path}"
    q = urllib.parse.parse_qs(u.query)
    if method == "POST" and base == TOKEN_URL:
        return True
    if method == "POST" and base == VIDEOS_URL and q.get("uploadType") == ["resumable"]:
        return True  # starts an upload session (videos.insert)
    if method == "PUT" and base == VIDEOS_URL and q.get("uploadType") == ["resumable"] and "upload_id" in q:
        return True  # sends the file into that session
    if method == "POST" and base == THUMBS_URL and q.get("videoId"):
        return True  # thumbnails.set
    return False


def _request(method, url, data=None, headers=None, timeout=120):
    if not _allowed(method, url):
        raise PermissionError(f"blocked: {method} {url.split('?')[0]} (the uploader only uploads)")
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    return urllib.request.urlopen(req, timeout=timeout)


def _error(e):
    body = e.read().decode(errors="replace")
    try:
        err = json.loads(body).get("error")
        msg = err.get("message") if isinstance(err, dict) else f"{err}: {json.loads(body).get('error_description', '')}"
    except (ValueError, AttributeError):
        msg = body[:300]
    return RuntimeError(f"YouTube {e.code}: {msg}")


# sign-in (OAuth for desktop apps: loopback redirect + PKCE)

def _client():
    return require_key("YOUTUBE_CLIENT_ID"), require_key("YOUTUBE_CLIENT_SECRET")


def _check_scope(granted):
    if set((granted or "").split()) != {SCOPE}:
        raise SystemExit(f"Google granted more or less than upload-only ({granted or 'nothing'}); not saving it. "
                         "Revoke it at https://myaccount.google.com/permissions and log in again.")


def login():
    cid, secret = _client()
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(16)
    got = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            got.update({k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Done, you can close this tab.".encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    redirect = f"http://127.0.0.1:{srv.server_port}"
    # no include_granted_scopes: the token must not pick up anything granted to this client before
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE, "state": state,
        "access_type": "offline", "prompt": "select_account consent",
        "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode(),
        "code_challenge_method": "S256"})
    print("Sign in in the browser and pick your show's channel. If it didn't open:\n" + url)
    webbrowser.open(url)
    while "code" not in got and "error" not in got:
        srv.handle_request()
    srv.server_close()
    if got.get("error") or got.get("state") != state:
        raise SystemExit(f"sign-in failed: {got.get('error') or 'state mismatch'}")
    tok = _token_call({"code": got["code"], "client_id": cid, "client_secret": secret, "redirect_uri": redirect,
                       "grant_type": "authorization_code", "code_verifier": verifier})
    _check_scope(tok.get("scope"))
    if not tok.get("refresh_token"):
        raise SystemExit("Google sent no refresh token; revoke the app at https://myaccount.google.com/permissions "
                         "and log in again")
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    fd = os.open(TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"refresh_token": tok["refresh_token"], "scope": tok["scope"]}, f)
    print(f"signed in, upload-only. Token in {TOKEN_PATH}")


def _token_call(fields):
    try:
        return json.load(_request("POST", TOKEN_URL, urllib.parse.urlencode(fields).encode(),
                                  {"Content-Type": "application/x-www-form-urlencoded"}))
    except urllib.error.HTTPError as e:
        raise _error(e) from None


def access_token():
    if not os.path.exists(TOKEN_PATH):
        raise SystemExit("not signed in: run `./clip publish youtube login`")
    with open(TOKEN_PATH) as f:
        saved = json.load(f)
    cid, secret = _client()
    tok = _token_call({"refresh_token": saved["refresh_token"], "client_id": cid, "client_secret": secret,
                       "grant_type": "refresh_token"})
    _check_scope(tok.get("scope"))
    return tok["access_token"]


# the plan: projects/<id>/youtube.json

def plan_path(pid):
    from . import plan_path as _path
    return _path(pid, "youtube")


def read_plan(pid):
    return _read(pid, "youtube")


def write_plan(pid, plan):
    _write(pid, "youtube", plan)


def draft_plan(pid):
    """a youtube.json draft from export/: one Short per clip folder, no publish time yet"""
    return {"shorts": [{"video": v, "title": t, "description": d, "tags": [], "publishAt": None}
                       for v, t, d in exported(pid)]}


def status(s):
    return f"uploaded {s['videoId']}" if s.get("videoId") else s.get("publishAt") or "private, no publish time"


def problems(pid, s, probe=_probe, now=None):
    """-> what's wrong with one Short in the plan (empty list = ready; an uploaded one is done)"""
    if s.get("videoId"):
        return []
    root, out = project_dir(pid), []
    title, desc = s.get("title") or "", s.get("description") or ""
    if not title.strip():
        out.append("no title")
    if len(title) > 100:
        out.append(f"title is {len(title)} characters (max 100)")
    if re.search(r"[<>]", title + desc):
        out.append("< or > in title or description (YouTube rejects them)")
    if len(desc.encode()) > 5000:
        out.append("description over 5000 bytes")
    if sum(len(t) + 2 for t in s.get("tags") or []) > 500:
        out.append("tags over 500 characters")
    video = os.path.join(root, s.get("video") or "")
    if not s.get("video") or not os.path.isfile(video):
        out.append(f"video not found: {s.get('video')}")
    else:
        w, h, dur = probe(video)
        if h <= w:
            out.append(f"not vertical ({w}x{h}), so it won't be a Short")
        if dur > 180:
            out.append(f"{dur:.0f} s long (Shorts are up to 3 min)")
    if s.get("thumbnail"):
        t = os.path.join(root, s["thumbnail"])
        if not os.path.isfile(t):
            out.append(f"thumbnail not found: {s['thumbnail']}")
        elif os.path.getsize(t) > 50 * 1024 * 1024:
            out.append("thumbnail over 50 MB")
        elif os.path.splitext(t)[1].lower() not in (".jpg", ".jpeg", ".png"):
            out.append("thumbnail must be .jpg or .png")
    if s.get("publishAt"):
        try:
            if _when(s["publishAt"]) <= (now or datetime.datetime.now(datetime.timezone.utc)):
                out.append(f"publishAt {s['publishAt']} is in the past")
        except ValueError as e:
            out.append(str(e))
    privacy = s.get("privacy", "private")
    if privacy not in ("private", "unlisted", "public"):
        out.append(f"privacy {privacy}?")
    if s.get("publishAt") and privacy != "private":
        out.append("a scheduled Short has to be private until publishAt (drop privacy)")
    return out


def video_body(s, lang="en"):
    snippet = {"title": s["title"], "description": s.get("description") or "", "categoryId": CATEGORY,
               "defaultLanguage": lang, "defaultAudioLanguage": lang}
    if s.get("tags"):
        snippet["tags"] = s["tags"]
    status = {"privacyStatus": s.get("privacy", "private"), "selfDeclaredMadeForKids": False}
    if s.get("publishAt"):
        status["publishAt"] = _when(s["publishAt"]).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"snippet": snippet, "status": status}


# upload

def _insert(token, path, body):
    size = os.path.getsize(path)
    try:
        r = _request("POST", VIDEOS_URL + "?uploadType=resumable&part=snippet,status", json.dumps(body).encode(),
                     {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
                      "X-Upload-Content-Length": str(size), "X-Upload-Content-Type": "video/mp4"})
    except urllib.error.HTTPError as e:
        raise _error(e) from None
    session = r.headers["Location"]
    sent = 0
    for attempt in range(5):
        try:
            with open(path, "rb") as f:
                f.seek(sent)
                hdr = {"Authorization": f"Bearer {token}", "Content-Length": str(size - sent),
                       "Content-Type": "video/mp4"}
                if sent:
                    hdr["Content-Range"] = f"bytes {sent}-{size - 1}/{size}"
                return json.load(_request("PUT", session, f.read(), hdr, timeout=900))
        except urllib.error.HTTPError as e:
            if e.code not in (500, 502, 503, 504):
                raise _error(e) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(2 ** attempt)
        sent = _uploaded(token, session, size)
    raise RuntimeError(f"upload of {os.path.basename(path)} kept failing")


def _uploaded(token, session, size):
    """bytes YouTube already has for a broken upload session"""
    try:
        _request("PUT", session, b"", {"Authorization": f"Bearer {token}", "Content-Range": f"bytes */{size}"})
    except urllib.error.HTTPError as e:
        if e.code == 308:
            m = re.match(r"bytes=0-(\d+)", e.headers.get("Range") or "")
            return int(m.group(1)) + 1 if m else 0
        raise _error(e) from None
    return 0


def _thumbnail(token, video_id, path):
    kind = "image/png" if path.lower().endswith(".png") else "image/jpeg"
    with open(path, "rb") as f:
        data = f.read()
    try:
        _request("POST", THUMBS_URL + "?" + urllib.parse.urlencode({"videoId": video_id, "uploadType": "media"}),
                 data, {"Authorization": f"Bearer {token}", "Content-Type": kind})
    except urllib.error.HTTPError as e:
        raise _error(e) from None


def upload(pid, only=None, log=print):
    """upload the Shorts in the plan that have no videoId yet (only: 1-based numbers), then their thumbnails"""
    plan = read_plan(pid)
    root, todo = project_dir(pid), []
    for i, s in enumerate(plan["shorts"], 1):
        if only and i not in only:
            continue
        if s.get("videoId") and (s.get("thumbnailSet") or not s.get("thumbnail")):
            continue
        bad = problems(pid, s)
        if bad:
            raise SystemExit(f"Short {i} ({s.get('title') or s.get('video')}): " + "; ".join(bad))
        todo.append((i, s))
    if not todo:
        log("nothing to upload")
        return plan
    token = access_token()
    for i, s in todo:
        if not s.get("videoId"):
            log(f"{i}. uploading {s['video']} …")
            v = _insert(token, os.path.join(root, s["video"]), video_body(s, get_project(pid).get("language") or "en"))
            s["videoId"] = v["id"]
            s["channel"] = v["snippet"].get("channelTitle")
            write_plan(pid, plan)  # written before anything else can fail, so a rerun never uploads it twice
            when = s.get("publishAt") or v["status"]["privacyStatus"]
            log(f"   https://youtube.com/shorts/{v['id']}  on {s['channel']}, {when}")
            log(f"   in Studio, set the cover and the related video: https://studio.youtube.com/video/{v['id']}/edit")
        if s.get("thumbnail") and not s.get("thumbnailSet"):
            try:
                _thumbnail(token, s["videoId"], os.path.join(root, s["thumbnail"]))
                s["thumbnailSet"] = True
                write_plan(pid, plan)
                log("   thumbnail uploaded (YouTube doesn't use it as the Shorts cover: set that in Studio)")
            except RuntimeError as e:
                log(f"   thumbnail not uploaded: {e}")
    return plan
