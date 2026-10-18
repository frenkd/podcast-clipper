"""The automatic checks every render runs, frame by frame, and the <name>.qa.txt they produce. A safety net, not the
judge: issues are almost always real; notes (UNDER APP UI, TIGHT) are worth a look at the stills, then your call.

  COVERS FACE   something over the face of the person on screen
  OVERLAP       two elements on top of each other (place(..., over=True) marks deliberate layering)
  AT EDGE       something in the thin band round the screen edge (red in zones.jpg): always wrong
  UNDER APP UI  something where Instagram / X / LinkedIn draw their own UI (orange in zones.jpg): a note
  TIGHT         content closer than MARGIN to its card's edge (recorded by place())
  CLIPPED       content drawn past its card's edge (recorded by place())
  CROP JUMP     the framing moved abruptly inside a shot
  FROZEN        the same picture for more than FROZEN_MAX while the voice runs
"""
import math
import os

from . import state
from .draw import MARGIN
from .project import FPS, STEP
from .safezones import at_edge, unsafe
from .video import face_rect

FROZEN_MAX = 1.3  # seconds a held source frame (or an unchanged picture) may last


def start():
    """begin collecting: place() records into state.QA while frames are drawn"""
    state.QA = {"boxes": [], "items": [], "clips": set(), "tight": set()}
    return Checker()


class Checker:
    def __init__(self):
        self.covered, self.overlaps, self.under_ui, self.edge, self.jumps, self.frozen = [], [], [], [], [], []
        self._prev_map = self._prev_src = self._prev_out = None
        self._same_src = self._same_out = 0

    def before_draw(self, t, fr):
        """call before drawing frame t (fr: the source frame the engine handed over)"""
        state.QA["boxes"], state.QA["items"] = [], []
        self._same_src = self._same_src + 1 if fr is self._prev_src else 0  # the engine holding one source frame
        self._prev_src = fr
        if self._same_src * STEP > FROZEN_MAX * FPS:
            self.frozen.append(t)

    def after_draw(self, t, face, out):
        """call with the drawn frame (out: the image that gets written)"""
        items = state.QA["items"]
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                ix = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
                small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
                if ix > 600 and ix > 0.06 * small:
                    self.overlaps.append((t, " × ".join(sorted({a[4], b[4]}))))
        m = state.LAST_MAP
        p = self._prev_map
        if p is not None and abs(m[2] - p[2]) / p[2] < 0.01:
            moved = math.hypot(m[0] - p[0], m[1] - p[1]) * m[2]
            gi = int(round(t * FPS))
            if moved > 25 * STEP and not any(abs(gi - b) <= STEP for b in state.SHOT_BOUNDS):
                self.jumps.append(t)
        self._prev_map = m
        fx0, fy0, fx1, fy1 = face_rect(face)
        mx, my = (fx1 - fx0) * 0.12, (fy1 - fy0) * 0.12  # a little tolerance at the edges of the head box
        for x0, y0, x1, y1, who, ui_frac in state.QA["boxes"]:
            if x0 < fx1 - mx and x1 > fx0 + mx and y0 < fy1 - my and y1 > fy0 + my:
                self.covered.append((t, who))
            if at_edge((x0, y0, x1, y1)):
                self.edge.append((t, who))
            hits = unsafe((x0, y0, x1, y1), frac=ui_frac)
            if hits:
                self.under_ui.append((t, f"{who} [{', '.join(hits)}]"))
        sig = out.convert("L").resize((27, 48)).tobytes()  # an unchanged picture is frozen, whatever the cause
        self._same_out = self._same_out + 1 if sig == self._prev_out else 0
        self._prev_out = sig
        if self._same_out * STEP > FROZEN_MAX * FPS:
            self.frozen.append(t)

    def report(self, path):
        """stop collecting, write the QA file, return 'OK', 'notes: …' (only notes) or a short summary of issues"""
        clipped, tight = sorted(state.QA["clips"]), sorted(state.QA["tight"] - state.QA["clips"])
        state.QA = None
        issues, notes = [], []
        for label, events, min_len, out in (("COVERS FACE ", self.covered, 0.1, issues),
                                            ("OVERLAP     ", self.overlaps, 0.25, issues),
                                            ("AT EDGE     ", self.edge, 0.15, issues),
                                            ("UNDER APP UI", self.under_ui, 0.25, notes)):
            by = {}
            for t, who in events:
                by.setdefault(who, []).append(t)
            for who, ts in by.items():
                r = _ranges(ts, min_len=min_len)
                if r:
                    out.append(f"{label} {who}: " + ", ".join(f"{x:.1f}–{y:.1f}s" for x, y in r))
        if self.frozen:
            issues.append("FROZEN       " + ", ".join(f"{x:.1f}–{y:.1f}s" for x, y in _ranges(self.frozen, 0.2, 0)) +
                          f" (the picture stood still > {FROZEN_MAX}s under the voice: show the shot instead)")
        if self.jumps:
            issues.append("CROP JUMP    at " + ", ".join(f"{x:.2f}s" for x in self.jumps[:12]) +
                          " (framing moved abruptly inside a shot)")
        issues += [f"CLIPPED      {who}: drawn past the edge of its card (text or icon cut off)" for who in clipped]
        notes += [f"TIGHT        {who}: closer than {MARGIN}px to its card's edge (give it room: PAD/GAP)" for who in tight]
        lines = issues + [f"note: {n}" for n in notes]
        with open(path, "w") as fh:
            fh.write("\n".join(lines) + "\n" if lines else "OK\n")
        if not lines:
            return "OK"
        if not issues:
            return "notes: " + "\n    ".join(notes)
        return f"{len(issues)} issue(s), see {os.path.basename(path)}\n    " + "\n    ".join(lines)


def _ranges(ts, gap=0.1, min_len=0.1):
    """sorted times -> [(start, end)] runs; runs shorter than min_len are dropped (a frame of pop-in overshoot)"""
    out, a = [], ts[0]
    for p, q in zip(ts, ts[1:] + [None]):
        if q is None or q - p > gap:
            out.append((a, p))
            a = q
    return [(x, y) for x, y in out if y - x >= min_len]
