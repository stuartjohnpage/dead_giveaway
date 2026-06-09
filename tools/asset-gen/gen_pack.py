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
from PIL import Image, ImageDraw, ImageFilter, ImageChops

# ----------------------------------------------------------------------------
# Theme definitions. Everything cosmetic flows from here.
# ----------------------------------------------------------------------------
THEMES = {
    "neon": {
        "display": "Neon Concourse",
        "blurb": "After-hours arcade concourse: black glass floor, humming neon, chrome trim.",
        "scene": "concourse",   # background composition archetype (see SCENES below)
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
        # ammo icon (in this folder) + reticle tint — emitted into theme.json's "ui".
        "bullet": "bullet.png",
        "reticle": "#ff5577",
    },
    "western": {
        "display": "Dead Man's Gulch",
        "blurb": "Sun-baked frontier main street: packed dirt, plank boardwalks, a noon showdown at the line.",
        "scene": "frontier",
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
        "scene": "orbital",
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
# Every theme names a `scene` — the composition archetype its backgrounds are built
# from (concourse / frontier / orbital). The palette still does all the colouring, so
# a new theme is still just a THEMES entry: a palette plus whichever scene fits.
AW, AH = 320, 180          # background design space (x4 = 1280x720)
BAND = 16                  # wall-band height = game.mjs FLOOR_TOP / SCALE_BG. In-game the
                           # floor TilingSprite covers y 16..163, so only the two bands
                           # (and the floor tile itself) are ever visible — they carry
                           # the arena's whole look.

def up(img):
    return img.resize((img.width * SCALE_BG, img.height * SCALE_BG), Image.NEAREST)

def _scene(pal, table):
    return table[pal.get("scene", "concourse")]

def _over(img, draw_fn):
    """Draw onto a transparent overlay and composite it down. Required for any
    semi-transparent ink: ImageDraw on an RGBA image REPLACES pixels (alpha included)
    rather than blending, which would punch translucent holes in the PNG."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    img.alpha_composite(layer)

def _hash01(x, y, seed=0):
    """Deterministic per-coordinate noise in [0,1) — seamless when fed wrapped coords."""
    n = (x * 374761393 + y * 668265263 + seed * 2654435761) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFF) / 65536.0

_BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]

def _dither_v(W, H, stops):
    """Vertical multi-stop gradient, ordered-dithered between quantised levels so the
    ramp reads as pixel-art shading instead of smooth banding. stops=[(t, colour), ...]
    with t running 0 (top) to 1 (bottom)."""
    img = Image.new("RGBA", (W, H))
    px = img.load()
    LEVELS = 5
    for y in range(H):
        t = y / max(1, H - 1)
        i = 0
        while i < len(stops) - 2 and t > stops[i + 1][0]:
            i += 1
        (t0, c0), (t1, c1) = stops[i], stops[i + 1]
        f = 0.0 if t1 <= t0 else max(0.0, min(1.0, (t - t0) / (t1 - t0)))
        v = f * LEVELS
        lo = blend(c0, c1, math.floor(v) / LEVELS)
        hi = blend(c0, c1, min(LEVELS, math.floor(v) + 1) / LEVELS)
        frac = v - math.floor(v)
        for x in range(W):
            th = (_BAYER[y % 4][x % 4] + 0.5) / 16
            px[x, y] = (hi if frac > th else lo) + (255,)
    return img

def _stars(d, box, n, seed, dim, bright):
    """Speckle a starfield into box=(x0, y0, x1, y1): mostly dim singles, every ninth a
    bright one with single-pixel sparkle arms."""
    rnd = random.Random(seed)
    x0, y0, x1, y1 = box
    for i in range(n):
        x, y = rnd.randrange(x0, x1), rnd.randrange(y0, y1)
        if i % 9 == 0:
            d.point((x, y), fill=bright)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                d.point((x + dx, y + dy), fill=dim)
        else:
            d.point((x, y), fill=dim)

# --- floor tiles (authored 32x32, shipped x2 so a texel is 2 design px) -----
def floor_tile(pal):
    tile = _scene(pal, {"concourse": _floor_concourse, "frontier": _floor_frontier,
                        "orbital": _floor_orbital})(pal)
    return tile.resize((tile.width * 2, tile.height * 2), Image.NEAREST)

def _floor_concourse(pal):
    # Black glass panels: quiet mottle, one soft diagonal sheen stripe, seams with a lit
    # inner edge and a pin-point LED per corner. Low contrast — the runners must pop.
    s = 32
    a, b = pal["floor"]
    img = Image.new("RGBA", (s, s))
    px = img.load()
    sheen = blend(a, (110, 130, 180), 0.10)
    for y in range(s):
        for x in range(s):
            c = blend(a, b, 0.65 * _hash01(x, y, 11))
            diag = (x + y) % s
            if diag in (10, 11, 12) or (diag in (9, 13) and _hash01(x, y, 5) > 0.5):
                c = blend(c, sheen, 0.35)
            px[x, y] = c + (255,)
    d = ImageDraw.Draw(img)
    d.line([(0, 0), (s - 1, 0)], fill=pal["grid_line"])
    d.line([(0, 0), (0, s - 1)], fill=pal["grid_line"])
    d.line([(1, 1), (s - 1, 1)], fill=blend(a, (130, 150, 200), 0.16))
    px[1, 1] = blend(pal["grid_line"], vivify(pal["accent"][0]), 0.5) + (255,)
    return img

def _floor_frontier(pal):
    # Packed dirt: a 4-tone speckle over coarse blotches, faint wheel-ruts along the
    # direction of travel, a few pebbles and dry-grass wisps. Organic — no grid.
    s = 32
    a, b = pal["floor"]
    tones = [a, b, shade(a, 1.05), shade(b, 0.93)]
    img = Image.new("RGBA", (s, s))
    px = img.load()
    for y in range(s):
        for x in range(s):
            blotch = _hash01((x // 8) % 4, (y // 8) % 4, 31)
            c = tones[int(_hash01(x, y, 17) * 4) % 4]
            c = blend(c, b, 0.30 * blotch)
            if y % 16 in (5, 6) and _hash01(x, y, 23) > 0.3:
                c = shade(c, 0.92)
            px[x, y] = c + (255,)
    rnd = random.Random(77)
    d = ImageDraw.Draw(img)
    for _ in range(5):
        x, y = rnd.randrange(s), rnd.randrange(s)
        d.point((x, y), fill=shade(b, 0.72))
        d.point(((x + 1) % s, y), fill=shade(a, 1.14))
    grass = blend(b, pal["accent"][2], 0.35)
    for _ in range(3):
        x, y = rnd.randrange(s), rnd.randrange(s)
        d.point((x, y), fill=shade(grass, 0.8))
        d.point((x, (y - 1) % s), fill=grass)
    return img

def _floor_orbital(pal):
    # Deck plating: 16px sub-panels in slightly different tones, embossed seams, corner
    # rivets and sparse wear scratches.
    s = 32
    a, b = pal["floor"]
    img = Image.new("RGBA", (s, s))
    px = img.load()
    for y in range(s):
        for x in range(s):
            q = (x // 16) + 2 * (y // 16)
            base = blend(a, b, (0.15, 0.55, 0.7, 0.3)[q])
            c = blend(base, b, 0.5 * _hash01(x, y, 41))
            if x % 16 == 0 or y % 16 == 0:
                c = shade(base, 0.62)
            elif y % 16 == 1:
                c = blend(base, pal["grid_line"], 0.55)
            px[x, y] = c + (255,)
    d = ImageDraw.Draw(img)
    for qx in (3, 19):
        for qy in (3, 19):
            for rx, ry in ((qx, qy), (qx + 9, qy), (qx, qy + 9), (qx + 9, qy + 9)):
                d.point((rx, ry), fill=blend(b, (140, 150, 165), 0.3))
                d.point((rx + 1, ry + 1), fill=shade(a, 0.75))
    rnd = random.Random(99)
    for _ in range(4):
        x, y = rnd.randrange(2, s - 5), rnd.randrange(2, s - 2)
        d.line([(x, y), (x + rnd.randrange(2, 4), y)], fill=blend(b, (140, 150, 165), 0.35))
    return img

# --- finish line: the 8px checker stays (legible race line in every theme); only the
# --- leading edge takes the theme's flavour ---------------------------------
def finish_line(pal):
    return up(_finish_strip(pal))

def _finish_strip(pal):
    w, h = 16, 180
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c0, c1 = pal["finish"]
    for y in range(h):
        for x in range(w):
            d.point((x, y), fill=c0 if (x // 8 + y // 8) % 2 == 0 else c1)
    scene = pal.get("scene", "concourse")
    if scene == "concourse":
        glow = vivify(pal["accent"][0])                     # a lit neon rail
        d.line([(0, 0), (0, h)], fill=glow)
        d.line([(1, 0), (1, h)], fill=blend(c1, glow, 0.45))
    elif scene == "frontier":
        rope = pal["accent"][2]                             # a knotted rope edge
        d.line([(0, 0), (0, h)], fill=rope)
        for y in range(0, h, 7):
            d.point((0, y), fill=shade(rope, 0.6))
        d.line([(1, 0), (1, h)], fill=shade(c1, 0.8))
    else:  # orbital: hazard-striped airlock edge
        amber = vivify(pal["accent"][0])
        for y in range(h):
            c = amber if (y // 4) % 2 == 0 else shade(c1, 0.7)
            d.point((0, y), fill=c)
            d.point((1, y), fill=c)
        d.line([(2, 0), (2, h)], fill=shade(c1, 0.6))
    return img

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
    img = _scene(pal, {"concourse": _arena_concourse, "frontier": _arena_frontier,
                       "orbital": _arena_orbital})(pal)
    return _vignette(up(img), pal["vignette"])

def _arena_base(pal):
    """Shared skeleton: the real floor tile previewed across the band the client's
    TilingSprite covers, plus the finish strip at its true in-game spot, so the
    standalone PNG matches the in-game composite. Bands are painted over by the scene."""
    img = Image.new("RGBA", (AW, AH), pal["wall"] + (255,))
    tile = floor_tile(pal).resize((BAND, BAND), Image.NEAREST)
    for ty in range(BAND, AH - BAND, BAND):
        for tx in range(0, AW, BAND):
            img.alpha_composite(tile, (tx, ty))
    fl = _finish_strip(pal).resize((16, AH - 2 * BAND), Image.NEAREST)
    img.alpha_composite(fl.crop((0, 0, AW - 306, fl.height)), (306, BAND))
    return img

def _rail(img, y, color, glow=True, posts=0, post_col=None):
    """The 2px field boundary at rows y..y+1: bloomed when it's a light, matte with
    grounding posts when it's paint on wood."""
    d = ImageDraw.Draw(img, "RGBA")
    if glow:
        img.alpha_composite(_bloom(AW, AH, lambda gd: gd.rectangle(
            [0, y, AW, y + 1], fill=color + (210,)), 2))
    d.rectangle([0, y, AW, y + 1], fill=color + (255,))
    d.line([(0, y), (AW, y)], fill=blend(color, (255, 255, 255), 0.4) + (255,))
    if posts:
        for x in range(6, AW, posts):
            d.rectangle([x, y, x + 1, y + 1], fill=(post_col or shade(color, 0.55)) + (255,))

def _band_crowd(d, x0, x1, feet, seed, body, rim, hat=False, helmet=False, gap=10):
    """Rail-side spectators for the wall bands: 5-7px head-and-shoulder silhouettes with
    the theme's headgear and a 1px lit crown. The crowd is the game's premise — the
    field should feel watched."""
    rnd = random.Random(seed)
    x = x0 + rnd.randrange(2, 6)
    while x < x1 - 7:
        if rnd.random() < 0.82:
            h = rnd.randrange(4, 6)
            top = feet - h - 3
            d.rectangle([x, feet - h, x + 5, feet], fill=body + (255,))
            d.rectangle([x + 1, top + 1, x + 4, feet - h], fill=body + (255,))
            cap = top + 1
            if hat:
                d.line([(x, top + 1), (x + 5, top + 1)], fill=body + (255,))
                d.rectangle([x + 1, top, x + 4, top], fill=body + (255,))
                cap = top
            elif helmet:
                d.line([(x + 1, top), (x + 4, top)], fill=body + (255,))
                cap = top
            d.line([(x + 1, cap), (x + 4, cap)], fill=rim + (255,))
        x += rnd.randrange(8, gap + 4)

def _gate_marks(img, d, pal, top_rows, bot_rows):
    """Start post (left, over the spawn) and finish chip (right, over the line) echoed
    on both wall bands — the bands' only hints at the race between them."""
    c = vivify(pal["accent"][0])
    f0, f1 = pal["finish"]
    for (y0, y1) in (top_rows, bot_rows):
        img.alpha_composite(_bloom(AW, AH, lambda gd: gd.rectangle(
            [5, y0, 7, y1], fill=c + (230,)), 2))
        d.rectangle([5, y0, 7, y1], fill=c + (255,))
        d.line([(5, y0), (5, y1)], fill=blend(c, (255, 255, 255), 0.45) + (255,))
        for i, x in enumerate(range(312, 320, 2)):
            for j, yy in enumerate(range(y0, y1 + 1, 2)):
                col = f0 if (i + j) % 2 == 0 else f1
                d.rectangle([x, yy, x + 1, yy + 1], fill=col + (255,))

def _arena_concourse(pal):
    # Far wall: lit back wall with neon sign boards and a gallery crowd behind the
    # magenta rail. Near wall: black glass catching the boards' reflections, an LED
    # ticker, the lime rail.
    img = _arena_base(pal)
    d = ImageDraw.Draw(img, "RGBA")
    wall, acc = pal["wall"], pal["accent"]
    rnd = random.Random(3)

    img.alpha_composite(_dither_v(AW, 14, [(0, shade(wall, 0.55)), (0.75, shade(wall, 1.5)),
                                           (1, shade(wall, 1.9))]), (0, 0))
    boards, glyphs = [], []
    x = 5
    while x < AW - 26:
        w = rnd.randrange(12, 24)
        c = acc[rnd.randrange(3)]
        boards.append((x, w, c))
        gx = x + 2
        while gx < x + w - 2:
            gw = rnd.randrange(2, 5)
            glyphs.append((gx, min(gx + gw, x + w - 2), c))
            gx += gw + 2
        x += w + rnd.randrange(7, 18)
    for bx, bw, _ in boards:
        d.rectangle([bx, 3, bx + bw, 9], fill=shade(wall, 0.4) + (255,))
        d.rectangle([bx, 3, bx + bw, 9], outline=(70, 75, 95, 255))
    def draw_glyphs(gd):
        for g0, g1, c in glyphs:
            gd.line([(g0, 5), (g1, 5)], fill=vivify(c) + (255,))
            gd.line([(g0, 7), (g1, 7)], fill=blend(vivify(c), (255, 255, 255), 0.5) + (255,))
    img.alpha_composite(_bloom(AW, AH, draw_glyphs, 2))
    draw_glyphs(d)
    d.line([(0, 11), (AW, 11)], fill=(80, 86, 108, 255))
    d.rectangle([0, 12, AW, 13], fill=blend(wall, (94, 84, 150), 0.4) + (255,))  # lit walkway
    _band_crowd(d, 0, AW, 13, seed=8, body=shade(wall, 0.4),
                rim=blend(wall, vivify(acc[0]), 0.75), gap=8)
    _rail(img, 14, vivify(acc[1]))

    by = AH - BAND
    img.alpha_composite(_dither_v(AW, BAND, [(0, shade(wall, 1.35)), (0.5, shade(wall, 1.0)),
                                             (1, shade(wall, 0.45))]), (0, by))
    for bx, bw, c in boards:                       # the boards' glow on the glass
        ref = Image.new("RGBA", (3, 12), vivify(c) + (50,))
        img.alpha_composite(_vfade_alpha(ref, 0.85, 0.0), (bx + bw // 2 - 1, by + 2))
    d.rectangle([0, by + 8, AW, by + 10], fill=shade(wall, 0.5) + (255,))   # LED housing
    d.line([(0, by + 8), (AW, by + 8)], fill=shade(wall, 1.9) + (255,))
    for x in range(6, AW - 4, 8):
        c = vivify(acc[(x // 8) % 3])
        bright = _hash01(x, 1, 27) > 0.72
        d.point((x, by + 9), fill=(c if bright else blend(c, wall, 0.55)) + (255,))
    _rail(img, by, vivify(acc[2]))

    _gate_marks(img, d, pal, (10, 13), (by + 4, by + 7))
    return img

def _arena_frontier(pal):
    # Far wall: a dusk sky sliver over false-front rooflines, lit windows, awnings and a
    # hatted boardwalk crowd. Near wall: the near boardwalk's planks. Painted rails.
    img = _arena_base(pal)
    d = ImageDraw.Draw(img, "RGBA")
    wall, acc = pal["wall"], pal["accent"]
    rnd = random.Random(4)

    img.alpha_composite(_dither_v(AW, 8, [(0, (208, 134, 86)), (1, (122, 66, 44))]), (0, 0))
    d.rectangle([0, 8, AW, 13], fill=wall + (255,))
    lit_windows = []
    x = 0
    while x < AW:
        bw = rnd.randrange(22, 42)
        roof = rnd.randrange(3, 7)
        col = blend(wall, (12, 7, 5), rnd.choice([0, 0.25, 0.45]))
        d.rectangle([x, roof, x + bw, 13], fill=col + (255,))
        if rnd.random() < 0.6:                     # false-front cornice
            d.line([(x + 1, roof - 1), (x + bw - 1, roof - 1)], fill=col + (255,))
        for wx in range(x + 3, x + bw - 2, rnd.randrange(5, 9)):
            if rnd.random() < 0.6:
                if rnd.random() < 0.55:
                    lit_windows.append((wx, roof + 3))
                else:
                    d.rectangle([wx, roof + 3, wx + 1, roof + 5], fill=shade(wall, 1.8) + (255,))
        if rnd.random() < 0.45:                    # awning stripes
            ay = min(roof + 7, 10)
            for sx in range(x + 2, x + bw - 3, 4):
                d.rectangle([sx, ay, sx + 1, ay + 1], fill=acc[1] + (255,))
                d.rectangle([sx + 2, ay, sx + 3, ay + 1], fill=(225, 210, 180, 255))
        x += bw + 1
    tx = 233                                       # water tower over the rooflines
    d.line([(tx + 1, 5), (tx + 1, 9)], fill=(14, 9, 6, 255))
    d.line([(tx + 6, 5), (tx + 6, 9)], fill=(14, 9, 6, 255))
    d.rectangle([tx, 1, tx + 7, 5], fill=(16, 10, 7, 255))
    d.line([(tx - 1, 1), (tx + 8, 1)], fill=(26, 16, 10, 255))
    d.line([(tx + 7, 2), (tx + 7, 4)], fill=blend((16, 10, 7), (208, 134, 86), 0.35) + (255,))
    warm = blend(acc[0], (255, 240, 200), 0.35)
    def windows(gd):
        for wx, wy in lit_windows:
            gd.rectangle([wx, wy, wx + 1, wy + 2], fill=warm + (255,))
    img.alpha_composite(_bloom(AW, AH, windows, 1))
    windows(d)
    plank = (96, 72, 44)
    d.rectangle([0, 12, AW, 13], fill=plank + (255,))   # far boardwalk edge
    for sx in range(0, AW, 7):
        d.point((sx, 13), fill=shade(plank, 0.6))
    _band_crowd(d, 0, AW, 13, seed=9, body=(38, 24, 16), rim=blend((38, 24, 16), vivify(acc[2]), 0.7),
                hat=True, gap=11)
    _rail(img, 14, acc[1], glow=False, posts=24, post_col=shade(acc[1], 0.6))

    by = AH - BAND
    _rail(img, by, acc[2], glow=False, posts=24, post_col=shade(acc[2], 0.6))
    for yy in range(by + 2, AH):                   # near boardwalk planks
        row = (yy - by - 2) % 4
        for x in range(AW):
            seg = (x + 13 * ((yy - by - 2) // 4)) // 34
            tone = 0.82 + 0.3 * _hash01(seg, (yy - by - 2) // 4, 57)
            c = shade(plank, tone * (0.62 if row == 3 else 1.0))
            if row != 3 and _hash01(x, yy, 71) > 0.985:
                c = shade(c, 0.7)                  # knots
            d.point((x, yy), fill=c + (255,))
        if row == 0:
            for jx in range(int(_hash01((yy - by) // 4, 0, 61) * 34), AW, 34):
                d.point((jx, yy), fill=shade(plank, 0.5))
                d.point((jx, yy + 1), fill=shade(plank, 0.5))
                d.point((jx, yy + 2), fill=shade(plank, 0.5))
    img.alpha_composite(Image.new("RGBA", (AW, 2), (0, 0, 0, 70)), (0, by + 2))

    _gate_marks(img, d, pal, (10, 13), (by + 4, by + 7))
    return img

def _arena_orbital(pal):
    # Far wall: a viewport strip of stars between struts, a pipe run, status LEDs and
    # hazard tape over the alert-red rail. Near wall: deck plating with sagging cables,
    # vents and the signal-blue rail.
    img = _arena_base(pal)
    d = ImageDraw.Draw(img, "RGBA")
    wall, acc = pal["wall"], pal["accent"]
    steel, hi = (52, 60, 72), (86, 96, 110)

    d.rectangle([0, 0, AW, 1], fill=shade(wall, 0.6) + (255,))
    d.rectangle([0, 2, AW, 9], fill=(5, 8, 16, 255))
    _stars(d, (1, 3, AW - 1, 9), 60, 5, (90, 110, 150, 255), (210, 225, 255, 255))
    d.line([(0, 2), (AW, 2)], fill=(60, 70, 85, 255))
    d.line([(0, 9), (AW, 9)], fill=(60, 70, 85, 255))
    d.rectangle([0, 10, AW, 13], fill=shade(wall, 1.25) + (255,))
    d.rectangle([0, 10, AW, 11], fill=(66, 76, 90, 255))    # pipe run
    d.line([(0, 10), (AW, 10)], fill=(104, 116, 132, 255))
    leds = []
    for x in range(18, AW - 4, 38):                          # struts
        d.rectangle([x, 2, x + 2, 13], fill=steel + (255,))
        d.line([(x, 2), (x, 13)], fill=hi + (255,))
        d.point((x + 1, 4), fill=(28, 32, 42, 255))
        d.point((x + 1, 7), fill=(28, 32, 42, 255))
        d.rectangle([x - 1, 10, x + 3, 11], fill=shade(steel, 0.8) + (255,))
        leds.append(x + 9)
    for i, x in enumerate(leds):                             # status LEDs
        c = [vivify(acc[0]), vivify(acc[1]), vivify(acc[2])][i % 3]
        if i % 4 == 3:
            c = shade(c, 0.35)                               # a dead one — derelict
        d.point((x, 12), fill=c + (255,))
        d.point((x + 1, 12), fill=blend(c, wall, 0.6) + (255,))
    amber = vivify(acc[0])
    for x in range(0, AW, 6):                                # hazard tape
        d.line([(x, 13), (x + 2, 13)], fill=shade(amber, 0.85) + (255,))
        d.line([(x + 3, 13), (x + 5, 13)], fill=(26, 22, 16, 255))
    _rail(img, 14, vivify(acc[1]))

    by = AH - BAND
    _rail(img, by, vivify(acc[2]))
    img.alpha_composite(_dither_v(AW, 14, [(0, shade(wall, 1.5)), (1, shade(wall, 0.7))]), (0, by + 2))
    for x in range(0, AW, 24):                               # deck panel seams
        d.line([(x, by + 2), (x, AH)], fill=shade(wall, 0.55) + (255,))
    d.line([(0, by + 8), (AW, by + 8)], fill=shade(wall, 0.55) + (255,))
    d.line([(0, by + 9), (AW, by + 9)], fill=shade(wall, 1.7) + (255,))
    for x0 in range(2, AW, 46):                              # sagging cable run
        x1 = min(x0 + 46, AW - 2)
        mid = (x0 + x1) // 2
        for (ca, sag) in (((20, 24, 32), 2), ((52, 40, 32), 1)):
            d.line([(x0, by + 4), (mid, by + 4 + sag)], fill=ca + (255,))
            d.line([(mid, by + 4 + sag), (x1, by + 4)], fill=ca + (255,))
        d.rectangle([x0 - 1, by + 3, x0, by + 5], fill=(78, 88, 102, 255))
    rnd = random.Random(15)
    for x in range(10, AW - 12, 46):                         # vents + telltale LEDs
        if rnd.random() < 0.7:
            d.rectangle([x, by + 11, x + 6, by + 13], fill=shade(wall, 0.5) + (255,))
            d.line([(x + 1, by + 12), (x + 5, by + 12)], fill=shade(wall, 1.6) + (255,))
        else:
            c = vivify(acc[rnd.randrange(3)])
            d.point((x + 3, by + 12), fill=c + (255,))
    _gate_marks(img, d, pal, (10, 13), (by + 4, by + 7))
    return img

def _silhouette(fr, body, rim):
    """Recolour a drawn agent frame into a backlit silhouette: its shape filled with a
    flat dark `body`, with a 1px `rim` light along its top contour only — light spilling
    over heads and shoulders from whatever glows behind, not a sticker outline."""
    a = fr.split()[3]
    mask = a.point(lambda v: 255 if v > 40 else 0)
    sil = Image.new("RGBA", fr.size, (0, 0, 0, 0))
    sil.paste(Image.new("RGBA", fr.size, body + (255,)), (0, 0), mask)
    px_s, px_a = sil.load(), a.load()
    w, h = fr.size
    for x in range(w):                  # topmost opaque pixel per column only — no
        for y in range(h):              # speckle from interior gaps (chins, armpits)
            if px_a[x, y] > 40:
                px_s[x, y] = rim + (255,)
                break
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
        # silhouette AFTER the resize so the rim stays 1px — light catching crowns and
        # shoulders, not a fat sticker outline
        fr = _silhouette(fr.resize((FW * sc, FH * sc), Image.NEAREST), body, rim)
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
    # Atmospheric only — the page renders all text/UI on top (behind heavy darkening on
    # home, so big shapes and bright glows are what survive).
    img = _scene(pal, {"concourse": _menu_concourse, "frontier": _menu_frontier,
                       "orbital": _menu_orbital})(pal)
    return _vignette(up(img), pal["vignette"])

def _menu_concourse(pal):
    # An after-hours arcade street: two skyline ranks with lit windows, neon sign boards
    # over a glowing horizon, black-glass floor smearing their light, the crowd backlit.
    W, H = AW, AH
    wall, acc = pal["wall"], pal["accent"]
    horizon = 126
    img = _dither_v(W, H, [(0, (5, 4, 12)), (0.45, blend(wall, (24, 16, 52), 0.7)),
                           (1, blend(wall, acc[0], 0.16))])
    d = ImageDraw.Draw(img, "RGBA")

    def skyline(hmin, hmax, col, win_cols, win_p, seed):
        r = random.Random(seed)
        x = -r.randrange(4, 10)
        while x < W:
            bw = r.randrange(14, 30)
            bh = r.randrange(hmin, hmax)
            d.rectangle([x, horizon - bh, x + bw, horizon], fill=col + (255,))
            if r.random() < 0.35:                   # rooftop mast
                ax = x + r.randrange(2, max(3, bw - 2))
                d.line([(ax, horizon - bh - r.randrange(3, 7)), (ax, horizon - bh)], fill=col + (255,))
            for wy in range(horizon - bh + 2, horizon - 4, 4):
                for wx in range(x + 2, x + bw - 1, 3):
                    if r.random() < win_p:
                        d.point((wx, wy), fill=r.choice(win_cols) + (255,))
            x += bw + r.randrange(2, 6)
    skyline(30, 54, blend(wall, (16, 12, 34), 0.5), [blend(acc[0], wall, 0.45)], 0.10, 31)
    skyline(12, 30, shade(wall, 0.55), [blend(acc[1], wall, 0.5), blend(acc[2], wall, 0.5)], 0.08, 32)

    # Sign boards: three tall verticals (the menu's signature) and two low horizontals,
    # each a chrome-framed plate whose neon glyph segments do the glowing.
    signs = [("v", 58, 30, 96, vivify(acc[0])), ("v", 152, 26, 100, vivify(acc[1])),
             ("v", 246, 32, 94, vivify(acc[2])), ("h", 96, 56, 30, vivify(acc[1])),
             ("h", 196, 64, 26, vivify(acc[2]))]
    for kind, x, y0, e, c in signs:
        if kind == "v":
            d.rectangle([x - 1, y0 - 2, x + 10, e + 2], fill=shade(wall, 0.4) + (255,), outline=(70, 76, 96, 255))
        else:
            d.rectangle([x - 2, y0 - 2, x + e + 2, y0 + 7], fill=shade(wall, 0.4) + (255,), outline=(70, 76, 96, 255))
    def glyphs(gd):
        r2 = random.Random(5)
        for kind, x, y0, e, c in signs:
            if kind == "v":
                yy = y0 + 2
                while yy < e - 2:
                    gh = r2.randrange(2, 6)
                    gd.rectangle([x + 2, yy, x + 7, min(yy + gh, e - 2)], fill=c + (255,))
                    yy += gh + 3
            else:
                xx = x + 1
                while xx < x + e - 1:
                    gw = r2.randrange(2, 6)
                    gd.rectangle([xx, y0 + 1, min(xx + gw, x + e - 1), y0 + 4], fill=c + (255,))
                    xx += gw + 3
    img.alpha_composite(_bloom(W, H, glyphs, 4))
    img.alpha_composite(_bloom(W, H, glyphs, 1))
    glyphs(d)
    _over(img, lambda gd: [gd.line([(x + 4, y0 + 2), (x + 4, e - 2)],
                                   fill=blend(c, (255, 255, 255), 0.55) + (130,))
                           for kind, x, y0, e, c in signs if kind == "v"])

    hor = vivify(acc[0])
    img.alpha_composite(_bloom(W, H, lambda gd: gd.rectangle(
        [0, horizon - 1, W, horizon + 1], fill=hor + (220,)), 5))
    d.line([(0, horizon), (W, horizon)], fill=blend(hor, (255, 255, 255), 0.5) + (255,))

    img.paste(_dither_v(W, H - horizon - 1, [(0, blend(wall, acc[0], 0.18)), (0.4, shade(wall, 0.8)),
                                             (1, (4, 3, 10))]), (0, horizon + 1))
    for kind, x, y0, e, c in signs:                 # signs smeared down the glass
        if kind == "v":
            ref = Image.new("RGBA", (10, 34), c + (70,))
            img.alpha_composite(_vfade_alpha(ref, 0.8, 0.0), (x, horizon + 1))
    _over(img, lambda gd: [gd.line([(0, y), (W, y)], fill=blend(wall, (160, 180, 230), 0.4) + (40,))
                           for y in range(horizon + 3, H, 5) if _hash01(0, y, 9) > 0.45])

    img = _crowd_layer(img, pal, n=24, baseline=H - 4, scale=2, body=(7, 6, 16),
                       rim=blend(hor, wall, 0.25), seed=7)
    img = _crowd_layer(img, pal, n=12, baseline=H + 34, scale=3, body=(3, 3, 8),
                       rim=blend(hor, wall, 0.62), seed=21)
    return img

def _menu_frontier(pal):
    # High-noon main street: a banded sun at the end of the road between silhouetted
    # false-front rows, mesas on the horizon, dust haze, the townsfolk's hats backlit.
    W, H = AW, AH
    acc = pal["accent"]
    horizon = 118
    img = Image.new("RGBA", (W, H))
    img.paste(_dither_v(W, horizon, [(0, (50, 22, 30)), (0.4, (122, 54, 44)),
                                     (0.75, (208, 116, 64)), (1.0, (246, 184, 108))]), (0, 0))
    d = ImageDraw.Draw(img, "RGBA")

    sx, sy, r = W // 2, 86, 18
    img.alpha_composite(_bloom(W, H, lambda gd: gd.ellipse(
        [sx - r, sy - r, sx + r, sy + r], fill=(255, 226, 150, 235)), 8))
    d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=(255, 232, 160, 255))
    d.ellipse([sx - r + 2, sy - r + 2, sx + r - 3, sy + r - 6], fill=(255, 244, 196, 255))
    for gy, gh in ((sy + 6, 2), (sy + 11, 3)):      # the banded cut-outs
        band = img.getpixel((4, gy))[:3]
        d.rectangle([sx - r - 2, gy, sx + r + 2, gy + gh - 1], fill=band + (255,))
    _over(img, lambda gd: [gd.line([(sx - r - 10, hy), (sx + r + 10, hy)],
                                   fill=(255, 210, 140, 90)) for hy in (sy - 4, sy + 2)])

    def mesas(hmax, col, seed):
        r2 = random.Random(seed)
        x = -20
        while x < W + 20:
            mw = r2.randrange(26, 60)
            mh = r2.randrange(hmax // 2, hmax)
            s = r2.randrange(4, 9)
            d.polygon([(x, horizon), (x + s, horizon - mh), (x + mw - s, horizon - mh),
                       (x + mw, horizon)], fill=col + (255,))
            x += mw + r2.randrange(10, 30)
    mesas(20, (150, 70, 52), 61)
    mesas(11, (96, 44, 36), 62)

    img.paste(_dither_v(W, H - horizon, [(0, (188, 120, 70)), (0.25, (124, 70, 44)),
                                         (1, (44, 24, 16))]), (0, horizon))
    _over(img, lambda gd: [gd.line([(sx + rx * 3, H), (sx + rx, horizon + 6)],
                                   fill=(70, 40, 26, 120)) for rx in (-66, -24, 26, 70)])

    def storefronts(side, seed):
        r2 = random.Random(seed)
        for depth in (3, 2, 1, 0):                  # far first, near drawn over
            bw = (44, 34, 26, 20)[depth] + r2.randrange(0, 8)
            bh = (78, 56, 40, 28)[depth] + r2.randrange(0, 6)
            base = horizon + (42, 24, 12, 5)[depth]
            edge = 0 if side < 0 else W
            inset = sum((46, 36, 27, 21)[k] for k in range(depth))
            x0 = edge + side * inset if side > 0 else edge + inset
            x0 = x0 - bw if side > 0 else x0
            col = blend((24, 13, 9), (70, 34, 24), depth * 0.22)
            top = base - bh
            d.rectangle([x0, top, x0 + bw, base], fill=col + (255,))
            d.line([(x0 - 1, top), (x0 + bw + 1, top)], fill=shade(col, 1.45) + (255,))  # cornice
            r3 = random.Random(seed * 7 + depth)
            for wx in range(x0 + 3, x0 + bw - 2, 6):
                if r3.random() < 0.5:
                    lit = r3.random() < 0.6
                    wc = (255, 196, 110) if lit else (14, 8, 6)
                    d.rectangle([wx, top + 4, wx + 1, top + 6], fill=wc + (255,))
            if depth < 2:                           # porch posts on the near fronts
                for px_ in range(x0 + 2, x0 + bw - 1, 7):
                    d.line([(px_, base - 8), (px_, base)], fill=shade(col, 0.55) + (255,))
                d.line([(x0, base - 8), (x0 + bw, base - 8)], fill=shade(col, 0.7) + (255,))
    storefronts(-1, 63)
    storefronts(+1, 64)

    for px_, ph in ((92, 34), (228, 30)):           # telegraph poles
        d.line([(px_, horizon - ph), (px_, horizon + 8)], fill=(20, 11, 8, 255))
        d.line([(px_ - 4, horizon - ph + 3), (px_ + 4, horizon - ph + 3)], fill=(20, 11, 8, 255))
        d.line([(px_ - 3, horizon - ph + 6), (px_ + 3, horizon - ph + 6)], fill=(20, 11, 8, 255))
    _over(img, lambda gd: gd.line([(96, horizon - 31), (160, horizon - 24), (224, horizon - 27)],
                                  fill=(20, 11, 8, 110)))

    img.alpha_composite(_bloom(W, H, lambda gd: gd.rectangle(
        [0, horizon - 3, W, horizon + 8], fill=(255, 190, 120, 110)), 6))

    img = _crowd_layer(img, pal, n=22, baseline=H - 4, scale=2, body=(24, 13, 9),
                       rim=(255, 214, 140), seed=7)
    img = _crowd_layer(img, pal, n=12, baseline=H + 34, scale=3, body=(13, 8, 6),
                       rim=(214, 140, 80), seed=21)
    return img

def _menu_orbital(pal):
    # The observation deck: a wall-wide viewport onto a starfield and a rim-lit planet,
    # hazard-striped struts, a flickering emergency strip, helmeted crowd in silhouette.
    W, H = AW, AH
    wall, acc = pal["wall"], pal["accent"]
    img = _dither_v(W, H, [(0, (3, 5, 11)), (0.6, (7, 10, 19)), (1, (12, 17, 28))])
    d = ImageDraw.Draw(img, "RGBA")
    _stars(d, (0, 8, W, 150), 130, 19, (88, 102, 132, 255), (215, 228, 255, 255))

    pcx, pcy, pr = 235, 262, 168                    # planet limb cresting over the crowd
    d.ellipse([pcx - pr, pcy - pr, pcx + pr, pcy + pr], fill=(17, 23, 38, 255))
    rim = vivify(acc[2])
    img.alpha_composite(_bloom(W, H, lambda gd: gd.arc(
        [pcx - pr, pcy - pr, pcx + pr, pcy + pr], 180, 360, fill=rim + (230,), width=2), 4))
    d.arc([pcx - pr, pcy - pr, pcx + pr, pcy + pr], 180, 360,
          fill=blend(rim, (255, 255, 255), 0.35) + (255,))
    _over(img, lambda gd: [gd.arc([pcx - pr + off, pcy - pr + off, pcx + pr - off, pcy + pr - off],
                                  200, 340, fill=blend(rim, (10, 14, 24), 0.45) + (al,))
                           for off, al in ((4, 70), (9, 45))])

    _over(img, lambda gd: (gd.line([(60, 18), (150, 64)], fill=(190, 210, 240, 26)),
                           gd.line([(180, 30), (262, 74)], fill=(190, 210, 240, 20))))

    steel, hi = (36, 42, 54), (64, 74, 90)
    amber = vivify(acc[0])
    for x in (34, 282):                             # viewport struts
        d.rectangle([x, 0, x + 5, H], fill=steel + (255,))
        d.line([(x, 0), (x, H)], fill=hi + (255,))
        for ry in range(12, H, 24):
            d.point((x + 3, ry), fill=hi + (255,))
        for sy_ in range(118, 134, 4):              # hazard base stripes
            d.rectangle([x, sy_, x + 5, sy_ + 1], fill=amber + (255,))
            d.rectangle([x, sy_ + 2, x + 5, sy_ + 3], fill=(26, 22, 16, 255))
    d.rectangle([0, 0, W, 5], fill=(30, 36, 46, 255))
    d.line([(0, 5), (W, 5)], fill=(58, 68, 84, 255))
    img.alpha_composite(_bloom(W, H, lambda gd: gd.rectangle(
        [118, 2, 204, 3], fill=amber + (230,)), 3))
    d.rectangle([118, 2, 204, 3], fill=amber + (255,))
    for gx in (146, 178):                           # the strip's dying flicker
        d.rectangle([gx, 2, gx + 5, 3], fill=blend(amber, (30, 36, 46), 0.75) + (255,))
    for i, x in enumerate(range(12, W - 12, 22)):   # frame status LEDs
        d.point((x, 4), fill=vivify(acc[i % 3]) + (255,))

    img = _crowd_layer(img, pal, n=20, baseline=H - 4, scale=2, body=(6, 9, 15),
                       rim=blend(rim, (255, 255, 255), 0.2), seed=7)
    img = _crowd_layer(img, pal, n=11, baseline=H + 34, scale=3, body=(3, 5, 9),
                       rim=blend(amber, wall, 0.25), seed=21)
    return img

# The lobby is one shared idea — a one-point corridor receding to a lit end where the
# card sits — materialised per scene: neon arch gates, lantern-lit timber frames, or
# octagonal airlock ribs. Bold shapes only: it lives behind a 2px blur + black/65 scrim.
GATE_STEPS = (0.16, 0.27, 0.40, 0.55, 0.72, 0.90, 1.08)   # innermost → past the viewer

def _gate_rect(f):
    return [AW / 2 - f * AW / 2, AH / 2 - f * AH / 2, AW / 2 + f * AW / 2, AH / 2 + f * AH / 2]

def _crisp_glow(img, draw_fn, blur=2, dim=0.55):
    """Draw once crisp over a dimmed blurred copy of itself — hard edges with a halo."""
    sharp = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(sharp))
    glow = sharp.filter(ImageFilter.GaussianBlur(blur))
    glow.putalpha(glow.split()[3].point(lambda v: int(v * dim)))
    img.alpha_composite(glow)
    img.alpha_composite(sharp)

def _corridor_joins(img, col, floor_a=110):
    """Floor edges linking consecutive gates' bottom corners — grounds the corridor
    without rebuilding a wall-to-wall X."""
    def lines(gd):
        for i in range(len(GATE_STEPS) - 1):
            ra, rb = _gate_rect(GATE_STEPS[i]), _gate_rect(GATE_STEPS[i + 1])
            gd.line([(ra[0], ra[3]), (rb[0], rb[3])], fill=col + (floor_a,))
            gd.line([(ra[2], ra[3]), (rb[2], rb[3])], fill=col + (floor_a,))
    _over(img, lines)

def lobby_bg(pal):
    img = _scene(pal, {"concourse": _lobby_concourse, "frontier": _lobby_frontier,
                       "orbital": _lobby_orbital})(pal)
    return _vignette(up(img), pal["vignette"])

def _lobby_concourse(pal):
    # Neon arch gates down a glass hall, each catching on the floor as a short smear.
    W, H = AW, AH
    wall, acc = pal["wall"], pal["accent"]
    vacc = [vivify(c) for c in acc]
    cx, cy = W // 2, H // 2
    img = _dither_v(W, H, [(0, shade(wall, 0.6)), (1, shade(wall, 1.05))])
    d = ImageDraw.Draw(img, "RGBA")
    img.alpha_composite(_bloom(W, H, lambda gd: gd.ellipse(
        [cx - 54, cy - 30, cx + 54, cy + 30], fill=blend(wall, vacc[2], 0.9) + (150,)), 20))
    _corridor_joins(img, blend(wall, vacc[2], 0.55))
    def gates(gd):
        for i, f in enumerate(GATE_STEPS):
            a = int(70 + 185 * min(1, f))
            c = vacc[i % 3]
            r = _gate_rect(f)
            gd.rounded_rectangle(r, radius=max(2, int(9 * f)), outline=c + (a,), width=1)
            gd.line([(cx - 2, r[1]), (cx + 2, r[1])], fill=blend(c, (255, 255, 255), 0.6) + (a,))
    _crisp_glow(img, gates)
    for i, f in enumerate(GATE_STEPS[:-1]):         # gate light pooling on the glass
        r = _gate_rect(f)
        c = vacc[i % 3]
        for gx in (int(r[0]), int(r[2])):
            ref = Image.new("RGBA", (1, 5), c + (80,))
            img.alpha_composite(_vfade_alpha(ref, 0.8, 0.0), (gx, int(r[3]) + 1))
    return img

def _lobby_frontier(pal):
    # Lantern-lit timber frames receding to daylight — the gulch's mine adit. Warm wood,
    # joint pegs, dust hanging in the light.
    W, H = AW, AH
    acc = pal["accent"]
    cx, cy = W // 2, H // 2
    gold = vivify(acc[2])
    img = _dither_v(W, H, [(0, (20, 12, 9)), (1, (40, 25, 16))])
    d = ImageDraw.Draw(img, "RGBA")
    img.alpha_composite(_bloom(W, H, lambda gd: gd.ellipse(
        [cx - 56, cy - 30, cx + 56, cy + 30], fill=blend((32, 20, 13), gold, 0.85) + (170,)), 20))
    _corridor_joins(img, (120, 82, 46), floor_a=150)
    wood = (158, 112, 62)
    def beams(gd):
        for i, f in enumerate(GATE_STEPS):
            a = int(130 + 125 * min(1, f))
            r = _gate_rect(f)
            t = 1 if f < 0.3 else 2
            tone = blend(wood, acc[0], 0.10 if i % 2 else 0.0)
            gd.rectangle([r[0], r[1], r[2], r[1] + t], fill=tone + (a,))               # lintel
            gd.rectangle([r[0], r[3] - t, r[2], r[3]], fill=shade(tone, 0.6) + (a,))   # sill
            gd.rectangle([r[0], r[1], r[0] + t, r[3]], fill=shade(tone, 0.85) + (a,))  # posts
            gd.rectangle([r[2] - t, r[1], r[2], r[3]], fill=shade(tone, 0.85) + (a,))
            gd.line([(r[0], r[1]), (r[2], r[1])], fill=blend(gold, (255, 255, 255), 0.25) + (a,))
            gd.line([(r[0] + t, r[1]), (r[0] + t, r[3])],                              # lamplit post edges
                    fill=blend(gold, wood, 0.45) + (int(a * 0.8),))
            gd.line([(r[2] - t, r[1]), (r[2] - t, r[3])],
                    fill=blend(gold, wood, 0.45) + (int(a * 0.8),))
            for (nx, ny) in ((r[0] + 1, r[1] + 1), (r[2] - 1, r[1] + 1),
                             (r[0] + 1, r[3] - 1), (r[2] - 1, r[3] - 1)):
                gd.point((nx, ny), fill=(20, 13, 8, a))                                # joint pegs
    _crisp_glow(img, beams, blur=2, dim=0.4)
    lamp = vivify(acc[0])
    for i, off in ((4, -38), (5, 30)):              # lanterns on the gates the card clears
        r = _gate_rect(GATE_STEPS[i])
        lx, ly = int(cx + off * GATE_STEPS[i]), int(r[1]) + 3
        img.alpha_composite(_bloom(W, H, lambda gd, lx=lx, ly=ly: gd.rectangle(
            [lx - 1, ly, lx + 1, ly + 2], fill=lamp + (220,)), 3))
        d.line([(lx, int(r[1])), (lx, ly - 1)], fill=(20, 13, 8, 255))
        d.rectangle([lx - 1, ly - 1, lx + 1, ly + 3], fill=(24, 16, 10, 255))
        d.rectangle([lx - 1, ly + 1, lx + 1, ly + 2], fill=blend(lamp, (255, 255, 220), 0.45) + (255,))
    def motes(gd):
        rnd = random.Random(8)
        for _ in range(46):                         # dust motes in the lamplight
            mx = cx + int((rnd.random() - 0.5) * 150)
            my = cy + int((rnd.random() - 0.5) * 90)
            dist = abs(mx - cx) / 75 + abs(my - cy) / 45
            if dist < 1.2 and rnd.random() > dist * 0.6:
                gd.point((mx, my), fill=(255, 224, 168, rnd.randrange(40, 110)))
    _over(img, motes)
    return img

def _lobby_orbital(pal):
    # Octagonal airlock ribs marching toward a lit lock, vertex status lights, hazard
    # chamfers on the nearest full rib.
    W, H = AW, AH
    acc = pal["accent"]
    vacc = [vivify(c) for c in acc]
    cx, cy = W // 2, H // 2
    img = _dither_v(W, H, [(0, (7, 10, 17)), (1, (15, 20, 30))])
    d = ImageDraw.Draw(img, "RGBA")
    img.alpha_composite(_bloom(W, H, lambda gd: gd.ellipse(
        [cx - 50, cy - 28, cx + 50, cy + 28], fill=(170, 205, 240, 165)), 18))
    _corridor_joins(img, (58, 68, 84), floor_a=120)
    def oct_pts(r, cut=0.34):
        x0, y0, x1, y1 = r
        c = cut * min(x1 - x0, y1 - y0) / 2
        return [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c),
                (x1 - c, y1), (x0 + c, y1), (x0, y1 - c), (x0, y0 + c)]
    def ribs(gd):
        for i, f in enumerate(GATE_STEPS):
            a = int(80 + 175 * min(1, f))
            r = _gate_rect(f)
            pts = oct_pts(r)
            gd.line(pts + [pts[0]], fill=(96, 108, 124, a), width=2, joint="curve")
            inner = oct_pts([r[0] + 2, r[1] + 2, r[2] - 2, r[3] - 2])
            gd.line(inner + [inner[0]], fill=vacc[i % 3] + (int(a * 0.85),), width=1, joint="curve")
    _crisp_glow(img, ribs, blur=2, dim=0.5)
    for i in (1, 3, 5):                             # vertex status lights
        pts = oct_pts(_gate_rect(GATE_STEPS[i]))
        for j, (px_, py_) in enumerate(pts):
            c = vacc[(i + j) % 3]
            d.point((int(px_), int(py_)), fill=blend(c, (255, 255, 255), 0.4) + (255,))
    amber = vacc[0]
    pts = oct_pts(_gate_rect(0.90))                 # hazard dashes on the chamfers
    for k in (1, 3, 5, 7):
        (xa, ya), (xb, yb) = pts[k], pts[(k + 1) % 8]
        for t in range(0, 8, 2):
            f0, f1 = t / 8, (t + 1) / 8
            d.line([(xa + (xb - xa) * f0, ya + (yb - ya) * f0),
                    (xa + (xb - xa) * f1, ya + (yb - ya) * f1)], fill=shade(amber, 0.9) + (255,))
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
    # Each theme is one self-contained folder under priv/static/themes/<key>/.
    base = os.path.join(repo, "priv", "static", "themes", theme_key)
    os.makedirs(base, exist_ok=True)

    sheet, atlas = build_atlas(pal, theme_key)
    sheet.save(os.path.join(base, "agents.png"))
    with open(os.path.join(base, "agents.json"), "w") as f:
        json.dump(atlas, f, indent=1)
        f.write("\n")

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
        # ui.crosshair is appended below only if the sprite exists (gen_crosshair.py).
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

    # The themed crosshair (#48) is generated separately (gen_crosshair.py); only
    # reference it if it exists so a fresh pack falls back to the procedural reticle.
    if os.path.exists(os.path.join(base, "crosshair.png")):
        manifest["ui"]["crosshair"] = "crosshair.png"

    # Audio lives in this folder too, but is generated separately (see tools/asset-gen).
    # Only reference tracks that actually exist so a fresh art-only pack falls back to the
    # default theme's music client-side rather than 404ing to silence. Same deal for the
    # themed gunshot (#48, gen_gunshot.py): absent → the default crack.
    audio = {}
    if os.path.exists(os.path.join(base, "menu_loop.mp3")):
        audio["menuLoop"] = "menu_loop.mp3"
    stages = [f"game/stage{i}.mp3" for i in range(1, 5)]
    if all(os.path.exists(os.path.join(base, s)) for s in stages):
        audio["gameStages"] = stages
    if os.path.exists(os.path.join(base, "shot.mp3")):
        audio["shot"] = "shot.mp3"
    if audio:
        manifest["audio"] = audio

    with open(os.path.join(base, "theme.json"), "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

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
