# aged-ink toolkit (used by the ink-print skill)

## A. Print-style STILLS: `fresh` and `aged`
| style | look | API | CLI |
|---|---|---|---|
| fresh | just-printed #1d1d1f ink multiplied into toned user paper; fibre-aligned ragged edges + fibre strands; paper-grain lift; no ageing, rub or halo | `fresh_print(paper, layers, ink='#1d1d1f', feather_reach=6, feather_density=1, rag=1, strand_width=1, ink_grain=1.3, seed=0, supersample=2, strength=1, unit=None, paper_mode='cover', paper_scale=1, paper_tint=None, paper_tone='none', return_spec=False)` | `print_still.py --style fresh` |
| aged | the worn old-print look; by default on the same feathered edges (aged = fresh + ageing) | `composite(..., style='aged', feather=True or {feather kwargs}, ink='#1d1d1f', paper_grain=1.3, halo=False)`; the classic look is `composite(...)` with its defaults | `print_still.py --style aged` (`--aged-classic` = original composite look) |

```
python3 print_still.py --style fresh --title "The Quiet Archive" --subtitle "records kept in ink" -o fresh.png
python3 print_still.py --style aged  --title "The Quiet Archive" --subtitle "records kept in ink" -o aged.png
```
- Text layers: `text_masks(W, H, [(text, font, size_px, y_frac), ...], S=2)` returns `(mask, cap, unit)` per line.
- Existing pictures: `age_image.py in.png out.png --style fresh|aged [--feathered] [--ink ...]` uses `extract_layers()`.
  - `fresh` re-prints the extracted ink with fresh feathering.
  - `aged` is the original behaviour; add `--feathered` to age on feathered edges.
- Shared pipeline: `prepare_print()` -> `print_layers(prep, q)` / `render_print(paper, prep, q)`. Here q = 0 is the fresh print and q = 1 the aged print; values in between are the ageing animation.

## B. ANIMATIONS: `seep` and `age` (separately or together; ask the user which)
| `--phases` | sequence | default `--durations` |
|---|---|---|
| `seep` | empty paper -> left-to-right centreline ink seep -> hold on the fresh print | `0.15,1.3,0.8` (empty, seep, hold) = 2.25 s |
| `age`  | fresh print -> quick ageing -> hold on aged | `0.4,0.5,1.0` (fresh hold, ageing, hold) = 1.9 s |
| `both` | seep -> fresh hold -> ageing -> aged hold | `0.15,1.3,0.2,0.4,0.95` = 3.0 s |

```
python3 ink_seep_anim.py --phases seep --title "The Quiet Archive" --out seep.mp4
python3 ink_seep_anim.py --phases age  --title "The Quiet Archive" --out age.mp4
python3 ink_seep_anim.py --phases both --title "The Quiet Archive" --out both.mp4
python3 ink_seep_anim.py --phases age --from-image fresh.png --out age_from_still.mp4   # age a supplied still
```
- 5 durations are always accepted. Frame counts use cumulative rounding, so totals are exact at any fps.
- The fresh frame always equals `fresh_print()` and the aged frame equals `composite(feather=...)`; both are checked every run.
- `--from-image` ages any still's extracted ink (its own colours and edges, no feathering added).
- The seep needs vector text, so it is text-only: there is no seep from an image.
- Samples: `examples/fresh_still.png, aged_still.png, anim_seep.mp4, anim_age.mp4, anim_both.mp4`.


### Multi-line text / small type (stills and videos)
- `layout_text(W, H, title, subtitle, title_font, sub_font, title_size, sub_size, title_y, sub_y=None, wrap='auto', max_width=0.78, line_spacing=1.42, sub_gap=1.25)`
  - A long title gets a balanced wrap onto the fewest lines that fit within `max_width`; `|` forces breaks.
  - A multi-line block is centred on `title_y`, and the subtitle is placed below it.
  - A single-line title keeps the classic layout.
  - CLI (`print_still.py`, `ink_seep_anim.py`): `--wrap auto|none --max-width --line-spacing`; `--sub-y` defaults to auto.
