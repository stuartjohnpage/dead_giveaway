#!/usr/bin/env python3
"""
Dead Giveaway - procedural pixel-art theme-pack generator.

Palette-driven. Produces, for one theme:
  - agents.png + agents.json  (Pixi spritesheet atlas: 12 variants x {idle, walk(4), run(6), dropped})
  - floor_tile.png            (seamless tileable arena floor)
  - finish_line.png           (vertical finish strip)
  - arena_bg.png              (full top-down room, 1280x720)
  - menu_bg.png               (1280x720)
  - lobby_bg.png              (1280x720)
  - theme.json                (manifest)
  - preview.png               (contact sheet)
  - walk_preview.gif / run_preview.gif (motion check)

Add a new lobby theme = add a THEMES entry. No art skills required.
"""
import json, math, os, sys, random
from PIL import Image, ImageDraw, ImageFilter

# ----------------------------------------------------------------------------
# Theme definitions. Everything cosmetic flows from here.
# ----------------------------------------------------------------------------
THEMES = {
    "neon": {
        "display": "Neon Concourse",
        "blurb": "After-hours arcade concourse: black glass floor, humming neon, chrome trim.",
        "floor": [(18, 16, 32), (24, 20, 44)],      # two-tone dark tile
        "grid_line": (60, 40, 90),
        "accent": [(0, 230, 230), (255, 60, 200), (160, 255, 60)],  # cyan / magenta / lime
        "wall": (12, 10, 22),
        "vignette": (4, 2, 10),
        "finish": [(245, 245, 255), (20, 18, 30)],   # checker colors
        # cosmetic swatches the 12 variants draw from (shirt, hair)
        "shirts": [(0,230,230),(255,60,200),(160,255,60),(255,170,40),(255,235,60),
                   (235,40,70),(60,120,255),(180,70,255),(0,200,160),(255,120,170),
                   (235,235,245),(120,255,210)],
        "hairs":  [(30,28,40),(80,40,30),(20,20,25),(110,80,40),(200,180,120),
                   (40,30,60),(150,30,40),(25,25,35),(90,60,30),(210,210,220),
                   (60,40,30),(35,30,45)],
        "skins":  [(245,205,170),(225,175,135),(200,150,110),(165,115,80),(120,80,55)],
        "pants":  (35,33,48),
        "outline":(8,6,14),
    },
}

FW = FH = 32                      # frame size
N_VARIANTS = 12
SCALE_BG = 4                      # backgrounds rendered at 1/4 then nearest-upscaled

# animation frame counts
ANIM = {"idle": 4, "walk": 4, "run": 6, "dropped": 1}
COLS = sum(ANIM.values())        # frames per variant row = 15
ROWS = N_VARIANTS

# ----------------------------------------------------------------------------
# low-level helpers
# ----------------------------------------------------------------------------
def add_outline(layer, color):
    """Return layer composited over a 1px dark outline derived from its own alpha."""
    a = layer.split()[3]
    grown = a.filter(ImageFilter.MaxFilter(3))
    edge = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    ed = ImageDraw.Draw(edge)
    px_e = edge.load(); px_a = a.load(); px_g = grown.load()
    w, h = layer.size
    for y in range(h):
        for x in range(w):
            if px_g[x, y] > 40 and px_a[x, y] <= 40:
                px_e[x, y] = (color[0], color[1], color[2], 255)
    out = Image.alpha_composite(edge, layer)
    return out

def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)

def blend(base, col, f):
    """Opaque blend of col onto base by factor f (0..1). Avoids alpha-hole artifacts."""
    return tuple(max(0, min(255, int(base[i]*(1-f) + col[i]*f))) for i in range(3))

