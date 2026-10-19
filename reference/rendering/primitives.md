# Primitives: the HTML a slide may contain

Everything on this page was converted to a native PowerPoint object and compared against the browser on the Skald test bench (PowerPoint for Mac 16.109, Chrome via Playwright, Oct 15, 2026). Anything not listed here is untested, so don't write it. `convey lint` refuses the known-bad features by name; [compatibility.md](compatibility.md) has the evidence for each line.

Run `convey lint slides/` after writing and before exporting. A refused slide is not exported.

## The slide

```html
<section class="slide"> … </section>
```

- One slide per HTML file, exactly **1280 × 720 px**. That is PowerPoint's 16:9 slide at 9,525 EMU per px, so nothing is scaled.
- The slide's `background-color` becomes the slide background. For a fade or a photo behind everything, use a
  full-bleed box or `<img>` (1280 × 720 at 0, 0): it works on a company template too, above the layout.
- **Set `font-kerning: none` on the slide.** PowerPoint never applies OpenType kerning, so a kerned browser line is wider than the PowerPoint line. Lint refuses any text with kerning on.
- Load the deck's fonts with `@font-face` from the same files installed on the machine that opens the .pptx.

## Naming

- `data-id="step-3"` names the element. The name becomes the object's name in PowerPoint's Selection Pane, and lint uses it in messages. Elements without one get an automatic name like `div-4`.

## Text

A text block is any element whose children are only text and inline elements (`<span>`, `<b>`, `<strong>`, `<br>`; italics are untested). Each block becomes one PowerPoint text box.

- **`line-height` in px, always.** `normal` is refused; the converter needs the number.
- **On a whole number of points** (px × 0.75 is whole: 16, 20, 24, 29.33, 53.33, 60 px …) for any text that wraps.
  PowerPoint draws exact line spacing in whole points, so 54 px (40.5 pt) becomes 41 pt and each later line drifts.
  Compose and the brand's tokens already do this; lint notes any other.
- **Text must fit its box.** A word wider than its box spills out in the browser but is broken in half by PowerPoint. Lint refuses overflow.
- Sizes 12–300 px and weights 100–900 are proven. Display type (120 px and up, a giant number or a one-line
  statement) sits best at a line height of 1.0 or 1.1 times its size; near 1.2 PowerPoint changes how it places a
  line, and big type shows it. Each weight maps to a named font face through `fonts.json` (PowerPoint has only bold on/off).
- Inline runs may change weight and color mid-sentence.
- `letter-spacing` (positive or negative), `text-transform: uppercase`, and `text-align` left, center or right all convert.
- Labels centered in a box with flexbox convert, including inside rounded boxes and circles.
- Semi-transparent text converts (`color` with alpha, or `opacity`), but PowerPoint's PDF draws it as a picture, so
  the export report can only compare its pixels. For quiet text, use a solid color: on the template's own background,
  the brand's body color (the one color the template promises reads there; a derived muted gray can vanish on a
  template whose background is a picture or a fade).
- A wrapped line may fill its box to the last pixel: the export gives wrapped text the spare width no line can use,
  so PowerPoint, which sets some fonts a hair wider, keeps the browser's line breaks.
- With a calibrated Brand Profile, the export also corrects how wide PowerPoint sets text up to 32 px, size by size
  (a long 14 px source line drifted 3 px by its end without it).

## Boxes

Any element with a background or a border becomes a PowerPoint shape.

- `background-color`, solid borders at any width, and borders on only some sides.
- One `border-radius` for all four corners. `border-radius: 50%` makes a circle, or an oval on a non-square box.
- Not allowed: dashed or dotted CSS borders (draw an SVG line), corners with different radii, outlines.

## Fades and shadows

Both become PowerPoint's own effects, editable in its Format pane, and both are proven against PowerPoint's PDF.

- **One gradient per box**, as its `background`: `linear-gradient(<angle> or to <side>, <color> <pos>%, …)`, any
  number of stops, see-through stops included (a dark wash that fades to clear over a photo). The export adds a
  stop every 10% so PowerPoint's blend matches the browser's.
- **Radial: a centred circle only**, `radial-gradient(circle, …)` (on a square box the default ellipse is a circle
  too). PowerPoint can't move a radial's centre or stretch it: for an off-centre glow, give the glow its own
  square box centred where the glow should be.
- **One soft shadow per box**: `box-shadow: X Y BLUR <color>` (no spread, not inset), on a box with a fill, a
  border, a gradient or a photo. Not on bare text (PowerPoint would shadow the letters).
- **A brand color with its own transparency:** `color-mix(in srgb, var(--brand-data-2) 50%, transparent)` works
  wherever a color does: a fill, a gradient stop, a shadow. That is how a glow or a wash stays in the brand's colors.
