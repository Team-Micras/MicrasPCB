"""Draft schematic placement: `micras-pcb sch --draft` and the parts `make gen` places itself.

A sheet's placement file (`boards/<board>/schematic/<sheet>.toml`) holds hand entries; every
part or sheet symbol without one is drafted here from what `pcb apply` wrote (parts, pins, the
label or power symbol pcb attached to each pin) and KiCad's netlist, with the rules of the
`micras-pcb` skill:

- blocks: parts joined by a net of their own (a local net, or a sheet port that reaches at most
  one multi-pin part) form one block; a part on supply rails only (decoupling, bulk) joins the
  block of the nearest multi-pin part before it in the Zener source that has a pin on its supply;
  a pull on a net shared by several blocks goes to a block of shared parts; test points and
  mounting holes get blocks of their own;
- inside a block the part with the most pins anchors it, upright; every other part is placed
  next to a pin it shares a net with, wired to it, trying the positions nearest first and keeping
  the one without overlaps with the fewest crossings: two-pin parts on a rail stand up with the
  supply on top and ground at the bottom, series parts lie down, decoupling capacitors hang from
  a bus wired to the supply pin they serve;
- every pin not wired keeps pcb's label or power symbol on a short stub; a wired net gets its
  label on the wire at a pin, or its label or power symbol at a short free end;
- blocks with the same parts and connections are laid out alike, each block gets a titled frame,
  and the blocks are packed on the smallest standard paper that holds them comfortably, around
  what the hand entries place.

Hints steer the draft without touching the circuit: a module-level `SCHEMATIC_HINTS` dict in the
sheet's Zener module (pcb evaluates and ignores it), read here from the source text. See
`read_hints`.
"""

from __future__ import annotations

import ast
import itertools
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import schlint
from .paths import board_zen
from .placement import Driver, PartSpec, Placer, Spec, field_layout, power_value_at, terminal
from .schematic import DOWN, GRID, LEFT, PAPER, RIGHT, UP, Symbol, text_width

HINTS = "SCHEMATIC_HINTS"
HINT_KEYS = {"title", "paper", "blocks", "titles", "flow", "order"}
GAP = 0.0  # grid units kept between two items' boxes
BODY_GAP = 1.0  # between two parts' bodies
TEXT_GAP = 0.8  # between two texts on one line
TEXT_CLEAR = 0.3  # from a wire to another net's text
CROSSING = 40  # what a wire crossing costs a candidate position, in grid steps of wire
PAD = 2  # frame padding, grid units
TITLE_H = 3  # room for a frame's title, grid units
BLOCK_GAP = 2  # between frames
MARGIN = 10  # from the page edge to the first frame (the border is at 10 mm = 7.9 steps)
DIRS = (RIGHT, UP, LEFT, DOWN)


def _neg(d):
    return (-d[0], -d[1])


def _add(p, d, n=1):
    return (p[0] + d[0] * n, p[1] + d[1] * n)


# ---------------------------------------------------------------------------------------------
# Hints and Zener source


def sheet_module(board: str, sheet: str) -> Path | None:
    """The Zener file of a sheet: the board's root for the root sheet, else the module the root
    instantiates with `name = "<sheet>"`."""
    root = board_zen(board)
    if sheet == board or not root.exists():
        return root if root.exists() else None
    text = root.read_text()
    m = re.search(rf'(\w+)\(\s*name\s*=\s*"{re.escape(sheet)}"', text)
    if not m:
        return None
    m2 = re.search(rf'^{m.group(1)}\s*=\s*Module\(\s*"\./([^"]+)"\s*\)', text, re.M)
    return root.parent / m2.group(1) if m2 else None


def _docstring(text: str) -> tuple[str, int]:
    m = re.match(r'\s*"""(.*?)"""', text, re.S)
    return (m.group(1), m.end()) if m else ("", 0)


def read_hints(zen: Path | None) -> dict:
    """The module's `SCHEMATIC_HINTS = {...}`: a literal dict at the top level of the module.
    pcb evaluates it as an unused value (no effect on the netlist, BOM or layout); this reads
    it from the text. Keys:

    - "title": the sheet's title block (default: the module docstring's first sentence);
    - "paper": the paper size (default: the smallest that holds the sheet comfortably);
    - "blocks": [{"parts": [refs], "title": "...", "anchor": ref}]: blocks given by hand, in
      reading order; the other parts join them by connectivity;
    - "titles": {ref: title}: the title of the block holding that part;
    - "flow": {ref: "left" | "right" | "above" | "below"}: where a part goes from its block's
      anchor;
    - "order": [refs]: blocks in this order on the page (by any part they hold), the rest after.
    """
    if zen is None or not zen.exists():
        return {}
    text = zen.read_text()
    m = re.search(rf"^{HINTS}\s*=\s*", text, re.M)
    if not m:
        return {}
    depth, i = 0, m.end()
    for j in range(m.end(), len(text)):
        c = text[j]
        if c in "[{(":
            depth += 1
        elif c in "]})":
            depth -= 1
            if depth == 0:
                i = j + 1
                break
    src = re.sub(r"#[^\n]*", "", text[m.end() : i])
    try:
        hints = ast.literal_eval(src)
    except (ValueError, SyntaxError) as e:
        raise ValueError(f"{zen.name}: {HINTS} must be a literal dict ({e})") from e
    if not isinstance(hints, dict) or set(hints) - HINT_KEYS:
        raise ValueError(f"{zen.name}: {HINTS} keys are {sorted(HINT_KEYS)}")
    return hints


def hint_refs(hints: dict) -> set[str]:
    """Every part a sheet's hints name."""
    refs = set(hints.get("titles", {})) | set(hints.get("flow", {})) | set(hints.get("order", []))
    for b in hints.get("blocks", []):
        refs |= set(b.get("parts", []))
        if b.get("anchor"):
            refs.add(b["anchor"])
    return refs


def hint_problems(hints: dict, refs: set[str]) -> list[str]:
    """What is wrong with a sheet's hints: parts the sheet does not have, unknown values."""
    out = []
    if stale := sorted(hint_refs(hints) - refs):
        out.append(f"{HINTS} names parts the sheet does not have: {', '.join(stale)}")
    for ref, side in hints.get("flow", {}).items():
        if side not in ("left", "right", "above", "below"):
            out.append(f"{HINTS} flow of {ref}: {side!r} is not left, right, above or below")
    if hints.get("paper") and hints["paper"] not in PAPERS:
        out.append(f"{HINTS} paper {hints['paper']!r} is not one of {', '.join(PAPERS)}")
    return out


def module_title(zen: Path | None) -> str:
    """The module docstring's first sentence, as a sheet title."""
    if zen is None or not zen.exists():
        return ""
    doc, _ = _docstring(zen.read_text())
    para = " ".join(doc.strip().split("\n\n")[0].split())
    m = re.match(r"(.+?[.:])(\s|$)", para)
    s = (m.group(1) if m else para).rstrip(".:")
    if text_width(s, 2.0) <= 95:  # the title block's title field
        return s
    words = s.split(" ")
    while len(words) > 1 and text_width(" ".join(words) + " ...", 2.0) > 95:
        words.pop()
    return " ".join(words).rstrip(",;:") + " ..."


def source_ranks(zen: Path | None, refs: list[str]) -> dict[str, int]:
    """Each part's position in the module source (where its quoted name first appears after
    the docstring), for ordering blocks and assigning decoupling; parts not found follow."""
    text = zen.read_text() if zen and zen.exists() else ""
    _, start = _docstring(text)
    body = re.sub(r"#[^\n]*", lambda m: " " * len(m.group(0)), text[start:])
    out = {}
    for ref in refs:
        i = body.find(f'"{ref}"')
        out[ref] = i if i >= 0 else len(body) + _refnum(ref)
    return out


def _refnum(ref: str) -> int:
    m = re.match(r"([A-Za-z#_]*)(\d*)", ref)
    return int(m.group(2) or 0) if m else 0


# ---------------------------------------------------------------------------------------------
# The sheet as pcb wrote it


@dataclass
class Site:
    """A connection point of a placed part: one pin, or several stacked at one point."""

    ref: str
    pids: list[str]
    loc: tuple[int, int]  # relative to the part's anchor until placed
    out: tuple[int, int]

    @property
    def rep(self) -> str:
        return min(self.pids)


@dataclass
class Shape:
    sym: Symbol
    sites: list[Site]
    box: tuple[float, float, float, float]  # body, pin lines and pin names; grid units