# ----------------------------------------------------------------------------
# character drawing  (3/4 side view, facing RIGHT)
# ----------------------------------------------------------------------------
def draw_agent(pal, variant, pose, t):
    """Render one 32x32 RGBA frame."""
    img = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    fig = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    d = ImageDraw.Draw(fig)

    skin = pal["skins"][variant % len(pal["skins"])]
    shirt = pal["shirts"][variant % len(pal["shirts"])]
    hair = pal["hairs"][variant % len(pal["hairs"])]
    pants = pal["pants"]

    cx = 16
    bob = 0
    lean = 0
    # phase math per pose
    if pose == "walk":
        ph = t / ANIM["walk"] * 2 * math.pi
        swing = int(round(3 * math.sin(ph)))
        aswing = int(round(3 * math.sin(ph + math.pi)))
        bob = 0 if t % 2 == 0 else -1
    elif pose == "run":
        ph = t / ANIM["run"] * 2 * math.pi
        swing = int(round(5 * math.sin(ph)))
        aswing = int(round(5 * math.sin(ph + math.pi)))
        bob = -1 if (t % 3) else -2
        lean = 2
    elif pose == "idle":
        ph = t / ANIM["idle"] * 2 * math.pi
        swing = 0; aswing = 0
        bob = 0 if t in (0, 2) else -1
    else:  # dropped
        swing = 0; aswing = 0; bob = 0

    if pose == "dropped":
        # slumped, lying toward the right; drawn faded later
        d.ellipse([6, 18, 26, 27], fill=shade(shirt, .6))
        d.ellipse([20, 17, 28, 25], fill=shade(skin, .7))   # head
        d.ellipse([21, 19, 25, 23], fill=shade(hair, .7))
        fig = add_outline(fig, pal["outline"])
        # fade it
        alpha = fig.split()[3].point(lambda v: int(v * 0.55))
        fig.putalpha(alpha)
        img = Image.alpha_composite(img, fig)
        return img

    bx = cx + lean
    top = 6 + bob

    # legs (behind torso)
    lcol = pants
    # back leg
    d.line([(bx-1, top+15), (bx-1 - aswing, top+22)], fill=shade(lcol,.8), width=3)
    d.rectangle([bx-3-aswing if aswing>0 else bx-3, top+21, bx-1-aswing+1, top+23], fill=shade(skin,.85))
    # front leg
    d.line([(bx+1, top+15), (bx+1 + swing, top+22)], fill=lcol, width=3)
    # foot
    fx = bx + swing
    d.rectangle([fx, top+21, fx+3, top+23], fill=shade(skin,.9))

    # torso
    d.rounded_rectangle([bx-4, top+8, bx+4, top+17], radius=2, fill=shirt)
    d.rounded_rectangle([bx-4, top+8, bx+1, top+17], radius=2, fill=shade(shirt,.85))  # shade back

    # back arm
    d.line([(bx-2, top+9), (bx-2 - aswing, top+15)], fill=shade(shirt,.8), width=2)
    # front arm + hand
    hx, hy = bx+3 + swing, top+15
    d.line([(bx+3, top+9), (hx, hy)], fill=shirt, width=2)
    d.ellipse([hx-1, hy-1, hx+1, hy+1], fill=skin)

    # head
    d.ellipse([bx-3, top, bx+4, top+8], fill=skin)
    # face hint (facing right): a touch of shadow on left, nose pixel on right
    d.ellipse([bx-3, top, bx+0, top+8], fill=shade(skin,.9))
    d.point((bx+4, top+4), fill=shade(skin,.85))
    # hair cap
    d.chord([bx-4, top-1, bx+5, top+6], 180, 360, fill=hair)
    d.rectangle([bx-4, top+1, bx-2, top+4], fill=hair)  # back of hair

    fig = add_outline(fig, pal["outline"])

    # shadow under feet (not outlined)
    sh = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([bx-6, top+24, bx+8, top+28], fill=(0, 0, 0, 70))
    img = Image.alpha_composite(img, sh)
    img = Image.alpha_composite(img, fig)
    return img

# ----------------------------------------------------------------------------
# atlas builder
# ----------------------------------------------------------------------------
def build_atlas(pal, theme_key):
    sheet = Image.new("RGBA", (COLS * FW, ROWS * FH), (0, 0, 0, 0))
    frames = {}
    animations = {}
    for v in range(N_VARIANTS):
        col = 0
        for pose in ("idle", "walk", "run", "dropped"):
            seq = []
            for t in range(ANIM[pose]):
                fr = draw_agent(pal, v, pose, t)
                x, y = col * FW, v * FH
                sheet.paste(fr, (x, y), fr)
                name = f"v{v:02d}_{pose}{t}"
                frames[name] = {
                    "frame": {"x": x, "y": y, "w": FW, "h": FH},
                    "sourceSize": {"w": FW, "h": FH},
                    "spriteSourceSize": {"x": 0, "y": 0, "w": FW, "h": FH},
                }
                seq.append(name)
                col += 1
            animations[f"v{v:02d}_{pose}"] = seq
    atlas = {
        "frames": frames,
        "animations": animations,
        "meta": {
            "app": "deadgiveaway-genpack",
            "image": "agents.png",
            "format": "RGBA8888",
            "size": {"w": COLS * FW, "h": ROWS * FH},
            "scale": "1",
            "theme": theme_key,
            "variants": N_VARIANTS,
            "frameSize": {"w": FW, "h": FH},
        },
    }
    return sheet, atlas

