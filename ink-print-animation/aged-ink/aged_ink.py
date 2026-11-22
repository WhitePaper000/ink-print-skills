"""
aged_ink: worn, faded old-print ink ageing (letterpress / copperplate print that has been photocopied).

Primary use: draw a picture in code with SEPARATE ink layers (text / line / pattern) as 0..1 masks,
then call composite(paper, layers). Every random choice is seeded -> deterministic.

Calibration: strength=1.0 with unit=1.0 reproduces the approved "v6" look (text ~36% of ink visibly
degraded, lines ~25%). unit is "pixels per reference pixel": the reference was tuned on masks where body
text had a cap height of ~130 px and hairlines were ~5-8 px wide. If your masks are drawn smaller, lower
unit (e.g. cap height 65 px -> unit 0.5).
"""
import math
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi
from scipy.special import ndtr, ndtri

INK_DARK = np.array([0x11, 0x11, 0x11], np.float32)
INK_MID = np.array([0x2a, 0x24, 0x20], np.float32)
INK_FADE = np.array([0x4a, 0x42, 0x3a], np.float32)
HALO_RGB = np.array([112, 86, 60], np.float32)

# per-kind defaults (values at strength 1.0) -- taken from the approved v6 build
KIND_PARAMS = {
    'text':    dict(s=1.0, bias=0.06, cap=0.55, erode=True,  solid_pits=0.0, pit_floor=0.75, rough=False, jitter=1.0),
    'line':    dict(s=0.8, bias=0.10, cap=0.60, erode=False, solid_pits=0.9, pit_floor=-9.0, rough=True,  jitter=1.2),
    'pattern': dict(s=0.9, bias=0.10, cap=0.60, erode=False, solid_pits=0.9, pit_floor=-9.0, rough=True,  jitter=1.2),
}


