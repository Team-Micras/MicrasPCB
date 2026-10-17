"""A KiCad schematic sheet as geometry: placed symbols with their pins, labels, wires, sheet
symbols, and the connectivity KiCad derives from them.

Coordinates are page millimetres, y down. A library symbol is drawn in library coordinates (y up);
KiCad flips y, then rotates by the symbol's angle, then mirrors (pcb-kicad-sch symbol.rs
transform_vector). KiCad connects items only at wire ends, pin ends, label anchors and
junctions, and a point lying inside a wire segment (KiCad's connectivity, which `pcb apply`
mirrors in pcb-kicad-sch connectivity/).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import sexpr

GRID = 1.27
EPS = 1e-4
LABEL_HEADS = ("label", "global_label", "hierarchical_label")

# Direction unit vectors (page coordinates, y down) and KiCad's label angles for each.
RIGHT, UP, LEFT, DOWN = (1, 0), (0, -1), (-1, 0), (0, 1)
ANGLE_OF = {RIGHT: 0, UP: 90, LEFT: 180, DOWN: 270}
DIR_OF = {v: k for k, v in ANGLE_OF.items()}


# KiCad's named paper sizes in mm, landscape (common/page_info.cpp).
PAPER = {
    "A5": (210, 148),
    "A4": (297, 210),
    "A3": (420, 297),
    "A2": (594, 420),
    "A1": (841, 594),
    "A0": (1189, 841),
    "A": (279.4, 215.9),
    "B": (431.8, 279.4),
    "C": (558.8, 431.8),
    "D": (863.6, 558.8),
    "E": (1117.6, 863.6),
    "USLetter": (279.4, 215.9),
    "USLegal": (355.6, 215.9),
    "USLedger": (431.8, 279.4),
    "GERBER": (812.8, 812.8),
}


# Advance widths of KiCad's newstroke font, U+0020 to U+007E, in 1/21 of the text size
# (common/newstroke_font.cpp, the first two characters of each glyph).
_ADVANCE = [
    16, 10, 16, 21, 20, 24, 26, 10, 14, 14, 16, 26, 10, 26, 10, 22, 20, 20, 20, 20, 20, 20, 20, 20,
    20, 20, 10, 10, 26, 26, 26, 18, 27, 18, 21, 21, 21, 19, 18, 21, 22, 10, 16, 21, 17, 24, 22, 22,
    21, 22, 21, 20, 16, 22, 18, 24, 20, 18, 20, 14, 14, 14, 12, 16, 8, 19, 19, 18, 19, 18, 12, 19,
    19, 10, 10, 17, 11, 28, 19, 19, 19, 19, 13, 17, 12, 19, 16, 22, 17, 16, 17, 14, 20, 14, 15,
]  # fmt: skip


def text_width(text: str, size: float = 1.27) -> float:
    """Width of a text in KiCad's stroke font, mm."""
    return sum(_ADVANCE[ord(c) - 32] if 32 <= ord(c) < 127 else 21 for c in text) / 21 * size


def paper_size(sch: sexpr.Node) -> tuple[float, float]:
    """A sheet's paper (width, height) in mm, as oriented."""
    paper = sch.child("paper")
    atoms = paper.atoms() if paper else ["A4"]
    if atoms[0] == "User":
        w, h = float(atoms[1]), float(atoms[2])
    else:
        w, h = PAPER[atoms[0]]
    return (h, w) if "portrait" in atoms else (w, h)


def key(p: tuple[float, float]) -> tuple[int, int]:
    """A point as integer KiCad schematic units (100 nm), for exact comparisons."""
    return round(p[0] * 10000), round(p[1] * 10000)


def transform(v: tuple[float, float], rot: int, mirror: str | None) -> tuple[float, float]:
    """A page-space vector through a symbol's rotation, then its mirror."""
    x, y = v
    x, y = {0: (x, y), 90: (y, -x), 180: (-x, -y), 270: (-y, x)}[rot % 360]
    if mirror == "x":
        y = -y
    elif mirror == "y":
        x = -x
    return x, y


def xy(node: sexpr.Node) -> tuple[float, float]:
    a = node.atoms()
    return float(a[0]), float(a[1])


@dataclass
class LibPin:
    number: str
    name: str
    etype: str
    at: tuple[float, float]  # connection point, library coordinates (y up)
    angle: int  # direction from the connection point into the body
    length: float
    hidden: bool


