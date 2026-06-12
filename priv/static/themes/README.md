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
`gen_gunshot.py` (firing SFX), `gen_watcher.py` + `gen_windup.py` (the Red Light
watcher and its wind-up cue, #53), and `gen_music*.py` / `gen_game_music*.py` (music),
plus `stems/` (raw layers for future WebAudio mixing). Two preview tools render a pack the way
players actually see it: `arena_preview.py` (arena_bg + tiled floor + finish + sprites)
and `scrim_preview.py` (menu_bg behind the lobby card's blur + scrim).

```
themes/
  README.md              # this file
  SD_RECIPES.md          # prompts + setup for upgrading to Stable Diffusion art
  neon/
    theme.json           # manifest: palette + assets/audio/ui paths, layer/animation counts
    agents.png           # sprite atlas — 3 layers (hat/face/body) x 6 options x states (#67)
    agents.json          # Pixi spritesheet atlas (frames + named animations)
    floor_tile.png       # seamless tileable arena floor
    finish_line.png      # vertical finish strip
    arena_bg.png         # full top-down room (1280x720)
    menu_bg.png          # menu backdrop (1280x720, no baked text); the manifest's
                         # lobbyBackground points here too — one shot serves both
    bullet.png           # ammo-counter icon (+ bullet_flat.png, the no-glow variant)
    crosshair.png        # the theme's reticle (38x38, centered) — yours and peers' (#48)
    watcher.png/.json    # the Red Light watcher atlas (#53): idle / spin / watch, 48x48
    menu_loop.mp3        # menu/lobby music loop
    game/stage1..4.mp3   # in-round escalating music (one stage per 15s, holds at 4)
    shot.mp3             # the theme's gunshot one-shot (#48)
    windup.mp3           # the watcher's wind-up warning cue (~0.8s, #53)
  western/               # same shape; PACK.md documents this pack's specifics
```

All paths inside `theme.json` are **relative to the theme's own folder**, so a pack is
fully self-contained and relocatable. A theme may omit `audio.gameStages` (e.g. before its
in-round music is generated); the client then falls back to the default theme's stages.
Likewise `ui.crosshair` (absent → a procedural cross tinted to `ui.reticle`),
`audio.shot` (absent → the default `/sounds/gunshot.mp3` crack), and the Red Light
watcher's `assets.watcher` / `audio.windup` (absent → the default theme's, #53).
Crosshairs are cosmetic only: keep the canvas size and centered anchor so aim feel
never changes between themes.

## The sprite pool (read this)

`agents.png` holds **three composable layers** (#67) — `hat`, `face` (head + hair), and
`body` (outfit) — with **6 options each**, every option drawn in all four animation
states: `idle` (4 frames), `walk` (4), `run` (6), `dropped` (1, the ghosted body after a
kill). Frame size is **32×32**; a character is the stack body → face → hat, all three
playing the same state in lockstep. Hat option 0 is bare-headed in every theme.

**Each character's look ({hat, face, body} indices) is assigned server-side and rides the
snapshot — players pick theirs on the name screen; bots are dealt random picks from the
same pool.** A look is decoration only and never correlates with the human/bot mapping:
the indices say nothing about who is driving the body. (Running is still the only hard
tell — a speed difference, not a visual one.) Option indices line up across themes, so a
player's saved pick maps onto whichever pack the lobby is using.

## Loading in Pixi

`agents.json` is a standard Pixi spritesheet with an `animations` block, so layers and
states load directly:

```js
import { Assets, AnimatedSprite, Container } from "pixi.js";

const sheet = await Assets.load("/themes/neon/agents.json");

// stack one AnimatedSprite per layer from the entity's server-sent look
const part = (layer, opt, state) =>
  new AnimatedSprite(sheet.animations[`${layer}${String(opt).padStart(2, "0")}_${state}`]);
const body = new Container();
body.addChild(part("body", look.body, "walk"), part("face", look.face, "walk"),
              part("hat", look.hat, "walk"));

// switch state without reallocating (per part):
sprite.textures = sheet.animations[`body03_run`];
sprite.gotoAndPlay(0); // restart all three together so the layers stay frame-locked
```

Animation names: `hat00_idle … hat05_idle`, `face00… face05…`, `body00… body05…`, each
with `…_walk`, `…_run`, `…_dropped`. All sprites face **right** (the only movement
direction). Render with nearest-neighbor scaling (`texture.source.scaleMode = "nearest"`)
to keep pixels crisp.

## Adding a new theme

1. Open `tools/asset-gen/gen_pack.py`, copy the `"neon"` block in `THEMES`, rename the key,
   and change the colours (`floor`, `accent`, `shirts`, `hairs`, `skins`, `wall`, `finish`,
   the 6 `hats` specs — shape + colours, shapes from `HAT_SHAPES`, entry 0 stays bare —
   and the `bullet`/`reticle` UI hints). Pick a `scene` — the composition archetype the
   backgrounds are drawn with (`concourse` = cyberpunk neon + black glass, `frontier` =
   desert badlands + dirt, `orbital` = viewports + deck plating); the palette does the
   colouring. Then, from the repo root:

   ```bash
   python3 tools/asset-gen/gen_pack.py . <your_key>     # writes priv/static/themes/<your_key>/
   python3 tools/asset-gen/gen_bullet.py priv/static/themes/<your_key> - cartridge
   ```

   The Red Light watcher (#53) needs a flavor drawn per theme, so `gen_watcher.py` /
   `gen_windup.py` take a new entry in their own `THEMES` tables (they run for every
   key at once); until then the pack falls back to the default theme's watcher + cue.

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
