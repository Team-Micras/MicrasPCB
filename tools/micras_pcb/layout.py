"""Read-only view of a .kicad_pcb for the layout-aware design tests: footprints, pads, outline.

from micras_pcb import layout
pcb = layout.load_file(path)             # or layout.load("main")
pcb.footprints["C12"].pads[0].xy         # absolute pad centre, mm, KiCad frame (y down)
pcb.placed                               # False until the board has an Edge.Cuts outline
pcb.tracks[0].start                      # copper track segments and arcs, mm; pcb.vias
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
    courtyard: list[tuple[float, float]] = field(default_factory=list)  # local points of the courtyard graphics

    def courtyard_box(self) -> tuple[float, float, float, float] | None:
        """The courtyard's bounding box on the board (KiCad frame: x0, y0, x1, y1), or None."""
        if not self.courtyard:
            return None
        pts = [_rotate(x, y, self.rotation) for x, y in self.courtyard]
        xs = [self.xy[0] + x for x, _ in pts]
        ys = [self.xy[1] + y for _, y in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def pasted(self, pad: Pad) -> bool:
        """The pad gets solder paste: its own opening (not cancelled by a negative paste margin), or a
        paste shape over it: drawn on the footprint's paste layer, or a paste-only pad (the KiCad
        library's way of splitting a stencil aperture from its copper pad, or an exposed pad's paste
        into windows around its centre)."""
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
        hw, hh = pad.size[0] / 2, pad.size[1] / 2
        return any(x0 < x + hw and x - hw < x1 and y0 < y + hh and y - hh < y1 for x0, y0, x1, y1 in boxes)

    def pads_named(self, number: str) -> list[Pad]:
        return [p for p in self.pads if p.number == number]

    @property
    def assembled(self) -> bool:
        """Placed by the assembler: not board-only copper, not excluded from the BOM, not DNP."""
        return not ({"board_only", "exclude_from_bom", "dnp"} & self.attributes)


@dataclass
class Track:
    kind: str  # "segment" or "arc"
    net: str
    layer: str
    start: tuple[float, float]
    end: tuple[float, float]
    width: float = 0.0


@dataclass
class Via:
    net: str
    xy: tuple[float, float]
    size: float  # copper diameter


@dataclass
class Board:
    footprints: dict[str, Footprint]
    edge_shapes: list[tuple[str, list[tuple[float, float]], float | None]]  # (kind, points, radius)
    embedded_files: set[str]
    tracks: list[Track] = field(default_factory=list)
    vias: list[Via] = field(default_factory=list)

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
    court = []
    for head in GRAPHICS:
        for g in fp.children(head):
            if g.child("layer"):
                glayers.add(g.child("layer").atoms()[0])
                if g.child("layer").atoms()[0] in COURTYARD:
                    court += [_xy(g.child(k)) for k in ("start", "end", "mid") if g.child(k)]
                    if g.child("pts"):
                        court += [_xy(q) for q in g.child("pts").children("xy")]
                    if head == "fp_rect" and g.child("start") and g.child("end"):
                        (x0, y0), (x1, y1) = _xy(g.child("start")), _xy(g.child("end"))
                        court += [(x0, y1), (x1, y0)]
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
        courtyard=court,
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
    tracks = []
    for head in ("segment", "arc"):
        for t in root.children(head):
            net = t.child("net")
            tracks.append(
                Track(
                    kind=head,
                    net=net.atoms()[-1] if net else "",
                    layer=t.child("layer").atoms()[0],
                    start=_xy(t.child("start")),
                    end=_xy(t.child("end")),
                    width=float(t.child("width").atoms()[0]) if t.child("width") else 0.0,
                )
            )
    vias = [
        Via(
            net=v.child("net").atoms()[-1] if v.child("net") else "",
            xy=_xy(v.child("at")),
            size=float(v.child("size").atoms()[0]),
        )
        for v in root.children("via")
    ]
    return Board(footprints=fps, edge_shapes=edges, embedded_files=embedded, tracks=tracks, vias=vias)


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


def part_heights(path: Path, thickness: float) -> dict[str, float]:
    """Each part's height above the board's top face (mm), from the 3D models: the tops of the
    meshes of a KiCad GLB export (kicad-cli), whose nodes carry the reference designators."""
    import json
    import struct
    import subprocess
    import tempfile

    from .tools import kicad_cli

    with tempfile.TemporaryDirectory() as d:
        glb = Path(d) / "board.glb"
        cmd = [kicad_cli(), "pcb", "export", "glb", "-f", "--no-board-body", "-o", str(glb), str(path)]
        subprocess.run(cmd, check=True, capture_output=True)
        data = glb.read_bytes()
    n = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20 : 20 + n])
    nodes, accessors = gltf["nodes"], gltf["accessors"]

    def mul(a, b):
        return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]

    def matrix(node):
        if "matrix" in node:
            m = node["matrix"]  # column-major
            return [[m[j * 4 + i] for j in range(4)] for i in range(4)]
        x, y, z, w = node.get("rotation", [0, 0, 0, 1])
        sx, sy, sz = node.get("scale", [1, 1, 1])
        tx, ty, tz = node.get("translation", [0, 0, 0])
        r = [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
        return [
            [r[0][0] * sx, r[0][1] * sy, r[0][2] * sz, tx],
            [r[1][0] * sx, r[1][1] * sy, r[1][2] * sz, ty],
            [r[2][0] * sx, r[2][1] * sy, r[2][2] * sz, tz],
            [0, 0, 0, 1],
        ]

    top: dict[str, float] = {}
    stack = [(i, [[float(i == j) for j in range(4)] for i in range(4)], None) for i in gltf["scenes"][0]["nodes"]]
    while stack:
        i, m, ref = stack.pop()
        node = nodes[i]
        m = mul(m, matrix(node))
        name = node.get("name") or ""
        if ref is None and name and not name.startswith("=>"):
            ref = name
        if "mesh" in node and ref:
            for prim in gltf["meshes"][node["mesh"]]["primitives"]:
                a = accessors[prim["attributes"]["POSITION"]]
                lo, hi = a["min"], a["max"]
                for x in (lo[0], hi[0]):
                    for y in (lo[1], hi[1]):
                        for z in (lo[2], hi[2]):
                            up = m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3]  # glTF: y up, metres
                            top[ref] = max(top.get(ref, -1.0), up)
        stack += [(c, m, ref) for c in node.get("children", [])]
    return {ref: round(v * 1000 - thickness, 3) for ref, v in top.items()}
