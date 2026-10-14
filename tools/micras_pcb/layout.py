"""Read-only view of a .kicad_pcb for the layout-aware design tests: footprints, pads, outline.

from micras_pcb import layout
pcb = layout.load_file(path)             # or layout.load("main")
pcb.footprints["C12"].pads[0].xy         # absolute pad centre, mm, KiCad frame (y down)
pcb.placed                               # False until the board has an Edge.Cuts outline
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from . import sexpr
from .paths import board_pcb

COURTYARD = {"F.CrtYd", "B.CrtYd"}
PASTE = {"F.Paste", "B.Paste", "*.Paste"}
GRAPHICS = ("fp_line", "fp_rect", "fp_circle", "fp_arc", "fp_poly")


@dataclass
class Pad:
    number: str
    net: str | None
    kind: str  # smd, thru_hole, np_thru_hole, connect
    layers: list[str]
    xy: tuple[float, float]
    size: tuple[float, float]
    local: tuple[float, float] = (0.0, 0.0)  # centre in footprint coordinates
    paste_margin: float = 0.0
    paste_ratio: float = 0.0


@dataclass
class Footprint:
    ref: str
    lib_id: str
    xy: tuple[float, float]
    rotation: float
    side: str  # "top" or "bottom"
    attributes: set[str]
    graphic_layers: set[str]
    pads: list[Pad] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    paste_boxes: list[tuple[float, float, float, float]] = field(default_factory=list)  # local x0, y0, x1, y1

    def pasted(self, pad: Pad) -> bool:
        """The pad gets solder paste: its own opening (not cancelled by a negative paste margin), or a
        paste shape over its centre: drawn on the footprint's paste layer, or a paste-only pad (the
        KiCad library's way of splitting a stencil aperture from its copper pad)."""
        if set(pad.layers) & PASTE:
            half = [d / 2 * (1 + pad.paste_ratio) + pad.paste_margin for d in pad.size]
            if min(half) > 0:
                return True
        x, y = pad.local
        boxes = list(self.paste_boxes)
        for q in self.pads:
            if q.layers and set(q.layers) <= PASTE:
                hx, hy = (d / 2 * (1 + q.paste_ratio) + q.paste_margin for d in q.size)
                if min(hx, hy) > 0:
                    boxes.append((q.local[0] - hx, q.local[1] - hy, q.local[0] + hx, q.local[1] + hy))
        return any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in boxes)

    def pads_named(self, number: str) -> list[Pad]:
        return [p for p in self.pads if p.number == number]

    @property
    def assembled(self) -> bool:
        """Placed by the assembler: not board-only copper, not excluded from the BOM, not DNP."""
        return not ({"board_only", "exclude_from_bom", "dnp"} & self.attributes)


@dataclass
class Board:
    footprints: dict[str, Footprint]
    edge_shapes: list[tuple[str, list[tuple[float, float]], float | None]]  # (kind, points, radius)
    embedded_files: set[str]

    @property
    def placed(self) -> bool:
        """The layout has an outline: until then placement is the tool's packing, not a design."""
        return bool(self.edge_shapes)


def _xy(node) -> tuple[float, float]:
    a = node.atoms()
    return float(a[0]), float(a[1])


def _rotate(x: float, y: float, deg: float) -> tuple[float, float]:
    """KiCad rotates counter-clockwise on screen, with y pointing down."""
    t = math.radians(deg)
    return x * math.cos(t) + y * math.sin(t), -x * math.sin(t) + y * math.cos(t)


