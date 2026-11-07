"""Apply a board's mechanical spec to its KiCad layout, and export it for the other repos.

The spec owns the aux/grid origin and the position of the footprints it names (written locked),
and the Edge.Cuts outline of the boards in `OUTLINES`. The layout's zones are written in a
canonical order (`zone_order`), so a regeneration is byte-stable. The other boards' outlines are layout
geometry (the boards keep their previous revisions'): the spec checks the features other parts
mate with (`FEATURES`). KiCad owns everything else: the remaining placement, routing and zones.

    micras-pcb mech encoder            # apply spec/encoder.toml to the layout, export the mech JSON
    micras-pcb mech encoder --check    # fail if the layout drifted from the spec (CI)
"""

from __future__ import annotations

import bisect
import json
import math
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import sexpr, spec
from .paths import board_pcb, build_dir

_NS = uuid.UUID("6f1f3c2e-8a51-4f0e-9a52-6d1c2a7e0b10")  # stable UUIDs for generated items
EDGE_WIDTH = 0.05


@dataclass
class Line:
    a: tuple[float, float]
    b: tuple[float, float]


@dataclass
class Arc:
    a: tuple[float, float]
    mid: tuple[float, float]
    b: tuple[float, float]


@dataclass
class Bezier:
    a: tuple[float, float]
    c1: tuple[float, float]
    c2: tuple[float, float]
    b: tuple[float, float]


def encoder_outline(s: dict) -> list:
    """Closed outline in the spec frame (u right, v up), counter-clockwise from the tab."""
    o, t = s["outline"], s["tab"]
    hw, top, r = o["width"] / 2, o["top"], o["corner_radius"]
    hb, ts = o["base_width"] / 2, o["taper_start"]
    ht, d, rr = t["width"] / 2, t["depth"], t["relief_radius"]
    c45 = r * (1 - math.sqrt(0.5))
    right = [
        Line((-ht, -d), (ht, -d)),
        Line((ht, -d), (ht, 0)),
        Arc((ht, 0), (ht + rr, rr), (ht + 2 * rr, 0)),
        Line((ht + 2 * rr, 0), (hb, 0)),
        # vertical tangents at both ends, both control points at taper_control
        Bezier((hb, 0), (hb, o["taper_control"]), (hw, o["taper_control"]), (hw, ts)),
        Line((hw, ts), (hw, top - r)),
        Arc((hw, top - r), (hw - c45, top - c45), (hw - r, top)),
    ]
    left = [_mirror(e) for e in reversed(right[1:])]
    return [*right, Line((hw - r, top), (-(hw - r), top)), *left]


def wall_outline(s: dict) -> list:
    """The wall board's Edge.Cuts in its spec frame (u right, v up), a paddle: the straight bottom
    edge that rests on the header's insulator, the handle's sides, the neck (an inside arc tangent
    to the handle's side, then a long outside arc tangent to the blade's side at neck_top), the
    blade's sides and rounded top corners; counter-clockwise from the bottom edge."""
    o, se = s["outline"], s["sensor"]
    hw, bottom, top, r = o["width"] / 2, o["bottom"], o["top"], o["corner_radius"]
    au = se["u"]
    n = wall_neck(s)
    hh, ht, t = o["handle_width"] / 2, n["handle_top"], n["tangent"]

    def mid(c, rad, a, b):
        """The midpoint of the shorter arc of circle (c, rad) from a to b."""
        m = ((a[0] + b[0]) / 2 - c[0], (a[1] + b[1]) / 2 - c[1])
        k = math.hypot(*m)
        return (c[0] + m[0] / k * rad, c[1] + m[1] / k * rad)

    c45 = math.sqrt(0.5)
    vt = o["neck_top"]
    right = [
        Line((au - hh, bottom), (au + hh, bottom)),
        Line((au + hh, bottom), (au + hh, ht)),
        Arc((au + hh, ht), mid(n["inside_centre"], o["neck_inside_radius"], (au + hh, ht), t), t),
        Arc(t, mid(n["outside_centre"], o["neck_radius"], t, (au + hw, vt)), (au + hw, vt)),
        Line((au + hw, vt), (au + hw, top - r)),
        Arc((au + hw, top - r), (au + hw - r * (1 - c45), top - r * (1 - c45)), (au + hw - r, top)),
    ]
    left = [_mirror(e) for e in reversed(right[1:])]
    return [*right, Line((au + hw - r, top), (au - (hw - r), top)), *left]


def wall_neck(s: dict) -> dict:
    """The wall board's neck, right side (spec frame): the outside arc tangent to the blade's side
    at neck_top, the inside arc tangent to it and to the handle's side, which ends at handle_top."""
    o, au = s["outline"], s["sensor"]["u"]
    hw, hh, vt = o["width"] / 2, o["handle_width"] / 2, o["neck_top"]
    ro, ri = o["neck_radius"], o["neck_inside_radius"]
    gap = hw - hh
    ht = vt - math.sqrt(2 * gap * (ri + ro) - gap * gap)  # |inside centre - outside centre| = ri + ro
    ci, co = (au + hh + ri, ht), (au + hw - ro, vt)
    k = ri / (ri + ro)
    t = (ci[0] + (co[0] - ci[0]) * k, ci[1] + (co[1] - ci[1]) * k)
    return {"handle_top": ht, "inside_centre": ci, "outside_centre": co, "tangent": t}


def _mirror(e):
    def m(p):
        return (-p[0], p[1])

    if isinstance(e, Line):
        return Line(m(e.b), m(e.a))
    if isinstance(e, Arc):
        return Arc(m(e.b), m(e.mid), m(e.a))
    return Bezier(m(e.b), m(e.c2), m(e.c1), m(e.a))


def _fillet(pts: list[tuple[float, float]], radii: list[float]) -> list:
    """A closed polygon with each corner rounded by its radius (0: sharp), as Line/Arc elements in
    order. Works for convex and concave corners alike: each arc is tangent to both edges."""
    n = len(pts)
    cuts = []  # (tangent point on the edge in, arc mid, tangent point on the edge out) per corner
    for i, (v, r) in enumerate(zip(pts, radii, strict=True)):
        a, b = pts[i - 1], pts[(i + 1) % n]
        u1 = _unit((a[0] - v[0], a[1] - v[1]))
        u2 = _unit((b[0] - v[0], b[1] - v[1]))
        half = math.acos(max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))) / 2
        if r <= 0:
            cuts.append((v, None, v))
            continue
        d = r / math.tan(half)
        p1, p2 = (v[0] + u1[0] * d, v[1] + u1[1] * d), (v[0] + u2[0] * d, v[1] + u2[1] * d)
        bis = _unit((u1[0] + u2[0], u1[1] + u2[1]))
        c = r / math.sin(half)  # vertex to the arc's centre, along the bisector
        mid = (v[0] + bis[0] * (c - r), v[1] + bis[1] * (c - r))
        cuts.append((p1, mid, p2))
    out = []
    for i, (p1, mid, p2) in enumerate(cuts):
        if mid is not None:
            out.append(Arc(p1, mid, p2))
        nxt = cuts[(i + 1) % n][0]
        if math.dist(p2, nxt) > 1e-9:
            out.append(Line(p2, nxt))
    return out