- Animation options:
  - `--stagger-order reading`: the sweep runs line by line in reading order, including the attribution.
  - `--glyph-merge 0`: groups glyphs without dilation, for small type where letters touch.
  - `--axis-crops 'name:x,y;...'`: custom 4x axis crop centres.
- Pull-quote example: 2.65 s at 1080p60, cap height 40 px. Feather and axis settings scale automatically with type size (unit).
```
python3 ink_seep_anim.py --phases seep --durations 0.15,1.6,0.9 --sweep 0.95 --stagger-order reading --glyph-merge 0 \
  --title "So we beat on, boats against the current, borne back ceaselessly into the past." \
  --subtitle "— F. Scott Fitzgerald, The Great Gatsby" --title-size 58 --sub-size 35 --title-y 0.45 --out quote_seep.mp4
```

# aged-ink: worn, faded old-print ink

A seeded, mask-based ageing pass that makes ink look like an old letterpress or copperplate print that has been
photocopied: uneven, faded inking, pits, eroded and broken strokes, skipped ink on rules, mottled solids,
rubbed patches, a faint bleed halo and paper grain showing through. It applies a style only, with no layout or
colours of its own. Requires numpy, Pillow and scipy.

```
aged_ink.py        module (primary path: you draw separate ink layers in code)
age_image.py       CLI for an existing picture (secondary path)
example_build.py   minimal primary-path example (vintage seed-packet label)
                   python3 example_build.py [strength] [outname] [paper_path] [paper_scale] [tone]
papers/            user paper textures (user_paper_01.jpg); preferred base layer
fonts/             IM Fell English roman / italic / small caps (OFL, see fonts/OFL.txt)
examples/          example_userpaper.png (+_zoom, user paper, tone vintage, scale 1.6), example_userpaper_aged.png,
                   example_userpaper_s10.png (+_zoom, scale 1.0 for comparison),
                   example.png, example_zoom.png, example_s05.png, example_clean.png (generated paper),
                   input_lineart.png -> aged_lineart.png (+ _classes.png), input_gradient.png -> aged_gradient.png,
                   make_test_inputs.py
```

## Paper: use the user's own paper (preferred)
Put paper scans or photos in `papers/` (for example `papers/user_paper_01.jpg`) and use them as the base layer.
`make_paper()` is only a fallback when no real paper is available.

```python
paper = ai.load_paper('path/to/aged-ink/papers/user_paper_01.jpg', W, H,
                      mode='cover', scale=1.6, tone='vintage', seed=0)
out = ai.composite(paper, layers, strength=1.0, seed=5, supersample=2)
# or let composite load it (size taken from the masks / supersample):
out = ai.composite('papers/user_paper_01.jpg', layers, supersample=2,
                   paper_mode='cover', paper_scale=1.6, paper_tone='vintage')
```
`load_paper(path, w, h, mode='cover', scale=1.0, tint=None, seed=0, offset=None, tone='none') -> uint8 (h,w,3)`
- `mode`:
  - `'cover'` (default) scales the paper to fill the target, then centre-crops it, so nothing is distorted.
  - `'tile'` keeps the texture at its native size (times `scale`) and mirror-tiles it, with an offset taken from `seed`.
  - `'stretch'` resizes the paper exactly to the target, which can distort the grain.
  - All modes use Lanczos resampling, and mirror tiling kicks in automatically whenever the image is smaller than
    the target, so there are no seams.
