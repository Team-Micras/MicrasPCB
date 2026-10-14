"""Apply a board's mechanical spec to its KiCad layout, and export it for the other repos.

The spec owns the Edge.Cuts outline, the aux/grid origin and the position of the footprints it
names (written locked). KiCad owns everything else: the remaining placement, routing and zones.

    micras-pcb mech encoder            # rewrite the layout from spec/encoder.toml
    micras-pcb mech encoder --check    # fail if the layout drifted from the spec (CI)
"""

from __future__ import annotations

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
        # vertical tangents at both ends, matching the Altium MicrasEncoder.PcbDoc spline within 0.03 mm
        Bezier((hb, 0), (hb, ts / 2), (hw, ts / 2), (hw, ts)),
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


OUTLINES = {"encoder": encoder_outline}


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
    hl, hw = e["length"] / 2, e["width"] / 2
    for path, (cx, cy) in slots(s).items():
        c = [(cx - hl, cy - hw), (cx + hl, cy - hw), (cx + hl, cy + hw), (cx - hl, cy + hw)]
        if not all(_has_line(lines, a, b) for a, b in zip(c, [*c[1:], c[0]], strict=True)):
            problems.append(f"no {e['length']} x {e['width']} mm encoder slot at ({cx}, {cy}) for {path}")

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


FEATURES = {"main": features, "bluetooth": bluetooth_features}


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
        for path in placements(s):
            fp = fps.get(path)
            drills = [float(d.atoms()[0]) for pad in fp.children("pad") if (d := pad.child("drill"))] if fp else []
            if drills != [s["holes"]["diameter"]]:
                problems.append(f"{path}: drill {drills}, spec {s['holes']['diameter']} mm")
    return problems


def _pt(s, p) -> str:
    x, y = _xy(s, p)
    return f"{sexpr.fmt(x)} {sexpr.fmt(y)}"


def _edge_item(s: dict, e, i: int) -> str:
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
    """Direction-independent geometry of an Edge.Cuts item."""
    pts = [tuple(round(float(v), 4) for v in c.atoms()) for c in n.children() if c.head in ("start", "mid", "end")]
    if n.head == "gr_curve":
        pts = [tuple(round(float(v), 4) for v in c.atoms()) for c in n.child("pts").children("xy")]
        return (n.head, min(tuple(pts), tuple(reversed(pts))))
    if n.head == "gr_arc":
        start, mid, end = pts
        return (n.head, tuple(sorted((start, end))), mid)
    return (n.head, tuple(sorted(pts)))


def apply(board: str, text: str) -> tuple[str, list[str], list[str]]:
    """The layout text with the spec applied, the changes made, and the problems only KiCad can fix."""
    s = spec.load(board)
    root = sexpr.parse(text)
    edits, changes, problems = [], [], []

    old_edges = edge_items(root)
    if board in OUTLINES:
        # Edge.Cuts: the spec owns the whole layer.
        new_items = [_edge_item(s, e, i) for i, e in enumerate(OUTLINES[board](s))]
        new_edges = "".join(new_items)
        # compared as geometry: KiCad re-sorts board graphics and normalises arc direction when it saves
        if sorted(map(_edge_key, old_edges)) != sorted(_edge_key(sexpr.parse(i)) for i in new_items):
            changes.append(f"Edge.Cuts outline ({len(old_edges)} -> {new_edges.count('(layer')} items)")
            for n in old_edges:
                edits.append((*sexpr.line_span(text, n), ""))
            anchor = root.children("footprint")[0] if root.children("footprint") else None
            at = sexpr.line_span(text, anchor)[0] if anchor else root.end - 1
            edits.append((at, at, new_edges))
    else:
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
    poly = [pt for e in OUTLINES["encoder"](s) for pt in sample(e)]
    return {
        "frame": "origin at the tab centre on the main board top surface; u right (chip side view), v up; mm",
        "thickness": s["pcb"]["thickness"],
        "outline": [_r(p) for p in poly],
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
            {"name": path.split(".")[1], "centre": list(c), "length": sl["length"], "width": sl["width"]}
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


EXPORTS = {"encoder": encoder_json, "main": main_json, "bluetooth": bluetooth_json}


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
