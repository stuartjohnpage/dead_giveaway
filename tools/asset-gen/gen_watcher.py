#!/usr/bin/env python3
"""Per-theme Red Light watcher (#53): the figure on the finish line that spins to face
the crowd. One small Pixi atlas per theme — watcher.png + watcher.json — with the three
animations the client drives off the snapshot's light:

  idle  (green)   — facing away from the crowd, dim and quiet
  spin  (wind-up) — turning: the warning (paired with windup.mp3, gen_windup.py)
  watch (red)     — facing the crowd, eye lit: moving past the grace is death

Frames are 48x48 at native pixel scale (the client renders x2 nearest — a ~96px
landmark, head and shoulders above any agent). Readability rule: green reads dim/cool
from behind, red reads hot — the state must land at a glance from across the field,
so every theme also echoes it in a base/lamp accent.

Theme fictions: neon = chrome sentinel cam-totem; western = vulture on a fence post;
station = sentry-eye turret. Same pipeline as the rest of the pack: palettes and
PIL primitives in, no art skills required.

Usage: python tools/asset-gen/gen_watcher.py [repo_root]
Writes priv/static/themes/<key>/watcher.{png,json}, patches each theme.json
(assets.watcher), and drops preview_watcher.png in the cwd (or PREVIEW_DIR).
"""
import json, os, sys
from PIL import Image, ImageChops, ImageDraw, ImageFilter

FW = FH = 48
CX = 24
ANIM = {"idle": 4, "spin": 4, "watch": 4}
COLS = sum(ANIM.values())


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def blend(a, b, f):
    return tuple(max(0, min(255, int(a[i] * (1 - f) + b[i] * f))) for i in range(3))


def add_outline(layer, color):
    """1px dark outline from the layer's own alpha — the agents' legibility trick."""
    a = layer.split()[3]
    grown = a.filter(ImageFilter.MaxFilter(3))
    edge = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    pe, pa, pg = edge.load(), a.load(), grown.load()
    for y in range(layer.size[1]):
        for x in range(layer.size[0]):
            if pg[x, y] > 40 and pa[x, y] <= 40:
                pe[x, y] = (*color, 255)
    return Image.alpha_composite(edge, layer)


def bloom(draw_fn, radius, alpha=0.8):
    """A blurred glow layer: draw the brights via draw_fn, gaussian them out."""
    layer = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    g = layer.filter(ImageFilter.GaussianBlur(radius))
    g.putalpha(g.split()[3].point(lambda p: int(p * alpha)))
    return g


def masked(layer, mask_img):
    """Clip `layer` to `mask_img`'s silhouette (e.g. a visor band onto a head)."""
    layer = layer.copy()
    layer.putalpha(ImageChops.multiply(layer.split()[3], mask_img.split()[3]))
    return layer


def base_shadow(img):
    sh = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([CX - 13, 42, CX + 13, 47], fill=(0, 0, 0, 70))
    return Image.alpha_composite(img, sh)


# ----------------------------------------------------------------------------
# neon — the Sentinel: a chrome cam-totem, visor sweeping round to a hot eye
# ----------------------------------------------------------------------------
NEON = {
    "chrome": (58, 60, 78), "hi": (96, 100, 126), "dark": (30, 30, 44),
    "cyan": (0, 230, 230), "mag": (255, 60, 200), "red": (255, 50, 100),
    "outline": (8, 6, 14),
}


def _neon_body(d, ring, blink_on):
    """Plinth + neon base ring + column + neck — shared by every state; the ring
    colour is the ground-level echo of the light."""
    d.rounded_rectangle([CX - 9, 41, CX + 9, 46], radius=2, fill=NEON["dark"])
    ring_c = ring if blink_on else shade(ring, 0.35)
    d.line([(CX - 8, 43), (CX + 8, 43)], fill=ring_c)
    d.rectangle([CX - 4, 24, CX + 4, 41], fill=NEON["chrome"])
    d.line([(CX - 3, 24), (CX - 3, 41)], fill=NEON["hi"])
    for sy in (30, 36):
        d.line([(CX - 4, sy), (CX + 4, sy)], fill=NEON["dark"])
    d.rectangle([CX - 2, 21, CX + 2, 24], fill=NEON["dark"])


def _neon_head(bob):
    """The head silhouette on its own layer, so face bands can be clipped to it."""
    head = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    ImageDraw.Draw(head).rounded_rectangle(
        [CX - 11, 5 + bob, CX + 11, 22 + bob], radius=8, fill=NEON["chrome"]
    )
    return head


