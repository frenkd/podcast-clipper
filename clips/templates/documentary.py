"""$title: the nature-documentary treatment ($style style, made with `./clip quick`): letterbox bars, a warm grade,
a typed caption card the way a documentary introduces its subject, and a calm drone under the voice. It's a normal
clip script: edit the settings below or anything else, then `./clip render $episode $num`."""
from clipkit import *

NAME = "$name"
# source seconds; tight() trims long pauses
E = Edit(tight(($start, $end)))
# the documentary card: a small label and the narrator's line, typed out
DOC_LABEL = $doc_label
DOC_LINE = $doc_line
# when the card types in, and how long it stays
DOC_T = 0.6
DOC_FOR = 5.0
CHUNKS = chunk_words(E.words(), 4, 22)


def draw(t, fr, face):
    zoom = push(min(t, E.dur), 0, E.dur, 1.04, 1.1)
    c = Image.fromarray(crop(fr, face, W, H, zoom=zoom)).convert("RGBA")
    c = faded(c, 0.35, seed=int(t * 12))  # warm, a little film grain
    letterbox(c, ease_out(t / 0.6), 170)
    if t >= E.dur:
        end_card(t - E.dur, c)
        return c
    if DOC_T <= t < DOC_T + DOC_FOR:
        k = (t - DOC_T) / 1.4
        card = doc_card(typed(DOC_LABEL, k * 2), typed(DOC_LINE, k - 0.25))
        full = doc_card(DOC_LABEL, DOC_LINE)  # placed by its full size, so it doesn't move while it types
        place(c, card, 70, CAPTION_TOP - full.height - 40, 1, 1 - clamp01((t - DOC_T - DOC_FOR + 0.4) / 0.4),
              anchor="tl")
    captions(c, CHUNKS, t, style="clean")
    return c


def sound(mix):
    for k in range(0, len(DOC_LINE), 3):  # a soft typewriter while the card types in
        mix.add(DOC_T + 0.35 + k / len(DOC_LINE) * 1.4, sfx_type(k), 0.12)


if __name__ == "__main__":
    render(NAME, E, draw, sound, bed=bed_drone, bed_gain=0.1)
