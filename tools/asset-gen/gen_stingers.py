#!/usr/bin/env python3
"""
Dead Giveaway - transitional stingers (one-shot SFX, not loops).

Two short cues layered OVER the background music at view transitions, played
through the SFX path (priv/static/sounds/, like gunshot.mp3) so they ride the
sfx volume and don't touch the music loops:

  round_start.mp3  a 3-2-1 riser that resolves into a downbeat hit, played as a
                   round opens (folds the "countdown" and "round-start" cues into
                   one so two sounds never collide at the same instant).
  win.mp3          a bright major fanfare on the win banner / round_over.

Pure-numpy additive synthesis, same house style as gen_music.py. These are
one-shots, so there's no seam to protect — every cue just starts and ends at
silence so it can't click.

Usage:  python gen_stingers.py [out_dir]   # writes round_start.wav, win.wav
        # then encode to mp3 and place under priv/static/sounds/ (see STINGERS.md)
"""
import numpy as np, sys, os, wave

SR = 44100


# ---- note frequencies ------------------------------------------------------
A4 = 440.0
def nf(name):
    names = {'C': -9, 'C#': -8, 'D': -7, 'D#': -6, 'E': -5, 'F': -4, 'F#': -3,
             'G': -2, 'G#': -1, 'A': 0, 'A#': 1, 'B': 2}
    p, octv = name[:-1], int(name[-1])
    return A4 * 2 ** ((names[p] + (octv - 4) * 12) / 12.0)


# ---- envelopes & oscillators (mirrors gen_music.py) ------------------------
def adsr(n, a, d, s, r):
    a, d, r = max(1, int(a * SR)), max(1, int(d * SR)), max(1, int(r * SR))
    s_len = max(0, n - a - d - r)
    if a + d + r > n:
        a = max(1, int(n * 0.1)); d = max(1, int(n * 0.2)); r = max(1, int(n * 0.3))
        s_len = max(0, n - a - d - r)
    env = np.concatenate([
        np.linspace(0, 1, a, endpoint=False),
        np.linspace(1, s, d, endpoint=False),
        np.full(s_len, s),
        np.linspace(s, 0, r),
    ])
    if len(env) < n:
        env = np.pad(env, (0, n - len(env)), constant_values=0)
    return env[:n]


def osc(freq, n, wave='sine'):
    t = np.arange(n) / SR
    ph = freq * t
    if wave == 'sine':   return np.sin(2 * np.pi * ph)
    if wave == 'tri':    return 2 * np.abs(2 * (ph - np.floor(ph + 0.5))) - 1
    if wave == 'square': return np.sign(np.sin(2 * np.pi * ph))
    return 2 * (ph - np.floor(ph + 0.5))  # saw


def lp_fast(x, cutoff):
    """One-pole lowpass as a truncated exponential-kernel convolution."""
    a = np.exp(-2 * np.pi * cutoff / SR); b = 1 - a
    if a <= 0:
        return x.copy()
    K = max(4, min(int(np.ceil(np.log(1e-4) / np.log(a))), 8000))
    h = b * (a ** np.arange(K))
    return np.convolve(x, h)[:len(x)]


def secs(s):
    return int(round(s * SR))


def sweep(f0, f1, n):
    """Sine with an exponential frequency glide f0 -> f1 (the riser 'whoosh')."""
    f = f0 * (f1 / f0) ** (np.arange(n) / n)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph)


def add(buf, sig, at, gain=1.0):
    i = secs(at)
    end = min(len(buf), i + len(sig))
    buf[i:end] += sig[:end - i] * gain


