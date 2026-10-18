# Agent instructions

This repo turns podcast episodes into short vertical clips (TikTok, Reels, Shorts), plus a few episode extras. People
open it with a coding agent and ask. Many of them are new to this; be friendly, do the work, explain in plain words.
Your jobs:

- **"What can you do?"**: answer in a few plain lines (below), then offer to start.
- **"First-time setup"**: get the machine ready (below).
- **"Make clips from <video>"** (or anything like it): follow [PLAYBOOK.md](PLAYBOOK.md). Read it fully first.
- **"Make it look like my show"**: write `theme.json` with them (PLAYBOOK §7, `clips/clipkit/theme.py`).

Be quick: previews while iterating, clips rendered in parallel (`./clip render` does both), nothing redone that hasn't
changed. Be brief with the user: what you made, what you fixed, one question (PLAYBOOK §1).

## A first session

Most people meet this repo with no setup, one video and a vague wish. Keep them moving:
- **Episode names:** `./clip new` makes a folder like `2026-10-ep12` (month + the slug); every command takes any
  unique part of it (`ep12`).
- **Asked for clips before setup?** Say so in a line and do the setup first (below), then carry on with their ask.
  `.venv/` missing or no transcription key in `.env` means setup isn't done.
- **Keys:** any one is enough to start. `OPENAI_API_KEY` (https://platform.openai.com/api-keys) does everything;
  `ELEVENLABS_API_KEY` transcribes best (it keeps speakers apart most reliably, and that decides who's on screen);
  both together are the best setup. Accounts need a payment method; everything is billed per use (point them at
  the provider's pricing page rather than quoting numbers). With no OpenAI key, `./clip go` skips reading the
  notes and the cleanup (it says so): read the episode with `./clip transcript <id>` and write the headlines and
  texts yourself (`--headline`, `--sticker` …).
- **Say how long things take** before they start: transcription is a few minutes per hour of audio, the first
  render of an episode analyses its cameras once (a few minutes), each preview takes about as long as the clip.
- **Names on screen:** the name line shows who's talking. Without `CLIPPER_HOST` or names in the brief, the
  host is labelled "host" and guests have no names: after `./clip go`, read the first minutes of
  `./clip transcript <id>`, and if people introduce themselves, fill `"speakers"` in `project.json` (speaker id ->
  name, e.g. `{"1": "Ana", "2": "Marko"}`), then confirm with the user.
- **No times in mind?** Don't ask for timestamps: read the transcript and pick the moments (PLAYBOOK §3).
- **Check who's on screen** in every first preview: look at a few frames, not only the QA line. QA clean means
  nothing covers a face; a `SPEAKER?` note means the person shown may not be the one talking (PLAYBOOK §2).
- **Show, don't describe:** after a render run `./clip gallery <episode>` and give them the `file://` link (or open
  it); it shows every preview with its QA result. Previews are under 10 MB: they can drop them into a chat as is.
- **Something none of the styles does?** ("make it a cooking show", "a boxing match") Write it: the eleven styles
  are a starter kit, and a new format is a new script on the engine (PLAYBOOK §4, `clipkit/fx.py`, `boards.py`).
- **Errors** come out as one plain line (a wrong key, no credit, a missing ffmpeg, an audio-only file): say what it
  means and what to do. Don't re-run transcription to "try again" unless asked: it's the step that costs.
- **Audio-only podcast?** The clips are cut from the video (faces, cameras); say so, and offer to clip the video
  version if they have one.

## What you can do

**Clip a podcast episode** into short vertical clips: it transcribes the episode, finds the funny and surprising
moments, and makes clips with a headline, captions, effects and an end card, from calm and classy to full meme edit
(PLAYBOOK §4). By default 7 candidates, the 5 best polished and ranked, the user picks 3. The fastest start is one
clip from a time range: `./clip quick <episode> 12:30-13:05 --style bold` (eleven styles: PLAYBOOK §4). Along the way: a **cleaned transcript**,
**subtitles** (.srt), **chapters** and a **description draft**. Optionally it **uploads** clips to YouTube Shorts
(`publish/`). Then offer: first-time setup if needed, or "give me the episode video and any notes you have".

## First-time setup

Do these in order and tell the user briefly what you did. Ask before installing anything system-wide.

1. **System.** macOS, Linux or Windows. On Windows the command is `clip` (`clip.cmd`) instead of `./clip`, and the
   venv's Python is `.venv\Scripts\python.exe` instead of `.venv/bin/python`.
2. **Tools.** `ffmpeg` and Python ≥ 3.14. Missing → ask first, then macOS `brew install ffmpeg python@3.14`,
   Linux the distro's `ffmpeg` package (and Python 3.14 from the distro, python.org or `uv`), Windows
   `winget install Gyan.FFmpeg Python.Python.3.14`.
3. **Dependencies.**
   ```bash
   python3.14 -m venv .venv && .venv/bin/pip install -r requirements.txt
   ```
   (Windows: `py -3.14 -m venv .venv` and `.venv\Scripts\pip install -r requirements.txt`.)
4. **API keys.** `cp .env.example .env` if there's no `.env`. Ask the user to open `.env` themselves and fill in
   at least one key (see "Keys" above): `ELEVENLABS_API_KEY` (the best transcription: names, speakers, other
   languages), `OPENAI_API_KEY` (transcription too, plus reading notes, transcript cleanup, headlines, cover
   frames), or `SONIOX_API_KEY`. Transcription uses ElevenLabs, then Soniox, then OpenAI, whichever is set first
   (`STT=elevenlabs|soniox|openai` picks one). Also `CLIPPER_HOST`: the host's first name, so the host and guest
   aren't mixed up.
   **Never** ask for keys in the chat, never print `.env` or a key, never put keys anywhere but `.env` (it's
   git-ignored). Check without revealing:
   `.venv/bin/python -c "import re;t=open('.env').read();print({k:bool(re.search(k+r'=\S+',t)) for k in ['OPENAI_API_KEY','ELEVENLABS_API_KEY','SONIOX_API_KEY']})"`
   (one True is enough to start; OpenAI adds the notes, the cleanup and the headlines)
5. **Smoke test.** `./clip test && ./clip selftest` (unit tests, then a test clip rendered end to end, ~10 s).
6. **Their look (optional).** Offer to make `theme.json` from `theme.example.json`: the show's name, an accent colour,
   a logo. The neutral default is fine to start with.
7. **Done.** Tell the user: give me an episode video (plus notes if you have them) and ask for clips.

## Publishing (optional): YouTube Shorts

`./clip publish youtube …` (`./clip yt …` for short) uploads exported clips as Shorts, scheduled, with title and
description. It is **upload-only by design**: the token has just the `youtube.upload` scope (Google refuses delete
and edit with it) and `publish/youtube.py` lets no other call through. Don't widen the scope or add other endpoints.
Other platforms: `publish/README.md` (what their APIs allow, how to add one with the same safety rules).

1. **Once:** `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` in `.env` (the user fills them in), then the user runs
   `./clip yt login` themselves and picks the channel (setup: `publish/youtube.md`).
2. `./clip yt plan <episode>` drafts `projects/<episode>/youtube.json` from `export/<clip>/` (an .mp4 and a
   `description.md`: `# Title`, then the description). Fix titles and descriptions, set `publishAt` with a time zone
   (`2026-10-20T17:00:00+02:00`). Without `publishAt` it stays private.
3. `./clip yt check <episode>`, show the user the list and **get a yes before uploading**: uploads publish.
4. `./clip yt upload <episode>`. Each videoId is written back right away, so a rerun only does what's left.
5. Tell the user what's left in Studio for each Short (the upload prints the links): the **cover** and the
   **related video** (neither is in the API).

## Repo map

```
PLAYBOOK.md            how to make clips (read before making any)
theme.example.json     a show's look: copy to theme.json (keys documented in clips/clipkit/theme.py)
clip, clip.cmd         the one command: ./clip (Windows: clip) (no arguments = help)
prep/                  getting an episode ready: folder, transcription (stt.py: OpenAI, ElevenLabs or Soniox),
                       LLM cleanup, name fixes, subtitles; quick.py (./clip quick)
publish/               optional: uploads finished clips to platforms (youtube.py: Shorts, upload-only)
clips/                 clipkit/ (the engine: theme, style, brand, fx, boards, angles, render + QA), templates/
                       (the eleven ./clip quick styles), run.py, selftest.py, review.py
tests/                 unit tests (./clip test)
assets/                fonts (Inter, JetBrains Mono, both OFL), YuNet face model
projects/<id>/         one episode: source/ (video + notes), work/ (transcripts, caches), scripts/, preview/, final/,
                       episode/ (extras), export/ (clips to publish), concepts.md
```

## Working on the code

- One language: Python ≥ 3.14, standard library plus numpy, opencv-python 5, pillow (and ffmpeg). No other runtimes.
  Faces: OpenCV's YuNet (`clipkit/faces.py`, model in `assets/models/`).
- `prep/steps.py` holds the prep steps, `prep/cli.py` is the thin `./clip` layer, prompts are in `prep/prompts.py`.
  Project state is `projects/<id>/project.json`, changed only through `update_project` (locked across threads and
  processes).
- Keep `clipkit` small. Anything that keeps clips from looking broken belongs in the engine as an automatic check,
  not only in the docs. Colours and fonts come from the theme, never hard-coded. After changes:
  `./clip test && ./clip selftest`, and render a real episode's clips.
- Commits: `fix:` one bug each, `feat:` / `docs:` for engine and docs, `content:` for episode work. Never commit
  media, renders, `.env` or `.venv/`.
