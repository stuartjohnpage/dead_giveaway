# Western pack — "Dead Man's Gulch"

Sun-baked frontier showdown. Same structure as the neon pack, plus a themed bullet and music.

Assets in this folder:
- `agents.png` / `agents.json` — 12 cowboy-hatted variants × {idle, walk, run, dropped}
- `floor_tile.png`, `finish_line.png`, `arena_bg.png`, `menu_bg.png`, `lobby_bg.png`
- `theme.json` — palette/manifest
- `bullet.png` / `bullet_flat.png` — brass cartridge for the ammo counter (flat = no glow)

Audio for this theme (kept under the sounds tree):
- Menu/lobby loop: `priv/static/sounds/music/western/western_loop.mp3`
  (fingerpicked guitar + lonesome whistle, ~22s seamless loop, 88 BPM)
- In-round escalating stages: NOT YET GENERATED — the western counterpart to
  `sounds/music/game/stage1..4.mp3`. Ask to generate next.

Note for the theme-switch rewire: a theme is more than sprites — it also owns its
**bullet** and its **music**. Consider extending `theme.json` (or a per-theme manifest)
to reference these paths so switching a lobby's theme swaps art + ammo icon + soundtrack
together:

```json
"audio": { "menuLoop": "/sounds/music/western/western_loop.mp3",
           "gameStages": ["/sounds/music/western/game/stage1.mp3", "..."] },
"ui":    { "bullet": "/images/themes/western/bullet.png" }
```

Regenerate: `python3 ../gen_pack.py . western` (visuals),
`python3 ../gen_bullet.py . ./ cartridge` (bullet),
`python3 ../../../sounds/music/western/gen_music_western.py western_loop.wav` (music).
