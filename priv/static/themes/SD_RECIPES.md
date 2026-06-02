# Upgrading to Stable Diffusion art (free, local)

The procedural pack is good programmer-art to build against. When you want richer
visuals, generate them locally — no paid credits, no per-image cost. Anthropic does not
offer image or sound generation, so this is the free route.

## Hardware note

For Stable Diffusion, **system RAM barely matters — VRAM is the constraint.** Your 16 GB
of RAM is fine. With a decent GPU (8 GB+ VRAM) you can run SDXL/pixel models comfortably;
6 GB works with `--medvram`. CPU-only is possible but slow.

## Setup (pick one)

- **ComfyUI** — node-based, most control over tiling/seeds. https://github.com/comfyanonymous/ComfyUI
- **Automatic1111 WebUI** — simpler form-based UI. https://github.com/AUTOMATIC1111/stable-diffusion-webui

Useful models/extensions (all free on Civitai/HuggingFace):
- A **pixel-art LoRA/checkpoint** (search "pixel art" on Civitai) for the sprite style.
- **Tiled Diffusion / "seamless"** option for the floor tile.
- **Aseprite** (cleanup, palette-locking, true pixel grid) — https://www.aseprite.org

## Workflow that matches this pack

1. Generate at a **small native size** (e.g. 128×128 for an agent, 512×288 for a
   background), then downscale + index the palette in Aseprite so it's true pixel art.
2. Keep the **same files and sizes** as the procedural pack (see `README.md`) so art
   drops straight into `themes/<key>/`.
3. For the sprite atlas, generate each pose, slice into 32×32 frames, and re-run the
   atlas packing (or keep `agents.json` and just replace `agents.png` if you match the
   exact grid).

## Prompt recipes (Neon Concourse theme)

Shared style suffix — append to every prompt:
```
pixel art, limited palette, crisp pixels, no anti-aliasing, 1px black outline,
retro arcade, neon on near-black, top-down 3/4 view
```
Negative:
```
blurry, jpeg artifacts, smooth gradients, photorealistic, text, watermark, signature, 3d render
```

**Agent (one cosmetic variant), right-facing:**
```
a single small humanoid character walking to the right, seen from a top-down 3/4 angle,
teal jacket, dark trousers, simple face, game character sprite, centered on transparent
background, {style suffix}
```
Vary `teal jacket` → cyan / magenta / lime / orange / yellow / red / blue / purple /
teal / pink / white / mint to build the 12-variant pool. Generate idle, a 4-frame walk,
and a 6-frame run per variant (use a low denoise img2img off one frame to keep them
consistent).

**Arena floor (tileable):**
```
seamless tileable dark glass floor tile, faint magenta grid seams, tiny neon speckles,
{style suffix}
```
Enable the seamless/tiling option.

**Arena background (full room):**
```
top-down empty arcade concourse floor, black glass, neon trim along top and bottom,
glowing cyan start line on the left, black-and-white checkered finish on the right,
faint horizontal lane guides, {style suffix}
```

**Menu backdrop:**
```
moody neon arcade concourse at night, a small crowd of identical-styled silhouettes near
the bottom, lots of dark empty space above for a title, glowing horizontal neon bands,
{style suffix}
```

**Lobby backdrop:**
```
a row of pixel characters standing and waiting on a neon-lit platform, dark room,
glowing lime floor edge, space above for UI, {style suffix}
```

Keep menu/lobby art **text-free** — the game renders the title and UI text on top in Pixi
so it stays crisp and localizable.

## Sound (also free, local)

Anthropic has no audio generation either. Free options that fit the retro vibe:
- **jsfxr / sfxr** (https://sfxr.me) — retro SFX (footsteps, the bullet, UI blips) in-browser, export WAV.
- **Freesound** (https://freesound.org) — CC-licensed clips.
- Your existing `gunshot.mp3` already lives in `priv/static/assets/sounds/`.
