"""SVG path data -> absolute segments PowerPoint can draw (move, line, cubic, quadratic, close).

Handles every path command (M L H V C S Q T A Z, absolute and relative). Arcs become cubic
Beziers, one per quarter turn or less. A 2x3 matrix (a, b, c, d, e, f) is applied to every point.
"""
from __future__ import annotations

import math
import re

_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}


def _tokens(d: str):
    """Yield (command, [numbers]) one command at a time, expanding implicit repeats."""
    i, n = 0, len(d)
    cmd = None
    while i < n:
        ch = d[i]
        if ch.isspace() or ch == ",":
            i += 1
            continue
        if ch.upper() in _ARGS:
            cmd, i = ch, i + 1
            if cmd.upper() == "Z":
                yield cmd, []
            continue
        if cmd is None:
            raise ValueError(f"path data must start with a command: {d[:20]!r}")
        k = _ARGS[cmd.upper()]
        args = []
        while len(args) < k:
            while i < n and (d[i].isspace() or d[i] == ","):
                i += 1
            if cmd.upper() == "A" and len(args) in (3, 4):  # flags may be packed: "0110"
                args.append(float(d[i]))
                i += 1
                continue
            m = _NUM.match(d, i)
            if not m:
                raise ValueError(f"bad path data near {d[i:i + 20]!r}")
            args.append(float(m.group()))
            i = m.end()
        yield cmd, args
        if cmd == "M":
            cmd = "L"
        elif cmd == "m":
            cmd = "l"


def _arc(x1, y1, rx, ry, phi, large, sweep, x2, y2):
    """Endpoint arc -> list of cubic control triples ((c1), (c2), (end))."""
    if (x1, y1) == (x2, y2):
        return []
    if rx == 0 or ry == 0:
        return [((x1, y1), (x2, y2), (x2, y2))]
    rx, ry = abs(rx), abs(ry)
    cp, sp = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    co = math.sqrt(max(num / den, 0)) if den else 0
    if large == sweep:
        co = -co
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx, cy = cp * cxp - sp * cyp + (x1 + x2) / 2, sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    segs = max(1, math.ceil(abs(dt) / (math.pi / 2) - 1e-9))
    step = dt / segs
    k = 4 / 3 * math.tan(step / 4)

    def pt(t):
        x, y = rx * math.cos(t), ry * math.sin(t)
        return cp * x - sp * y + cx, sp * x + cp * y + cy

    def dv(t):
        x, y = -rx * math.sin(t), ry * math.cos(t)
        return cp * x - sp * y, sp * x + cp * y

    out = []
    for s in range(segs):
        a0, a1 = t1 + s * step, t1 + (s + 1) * step
        p0, p1 = pt(a0), pt(a1)
        d0, d1 = dv(a0), dv(a1)
        out.append(((p0[0] + k * d0[0], p0[1] + k * d0[1]), (p1[0] - k * d1[0], p1[1] - k * d1[1]), p1))
    out[-1] = (out[-1][0], out[-1][1], (x2, y2))
    return out


def parse(d: str, matrix=(1, 0, 0, 1, 0, 0)) -> list[tuple]:
    """Return [("M", p) | ("L", p) | ("C", c1, c2, p) | ("Q", c, p) | ("Z",)] with points
    as (x, y) after the matrix."""
    a, b, c, dd, e, f = matrix
    T = lambda p: (a * p[0] + c * p[1] + e, b * p[0] + dd * p[1] + f)
    out = []
    cur = start = (0.0, 0.0)
    last_c = last_q = None  # reflection points for S and T
    for cmd, v in _tokens(d):
        rel = cmd.islower()
        C = cmd.upper()
        ox, oy = cur if rel else (0.0, 0.0)
        nc = nq = None
        if C == "M":
            cur = start = (v[0] + ox, v[1] + oy)
            out.append(("M", T(cur)))
        elif C == "L":
            cur = (v[0] + ox, v[1] + oy)
            out.append(("L", T(cur)))
        elif C == "H":
            cur = (v[0] + (cur[0] if rel else 0), cur[1])
            out.append(("L", T(cur)))
        elif C == "V":
            cur = (cur[0], v[0] + (cur[1] if rel else 0))
            out.append(("L", T(cur)))
        elif C in ("C", "S"):
            if C == "C":
                c1 = (v[0] + ox, v[1] + oy)
                c2, p = (v[2] + ox, v[3] + oy), (v[4] + ox, v[5] + oy)
            else:
                c1 = (2 * cur[0] - last_c[0], 2 * cur[1] - last_c[1]) if last_c else cur
                c2, p = (v[0] + ox, v[1] + oy), (v[2] + ox, v[3] + oy)
            out.append(("C", T(c1), T(c2), T(p)))
            cur, nc = p, c2
        elif C in ("Q", "T"):
            if C == "Q":
                c1, p = (v[0] + ox, v[1] + oy), (v[2] + ox, v[3] + oy)
            else:
                c1 = (2 * cur[0] - last_q[0], 2 * cur[1] - last_q[1]) if last_q else cur
                p = (v[0] + ox, v[1] + oy)
            out.append(("Q", T(c1), T(p)))
            cur, nq = p, c1
        elif C == "A":
            p = (v[5] + ox, v[6] + oy)
            for c1, c2, end in _arc(cur[0], cur[1], v[0], v[1], v[2], int(v[3]), int(v[4]), p[0], p[1]):
                out.append(("C", T(c1), T(c2), T(end)))
            cur = p
        elif C == "Z":
            out.append(("Z",))
            cur = start
        last_c, last_q = nc, nq
    return out