class Model:
    """A generated sheet: parts, their nets and what pcb attached to each pin."""

    def __init__(self, board: str, path: Path, text: str, pin_net: dict[str, str]):
        self.board, self.path = board, path
        self.placer = Placer(board, path, text, Spec(), pin_net)
        self.sheet = self.placer.sheet
        self.parts = {s.ref: s for s in self.sheet.parts()}
        self.net: dict[str, str | None] = {}
        for s in self.parts.values():
            for p in s.pins():
                n = pin_net.get(p.id)
                self.net[p.id] = None if n is None or n.startswith("unconnected-") else n
        self.rail: dict[str, str] = {}  # net -> "supply" | "ground"
        self.port: set[str] = set()  # nets with a global or hierarchical label
        for pid, drivers in self.placer.pin_drivers.items():
            n = self.net.get(pid)
            for d in drivers:
                if d.kind == "power":
                    self.rail[n] = "ground" if d.extra == "GND" else "supply"
                elif d.kind in ("global_label", "hierarchical_label"):
                    self.port.add(n)
        self.pins_of = {ref: s.pins() for ref, s in self.parts.items()}
        self._shapes: dict = {}
        self._fields: dict = {}
        self._terms: dict = {}

    def nets_of(self, ref: str) -> list[str]:
        return [n for p in self.pins_of[ref] if (n := self.net.get(p.id))]

    def kind(self, ref: str) -> str:
        pins = self.pins_of[ref]
        if not self.nets_of(ref):
            return "none"
        if len(pins) == 1:
            return "one"
        return "two" if len(pins) == 2 else "multi"

    def role(self, ref: str) -> str:
        """A two-pin part's role: decap (supply to ground), shunt_gnd, shunt_sup, series."""
        kinds = [self.rail.get(self.net.get(p.id)) for p in self.pins_of[ref]]
        if "ground" in kinds and "supply" in kinds:
            return "decap"
        if "ground" in kinds:
            return "shunt_gnd"
        if "supply" in kinds and None in kinds:
            # an inductor, bead or diode from a supply carries it on: in series, lying down
            return "series" if re.match(r"(L|FB|D)\d", ref) else "shunt_sup"
        return "series"

    def drivers(self, pid: str) -> list[Driver]:
        return self.placer.pin_drivers.get(pid, [])

    def wired_drivers(self, pids: list[str]) -> list[Driver]:
        """The labels and power symbols of pins wired together, with those of the pins tied to
        them inside their parts (jumper pin groups), as placement._drivers_of_group finds them."""
        seen, out = set(), []
        for pid in pids:
            ref, num = pid.rsplit(".", 1)
            group = next((g for g in self.parts[ref].lib.jumpers if num in g), {num})
            for q in sorted(group):
                for d in self.drivers(f"{ref}.{q}"):
                    if (d.kind, d.text, d.extra) not in seen:
                        seen.add((d.kind, d.text, d.extra))
                        out.append(d)
        return sorted(out, key=lambda d: (d.rank, d.kind, d.text))

    def shape(self, ref: str, rot: int, mirror: str | None) -> Shape:
        k = (ref, rot, mirror)
        if k not in self._shapes:
            s0 = self.parts[ref]
            s = Symbol(s0.node, s0.lib, (0.0, 0.0), rot, mirror)
            by_loc: dict = {}
            for p in s.pins():
                loc = (round(p.at[0] / GRID), round(p.at[1] / GRID))
                by_loc.setdefault(loc, []).append(p)
            sites = [Site(ref, sorted(p.id for p in ps), loc, ps[0].out) for loc, ps in sorted(by_loc.items())]
            boxes = []
            b = s.body()
            if b:
                boxes.append(b)
            for p in s.pins():
                lp = next(lp for lp in s.lib.pins if lp.number == p.number)
                end = (p.at[0] - p.out[0] * lp.length, p.at[1] - p.out[1] * lp.length)
                boxes.append((min(p.at[0], end[0]), min(p.at[1], end[1]), max(p.at[0], end[0]), max(p.at[1], end[1])))
            boxes += [(nb.x0, nb.y0, nb.x1, nb.y1) for nb in schlint.pin_names(s)]
            box = (
                min(b[0] for b in boxes) / GRID,
                min(b[1] for b in boxes) / GRID,
                max(b[2] for b in boxes) / GRID,
                max(b[3] for b in boxes) / GRID,
            )
            self._shapes[k] = Shape(s, sites, box)
        return self._shapes[k]

    def field_boxes(self, ref: str, rot: int, mirror: str | None, side) -> list[tuple]:
        k = (ref, rot, mirror, side)
        if k not in self._fields:
            self._fields[k] = self._field_boxes(ref, rot, mirror, side)
        return self._fields[k]

    def _field_boxes(self, ref: str, rot: int, mirror: str | None, side) -> list[tuple]:
        s0 = self.parts[ref]
        s = Symbol(s0.node, s0.lib, (0.0, 0.0), rot, mirror)
        out = []
        for name, ((x, y), j) in field_layout(s, PartSpec((0.0, 0.0), rot, mirror, side)).items():
            prop = next(p for p in s0.node.children("property") if p.atoms()[0] == name)
            eff = prop.child("effects")
            size = float(eff.child("font").child("size").atoms()[1]) if eff and eff.child("font") else 1.27
            b = schlint._text_box(x, y, s0.node.prop(name) or "", 0, j, "center", size)
            out.append((b.x0 / GRID, b.y0 / GRID, b.x1 / GRID, b.y1 / GRID, "text", None))
        return out

    def term_items(self, at, out, first: Driver, opts: dict, gid) -> Items:
        """The stub, and the label's or power symbol's box, drawn for a driver at a point."""
        k = (first.kind, first.text, first.extra, out, tuple(sorted(opts.items())))
        if k not in self._terms:
            self._terms[k] = self._term_items((0, 0), out, first, opts, None)
        r = self._terms[k]
        dx, dy = at
        return Items(
            [(b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy, b[4], gid) for b in r.boxes],
            [((a[0] + dx, a[1] + dy), (b[0] + dx, b[1] + dy), gid) for a, b, _ in r.segs],
            [((p[0] + dx, p[1] + dy), ("end", (p[0] + dx, p[1] + dy), gid)) for p, _ in r.pts],
        )

    def _term_items(self, at, out, first: Driver, opts: dict, gid) -> Items:
        it = Items()
        at_mm = (at[0] * GRID, at[1] * GRID)
        wire, (kind, end, ang) = terminal(at_mm, out, first, opts)
        e = (round(end[0] / GRID, 4), round(end[1] / GRID, 4))
        if wire:
            it.segs.append((tuple(at), e, gid))
        it.pts.append((e, ("end", e, gid)))  # a label's anchor or a free end: nothing else may touch it
        if kind == "label":
            tmpl = self.placer.label_template.get((first.kind, first.text, first.extra))
            size = 1.27
            if tmpl is not None and tmpl.child("effects") and tmpl.child("effects").child("font"):
                size = float(tmpl.child("effects").child("font").child("size").atoms()[1])
            b = schlint.label_box(first.kind, first.text, end, ang, size)
            it.boxes.append((b.x0 / GRID, b.y0 / GRID, b.x1 / GRID, b.y1 / GRID, "text", gid))
        else:
            tmpl = self.placer.power_template[(first.extra, first.text)]
            lib = self.sheet.libs[first.extra]
            sym = Symbol(tmpl, lib, end, ang, None)
            b = sym.body()
            if b:
                it.boxes.append((b[0] / GRID, b[1] / GRID, b[2] / GRID, b[3] / GRID, "text", gid))
            (vx, vy), _, j = power_value_at(sym, first.extra)
            t = schlint._text_box(vx, vy, first.text, 0, j, "center", 1.27)
            it.boxes.append((t.x0 / GRID, t.y0 / GRID, t.x1 / GRID, t.y1 / GRID, "text", gid))
        return it


# ---------------------------------------------------------------------------------------------
# Collision model


@dataclass
class Items:
    boxes: list = field(default_factory=list)  # (x0, y0, x1, y1)
    segs: list = field(default_factory=list)  # (a, b, gid), axis-aligned
    pts: list = field(default_factory=list)  # (p, gid): pin ends, wire ends, label anchors

    def shifted(self, d) -> Items:
        dx, dy = d
        return Items(
            [(b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy, *b[4:]) for b in self.boxes],
            [((a[0] + dx, a[1] + dy), (b[0] + dx, b[1] + dy), g) for a, b, g in self.segs],
            [((p[0] + dx, p[1] + dy), g) for p, g in self.pts],
        )


def _on(p, a, b, eps=1e-6) -> bool:
    if abs(a[0] - b[0]) < eps:
        return abs(p[0] - a[0]) < eps and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps
    if abs(a[1] - b[1]) < eps:
        return abs(p[1] - a[1]) < eps and min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps
    return False


def _seg_box(a, b, box, m=0.05) -> bool:
    """The axis-aligned segment enters the box's interior (shrunk by m)."""
    x0, y0, x1, y1 = box[0] + m, box[1] + m, box[2] - m, box[3] - m
    if x0 >= x1 or y0 >= y1:
        return False
    if abs(a[1] - b[1]) < 1e-9:  # horizontal
        return y0 < a[1] < y1 and min(a[0], b[0]) < x1 and max(a[0], b[0]) > x0
    return x0 < a[0] < x1 and min(a[1], b[1]) < y1 and max(a[1], b[1]) > y0


def _seg_seg(a, b, c, d) -> str:
    """'touch' (share a point or overlap), 'cross' (a proper crossing) or ''."""
    if _on(a, c, d) or _on(b, c, d) or _on(c, a, b) or _on(d, a, b):
        return "touch"
    h1, h2 = abs(a[1] - b[1]) < 1e-9, abs(c[1] - d[1]) < 1e-9
    if h1 == h2:
        return ""
    if h1:
        if min(a[0], b[0]) < c[0] < max(a[0], b[0]) and min(c[1], d[1]) < a[1] < max(c[1], d[1]):
            return "cross"
    elif min(c[0], d[0]) < a[0] < max(c[0], d[0]) and min(a[1], b[1]) < c[1] < max(a[1], b[1]):
        return "cross"
    return ""


def _items_bbox(it: Items):
    xs0 = [b[0] for b in it.boxes] + [min(a[0], b[0]) for a, b, _ in it.segs] + [p[0] for p, _ in it.pts]
    if not xs0:
        return None
    ys0 = [b[1] for b in it.boxes] + [min(a[1], b[1]) for a, b, _ in it.segs] + [p[1] for p, _ in it.pts]
    xs1 = [b[2] for b in it.boxes] + [max(a[0], b[0]) for a, b, _ in it.segs] + [p[0] for p, _ in it.pts]
    ys1 = [b[3] for b in it.boxes] + [max(a[1], b[1]) for a, b, _ in it.segs] + [p[1] for p, _ in it.pts]
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def _hits(p, q, gap=GAP, gy=None) -> bool:
    gy = gap if gy is None else gy
    return p[0] < q[2] + gap and q[0] < p[2] + gap and p[1] < q[3] + gy and q[1] < p[3] + gy


def _box_gap(a, b) -> tuple[float, float]:
    """The room kept between two boxes (x, y): bodies apart, texts a word space apart along a
    line, label rows at a pin pitch."""
    if a[4] == b[4] == "body":
        return BODY_GAP, BODY_GAP
    if a[4] == b[4] == "text":
        return TEXT_GAP, GAP
    return GAP, GAP


class Canvas:
    """What a block holds so far, by owner tag, with the electrical group of each wire and point
    (union-find, so groups merge as wires join them)."""

    def __init__(self):
        self.layers: dict = {}  # tag -> Items
        self.parent: dict = {}
        self.boxes_of: dict = {}  # tag -> bounding box of its items

    def find(self, g):
        while self.parent.setdefault(g, g) != g:
            self.parent[g] = self.parent[self.parent[g]]
            g = self.parent[g]
        return g

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra
        return ra

    def add(self, tag, items: Items):
        self.layers.setdefault(tag, Items())
        lay = self.layers[tag]
        lay.boxes += items.boxes
        lay.segs += items.segs
        lay.pts += items.pts
        self.boxes_of.pop(tag, None)

    def remove(self, tag):
        self.layers.pop(tag, None)
        self.boxes_of.pop(tag, None)

    def _near(self, tag, lay: Items, bb) -> bool:
        if tag not in self.boxes_of:
            self.boxes_of[tag] = _items_bbox(lay)
        lb = self.boxes_of[tag]
        return lb is not None and _hits(bb, lb, 2.0)

    def conflicts(self, items: Items, allowed=(), ignore=(), extra: list | None = None) -> int | None:
        """None if the items collide with what is there (or with `extra`, items not yet added),
        else the number of wire crossings. `allowed`: groups the new wires may touch."""
        ok = {self.find(g) for g in allowed}
        bb = _items_bbox(items)
        if bb is None:
            return 0
        layers = [it for tag, it in self.layers.items() if tag not in ignore and self._near(tag, it, bb)]
        layers += [it for it in extra or [] if (eb := _items_bbox(it)) is not None and _hits(bb, eb, 2.0)]
        crossings = 0
        for nb in items.boxes:
            for lay in layers:
                for b in lay.boxes:
                    if _hits(nb, b, *_box_gap(nb, b)):
                        return None
                for a, b, h in lay.segs:
                    if _seg_box(a, b, nb, self._clear(nb, h, ok)):
                        return None
        for a, b, g in items.segs:
            mine = {self.find(g)} | ok
            for lay in layers:
                for bx in lay.boxes:
                    if _seg_box(a, b, bx, self._clear(bx, g, ok)):
                        return None
                for c, d, h in lay.segs:
                    r = _seg_seg(a, b, c, d)
                    if r == "cross":  # unconnected where they cross, whatever their nets
                        crossings += 1
                    elif r and self.find(h) not in mine:
                        return None
                for p, h in lay.pts:
                    if self.find(h) not in mine and _on(p, a, b):
                        return None
        for p, g in items.pts:
            mine = {self.find(g)} | ok
            for lay in layers:
                for c, d, h in lay.segs:
                    if self.find(h) not in mine and _on(p, c, d):
                        return None
                for q, h in lay.pts:
                    if self.find(h) not in mine and abs(p[0] - q[0]) < 1e-6 and abs(p[1] - q[1]) < 1e-6:
                        return None
        return crossings

    def _clear(self, box, g, ok) -> float:
        """How far a wire of group g keeps from a box: clear of another net's texts, touching
        allowed for bodies (wires end at pins on their edge) and the net's own label."""
        if box[4] != "text" or box[5] is None:
            return -TEXT_CLEAR if box[4] == "text" else 0.05
        own = self.find(box[5])
        return 0.05 if own == self.find(g) or own in ok else -TEXT_CLEAR

    def bbox(self) -> tuple[float, float, float, float]:
        xs0, ys0, xs1, ys1 = [], [], [], []
        for lay in self.layers.values():
            for b in lay.boxes:
                xs0.append(b[0])
                ys0.append(b[1])
                xs1.append(b[2])
                ys1.append(b[3])
            for a, b, _ in lay.segs:
                xs0.append(min(a[0], b[0]))
                xs1.append(max(a[0], b[0]))
                ys0.append(min(a[1], b[1]))
                ys1.append(max(a[1], b[1]))
        if not xs0:
            return (0, 0, 0, 0)
        return min(xs0), min(ys0), max(xs1), max(ys1)


