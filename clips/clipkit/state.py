"""Mutable per-render state shared between modules (one render per process)."""
QA = None          # render(): {"boxes": [...], "clips": set()} while frames are drawn
PROBE = None       # render(): {key: {"rects": [...], "h": int}} during the dry run that places the hook
LAST_MAP = (0.0, 0.0, 1.0, 0, 0)  # crop(): source px -> canvas px as (x0, y0, scale, paste_x, paste_y)
SHOT_BOUNDS = []   # frames(): output frame indices where the picture changes shot
HOOK_SLOTS = {}    # place_hook(): key -> (y, scale), fixed once per clip
SHOT_INFO = {}    # track_edit(): output frame -> {angle, speaker, mode, wide}
CAPTIONS_AFTER = 0.0  # intro(): captions wait until the headline leaves the caption zone
HOOK_SPEAKER = ""     # render(): who is talking while the headline is up (its name line)
CLIP_SPEAKER = ""     # render(): the name of whoever speaks most in the clip (headline name line, end card)
DOUBT = []             # (t0, t1) output seconds where the person on screen barely moves their mouth (QA note)
MOVES = set()          # (t0, t1) of deliberate camera moves (fx.snap, shake, punch): QA's CROP JUMP skips them