# ----------------------------------------------------------------------------- noise helpers
def _noise(shape, scale, seed):
    """unit-variance gaussian value noise with feature size ~scale px (scale>=1), deterministic."""
    scale = max(1, int(round(scale)))
    r = np.random.default_rng(seed).standard_normal((shape[0]//scale + 3, shape[1]//scale + 3)).astype(np.float32)
    if scale > 1:
        r = ndi.zoom(r, scale, order=1)
    r = r[:shape[0], :shape[1]]
    return (r - r.mean()) / (r.std() + 1e-6)


def _hex(c):
    if isinstance(c, str):
        c = c.lstrip('#'); return np.array([int(c[i:i+2], 16) for i in (0, 2, 4)], np.float32)
    return np.asarray(c, np.float32)


def ink_palette(ink=None):
    """(dark, mid, fade) ink colours. ink=None -> classic #111/#2a2420/#4a423a; a hex/RGB base shifts the whole
    ramp so heavy ink == that colour and faded ink keeps the same warm offsets (e.g. ink='#1d1d1f')."""
    if ink is None:
        return INK_DARK, INK_MID, INK_FADE
    c = _hex(ink).astype(np.float32)
    return c, np.clip(c + (INK_MID - INK_DARK), 0, 255), np.clip(c + (INK_FADE - INK_DARK), 0, 255)


def _down(x, S):
    if S == 1:
        return x
    # box-average aligned SxS blocks
    H, W = x.shape[0]//S, x.shape[1]//S
    x = x[:H*S, :W*S]
    if x.ndim == 2:
        return x.reshape(H, S, W, S).mean(axis=(1, 3))
    return x.reshape(H, S, W, S, x.shape[2]).mean(axis=(1, 3))


# ----------------------------------------------------------------------------- core pass
def age_layer(ink_mask, kind='text', strength=1.0, seed=0, glyph_boxes=None, unit=1.0, ink=None, feather=None, **override):
    """
    Age one ink layer.
      ink_mask   : 2-D array 0..1 (or 0..255 / bool) -- where ink would print, at working resolution.
      kind       : 'text' | 'line' | 'pattern'
      strength   : 0..1 (1.0 = approved v6 look, 0.5 = light/moderate)
      seed       : int
      glyph_boxes: optional list of (x0, y0, x1, y1) boxes in mask px; each box is one glyph for per-glyph
                   inking/pressure. Default: connected components.
      unit       : pixel scale relative to the reference (see module doc)
      override   : any KIND_PARAMS key (s, bias, cap, erode, solid_pits, pit_floor, rough, jitter)
    Returns (alpha, rgb, info):
      alpha (H,W) float 0..1, rgb (H,W,3) float ink colour (#111 heavy -> #2a2420 -> #4a423a faded),
      info dict: 'fade' map (0..cap), 'degraded' fraction of ink visibly degraded.
    """
    return age_apply(age_prepare(ink_mask, kind, strength, seed, glyph_boxes, unit, feather=feather, **override), 1.0, ink=ink)


def age_prepare(ink_mask, kind='text', strength=1.0, seed=0, glyph_boxes=None, unit=1.0, feather=None, **override):
    """Precompute every deterministic field of the ageing pass (same args as age_layer). Use with
    age_apply(fields, q) to ANIMATE the ageing: q=0 is clean (just the jittered plate), q=1 equals age_layer().
    Intermediate q sweeps the thresholds over the same noise, so wear appears progressively, without flicker."""
    p = dict(KIND_PARAMS[kind]); p.update(override)
    m = np.asarray(ink_mask, np.float32)
    if m.max() > 1.5:
        m = m / 255.0
    sh = m.shape
    u = float(unit)
    N = lambda sc, k: _noise(sh, sc*u, seed*1000 + k)
    s = p['s'] * strength
    yy, xx = np.mgrid[0:sh[0], 0:sh[1]].astype(np.float32)

    # small positional jitter (hand-set / worn plate) + for line work a toner-style ragged re-threshold
    if p['jitter'] and strength > 0:
        jamp = p['jitter'] * u * min(1.0, 0.4 + 0.6*strength)
        sc = (8 if p['rough'] else 10)
        m = ndi.map_coordinates(m, [yy + N(sc, 1)*jamp, xx + N(sc, 2)*jamp], order=1)
    if p['rough']:
        b0 = ndi.gaussian_filter(m, 1.8*u)
        thr0 = 0.40 + min(1.0, strength*1.2)*(N(1, 3)*0.10 + N(3, 4)*0.06 + N(50, 5)*0.03)
        m = (b0 > np.maximum(thr0, 0.08)).astype(np.float32)
        del b0, thr0

    solid = m > 0.5
    if not solid.any():
        return dict(empty=True, sh=sh)

    # ---- per-glyph / per-blob inking level + one-side light pressing
    rg = np.random.default_rng(seed)
    if glyph_boxes:
        lab = np.zeros(sh, np.int32)
        for i, (x0, y0, x1, y1) in enumerate(glyph_boxes, 1):
            lab[int(max(0, y0)):int(y1), int(max(0, x0)):int(x1)] = i
        lab[~solid] = 0; nl = len(glyph_boxes)
    else:
        lab, nl = ndi.label(solid)
    per = rg.normal(0, 1, nl+1).astype(np.float32); per[0] = 0
    idx = np.arange(1, nl+1)
    cyx = np.array(ndi.center_of_mass(solid, lab, idx), np.float32).reshape(-1, 2)
    cyx = np.nan_to_num(cyx)
    objs = ndi.find_objects(lab, nl)
    ext = np.array([max(o[0].stop-o[0].start, o[1].stop-o[1].start) if o else 1 for o in objs], np.float32)
    th = rg.uniform(0, 2*np.pi, nl).astype(np.float32)
    side_amt = np.where(rg.random(nl) < 0.45, rg.uniform(0.6, 1.0, nl), 0).astype(np.float32)
    cy_ = np.concatenate([[0], cyx[:, 0]]); cx_ = np.concatenate([[0], cyx[:, 1]])
    ex_ = np.concatenate([[1], np.maximum(ext, 1)])
    ux = np.concatenate([[0], np.cos(th)]); uy = np.concatenate([[0], np.sin(th)])
    sa = np.concatenate([[0], side_amt])
    big = np.concatenate([[False], ext > 900*u])           # long rings / borders: no per-blob terms
    side = ((xx - cx_[lab])*ux[lab] + (yy - cy_[lab])*uy[lab]) / ex_[lab] * 2 * sa[lab]
    side[big[lab]] = 0
    per_px = per[lab]; per_px[big[lab]] = 0
    del lab, xx, yy

    lo = 0.5*N(14, 11) + 0.3*N(60, 12) + 0.45*N(170, 13)    # stroke scale + multi-letter patches
    fade = np.clip(s*(0.34*per_px + 0.40*lo + 0.34*side) - p['bias'], 0, p['cap'])
    del side, per_px
    F = dict(empty=False, sh=sh, p=p, s=s, strength=strength, u=u, m=m, solid=solid, fade=fade,
             bleed=np.clip(-lo - 1.1, 0, 1) * s)
    del lo
    if p['erode']:
        F['b'] = ndi.gaussian_filter(m, 1.6*u)
        if feather:
            _feather_prepare(F, feather, seed)
        F['en'] = 0.13*N(1, 21) + 0.08*N(2, 22) + 0.08*N(4, 23) + 0.06*N(9, 24)
    else:
        if feather:                                  # line / pattern: fibre strands only (keep the toner edge)
            F['b'] = ndi.gaussian_filter(solid.astype(np.float32), 1.0*u)
            _feather_prepare(F, dict(feather, rag=0.0), seed); del F['b']
        F['er'] = N(2, 31) + 0.6*N(6, 32)
        F['edge'] = ~ndi.binary_erosion(solid, iterations=max(1, int(round(2*u))))
        F['skip'] = N(10, 33) + 0.5*N(3, 34)
    brk = ndi.gaussian_filter(N(1, 41), 2.2*u); F['brk'] = brk/(brk.std() + 1e-6)
    pit = ndi.gaussian_filter(N(2, 51), 1.0*u); pit /= pit.std() + 1e-6
    pit2 = ndi.gaussian_filter(N(4, 52), 1.6*u); pit2 /= pit2.std() + 1e-6
    F['pits'] = np.maximum(pit, 0.95*pit2); del pit, pit2
    if p['solid_pits']:
        inner = ndi.binary_erosion(solid, iterations=max(1, int(round(3*u))))
        deep = ndi.binary_erosion(inner, iterations=max(1, int(round(14*u))))
        F['sp'] = (p['solid_pits']*strength*(inner.astype(np.float32) - 0.45*deep)).astype(np.float32)
    gt = ndi.gaussian_filter(N(1, 61), 0.7*u); gt /= gt.std() + 1e-6
    F['gtex'] = np.clip(gt*0.5 + 0.2*N(5, 62), -1, 1)
    return F


def age_apply(F, q=1.0, sweep=6.0, ink=None):
    """Render prepared fields at ageing progress q in [0, 1] -> (alpha, rgb, info). q=1 == age_layer().
    ink: base ink colour (hex/RGB, see ink_palette); None = classic #111."""
    sh = F['sh']
    if F['empty']:
        return np.zeros(sh, np.float32), np.zeros(sh + (3,), np.float32), dict(fade=np.zeros(sh, np.float32), degraded=0.0)
    p, s, solid = F['p'], F['s'], F['solid']
    q = float(np.clip(q, 0, 1)); off = (1 - q)*sweep         # threshold sweep: extreme noise first
    fade = F['fade']*q if q < 1 else F['fade']
    bleed = F['bleed']*q
    if p['erode']:
        thr = 0.50 + s*q*F['en'] + 0.16*fade - 0.22*bleed
        C = F['b'] > np.maximum(thr, 0.08)
    else:
        C = solid.copy()
        C &= ~((F['er'] > (2.6 - 2.5*fade + off)) & F['edge'])
        C &= ~(F['skip'] > (2.5 - 2.0*fade/0.6 + off))
    C &= ~(F['brk'] > (2.7 - 1.6*fade/0.8 + off))
    thr_p = 2.4 - 3.2*fade/0.8
    if 'sp' in F:
        thr_p = thr_p - F['sp']
    thr_p = np.maximum(thr_p, p['pit_floor']) + off
    C &= ~(F['pits'] > thr_p)
    ghost = (~C) & solid & (fade > 0.25)
    alpha = C.astype(np.float32)*np.clip(0.97 - 0.32*fade - 0.14*s*q*np.clip(F['gtex'], 0, 1), 0.5, 1) + ghost*0.14*s*q
    if 'fe_idx' in F:                                   # fibre feather strands: live while their root ink lives
        ix = F['fe_idx']; tp = thr_p if np.ndim(thr_p) else np.full(sh, thr_p, np.float32)
        alive = C.ravel()[F['fe_root']] & ~(F['pits'].ravel()[ix] > tp.ravel()[ix] - 0.25*q)
        v = F['fe_a']*alive*np.clip(1 - 0.45*fade.ravel()[ix], 0.4, 1)
        af = alpha.ravel(); af[ix] = np.maximum(af[ix], v); alpha = af.reshape(sh)
    t = np.clip(fade/0.42, 0, 1)[..., None]
    D, M, Fd = ink_palette(ink)
    rgb = np.where(t < 0.5, D + (M-D)*(t*2), M + (Fd-M)*(t*2-1)).astype(np.float32)
    degraded = float((solid & ((~C) | (fade > 0.15))).sum()) / float(solid.sum())
    return alpha.astype(np.float32), rgb, dict(fade=fade.astype(np.float32), degraded=degraded)


# ----------------------------------------------------------------------------- extras
def rub_patches(shape, n=3, seed=0, avoid_boxes=None, strength=1.0, size=1.0):
    """
    Irregular rubbed / abraded areas. Returns a removal map (H,W) in 0..1: multiply ink alpha by (1 - rub).
    Inside a patch 30-50% of ink is removed in grainy clumps (x strength) plus a slight overall lift.
    avoid_boxes: list of (x0, y0, x1, y1) in output px that patches must not touch (key words, logos).
    size: patch size multiplier (default ~12% of the short side).
    """
    H, W = shape[:2]
    rg = np.random.default_rng(seed + 7)
    base = 0.12*min(H, W)*size
    blobs, tries = [], 0
    while len(blobs) < n and tries < 400:
        tries += 1
        rx = base*rg.uniform(0.8, 1.3); ry = base*rg.uniform(0.55, 1.1)
        cx = rg.uniform(0.05, 0.95)*W; cy = rg.uniform(0.05, 0.95)*H
        R = max(rx, ry)*1.25
        if avoid_boxes and any(cx+R > x0 and cx-R < x1 and cy+R > y0 and cy-R < y1 for x0, y0, x1, y1 in avoid_boxes):
            continue
        if any(math.hypot(cx-b[0], cy-b[1]) < (R + max(b[2], b[3])) for b in blobs):
            continue
        blobs.append((cx, cy, rx, ry, rg.uniform(-40, 40)))
    k = max(1.0, min(H, W)/2000.0)
    Y, X = np.mgrid[0:H, 0:W].astype(np.float32)
    M = np.zeros((H, W), np.float32)
    for cx, cy, rx, ry, rt in blobs:
        t = math.radians(rt)
        u = ((X-cx)*math.cos(t) + (Y-cy)*math.sin(t))/rx; v = (-(X-cx)*math.sin(t) + (Y-cy)*math.cos(t))/ry
        M = np.maximum(M, np.exp(-(u*u + v*v)*1.4))
    del X, Y
    M = np.clip((M + 0.22*_noise((H, W), 60*k, seed+71) + 0.10*_noise((H, W), 15*k, seed+72) - 0.35)*2.2, 0, 1)
    if avoid_boxes:
        for x0, y0, x1, y1 in avoid_boxes:
            M[int(max(0, y0)):int(y1), int(max(0, x0)):int(x1)] = 0
        M = ndi.gaussian_filter(M, 6*k)
    rubf = M*(0.30 + 0.20*np.clip(_noise((H, W), 40*k, seed+73)*0.5 + 0.5, 0, 1))*strength
    hf = ndi.gaussian_filter(np.random.default_rng(seed+74).standard_normal((H, W)).astype(np.float32), 0.8)
    hf = 0.75*hf/hf.std() + 0.45*_noise((H, W), 3, seed+75)
    uu = ndtr((hf - hf.mean())/hf.std())
    keep = np.clip((uu - rubf)/0.08 + 0.5, 0, 1)
    return (1 - keep*(1 - 0.12*M*strength)).astype(np.float32)


def bleed_halo(alpha, unit=1.0):
    """faint 1-2 px halo just outside heavy strokes (0..1). Tint paper with HALO_RGB at ~0.16*strength."""
    a = np.clip(alpha, 0, 1)
    return (np.clip(ndi.gaussian_filter(a, 1.6*unit) - a, 0, 1) * (ndi.gaussian_filter(a, 5*unit) > 0.30)).astype(np.float32)


def show_through(alpha, premult_rgb, paper_rgb, amount=1.0, grain=1.0):
    """
    Let the real paper show through the ink (works with load_paper() images and make_paper()).
    - grain: raised/lighter paper fibres take less ink (alpha lifted there), valleys hold it -> paper relief
      reads through solid ink instead of a flat fill;
    - tone: the ink colour is multiplied by the paper's local tone (relative to its mean), so ink on a warm or
      shaded part of the sheet picks up that colour.
    Returns (alpha, premult_rgb).
    """
    P = np.asarray(paper_rgb, np.float32)
    det = paper_detail(P, 2.5)                          # fine grain relief
    z = det/(det.std() + 1e-6)
    a2 = alpha*np.clip(1 - 0.16*amount*grain*np.clip(z, 0, 2.0) + 0.04*amount*grain*np.clip(-z, 0, 2.0), 0, 1)
    tone = np.clip(P/(P.reshape(-1, 3).mean(0) + 1e-6), 0.7, 1.3)
    tone = 1 + (tone - 1)*amount
    pr = premult_rgb*(a2/np.maximum(alpha, 1e-6))[..., None]*tone
    return a2, pr


def toner_grain(region_mask, density=0.3, seed=0, unit=1.0):
    """optional: clumpy photocopy-toner speckle inside a region (0..1 mask, or a density map). Returns 0/1 mask."""
    sh = region_mask.shape
    g = ndi.gaussian_filter(_noise(sh, 1, seed), 1.1*unit) + 0.30*_noise(sh, 4*unit, seed+1) + 0.22*_noise(sh, 25*unit, seed+2)
    g = (g - g.mean())/g.std()
    dens = np.clip(np.asarray(density, np.float32)*np.ones(sh, np.float32), 0.005, 0.7)
    return ((g > ndtri(1 - dens)) & (np.asarray(region_mask) > 0.5)).astype(np.float32)


PAPER_TONES = {
    # target mean colour, low-freq unevenness, edge browning amount, edge colour
    'vintage': dict(target='#EAD9AC', uneven=0.018, edge=0.07, edge_col='#C9A86E'),
    'aged':    dict(target='#E2CB93', uneven=0.020, edge=0.20, edge_col='#B08A50'),
}


def tone_paper(paper_rgb, tone='vintage', seed=0):
    """
    Colour-grade a paper image while keeping its luminance texture: every pixel becomes
    target * (pixel luminance / mean luminance), so grain and fibres keep their relative relief; the sheet's mean
    lands on the target. 'vintage'/'aged' add subtle low-frequency uneven yellowing and darker, browner edges
    (irregular, noise-modulated). tone: 'none' | 'vintage' | 'aged' | '#RRGGBB' (plain grade, no edge browning)
    | dict(target=, uneven=, edge=, edge_col=).
    """
    if tone is None or tone == 'none':
        return np.asarray(paper_rgb, np.uint8)
    cfg = dict(PAPER_TONES[tone]) if isinstance(tone, str) and tone in PAPER_TONES else \
        (dict(tone) if isinstance(tone, dict) else dict(target=tone, uneven=0.0, edge=0.0, edge_col='#B08A50'))
    P = np.asarray(paper_rgb, np.float32); h, w = P.shape[:2]
    L = P.mean(axis=2, keepdims=True)
    rel = L/(L.mean() + 1e-6)                                # luminance texture, mean 1
    chroma = (P - L)/(L + 1e-6)                              # keep a little of the original fibre colour
    out = _hex(cfg['target'])*rel*(1 + 0.25*chroma)
    k = max(1.0, min(w, h)/1000.0)
    if cfg.get('uneven'):
        lf = 0.65*_noise((h, w), 220*k, seed+201) + 0.35*_noise((h, w), 70*k, seed+202)
        out *= (1 + cfg['uneven']*lf)[..., None]
        out[..., 2] *= (1 - 0.6*cfg['uneven']*np.clip(lf, 0, None))          # yellower where it is darker
    if cfg.get('edge'):
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        de = np.minimum(np.minimum(xx, w-1-xx), np.minimum(yy, h-1-yy))/(0.5*min(w, h))   # 0 edge .. 1 centre
        de = de + 0.06*_noise((h, w), 90*k, seed+203)                                       # irregular front
        e = np.clip(1 - de/0.32, 0, 1)**1.6*cfg['edge']
        ec = _hex(cfg['edge_col'])/(_hex(cfg['target']) + 1e-6)
        out *= (1 - e[..., None]*(1 - ec))
    return np.clip(out, 0, 255).astype(np.uint8)


def load_paper(path, w, h, mode='cover', scale=1.0, tint=None, seed=0, offset=None, tone='none'):
    """
    Load a user paper image as the base layer, at exactly (h, w, 3) uint8. Colour is untouched by default.
      path : file path, PIL image or array.
      mode : 'cover'   (default) scale to fill the target, then centre-crop. Nothing is stretched.
             'tile'    keep the texture at native size (x scale) and mirror-tile it over the target.
             'stretch' resize straight to (w, h) (distorts the grain if aspect ratios differ).
      scale: texture magnification (2.0 = grain twice as coarse relative to the canvas). In 'cover', values < 1
             shrink the texture and mirror-tile it; > 1 crops a smaller area and enlarges it.
      tint : None | colour | (colour, amount): luminance-preserving tint toward a colour (e.g. aged cream).
      seed : picks the crop/tile offset for 'tile' (and for 'cover' when scale > 1) unless offset=(x, y) is given.
      tone : 'none' (as-is, default) | 'vintage' (warm yellow ~#EAD9AC) | 'aged' (deeper ~#E2CB93, browner edges)
             | '#RRGGBB' custom target | dict -- see tone_paper(). Keeps the paper's own grain and fibres.
    Resampling is Lanczos; mirror tiling avoids visible seams.
    """
    if path is None or (isinstance(path, str) and not os.path.exists(path)):
        import sys as _s
        print(f"[aged_ink] paper {path!r} not found; using generated paper (put a real paper photo in papers/ for best results)", file=_s.stderr)
        return make_paper(w, h, seed=seed)
    im = path if isinstance(path, Image.Image) else (Image.fromarray(np.asarray(path, np.uint8)) if not isinstance(path, str) else Image.open(path))
    im = im.convert('RGB'); iw, ih = im.size
    if mode == 'stretch':
        out = np.asarray(im.resize((w, h), Image.LANCZOS), np.float32)
    else:
        f = (max(w/iw, h/ih) if mode == 'cover' else 1.0) * scale
        nw, nh = max(1, int(round(iw*f))), max(1, int(round(ih*f)))
        arr = np.asarray(im.resize((nw, nh), Image.LANCZOS) if (nw, nh) != (iw, ih) else im, np.float32)
        if nw < w or nh < h:                                   # mirror-tile (no seams)
            ry, rx = -(-h // nh) + 1, -(-w // nw) + 1
            row = np.concatenate([arr if i % 2 == 0 else arr[:, ::-1] for i in range(rx)], 1)
            arr = np.concatenate([row if j % 2 == 0 else row[::-1] for j in range(ry)], 0)
        AH, AW = arr.shape[:2]
        if offset is not None:
            ox, oy = offset
        elif mode == 'tile' or scale > 1.0:
            rg = np.random.default_rng(seed); ox = int(rg.integers(0, AW - w + 1)); oy = int(rg.integers(0, AH - h + 1))
        else:
            ox, oy = (AW - w)//2, (AH - h)//2                  # centre crop
        out = arr[oy:oy+h, ox:ox+w]
    if tint is not None:
        col, amt = (tint if (isinstance(tint, tuple) and len(tint) == 2 and not isinstance(tint[0], (int, float))) else (tint, 1.0))
        c = _hex(col); L = out.mean(axis=2, keepdims=True); Lm = L.mean()
        out = out*(1 - amt) + (L/Lm*c)*amt
    out = np.clip(out, 0, 255).astype(np.uint8)
    return tone_paper(out, tone, seed)


def paper_detail(paper_rgb, sigma=None):
    """luminance detail of a paper image: (lum / local mean) - 1, i.e. the grain/fibre relief (about +-0.05)."""
    P = np.asarray(paper_rgb, np.float32); L = P.mean(axis=2)
    sg = sigma if sigma else max(6.0, min(L.shape)/120.0)
    return L/(ndi.gaussian_filter(L, sg) + 1e-6) - 1.0


def make_paper(w, h, base='#EEE8DA', seed=0, grain=1.0, stains=True, vignette=True):
    """aged paper: multi-scale grain, fibres, faint foxing stains, vignette. Returns uint8 (h,w,3)."""
    from PIL import ImageDraw
    rg = np.random.default_rng(seed)
    k = max(1.0, min(w, h)/2000.0)
    img = np.ones((h, w, 3), np.float32)*_hex(base)
    gr = (_noise((h, w), 1, seed+1)*1.6 + _noise((h, w), 2*k, seed+2)*2.4 + _noise((h, w), 12*k, seed+3)*3.0 + _noise((h, w), 140*k, seed+4)*4.0)*grain
    img += gr[..., None]
    fib = Image.new('L', (w, h), 0); df = ImageDraw.Draw(fib)
    for _ in range(int(350*w*h/4.9e6) + 20):
        x, y = rg.uniform(0, w), rg.uniform(0, h); t = rg.uniform(0, math.pi); l = rg.uniform(6, 30)*k
        df.line([(x, y), (x+l*math.cos(t), y+l*math.sin(t))], fill=int(rg.uniform(20, 60)), width=1)
    img -= (np.asarray(fib, np.float32)/255*14*grain)[..., None]
    if stains:
        fox = np.zeros((h, w), np.float32)
        for _ in range(max(3, int(8*w*h/4.9e6))):
            fox[rg.integers(0, h), rg.integers(0, w)] = rg.uniform(0.5, 1)
        fox = np.clip(ndi.gaussian_filter(fox, 18*k)*900*k*k, 0, 1)
        img -= fox[..., None]*np.array([8, 14, 26])
    if vignette:
        vy, vx = np.mgrid[0:h, 0:w]
        img *= (1 - (((vx/w-0.5)**2 + (vy/h-0.5)**2)*0.07))[..., None]
    return np.clip(img, 0, 255).astype(np.uint8)


# ----------------------------------------------------------------------------- paper fibres / feathering
def fibre_field(paper_rgb, sigma=1.0, rho=5.0):
    """
    Fibre structure of a (real) paper image, at its own resolution:
      dy, dx : unit fibre direction (structure tensor: direction of least intensity change, smoothed by rho px)
      coh    : coherence 0..1 (how strongly oriented the grain is there)
      ridge  : thin dark fibre channels (Hessian valley measure, ~N(0,1) normalised, >0 = channel)
      grain  : fine relief (paper_detail, normalised; >0 raised/light fibre, <0 valley)
    """
    P = np.asarray(paper_rgb, np.float32); L = P.mean(axis=2)
    Ix = ndi.gaussian_filter(L, sigma, order=(0, 1)); Iy = ndi.gaussian_filter(L, sigma, order=(1, 0))
    Jxx = ndi.gaussian_filter(Ix*Ix, rho); Jyy = ndi.gaussian_filter(Iy*Iy, rho); Jxy = ndi.gaussian_filter(Ix*Iy, rho)
    tg = 0.5*np.arctan2(2*Jxy, Jxx - Jyy); tf = tg + np.pi/2
    coh = np.sqrt((Jxx - Jyy)**2 + 4*Jxy**2)/(Jxx + Jyy + 1e-6)
    s1 = 1.2
    Hxx = ndi.gaussian_filter(L, s1, order=(0, 2)); Hyy = ndi.gaussian_filter(L, s1, order=(2, 0))
    Hxy = ndi.gaussian_filter(L, s1, order=(1, 1))
    lam = 0.5*(Hxx + Hyy + np.sqrt((Hxx - Hyy)**2 + 4*Hxy**2))       # >0 across a dark line
    lam = lam - ndi.gaussian_filter(lam, 12); ridge = lam/(lam.std() + 1e-6)
    z = paper_detail(P, 2.5); z = z/(z.std() + 1e-6)
    return dict(dy=np.sin(tf).astype(np.float32), dx=np.cos(tf).astype(np.float32), coh=coh.astype(np.float32),
                ridge=ridge.astype(np.float32), grain=z.astype(np.float32))


def _up_dir(dy, dx, S):
    """upsample a direction field by S (double-angle interpolation, so +d and -d don't cancel)"""
    c2 = ndi.zoom(dx*dx - dy*dy, S, order=1); s2 = ndi.zoom(2*dx*dy, S, order=1)
    t = 0.5*np.arctan2(s2, c2); return np.sin(t).astype(np.float32), np.cos(t).astype(np.float32)


def lic(noise, dy, dx, L=6, step=1.0):
    """line-integral convolution: average `noise` along the streamlines of (dy, dx) -> fibre-aligned streaks"""
    H, W = noise.shape
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    acc = noise.astype(np.float32).copy(); n = 1
    for sg in (1.0, -1.0):
        py, px = yy.copy(), xx.copy()
        vy, vx = dy.copy(), dx.copy()
        for k in range(L):
            iy = np.clip(np.rint(py), 0, H-1).astype(np.int32); ix = np.clip(np.rint(px), 0, W-1).astype(np.int32)
            ny, nx = dy[iy, ix], dx[iy, ix]
            flip = np.where(ny*vy + nx*vx < 0, -1.0, 1.0).astype(np.float32)   # keep heading consistent
            vy, vx = ny*flip, nx*flip
            py = py + sg*step*vy; px = px + sg*step*vx
            acc += ndi.map_coordinates(noise, [py, px], order=1, mode='reflect'); n += 1
    return acc/n


def feather_spec(paper_rgb, S=2, reach=6.0, density=1.0, rag=1.0, strand_w=1.0, fibre=None):
    """
    Fibrous ink-bleed spec for age_prepare(feather=...) / composite layer opts {'feather': spec}.
      paper_rgb : the paper at OUTPUT resolution (fibre field is measured on it), S: mask supersample factor.
      reach     : max strand length in output px (strands vary 0..reach along the edge, many absent).
      density   : how many fibre channels carry strands (1 = default, 0 = no strands).
      rag       : edge raggedness amount (fibre-aligned, 2-4 output px scale at 1).
      strand_w  : strand thickness multiplier.
    """
    ff = fibre if fibre is not None else fibre_field(paper_rgb)
    dy, dx = _up_dir(ff['dy'], ff['dx'], S)
    return dict(S=S, dy=dy, dx=dx, ridge=ndi.zoom(ff['ridge'], S, order=1), grain=ndi.zoom(ff['grain'], S, order=1),
                reach=float(reach), density=float(density), rag=float(rag), strand_w=float(strand_w))


def _feather_prepare(F, fe, seed):
    """add fibre-aligned edge raggedness to F['b'] and precompute discrete outward ink strands (in place)"""
    m = F['m']; u = F['u']; sh = m.shape; S = fe['S']
    ys, xs = np.nonzero(m > 0.05)
    if len(ys) == 0:
        return
    R = int(np.ceil(fe['reach']*S)) + 8
    y0, y1, x0, x1 = max(0, ys.min()-R), min(sh[0], ys.max()+R+1), max(0, xs.min()-R), min(sh[1], xs.max()+R+1)
    cs = (slice(y0, y1), slice(x0, x1)); ch = (y1-y0, x1-x0)
    dy, dx = fe['dy'][cs], fe['dx'][cs]; ridge = fe['ridge'][cs]; grain = fe['grain'][cs]
    rg = np.random.default_rng(seed*7 + 5)
    wsig = 0.55*S*fe['strand_w']
    wn = ndi.gaussian_filter(rg.standard_normal(ch).astype(np.float32), wsig)
    st = lic(wn, dy, dx, L=int(3*S + 2), step=1.0); st = st/(st.std() + 1e-6)
    fibre = 0.65*st + 0.35*np.clip(ridge, -2, 3)            # fibre channels: streaks aligned to the real grain
    fibre = fibre/(fibre.std() + 1e-6)
    # -- edge raggedness (2-4 output px), only in the edge band of the blurred plate
    b = F['b'][cs]
    band = np.clip(4*b*(1 - b), 0, 1)
    n2 = _noise(ch, 1.3*S, seed*31 + 1); n2 = n2/(n2.std() + 1e-6)
    rn = 0.55*fibre + 0.30*n2 - 0.25*np.clip(grain, -2, 2)
    F['b'][cs] = b + 0.11*fe['rag']*band*np.clip(rn, -3, 3)
    C0 = F['b'][cs] > 0.5
    if fe['density'] <= 0 or fe['reach'] <= 0:
        return
    # -- strands: march out of the inked shape along the local fibre direction
    K = int(np.ceil(fe['reach']*S*min(1.0, max(0.5, u/2.0))))
    dout = ndi.distance_transform_edt(~C0)
    by, bx = np.nonzero((dout > 0) & (dout <= K))
    vy, vx = dy[by, bx], dx[by, bx]
    dist = np.full(len(by), np.inf, np.float32); ry = np.zeros(len(by), np.int32); rx = np.zeros(len(by), np.int32)
    for k in range(1, K + 1):
        for sg in (1, -1):
            py = np.clip(np.rint(by + sg*k*vy), 0, ch[0]-1).astype(np.int32)
            px = np.clip(np.rint(bx + sg*k*vx), 0, ch[1]-1).astype(np.int32)
            hit = C0[py, px] & ~np.isfinite(dist)
            dist[hit] = k; ry[hit] = py[hit]; rx[hit] = px[hit]
    ok = np.isfinite(dist)
    by, bx, dist, ry, rx = by[ok], bx[ok], dist[ok], ry[ok], rx[ok]
    # per-location reach: varies along the edge (~4 output px scale), absent in many places
    nr = _noise(ch, 2.2*S, seed*31 + 2); nr = nr/(nr.std() + 1e-6)
    reach = K*np.clip(0.15 + 0.5*nr[ry, rx] + 0.25*fibre[ry, rx], 0, 1)**1.2
    thr = 1.05 - 0.35*(fe['density'] - 1)
    on = np.clip((fibre[by, bx] - thr)/0.45, 0, 1)          # thin strand cross-section
    hf = rg.standard_normal(len(by)).astype(np.float32)
    grains = (hf > -1.3).astype(np.float32)                   # a few breaks -> grains, not lines
    tip = np.clip(dist/np.maximum(reach, 1e-3), 0, 1)
    a = on*(dist <= reach)*grains*(0.95 - 0.5*tip)
    keep = a > 0.02
    W = sh[1]
    F['fe_idx'] = ((by[keep] + y0)*W + bx[keep] + x0).astype(np.int64)
    F['fe_root'] = ((ry[keep] + y0)*W + rx[keep] + x0).astype(np.int64)
    F['fe_a'] = a[keep].astype(np.float32)


# ----------------------------------------------------------------------------- full pipeline
_FK = dict(feather_reach='reach', feather_density='density', strand_width='strand_w')


def composite(paper_rgb, layers, strength=1.0, seed=0, supersample=1, unit=None, rub=3, avoid_boxes=None,
              halo=True, text_rub=0.45, paper_show=True, return_info=False, paper_mode='cover', paper_scale=1.0,
              paper_tint=None, paper_tone='none', ink=None, paper_grain=1.0, style='aged', feather=None):
    """
    paper_rgb  : (H,W,3) uint8/float background (kept as-is outside the ink) OR a path to a paper image
                 (preferred: the user's own paper scan/photo) -> load_paper(path, W, H, paper_mode, paper_scale,
                 paper_tint, tone=paper_tone) with W, H = mask size / supersample.
    layers     : list of (mask, kind) or (mask, kind, opts). mask at (H*supersample, W*supersample), 0..1/0..255.
                 opts may hold glyph_boxes (in mask px), 'color' (hex/RGB -> tint ink of this layer, e.g. red),
                 'strength' (per-layer multiplier), 'unit' (per-layer scale: give small type its own layer
                 with a smaller unit) and any age_layer override (e.g. solid_pits=0.4 for big solid areas).
                 Layers are printed in order (later on top).
    strength   : global 0..1. supersample: mask scale factor. unit: default supersample/2 (reference was 2x).
    rub        : number of rubbed patches (0 = none). avoid_boxes: output-px boxes rubs must not touch.
    text_rub   : text receives this fraction of the rub (keeps worn words legible).
    style      : 'aged' (default, this function) or 'fresh' (-> fresh_print(): no ageing/rub/halo, feathered).
    feather    : None (clean edges, default) | True | dict of feather_spec kwargs | a feather_spec() result:
                 feathered fibrous edges under the ageing (aged print of the fresh print). For style='fresh'
                 a kwargs dict (feather_reach, feather_density, rag, strand_width) tunes the fresh feathering.
    ink        : base ink colour for all non-'color' layers (hex/RGB, e.g. '#1d1d1f'); None = classic #111.
                 A layer's opts may also carry its own 'ink', and 'feather' (see feather_spec()) for fibrous
                 ink-bleed edges ('text' kind). paper_grain: multiplier on the paper-grain lift inside the ink.
    Returns uint8 (H,W,3) [, info dict with per-layer 'degraded'].
    """
    S = int(supersample)
    if isinstance(paper_rgb, (str, Image.Image)):
        mh, mw = np.asarray(layers[0][0]).shape[:2]
        paper_rgb = load_paper(paper_rgb, mw//S, mh//S, paper_mode, paper_scale, paper_tint, seed, tone=paper_tone)
    if style == 'fresh':
        fk = feather if isinstance(feather, dict) and 'dy' not in feather else {}
        return fresh_print(paper_rgb, layers, ink='#1d1d1f' if ink is None else ink, seed=seed, supersample=S,
                           strength=strength, unit=unit, ink_grain=paper_grain, **fk)
    if feather is not None and feather is not False:            # aged print on the feathered (fresh) edges
        spec = feather if isinstance(feather, dict) and 'dy' in feather else \
            feather_spec(np.asarray(paper_rgb, np.float32), S, **{_FK.get(k, k): v for k, v in
                                                                  (feather.items() if isinstance(feather, dict) else [])})
        layers = [(L[0], L[1], dict(L[2]) if len(L) > 2 else {}) for L in layers]
        for L in layers:
            L[2].setdefault('feather', spec)
    P = np.asarray(paper_rgb, np.float32).copy()
    H, W = P.shape[:2]
    u = S/2.0 if unit is None else unit
    outs, info = [], dict(degraded={})
    for i, L in enumerate(layers):
        mask, kind = L[0], L[1]; opts = dict(L[2]) if len(L) > 2 else {}
        color = opts.pop('color', None); ls = opts.pop('strength', 1.0); lu = opts.pop('unit', u)
        lk = opts.pop('ink', ink); fe = opts.pop('feather', None)
        a, rgb, inf = age_layer(mask, kind, strength*ls, seed + 101*(i+1), unit=lu, ink=lk, feather=fe, **opts)
        if color is not None:                       # coloured ink: keep hue, fade it toward lighter tone
            c = _hex(color); fade = np.clip(inf['fade']/0.42, 0, 1)[..., None]
            rgb = (c + (np.array([200, 190, 175], np.float32) - c)*0.35*fade).astype(np.float32)
        A = _down(a, S); Pm = _down(rgb*a[..., None], S)
        info['degraded'][f'{i}:{kind}'] = round(inf['degraded']*100, 1)
        outs.append([A, Pm, kind])
        del a, rgb
    if rub and strength > 0:
        R = rub_patches((H, W), rub, seed, avoid_boxes, strength)
        for o in outs:
            f = text_rub if o[2] == 'text' else 1.0
            o[0] = o[0]*(1 - R*f); o[1] = o[1]*(1 - R*f)[..., None]
    if paper_show:
        for o in outs:
            o[0], o[1] = show_through(o[0], o[1], P, strength, paper_grain)
    if halo and strength > 0:
        At = np.clip(sum(o[0] for o in outs), 0, 1)
        hl = bleed_halo(At, max(0.5, u*2.0/S))*0.20*strength
        P = P*(1 - hl[..., None]*(1 - HALO_RGB/255.0))      # multiply blend: tints, keeps the paper texture
    for A, Pm, _ in outs:
        P = P*(1 - A[..., None]) + Pm
    out = np.clip(P, 0, 255).astype(np.uint8)
    return (out, info) if return_info else out


# ----------------------------------------------------------------------------- shared print pipeline (fresh / aged)
REF_CAP = 130.0          # cap height (px, at output res) that unit=1.0 corresponds to (text_masks units)


def text_masks(W, H, lines, S=2):
    """
    Render centred text lines to ink masks at S x resolution.
      lines: list of (text, font_path, size_px_at_output, y_centre_frac).
    Returns list of (mask (H*S, W*S) float 0..1, cap_height_px_at_S, unit) -- unit = cap/REF_CAP (clipped 0.3..3).
    """
    out = []
    for ln in lines:
        text, fp, size, yc = ln[:4]
        f = ImageFont.truetype(fp, int(size*S))
        im = Image.new('L', (W*S, H*S), 0); d = ImageDraw.Draw(im)
        tw = d.textlength(text, font=f); bb = f.getbbox('H')
        d.text(((W*S - tw)/2, yc*H*S), text, font=f, fill=255, anchor='lm')
        cap = float(bb[3]-bb[1])
        out.append((np.asarray(im, np.float32)/255.0, cap, float(np.clip(cap/REF_CAP, 0.3, 3.0))))
    return out


def _split_balanced(words, k, width):
    """split words into k lines minimising the widest line (exhaustive over break points for k<=3)"""
    import itertools
    best = None
    for cuts in itertools.combinations(range(1, len(words)), k - 1):
        b = (0,) + cuts + (len(words),)
        ls = [' '.join(words[b[i]:b[i+1]]) for i in range(k)]
        w = max(width(x) for x in ls)
        if best is None or w < best[0] - 1e-6:
            best = (w, ls)
    return best[1] if best else [' '.join(words)]


def layout_text(W, H, title, subtitle=None, title_font=None, sub_font=None, title_size=190, sub_size=62,
                title_y=0.43, sub_y=None, wrap='auto', max_width=0.78, line_spacing=1.42, sub_gap=1.25):
    """
    Lines for text_masks(): [(text, font, size, y_frac, role)], role 'title' or 'sub'.
      title    : '|' forces line breaks; wrap='auto' balances the title over the fewest lines that fit within
                 max_width*W (wrap='none' keeps one line).
      single-line title: placed at title_y and the subtitle at sub_y (default 0.60) -- the classic layout.
      multi-line title: the block is centred on title_y with line_spacing*size pitch; the subtitle sits
                 sub_gap*title_size below the last line unless sub_y is given.
    """
    f = ImageFont.truetype(title_font, int(title_size))
    width = lambda t: f.getlength(t)
    if '|' in title:
        tl = [x.strip() for x in title.split('|')]
    elif wrap == 'auto' and width(title) > max_width*W and len(title.split()) > 1:
        words = title.split(); k = 2
        while k < min(4, len(words)) and width(_split_balanced(words, k, width)[0]) > max_width*W and \
                max(width(x) for x in _split_balanced(words, k, width)) > max_width*W:
            k += 1
        tl = _split_balanced(words, k, width)
    else:
        tl = [title]
    out = []
    if len(tl) == 1:
        out.append((tl[0], title_font, title_size, title_y, 'title'))
        if subtitle:
            out.append((subtitle, sub_font, sub_size, 0.60 if sub_y is None else sub_y, 'sub'))
        return out
    pitch = line_spacing*title_size/H
    ys = [title_y + (i - (len(tl) - 1)/2)*pitch for i in range(len(tl))]
    for t, y in zip(tl, ys):
        out.append((t, title_font, title_size, y, 'title'))
    if subtitle:
        out.append((subtitle, sub_font, sub_size, ys[-1] + sub_gap*title_size/H + 0.5*sub_size/H if sub_y is None else sub_y, 'sub'))
    return out


def prepare_print(layers, strength=1.0, seed=0, supersample=1, unit=None, feather=None, ink=None):
    """
    Precompute every layer of a print (fresh or aged) once. layers as in composite(): (mask, kind[, opts]).
    feather: a feather_spec() dict applied to every layer that has no opts['feather'] (None = clean edges).
    Returns a list of dicts (F, kind, color, ink) for print_layers()/render_print().
    """
    S = int(supersample); u = S/2.0 if unit is None else unit
    out = []
    for i, L in enumerate(layers):
        mask, kind = L[0], L[1]; opts = dict(L[2]) if len(L) > 2 else {}
        color = opts.pop('color', None); ls = opts.pop('strength', 1.0); lu = opts.pop('unit', u)
        lk = opts.pop('ink', ink); fe = opts.pop('feather', feather)
        F = age_prepare(mask, kind, strength*ls, seed + 101*(i+1), unit=lu, feather=fe, **opts)
        out.append(dict(F=F, kind=kind, color=color, ink=lk))
    return out


def print_layers(prepared, q, supersample=1, sweep=3.5):
    """per-layer (alpha, premult_rgb, kind) at output resolution, ageing progress q (0 = fresh, 1 = aged)"""
    S = int(supersample); out = []
    for L in prepared:
        a, rgb, inf = age_apply(L['F'], q, sweep, ink=L['ink'])
        if L['color'] is not None:
            c = _hex(L['color']); fade = np.clip(inf['fade']/0.42, 0, 1)[..., None]
            rgb = (c + (np.array([200, 190, 175], np.float32) - c)*0.35*fade).astype(np.float32)
        out.append([_down(a, S), _down(rgb*a[..., None], S), L['kind']])
    return out


def render_print(paper_rgb, prepared, q=1.0, supersample=1, strength=1.0, seed=0, rub=3, avoid_boxes=None,
                 text_rub=0.45, halo=0.0, paper_show=True, paper_grain=1.0, unit=None, sweep=3.5, layers_out=None):
    """
    Composite prepared layers over the paper at ageing progress q:
      q = 0 -> FRESH print (clean plate + feathering, no rub, no halo); q = 1 -> AGED print; in between = the
      ageing animation (same noise fields, thresholds swept: no flicker). rub patches ramp in with q.
    halo: bleed-halo amount (0 = off). Returns uint8 (H,W,3).
    """
    P = np.asarray(paper_rgb, np.float32)
    H, W = P.shape[:2]; S = int(supersample); u = S/2.0 if unit is None else unit
    outs = layers_out if layers_out is not None else print_layers(prepared, q, S, sweep)
    if rub and q > 0 and strength > 0:
        R = rub_patches((H, W), rub, seed, avoid_boxes, strength*q)*min(1.0, q*4)
        for o in outs:
            f = text_rub if o[2] == 'text' else 1.0
            o[0] = o[0]*(1 - R*f); o[1] = o[1]*(1 - R*f)[..., None]
    if paper_show:
        for o in outs:
            o[0], o[1] = show_through(o[0], o[1], P, strength, paper_grain)
    Q = P
    if halo and q > 0 and strength > 0:
        At = np.clip(sum(o[0] for o in outs), 0, 1)
        hl = bleed_halo(At, max(0.5, u*2.0/S))*0.20*strength*q*halo
        Q = P*(1 - hl[..., None]*(1 - HALO_RGB/255.0))
    for A, Pm, _ in outs:
        Q = Q*(1 - A[..., None]) + Pm
    return np.clip(Q, 0, 255).astype(np.uint8)


def fresh_print(paper, layers, ink='#1d1d1f', feather_reach=6.0, feather_density=1.0, rag=1.0, strand_width=1.0,
                ink_grain=1.3, seed=0, supersample=2, strength=1.0, unit=None, paper_mode='cover', paper_scale=1.0,
                paper_tint=None, paper_tone='none', return_spec=False):
    """
    FRESH print still: just-printed ink on real paper -- #1d1d1f ink multiplied with the paper, fibre-aligned
    ragged edges + discrete fibre strands wicking out along the paper grain (feather_spec), paper-grain lift
    inside strokes (ink_grain), no ageing, no rub, no halo. Same edges/seeds as the aged print, so
    composite(..., style='aged', feather=True, ink=ink, paper_grain=ink_grain, halo=False) is this print, aged.
      paper  : (H,W,3) array at OUTPUT res, or a path (-> load_paper(path, W, H, paper_mode, paper_scale, ...)).
      layers : (mask, kind[, opts]) at (H*supersample, W*supersample) -- text / line / pattern. Strands on all
               kinds; edge raggedness on 'text' (line/pattern keep their own toner edge).
    """
    S = int(supersample)
    if isinstance(paper, (str, Image.Image)):
        mh, mw = np.asarray(layers[0][0]).shape[:2]
        paper = load_paper(paper, mw//S, mh//S, paper_mode, paper_scale, paper_tint, seed, tone=paper_tone)
    P = np.asarray(paper, np.float32)
    spec = feather_spec(P, S, feather_reach, feather_density, rag, strand_width)
    prep = prepare_print(layers, strength, seed, S, unit, feather=spec, ink=ink)
    out = render_print(P, prep, 0.0, S, strength, seed, rub=0, halo=0.0, paper_grain=ink_grain, unit=unit)
    return (out, spec) if return_spec else out