# ---------------------------------------------------------------------------------------------
# One block


@dataclass
class Placed:
    at: tuple[int, int]
    rot: int
    mirror: str | None
    fields: str | None
    shape: Shape


@dataclass
class Group:
    sites: list[str]  # site keys
    chains: list[list]  # tokens: site key or point
    term: tuple | None = None  # ("onwire", site key) | ("branch", start, end) | None


class Block:
    """Parts drafted into one titled frame, in grid units relative to the anchor."""

    def __init__(self, model: Model, refs: list[str], anchor: str, title: str, hints: dict, ranks: dict):
        self.m, self.refs, self.anchor, self.title = model, refs, anchor, title
        self.hints, self.ranks = hints, ranks
        self.cv = Canvas()
        self.placed: dict[str, Placed] = {}
        self.sites: dict[str, Site] = {}  # key "REF@x,y" -> site, absolute
        self.site_of: dict[str, str] = {}  # pid -> site key
        self.groups: dict[str, Group] = {}  # group root -> wired group
        self.stub_opts: dict[str, dict] = {}  # site rep pid -> terminal options (non-default)
        self.prefer: dict = {}  # ref -> (rot, mirror, at, conn) of the same part in an identical block
        self.deferred: list[str] = []  # sites placed without room for their label yet
        self.extra_log: list = []  # (site, site, corners) of the wires extra_wires drew
        self.like: tuple | None = None  # (block, ref map) of an identical block laid out before

    # --- sites and groups

    def gid(self, sk: str):
        return self.cv.find(("site", sk))

    def wired(self, sk: str) -> bool:
        return self.gid(sk) in self.groups

    def net(self, sk: str) -> str | None:
        return self.m.net.get(self.sites[sk].pids[0])

    def group_drivers(self, sks: list[str], sitemap: dict | None = None) -> list[Driver]:
        """A wired net's labels and power symbols, as placement._drivers_of_group gathers them."""
        sitemap = sitemap or self.sites
        return self.m.wired_drivers([pid for sk in sks for pid in sitemap[sk].pids])

    def _site_term(self, site: Site, opts: dict, gid) -> Items | None:
        """A lone site's own terminal: pcb's label or power symbol on a stub; None draws nothing
        (no-connect flag, or nothing attached)."""
        pid = site.rep
        if pid in self.m.placer.pin_nc:
            return Items(pts=[(site.loc, gid)])
        drivers = self.m.drivers(pid)
        if not drivers:
            return None
        return self.m.term_items(site.loc, site.out, drivers[0], opts, gid)

    def _assign_terms(self, todo, ignore, pending, defer, budget=400):
        """Each site's label or power symbol: the first variant that fits, going back to the
        previous site's next variant when one has none (a few hundred tries at most).
        Returns (terms, deferred, crossings) or None."""
        variants = [self._term_variants(s) for _, s in todo]
        choice = [0] * len(todo)
        items: list = [None] * len(todo)
        cross = [0] * len(todo)
        i, tries = 0, 0
        deferred: list[str] = []
        while i < len(todo):
            sk, s = todo[i]
            placed = False
            while choice[i] < len(variants[i]) and tries < budget:
                opts = variants[i][choice[i]]
                ti = self._site_term(s, opts, ("site", sk))
                tries += 1
                if ti is None:
                    items[i], placed = None, True
                    break
                extra = pending + [x for x in items[:i] if x is not None]
                c = self.cv.conflicts(ti, allowed=[("site", sk)], ignore=ignore, extra=extra)
                if c == 0:
                    items[i], cross[i], placed = ti, c, True
                    break
                choice[i] += 1
            if placed:
                i += 1
                continue
            back = i - 1
            while back >= 0 and choice[back] + 1 >= len(variants[back]):
                back -= 1
            if back >= 0 and tries < budget:
                choice[back] += 1
                for j in range(back + 1, len(todo)):
                    choice[j], items[j] = 0, None
                i = back
                continue
            if not defer:
                return None
            # leave this one for later, keep the others as they were first found
            deferred.append(sk)
            variants[i] = []
            items[i] = None
            i += 1
        terms = {}
        for k, (sk, _) in enumerate(todo):
            if sk in deferred:
                continue
            terms[sk] = (variants[k][choice[k]] if choice[k] < len(variants[k]) else {}, items[k])
        return terms, deferred, sum(cross)

    def _blockers(self, items: Items | None, sk: str) -> list:
        if items is None:
            return []
        out = []
        for tag in self.cv.layers:
            if self.cv.conflicts(items, allowed=[("site", sk)], ignore=set(self.cv.layers) - {tag}) is None:
                out.append(tag)
        return out

    def _term_variants(self, site: Site) -> list[dict]:
        drivers = self.m.drivers(site.rep)
        if not drivers or site.rep in self.m.placer.pin_nc:
            return [{}]
        if drivers[0].kind == "power":
            natural = DOWN if drivers[0].extra == "GND" else UP
            if site.out == natural:
                return [{}, {"len": 2}, {"len": 4}]
            # beside other pins: pointing out along the pin takes no room from its neighbours
            return [{"point": "out"}, {}, {"len": 4, "point": "out"}, {"len": 4}, {"len": 6}]
        if site.out in (UP, DOWN):  # a label reads across the page, at the stub's end
            return [
                {"label": "right"},
                {"label": "left"},
                {"len": 4, "label": "right"},
                {"len": 4, "label": "left"},
                {"len": 6, "label": "right"},
                {"len": 6, "label": "left"},
                {},
                {"len": 4},
            ]
        return [{}, {"len": 4}, {"len": 6}, {"len": 8}, {"len": 10}]

    # --- placing a part

    def _runs(self, ref: str, sites: list[Site]) -> list[list[Site]]:
        """Sites of a multi-pin part on one net, side by side on one edge with no other pin
        between them: wired together by a short bus, with one label or power symbol."""
        if self.m.kind(ref) != "multi":
            return []
        out = []
        for d in DIRS:
            side = sorted(
                (s for s in sites if s.out == d), key=lambda s: (s.loc[1], s.loc[0]) if d[0] else (s.loc[0], s.loc[1])
            )
            run: list[Site] = []
            for s in [*side, None]:
                n = self.m.net.get(s.rep) if s else None
                if run and s and n and n == self.m.net.get(run[0].rep) and s.rep not in self.m.placer.pin_nc:
                    run.append(s)
                    continue
                if len(run) > 1 and self.m.drivers(run[0].rep):
                    out.append(run)
                run = [s] if s and n and s.rep not in self.m.placer.pin_nc else []
        return out

    def orientations(self, ref: str) -> list[tuple[int, str | None]]:
        kind = self.m.kind(ref)
        n = len(self.m.pins_of[ref])
        if kind == "two":
            role = self.m.role(ref)
            out = []
            for rot in (0, 90, 180, 270):
                sh = self.m.shape(ref, rot, None)
                outs = {s.out for s in sh.sites}
                vertical = outs <= {UP, DOWN}
                rails = {s.out: self.m.rail.get(self.m.net.get(s.rep)) for s in sh.sites}
                if role == "series" and vertical:
                    continue
                if role != "series" and not vertical:
                    continue
                if role in ("decap", "shunt_sup") and rails.get(UP) != "supply":
                    continue
                if role in ("decap", "shunt_gnd") and rails.get(DOWN) != "ground":
                    continue
                out.append((rot, None))
            return out or [(0, None)]
        if n > 8:
            return [(0, None)]
        return [(r, m) for m in (None, "x") for r in (0, 90, 180, 270)]

    def part_items(self, ref: str, at, rot, mirror) -> tuple[Items, list[Site]]:
        sh = self.m.shape(ref, rot, mirror)
        it = Items(boxes=[(sh.box[0] + at[0], sh.box[1] + at[1], sh.box[2] + at[0], sh.box[3] + at[1], "body", None)])
        sites = []
        for s in sh.sites:
            loc = (s.loc[0] + at[0], s.loc[1] + at[1])
            site = Site(ref, s.pids, loc, s.out)
            sites.append(site)
            it.pts.append((loc, ("site", f"{ref}@{loc[0]},{loc[1]}")))
        return it, sites

    def field_sides(self, ref: str, rot: int, mirror) -> list:
        if self.m.kind(ref) == "two":
            outs = {s.out for s in self.m.shape(ref, rot, mirror).sites}
            return ["right", "left"] if outs <= {UP, DOWN} else ["top", "bottom"]
        return [None, "top-left", "top-right", "bottom-left", "bottom-right", "right", "left"]

    def try_place(self, ref, at, rot, mirror, conn=None, defer=False):
        """Try the part at `at`; conn = (host site key, the part's site location relative to its
        anchor... as placed, path corners) wires that site to the placed host. Returns
        (crossings, plan) or None when anything collides."""
        it, sites = self.part_items(ref, at, rot, mirror)
        # the host pin's own label gives way to the wire; so do the labels of placed pins this
        # part's pins face in line on their net (a bus to a connector), wired straight
        links = self._links(ref, sites, conn)
        ignore: set = {("pterm", conn[0]), ("dterm", conn[0])} if conn else set()
        ignore |= {(t, hk) for hk, _ in links for t in ("pterm", "dterm")}
        if self.cv.conflicts(it, ignore=ignore) is None:
            self.fail = "body"
            return None
        pending: list[Items] = [it]
        cross = 0
        plan = {"ref": ref, "at": at, "rot": rot, "mirror": mirror, "sites": sites, "part": it}
        segs: list = []
        if conn:
            hk, qloc, path = conn
            qk = f"{ref}@{qloc[0]},{qloc[1]}"
            g = ("site", hk)
            pts = [self.sites[hk].loc, *path, qloc]
            segs = [(a, b) for a, b in itertools.pairwise(pts) if a != b]
            wi = Items(segs=[(a, b, g) for a, b in segs])
            c = self.cv.conflicts(wi, allowed=[g, ("site", qk)], ignore=ignore, extra=pending)
            if c is None:
                self.fail = "wire"
                return None
            cross += c
            pending.append(wi)
            plan["conn"] = (hk, qk, path)
        for hk, sk in links:
            wl = Items(segs=[(self.sites[hk].loc, next(s.loc for s in sites if _key(s) == sk), ("site", hk))])
            if self.cv.conflicts(wl, allowed=[("site", hk), ("site", sk)], ignore=ignore, extra=pending) != 0:
                self.fail = "bus"
                return None
            pending.append(wl)
        plan["links"] = links
        for side in self.field_sides(ref, rot, mirror):
            fb = Items(boxes=[_shift(b, at) for b in self.m.field_boxes(ref, rot, mirror, side)])
            if self.cv.conflicts(fb, ignore=ignore, extra=pending[1:]) is not None:
                plan["fields"] = side
                pending.append(fb)
                break
        else:
            self.fail = "fields"
            return None
        joins, joined = [], set()
        for run in self._runs(ref, sites):
            keys = [f"{ref}@{s.loc[0]},{s.loc[1]}" for s in run]
            out = run[0].out
            bus = [_add(s.loc, out) for s in run]
            chains = [[keys[0], bus[0], bus[-1], keys[-1]]] + [
                [k, b] for k, b in zip(keys[1:-1], bus[1:-1], strict=True)
            ]
            g = ("site", keys[0])
            segs = [(run[0].loc, bus[0]), (bus[0], bus[-1]), (bus[-1], run[-1].loc)]
            segs += [(s.loc, b) for s, b in zip(run[1:-1], bus[1:-1], strict=True)]
            wi = Items(segs=[(a, b, g) for a, b in segs if a != b], pts=[(b, g) for b in bus])
            allowed = [("site", k) for k in keys]
            if conn and plan["conn"][1] in keys:
                allowed.append(("site", plan["conn"][0]))
            c = self.cv.conflicts(wi, allowed=allowed, ignore=ignore, extra=pending)
            if c is None:
                continue
            sitemap = dict(zip(keys, run, strict=True))
            gt = self.group_term(
                keys, sitemap, [run[0].loc, bus[0], bus[-1], run[-1].loc], g, ignore, [*pending, wi], allowed, out
            )
            if gt is None:
                continue
            cross += c
            pending += [wi, gt[1]]
            joins.append((keys, chains, wi, gt))
            joined |= set(keys)
        plan["joins"] = joins
        linked = {sk for _, sk in links}
        todo = [
            (_key(s), s)
            for s in sites
            if not ((conn and _key(s) == plan["conn"][1]) or _key(s) in joined or _key(s) in linked)
        ]
        res = self._assign_terms(todo, ignore, pending, defer)
        if res is None:
            self.fail = "labels"
            return None
        terms, deferred, c = res
        cross += c
        pending += [ti for _, ti in terms.values() if ti is not None]
        plan["terms"] = terms
        plan["deferred"] = deferred
        if conn and not self.wired(plan["conn"][0]):
            hk, qk, path = plan["conn"]
            sitemap = {hk: self.sites[hk], qk: next(s for s in sites if s.loc == conn[1])}
            gt = self.group_term(
                [hk, qk],
                sitemap,
                [self.sites[hk].loc, *path, conn[1]],
                ("site", hk),
                ignore,
                pending,
                None,
                self.sites[hk].out,
            )
            if gt is None:
                self.fail = "net label"
                return None
            plan["gterm"] = gt
            pending.append(gt[1])
        plan["link_terms"] = {}
        for hk, sk in links:
            if self.wired(hk):
                continue
            s = next(s for s in sites if _key(s) == sk)
            gt = self.group_term(
                [hk, sk], {hk: self.sites[hk], sk: s}, [self.sites[hk].loc, s.loc], ("site", hk), ignore, pending
            )
            if gt is None:
                self.fail = "bus label"
                return None
            plan["link_terms"][hk] = gt
            pending.append(gt[1])
        return cross, plan

    def group_term(self, sks, sitemap, path, gid, ignore, pending, allowed=None, outward=None):
        """Where a newly wired net's label or power symbol goes: on the wire at a pin (a local
        label), else at a short free end branching off the new wire. Returns (term, items),
        (None, empty) when pcb attached nothing, or None when nothing fits."""
        drivers = self.group_drivers(sks, sitemap)
        if not drivers:
            return (None, Items())
        first = drivers[0]
        segs = [(a, b) for a, b in itertools.pairwise(path) if a != b]
        if first.kind == "label":
            for sk in sks:
                s = sitemap[sk]
                if s.out in (UP, DOWN):
                    continue
                q = _add(s.loc, s.out)
                at = q if any(_on(q, a, b) for a, b in segs) else s.loc
                it = self.m.term_items(at, s.out, first, {"len": 0}, gid)
                it.pts = [(at, gid)]  # on the net's own wire: no other net may touch it
                if self.cv.conflicts(it, allowed=allowed or [gid], ignore=ignore, extra=pending) == 0:
                    return (("onwire", sk), it)
        if first.kind == "power":
            natural = DOWN if first.extra == "GND" else UP
            dirs, lengths = [(natural, {}), (LEFT, {}), (RIGHT, {})], (1, 2, 3, 4, 6)
            if outward and outward != natural:  # pins side by side: point away from them
                dirs.insert(0, (outward, {"point": "out"}))
        else:
            dirs = [(LEFT, {}), (RIGHT, {}), (UP, {"label": "right"}), (DOWN, {"label": "right"})]
            dirs += [(UP, {"label": "left"}), (DOWN, {"label": "left"})]
            if outward in (LEFT, RIGHT):
                dirs.remove((outward, {}))
                dirs.insert(0, (outward, {}))
            lengths = (2, 3, 4, 6)
        pins = {sitemap[sk].loc for sk in sks}
        starts: list = []
        for a, b in segs:
            n = round(abs(a[0] - b[0]) + abs(a[1] - b[1]))
            for i in range(n + 1):
                p = (round(a[0] + (b[0] - a[0]) * i / n), round(a[1] + (b[1] - a[1]) * i / n))
                if p not in pins and p not in starts:
                    starts.append(p)
        for L in lengths:
            for d, opts in dirs:
                for p in starts:
                    e = _add(p, d, L)
                    # the branch runs on no wire of the net, and its end touches none
                    half = (p[0] + d[0] * 0.5, p[1] + d[1] * 0.5)
                    if any(_on(e, a, b) or _on(half, a, b) for a, b in segs):
                        continue
                    it = self.m.term_items(e, d, first, {"len": 0, **opts}, gid)
                    it.segs.append((p, e, gid))
                    if self.cv.conflicts(it, allowed=allowed or [gid], ignore=ignore, extra=pending) == 0:
                        return (("branch", p, e, opts), it)
        return None

    def commit(self, plan):
        ref = plan["ref"]
        sh = self.m.shape(ref, plan["rot"], plan["mirror"])
        self.placed[ref] = Placed(plan["at"], plan["rot"], plan["mirror"], plan.get("fields"), sh)
        for s in plan["sites"]:
            sk = f"{ref}@{s.loc[0]},{s.loc[1]}"
            self.sites[sk] = s
            for pid in s.pids:
                self.site_of[pid] = sk
        self.cv.add(("part", ref), plan["part"])
        fb = Items(
            boxes=[
                _shift(b, plan["at"]) for b in self.m.field_boxes(ref, plan["rot"], plan["mirror"], plan.get("fields"))
            ]
        )
        self.cv.add(("part", ref), fb)
        for sk, (opts, ti) in plan["terms"].items():
            if opts:
                self.stub_opts[self.sites[sk].rep] = opts
            if ti is not None:
                self.cv.add(("pterm", sk), ti)
        for sk in plan.get("deferred", []):  # keep the room a default label takes
            self.deferred.append(sk)
            ti = self._site_term(self.sites[sk], {}, ("site", sk))
            if ti is not None:
                self.cv.add(("dterm", sk), ti)
        for keys, chains, wi, gt in plan.get("joins", []):
            root = ("site", keys[0])
            for k in keys[1:]:
                root = self.cv.union(root, ("site", k))
            self.cv.add(("wire", root), wi)
            if gt[0]:
                self.cv.add(("gterm", root), gt[1])
            self.groups[root] = Group(list(keys), chains, gt[0])
        if "conn" in plan:
            hk, qk, path = plan["conn"]
            self._join(hk, qk, path, plan.get("gterm"))
        for hk, sk in plan.get("links", []):
            self._join(hk, sk, [], plan["link_terms"].get(hk))

    def _join(self, hk, qk, path, gterm, replace=False):
        """Record a wire from site hk to site qk (through path points) and merge their groups
        (replace: the new net terminal `gterm` replaces both groups' own)."""
        ga, gb = self.gid(hk), self.gid(qk)
        A, B = self.groups.pop(ga, None), self.groups.pop(gb, None)
        if replace:
            for g, G in ((ga, A), (gb, B)):
                self.cv.remove(("gterm", g))
                if G:
                    G.term = None
        root = self.cv.union(("site", hk), ("site", qk))
        for sk in (hk, qk):
            self.cv.remove(("pterm", sk))
            self.cv.remove(("dterm", sk))
            self.stub_opts.pop(self.sites[sk].rep, None)
        pts = [self.sites[hk].loc, *path, self.sites[qk].loc]
        self.cv.add(
            ("wire", root),
            Items(segs=[(a, b, root) for a, b in itertools.pairwise(pts) if a != b], pts=[(p, root) for p in path]),
        )
        sites = (A.sites if A else [hk]) + (B.sites if B else [qk])
        chains = (A.chains if A else []) + (B.chains if B else []) + [[hk, *path, qk]]
        term = None
        if A and A.term:
            term = A.term
            if B and B.term:
                self.cv.remove(("gterm", gb))
        elif B and B.term:
            term = B.term
        elif gterm and gterm[0]:
            term = gterm[0]
            self.cv.add(("gterm", root), gterm[1])
        if A and A.term:
            lay = self.cv.layers.pop(("gterm", ga), None)
            if lay:
                self.cv.add(("gterm", root), lay)
        elif B and B.term:
            lay = self.cv.layers.pop(("gterm", gb), None)
            if lay:
                self.cv.add(("gterm", root), lay)
        self.groups[root] = Group(sites, chains, term)

    # --- candidates

    def owner(self, ref: str) -> str | None:
        """The multi-pin part a two-pin part on rails serves: the nearest before it in the
        source with a pin on its supply, else the nearest after."""
        sup = {n for n in self.m.nets_of(ref) if self.m.rail.get(n) == "supply"}
        cands = [r for r in self.refs if self.m.kind(r) == "multi" and sup & set(self.m.nets_of(r))]
        if not cands:  # no IC on that supply here: the parts that use it (an emitter resistor)
            cands = [
                r
                for r in self.refs
                if self.m.kind(r) == "two" and self.m.role(r) != "decap" and sup & set(self.m.nets_of(r))
            ]
        rank = self.ranks.get(ref, 0)
        before = [r for r in cands if self.ranks.get(r, 0) <= rank]
        after = [r for r in cands if self.ranks.get(r, 0) > rank]
        if before:
            return max(before, key=lambda r: self.ranks.get(r, 0))
        return min(after, key=lambda r: self.ranks.get(r, 0)) if after else None

    def hosts(self, ref: str) -> list[tuple[str, str]]:
        """(placed site key, part pin id) pairs on one net: signal nets first, then supplies;
        a decoupling capacitor's at the part it serves (or at capacitors already there)."""
        out = []
        decap = self.m.kind(ref) == "two" and self.m.role(ref) == "decap"
        owner = self.owner(ref) if decap else None
        for p in self.m.pins_of[ref]:
            n = self.m.net.get(p.id)
            if not n or self.m.rail.get(n) == "ground":
                continue
            for sk, s in self.sites.items():
                if self.net(sk) != n or s.rep in self.m.placer.pin_nc:
                    continue
                if owner and owner in self.placed and s.ref != owner and self.owner(s.ref) != owner:
                    continue
                out.append((sk, p.id))
        sig = [h for h in out if self.m.rail.get(self.m.net.get(h[1])) is None]
        return sig or out

    def candidates(self, ref: str):
        hosts = self.hosts(ref)
        cands = []
        ax, ay = self.center()
        flow = self.hints.get("flow", {}).get(ref)
        for rot, mirror in self.orientations(ref):
            sh = self.m.shape(ref, rot, mirror)
            for hk, pid in hosts:
                H = self.sites[hk]
                q = next(s for s in sh.sites if pid in s.pids)
                two = self.m.kind(H.ref) == "two" and self.m.kind(ref) == "two"
                via_passive = 4 if two and self.m.role(H.ref) != "decap" else 0
                row = two and self.m.role(H.ref) == "decap" and self.m.role(ref) == "decap"
                supply = self.m.rail.get(self.m.net.get(pid)) == "supply"
                for Q, path, cost in _routes(H.loc, H.out, q.out, supply, row):
                    cost += 3 * len(path)
                    at = (Q[0] - q.loc[0], Q[1] - q.loc[1])
                    cost += via_passive
                    cx = at[0] + (sh.box[0] + sh.box[2]) / 2
                    cy = at[1] + (sh.box[1] + sh.box[3]) / 2
                    c = cost + 0.05 * (abs(cx - ax) + abs(cy - ay))
                    if flow and not self._on_side(flow, cx, cy):
                        continue
                    if len(sh.sites) > 2:
                        c -= 8 * self._aligned(sh, at, pid)
                    cands.append((c, rot, mirror, at, (hk, Q, path)))
        cands.sort(key=lambda c: (c[0], c[1], str(c[2]), c[3]))
        return cands

    def _links(self, ref: str, sites: list[Site], conn) -> list[tuple[str, str]]:
        """(placed site, part site) pairs a straight wire would join: one net (not a rail),
        facing each other in line, two steps apart or more."""
        if self.m.kind(ref) != "multi":
            return []
        out, used = [], set()
        for s in sites:
            sk = _key(s)
            net = self.m.net.get(s.rep)
            if (conn and sk == f"{ref}@{conn[1][0]},{conn[1][1]}") or not net or net in self.m.rail:
                continue
            for hk, h in sorted(self.sites.items()):
                if hk in used or h.out != _neg(s.out) or self.net(hk) != net or (conn and hk == conn[0]):
                    continue
                d = (s.loc[0] - h.loc[0], s.loc[1] - h.loc[1])
                if (d[0] * h.out[0] + d[1] * h.out[1]) >= 2 and (d[0] * h.out[1] - d[1] * h.out[0]) == 0:
                    out.append((hk, sk))
                    used.add(hk)
                    break
        return out

    def _aligned(self, sh: Shape, at, skip: str) -> int:
        """How many more of the part's pins would face a placed pin of their net in line."""
        n = 0
        for s in sh.sites:
            if skip in s.pids:
                continue
            net = self.m.net.get(s.rep)
            if not net or net in self.m.rail:
                continue
            loc = (s.loc[0] + at[0], s.loc[1] + at[1])
            for sk, h in self.sites.items():
                if h.out == _neg(s.out) and self.net(sk) == net:
                    d = (loc[0] - h.loc[0], loc[1] - h.loc[1])
                    if (d[0] * h.out[0] + d[1] * h.out[1]) >= 2 and (d[0] * h.out[1] - d[1] * h.out[0]) == 0:
                        n += 1
                        break
        return n

    def _on_side(self, flow: str, x: float, y: float) -> bool:
        """The point lies on that side of the anchor (a `flow` hint)."""
        ax, ay = self.center()
        return {"left": x < ax, "right": x > ax, "above": y < ay, "below": y > ay}[flow]

    def center(self):
        p = self.placed.get(self.anchor)
        if not p:
            return (0.0, 0.0)
        b = p.shape.box
        return (p.at[0] + (b[0] + b[2]) / 2, p.at[1] + (b[1] + b[3]) / 2)

    def place_part(self, ref: str) -> bool:
        pref = self.prefer.get(ref)
        if pref and pref[3] and pref[3][0] in self.sites:
            rot, mirror, at, conn = pref
            r = self.try_place(ref, at, rot, mirror, conn)
            if r is not None and r[0] == 0:
                self.commit(r[1])
                return True
        best = None
        tried = 0
        for c, rot, mirror, at, conn in self.candidates(ref):
            if best and c > best[0] + 25:
                break
            r = self.try_place(ref, at, rot, mirror, conn)
            tried += 1
            if r is None:
                if tried > 4000:
                    break
                continue
            cost = c + CROSSING * r[0]
            if best is None or cost < best[0]:
                best = (cost, r[1])
            if r[0] == 0:
                break
        if best:
            self.commit(best[1])
            return True
        return False

    def place_free(self, ref: str, rot=None, mirror=None):
        """Place a part without wires, nearest the block's centre, each pin keeping its label."""
        pref = self.prefer.get(ref)
        if pref and pref[3] is None:
            r = self.try_place(ref, pref[2], pref[0], pref[1])
            if r is not None:
                self.commit(r[1])
                return
        if rot is None:
            rot, mirror = self.orientations(ref)[0]
        nets = {n for n in self.m.nets_of(ref) if n not in self.m.rail}
        near = [s.loc for sk, s in self.sites.items() if self.net(sk) in nets]
        if near:  # beside the pins it shares a net with
            cx = round(sum(p[0] for p in near) / len(near))
            cy = round(sum(p[1] for p in near) / len(near))
        else:
            x0, y0, x1, y1 = self.cv.bbox()
            cx, cy = round((x0 + x1) / 2), round((y0 + y1) / 2)
        flow = self.hints.get("flow", {}).get(ref)
        if flow:  # start beyond the anchor on that side
            x0, y0, x1, y1 = self.placed[self.anchor].shape.box if self.anchor in self.placed else (0, 0, 0, 0)
            ax, ay = self.placed[self.anchor].at if self.anchor in self.placed else (0, 0)
            cx, cy = {
                "left": (round(ax + x0) - 6, cy),
                "right": (round(ax + x1) + 6, cy),
                "above": (cx, round(ay + y0) - 6),
                "below": (cx, round(ay + y1) + 6),
            }[flow]
        sh = self.m.shape(ref, rot, mirror)
        for r in range(0, 200, 2):
            ring = sorted(
                {(cx + dx, cy + dy) for dx in range(-r, r + 1, 2) for dy in (-r, r)}
                | {(cx + dx, cy + dy) for dy in range(-r, r + 1, 2) for dx in (-r, r)},
                key=lambda p: (abs(p[1] - cy) + abs(p[0] - cx), p[1], p[0]),
            )
            for at in ring:
                mid = (at[0] + (sh.box[0] + sh.box[2]) / 2, at[1] + (sh.box[1] + sh.box[3]) / 2)
                if flow and not self._on_side(flow, *mid):
                    continue
                res = self.try_place(ref, at, rot, mirror)
                if res:
                    self.commit(res[1])
                    return
        raise RuntimeError(f"no room for {ref}")

    def extra_wires(self, only: str | None = None, crossings: bool = False) -> bool:
        """Wire placed pins of one net that are still apart, where a short clean path exists
        (only: from this site; crossings: across other wires too). True if it wired any."""
        done = False
        by_net: dict = {}
        for sk in sorted(self.sites):
            n = self.net(sk)
            if n and self.sites[sk].rep not in self.m.placer.pin_nc and self.m.drivers(self.sites[sk].rep):
                by_net.setdefault(n, []).append(sk)
        for n, sks in sorted(by_net.items()):
            if len(sks) < 2 or self.m.rail.get(n) == "ground":
                continue
            for i, a in enumerate(sks):
                for b in sks[i + 1 :]:
                    if self.gid(a) == self.gid(b) or (only and only not in (a, b)):
                        continue
                    A, B = self.sites[a], self.sites[b]
                    paths = _paths_between(A.loc, A.out, B.loc, B.out)
                    routed = _route_grid(
                        self.cv,
                        A.loc,
                        A.out,
                        B.loc,
                        B.out,
                        [("site", a), ("site", b)],
                        {("pterm", a), ("pterm", b), ("dterm", a), ("dterm", b)},
                        crossings,
                    )
                    if routed is not None:
                        paths.append(routed)
                    for path in paths:
                        pts = [A.loc, *path, B.loc]
                        length = sum(abs(p[0] - q[0]) + abs(p[1] - q[1]) for p, q in itertools.pairwise(pts))
                        if length > 30:
                            continue
                        g = ("site", a)
                        allowed = [g, ("site", b)]
                        ignore = {("pterm", a), ("pterm", b), ("dterm", a), ("dterm", b)}
                        wi = Items(segs=[(p, q, g) for p, q in itertools.pairwise(pts) if p != q])
                        c = self.cv.conflicts(wi, allowed=allowed, ignore=ignore)
                        replace = False
                        if c is None and crossings:
                            # the nets' own labels may be in the way: draw the joined net's anew
                            ignore |= {("gterm", self.gid(a)), ("gterm", self.gid(b))}
                            c = self.cv.conflicts(wi, allowed=allowed, ignore=ignore)
                            replace = True
                        if c is None or (c and not crossings):
                            continue
                        gterm = None
                        if replace or (not self.wired(a) and not self.wired(b)):
                            gterm = self.group_term([a, b], self.sites, pts, g, ignore, [wi])
                            if gterm is None:
                                continue
                        self._join(a, b, path, gterm, replace)
                        self.extra_log.append((a, b, path))
                        done = True
                        break
        return done

    def replay_wires(self, log, rmap) -> None:
        """An identical block's extra wires, mapped onto this one's parts, where they fit."""
        for a, b, path in log:
            a2 = "{}@{}".format(rmap[a.split("@")[0]], a.split("@")[1])
            b2 = "{}@{}".format(rmap[b.split("@")[0]], b.split("@")[1])
            if a2 not in self.sites or b2 not in self.sites or self.gid(a2) == self.gid(b2):
                continue
            A, B = self.sites[a2], self.sites[b2]
            pts = [A.loc, *path, B.loc]
            g = ("site", a2)
            ignore = {("pterm", a2), ("pterm", b2), ("dterm", a2), ("dterm", b2)}
            wi = Items(segs=[(p, q, g) for p, q in itertools.pairwise(pts) if p != q])
            if self.cv.conflicts(wi, allowed=[g, ("site", b2)], ignore=ignore) is None:
                continue
            gterm = None
            if not self.wired(a2) and not self.wired(b2):
                gterm = self.group_term([a2, b2], self.sites, pts, g, ignore, [wi])
                if gterm is None:
                    continue
            self._join(a2, b2, path, gterm)

    def layout(self):
        order = [r for r in self.refs if r != self.anchor]
        r = self.try_place(self.anchor, (0, 0), 0, None, defer=True)
        if r is None:
            raise RuntimeError(f"{self.anchor}: its own fields collide")
        self.commit(r[1])
        left = list(order)
        while left:
            nxt = min(left, key=self._priority)
            left.remove(nxt)
            if not self.hosts(nxt) or not self.place_part(nxt):
                self.place_free(nxt)
        if self.like:
            self.replay_wires(self.like[0].extra_log, self.like[1])
        else:
            self.extra_wires()
        self.resolve_deferred()

    def resolve_deferred(self):
        """Labels for the sites that had no room when their part was placed: wired since, or
        on a stub now, or wired to a pin of their net across other wires, or drawn anyway (the
        overlap check then names them)."""
        for sk in self.deferred:
            if self.wired(sk):
                continue
            s = self.sites[sk]
            self.cv.remove(("dterm", sk))
            for opts in self._term_variants(s):
                ti = self._site_term(s, opts, ("site", sk))
                if ti is None or self.cv.conflicts(ti, allowed=[("site", sk)]) == 0:
                    break
            else:
                if self.extra_wires(only=sk, crossings=False) or self._dogleg(sk):
                    continue
                if self.extra_wires(only=sk, crossings=True):
                    continue
                # a long stub carries the label past its neighbours' labels
                for opts in [{"len": n, **o} for n in (12, 16, 20, 24, 30) for o in ({}, {"point": "out"})]:
                    ti = self._site_term(s, opts, ("site", sk))
                    if ti is None or self.cv.conflicts(ti, allowed=[("site", sk)]) == 0:
                        break
                else:
                    opts = {}
                    ti = self._site_term(s, opts, ("site", sk))
                if os.environ.get("AUTOPLACE_DEBUG"):
                    print(f"  no room for the label of {s.rep} at {s.loc}: {self._blockers(ti, sk)}")
            if opts:
                self.stub_opts[s.rep] = opts
            if ti is not None:
                self.cv.add(("pterm", sk), ti)
        self.deferred = []

    def _dogleg(self, sk: str) -> bool:
        """A lone pin's label on a short stub that steps sideways, clear of its neighbours."""
        s = self.sites[sk]
        drivers = self.m.drivers(s.rep)
        if not drivers or s.rep in self.m.placer.pin_nc:
            return False
        perp = (s.out[1], s.out[0])
        g = ("site", sk)
        for k in (1, 2, 3, 4, 6):
            for dv in (1, -1, 2, -2, 3, -3):
                for L in (2, 3, 4, 6, 8):
                    p1 = _add(s.loc, s.out, k)
                    p2 = _add(p1, perp, dv)
                    e = _add(p2, s.out, L)
                    pts = [s.loc, p1, p2, e]
                    it = self.m.term_items(e, s.out, drivers[0], {"len": 0}, g)
                    it.segs += [(a, b, g) for a, b in itertools.pairwise(pts)]
                    if self.cv.conflicts(it, allowed=[g]) == 0:
                        self.cv.add(("gterm", g), it)
                        self.groups[self.gid(sk)] = Group([sk], [[sk, p1, p2, e]], ("free",))
                        return True
        return False

    def _priority(self, ref):
        kind = self.m.kind(ref)
        hosts = self.hosts(ref)
        sig = [h for h in hosts if self.m.rail.get(self.m.net.get(h[1])) is None]
        if kind == "multi":
            tier = 0 if sig else 4
        elif kind == "two":
            role = self.m.role(ref)
            tier = {"series": 1, "shunt_sup": 2, "shunt_gnd": 2, "decap": 3}[role] if hosts else 5
        else:
            tier = 5
        shared = len({self.m.net.get(h[1]) for h in sig})
        return (tier, -shared, self.ranks.get(ref, 0), ref)

    # --- output

    def tokens(self, sk: str) -> str:
        site = self.sites[sk]
        p = next(p for p in self.m.pins_of[site.ref] if p.id == site.rep)
        names = [q.name for q in self.m.pins_of[site.ref]]
        if p.name and p.name != "~" and names.count(p.name) == 1 and re.fullmatch(r"[A-Za-z0-9_+\-/]+", p.name):
            return f"{site.ref}.{p.name}"
        return site.rep


