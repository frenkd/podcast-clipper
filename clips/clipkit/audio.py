"""Audio: the edit's voice track, a mixer that ducks the bed under speech, and synthesized SFX / beds
(numpy only, so there is never any copyrighted audio in a clip)."""
import os
import numpy as np

from .project import SR, VIDEO, run


def seconds(d):
    """time axis of d seconds at the sample rate"""
    return np.arange(int(d * SR)) / SR


def edit_audio(edit, xfade=0.012):
    """the edit's source audio, pieces butted together with tiny fades"""
    n = int(round(edit.dur * SR))
    out = np.zeros((n, 2), np.float32)
    f = int(xfade * SR)
    ramp = np.linspace(0, 1, f, dtype=np.float32)[:, None]
    for (a, b), o in zip(edit.pieces, edit.offsets):
        raw = run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", VIDEO, "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"])
        x = np.frombuffer(raw, np.float32).reshape(-1, 2).copy()
        x[:f] *= ramp
        x[-f:] *= ramp[::-1]
        i = int(round(o * SR))
        m = min(len(x), n - i)
        out[i:i + m] += x[:m]
    return out


class Mix:
    """voice + fx + bed. mix.add(t, sound, gain, track="fx"|"voice"|"bed"); mix.mute(t0, t1) silences the voice."""

    def __init__(self, dur, duck=0.35):
        self.n = int(round(dur * SR)) + SR
        self.dur = dur
        self.duck = duck
        self.voice, self.fx, self.bed = (np.zeros((self.n, 2), np.float32) for _ in range(3))

    def add(self, t, snd, gain=1.0, track="fx"):
        buf = getattr(self, track)
        if snd.ndim == 1:
            snd = np.stack([snd, snd], 1)
        i = int(round(t * SR))
        if i < 0:
            snd, i = snd[-i:], 0
        m = min(len(snd), self.n - i)
        if m > 0:
            buf[i:i + m] += snd[:m] * gain

    def mute(self, t0, t1, fade=0.01, track="voice"):
        buf = getattr(self, track)
        i0, i1, f = int(t0 * SR), int(t1 * SR), int(fade * SR)
        env = np.ones(self.n, np.float32)
        env[i0:i1] = 0
        env[max(0, i0 - f):i0] = np.linspace(1, 0, i0 - max(0, i0 - f))
        env[i1:i1 + f] = np.linspace(0, 1, len(env[i1:i1 + f]))
        buf *= env[:, None]

    def write(self, path, voice_gain=1.0, bed_gain=0.2):
        v = np.abs(self.voice).mean(1)
        k, sm = int(0.08 * SR), int(0.25 * SR)
        speech = np.clip(_box(v, k) / 0.02, 0, 1)
        duck = _box(1 - self.duck * speech, sm).astype(np.float32)
        mix = (self.voice * voice_gain + self.fx + self.bed * bed_gain * duck[:, None])[: int(round(self.dur * SR))]
        f = min(len(mix), int(0.25 * SR))  # end on silence: platforms loop the clip, a click at the seam sounds broken
        mix[-f:] *= np.linspace(1, 0, f, dtype=np.float32)[:, None]
        peak = np.abs(mix).max()
        if peak > 0.98:
            mix = np.tanh(mix / peak * 1.2) / np.tanh(1.2) * 0.98
        raw = path + ".f32"
        mix.astype(np.float32).tofile(raw)
        run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", raw, path])
        os.remove(raw)


def _box(x, k):
    """np.convolve(x, np.ones(k) / k, mode="same") as a running sum: O(n) instead of O(n*k)"""
    c = np.concatenate(([0.0], np.cumsum(x, dtype=np.float64)))
    hi = np.arange(len(x)) + (k - 1) // 2 + 1
    return (c[np.minimum(hi, len(x))] - c[np.maximum(hi - k, 0)]) / k


# ---- building blocks
def _env(n, a=0.002, r=0.2):
    t = np.arange(n) / SR
    return (np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / max(r, 1e-4))).astype(np.float32)


def _noise(d, seed=0):
    return np.random.default_rng(seed).standard_normal(int(d * SR)).astype(np.float32)


