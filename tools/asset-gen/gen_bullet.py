#!/usr/bin/env python3
"""Sleek neon 'round' for the ammo counter (armed state). Pixel art, neon theme.
Exports bullet.png (transparent, 6x) + a preview showing it at small HUD sizes."""
import sys, os
from PIL import Image, ImageDraw, ImageFilter

CYAN=(0,230,230); MAG=(255,60,200); WHITE=(235,255,255); OUT=(8,6,14)
# brass cartridge palette (western)
BRASS=(214,170,74); BRASS_D=(150,116,42); BRASS_HL=(245,225,150)
COPPER=(196,118,66); COPPER_L=(228,152,96); RIM=(120,92,36); OUT_W=(28,16,8)
# energy-cell palette (station): steel casing, glowing signal-blue core, amber end caps
STEEL=(170,180,193); STEEL_HL=(222,230,240); CORE=(110,205,232); CORE_HL=(225,248,255)
CAP=(255,150,60); OUT_S=(14,18,28)
W,H=34,18                      # native canvas (wide; bullet points right)
SC=6                           # export scale

def shade(c,f): return tuple(max(0,min(255,int(v*f))) for v in c)

def draw_round():
    fig=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(fig)
    cy=H//2
    # body capsule (x 5..24), nose point to x~30, flat tail at x5
    bx0,bx1=6,24; by0,by1=cy-4,cy+4
    d.rounded_rectangle([bx0,by0,bx1,by1],radius=3,fill=CYAN)
    # pointed nose (triangle to the right)
    d.polygon([(bx1-1,by0),(bx1-1,by1),(30,cy)],fill=CYAN)
    # tail cap accent (magenta base ring)
    d.rounded_rectangle([bx0-1,by0,bx0+3,by1],radius=2,fill=MAG)
    d.rectangle([bx0+3,by0,bx0+4,by1],fill=shade(MAG,0.8))
    # vertical shading: darken lower half for volume
    sh=Image.new("RGBA",(W,H),(0,0,0,0)); ds=ImageDraw.Draw(sh)
    ds.rectangle([0,cy+1,W,H],fill=(0,0,0,70))
    fig=Image.alpha_composite(fig,_mask_to(fig,sh))
    # white-hot specular highlight (upper edge) + tip flash
    hl=Image.new("RGBA",(W,H),(0,0,0,0)); dh=ImageDraw.Draw(hl)
    dh.line([(bx0+2,by0+1),(bx1,by0+1)],fill=WHITE,width=1)
    dh.line([(bx1,cy-1),(29,cy)],fill=WHITE,width=1)       # nose glint
    dh.point((bx0+5,cy),fill=WHITE)
    fig=Image.alpha_composite(fig,_mask_to(fig,hl))
    # crisp dark outline from silhouette
    fig=_outline(fig,OUT)
    return fig

def draw_cartridge():
    """Classic brass cartridge: casing + copper bullet + extractor rim (points right)."""
    fig=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(fig)
    cy=H//2
    # casing body (brass)
    d.rectangle([6,cy-4,22,cy+4],fill=BRASS)
    # extractor rim at the base (slightly proud)
    d.rectangle([4,cy-5,7,cy+5],fill=BRASS)
    # bullet (copper) seated in the case mouth, rounded nose
    d.rectangle([21,cy-3,27,cy+3],fill=COPPER)
    d.ellipse([25,cy-3,31,cy+3],fill=COPPER)
    # volume shading (lower half darker), clipped to the shape
    sh=Image.new("RGBA",(W,H),(0,0,0,0)); ds=ImageDraw.Draw(sh)
    ds.rectangle([0,cy+1,W,H],fill=(0,0,0,85))
    fig=Image.alpha_composite(fig,_mask_to(fig,sh))
    # metal highlights
    hl=Image.new("RGBA",(W,H),(0,0,0,0)); dh=ImageDraw.Draw(hl)
    dh.line([(7,cy-3),(20,cy-3)],fill=BRASS_HL,width=1)     # brass sheen
    dh.line([(22,cy-2),(28,cy-2)],fill=COPPER_L,width=1)    # copper glint
    fig=Image.alpha_composite(fig,_mask_to(fig,hl))
    # detail lines: case mouth + extractor groove
    dl=Image.new("RGBA",(W,H),(0,0,0,0)); dd=ImageDraw.Draw(dl)
    dd.line([(21,cy-4),(21,cy+4)],fill=BRASS_D,width=1)     # case mouth
    dd.line([(8,cy-4),(8,cy+4)],fill=RIM,width=1)           # extractor groove
    fig=Image.alpha_composite(fig,_mask_to(fig,dl))
    fig=_outline(fig,OUT_W)
    return fig