def _unit(v: tuple[float, float]) -> tuple[float, float]:
    d = math.hypot(*v)
    return v[0] / d, v[1] / d


def _ring(c: tuple[float, float], r: float) -> list:
    """A circle as two half arcs."""
    (x, y) = c
    return [Arc((x + r, y), (x, y + r), (x - r, y)), Arc((x - r, y), (x, y - r), (x + r, y))]


def _slot(c: tuple[float, float], length: float, width: float, angle: float = 0.0) -> list:
    """A milled slot along x, turned by angle (degrees, counter-clockwise): straight sides,
    half-circle ends (the cutter's width)."""
    hl, hw = length / 2, width / 2
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))

    def p(x, y):
        return (c[0] + x * ca - y * sa, c[1] + x * sa + y * ca)

    return [
        Line(p(-hl + hw, hw), p(hl - hw, hw)),
        Arc(p(hl - hw, hw), p(hl, 0), p(hl - hw, -hw)),
        Line(p(hl - hw, -hw), p(-hl + hw, -hw)),
        Arc(p(-hl + hw, -hw), p(-hl, 0), p(-hl + hw, hw)),
    ]


def wall_joints(s: dict) -> dict[str, tuple[tuple[float, float], float]]:
    """The wall joints in the robot frame, keyed by the joint footprint's instance path: (centre of
    the 2x3 hole pattern, under the wall board's mid-plane; the direction the sensor looks in
    degrees, counter-clockwise from forward)."""
    return {
        v["path"]: ((v["x"], v["y"]), v["rotation"])
        for k, v in s.items()
        if k[:1] == "w" and k[1:].isdigit() and isinstance(v, dict) and "path" in v
    }


def notch_box(s: dict, name: str) -> tuple[float, float, float, float]:
    """A rear-corner notch of the main board ([switch_notch], [antenna_notch]) in the robot frame:
    (x_min, x_max, y_min, y_max), on the side its spec names (left: y > 0, right: y < 0)."""
    o, n = s["outline"], s[name]
    r, hw = o["rear"], o["width"] / 2
    if n["side"] == "left":
        return r, r + n["depth"], hw - n["width"], hw
    if n["side"] == "right":
        return r, r + n["depth"], -hw, -hw + n["width"]
    raise ValueError(f"[{name}] side must be left or right, not {n['side']!r}")


def main_perimeter(s: dict) -> list:
    """The main board's outer edge in the robot frame: the nose, the wheel notches, the antenna and
    switch notches in the rear corners, the rounded corners."""
    o, n = s["outline"], s["wheel_notches"]
    f, r, hw = o["front"], o["rear"], o["width"] / 2
    ni, nx, nr = n["inner_y"], n["half_length"], n["corner_radius"]
    side = {s[k]["side"]: k for k in ("switch_notch", "antenna_notch")}
    if sorted(side) != ["left", "right"]:
        raise ValueError("[switch_notch] and [antenna_notch] must take one rear corner each")
    left, right = side["left"], side["right"]
    _, lx, ly, _ = notch_box(s, left)
    _, rx, _, ry = notch_box(s, right)
    lr, rr = s[left]["corner_radius"], s[right]["corner_radius"]
    corners = [  # counter-clockwise from the front edge's right end (x forward, y left)
        ((f, -o["nose_half_width"]), o["front_corner_radius"]),
        ((f, o["nose_half_width"]), o["front_corner_radius"]),
        ((o["nose_shoulder_x"], hw), o["shoulder_radius"]),
        ((nx, hw), nr),
        ((nx, ni), nr),
        ((-nx, ni), nr),
        ((-nx, hw), nr),
        ((lx, hw), lr),
        ((lx, ly), lr),
        ((r, ly), lr),
        ((r, ry), rr),
        ((rx, ry), rr),
        ((rx, -hw), rr),
        ((-nx, -hw), nr),
        ((-nx, -ni), nr),
        ((nx, -ni), nr),
        ((nx, -hw), nr),
        ((o["nose_shoulder_x"], -hw), o["shoulder_radius"]),
    ]
    return _fillet([c for c, _ in corners], [rad for _, rad in corners])


def main_outline(s: dict) -> list:
    """The main board's Edge.Cuts in the robot frame: the perimeter (main_perimeter), the encoder
    slots and the fan hole (the wall boards stand on their headers, through holes: no slot)."""
    els = main_perimeter(s)
    e = s["encoder_slots"]
    for c in slots(s).values():
        els += _slot(c, e["length"], e["width"])
    els += _ring((s["fan_hole"]["x"], 0.0), s["fan_hole"]["diameter"] / 2)
    return els


def keepout_zones(s: dict) -> list[tuple[str, list[float]]]:
    """The main board's zones of the chassis over the board, the drive blocks' and the encoder
    boards': (name, [x_min, x_max, y_min, y_max, max_part_height])."""
    return [*s["drive_blocks"].items(), *((f"encoder_{k}", v) for k, v in s["encoder_boards"].items())]


# boards whose Edge.Cuts outline the spec generates: (outline in the spec frame, spec frame to KiCad)
OUTLINES: dict = {
    "main": (main_outline, lambda s, p: robot_to_kicad(s, p)),
    "wall": (wall_outline, lambda s, p: _xy(s, p)),
}


# ---------------------------------------------------------------------------------------------
# spec-drawn silkscreen: the fan ring and the drive blocks' outlines on the main board

SILK_LAYER = "F.SilkS"
SILK_EDGE = 0.3  # mm: a drawn line keeps this far inside the board's edge (the copper-to-edge 0.2 mm, plus margin)


def rect_union_outline(rects: list[list[float]]) -> list[Line]:
    """The boundary of a union of axis-aligned rectangles [x_min, x_max, y_min, y_max] as maximal
    straight segments (the outer outline and any hole's)."""
    xs = sorted({v for r in rects for v in r[:2]})
    ys = sorted({v for r in rects for v in r[2:4]})

    def covered(i: int, j: int) -> bool:
        if not (0 <= i < len(xs) - 1 and 0 <= j < len(ys) - 1):
            return False
        cx, cy = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
        return any(r[0] < cx < r[1] and r[2] < cy < r[3] for r in rects)

    out: list[Line] = []
    # horizontal edges: along y = ys[j], between cells (i, j - 1) and (i, j)
    for j in range(len(ys)):
        run = None
        for i in range(len(xs)):
            edge = i < len(xs) - 1 and covered(i, j - 1) != covered(i, j)
            if edge and run is None:
                run = i
            elif not edge and run is not None:
                out.append(Line((xs[run], ys[j]), (xs[i], ys[j])))
                run = None
    # vertical edges: along x = xs[i], between cells (i - 1, j) and (i, j)
    for i in range(len(xs)):
        run = None
        for j in range(len(ys)):
            edge = j < len(ys) - 1 and covered(i - 1, j) != covered(i, j)
            if edge and run is None:
                run = j
            elif not edge and run is not None:
                out.append(Line((xs[i], ys[run]), (xs[i], ys[j])))
                run = None
    return out


