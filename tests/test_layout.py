"""Layout checks on every board: decoupling next to its pin, the encoder joint's slot, fab hygiene.

The placement-dependent checks skip, with the reason, while a board's layout has no outline: until
then the footprints sit where the netlist sync packed them, which says nothing about the design. A
schematic-only board (no layout file, Project(layout = False)) is not listed at all.
"""

import json
import math
import shutil
import tomllib

import pytest
from micras_pcb import jlc, layout, sexpr, spec
from micras_pcb.paths import ROOT, board_pcb, layout_boards, layout_dir

from .conftest import needs_kicad
from .design import design

needs_pcb = pytest.mark.skipif(shutil.which("pcb") is None, reason="pcb not installed")

# Decoupling the datasheets ask to sit at the pin ("as close as possible", "near", "close to"):
# (MPN prefix, pin names, count, capacitance range in F, source). count None: one capacitor per pad
# (the STM32's five VDD pads); a number: that many capacitors at the pin group.
PER_PAD = None
DECOUPLING = [
    (
        "STM32H725",
        ("VDD",),
        PER_PAD,
        (90e-9, 110e-9),
        "AN5419 Rev 3 Table 2 p7: 100 nF per VDD pin, as close as possible",
    ),
    ("STM32H725", ("VDDA",), 1, (90e-9, 110e-9), "AN5419 Table 2 p7: 100 nF as close as possible to VDDA"),
    ("STM32H725", ("VBAT",), 1, (90e-9, 110e-9), "AN5419 Table 2 p7: 100 nF close to the VBAT pin"),
    ("STM32H725", ("VCAP1",), 1, (90e-9, 110e-9), "AN5419 Figure 5 p10: 100 nF close to each VCAP pin"),
    ("STM32H725", ("VCAP2",), 1, (90e-9, 110e-9), "AN5419 Figure 5 p10: 100 nF close to each VCAP pin"),
    ("STM32H725", ("VCAP3",), 1, (90e-9, 110e-9), "AN5419 Figure 5 p10: 100 nF close to each VCAP pin"),
    ("LSM6DSV", ("Vdd",), 1, (90e-9, 110e-9), "DS13476 Rev 5 Table 2 note 1, Figure 27: 100 nF as near as possible"),
    ("LSM6DSV", ("Vdd_IO",), 1, (90e-9, 110e-9), "DS13476 Rev 5 Table 2 note 1, Figure 27: 100 nF as near as possible"),
    (
        "TSC2020",
        ("VCC",),
        1,
        (90e-9, 110e-9),
        "DS14393 Rev 7 section 5.11: 100 nF as close as possible to the supply pins",
    ),
    (
        "L6205",
        ("VSA", "VSB"),
        1,
        (90e-9, 220e-9),
        "L6205 p12: 100-200 nF ceramic between VSA/VSB and ground near the L6205",
    ),
    ("STSPIN958", ("VS",), 2, (420e-9, 520e-9), "DS14341 Rev 1 section 8, Table 12: 2 x 470 nF close to the VS pins"),
    ("STSPIN958", ("VDD",), 1, (198e-9, 242e-9), "DS14341 Rev 1 section 8, Table 12: 220 nF close to VDD"),
    (
        "INA241",
        ("VS",),
        1,
        (90e-9, 110e-9),
        "SBOSA30D sections 8.3.1, 8.4.1: 0.1 uF as close as possible to the supply and ground pins",
    ),
    (
        "DRV8874",
        ("VM",),
        1,
        (90e-9, 110e-9),
        "SLVSF66A Table 1, section 10.1: CVM1 0.1 uF from VM to GND close to the pins",
    ),
    (
        "ADP7142",
        ("VIN",),
        1,
        (2.2e-6, 22e-6),
        "ADP7142 Rev H Table 2, p20: >= 2.2 uF input capacitor close to the pins",
    ),
    (
        "ADP7142",
        ("VOUT",),
        1,
        (2.2e-6, 22e-6),
        "ADP7142 Rev H Table 2, p20: >= 2.2 uF output capacitor close to the pins",
    ),
]
# Not listed: the AS5047U in 3.3 V mode. Its datasheet (v1-00 p11, Figure 11) asks "close to chip"
# only for the 1 uF of the 5 V LDO mode; the 3.3 V mode drawing just shows 100 nF on VDD.
# The datasheets give no number for "close". This project reads it as: the capacitor's nearest pad
# centre within 3 mm of the pin's pad centre, which puts an 0402 beside the pin with one via (the
# previous main board's LSM6DSV capacitors sit 2.1-2.5 mm from the part).
MAX_DECOUPLING_MM = 3.0

