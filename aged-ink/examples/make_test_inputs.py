"""generate the two CLI test inputs: clean typographic line art, and a soft gradient 'photo'."""
import os, math, numpy as np
from PIL import Image, ImageDraw, ImageFont
D = os.path.dirname(os.path.abspath(__file__)); F = os.path.join(D, '..', 'fonts')
W, H = 1400, 1000
im = Image.new('RGB', (W, H), (246, 242, 232)); d = ImageDraw.Draw(im)
d.rectangle([40, 40, W-40, H-40], outline=(20, 20, 20), width=10)
d.rectangle([62, 62, W-62, H-62], outline=(20, 20, 20), width=3)
f1 = ImageFont.truetype(os.path.join(F, 'IMFeENsc28P.ttf'), 120)
f2 = ImageFont.truetype(os.path.join(F, 'IMFeENit28P.ttf'), 48)
f3 = ImageFont.truetype(os.path.join(F, 'IMFeENrm28P.ttf'), 34)
def c(y, s, f, fill=(20, 20, 20)):
    tw = d.textlength(s, font=f); d.text(((W-tw)/2, y), s, font=f, fill=fill)
c(110, 'THE GRAND TOUR', f1)
c(260, 'A Railway Excursion to the Lakes & Mountains', f2)
d.line([(160, 345), (W-160, 345)], fill=(20, 20, 20), width=4)
d.line([(160, 357), (W-160, 357)], fill=(20, 20, 20), width=2)
# hatched mountains
for (x0, x1, peak) in [(180, 700, 430), (520, 1220, 470)]:
    xm = (x0+x1)/2; base = 760
    d.polygon([(x0, base), (xm, peak), (x1, base)], outline=(20, 20, 20), width=5)
    for k in range(0, int(x1-xm), 16):
        xa = xm + k; ya = peak + (base-peak)*k/(x1-xm)
        d.line([(xa, ya+6), (xa-40, base)], fill=(20, 20, 20), width=3) if xa - 40 > xm - (base-ya) else None
d.ellipse([1040, 400, 1180, 540], fill=(20, 20, 20))         # solid sun
d.rectangle([180, 790, 1220, 850], fill=(20, 20, 20))         # solid band
f4 = ImageFont.truetype(os.path.join(F, 'IMFeENsc28P.ttf'), 44)
tw = d.textlength('DEPARTING DAILY AT NINE', font=f4); d.text(((W-tw)/2, 795), 'DEPARTING DAILY AT NINE', font=f4, fill=(246, 242, 232))
c(880, 'Third Class Return, Five Shillings  -  Apply at any Booking Office', f3)
d.text((190, 400), 'SPECIAL', font=f2, fill=(178, 52, 40))
im.save(os.path.join(D, 'input_lineart.png'))
# soft gradient image (no clean ink)
y, x = np.mgrid[0:700, 0:1000].astype(np.float32)
g = np.stack([120 + 90*np.sin(x/260) + 20*np.cos(y/90), 110 + 60*np.cos((x+y)/300), 150 + 70*np.sin(y/200)], -1)
g = g + 25*np.exp(-((x-650)**2 + (y-300)**2)/(2*150**2))[..., None]
Image.fromarray(np.clip(g, 0, 255).astype(np.uint8)).save(os.path.join(D, 'input_gradient.png'))
print('ok')
