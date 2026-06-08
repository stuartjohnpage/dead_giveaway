# Transitional stingers (one-shot SFX)

Two short cues layered **over** the background music at view transitions, so the flow
between views reads as deliberate rather than a hard cut. They're played through the SFX
path (`priv/static/sounds/`, like `gunshot.mp3`) — one-shots that ride the *sfx* volume
and never touch the music loops.

```
round_start.mp3   a 3-2-1 riser that resolves into a downbeat hit, on round_start.
                  Doubles as the "countdown" flourish and masks the menu→game music
                  crossfade. (Client-only — there's no server-side round delay.)
win.mp3           a bright major fanfare on the win banner / round_over, just before the
                  music ducks to its between-rounds limbo bed.
```

These are **global** (theme-neutral), not per-theme like the music — they're brief and
sit over both the neon and western beds. If a theme ever wants its own stingers, add an
`audio.stingers` block to its `theme.json` and retarget them in `loadTheme()` the same way
the music loops are (see `music-director.mjs`'s `setTheme`); for now `audio-shell.mjs`
hard-codes the two global files.

Pure-numpy additive synthesis, same house style as `gen_music.py` (ADSR envelopes,
oscillators, a one-pole lowpass). One-shots, so there's no loop seam to protect — each cue
just opens and closes at silence so it can't click.

## Regenerating

```bash
python tools/asset-gen/gen_stingers.py out/        # writes round_start.wav, win.wav
ffmpeg -y -i out/round_start.wav -b:a 160k priv/static/sounds/round_start.mp3
ffmpeg -y -i out/win.wav         -b:a 160k priv/static/sounds/win.mp3
```

Knobs in `gen_stingers.py`: the blip notes/timing and the resolving chord in
`round_start()`, and the arpeggio + sustained chord in `win()`. `FADE_MS` / `DUCK_LEVEL`
in `assets/js/music.mjs` control how the *music* fades around these cues (the crossfade
length and the between-rounds duck depth), not the stingers themselves.

## How they're wired

- `assets/js/audio-shell.mjs` preloads each as an `Audio` one-shot (`playRoundStart`,
  `playWin`) and `cloneNode`s per play so overlaps sound.
- `assets/js/game.mjs` fires `playRoundStart()` in the `round_start` handler and
  `playWin()` in `round_over`, alongside the music director's `toRound()` / `toCard()`.
