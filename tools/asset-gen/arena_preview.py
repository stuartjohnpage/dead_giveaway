#!/usr/bin/env python3
"""Show an arena as the player actually sees it: arena_bg under the full-width floor
TilingSprite band (game.mjs covers y 64..656), the finish sprite at its real spot, and
a scatter of agent sprites on the lanes. Usage: arena_preview.py <theme_dir> <out.png>"""
import json, os, random, sys
from PIL import Image

theme, out = sys.argv[1], sys.argv[2]
W, H = 1280, 720
FLOOR_TOP, PAD, SPRITE_SCALE = 64, 24, 1.5
LANE_PAD_Y = FLOOR_TOP + int(SPRITE_SCALE * 16)

img = Image.open(os.path.join(theme, "arena_bg.png")).convert("RGBA")
tile = Image.open(os.path.join(theme, "floor_tile.png")).convert("RGBA")
for ty in range(FLOOR_TOP, H - FLOOR_TOP, tile.height):
    for tx in range(0, W, tile.width):
        band = tile.crop((0, 0, tile.width, min(tile.height, H - FLOOR_TOP - ty)))
        img.paste(band, (tx, ty))
finish = Image.open(os.path.join(theme, "finish_line.png")).convert("RGBA")
finish = finish.resize((finish.width, H - 2 * FLOOR_TOP), Image.NEAREST)
img.alpha_composite(finish.crop((0, 0, W - (W - PAD - finish.width // 2), finish.height)),
                    (W - PAD - finish.width // 2, FLOOR_TOP))

sheet = Image.open(os.path.join(theme, "agents.png")).convert("RGBA")
atlas = json.load(open(os.path.join(theme, "agents.json")))
rnd = random.Random(5)
lanes = 14
layers = atlas["meta"]["layers"]
for lane in range(lanes):
    pose = rnd.choice(["idle0", "walk1", "run2", "idle2"])
    # Compose a random look the way the client does (#67): body, then face, then hat.
    spr = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    for layer in ("body", "face", "hat"):
        opt = rnd.randrange(layers[layer])
        fr = atlas["frames"][f"{layer}{opt:02d}_{pose}"]["frame"]
        spr.alpha_composite(sheet.crop((fr["x"], fr["y"], fr["x"] + fr["w"], fr["y"] + fr["h"])))
    spr = spr.resize((int(32 * SPRITE_SCALE), int(32 * SPRITE_SCALE)), Image.NEAREST)
    sy = LANE_PAD_Y + lane * (H - 2 * LANE_PAD_Y) // (lanes - 1)
    sx = PAD + rnd.randrange(0, W - 2 * PAD - 120)
    img.alpha_composite(spr, (sx - 24, sy - 24))
img.convert("RGB").save(out)
print("wrote", out)