def _filt(x, lo=None, hi=None):
    """band-limit x (soft 4th-order high/low pass in the frequency domain)"""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    m = np.ones_like(f)
    if lo:
        m *= 1 / (1 + (lo / np.maximum(f, 1)) ** 4)
    if hi:
        m *= 1 / (1 + (f / hi) ** 4)
    return np.fft.irfft(X * m, len(x)).astype(np.float32)


def _sweep(f0, f1, d):
    t = seconds(d)
    return np.sin(2 * np.pi * np.cumsum(f0 * (f1 / f0) ** (t / d)) / SR).astype(np.float32)


def _norm(x, peak=0.9):
    m = np.abs(x).max()
    return (x / m * peak).astype(np.float32) if m > 0 else x


# ---- sound effects
def sfx_pop():
    return _norm(_sweep(900, 260, 0.09) * _env(int(0.09 * SR), 0.001, 0.03), 0.6)


def sfx_click():
    return _norm(_filt(_noise(0.02, 3), 1500, 8000) * _env(int(0.02 * SR), 0.0005, 0.004), 0.5)


def sfx_tick():
    return _norm((np.sin(2 * np.pi * 2400 * seconds(0.05)) * _env(int(0.05 * SR), 0.0005, 0.012)).astype(np.float32), 0.45)


def sfx_whoosh(d=0.45, up=True, seed=1):
    n, t = _noise(d, seed), seconds(d)
    pos = (t / d) if up else 1 - t / d
    out = sum(_filt(n, lo, lo * 2.2) * np.clip(1 - np.abs(pos * 3 - k), 0, 1) for k, lo in enumerate((300, 700, 1600, 3500)))
    return _norm(out * np.sin(np.pi * np.clip(t / d, 0, 1)) ** 2, 0.5)


def sfx_boom(d=1.4):
    t = seconds(d)
    x = np.tanh(np.sin(2 * np.pi * np.cumsum(45 + 110 * np.exp(-t * 9)) / SR) * 3.0) * np.exp(-t * 2.6)
    return _norm((x + _filt(_noise(d, 9), 80, 900) * np.exp(-t * 40) * 0.6).astype(np.float32), 0.95)


def sfx_ding(f0=1318.5, d=1.2):
    t = seconds(d)
    x = sum(a * np.sin(2 * np.pi * f0 * k * t) * np.exp(-t * (3 + k * 1.5)) for k, a in [(1, 1), (2.01, 0.35), (3.02, 0.15), (4.2, 0.08)])
    return _norm((x * np.minimum(1, t / 0.002)).astype(np.float32), 0.55)


def sfx_correct():
    a, b = sfx_ding(1046.5, 0.6), sfx_ding(1568, 1.1)
    out = np.zeros(int(1.3 * SR), np.float32)
    out[: len(a)] += a * 0.8
    i = int(0.11 * SR)
    out[i:i + len(b)] += b[: len(out) - i]
    return _norm(out, 0.6)


def sfx_wrong():
    t = seconds(0.5)
    x = np.sign(np.sin(2 * np.pi * 110 * t)) * 0.5 + np.sign(np.sin(2 * np.pi * 116 * t)) * 0.5
    return _norm(_filt(x.astype(np.float32), None, 2000) * _env(len(t), 0.005, 0.4), 0.45)


def sfx_bleep(d=0.6):
    t = seconds(d)
    return (np.sin(2 * np.pi * 1000 * t) * np.minimum(1, t / 0.005) * np.minimum(1, (d - t) / 0.005) * 0.35).astype(np.float32)


def sfx_glitch(d=0.25, seed=4):
    n, t = _noise(d, seed), seconds(d)
    sq = np.sign(np.sin(2 * np.pi * (80 + 600 * (np.floor(t * 40) % 5)) * t))
    x = np.round((n * 0.5 + sq * 0.6) * (np.floor(t * 60) % 2) * 6) / 6
    return _norm(x.astype(np.float32) * _env(len(t), 0.001, d), 0.45)


def sfx_type(seed=0):
    """one key press"""
    rng = np.random.default_rng(seed)
    n = _filt(_noise(0.05, seed), 1200 + rng.integers(0, 1500), 7000) * _env(int(0.05 * SR), 0.0005, 0.008)
    return _norm(n, 0.25 + rng.random() * 0.1)


