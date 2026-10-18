"""clipkit: everything a clip script needs. `from clipkit import *`, then write draw()/sound() and call render().

  project  the episode (CLIP_PROJECT), output size, the theme's colours and fonts, PREVIEW mode
  theme    your show's look: theme.json (accent colour, fonts, logo, end card)
  words    Edit / tight() (cut a moment from word timings), captions chunking
  video    face-tracked crop that follows camera cuts, glitch()
  draw     text, emoji, cards, easing, place() (also feeds the automatic QA)
  angles   the episode's camera angles and who sits where (work/angles.json, checked once via work/angles.jpg)
  style    the look as parts: tokens (U, PAD, GAP, fonts) and prefabs (bar, tag, label, chip, panel, mark,
           stamp, gradient, fade_in, vstack/hstack)
  brand    intro() headline, cap() (captions), end_card()
  audio    Mix, synthesized sfx_* and bed_*
  fx       motion and effects for louder clips: punch/push/shake, mono, deep_fry, flash, meme_text, sticker
  render   render(): encode + cover + <name>.qa.txt / .events.jpg / .grid.jpg (preview/ or final/)
"""
import functools, math, re
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .project import (PROJECT, PROJECT_DIR, PREVIEW, FPS, W, H, SW, SH, ACCENT, ON_ACCENT, TEXT, THEME, INK, EPISODE, GUEST, GUESTS, HOST, LANG,
                      F_BLACK, F_XBOLD, F_BOLD, F_MED, F_SF, F_MENLO, F_COURIER, F_TIMES)
from .words import Edit, tight, all_words, chunk_words, clean_word, active
from .video import BAND, crop, frame_canvas, frame_window, face_out, face_rect, glitch, shot_info
from .draw import (clamp01, ease_out, ease_in_out, back_out, pop, font, emoji, text_line, text_block, with_shadow,
                   rounded, boxed, asset, place)
from .brand import (brand_hook, place_hook, intro, cap, captions, accent, beside_face, caption_y, end_card, board_y,
                    SAFE_TOP, CAPTION_TOP, CAPTION_Y, CAPTION_W, BOARD_TOP, BOARD_BOTTOM)
from .safezones import safe_box, safe_width, unsafe
from .project import F_MONO, F_MONO_B, F_MONO_XB, F_REG
from .style import (WHITE, PAPER, GREY, LINE, MUTED, U, PAD, GAP, MARGIN, R, bar, fade_in, tag, label, chip, panel,
                    stamp, mark, gradient, fade, radial, grain, vstack, hstack, on_panel)
from .audio import (Mix, seconds, sfx_pop, sfx_click, sfx_tick, sfx_whoosh, sfx_boom, sfx_ding, sfx_correct, sfx_wrong,
                    sfx_bleep, sfx_glitch, sfx_type, sfx_typewriter, sfx_stamp, sfx_riser, sfx_cash, sfx_record_scratch,
                    sfx_outro, sfx_impact, bed_drone, bed_beat, bed_phonk, bed_soft, bed_credits)
from .fx import (punch, push, shake, mono, deep_fry, vignette, flash, letterbox, meme_text, sticker, wobble,
                 slam, faded, credits_card, red_vignette, snap)
from .render import render