def draw_cell():
    """Energy cell: a steel capsule with amber end caps and a glowing signal-blue core
    window (points right, like the other ammo icons)."""
    fig=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(fig)
    cy=H//2
    # steel casing capsule
    d.rounded_rectangle([6,cy-4,28,cy+4],radius=3,fill=STEEL)
    # amber end caps (charge terminals)
    d.rectangle([5,cy-3,8,cy+3],fill=CAP)
    d.rectangle([26,cy-3,29,cy+3],fill=CAP)
    # glowing core window
    d.rounded_rectangle([11,cy-2,24,cy+2],radius=1,fill=CORE)
    # volume shading (lower half darker), clipped to the shape
    sh=Image.new("RGBA",(W,H),(0,0,0,0)); ds=ImageDraw.Draw(sh)
    ds.rectangle([0,cy+1,W,H],fill=(0,0,0,80))
    fig=Image.alpha_composite(fig,_mask_to(fig,sh))
    # highlights: steel sheen + bright core line
    hl=Image.new("RGBA",(W,H),(0,0,0,0)); dh=ImageDraw.Draw(hl)
    dh.line([(8,cy-3),(27,cy-3)],fill=STEEL_HL,width=1)
    dh.line([(12,cy-1),(23,cy-1)],fill=CORE_HL,width=1)
    fig=Image.alpha_composite(fig,_mask_to(fig,hl))
    # core segment ticks
    dl=Image.new("RGBA",(W,H),(0,0,0,0)); dd=ImageDraw.Draw(dl)
    dd.line([(15,cy-2),(15,cy+2)],fill=shade(CORE,0.65),width=1)
    dd.line([(19,cy-2),(19,cy+2)],fill=shade(CORE,0.65),width=1)
    fig=Image.alpha_composite(fig,_mask_to(fig,dl))
    fig=_outline(fig,OUT_S)
    return fig

def _mask_to(base, overlay):
    """Clip overlay to base's alpha so highlights/shading stay on the shape."""
    a=base.split()[3]
    out=overlay.copy(); oa=out.split()[3]
    out.putalpha(Image.composite(oa,Image.new("L",base.size,0),a))
    return out

def _outline(layer,color):
    a=layer.split()[3]; grown=a.filter(ImageFilter.MaxFilter(3))
    edge=Image.new("RGBA",layer.size,(0,0,0,0)); pe=edge.load()
    pa=a.load(); pg=grown.load()
    for y in range(layer.size[1]):
        for x in range(layer.size[0]):
            if pg[x,y]>40 and pa[x,y]<=40: pe[x,y]=(*color,255)
    return Image.alpha_composite(edge,layer)

def with_glow(fig, scale, glow_col=CYAN):
    big=fig.resize((W*scale,H*scale),Image.NEAREST)
    # glow: blurred cyan silhouette behind
    sil=Image.new("RGBA",big.size,(0,0,0,0))
    tint=Image.new("RGBA",big.size,(*glow_col,255))
    sil.paste(tint,(0,0),big.split()[3])
    glow=sil.filter(ImageFilter.GaussianBlur(scale*1.6))
    glow.putalpha(glow.split()[3].point(lambda p:int(p*0.7)))
    out=Image.new("RGBA",big.size,(0,0,0,0))
    out=Image.alpha_composite(out,glow)
    out=Image.alpha_composite(out,big)
    return out

def main():
    # args: outdir  [target_dir | '-']  [style: round|cartridge]
    outdir=sys.argv[1] if len(sys.argv)>1 else "."
    target=sys.argv[2] if len(sys.argv)>2 and sys.argv[2]!='-' else None
    style=sys.argv[3] if len(sys.argv)>3 else "round"
    fig = {"cartridge": draw_cartridge, "cell": draw_cell}.get(style, draw_round)()
    glow = {"cartridge": (230,170,70), "cell": CORE}.get(style, CYAN)
    bg = {"cartridge": (26,18,12,255), "cell": (14,18,28,255)}.get(style, (16,14,26,255))
    icon=with_glow(fig,SC,glow_col=glow)
    fig.resize((W*SC,H*SC),Image.NEAREST).save(os.path.join(outdir,"bullet_flat.png"))  # no glow
    icon.save(os.path.join(outdir,"bullet.png"))                                          # with glow
    if target:
        os.makedirs(target,exist_ok=True)
        icon.save(os.path.join(target,"bullet.png"))
        fig.resize((W*SC,H*SC),Image.NEAREST).save(os.path.join(target,"bullet_flat.png"))
    # preview: dark HUD bg, icon at several real sizes
    P=Image.new("RGBA",(560,200),bg); dp=ImageDraw.Draw(P)
    x=24
    for s in (2,3,4,6):
        im=with_glow(fig,s,glow_col=glow); P.alpha_composite(im,(x,100-im.height//2)); x+=im.width+24
        dp.text((x-im.width, 150),f"{s}x",fill=(170,150,110))
    im=with_glow(fig,3,glow_col=glow); P.alpha_composite(im,(390,30))
    dp.text((390,12),"ammo",fill=(210,180,120))
    P.save(os.path.join(outdir,"preview_bullet.png"))
    print("style",style,"native",(W,H),"export",(W*SC,H*SC),"-> bullet.png (+ glow), bullet_flat.png")

if __name__=="__main__": main()
