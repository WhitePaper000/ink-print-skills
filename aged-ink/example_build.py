"""Minimal PRIMARY-path example: draw a vintage seed-packet label in code with separate
text / line / pattern layers, then age them with aged_ink.composite()."""
import math, os, sys, numpy as np
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import aged_ink as ai

strength = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
outname = sys.argv[2] if len(sys.argv) > 2 else 'example.png'
paper_path = sys.argv[3] if len(sys.argv) > 3 else None          # e.g. papers/user_paper_01.jpg (preferred)
paper_scale = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
paper_tone = sys.argv[5] if len(sys.argv) > 5 else 'vintage'
W, H, S = 1600, 1100, 2                      # output size, supersample (unit defaults to S/2 = 1.0)
w, h = W*S, H*S
F = os.path.join(HERE, 'fonts')
f_title = ImageFont.truetype(os.path.join(F, 'IMFeENsc28P.ttf'), 190)
f_sub   = ImageFont.truetype(os.path.join(F, 'IMFeENit28P.ttf'), 92)
f_cap   = ImageFont.truetype(os.path.join(F, 'IMFeENit28P.ttf'), 64)
f_rm    = ImageFont.truetype(os.path.join(F, 'IMFeENrm28P.ttf'), 74)
f_block = ImageFont.truetype(os.path.join(F, 'IMFeENsc28P.ttf'), 120)

def layer(): im = Image.new('L', (w, h), 0); return im, ImageDraw.Draw(im)
TXT, dt = layer(); SML, ds = layer(); LIN, dl = layer(); PAT, dp = layer(); BLK, db = layer(); RED, dr = layer()

# ---- line work: double ruled border, rules, corner rosettes
m = 70
dl.rectangle([m, m, w-m, h-m], outline=255, width=22)
dl.rectangle([m+44, m+44, w-m-44, h-m-44], outline=255, width=6)
for y in (640, 662):
    dl.line([(m+120, y), (w-m-120, y)], fill=255, width=6 if y == 640 else 3)
for cx, cy in [(m+44, m+44), (w-m-44, m+44), (m+44, h-m-44), (w-m-44, h-m-44)]:
    dl.ellipse([cx-34, cy-34, cx+34, cy+34], fill=0, outline=255, width=8)
    dl.ellipse([cx-10, cy-10, cx+10, cy+10], fill=255)

# ---- text
def ctext(d, y, s, f, x=None):
    tw = d.textlength(s, font=f); d.text(((w-tw)/2 if x is None else x, y), s, font=f, fill=255)
ctext(dt, 250, 'HORTUS BOTANICUS', f_title)
ctext(dt, 480, 'Seeds of the Common Fern, gathered at Kew', f_sub)
ds.text((1700, 760), 'Polypodium vulgare.', font=f_rm, fill=255)
cap = ('Sow thinly upon damp peat in a shaded frame;\n'
       'keep moist and cover with glass until the\n'
       'young fronds appear. Germination in six weeks.')
ds.multiline_text((1700, 880), cap, font=f_cap, fill=255, spacing=26)

# ---- pattern: hatched fern frond + solid block with knocked-out lettering
def hatch_into(dst, poly, ang, gap, wd):
    mk = Image.new('L', (w, h), 0); ImageDraw.Draw(mk).polygon(poly, fill=255)
    L = Image.new('L', (w, h), 0); d2 = ImageDraw.Draw(L)
    t = math.radians(ang); dx, dy = math.cos(t), math.sin(t)
    for k in range(-h-w, h+w, gap):
        ox, oy = w/2 - dy*k, h/2 + dx*k
        d2.line([(ox-dx*4000, oy-dy*4000), (ox+dx*4000, oy+dy*4000)], fill=255, width=wd)
    dst.paste(255, (0, 0), Image.fromarray(np.minimum(np.asarray(mk), np.asarray(L))))
x0, y0, x1, y1 = 330, 1880, 1300, 780          # frond stem from bottom-left up to the right
dp.line([(x0, y0), (x1, y1)], fill=255, width=12)
for i in range(1, 13):
    t = i/13; bx, by = x0 + (x1-x0)*t, y0 + (y1-y0)*t
    L = 300*(1 - t*0.75)
    a = math.atan2(y1-y0, x1-x0)
    for sgn in (1, -1):
        n = a + sgn*math.radians(62)
        tip = (bx + L*math.cos(n), by + L*math.sin(n))
        wv = L*0.18
        nx, ny = -math.sin(n)*wv, math.cos(n)*wv
        mid = (bx + 0.45*L*math.cos(n), by + 0.45*L*math.sin(n))
        leaf = [(bx, by), (mid[0]+nx, mid[1]+ny), tip, (mid[0]-nx, mid[1]-ny)]
        half = [(bx, by), (mid[0]+nx, mid[1]+ny), tip]
        hatch_into(PAT, half, math.degrees(n)+90+8, 14, 4)
        dp.line(leaf + [leaf[0]], fill=255, width=7, joint='curve')
        dp.line([(bx, by), tip], fill=255, width=4)
# solid block with reversed lettering
bx0, by0, bx1, by1 = 1700, 1560, w-m-150, 1860
db.rectangle([bx0, by0, bx1, by1], fill=255)
tw = db.textlength('SEED Co. 1887', font=f_block)
db.text(((bx0+bx1-tw)/2, by0+70), 'SEED Co. 1887', font=f_block, fill=0, stroke_width=3, stroke_fill=0)
# small solid triangles under the title rule
for xx in range(900, 2400, 300):
    dp.polygon([(xx, 700), (xx+40, 700), (xx+20, 735)], fill=255)

# ---- a second colour: red price stamp
dr.ellipse([2560, 1250, 2860, 1550], outline=255, width=12)
f_red = ImageFont.truetype(os.path.join(F, 'IMFeENsc28P.ttf'), 88)
for j, s_ in enumerate(['No.', '27']):
    tw = dr.textlength(s_, font=f_red); dr.text((2710-tw/2, 1300+j*100), s_, font=f_red, fill=255)

LAYERS = [(LIN, 'line'), (PAT, 'pattern'),
          (BLK, 'pattern', {'solid_pits': 0.3, 'rough': False}),   # big solid: fewer pits, keep knock-outs open
          (TXT, 'text'),
          (SML, 'text', {'unit': 0.5}),                          # small caption: finer noise scale
          (RED, 'text', {'color': '#B8402E', 'unit': 0.7})]
paper = ai.load_paper(paper_path, W, H, mode='cover', scale=paper_scale, tone=paper_tone) if paper_path else ai.make_paper(W, H, base='#EEE6D2', seed=3)
out, info = ai.composite(paper, LAYERS,
                         strength=strength, seed=5, supersample=S, rub=3,
                         avoid_boxes=[(100, 115, 1500, 240)], return_info=True)
os.makedirs(os.path.join(HERE, 'examples'), exist_ok=True)
Image.fromarray(out).save(os.path.join(HERE, 'examples', outname))
if outname != 'example_s05.png':
    z = Image.fromarray(out).crop((80, 100, 880, 560))
    z.resize((z.width*2, z.height*2), Image.LANCZOS).save(os.path.join(HERE, 'examples', outname.replace('.png', '_zoom.png')))
if outname == 'example.png':
    # clean reference (strength 0) for comparison
    Image.fromarray(ai.composite(paper, LAYERS,
                                 strength=0.0, seed=5, supersample=S, rub=0)).save(os.path.join(HERE, 'examples', 'example_clean.png'))
print(outname, 'strength', strength, 'degraded %', info['degraded'])
