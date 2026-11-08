"""The wall-sensor board: its joint to the main board, the fit of the parts it seats and the
separation of its receiver from its emitter's switching.

Frame: spec/wall.toml (u right seen from the front, v up from the main board's top surface).
"""

import math
import re
from pathlib import Path

import pytest
from micras_pcb import layout, mech, spec
from micras_pcb.nets import ANALOG_GAP

from .conftest import needs_kicad
from .design import design

S = spec.load("wall")
MAIN = spec.load("main")
OX, OY = S["kicad"]["origin_x"], S["kicad"]["origin_y"]

# J1 pin -> net: the main board's wall joint meets the same pins. Changing it breaks every main
# board built for it. Odd pins on the front face, even behind them; pins 1-2 on the left seen from
# the front.
HEADER_PINOUT = {"1": "Wall_Sensor", "2": "GND", "3": "3V3_A", "4": "3V3_D", "5": "EMITTER_SINK", "6": "PWM"}
# The emitter's switched nets (the selector's drive, gate, drain and source; 175 mA pulses) and the
# receiver's output, a current into the main board's 1 kOhm load (boards/wall/wall.zen).
SWITCHING = {"PWM", "DRIVE", "GATE", "LED_K", "EMITTER_SINK"}
RECEIVER = "Wall_Sensor"
# The main board's side of the joint declares the emitter resistor its emitter checks use.
WALL_JOINT = Path(__file__).resolve().parents[1] / "components/micras/WallJoint/WallJoint.zen"

# Largest outlines (components/micras/WallSensor docstring): flange radii, the TPS601A key tab
# (1.0 +-0.2 mm beyond the flange, 1.0 +-0.2 mm wide, 45 deg from the lead line beside pin 1), the
# SFH 4550's wider lead section from 1.0 mm behind its seating plane.
SFH_FLANGE_R, TPS_FLANGE_R = 5.9 / 2, 5.8 / 2
TAB_REACH, TAB_W = 1.2, 1.2
SFH_DAMBAR = 1.0
MAIN_PIN_PAD = 1.1  # mm, the main board's pads for J1's pins
JLC_THIN_BOARD_TOL = 0.1  # mm, boards below 1.0 mm (spec/encoder.toml pcb.thickness)
JLC_HOLE_MINUS = 0.08  # mm, JLCPCB's finished plated-hole tolerance below the drill
JLC_RING_MULTILAYER = 0.15  # mm, the main board's PTH annular ring minimum (rules/jlcpcb-pdk.toml)
EDGE_CLEARANCE = 0.2  # mm, copper to the board edge (rules/jlcpcb.kicad_dru)
# The board between the header's rows: at its thickest a press fit the brass pins take, at its
# thinnest a gap the solder fills.
PRESS_MAX = 0.05  # mm of interference across both rows
SOLDER_GAP_MAX = 0.1  # mm a side
# The joints on the front face: J1's pads with their solder, which must stay off every flange; a
# key tab that pointed down would lie flat beside pin 1's joint, off its pad by TAB_GAP at least.
SOLDER_MARGIN = 0.2
TAB_GAP = 0.15
# mm: each flange this far inside the paddle's outline at every height, so it seats fully on the
# board: the TPS601A's 1.1 mm by the neck (the owner, 2026-11-03), the SFH 4550's 0.45 mm under the
# top edge (spec/wall.toml outline.top)
FLANGE_INSIDE = {"TPS601A": 1.1, "SFH 4550": 0.45}
JOINT_COURTYARD = 0.25  # mm round the insulator: the main board's joint courtyard (components/micras/WallJoint)


@pytest.fixture(scope="module")
def pcb():
    return layout.load("wall")


def _uv(xy):
    return round(xy[0] - OX, 4), round(OY - xy[1], 4)


def _box(p):
    """A pad's copper as (u0, v0, u1, v1): its size turned with its footprint (multiples of 90 deg)."""
    (u, v), (w, h) = _uv(p.xy), p.size
    return u - w / 2, v - h / 2, u + w / 2, v + h / 2