def _route_grid(cv: Canvas, A, ao, B, bo, allowed, ignore, crossings: bool, pad: int = 12):
    """A short orthogonal path from pin A (leaving along ao) to pin B (entering against bo) on
    the grid, around boxes and other nets' wires and points; crossing another wire costs, or is
    barred. Returns the corner points, or None."""
    import heapq

    ok = {cv.find(g) for g in allowed}
    x0, x1 = min(A[0], B[0]) - pad, max(A[0], B[0]) + pad
    y0, y1 = min(A[1], B[1]) - pad, max(A[1], B[1]) + pad
    win = (x0, y0, x1, y1)
    boxes, hseg, vseg, pts = [], set(), set(), set()
    for tag, lay in cv.layers.items():
        if tag in ignore:
            continue
        for b in lay.boxes:
            if _hits(b, win, 1):
                m = -TEXT_CLEAR if b[4] == "text" and (b[5] is None or cv.find(b[5]) not in ok) else 0.05
                boxes.append((b[0] + m, b[1] + m, b[2] - m, b[3] - m))
        for a, b, g in lay.segs:
            if cv.find(g) in ok:
                continue
            if abs(a[1] - b[1]) < 1e-9:
                for x in range(math.ceil(min(a[0], b[0])), math.floor(max(a[0], b[0])) + 1):
                    hseg.add((x, round(a[1])))
            else:
                for y in range(math.ceil(min(a[1], b[1])), math.floor(max(a[1], b[1])) + 1):
                    vseg.add((round(a[0]), y))
            pts.add((round(a[0]), round(a[1])))
            pts.add((round(b[0]), round(b[1])))
        for p, g in lay.pts:
            if cv.find(g) not in ok:
                pts.add((round(p[0]), round(p[1])))

    def inside(p):
        return any(b[0] < p[0] < b[2] and b[1] < p[1] < b[3] for b in boxes)

    def edge_ok(p, q):
        mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
        return not any(b[0] < mx < b[2] and b[1] < my < b[3] for b in boxes)

    start = (A[0] + ao[0], A[1] + ao[1])
    goal = (B[0] + bo[0], B[1] + bo[1])
    if inside(start) or start in pts:
        if os.environ.get("AUTOPLACE_DEBUG"):
            print("   route start blocked", start, inside(start), start in pts)
        return None
    dist = {(start, ao): 0}
    prev = {}
    heap = [(0, start, ao)]
    end = None
    while heap:
        c, p, d = heapq.heappop(heap)
        if dist.get((p, d), 1e9) < c:
            continue
        if (p == goal and d == _neg(bo)) or (p == goal and (p[0] - bo[0], p[1] - bo[1]) == B and d == _neg(bo)):
            end = (p, d)
            break
        if p == goal:
            # turn into the pin: allowed only moving against bo
            pass
        for nd in DIRS:
            if nd == _neg(d):
                continue
            q = (p[0] + nd[0], p[1] + nd[1])
            if not (x0 <= q[0] <= x1 and y0 <= q[1] <= y1):
                continue
            if q == B:
                continue
            horiz = nd[1] == 0
            if (horiz and (q in hseg or (p in hseg and q in hseg))) or (not horiz and q in vseg):
                continue
            cost = 1 + (4 if nd != d else 0)
            if q in pts or inside(q) or not edge_ok(p, q):
                continue
            if (horiz and q in vseg) or (not horiz and q in hseg):
                if not crossings:
                    continue
                cost += 15
            nc = c + cost
            if nc < dist.get((q, nd), 1e9):
                dist[(q, nd)] = nc
                prev[(q, nd)] = (p, d)
                heapq.heappush(heap, (nc, q, nd))
        if len(dist) > 20000:
            return None
    if end is None:
        if os.environ.get("AUTOPLACE_DEBUG"):
            print("   route: no path", len(dist), "states; goal", goal, "blocked", inside(goal), goal in pts)
        return None
    path = [end[0]]
    k = end
    while k in prev:
        k = prev[k]
        path.append(k[0])
    path.reverse()
    full = [A, *path, B]
    corners = [
        q
        for p, q, r in zip(full, full[1:], full[2:], strict=False)
        if (q[0] - p[0], q[1] - p[1]) != (r[0] - q[0], r[1] - q[1])
    ]
    return corners


