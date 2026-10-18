"""$title: a punchy clip ($style style, made with `./clip quick`). It's a normal clip script: edit the settings below
or anything else, then `./clip render $episode $num`. See PLAYBOOK.md for what else a clip can do."""
from clipkit import *

NAME = "$name"
# source seconds; tight() trims long pauses
E = Edit(tight(($start, $end)))
# the opening line (None: no headline)
HEADLINE = $headline
# a word or two that pops up beside the head (None: none)
STICKER = $sticker
# when
STICKER_T = E.dur * 0.45
CHUNKS = chunk_words(E.words(), 3, 16)
BEATS = [ch["s"] for ch in CHUNKS][1::2]   # a zoom punch on every other caption


def draw(t, fr, face):
    zoom = 1.06 * punch(t, BEATS, 0.06)
    c = Image.fromarray(crop(fr, face, W, H, zoom=zoom)).convert("RGBA")
    if t >= E.dur:
        end_card(t - E.dur, c)
        return c
    if HEADLINE:
        intro(c, HEADLINE, face, t)
    if STICKER and STICKER_T <= t < STICKER_T + 1.8:
        im = sticker(STICKER, 60)
        k = 0.6 + 0.4 * back_out((t - STICKER_T) / 0.25)  # pops in
        im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.BICUBIC)
        a = 1 - clamp01((t - STICKER_T - 1.55) / 0.25)
        beside_face(c, im.rotate(-6 + wobble(t, STICKER_T, 2), expand=True, resample=Image.BICUBIC), face, a)
    captions(c, CHUNKS, t, style="bold")
    return c


def sound(mix):
    mix.add(0.05, sfx_whoosh(0.4), 0.25)
    if STICKER:
        mix.add(STICKER_T, sfx_pop(), 0.5)


if __name__ == "__main__":
    render(NAME, E, draw, sound, bed=bed_beat, bed_gain=0.09)