def sfx_typewriter(seed=0):
    n = _filt(_noise(0.09, seed), 400, 5000) * _env(int(0.09 * SR), 0.0005, 0.012)
    return _norm(n + np.sin(2 * np.pi * 140 * seconds(0.09)) * _env(int(0.09 * SR), 0.001, 0.02) * 0.5, 0.5)


def sfx_stamp():
    t = seconds(0.6)
    thud = np.sin(2 * np.pi * (60 + 90 * np.exp(-t * 30)) * t) * np.exp(-t * 9)
    return _norm((thud + _filt(_noise(0.6, 5), 200, 3000) * np.exp(-t * 35) * 0.7).astype(np.float32), 0.9)


def sfx_riser(d=1.5):
    t = seconds(d)
    return _norm((_sweep(200, 1800, d) * 0.3 + _filt(_noise(d, 7), 2000, 9000) * 0.5) * (t / d) ** 2, 0.4)


def sfx_cash():
    b, c = sfx_ding(2093, 0.9), sfx_ding(2637, 0.9)
    out = np.zeros(int(1.1 * SR), np.float32)
    clk = _filt(_noise(0.08, 2), 800, 6000) * _env(int(0.08 * SR), 0.0005, 0.015)
    out[: len(clk)] += clk * 0.8
    i = int(0.06 * SR)
    out[i:i + len(b)] += b * 0.7
    out[i + 3000:i + 3000 + len(c)] += c[: len(out) - i - 3000] * 0.6
    return _norm(out, 0.6)


def sfx_record_scratch():
    t = seconds(0.45)
    wob = np.abs(np.sin(2 * np.pi * 3.3 * t))
    x = (np.sin(2 * np.pi * np.cumsum(300 + 900 * wob) / SR) * 0.4 + _filt(_noise(0.45, 11), 500, 4000) * 0.6) * wob
    return _norm(x.astype(np.float32) * _env(len(t), 0.002, 0.3), 0.55)


