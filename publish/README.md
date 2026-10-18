# Publishing (optional)

The clipper's job ends with videos in `projects/<episode>/export/`. This package takes them further: it uploads
them to a platform with their titles, descriptions and publish times. It's optional. Nothing else in the repo
depends on it, and each platform only needs its own keys in `.env`.

```bash
./clip publish                                  # which platforms there are
./clip publish youtube plan <episode>           # draft projects/<episode>/youtube.json from export/
./clip publish youtube check <episode>          # what's missing or wrong
./clip publish youtube upload <episode>         # upload what isn't up yet
```

Every platform works the same way: a **plan** per episode (`projects/<episode>/<platform>.json`, one entry per
clip) that you draft, edit, check and then upload. Uploads write each post's id back into the plan right away, so a
rerun only does what's left and nothing gets posted twice. Uploads publish, so the agent shows you the plan and
waits for a yes first.

## Platforms

| Platform | Status | What the API allows (October 2026) |
|---|---|---|
| **YouTube Shorts** | ✓ [`youtube.py`](youtube.py), setup in [youtube.md](youtube.md) | Upload with title, description and a scheduled publish time. Upload-only by design. The Short's cover and related video are set in Studio, not through the API. |
| **TikTok** | possible | The Content Posting API can post directly or upload to the creator's inbox as a draft. Until TikTok audits the app, direct posts are private only, so the practical start is drafts that you publish in the TikTok app. |
| **LinkedIn** | possible | Video posts go through the Videos API, then the Posts API. Posting to your own profile is self-serve (`w_member_social`). Posting to a company Page (`w_organization_social`) needs LinkedIn's Community Management API approval and a Page admin role. Tokens last about 60 days. |
| **X** | possible, paid | Chunked video upload, then a post. API access is pay-per-use: about $0.015 a post, more with a link in it. |
| **Instagram Reels** | possible, with a catch | The Graph API publishes Reels for business or creator accounts. It needs Meta's app review for anyone outside the app's own roles. Reels must be 9:16 and 5-90 s. |

## Adding a platform

A platform is one module here plus a line in `PLATFORMS` in [`__init__.py`](__init__.py). It needs:

- `ITEMS`: the plan's list key (`"shorts"` for YouTube).
- `login()`: one-time sign-in. Keys go in `.env` (the user fills them in), the token in `~/.config/…` on this
  machine, never in the repo.
- `draft_plan(pid)`: a first plan. `exported(pid)` gives you every exported clip with its title and description.
- `problems(pid, item)`: what's wrong with one entry (an empty list means ready). Check everything the platform
  would reject before uploading: length, aspect ratio, text limits, publish time.
- `status(item)`: one line for `check` (uploaded, scheduled, draft…).
- `upload(pid, only=None)`: upload the entries that aren't up yet. Write the id back with `write_plan` right after
  each one.

Keep the same safety rules as `youtube.py`. Ask for the narrowest scope the platform offers, refuse a token with
more, and let no call through except the few you need (`_allowed` in `youtube.py`). Standard library only.
