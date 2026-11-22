---
name: ink-print-style
description: >-
  Use when the user wants text or an image (mainly one you generate in code, or
  a picture they supply) to look printed in ink on real vintage paper: either
  FRESH PRINT (crisp #1d1d1f ink with fibre-feathered edges) or AGED PRINT (ink
  faded and worn over decades). Still images only; style only, any subject. Ask
  which style before applying.
---
# Ink print style (still images)

A reusable *style*, not a design. It makes text, lines and patterns look printed in ink on real, yellowed paper, in one of two styles. Subject, wording, layout and composition always come from the request; never copy content from earlier projects (for example the compass card or "The Quiet Archive").

For animating these styles (ink seeping in, or ageing on screen), use the separate `ink-print-animation` skill.

## 1. Ask first
Before rendering, ask the user which style they want, with a question widget, unless they already said:
- **Fresh print:** freshly printed ink that sits in the paper.
- **Aged print:** the same print, worn and faded over decades.

If they answer vaguely, suggest the one that fits and confirm.

## Tool
It's in the `aged-ink/` folder next to this skill folder (`../aged-ink/` relative to this SKILL.md). Read `README.md` first; its "Two skills" section has the commands.
- `aged_ink.py` is the module: `fresh_print()`, `composite()`, `load_paper()`, `text_masks()`.
- `print_still.py` renders title and subtitle text as a still.
- `age_image.py` handles existing pictures, with `--style fresh|aged`.
- `fonts/` holds IM Fell English roman, italic and small caps.
- `papers/` holds the user's paper textures.
- `examples/fresh_still.png` and `examples/aged_still.png` are the approved references.

## Paper (always)
- **Base:** use the user's real paper image, never generated paper. When they attach a new paper, copy it to `papers/user_paper_NN.ext` and use it; otherwise use the latest one in `papers/`. Fall back to `make_paper()` only when none exists.
- **Loading:** `load_paper(path, w, h, mode='cover', scale=1.6, tone='vintage')`.
- **Tone:** `'vintage'` (#EAD9AC, the default), `'aged'` (#E2CB93, browner edges), `'none'`, `'#RRGGBB'` or a dict. Toning keeps the grain.

## Ink
- The default ink is `#1d1d1f`, never pure black. It is multiplied into the paper so the grain shows through.
- There's no bleed halo or grey rim around letters. The user has rejected any soft grey outline or translucent grey veil, so never add one.

## Fresh print: what success looks like
- Edges are ragged at a 2–4 px scale and follow the paper's fibre direction, which is measured from the paper image itself.
- Thin ink strands wick out 3–8 px along the fibres. They're absent in many places, lighter at the tips, and leave bare paper between them.
- The paper grain lightens fibre ridges slightly inside strokes.
- Everything stays crisp and legible.
- Code path: `fresh_print(paper, layers=[(mask, 'text'|'line'|'pattern', opts)], ink='#1d1d1f', seed=..., supersample=2)`. The knobs are `feather_reach`, `feather_density`, `rag`, `strand_width` and `ink_grain`. Lines and patterns get strands but keep their own edge.
- Command line: `python3 print_still.py --style fresh --title "…" --subtitle "…" -o out.png`.

## Aged print: what success looks like
- **Text:** inking varies from letter to letter, with some near-full ink and some washed to brown-grey. Faded patches can span several letters. Edges are nibbled, thin strokes and serifs break, and small paper-coloured pits show inside strokes. Every word stays legible.
- **Lines:** uneven ink, thinned stretches, short skipped-ink gaps and rough edges.
- **Patterns and fills:** hatching fades in patches and solids are mottled and pitted. `toner_grain` adds optional speckle.
- **Overall:** two or three grainy rubbed patches lighten everything by 30–50%, and the paper grain shows through the ink.
- **Strength:** at 1.0 (the approved look), about 35% of the text ink and 20–25% of lines and patterns is worn. Use 0.5 for subtle.
- **Code path:** `composite(paper, layers, strength=1.0, seed=..., supersample=2, avoid_boxes=[key words], feather=True, ink='#1d1d1f')`. Aged is the fresh print plus wear on the same feathered edges.
- **Command line:** `python3 print_still.py --style aged -o out.png`. `--aged-classic` gives the older look: #111 ink, clean edges, halo.

## Images you generate (primary path)
1. Design the picture as the request asks, in Python with PIL or numpy, at 2× supersample.
2. Draw each ink category as its own mask: text, lines and patterns.
   - Small type goes on its own text layer with a smaller `unit`, for example 0.5.
   - Use `text_masks()` for text lines.
3. Load the paper as above. Lay non-ink colour areas on the paper by multiply. Coloured ink goes in its own layer with `opts={'color': ...}`.
4. Render with `fresh_print` or `composite` according to the chosen style. Keep the seed fixed so results reproduce.

## Existing pictures (secondary path)
`python3 age_image.py in.png out.png --style fresh|aged --paper papers/<paper> --paper-tone vintage --paper-scale 1.4 [--paper-replace] [--debug]`
- It extracts dark ink from a lighter ground, sorts it into text, lines and fills, and treats each.
- It works best on high-contrast line art, typography, logos and scans.
- Photos fall back to a lighter overall effect, so tell the user when that happens.
- For the aged style, 0.6–0.7 here is roughly equal to 1.0 on the primary path.

## Verify before delivering
- Check the full image plus a 2× crop of the densest text and of a pattern area.
- It must read as real ink on real paper, with no grey outline or veil, no stray specks on empty paper, and every word readable. No rub patch should erase a key word.
- To change the strength, adjust `strength` or the per-layer options. To change the colour, use `tone` or `ink`.

## Notes
- A supersampled canvas of about 3200×2200 takes roughly 40–60 s and a few GB of RAM.
- The tool needs scikit-image, which is installed on the box.
