"""$title: a meme edit ($style style, made with `./clip quick`): one-word captions, punches on the beat, and when
the line lands, the "sigma" drop: black and white, a slow push-in, a big caption and a phonk beat. It's a normal
clip script: edit the settings below or anything else, then `./clip render $episode $num`."""
from clipkit import *

NAME = "$name"
# source seconds; tight() trims long pauses
E = Edit(tight(($start, $end)))
# the opening line (None: no headline)
HEADLINE = $headline
# the caption of the drop
DROP_TEXT = $meme
# seconds of drop after the last word
DROP = 2.6
CHUNKS = chunk_words(E.words(), 3, 16)
BEATS = [ch["s"] for ch in CHUNKS]


def draw(t, fr, face):
    if t < E.dur:
        c = Image.fromarray(crop(fr, face, W, H, zoom=1.08 * punch(t, BEATS, 0.05))).convert("RGBA")
        if HEADLINE:
            intro(c, HEADLINE, face, t)
        captions(c, CHUNKS, t, style="meme")
        return c
    k = t - E.dur
    if k < DROP:  # the drop: the last frame, held on purpose
        sx, sy = shake(k, 0.0, 0.35, 30)
        c = Image.fromarray(crop(fr, face, W, H, zoom=push(k, 0, DROP, 1.08, 1.32), dx=sx, dy=sy)).convert("RGBA")
        c = vignette(mono(c, ease_out(k / 0.2)), 0.8)
        if k < 0.35:
            c = deep_fry(c, 1 - k / 0.35)
        flash(c, k, 0.0, 0.18)
        place(c, meme_text(DROP_TEXT, 112), W / 2, 420, slam(k, 0.12), clip_ok=True)
        return c
    c = Image.fromarray(crop(fr, face, W, H, zoom=1.32)).convert("RGBA")
    end_card(k - DROP, c)
    return c


def sound(mix):
    mix.add(E.dur, sfx_boom(), 0.7)
    mix.add(E.dur, bed_phonk(DROP + 1.6), 0.85)


if __name__ == "__main__":
    render(NAME, E, draw, sound, tail=DROP + 1.4, outro_sound=False)
