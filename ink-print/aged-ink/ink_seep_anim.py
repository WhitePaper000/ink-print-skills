#!/usr/bin/env python3
"""
Ink-seep text animation in the aged-ink style.

Timeline: empty paper -> ink wicks up through the paper from scattered points inside the glyphs (soft, blotchy,
capillary, feathered, lighter at first) -> converges to crisp, fully inked text -> short hold -> quick ageing
(threshold sweep over the SAME deterministic noise fields as aged_ink.age_layer: no flicker) -> hold on the aged
result. The final frame equals aged_ink.composite() of the same layers (checked at the end of a run).

  python3 ink_seep_anim.py --title "The Quiet Archive" --subtitle "records kept in ink" \
      --out out/ink_seep.mp4 --stills out/ [--fps 60] [--durations 0.3,2.2,0.4,0.5,1.8] \
      [--paper papers/user_paper_01.jpg --paper-scale 1.6 --tone vintage] [--seed 7] [--strength 1.0]
      [--ink '#1d1d1f'] [--halo 0]   (v2: glyph-confined geodesic seep, no outline; previous: ink_seep_anim_v1.py)
"""
import argparse, os, subprocess, sys, time
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import aged_ink as ai

REF_CAP = 130.0          # cap height (px, at working res) that unit=1.0 corresponds to


def smooth(e0, e1, x):
    t = np.clip((x - e0)/(e1 - e0), 0, 1); return t*t*(3 - 2*t)


def render_lines(W, H, S, lines):
    """lines: list of (text, font_path, size_px_at_output, y_centre_frac). Returns per-line masks at S x res, caps."""
    out = []
    for text, fp, size, yc in lines:
        f = ImageFont.truetype(fp, int(size*S))
        im = Image.new('L', (W*S, H*S), 0); d = ImageDraw.Draw(im)
        tw = d.textlength(text, font=f); bb = f.getbbox('H')
        d.text(((W*S - tw)/2, yc*H*S), text, font=f, fill=255, anchor='lm')
        out.append((np.asarray(im, np.float32)/255.0, float(bb[3]-bb[1])))
    return out


def ease(x):
    """smootherstep ease-in-out (C2: no velocity/acceleration jumps)"""
    t = np.clip(x, 0, 1); return t*t*t*(t*(6*t - 15) + 10)


EASES = {
    'linear': lambda x: x,
    'inOutCubic': lambda x: np.where(x < 0.5, 4*x**3, 1 - (-2*x + 2)**3/2),
    'outCubic': lambda x: 1 - (1 - x)**3,
    'inOutSine': lambda x: 0.5 - 0.5*np.cos(np.pi*x),
    'inOutQuad': lambda x: np.where(x < 0.5, 2*x*x, 1 - (-2*x + 2)**2/2),
}


def stagger_inverse(xn, name):
    """start-time fraction for a glyph at normalised x so the sweep FRONT moves as x = ease(t)"""
    tt = np.linspace(0, 1, 4001); xs = EASES[name](tt)
    return np.interp(np.clip(xn, 0, 1), xs, tt)


SEPIA = np.array([0x6a, 0x55, 0x40], np.float32)       # faint warm tint of the lightest fresh ink
WARM_WASH = np.array([0x7a, 0x66, 0x50], np.float32)     # warm tint of dilute, just-arrived ink