# ----------------------------------------------------------------------------
# backgrounds (rendered small, nearest-upscaled for crisp pixels)
# ----------------------------------------------------------------------------
def up(img):
    return img.resize((img.width * SCALE_BG, img.height * SCALE_BG), Image.NEAREST)

def floor_tile(pal):
    s = 32
    img = Image.new("RGBA", (s, s), (0, 0, 0, 255))
    d = ImageDraw.Draw(img)
    a, b = pal["floor"]
    for y in range(s):
        for x in range(s):
            d.point((x, y), fill=a if (x // 8 + y // 8) % 2 == 0 else b)
    # grid seams (seamless: only top & left) — clean tile, no speckle
    d.line([(0, 0), (s, 0)], fill=pal["grid_line"])
    d.line([(0, 0), (0, s)], fill=pal["grid_line"])
    return img

def finish_line(pal):
    w, h = 16, 180
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c0, c1 = pal["finish"]
    for y in range(h):
        for x in range(w):
            d.point((x, y), fill=c0 if (x // 8 + y // 8) % 2 == 0 else c1)
    return up(img)

def _vignette(img, col):
    w, h = img.size
    v = Image.new("L", (w, h), 0)
    dv = ImageDraw.Draw(v)
    dv.ellipse([-w*0.25, -h*0.25, w*1.25, h*1.25], fill=255)
    v = v.filter(ImageFilter.GaussianBlur(w*0.12))
    dark = Image.new("RGBA", (w, h), (col[0], col[1], col[2], 255))
    inv = v.point(lambda p: 255 - p)
    img.paste(dark, (0, 0), inv)
    return img

def arena_bg(pal):
    W, H = 320, 180
    img = Image.new("RGBA", (W, H), pal["wall"] + (255,))
    tile = floor_tile(pal)
    # play area inset
    pad_x, pad_y = 8, 18
    for ty in range(pad_y, H - pad_y, tile.height):
        for tx in range(pad_x, W - pad_x, tile.width):
            img.paste(tile, (tx, ty))
    d = ImageDraw.Draw(img, "RGBA")
    # lane rows (subtle) – characters sit on fixed vertical rows
    rows = 6
    for i in range(rows):
        y = pad_y + 6 + i * ((H - 2*pad_y - 12) // (rows - 1))
        lc = blend(pal["floor"][1], pal["accent"][i % 3], 0.16)
        d.line([(pad_x, y), (W - pad_x, y)], fill=lc)
    # start (left) and finish (right) neon posts
    d.rectangle([pad_x, pad_y, pad_x+2, H-pad_y], fill=pal["accent"][0])
    fl = finish_line(pal).resize((10, H-2*pad_y), Image.NEAREST)
    img.paste(fl, (W - pad_x - 10, pad_y))
    # top & bottom neon trim
    d.rectangle([0, pad_y-3, W, pad_y-1], fill=pal["accent"][1])
    d.rectangle([0, H-pad_y+1, W, H-pad_y+3], fill=pal["accent"][2])
    # solid black below the finish-edge line (no floor beneath it)
    d.rectangle([0, H-pad_y+4, W, H], fill=pal["wall"])
    img = up(img)
    img = _vignette(img, pal["vignette"])
    return img

def _scatter_crowd(img, pal, n, y0, y1, seed):
    """Paste tiny silhouettes for menu/lobby flavor."""
    rnd = random.Random(seed)
    for _ in range(n):
        v = rnd.randrange(N_VARIANTS)
        fr = draw_agent(pal, v, "walk", rnd.randrange(ANIM["walk"]))
        sc = rnd.choice([2, 2, 3])
        fr = fr.resize((FW*sc, FH*sc), Image.NEAREST)
        x = rnd.randrange(0, img.width - FW*sc)
        y = rnd.randrange(y0, y1)
        img.paste(fr, (x, y), fr)
    return img

def menu_bg(pal):
    # Atmospheric only — game renders the title/UI text on top in Pixi/HTML.
    W, H = 320, 180
    img = Image.new("RGBA", (W, H), pal["wall"] + (255,))
    d = ImageDraw.Draw(img, "RGBA")
    # backdrop neon glow bands behind the crowd
    for i, c in enumerate(pal["accent"]):
        y = H - 30 - i * 7
        d.rectangle([0, y, W, y + 2], fill=blend(pal["wall"], c, 0.35))
    img = _scatter_crowd(img, pal, 10, H-70, H-34, seed=21)
    img = up(img)
    img = _vignette(img, pal["vignette"])
    return img

def lobby_bg(pal):
    W, H = 320, 180
    img = Image.new("RGBA", (W, H), shade(pal["wall"], 1.4) + (255,))
    d = ImageDraw.Draw(img, "RGBA")
    tile = floor_tile(pal)
    for tx in range(0, W, tile.width):
        img.paste(tile, (tx, H-40))
    d.rectangle([0, H-44, W, H-41], fill=pal["accent"][2])
    # a waiting line of agents (idle)
    rnd = random.Random(5)
    x = 20
    while x < W-30:
        v = rnd.randrange(N_VARIANTS)
        fr = draw_agent(pal, v, "idle", rnd.randrange(ANIM["idle"]))
        fr = fr.resize((FW*2, FH*2), Image.NEAREST)
        img.paste(fr, (x, H-40-50), fr)
        x += rnd.choice([26, 30, 34])
    img = up(img)
    img = _vignette(img, pal["vignette"])
    return img

# ----------------------------------------------------------------------------
# previews
# ----------------------------------------------------------------------------
def contact_sheet(pal):
    pad = 4
    cellw, cellh = FW*COLS, FH
    sc = 2
    img = Image.new("RGBA", (cellw*sc + pad*2, cellh*ROWS*sc + pad*2), (20,18,28,255))
    sheet, _ = build_atlas(pal, "preview")
    big = sheet.resize((sheet.width*sc, sheet.height*sc), Image.NEAREST)
    img.paste(big, (pad, pad), big)
    return img

def make_gif(pal, variant, pose, path):
    frames = []
    for t in range(ANIM[pose]):
        fr = draw_agent(pal, variant, pose, t).resize((FW*6, FH*6), Image.NEAREST)
        bg = Image.new("RGBA", fr.size, (24,20,40,255))
        bg.alpha_composite(fr)
        frames.append(bg.convert("P", palette=Image.ADAPTIVE))
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=120 if pose=="walk" else 80, loop=0, disposal=2)

# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------
def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    theme_key = sys.argv[2] if len(sys.argv) > 2 else "neon"
    pal = THEMES[theme_key]
    base = os.path.join(repo, "priv", "static", "images", "themes", theme_key)
    os.makedirs(base, exist_ok=True)

    sheet, atlas = build_atlas(pal, theme_key)
    sheet.save(os.path.join(base, "agents.png"))
    with open(os.path.join(base, "agents.json"), "w") as f:
        json.dump(atlas, f, indent=1)

    floor_tile(pal).save(os.path.join(base, "floor_tile.png"))
    finish_line(pal).save(os.path.join(base, "finish_line.png"))
    arena_bg(pal).save(os.path.join(base, "arena_bg.png"))
    menu_bg(pal).save(os.path.join(base, "menu_bg.png"))
    lobby_bg(pal).save(os.path.join(base, "lobby_bg.png"))

    manifest = {
        "key": theme_key,
        "display": pal["display"],
        "blurb": pal["blurb"],
        "frameSize": {"w": FW, "h": FH},
        "variants": N_VARIANTS,
        "animations": {k: v for k, v in ANIM.items()},
        "assets": {
            "agentsAtlas": "agents.json",
            "agentsImage": "agents.png",
            "floorTile": "floor_tile.png",
            "finishLine": "finish_line.png",
            "arenaBackground": "arena_bg.png",
            "menuBackground": "menu_bg.png",
            "lobbyBackground": "lobby_bg.png",
        },
        "palette": {
            "wall": pal["wall"], "floor": pal["floor"], "accent": pal["accent"],
        },
        "note": "Cosmetic variants are NOT correlated with human/bot identity. "
                "Assign a random variant per character at spawn, server-side.",
    }
    with open(os.path.join(base, "theme.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    # previews into outputs (cwd) so they can be shown without polluting the repo
    outdir = os.environ.get("PREVIEW_DIR", ".")
    contact_sheet(pal).save(os.path.join(outdir, "preview_agents.png"))
    arena_bg(pal).save(os.path.join(outdir, "preview_arena.png"))
    menu_bg(pal).save(os.path.join(outdir, "preview_menu.png"))
    lobby_bg(pal).save(os.path.join(outdir, "preview_lobby.png"))
    make_gif(pal, 0, "walk", os.path.join(outdir, "preview_walk.gif"))
    make_gif(pal, 3, "run", os.path.join(outdir, "preview_run.gif"))

    print("OK theme=", theme_key)
    print("atlas size:", sheet.size, "frames:", len(atlas["frames"]))
    print("written to:", base)

if __name__ == "__main__":
    main()
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            