@dataclass
class LibSymbol:
    name: str
    node: sexpr.Node
    pins: list[LibPin]
    body: list[tuple[float, float]]  # graphic points, library coordinates
    power: bool
    name_offset: float | None  # pin names drawn inside the body at this offset; None: not drawn
    jumpers: list[set[str]] = field(default_factory=list)  # pin numbers joined inside the part

    @classmethod
    def parse(cls, node: sexpr.Node) -> LibSymbol:
        pins, body = [], []
        for sub in node.children("symbol"):
            unit, style = sub.atoms()[0].rsplit("_", 2)[1:]
            if int(style) not in (0, 1) or int(unit) not in (0, 1):
                continue
            for g in sub.children():
                if g.head == "pin":
                    at = g.child("at").atoms()
                    hide = g.child("hide")
                    pins.append(
                        LibPin(
                            number=g.child("number").atoms()[0],
                            name=g.child("name").atoms()[0],
                            etype=g.atoms()[0],
                            at=(float(at[0]), float(at[1])),
                            angle=int(float(at[2])) if len(at) > 2 else 0,
                            length=float(g.child("length").atoms()[0]),
                            hidden=bool(hide and hide.atoms() in (["yes"], [])) or "hide" in g.atoms(),
                        )
                    )
                elif g.head == "rectangle":
                    body += [xy(g.child("start")), xy(g.child("end"))]
                elif g.head in ("polyline", "bezier"):
                    body += [xy(p) for p in g.child("pts").children("xy")]
                elif g.head == "arc":
                    body += [xy(g.child(k)) for k in ("start", "mid", "end")]
                elif g.head == "circle":
                    (cx, cy), r = xy(g.child("center")), float(g.child("radius").atoms()[0])
                    body += [(cx - r, cy - r), (cx + r, cy + r)]
        names = node.child("pin_names")
        offset = 0.508
        if names is not None:
            hide = names.child("hide")
            if (hide and hide.atoms() in (["yes"], [])) or "hide" in names.atoms():
                offset = None
            elif names.child("offset"):
                offset = float(names.child("offset").atoms()[0])
        if offset == 0:
            offset = None  # drawn above the pin line, outside the body: short names on small parts
        groups = node.child("jumper_pin_groups")
        jumpers = [set(g.items) for g in groups.children()] if groups else []
        return cls(node.atoms()[0], node, pins, body, node.child("power") is not None, offset, jumpers)


@dataclass
class Pin:
    ref: str
    number: str
    name: str
    etype: str
    at: tuple[float, float]  # connection point, page coordinates
    out: tuple[int, int]  # unit vector pointing away from the body
    hidden: bool

    @property
    def id(self) -> str:
        return f"{self.ref}.{self.number}"


@dataclass
class Symbol:
    node: sexpr.Node
    lib: LibSymbol
    at: tuple[float, float]
    rot: int
    mirror: str | None

    @property
    def ref(self) -> str:
        return self.node.prop("Reference") or ""

    @property
    def value(self) -> str:
        return self.node.prop("Value") or ""

    @property
    def power(self) -> bool:
        return self.lib.power

    def page(self, p: tuple[float, float]) -> tuple[float, float]:
        x, y = transform((p[0], -p[1]), self.rot, self.mirror)
        return self.at[0] + x, self.at[1] + y

    def pins(self) -> list[Pin]:
        out = []
        for lp in self.lib.pins:
            ix, iy = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}[lp.angle % 360]
            dx, dy = transform((-ix, iy), self.rot, self.mirror)  # outward, page coordinates
            out.append(Pin(self.ref, lp.number, lp.name, lp.etype, self.page(lp.at), (round(dx), round(dy)), lp.hidden))
        return out

    def body(self) -> tuple[float, float, float, float] | None:
        """The body graphics' bounding box (x0, y0, x1, y1), without pins and fields."""
        pts = [self.page(p) for p in self.lib.body]
        if not pts:
            return None
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)


@dataclass
class Label:
    node: sexpr.Node
    kind: str  # label, global_label, hierarchical_label
    text: str
    at: tuple[float, float]
    angle: int

    @property
    def shape(self) -> str | None:
        s = self.node.child("shape")
        return s.atoms()[0] if s else None


@dataclass
class SheetPin:
    sheet: str  # Sheetname
    name: str
    at: tuple[float, float]


