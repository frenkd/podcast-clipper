"""$title: an explainer list ($style style, made with `./clip quick`): a card whose items appear as they're said, over
the shot, with the captions making room. It's a normal clip script: edit the settings below (labels, the words they
appear on) or anything else, then `./clip render $episode $num`."""
from clipkit import *

NAME = "$name"
# source seconds; tight() trims long pauses
E = Edit(tight(($start, $end)))
# the opening line (None: no headline)
HEADLINE = $headline
# the card: a small title, and each item with the word it appears on
TITLE = $list_title
ITEMS = $items
TIMES = timeline(E, [word for _, word in ITEMS], 0.8)
BOARD_IN, BOARD_OUT = TIMES[0] - 0.35, min(E.dur - 0.2, TIMES[-1] + 3.0)
CHUNKS = chunk_words(E.words(), 3, 18)
# the board sits over the video, off the face: under the chin if there's room, else above the head
# ("split": the video eases into a band at the top instead)
LOOK = "overlay"
deliberate(BOARD_IN, BOARD_IN + 0.35)
deliberate(BOARD_OUT, BOARD_OUT + 0.35)


def draw(t, fr, face):
    split = ease_out(clamp01((t - BOARD_IN) / 0.35)) * (1 - ease_out(clamp01((t - BOARD_OUT) / 0.35)))
    c = frame_canvas(fr, face, split, layout=LOOK)
    if t >= E.dur:
        end_card(t - E.dur, c)
        return c
    if HEADLINE and BOARD_IN > 1.2:
        intro(c, HEADLINE, face, t, until=min(2.6, BOARD_IN - 0.3))
    if split > 0:
        b = list_board(TITLE, [label for label, _ in ITEMS], [(t - ti) / 0.3 for ti in TIMES])
        if LOOK == "overlay":
            place_board(c, b, face, clamp01((split - 0.6) / 0.4))  # once the shot has made room
        else:
            place(c, b, W / 2, board_y(b.height, LOOK), 1, split)
    captions(c, CHUNKS, t, split)
    return c


def sound(mix):
    mix.add(BOARD_IN, sfx_whoosh(0.35), 0.2)
    for ti in TIMES:
        mix.add(ti, sfx_pop(), 0.35)


if __name__ == "__main__":
    render(NAME, E, draw, sound, bed=bed_soft, bed_gain=0.06)
