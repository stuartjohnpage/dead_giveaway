# Sound Credits

Third-party audio assets used in Dead Giveaway, with attribution.
Attribution is not strictly required by every license below, but is recorded here
as a courtesy and so we can verify provenance later.

## gunshot.mp3

- **Source:** Pixabay — [Film Special Effects Gunshot](https://pixabay.com/sound-effects/film-special-effects-gunshot-352466/)
- **Author:** [Universfield](https://pixabay.com/users/universfield-28281460/)
- **License:** [Pixabay Content License](https://pixabay.com/service/license-summary/) — free for commercial and non-commercial use, no attribution required.
- **Notes:** Used as the firing sound for the single-bullet hitscan shot (DESIGN §5).
  Since #48 this is the *fallback*: each theme pack ships its own `shot.mp3` (below),
  and this clip plays only for a pack that doesn't declare one.

## themes/<key>/shot.mp3 (per-theme gunshots, #48)

- **Source:** Generated procedurally in-repo by `tools/asset-gen/gen_gunshot.py`
  (pure-numpy synthesis, encoded with ffmpeg) — no external samples.
- **License:** Original to this project; free to use.
- **Notes:** One firing sound per theme, matched to the pack's fiction: neon's arcade
  zapper, western's revolver report, station's energy blaster.

## themes/neon/menu_loop.mp3 (and other theme music)

- **Source:** Generated procedurally in-repo by the generators in `tools/asset-gen/`
  (`gen_music*.py`, `gen_game_music*.py`) — no external service.
- **License:** Original to this project; free to use.
- **Notes:** Each theme owns its music under `priv/static/themes/<key>/` — a `menu_loop.mp3`
  (menu/lobby) and `game/stage1..4.mp3` (the in-round escalation). Neon's loop is the ~46s
  seamless synthwave matched to the Neon Concourse theme.
