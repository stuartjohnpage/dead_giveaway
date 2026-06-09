#!/usr/bin/env python3
"""Show a lobby backdrop (the theme's menu_bg) as the player actually sees it: bg-cover
at 1280x720, behind the lobby's 2px backdrop-blur + bg-black/65 scrim, with the centred
card blocked out so we judge only the visible framing around it.
Usage: scrim_preview.py <menu_bg.png> <out.png>"""
import sys
from PIL import Image, ImageDraw, ImageFilter

src, out = sys.argv[1], sys.argv[2]
VW, VH = 1280, 720
bg = Image.open(src).convert("RGBA")
# bg-cover: scale to fill the viewport, crop the overflow (centre).
s = max(VW / bg.width, VH / bg.height)
bg = bg.resize((round(bg.width * s), round(bg.height * s)), Image.LANCZOS)
bg = bg.crop(((bg.width - VW) // 2, (bg.height - VH) // 2,
              (bg.width - VW) // 2 + VW, (bg.height - VH) // 2 + VH))
# backdrop-blur-[2px] then bg-black/65 scrim.
img = bg.filter(ImageFilter.GaussianBlur(2))
img = Image.alpha_composite(img, Image.new("RGBA", (VW, VH), (0, 0, 0, 166)))
# Block out the centred card (max-w-lg ~512 wide; height ~ content) so we see the framing.
d = ImageDraw.Draw(img, "RGBA")
cw, ch = 512, 460
x0, y0 = (VW - cw) // 2, (VH - ch) // 2
d.rectangle([x0, y0, x0 + cw, y0 + ch], fill=(10, 15, 34, 235), outline=(182, 255, 61, 60), width=2)
d.text((x0 + 20, y0 + 18), "[ lobby card ]", fill=(120, 130, 150, 255))
img.convert("RGB").save(out)
print("wrote", out)
