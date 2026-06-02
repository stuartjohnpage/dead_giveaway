# Background music

> **Note:** the *shipped* loops now live with their theme packs under
> `priv/static/themes/<key>/` (`menu_loop.mp3` and `game/stage1..4.mp3`), so switching a
> lobby's theme swaps its music too. This directory keeps the music *generators* and
> stems/demos — generate here, then place the encoded mp3s in the theme folder.

`neon_loop` — chill / hypnotic synthwave, matched to the Neon Concourse theme.
~46s seamless loop, A minor, 84 BPM. Generated procedurally (`gen_music.py`), free, no
external service. (Shipped as `themes/neon/menu_loop.mp3`.)

File: `neon_loop.mp3` (kept as the single, widely-supported format for an HTML5
`<audio>` element). Regenerate an `.ogg` from the steps below if you want the gapless
WebAudio path.

## Looping it gaplessly (important)

The source loop is sample-accurate (verified: seam step is well below the in-track
sample step). But **MP3 adds encoder padding** at the start/end, so `<audio loop>` with
the MP3 will have a tiny gap. Two ways to avoid it:

1. **WebAudio (truly gapless, recommended).** Decoded PCM has no padding, and
   `AudioBufferSourceNode.loop` is sample-accurate:

   ```js
   const ctx = new AudioContext();
   const res = await fetch("/sounds/music/neon_loop.ogg");
   const buf = await ctx.decodeAudioData(await res.arrayBuffer());
   const src = ctx.createBufferSource();
   src.buffer = buf; src.loop = true;
   const gain = ctx.createGain(); gain.gain.value = 0.5;   // bg level
   src.connect(gain).connect(ctx.destination);
   src.start();                 // call after a user gesture (autoplay policy)
   ```

2. **HTML5 `<audio loop>`** — fine if a ~tens-of-ms gap is acceptable; prefer the
   `.ogg`, whose padding is smaller than MP3's.

Mix level: the track sits at ~-13 dBFS RMS. Drop game music to roughly 0.4–0.5 gain so
SFX (the bullet, footsteps) cut through.

## Regenerating / tuning

```bash
python3 priv/static/sounds/music/gen_music.py neon_loop.wav
# then re-encode:
ffmpeg -y -i neon_loop.wav -c:a libvorbis -qscale:a 5 neon_loop.ogg
ffmpeg -y -i neon_loop.wav -c:a libmp3lame -b:a 160k neon_loop.mp3
```

Knobs in `gen_music.py`: `BPM`, `BARS`, the `PROG` chord progression, and per-voice
gains. A future theme = new progression + palette-matched mood (e.g. darker, sparser for
a tense theme). Seamlessness is structural (all voices and the ping-pong delay write with
modulo-wrapped indices), so changing content keeps the loop clean.
