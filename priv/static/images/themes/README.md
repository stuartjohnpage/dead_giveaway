# Theme asset packs

Each lobby theme is a self-contained folder under `priv/static/images/themes/<key>/`.
Swapping a lobby's look = pointing the client at a different theme folder. Nothing about
the pack is correlated with the human/bot mapping — see the identity note below.

## Layout

```
themes/
  gen_pack.py            # palette-driven generator (no art skills needed)
  README.md              # this file
  SD_RECIPES.md          # prompts + setup for upgrading to Stable Diffusion art
  neon/
    theme.json           # manifest: palette, asset paths, variant/animation counts
    agents.png           # sprite atlas — 12 variants x {idle, walk, run, dropped}
    agents.json          # Pixi spritesheet atlas (frames + named animations)
    floor_tile.png       # seamless tileable arena floor
    finish_line.png      # vertical finish strip
    arena_bg.png         # full top-down room (1280x720)
    menu_bg.png          # main-menu backdrop (1280x720, no baked text)
    lobby_bg.png         # between-rounds lobby backdrop (1280x720, no baked text)
```

## The sprite pool (read this)

`agents.png` holds **12 cosmetic variants**. Each variant has four animation states:
`idle` (4 frames), `walk` (4), `run` (6), `dropped` (1, the ghosted body after a kill).
Frame size is **32×32**.

**Assign a variant to each character randomly at spawn, server-side, and never tie it to
identity.** A variant is decoration only: the same look can be a human this round and a
bot the next. This is what makes the crowd feel like a crowd instead of a row of clones,
without leaking who is who. (Running is still the only hard tell — a speed difference,
not a visual one.)

## Loading in Pixi

`agents.json` is a standard Pixi spritesheet with an `animations` block, so variants and
states load directly:

```js
import { Assets, AnimatedSprite } from "pixi.js";

const sheet = await Assets.load("/images/themes/neon/agents.json");

// pick a random cosmetic variant for a character (server tells you which)
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

Open `gen_pack.py`, copy the `"neon"` block in `THEMES`, rename the key, and change the
colours (`floor`, `accent`, `shirts`, `hairs`, `skins`, `wall`, `finish`). Then:

```bash
python3 priv/static/images/themes/gen_pack.py . <your_key>
```

That regenerates the whole pack — atlas, backgrounds, manifest — in the matching style.
When you're ready for higher-fidelity art, `SD_RECIPES.md` has Stable Diffusion prompts
that match this structure so generated art drops into the same folders.
