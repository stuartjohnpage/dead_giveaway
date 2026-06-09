#!/usr/bin/env python3
"""Per-theme crosshair sprites (#48). One 38x38 transparent PNG per theme, drawn on a
19x19 native pixel grid and scaled 2x nearest — same pixel-art pipeline as gen_bullet.py.

The client renders this 1:1 in screen space (game.mjs myCross; peers adopt the same
texture), so every export uses the SAME canvas size and a centered anchor point — the
shape is themed, the aim feel is not (issue #48: cosmetic only).

Usage: python tools/asset-gen/gen_crosshair.py [repo_root]
Writes priv/static/themes/<key>/crosshair.png + preview_crosshair.png in the cwd.
"""
import os, sys
from PIL import Image, ImageDraw, ImageFilter

NATIVE = 19            # odd, so (9,9) is a true center pixel
SC = 2                 # export scale -> 38x38, matching the old procedural cross (~32px)
C = NATIVE // 2        # center

# Theme accents — must match each pack's ui.reticle tint.
NEON = (255, 85, 119)      # #ff5577
NEON_2 = (0, 230, 230)     # cyan center spark
WESTERN = (224, 150, 60)   # #e0963c
WESTERN_D = (150, 100, 40)
STATION = (95, 192, 224)   # #5fc0e0
STATION_2 = (255, 150, 60) # amber center (the station palette's hazard accent)


def neon():
    """Neon Concourse: the classic ring-and-cross, glowed up — open ring with four
    gaps, tick arms reaching past it, a cyan spark in the middle."""
    im = Image.new("RGBA", (NATIVE, NATIVE), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([C - 6, C - 6, C + 6, C + 6], outline=NEON, width=1)
    # cut the ring open at the four compass points (the arms pass through the gaps)
    for dx, dy in ((0, -6), (0, 6), (-6, 0), (6, 0)):
        d.rectangle([C + dx - 1, C + dy - 1, C + dx + 1, C + dy + 1], fill=(0, 0, 0, 0))
    # arms: from just outside the center to past the ring, leaving the middle open
    for a, b in (((C, C - 8), (C, C - 3)), ((C, C + 3), (C, C + 8)),
                 ((C - 8, C), (C - 3, C)), ((C + 3, C), (C + 8, C))):
        d.line([a, b], fill=NEON, width=1)
    d.point((C, C), fill=NEON_2)
    return im, NEON, 0.65  # glow color + strength


def western():
    """Dead Man's Gulch: iron sights — a fine ring, four duplex posts that stop short
    of the middle, and a bead. No glow (western is the flat/no-glow pack); instead a
    dark outline keeps it legible against the sunlit dirt."""
    im = Image.new("RGBA", (NATIVE, NATIVE), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([C - 7, C - 7, C + 7, C + 7], outline=WESTERN, width=1)
    # posts ride OVER the ring from just inside the rim toward the center, stopping
    # well short of it — the open middle is what makes it read as sights, not a wheel
    d.rectangle([C, C - 8, C, C - 4], fill=WESTERN)   # N
    d.rectangle([C, C + 4, C, C + 8], fill=WESTERN)   # S
    d.rectangle([C - 8, C, C - 4, C], fill=WESTERN)   # W
    d.rectangle([C + 4, C, C + 8, C], fill=WESTERN)   # E
    d.point((C, C), fill=WESTERN)  # the bead
    return im, WESTERN, 0.0


def station():
    """Derelict Orbital: a HUD targeting box — four corner brackets, edge ticks, and an
    amber center pip. Cool blue with a faint instrument glow."""
    im = Image.new("RGBA", (NATIVE, NATIVE), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = 6
    for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):   # corner L-brackets
        cx, cy = C + sx * r, C + sy * r
        d.line([(cx, cy), (cx - sx * 3, cy)], fill=STATION, width=1)
        d.line([(cx, cy), (cx, cy - sy * 3)], fill=STATION, width=1)
    for dx, dy in ((0, -8), (0, 8), (-8, 0), (8, 0)):     # compass ticks outside the box
        d.line([(C + dx, C + dy), (C + dx * 7 // 8, C + dy * 7 // 8)], fill=STATION, width=1)
    d.point((C, C), fill=STATION_2)
    return im, STATION, 0.45


def _outline(layer, color):
    """1px dark halo from the silhouette (gen_bullet.py's trick) — contrast insurance
    for reticles that sit on light ground instead of glowing on dark."""
    a = layer.split()[3]
    grown = a.filter(ImageFilter.MaxFilter(3))
    edge = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    pe, pa, pg = edge.load(), a.load(), grown.load()
    for y in range(layer.size[1]):
        for x in range(layer.size[0]):
            if pg[x, y] > 40 and pa[x, y] <= 40:
                pe[x, y] = (*color, 200)
    return Image.alpha_composite(edge, layer)


def export(fig, glow_col, glow_amt):
    if glow_amt <= 0:  # no glow → outline instead (the flat, sunlit-theme variant)
        fig = _outline(fig, (28, 16, 8))
    big = fig.resize((NATIVE * SC, NATIVE * SC), Image.NEAREST)
    if glow_amt <= 0:
        return big
    sil = Image.new("RGBA", big.size, (0, 0, 0, 0))
    sil.paste(Image.new("RGBA", big.size, (*glow_col, 255)), (0, 0), big.split()[3])
    glow = sil.filter(ImageFilter.GaussianBlur(SC * 1.4))
    glow.putalpha(glow.split()[3].point(lambda p: int(p * glow_amt)))
    out = Image.new("RGBA", big.size, (0, 0, 0, 0))
    out = Image.alpha_composite(out, glow)
    return Image.alpha_composite(out, big)


THEMES = {"neon": neon, "western": western, "station": station}
# preview backdrops approximating each arena so the contrast check is honest
PREVIEW_BG = {"neon": (18, 16, 32), "western": (124, 96, 60), "station": (44, 50, 60)}


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    size = NATIVE * SC
    big = size * 3  # a 3x blow-up beside the true-size icon, for shape checking
    cell = big + 60
    P = Image.new("RGBA", (len(THEMES) * cell + 20, big + 70), (10, 10, 14, 255))
    dp = ImageDraw.Draw(P)
    for i, (key, draw) in enumerate(THEMES.items()):
        icon = export(*draw())
        target = os.path.join(root, "priv", "static", "themes", key)
        os.makedirs(target, exist_ok=True)
        icon.save(os.path.join(target, "crosshair.png"))
        x = 20 + i * cell
        dp.rectangle([x - 6, 14, x + big + 6, 14 + big + 12], fill=PREVIEW_BG[key])
        P.alpha_composite(icon.resize((big, big), Image.NEAREST), (x, 20))
        P.alpha_composite(icon, (x + big - size, 20 + big - size))  # true size, corner
        dp.text((x, big + 40), key, fill=(200, 200, 210))
        print(f"{key}: crosshair.png {icon.size[0]}x{icon.size[1]} -> {target}")
    P.save("preview_crosshair.png")


if __name__ == "__main__":
    main()