def _key(s: Site) -> str:
    return f"{s.ref}@{s.loc[0]},{s.loc[1]}"


def _shift(b, d):
    return (b[0] + d[0], b[1] + d[1], b[2] + d[0], b[3] + d[1], *b[4:])


def _colinear(p, e, a, b) -> bool:
    return (abs(p[0] - e[0]) < 1e-9 and abs(a[0] - b[0]) < 1e-9) or (
        abs(p[1] - e[1]) < 1e-9 and abs(a[1] - b[1]) < 1e-9
    )


def _routes(H, ho, qo, supply: bool, row: bool = False):
    """Where a part's pin (pointing qo) can go to be wired to a placed pin at H pointing ho:
    (pin point, corner points, cost), nearest first. row: H is a capacitor's supply pin, and
    the part goes beside it in its row."""
    out = []
    if row:
        if qo == ho == UP:
            for j in range(2, 40):
                out += [((H[0] + j, H[1]), [], j), ((H[0] - j, H[1]), [], j + 0.5)]
        return out
    perp = (ho[1], ho[0])
    if qo == _neg(ho):  # facing it: in line
        for k in range(2, 24):
            out.append((_add(H, ho, k), [], k))
        for k in range(2, 12):  # in line, stepped sideways
            for dy in (-2, 2, -4, 4, -6, 6):
                c1 = _add(H, ho, k)
                c2 = _add(c1, perp, dy)
                for m in (2, 4, 6):
                    out.append((_add(c2, ho, m), [c1, c2], k + m + abs(dy) + 4))
    elif qo in (perp, _neg(perp)):  # standing across the pin's line: one corner
        for k in range(1, 24):
            c = _add(H, ho, k)
            for m in range(1, 12):
                out.append((_add(c, qo, -m), [c], k + m + 2))
    if supply and qo == UP:  # a supply pin on top: hang from a bus above
        if ho == UP:
            for m in range(0, 14):
                c = _add(H, UP, m)
                for j in range(2, 30):
                    for s in (1, -1):
                        Q = (c[0] + s * j, c[1])
                        out.append((Q, [c] if m else [], m + j + (2 if m else 0)))
        elif ho in (LEFT, RIGHT):
            for k in range(1, 12):
                c1 = _add(H, ho, k)
                for m in range(2, 16):
                    c2 = _add(c1, UP, m)
                    for j in range(2, 30):
                        for s in (1, -1):
                            out.append(((c2[0] + s * j, c2[1]), [c1, c2], k + m + j + 4))
    return sorted(out, key=lambda r: r[2])


