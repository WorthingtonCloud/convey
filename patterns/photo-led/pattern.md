# Pattern: photo-led

**Answers:** What should this feel like?

## Content (the storyboard's `content` for this slide)

```json
{"image": "sources/site-visit.jpg", "focus": "60% 50%", "kicker": "Field visit · March", "subtitle": "One line on what the audience will get.", "credit": "Photo: the team"}
```

A real photo from the person's material (a path in the project), what part of it matters (`focus`, CSS
`object-position`), the headline, and at most a kicker and one line under it. Use it to open a deck or a part,
or for one moment the audience should feel before they see numbers.

## Variants

- **`wash-left`** (full-bleed): the photo fills the right; a fade in the ground color runs into it from the text
  side, so the type always sits on the ground, never on the picture. Best when the subject sits right of center.
- **`framed`** (title-only): the template's title, logo and footer stay; the photo sits in a rounded frame on the right of the body, the kicker and one sentence on the left. The company-template way to show a photo.
- **`bleed-bottom`** (full-bleed): the photo fills the slide; a wash in the ground color rises from the foot, and the kicker, headline and subtitle sit on it. Best when the subject sits in the top half.

## What suits it

A photo of the real thing: the place, the product, the people, the problem. Never stock imagery standing in for
a claim. No photo in the material: use a cover, section or statement variant instead (compose refuses a photo
variant with no `image`).

## Density

- **Live:** headline and a kicker; the subtitle can be spoken.
- **Read-ahead:** the subtitle says what the photo shows.

## Common failures

- A photo that decorates rather than shows (the audience asks "what am I looking at?").
- Text over the busy part of the photo: move `focus` so the subject sits clear of the type.
- Two photo-led slides in a row: the second stops landing.

## On a company template

A full-bleed variant sits on the template's title-only layout, so its headline is still the slide's real title,
but it paints over the layout's art (logo, footer) for that one slide. If the style guide forbids that, keep
photo-led for the cover, or use a title-only variant.