def _footprint(fp) -> Footprint:
    at = fp.child("at").atoms()
    fx, fy = float(at[0]), float(at[1])
    rot = float(at[2]) if len(at) > 2 else 0.0
    layer = fp.child("layer").atoms()[0]
    attr = set(fp.child("attr").atoms()) if fp.child("attr") else set()
    glayers = set()
    paste_boxes = []
    for head in GRAPHICS:
        for g in fp.children(head):
            if g.child("layer"):
                glayers.add(g.child("layer").atoms()[0])
                if g.child("layer").atoms()[0] in PASTE:
                    pts = [_xy(g.child(k)) for k in ("start", "end", "center", "mid") if g.child(k)]
                    if g.child("pts"):
                        pts += [_xy(q) for q in g.child("pts").children("xy")]
                    if head == "fp_circle" and len(pts) >= 2:
                        r = math.dist(pts[0], pts[1])
                        pts = [(pts[0][0] - r, pts[0][1] - r), (pts[0][0] + r, pts[0][1] + r)]
                    if pts:
                        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
                        paste_boxes.append((min(xs), min(ys), max(xs), max(ys)))
    out = Footprint(
        ref=fp.prop("Reference") or "",
        lib_id=fp.atoms()[0] if fp.atoms() else "",
        xy=(fx, fy),
        rotation=rot,
        side="bottom" if layer.startswith("B.") else "top",
        attributes=attr,
        graphic_layers=glayers,
        paste_boxes=paste_boxes,
    )
    for pad in fp.children("pad"):
        a = pad.atoms()
        px, py = _xy(pad.child("at"))
        dx, dy = _rotate(px, py, rot)
        size = _xy(pad.child("size")) if pad.child("size") else (0.0, 0.0)
        net = pad.child("net")
        out.pads.append(
            Pad(
                number=a[0] if a else "",
                net=net.atoms()[-1] if net else None,
                kind=a[1] if len(a) > 1 else "",
                layers=pad.child("layers").atoms() if pad.child("layers") else [],
                xy=(fx + dx, fy + dy),
                size=size,
                local=(px, py),
                paste_margin=float(pad.child("solder_paste_margin").atoms()[0])
                if pad.child("solder_paste_margin")
                else 0.0,
                paste_ratio=float(pad.child("solder_paste_margin_ratio").atoms()[0])
                if pad.child("solder_paste_margin_ratio")
                else 0.0,
            )
        )
    out.models = [m.atoms()[0] for m in fp.children("model") if m.atoms()]
    return out


def parse(text: str) -> Board:
    root = sexpr.parse(text)
    fps = {}
    for fp in root.children("footprint"):
        f = _footprint(fp)
        fps[f.ref or f"#{len(fps)}"] = f
    edges = []
    for head in ("gr_line", "gr_arc", "gr_rect", "gr_circle", "gr_poly"):
        for g in root.children(head):
            if not g.child("layer") or g.child("layer").atoms()[0] != "Edge.Cuts":
                continue
            pts = [_xy(g.child(k)) for k in ("start", "mid", "end", "center") if g.child(k)]
            if g.child("pts"):
                pts += [_xy(p) for p in g.child("pts").children("xy")]
            radius = None
            if head == "gr_arc":
                radius = _arc_radius(*pts[:3])
            edges.append((head, pts, radius))
    embedded = set()
    ef = root.child("embedded_files")
    if ef:
        embedded = {f.child("name").atoms()[0] for f in ef.children("file") if f.child("name")}
    return Board(footprints=fps, edge_shapes=edges, embedded_files=embedded)


def _arc_radius(a, m, b) -> float:
    """Radius of the circle through three points."""
    ax, ay = a
    bx, by = m
    cx, cy = b
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    ux = ((ax**2 + ay**2) * (by - cy) + (bx**2 + by**2) * (cy - ay) + (cx**2 + cy**2) * (ay - by)) / d
    uy = ((ax**2 + ay**2) * (cx - bx) + (bx**2 + by**2) * (ax - cx) + (cx**2 + cy**2) * (bx - ax)) / d
    return math.dist((ux, uy), a)


def load_file(path: Path) -> Board:
    return parse(Path(path).read_text())


def load(board: str) -> Board:
    return load_file(board_pcb(board))
