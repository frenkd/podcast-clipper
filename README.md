# podcast-clipper

Turn a podcast episode into short vertical clips for TikTok, Reels and Shorts. A coding agent does the editing: it
finds the moments worth sharing and makes clips with a headline, captions, effects and an end card, in your show's
look.

![An episode goes in, clips in three styles come out: chill, bold and meme](docs/hero.png)

## Get started

You need Python 3.14+, ffmpeg, a coding agent (Claude Code, Codex, Cursor, …) and an
[OpenAI API key](https://platform.openai.com/api-keys).

1. `git clone https://github.com/frenkd/podcast-clipper`, open the folder with your agent and ask:
   **"Do the first-time setup."** It installs what's missing (asking first) and runs a self-test.
2. Open `.env` and paste in your OpenAI key. (Never paste keys into the chat.)
3. Ask: **"Make clips from ~/Videos/episode.mp4"**. Add anything that helps (show notes, the guest's name, a moment
   you liked) or just say "go with the defaults".

It shows you previews, you say what to change, and the finals land in `projects/<episode>/final/`.

## Your first clip in a minute

Know the moment already? One command makes one clip:

```bash
./clip quick my-episode 12:30-13:05 --style meme
```

| style | what you get |
|---|---|
| `chill` | clean captions, a slow push-in, a soft beat |
| `bold` | caps captions with the spoken word on a plate, zoom punches, a sticker |
| `meme` | one huge word at a time, then the black-and-white "sigma" drop with a phonk beat |
| `dramatic` | on the punchline: a smash zoom into the face, a shake, a boom and a big reaction |
| `credits` | the clip plays out, freezes, and a "directed by" card rolls in over a bouncy riff |

It writes a short script in `projects/my-episode/scripts/` and renders a preview. The script is yours: change a
word, a colour, the timing, and render again. Try the same moment in a few styles to feel the range.

## Make it yours

Copy `theme.example.json` to `theme.json`:

```json
{ "name": "My Podcast", "accent": "#FFC53D", "captions": "bold", "logo": "assets/logo.png" }
```

Every clip follows it: colours, fonts, caption style, logo, end card. All the options are in
[`clips/clipkit/theme.py`](clips/clipkit/theme.py), or ask the agent: "make it look like our show, here's our logo".

## What it takes care of

![Transcribe, find moments, make clips, you pick](docs/how.png)

- **Picking moments:** it reads the whole transcript and suggests the funny, surprising and quotable bits.
- **The right person on screen:** it learns the camera angles and who sits where, and follows whoever talks.
- **Nothing looks broken:** every frame is checked so text never covers a face or sits under the apps' buttons,
  and the picture never jumps or freezes mid-sentence.
- **Shareable previews:** always under 10 MB, ready for Discord or a chat. Finals at full quality, using your
  graphics chip's encoder when there is one.
- **Extras:** subtitles (.srt), chapters, a description draft, covers. Optionally it uploads to YouTube Shorts
  ([publish/](publish/README.md)).
- **No copyright trouble:** all music and sound effects are generated in code.

Transcription uses OpenAI by default; add a [Soniox](https://soniox.com) key to `.env` for better accuracy with
names and non-English shows. Runs on macOS, Linux and Windows.

## How it's built

Plain Python (numpy, OpenCV, Pillow) and ffmpeg, no web app and no service of its own: it runs on your computer and
talks only to the APIs you give it keys for. The agent reads [AGENTS.md](AGENTS.md) first and follows
[PLAYBOOK.md](PLAYBOOK.md) to make clips; `./clip` is the one command (run it without arguments for help), and each
clip is a small script on the engine in [`clips/clipkit/`](clips/clipkit/).

MIT licensed ([LICENSE](LICENSE)). Fonts: Inter and JetBrains Mono (SIL Open Font License).
