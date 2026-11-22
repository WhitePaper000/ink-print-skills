#!/usr/bin/env python3
"""
Print-style STILL renderer (skill A): text on (toned) user paper in one of two styles.

  fresh : just-printed #1d1d1f ink multiplied with the paper; fibre-aligned ragged edges + discrete fibre
          strands wicking out along the paper grain; paper-grain lift inside strokes; no ageing, rub or halo
          (== the crisp frame of ink_seep_anim.py).
  aged  : the worn old-print look (aged_ink.composite). By default on the same feathered edges, so
          aged == fresh + ageing (== the final frame of ink_seep_anim.py). --aged-classic = original composite
          look (#111 ink, clean edges, bleed halo).

  python3 print_still.py --style fresh --title "The Quiet Archive" --subtitle "records kept in ink" -o fresh.png
  python3 print_still.py --style aged  --title "The Quiet Archive" -o aged.png
"""
import argparse, os, sys
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import aged_ink as ai


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--style', default='fresh', choices=['fresh', 'aged'])
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--title', default='The Quiet Archive')
    ap.add_argument('--subtitle', default='records kept in ink, and in the patience of paper', help="'' = none")
    ap.add_argument('--title-font', default=os.path.join(HERE, 'fonts', 'IMFeENrm28P.ttf'))
    ap.add_argument('--sub-font', default=os.path.join(HERE, 'fonts', 'IMFeENit28P.ttf'))
    ap.add_argument('--title-size', type=float, default=190); ap.add_argument('--sub-size', type=float, default=62)
    ap.add_argument('--title-y', type=float, default=0.43); ap.add_argument('--sub-y', type=float, default=None)
    ap.add_argument('--wrap', default='auto', choices=['auto', 'none']); ap.add_argument('--max-width', type=float, default=0.78)
    ap.add_argument('--line-spacing', type=float, default=1.42)
    ap.add_argument('--width', type=int, default=1920); ap.add_argument('--height', type=int, default=1080)
    ap.add_argument('--paper', default=os.path.join(HERE, 'papers', 'user_paper_01.jpg'))
    ap.add_argument('--paper-mode', default='cover', choices=['cover', 'tile', 'stretch'])
    ap.add_argument('--paper-scale', type=float, default=1.6); ap.add_argument('--tone', default='vintage')
    ap.add_argument('--ink', default='#1d1d1f')
    ap.add_argument('--seed', type=int, default=7); ap.add_argument('--strength', type=float, default=1.0)
    ap.add_argument('--feather-reach', type=float, default=6.0); ap.add_argument('--feather-density', type=float, default=1.0)
    ap.add_argument('--rag', type=float, default=1.0); ap.add_argument('--strand-width', type=float, default=1.0)
    ap.add_argument('--ink-grain', type=float, default=1.3)
    ap.add_argument('--rub', type=int, default=3, help='aged: rubbed patches (0 = none)')
    ap.add_argument('--halo', action='store_true', help='aged: add the bleed halo (off by default: no grey rim)')
    ap.add_argument('--aged-classic', action='store_true', help='aged: original composite() look (clean edges, #111, halo)')
    a = ap.parse_args()
    W, H, S = a.width, a.height, 2
    P8 = ai.load_paper(a.paper, W, H, a.paper_mode, a.paper_scale, None, a.seed, tone=a.tone)
    lines = ai.layout_text(W, H, a.title, a.subtitle, a.title_font, a.sub_font, a.title_size, a.sub_size,
                           a.title_y, a.sub_y, a.wrap, a.max_width, a.line_spacing)
    layers = [(m, 'text', {'unit': u}) for m, _, u in ai.text_masks(W, H, lines, S)]
    fe = dict(feather_reach=a.feather_reach, feather_density=a.feather_density, rag=a.rag, strand_width=a.strand_width)
    if a.style == 'fresh':
        out = ai.fresh_print(P8, layers, ink=a.ink, ink_grain=a.ink_grain, seed=a.seed, supersample=S,
                             strength=a.strength, **fe)
    elif a.aged_classic:
        out = ai.composite(P8, layers, strength=a.strength, seed=a.seed, supersample=S, rub=a.rub)
    else:
        out = ai.composite(P8, layers, strength=a.strength, seed=a.seed, supersample=S, rub=a.rub, halo=a.halo,
                           ink=a.ink, paper_grain=a.ink_grain, feather=fe)
    Image.fromarray(out).save(a.out)
    print('wrote', a.out)


if __name__ == '__main__':
    main()