def _paths_between(A, ao, B, bo):
    """Corner points of short orthogonal paths leaving A along ao and entering B against bo."""
    out = []
    if ao == _neg(bo):
        if (ao[0] and A[1] == B[1] and (B[0] - A[0]) * ao[0] > 0) or (
            ao[1] and A[0] == B[0] and (B[1] - A[1]) * ao[1] > 0
        ):
            out.append([])
        else:
            if ao[0]:
                span = (B[0] - A[0]) * ao[0]
                for k in range(1, int(span)):
                    x = A[0] + ao[0] * k
                    out.append([(x, A[1]), (x, B[1])])
            else:
                span = (B[1] - A[1]) * ao[1]
                for k in range(1, int(span)):
                    y = A[1] + ao[1] * k
                    out.append([(A[0], y), (B[0], y)])
    elif ao == bo:
        for m in range(1, 5):
            if ao[0]:
                x = (max(A[0], B[0]) + m) if ao[0] > 0 else (min(A[0], B[0]) - m)
                out.append([(x, A[1]), (x, B[1])])
            else:
                y = (max(A[1], B[1]) + m) if ao[1] > 0 else (min(A[1], B[1]) - m)
                out.append([(A[0], y), (B[0], y)])
    else:
        c = (B[0], A[1]) if ao[0] else (A[0], B[1])
        if (c[0] - A[0]) * ao[0] + (c[1] - A[1]) * ao[1] > 0 and (c[0] - B[0]) * bo[0] + (c[1] - B[1]) * bo[1] > 0:
            out.append([c])
    return out


# ---------------------------------------------------------------------------------------------
# Blocks of a sheet


@dataclass
class BlockPlan:
    title: str
    anchor: str
    refs: list[str]
    kind: str = "circuit"  # circuit, grid (unconnected parts in rows)