# ---- music beds (pass e.g. bed=lambda d: bed_beat(d, 96) to render)
def bed_drone(d, seed=0):
    """dark ambient pad with sparse low notes (documentary, suspense)"""
    t = seconds(d)
    x = (np.sin(2 * np.pi * 55 * t) * 0.5 + np.sin(2 * np.pi * 82.4 * t) * 0.3 + np.sin(2 * np.pi * 110.3 * t) * 0.15)
    x *= 0.6 + 0.4 * np.sin(2 * np.pi * 0.11 * t)
    x += _filt(_noise(d, seed), 200, 900) * 0.25 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.07 * t + 1))
    for k, (st, f) in enumerate([(0.5, 220), (4.5, 196), (8.5, 174.6), (12.5, 164.8)] * 6):
        st += (k // 4) * 16
        if st > d:
            break
        tt = t[int(st * SR):] - st
        x[int(st * SR):] += np.sin(2 * np.pi * f * tt) * np.exp(-tt * 1.2) * 0.4
    return _norm((x * np.minimum(1, t / 1.0) * np.minimum(1, (d - t) / 1.0)).astype(np.float32), 0.5)


def bed_beat(d, bpm=96, seed=0, key=55.0):
    """minimal lo-fi loop: kick, snare, hats, sub bass"""
    t = seconds(d)
    out = np.zeros_like(t, dtype=np.float32)
    beat = 60 / bpm
    kick = np.sin(2 * np.pi * np.cumsum(45 + 120 * np.exp(-seconds(0.4) * 30)) / SR) * np.exp(-seconds(0.4) * 7)
    snare = _filt(_noise(0.25, seed + 1), 900, 7000) * _env(int(0.25 * SR), 0.001, 0.06) + \
        np.sin(2 * np.pi * 190 * seconds(0.25)) * _env(int(0.25 * SR), 0.001, 0.05) * 0.5
    hat = _filt(_noise(0.05, seed + 2), 6000, None) * _env(int(0.05 * SR), 0.0005, 0.012)
    prog = [key, key * 1.189, key * 0.891, key]

    def put(s, g, at):
        m = min(len(s), len(out) - at)
        if m > 0:
            out[at:at + m] += s[:m] * g
    for b in range(int(d / beat) + 1):
        i = int(b * beat * SR)
        if b % 4 in (0, 2) or b % 8 == 7:
            put(kick, 0.9, i)
        if b % 4 in (1, 3):
            put(snare, 0.35, i)
        put(hat, 0.12, i)
        put(hat, 0.07, int((b + 0.5) * beat * SR))
        if b % 2 == 0:
            tt = seconds(beat * 2)
            put(np.tanh(np.sin(2 * np.pi * prog[(b // 8) % 4] * tt) * 1.5) * np.minimum(1, tt / 0.01) * np.exp(-tt * 1.2), 0.35, i)
    return _norm(out * np.minimum(1, t / 0.3) * np.minimum(1, (d - t) / 0.8), 0.6)


def bed_phonk(d, bpm=130, seed=0):
    """cowbell melody + distorted 808 (use sparingly: one punchline drop, never a whole clip)"""
    t = seconds(d)
    out = np.zeros_like(t, dtype=np.float32)
    beat = 60 / bpm
    step = beat / 4

    def put(sig, at, g):
        i = int(at * SR)
        m = min(len(sig), len(out) - i)
        if m > 0 and i >= 0:
            out[i:i + m] += sig[:m] * g

    def cowbell(f, dd=0.18):
        tt = seconds(dd)
        x = (np.sign(np.sin(2 * np.pi * f * tt)) + np.sign(np.sin(2 * np.pi * f * 1.48 * tt))) * 0.5
        return _filt(x.astype(np.float32), 500, 4000) * np.exp(-tt * 18)

    def b808(f, dd):
        tt = seconds(dd)
        return np.tanh(np.sin(2 * np.pi * np.cumsum(f * (1 + 1.5 * np.exp(-tt * 40))) / SR) * 3) * np.exp(-tt * 1.5)
    hat = _filt(_noise(0.04, seed + 3), 7000, None) * _env(int(0.04 * SR), 0.0005, 0.01)
    mel = [0, 3, 7, 3, 10, 7, 3, 0, 0, 3, 7, 12, 10, 7, 5, 3]
    for i in range(int(d / step)):
        at = i * step
        if i % 2 == 0:
            put(cowbell(554.0 * 2 ** (mel[(i // 2) % 16] / 12)), at, 0.32)
        put(hat, at, 0.10 if i % 2 else 0.05)
        if i % 16 == 0:
            put(b808(46.25, beat * 3), at, 0.75)
        if i % 16 == 10:
            put(b808(41.2, beat * 1.4), at, 0.6)
        if i % 8 == 4:
            put(_filt(_noise(0.2, i), 1200, 8000) * _env(int(0.2 * SR), 0.001, 0.05), at, 0.35)
    return _norm(out * np.minimum(1, t / 0.05) * np.minimum(1, (d - t) / 0.6), 0.7)


# ---- outro and a soft bed: neutral sounds for any show (render() puts sfx_outro() under the end card unless the
# theme turns it off; no intro jingle: a clip starts straight on the voice)

def _bell(f, d, decay=0.9):
    """a soft bell: a sine with a quieter octave and twelfth, quick attack, long fade"""
    t = seconds(d)
    x = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) + 0.12 * np.sin(2 * np.pi * 3 * f * t)
    return (x * _env(len(t), 0.004, decay)).astype(np.float32)


def sfx_outro():
    """end card: two soft bell notes a fifth apart over a low hum (~1.4 s)"""
    out = np.zeros(int(1.5 * SR), np.float32)
    for at, f, g in ((0.0, 523.25, 0.6), (0.16, 783.99, 0.5)):  # C5, G5
        b = _bell(f, 1.3, 0.55)
        i = int(at * SR)
        out[i:i + len(b)] += g * b[:len(out) - i]
    t = seconds(1.5)
    out += 0.25 * np.sin(2 * np.pi * 130.81 * t).astype(np.float32) * _env(len(t), 0.05, 0.5)
    return _norm(out, 0.7)


def bed_soft(d, bpm=92, seed=0):
    """a quiet, warm bed: a slow two-chord pad and a soft pulse on the beat (sits under speech without fighting it)"""
    t = seconds(d)
    beat = 60 / bpm
    bar_ = 4 * beat
    chords = [(130.81, 164.81, 196.0), (110.0, 138.59, 164.81)]  # C major, A minor
    out = np.zeros(len(t), np.float32)
    for b in range(int(d / bar_) + 1):
        i, n = int(b * bar_ * SR), int(bar_ * SR)
        seg = t[:min(n, len(t) - i)]
        if len(seg) <= 0:
            break
        tone = sum(np.sin(2 * np.pi * f * (seg + b * bar_)) for f in chords[b % 2]) / 3
        env = np.minimum(1, seg / 0.6) * np.minimum(1, (bar_ - seg) / 0.6)
        out[i:i + len(seg)] += 0.5 * (tone * env).astype(np.float32)
    kick = _bell(55.0, 0.25, 0.08)
    for k in range(int(d / beat) + 1):
        i = int(k * beat * SR)
        m = min(len(kick), len(out) - i)
        if m > 0:
            out[i:i + m] += 0.35 * kick[:m]
    out = _filt(out, 60, 2500)
    return _norm(out * np.minimum(1, t / 0.5).astype(np.float32) * np.minimum(1, (d - t) / 0.8).astype(np.float32), 0.6)


# ---- meme formats

def bed_credits(d, bpm=132, seed=0):
    """a bouncy, slightly silly jazz riff for the "directed by" credits ending: a tuba-ish bass hopping root-fifth,
    a woody lead with a few blue notes, brushed snare on 2 and 4 (an original tune, written here)"""
    t = seconds(d)
    out = np.zeros(len(t), np.float32)
    beat = 60 / bpm
    root = [130.81, 110.0, 146.83, 98.0]                              # C, A, D, G: one bar each
    lead = [0, 4, 7, 9, 10, 9, 7, 4, 3, 4, 7, 12, 11, 7, 5, 2]          # semitones over C5, in eighths

    def put(sig, at, g):
        i = int(at * SR)
        m = min(len(sig), len(out) - i)
        if m > 0 and i >= 0:
            out[i:i + m] += sig[:m] * g

    def tuba(f, dd):
        tt = seconds(dd)
        x = sum(np.sin(2 * np.pi * f * k * tt) / k ** 1.4 for k in range(1, 6))
        return (x * np.minimum(1, tt / 0.02) * np.exp(-tt * 5)).astype(np.float32)

    def reed(f, dd):
        tt = seconds(dd)
        x = np.sign(np.sin(2 * np.pi * f * tt)) * 0.5 + np.sin(2 * np.pi * 2 * f * tt) * 0.3
        return _filt((x * np.minimum(1, tt / 0.015) * np.exp(-tt * 7)).astype(np.float32), 300, 3500)
    brush = _filt(_noise(0.12, seed + 5), 2000, 9000) * _env(int(0.12 * SR), 0.004, 0.05)
    for b in range(int(d / beat) + 1):
        at = b * beat
        bar = b // 4
        f = root[bar % 4] / 2
        put(tuba(f * (1.5 if b % 2 else 1.0), beat * 0.9), at, 0.55)
        if b % 2:
            put(brush, at, 0.25)
        for half in (0, 1):  # swung eighths
            n = lead[(b * 2 + half) % 16]
            put(reed(523.25 * 2 ** (n / 12), beat * 0.42), at + half * beat * 0.62, 0.22)
    return _norm(out * np.minimum(1, t / 0.05).astype(np.float32) * np.minimum(1, (d - t) / 0.8).astype(np.float32), 0.7)


def sfx_impact():
    """the dramatic-zoom hit: a deep boom with a metallic ring on top"""
    t = seconds(1.6)
    ring = (np.sin(2 * np.pi * 1760 * t) * 0.18 + np.sin(2 * np.pi * 2637 * t) * 0.1) * np.exp(-t * 6)
    boom = sfx_boom(1.6)
    return _norm(boom[:len(t)] + ring.astype(np.float32), 0.95)