def neon(state, t):
    img = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    fig = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    d = ImageDraw.Draw(fig)
    bob = (0, -1, -1, 0)[t] if state == "idle" else 0

    ring = {"idle": NEON["cyan"], "spin": NEON["mag"], "watch": NEON["red"]}[state]
    _neon_body(d, ring, blink_on=(state != "spin" or t % 2 == 0))

    head = _neon_head(bob)
    hd = ImageDraw.Draw(head)
    if state == "idle":
        # The back of the head: a darker shell, centre seam, arena light rimming the
        # right edge, a tail antenna with a lazy magenta blink.
        hd.rounded_rectangle([CX - 11, 5 + bob, CX + 11, 22 + bob], radius=8, fill=NEON["dark"])
        hd.line([(CX, 6 + bob), (CX, 21 + bob)], fill=shade(NEON["dark"], 0.7))
        hd.arc([CX - 11, 5 + bob, CX + 11, 22 + bob], -60, 60, fill=blend(NEON["dark"], NEON["cyan"], 0.5))
        fig.alpha_composite(head)
        d.line([(CX + 6, 5 + bob), (CX + 6, 1 + bob)], fill=NEON["dark"])
        d.point((CX + 6, 0 + bob), fill=NEON["mag"] if t < 2 else shade(NEON["mag"], 0.4))
    elif state == "spin":
        # The visor band sweeps across the face as the head comes round.
        vx = (CX - 12, CX - 6, CX + 1, CX + 7)[t]
        band = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
        bd = ImageDraw.Draw(band)
        bd.ellipse([vx - 8, 8, vx + 8, 20], fill=(16, 14, 26))
        bd.line([(vx - 5, 14), (vx + 5, 14)], fill=shade(NEON["red"], 0.6))
        fig.alpha_composite(Image.alpha_composite(head, masked(band, head)))
        # 1px motion ticks chasing the turn
        my = 12
        d.line([(CX - 17, my), (CX - 14, my)], fill=shade(NEON["hi"], 1.1 if t % 2 else 0.7))
        d.line([(CX + 14, my + 4), (CX + 17, my + 4)], fill=shade(NEON["hi"], 0.7 if t % 2 else 1.1))
    else:  # watch
        # Full face: black faceplate, one hot wide eye. Unmissable.
        plate = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
        pd = ImageDraw.Draw(plate)
        pd.ellipse([CX - 9, 8, CX + 9, 20], fill=(10, 9, 18))
        r = (5, 6, 7, 6)[t]
        pd.ellipse([CX - r, 14 - r // 2, CX + r, 14 + r // 2], fill=NEON["red"])
        pd.ellipse([CX - 2, 13, CX + 2, 15], fill=(255, 200, 220))
        fig.alpha_composite(Image.alpha_composite(head, masked(plate, head)))
        img = Image.alpha_composite(
            img, bloom(lambda g: g.ellipse([CX - r, 14 - r // 2, CX + r, 14 + r // 2], fill=NEON["red"]), 3)
        )

    fig = add_outline(fig, NEON["outline"])
    return Image.alpha_composite(base_shadow(img), fig)


# ----------------------------------------------------------------------------
# western — the Vulture: hunched on a fence post, flaring round at the wind-up
# ----------------------------------------------------------------------------
WEST = {
    "post": (92, 62, 36), "post_d": (70, 48, 28), "rope": (214, 180, 96),
    "feather": (26, 20, 18), "feather_hi": (52, 42, 36),
    "head": (150, 64, 48), "beak": (66, 54, 40), "eye": (255, 46, 36),
    "outline": (20, 12, 8),
}


def _west_post(d):
    d.rectangle([21, 23, 26, 45], fill=WEST["post"])
    d.line([(22, 23), (22, 45)], fill=shade(WEST["post"], 1.2))
    d.line([(25, 23), (25, 45)], fill=WEST["post_d"])
    d.rectangle([20, 21, 27, 23], fill=WEST["post_d"])
    for ry in (32, 33):
        d.line([(21, ry), (26, ry)], fill=shade(WEST["rope"], 0.75 if ry == 33 else 0.95))


def western(state, t):
    img = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    fig = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    d = ImageDraw.Draw(fig)
    _west_post(d)

    if state == "idle":
        # Tail to the crowd: a dark hunched back, bald head tucked low on the far side.
        bob = (0, 0, 1, 0)[t]
        d.ellipse([13, 8 + bob, 33, 23], fill=WEST["feather"])
        d.polygon([(7, 12 + bob), (15, 9 + bob), (15, 17 + bob)], fill=WEST["feather"])
        d.arc([14, 9 + bob, 32, 22], 200, 320, fill=WEST["feather_hi"])
        if t == 3:  # a feather ruffles
            d.point((19, 7 + bob), fill=WEST["feather_hi"])
        d.ellipse([29, 5 + bob, 37, 12 + bob], fill=shade(WEST["head"], 0.8))
        d.polygon([(37, 8 + bob), (41, 10 + bob), (37, 11 + bob)], fill=WEST["beak"])
        for nx in (29, 31):  # the neck-ruff collar
            d.point((nx, 12 + bob), fill=(196, 186, 162))
    elif state == "spin":
        # The flap-turn: wings flare wide and the head comes round to face the field.
        spread = (4, 9, 14, 9)[t]
        d.polygon([(CX - 6 - spread, 14 - spread), (CX - 3, 12), (CX - 7, 19)], fill=WEST["feather"])
        d.polygon([(CX + 6 + spread, 14 - spread), (CX + 3, 12), (CX + 7, 19)], fill=WEST["feather"])
        d.ellipse([15, 9, 33, 23], fill=WEST["feather"])
        d.ellipse([20, 3, 28, 11], fill=shade(WEST["head"], 0.9))
        d.polygon([(21, 10), (24, 13), (27, 10)], fill=WEST["beak"])
        if t >= 1:  # the eyes find you mid-turn
            d.point((21, 6), fill=WEST["eye"])
            d.point((26, 6), fill=WEST["eye"])
    else:  # watch
        # Facing the crowd: shoulders up like a cloak, bald red head low, eye burning.
        d.ellipse([15, 7, 35, 23], fill=WEST["feather"])
        d.ellipse([14, 4, 23, 13], fill=WEST["feather"])  # raised shoulder humps
        d.ellipse([26, 4, 35, 13], fill=WEST["feather"])
        d.polygon([(33, 12), (40, 10), (40, 16)], fill=WEST["feather"])  # tail, far side
        d.ellipse([9, 9, 18, 17], fill=WEST["head"])
        d.polygon([(10, 14), (5, 16), (10, 17)], fill=WEST["beak"])
        eye = WEST["eye"] if t % 2 == 0 else (255, 110, 70)
        d.point((12, 12), fill=eye)
        d.point((13, 12), fill=eye)
        if t % 2 == 0:  # flat pack, so the pulse is a 1px halo, not a glow
            for hx, hy in ((11, 11), (14, 11), (11, 13), (14, 13)):
                d.point((hx, hy), fill=(180, 60, 40))

    fig = add_outline(fig, WEST["outline"])
    return Image.alpha_composite(base_shadow(img), fig)


# ----------------------------------------------------------------------------
# station — the Sentry Eye: a turret pod that rotates its lens onto the field
# ----------------------------------------------------------------------------
STAT = {
    "steel": (60, 68, 82), "hi": (96, 106, 122), "dark": (34, 40, 52),
    "amber": (255, 150, 50), "red": (232, 72, 58), "blue": (96, 190, 220),
    "outline": (10, 12, 20),
}


def _stat_pylon(d):
    d.rectangle([CX - 4, 22, CX + 4, 41], fill=STAT["steel"])
    d.line([(CX - 3, 22), (CX - 3, 41)], fill=STAT["hi"])
    d.rectangle([CX - 7, 41, CX + 7, 45], fill=STAT["dark"])
    for x in range(CX - 7, CX + 8):  # hazard chevrons on the base
        if (x // 3) % 2 == 0:
            d.line([(x, 42), (x, 44)], fill=shade(STAT["amber"], 0.8))
    d.rectangle([CX - 2, 20, CX + 2, 22], fill=STAT["dark"])


def station(state, t):
    img = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    fig = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    d = ImageDraw.Draw(fig)
    _stat_pylon(d)

    pod = [CX - 13, 8, CX + 13, 21]
    d.rounded_rectangle(pod, radius=6, fill=STAT["steel"])
    d.line([(CX - 9, 9), (CX + 9, 9)], fill=STAT["hi"])  # top sheen
    lamp_box = [CX - 2, 4, CX + 2, 8]

    if state == "idle":
        # The pod's vented back; a slow blue heartbeat LED, warning lamp dark.
        for vx in (CX + 3, CX + 6, CX + 9):
            d.line([(vx, 11), (vx, 18)], fill=STAT["dark"])
        led = STAT["blue"] if t in (0, 1) else shade(STAT["blue"], 0.35)
        d.point((CX - 9, 14), fill=led)
        d.rectangle(lamp_box, fill=(40, 36, 30))
    elif state == "spin":
        # Vents slide as the pod rotates; the roof lamp strobes amber.
        for i in range(3):
            vx = CX + 9 - ((t * 5 + i * 6) % 18)
            d.line([(vx, 11), (vx, 18)], fill=STAT["dark"])
        d.line([(CX - 12, 11), (CX - 12, 18)], fill=STAT["hi"])  # leading edge catches light
        lamp_on = t % 2 == 0
        d.rectangle(lamp_box, fill=STAT["amber"] if lamp_on else (40, 36, 30))
        if lamp_on:
            img = Image.alpha_composite(img, bloom(lambda g: g.rectangle(lamp_box, fill=STAT["amber"]), 3, 0.6))
    else:  # watch
        # The lens rides the crowd: dark aperture, red iris pulsing, lamp held red.
        lx, ly = CX - 6, 14
        d.ellipse([lx - 6, ly - 6, lx + 6, ly + 6], fill=(18, 22, 30))
        d.ellipse([lx - 6, ly - 6, lx + 6, ly + 6], outline=STAT["hi"])
        r = (3, 4, 5, 4)[t]
        d.ellipse([lx - r, ly - r, lx + r, ly + r], fill=STAT["red"])
        d.point((lx + 1, ly - 1), fill=(255, 210, 200))
        if t == 2:
            d.ellipse([lx - 5, ly - 5, lx + 5, ly + 5], outline=shade(STAT["red"], 0.7))
        for vx in (CX + 7, CX + 10):  # a sliver of vents left on the trailing side
            d.line([(vx, 11), (vx, 18)], fill=STAT["dark"])
        d.rectangle(lamp_box, fill=STAT["red"])
        img = Image.alpha_composite(
            img, bloom(lambda g: (g.ellipse([lx - r, ly - r, lx + r, ly + r], fill=STAT["red"]),
                                  g.rectangle(lamp_box, fill=STAT["red"])), 3, 0.65)
        )

    fig = add_outline(fig, STAT["outline"])
    return Image.alpha_composite(base_shadow(img), fig)


# ----------------------------------------------------------------------------
# atlas + manifest + preview
# ----------------------------------------------------------------------------
THEMES = {"neon": neon, "western": western, "station": station}
PREVIEW_BG = {"neon": (18, 16, 32), "western": (124, 96, 60), "station": (44, 50, 60)}


def build_atlas(draw, theme_key):
    sheet = Image.new("RGBA", (COLS * FW, FH), (0, 0, 0, 0))
    frames, animations = {}, {}
    col = 0
    for pose in ("idle", "spin", "watch"):
        seq = []
        for t in range(ANIM[pose]):
            fr = draw(pose, t)
            x = col * FW
            sheet.paste(fr, (x, 0), fr)
            name = f"{pose}{t}"
            frames[name] = {
                "frame": {"x": x, "y": 0, "w": FW, "h": FH},
                "sourceSize": {"w": FW, "h": FH},
                "spriteSourceSize": {"x": 0, "y": 0, "w": FW, "h": FH},
            }
            seq.append(name)
            col += 1
        animations[pose] = seq
    atlas = {
        "frames": frames,
        "animations": animations,
        "meta": {
            "app": "deadgiveaway-genwatcher",
            "image": "watcher.png",
            "format": "RGBA8888",
            "size": {"w": COLS * FW, "h": FH},
            "scale": "1",
            "theme": theme_key,
            "frameSize": {"w": FW, "h": FH},
        },
    }
    return sheet, atlas


def patch_manifest(base):
    """Point the pack's theme.json at the watcher atlas (gen_pack.py emits the key
    itself for packs generated after #53; this covers the already-shipped ones)."""
    path = os.path.join(base, "theme.json")
    if not os.path.exists(path):
        return
    with open(path) as f:
        manifest = json.load(f)
    manifest.setdefault("assets", {})["watcher"] = "watcher.json"
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    outdir = os.environ.get("PREVIEW_DIR", ".")
    sc = 2
    cell_w, cell_h = FW * sc * COLS + 24, FH * sc + 34
    P = Image.new("RGBA", (cell_w, cell_h * len(THEMES) + 10), (10, 10, 14, 255))
    dp = ImageDraw.Draw(P)
    for i, (key, draw) in enumerate(THEMES.items()):
        sheet, atlas = build_atlas(draw, key)
        base = os.path.join(root, "priv", "static", "themes", key)
        os.makedirs(base, exist_ok=True)
        sheet.save(os.path.join(base, "watcher.png"))
        with open(os.path.join(base, "watcher.json"), "w") as f:
            json.dump(atlas, f, indent=1)
            f.write("\n")
        patch_manifest(base)
        y = 10 + i * cell_h
        dp.rectangle([10, y, 14 + FW * sc * COLS, y + FH * sc + 4], fill=PREVIEW_BG[key])
        big = sheet.resize((sheet.width * sc, sheet.height * sc), Image.NEAREST)
        P.alpha_composite(big, (12, y + 2))
        dp.text((12, y + FH * sc + 8), f"{key}: idle x4 | spin x4 | watch x4", fill=(200, 200, 210))
        print(f"{key}: watcher.png {sheet.size[0]}x{sheet.size[1]} -> {base}")
    P.save(os.path.join(outdir, "preview_watcher.png"))


if __name__ == "__main__":
    main()
