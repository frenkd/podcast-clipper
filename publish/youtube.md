# YouTube upload: one-time setup

`./clip publish youtube` (or `./clip yt` for short) uploads Shorts with title, description and publish time. It can't delete or edit anything:
the sign-in asks Google for the `youtube.upload` scope only, and Google refuses `videos.delete` and `videos.update`
with that scope. The code also blocks every call except upload and thumbnail, and refuses a token with any other
scope.

Two things the API can't do, so they stay in Studio after each upload (it prints the links): the Short's **cover**
and its **related video**.

## 1. Google Cloud project

1. Open https://console.cloud.google.com, sign in with your own Google account, create a project (e.g.
   `podcast-uploader`).
2. **APIs & Services → Library**, search **YouTube Data API v3**, **Enable**.

## 2. Consent screen (Google Auth Platform)

1. **Google Auth Platform → Branding**: app name `Podcast uploader`, your email as support and developer contact.
2. **Audience**: *External*. Then **Publish app** so the status is **In production**. In *Testing* the sign-in
   expires every 7 days. You don't need Google's verification for your own use; you'll just see an "unverified app"
   warning when you sign in.
3. **Data access → Add or remove scopes**: add only `https://www.googleapis.com/auth/youtube.upload`. Nothing else.

## 3. OAuth client

1. **Google Auth Platform → Clients → Create client**, type **Desktop app**, name it `clipper`.
2. Copy the client ID and secret into `.env` yourself (never into a chat):
   ```
   YOUTUBE_CLIENT_ID=…apps.googleusercontent.com
   YOUTUBE_CLIENT_SECRET=…
   ```

## 4. Sign in

```bash
./clip publish youtube login
```

The browser opens. Pick **your show's** channel in the account picker (not your personal one). On the unverified
warning: **Advanced → Go to Podcast uploader**. Google labels the permission "Manage your YouTube videos", but with
this scope it only allows uploading and setting thumbnails. The terminal confirms "signed in, upload-only". The token is
saved in `~/.config/podcast-clipper/youtube-token.json` (only you can read it, outside the repo).

If the channel isn't in the picker, your account has channel permissions in Studio but isn't an owner or
manager of the **Brand Account** behind the channel; ask the owner to add you at
https://myaccount.google.com/brandaccounts.

To cut access at any time: https://myaccount.google.com/permissions → Podcast uploader → remove, and delete the token
file.

## 5. Use it

```bash
./clip publish youtube plan my-ep    # drafts projects/<episode>/youtube.json from export/
./clip publish youtube check my-ep   # titles, files, vertical, ≤3 min, publish times
./clip publish youtube upload my-ep  # uploads the ones without a videoId yet
```

In `youtube.json`, each Short has `title` (max 100 characters), `description`, `tags` and `publishAt`
with a time zone, e.g. `"2026-10-20T17:00:00+02:00"`. With a `publishAt` it uploads as private and goes public at
that time; without one it stays private. Once uploaded, the entry gets its `videoId`. To change anything after
that (title, time), use YouTube Studio: the uploader can't.

## Good to know

- **Quota:** 100 uploads a day per Cloud project.
- **Cover:** `thumbnails.set` accepts an image for a Short and reports success, but YouTube doesn't show it as the
  Short's cover (tried October 2026). Pick the cover in Studio. `thumbnail` in `youtube.json` still works if you
  want to send one anyway; the draft leaves it out.
- **Related video:** not in the API at all. In Studio: the Short → Related video → the full episode. It needs
  advanced features on the channel, and the episode has to be public or unlisted.
- **It becomes a Short** by itself: vertical and up to 3 minutes. There's no API flag for it.
