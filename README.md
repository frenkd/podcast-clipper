# podcast-clipper

Turn a podcast episode into short vertical clips for TikTok, Reels and Shorts, with a coding agent doing the
editing. You give it the episode; it finds the moments worth sharing and makes clips with a headline, captions,
effects and an end card, in your show's look. From calm and classy to full meme edit.

![An episode goes in, clips in three styles come out: chill, bold and meme](docs/hero.png)

It's made for working with an AI coding agent (Claude Code, Codex, Cursor, …): open the folder, ask in plain
words, and the agent runs the tools, reviews its own work and shows you previews. Everything is plain Python you can
read and change.

## What it does

![Transcribe, find moments, make clips, you pick](docs/how.png)

- **Finds the moments.** It transcribes the episode (who said what, word by word), reads the whole thing and picks
  the funny, surprising and quotable bits: by default 7 candidates, the 5 best polished, and you choose 3.
- **Makes real clips, not just cut-outs.** A hook headline, word-by-word captions, the camera on whoever is talking
  (it learns the camera angles and who sits where), graphics drawn in sync with what's said, sound effects, an end
  card. Every frame is checked automatically: nothing covers a face, nothing sits under the apps' buttons.
- **Any energy.** `chill` (clean captions, a slow push-in), `bold` (caps captions with the spoken word on a plate,
  zoom punches, stickers) or `meme` (one huge word at a time and the black-and-white "sigma" drop at the end). Mix
  them, or go further: each clip is a small script.
- **Your look.** One file, `theme.json`: your show's name, accent colour, fonts, logo, end-card line.
- **The extras.** Full-episode subtitles (.srt), chapters, a description draft, covers. Optionally it uploads
  clips to YouTube Shorts.
- **Fast on any computer.** macOS, Linux or Windows; it uses your graphics chip's video encoder when there is one.
  Previews are always under 10 MB, so you can drop them straight into Discord or a chat.

## Get started

You need **Python 3.14+**, **ffmpeg**, a coding agent, and two API keys: [Soniox](https://soniox.com) for
transcription and [OpenAI](https://platform.openai.com/api-keys) for reading the transcript and writing headlines.

1. **Get the code.** `git clone https://github.com/frenkd/podcast-clipper` and open the folder with your agent.
2. **Ask: "Do the first-time setup."** It installs what's missing (it asks first), creates a `.env` file and runs a
   quick self-test.
3. **Add your keys.** Open `.env` yourself and paste in the two keys. Never paste keys into the chat.
4. **Ask: "Make clips from ~/Videos/episode.mp4".** Add anything you have (show notes, the guest's name, moments you
   liked) or just say "go with the defaults".

That's it. The agent shows you previews, you say what to change, it renders the finals into
`projects/<episode>/final/`.

### The fastest first clip

Already have the episode transcribed and know the moment? One command, one clip, about a minute:

```bash
./clip quick my-episode 12:30-13:05 --style meme
```

It writes a small script from a template (`clips/templates/`) and renders a preview. Try the same moment as `chill`,
`bold` and `meme` to see the range. With your OpenAI key it writes the headline itself; or pass `--headline "…"`.
The script it made is yours to edit: change a word, a colour, the timing, add a sticker, and render again.

## Make it look like your show

Copy `theme.example.json` to `theme.json` and change what you like:

```json
{
  "name": "My Podcast",
  "accent": "#FFC53D",
  "captions": "bold",
  "logo": "assets/my-logo.png",
  "end_line": "Full episode on YouTube"
}
```

Every key is optional and documented in [`clips/clipkit/theme.py`](clips/clipkit/theme.py): the accent colour, the
text colour, all the fonts, the caption style, the logo, the end card, the outro chime. Or just ask the agent:
"make it look like our show, here's our logo".

## How it decides

The agent follows [a playbook](PLAYBOOK.md): how to pick moments, how to match the energy to the moment, and the
rules that keep clips from looking broken. Some of them:

- **Faces first.** Nothing covers a face, and every clip opens on a good frame of the speaker (apps use it as the
  preview).
- **Safe zones.** Text stays clear of each app's own buttons and captions; it checks every frame against Instagram's,
  X's, LinkedIn's and TikTok's layouts.
- **No glitches.** Framing never jumps at camera cuts, and the picture never freezes while someone is talking.
- **Jokes from the content.** Funny comes from what was said. One meme drop per clip, and nothing mean about people.
- **No copyright trouble.** All music and sound effects are synthesized in code.

## Publishing (optional)

```bash
./clip publish youtube plan my-episode     # drafts titles, descriptions, publish times
./clip publish youtube upload my-episode   # after you've checked them
```

It can only upload: the sign-in gives it upload access and nothing else, so it can't delete or edit anything on your
channel. Setup is in [publish/youtube.md](publish/youtube.md); [publish/README.md](publish/README.md) says what
TikTok, LinkedIn, X and Instagram allow and how to add them.

## Under the hood

- `./clip`: the one command (`clip` on Windows); run it without arguments for help.
- `AGENTS.md`: what the agent reads first. `PLAYBOOK.md`: how it makes clips.
- `prep/`: gets an episode ready: transcription, cleanup, name fixes, subtitles, `./clip quick`.
- `clips/clipkit/`: the clip engine: theme, captions, effects (`fx.py`), face tracking, rendering with automatic
  checks. `clips/templates/`: the chill, bold and meme starters.
- `publish/`: optional uploads.
- `projects/<episode>/`: everything for one episode (video, transcript, clip scripts, previews, finals).

Python with numpy, OpenCV and Pillow, plus ffmpeg. No web app, no cloud service of its own: it runs on your computer
and talks only to the transcription and LLM APIs you give it keys for.

## License

MIT, see [LICENSE](LICENSE). Fonts: Inter and JetBrains Mono (SIL Open Font License).

Started as the clipping tool of [Ogrodje](https://ogrodje.si), a Slovenian tech podcast.