def _seg_distance(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    u = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.dist(p, (a[0] + u * dx, a[1] + u * dy))


def _inside(p, poly) -> bool:
    x, y = p
    hit = False
    for (x0, y0), (x1, y1) in zip(poly, [*poly[1:], poly[0]], strict=True):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def clip_lines(lines: list[Line], keep, step: float = 0.01, min_piece: float = 1.0) -> list[Line]:
    """The parts of each line where keep(point) holds; a piece cut from a longer line is dropped
    when shorter than min_piece (a stub where a zone's edge meets the board's)."""
    out = []
    for ln in lines:
        n = max(1, round(math.dist(ln.a, ln.b) / step))
        pts = [(ln.a[0] + (ln.b[0] - ln.a[0]) * k / n, ln.a[1] + (ln.b[1] - ln.a[1]) * k / n) for k in range(n + 1)]
        ok = [keep(q) for q in pts]
        if all(ok):
            out.append(ln)
            continue
        k = 0
        while k <= n:
            if not ok[k]:
                k += 1
                continue
            j = k
            while j + 1 <= n and ok[j + 1]:
                j += 1
            if math.dist(pts[k], pts[j]) >= min_piece:
                out.append(Line(pts[k], pts[j]))
            k = j + 1
    return out


SILK_PAD = (
    0.2 + 0.075
)  # mm: a drawn line's centre keeps the pad's mask margin and the silk clearance, plus half its width, off a pad


def spec_pads(
    s: dict, root: sexpr.Node | None, extra: tuple[str, ...] | list[str] = ()
) -> list[tuple[tuple[float, float], float]]:
    """The pads of the footprints the spec places (screw holes, slots, switch, module, wall joints)
    in the robot frame, each as (centre, radius of its circumscribed circle), at the spec's
    positions; and those of the footprints whose instance paths `extra` names, where the layout
    put them."""
    if root is None:
        return []
    want, slot_paths = placements(s), set(slots(s)) | set(extra)
    out = []
    for fp in root.children("footprint"):
        path = fp.prop("Path")
        if path not in want and path not in slot_paths:
            continue
        a = fp.child("at").atoms()
        rot = float(a[2]) if len(a) > 2 else 0.0
        at = _place_xy(s, want[path]) if path in want else (float(a[0]), float(a[1]))
        t = math.radians(rot)
        for pad in fp.children("pad"):
            px, py = (float(v) for v in pad.child("at").atoms()[:2])
            dx, dy = px * math.cos(t) + py * math.sin(t), -px * math.sin(t) + py * math.cos(t)
            w, h = (float(v) for v in pad.child("size").atoms()[:2])
            out.append((kicad_to_robot(s, (at[0] + dx, at[1] + dy)), math.hypot(w, h) / 2))
    return out


def drive_block_outlines(s: dict, root: sexpr.Node | None = None) -> dict[str, list[Line]]:
    """Each drive block's outline on the main board (robot frame): the union of its [drive_blocks]
    zones that [silkscreen] names, inside the board and SILK_EDGE in from its edge (the edge itself
    shows where a zone meets it), and off the spec-placed footprints' pads (spec_pads)."""
    poly = chain(main_perimeter(s))
    edges = list(zip(poly, [*poly[1:], poly[0]], strict=True))
    pads = spec_pads(s, root)

    def keep(q) -> bool:
        if not _inside(q, poly) or min(_seg_distance(q, a, b) for a, b in edges) < SILK_EDGE:
            return False
        return all(math.dist(q, c) >= r + SILK_PAD for c, r in pads)

    zones = s["drive_blocks"]
    return {
        side: clip_lines(rect_union_outline([zones[k] for k in s["silkscreen"][f"drive_block_{side}"]]), keep)
        for side in ("left", "right")
    }


RING_STEPS = 3600  # the fan ring's silk circle is clipped at 0.1 deg steps


def ring_silk(s: dict, root: sexpr.Node | None = None) -> list:
    """The fan ring's edge on the silkscreen: the circle as two half arcs, or, where a spec-placed
    footprint's pad (spec_pads: IC1 straddles the ring) or a pad of a part [fan_ring] silk_breaks
    names (at its layout position) comes within SILK_PAD of it, the arcs left between those pads; a
    piece under 1 mm is dropped (as clip_lines does)."""
    c, r = (s["fan_hole"]["x"], 0.0), s["fan_ring"]["diameter"] / 2
    pads = spec_pads(s, root, s["fan_ring"].get("silk_breaks", ()))
    pts = [
        (c[0] + r * math.cos(k * math.tau / RING_STEPS), r * math.sin(k * math.tau / RING_STEPS))
        for k in range(RING_STEPS)
    ]
    ok = [all(math.dist(q, pc) >= pr + SILK_PAD for pc, pr in pads) for q in pts]
    if all(ok):
        return _ring(c, r)
    start = ok.index(False)  # walk the circle from a clipped point, so no kept run wraps round
    arcs, k = [], 0
    while k < RING_STEPS:
        i = (start + k) % RING_STEPS
        if not ok[i]:
            k += 1
            continue
        j = k
        while j + 1 < RING_STEPS and ok[(start + j + 1) % RING_STEPS]:
            j += 1
        a, b = start + k, start + j
        if (b - a) * math.tau / RING_STEPS * r >= 1.0:
            arcs.append(Arc(pts[a % RING_STEPS], pts[((a + b) // 2) % RING_STEPS], pts[b % RING_STEPS]))
        k = j + 1
    return arcs


def main_silk(s: dict, root: sexpr.Node | None = None) -> list:
    """The silkscreen the spec draws on the main board, in the robot frame: the fan ring's edge
    (ring_silk) and both drive blocks' outlines."""
    els = ring_silk(s, root)
    for lines in drive_block_outlines(s, root).values():
        els += lines
    return els


def _silk_item(s: dict, e, i: int, width: float) -> str:
    def _pt(p) -> str:
        x, y = robot_to_kicad(s, p)
        return f"{sexpr.fmt(x)} {sexpr.fmt(y)}"

    uid = uuid.uuid5(_NS, f"silk/{i}")
    tail = (
        f"\t\t(stroke\n\t\t\t(width {sexpr.fmt(width)})\n\t\t\t(type solid)\n\t\t)\n"
        f'\t\t(layer "{SILK_LAYER}")\n\t\t(uuid "{uid}")\n\t)\n'
    )
    if isinstance(e, Line):
        return f"\t(gr_line\n\t\t(start {_pt(e.a)})\n\t\t(end {_pt(e.b)})\n" + tail
    return f"\t(gr_arc\n\t\t(start {_pt(e.a)})\n\t\t(mid {_pt(e.mid)})\n\t\t(end {_pt(e.b)})\n" + tail


SILK_UUIDS = {str(uuid.uuid5(_NS, f"silk/{i}")) for i in range(1000)}


def silk_items(root: sexpr.Node) -> list[sexpr.Node]:
    """The layout's spec-drawn silkscreen items (their UUIDs are the spec's)."""
    return [
        n
        for n in root.children()
        if n.head in ("gr_line", "gr_arc") and n.child("uuid") and n.child("uuid").atoms()[0] in SILK_UUIDS
    ]


def _silk_key(n: sexpr.Node) -> tuple:
    width = float(n.child("stroke").child("width").atoms()[0])
    return (*_edge_key(n), round(width, 6), n.child("layer").atoms()[0])


# boards whose silkscreen the spec partly draws: (items in the spec frame, line width)
SILK: dict = {"main": (main_silk, lambda s: s["fan_ring"]["silk_width"])}


def placements(s: dict) -> dict[str, dict]:
    """Footprints the spec positions (sections with a path and a position), keyed by instance path."""
    return {v["path"]: v for v in s.values() if isinstance(v, dict) and "path" in v and ("u" in v or "x" in v)}


def _xy(s: dict, p: tuple[float, float]) -> tuple[float, float]:
    """Spec frame of the encoder (u right, v up) to KiCad."""
    return s["kicad"]["origin_x"] + p[0], s["kicad"]["origin_y"] - p[1]


def robot_to_kicad(s: dict, p: tuple[float, float]) -> tuple[float, float]:
    """Robot frame of the main board (x forward, y left) to KiCad."""
    return s["kicad"]["origin_x"] - p[1], s["kicad"]["origin_y"] - p[0]


def kicad_to_robot(s: dict, p: tuple[float, float]) -> tuple[float, float]:
    return s["kicad"]["origin_y"] - p[1], s["kicad"]["origin_x"] - p[0]


def kicad_to_board(s: dict, p: tuple[float, float]) -> tuple[float, float]:
    """KiCad to a board frame with u right and v up (the encoder's)."""
    return p[0] - s["kicad"]["origin_x"], s["kicad"]["origin_y"] - p[1]


def _place_xy(s: dict, p: dict) -> tuple[float, float]:
    return _xy(s, (p["u"], p["v"])) if "u" in p else robot_to_kicad(s, (p["x"], p["y"]))


# ---------------------------------------------------------------------------------------------
# layout-owned outlines: the Edge.Cuts read back, for the interface features the spec checks

TOL = 1e-3  # mm: the spec rounds the Altium numbers to 0.1 um, KiCad stores 1 nm


def edge_items(root: sexpr.Node) -> list[sexpr.Node]:
    return [
        n
        for n in root.children()
        if n.head and n.head.startswith("gr_") and (layer := n.child("layer")) and layer.atoms() == ["Edge.Cuts"]
    ]


def _xy_of(n: sexpr.Node | None) -> tuple[float, float]:
    a = n.atoms()
    return float(a[0]), float(a[1])


def outline_elements(s: dict, root: sexpr.Node, to=kicad_to_robot) -> list:
    """Edge.Cuts as Line/Arc elements in the robot frame, or the frame `to` maps KiCad points into
    (gr_poly as its edges, gr_circle as two arcs)."""
    out = []
    for n in edge_items(root):
        if n.head == "gr_line":
            out.append(Line(*(to(s, _xy_of(n.child(k))) for k in ("start", "end"))))
        elif n.head == "gr_arc":
            out.append(Arc(*(to(s, _xy_of(n.child(k))) for k in ("start", "mid", "end"))))
        elif n.head == "gr_circle":
            (cx, cy), (ex, ey) = to(s, _xy_of(n.child("center"))), to(s, _xy_of(n.child("end")))
            far, side = (2 * cx - ex, 2 * cy - ey), (cx - (ey - cy), cy + (ex - cx))
            out += [Arc((ex, ey), side, far), Arc(far, (2 * cx - side[0], 2 * cy - side[1]), (ex, ey))]
        elif n.head == "gr_poly":
            pts = [to(s, _xy_of(p)) for p in n.child("pts").children("xy")]
            out += [Line(a, b) for a, b in zip(pts, [*pts[1:], pts[0]], strict=True)]
        else:
            raise ValueError(f"Edge.Cuts item {n.head} not handled")
    return out


def _circle(e: Arc) -> tuple[float, float, float]:
    (x1, y1), (x2, y2), (x3, y3) = e.a, e.mid, e.b
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    cx = ((x1**2 + y1**2) * (y2 - y3) + (x2**2 + y2**2) * (y3 - y1) + (x3**2 + y3**2) * (y1 - y2)) / d
    cy = ((x1**2 + y1**2) * (x3 - x2) + (x2**2 + y2**2) * (x1 - x3) + (x3**2 + y3**2) * (x2 - x1)) / d
    return cx, cy, math.hypot(x1 - cx, y1 - cy)


def _sweep(e: Arc) -> float:
    cx, cy, _ = _circle(e)
    a1, am, a2 = (math.atan2(y - cy, x - cx) for x, y in (e.a, e.mid, e.b))
    tau = 2 * math.pi
    full = (a2 - a1) % tau
    return full if (am - a1) % tau < full else tau - full


def _has_line(lines: list[Line], a, b) -> bool:
    return any(
        (math.dist(e.a, a) < TOL and math.dist(e.b, b) < TOL) or (math.dist(e.a, b) < TOL and math.dist(e.b, a) < TOL)
        for e in lines
    )


def slots(s: dict) -> dict[str, tuple[float, float]]:
    """Encoder slot centres in the robot frame, keyed by the slot footprint's instance path."""
    e = s["encoder_slots"]
    return {e["right_path"]: (0.0, -e["y"]), e["left_path"]: (0.0, e["y"])}


def slot_rotations(s: dict) -> dict[str, float]:
    """Encoder slot footprints' rotations in KiCad (degrees), keyed by instance path: the chip side
    (pads 5-8) outboard on each side."""
    e = s["encoder_slots"]
    return {e["right_path"]: float(e["right_rotation"]), e["left_path"]: float(e["left_rotation"])}


def footprint_checks(s: dict, root: sexpr.Node) -> list[str]:
    """Spec footprints the spec does not place: encoder slot footprints centred on their slots, hole drills."""
    problems = []
    fps = {fp.prop("Path"): fp for fp in root.children("footprint")}
    if "encoder_slots" in s:
        for path, centre in slots(s).items():
            fp = fps.get(path)
            if fp is None:
                problems.append(f"{path} (encoder slot footprint) is missing")
                continue
            got = kicad_to_robot(s, _xy_of(fp.child("at")))
            if math.dist(got, centre) > TOL:
                problems.append(f"{path} at ({got[0]:.4f}, {got[1]:.4f}), not on its slot centre {centre}")
            at = fp.child("at").atoms()
            rot, want = float(at[2]) if len(at) > 2 else 0.0, slot_rotations(s)[path]
            if abs((rot - want + 180) % 360 - 180) > 1e-6:
                problems.append(
                    f"{path} at {rot:g} deg, not the {want:g} deg of spec [encoder_slots] (its chip side outboard)"
                )
    if "holes" in s:
        # the screw holes: the [h1], [h2], ... sections
        holes = [v["path"] for k, v in s.items() if k[:1] == "h" and k[1:].isdigit()]
        for path in holes:
            fp = fps.get(path)
            drills = [float(d.atoms()[0]) for pad in fp.children("pad") if (d := pad.child("drill"))] if fp else []
            if drills != [s["holes"]["diameter"]]:
                problems.append(f"{path}: drill {drills}, spec {s['holes']['diameter']} mm")
    return problems


# ---------------------------------------------------------------------------------------------
# encoder board: features of a layout-owned outline

TAPER_TOL = 0.03  # mm: the spec's taper curve against the layout's (the Altium curve is within 0.021 mm)


def loop(els: list) -> list:
    """The elements as one closed loop, each oriented end to start, counter-clockwise (v up)."""

    def key(p):
        return round(p[0], 6), round(p[1], 6)

    def flip(e):
        return Line(e.b, e.a) if isinstance(e, Line) else Arc(e.b, e.mid, e.a)

    ends: dict[tuple, list[int]] = {}
    for i, e in enumerate(els):
        for p in (e.a, e.b):
            ends.setdefault(key(p), []).append(i)
    if not els or any(len(v) != 2 for v in ends.values()):
        raise ValueError("Edge.Cuts is not one closed loop")
    out, used = [els[0]], {0}
    while len(out) < len(els):
        here = key(out[-1].b)
        nxt = [i for i in ends[here] if i not in used]
        if not nxt:
            raise ValueError("Edge.Cuts is not one closed loop")
        e = els[nxt[0]]
        out.append(e if key(e.a) == here else flip(e))
        used.add(nxt[0])
    if key(out[-1].b) != key(out[0].a):
        raise ValueError("Edge.Cuts is not one closed loop")
    pts = [p for e in out for p in sample(e)]
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, [*pts[1:], pts[0]], strict=True))
    return out if area > 0 else [flip(e) for e in reversed(out)]


def encoder_features(s: dict, root: sexpr.Node) -> list[str]:
    """Every spec feature the encoder's Edge.Cuts outline lacks, as one line each (empty: all present)."""
    els = outline_elements(s, root, kicad_to_board)
    try:
        loop(els)
    except ValueError as e:
        return [str(e)]
    lines = [e for e in els if isinstance(e, Line)]
    arcs = [e for e in els if isinstance(e, Arc)]
    o, t = s["outline"], s["tab"]
    hw, top, r, hb, ts = o["width"] / 2, o["top"], o["corner_radius"], o["base_width"] / 2, o["taper_start"]
    ht, d, rr = t["width"] / 2, t["depth"], t["relief_radius"]
    problems = []

    pts = [p for e in els for p in sample(e, 64)]
    us, vs = [p[0] for p in pts], [p[1] for p in pts]
    for name, got, want in (
        ("left side", min(us), -hw),
        ("right side", max(us), hw),
        ("top", max(vs), top),
        ("tab edge", min(vs), -d),
    ):
        if abs(got - want) > TOL:
            problems.append(f"outline {name} at {got:.4f}, spec {want}")

    want_lines = {"tab edge": ((-ht, -d), (ht, -d)), "top edge": ((-(hw - r), top), (hw - r, top))}
    want_arcs = {}
    for sign, side in ((1, "right"), (-1, "left")):
        want_lines |= {
            f"{side} tab side": ((sign * ht, -d), (sign * ht, 0.0)),
            f"{side} shoulder": ((sign * (ht + 2 * rr), 0.0), (sign * hb, 0.0)),
            f"{side} side": ((sign * hw, ts), (sign * hw, top - r)),
        }
        want_arcs |= {
            f"{side} tab relief": ((sign * (ht + rr), 0.0), rr),
            f"{side} top corner": ((sign * (hw - r), top - r), r),
        }
    for what, (a, b) in want_lines.items():
        if not _has_line(lines, a, b):
            problems.append(f"no {what} from {a} to {b}")
    for what, (centre, radius) in want_arcs.items():
        if not any(math.dist(_circle(a)[:2], centre) < TOL and abs(_circle(a)[2] - radius) < TOL for a in arcs):
            problems.append(f"no {what}: {radius} mm arc centred at {centre}")

    # the tapers: the outline between the shoulder and the straight sides follows the spec's curve
    curve = sorted((p[1], abs(p[0])) for e in encoder_outline(s) if isinstance(e, Bezier) for p in sample(e, 512))
    worst = (0.0, None)
    for u, v in pts:
        if 0 < v < ts and abs(u) > hb - TOL:
            i = min(max(bisect.bisect(curve, (v, 0.0)), 1), len(curve) - 1)
            (v0, u0), (v1, u1) = curve[i - 1], curve[i]
            want = u0 + (u1 - u0) * (v - v0) / (v1 - v0) if v1 != v0 else u0
            worst = max(worst, (abs(abs(u) - want), (round(u, 4), round(v, 4))), key=lambda w: w[0])
    if worst[0] > TAPER_TOL:
        problems.append(f"taper {worst[0]:.3f} mm off the spec's curve at {worst[1]} (tolerance {TAPER_TOL} mm)")
    return problems


FEATURES = {"encoder": encoder_features}


def _edge_item(s: dict, e, i: int, to=None) -> str:
    """An outline element as a KiCad Edge.Cuts item; `to` maps spec points to KiCad (default: the
    encoder's u-v frame)."""

    def _pt(s, p) -> str:
        x, y = (to or _xy)(s, p)
        return f"{sexpr.fmt(x)} {sexpr.fmt(y)}"

    uid = uuid.uuid5(_NS, f"edge/{i}")
    tail = (
        f"\t\t(stroke\n\t\t\t(width {sexpr.fmt(EDGE_WIDTH)})\n\t\t\t(type default)\n\t\t)\n"
        f'\t\t(layer "Edge.Cuts")\n\t\t(uuid "{uid}")\n\t)\n'
    )
    if isinstance(e, Line):
        return f"\t(gr_line\n\t\t(start {_pt(s, e.a)})\n\t\t(end {_pt(s, e.b)})\n" + tail
    if isinstance(e, Arc):
        return f"\t(gr_arc\n\t\t(start {_pt(s, e.a)})\n\t\t(mid {_pt(s, e.mid)})\n\t\t(end {_pt(s, e.b)})\n" + tail
    pts = " ".join(f"(xy {_pt(s, p)})" for p in (e.a, e.c1, e.c2, e.b))
    return f"\t(gr_curve\n\t\t(pts\n\t\t\t{pts}\n\t\t)\n" + tail


def _edge_key(n: sexpr.Node) -> tuple:
    """Direction-independent geometry of an Edge.Cuts item: (kind, points)."""
    pts = [tuple(float(v) for v in c.atoms()) for c in n.children() if c.head in ("start", "mid", "end")]
    if n.head == "gr_curve":
        pts = [tuple(float(v) for v in c.atoms()) for c in n.child("pts").children("xy")]
        return (n.head, min(tuple(pts), tuple(reversed(pts))))
    if n.head == "gr_arc":
        start, mid, end = pts
        return (n.head, (*sorted((start, end)), mid))
    return (n.head, tuple(sorted(pts)))


EDGE_TOL = 1e-3  # mm: KiCad recomputes an arc's mid point when it saves, within 0.1 um


def _same_edges(old: list[tuple], new: list[tuple]) -> bool:
    """The two sets of edge keys describe the same outline, point for point within EDGE_TOL."""
    left = list(old)
    for kind, pts in new:
        hit = next(
            (
                k
                for k, (kk, pp) in enumerate(left)
                if kk == kind
                and len(pp) == len(pts)
                and all(math.dist(a, b) <= EDGE_TOL for a, b in zip(pp, pts, strict=True))
            ),
            None,
        )
        if hit is None:
            return False
        left.pop(hit)
    return not left


def zone_order(text: str) -> str:
    """The layout with its board-level zones in a canonical order: the zones with a UUID as KiCad
    wrote them, then the zones without one (teardrops) by their text. KiCad 10 saves a teardrop
    zone without its UUID and gives it a new one on every load, so each save of a board with
    teardrops interleaves them with the other zones in another order; this order keeps `make gen`
    byte-stable. Only the order changes: every zone keeps its text, and a board without teardrops
    is left as it is."""
    root = sexpr.parse(text)
    zones = root.children("zone")
    spans = [sexpr.line_span(text, z) for z in zones]
    items = [
        (i, text[a:b], z.child("uuid") is not None) for i, (z, (a, b)) in enumerate(zip(zones, spans, strict=True))
    ]
    canon = [s for _, s, _ in sorted(items, key=lambda it: (0, it[0], "") if it[2] else (1, 0, it[1]))]
    return sexpr.splice(text, [(a, b, s) for (a, b), s in zip(spans, canon, strict=True)])


def apply(board: str, text: str) -> tuple[str, list[str], list[str]]:
    """The layout text with the spec applied, the changes made, and the problems only KiCad can fix."""
    s = spec.load(board)
    root = sexpr.parse(text)
    edits, changes, problems = [], [], []

    old_edges = edge_items(root)
    if board in OUTLINES:
        # Edge.Cuts: the spec owns the whole layer.
        make, to = OUTLINES[board]
        new_items = [_edge_item(s, e, i, to) for i, e in enumerate(make(s))]
        new_edges = "".join(new_items)
        # compared as geometry: KiCad re-sorts board graphics and normalises arc direction when it saves
        if not _same_edges([_edge_key(n) for n in old_edges], [_edge_key(sexpr.parse(i)) for i in new_items]):
            changes.append(f"Edge.Cuts outline ({len(old_edges)} -> {new_edges.count('(layer')} items)")
            for n in old_edges:
                edits.append((*sexpr.line_span(text, n), ""))
            anchor = root.children("footprint")[0] if root.children("footprint") else None
            at = sexpr.line_span(text, anchor)[0] if anchor else root.end - 1
            edits.append((at, at, new_edges))
    elif board in FEATURES:
        # Edge.Cuts belongs to the layout: the spec checks its features, which only KiCad can fix.
        problems += FEATURES[board](s, root)

    if board in SILK:
        # the spec's silkscreen (its own items, by UUID): the rest of the silkscreen is the layout's
        make, width = SILK[board]
        old_silk = silk_items(root)
        new_items = [_silk_item(s, e, i, width(s)) for i, e in enumerate(make(s, root))]
        old_keys = sorted(_silk_key(n) for n in old_silk)
        new_keys = sorted(_silk_key(sexpr.parse(i)) for i in new_items)
        same = len(old_keys) == len(new_keys) and all(
            a[0] == b[0]
            and a[2:] == b[2:]
            and all(math.dist(p, q) <= EDGE_TOL for p, q in zip(a[1], b[1], strict=True))
            for a, b in zip(old_keys, new_keys, strict=True)
        )
        if not same:
            changes.append(f"spec silkscreen ({len(old_silk)} -> {len(new_items)} items)")
            for n in old_silk:
                edits.append((*sexpr.line_span(text, n), ""))
            anchor = root.children("footprint")[0] if root.children("footprint") else None
            at = sexpr.line_span(text, anchor)[0] if anchor else root.end - 1
            edits.append((at, at, "".join(new_items)))

    # Aux (drill/placement) and grid origins: the spec's aux origin if it names one, else the spec
    # origin, so exports use that frame.
    setup = root.child("setup")
    k = s["kicad"]
    ox, oy = sexpr.fmt(k.get("aux_origin_x", k["origin_x"])), sexpr.fmt(k.get("aux_origin_y", k["origin_y"]))
    for key in ("aux_axis_origin", "grid_origin"):
        node = setup.child(key)
        want = f"({key} {ox} {oy})"
        if node is None:
            plot = setup.child("pcbplotparams")
            pos = sexpr.line_span(text, plot)[0] if plot else setup.end - 1
            edits.append((pos, pos, f"\t\t{want}\n"))
            changes.append(f"{key} set")
        elif text[node.start : node.end] != want:
            edits.append((node.start, node.end, want))
            changes.append(f"{key} moved")

    # Spec-placed footprints: position fixed, rotation and side checked, locked.
    want_fp = placements(s)
    found = set()
    for fp in root.children("footprint"):
        path = fp.prop("Path")
        if path not in want_fp:
            continue
        found.add(path)
        p = want_fp[path]
        at = fp.child("at")
        a = at.atoms()
        rot = float(a[2]) if len(a) > 2 else 0.0
        if fp.child("layer").atoms() != ["F.Cu"]:
            raise SystemExit(f"{path}: must be on the top side (flip it back in KiCad)")
        if not math.isclose(rot % 360, p["rotation"] % 360, abs_tol=1e-6):
            raise SystemExit(f"{path}: rotation {rot} != spec {p['rotation']} (rotate it in KiCad, then rerun)")
        x, y = _place_xy(s, p)
        want_at = f"(at {sexpr.fmt(x)} {sexpr.fmt(y)}" + (f" {sexpr.fmt(rot)})" if len(a) > 2 else ")")
        if text[at.start : at.end] != want_at:
            edits.append((at.start, at.end, want_at))
            changes.append(f"{path} moved to ({sexpr.fmt(x)}, {sexpr.fmt(y)})")
        if fp.child("locked") is None:
            layer = fp.child("layer")
            pos = sexpr.line_span(text, layer)[0]
            edits.append((pos, pos, "\t\t(locked yes)\n"))
            changes.append(f"{path} locked")
    missing = set(want_fp) - found
    if missing:
        raise SystemExit(
            f"footprints named in spec/{board}.toml are missing from the layout: {sorted(missing)} "
            "(run `pcb apply` first)"
        )
    problems += footprint_checks(s, root)

    new = sexpr.splice(text, edits)
    ordered = zone_order(new)
    if ordered != new:
        changes.append("zones written in canonical order (zone_order)")
    return ordered, changes, problems


def sample(e, n: int = 16) -> list[tuple[float, float]]:
    """Points along an outline element (without its end point)."""
    if isinstance(e, Line):
        return [e.a]
    if isinstance(e, Arc):
        (x1, y1), (x2, y2), (x3, y3) = e.a, e.mid, e.b
        d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
        cx = ((x1**2 + y1**2) * (y2 - y3) + (x2**2 + y2**2) * (y3 - y1) + (x3**2 + y3**2) * (y1 - y2)) / d
        cy = ((x1**2 + y1**2) * (x3 - x2) + (x2**2 + y2**2) * (x1 - x3) + (x3**2 + y3**2) * (x2 - x1)) / d
        r = math.hypot(x1 - cx, y1 - cy)
        a1, a2, am = (math.atan2(y - cy, x - cx) for x, y in (e.a, e.b, e.mid))
        sweep = (a2 - a1) % (2 * math.pi)
        if not (0 < (am - a1) % (2 * math.pi) < sweep):
            sweep -= 2 * math.pi
        return [(cx + r * math.cos(a1 + sweep * i / n), cy + r * math.sin(a1 + sweep * i / n)) for i in range(n)]
    pts = []
    for i in range(n):
        t = i / n
        k = [(1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t**2, t**3]
        pts.append(tuple(sum(w * p[j] for w, p in zip(k, (e.a, e.c1, e.c2, e.b), strict=True)) for j in (0, 1)))
    return pts


def _r(p) -> list[float]:
    return [round(p[0], 4), round(p[1], 4)]


def encoder_json(s: dict, root: sexpr.Node) -> dict:
    """The encoder board in its spec frame: the Edge.Cuts outline from the layout (a polygon, arcs as
    16 segments), the rest from the spec (which `encoder_features` and the placements have checked)."""
    poly: list[list[float]] = []
    for p in (pt for e in loop(outline_elements(s, root, kicad_to_board)) for pt in sample(e)):
        if not poly or _r(p) != poly[-1]:
            poly.append(_r(p))
    return {
        "frame": "origin at the tab centre on the main board top surface; u right (chip side view), v up; mm",
        "thickness": s["pcb"]["thickness"],
        "outline": poly,
        "top": s["outline"]["top"],
        "tab": {"width": s["tab"]["width"], "depth": s["tab"]["depth"]},
        "sensor": {"u": s["sensor"]["u"], "v": s["sensor"]["v"], "side": "top"},
    }


def wall_json(s: dict, root: sexpr.Node) -> dict:
    """The wall board in its spec frame: the outline (the spec's, which the layout carries), the
    optical axes and the header joint."""
    poly: list[list[float]] = []
    for p in (pt for e in wall_outline(s) for pt in sample(e)):
        if not poly or _r(p) != poly[-1]:
            poly.append(_r(p))
    se, h, th = s["sensor"], s["header"], s["pcb"]["thickness"]
    mid = round(-th / 2, 4)
    return {
        "frame": "origin on the main board's top surface under the middle of the bottom edge; u right (front view), v up; front face at z = 0, back face at z = -thickness; mm",
        "thickness": th,
        "outline": poly,
        "bottom": s["outline"]["bottom"],
        "top": s["outline"]["top"],
        "handle": {"width": s["outline"]["handle_width"], "top": round(wall_neck(s)["handle_top"], 4)},
        "neck": {
            "top": s["outline"]["neck_top"],
            "radius": s["outline"]["neck_radius"],
            "inside_radius": s["outline"]["neck_inside_radius"],
        },
        "blade_width": s["outline"]["width"],
        "receiver_axis": {"u": se["u"], "v": se["v"], "part": "TPS601A(F)"},
        "emitter_axis": {"u": se["u"], "v": round(se["v"] + se["led_above"], 4), "part": "SFH 4550"},
        "header": {
            "part": "HX PZ1.27-2x3P ZZ",
            "pins": h["pins"],
            "pitch": h["pitch"],
            "row_pitch": h["row_pitch"],
            "pins_u": [round(h["u"] + h["pitch"] * k, 4) for k in (-1, 0, 1)],
            "rows_z": [round(mid + h["row_pitch"] / 2, 4), round(mid - h["row_pitch"] / 2, 4)],
            "insulator": {
                "u": [round(h["u"] - h["insulator_length"] / 2, 4), round(h["u"] + h["insulator_length"] / 2, 4)],
                "v": [0.0, h["insulator_height"]],
                "z": [round(mid - h["insulator_width"] / 2, 4), round(mid + h["insulator_width"] / 2, 4)],
            },
            "pins_top_v": round(h["insulator_height"] + h["pin_up"], 4),
            "pins_end_v": round(-h["pin_down"], 4),
        },
        "joint": {k: s["joint"][k] for k in ("drill", "pad")},
    }


def main_json(s: dict, root: sexpr.Node) -> dict:
    """The main board in the robot frame: the Edge.Cuts outline (from the layout, which the spec
    draws), the screw holes and their countersinks, the encoder slots, the fan hole, the wheel,
    antenna and switch notches, the ESP32 module, the wall sensors and the drive blocks' zones."""
    edge = []
    for e in outline_elements(s, root):
        if isinstance(e, Line):
            edge.append({"type": "line", "start": _r(e.a), "end": _r(e.b)})
        else:
            edge.append({"type": "arc", "start": _r(e.a), "mid": _r(e.mid), "end": _r(e.b)})
    o, sl, n, sw, an = (s[k] for k in ("outline", "encoder_slots", "wheel_notches", "switch_notch", "antenna_notch"))
    swx0, swx1, swy0, swy1 = notch_box(s, "switch_notch")
    anx0, anx1, any0, any1 = notch_box(s, "antenna_notch")
    holes = [v for v in s.values() if isinstance(v, dict) and v.get("path", "").startswith("H")]
    wall = spec.load("wall")
    th, wth, se = s["pcb"]["thickness"], wall["pcb"]["thickness"], wall["sensor"]

    def sensor(path: str, c: tuple[float, float], look: float) -> dict:
        d = (math.cos(math.radians(look)), math.sin(math.radians(look)))
        face = (c[0] + d[0] * wth / 2, c[1] + d[1] * wth / 2)
        return {
            "name": path.split(".")[1],
            "joint_centre": list(c),
            "look_deg": look,
            "front_face": _r(face),
            "receiver_z": round(th + se["v"], 4),
            "emitter_z": round(th + se["v"] + se["led_above"], 4),
        }

    return {
        "frame": "robot: origin at the wheel-axle midpoint on the board's bottom surface, x forward, y left, z up; mm",
        "kicad_origin": [s["kicad"]["origin_x"], s["kicad"]["origin_y"]],
        "thickness": s["pcb"]["thickness"],
        "extents": {"front": o["front"], "rear": o["rear"], "width": o["width"]},
        "edge": edge,
        "holes": [
            {"name": h["path"].split(".")[0], "pos": [h["x"], h["y"]], "drill": s["holes"]["diameter"]} for h in holes
        ],
        "countersink": {
            "diameter": s["countersink"]["diameter"],
            "angle": s["countersink"]["angle"],
            "side": s["countersink"]["side"],
            "fabricated": s["countersink"]["fabricated"],
        },
        "encoder_slots": [
            {
                "name": path.split(".")[1],
                "centre": list(c),
                "length": sl["length"],
                "width": sl["width"],
                "corner_radius": sl["corner_radius"],
            }
            for path, c in slots(s).items()
        ],
        "fan_hole": {"centre": [s["fan_hole"]["x"], 0.0], "diameter": s["fan_hole"]["diameter"]},
        "fan_ring": {
            "centre": [s["fan_hole"]["x"], 0.0],
            "diameter": s["fan_ring"]["diameter"],
            "max_part_height": s["fan_ring"]["max_part_height"],
        },
        "wheel_notches": {
            "inner_y": n["inner_y"],
            "x": [-n["half_length"], n["half_length"]],
            "corner_radius": n["corner_radius"],
        },
        "switch_notch": {
            "side": sw["side"],
            "x": [swx0, swx1],
            "y": [swy0, swy1],
            "corner_radius": sw["corner_radius"],
            "switch": {"pos": [s["sw4"]["x"], s["sw4"]["y"]], "lever": "along -x, 6.0 mm from the body's rear face"},
        },
        "antenna_notch": {
            "side": an["side"],
            "x": [anx0, anx1],
            "y": [any0, any1],
            "corner_radius": an["corner_radius"],
            "module": {"pos": [s["u13"]["x"], s["u13"]["y"]], "antenna": "along -x, over the notch"},
        },
        "wall_sensors": [sensor(path, c, look) for path, (c, look) in wall_joints(s).items()],
        "wall_joint": {
            "holes": "2x3 at the header's pitch, rows across the look direction, the centre under the wall board's mid-plane",
            "pitch": wall["header"]["pitch"],
            "row_pitch": wall["header"]["row_pitch"],
            "drill": wall["joint"]["drill"],
            "under_blade_max_height": wall["joint"]["under_blade"],
            "insulator": [
                wall["header"]["insulator_length"],
                wall["header"]["insulator_width"],
                wall["header"]["insulator_height"],
            ],
        },
        "keepouts": [
            {"name": name, "x": [z[0], z[1]], "y": [z[2], z[3]], "max_part_height": z[4]}
            for name, z in keepout_zones(s)
        ],
    }


def chain(els: list, tol: float = 1e-3) -> list[tuple[float, float]]:
    """A closed outline's elements, in any order and direction, as one polygon (arcs sampled)."""
    left = list(els)
    poly: list[tuple[float, float]] = []
    end = None
    while left:
        if end is None:
            e = left.pop(0)
        else:
            i = min(range(len(left)), key=lambda k: min(math.dist(end, left[k].a), math.dist(end, left[k].b)))
            e = left.pop(i)
            if math.dist(end, e.a) > math.dist(end, e.b):
                e = Line(e.b, e.a) if isinstance(e, Line) else Arc(e.b, e.mid, e.a)
            if math.dist(end, e.a) > tol:
                raise ValueError(f"outline gap at {end}")
        poly += sample(e, 16)
        end = e.b
    return poly


EXPORTS = {"encoder": encoder_json, "main": main_json, "wall": wall_json}


def mech_json(board: str, text: str | None = None) -> dict:
    """The board for MicrasHardware and micras-simulation, in the spec frame."""
    s = spec.load(board)
    root = sexpr.parse(text if text is not None else board_pcb(board).read_text())
    return {"board": board, "source": f"MicrasPCB spec/{board}.toml", **EXPORTS[board](s, root)}


def run(board: str, check: bool) -> int:
    if not (spec.SPEC_DIR / f"{board}.toml").is_file():
        print(f"{board}: no spec/{board}.toml, no spec-owned mechanics to apply or check")
        return 0
    pcb = board_pcb(board)
    text = pcb.read_text()
    new, changes, problems = apply(board, text)
    for p in problems:
        print(f"  - {p}")
    if check:
        if changes:
            print(f"{pcb}: drifted from spec/{board}.toml:")
            for c in changes:
                print(f"  - {c}")
            print(f"run `micras-pcb mech {board}` and commit the result")
            return 1
        if problems:
            print(f"{pcb}: does not match spec/{board}.toml (fix the layout in KiCad or the spec)")
            return 1
        print(f"{pcb}: matches spec/{board}.toml")
        return 0
    if changes:
        pcb.write_text(new)
        for c in changes:
            print(f"  {c}")
    if problems:
        print(f"{pcb}: does not match spec/{board}.toml (fix the layout in KiCad or the spec)")
        return 1
    out = build_dir(board) / f"{board}_mech.json"
    out.write_text(json.dumps(mech_json(board, new), indent=1) + "\n")
    print(
        f"{pcb}: {'updated' if changes else 'already matches the spec'}; wrote {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}"
    )
    return 0