class Seep:
    """
    Granular, fibre-guided seep, confined to the (feathered) printed shape A0 -- no ink ever outside it:
      * ink appears first at many tiny pinpoints (1-3 px) on the paper's absorbent spots (fine grain valleys and
        fibre channels), scattered over the whole stroke area;
      * from each point it wicks along the paper fibres: geodesic travel time (skimage MCP) over a cost map that
        is cheap along fibre streaks (LIC of noise along the paper's structure-tensor fibre direction) and dark
        fibre channels, expensive across raised grain -> anisotropic, fibre-aligned growth into threads;
      * arrival time = high-frequency (point start + fibre travel) with only a weak large-scale term for
        coherence, CDF-remapped so the title emerges evenly; strands at the edges fill last via their fibres;
      * per-pixel soft arrival ramp + slower deepening ramp: light warm wash -> full ink.
    """
    def __init__(self, A0, ff, paper, seed, d_seep, ramp_s=0.22, deepen_s=0.65, spacing=6.0, lowfreq=0.25,
                 fibre_bias=0.6, hf_w=0.55, glyph_dur=0.5, sweep_starts=0.75, stagger_ease='inOutCubic',
                 sub_delay=0.05, lr_bias=0.25, split_y=None, axis_w=1.0, order='x', line_info=None, glyph_merge=1,
                 grain_w=0.35, along_w=0.12, glyph_ramp=0.18, glyph_deepen=0.45,
                 arrival_frames=1.5, fps=60, ridge_light=0.2,
                 init_density=0.5, density_spread=0.15, deepen_time=0.28, tint=0.12):
        from skimage.graph import MCP_Geometric
        self.span = 0.58
        H, W = A0.shape; sh = (H, W)
        rg = np.random.default_rng(seed + 900)
        self.A0 = A0
        ys, xs = np.nonzero(A0 > 0.01)
        y0, y1, x0, x1 = max(0, ys.min()-4), min(H, ys.max()+5), max(0, xs.min()-4), min(W, xs.max()+5)
        cs = (slice(y0, y1), slice(x0, x1)); ch = (y1-y0, x1-x0); self.box = (y0, y1, x0, x1)
        A = A0[cs]; G = A > 0.06; core = A > 0.5
        z = ff['grain'][cs]; ridge = ff['ridge'][cs]
        wn = ndi.gaussian_filter(rg.standard_normal(ch).astype(np.float32), 0.6)
        st = ai.lic(wn, ff['dy'][cs], ff['dx'][cs], L=5); st /= st.std() + 1e-6
        fib = 0.55*st + 0.30*np.clip(ridge, -2, 3) - 0.35*np.clip(z, -2.5, 2.5)
        fib = fib/(fib.std() + 1e-6)                                  # >0: absorbent fibre channel / valley
        self.fib = fib.astype(np.float32); self.z = z
        cost = np.exp(-fibre_bias*np.clip(fib, -2.5, 2.5))
        cost = np.where(G, np.clip(cost, 0.15, 6), 1e5).astype(np.float64)
        # pinpoint seeds: local maxima of absorbency inside the strokes, thinned to ~1 per spacing^2
        pk = (ndi.maximum_filter(fib, size=3) == fib) & core & (fib > 0.2)
        py, px = np.nonzero(pk)
        want = int(core.sum()/(spacing*spacing))
        if len(py) > want:
            sel = rg.choice(len(py), want, replace=False); py, px = py[sel], px[sel]
        lab, nl = ndi.label(G)                                   # every isolated piece gets a point
        have = set(lab[py, px].tolist())
        extra = [np.unravel_index(np.argmax(np.where(lab == k, A + 0.01*fib, -9)), ch) for k in range(1, nl+1) if k not in have]
        if extra:
            ey, ex = np.array(extra).T; py = np.concatenate([py, ey]); px = np.concatenate([px, ex])
        # start times: high-frequency (random + absorbency) with a weak large-scale term for coherence
        lf = ai._noise(ch, 90, seed+905); lf = (lf - lf.mean())/(lf.std() + 1e-6)
        r = rg.random(len(py)) - 0.15*fib[py, px]
        r = (np.argsort(np.argsort(r)) + 0.5)/len(r)
        t0 = (1 - lowfreq)*r + lowfreq*np.clip(0.5 + 0.25*lf[py, px], 0, 1)
        groups = 10
        q = np.minimum((np.argsort(np.argsort(t0))*groups)//len(t0), groups-1)
        T = np.full(ch, np.inf)
        for k in range(groups):
            sel = q == k
            if not sel.any():
                continue
            c, _ = MCP_Geometric(cost).find_costs(list(zip(py[sel].tolist(), px[sel].tolist())))
            T = np.minimum(T, t0[sel].mean() + c*0.045)
        ok = G & np.isfinite(T) & (T < 1e3)
        def rank(x):
            v = np.full(ch, np.nan, np.float32); o = np.argsort(np.argsort(x[ok])); v[ok] = (o + 0.5)/ok.sum(); return v
        # high-frequency absorbency: paper grain valleys + fibre-aligned streaks + fine pinpoint noise
        pin = ndi.gaussian_filter(rg.standard_normal(ch).astype(np.float32), 0.55); pin /= pin.std() + 1e-6
        hfa = 0.45*fib + 0.35*st + 0.45*pin
        Tm = rank(T); Th = rank(-hfa)
        T = hf_w*Th + (1 - hf_w - lowfreq*0.5)*Tm + lowfreq*0.5*np.clip(0.5 - 0.25*lf, 0, 1)
        T = np.where(ok, T, np.nan)
        # ---- per-glyph stagger: each glyph runs its own compressed seep; starts ordered by x along an eased sweep
        gd = glyph_dur; self.r1 = arrival_frames/fps; self.r2 = deepen_time; span = gd - self.r2 - 0.03 - 0.01
        self.tint = tint
        lab, nl = ndi.label(ndi.binary_dilation(G, iterations=glyph_merge) if glyph_merge > 0 else G)
        lab = np.where(ok, lab, 0)
        idx = np.arange(1, nl + 1)
        cy, cx = [np.array(v) for v in zip(*ndi.center_of_mass(ok, lab, idx))] if nl else ([], [])
        valid = np.isfinite(cx)
        xn = np.zeros(nl); xn[valid] = (cx[valid] - np.nanmin(cx))/max(np.nanmax(cx) - np.nanmin(cx), 1)
        sub = (cy + y0) > split_y
        if order == 'reading' and line_info:
            # reading order: position along the concatenated lines (line widths), eased as one sweep
            ly = np.array([l[0] for l in line_info]); lx0 = np.array([l[1] for l in line_info]); lw = np.array([l[2] - l[1] for l in line_info])
            cum = np.concatenate([[0], np.cumsum(lw)])
            li = np.argmin(np.abs((cy[:, None] + y0) - ly[None, :]), axis=1) if nl else np.zeros(0, int)
            pos = (cum[li] + np.clip(cx + x0 - lx0[li], 0, lw[li]))/max(cum[-1], 1)
            pv = pos[valid]; xn = np.where(valid, (pos - pv.min())/max(pv.max() - pv.min(), 1e-6), 0)
            st = stagger_inverse(xn, stagger_ease)*sweep_starts
        else:
            st = stagger_inverse(xn, stagger_ease)*sweep_starts + np.where(sub, sub_delay, 0.0)
        # ---- medial axis: normalised distance from each stroke's centreline (0 = axis, 1 = outline)
        from skimage.morphology import medial_axis
        coreS = (ndi.gaussian_filter(core.astype(np.float32), 1.0) > 0.45) | ndi.binary_erosion(core)
        skel, mdist = medial_axis(coreS, return_distance=True, rng=0)   # seeded tie-break: reproducible
        locmax = ndi.maximum_filter(np.where(skel, mdist, 0), size=7)
        skel &= mdist >= 0.55*locmax                                  # prune spurs from the ragged outline
        cl, ncl = ndi.label(coreS)
        has = set(np.unique(cl[skel]).tolist())
        for k in range(1, ncl + 1):                                    # dots / tiny pieces: keep a centre point
            if k not in has:
                m_ = cl == k; e = np.where(m_, mdist, -1); skel[np.unravel_index(np.argmax(e), ch)] = True
        dsk, (sy, sx) = ndi.distance_transform_edt(~skel, return_indices=True)
        Rw = np.maximum(mdist[sy, sx], 0.7)                            # local half-width at nearest axis point
        din = ndi.distance_transform_edt(core)
        dn = np.clip(0.5*dsk/Rw + 0.5*(1 - din/Rw), 0, 1)
        dcore = ndi.distance_transform_edt(~core)
        dn = np.where(core, dn, 1.25 + 0.6*np.clip(dcore/6.0, 0, 1))  # feather strands wick out last
        self.skel = skel; self.dn = dn
        Tl = np.full(ch, np.nan, np.float32)
        sxf = sx.astype(np.float32)
        objs = ndi.find_objects(lab, nl)
        self.gbox = {}
        for k in range(1, nl + 1):
            if objs[k-1] is None:
                continue
            sl = objs[k-1]; mk = lab[sl] == k
            tv = T[sl][mk]; xv = sxf[sl][mk]
            g = (np.argsort(np.argsort(tv)) + 0.5)/len(tv)                  # paper grain / fibre order
            xr = (xv - xv.min())/max(xv.max() - xv.min(), 1)               # along-axis, left-to-right lean
            v = axis_w*dn[sl][mk] + grain_w*g + along_w*xr
            v = (np.argsort(np.argsort(v)) + 0.5)/len(v)
            blk = Tl[sl]; blk[mk] = st[k-1] + v*span; Tl[sl] = blk
            self.gbox[k-1] = (sl[0].start + y0, sl[0].stop + y0, sl[1].start + x0, sl[1].stop + x0)
        ok = np.isfinite(Tl)
        _, (iy, ix) = ndi.distance_transform_edt(~ok, return_indices=True)
        self.T = np.where(ok, Tl, 0)[iy, ix].astype(np.float32)
        self.t_end = float(np.nanmax(Tl)) + 0.03 + self.r2 + 0.01
        self.starts = np.sort(st); self.nglyph = nl
        self.gl = [(float(st[k]), float(cx[k] + x0), float(cy[k] + y0), bool(sub[k]), self.gbox.get(k)) for k in range(nl) if valid[k]]
        self.gd = gd
        self.fibs = ndi.gaussian_filter(self.fib, 0.8); self.fibs /= self.fibs.std() + 1e-6
        gn = ndi.gaussian_filter(rg.standard_normal(ch).astype(np.float32), 0.6); gn /= gn.std() + 1e-6
        self.d0 = np.clip(init_density + density_spread*np.tanh(0.9*self.fibs) + 0.05*gn, 0.2, 0.9).astype(np.float32)
        self.d0min = float(self.d0.min())

    def frame(self, p, ink):
        self.inkc = ai._hex(ink)
        """p = time in seconds since the seep phase started"""
        y0, y1, x0, x1 = self.box
        A0 = self.A0[y0:y1, x0:x1]; T = self.T
        tau = float(p)                                               # seconds since the seep started
        # COVERAGE: near-binary arrival (paper -> ink within ~1-2 frames); no soft spatial ramp, no blur
        C = np.clip((tau - T)/self.r1, 0, 1)
        # DENSITY of already-arrived ink: texture-driven start (valleys darker, ridges lighter, fine grain),
        # ease-out deepening to full over r2 seconds per pixel
        Dd = np.clip((tau - T)/self.r2, 0, 1); Dd = 1 - (1 - Dd)**3
        dens = self.d0 + (1 - self.d0)*Dd
        a = np.clip(A0*C*dens, 0, 1)
        t_ = (self.tint*(1 - dens)/(1 - self.d0min + 1e-6))[..., None]
        rgb = self.inkc*(1 - t_) + SEPIA*t_
        self.last_C = C; self.last_dens = dens
        Af = np.zeros(self.A0.shape, np.float32); R = np.zeros(self.A0.shape + (3,), np.float32)
        Af[y0:y1, x0:x1] = a; R[y0:y1, x0:x1] = rgb
        return Af, R


def comp(P, A, rgb, halo_amt=0.0, u_halo=1.0, grain=1.0):
    A2, Pm2 = ai.show_through(A, rgb*A[..., None], P, 1.0, grain)
    Q = P
    if halo_amt > 0:
        hl = ai.bleed_halo(np.clip(A2, 0, 1), u_halo)*halo_amt
        Q = P*(1 - hl[..., None]*(1 - ai.HALO_RGB/255.0))
    return np.clip(Q*(1 - A2[..., None]) + Pm2, 0, 255).astype(np.uint8)


def report_seep(lastseep, crisp, covstats, dstats, a):
    cs_ = np.array(covstats)
    print('COVERAGE: intermediate (0.1-0.8) per seep frame mean %.4f max %.4f of glyph px; largest contiguous mid-coverage blob %d px'
          % (cs_[:, 1].mean(), cs_[:, 1].max(), cs_[:, 3].max()))
    act = cs_[:, 2] > 0.02
    print('DENSITY of arrived ink: mean per frame %.2f..%.2f; share still deepening (<0.95) up to %.2f'
          % (cs_[act, 4].min(), cs_[act, 4].max(), cs_[act, 5].max()))
    for row in cs_[::8]:
        print('  t=%.3fs  mid-coverage %.4f  arrived %.3f  max blob %4d  mean density %.2f  deepening %.2f' % tuple(row))
    if a.stills:
        np.savetxt(os.path.join(a.stills, 'seep_coverage_stats.csv'), cs_, delimiter=',', fmt='%.5f',
                   header='t_s,frac_glyph_px_coverage_0.1_0.8,frac_arrived,largest_mid_coverage_component_px,mean_density_arrived,frac_arrived_deepening')
    print('last seep frame vs crisp: max diff %d' % np.abs(lastseep.astype(int) - crisp.astype(int)).max())
    if dstats:
        ds = np.array(dstats)
        print('seep per-frame alpha: max rise %.3f, max drop %.4f; mean |dA| in glyphs min %.4f max %.4f (ratio %.2f)'
              % (ds[:, 1].max(), ds[:, 2].max(), ds[:, 3].min(), ds[:, 3].max(), ds[:, 3].max()/max(ds[:, 3][ds[:, 3] > 0].min(), 1e-6)))
        np.savetxt(os.path.join(a.stills or '.', 'seep_frame_stats.csv'), ds, delimiter=',', header='p,max_rise,max_drop,mean_abs_dA_in_glyph', fmt='%.5f')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--title', default='The Quiet Archive')
    ap.add_argument('--subtitle', default='records kept in ink, and in the patience of paper')
    ap.add_argument('--title-font', default=os.path.join(HERE, 'fonts', 'IMFeENrm28P.ttf'))
    ap.add_argument('--sub-font', default=os.path.join(HERE, 'fonts', 'IMFeENit28P.ttf'))
    ap.add_argument('--title-size', type=float, default=190, help='font size in output px')
    ap.add_argument('--sub-size', type=float, default=62)
    ap.add_argument('--title-y', type=float, default=0.43, help='title (block) centre, fraction of height')
    ap.add_argument('--sub-y', type=float, default=None, help='subtitle y (default 0.60, or below a multi-line title)')
    ap.add_argument('--wrap', default='auto', choices=['auto', 'none'], help="balanced wrap of long titles ('|' forces breaks)")
    ap.add_argument('--max-width', type=float, default=0.78, help='max line width, fraction of frame width')
    ap.add_argument('--line-spacing', type=float, default=1.42, help='title line pitch, x font size')
    ap.add_argument('--axis-crops', default=None, help="stills: 'name:x,y;...' centres for zoom_axis_4x (default: auto T/Q)")
    ap.add_argument('--glyph-merge', type=int, default=1, help='px dilation when grouping ink into glyphs (0 for small type)')
    ap.add_argument('--stagger-order', default='x', choices=['x', 'reading'],
                    help="x: all lines sweep together by x (subtitle +sub-delay); reading: line by line in reading order")
    ap.add_argument('--width', type=int, default=1920); ap.add_argument('--height', type=int, default=1080)
    ap.add_argument('--fps', type=int, default=60)
    ap.add_argument('--phases', default='both', choices=['seep', 'age', 'both'],
                    help="seep = empty -> seep -> hold on the fresh print; age = fresh print -> ageing -> hold on aged; both")
    ap.add_argument('--durations', default=None,
                    help='seconds. both: empty,seep,fresh-hold,ageing,aged-hold (default 0.15,1.3,0.2,0.4,0.95 = 3.0 s); '
                         'seep: empty,seep,hold (0.15,1.3,0.8); age: fresh-hold,ageing,hold (0.4,0.5,1.0); 5 values always accepted')
    ap.add_argument('--from-image', default=None, help="(phases=age only) age the ink of an existing still, e.g. a fresh print PNG")
    ap.add_argument('--paper', default=os.path.join(HERE, 'papers', 'user_paper_01.jpg'))
    ap.add_argument('--paper-scale', type=float, default=1.6); ap.add_argument('--tone', default='vintage')
    ap.add_argument('--strength', type=float, default=1.0); ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--rub', type=int, default=3)
    ap.add_argument('--ink', default='#1d1d1f', help='base ink colour (seep wash -> crisp -> aged all derive from it)')
    ap.add_argument('--feather-reach', type=float, default=6.0, help='max fibre strand length (output px)')
    ap.add_argument('--feather-density', type=float, default=1.0, help='share of fibre channels carrying strands (0 = none)')
    ap.add_argument('--rag', type=float, default=1.0, help='fibre-aligned edge raggedness (0 = smooth edge)')
    ap.add_argument('--strand-width', type=float, default=1.0)
    ap.add_argument('--ink-grain', type=float, default=1.3, help='paper-grain lift inside strokes (1 = composite default)')
    ap.add_argument('--grain-spacing', type=float, default=4.5, help='seep pinpoint spacing (output px)')
    ap.add_argument('--grain-lowfreq', type=float, default=0.25, help='weight of the large-scale term in seep timing')
    ap.add_argument('--glyph-dur', type=float, default=0.6, help='per-glyph local seep duration (s)')
    ap.add_argument('--sweep', type=float, default=0.65, help='time from first to last glyph start (s)')
    ap.add_argument('--stagger-ease', default='inOutCubic', choices=list(EASES), help='easing of the left-to-right sweep front')
    ap.add_argument('--sub-delay', type=float, default=0.05, help='subtitle start delay (s)')
    ap.add_argument('--lr-bias', type=float, default=0.25, help='left-to-right bias inside each glyph (0..1)')
    ap.add_argument('--axis-weight', type=float, default=1.0, help='weight of centreline->outline distance in arrival')
    ap.add_argument('--axis-grain', type=float, default=0.5, help='weight of paper grain/fibre order in arrival')
    ap.add_argument('--axis-along', type=float, default=0.12, help='along-axis (left-to-right) drawing component')
    ap.add_argument('--glyph-ramp', type=float, default=0.18, help='(superseded by --arrival-frames)')
    ap.add_argument('--arrival-frames', type=float, default=1.5, help='per-pixel paper->ink switch time in frames (near-binary)')
    ap.add_argument('--init-density', type=float, default=0.5, help='density of freshly arrived ink (mean)')
    ap.add_argument('--density-spread', type=float, default=0.15, help='+- density by fibre: valleys darker, ridges lighter')
    ap.add_argument('--deepen-time', type=float, default=0.28, help='per-pixel ease-out deepening to full density (s)')
    ap.add_argument('--tint', type=float, default=0.12, help='faint sepia tint of the lightest fresh ink (0 = none)')
    ap.add_argument('--ridge-light', type=float, default=0.2, help='how much lighter raised fibre ridges are just after arrival')
    ap.add_argument('--glyph-deepen', type=float, default=0.12, help='ridge-only deepening time as fraction of glyph-dur')
    ap.add_argument('--grain-hf', type=float, default=0.55, help='weight of fine grain/fibre absorbency in seep timing')
    ap.add_argument('--fibre-bias', type=float, default=0.6, help='how strongly fibre channels speed up wicking')
    ap.add_argument('--ramp', type=float, default=0.22, help='per-pixel arrival ramp (s)')
    ap.add_argument('--deepen', type=float, default=0.65, help='per-pixel density-deepening ramp (s)')
    ap.add_argument('--halo', type=float, default=0.0, help='bleed-halo amount in the ageing (0 = off: no grey rim)')
    ap.add_argument('--out', default='out/ink_seep.mp4')
    ap.add_argument('--stills', default=None, help='directory for stills + contact sheet + zoom')
    ap.add_argument('--crf', type=int, default=16)
    a = ap.parse_args()
    t_start = time.time()
    if a.stills:
        os.makedirs(a.stills, exist_ok=True)
    W, H, S = a.width, a.height, 2
    DEF = {'both': '0.15,1.3,0.2,0.4,0.95', 'seep': '0.15,1.3,0.8', 'age': '0.4,0.5,1.0'}
    dv = [float(x) for x in (a.durations or DEF[a.phases]).split(',')]
    if len(dv) == 5:
        d_empty, d_seep, d_crisp, d_age, d_hold = dv
    elif len(dv) == 3 and a.phases == 'seep':
        d_empty, d_seep, d_crisp, d_age, d_hold = dv[0], dv[1], dv[2], 0.0, 0.0
    elif len(dv) == 3 and a.phases == 'age':
        d_empty, d_seep, d_crisp, d_age, d_hold = 0.0, 0.0, dv[0], dv[1], dv[2]
    else:
        sys.exit('--durations: give 5 values, or 3 for --phases seep/age')
    if a.phases == 'seep':
        d_age = d_hold = 0.0
    if a.phases == 'age':
        d_empty = d_seep = 0.0
    if a.from_image and a.phases != 'age':
        sys.exit('--from-image works with --phases age (the seep needs vector text)')

    P8 = ai.load_paper(a.paper, W, H, mode='cover', scale=a.paper_scale, tone=a.tone, seed=a.seed)
    P = P8.astype(np.float32)
    lines = ai.layout_text(W, H, a.title, a.subtitle, a.title_font, a.sub_font, a.title_size, a.sub_size,
                           a.title_y, a.sub_y, a.wrap, a.max_width, a.line_spacing)
    for ln in lines:
        print('line %-5s y=%.3f size=%g: %s' % (ln[4], ln[3], ln[2], ln[0]))
    sub_y_eff = next((ln[3] for ln in lines if ln[4] == 'sub'), 0.60)
    last_title_y = [ln[3] for ln in lines if ln[4] == 'title'][-1]
    if a.from_image:
        masks, units, prep, P8, P, spec, fibf = None, None, None, None, None, None, None
        import age_image as AI
        img = np.asarray(Image.open(a.from_image).convert('RGB'), np.float32)
        ex = AI.extract_layers(img, None, a.seed)
        if ex is None:
            sys.exit('no clean ink found in %s' % a.from_image)
        P = ex['background'].astype(np.float32); P8 = np.clip(P, 0, 255).astype(np.uint8); H, W = P8.shape[:2]
        S = ex['S']
        prep = ai.prepare_print(ex['layers'], a.strength, a.seed, S, ex['unit'], feather=None, ink=None)
        layer_list = ex['layers']
        print('from-image: %d ink layers (its own ink colours/edges kept), ageing only' % len(prep))
    else:
        tm = ai.text_masks(W, H, lines, S)
        masks = [(m, cap) for m, cap, _ in tm]; units = [u for _, _, u in tm]
        fibf = ai.fibre_field(P)
        spec = ai.feather_spec(P, S, a.feather_reach, a.feather_density, a.rag, a.strand_width, fibre=fibf)
        layer_list = [(m, 'text', {'unit': u}) for (m, _), u in zip(masks, units)]
        prep = ai.prepare_print(layer_list, a.strength, a.seed, S, feather=spec, ink=a.ink)
        print('units', [round(x, 2) for x in units])

    def age_frame(q):
        """print at ageing progress q (0 = fresh print, 1 = aged == aged_ink.composite())"""
        return ai.render_print(P, prep, q, S, a.strength, a.seed, rub=a.rub, halo=a.halo,
                               paper_grain=1.0 if a.from_image else a.ink_grain)

    seep = None; A0 = None
    line_info = []
    if masks:
        for m, _ in masks:
            md = ai._down(m, S); ys_, xs_ = np.nonzero(md > 0.5)
            if len(ys_):
                line_info.append((float(ys_.mean()), float(xs_.min()), float(xs_.max())))
    if d_seep > 0:
        A0 = np.clip(sum(x[0] for x in ai.print_layers(prep, 0.0, S)), 0, 1)
        seep = Seep(A0, fibf, P, a.seed, d_seep, ramp_s=a.ramp, deepen_s=a.deepen, spacing=a.grain_spacing,
                    lowfreq=a.grain_lowfreq, fibre_bias=a.fibre_bias, hf_w=a.grain_hf,
                    glyph_dur=a.glyph_dur, sweep_starts=a.sweep, stagger_ease=a.stagger_ease, sub_delay=a.sub_delay,
                    lr_bias=a.lr_bias, split_y=0.5*(last_title_y + sub_y_eff)*H, axis_w=a.axis_weight,
                    order=a.stagger_order, line_info=line_info, glyph_merge=a.glyph_merge,
                    grain_w=a.axis_grain, along_w=a.axis_along, glyph_ramp=a.glyph_ramp, glyph_deepen=a.glyph_deepen,
                    arrival_frames=a.arrival_frames, fps=a.fps, ridge_light=a.ridge_light,
                    init_density=a.init_density, density_spread=a.density_spread, deepen_time=a.deepen_time, tint=a.tint)
        print('glyphs %d, starts %.3f..%.3f s, seep fully inked at %.3f s (phase %.2f s)'
              % (seep.nglyph, seep.starts[0], seep.starts[-1], seep.t_end, d_seep))
    fps = a.fps
    cum = np.round(np.cumsum([0, d_empty, d_seep, d_crisp, d_age, d_hold])*fps + 1e-9).astype(int)
    n = [int(x) for x in np.diff(cum)]                    # cumulative rounding: total frames exact at any fps
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
                           '-r', str(fps), '-i', '-', '-c:v', 'libx264', '-preset', 'slow', '-crf', str(a.crf),
                           '-pix_fmt', 'yuv420p', '-movflags', '+faststart', a.out], stdin=subprocess.PIPE)
    stills = {}
    want = {k: (1, v) for k, v in [('seep20', .2), ('seep30', .3), ('seep40', .4), ('seep50', .5), ('seep60', .6),
                                    ('seep70', .7), ('seep80', .8), ('seep90', .9)]}
    tkeys = []
    for j in range(1, int(d_seep/0.15) + 1):
        k = 't%.2fs' % (j*0.15); tkeys.append(k); want[k] = (1, j*0.15/d_seep - 1e-6)
    prevA = None; dstats = []; covstats = []; gmask = A0 > 0.5 if A0 is not None else None
    def put(img): ff.stdin.write(img.tobytes())
    for _ in range(n[0]):
        put(P8)
    for i in range(n[1]):
        p = (i + 1)/n[1]
        A, rgb = seep.frame((i + 1)/fps, a.ink)
        by0, by1, bx0, bx1 = seep.box; gm = gmask[by0:by1, bx0:bx1]
        cov = seep.last_C[gm]; midm = (cov > 0.1) & (cov < 0.8)
        mm = np.zeros(gm.shape, bool); mm[gm] = midm
        lb, nlb = ndi.label(mm); big = int(np.bincount(lb.ravel())[1:].max()) if nlb else 0
        arr = cov >= 0.999; dv = seep.last_dens[gm][arr]
        covstats.append(((i + 1)/fps, float(midm.mean()), float(arr.mean()), big,
                         float(dv.mean()) if dv.size else 0.0, float((dv < 0.95).mean()) if dv.size else 0.0))
        img = comp(P, A, rgb, grain=a.ink_grain)
        put(img)
        if prevA is not None:
            dA = A - prevA
            dstats.append((p, float(dA.max()), float(-dA.min()), float(np.abs(dA)[A0 > 0.5].mean())))
        prevA = A
        for k, (ph, frac) in want.items():
            if k not in stills and p >= frac:
                stills[k] = img
    crisp = age_frame(0.0)
    stills['crisp'] = crisp
    if n[1] > 0:
        report_seep(img, crisp, covstats, dstats, a)
    for _ in range(n[2]):
        put(crisp)
    for i in range(n[3]):
        x = (i + 1)/n[3]
        q = float(smooth(0, 1, x)) if i < n[3]-1 else 1.0
        img = age_frame(q)
        if 'mid_ageing' not in stills and x >= 0.5:
            stills['mid_ageing'] = img
        put(img)
    final = age_frame(1.0) if n[3] > 0 else crisp
    if n[3] > 0:
        stills['final'] = final
    for _ in range(n[4]):
        put(final)
    ff.stdin.close(); ff.wait()
    total = sum(n)/fps
    print(f'wrote {a.out}: {sum(n)} frames @ {fps} fps = {total:.2f} s  (render {time.time()-t_start:.0f} s)')

    # consistency checks against the still APIs
    if not a.from_image:
        if n[3] > 0:
            ref = ai.composite(P8, [(m, 'text', {'unit': u, 'feather': spec}) for (m, _), u in zip(masks, units)],
                               strength=a.strength, seed=a.seed, supersample=S, rub=a.rub, halo=a.halo > 0, ink=a.ink,
                               paper_grain=a.ink_grain)
            print('final vs composite(): mean abs diff %.3f, max %d' % (np.abs(ref.astype(int) - final.astype(int)).mean(),
                                                                       np.abs(ref.astype(int) - final.astype(int)).max()))
        fr = ai.fresh_print(P8, [(m, 'text', {'unit': u}) for (m, _), u in zip(masks, units)], ink=a.ink,
                            feather_reach=a.feather_reach, feather_density=a.feather_density, rag=a.rag,
                            strand_width=a.strand_width, ink_grain=a.ink_grain, seed=a.seed, supersample=S, strength=a.strength)
        print('fresh frame vs fresh_print(): max diff %d' % np.abs(fr.astype(int) - crisp.astype(int)).max())
    if a.stills and n[1] == 0:
        os.makedirs(a.stills, exist_ok=True)
        ks = ['crisp'] + [k for k in ('mid_ageing', 'final') if k in stills]
        tw, th = W//3, H//3
        sheet = Image.new('RGB', (tw*len(ks) + 10*(len(ks)+1), th + 54), (30, 30, 30)); dd = ImageDraw.Draw(sheet)
        lab = ImageFont.truetype(os.path.join(HERE, 'fonts', 'IMFeENrm28P.ttf'), 26)
        for j, k in enumerate(ks):
            Image.fromarray(stills[k]).save(os.path.join(a.stills, f'still_{k}.png'))
            sheet.paste(Image.fromarray(stills[k]).resize((tw, th), Image.LANCZOS), (10 + j*(tw + 10), 44))
            dd.text((10 + j*(tw + 10), 8), {'crisp': 'fresh print', 'mid_ageing': 'mid-ageing', 'final': 'aged'}[k], font=lab, fill=(235, 230, 215))
        sheet.save(os.path.join(a.stills, 'contact.png'))
        return
    if a.stills:
        os.makedirs(a.stills, exist_ok=True)
        order = tkeys + [k for k in ('crisp', 'mid_ageing', 'final') if k in stills]
        for k in list(stills):
            Image.fromarray(stills[k]).save(os.path.join(a.stills, f'still_{k}.png'))
        nc = 4; nr = (len(order) + 1 + nc - 1)//nc
        tw, th = W//4, H//4
        sheet = Image.new('RGB', (tw*nc + 10*(nc+1), (th + 44)*nr + 20), (30, 30, 30)); dd = ImageDraw.Draw(sheet)
        lab = ImageFont.truetype(os.path.join(HERE, 'fonts', 'IMFeENrm28P.ttf'), 26)
        t0s = d_empty
        names = {'seep20': 'seep 20%', 'seep40': 'seep 40%', 'seep60': 'seep 60%', 'seep80': 'seep 80%',
                 'crisp': 'crisp (%.2f s)' % (d_empty + d_seep), 'mid_ageing': 'mid-ageing',
                 'final': 'final aged (%.2f-%.2f s)' % (d_empty + d_seep + d_crisp + d_age, d_empty + d_seep + d_crisp + d_age + d_hold)}
        for k in tkeys:
            names[k] = 'video %.2f s (seep +%s)' % (d_empty + float(k[1:-1]), k[1:])
        for j, k in enumerate(order + ['paper']):
            x, y = 10 + (j % nc)*(tw + 10), 10 + (j//nc)*(th + 44)
            im = P8 if k == 'paper' else stills[k]
            sheet.paste(Image.fromarray(im).resize((tw, th), Image.LANCZOS), (x, y + 34))
            dd.text((x, y + 2), names.get(k, 'empty paper (0-%.2f s)' % d_empty), font=lab, fill=(235, 230, 215))
        sheet.save(os.path.join(a.stills, 'contact.png'))
        # 4x axis crops: horizontal stroke (T crossbar), vertical stem (T stem), curve (Q bowl) through local seep
        tl, ntl = ndi.label((A0 > 0.5) & (np.arange(H)[:, None] < 0.5*(last_title_y + sub_y_eff)*H))
        ob = [o for o in ndi.find_objects(tl) if o is not None and (o[0].stop - o[0].start) > 40]
        ob.sort(key=lambda o: o[1].start)
        oT = ob[0]; oQ = max(ob[:5], key=lambda o: o[0].stop - o[0].start)
        ty0, ty1, tx0, tx1 = oT[0].start, oT[0].stop, oT[1].start, oT[1].stop
        qy0, qy1, qx0, qx1 = oQ[0].start, oQ[0].stop, oQ[1].start, oQ[1].stop
        y0_, y1_, x0_, x1_ = seep.box
        Tfull = np.full((H, W), np.inf, np.float32); Tfull[y0_:y1_, x0_:x1_] = seep.T
        gstart = lambda o: float(Tfull[o][(A0[o] > 0.5)].min())
        cwz, chz = 100, 64
        regions = [('T crossbar (horizontal)', (gstart(oT),), tx0 + 4, ty0 - 4),
                   ('T stem (vertical)', (gstart(oT),), (tx0 + tx1)//2 - 50, ty0 + 62),
                   ('Q bowl (curve)', (gstart(oQ),), qx0 - 6, qy0 + 36)]
        if a.axis_crops:                      # 'name:x,y;...' crop centres in output px; glyph = ink nearest the point
            labA, _ = ndi.label(A0 > 0.5)
            regions = []
            for item in a.axis_crops.split(';'):
                nm, xy = item.rsplit(':', 1); px_, py_ = [int(v) for v in xy.split(',')]
                dd_, (iy_, ix_) = ndi.distance_transform_edt(labA[py_-40:py_+40, px_-60:px_+60] == 0, return_indices=True)
                k_ = labA[py_-40:py_+40, px_-60:px_+60][iy_[40, 60], ix_[40, 60]]
                regions.append((nm, (gstart(labA == k_),), px_ - 50, py_ - 32))
        fr_ = [0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 0.9, 1.0]
        za = Image.new('RGB', (len(fr_)*(cwz*4 + 8) + 8 + 260, len(regions)*(chz*4 + 8) + 44), (30, 30, 30)); dz = ImageDraw.Draw(za)
        for j, f in enumerate(fr_):
            dz.text((268 + j*(cwz*4 + 8), 6), 'glyph seep %d%%' % round(f*100), font=lab, fill=(235, 230, 215))
        for r, (nm, g, rx, ry) in enumerate(regions):
            dz.text((8, 44 + r*(chz*4 + 8) + chz*2 - 14), nm, font=lab, fill=(235, 230, 215))
            for j, f in enumerate(fr_):
                tt = g[0] + f*seep.gd
                A_, rgb_ = seep.frame(tt, a.ink); im_ = comp(P, A_, rgb_, grain=a.ink_grain)
                c = Image.fromarray(im_).crop((rx, ry, rx + cwz, ry + chz)).resize((cwz*4, chz*4), Image.NEAREST)
                za.paste(c, (268 + j*(cwz*4 + 8), 40 + r*(chz*4 + 8)))
        za.save(os.path.join(a.stills, 'zoom_axis_4x.png'))
        tq = gstart(oQ) + 0.45*seep.gd
        A_, rgb_ = seep.frame(tq, a.ink); im_ = comp(P, A_, rgb_, grain=a.ink_grain)
        Image.fromarray(im_).crop((qx0 - 10, qy0 + 10, qx0 + 130, qy0 + 110)).resize((1120, 800), Image.NEAREST).save(
            os.path.join(a.stills, 'zoom_mid_8x.png'))
        # axis overlay for the same regions (skeleton in red over crisp)
        y0_, y1_, x0_, x1_ = seep.box
        ov = stills['crisp'].copy(); sk = np.zeros((H, W), bool); sk[y0_:y1_, x0_:x1_] = seep.skel
        ov[sk] = (220, 40, 40)
        zo = Image.new('RGB', (len(regions)*(cwz*4 + 8) + 8, chz*4 + 16), (30, 30, 30))
        for r, (nm, g, rx, ry) in enumerate(regions):
            zo.paste(Image.fromarray(ov).crop((rx, ry, rx + cwz, ry + chz)).resize((cwz*4, chz*4), Image.NEAREST), (8 + r*(cwz*4 + 8), 8))
        zo.save(os.path.join(a.stills, 'zoom_axis_skeleton_4x.png'))
        z = Image.fromarray(stills['seep50']).crop((int(W*0.16), int(H*0.30), int(W*0.50), int(H*0.55)))
        z.resize((z.width*2, z.height*2), Image.LANCZOS).save(os.path.join(a.stills, 'zoom_seep50_2x.png'))
        crops = [(int(W*0.235), int(H*0.385), 110, 80), (int(W*0.43), int(H*0.575), 110, 80)]
        ph = [k for k in ['seep20', 'seep40', 'seep60', 'seep80', 'crisp', 'final'] if k in stills]
        cw, chh = 110*4, 80*4
        ez = Image.new('RGB', (len(ph)*(cw + 8) + 8, len(crops)*(chh + 8) + 44), (30, 30, 30)); de = ImageDraw.Draw(ez)
        for j, k in enumerate(ph):
            de.text((8 + j*(cw + 8), 6), names[k], font=lab, fill=(235, 230, 215))
            for r, (cx, cy, w_, h_) in enumerate(crops):
                c = Image.fromarray(stills[k]).crop((cx, cy, cx + w_, cy + h_)).resize((cw, chh), Image.NEAREST)
                ez.paste(c, (8 + j*(cw + 8), 40 + r*(chh + 8)))
        ez.save(os.path.join(a.stills, 'zoom_edges_4x.png'))
        # fibre-orientation overlay next to the strands (4x): paper+field | crisp | crisp+field
        fx, fy, fw, fh = int(W*0.255), int(H*0.40), 90, 64
        tiles = []
        for k, ov in (('paper', True), ('crisp', False), ('crisp', True)):
            src = P8 if k == 'paper' else stills['crisp']
            t = Image.fromarray(src).crop((fx, fy, fx + fw, fy + fh)).resize((fw*4, fh*4), Image.NEAREST).convert('RGB')
            if ov:
                dr = ImageDraw.Draw(t)
                for yy in range(2, fh, 5):
                    for xx in range(2, fw, 5):
                        gy, gx = fy + yy, fx + xx; vy, vx = fibf['dy'][gy, gx], fibf['dx'][gy, gx]
                        cc = float(np.clip(fibf['coh'][gy, gx]*2, 0.2, 1))
                        dr.line([(xx*4 - 8*vx, yy*4 - 8*vy), (xx*4 + 8*vx, yy*4 + 8*vy)],
                                fill=(int(40 + 200*cc), 60, int(200 - 150*cc)), width=2)
            tiles.append(t)
        fz = Image.new('RGB', (3*(fw*4 + 8) + 8, fh*4 + 52), (30, 30, 30)); dz = ImageDraw.Draw(fz)
        for j, (t, nm) in enumerate(zip(tiles, ['paper + fibre direction', 'crisp feathered ink', 'crisp + fibre direction'])):
            fz.paste(t, (8 + j*(fw*4 + 8), 44)); dz.text((8 + j*(fw*4 + 8), 8), nm, font=lab, fill=(235, 230, 215))
        fz.save(os.path.join(a.stills, 'zoom_fibres_4x.png'))
        # strand alignment: orientation of darkened outside-edge components vs paper fibre direction
        Gp = np.clip(sum(ai._down(m, S) for m, _ in masks), 0, 1) > 0.5
        dout = ndi.distance_transform_edt(~Gp)
        Lp = P8.astype(np.float32).mean(2)
        from skimage.morphology import skeletonize
        for k in ph:
            dL = stills[k].astype(np.float32).mean(2) - Lp
            dk = dL < -8
            for lo, hi in ((1.5, 3.0), (3.0, 8.0)):
                band = (dout >= lo) & (dout <= hi)
                fr = dk[band].mean()
                msg = 'band %-7s %.1f-%.0fpx: darkened %.1f%%' % (k, lo, hi, 100*fr)
                if fr > 0:
                    comp_ = dk & band
                    sk = skeletonize(comp_).sum()
                    msg += ', mean width %.2f px (area/skeleton), mean dL of bare band %.2f' % (comp_.sum()/max(sk, 1), dL[band & ~dk].mean())
                print(msg)
        # alignment: for outer strand pixels, compare strand local direction (structure tensor of the dark mask)
        dk = (stills['crisp'].astype(np.float32).mean(2) - Lp < -8) & (dout >= 2.5)
        if dk.sum() > 50:
            f = dk.astype(np.float32)
            gx = ndi.sobel(f, 1); gy = ndi.sobel(f, 0)
            jxx = ndi.gaussian_filter(gx*gx, 1.5); jyy = ndi.gaussian_filter(gy*gy, 1.5); jxy = ndi.gaussian_filter(gx*gy, 1.5)
            ts = 0.5*np.arctan2(2*jxy, jxx - jyy) + np.pi/2
            tf = np.arctan2(fibf['dy'], fibf['dx'])
            dang = np.abs(((ts - tf + np.pi/2) % np.pi) - np.pi/2)[dk]
            print('strand vs fibre direction: median angle diff %.1f deg (random would be 45)' % np.degrees(np.median(dang)))
        core = ndi.distance_transform_edt(A0 > 0.5) >= 3
        cr = stills['crisp'][core].astype(np.float32)
        print('crisp full-coverage ink: median RGB', np.median(cr, 0), ' p5', np.percentile(cr, 5, 0), ' min', cr.min(0))
        print('stills ->', a.stills)


if __name__ == '__main__':
    main()
