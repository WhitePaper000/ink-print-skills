---
name: ink-print
description: >-
  Use when the user wants text or an image to look printed in ink on real
  vintage paper, as a STILL (fresh print or aged print) or as a short VIDEO
  (ink seeping into the paper, the print ageing, or both). Style only, any
  subject. Ask still or video, then which look, before rendering.
---
# Ink print (stills and videos)

A reusable *style*, not a design. It makes text, lines and patterns look printed in ink on real, yellowed paper. Subject, wording, fonts, layout and composition always come from the request; never reuse earlier sample content (such as "The Quiet Archive" or the compass card).

## 1. Ask first
Unless the user already said, ask (one short question with options) which output they want:
- **Still, fresh print:** freshly printed ink that sits in the paper.
- **Still, aged print:** the same print, worn and faded over decades.
- **Video, ink seep-in:** blank paper, then ink seeps in, ending on the fresh print (default 2.25 s).
- **Video, ageing:** fresh print that quickly wears to aged print (default 1.9 s).
- **Video, both:** seep-in, then ageing (default 3.0 s).

Even "animate it" needs the video choice asked. Also confirm the text, unless given, and the length if they care. If they answer vaguely, suggest the option that fits and confirm.

## Tool
Everything is in `aged-ink/` inside this skill folder. Run commands from there. Read its `README.md` for full details.
- Install once: `pip install -r requirements.txt` (numpy, scipy, Pillow, scikit-image) and `ffmpeg` on PATH for videos.
- `aged_ink.py` is the module: `fresh_print()`, `composite()`, `load_paper()`, `text_masks()`.
- `print_still.py` renders title and subtitle text as a still.
- `age_image.py` applies a style to an existing picture.
- `ink_seep_anim.py` renders the videos.
- `fonts/` holds IM Fell English roman, italic and small caps (SIL OFL).
- `papers/` holds real paper photos; `user_paper_01.jpg` is the default.
- `examples/` holds approved references: `fresh_still.png`, `aged_still.png`, `anim_seep.mp4`, `anim_age.mp4`, `anim_both.mp4`.

