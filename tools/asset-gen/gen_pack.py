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
import json, math, os, sys, random, hashlib
from PIL import Image, ImageDraw, ImageFilter, ImageChops

# ----------------------------------------------------------------------------
# Theme definitions. Everything cosmetic flows from here.
# ----------------------------------------------------------------------------
THEMES = {
    "neon": {
        "display": "Neon Concourse",
        "blurb": "After-hours arcade concourse: black glass floor, humming neon, chrome trim.",
        # Palette is locked to the UI chrome's --dg-* tokens (assets/css/app.css) so the
        # baked art and the HUD are literally the same light: same ink, same three neons.
        # No fourth hue — the old purple grid/wall is gone; seams are dim cyan instead.
        "floor": [(14, 16, 26), (20, 23, 36)],       # cool dark glass two-tone (no purple)
        "grid_line": (28, 70, 86),                   # dim cyan seam (was purple)
        "accent": [(56, 225, 255), (255, 61, 139), (182, 255, 61)],  # --dg-cyan / magenta / lime
        "wall": (6, 7, 14),                          # --dg-ink
        "vignette": (3, 4, 9),                        # one notch under ink
        "finish": [(240, 245, 255), (12, 14, 22)],   # checker colors
        # cosmetic swatches the 12 variants draw from (shirt, hair)
        "shirts": [(0,230,230),(255,60,200),(160,255,60),(255,170,40),(255,235,60),
                   (235,40,70),(60,120,255),(180,70,255),(0,200,160),(255,120,170),
                   (235,235,245),(120,255,210)],
        "hairs":  [(30,28,40),(80,40,30),(20,20,25),(110,80,40),(200,180,120),
                   (40,30,60),(150,30,40),(25,25,35),(90,60,30),(210,210,220),
                   (60,40,30),(35,30,45)],
        "skins":  [(245,205,170),(225,175,135),(200,150,110),(165,115,80),(120,80,55)],
        "pants":  (35,33,48),
        "outline":(6,7,14),
        # ammo icon (in this folder) + reticle tint — emitted into theme.json's "ui".
        # Reticle tint = --dg-magenta exactly, so the in-game aiming reticle matches the
        # HUD's "run / danger" magenta rather than the old salmon that matched neither.
        "bullet": "bullet.png",
        "reticle": "#ff3d8b",
        # Opt this theme's backgrounds into the surveillance-HUD motifs that match the global
        # chrome (assets/css/app.css): broken marquee tubing + targeting reticles on menu_bg,
        # baked CRT scanlines + start/finish bloom on arena_bg, a cyan vanishing-point glow on
        # lobby_bg. Off for western/station — those keep their own scene language untouched.
        "hud": True,
    },
    "western": {
        "display": "Dead Man's Gulch",
        "blurb": "Sun-baked frontier main street: packed dirt, plank boardwalks, a noon showdown at the line.",
        "floor": [(124, 96, 60), (110, 84, 52)],     # packed-dirt two-tone
        "grid_line": (84, 60, 38),                   # dry plank/dirt seams
        "accent": [(224, 150, 60), (196, 72, 48), (214, 180, 96)],  # sunset orange / barn red / gold
        "wall": (28, 18, 12),
        "vignette": (14, 8, 4),
        "finish": [(235, 225, 200), (70, 44, 28)],   # cream / brown finish banner
        "shirts": [(70,96,150),(150,60,45),(170,140,80),(96,110,70),(196,160,70),
                   (110,80,55),(205,195,170),(120,50,55),(120,120,128),(70,95,75),
                   (180,120,60),(60,55,60)],
        "hairs":  [(40,28,18),(20,16,12),(90,60,35),(120,90,55),(150,150,155),
                   (60,40,25),(30,25,22),(80,55,30),(110,75,45),(25,22,20),
                   (95,65,38),(45,35,28)],
        "skins":  [(245,205,170),(225,175,135),(200,150,110),(165,115,80),(120,80,55)],
        "pants":  (60,48,36),
        "outline":(20,12,8),
        # presence of "hats" switches the head to a cowboy hat
        "hats":   [(92,62,36),(70,48,28),(120,92,58),(45,32,22),(140,110,72),(60,40,26),
                   (30,24,18),(100,72,44),(150,120,80),(80,55,32),(55,42,30),(110,85,52)],
        # ammo icon (in this folder) + reticle tint — emitted into theme.json's "ui".
        "bullet": "bullet_flat.png",
        "reticle": "#e0963c",
    },
    "station": {
        "display": "Derelict Orbital",
        "blurb": "A powered-down orbital station: gunmetal grating, flickering hazard strips, a starboard airlock at the line.",
        "floor": [(44, 50, 60), (36, 42, 52)],       # gunmetal grate two-tone
        "grid_line": (72, 82, 96),                   # panel seams
        "accent": [(255, 150, 50), (232, 72, 58), (96, 190, 220)],  # hazard amber / alert red / signal blue
        "wall": (16, 20, 30),
        "vignette": (4, 6, 12),
        "finish": [(228, 234, 244), (30, 36, 48)],   # white / dark-steel airlock stripe
        "shirts": [(220,120,40),(70,110,150),(184,188,196),(80,160,150),(204,200,90),
                   (160,64,58),(108,118,134),(60,92,134),(176,116,64),(96,172,184),
                   (206,212,222),(126,96,156)],
        "hairs":  [(30,28,40),(80,40,30),(20,20,25),(110,80,40),(200,180,120),
                   (40,30,60),(150,30,40),(25,25,35),(90,60,30),(210,210,220),
                   (60,40,30),(35,30,45)],
        "skins":  [(245,205,170),(225,175,135),(200,150,110),(165,115,80),(120,80,55)],
        "pants":  (50,55,68),
        "outline":(10,12,20),
        # presence of "helmets" switches the head to an EVA helmet (shell + accent visor)
        "helmets":[(212,217,226),(190,196,206),(170,178,190),(202,207,216),(150,160,176),
                   (206,211,221),(182,190,200),(162,170,184),(196,202,214),(176,184,196),
                   (210,214,224),(166,174,188)],
        # ammo icon (in this folder) + reticle tint — emitted into theme.json's "ui".
        "bullet": "bullet.png",
        "reticle": "#5fc0e0",
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

def vivify(c):
    """Push a colour to full value (brightest channel = 255) while keeping its hue. Lifts
    muted palettes (western's amber/red) to neon brightness; near no-op for already-bright
    colours (neon cyan). Lets one brightness work across every theme's accents."""
    m = max(c)
    return c if m == 0 else tuple(min(255, round(v * 255 / m)) for v in c)

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
    if pal.get("hats"):
        # cowboy hat (3/4 side, facing right): crown + wide brim + accent band
        hat = pal["hats"][variant % len(pal["hats"])]
        band = pal["accent"][variant % len(pal["accent"])]
        d.rectangle([bx-4, top+5, bx-2, top+7], fill=hair)              # sliver of hair at back
        d.ellipse([bx-5, top+3, bx+7, top+6], fill=hat)                 # brim
        d.rounded_rectangle([bx-2, top-2, bx+3, top+3], radius=1, fill=hat)  # crown
        d.rectangle([bx-2, top+2, bx+3, top+3], fill=shade(band, .9))   # hat band
        d.line([(bx-2, top-2), (bx+2, top-2)], fill=shade(hat, 1.2))    # crown highlight
    elif pal.get("helmets"):
        # EVA helmet (3/4 side, facing right): a rounded shell dome over the head with a
        # glassy accent visor on the front, plus a bright crown sheen and a back rivet.
        shell = pal["helmets"][variant % len(pal["helmets"])]
        visor = pal["accent"][variant % len(pal["accent"])]
        d.ellipse([bx-4, top-2, bx+5, top+8], fill=shell)                       # dome shell
        d.rounded_rectangle([bx-1, top+1, bx+4, top+6], radius=2, fill=shade(visor, .85))  # visor glass
        d.line([(bx+1, top+2), (bx+3, top+2)], fill=blend(visor, (255,255,255), 0.55))     # visor glare
        d.line([(bx-2, top-2), (bx+1, top-2)], fill=shade(shell, 1.25))         # crown sheen
        d.point((bx-3, top+3), fill=shade(shell, .8))                           # back rivet
    else:
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

def _draw_reticle(d, box, col, length=7, th=2, cross=True):
    """Paint the UI's corner-bracket reticle (assets/css/app.css `.dg-reticle::after`) into
    ImageDraw `d`: four L-shaped corner ticks framing `box` (x0,y0,x1,y1), in RGBA `col`,
    with an optional centre crosshair. This is the game's "lock acquired" motif, baked into
    the art so the scene wears the same targeting language as the chrome over it."""
    x0, y0, x1, y1 = box
    L, T = length, th
    for (cx, cy, sx, sy) in [(x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)]:
        d.rectangle([min(cx, cx + sx * L), min(cy, cy + sy * (T - 1)),
                     max(cx, cx + sx * L), max(cy, cy + sy * (T - 1))], fill=col)
        d.rectangle([min(cx, cx + sx * (T - 1)), min(cy, cy + sy * L),
                     max(cx, cx + sx * (T - 1)), max(cy, cy + sy * L)], fill=col)
    if cross:
        mx, my = (x0 + x1) // 2, (y0 + y1) // 2
        faint = col[:3] + (max(60, col[3] * 7 // 10),) if len(col) == 4 else col
        d.point((mx, my), fill=col)
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            d.line([(mx + dx * 2, my + dy * 2), (mx + dx * 4, my + dy * 4)], fill=faint)

def _scanlines(img, period=4, dark=0.16):
    """Overlay faint horizontal CRT scanlines at full (upscaled) resolution — the baked
    cousin of app.css `.dg-scanlines::before`, so the floor reads as 'seen through the
    monitor' rather than as a clean print. Applied after up()."""
    w, h = img.size
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    a = int(255 * dark)
    for y in range(0, h, period):
        od.line([(0, y), (w, y)], fill=(0, 0, 0, a))
    return Image.alpha_composite(img, ov)

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
    # HUD themes bloom the start (left) and finish (right) before the crisp lines, so each
    # carries its gameplay colour as a glow: cyan = you/start, lime = go/finish (DESIGN code).
    fl_x = W - pad_x - 10
    if pal.get("hud"):
        img.alpha_composite(_bloom(W, H, lambda gd: gd.rectangle([pad_x, pad_y, pad_x+2, H-pad_y], fill=pal["accent"][0] + (255,)), 4))
        img.alpha_composite(_bloom(W, H, lambda gd: gd.rectangle([fl_x, pad_y, fl_x+10, H-pad_y], fill=pal["accent"][2] + (170,)), 4))
    # crisp start post + checkered finish strip on top of any glow
    d.rectangle([pad_x, pad_y, pad_x+2, H-pad_y], fill=pal["accent"][0])
    fl = finish_line(pal).resize((10, H-2*pad_y), Image.NEAREST)
    img.paste(fl, (fl_x, pad_y))
    # top & bottom neon trim
    d.rectangle([0, pad_y-3, W, pad_y-1], fill=pal["accent"][1])
    d.rectangle([0, H-pad_y+1, W, H-pad_y+3], fill=pal["accent"][2])
    # solid black below the finish-edge line (no floor beneath it)
    d.rectangle([0, H-pad_y+4, W, H], fill=pal["wall"])
    img = up(img)
    if pal.get("hud"):
        img = _scanlines(img)      # baked CRT scanlines — the floor is on the monitor too
    img = _vignette(img, pal["vignette"])
    return img

def _vgradient(W, H, top, bottom):
    """A vertical top→bottom colour ramp as an opaque RGBA image."""
    img = Image.new("RGBA", (W, H))
    px = img.load()
    for y in range(H):
        c = blend(top, bottom, y / max(1, H - 1))
        row = c + (255,)
        for x in range(W):
            px[x, y] = row
    return img

def _silhouette(fr, body, rim):
    """Recolour a drawn agent frame into a backlit silhouette: its shape filled with a
    flat dark `body`, plus a 1px accent `rim` light around the edge (the glow behind it)."""
    a = fr.split()[3]
    mask = a.point(lambda v: 255 if v > 40 else 0)
    sil = Image.new("RGBA", fr.size, (0, 0, 0, 0))
    sil.paste(Image.new("RGBA", fr.size, body + (255,)), (0, 0), mask)
    grown = a.filter(ImageFilter.MaxFilter(3))
    px_s, px_a, px_g = sil.load(), a.load(), grown.load()
    w, h = fr.size
    for y in range(h):
        for x in range(w):
            if px_g[x, y] > 40 and px_a[x, y] <= 40:
                px_s[x, y] = rim + (255,)
    return sil

def _crowd_layer(img, pal, n, baseline, scale, body, rim, seed):
    """Scatter `n` backlit silhouettes standing with their feet at `baseline` (so a layer
    placed below the canvas edge is cropped into a foreground rank). `scale` sets depth;
    each figure varies a little in height so the crowd isn't a flat row of clones."""
    rnd = random.Random(seed)
    for _ in range(n):
        v = rnd.randrange(N_VARIANTS)
        sc = scale + rnd.choice([0, 0, 1])
        fr = draw_agent(pal, v, rnd.choice(["idle", "walk"]), rnd.randrange(ANIM["walk"]))
        fr = _silhouette(fr, body, rim).resize((FW * sc, FH * sc), Image.NEAREST)
        x = rnd.randrange(-FW, img.width)
        img.alpha_composite(fr, (x, baseline - FH * sc))
    return img

def _bloom(W, H, draw_fn, radius):
    """Render onto a transparent layer via draw_fn(ImageDraw), then blur it for a glow."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    return layer.filter(ImageFilter.GaussianBlur(radius))

def _vfade_alpha(layer, top_a, bot_a):
    """Scale a layer's alpha by a vertical ramp (top_a..bot_a, each 0..1) so it fades from
    one opacity at the top edge to another at the bottom. Mutates and returns `layer`."""
    w, h = layer.size
    ramp = Image.new("L", (1, h))
    rpx = ramp.load()
    for y in range(h):
        f = top_a + (bot_a - top_a) * (y / max(1, h - 1))
        rpx[0, y] = max(0, min(255, int(255 * f)))
    ramp = ramp.resize((w, h))
    layer.putalpha(ImageChops.multiply(layer.split()[3], ramp))
    return layer

def menu_bg(pal):
    # Atmospheric only — the game renders the title/UI text on top in Pixi/HTML. A lit back
    # wall, a glowing horizon, a reflective floor, and a two-layer backlit crowd give depth.
    # HUD themes (neon) wear the chrome's language: the back wall becomes broken horizontal
    # marquee tubing and three corner-bracket reticles lock onto figures in the crowd — "neon
    # targeting reticles hovering over a dark crowd," exactly what app.css's header keys off.
    # Non-HUD themes keep the original vertical neon signage + sign reflections in the floor.
    W, H = 320, 180
    wall = pal["wall"]
    accent = pal["accent"]
    horizon = H - 54
    hud = pal.get("hud")

    img = _vgradient(W, H,
                     blend(wall, accent[0], 0.05) if hud else shade(wall, 0.7),
                     wall if hud else blend(wall, accent[2], 0.10))

    if hud:
        # Back-wall marquee: broken horizontal neon tubes (segment/gap), bloomed for glow with
        # a brighter crisp core. Horizontal + broken = concourse signage, not a vertical cross.
        bars = [(accent[0], 17, 22, 168), (accent[1], 39, 96, 252), (accent[2], 29, 188, 300)]
        def marquee(gd):
            for c, y, x0, x1 in bars:
                x = x0
                while x < x1:
                    seg = 17 if (x - x0) % 46 else 9     # one short "dead" segment in the run
                    gd.rectangle([x, y, min(x + seg, x1), y + 2], fill=c + (255,))
                    x += seg + 7
        img.alpha_composite(_bloom(W, H, marquee, 4))
        dcore = ImageDraw.Draw(img, "RGBA")
        for c, y, x0, x1 in bars:
            x = x0
            while x < x1:
                seg = 17 if (x - x0) % 46 else 9
                dcore.rectangle([x, y + 1, min(x + seg, x1), y + 1], fill=blend(c, (255, 255, 255), 0.4) + (255,))
                x += seg + 7
    else:
        # Original vertical neon signage: fat bars bloomed for glow, with a brighter crisp core.
        def signage(gd):
            for i, c in enumerate(accent):
                x = 26 + i * 96
                gd.rectangle([x, 22, x + 11, horizon - 16], fill=c + (255,))
                gd.rectangle([x - 16, 30 + i * 12, x + 52, 34 + i * 12], fill=c + (170,))
        img.alpha_composite(_bloom(W, H, signage, 5))
        dcore = ImageDraw.Draw(img, "RGBA")
        for i, c in enumerate(accent):
            x = 26 + i * 96
            dcore.rectangle([x + 4, 22, x + 7, horizon - 16], fill=blend(c, (255, 255, 255), 0.35) + (255,))

    # Glowing horizon where the wall meets the floor.
    img.alpha_composite(_bloom(W, H, lambda gd: gd.rectangle([0, horizon - 2, W, horizon + 2], fill=accent[0] + (210,)), 6))

    # Reflective floor: its own dimmer gradient. Non-HUD themes also reflect the vertical signs.
    floor = _vgradient(W, H - horizon, blend(wall, accent[0], 0.07), shade(wall, 0.45))
    if not hud:
        def reflections(gd):
            for i, c in enumerate(accent):
                gd.rectangle([26 + i * 96, 0, 37 + i * 96, H - horizon], fill=c + (60,))
        floor.alpha_composite(_bloom(W, H - horizon, reflections, 7))
    img.paste(floor, (0, horizon))

    # Two crowd layers, both standing on the floor: a dense, small, dimly back-lit rank far
    # off, and a larger near rank cropped by the bottom edge. Rims are dim (blended toward
    # the wall) so they read as a backlit crowd, not bright outlines.
    img = _crowd_layer(img, pal, n=20, baseline=H - 2, scale=2, body=shade(wall, 0.5), rim=blend(wall, accent[2], 0.3), seed=7)
    img = _crowd_layer(img, pal, n=11, baseline=H + 34, scale=3, body=shade(wall, 0.22), rim=blend(wall, accent[0], 0.45), seed=21)

    if hud:
        # Three reticles hovering over the crowd, one per accent, each framing a target's head.
        # Bloomed glow under crisp brackets — the chrome's "lock acquired" tick, in the art.
        spots = [(accent[0], 50, 96), (accent[1], 159, 86), (accent[2], 252, 106)]
        def reticles(gd):
            for c, rx, ry in spots:
                _draw_reticle(gd, (rx - 13, ry - 17, rx + 13, ry + 17), c + (255,), length=7, th=2)
        img.alpha_composite(_bloom(W, H, reticles, 3))
        reticles(ImageDraw.Draw(img, "RGBA"))

    img = up(img)
    img = _vignette(img, pal["vignette"])
    return img

def lobby_bg(pal):
    # The waiting room as a sleek one-point-perspective light corridor: clean concentric
    # frames receding to a glowing vanishing point dead centre, with guide lines running
    # from the corners through every frame corner. It fills the frame edge-to-edge with
    # quiet geometry and leaves the centre luminous, so the card sits in the lit doorway at
    # the end of the hall. Palette-driven: each theme keeps its own accent identity.
    W, H = 320, 180
    wall = pal["wall"]
    accent = pal["accent"]
    cx, cy = W // 2, H // 2

    # Deep gradient: lighter at the vanishing centre is faked by a soft bloom below, so the
    # base ramp just darkens toward the floor for grounding.
    img = _vgradient(W, H, shade(wall, 0.62), shade(wall, 0.92))

    # The light at the end of the corridor — a soft bloom the card will sit over. HUD themes
    # glow cyan (the chrome's "you / primary" colour, so the doorway is the same light the UI
    # uses); other themes keep their lime vanishing point.
    glow_acc = accent[0] if pal.get("hud") else accent[2]
    img.alpha_composite(_bloom(W, H, lambda gd: gd.ellipse(
        [cx - 30, cy - 30, cx + 30, cy + 30], fill=blend(wall, vivify(glow_acc), 0.85) + (150,)), 20))

    vacc = [vivify(c) for c in accent]   # brightness-equalised accents, so every theme reads

    def corridor(gd):
        # Guide lines from each corner to the vanishing point. Because every frame is the
        # full frame scaled about the centre, these pass cleanly through all frame corners.
        for corner in [(0, 0), (W, 0), (0, H), (W, H)]:
            gd.line([corner, (cx, cy)], fill=blend(wall, vacc[2], 0.7) + (90,), width=1)
        # Concentric frames from the vanishing point outward; the nearer (larger) a frame,
        # the brighter and more opaque, so the corridor reads as coming toward the viewer.
        steps = 8
        for i in range(steps):
            f = 0.13 + (1.0 - 0.13) * (i / (steps - 1))   # 0→point, 1→full frame
            hw, hh = f * (W / 2), f * (H / 2)
            a = int(80 + 175 * f)
            gd.rectangle([cx - hw, cy - hh, cx + hw, cy + hh], outline=vacc[i % len(vacc)] + (a,), width=1)

    # Draw the corridor once, crisp; use a dimmed blurred copy underneath as the glow and lay
    # the crisp lines on top at full strength so they read hard-edged rather than fuzzy.
    sharp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    corridor(ImageDraw.Draw(sharp))
    glow = sharp.filter(ImageFilter.GaussianBlur(2))
    glow.putalpha(glow.split()[3].point(lambda v: int(v * 0.55)))
    img.alpha_composite(glow)
    img.alpha_composite(sharp)

    # No baked reticle here: the lobby card wears its own `.dg-reticle--lime` corner brackets
    # (game_html/show.html.heex), so the card's lime lock-on sits inside this cyan-lit
    # doorway — the bracket/glow colour contrast is the framing, no duplicate needed.
    img = up(img)
    img = _vignette(img, pal["vignette"])
    return img

# ----------------------------------------------------------------------------
# cache-busting version
# ----------------------------------------------------------------------------
def pack_version(base, files):
    """A short content hash over the pack's runtime files. Emitted into theme.json as
    `version`; the client appends it as `?v=…` to every asset URL (game.mjs) and the home
    page does the same for menu_bg, so regenerated art busts the browser cache. These paths
    are raw strings, not phx.digest'd, so without this a redeploy serves stale art."""
    h = hashlib.md5()
    for f in sorted(files):
        p = os.path.join(base, f)
        if os.path.exists(p):
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()[:10]

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
    # Each theme is one self-contained folder under priv/static/themes/<key>/.
    base = os.path.join(repo, "priv", "static", "themes", theme_key)
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
        # The ammo icon + reticle tint the client loads (paths relative to this folder).
        "ui": {
            "bullet": pal.get("bullet", "bullet.png"),
            "reticle": pal.get("reticle", "#ff5577"),
        },
        "palette": {
            "wall": pal["wall"], "floor": pal["floor"], "accent": pal["accent"],
        },
        "note": "Cosmetic variants are NOT correlated with human/bot identity. "
                "Assign a random variant per character at spawn, server-side.",
    }

    # Audio lives in this folder too, but is generated separately (see tools/asset-gen).
    # Only reference tracks that actually exist so a fresh art-only pack falls back to the
    # default theme's music client-side rather than 404ing to silence.
    audio = {}
    if os.path.exists(os.path.join(base, "menu_loop.mp3")):
        audio["menuLoop"] = "menu_loop.mp3"
    stages = [f"game/stage{i}.mp3" for i in range(1, 5)]
    if all(os.path.exists(os.path.join(base, s)) for s in stages):
        audio["gameStages"] = stages
    if audio:
        manifest["audio"] = audio

    # Content version over everything the client loads, so a regenerated pack busts caches.
    version_files = list(manifest["assets"].values()) + [pal.get("bullet", "bullet.png")]
    version_files += list(audio.get("gameStages", [])) + ([audio["menuLoop"]] if "menuLoop" in audio else [])
    manifest["version"] = pack_version(base, version_files)

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
