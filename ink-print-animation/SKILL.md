---
name: ink-print-animation
description: >-
  Use when the user wants a short video of text printing itself in ink on
  vintage paper: an INK SEEP-IN (ink seeps through the paper fibres from each
  stroke's centre, letters left to right) and/or an AGEING animation (fresh
  print wears to faded old print in a moment). The two can be used separately or
  together; ask which before rendering.
---
# Ink print animation

This skill has two animations in the ink-print style. They work independently or chained. The still looks they start and end on, fresh print and aged print, are defined in the `ink-print-style` skill; follow its paper and ink rules here too. Wording, fonts and layout come from the request; never reuse earlier sample text such as "The Quiet Archive".

## 1. Ask first, always
Before rendering, ask the user which animation they want, with a question widget, even if they say "animate it". Only skip the question when they named the choice explicitly in this request. The options are:
- **Ink seep-in only:** blank paper, then ink seeps in, ending on the fresh print. The default runs 2.25 s.
- **Ageing only:** fresh print, then it quickly wears to aged print. The default runs 1.9 s.
- **Both:** seep-in, then ageing. The default runs 3.0 s.

Also confirm the text, unless it's given, and the length if they care about it.

## Tool
It's in the `aged-ink/` folder inside this skill folder. Read the "Two skills" section of `README.md` first.
```
python3 ink_seep_anim.py --phases seep|age|both --title "…" [--subtitle "…"] --out out.mp4 \
  [--stills dir/] [--fps 60] [--durations …] [--paper papers/<paper> --paper-scale 1.6 --tone vintage] \
  [--ink '#1d1d1f'] [--seed 7] [--strength 1.0]
```
- **Durations:** `--durations` takes 3 values for seep or age, or 5 for both (empty, seep, fresh hold, ageing, aged hold). Frame counts are exact at any frame rate.
- **Ageing an existing image:** `--phases age --from-image img.png` ages the image's own extracted ink. The seep needs vector text, so it can't start from a picture.
- **References:** samples are in `examples/` (`anim_seep.mp4`, `anim_age.mp4`, `anim_both.mp4`).

## Seep-in: what success looks like
- **Order:** letters appear one by one from left to right on an eased curve (inOutCubic, `--stagger-ease`). Neighbouring letters overlap, so it flows rather than ticks. The subtitle sweeps with the title, slightly delayed.
- **Within each stroke:** ink starts as a thin, grainy thread along the stroke's centre line, the axis of symmetry, curves and serifs included. It then widens evenly to both edges. Thick and thin strokes finish together.
- **Fibres:** the ink spreads through the paper's fibre channels and grain pits first and raised fibres last. Advancing edges look like ink-soaked fibres and specks with bare paper beside them. Feathered strands wick out last.
- **Colour:** fresh ink lands lighter, at about 50% and textured (darker in fibre channels, paler on ridges). It deepens to full `#1d1d1f` over about 0.28 s.
- **Never:** a grey shadow, veil or outline (the user rejected these three times); a plain opacity fade, wipe or blur; or ink that retracts. Each pixel switches from paper to ink almost instantly, and only its darkness animates.
- **Knobs:** `--glyph-dur` 0.6, `--sweep` 0.65, `--axis-weight`, `--axis-grain`, `--axis-along`, `--init-density`, `--density-spread`, `--deepen-time`, `--tint`, `--arrival-frames`, and the feather options.

## Ageing: what success looks like
- The fresh print wears to the aged print in about 0.4–0.5 s. Fading, broken strokes, pits and rub patches spread progressively from the same fixed noise, so there's no flicker. The final frame matches the aged still exactly.
- Hold on the aged result long enough to read it, at least 0.9 s.

## Verify before delivering
- Render with `--stills` and look at the contact sheet plus 4× crops of a horizontal stroke, a vertical stem and a curve partway through the seep.
- Check for no grey veil, no shadow outside the letters and no pops. The script's own checks also confirm that the fresh frame matches `fresh_print()` and the aged frame matches `composite()`.
- Deliver the mp4 as an attachment, then a short note with the key frames.

## Notes
- A 1080p60 render of the full version takes a few minutes. Use 30 fps for quick previews.
- Changing the seed moves the wear and rub patches. If a rub lands on a key word, try another seed.