def assign_blocks(m: Model, refs: list[str], hints: dict, ranks: dict) -> list[BlockPlan]:
    """Group a sheet's parts into function blocks (see the module docstring)."""
    refs = sorted(refs, key=lambda r: (ranks.get(r, 0), r))
    parent = {r: r for r in refs}
    locked: dict[str, int] = {}  # part -> hint block index

    def find(r):
        while parent[r] != r:
            parent[r] = parent[parent[r]]
            r = parent[r]
        return r

    multi = {r: m.kind(r) == "multi" for r in refs}

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        la, lb = locked.get(ra), locked.get(rb)
        if la is not None and lb is not None and la != lb:
            return
        # a hinted block takes in passives by connectivity, never a multi-pin part it does not list
        if (la is None) != (lb is None) and multi[ra if la is None else rb]:
            return
        parent[rb] = ra
        multi[ra] = multi[ra] or multi[rb]
        if lb is not None:
            locked[ra] = lb

    for i, hb in enumerate(hints.get("blocks", [])):
        members = [r for r in hb.get("parts", []) if r in parent]
        for r in members:
            locked[find(r)] = i
        for r in members[1:]:
            union(members[0], r)
    kind = {r: m.kind(r) for r in refs}
    on_net: dict[str, list[str]] = {}
    for r in refs:
        if kind[r] in ("one", "none"):
            continue
        for n in set(m.nets_of(r)):
            if n not in m.rail:
                on_net.setdefault(n, []).append(r)
    for n, rs in sorted(on_net.items()):
        multis = [r for r in rs if kind[r] == "multi"]
        local = n not in m.port
        if (local and len(multis) <= 2) or (not local and len(multis) <= 1):
            for r in rs[1:]:
                union(rs[0], r)
    comps: dict[str, list[str]] = {}
    for r in refs:
        if kind[r] not in ("one", "none") or find(r) in locked:
            comps.setdefault(find(r), []).append(r)
    blocks: list[BlockPlan] = []
    hint_blocks: dict[int, BlockPlan] = {}
    loose: list[list[str]] = []
    for root, rs in comps.items():
        hb = locked.get(root)
        multis = [r for r in rs if kind[r] == "multi"]
        if hb is not None:
            h = hints["blocks"][hb]
            anchor = h.get("anchor") or (
                max(multis, key=lambda r: (len(m.pins_of[r]), -ranks.get(r, 0))) if multis else rs[0]
            )
            hint_blocks[hb] = BlockPlan(h.get("title", ""), anchor, rs)
        elif multis:
            anchor = max(multis, key=lambda r: (len(m.pins_of[r]), -ranks.get(r, 0)))
            blocks.append(BlockPlan("", anchor, rs))
        else:
            loose.append(rs)
    blocks = [hint_blocks[i] for i in sorted(hint_blocks)] + blocks
    block_of = {r: b for b in blocks for r in b.refs}
    shared = BlockPlan("", "", [])
    for rs in loose:
        rank = min(ranks.get(r, 0) for r in rs)
        sig = {n for r in rs for n in m.nets_of(r) if n not in m.rail}
        sup = {n for r in rs for n in m.nets_of(r) if m.rail.get(n) == "supply"}
        touched = {id(block_of[r]) for n in sig for r in refs if r in block_of and n in m.nets_of(r)}
        if sig and len(touched) > 1:
            shared.refs += rs
            continue
        if sig and touched:
            target = next(b for b in blocks if id(b) in touched)
        else:
            # the nearest part before it in the source that has its supply (one function's
            # parts are written together), else the nearest after
            cands = [(ranks.get(r, 0), b) for b in blocks for r in b.refs if sup & set(m.nets_of(r))]
            before = [c for c in cands if c[0] <= rank]
            after = [c for c in cands if c[0] > rank]
            target = (
                max(before, key=lambda c: c[0])[1] if before else (min(after, key=lambda c: c[0])[1] if after else None)
            )
        if target is None:
            anchor = rs[0]
            b = BlockPlan("", anchor, rs)
            blocks.append(b)
            for r in rs:
                block_of[r] = b
        else:
            target.refs += rs
            for r in rs:
                block_of[r] = target
    if shared.refs:
        nets = sorted({n for r in shared.refs for n in m.nets_of(r) if n not in m.rail})
        shared.title = "Shared nets: " + ", ".join(nets[:4]) + (", ..." if len(nets) > 4 else "")
        shared.anchor = shared.refs[0]
        blocks.append(shared)
    tps = [r for r in refs if kind[r] == "one" and r not in block_of]
    if tps:
        blocks.append(BlockPlan("Test points", tps[0], tps, "grid"))
    mech = [r for r in refs if kind[r] == "none" and r not in block_of]
    if mech:
        blocks.append(BlockPlan("Parts without connections", mech[0], mech, "grid"))
    titles = hints.get("titles", {})
    for b in blocks:
        b.refs = sorted(b.refs, key=lambda r: (ranks.get(r, 0), r))
        for r in b.refs:
            if r in titles:
                b.title = titles[r]
        if not b.title:
            multis = sorted(
                (r for r in b.refs if kind[r] == "multi"), key=lambda r: (-len(m.pins_of[r]), ranks.get(r, 0))
            )
            others = [r for r in b.refs if not re.match(r"[RC]\d", r)] or b.refs
            # the main part, and the next active one (an IC, a transistor, a sensor)
            active = [r for r in multis[1:] if not re.match(r"(R|C|L|J|M|P|F|SW|H)\d", r)]
            main = (multis[:1] + active[:1]) or others[:1]
            b.title = ", ".join(f"{r} {m.parts[r].value}" for r in main)
    order = hints.get("order", [])

    def key(b):
        idx = [order.index(r) for r in b.refs if r in order]
        tail = 2 if b.kind == "grid" else (1 if b is shared else 0)
        return (min(idx) if idx else len(order), tail, min(ranks.get(r, 0) for r in b.refs))

    return sorted(blocks, key=key)


def _signature(m: Model, b: BlockPlan) -> tuple:
    """A block's parts and connections, independent of names: equal for repeated blocks."""
    nets: dict = {}
    sig = []
    for r in b.refs:
        s = m.parts[r]
        pins = []
        for p in sorted(m.pins_of[r], key=lambda p: p.number):
            n = m.net.get(p.id)
            if n in m.rail or n is None:
                pins.append((p.number, n))
            else:
                pins.append((p.number, nets.setdefault(n, len(nets))))
        sig.append((s.lib.name, s.value, tuple(pins), r == b.anchor))
    return tuple(sig)


def layout_block(m: Model, b: BlockPlan, hints: dict, ranks: dict, like: tuple | None = None) -> Block:
    """Lay a block out; `like` = (block, ref map) of an identical block whose positions to try
    first."""
    blk = Block(m, b.refs, b.anchor, b.title, hints, ranks)
    if b.kind == "grid":
        x = 0
        for r in b.refs:
            rot, mirror = blk.orientations(r)[0]
            for dx in range(0, 400):
                res = blk.try_place(r, (x + dx, 0), rot, mirror)
                if res:
                    blk.commit(res[1])
                    bx = blk.cv.bbox()
                    x = math.ceil(bx[2]) + 2
                    break
        return blk
    if like:
        other, rmap = like
        blk.like = like
        blk.prefer = {
            rmap[r]: (p.rot, p.mirror, p.at, _map_conn(other, r, rmap)) for r, p in other.placed.items() if r in rmap
        }
    blk.layout()
    return blk


def _map_conn(other: Block, ref: str, rmap: dict):
    for g in other.groups.values():
        for ch in g.chains:
            for a, z in ((ch[0], ch[-1]), (ch[-1], ch[0])):
                if (
                    isinstance(a, str)
                    and isinstance(z, str)
                    and z.startswith(f"{ref}@")
                    and not a.startswith(f"{ref}@")
                ):
                    aref, aloc = a.split("@")
                    zloc = z.split("@")[1]
                    path = ch[1:-1] if ch[-1] == z else list(reversed(ch[1:-1]))
                    zl = tuple(int(v) for v in zloc.split(","))
                    return (f"{rmap[aref]}@{aloc}", zl, path)
    return None


# ---------------------------------------------------------------------------------------------
# A sheet's draft


def _fmt_pt(p, o):
    return [round(p[0] + o[0]), round(p[1] + o[1])]


def block_data(blk: Block) -> dict:
    """A laid-out block as placement-file data: frame size, parts, wires and stubs, relative to
    the frame's top-left corner (its `at`, set when the sheet is packed)."""
    bx0, by0, bx1, by1 = blk.cv.bbox()
    o = (PAD - math.floor(bx0), PAD + TITLE_H - math.floor(by0))
    w = math.ceil(bx1) - math.floor(bx0) + 2 * PAD
    w = max(w, math.ceil(text_width(blk.title, 1.5) * 1.1 / GRID) + 3)
    h = math.ceil(by1) - math.floor(by0) + 2 * PAD + TITLE_H
    parts = {}
    for ref in blk.refs:
        p = blk.placed.get(ref)
        if p is None:
            continue
        e: dict = {"at": _fmt_pt(p.at, o)}
        if p.rot:
            e["rot"] = p.rot
        if p.mirror:
            e["mirror"] = p.mirror
        if p.fields:
            e["fields"] = p.fields
        parts[ref] = e
    wires = []
    for g in sorted(blk.groups.values(), key=lambda g: g.chains[0][0] if isinstance(g.chains[0][0], str) else ""):
        chains = [list(c) for c in g.chains]
        if g.term and g.term[0] == "onwire":
            sk = g.term[1]
            i = next(i for i, c in enumerate(chains) if sk in (c[0], c[-1]))
            c = chains.pop(i)
            chains.insert(0, c if c[0] == sk else list(reversed(c)))
        for c in chains:
            wires.append([blk.tokens(t) if isinstance(t, str) else _fmt_pt(t, o) for t in c])
        if g.term and g.term[0] == "branch":
            wires.append([_fmt_pt(g.term[1], o), _fmt_pt(g.term[2], o), *([g.term[3]] if g.term[3] else [])])
    data: dict = {"title": blk.title, "at": [0, 0], "size": [w, h], "auto": True, "parts": parts}
    if wires:
        data["wires"] = wires
    if blk.stub_opts:
        data["stubs"] = {k: v for k, v in sorted(blk.stub_opts.items())}
    return data


def _equal_frames(blocks: list[dict], groups: list[int]) -> None:
    """Identical blocks get one frame size (the largest), so they line up."""
    for g in set(groups):
        members = [b for b, gg in zip(blocks, groups, strict=True) if gg == g]
        w = max(b["size"][0] for b in members)
        h = max(b["size"][1] for b in members)
        for b in members:
            b["size"] = [w, h]


def _io_order(zen: Path | None) -> list[str]:
    text = zen.read_text() if zen and zen.exists() else ""
    return re.findall(r"^(\w+)\s*=\s*io\(", text, re.M)