- Refused: two gradients or shadows on one element, gradient text (`background-clip: text`), background images
  (use an `<img>`), and `opacity` on a box with a gradient (Chrome's PDF draws it as one flat color, so the report
  can't check it: put the transparency in the stops with `color-mix`).

## Layout

Position elements any way CSS allows: `position: absolute`, flexbox, grid, padding, margins and nesting. The converter reads the final position from the browser, so the method doesn't matter.

- Layer order follows `z-index`, then the order elements appear in the HTML.

## Lists

```html
<ul style="list-style-type: '•  '; line-height: 32px"> <li>One</li> <li>Two</li> </ul>
<ol style="line-height: 32px"> <li>First</li> <li>Second</li> </ol>
```

- One list becomes one text box with real PowerPoint bullets or numbering.
- **Bullets must be a text marker**: `list-style-type: "•  "` (or `"–  "`). The default `disc`, `circle` and `square` dots are drawn as shapes by the browser and can't match PowerPoint's bullet. Lint refuses them.
- `<ol>` numbering (`decimal`) converts. Every `<li>` must hold text only.
- Space between items with `margin-top` on the `<li>`.

## SVG shapes

Inline `<svg>` elements become native, editable PowerPoint shapes.

- Allowed: `rect`, `circle`, `ellipse`, `line`, `polyline`, `polygon`, `path` (straight, curved and arc segments), solid fills, strokes, `stroke-dasharray`, line caps.
- `<g data-id="…">` or `<svg data-group>` makes a PowerPoint group.
- Not allowed: SVG `<text>` (use HTML text placed over the SVG), gradients, patterns, filters, clip paths, masks, `<image>`, `<foreignObject>`.

## Arrows and connectors

```html
<marker id="head" markerUnits="userSpaceOnUse" markerWidth="8" markerHeight="8"
        viewBox="0 0 8 8" refX="8" refY="4" orient="auto-start-reverse">
  <path d="M0 0 L8 4 L0 8 z" fill="#888888"/>
</marker>
<line data-id="e1" data-from="src" data-to="mid" x1="300" y1="168" x2="530" y2="168"
      stroke="#888888" stroke-width="2" marker-end="url(#head)"/>
```

- **An arrowhead is one filled triangle**, the same color as its line, with its tip at the line's end (`refX` = the tip).
- **Its length and width must each be 2, 3 or 5 × the line width**, counting the line width as no less than 2.667 px. Those are PowerPoint's only sizes (small, medium, large). For a 2 px line the sizes are 5.333, 8 and 13.333 px.
- `data-from` and `data-to` name the boxes a line connects. The line becomes a PowerPoint connector glued to those boxes, so moving a box drags its arrows.

## Charts

```html
<figure data-chart='{"type":"column","categories":["Jan","Feb"],
  "series":[{"name":"A","values":[62,71],"color":"#3366aa"}],
  "axis":{"min":0,"max":100,"step":20,"format":"{v}%"}}'
  style="position:absolute; left:64px; top:130px; width:1150px; height:520px"></figure>
<script src="chart.js"></script>
```

- A chart is a data file, never hand-drawn SVG. `chart.js` draws it in the page with PowerPoint's own geometry, and the export builds a native chart with editable data from the same spec.
- Types: `column` and `bar` (horizontal, first category at the top), each clustered or `"stacked": true`
  (negatives stack below zero); `line`; `area` (a series may set `"opacity"` to see the one behind);
  `doughnut` (one series; `colors` per slice).
- Spec fields: `categories`, `series[].name/values/color`, `axis.min/max/step/format`, and optional `fontSize`, `gap` (column gap %), `lineWidth`, `hole` (doughnut %), `gridWidth`, `plot` (`l`, `t`, `r`, `b` margins in px).
- **Value labels:** `"labels": true` puts each value on the chart as a native text box (above a column, at a
  bar's end, inside a stacked segment, after a line's last point), in `labelFormat` (default: the axis format);
  `valueLabelColor`, `insideLabelColor`, `labelWeight` style them. chart.js places them; never hand-place values.
- The label font comes from the figure's CSS `font-family` and `font-weight`. Label color is the figure's `color`, and gridline color is its `--chart-grid` custom property.
- No legend and no title inside the chart: write those as HTML text. Compose writes the key for you: every series of
  a multi-series chart, or the storyboard's `content.legend` (`[{"label", "color"}]`) for one series whose bars take
  their own colors. It sits beside the figure as `data-legend-for="<figure's data-id>"`, and chart.js places it on the
  plot's top edge and leaves room for it.
- chart.js fits the plot's margins to its axis labels; give `plot` only for a side you want fixed. PowerPoint places
  axis labels by the font's own metrics, so `convey brand calibrate` measures them in the brand's body font and
  writes `--brand-chart-labels` into tokens.css; chart.js follows it (Berlin's category names sat 2 px low without). Lint refuses a value
  label that a fixed `plot.l` cuts off (the browser cuts it; PowerPoint doesn't). Negative values read "-$100K", as
  PowerPoint writes them, and category labels stay under the plot.

## Pictures

- `<img>` with a photo or PNG becomes a PowerPoint picture. `object-fit: cover` and `contain` become a PowerPoint crop, and PNG transparency survives.
- `object-position` (`30% 50%`, `left center`) picks which part of a cover-cropped photo shows.
- `border-radius` on the picture rounds it, `50%` makes it a circle (PowerPoint crops to that shape), and one
  `box-shadow` lifts it.
- A headline on a photo: the photo, then a box with a see-through gradient over it (dark where the text sits), then
  the text.
- Pictures are for photos. A logo or icon should be inline SVG, so it stays editable.

## Rotation

- `transform: rotate(…)` about the element's center converts to PowerPoint's own rotation.
- Only on an element with no child elements: a text block, a box, or a picture.
- No other transform: no scale, skew, translate or off-center origin.

## Refused outright

Lint names the element for each of these:

- background images, gradient text, and gradients or shadows beyond the ones above;
- text shadows;
- filters, backdrop filters and blur;
- clip paths and masks;
- blend modes;
- `::before` / `::after` content;
- `<canvas>`, `<video>`, `<iframe>`, `<object>`, `<embed>`, `<audio>`;
- SVG text, gradients and patterns;
- dashed or dotted CSS borders;
- outlines;
- corners with different radii;
- vertical writing modes;
- transforms other than rotation about the center, and rotation on an element with children;
- `line-height: normal`, kerning left on, and text overflowing its box;
- characters the text's font doesn't have (another script, a rare symbol): the browser borrows another font for them
  and PowerPoint picks a different one;
- arrowheads that aren't a PowerPoint size, aren't a single triangle, aren't the line's color, or don't end at the tip;
- `disc`, `circle` or `square` list bullets;
- a chart figure without `chart.js` on the page.

## Company layouts

With a Brand Profile, `convey export --brand NAME` writes each slide onto the company template's own layout:
the slide's `data-layout="Layout name"`, else the brand's binding for its `data-pattern`, else the template's
blank layout. The layout then draws its own background, logos, rules and footer, and the template's fonts
are referenced through the theme, so a template change restyles the deck.

- **The headline goes in the layout's title placeholder:** give the slide's headline `data-bind="headline"`
  (plain text, no background, not inside a group). PowerPoint's outline view then lists it.
- **Show the layout in the browser with an underlay** (`convey brand render` pictures every layout):

  ```html
  <section class="slide" data-pattern="chart">
  <style>.slide { isolation: isolate; }</style>
  <img data-underlay alt="" src="layouts/07-chart.png"
       style="position:absolute;left:0;top:0;width:1280px;height:720px;z-index:-1">
  …
  ```

  Export skips anything marked `data-underlay`: the layout itself draws it. Don't redraw what the layout
  already draws (its rules, logo or footer), or the slide shows both.
- `--numbers` adds the layout's slide-number placeholder to every slide.

## Icons and diagram parts

The skill ships its own picture vocabulary in `skill/assets/`: 80 concept icons and 8 diagram parts. Every
one is drawn for this skill, released MIT-0 with it, and built only from the primitives above, so each
exports as native, editable PowerPoint shapes. Reach for one when a picture says it faster than a word.
`assets/gallery.html` shows them all.

- **Find an icon by meaning:** `convey assets find risk` lists the icons whose concepts match
  (`assets/catalog.json` maps each icon to the words it stands for).
- **Paste it:** `convey assets show warning --size 64 --id risk-icon` prints the inline SVG. It becomes one
  named group in PowerPoint.
- **Color:** icons draw in `currentColor`. Set `color: var(--brand-ink)` (or any brand variable) on the icon
  or its parent; never write a color into the icon itself.
- **Size: 32 px and up.** The 3-unit strokes run together below that, and lint refuses an icon (`data-icon`)
  smaller than 32 px. Keep one size per row of icons.
- **Diagram parts:** `convey assets part NAME key=value…` prints slide HTML for `arrow` (glue it to boxes
  with `from_id`/`to_id`), `elbow` (`points=x,y,x,y,…`), `curve`, `brace` and `bracket` (`side=left|right|top|bottom`),
  `step` (a numbered disc), `callout` (a note box with a pointer) and `chevrons` (a process row,
  `labels="Plan|Build|Ship"`). Arrowheads come out in PowerPoint's medium size, so lint passes them.
- Text never goes inside an icon. Labels are HTML text placed beside or under it.