# ---------------------------------------------------------------------------
# round_start: 3-2-1 blips + rising noise/whoosh, resolving on a bright hit
# ---------------------------------------------------------------------------
def round_start():
    total = secs(1.7)
    buf = np.zeros(total)
    rng = np.random.default_rng(11)

    # Three rising blips — the "3..2..1" — bright plucks a major triad apart.
    for k, (tone, at) in enumerate([('C5', 0.0), ('E5', 0.38), ('G5', 0.76)]):
        n = secs(0.2)
        env = adsr(n, 0.004, 0.06, 0.0, 0.12)
        f = nf(tone)
        sig = (osc(f, n, 'tri') + 0.35 * osc(f, n, 'sine') + 0.2 * osc(2 * f, n, 'sine')) * env
        add(buf, sig, at, gain=0.5 + 0.08 * k)  # each a touch louder

    # Rising whoosh under the blips: a sine sweep + airy noise build to the hit.
    rise_n = secs(1.18)
    build = (np.arange(rise_n) / rise_n) ** 2.2          # slow then fast swell
    whoosh = sweep(180, 1900, rise_n) * build * 0.22
    noise = rng.standard_normal(rise_n)
    noise = (noise - lp_fast(noise, 1200)) * build * 0.18  # rising airy hiss
    add(buf, whoosh + noise, 0.0, gain=1.0)

    # The hit at ~1.18s: a bright major stab (the "GO" where the music kicks).
    n = secs(0.5)
    chord = ['C5', 'E5', 'G5', 'C6']
    stab = sum(osc(nf(t), n, 'saw') for t in chord) / len(chord)
    stab = lp_fast(stab, 4200) * adsr(n, 0.003, 0.2, 0.25, 0.3)
    crash = rng.standard_normal(n)
    crash = (crash - lp_fast(crash, 5000)) * np.exp(-np.arange(n) / SR * 9) * 0.5
    add(buf, stab * 0.6 + crash, 1.18, gain=1.0)

    return buf


# ---------------------------------------------------------------------------
# win: a quick major arpeggio resolving into a sustained, shimmering chord
# ---------------------------------------------------------------------------
def win():
    total = secs(1.8)
    buf = np.zeros(total)

    # Bright arpeggio up: C - E - G - C, plucky.
    for tone, at in [('C5', 0.0), ('E5', 0.11), ('G5', 0.22), ('C6', 0.33)]:
        n = secs(0.5)
        f = nf(tone)
        env = adsr(n, 0.004, 0.1, 0.3, 0.35)
        sig = (osc(f, n, 'tri') + 0.4 * osc(f, n, 'sine') + 0.18 * osc(2 * f, n, 'sine')) * env
        add(buf, lp_fast(sig, 5000), at, gain=0.34)

    # Sustained major chord from the top of the arpeggio — slow attack, long tail,
    # detuned saws for shimmer plus a low root for body.
    n = secs(1.4)
    env = adsr(n, 0.06, 0.3, 0.7, 0.7)
    pad = np.zeros(n)
    for tone in ['C4', 'E4', 'G4', 'C5', 'E5']:
        f = nf(tone)
        pad += osc(f * 2 ** (-6 / 1200), n, 'saw') + osc(f * 2 ** (+6 / 1200), n, 'saw')
    pad = lp_fast(pad / 10.0, 3200) * env
    root = osc(nf('C3'), n, 'sine') * adsr(n, 0.02, 0.2, 0.6, 0.6) * 0.4
    add(buf, pad * 0.7 + root, 0.36, gain=1.0)

    return buf


# ---------------------------------------------------------------------------
def master(mono):
    """Soft-limit, give it a hair of stereo width, normalize to ~-1 dBFS."""
    mono = lp_fast(mono, 14000)                 # tame harshness
    mono = np.tanh(mono * 1.2)
    # subtle width: tiny Haas-ish offset between channels
    d = secs(0.008)
    left = mono
    right = np.concatenate([np.zeros(d), mono])[:len(mono)]
    st = np.stack([left, 0.85 * left + 0.15 * right], axis=1)
    st = st / (np.max(np.abs(st)) + 1e-9) * 0.89
    return st


def write_wav(path, stereo):
    out = (stereo * 32767).astype(np.int16)
    with wave.open(path, 'w') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(out.tobytes())
    print(f"wrote {path}  dur={len(stereo) / SR:.2f}s  peak={np.max(np.abs(stereo)):.3f}")


if __name__ == "__main__":
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out_dir, exist_ok=True)
    write_wav(os.path.join(out_dir, "round_start.wav"), master(round_start()))
    write_wav(os.path.join(out_dir, "win.wav"), master(win()))
