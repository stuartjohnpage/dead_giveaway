#!/usr/bin/env python3
"""
Dead Giveaway - procedural pixel-art theme-pack generator.

Palette-driven. Produces, for one theme:
  - agents.png + agents.json  (Pixi spritesheet atlas: 12 variants x {idle, walk(4), run(6), dropped})
  - floor_tile.png            (seamless tileable arena floor)
  - finish_line.png           (vertical finish strip)
  - arena_bg.png              (full top-down room, 1280x720)
  - menu_bg.png               (1280x720; the lobby backdrop reuses it)
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
        "blurb": "Sun-baked badlands: packed dirt, distant peaks, a showdown at sundown.",
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

# --- desert silhouettes (frontier arena + menu) ------------------------------
def _peak(d, x0, x1, apex_x, apex_y, y_base, col, seed=5):
    """One mountain in silhouette: a jagged ridge stepping up to the apex, a notched
    secondary summit beside it — rugged, not a clean pyramid."""
    rnd = random.Random(seed)
    def ridge(xa, xb):
        pts = []
        for f, jag in ((0.35, -rnd.randrange(3, 10)), (0.68, rnd.randrange(2, 7))):
            x = xa + (xb - xa) * f
            y = y_base + (apex_y - y_base) * f + jag
            pts.append((x, min(y, y_base - 1)))
        return pts
    pts = [(x0, y_base)] + ridge(x0, apex_x) + [(apex_x, apex_y)]
    pts.append((apex_x + rnd.randrange(4, 9), apex_y + rnd.randrange(3, 8)))
    pts += list(reversed(ridge(x1, apex_x)))
    pts.append((x1, y_base))
    d.polygon(pts, fill=col + (255,))

def _bare_tree(d, x, y, h, col, seed=3):
    """A dead tree in silhouette: a trunk forking into gnarled boughs and twigs."""
    rnd = random.Random(seed)
    c = col + (255,)
    trunk_top = y - max(3, int(h * 0.42))
    d.line([(x, y), (x, trunk_top)], fill=c, width=2 if h >= 18 else 1)
    tips = [(x, trunk_top)]
    for i in range(5 if h >= 18 else 3):
        bx, by = tips[rnd.randrange(len(tips))]
        side = -1 if i % 2 == 0 else 1
        mx_, my_ = bx + side * rnd.randrange(2, max(3, h // 4)), by - rnd.randrange(2, max(3, h // 4))
        ex, ey = mx_ + side * rnd.randrange(1, 3), my_ - rnd.randrange(1, max(2, h // 5))
        d.line([(bx, by), (mx_, my_)], fill=c)
        d.line([(mx_, my_), (ex, ey)], fill=c)
        if rnd.random() < 0.7:
            d.line([(mx_, my_), (mx_ - side, my_ - rnd.randrange(1, 3))], fill=c)
        tips.append((mx_, my_))

def _cactus(d, x, y, h, col):
    """A saguaro in silhouette: trunk and one or two upturned arms."""
    c = col + (255,)
    d.line([(x, y), (x, y - h)], fill=c, width=2 if h >= 12 else 1)
    if h >= 6:
        ay = y - int(h * 0.55)
        d.line([(x - 2, ay), (x - 2, ay - max(2, h // 3))], fill=c)
        d.line([(x - 2, ay), (x, ay)], fill=c)
    if h >= 10:
        ay = y - int(h * 0.35)
        d.line([(x + 2, ay), (x + 2, ay - max(2, h // 4))], fill=c)
        d.line([(x, ay), (x + 2, ay)], fill=c)

def _tumbleweed(d, x, y, r, col):
    """A tumbleweed: a scraggly ball of arcs."""
    c = col + (255,)
    d.ellipse([x - r, y - r, x + r, y + r], outline=c)
    d.arc([x - r + 1, y - r + 2, x + r - 1, y + r], 20, 200, fill=c)
    d.arc([x - r + 2, y - r, x + r, y + r - 2], 160, 340, fill=c)
    d.line([(x - r + 2, y + 1), (x + r - 2, y - 1)], fill=c)

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

def _band_crowd(d, x0, x1, feet, seed, body, rim, gap=10):
    """Rail-side spectators for the wall bands: 5-7px head-and-shoulder silhouettes with
    a 1px lit crown. The crowd is the game's premise — the field should feel watched."""
    rnd = random.Random(seed)
    x = x0 + rnd.randrange(2, 6)
    while x < x1 - 7:
        if rnd.random() < 0.82:
            h = rnd.randrange(4, 6)
            top = feet - h - 3
            d.rectangle([x, feet - h, x + 5, feet], fill=body + (255,))
            d.rectangle([x + 1, top + 1, x + 4, feet - h], fill=body + (255,))
            d.line([(x + 1, top + 1), (x + 4, top + 1)], fill=rim + (255,))
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
    # Far wall: open badlands — the sun setting on the horizon between dark peaks, a
    # dead tree, a saguaro or two. Near wall: the same plain running on in shadow.
    # Painted fence rails bound the field.
    img = _arena_base(pal)
    d = ImageDraw.Draw(img, "RGBA")
    acc = pal["accent"]

    img.alpha_composite(_dither_v(AW, 12, [(0, (84, 38, 34)), (0.5, (164, 84, 54)),
                                           (1, (224, 142, 88))]), (0, 0))
    sun_x = 84
    img.alpha_composite(_bloom(AW, AH, lambda gd: gd.ellipse(
        [sun_x - 5, 6, sun_x + 5, 16], fill=(255, 226, 150, 235)), 4))
    d.ellipse([sun_x - 5, 6, sun_x + 5, 16], fill=(255, 232, 162, 255))
    d.ellipse([sun_x - 4, 7, sun_x + 4, 14], fill=(255, 244, 198, 255))
    _peak(d, -12, 70, 34, 2, 12, (120, 56, 40), seed=11)     # hazy far peak
    _peak(d, 6, 64, 38, 4, 12, (54, 27, 21), seed=12)
    _peak(d, 224, 312, 264, 3, 12, (54, 27, 21), seed=13)
    d.rectangle([0, 12, AW, 13], fill=(64, 31, 22, 255))     # the plain behind the fence
    for x in range(0, AW, 3):
        if _hash01(x, 0, 33) > 0.72:
            d.point((x, 12), fill=(84, 42, 28, 255))
    _bare_tree(d, 152, 13, 13, (16, 9, 6), seed=6)
    _cactus(d, 40, 13, 10, (20, 11, 8))
    _cactus(d, 286, 13, 10, (20, 11, 8))
    _rail(img, 14, acc[1], glow=False, posts=24, post_col=shade(acc[1], 0.6))

    by = AH - BAND
    _rail(img, by, acc[2], glow=False, posts=24, post_col=shade(acc[2], 0.6))
    img.alpha_composite(_dither_v(AW, 14, [(0, (56, 30, 19)), (1, (30, 16, 11))]), (0, by + 2))
    for yy in range(by + 2, AH):                   # night-side scrub
        for x in range(AW):
            n = _hash01(x, yy, 83)
            if n > 0.94:
                d.point((x, yy), fill=(22, 12, 8, 255))
            elif n < 0.05:
                d.point((x, yy), fill=(74, 42, 26, 255))
    rnd = random.Random(21)
    for _ in range(9):                             # stones
        x, yy = rnd.randrange(4, AW - 4), rnd.randrange(by + 5, AH - 2)
        d.point((x, yy), fill=(18, 10, 7, 255))
        d.point((x + 1, yy), fill=(66, 38, 24, 255))
    grass = blend((30, 16, 11), vivify(acc[2]), 0.3)
    for _ in range(12):                            # dry tufts
        x, yy = rnd.randrange(4, AW - 4), rnd.randrange(by + 4, AH - 1)
        d.point((x, yy), fill=grass + (255,))
        d.point((x, yy - 1), fill=shade(grass, 0.7) + (255,))
    _cactus(d, 70, by + 13, 7, (16, 9, 6))
    _cactus(d, 248, by + 12, 6, (16, 9, 6))
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
    # An empty cyberpunk cityscape: three tower ranks full of lit windows under a
    # crescent moon, neon boards and rooftop beacons, a wet street holding the glow.
    # Nobody out tonight.
    W, H = AW, AH
    wall, acc = pal["wall"], pal["accent"]
    vacc = [vivify(c) for c in acc]
    horizon = 132
    img = _dither_v(W, H, [(0, (4, 3, 10)), (0.55, (16, 11, 34)),
                           (1, blend(wall, acc[1], 0.12))])
    d = ImageDraw.Draw(img, "RGBA")
    _stars(d, (0, 3, W, 60), 46, 23, (62, 68, 104, 255), (140, 150, 200, 255))

    mx, my, mr = 251, 25, 9                         # crescent moon
    sky_c = img.getpixel((mx - mr - 6, my))[:3]
    img.alpha_composite(_bloom(W, H, lambda gd: gd.ellipse(
        [mx - mr, my - mr, mx + mr, my + mr], fill=(210, 225, 255, 150)), 6))
    d.ellipse([mx - mr, my - mr, mx + mr, my + mr], fill=(224, 234, 255, 255))
    d.ellipse([mx - mr - 4, my - mr - 3, mx + mr - 4, my + mr - 3], fill=sky_c + (255,))

    boards, beacons = [], []
    def rank(hmin, hmax, col, wins, win_p, seed, masts=False, signage=False):
        r = random.Random(seed)
        x = -r.randrange(2, 8)
        while x < W:
            bw = r.randrange(13, 27)
            bh = r.randrange(hmin, hmax)
            top = horizon - bh
            d.rectangle([x, top, x + bw, horizon], fill=col + (255,))
            if masts and r.random() < 0.4:
                ax = x + r.randrange(2, max(3, bw - 2))
                ah = r.randrange(4, 9)
                d.line([(ax, top - ah), (ax, top)], fill=col + (255,))
                if r.random() < 0.55:
                    beacons.append((ax, top - ah))
            if signage and bh > 24 and r.random() < 0.4:
                boards.append((x + r.randrange(2, max(3, bw - 6)),
                               top + r.randrange(3, bh - 18), r.randrange(3)))
            for wy in range(top + 2, horizon - 3, 3):
                for wx in range(x + 2, x + bw - 1, 3):
                    if r.random() < win_p:
                        d.point((wx, wy), fill=r.choice(wins) + (255,))
            x += bw + r.randrange(2, 6)
    rank(34, 66, blend(wall, (22, 17, 46), 0.6), [blend(acc[0], wall, 0.55)], 0.05, 31)
    rank(18, 46, (10, 8, 24), [blend(acc[0], wall, 0.35), blend(acc[1], wall, 0.4)],
         0.085, 32, masts=True, signage=True)
    rank(6, 26, (6, 5, 15), [blend(acc[2], wall, 0.45)], 0.05, 33, masts=True)

    for bx_, by_, ci in boards:                     # neon boards on the tower faces
        d.rectangle([bx_, by_, bx_ + 4, by_ + 13], fill=(5, 4, 12, 255), outline=(58, 62, 82, 255))
    def board_glyphs(gd):
        for bx_, by_, ci in boards:
            for i in range(4):
                gy = by_ + 2 + i * 3
                gd.rectangle([bx_ + 1, gy, bx_ + 3, gy + 1], fill=vacc[ci] + (255,))
    img.alpha_composite(_bloom(W, H, board_glyphs, 2))
    board_glyphs(d)
    def beacon_dots(gd):
        for ax, ay in beacons:
            gd.point((ax, ay), fill=vacc[1] + (255,))
    img.alpha_composite(_bloom(W, H, beacon_dots, 2))
    beacon_dots(d)

    bbx, bby = 148, 56                              # the big rooftop billboard
    d.line([(bbx + 5, bby + 10), (bbx + 5, bby + 26)], fill=(46, 50, 68, 255))
    d.line([(bbx + 27, bby + 10), (bbx + 27, bby + 26)], fill=(46, 50, 68, 255))
    d.rectangle([bbx, bby, bbx + 32, bby + 10], fill=(6, 5, 14, 255), outline=(70, 76, 96, 255))
    def billboard(gd):
        r3 = random.Random(9)
        for gy, c, end in ((bby + 2, vacc[0], 30), (bby + 6, vacc[1], 26)):
            xx = bbx + 2
            while xx < bbx + end:
                gw = r3.randrange(2, 6)
                gd.rectangle([xx, gy, min(xx + gw, bbx + end), gy + 2], fill=c + (255,))
                xx += gw + 2
    img.alpha_composite(_bloom(W, H, billboard, 3))
    billboard(d)

    hor = vacc[0]
    img.alpha_composite(_bloom(W, H, lambda gd: gd.rectangle(
        [0, horizon - 1, W, horizon], fill=hor + (190,)), 4))
    d.line([(0, horizon), (W, horizon)], fill=blend(hor, (255, 255, 255), 0.45) + (255,))

    img.paste(_dither_v(W, H - horizon - 1, [(0, blend(wall, acc[0], 0.16)), (0.45, shade(wall, 0.75)),
                                             (1, (3, 2, 8))]), (0, horizon + 1))
    streaks = [(bbx + 8, vacc[0]), (bbx + 22, vacc[1])] + \
              [(bx_ + 1, vacc[ci]) for bx_, by_, ci in boards] + \
              [(ax - 1, vacc[1]) for ax, ay in beacons[:4]]
    for sx_, c in streaks:                          # the city smeared on the wet street
        ref = Image.new("RGBA", (3, 16 + (sx_ % 13)), c + (72,))
        img.alpha_composite(_vfade_alpha(ref, 0.8, 0.0), (max(0, min(W - 3, sx_)), horizon + 1))
    _over(img, lambda gd: [gd.line([(0, y), (W, y)], fill=blend(wall, (160, 180, 230), 0.4) + (40,))
                           for y in range(horizon + 3, H, 5) if _hash01(0, y, 9) > 0.45])
    return img