## Paper (always)
- **Base:** use a real paper photo, never generated paper. When the user supplies a new paper, copy it to `papers/user_paper_NN.ext` and use it; otherwise use the latest in `papers/`. `make_paper()` is only a fallback when none exists (the scripts fall back automatically and warn).
- **Loading:** `load_paper(path, w, h, mode='cover', scale=1.6, tone='vintage')`.
- **Tone:** `'vintage'` (#EAD9AC, default), `'aged'` (#E2CB93, browner edges), `'none'`, `'#RRGGBB'` or a dict. Toning keeps the grain.

## Ink
- Default ink is `#1d1d1f`, never pure black, multiplied into the paper so the grain shows through.
- No bleed halo, grey rim, shadow, outline or translucent grey veil around letters, ever, in stills or video.

## Stills

### Fresh print: what success looks like
- Edges are ragged at a 2–4 px scale and follow the paper's fibre direction, measured from the paper image itself.
- Thin ink strands wick out 3–8 px along the fibres. They're absent in many places, lighter at the tips, with bare paper between them.
- The paper grain lightens fibre ridges slightly inside strokes. Everything stays crisp and legible.
- Code: `fresh_print(paper, layers=[(mask, 'text'|'line'|'pattern', opts)], ink='#1d1d1f', seed=..., supersample=2)`. Knobs: `feather_reach`, `feather_density`, `rag`, `strand_width`, `ink_grain`. Lines and patterns get strands but keep their own edge.
- Command: `python3 print_still.py --style fresh --title "…" --subtitle "…" -o out.png`.

### Aged print: what success looks like
- **Text:** inking varies letter to letter, some near-full and some washed to brown-grey; faded patches can span several letters. Edges are nibbled, thin strokes and serifs break, small paper-coloured pits show inside strokes. Every word stays legible.
- **Lines:** uneven ink, thinned stretches, short skipped-ink gaps, rough edges.
- **Patterns and fills:** hatching fades in patches; solids are mottled and pitted. `toner_grain` adds optional speckle.
- **Overall:** two or three grainy rubbed patches lighten everything by 30–50%; paper grain shows through the ink.
- **Strength:** 1.0 is the approved look (about 35% of text ink and 20–25% of lines and patterns worn). Use 0.5 for subtle.
- Code: `composite(paper, layers, strength=1.0, seed=..., supersample=2, avoid_boxes=[key words], feather=True, ink='#1d1d1f')`. Aged is the fresh print plus wear on the same feathered edges.
- Command: `python3 print_still.py --style aged -o out.png`. `--aged-classic` gives the older look (#111 ink, clean edges, halo).

### Images you generate (primary path)
1. Design the picture as requested, in Python with PIL or numpy, at 2x supersample.
2. Draw each ink category as its own mask: text, lines, patterns. Small type goes on its own text layer with a smaller `unit` (e.g. 0.5). Use `text_masks()` for text lines.
3. Load the paper. Lay non-ink colour areas on it by multiply. Coloured ink goes in its own layer with `opts={'color': ...}`.
4. Render with `fresh_print` or `composite` per the chosen style, with a fixed seed.

### Existing pictures (secondary path)
`python3 age_image.py in.png out.png --style fresh|aged --paper papers/<paper> --paper-tone vintage --paper-scale 1.4 [--paper-replace] [--debug]`
- Extracts dark ink from a lighter ground, sorts it into text, lines and fills, and treats each.
- `--paper-replace` puts the picture on the user's paper; grey and colour fills are kept as a tint printed onto it. Use `--paper-tone none` to keep a supplied paper's own colour.
- Best on high-contrast line art, typography, logos and scans. Photos get a lighter overall effect; tell the user.
- For aged, 0.6–0.7 here is roughly equal to 1.0 on the primary path.

## Videos
```
python3 ink_seep_anim.py --phases seep|age|both --title "…" [--subtitle "…"] --out out.mp4 \
  [--stills dir/] [--fps 60] [--durations …] [--paper papers/<paper> --paper-scale 1.6 --tone vintage] \
  [--ink '#1d1d1f'] [--seed 7] [--strength 1.0]
```
- **Durations:** 3 values for seep or age, 5 for both (empty, seep, fresh hold, ageing, aged hold). Frame counts are exact at any fps.
- **Ageing an existing image:** `--phases age --from-image img.png`. The seep needs vector text, so it can't start from a picture.
- The first and last frames match the fresh and aged stills above exactly.

### Seep-in: what success looks like
- **Order:** letters appear left to right on an eased curve (inOutCubic, `--stagger-ease`). Neighbouring letters overlap so it flows rather than ticks. The subtitle sweeps with the title, slightly delayed.
- **Within each stroke:** ink starts as a thin, grainy thread along the stroke's centre line (curves and serifs included), then widens evenly to both edges. Thick and thin strokes finish together.
- **Fibres:** ink spreads through fibre channels and grain pits first, raised fibres last. Advancing edges look like ink-soaked fibres and specks with bare paper beside them. Feathered strands wick out last.
- **Colour:** fresh ink lands lighter (about 50%, textured: darker in channels, paler on ridges) and deepens to full `#1d1d1f` over about 0.28 s.
- **Never:** a plain opacity fade, wipe or blur, or ink that retracts. Each pixel switches from paper to ink almost instantly; only its darkness animates.
- **Knobs:** `--glyph-dur` 0.6, `--sweep` 0.65, `--axis-weight`, `--axis-grain`, `--axis-along`, `--init-density`, `--density-spread`, `--deepen-time`, `--tint`, `--arrival-frames`, plus the feather options.

### Ageing: what success looks like
- The fresh print wears to the aged print in about 0.4–0.5 s. Fading, broken strokes, pits and rub patches spread progressively from the same fixed noise, so there's no flicker. The final frame matches the aged still exactly.
- Hold on the aged result at least 0.9 s so it can be read.

## Verify before delivering
- **Stills:** check the full image plus a 2x crop of the densest text and of a pattern area.
- **Videos:** render with `--stills`, check the contact sheet plus 4x crops of a horizontal stroke, a vertical stem and a curve partway through the seep. The script's own checks confirm the fresh and aged frames match the stills.
- Always: reads as real ink on real paper, no grey outline or veil, no stray specks on empty paper, no pops, every word readable, no rub patch erasing a key word.
- Adjust `strength` or per-layer options for strength, `tone` or `ink` for colour. If a rub lands on a key word, try another seed.

## Notes
- A supersampled still of about 3200x2200 takes roughly 40–60 s and a few GB of RAM.
- A 1080p60 render of the full video takes a few minutes. Use 30 fps for quick previews.
