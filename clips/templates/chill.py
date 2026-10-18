"""$title: a calm clip ($style style, made with `./clip quick`). It's a normal clip script: edit the settings below
or anything else, then `./clip render $episode $num`. See PLAYBOOK.md for what else a clip can do."""
from clipkit import *

NAME = "$name"
# source seconds; tight() trims long pauses
E = Edit(tight(($start, $end)))
# the opening line (None: no headline)
HEADLINE = $headline
CHUNKS = chunk_words(E.words(), 4, 22)


def draw(t, fr, face):
    zoom = push(min(t, E.dur), 0, E.dur, 1.0, 1.08)   # a slow push-in over the whole clip
    c = Image.fromarray(crop(fr, face, W, H, zoom=zoom)).convert("RGBA")
    if t >= E.dur:
        end_card(t - E.dur, c)
        return c
    if HEADLINE:
        intro(c, HEADLINE, face, t)
    captions(c, CHUNKS, t, style="clean")
    return c


def sound(mix):
    pass


if __name__ == "__main__":
    render(NAME, E, draw, sound, bed=bed_soft, bed_gain=0.07)