def _menu_frontier(pal):
    # Empty desert at sundown: the banded sun sinking onto the horizon between dark
    # peaks, a dead tree, saguaros, a tumbleweed mid-roll. Nobody for miles.
    W, H = AW, AH
    acc = pal["accent"]
    horizon = 118
    img = Image.new("RGBA", (W, H))
    img.paste(_dither_v(W, horizon, [(0, (50, 22, 30)), (0.4, (122, 54, 44)),
                                     (0.75, (208, 116, 64)), (1.0, (246, 184, 108))]), (0, 0))
    d = ImageDraw.Draw(img, "RGBA")

    sx, sy, r = W // 2, horizon - 12, 20            # setting: the disc sits on the horizon
    img.alpha_composite(_bloom(W, H, lambda gd: gd.ellipse(
        [sx - r, sy - r, sx + r, sy + r], fill=(255, 226, 150, 235)), 8))
    d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=(255, 232, 160, 255))
    d.ellipse([sx - r + 2, sy - r + 2, sx + r - 3, sy + r - 6], fill=(255, 244, 196, 255))
    for gy, gh in ((sy + 4, 2), (sy + 9, 3)):       # the banded cut-outs
        band = img.getpixel((4, gy))[:3]
        d.rectangle([sx - r - 2, gy, sx + r + 2, gy + gh - 1], fill=band + (255,))
    _over(img, lambda gd: [gd.line([(sx - r - 10, hy), (sx + r + 10, hy)],
                                   fill=(255, 210, 140, 90)) for hy in (sy - 5, sy + 1)])

    def mesas(hmax, col, seed):                     # a low haze ridge behind the peaks
        r2 = random.Random(seed)
        x = -20
        while x < W + 20:
            mw = r2.randrange(26, 60)
            mh = r2.randrange(hmax // 2, hmax)
            s = r2.randrange(4, 9)
            d.polygon([(x, horizon), (x + s, horizon - mh), (x + mw - s, horizon - mh),
                       (x + mw, horizon)], fill=col + (255,))
            x += mw + r2.randrange(10, 30)
    mesas(12, (158, 76, 54), 61)
    _peak(d, 4, 122, 56, 62, horizon, (74, 36, 28), seed=14)    # the two mountains
    _peak(d, 196, 312, 254, 72, horizon, (62, 31, 25), seed=15)

    img.paste(_dither_v(W, H - horizon, [(0, (188, 120, 70)), (0.25, (124, 70, 44)),
                                         (1, (44, 24, 16))]), (0, horizon))
    _over(img, lambda gd: [gd.line([(sx + rx * 3, H), (sx + rx, horizon + 6)],
                                   fill=(70, 40, 26, 120)) for rx in (-24, 26)])

    img.alpha_composite(_bloom(W, H, lambda gd: gd.rectangle(
        [0, horizon - 3, W, horizon + 8], fill=(255, 190, 120, 110)), 6))

    _bare_tree(d, 66, 164, 42, (18, 10, 7), seed=8)             # the dead tree
    _cactus(d, 30, 148, 11, (30, 16, 11))
    _cactus(d, 246, 170, 24, (24, 13, 9))
    _cactus(d, 302, 152, 8, (34, 18, 12))
    _tumbleweed(d, 284, 162, 5, (44, 24, 15))
    return img

def _menu_orbital(pal):
    # The observation deck, deserted: a wall-wide viewport onto a starfield and a
    # rim-lit planet, hazard-striped struts, a flickering emergency strip. Nobody home.
    W, H = AW, AH
    acc = pal["accent"]
    img = _dither_v(W, H, [(0, (3, 5, 11)), (0.6, (7, 10, 19)), (1, (12, 17, 28))])
    d = ImageDraw.Draw(img, "RGBA")
    _stars(d, (0, 8, W, 150), 130, 19, (88, 102, 132, 255), (215, 228, 255, 255))

    pcx, pcy, pr = 235, 262, 168                    # planet limb low in the viewport
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
    return img

# The lobby reuses the menu backdrop (manifest lobbyBackground → menu_bg.png): one
# strong establishing shot per theme, shown behind the lobby's blur + black/65 scrim.

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
            # the lobby shows the menu shot behind its scrim — one backdrop per theme
            "lobbyBackground": "menu_bg.png",
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
    make_gif(pal, 0, "walk", os.path.join(outdir, "preview_walk.gif"))
    make_gif(pal, 3, "run", os.path.join(outdir, "preview_run.gif"))

    print("OK theme=", theme_key)
    print("atlas size:", sheet.size, "frames:", len(atlas["frames"]))
    print("written to:", base)

if __name__ == "__main__":
    main()