def _to_box(box, q):
    u0, v0, u1, v1 = box
    return math.hypot(max(u0 - q[0], 0.0, q[0] - u1), max(v0 - q[1], 0.0, q[1] - v1))


@needs_kicad
def test_header_pinout_is_the_main_board_contract():
    d = design("wall")
    got = {pad: d.net("J1", pad) for pad in HEADER_PINOUT}
    assert got == HEADER_PINOUT
    assert S["header"]["pins"] == len(HEADER_PINOUT)


def test_receiver_pin_has_only_quiet_neighbours():
    # Pin n sits at column (n - 1) // 2 along the edge, row (n - 1) % 2 (front, back). Beside it,
    # across the board and diagonally count as neighbours: none of the receiver's may switch.
    at = {n: ((int(n) - 1) // 2, (int(n) - 1) % 2) for n in HEADER_PINOUT}
    rx = next(n for n, net in HEADER_PINOUT.items() if net == RECEIVER)
    near = [
        HEADER_PINOUT[n]
        for n in HEADER_PINOUT
        if n != rx and abs(at[n][0] - at[rx][0]) <= 1 and abs(at[n][1] - at[rx][1]) <= 1
    ]
    assert not set(near) & SWITCHING, f"{RECEIVER} beside {near}"


@needs_kicad
def test_emitter_resistor_is_the_one_the_main_board_checks():
    # The main board's emitter_pulse_within_rating bench reads the joint's emitter_resistor; it must
    # be the wall board's R1.
    m = re.search(r'"emitter_resistor":\s*Resistance\("([0-9.]+)Ohm"\)', WALL_JOINT.read_text())
    assert m, f"{WALL_JOINT} declares no emitter_resistor"
    r1 = design("wall").value("R1", "resistance")
    assert r1 == pytest.approx(float(m.group(1))), f"R1 is {r1} Ohm, the joint declares {m.group(1)} Ohm"


@needs_kicad
def test_sensor_and_header_on_the_front_every_smd_part_on_the_back(pcb):
    # The front face carries the two flanges and the header's odd pins; JLCPCB assembles the rest
    # on the back.
    w = pcb.footprints["W1"]
    assert "Upright" in w.lib_id and w.side == "top", (w.lib_id, w.side)
    assert pcb.footprints["J1"].side == "top"
    front = [r for r, f in pcb.footprints.items() if r not in ("W1", "J1") and f.side != "bottom"]
    assert not front, f"SMD parts on the front, under the flanges: {front}"


def _tab_down_corners(axis_v):
    """The TPS601A key tab's outer corners if it pointed down at pin 1 (left) instead of up: the
    worst case for the header joints below it."""
    d = (-math.sqrt(0.5), -math.sqrt(0.5))
    n = (math.sqrt(0.5), -math.sqrt(0.5))
    tip = TPS_FLANGE_R + TAB_REACH
    return [(d[0] * tip + n[0] * s, axis_v + d[1] * tip + n[1] * s) for s in (-TAB_W / 2, TAB_W / 2)]


@needs_kicad
def test_header_pads_straddle_the_bottom_edge(pcb):
    # Odd pins on front pads, even pins on back pads, at the header's pitch, from the copper-to-edge
    # clearance above the bottom edge to past the longest pin.
    h, bottom = S["header"], S["outline"]["bottom"]
    pads = {p.number: p for p in pcb.footprints["J1"].pads}
    assert sorted(pads) == sorted(HEADER_PINOUT)
    for n, p in pads.items():
        u0, v0, u1, v1 = _box(p)
        want_u = h["u"] + h["pitch"] * ((int(n) - 1) // 2 - 1)
        assert (u0 + u1) / 2 == pytest.approx(want_u), f"J1 pin {n} at u {(u0 + u1) / 2}"
        assert p.layers[0] == ("F.Cu" if int(n) % 2 else "B.Cu"), f"J1 pin {n} on {p.layers}"
        assert v0 == pytest.approx(bottom + EDGE_CLEARANCE), f"J1 pin {n} starts at v {v0}"
        assert v1 == pytest.approx(bottom + h["pad_top"]), f"J1 pin {n} ends at v {v1}"
        assert v1 - bottom >= h["pin_up"] + h["pin_tolerance"] + 0.3 - 1e-9, f"J1 pin {n}: no toe past the pin"
        assert u1 - u0 >= h["pin_section"] + 0.3 - 1e-9, f"J1 pin {n}: no side fillet"


@needs_kicad
def test_receiver_flange_and_tab_clear_the_header_joints(pcb):
    pt_v = S["sensor"]["v"]
    for p in pcb.footprints["J1"].pads:
        if "F.Cu" not in p.layers:
            continue
        box = _box(p)
        # the flange's nearest point to the pad: the circle less the pad's distance from the axis
        gap = _to_box(box, (0.0, pt_v)) - TPS_FLANGE_R - SOLDER_MARGIN
        assert gap >= 0, f"J1 pin {p.number}: the TPS601A flange is {-gap:.2f} mm onto its joint"
        for corner in _tab_down_corners(pt_v):
            gap = _to_box(box, corner)
            assert gap >= TAB_GAP, f"J1 pin {p.number}: a downward key tab would reach {gap:.2f} mm from its pad"


@needs_kicad
def test_flanges_fit_the_board_and_each_other(pcb):
    w = {p.number: _uv(p.xy) for p in pcb.footprints["W1"].pads}
    pt_v, led_v = w["3"][1], w["1"][1]
    assert pt_v == pytest.approx(S["sensor"]["v"]) and led_v == pytest.approx(
        S["sensor"]["v"] + S["sensor"]["led_above"]
    )
    assert led_v - pt_v >= SFH_FLANGE_R + TPS_FLANGE_R, "the SFH 4550 and TPS601A flanges overlap"
    edge = _edge()
    for name, v, r in (("SFH 4550", led_v, SFH_FLANGE_R), ("TPS601A", pt_v, TPS_FLANGE_R)):
        gap = min(math.dist(p, (S["sensor"]["u"], v)) for p in edge) - r
        assert gap >= FLANGE_INSIDE[name] - 1e-3, f"the {name} flange comes {gap:.3f} mm from the board's edge"


def _edge():
    """The paddle's outline (spec frame) densely sampled, its straight edges included."""
    out = []
    for e in mech.wall_outline(S):
        if isinstance(e, mech.Line):
            out += [(e.a[0] + (e.b[0] - e.a[0]) * k / 200, e.a[1] + (e.b[1] - e.a[1]) * k / 200) for k in range(201)]
        else:
            out += mech.sample(e, 512)
    return out


def test_sfh_seats_flat_past_the_board():
    # The SFH 4550's wider lead section must start behind the board's back face.
    assert S["pcb"]["thickness"] + JLC_THIN_BOARD_TOL < SFH_DAMBAR


def test_board_stands_between_the_rows_on_the_insulator():
    # The board's bottom edge rests on the insulator, which sits on the main board; the board fits
    # between the rows at JLCPCB's thickness tolerance; the long pins reach through the main board.
    h = S["header"]
    assert S["outline"]["bottom"] == pytest.approx(h["insulator_height"])
    assert h["v"] == pytest.approx(S["outline"]["bottom"]) and h["u"] == pytest.approx(S["sensor"]["u"])
    gap = h["row_pitch"] - h["pin_section"]
    t = S["pcb"]["thickness"]
    assert t <= gap, "the board does not fit between the rows at its nominal thickness"
    assert (t + JLC_THIN_BOARD_TOL) - gap <= PRESS_MAX, "the thickest board forces the rows apart"
    assert (gap - (t - JLC_THIN_BOARD_TOL)) / 2 <= SOLDER_GAP_MAX, "the thinnest board leaves too wide a solder gap"
    assert h["pin_down"] - h["pin_tolerance"] > MAIN["pcb"]["thickness"] + 0.3


def test_handle_stands_on_the_insulator_and_holds_the_pads(pcb):
    # The paddle's handle (spec/wall.toml [outline]): within the main board's joint courtyard (the
    # insulator plus its margin), its straight sides and the neck above them clear of the header's
    # pads; the neck's inside arc millable and its outside arc smooth into the blade; the main
    # board's parts under the blade's overhang, outside the joint's courtyard, stay 0.5 mm below
    # its lowest edge there.
    o, h = S["outline"], S["header"]
    court = h["insulator_length"] / 2 + JOINT_COURTYARD
    assert o["handle_width"] / 2 <= court
    assert o["neck_inside_radius"] >= 0.5, "JLCPCB mills inside corners with at least a 0.5 mm radius"
    assert o["bottom"] < mech.wall_neck(S)["handle_top"] < o["neck_top"] <= o["top"] - o["corner_radius"]
    edge = _edge()
    for p in pcb.footprints["J1"].pads:
        box = _box(p)
        gap = min(_to_box(box, q) for q in edge if q[1] > o["bottom"] + 1e-6)
        assert gap >= EDGE_CLEARANCE - 1e-6, f"J1 pin {p.number} is {gap:.3f} mm from the board's edge"
    lowest = min(q[1] for q in edge if abs(q[0]) >= court)
    assert S["joint"]["under_blade"] <= lowest - 0.5 + 1e-6, f"the blade comes down to {lowest:.2f} mm"


def _seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy))


def _segs_dist(a, b, c, d):
    """Distance between segments ab and cd (0 if they cross)."""

    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if o1 * o2 < 0 and o3 * o4 < 0:
        return 0.0
    return min(_seg_dist(c, a, b), _seg_dist(d, a, b), _seg_dist(a, c, d), _seg_dist(b, c, d))


def _copper(pcb, nets, layer):
    """Copper of the nets on a layer as segments with a half width: tracks, vias and pads (a round
    pad by its circle; a rectangle by a segment along its long side whose radius takes its corners
    in, conservative)."""
    out = [((t.start, t.end), t.width / 2, t.net) for t in pcb.tracks if t.net in nets and t.layer == layer]
    out += [((v.xy, v.xy), v.size / 2, v.net) for v in pcb.vias if v.net in nets]
    for f in pcb.footprints.values():
        for p in f.pads:
            if p.net not in nets or not ("*.Cu" in p.layers or layer in p.layers):
                continue
            if p.kind != "smd":
                out.append(((p.xy, p.xy), max(p.size) / 2, p.net))
                continue
            w, h = p.size if round(f.rotation) % 180 == 0 else p.size[::-1]
            r, half = min(w, h) / math.sqrt(2), max(abs(w - h), 0.0) / 2
            dx, dy = (half, 0.0) if w > h else (0.0, half)
            out.append((((p.xy[0] - dx, p.xy[1] - dy), (p.xy[0] + dx, p.xy[1] + dy)), r, p.net))
    return out


@needs_kicad
def test_receiver_output_keeps_away_from_the_switching(pcb):
    # The receiver's output (its tracks and pads) keeps ANALOG_GAP of copper-free gap from every
    # switched net on its own layer, and no switched track runs over or under it on the other.
    tracks = {t.layer for t in pcb.tracks if t.net == RECEIVER}
    assert tracks, f"{RECEIVER} has no track"
    problems = []
    for layer in ("F.Cu", "B.Cu"):
        rx, sw = _copper(pcb, {RECEIVER}, layer), _copper(pcb, SWITCHING, layer)
        for (a, b), ra, _ in rx:
            for (c, d), rb, net in sw:
                gap = _segs_dist(a, b, c, d) - ra - rb
                if gap < ANALOG_GAP - 1e-6:
                    problems.append(f"{layer}: {net} {gap:.2f} mm from {RECEIVER} at {_uv(a)}")
    other = {"F.Cu": "B.Cu", "B.Cu": "F.Cu"}
    for t in [t for t in pcb.tracks if t.net == RECEIVER]:
        for s in pcb.tracks:
            if s.net in SWITCHING and s.layer == other[t.layer]:
                gap = _segs_dist(t.start, t.end, s.start, s.end) - t.width / 2 - s.width / 2
                if gap < ANALOG_GAP - 1e-6:
                    problems.append(f"{s.net} on {s.layer} {gap:.2f} mm from {RECEIVER} on {t.layer} in plan")
    assert not problems, "\n".join(problems)
