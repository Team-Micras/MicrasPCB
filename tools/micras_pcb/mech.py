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
    """Footprints the spec positions, keyed by their Zener instance path."""
    return {s[k]["path"]: s[k] for k in ("sensor", "connector") if k in s}


def _xy(s: dict, p: tuple[float, float]) -> tuple[float, float]:
    return s["kicad"]["origin_x"] + p[0], s["kicad"]["origin_y"] - p[1]


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


def apply(board: str, text: str) -> tuple[str, list[str]]:
    """Return the layout text with the spec applied, and the list of changes made."""
    s = spec.load(board)
    root = sexpr.parse(text)
    edits, changes = [], []

    # Edge.Cuts: the spec owns the whole layer.
    old_edges = [
        n
        for n in root.children()
        if n.head and n.head.startswith("gr_") and (layer := n.child("layer")) and layer.atoms() == ["Edge.Cuts"]
    ]
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

    # Aux (drill/placement) and grid origins on the spec origin, so exports use the spec frame.
    setup = root.child("setup")
    ox, oy = sexpr.fmt(s["kicad"]["origin_x"]), sexpr.fmt(s["kicad"]["origin_y"])
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
        x, y = _xy(s, (p["u"], p["v"]))
        want_at = f"(at {sexpr.fmt(x)} {sexpr.fmt(y)}" + (f" {sexpr.fmt(rot)})" if len(a) > 2 else ")")
        if text[at.start : at.end] != want_at:
            edits.append((at.start, at.end, want_at))
            changes.append(f"{path} moved to ({p['u']}, {p['v']})")
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

    return sexpr.splice(text, edits), changes


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


def mech_json(board: str) -> dict:
    """The board for MicrasHardware and micras-simulation, in the spec frame."""
    s = spec.load(board)
    poly = [pt for e in OUTLINES[board](s) for pt in sample(e)]
    return {
        "board": board,
        "source": f"MicrasPCB spec/{board}.toml",
        "frame": "origin at the tab centre on the main board top surface; u right (chip side view), v up; mm",
        "thickness": s["pcb"]["thickness"],
        "outline": [[round(u, 4), round(v, 4)] for u, v in poly],
        "top": s["outline"]["top"],
        "tab": {"width": s["tab"]["width"], "depth": s["tab"]["depth"]},
        "sensor": {"u": s["sensor"]["u"], "v": s["sensor"]["v"], "side": "top"},
    }


def run(board: str, check: bool) -> int:
    if not (spec.SPEC_DIR / f"{board}.toml").is_file():
        print(f"{board}: no spec/{board}.toml, no spec-owned mechanics to apply or check")
        return 0
    pcb = board_pcb(board)
    text = pcb.read_text()
    new, changes = apply(board, text)
    if check:
        if changes:
            print(f"{pcb}: drifted from spec/{board}.toml:")
            for c in changes:
                print(f"  - {c}")
            print(f"run `micras-pcb mech {board}` and commit the result")
            return 1
        print(f"{pcb}: matches spec/{board}.toml")
        return 0
    if changes:
        pcb.write_text(new)
        for c in changes:
            print(f"  {c}")
    out = build_dir(board) / f"{board}_mech.json"
    out.write_text(json.dumps(mech_json(board), indent=1) + "\n")
    print(
        f"{pcb}: {'updated' if changes else 'already matches the spec'}; wrote {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}"
    )
    return 0
