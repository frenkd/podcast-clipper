"""$title: breaking news ($style style, made with `./clip quick`): a red BREAKING banner with the headline, a
LIVE tag, a ticker of (made-up, clearly joking) news lines, and a news sting. It's a normal clip script: edit the
settings below or anything else, then `./clip render $episode $num`."""
from clipkit import *

NAME = "$name"
# source seconds; tight() trims long pauses
E = Edit(tight(($start, $end)))
# the banner's headline
HEADLINE = $headline
# the ticker: short made-up lines (say so in the post: they're jokes, not news)
TICKER = $ticker
BANNER_Y = int(H * 0.56)
CHUNKS = chunk_words(E.words(), 4, 22)


def draw(t, fr, face):
    c = Image.fromarray(crop(fr, face, W, H, zoom=1.05)).convert("RGBA")
    if t >= E.dur:
        end_card(t - E.dur, c)
        return c
    news_banner(c, HEADLINE or "", t, 0.25, y=BANNER_Y)
    ticker(c, TICKER, t, y=BANNER_Y + 196)
    live = text_line("●  LIVE", F_BLACK, 34, (255, 255, 255))
    place(c, on_panel(live, pad=12), 60, SAFE_TOP + 30, 1, ease_out((t - 0.2) / 0.3), anchor="tl")
    captions(c, CHUNKS, t, style="clean")
    return c


def sound(mix):
    mix.add(0.0, sfx_news(), 0.45)


if __name__ == "__main__":
    render(NAME, E, draw, sound, bed=bed_drone, bed_gain=0.07)
