# Western pack — "Dead Man's Gulch"

Sun-baked frontier showdown. Same structure as the neon pack, plus a themed bullet and music.

Everything for this theme lives in **this one folder** (`priv/static/themes/western/`),
served at `/themes/western/`. To add a future theme, drop a sibling folder with the same
shape and register its key in `DeadGiveaway.Themes`.

Assets in this folder:
- `agents.png` / `agents.json` — 12 cowboy-hatted variants × {idle, walk, run, dropped}
- `floor_tile.png`, `finish_line.png`, `arena_bg.png`, `menu_bg.png`, `lobby_bg.png`
- `bullet.png` / `bullet_flat.png` — brass cartridge for the ammo counter (flat = no glow)
- `menu_loop.mp3` — menu/lobby loop (fingerpicked guitar + lonesome whistle, ~22s, 88 BPM)
- `game/stage1..4.mp3` — in-round escalating stages. **Not generated yet** — the western
  counterpart to neon's `game/stage*.mp3`. Same 4-stage / 15s / 128 BPM crossfade contract,
  RMS-matched so switching themes doesn't change perceived volume. Until these exist the
  client falls back to neon's stages (see `theme.json` note + `assets/js/game.mjs`).
- `theme.json` — manifest: palette + the `assets` / `audio` / `ui` paths the client loads.

The theme-switch rewire is **done**: `theme.json` declares this pack's art, audio, and
bullet, and the lobby's theme picker swaps all of it live for everyone in the room. When
the in-round stages are generated, add them under `game/` here and list them in
`theme.json`:

```json
"audio": { "menuLoop": "menu_loop.mp3",
           "gameStages": ["game/stage1.mp3", "game/stage2.mp3",
                          "game/stage3.mp3", "game/stage4.mp3"] }
```

Regenerate (paths relative to this folder):
- Visuals: `python3 ../gen_pack.py . western`
- Bullet: `python3 ../gen_bullet.py . ./ cartridge`
- Menu loop: `python3 ../../sounds/music/western/gen_music_western.py western_loop.wav`,
  encode to mp3, place here as `menu_loop.mp3`.
- Game stages: `python3 ../../sounds/music/western/gen_game_music_western.py out/`,
  encode each to mp3, place under `game/` as `stage1..4.mp3`.