def sheet_symbols(m: Model, board: str, names: list[str]) -> list[dict]:
    """Each module's sheet symbol: its pins that meet the root sheet's parts on the left, those
    that only join other modules on the right, each side in the order of the module's io()
    declarations (a protocol's signals together)."""
    root_texts = {d.text for pid, ds in m.placer.pin_drivers.items() for d in ds}
    out = []
    for n in m.sheet.root.children("sheet"):
        name = n.prop("Sheetname") or ""
        if name not in names:
            continue
        pins = [p.atoms()[0] for p in n.children("pin")]
        order = _io_order(sheet_module(board, name))
        upper = [o.upper() for o in order]

        def key(p, upper=upper, pins=pins):
            base = p.split(".")[0].upper()
            return (upper.index(base) if base in upper else len(upper), pins.index(p))

        left, right = [], []
        for p in sorted(pins, key=key):
            drivers = m.placer.sheet_pin_drivers.get((name, p), [])
            (left if any(d.text in root_texts for d in drivers) or not drivers else right).append(p)
        lw = max((text_width(p) for p in left), default=0)
        rw = max((text_width(p) for p in right), default=0)
        w = max(16, math.ceil((lw + rw) / GRID) + 6, math.ceil(text_width(name) / GRID) + 2)
        h = 2 * (max(len(left), len(right)) + 1)
        ext_l = max(
            (text_width(d.text) for p in left for d in m.placer.sheet_pin_drivers.get((name, p), [])[:1]), default=0
        )
        ext_r = max(
            (text_width(d.text) for p in right for d in m.placer.sheet_pin_drivers.get((name, p), [])[:1]), default=0
        )
        out.append(
            {
                "name": name,
                "size": [w, h],
                "left": left,
                "right": right,
                "ext": (
                    math.ceil(ext_l / GRID + 2 + 3.5) if left else 0,
                    math.ceil(ext_r / GRID + 2 + 3.5) if right else 0,
                ),
            }
        )
    return out


def ports_entries(m: Model, blocks: list[Block] = ()) -> list[tuple[Driver, Driver]]:
    """The ports column's rows: each further label of a pin, or of a wired net, that pcb gave
    several (placement._ports)."""
    seen, out = set(), []
    wired = {pid for b in blocks for g in b.groups.values() for sk in g.sites for pid in b.sites[sk].pids}
    lists = [ds for pid, ds in m.placer.pin_drivers.items() if pid not in wired]
    lists += [b.group_drivers(g.sites) for b in blocks for g in b.groups.values()]
    for ds in [*lists, *m.placer.sheet_pin_drivers.values()]:
        for other in ds[1:]:
            k = (ds[0].kind, ds[0].text, other.kind, other.text)
            if k not in seen:
                seen.add(k)
                out.append((ds[0], other))
    return out


def ports_size(entries) -> tuple[int, int, int]:
    """(width, height, rows) of the ports column, grid units (placement._ports)."""
    n = len(entries)
    cols = math.ceil(n / 14)
    rows = math.ceil(n / cols)
    left = math.ceil((max(text_width(e[0].text) for e in entries) + 3.3) / GRID - 1e-6) + 2
    right = math.ceil((max(text_width(e[1].text) for e in entries) + 3.3) / GRID - 1e-6) + 1
    column = left + 4 + right + 2
    return cols * column, 4 + 2 * (rows - 1) + 2, rows


def _page(paper: str) -> tuple[float, float]:
    w, h = PAPER[paper]
    return w / GRID, h / GRID


def pack(sizes: list[tuple[int, int]], occupied: list[tuple], paper: str) -> list[tuple[int, int]] | None:
    """Top-left first fit of frames (w, h) on the page, clear of `occupied` boxes, the border
    and the title block; None when they do not fit."""
    W, H = _page(paper)
    title = (W - 120 / GRID - 1, H - 45 / GRID - 1, W, H)
    rects = [*occupied, title]
    out = []
    for w, h in sizes:
        xs = sorted({MARGIN} | {math.ceil(r[2]) + BLOCK_GAP for r in rects})
        ys = sorted({MARGIN} | {math.ceil(r[3]) + BLOCK_GAP for r in rects})
        spot = None
        for y in ys:
            if y + h > H - MARGIN:
                break
            for x in xs:
                if x + w > W - MARGIN:
                    break
                c = (x, y, x + w, y + h)
                if not any(_hits(c, r, BLOCK_GAP - 0.01) for r in rects):
                    spot = (x, y)
                    break
            if spot:
                break
        if spot is None:
            return None
        out.append(spot)
        rects.append((spot[0], spot[1], spot[0] + w, spot[1] + h))
    return out


PAPERS = ("A5", "A4", "A3", "A2", "A1", "A0")


def _units(sizes: list[tuple[int, int]], groups: list[int], width: float) -> list[tuple[int, int, list]]:
    """Frames to pack as units: a run of identical blocks (same group number) becomes one
    unit, its blocks side by side in as few rows as fit the page width, all rows alike."""
    out, i = [], 0
    while i < len(sizes):
        j = i
        while j + 1 < len(sizes) and groups[j + 1] == groups[i] and sizes[j + 1] == sizes[i]:
            j += 1
        n, (w, h) = j - i + 1, sizes[i]
        kmax = max(1, min(n, int((width + BLOCK_GAP) // (w + BLOCK_GAP))))
        rows = math.ceil(n / kmax)
        k = math.ceil(n / rows)
        offs = [((c % k) * (w + BLOCK_GAP), (c // k) * (h + BLOCK_GAP)) for c in range(n)]
        out.append((k * w + (k - 1) * BLOCK_GAP, rows * h + (rows - 1) * BLOCK_GAP, offs))
        i = j + 1
    return out


def choose_paper(sizes, occupied, start: str | None, groups: list[int] | None = None) -> tuple[str, list]:
    """The smallest standard paper (from `start`) whose page the frames fill to 70 % at most
    and fit on; identical blocks (same number in groups) side by side."""
    groups = groups or list(range(len(sizes)))
    area = sum(w * h for w, h in sizes) + sum((r[2] - r[0]) * (r[3] - r[1]) for r in occupied)
    papers = PAPERS[PAPERS.index(start) :] if start in PAPERS else PAPERS
    for paper in papers:
        W, H = _page(paper)
        usable = (W - 2 * MARGIN) * (H - 2 * MARGIN) - (120 / GRID) * (45 / GRID)
        if area > 0.7 * usable and paper != papers[-1]:
            continue
        units = _units(sizes, groups, W - 2 * MARGIN)
        spots = pack([(w, h) for w, h, _ in units], occupied, paper)
        if spots is not None:
            out = [(x + dx, y + dy) for (x, y), (_, _, offs) in zip(spots, units, strict=True) for dx, dy in offs]
            return paper, out
    raise RuntimeError("the sheet does not fit on A0")


@dataclass
class Draft:
    data: dict  # placement-file data drafted: blocks, sheet symbols, ports, paper, title
    auto: list[str]  # parts and sheet symbols it places
    notes: list[str] = field(default_factory=list)


def draft_sheet(board: str, path: Path, text: str, pin_net: dict, hand: dict, everything: bool = False) -> Draft | None:
    """Draft what the hand entries of a sheet leave out (everything: the whole sheet, ignoring
    them). Returns None when nothing is missing."""
    from .placement import spec_from_data

    m = Model(board, path, text, pin_net)
    hand = {} if everything else hand
    spec = spec_from_data(hand, path.name)
    missing = sorted(r for r in m.parts if r not in spec.parts)
    sheet_names = [n.prop("Sheetname") or "" for n in m.sheet.root.children("sheet")]
    missing_sheets = [s for s in sheet_names if s not in spec.sheets]
    if not missing and not missing_sheets:
        return None
    zen = sheet_module(board, path.stem)
    hints = read_hints(zen)
    notes = hint_problems(hints, set(m.parts))
    if notes:
        raise ValueError("; ".join(notes))
    ranks = source_ranks(zen, list(m.parts))
    plans = assign_blocks(m, missing, hints, ranks)
    blocks: list[dict] = []
    seen: dict = {}
    groups: list[int] = []
    laid: list[Block] = []
    for plan in plans:
        sig = _signature(m, plan)
        like = None
        if sig in seen:
            first_plan, first_blk, _ = seen[sig]
            like = (first_blk, dict(zip(first_plan.refs, plan.refs, strict=True)))
        blk = layout_block(m, plan, hints, ranks, like)
        laid.append(blk)
        seen.setdefault(sig, (plan, blk, len(seen)))
        groups.append(seen[sig][2])
        blocks.append(block_data(blk))
    _equal_frames(blocks, groups)
    data: dict = {}
    if not hand.get("title"):
        data["title"] = hints.get("title") or module_title(zen) or path.stem
    sizes = [tuple(b["size"]) for b in blocks]
    syms = sheet_symbols(m, board, missing_sheets)
    sym_block = None
    if syms:
        w = max(s["ext"][0] + s["size"][0] + s["ext"][1] for s in syms) + 2 * PAD
        h = PAD + TITLE_H + sum(s["size"][1] + 5 for s in syms) + PAD
        sym_block = {"title": "Module sheets", "at": [0, 0], "size": [w, h], "auto": True}
        sizes.append((w, h))
    ports = None
    entries = ports_entries(m, laid)
    if entries and "ports" not in hand:
        pw, ph, rows = ports_size(entries)
        ports = {"rows": rows, "title": "Sheet ports"}
        sizes.append((pw, ph))
    occupied = (
        hand_occupied(board, path, text, pin_net, hand, missing, missing_sheets) if (spec.parts or spec.sheets) else []
    )
    start = hints.get("paper") or (hand.get("paper") if spec.parts else None)
    groups += [-1 - i for i in range(len(sizes) - len(groups))]
    paper, spots = choose_paper(sizes, occupied, start, groups)
    if hand.get("paper") != paper:
        data["paper"] = paper
    for b, (x, y) in zip(blocks, spots, strict=False):
        b["at"] = [x, y]
    i = len(blocks)
    if sym_block:
        x, y = spots[i]
        i += 1
        sym_block["at"] = [x, y]
        blocks.append(sym_block)
        yy = y + PAD + TITLE_H + 1
        data["sheet"] = {}
        for s in syms:
            data["sheet"][s["name"]] = {
                "at": [x + PAD + s["ext"][0], yy],
                "size": s["size"],
                "left": s["left"],
                "right": s["right"],
                "auto": True,
            }
            yy += s["size"][1] + 5
    if ports:
        x, y = spots[i]
        data["ports"] = {"at": [x, y], **ports}
    data["block"] = blocks
    auto = missing + [f"sheet {s}" for s in missing_sheets]
    return Draft(data, auto)


def hand_occupied(board, path, text, pin_net, hand, missing, missing_sheets) -> list[tuple]:
    """Boxes (grid units) of what the hand entries draw: their frames, and every item outside a
    frame, so the drafted blocks go around them."""
    from .placement import PartSpec as PS
    from .placement import Placer as P
    from .placement import spec_from_data
    from .schematic import Sheet

    spec = spec_from_data(hand, path.name)
    for r in missing:
        spec.parts[r] = PS(at=(5000.0, 5000.0))
    placer = P(board, path, text, spec, pin_net)
    placed = Sheet.load(path, placer.place())
    texts, bodies, lines = schlint.collect(placed)
    frames = [(x0 / GRID, y0 / GRID, x1 / GRID, y1 / GRID) for _, x0, y0, x1, y1 in spec.frames]
    out = list(frames)
    for b in [*texts, *bodies]:
        r = (b.x0 / GRID, b.y0 / GRID, b.x1 / GRID, b.y1 / GRID)
        if r[0] > 3000 or any(b.owner == f"sheet:{s}" for s in missing_sheets):
            continue
        if not any(f[0] <= r[0] and f[1] <= r[1] and r[2] <= f[2] and r[3] <= f[3] for f in frames):
            out.append(r)
    for ln in lines:
        r = (
            min(ln.a[0], ln.b[0]) / GRID,
            min(ln.a[1], ln.b[1]) / GRID,
            max(ln.a[0], ln.b[0]) / GRID,
            max(ln.a[1], ln.b[1]) / GRID,
        )
        if r[0] > 3000 or ln.owner == "frame":
            continue
        if not any(f[0] <= r[0] and f[1] <= r[1] and r[2] <= f[2] and r[3] <= f[3] for f in frames):
            out.append(r)
    return out
