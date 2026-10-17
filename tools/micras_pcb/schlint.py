"""Legibility checks of a schematic sheet: what overlaps what.

Each text (symbol fields, labels, sheet names, free text) is a box estimated from KiCad's stroke
font advance widths; each symbol body is its graphics' bounding box; wires, pin lines and frame
edges are segments. A sheet reads cleanly when no two texts overlap, no text sits on a body or is
crossed by a line, no two bodies overlap, no wire runs through a body, and everything lies on the
page, clear of the title block.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from .schematic import PAPER, Sheet, Symbol, text_width, transform, xy

FONT = 1.27
MARGIN = 0.05  # mm two boxes may share before they count as overlapping


@dataclass
class Box:
    x0: float
    y0: float
    x1: float
    y1: float
    what: str
    owner: str = ""  # the symbol or label it belongs to

    def hits(self, o: Box, m: float = MARGIN) -> bool:
        return self.x0 < o.x1 - m and o.x0 < self.x1 - m and self.y0 < o.y1 - m and o.y0 < self.y1 - m


@dataclass
class Line:
    a: tuple[float, float]
    b: tuple[float, float]
    what: str
    owner: str = ""

    def crosses(self, box: Box, m: float = MARGIN) -> bool:
        """The segment enters the box's interior (shrunk by m)."""
        x0, y0, x1, y1 = box.x0 + m, box.y0 + m, box.x1 - m, box.y1 - m
        (ax, ay), (bx, by) = self.a, self.b
        # Liang-Barsky clipping against the box
        t0, t1 = 0.0, 1.0
        dx, dy = bx - ax, by - ay
        for p, q in ((-dx, ax - x0), (dx, x1 - ax), (-dy, ay - y0), (dy, y1 - ay)):
            if abs(p) < 1e-12:
                if q <= 0:
                    return False
                continue
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 >= t1:
                return False
        return True


def _text_box(x, y, text, angle, h_justify, v_justify="center", size=FONT, what="", owner="") -> Box:
    """A text's box: angle 0 reads left to right, 90 bottom to top."""
    w, h = text_width(text, size), size
    lo, hi = {"left": (0, w), "right": (-w, 0), "center": (-w / 2, w / 2)}[h_justify]
    vlo, vhi = {"center": (-h / 2, h / 2), "bottom": (-h, 0), "top": (0, h)}[v_justify]
    pad = 0.2 * size  # strokes, and the space KiCad leaves between lines
    if angle % 180 == 0:
        return Box(x + lo, y + vlo - pad, x + hi, y + vhi + pad, what, owner)
    return Box(x + vlo - pad, y - hi, x + vhi + pad, y - lo, what, owner)


def _justify(eff) -> tuple[str, str]:
    j = eff.child("justify").atoms() if eff and eff.child("justify") else []
    h = "left" if "left" in j else "right" if "right" in j else "center"
    v = "top" if "top" in j else "bottom" if "bottom" in j else "center"
    return h, v


def _hidden(node) -> bool:
    hide = node.child("hide")
    return bool(hide and hide.atoms() == ["yes"])


def symbol_fields(s: Symbol) -> list[Box]:
    """Visible fields as drawn: KiCad applies the symbol's transform to each field's angle and
    justification, and keeps the text readable (never upside down)."""
    out = []
    for p in s.node.children("property"):
        a = p.atoms()
        if _hidden(p) or len(a) < 2 or not a[1].strip() or not p.child("at"):
            continue
        at = p.child("at").atoms()
        fr = int(float(at[2])) if len(at) > 2 else 0
        eff = p.child("effects")
        size = float(eff.child("font").child("size").atoms()[1]) if eff and eff.child("font") else FONT
        h, v = _justify(eff)
        r = math.radians(fr)
        ax, ay = transform((round(math.cos(r)), round(-math.sin(r))), s.rot, s.mirror)
        if ay == 0:  # horizontal on the page
            if ax < 0 and h != "center":
                h = {"left": "right", "right": "left"}[h]
            angle = 0
        else:
            if ay > 0 and h != "center":
                h = {"left": "right", "right": "left"}[h]
            angle = 90
        x, y = float(at[0]), float(at[1])
        out.append(_text_box(x, y, a[1], angle, h, v, size, f"{s.ref} {a[0]} '{a[1]}'", s.ref))
    return out


def pin_names(s: Symbol) -> list[Box]:
    """Pin names drawn inside the body, beside each pin's inner end."""
    if s.lib.name_offset is None:
        return []
    out = []
    for p in s.pins():
        lp = next(lp for lp in s.lib.pins if lp.number == p.number)
        if p.hidden or p.name in ("", "~"):
            continue
        ix, iy = (
            p.at[0] - p.out[0] * (lp.length + s.lib.name_offset),
            p.at[1] - p.out[1] * (lp.length + s.lib.name_offset),
        )
        w = text_width(p.name.replace("~{", "").replace("}", ""))
        if p.out[1] == 0:
            x0 = ix if p.out[0] < 0 else ix - w
            out.append(Box(x0, iy - 0.7, x0 + w, iy + 0.7, f"{s.ref} pin name {p.name}", s.ref))
        else:
            y0 = iy if p.out[1] < 0 else iy - w
            out.append(Box(ix - 0.7, y0, ix + 0.7, y0 + w, f"{s.ref} pin name {p.name}", s.ref))
    return out


