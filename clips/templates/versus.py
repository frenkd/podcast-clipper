"""$title: versus ($style style, made with `./clip quick`): two sides as crowds of plain figures that fill in as each
is mentioned, and on the punchline one beat of black and white with a slow push-in. It's a normal clip script: edit
the settings below (the names, the counts, the words they appear on) or anything else, then `./clip render $episode
$num`."""
from clipkit import *

NAME = "$name"
# source seconds; tight() trims long pauses
E = Edit(tight(($start, $end)))
# the opening line (None: no headline)
HEADLINE = $headline
# the two sides: a name, how many figures, the word each one fills in on
LEFT, LEFT_N, LEFT_WORD = $left, $nl, $left_word
RIGHT, RIGHT_N, RIGHT_WORD = $right, $nr, $right_word
# the punchline beat: black and white for a moment, on this word
PUNCH_WORD = $punch_word
LEFT_T = when_said(E, LEFT_WORD, 0.5, 1.0)
RIGHT_T = when_said(E, RIGHT_WORD, LEFT_T + 0.5, LEFT_T + 2.5)
PUNCH_T = when_said(E, PUNCH_WORD, RIGHT_T + 0.5, None)
BOARD_IN, BOARD_OUT = LEFT_T - 0.35, E.dur - 0.2
CHUNKS = chunk_words(E.words(), 3, 18)
# the board sits over the video, off the face: under the chin if there's room, else above the head
# ("split": the video eases into a band at the top instead)
LOOK = "overlay"
deliberate(BOARD_IN, BOARD_IN + 0.35)
deliberate(BOARD_OUT, BOARD_OUT + 0.35)


def draw(t, fr, face):
    split = ease_out(clamp01((t - BOARD_IN) / 0.35)) * (1 - ease_out(clamp01((t - BOARD_OUT) / 0.35)))
    zoom = push(t, PUNCH_T, PUNCH_T + 1.6, 1.0, 1.12) if PUNCH_T else 1.0
    c = frame_canvas(fr, face, split, zoom=zoom, layout=LOOK)
    if PUNCH_T and PUNCH_T <= t < PUNCH_T + 1.8:  # the one beat
        c = mono(c, ease_out((t - PUNCH_T) / 0.2) * (1 - clamp01((t - PUNCH_T - 1.5) / 0.3)))
    if t >= E.dur:
        end_card(t - E.dur, c)
        return c
    if HEADLINE and BOARD_IN > 1.2:
        intro(c, HEADLINE, face, t, until=min(2.6, BOARD_IN - 0.3))
    if split > 0:
        b = versus_board(LEFT, RIGHT, LEFT_N, RIGHT_N, (t - LEFT_T) / 1.0, (t - RIGHT_T) / 1.0)
        if LOOK == "overlay":
            place_board(c, b, face, clamp01((split - 0.6) / 0.4))  # once the shot has made room
        else:
            place(c, b, W / 2, board_y(b.height, LOOK), 1, split)
    captions(c, CHUNKS, t, split)
    return c


def sound(mix):
    mix.add(LEFT_T, sfx_pop(), 0.35)
    mix.add(RIGHT_T, sfx_pop(), 0.35)
    if PUNCH_T:
        mix.add(PUNCH_T, sfx_boom(0.9), 0.4)


if __name__ == "__main__":
    render(NAME, E, draw, sound, bed=bed_soft, bed_gain=0.06)
