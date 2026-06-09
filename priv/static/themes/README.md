# Theme asset packs

Each lobby theme is a **self-contained folder** under `priv/static/themes/<key>/`
(served at `/themes/<key>/`) holding *all* of the theme's runtime assets — art, audio,
and bullet. The host picks the theme in the lobby; the client's `loadTheme()`
(`assets/js/game.mjs`) reads the folder's `theme.json` and swaps everything live for
everyone in the room. Nothing about the pack is correlated with the human/bot mapping —
see the identity note below.

## Layout

The generators that produce these packs live OUTSIDE the web-served tree, in
`tools/asset-gen/` (so `mix phx.digest` doesn't bundle them): `gen_pack.py` (sprites +
backgrounds + manifest), `gen_bullet.py` (ammo icon), `gen_crosshair.py` (reticle),
`gen_gunshot.py` (firing SFX), and `gen_music*.py` / `gen_game_music*.py` (music), plus
`stems/` (raw layers for future WebAudio mixing).

```
themes/
  README.md              # this file
  SD_RECIPES.md          # prompts + setup for upgrading to Stable Diffusion art
  neon/
    theme.json           # manifest: palette + assets/audio/ui paths, variant/animation counts
    agents.png           # sprite atlas — 12 variants x {idle, walk, run, dropped}
    agents.json          # Pixi spritesheet atlas (frames + named animations)
    floor_tile.png       # seamless tileable arena floor
    finish_line.png      # vertical finish strip
    arena_bg.png         # full top-down room (1280x720)
    menu_bg.png          # main-menu backdrop (1280x720, no baked text)
    lobby_bg.png         # between-rounds lobby backdrop (1280x720, no baked text)
    bullet.png           # ammo-counter icon (+ bullet_flat.png, the no-glow variant)
    crosshair.png        # the theme's reticle (38x38, centered) — yours and peers' (#48)
    menu_loop.mp3        # menu/lobby music loop
    game/stage1..4.mp3   # in-round escalating music (one stage per 15s, holds at 4)
    shot.mp3             # the theme's gunshot one-shot (#48)
  western/               # same shape; PACK.md documents this pack's specifics
```

All paths inside `theme.json` are **relative to the theme's own folder**, so a pack is
fully self-contained and relocatable. A theme may omit `audio.gameStages` (e.g. before its
in-round music is generated); the client then falls back to the default theme's stages.
Likewise `ui.crosshair` (absent → a procedural cross tinted to `ui.reticle`) and
`audio.shot` (absent → the default `/sounds/gunshot.mp3` crack). Crosshairs are cosmetic
only: keep the canvas size and centered anchor so aim feel never changes between themes.

## The sprite pool (read this)

`agents.png` holds **12 cosmetic variants**. Each variant has four animation states:
`idle` (4 frames), `walk` (4), `run` (6), `dropped` (1, the ghosted body after a kill).
Frame size is **32×32**.

**Each character's variant is derived client-side from a deterministic hash of its entity
id — never tied to identity.** Every client therefore shows a given character the same way
with no variant data on the wire, and a variant is decoration only: the same look can be a
human this round and a bot the next (identity is re-rolled per round). This is what makes
the crowd feel like a crowd instead of a row of clones, without leaking who is who.
(Running is still the only hard tell — a speed difference, not a visual one.)

## Loading in Pixi

`agents.json` is a standard Pixi spritesheet with an `animations` block, so variants and
states load directly:

```js
import { Assets, AnimatedSprite } from "pixi.js";

const sheet = await Assets.load("/themes/neon/agents.json");

// derive the variant from the entity id (deterministic, identity-independent)
const v = String(variantIndex).padStart(2, "0");      // e.g. "07"
const sprite = new AnimatedSprite(sheet.animations[`v${v}_walk`]);
sprite.animationSpeed = 0.15;   // run uses ~0.28; idle ~0.05
sprite.play();

// switch state without reallocating:
sprite.textures = sheet.animations[`v${v}_run`];
sprite.play();
```

Animation names: `v00_idle … v11_idle`, `…_walk`, `…_run`, `…_dropped`.
All sprites face **right** (the only movement direction). Render with nearest-neighbor
scaling (`texture.source.scaleMode = "nearest"`) to keep pixels crisp.

## Adding a new theme

1. Open `tools/asset-gen/gen_pack.py`, copy the `"neon"` block in `THEMES`, rename the key,
   and change the colours (`floor`, `accent`, `shirts`, `hairs`, `skins`, `wall`, `finish`,
   and the `bullet`/`reticle` UI hints). Then, from the repo root:

   ```bash
   python3 tools/asset-gen/gen_pack.py . <your_key>     # writes priv/static/themes/<your_key>/
   python3 tools/asset-gen/gen_bullet.py priv/static/themes/<your_key> - cartridge
   ```

   That generates the atlas, backgrounds, bullet, and `theme.json`. Add `menu_loop.mp3`
   (+ optionally `game/stage1..4.mp3`) under the folder with the `gen_music*.py` scripts.
   `gen_pack.py` writes the manifest's `assets`/`ui` keys, and the `audio` keys for any
   music it finds already in the folder — so generate art first, then music, then re-run
   `gen_pack.py` (or hand-add `audio`) once the tracks exist. A pack that declares no
   `audio.gameStages` falls back to the default theme's stages client-side.

2. **Register the key** in `lib/dead_giveaway/themes.ex` (`@catalog`) — its display name
   there is what shows in the lobby's theme picker, and the server validates a host's pick
   against this list. This is the only code change needed to light a new pack up.

When you're ready for higher-fidelity art, `SD_RECIPES.md` has Stable Diffusion prompts
that match this structure so generated art drops into the same folders.