- `scale`: texture magnification. Above 1 the grain is coarser relative to the canvas; below 1 it is finer (and tiled).
- `tone`:
  - `'none'` (default) keeps the colour untouched.
  - `'vintage'` gives a warm yellow with a mean of about #EAD9AC, subtle low-frequency uneven yellowing, and slightly
    browner edges. It is the demo default.
  - `'aged'` is deeper (about #E2CB93), with clearly darker, brown, irregular edges.
  - `'#RRGGBB'` is a plain grade to that mean colour.
  - A `dict(target=, uneven=, edge=, edge_col=)` gives full control.
  - Every tone is a colour grade, `target * (pixel luminance / mean luminance)`, so the paper's own grain and fibres
    keep their relief. `tone_paper(img, tone, seed)` applies it to any image.
- `tint`: optional extra luminance-preserving tint, as a colour or `(colour, amount)`.
- `offset`: `(x, y)` crop offset; the default is the centre for `cover` and a seeded offset for `tile`.

How ink interacts with real paper:
- `show_through` lifts the ink on raised, lighter fibres and multiplies the ink colour by the paper's local tone, so
  the grain reads through solid ink.
- The bleed halo is blended by multiply, so it tints the paper without covering its texture.

Paper tips:
- Choose `scale` so the grain looks like real stock next to the type. For the 1600×1100 example with a 65 px title
  cap, `scale=1.6` on the 1920×1281 user paper looked right; at 1.0 the felt grain was too fine.
- Check a 2× zoom: fibres should be visible in both the bare paper and through the solids.
- Don't scale past about 2.5× the source resolution, or Lanczos softening starts to look smoothed.
- Ink colours (#111 to #4a423a, and red) read well on both `vintage` and `aged`. For very dark papers, lower `strength`.

## Primary path (best results)
Draw each ink class into its own 0..255 / 0..1 mask, ideally supersampled 2x, then:

```python
import sys; sys.path.insert(0, 'path/to/aged-ink'); import aged_ink as ai
paper = ai.make_paper(W, H, base='#EEE8DA', seed=3)                # or any (H,W,3) image, kept as-is
out = ai.composite(paper,
        [(LINES, 'line'), (HATCH_AND_FILLS, 'pattern'),
         (TITLE, 'text'), (CAPTION, 'text', {'unit': 0.5}),        # small type: its own layer, smaller unit
         (RED_STAMP, 'text', {'color': '#B8402E'})],
        strength=1.0, seed=5, supersample=2, rub=3,
        avoid_boxes=[(x0, y0, x1, y1)])                             # output px; no rub over key words
```
Run `python3 example_build.py [strength] [outname]` to see it end to end.

## API
`age_layer(ink_mask, kind='text'|'line'|'pattern', strength=1.0, seed=0, glyph_boxes=None, unit=1.0, **override) -> (alpha, rgb, info)`
- Returns `alpha` (H,W) 0..1, `rgb` (H,W,3) ink colour per pixel (#111 heavy, through #2a2420, to #4a423a faded), and
  `info = {'fade': map, 'degraded': fraction of ink visibly degraded}`.
- **text**: per-glyph inking from `glyph_boxes` (one box per glyph, mask px) or from connected components; lighter
  pressing on one side for about 45% of glyphs; faded patches spanning several letters; edges eroded with
  multi-scale threshold noise; breaks in hairlines and serifs; paper pits; occasional squash or bleed. A per-glyph
  fade cap (`cap=0.55`) and a pit floor keep text legible.
- **line**: ragged toner edges, uneven inking, thinned grey stretches, skipped-ink gaps, nibbled edges.
- **pattern**: like line, plus mottled pits in solids. Use `solid_pits=0.3` and `rough=False` for big solid blocks
  with knocked-out lettering.
- Overrides (per-kind defaults are in `KIND_PARAMS`):
  - `s`: base strength.
  - `bias`: a higher value means fewer faded areas.
  - `cap`: maximum fade.
  - `erode`: threshold-erode edges (text) or nibble them (lines).
  - `solid_pits`: mottling of solid fills.
  - `pit_floor`: limits the pit rate.
  - `rough`: toner re-threshold.
  - `jitter`: positional wobble in px.

`composite(paper_rgb, layers, strength=1.0, seed=0, supersample=1, unit=None, rub=3, avoid_boxes=None, halo=True, text_rub=0.45, paper_show=True, return_info=False)`
- `layers`: a list of `(mask, kind)` or `(mask, kind, opts)`, with masks at paper size times `supersample`. They print in
  order, so later layers sit on top. `opts` keys are `glyph_boxes`, `color` (coloured ink keeps its hue and fades
  lighter), `strength` (a per-layer multiplier), `unit`, and any `age_layer` override.
- `unit` defaults to `supersample/2`.
- `rub` sets the number of rubbed patches; `text_rub` sets the share of the rub that text receives.
- `return_info=True` also returns per-layer `degraded` percentages.

`rub_patches(shape, n=3, seed=0, avoid_boxes=None, strength=1.0, size=1.0) -> removal map`. It gives irregular
patches where 30–50% of the ink is removed in grainy clumps. Multiply alpha by `(1 - map)`.

`bleed_halo(alpha, unit=1.0)` gives a 1–2 px halo mask around heavy strokes; tint the paper with it (composite uses
#70563C at 0.16).

`show_through(alpha, premult_rgb, paper_rgb, amount)` multiplies paper grain into the ink.

`toner_grain(region_mask, density=0.3, seed=0, unit=1.0)` gives optional clumpy photocopy speckle for a region (or a
density map).

`make_paper(w, h, base='#EEE8DA', seed=0, grain=1.0, stains=True, vignette=True) -> uint8 image` gives a generated
fallback paper (grain, fibres, faint foxing, vignette). Prefer `load_paper()` with a real paper image.

`composite(...)` also accepts a paper path, together with `paper_mode`, `paper_scale`, `paper_tint` and `paper_tone`.

### strength, unit and calibration
- `strength=1.0` is the approved reference look: text about 36% degraded, lines about 20–25%. In the seed-label
  example it gives text 36%, lines 20% and patterns 19–21%.
- `strength=0.5` is light to moderate: text about 20–23%, lines about 7%.
- `unit` sets the size of the wear relative to the reference, where body text had a cap height of about 130 px
  (stem about 17–20 px) and rules were 5–20 px wide.
  - Halve `unit` for half-size type.
  - With too large a `unit`, wear looks blotchy; with too small a `unit`, it looks like fine digital noise.

## CLI (existing pictures)
```
python3 age_image.py in.png out.png --strength 0.7 --seed 1 [--paper paper.png] [--paper-mode cover|tile|stretch]
        [--paper-scale 1.0] [--paper-tone none|vintage|aged|#RRGGBB] [--paper-replace] [--no-rub] [--debug]
```
`--paper` loads the image through `load_paper`. By default its luminance texture is multiplied into the picture's
own background, so the picture's colours are kept. `--paper-replace` uses the (toned) paper itself as the
background, which is best for black-on-white art.
It works in these steps:
1. Estimates the background (wide morphological closing) and treats pixels clearly darker than it as ink.
2. Splits the ink into text (small and large groups, each with its own unit), lines (long or thin) and fills
   (fat, dense) by component shape, and separates coloured ink from black.
3. Ages each class on the ink-free background, so non-ink colours are kept.

`--debug` writes `<out>_classes.png` (red: text, magenta: large text, blue: line, green: fill). If no clean ink is
found (low contrast, soft image), it prints a note and applies only global speckle, fading, rub patches and grain.

## Tips
- Keep layers separate (text, small text, lines, patterns, solids, and each colour), because each needs a
  different strength and unit.
- Always check a 2× zoom of the result. If the wear reads as uniform static, lower `strength` or raise `unit`. If
  faded areas look like smooth transparency rather than broken grain, increase pits (lower `bias`) rather than
  lowering opacity.
- Keep rubs off key words (`avoid_boxes`), and keep `text_rub` below 0.5.
- For large solid blocks with knocked-out (reversed) lettering, use `solid_pits` of about 0.3 and `rough=False`, so the
  counters stay open.
- Draw thin hairlines at 2× supersample at least 4 px wide, or they vanish.
- Everything is seeded: the same inputs and seed always give the same image.

## Limits
- The CLI assumes dark ink on a lighter ground. Light-on-dark ink, and big flat coloured areas, are treated as
  ink or fill.
- Shape classification is heuristic. Touching letters can be read as lines, and very large text as fill; check
  with `--debug`.
- Speed is about 40–60 s for a 3200×2200 mask set, and roughly 1 GB of RAM per 10 MP of mask.

## Animating the ageing: `age_prepare` / `age_apply`
`age_layer()` is now `age_apply(age_prepare(...), 1.0)`, with bit-identical output.
- `age_prepare(ink_mask, kind, strength, seed, glyph_boxes=None, unit=1.0, **override)` precomputes every
  deterministic field once.
- `age_apply(fields, q, sweep=6.0)` renders the result at ageing progress `q`. `q=0` is the clean plate and `q=1` is
  the full look. Intermediate `q` sweeps the thresholds over the same noise, so wear appears progressively, with the
  most extreme noise first, and no frame flickers.
- `rub_patches(..., strength=q)` sweeps the same way.

## Ink-seep text animation: `ink_seep_anim.py`
Ink wicks up through the paper from scattered points inside the glyphs.
- The emergence comes from an arrival-time field (staggered seeds, noise, and the paper's own relief), remapped
  through its own distribution so it spreads evenly over the seep.
- Edges are soft, blotchy and feathered, with capillary spill that follows the paper's valleys. Ink starts dilute and
  brown, then converges to crisp text.
- After a short crisp hold, the text ages quickly through `age_apply(q)`. The final frame is identical to
  `composite()`, and the script verifies this on every run.
- The paper stays static throughout.
```
python3 ink_seep_anim.py --title "The Quiet Archive" --subtitle "records kept in ink, and in the patience of paper" \
    --out out/ink_seep.mp4 --stills out/ --fps 60 --durations 0.3,2.2,0.4,0.5,1.8 \
    --paper papers/user_paper_01.jpg --paper-scale 1.6 --tone vintage --seed 7 --strength 1.0 [--rub 3] [--crf 16]
```
Other options:
- `--title-font`, `--sub-font`, `--title-size`, `--sub-size` (output px), `--title-y`, `--sub-y` (fractions of the
  height), `--width`, `--height`.
- `--stills` writes still_seep20/50/90, still_crisp, still_mid_ageing and still_final, plus contact.png and 2× zooms.

Output is H.264 yuv420p. Rendering takes about 160 s for 1920×1080 at 60 fps, or about 95 s at 30 fps.


### Ink colour and the seep (v2)
- `composite(..., ink='#1d1d1f')`, `age_layer(..., ink=...)`, `age_apply(F, q, ink=...)`: base ink colour. The
  aged ramp shifts with it (heavy = ink, mid/faded keep the same warm offsets). Default `None` = classic #111.
  A layer can carry its own `opts['ink']`. `ink_palette(ink)` returns (dark, mid, fade).
- `ink_seep_anim.py --ink '#1d1d1f'` (default) and `--halo 0` (default: no bleed halo, so no grey rim; `--halo 1`
  restores composite's halo). The final frame equals `composite(..., ink=..., halo=halo>0)` exactly.
- The seep is confined to the glyphs. There is no blur, spill or full-glyph blend layer, so paper outside the edges is never touched.
  Arrival time is geodesic travel inside the strokes from evenly spread seeds (skimage `MCP_Geometric`; needs
  `pip install --break-system-packages scikit-image`). The cost map uses paper and fibre noise, so blots run along strokes with fibrous fronts.
  The arrival time is CDF-remapped so the whole title emerges evenly. Each pixel gets an arrival ramp of about 0.34 s
  and a deepening ramp of about 1.0 s (a light warm wash deepening to the full ink colour). Edges sharpen per pixel, from an inset soft edge onto the true glyph edge.
  The global progress uses an ease-in-out. The run prints per-frame alpha stats, a grey-ring metric and the measured ink colour.

### Fibrous feathering + granular seep (v4)
- `fibre_field(paper_rgb)` measures the real paper. It gives the fibre direction (structure tensor), coherence, dark fibre channels (Hessian ridge) and grain.
  `lic(noise, dy, dx)` turns noise into fibre-aligned streaks.
- `feather_spec(paper_rgb, S, reach=6, density=1, rag=1, strand_w=1)` -> pass as `age_prepare(..., feather=spec)` or
  composite layer opts `{'feather': spec}` (text kind). It does two things:
  - It adds fibre-aligned raggedness to the edge band of the plate (2-4 px).
  - It adds discrete ink strands that run outward from the edge along the fibre direction, from 0 up to `reach` px long. Strands are absent in many places, lighter at the tips, and are not a blur or halo.
  Each strand is tied to its root pixel, so aging keeps it while the root ink survives and fades it with the root.
- `show_through(..., grain=)` / `composite(paper_grain=)` scales how much raised fibres lighten the ink.
- ink_seep_anim.py options: `--feather-reach --feather-density --rag --strand-width --ink-grain --grain-spacing
  --grain-hf --grain-lowfreq --fibre-bias --ramp --deepen`. The seep timing is a weighted mix of:
  - fine absorbency: grain valleys, fibre streaks and pinpoint noise;
  - travel time along fibre-cheap paths from dense pinpoint seeds;
  - a weak large-scale term.
  The result appears as stipple, then fibre threads, then solid strokes.

### Left-to-right glyph stagger (v5, default)
- Each glyph is one connected piece of the feathered ink, merged by 1 px. It runs its own granular -> fibre -> solid seep over `--glyph-dur` (default 0.5 s).
  Within a glyph the arrival ramp is 0.24×glyph-dur and the deepening ramp 0.50×glyph-dur; this replaces `--ramp/--deepen`. Order inside a glyph is grain-driven, with a slight left-to-right bias (`--lr-bias`, default 0.25).
- Start times come from the glyph's x-centroid. They are spread over `--sweep` (default 0.75 s) through the inverse of `--stagger-ease` (default inOutCubic; also linear, outCubic, inOutSine, inOutQuad). The result is a sweep front that moves as x = ease(t). Subtitle glyphs share the same x mapping, delayed by `--sub-delay` (default 0.05 s).
- Default durations: `0.15,1.3,0.2,0.4,0.95` = 3.0 s (180 frames @ 60 fps).

### Centre-axis seep (v6, default)
Within each glyph's local seep, ink starts on the stroke's medial axis and widens to both outlines.
- `skimage.morphology.medial_axis` runs on the lightly smoothed stroke core. Spurs from the ragged outline are pruned: an axis pixel is kept only if its width is at least 0.55× the local maximum.
- For each pixel: `d_norm = 0.5*dist_to_axis/R + 0.5*(1 - dist_to_outline/R)`, where R is the half-width at the nearest axis pixel (from the feature transform). Thick strokes and hairlines therefore finish together.
- Arrival order inside the glyph = rank of `axis_weight*d_norm + axis_grain*grain_rank + axis_along*x_along_axis`.
  Defaults: 1.0 / 0.35 / 0.12. CLI: `--axis-weight --axis-grain --axis-along`.
- Feather strands get `d_norm` ≥ 1.25, so they wick out after the edge arrives.
- Per-pixel ramps: `--glyph-ramp 0.18` / `--glyph-deepen 0.45` (fractions of `--glyph-dur`). Ink near the axis therefore deepens first.
- `--lr-bias` is superseded by `--axis-along`.

### No grey veil (v7, default)
The light-wash stage, the warm wash colour, the global deepening ramp and the soft per-pixel ramp are gone.
- Each pixel switches from paper to full ink in `--arrival-frames` (default 1.5 frames). Ink is always the ink colour.
- Visible gradation comes only from where ink has arrived: the centre-axis distance plus a stronger paper grain/fibre order (`--axis-grain` 0.5). Fronts are therefore ink-filled fibres and speckles with bare paper between.
- Raised fibre ridges alone sit up to `--ridge-light` (0.2) lighter for `--glyph-deepen` (0.12 × glyph-dur) after arrival.
- No blur on the alpha field. The run reports the per-frame share of glyph pixels at intermediate coverage (`seep_coverage_stats.csv`).

### Lighter fresh ink that deepens (v8, default)
Coverage stays near-binary: `--arrival-frames` 1.5, no spatial ramp, no blur. Only the DENSITY of ink that has already arrived is animated.
- Starting density follows the texture: `--init-density` (0.5) ± `--density-spread` (0.15). Fibre valleys and channels start at about 65%, ridges at about 35%, plus fine grain noise.
- Density then eases out (cubic) to 100% over `--deepen-time` (0.28 s) per pixel. The lightest fresh ink gets a faint sepia tint (`--tint` 0.12).
- To fit the deepening inside the 1.3 s seep, the new defaults are `--glyph-dur 0.6` and `--sweep 0.65`.
- `seep_coverage_stats.csv` reports coverage and density separately.
