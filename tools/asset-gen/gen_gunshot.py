#!/usr/bin/env python3
"""Per-theme gunshot SFX (#48). Pure-numpy synthesis, same pipeline as the music
generators: render 16-bit stereo WAV, encode to mp3 with ffmpeg, no external samples.

One shot per theme, each matched to the pack's fiction:
  neon    — arcade zapper: square-wave pitch dive + click + sub thump, lightly bit-crushed
  western — revolver report: noise crack + powder boom + low thump + street slapback
  station — energy blaster: inharmonic ring-modded dive + metallic attack + hull echo

All are short one-shots (≈0.4–0.7s) with instant attack — the client overlaps clones per
shot (audio-shell.mjs playShot), so tails must decay to silence on their own.

Usage: python tools/asset-gen/gen_gunshot.py [repo_root]
Writes priv/static/themes/<key>/shot.mp3.
"""
import os, subprocess, sys, wave

import numpy as np

SR = 44100
rng = np.random.default_rng(48)


def env_exp(n, tau):
    """Exponential decay envelope over n samples with time constant tau (seconds)."""
    return np.exp(-np.arange(n) / (tau * SR))


def lowpass(x, cutoff):
    """One-pole lowpass as a truncated exponential-kernel convolution (vectorized) —
    the same warm filter the music generators use."""
    a = np.exp(-2 * np.pi * cutoff / SR)
    b = 1 - a
    if a <= 0:
        return x.copy()
    K = max(4, min(int(np.ceil(np.log(1e-4) / np.log(a))), 8000))
    h = b * (a ** np.arange(K))
    return np.convolve(x, h)[: len(x)]


def sweep(f0, f1, n, shape="sine"):
    """Oscillator whose pitch glides exponentially f0 -> f1 over n samples."""
    f = f0 * (f1 / f0) ** (np.arange(n) / n)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sign(np.sin(ph)) if shape == "square" else np.sin(ph)


def echo(x, delay_s, gain, cutoff=2500):
    """One muffled repeat — a slapback off the street front / hull."""
    d = int(delay_s * SR)
    out = np.zeros(len(x) + d)
    out[: len(x)] += x
    out[d:] += gain * lowpass(x, cutoff)
    return out


def neon_shot():
    n = int(0.32 * SR)
    zap = sweep(1500, 170, n, "square") * env_exp(n, 0.07)
    zap += 0.4 * sweep(2230, 250, n) * env_exp(n, 0.045)        # detuned shimmer layer
    click = rng.standard_normal(int(0.008 * SR)) * 0.8
    sub = np.sin(2 * np.pi * 88 * np.arange(int(0.18 * SR)) / SR) * env_exp(int(0.18 * SR), 0.05)
    x = np.zeros(int(0.42 * SR))
    x[: len(click)] += click
    x[: n] += 0.8 * zap
    x[: len(sub)] += 0.55 * sub
    x = np.round(x * 31) / 31                                   # gentle bit-crush, arcade grit
    return lowpass(x, 9000)


def western_shot():
    crack_n = int(0.05 * SR)
    crack = rng.standard_normal(crack_n) * env_exp(crack_n, 0.011)
    crack += 0.6 * np.diff(crack, prepend=0.0)                  # high-frequency snap on top
    boom_n = int(0.34 * SR)
    boom = lowpass(rng.standard_normal(boom_n), 750) * env_exp(boom_n, 0.075) * 3.0
    thump_n = int(0.15 * SR)
    thump = sweep(210, 65, thump_n) * env_exp(thump_n, 0.05)
    x = np.zeros(int(0.45 * SR))
    x[: crack_n] += 1.1 * crack
    x[: boom_n] += boom
    x[: thump_n] += 0.9 * thump
    return echo(x, 0.105, 0.22, 1800)                            # slapback off the storefronts


def station_shot():
    n = int(0.4 * SR)
    f = 950 * (140 / 950) ** (np.arange(n) / n)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.sin(1.83 * ph)                        # ring-mod: inharmonic, metallic
    body *= env_exp(n, 0.09)
    atk_n = int(0.03 * SR)
    atk = rng.standard_normal(atk_n)
    atk = (atk + np.roll(atk, int(0.0012 * SR))) * env_exp(atk_n, 0.008)  # comb = clang
    hum_n = int(0.3 * SR)
    hum = np.sin(2 * np.pi * 118 * np.arange(hum_n) / SR) * env_exp(hum_n, 0.1)
    x = np.zeros(int(0.5 * SR))
    x[: atk_n] += 0.9 * atk
    x[: n] += body
    x[: hum_n] += 0.3 * hum
    return echo(x, 0.13, 0.25, 1200)                             # hollow repeat down the hull


THEMES = {"neon": neon_shot, "western": western_shot, "station": station_shot}


def write(x, path):
    x = x / np.max(np.abs(x)) * 0.92
    fade = int(0.02 * SR)                                        # tail fade only: attack stays instant
    x[-fade:] *= np.linspace(1, 0, fade)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    stereo = np.repeat(pcm[:, None], 2, axis=1)
    tmp = path + ".tmp.wav"
    with wave.open(tmp, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-codec:a", "libmp3lame", "-q:a", "4", path],
        check=True,
    )
    os.remove(tmp)


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    for key, build in THEMES.items():
        x = build()
        out = os.path.join(root, "priv", "static", "themes", key, "shot.mp3")
        write(x, out)
        print(f"{key}: shot.mp3 {len(x)/SR:.2f}s -> {out}")


if __name__ == "__main__":
    main()
