"""$title: "wait, rewind" ($style style, made with `./clip quick`): the clip plays, then a VHS rewind scrubs back
over the punchline and it plays again, sound and all. It's a normal clip script: edit the settings below or anything
else, then `./clip render $episode $num`."""
from clipkit import *

NAME = "$name"
# source seconds; tight() trims long pauses
E = Edit(tight(($start, $end)))
# the opening line (None: no headline)
HEADLINE = $headline
# seconds of the end that rewind and play again (within the last piece of the edit)
REPLAY = min(2.2, E.pieces[-1][1] - E.pieces[-1][0])
REWIND = 0.8
CHUNKS = chunk_words(E.words(), 3, 16)
KEPT = {}  # output frame -> a half-size copy of the shot, for the rewind and the replay


def shot(fr, face, zoom=1.04):
    return Image.fromarray(crop(fr, face, W, H, zoom=zoom)).convert("RGBA")


def draw(t, fr, face):
    if t < E.dur:
        c = shot(fr, face)
        if t >= E.dur - REPLAY - 0.1:
            KEPT[int(round(t * FPS))] = c.convert("RGB").resize((W // 2, H // 2), Image.BILINEAR)
        if HEADLINE:
            intro(c, HEADLINE, face, t)
        captions(c, CHUNKS, t, style="bold")
        return c
    k = t - E.dur
    keys = sorted(KEPT)
    if keys and k < REWIND:  # backwards, fast
        i = keys[max(0, int(len(keys) * (1 - k / REWIND)) - 1)]
        return vhs(KEPT[i].resize((W, H), Image.BILINEAR), 1.0, seed=int(t * 30), osd="◀◀ REWIND")
    if keys and k < REWIND + REPLAY:  # and again, at normal speed
        tt = E.dur - REPLAY + (k - REWIND)
        i = min(keys, key=lambda x: abs(x - tt * FPS))
        c = vhs(KEPT[i].resize((W, H), Image.BILINEAR), 0.35, seed=int(t * 30), osd="▶ PLAY")
        captions(c, CHUNKS, tt, style="bold")
        return c
    c = shot(fr, face)
    end_card(k - REWIND - REPLAY, c)
    return c


def sound(mix):
    mix.add(E.dur, sfx_rewind(REWIND), 0.6)
    a, b = E.pieces[-1]
    mix.add(E.dur + REWIND, edit_audio(Edit([(b - REPLAY, b)])), 1.0, track="voice")


if __name__ == "__main__":
    render(NAME, E, draw, sound, tail=REWIND + REPLAY + 1.4, outro_t=E.dur + REWIND + REPLAY)