@dataclass
class Sheet:
    path: Path
    text: str
    root: sexpr.Node
    libs: dict[str, LibSymbol]
    symbols: list[Symbol]
    labels: list[Label]
    wires: list[tuple[tuple[float, float], tuple[float, float]]]
    junctions: list[tuple[float, float]]
    no_connects: list[tuple[float, float]]
    sheet_pins: list[SheetPin]

    @classmethod
    def load(cls, path: Path, text: str | None = None) -> Sheet:
        text = path.read_text() if text is None else text
        root = sexpr.parse(text)
        libs = {}
        if root.child("lib_symbols"):
            libs = {s.atoms()[0]: LibSymbol.parse(s) for s in root.child("lib_symbols").children("symbol")}
        symbols, labels, wires, junctions, ncs, spins = [], [], [], [], [], []
        for n in root.children():
            if n.head == "symbol":
                at = n.child("at").atoms()
                m = n.child("mirror")
                symbols.append(
                    Symbol(
                        n,
                        libs[n.child("lib_id").atoms()[0]],
                        (float(at[0]), float(at[1])),
                        int(float(at[2])) % 360 if len(at) > 2 else 0,
                        m.atoms()[0] if m else None,
                    )
                )
            elif n.head in LABEL_HEADS:
                at = n.child("at").atoms()
                labels.append(Label(n, n.head, n.atoms()[0], (float(at[0]), float(at[1])), int(float(at[2])) % 360))
            elif n.head == "wire":
                a, b = (xy(p) for p in n.child("pts").children("xy"))
                wires.append((a, b))
            elif n.head == "junction":
                junctions.append(xy(n.child("at")))
            elif n.head == "no_connect":
                ncs.append(xy(n.child("at")))
            elif n.head == "sheet":
                name = n.prop("Sheetname") or ""
                spins += [SheetPin(name, p.atoms()[0], xy(p.child("at"))) for p in n.children("pin")]
        return cls(path, text, root, libs, symbols, labels, wires, junctions, ncs, spins)

    def parts(self) -> list[Symbol]:
        return [s for s in self.symbols if not s.power]


def on_segment(p, a, b) -> bool:
    """p lies on the axis-aligned or diagonal segment a-b (ends included)."""
    (px, py), (ax, ay), (bx, by) = key(p), key(a), key(b)
    if (bx - ax) * (py - ay) != (by - ay) * (px - ax):
        return False
    return min(ax, bx) <= px <= max(ax, bx) and min(ay, by) <= py <= max(ay, by)


@dataclass
class Island:
    """Items KiCad connects on one sheet."""

    pins: list[Pin] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    power: list[Symbol] = field(default_factory=list)
    sheet_pins: list[SheetPin] = field(default_factory=list)
    no_connect: bool = False
    wires: list[int] = field(default_factory=list)

    def drivers(self) -> set[tuple[str, str, str | None]]:
        """The island's name drivers: (kind, text, label shape or power library symbol)."""
        out = {(lb.kind, lb.text, lb.shape) for lb in self.labels}
        out |= {("power", p.value, p.lib.name) for p in self.power}
        return out


def islands(sheet: Sheet) -> list[Island]:
    """Connected groups of a sheet's items. Wires join at their ends and at any connection point
    lying inside them; pins, labels, power pins, sheet pins and no-connect flags join at a point."""
    parent: dict = {}

    def find(k):
        while parent.setdefault(k, k) != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    def union(a, b):
        parent[find(a)] = find(b)

    points: list[tuple[float, float]] = []
    pins = [p for s in sheet.symbols if not s.power for p in s.pins()]
    power_pins = [(s, p) for s in sheet.symbols if s.power for p in s.pins()]
    points += [p.at for p in pins] + [p.at for _, p in power_pins] + [lb.at for lb in sheet.labels]
    points += [sp.at for sp in sheet.sheet_pins] + sheet.no_connects + sheet.junctions
    points += [e for w in sheet.wires for e in w]
    for i, (a, b) in enumerate(sheet.wires):
        union(("w", i), key(a))
        union(("w", i), key(b))
        for p in points:
            if on_segment(p, a, b):
                union(("w", i), key(p))
    groups: dict = {}

    def isl(p) -> Island:
        return groups.setdefault(find(key(p)), Island())

    for p in pins:
        isl(p.at).pins.append(p)
    for s, p in power_pins:
        isl(p.at).power.append(s)
    for lb in sheet.labels:
        isl(lb.at).labels.append(lb)
    for sp in sheet.sheet_pins:
        isl(sp.at).sheet_pins.append(sp)
    for nc in sheet.no_connects:
        isl(nc).no_connect = True
    for i, (a, _) in enumerate(sheet.wires):
        isl(a).wires.append(i)
    return list(groups.values())
