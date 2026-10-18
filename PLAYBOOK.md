# Playbook: making clips

You turn a podcast episode into short vertical clips that people actually watch, and you guide the user from video
to finished clips: ask for what you need, show results early, take feedback, finish. Each clip is a small Python
script on `clipkit` (`clips/clipkit/`), so anything is possible; the rules here keep clips from looking broken.

## 1. Working with the user

**Kickoff.** Look at what you were given before asking anything.
- Only a video? Start step 2 right away, skim the transcript while it runs, then ask **once**, in one short message:
  show notes, a description, a guest bio, names of people and projects that come up? Moments they'd like as clips?
  Anything off-limits? **What energy:** calm and classy, punchy, or full meme (§4)? And offer the shortcut: *"or I
  just pick the best moments and show you previews."*
- They gave notes or a brief already? Don't re-ask what's in them.
- No `theme.json` yet? Offer to make one (show name, accent colour, logo; §7). Until then the neutral default works.

**First clip fast.** For a first-timer, the quickest win is `./clip quick` (§5): one clip from a time range, in a
style, in about a minute. Show it, then build the real set.

**The default set: 7 candidates → 5 finalists → the user picks 3.** Unless the user asks otherwise:
1. build 7 candidates: **3 concept clips** (something concrete you can draw: a number, an object, a process),
   **3 conversation clips** (the exchange carries it: captions and the frame, at most one small accent) and
   **1 experiment** (a format or a visual idea this repo hasn't done yet),
2. review all 7 yourself, keep the **5 best**, give those another improvement pass,
3. show the user the funnel, short: all 7 with one line each on why it made it or not, then the 5 finalists ranked.
   They pick 3 and maybe give feedback; log it all in `projects/<id>/concepts.md`.

**Read the room.** Someone who answers in detail wants to steer: show the shortlist before building. Someone who says
"just go" wants results: use defaults and come back with previews. Never more than one round of questions in a row.
When the style itself is the open question, render the same moment in two or three styles side by side.

**Be concise.** Every message the user reads should be short: what you made (paths), what you fixed after your own
review, one question (*anything janky, boring, covered or off?*). At finals: on-screen text you made up for the joke
and names you couldn't verify. No essays about your process.

**Git.** If the user keeps episodes in git: one branch per episode (`episode/<id>`), commits with `content:` for
episode work and `fix:` / `feat:` for the tool. `.gitignore` lets through only an episode's text; video, audio and
renders never get committed. Ask before pushing.

## 2. Prepare the episode

```bash
./clip new <video> [notes.md subs.srt …] --slug <short-name> --go   # episode folder, transcribe, clean up
./clip add <id> notes.md && ./clip step <id> clean                   # material that arrives later
./clip meta <id> --episode S02E08 --guest "First Last"               # if the notes didn't say
./clip meta <id> --episode-title "Guest Name: Topic"                 # the end card shows it
```

Result: `projects/<id>/work/words.json` (every word: `t`, `s`/`e` in ms, `sp` speaker) and `work/transcript.clean.json`.

**Names and odd wordings.** The cleanup is an LLM pass with a glossary from the notes; it still misses things. Read the
cleaned transcript for names spelled wrongly or inconsistently, misheard terms and phrases that make no sense. Check
names against the notes and, if you can search the web, confirm people, companies and projects there. What you can't
confirm goes into your one question. Apply every correction with `./clip fix <id> "wrong => right" …`: it fixes the
word timings (so all captions), the transcripts and the glossary, and survives a re-transcription.

**Cameras and people.** The first render analyses the episode's camera angles and who sits where (a few minutes,
once): `work/angles.json` and the contact sheet `work/angles.jpg`. **Look at the sheet once.** Each row is an angle
with its faces boxed and labelled with the matched speaker; orange `(?)` labels are guesses. Fix what's wrong in one
line, `./clip angles <id> --set A2=3 C1=1` (angle A's 2nd face from the left is speaker 3), or set `"skip": true` on a
junk angle, then re-render. If names are swapped, fix `"speakers"` in `project.json` (id -> name) and re-run
`./clip angles <id> --force`. A single-camera show needs none of this.

## 3. Pick moments

Read the **whole** cleaned transcript. Keep moments that are funny, surprising or quotable (a confession, a strong
take, a number nobody expected, a story told well, a callback that pays off), not dry explanations. Each stands alone:
setup → turn → payoff in 15–40 s, ending right after the payoff. Start a second or two **before** the setup, so the
clip never opens mid-thought. Sort them as you go: **animatable** or **conversation**.

## 4. Pick the energy

Clips can be anything from a calm, classy quote to a full meme edit. Match the moment and the show; ask when unsure.

| energy | looks like | parts |
|---|---|---|
| **chill** | clean captions, a slow push-in, a soft bed; the conversation does the work | `captions(style="clean")`, `push()`, `bed_soft` |
| **bold** | caps captions with the spoken word on a plate, zoom punches on the beat, a sticker by the head, a beat | `captions(style="bold")`, `punch()`, `sticker()`, `wobble()`, `bed_beat` |
| **meme** | one huge word at a time, punches on every line, and the drop: black and white, slow push-in, a big caption, a phonk beat | `captions(style="meme")`, `mono()`, `vignette()`, `meme_text()`, `slam()`, `shake()`, `flash()`, `deep_fry()`, `bed_phonk` |

`clips/templates/` has a working script for each (that's what `./clip quick` copies). Mix freely: a chill clip with
one meme drop on the punchline is often the funniest version. Two rules for the loud end:
- **One drop per clip.** The deep-fry, the shake, the "SIGMA RULE #47": once, on the payoff, reads as a joke. Five
  times reads as noise.
- **Tease situations, not people.** Nothing mean or tasteless about the guest, other people or groups.

## 5. Build, render, review

**The fast path.** One clip from a time range, from a template, rendered as a preview:

```bash
./clip quick <id> 12:30-13:05 --style chill|bold|meme [--headline "…"] [--sticker "…"] [--meme "…"]
```

With an OpenAI key it writes the headline (and the sticker or the drop's caption) itself. The result is a normal
script in `projects/<id>/scripts/`: edit it like any other.

**The full path.** Scripts go in `projects/<id>/scripts/NN_name.py` (shared helpers: `_name.py`). Start from a
template; `from clipkit import *` gives you everything (summary at the end).

```bash
./clip render <id>             # every script: fast previews (540p, 15 fps) in parallel + QA table
./clip render <id> 03 05       # just these
./clip render <id> --final     # full quality → projects/<id>/final/
```

Previews always stay under 10 MB, so they can go straight into Discord or a chat. Renders use the best video encoder
the machine has (the header line of `./clip render` names it); `CLIP_ENCODER=x264` forces the CPU one.

Every render writes, next to the video (`preview/` or `final/`):
- `<name>.qa.txt`: automatic checks, a safety net. **Issues** get fixed; **notes** (UNDER APP UI, TIGHT) you judge on
  the stills (`run.py` shows both):
  - `COVERS FACE`: something over the face of the person on screen,
  - `OVERLAP`: two elements on top of each other (mark a deliberate one with `place(..., over=True)`),
  - `TIGHT`: content closer than 16 px to the edge of its card,
  - `CLIPPED`: text or an icon cut off at its card's edge (`clip_ok=True` for things meant to run off),
  - `CROP JUMP`: the framing moved abruptly inside a shot,
  - `FROZEN`: one source frame held over 1.3 s while the voice runs (it reads as a bug; a held frame *after* the
    voice, like the meme drop, is fine),
  - `UNDER APP UI`: something sits where Instagram, X or LinkedIn draw their own UI (§7 Safe zones).
- `<name>.events.jpg`: every `*_T` moment of your script, frame by frame from −0.1 s to +2.4 s. Each element should
  enter cleanly, read fully, never jump, and leave on purpose. **Name every moment the edit reacts to `SOMETHING_T`**
  so it shows up here.
- `<name>.grid.jpg`: one frame per second. `<name>.cover.jpg`: the first frame, which apps use as the preview.
- `<name>.zones.jpg`: three moments under each app's UI. For any other moment: `./clip zones <mp4> out.jpg --at 12.5`.
  To watch a whole clip as people will see it: `CLIP_MOCK=instagram CLIP_OUTDIR=../variants/ig ./clip render <id> 03`.
- Trying a look without editing: `CLIP_LAYOUT=split`, `CLIP_PANEL_ALPHA=170` (see-through cards), `CLIP_THEME=other.json`.

**Look at full-size stills of every board**, not just the grids: `ffmpeg -ss <t> -i <mp4> -frames:v 1 still.jpg` (or
`./clip review <mp4> out.jpg --step 0.1 --from 12 --to 14`). Judge spacing like a designer: even margins inside cards,
the same gap between rows, nothing crammed against an edge, text big enough to read on a phone. Fix and look again;
2–4 rounds per clip is normal. Render finals when previews are clean and the user is happy (or said "just go").

**Covers.** Apps show the first frame, but a designed cover does better: `clipkit/thumb.py` cuts the person out of a
frame (macOS Vision; elsewhere the shot with soft edges) and sets them under a headline with the key words in the
accent colour: `cover(src_t, "**Key words** and the rest", out, layout="frame"|"quote"|"face")`. Pick the frame by eye
(eyes open, a real expression).

## 6. Episode extras

Offer them in one line at hand-off unless they asked already. They go in `projects/<id>/episode/`.
- **Subtitles:** `./clip srt <id>` → `subtitles.srt` (after the name fixes).
- **Chapters:** `chapters.txt` in YouTube format (`0:00 Intro`, …): first at 0:00, 6–14 chapters of at least ~2
  minutes, starting where the topic really changes, short specific titles, in the episode's language.
- **Description draft:** `description.md`: two or three short paragraphs on who the guest is and what they talk about,
  plain and concrete, no hype, then the chapters.
- **Post texts** per clip, for publishing: `export/<clip>/description.md` (`# Title`, then the description).

## 7. Rules

**The look is the show's.** `theme.json` (copy `theme.example.json`) holds the show's name, accent colour, fonts, logo,
end-card line and default caption style; `clipkit/theme.py` documents every key. The engine draws everything from it,
so one file changes every clip. Within a theme, make each idea look designed, not like default "AI motion graphics":
- One accent colour, used for what matters (the spoken word, the key number). Colours that belong to the idea are fine
  inside it (terminal green, a stock chart's red).
- Plain shapes, generous spacing, crisp text. Avoid the tired patterns: eyebrow text (small tracked caps above a
  heading), "x · y · z" strings joined by dots, circling things in an ellipse, soft drop shadows on everything.
- Headline = `intro()`: two lines max, fully visible on frame 1, gone after ~2.6 s; it finds a spot off the face by
  itself. Captions = `captions()`. End card = `end_card()` (the logo or the show's name, the episode, the end line).
- No logo or watermark inside the clip (the app shows the channel); the end card has it.

**Illustrations, not reading.** The graphics keep people watching; the conversation is the content. A few words per
element, ideally the speaker's own; main words ≥ 44 px, small labels ≥ 32 px (check on a full-size still). Vary the
form: a big number straight on the shot, a chart drawn in sync with the argument, a fake artifact the story happens in
(a receipt, a chat log, a terminal, an app screen), a scoreboard, a before/after, a sticker by the head.

**Headlines** read like a person wrote them: a hook in plain words, two lines max. No colon twists, no hype words.

**Layout and spacing.** Start full-frame (`frame_canvas`) and bring a board in only while it has content. By default
the board sits **over the video**, just above the captions (`board_y(h)` places it); `"layout": "split"` in
project.json puts the video in a band at the top instead. Build boards from parts with `vstack`/`hstack`/`on_panel`
and the spacing tokens: padding inside cards ≥ `PAD` (40), gaps ≥ `GAP` (24), everything on the 8 px grid.

**Safe zones.** The apps draw over the clip: a top bar (~230 px), the username + caption block at the bottom
(~400 px) and a like/comment rail on the right from y≈1020 (x > ~950). The numbers live in `clipkit/safezones.py`.
`intro()` and `captions()` are placed right already; boards stay ≤ `CAPTION_W` wide, between `BOARD_TOP` and
`BOARD_BOTTOM`; `safe_width(y0, y1)` tells you how wide something centred can be.

**Faces.** Nothing covers a face (QA checks every frame). The first frame must be a good face of the person speaking
(eyes open, no hand near the face); `render()` picks it, so check the cover.

**Cuts and cameras.** Jump cuts are fine, glitches and freezes under a running voice are not. `tight()` keeps pauses up
to 0.45 s; `./clip meta <id> --cuts tight|loose|0.6` changes it for an episode, `tight(..., max_gap=0.8)` for one clip
(a conversation clip often wants the beat before a punchline). Each shot keeps one person, whoever talks most (or
`Edit(..., focus="Name")`). To hold the speaker over a short cutaway at a payoff: `Edit(..., hold=0.8)` (max 1.2 s).
Your own zooms: smooth, never starting on a camera cut (`punch()` and `push()` are).

**Motion and sound.** Animate when something happens; nothing idles. Hold the payoff ≥ 1.5 s before the end card. The
voice stays clean (no effects on speech). Sound only from `sfx_*` / `bed_*`: synthesized in code, so no copyrighted
music ever ends up in a clip. `render()` puts a short chime under the end card (`"outro_chime": false` in the theme
turns it off); there's no intro jingle.

**Loops.** Platforms replay clips in a loop: keep the end card short, end on silence (automatic), and make the first
second strong (a good face, the headline) so the replay reads as a fresh start.

**Words.** Captions say what was said: fix ASR errors with `./clip fix` (everywhere) or `E.words(fix={...})` (one
clip), never change meaning. Facts and numbers on screen must be true.

## clipkit in one screen

- `Edit(tight((start_s, end_s), …), focus=None, hold=0.0)`: cut a moment from word timings (pauses and lone fillers
  removed). `tight()` may split a range into pieces, so find times with `E.out_t(src_s)`. `E.words(fix=…)` → caption
  words; `chunk_words`, `active`.
- `frame_canvas(fr, face, split)`: video full-frame or split. `crop(fr, face, w, h, zoom, face_y, dx, dy)`:
  face-following crop; `face_out(face)`, `face_rect(face)`; `shot_info(t)`.
- Look: `bar`, `tag`, `label`, `chip`, `panel`, `stamp`, `mark`, `gradient`, `fade`, `radial`, `grain`, `fade_in`,
  `vstack`, `hstack`, `on_panel`; tokens `U`, `PAD`, `GAP`, `R`, `WHITE`, `GREY`, `LINE`, `MUTED`; theme `ACCENT`,
  `ON_ACCENT`, `TEXT`, `INK`, `THEME`; fonts `F_BLACK`, `F_XBOLD`, `F_BOLD`, `F_MED`, `F_REG`, `F_MONO`, `F_MONO_B`,
  `F_MONO_XB`.
- Effects (`clipkit/fx.py`): `punch`, `push`, `shake`, `mono`, `deep_fry`, `vignette`, `flash`, `letterbox`,
  `meme_text`, `sticker`, `wobble`, `slam`.
- `text_line`, `text_block`, `emoji`, `rounded`, `asset`; easing `ease_out`, `ease_in_out`, `clamp01`, `pop`;
  `place(canvas, im, x, y, scale, alpha, rot, anchor, over=, clip_ok=)`.
- `intro(c, text, face, t)`, `captions(c, CHUNKS, t, split, style=)` (or `cap(chunk, t)`), `accent(…)`,
  `beside_face(c, im, face)`, `end_card(t, c)`; `BOARD_TOP`, `BOARD_BOTTOM`, `CAPTION_Y`, `CAPTION_W`, `SAFE_TOP`,
  `safe_width(y0, y1)`.
- `render(NAME, E, draw, sound, bed=…, tail=…, outro_sound=…)`; in `sound(mix)`: `mix.add(t, sfx_…(), gain)`,
  `mix.mute(t0, t1)`; beds `bed_soft`, `bed_beat`, `bed_drone`, `bed_phonk`.

## Checklist (every round, every clip)

- [ ] `./clip render` has no issues; notes judged on the stills; `zones.jpg` looks right
- [ ] `events.jpg` and full-size stills: clean entrances and exits, even spacing, readable on a phone
- [ ] headline off the face, visible on frame 1, gone by ~2.6 s; the cover is a good face of the speaker
- [ ] the right person on screen through camera cuts (check `work/angles.jpg` once per episode)
- [ ] the energy fits the moment; at most one drop; nothing mean
- [ ] graphics are illustrations: few words, big enough; the set mixes concept, conversation and one experiment
- [ ] every animation tied to a moment; payoff held, then the end card
- [ ] names, numbers and idioms checked; made-up on-screen text listed for the user
