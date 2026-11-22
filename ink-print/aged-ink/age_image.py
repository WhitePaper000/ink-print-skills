#!/usr/bin/env python3
"""
Age an EXISTING picture with the aged_ink pass (secondary path; drawing layers in code is better).

  python3 age_image.py in.png out.png --strength 0.7 --seed 1 [--paper paper.png] [--no-rub] [--debug]

1. Estimates the local background (morphological closing) and takes ink = pixels clearly darker than it.
2. Splits ink components into text-like / line-like / fill-like by shape (stroke thickness, size, elongation),
   and coloured ink (e.g. red) from dark ink.
3. Ages each class with aged_ink.composite() on the ink-free background, so non-ink colours are kept.
Photo fallback: if no clean ink is found (low contrast / soft image), it only applies global speckle,
fading, rub patches and grain, and prints a note.
Limit: assumes dark ink on a lighter ground (light-on-dark ink is treated as background).
"""
import argparse, os, sys
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aged_ink as ai

REF_STROKE = 17.0      # text stem width (px) at unit 1.0 in the reference build


def lum(x): return x[..., 0]*0.299 + x[..., 1]*0.587 + x[..., 2]*0.114


def background(img, k):
    bg = np.stack([ndi.grey_closing(img[..., c], size=(k, k)) for c in range(3)], -1)
    return ndi.uniform_filter(bg, size=(k//2*2+1, k//2*2+1, 1))


def classify(mask, H, W):
    """returns label->kind arrays and the median text stroke thickness"""
    lab, n = ndi.label(mask, structure=np.ones((3, 3)))
    if n == 0:
        return lab, np.array(['text']), 3.0, np.zeros(1, bool), np.zeros(0)
    idx = np.arange(1, n+1)
    area = ndi.sum(mask, lab, idx)
    edge = mask & ~ndi.binary_erosion(mask)
    perim = np.maximum(ndi.sum(edge, lab, idx), 1)
    thick = 2*area/perim                                   # ~ stroke width
    objs = ndi.find_objects(lab)
    hh = np.array([o[0].stop-o[0].start for o in objs]); ww = np.array([o[1].stop-o[1].start for o in objs])
    long_ = np.maximum(hh, ww); short = np.maximum(np.minimum(hh, ww), 1)
    fill = area/(hh*ww)
    small_side = min(H, W)
    tmed = float(np.median(thick[(long_ < 0.12*small_side) & (area > 20)])) if np.any((long_ < 0.12*small_side) & (area > 20)) else float(np.median(thick))
    kinds = np.empty(n+1, dtype=object); kinds[0] = 'none'
    for i in range(n):
        if thick[i] > max(8.0, 4.0*tmed) and fill[i] > 0.5 and area[i] > 400:
            k = 'pattern'                                  # fat solid fills, blocks, dots
        elif long_[i] > 0.12*small_side or (long_[i]/short[i] > 6 and thick[i] < 1.6*tmed):
            k = 'line'                                     # rules, borders, long outlines, hatching
        elif long_[i] > 0.06*small_side and fill[i] < 0.12:
            k = 'pattern'                                  # big sparse line drawings (hatched shapes)
        else:
            k = 'text'
        kinds[i+1] = k
    big_text = np.zeros(n+1, bool); big_text[1:] = thick > 1.8*tmed
    return lab, kinds, tmed, big_text, thick


def photo_fallback(img, strength, seed, paper):
    H, W = img.shape[:2]; s = strength
    out = img.copy()
    mean = out.reshape(-1, 3).mean(0)
    sepia = np.array([236, 226, 205], np.float32)
    out = out*(1 - 0.18*s) + (mean*0.4 + sepia*0.6)*0.18*s           # fade + slight warm cast
    k = max(1.0, min(H, W)/1000.0)
    rub = ndi.gaussian_filter(ai.rub_patches((H, W), 3, seed, None, s), 1.8*k)
    out = out*(1 - rub[..., None]*0.45) + sepia*rub[..., None]*0.45   # rubbed, lighter worn patches
    rg = np.random.default_rng(seed)
    g = ai._noise((H, W), 1, seed+5)
    dark = ndi.gaussian_filter((g > 3.0).astype(np.float32), 0.6) > 0.15
    light = ndi.gaussian_filter((ai._noise((H, W), 1, seed+6) > 3.1).astype(np.float32), 0.7) > 0.15
    out[dark] = out[dark]*(1 - 0.7*s) + 25*0.7*s
    out[light] = out[light]*(1 - 0.6*s) + sepia*0.6*s
    grain = ai.make_paper(W, H, base='#808080', seed=seed, stains=True, vignette=True).astype(np.float32)/128.0
    out *= (1 + (grain - 1)*s)
    if paper is not None:
        pl = paper.mean(axis=2, keepdims=True); out *= pl/pl.mean()
    return np.clip(out, 0, 255).astype(np.uint8)


def extract_layers(img, paper=None, seed=1, paper_replace=False):
    """
    Split a picture into ink layers + an ink-free background (the CLI's ink extraction, reusable).
    img: (H,W,3) float. paper: optional (H,W,3) paper at the same size (multiplied in, or used as background with
    paper_replace). Returns None if no clean ink is found, else dict(background, layers, S, unit, frac, tmed,
    counts, kind_px, mask) -- layers as composite()/fresh_print() take them (masks at S x res).
    """
    H, W = img.shape[:2]
    k = int(max(31, min(H, W)//5)) | 1                     # wide enough to see past solid fills
    bg = background(img, k)
    d = lum(bg) - lum(img)
    p995 = float(np.percentile(d, 99.5))
    thr = max(28.0, 0.35*p995)
    mask = d > thr
    mask = ndi.binary_opening(mask, iterations=1) | (d > thr*1.6)
    frac = mask.mean()
    gm = np.hypot(*np.gradient(lum(img)))
    border = mask & ~ndi.binary_erosion(mask)
    sharp = float(gm[border].mean()) if border.any() else 0.0
    if p995 < 45 or frac < 0.0008 or frac > 0.55 or sharp < 12:
        print(f'note: no clean ink found (contrast {p995:.0f}, ink {frac*100:.2f}%, edge {sharp:.1f})')
        return None
    alpha = np.clip((d - 0.5*thr)/(np.percentile(d[mask], 70) - 0.5*thr + 1e-6), 0, 1)
    alpha[~ndi.binary_dilation(mask, iterations=2)] = 0
    ink_rgb = np.where(alpha[..., None] > 0.05, (img - bg*(1 - alpha[..., None]))/np.maximum(alpha[..., None], 0.05), 0)
    dm = ndi.binary_dilation(mask, iterations=2)[..., None]
    clean_bg = img*(1 - dm) + bg*dm
    if paper is not None:
        if paper_replace:
            clean_bg = paper
        else:                                   # keep colours, add the paper's relief/tone (luminance multiply)
            pl = paper.mean(axis=2, keepdims=True)
            clean_bg = clean_bg*(pl/pl.mean())
    lab, kinds, tmed, big_text, thick = classify(mask, H, W)
    mx, mn = img.max(-1), img.min(-1)
    sat = (mx - mn)/np.maximum(mx, 1)
    coloured = (sat > 0.30) & mask
    S = 2 if H*W <= 3.5e6 else 1
    unit = float(np.clip(S*tmed/REF_STROKE, 0.25, 3.0))
    lab_d = ndi.grey_dilation(lab, size=(5, 5))
    kind_px = kinds[lab_d]
    kind_px[(kind_px == 'text') & big_text[lab_d]] = 'text_big'
    tbig = float(np.median(thick[big_text[1:]])) if big_text[1:].any() else tmed
    units = {'text': unit, 'text_big': float(np.clip(S*tbig/REF_STROKE, 0.25, 3.0)), 'line': unit, 'pattern': unit}
    layers, counts = [], {}
    up = lambda x: np.asarray(Image.fromarray((x*255).astype(np.uint8)).resize((W*S, H*S), Image.BILINEAR), np.float32)/255
    for kind in ('line', 'pattern', 'text', 'text_big'):
        sel = (kind_px == kind)
        for col in (False, True):
            m = alpha*(sel & (ndi.binary_dilation(coloured, iterations=2) == col))
            if (m > 0.5).sum() < 30:
                continue
            opts = {'unit': units[kind]}
            if col:
                cpx = ink_rgb[(m > 0.6) & coloured]
                opts['color'] = np.clip(np.median(cpx, 0), 0, 255) if len(cpx) else np.array([170, 60, 45])
            layers.append((up(m), 'text' if kind.startswith('text') else kind, opts))
            counts[f'{kind}{"(colour)" if col else ""}'] = round(float((m > 0.5).mean()*100), 2)
    return dict(background=clean_bg, layers=layers, S=S, unit=unit, frac=frac, tmed=tmed, counts=counts,
                kind_px=kind_px, mask=mask)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('inp'); ap.add_argument('out')
    ap.add_argument('--strength', type=float, default=0.7)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--paper', help='paper image (e.g. the user\'s own scan) used as the base texture')
    ap.add_argument('--paper-mode', default='cover', choices=['cover', 'tile', 'stretch'])
    ap.add_argument('--paper-scale', type=float, default=1.0, help='texture magnification')
    ap.add_argument('--paper-tone', default='none', help="none | vintage | aged | #RRGGBB (colour grade of the paper)")
    ap.add_argument('--paper-replace', action='store_true',
                    help='use the paper image itself as the background (for black-on-white art); default multiplies '
                         'its luminance texture into the original background so the picture\'s colours are kept')
    ap.add_argument('--no-rub', action='store_true', help='disable rubbed patches')
    ap.add_argument('--style', default='aged', choices=['aged', 'fresh'],
                    help="aged (default) = worn old print; fresh = re-print the extracted ink as fresh feathered ink "
                         "(fibre-aligned ragged edges + strands, paper grain, no ageing). Colour layers keep their colour.")
    ap.add_argument('--ink', default=None, help="ink colour for dark ink layers (fresh default #1d1d1f; aged default #111)")
    ap.add_argument('--feathered', action='store_true', help='aged style on the feathered fresh edges (aged = fresh + ageing)')
    ap.add_argument('--feather-reach', type=float, default=6.0); ap.add_argument('--feather-density', type=float, default=1.0)
    ap.add_argument('--rag', type=float, default=1.0); ap.add_argument('--ink-grain', type=float, default=1.3)
    ap.add_argument('--debug', action='store_true', help='also write <out>_classes.png (red text, magenta large text, blue line, green fill)')
    a = ap.parse_args()

    img = np.asarray(Image.open(a.inp).convert('RGB'), np.float32)
    H, W = img.shape[:2]
    paper = None
    if a.paper:
        paper = ai.load_paper(a.paper, W, H, a.paper_mode, a.paper_scale, None, a.seed, tone=a.paper_tone).astype(np.float32)
    ex = extract_layers(img, paper, a.seed, a.paper_replace)
    if ex is None:
        if a.style == 'fresh':
            sys.exit('fresh style needs clean ink to re-print; none found')
        print('applying photo fallback: global speckle, fading, rub patches and grain only.')
        Image.fromarray(photo_fallback(img, a.strength, a.seed, paper)).save(a.out); return
    clean_bg, layers, S, unit = ex['background'], ex['layers'], ex['S'], ex['unit']
    frac, tmed, counts, kind_px, mask = ex['frac'], ex['tmed'], ex['counts'], ex['kind_px'], ex['mask']
    if a.style == 'fresh':
        out = ai.fresh_print(clean_bg, layers, ink=a.ink or '#1d1d1f', feather_reach=a.feather_reach,
                             feather_density=a.feather_density, rag=a.rag, ink_grain=a.ink_grain, seed=a.seed,
                             supersample=S, strength=a.strength, unit=unit)
        Image.fromarray(out).save(a.out)
        print(f'fresh print: ink {frac*100:.1f}% of image, layers (% px): {counts}')
        return
    fe = dict(feather_reach=a.feather_reach, feather_density=a.feather_density, rag=a.rag) if a.feathered else None
    out, info = ai.composite(clean_bg, layers, strength=a.strength, seed=a.seed, supersample=S, unit=unit,
                             rub=0 if a.no_rub else 3, return_info=True, ink=a.ink, feather=fe,
                             halo=not a.feathered, paper_grain=a.ink_grain if a.feathered else 1.0)
    Image.fromarray(out).save(a.out)
    print(f'ink {frac*100:.1f}% of image, text stroke ~{tmed:.1f}px -> unit {unit:.2f}, layers (% px): {counts}')
    print('degraded % per layer:', info['degraded'])
    if a.debug:
        dbg = np.full((H, W, 3), 255, np.uint8)
        dbg[kind_px == 'text'] = [220, 40, 40]; dbg[kind_px == 'text_big'] = [200, 40, 160]; dbg[kind_px == 'line'] = [40, 80, 220]; dbg[kind_px == 'pattern'] = [40, 170, 60]
        dbg[~mask] = 255
        Image.fromarray(dbg).save(os.path.splitext(a.out)[0] + '_classes.png')


if __name__ == '__main__':
    main()
