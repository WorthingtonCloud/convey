# Compatibility: what converts, measured

Each row is a feature, its status, and the evidence. **Text shift** is the worst distance any word moved between the browser and PowerPoint. **Pixels** is the share of the slide that looks different after forgiving edge smoothing.

Measured on the Skald test bench, Oct 15, 2026: PowerPoint for Mac 16.109 against headless Chrome (Playwright 1.58), both rendered to PDF and rasterized by the same program. Cards are in the bench's `cards/` folder.

**Status:** ✅ converts with no visible difference (text within 2 px, under 0.05% of pixels) · 🟡 converts, text 2–3 px off or 0.05–0.11% of pixels, identical to the eye · ⛔ refused by `convey lint`.

## Text

| Feature | Status | Evidence |
|---|---|---|
| Sizes 12–96 px, one line each | ✅ | t01: 1.12 px |
| Weights 100–900, as named faces | ✅ | t02: 0.44 px, the real face used every time |
| Paragraph wrapping at four widths | 🟡 | t03: same line breaks, 2.1 px |
| Letter spacing (−0.05 to 0.3 em), uppercase | ✅ | t04: 1.39 px |
| Line height 1.0–2.0 | 🟡 | t05: 2.08 px |
| Left, center, right alignment | 🟡 | t06: 2.24 px |
| Mixed weights and colors in one sentence | 🟡 | t07: 2.84 px |
| Labels centered in boxes, rounded boxes and circles | ✅ | t08: 1.38 px |
| Vertical position, 12–32 px | ✅ | t10: 1.08 px |
| Semi-transparent text | ✅ | l05: 1.56 px (see caveat 4) |
| Text overflowing its box | ⛔ | t11: PowerPoint broke the word in half |
| `line-height: normal` | ⛔ | the converter needs the number |
| Kerning left on | ⛔ | "Weight" at 40 px drew 2.5 px wider, pushing every later word right |

## Shapes and layout

| Feature | Status | Evidence |
|---|---|---|
| Rectangles, borders at every width | ✅ | s01: 0.00% |
| Rounded corners, circles, ovals | ✅ | s02: 0.00% |
| One-sided borders and rules | ✅ | s03: 0.00% |
| Overlapping layers, z-index | ✅ | l01, l02: 0.00% |
| CSS grid | ✅ | l03: 0.007% |
| Flexbox flow and nesting | ✅ | l04: 0.00% |
| Transparent fills | ✅ | l05: 0.004% |
| Groups, including nested groups | ✅ | g01: 3 PowerPoint groups, 0.00% |
| Rotation about the center | ✅ | i02: box, picture, text and rule, 0.00% |
| Dashed or dotted CSS borders | ⛔ | draw an SVG line with `stroke-dasharray` |
| Corners with different radii | ⛔ | no single PowerPoint shape matches |
| Other transforms, rotation on a parent | ⛔ | — |

## SVG, arrows and connectors

| Feature | Status | Evidence |
|---|---|---|
| rect, circle, ellipse, line, polyline, polygon | ✅ | s04: 0.00%, all native |
| Paths: curves, arcs, dashes | ✅ | s05: 0.00%, native freeforms |
| Arrowheads in PowerPoint's sizes | ✅ | a01: 14 arrows, 0.00% |
| Connectors glued to boxes | ✅ | a02: all 8 ends attached, 0.001% |
| Other arrowhead sizes, tip not at the end | ⛔ | s06 |
| SVG text | ⛔ | x05 |
| SVG gradients and patterns | ⛔ | x05 |

## Lists, charts and pictures

| Feature | Status | Evidence |
|---|---|---|
| Text-marker bullets and numbering | ✅ | b01: one text box per list, 1.04 px |
| Default dot bullets (`disc`) | ⛔ | t09, x06: the browser draws a shape, PowerPoint a character |
| Native column chart | ✅ | k01: 0.00%, labels 0.8 px, data editable |
| Native line chart | ✅ | k02: 0.00%, labels 0.8 px |
| Native doughnut chart | ✅ | k03: 0.00% |
| Small chart with a % axis | ✅ | k04: 0.00%, labels 0.71 px |
| Photos with `object-fit` cover/contain | ✅ | i01: kept as a PowerPoint crop |
| PNG transparency | ✅ | i01 |
| Inline SVG logo | ✅ | i01: native shapes, no picture |

## Refused effects

| Feature | Status | Evidence |
|---|---|---|
| Gradients, background images | ⛔ | x01: 60.8% of pixels differ if exported |
| Box and text shadows | ⛔ | x02 |
| Filters, blur, clip paths | ⛔ | x03: 6.1% of pixels differ if exported |
| `::before`/`::after`, canvas | ⛔ | x04 |
| Blend modes, masks, outlines, vertical text | ⛔ | no native equivalent |

## Whole slides

Six realistic slides were written after the line-spacing correction was fitted, so they test it on unseen content.

| Slide | Status | Text shift | Pixels |
|---|---|---|---|
| r01 Agenda | ✅ | 1.17 px | 0.00% |
| r02 Executive summary | ✅ | 2.0 px | 0.032% |
| r03 Before and after | ✅ | 1.28 px | 0.016% |
| r04 Timeline | ✅ | 1.28 px | 0.017% |
| r05 Architecture | 🟡 | 1.76 px | 0.061% |
| r06 KPI row | 🟡 | 1.76 px | 0.057% |

## Caveats

1. **Line spacing needs a per-font calibration.** With exact line spacing, PowerPoint sets each line lower than a browser does: `drop = a × line height + b × font size + c` px. The bench fitted `a = 0.219, b = −0.28, c = 0.154` for one sans-serif font. Each font in a template needs its own fit, stored in `fonts.json` under `_vertical`. The leftover error averages 0.8 px.
2. **Weights become named faces.** PowerPoint has bold on or off, nothing else. `fonts.json` maps each CSS weight to the installed face's family name (for example `"600": ["Family SemiBold", false]`, `"700": ["Family", true]`).
3. **One-line text is not wrapped in PowerPoint.** PowerPoint measures text a hair wider than Chrome, so the converter turns wrapping off for single-line text. Without that, the last word dropped a line (a 192 px "shift").
4. **PowerPoint's PDF export drops semi-transparent text as text.** It renders correctly, but the checker can't read its position back, so it is graded on pixels only.
5. **Preset shapes inset their text.** PowerPoint pulls text in by 0.293 × the corner radius in a rounded box and 0.146 × the size in an oval. The converter compensates.

## Untested: don't write these yet

Italic text, underline, links, tables, `<sup>`/`<sub>`, justified text, right-to-left text, emoji, SVG `<image>` and `<use>`, more than one font per slide, and slides other than 1280 × 720. Each needs a bench card before it is allowed.