def label_box(kind: str, text: str, at, angle: int, size: float = FONT) -> Box:
    """A label's text, with its flag for a global or hierarchical label, along its angle."""
    w = text_width(text, size)
    x, y = at
    if kind == "label":
        start, length, lo, hi = 0.25, w, -0.45 - 1.05 * size, -0.2  # above the wire (left of a vertical one)
    elif kind == "global_label":
        start, length, lo, hi = 0.0, w + 2.4, -1.05, 1.05
    else:
        start, length, lo, hi = 0.0, w + 1.9, -0.85, 0.85
    d = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}[angle % 360]
    a0, a1 = start, start + length
    if d[1] == 0:
        xs = sorted((x + d[0] * a0, x + d[0] * a1))
        return Box(xs[0], y + lo, xs[1], y + hi, f"{kind} {text}", f"{kind}:{text}@{x:g},{y:g}")
    ys = sorted((y + d[1] * a0, y + d[1] * a1))
    return Box(x + lo, ys[0], x + hi, ys[1], f"{kind} {text}", f"{kind}:{text}@{x:g},{y:g}")


def collect(sheet: Sheet) -> tuple[list[Box], list[Box], list[Line]]:
    """(texts, bodies, lines) of a sheet."""
    texts, bodies, lines = [], [], []
    for s in sheet.symbols:
        name = s.ref if not s.power else f"{s.value} symbol {s.ref[-6:]}"
        b = s.body()
        if b:
            bodies.append(Box(*b, f"body of {name}", s.ref))
        texts += symbol_fields(s)
        texts += pin_names(s)
        for p in s.pins():
            if p.hidden:
                continue
            lp = next(lp for lp in s.lib.pins if lp.number == p.number)
            end = (p.at[0] - p.out[0] * lp.length, p.at[1] - p.out[1] * lp.length)
            if lp.length:
                lines.append(Line(p.at, end, f"pin {p.id}", s.ref))
    for lb in sheet.labels:
        eff = lb.node.child("effects")
        size = float(eff.child("font").child("size").atoms()[1]) if eff and eff.child("font") else FONT
        texts.append(label_box(lb.kind, lb.text, lb.at, lb.angle, size))
    for a, b in sheet.wires:
        lines.append(Line(a, b, f"wire ({a[0]:g}, {a[1]:g})-({b[0]:g}, {b[1]:g})"))
    for n in sheet.root.children("sheet"):
        (x, y), (w, h) = xy(n.child("at")), xy(n.child("size"))
        name = n.prop("Sheetname") or ""
        bodies.append(Box(x, y, x + w, y + h, f"sheet {name}", f"sheet:{name}"))
        for p in n.children("property"):
            if _hidden(p) or not p.child("at"):
                continue
            px, py = xy(p.child("at"))
            hj, vj = _justify(p.child("effects"))
            texts.append(
                _text_box(px, py, p.atoms()[1], 0, hj, vj, FONT, f"sheet {name} {p.atoms()[0]}", f"sheet:{name}")
            )
        for p in n.children("pin"):
            px, py = xy(p.child("at"))
            ang = int(float(p.child("at").atoms()[2]))
            w_ = text_width(p.atoms()[0])
            # the pin's name, inside the sheet box
            x0 = px + 0.6 if ang == 180 else px - 0.6 - w_
            texts.append(Box(x0, py - 0.75, x0 + w_, py + 0.75, f"sheet {name} pin {p.atoms()[0]}", f"sheet:{name}"))
    for n in sheet.root.children("rectangle"):
        (x0, y0), (x1, y1) = xy(n.child("start")), xy(n.child("end"))
        for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            lines.append(Line(a, b, f"frame edge ({x0:g}, {y0:g})-({x1:g}, {y1:g})", "frame"))
    for n in sheet.root.children("text"):
        x, y = xy(n.child("at"))
        eff = n.child("effects")
        size = float(eff.child("font").child("size").atoms()[1]) if eff and eff.child("font") else FONT
        hj, vj = _justify(eff)
        texts.append(_text_box(x, y, n.atoms()[0], 0, hj, vj, size, f"text '{n.atoms()[0]}'", "text"))
    return texts, bodies, lines


def _page(sheet: Sheet) -> tuple[float, float]:
    paper = sheet.root.child("paper")
    atoms = paper.atoms() if paper else ["A4"]
    w, h = PAPER[atoms[0]] if atoms[0] in PAPER else (float(atoms[1]), float(atoms[2]))
    return (h, w) if "portrait" in atoms else (w, h)


def problems(path: Path) -> list[str]:
    """What overlaps on a sheet, one line per pair, worst first."""
    sheet = Sheet.load(path)
    texts, bodies, lines = collect(sheet)
    out = []
    for i, a in enumerate(texts):
        for b in texts[i + 1 :]:
            if a.hits(b):
                out.append(f"text {a.what} overlaps text {b.what}")
        for b in bodies:
            if a.hits(b) and not (a.owner == b.owner and " pin name " in a.what):
                out.append(f"text {a.what} overlaps {b.what}")
        for ln in lines:
            if ln.owner == a.owner and ln.owner:
                continue
            if ln.crosses(a):
                out.append(f"{ln.what} crosses text {a.what}")
    for i, a in enumerate(bodies):
        for b in bodies[i + 1 :]:
            if a.hits(b):
                out.append(f"{a.what} overlaps {b.what}")
        for ln in lines:
            if ln.owner == a.owner:
                continue
            if ln.crosses(a, 0.2):
                out.append(f"{ln.what} crosses {a.what}")
    w, h = _page(sheet)
    border = Box(10, 10, w - 10, h - 10, "page border")
    title = Box(w - 120, h - 45, w - 10, h - 10, "title block")
    for it in [*texts, *bodies]:
        if it.x0 < border.x0 or it.y0 < border.y0 or it.x1 > border.x1 or it.y1 > border.y1:
            out.append(f"{it.what} runs past the page border")
        elif it.hits(title):
            out.append(f"{it.what} overlaps the title block")
    for ln in lines:
        if ln.crosses(title):
            out.append(f"{ln.what} crosses the title block")
    return out
