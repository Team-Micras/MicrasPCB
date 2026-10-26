"""Apply a board's mechanical spec to its KiCad layout, and export it for the other repos.

The spec owns the aux/grid origin and the position of the footprints it names (written locked),
and the Edge.Cuts outline of the boards in `OUTLINES`. The other boards' outlines are layout
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


def _slot(c: tuple[float, float], length: float, width: float) -> list:
    """A milled slot along x: straight sides, half-circle ends (the cutter's width)."""
    (x, y), hl, hw = c, length / 2, width / 2
    return [
        Line((x - hl + hw, y + hw), (x + hl - hw, y + hw)),
        Arc((x + hl - hw, y + hw), (x + hl, y), (x + hl - hw, y - hw)),
        Line((x + hl - hw, y - hw), (x - hl + hw, y - hw)),
        Arc((x - hl + hw, y - hw), (x - hl, y), (x - hl + hw, y + hw)),
    ]


def main2_outline(s: dict) -> list:
    """boards/main2's Edge.Cuts in the robot frame: the board (nose, wheel notches, the antenna and
    switch notches in the rear corners, rounded corners), the encoder slots, the fan hole and the
    USB-C peg holes."""
    o, n, sw, an = s["outline"], s["wheel_notches"], s["switch_notch"], s["antenna_notch"]
    f, r, hw = o["front"], o["rear"], o["width"] / 2
    ni, nx, nr = n["inner_y"], n["half_length"], n["corner_radius"]
    sr, ar = sw["corner_radius"], an["corner_radius"]
    corners = [  # counter-clockwise from the front edge's right end (x forward, y left)
        ((f, -o["nose_half_width"]), o["front_corner_radius"]),
        ((f, o["nose_half_width"]), o["front_corner_radius"]),
        ((o["nose_shoulder_x"], hw), o["shoulder_radius"]),
        ((nx, hw), nr),
        ((nx, ni), nr),
        ((-nx, ni), nr),
        ((-nx, hw), nr),
        ((r + an["depth"], hw), ar),
        ((r + an["depth"], hw - an["width"]), ar),
        ((r, hw - an["width"]), ar),
        ((r, -hw + sw["width"]), sr),
        ((r + sw["depth"], -hw + sw["width"]), sr),
        ((r + sw["depth"], -hw), sr),
        ((-nx, -hw), nr),
        ((-nx, -ni), nr),
        ((nx, -ni), nr),
        ((nx, -hw), nr),
        ((o["nose_shoulder_x"], -hw), o["shoulder_radius"]),
    ]
    els = _fillet([c for c, _ in corners], [rad for _, rad in corners])
    e = s["encoder_slots"]
    for c in slots(s).values():
        els += _slot(c, e["length"], e["width"])
    els += _ring((s["fan_hole"]["x"], 0.0), s["fan_hole"]["diameter"] / 2)
    for c in usb_pegs(s):
        els += _ring(c, s["usb"]["peg_diameter"] / 2)
    return els


def keepout_zones(s: dict) -> list[tuple[str, list[float]]]:
    """boards/main2's zones of the chassis over the board, the drive blocks' and the encoder
    boards': (name, [x_min, x_max, y_min, y_max, max_part_height])."""
    return [*s["drive_blocks"].items(), *((f"encoder_{k}", v) for k, v in s["encoder_boards"].items())]


def usb_pegs(s: dict) -> list[tuple[float, float]]:
    """boards/main2's USB-C housing-peg holes, from the receptacle's spec position (robot frame)."""
    u = s["usb"]
    return [(u["x"] + u["peg_x_offset"], u["y"] + side * u["peg_offset"]) for side in (1, -1)]


# boards whose Edge.Cuts outline the spec generates: (outline in the spec frame, spec frame to KiCad)
OUTLINES: dict = {"main2": (main2_outline, lambda s, p: robot_to_kicad(s, p))}


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
    """KiCad to a board frame with u right and v up (the encoder's and the Bluetooth module's)."""
    return p[0] - s["kicad"]["origin_x"], s["kicad"]["origin_y"] - p[1]


def _place_xy(s: dict, p: dict) -> tuple[float, float]:
    return _xy(s, (p["u"], p["v"])) if "u" in p else robot_to_kicad(s, (p["x"], p["y"]))


# ---------------------------------------------------------------------------------------------
# main board: interface features of a layout-owned outline

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


def pegs(s: dict) -> list[tuple[float, float]]:
    p = s["usb_pegs"]
    return [(p["x"], p["left_y"]), (p["x"], p["right_y"])]


def features(s: dict, root: sexpr.Node) -> list[str]:
    """Every spec feature the Edge.Cuts outline lacks, as one line each (empty: all present)."""
    els = outline_elements(s, root)
    lines = [e for e in els if isinstance(e, Line)]
    arcs = [e for e in els if isinstance(e, Arc)]
    problems = []

    pts = [p for e in els for p in sample(e, 64)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    o = s["outline"]
    for name, got, want in (
        ("front", max(xs), o["front"]),
        ("rear", min(xs), o["rear"]),
        ("left side", max(ys), o["width"] / 2),
        ("right side", min(ys), -o["width"] / 2),
    ):
        if abs(got - want) > TOL:
            problems.append(f"outline {name} at {got:.4f}, spec {want}")

    e = s["encoder_slots"]
    hl, hw, r = e["length"] / 2, e["width"] / 2, e.get("corner_radius", 0.0)
    for path, (cx, cy) in slots(s).items():
        # straight sides along the slot, straight ends if the corners leave any, and corner arcs
        # (centred r in from each corner) that together sweep a full circle
        want = [((cx - hl + r, cy + sy * hw), (cx + hl - r, cy + sy * hw)) for sy in (1, -1)]
        if hw - r > TOL:
            want += [((cx + sx * hl, cy - hw + r), (cx + sx * hl, cy + hw - r)) for sx in (1, -1)]
        centres = {(cx + sx * (hl - r), cy + sy * (hw - r)) for sx in (1, -1) for sy in (1, -1)}
        corner = [
            a for a in arcs if any(math.dist(_circle(a)[:2], c) < TOL for c in centres) and abs(_circle(a)[2] - r) < TOL
        ]
        rounded = r <= TOL or abs(sum(map(_sweep, corner)) - 2 * math.pi) < 1e-3
        if not all(_has_line(lines, a, b) for a, b in want) or not rounded:
            problems.append(
                f"no {e['length']} x {e['width']} mm encoder slot with R{r} ends at ({cx}, {cy}) for {path}"
            )

    p = s["usb_pegs"]
    for cx, cy in pegs(s):
        near = [q for el in lines for q in (el.a, el.b) if math.dist(q, (cx, cy)) < p["diameter"]]
        r = [math.dist(q, (cx, cy)) for q in near]
        # a polygon with flats on the nominal diameter: vertices sit up to 2.5 % further out
        if len(near) < 16 or min(r) < p["diameter"] / 2 - TOL or max(r) > p["diameter"] / 2 * 1.025 + TOL:
            problems.append(f"no {p['diameter']} mm USB-C peg hole at ({cx}, {cy})")

    f = s["fan_hole"]
    ring = [
        a
        for a in arcs
        if math.dist(_circle(a)[:2], (f["x"], 0.0)) < TOL and abs(_circle(a)[2] - f["diameter"] / 2) < TOL
    ]
    if abs(sum(map(_sweep, ring)) - 2 * math.pi) > 1e-3:
        problems.append(f"no {f['diameter']} mm fan hole at ({f['x']}, 0)")

    n = s["wheel_notches"]
    inner, half, r = n["inner_y"], n["half_length"], n["corner_radius"]
    for sign in (1, -1):
        y0, y1 = sign * inner, sign * (o["width"] / 2)
        want = [
            ((half - r, y0), (-(half - r), y0)),  # inner face
            ((half, y0 + sign * r), (half, y1 - sign * r)),  # front side
            ((-half, y0 + sign * r), (-half, y1 - sign * r)),  # rear side
        ]
        if not all(_has_line(lines, a, b) for a, b in want):
            problems.append(f"no wheel notch {inner} mm from the centre line on the {'left' if sign > 0 else 'right'}")
    return problems


def bluetooth_features(s: dict, root: sexpr.Node) -> list[str]:
    """What the Bluetooth module's layout lacks of spec/bluetooth.toml: outline extents (board frame)
    and the HM-19 at its position."""
    pts = [p for e in outline_elements(s, root, kicad_to_board) for p in sample(e, 16)]
    if not pts:
        return ["no Edge.Cuts outline"]
    us, vs = [p[0] for p in pts], [p[1] for p in pts]
    o = s["outline"]
    problems = [
        f"outline {name} at {got:.4f}, spec {want}"
        for name, got, want in (
            ("left", min(us), o["left"]),
            ("right", max(us), o["right"]),
            ("top", max(vs), o["top"]),
            ("bottom", min(vs), o["bottom"]),
        )
        if abs(got - want) > TOL
    ]
    m = s["module"]
    fp = next((f for f in root.children("footprint") if f.prop("Reference") == m["ref"]), None)
    if fp is None:
        problems.append(f"{m['ref']} (the HM-19) is missing")
    else:
        u, v = kicad_to_board(s, _xy_of(fp.child("at")))
        if math.dist((u, v), (m["u"], m["v"])) > TOL:
            problems.append(f"{m['ref']} at ({u:.4f}, {v:.4f}), spec ({m['u']}, {m['v']})")
    return problems


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


FEATURES = {"main": features, "encoder": encoder_features, "bluetooth": bluetooth_features}


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

    return sexpr.splice(text, edits), changes, problems


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


def main_json(s: dict, root: sexpr.Node) -> dict:
    """The main board in the robot frame: the Edge.Cuts outline from the layout, the rest from the spec
    (which `features` and the placements have checked against the layout)."""
    edge = []
    for e in outline_elements(s, root):
        if isinstance(e, Line):
            edge.append({"type": "line", "start": _r(e.a), "end": _r(e.b)})
        else:
            edge.append({"type": "arc", "start": _r(e.a), "mid": _r(e.mid), "end": _r(e.b)})
    sl, n = s["encoder_slots"], s["wheel_notches"]
    holes = [v for v in s.values() if isinstance(v, dict) and v.get("path", "").startswith("H")]
    return {
        "frame": "robot: origin at the wheel-axle midpoint on the board's bottom surface, x forward, y left, z up; mm",
        "kicad_origin": [s["kicad"]["origin_x"], s["kicad"]["origin_y"]],
        "thickness": s["pcb"]["thickness"],
        "extents": {"front": s["outline"]["front"], "rear": s["outline"]["rear"], "width": s["outline"]["width"]},
        "edge": edge,
        "holes": [
            {"name": h["path"].split(".")[0], "pos": [h["x"], h["y"]], "drill": s["holes"]["diameter"]} for h in holes
        ],
        "encoder_slots": [
            {
                "name": path.split(".")[1],
                "centre": list(c),
                "length": sl["length"],
                "width": sl["width"],
                "corner_radius": sl.get("corner_radius", 0.0),
            }
            for path, c in slots(s).items()
        ],
        "usb_pegs": [{"centre": list(c), "diameter": s["usb_pegs"]["diameter"]} for c in pegs(s)],
        "fan_hole": {"centre": [s["fan_hole"]["x"], 0.0], "diameter": s["fan_hole"]["diameter"]},
        "wheel_notches": {
            "inner_y": n["inner_y"],
            "x": [-n["half_length"], n["half_length"]],
            "corner_radius": n["corner_radius"],
        },
    }


def main2_json(s: dict, root: sexpr.Node) -> dict:
    """The second main board in the robot frame: main_json's fields (the outline from the layout,
    which the spec draws), plus the antenna and switch notches, the USB-C receptacle, the ESP32
    module, the wall sensors and the drive blocks' zones."""
    edge = []
    for e in outline_elements(s, root):
        if isinstance(e, Line):
            edge.append({"type": "line", "start": _r(e.a), "end": _r(e.b)})
        else:
            edge.append({"type": "arc", "start": _r(e.a), "mid": _r(e.mid), "end": _r(e.b)})
    o, sl, n, sw, an, u = (
        s[k] for k in ("outline", "encoder_slots", "wheel_notches", "switch_notch", "antenna_notch", "usb")
    )
    holes = [v for v in s.values() if isinstance(v, dict) and v.get("path", "").startswith("H")]
    walls = [v for k, v in s.items() if k.startswith("w") and isinstance(v, dict) and "path" in v]
    return {
        "frame": "robot: origin at the wheel-axle midpoint on the board's bottom surface, x forward, y left, z up; mm",
        "kicad_origin": [s["kicad"]["origin_x"], s["kicad"]["origin_y"]],
        "thickness": s["pcb"]["thickness"],
        "extents": {"front": o["front"], "rear": o["rear"], "width": o["width"]},
        "edge": edge,
        "holes": [
            {"name": h["path"].split(".")[0], "pos": [h["x"], h["y"]], "drill": s["holes"]["diameter"]} for h in holes
        ],
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
        "wheel_notches": {
            "inner_y": n["inner_y"],
            "x": [-n["half_length"], n["half_length"]],
            "corner_radius": n["corner_radius"],
        },
        "switch_notch": {
            "x": [o["rear"], o["rear"] + sw["depth"]],
            "y": [-o["width"] / 2, -o["width"] / 2 + sw["width"]],
            "corner_radius": sw["corner_radius"],
            "switch": {"pos": [s["sw4"]["x"], s["sw4"]["y"]], "lever": "along -x, 6.0 mm from the body's rear face"},
        },
        "antenna_notch": {
            "x": [o["rear"], o["rear"] + an["depth"]],
            "y": [o["width"] / 2 - an["width"], o["width"] / 2],
            "corner_radius": an["corner_radius"],
            "module": {"pos": [s["u13"]["x"], s["u13"]["y"]], "antenna": "along -x, over the notch"},
        },
        "usb": {
            "pos": [u["x"], u["y"]],
            "mouth": "along -x, on the rear edge",
            "pegs": [{"centre": list(c), "diameter": u["peg_diameter"]} for c in usb_pegs(s)],
        },
        "wall_sensors": [
            {"name": w["path"].split(".")[1], "pos": [w["x"], w["y"]], "kicad_rotation": w["rotation"]} for w in walls
        ],
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


def bluetooth_json(s: dict, root: sexpr.Node) -> dict:
    """The module in its board frame (outline from the layout, the rest from the spec), and where the
    mating puts that frame in the robot."""
    poly: list[tuple[float, float]] = []
    for p in chain(outline_elements(s, root, kicad_to_board)):
        if not poly or math.dist(p, poly[-1]) >= 0.02:
            poly.append(p)
    m, pl, mt = s["module"], s["plug"], s["mating"]
    main = spec.load("main")
    face_x = mt["receptacle_x"] - mt["mouth_offset"] + mt["insertion"] - pl["height"]
    return {
        "frame": "board: origin at the plug centre on the component side, u right and v up seen from the component side; mm",
        "thickness": s["pcb"]["thickness"],
        "outline": [_r(p) for p in poly],
        "plug": {"u": pl["u"], "v": pl["v"], "height": pl["height"], "side": "top"},
        "module": {
            "u": m["u"],
            "v": m["v"],
            "width": m["width"],
            "length": m["length"],
            "thickness": m["thickness"],
            "side": "top",
            "note": "footprint origin on the module's bottom edge; the module extends length up from it",
        },
        "robot": {
            "frame": "spec/main.toml robot frame: x forward, y left, z up from the main board's bottom surface",
            "origin": [
                round(face_x, 4),
                mt["receptacle_y"],
                round(main["pcb"]["thickness"] + mt["centre_height"], 4),
            ],
            "u": [0, 1, 0],
            "v": [0, 0, 1],
            "component_side": [1, 0, 0],
        },
    }


EXPORTS = {"encoder": encoder_json, "main": main_json, "main2": main2_json, "bluetooth": bluetooth_json}


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
