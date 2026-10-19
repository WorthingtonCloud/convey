"""PowerPoint draws exact line spacing in whole points.

Measured Oct 18, 2026 (PowerPoint for Mac 16.114, one sans-serif family, 24 size x line-height blocks of three lines): a line
height that is a whole number of points (16, 20, 24, 36 px ...) advances exactly; a fractional one is rounded half up
before drawing, whatever the file says: 18 px (13.5 pt) is drawn at 14 pt, 30 px (22.5 pt) at 23, 54 px (40.5 pt) at
41, so every line after the first drifts 0.5 to 0.7 px. Slides therefore use line heights PowerPoint will draw as
written: `whole_pt(px)` is the line height in px that a given CSS line height becomes in PowerPoint.
"""
from __future__ import annotations

import math

PT_PER_PX = 0.75


def whole_pt(px: float) -> float:
    """The line height PowerPoint actually draws for an exact spacing of `px`, in px (to 1/100 px)."""
    return round(math.floor(px * PT_PER_PX + 0.5 + 1e-9) / PT_PER_PX, 2)


def is_whole_pt(px: float) -> bool:
    return abs(px * PT_PER_PX - round(px * PT_PER_PX)) < 0.01


def author_pt(px: float) -> float:
    """A line height to write into a slide: the nearest whole point, an exact half rounded DOWN, so the text never
    outgrows the box a template designed for it (a 22.5 pt standfirst in a 60 px box: 22 pt fits two lines,
    23 pt would not). The emitter then writes that whole point, which PowerPoint draws as written."""
    return round(math.ceil(px * PT_PER_PX - 0.5 - 1e-9) / PT_PER_PX, 2)
