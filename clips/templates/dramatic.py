"""$title: the dramatic zoom ($style style, made with `./clip quick`): bold captions, and on the punchline a smash
zoom into the face with a shake, a red vignette, a boom and a big reaction in place of the captions. It's a normal clip script: edit the
settings below or anything else, then `./clip render $episode $num`."""
from clipkit import *

NAME = "$name"
# source seconds; tight() trims long pauses
E = Edit(tight(($start, $end)))
# the opening line (None: no headline)
HEADLINE = $headline
# the caption when it hits
DRAMA_TEXT = $drama
CHUNKS = chunk_words(E.words(), 3, 16)
# when it hits: the caption that starts closest to 2.5 s before the end (or set a time in seconds)
PUNCH_T = min((ch["s"] for ch in CHUNKS), key=lambda s: abs(s - (E.dur - 2.5))) if CHUNKS else E.dur * 0.7
# seconds the zoomed-in shot holds after the last word, before the end card
HOLD = 1.2


def draw(t, fr, face):
    tt = min(t, E.dur)
    sx, sy = shake(t, PUNCH_T, 0.45, 0.035)
    z = 1.04 * snap(tt, PUNCH_T, 1.0, 1.9)
    c = Image.fromarray(crop(fr, face, W, H, zoom=z, dx=sx, dy=sy, face_y=0.36 + 0.08 * (z > 1.05), max_zoom=4.0))
    c = c.convert("RGBA")
    if t >= PUNCH_T:
        red_vignette(c, round(0.9 * ease_out((t - PUNCH_T) / 0.15), 1))
        flash(c, t, PUNCH_T, 0.12)
    if t >= E.dur + HOLD:
        end_card(t - E.dur - HOLD, c)
        return c
    if HEADLINE and t < PUNCH_T:
        intro(c, HEADLINE, face, t)
    if t >= PUNCH_T:  # the reaction takes the captions' place: the face is too big now for anything beside it
        place(c, meme_text(DRAMA_TEXT, 120), W / 2, CAPTION_Y, slam(t, PUNCH_T), ui_frac=0.45)
    else:
        captions(c, CHUNKS, t, style="bold")
    return c


def sound(mix):
    mix.add(PUNCH_T, sfx_impact(), 0.8)


if __name__ == "__main__":
    render(NAME, E, draw, sound, bed=bed_drone, bed_gain=0.08, tail=HOLD + 1.6, outro_t=E.dur + HOLD)