# A schematic-only board (no .kicad_pcb yet) has nothing to check here.
LAYOUT_BOARDS = layout_boards()


def _placed(board: str) -> layout.Board:
    pcb = layout.load(board)
    if not pcb.placed:
        pytest.skip(f"{board}: the layout has no Edge.Cuts outline yet (placement not done)")
    return pcb


def _match(groups: list[list[str]]) -> dict[int, str]:
    """Maximum matching of pin groups to distinct capacitors (groups[i] lists acceptable capacitors)."""
    owner: dict[str, int] = {}

    def augment(i: int, seen: set[str]) -> bool:
        for cap in groups[i]:
            if cap in seen:
                continue
            seen.add(cap)
            if cap not in owner or augment(owner[cap], seen):
                owner[cap] = i
                return True
        return False

    for i in range(len(groups)):
        augment(i, set())
    return {i: cap for cap, i in owner.items()}


def decoupling_findings(board: str, pcb: layout.Board) -> list[str]:
    """Every listed pin (group) gets its own capacitor within MAX_DECOUPLING_MM; one capacitor
    serves one pin of a part."""
    d = design(board)
    problems = []
    for ref in sorted({r for mpn, *_ in DECOUPLING for r in d.refs(mpn)}):
        wants = []  # (description, source, [(distance, cap)] in range on the pin's rail)
        for mpn, names, count, (lo, hi), source in DECOUPLING:
            if ref not in d.refs(mpn):
                continue
            numbers = [n for name in names for n in d.pads(ref, name)]
            if not numbers:
                problems.append(f"{ref} has no pin named {'/'.join(names)}")
                continue
            for group in [[n] for n in numbers] if count is PER_PAD else [numbers] * count:
                rail = d.net(ref, group[0])
                pads = [p for n in group for p in pcb.footprints[ref].pads_named(n)]
                options = []
                for cap in d.two_terminal("capacitor", rail, "GND"):
                    value = d.value(cap, "capacitance")
                    if value is not None and lo <= value <= hi and cap in pcb.footprints:
                        dist = min(math.dist(a.xy, c.xy) for a in pads for c in pcb.footprints[cap].pads if c.net)
                        options.append((dist, cap))
                wants.append((f"{ref} {'/'.join(names)} (pad {', '.join(group)}, {rail})", source, sorted(options)))
        matched = _match([[cap for dist, cap in opts if dist <= MAX_DECOUPLING_MM] for _, _, opts in wants])
        for i, (where, source, options) in enumerate(wants):
            if i in matched:
                continue
            if not options:
                problems.append(f"{where}: no capacitor of the required value; {source}")
            else:
                dist, cap = options[0]
                problems.append(
                    f"{where}: no capacitor of its own within {MAX_DECOUPLING_MM} mm (nearest {cap} at {dist:.1f} mm); {source}"
                )
    return problems


@needs_kicad
@needs_pcb
@pytest.mark.parametrize("board", LAYOUT_BOARDS)
def test_decoupling_sits_at_its_pin(board):
    pcb = _placed(board)
    problems = decoupling_findings(board, pcb)
    assert not problems, "\n".join(problems)


# Bypass capacitors whose loop the datasheet wants on the IC's own layer, with no via between the
# capacitor and the pin (TI SLVA959B section 5.3.1; DRV8874 SLVSF66A section 10.1 and Figure 37):
# the capacitor DECOUPLING matches to such a pin has its rail pad joined to the pin by copper of the
# pin's layer alone (tracks and pours of the rail on that layer, no via).
DECOUPLING_SAME_LAYER = [("DRV8874", ("VM",))]


