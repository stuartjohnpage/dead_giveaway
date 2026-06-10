#!/usr/bin/env python3
"""Per-theme Red Light wind-up cue (#53). Pure-numpy synthesis, same pipeline as
gen_gunshot.py: render 16-bit stereo WAV, encode to mp3 with ffmpeg, no samples.

The cue is the watcher's spin made audible — it plays once at the green→wind-up
transition (audio-shell.mjs playWindup), so it's sized to the wind-up itself
(~0.8s = World's 16 ticks) and must end decayed: red arrives right behind it.
Each is a RISING gesture (a warning, not an impact), matched to the pack's fiction:

  neon    — arcade alarm: a square sweep climbing through accelerating gate pulses
  western — rattlesnake: an accelerating noise rattle, capped by the hammer cocking
  station — servo slew: a motor whine spinning up, capped by two alert beeps

Usage: python tools/asset-gen/gen_windup.py [repo_root]
Writes priv/static/themes/<key>/windup.mp3 and patches each theme.json (audio.windup).
"""
import json, os, subprocess, sys, wave

import numpy as np

SR = 44100
DUR = 0.8
rng = np.random.default_rng(53)


def env_exp(n, tau):
    return np.exp(-np.arange(n) / (tau * SR))


def lowpass(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR)
    b = 1 - a
    if a <= 0:
        return x.copy()
    K = max(4, min(int(np.ceil(np.log(1e-4) / np.log(a))), 8000))
    h = b * (a ** np.arange(K))
    return np.convolve(x, h)[: len(x)]


def sweep(f0, f1, n, shape="sine"):
    f = f0 * (f1 / f0) ** (np.arange(n) / n)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sign(np.sin(ph)) if shape == "square" else np.sin(ph)


def accel_gate(n, hz0, hz1, duty=0.55):
    """An on/off gate whose rate accelerates hz0 -> hz1 over n samples — the
    'winding up' figure all three cues share."""
    rate = hz0 * (hz1 / hz0) ** (np.arange(n) / n)
    ph = np.cumsum(rate) / SR
    return ((ph % 1.0) < duty).astype(float)


def neon_windup():
    n = int(DUR * SR)
    tone = 0.7 * sweep(330, 990, n, "square") + 0.3 * sweep(662, 1985, n)
    x = tone * accel_gate(n, 6, 22) * np.linspace(0.5, 1.0, n)
    x = np.round(x * 31) / 31                                  # the pack's arcade grit
    x[-int(0.06 * SR):] *= env_exp(int(0.06 * SR), 0.015)      # clipped off as red lands
    return lowpass(x, 7000)


def western_windup():
    n = int(DUR * SR)
    rattle = lowpass(rng.standard_normal(n), 5200) * accel_gate(n, 11, 38, duty=0.4)
    x = rattle * np.linspace(0.4, 1.0, n) ** 1.5
    # the hammer cocks at the top: two dry mechanical clicks
    for at, gain in ((0.68, 0.9), (0.74, 1.2)):
        i = int(at * SR)
        click = rng.standard_normal(int(0.012 * SR)) * env_exp(int(0.012 * SR), 0.003)
        x[i : i + len(click)] += gain * click
    return x


def station_windup():
    n = int(DUR * SR)
    whine = sweep(70, 540, n) * 0.6 + 0.4 * sweep(140, 1080, n)
    flutter = 1.0 + 0.18 * np.sign(np.sin(2 * np.pi * 27 * np.arange(n) / SR))
    x = lowpass(whine * flutter, 2400) * np.linspace(0.45, 1.0, n)
    # two alert beeps as the lens locks on (the second clipped by the buffer's end,
    # exactly as red clips the spin)
    for at, f in ((0.62, 880), (0.74, 1175)):
        i = int(at * SR)
        bn = min(int(0.07 * SR), n - i)
        beep = np.sin(2 * np.pi * f * np.arange(bn) / SR) * env_exp(bn, 0.03)
        x[i : i + bn] += 0.8 * beep
    return x


THEMES = {"neon": neon_windup, "western": western_windup, "station": station_windup}


def write(x, path):
    x = x / np.max(np.abs(x)) * 0.9
    fade = int(0.02 * SR)
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


def patch_manifest(base):
    """Point the pack's theme.json at the cue (gen_pack.py emits the key itself for
    packs generated after #53; this covers the already-shipped ones)."""
    path = os.path.join(base, "theme.json")
    if not os.path.exists(path):
        return
    with open(path) as f:
        manifest = json.load(f)
    manifest.setdefault("audio", {})["windup"] = "windup.mp3"
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    for key, build in THEMES.items():
        x = build()
        base = os.path.join(root, "priv", "static", "themes", key)
        out = os.path.join(base, "windup.mp3")
        write(x, out)
        patch_manifest(base)
        print(f"{key}: windup.mp3 {len(x)/SR:.2f}s -> {out}")


if __name__ == "__main__":
    main()
