"""$title: the "directed by" ending ($style style, made with `./clip quick`): the clip plays out with clean
captions, then the last frame freezes, fades to warm film and a credits card rolls in over a bouncy jazz riff.
It's a normal clip script: edit the settings below or anything else, then `./clip render $episode $num`."""
from clipkit import *

NAME = "$name"
# source seconds; tight() trims long pauses
E = Edit(tight(($start, $end)))
# the opening line (None: no headline)
HEADLINE = $headline
# the credits card: a small line over a big name (None: whoever is on screen, else the show's name)
CREDIT_TOP = $credit_top
CREDIT = $credit
# seconds of freeze and credits after the last word
FREEZE = 3.2
CHUNKS = chunk_words(E.words(), 4, 22)


def draw(t, fr, face):
    if t < E.dur:
        c = Image.fromarray(crop(fr, face, W, H, zoom=1.04)).convert("RGBA")
        if HEADLINE:
            intro(c, HEADLINE, face, t)
        captions(c, CHUNKS, t, style="clean")
        return c
    k = t - E.dur
    c = Image.fromarray(crop(fr, face, W, H, zoom=push(k, 0, FREEZE, 1.04, 1.12))).convert("RGBA")
    if k < FREEZE:  # the freeze: the last frame, held on purpose
        c = faded(c, ease_out(k / 0.15))
        if k > 0.45:
            a = ease_out((k - 0.45) / 0.5)
            c.alpha_composite(fade(W, 760, INK, 0.0, 0.7 * a), (0, H - 760))
            name = CREDIT or speaker() or THEME["name"] or "nobody, apparently"
            place(c, credits_card(CREDIT_TOP, name, 92), W / 2, H * 0.66, 1, a)
        return c
    c = faded(c)
    end_card(k - FREEZE, c)
    return c


def sound(mix):
    mix.add(E.dur - 0.05, bed_credits(FREEZE + 1.6), 0.8)


if __name__ == "__main__":
    render(NAME, E, draw, sound, tail=FREEZE + 1.4, outro_sound=False)