def _layer_zones(board: str) -> list[tuple[str, list[str], list[tuple[float, float]]]]:
    """The board's pours (net, layers, outline): rule areas and teardrops left out."""
    root = sexpr.parse(board_pcb(board).read_text())
    out = []
    for z in root.children("zone"):
        if z.child("keepout") or (z.child("attr") and z.child("attr").child("teardrop")):
            continue
        name = z.child("net_name") or z.child("net")
        layers = (z.child("layers") or z.child("layer")).atoms()
        pts = [(float(a), float(b)) for a, b in (q.atoms() for q in z.child("polygon").child("pts").children("xy"))]
        out.append((name.atoms()[-1] if name else "", layers, pts))
    return out


def _in_poly(p: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
    x, y = p
    hit = False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1], strict=True):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def _seg_point(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    u = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.dist(p, (a[0] + u * dx, a[1] + u * dy))


def same_layer_findings(board: str, pcb: layout.Board) -> list[str]:
    d = design(board)
    zones = _layer_zones(board)
    problems = []
    for mpn, names in DECOUPLING_SAME_LAYER:
        for ref in d.refs(mpn):
            for name in names:
                for num in d.pads(ref, name):
                    pin = pcb.footprints[ref].pads_named(num)[0]
                    layer = next(l_ for l_ in ("F.Cu", "B.Cu") if l_ in pin.layers)
                    rail = pin.net
                    # the capacitor of DECOUPLING's value range nearest the pin on the rail
                    spec_ = next(e for e in DECOUPLING if mpn.startswith(e[0]) and name in e[1])
                    lo, hi = spec_[3]
                    caps = [
                        c
                        for c in d.two_terminal("capacitor", rail, "GND")
                        if c in pcb.footprints and lo <= (d.value(c, "capacitance") or 0) <= hi
                    ]
                    if not caps:
                        problems.append(f"{ref}.{num}: no capacitor on {rail}")
                        continue
                    cap = min(caps, key=lambda c: min(math.dist(p.xy, pin.xy) for p in pcb.footprints[c].pads))
                    target = next(p for p in pcb.footprints[cap].pads if p.net == rail)
                    # items of the rail on the layer: pads (inscribed circle), tracks, pours
                    items = [
                        ("pad", p.xy, min(p.size) / 2)
                        for f in pcb.footprints.values()
                        for p in f.pads
                        if p.net == rail and (layer in p.layers or "*.Cu" in p.layers)
                    ]
                    items += [
                        ("track", (t.start, t.end), t.width / 2)
                        for t in pcb.tracks
                        if t.net == rail and t.layer == layer
                    ]
                    items += [("zone", pts, 0.0) for n, layers, pts in zones if n == rail and layer in layers]

                    def touch(a, b):
                        (ka, ga, ra), (kb, gb, rb) = a, b
                        if ka == "zone" and kb == "zone":
                            return any(_in_poly(q, gb) for q in ga) or any(_in_poly(q, ga) for q in gb)
                        if kb == "zone":
                            a, b = b, a
                            (ka, ga, ra), (kb, gb, rb) = a, b
                        if ka == "zone":
                            pts = [gb] if kb == "pad" else list(gb)
                            return any(_in_poly(q, ga) for q in pts)
                        if ka == "pad" and kb == "pad":
                            return math.dist(ga, gb) <= ra + rb
                        if ka == "track" and kb == "pad":
                            a, b = b, a
                            (ka, ga, ra), (kb, gb, rb) = a, b
                        if ka == "pad":
                            return _seg_point(ga, *gb) <= ra + rb
                        return (
                            min(_seg_point(q, *gb) for q in ga) <= ra + rb
                            or min(_seg_point(q, *ga) for q in gb) <= ra + rb
                        )

                    start = next(i for i, it in enumerate(items) if it[0] == "pad" and it[1] == pin.xy)
                    goal = next(i for i, it in enumerate(items) if it[0] == "pad" and it[1] == target.xy)
                    seen, todo = {start}, [start]
                    while todo:
                        i = todo.pop()
                        for j in range(len(items)):
                            if j not in seen and touch(items[i], items[j]):
                                seen.add(j)
                                todo.append(j)
                    if goal not in seen:
                        problems.append(f"{ref}.{num} ({rail}): {cap} not joined to the pin on {layer} without a via")
    return problems


@needs_kicad
@needs_pcb
@pytest.mark.parametrize("board", LAYOUT_BOARDS)
def test_decoupling_joins_its_pin_on_the_same_layer(board):
    if not any(design(board).refs(mpn) for mpn, _ in DECOUPLING_SAME_LAYER):
        pytest.skip(f"{board}: none of {[m for m, _ in DECOUPLING_SAME_LAYER]}")
    pcb = _placed(board)
    problems = same_layer_findings(board, pcb)
    assert not problems, "\n".join(problems)


# --- the encoder joint: the encoder board's tab in the main board's slots ------------------------

# JLCPCB PCB capabilities (jlcpcb.com/capabilities/pcb-capabilities, read 2026-10-14):
# "The minimum Non-Plated Slot Width is 1.0mm, please draw the slot outline in the mechanical
# layer (GM1 or GKO)"; "Rectangular holes and slots without rounded corners are not supported";
# board thickness below 1.0 mm: +-0.1 mm. A slot is milled by a cutter no wider than the slot, so
# its corners come out with a radius of at least half the 1.0 mm minimum width.
JLC_MIN_SLOT_MM = 1.0
JLC_THIN_BOARD_TOL_MM = 0.1


def _slot_outline(pcb: layout.Board, ref: str) -> tuple[float, float, float] | None:
    """(width, length, drawn corner radius) of the Edge.Cuts cut-out at an EncoderSlot footprint."""
    fp = pcb.footprints[ref]
    cx, cy = fp.xy
    t = math.radians(fp.rotation)
    near, radius = [], 0.0
    for kind, pts, r in pcb.edge_shapes:
        if all(math.dist(p, (cx, cy)) < 4.0 for p in pts):
            for x, y in pts:
                dx, dy = x - cx, y - cy
                near.append((dx * math.cos(t) - dy * math.sin(t), dx * math.sin(t) + dy * math.cos(t)))
            if kind == "gr_arc" and r:
                radius = max(radius, r)
    if not near:
        return None
    xs, ys = [p[0] for p in near], [p[1] for p in near]
    return max(xs) - min(xs), max(ys) - min(ys), radius


def slot_findings(pcb: layout.Board, refs: list[str]) -> list[str]:
    enc = spec.load("encoder")
    tab_w = enc["tab"]["width"]
    tab_t = enc["pcb"]["thickness"] + JLC_THIN_BOARD_TOL_MM
    problems = []
    for ref in refs:
        found = _slot_outline(pcb, ref)
        if found is None:
            problems.append(f"{ref}: no Edge.Cuts slot at the footprint")
            continue
        w, length, drawn_r = found
        r = max(drawn_r, JLC_MIN_SLOT_MM / 2)
        if w < JLC_MIN_SLOT_MM - 1e-6:
            problems.append(f"{ref}: slot {w:.2f} mm wide, below JLCPCB's {JLC_MIN_SLOT_MM} mm minimum non-plated slot")
        if w < tab_t - 1e-6:
            problems.append(
                f"{ref}: slot {w:.2f} mm wide for a {tab_t:.2f} mm thick encoder board (spec thickness + 0.1 mm)"
            )
        # the tab's corner (tab_w / 2, tab_t / 2) must lie inside the slot's rounded end
        cx, cy = length / 2 - r, w / 2 - r
        ex, ey = max(tab_w / 2 - cx, 0.0), max(tab_t / 2 - cy, 0.0)
        if tab_w > length or math.hypot(ex, ey) > r + 1e-6:
            problems.append(
                f"{ref}: a {length:.2f} x {w:.2f} mm slot with {r:.2f} mm milled corners does not take the "
                f"{tab_w} x {tab_t:.2f} mm encoder tab (spec/encoder.toml)"
            )
    return problems


@needs_kicad
@needs_pcb
def test_encoder_slots_take_the_encoder_tab():
    pcb = _placed("main")
    refs = sorted(r for r, f in pcb.footprints.items() if "EncoderSlot" in f.lib_id)
    assert refs, "no EncoderSlot footprints on the main board"
    problems = slot_findings(pcb, refs)
    assert not problems, "\n".join(problems)


# --- routing style: octilinear tracks, no acute corners ------------------------------------------

# Tracks run as on the previous revisions, hand-routed in Altium: every track straight, at a
# multiple of 45 degrees, no arcs. A segment counts as octilinear when its end lies within
# OCTILINEAR_TOL_MM of the nearest 45-degree line through its start: KiCad stores coordinates on a
# 1 nm grid, and the conversion from Altium leaves segments 0.06-3.4 um long up to 10 nm off the
# line (0.1-6.3 degrees, from rounding alone), far below any copper feature. Zero-length segments
# have no direction (DRC reports them: tracks_crossing, track_dangling).
OCTILINEAR_TOL_MM = 1e-3
# Two segments of a net joined end to end on a layer at an interior angle below 90 degrees leave a
# wedge that traps etchant (an acid trap), unless the joint sits in a pad or via, whose copper
# fills it.
MIN_CORNER_DEG = 90.0
ANGLE_TOL_DEG = 0.1


def _pt(p: tuple[float, float]) -> str:
    return f"({p[0]:.4f}, {p[1]:.4f})"


def _covered(pcb: layout.Board, layer: str, xy: tuple[float, float]) -> bool:
    """xy lies in the solid copper of a via, or of a pad on the layer (its inscribed circle)."""
    if any(math.dist(xy, v.xy) <= v.size / 2 for v in pcb.vias):
        return True
    return any(
        math.dist(xy, p.xy) <= min(p.size) / 2
        for f in pcb.footprints.values()
        for p in f.pads
        if layer in p.layers or "*.Cu" in p.layers
    )


def routing_findings(board: str, pcb: layout.Board) -> list[str]:
    """Every track a straight segment at a multiple of 45 degrees; no acute corner outside a pad or via."""
    problems = []
    segments = []
    for t in pcb.tracks:
        where = f"{board} {t.net} {t.layer} {_pt(t.start)} -> {_pt(t.end)}"
        if t.kind == "arc":
            problems.append(f"{where}: arc track (curved)")
            continue
        dx, dy = t.end[0] - t.start[0], t.end[1] - t.start[1]
        length = math.hypot(dx, dy)
        if length == 0:
            continue
        segments.append(t)
        angle = math.degrees(math.atan2(-dy, dx))  # counter-clockwise from +x on screen (y down)
        off = abs((angle + 22.5) % 45 - 22.5)
        miss = length * math.sin(math.radians(off))
        if miss > OCTILINEAR_TOL_MM:
            problems.append(
                f"{where}: {length:.3f} mm at {angle:.2f} deg, {off:.2f} deg off a multiple of 45 "
                f"(end {miss * 1000:.0f} um off the 45-degree line)"
            )
    ends: dict[tuple, list[tuple[tuple[float, float], tuple[float, float]]]] = {}
    for t in segments:
        for a, b in ((t.start, t.end), (t.end, t.start)):
            ends.setdefault((t.net, t.layer, round(a[0], 5), round(a[1], 5)), []).append((a, b))
    for (net, layer, *_), arms in ends.items():
        corner = arms[0][0]
        if len(arms) < 2 or _covered(pcb, layer, corner):
            continue
        for i, (a1, b1) in enumerate(arms):
            for a2, b2 in arms[i + 1 :]:
                u = (b1[0] - a1[0], b1[1] - a1[1])
                v = (b2[0] - a2[0], b2[1] - a2[1])
                cos = (u[0] * v[0] + u[1] * v[1]) / (math.hypot(*u) * math.hypot(*v))
                interior = math.degrees(math.acos(max(-1.0, min(1.0, cos))))
                if interior < MIN_CORNER_DEG - ANGLE_TOL_DEG:
                    problems.append(
                        f"{board} {net} {layer} corner at {_pt(corner)}: {interior:.1f} deg between the segments "
                        f"to {_pt(b1)} and {_pt(b2)}, below {MIN_CORNER_DEG:.0f} (acid trap)"
                    )
    return problems


@pytest.mark.parametrize("board", LAYOUT_BOARDS)
def test_tracks_are_octilinear_without_acute_corners(board):
    problems = routing_findings(board, layout.load(board))
    assert not problems, "\n".join(problems)


def _segment(net: str, a: tuple[float, float], b: tuple[float, float], head: str = "segment") -> str:
    mid = f"(mid {(a[0] + b[0]) / 2} {(a[1] + b[1]) / 2 + 1})" if head == "arc" else ""
    return f'({head} (start {a[0]} {a[1]}) {mid} (end {b[0]} {b[1]}) (width 0.2) (layer "F.Cu") (net "{net}"))'


def test_routing_rule_flags_only_off_angle_arcs_and_acute_corners():
    board = layout.parse(
        "(kicad_pcb "
        + " ".join(
            [
                _segment("A", (0, 0), (1, 0)),  # 0 deg, then 45 deg: a 135 deg corner
                _segment("A", (1, 0), (2, -1)),
                _segment("B", (0, 5), (0.002425, 4.99828)),  # 2.4 um at 45.17 deg: 7 nm off the line
                _segment("B", (5, 5), (5, 5)),  # zero length
                _segment("C", (0, 10), (2, 9)),  # 26.6 deg
                _segment("D", (0, 15), (1, 15), "arc"),
                _segment("E", (0, 20), (1, 20)),  # 45 deg corner at (1, 20)
                _segment("E", (1, 20), (0, 19)),
                _segment("F", (0, 25), (1, 25)),  # the same corner in a via
                _segment("F", (1, 25), (0, 24)),
                '(via (at 1 25) (size 0.45) (drill 0.3) (layers "F.Cu" "B.Cu") (net "F"))',
            ]
        )
        + ")"
    )
    problems = routing_findings("test", board)
    assert [p.split()[1] for p in problems] == ["C", "D", "E"], "\n".join(problems)


# --- fab and assembly hygiene, every footprint --------------------------------------------------


def _assembled(board: str) -> list[layout.Footprint]:
    return [f for f in layout.load(board).footprints.values() if f.assembled and f.ref and not f.ref.startswith("#")]


@pytest.mark.parametrize("board", LAYOUT_BOARDS)
def test_every_assembled_footprint_has_a_courtyard(board):
    # IPC-7351 courtyard: KiCad's DRC checks courtyard overlap (and JLCPCB's placement spacing)
    # only for footprints that draw one on F.CrtYd/B.CrtYd.
    missing = sorted(f.ref for f in _assembled(board) if not (f.graphic_layers & layout.COURTYARD))
    assert not missing, f"no courtyard on F.CrtYd/B.CrtYd: {', '.join(missing)}"


@pytest.mark.parametrize("board", LAYOUT_BOARDS)
def test_every_smd_pad_of_an_assembled_part_has_paste(board):
    # Reflow assembly prints paste through the stencil (F.Paste/B.Paste); an SMD pad without a
    # paste opening is not soldered. A pad's own opening counts unless a negative paste margin
    # cancels it; a paste shape drawn on the footprint over the pad counts too (Q6, U2 draw theirs).
    missing = []
    for f in _assembled(board):
        bare = [p.number for p in f.pads if p.kind == "smd" and p.net and not f.pasted(p)]
        if bare:
            missing.append(f"{f.ref} pads {sorted(set(bare))}")
    assert not missing, f"SMD pads without paste: {'; '.join(missing)}"


@pytest.mark.parametrize("board", LAYOUT_BOARDS)
def test_every_assembled_footprint_has_an_embedded_3d_model(board):
    # The STEP and GLB outputs (make review) and MicrasHardware's import need every part's body;
    # models are embedded in the footprint (pcb embed-step), so they travel with the board.
    pcb = layout.load(board)
    problems = []
    for f in _assembled(board):
        if not f.models:
            problems.append(f"{f.ref}: no 3D model")
        for m in f.models:
            if m.startswith("kicad-embed://") and m.removeprefix("kicad-embed://") not in pcb.embedded_files:
                problems.append(f"{f.ref}: {m} is not embedded in the board")
    assert not problems, "\n".join(problems)


# --- silkscreen text ------------------------------------------------------------------------------

SILK_LAYERS = {"F.SilkS", "B.SilkS", "F.Silkscreen", "B.Silkscreen"}


def _hidden(node: sexpr.Node) -> bool:
    for n in (node, node.child("effects")):
        if n is None:
            continue
        if "hide" in n.atoms():
            return True
        h = n.child("hide")
        if h is not None and h.atoms()[:1] in ([], ["yes"]):
            return True
    return False


def _silk_texts(node: sexpr.Node, owner: str = ""):
    """(where, text, height, width, stroke) of every visible silkscreen text: board texts,
    footprint texts and footprint fields."""
    for child in node.children():
        if child.head == "footprint":
            yield from _silk_texts(child, child.prop("Reference") or "?")
        elif child.head in ("gr_text", "fp_text", "property"):
            layer = child.child("layer")
            font = child.child("effects") and child.child("effects").child("font")
            if layer is None or layer.atoms()[0] not in SILK_LAYERS or font is None or _hidden(child):
                continue
            h, w = (float(v) for v in font.child("size").atoms()[:2])
            t = float(font.child("thickness").atoms()[0]) if font.child("thickness") else h * 0.15
            text = child.atoms()[{"property": -1, "fp_text": 1}.get(child.head, 0)]
            where = f"{owner} " if owner else "board "
            yield where + child.head, text, h, w, t


# The board's silkscreen limits, written into its .kicad_pro: the height by Zener
# (<board>.zen Silkscreen), the stroke by `micras-pcb rules` (rules/kicad-severities.toml
# [design.<board>]). KiCad's stroke font draws a text's stroke at most a quarter of its smaller
# size, so the stroke that reaches the Gerbers is min(thickness, size / 4).
@pytest.mark.parametrize("board", ["main", "bluetooth"])
def test_silkscreen_text_meets_the_board_minimum(board):
    rules = json.loads((layout_dir(board) / f"{board}.kicad_pro").read_text())["board"]["design_settings"]["rules"]
    min_h, min_t = rules["min_text_height"], rules["min_text_thickness"]
    problems = []
    for where, text, h, w, t in _silk_texts(sexpr.parse(board_pcb(board).read_text())):
        stroke = min(t, min(h, w) / 4)
        if min(h, w) < min_h - 1e-6 or stroke < min_t - 1e-6:
            problems.append(f"{where} {text!r}: {h} x {w} mm, stroke {stroke:.3f} mm (minimum {min_h} mm, {min_t} mm)")
    assert not problems, "\n".join(problems)


def test_jlc_part_data_is_complete():
    # parts/jlc.toml: every entry carries what `make fab` and `make parts-online` need.
    raw = tomllib.loads((ROOT / "parts" / "jlc.toml").read_text())["parts"]
    problems = []
    for mpn, e in raw.items():
        if not str(e.get("lcsc", "")).startswith("C") or not str(e["lcsc"])[1:].isdigit():
            problems.append(f"{mpn}: lcsc {e.get('lcsc')!r} is not an LCSC number")
        if e.get("type") not in ("basic", "extended"):
            problems.append(f"{mpn}: type {e.get('type')!r}")
        if not isinstance(e.get("rotation", 0), int | float) or not isinstance(e.get("rotation_verified"), bool):
            problems.append(f"{mpn}: rotation / rotation_verified missing")
        if not e.get("source"):
            problems.append(f"{mpn}: no source")
    assert not problems, "\n".join(problems)


@needs_kicad
@needs_pcb
@pytest.mark.parametrize("board", LAYOUT_BOARDS)
def test_jlc_bom_excludes_dnp(board, tmp_path):
    # The assembler's BOM and CPL list the same parts: JLCPCB fits every BOM row, so a DNP part in
    # the BOM (a 0 Ohm across a choke, a jumper's extended-part fee) would be fitted or charged.
    rows, errors = jlc.jlc_bom(board)
    assert not errors, "\n".join(errors)
    bom = {d for row in rows for d in row["Designator"].split(",")}
    members = [m for line in jlc.design_bom(board) for m in line["members"]]
    dnp = sorted(bom & {m["designator"] for m in members if m.get("dnp")})
    assert not dnp, f"DNP parts in the JLCPCB BOM: {', '.join(dnp)}"
    placed = {r["Ref"] for r in jlc.positions(board, tmp_path)} & {m["designator"] for m in members}
    assert bom == placed, f"BOM only: {sorted(bom - placed)}; CPL only: {sorted(placed - bom)}"
