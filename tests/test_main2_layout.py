"""The second main board's layout against the robot: size, sides, and the chassis over the board.

spec/main2.toml holds the owner's brief and the zones the chassis takes: the drive blocks, motors
and encoder boards (MicrasHardware's model). The parts' heights come from their 3D models.
"""

import functools
import math
import shutil

import pytest
from micras_pcb import layout, mech, nets, spec
from micras_pcb.paths import board_pcb, has_layout

from .conftest import needs_kicad

pytestmark = pytest.mark.skipif(not has_layout("main2"), reason="main2 has no layout yet")

S = spec.load("main2") if has_layout("main2") else {}


def _robot_box(box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """A KiCad box (x0, y0, x1, y1) in the robot frame: (x_min, x_max, y_min, y_max)."""
    (ax, ay), (bx, by) = (mech.kicad_to_robot(S, p) for p in ((box[0], box[1]), (box[2], box[3])))
    return min(ax, bx), max(ax, bx), min(ay, by), max(ay, by)


def _spec_placed() -> set[str]:
    """The footprints the spec places (screw holes, slots, switch, ESP32 module, wall sensors)."""
    from micras_pcb import sexpr

    paths = set(mech.placements(S)) | set(mech.slots(S))
    root = sexpr.parse(board_pcb("main2").read_text())
    return {fp.prop("Reference") for fp in root.children("footprint") if fp.prop("Path") in paths}


def test_the_board_keeps_to_the_owner_maximum():
    # owner, 2026-10-17: at most 100 x 50 mm
    o = S["outline"]
    assert o["front"] - o["rear"] <= 100.0
    assert o["width"] <= 50.0
    pcb = layout.load("main2")
    assert pcb.placed, "no Edge.Cuts outline"


def test_every_part_is_on_the_top_side():
    # the board rides 1.2 mm off the floor (MicrasHardware Board.bottom_z): no parts underneath
    pcb = layout.load("main2")
    bottom = sorted(f.ref for f in pcb.footprints.values() if f.side != "top")
    assert not bottom, f"parts on the bottom side: {bottom}"


@needs_kicad
def test_parts_keep_under_the_chassis():
    """Each part's courtyard over a chassis zone stays at or below the zone's height; elsewhere at
    or below the open height (but for the parts the spec places: the wall sensors stand in the
    nose, where the chassis leaves room for them)."""
    pcb = layout.load("main2")
    heights = layout.part_heights(board_pcb("main2"), S["pcb"]["thickness"])
    exempt = _spec_placed()
    problems = []
    for f in pcb.footprints.values():
        box = f.courtyard_box()
        if box is None or f.ref in exempt:
            continue
        h = heights.get(f.ref, 0.0)
        x0, x1, y0, y1 = _robot_box(box)
        for name, (zx0, zx1, zy0, zy1, zh) in mech.keepout_zones(S):
            if min(x1, zx1) - max(x0, zx0) > 1e-6 and min(y1, zy1) - max(y0, zy0) > 1e-6 and h > zh + 1e-6:
                problems.append(f"{f.ref} ({h:.2f} mm) in {name} (parts up to {zh} mm)")
        if h > S["chassis"]["open_height"] + 1e-6:
            problems.append(f"{f.ref} ({h:.2f} mm) above the open height {S['chassis']['open_height']} mm")
    assert not problems, "\n".join(problems)


def test_the_chassis_zones_are_inside_the_board():
    o = S["outline"]
    for name, (x0, x1, y0, y1, h) in mech.keepout_zones(S):
        assert o["rear"] <= x0 < x1 <= o["front"], name
        assert -o["width"] / 2 <= y0 < y1 <= o["width"] / 2, name
        assert h >= 0, name


# --- copper: return paths, the bridges' supply, noise ----------------------------------------------


def _zones() -> list[tuple[str, list[str], list[tuple[float, float]]]]:
    """The board's pours: (net, layers, outline points); rule areas and teardrops (part of their
    track) left out."""
    from micras_pcb import sexpr

    root = sexpr.parse(board_pcb("main2").read_text())
    out = []
    for z in root.children("zone"):
        if z.child("keepout") or (z.child("attr") and z.child("attr").child("teardrop")):
            continue
        name = z.child("net_name") or z.child("net")
        layers = (z.child("layers") or z.child("layer")).atoms()
        pts = [(float(a), float(b)) for a, b in (p.atoms() for p in z.child("polygon").child("pts").children("xy"))]
        out.append((name.atoms()[-1] if name else "", layers, pts))
    return out


def _inside(p: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
    x, y = p
    hit = False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1], strict=True):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def _samples(t, step: float = 0.1):
    n = max(1, int(math.dist(t.start, t.end) / step))
    return [
        (t.start[0] + (t.end[0] - t.start[0]) * k / n, t.start[1] + (t.end[1] - t.start[1]) * k / n)
        for k in range(n + 1)
    ]


def _gap(a, b) -> float:
    """Copper between two tracks (mm): their centre lines' distance less the half widths."""

    def point_seg(p, s0, s1):
        dx, dy = s1[0] - s0[0], s1[1] - s0[1]
        L = dx * dx + dy * dy
        u = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - s0[0]) * dx + (p[1] - s0[1]) * dy) / L))
        return math.dist(p, (s0[0] + u * dx, s0[1] + u * dy))

    def cross(p, q, r, s):
        d = lambda a, b, c: (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])  # noqa: E731
        return d(p, q, r) * d(p, q, s) < 0 and d(r, s, p) * d(r, s, q) < 0

    centre = (
        0.0
        if cross(a.start, a.end, b.start, b.end)
        else min(
            point_seg(a.start, b.start, b.end),
            point_seg(a.end, b.start, b.end),
            point_seg(b.start, a.start, a.end),
            point_seg(b.end, a.start, a.end),
        )
    )
    return centre - a.width / 2 - b.width / 2


# The STM32's supplies on In2.Cu (boards/main2/layout/route.py, planes()): its 3V3_D and VCORE pins
# alternate round all four of its sides, and nest there as islands rather than ring it as tracks
# (owner, 2026-10-18). They stay within MCU_REACH of its centre.
MCU_ISLANDS = {"3V3_D", "VCORE"}
MCU_REACH = 12.5  # mm


def test_inner_layers_are_ground_planes():
    # every track has a plane beside it for its return current: F.Cu over In1.Cu, ground
    # throughout; B.Cu over In2.Cu, ground but for the STM32's supply islands round it (the
    # dielectric between an outer and its inner layer is the thin one)
    zones = _zones()
    assert {n for n, layers, _ in zones if "In1.Cu" in layers} == {"GND"}
    in2 = {n for n, layers, _ in zones if "In2.Cu" in layers}
    assert "GND" in in2 and in2 <= {"GND"} | MCU_ISLANDS, f"In2.Cu: {in2}"
    mcu = layout.load("main2").footprints["IC1"].xy
    far = sorted(
        {
            f"{n} at {_xy(p)}"
            for n, layers, pts in zones
            if "In2.Cu" in layers and n in MCU_ISLANDS
            for p in pts
            if math.dist(p, mcu) > MCU_REACH
        }
    )
    assert not far, "\n".join(far)


# VCORE's island is as small as its job (owner, 2026-10-24; route.py vcore_outline()): it takes in
# every VCORE via (VFBSMPS, VCAP1-3, their capacitors, the SMPS output) and leaves the chip's rear
# tip, between it and the fan hole, to In2.Cu's ground and the hops.
VCORE_AREA_MAX = 120.0  # mm2 of outline (the full ring round the 3V3_D island was 161)


def test_vcore_island_is_minimal():
    pcb = layout.load("main2")
    zones = [pts for n, layers, pts in _zones() if n == "VCORE" and "In2.Cu" in layers]
    assert len(zones) == 1, f"{len(zones)} VCORE islands on In2.Cu"
    poly = zones[0]
    area = abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1], strict=True))) / 2
    assert area <= VCORE_AREA_MAX, f"VCORE island {area:.0f} mm2"
    vias = [v for v in pcb.vias if v.net == "VCORE"]
    assert vias and all(_inside(v.xy, poly) for v in vias), "a VCORE via off its island"
    mcu = pcb.footprints["IC1"].xy
    tip = (mcu[0], mcu[1] + 9.0)  # 9 mm behind the chip's centre (KiCad y grows rearward)
    assert not _inside(tip, poly), "VCORE covers the rear tip"


# 3V3_D's island is as small as its job too (owner, 2026-10-25; route.py mcu_3v3_outline()): the
# square under the chip to its pin tips, with a tab to each 3V3_D pin's via (VBAT pin 1, VDDSMPS pin
# 6, VDD pins 9, 22, 35, 51, 68: main2.zen), so the escape rows past the pin tips are In2.Cu ground.
MCU_3V3_AREA_MAX = 90.0  # mm2 of outline (the full square past the pin tips was 109)


def test_3v3d_island_is_minimal():
    pcb = layout.load("main2")
    zones = [pts for n, layers, pts in _zones() if n == "3V3_D" and "In2.Cu" in layers]
    assert len(zones) == 1, f"{len(zones)} 3V3_D islands on In2.Cu"
    poly = zones[0]
    area = abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1], strict=True))) / 2
    assert area <= MCU_3V3_AREA_MAX, f"3V3_D island {area:.0f} mm2"
    mcu = pcb.footprints["IC1"]
    tips = [v for v in pcb.vias if v.net == "3V3_D" and math.dist(v.xy, mcu.xy) < 6.2]  # at the pin tips
    assert len(tips) >= 7 and all(_inside(v.xy, poly) for v in tips), "a 3V3_D pin's via off its island"


# Signal hops on In2.Cu (owner, 2026-10-21): where F.Cu and B.Cu leave no room, a digital line of
# the STM32 or the ESP32 crosses under on In2.Cu. A hop sits 0.21 mm under B.Cu but 0.5 mm over
# In1.Cu, so it couples mostly to the B.Cu copper above it, and its slot in In2.Cu's ground breaks
# the return of every B.Cu track that crosses it (TI SPRAAR7J 2.4: no traces over voids, adjacent
# layers cross at 90 degrees). So a hop keeps IN2_UNDER (plan view) from every switching, analog
# and battery-side supply track on B.Cu, stays off every B.Cu pour but ground (the VBAT pours, the
# fan's) and out of the STM32's supply islands, and any other B.Cu track over it crosses it square;
# In1.Cu carries no track. The one relaxation (owner, 2026-10-24): a hop of a slow digital line may
# run under another slow digital line's B.Cu track for at most nets.IN2_PARALLEL_MAX along each of its
# segments (nets.SLOW_DIGITAL: both ends switch rarely and slowly, so the coupling is harmless).
IN2_UNDER = 0.25  # mm
SUPPLIES = {"GND", "3V3_D", "3V3_A", "VCORE", "VDDA", "VBAT", "VSYS", "5V_IN"}
# the battery-side supplies, which carry the bridges' and the fan's ripple, are never above a hop;
# the digital supplies (3V3_D, VCORE) are crossed square like any digital line (3V3_A and VDDA are
# analog, nets.ANALOG)
POWER = {"VBAT", "VSYS", "5V_IN", "BAT_P", "GND_BAT", "REGULATORS.LDO_IN"}


def _angle(a, b) -> float:
    """The angle (degrees, 0-90) between two tracks' directions."""
    u = math.atan2(a.end[1] - a.start[1], a.end[0] - a.start[0])
    v = math.atan2(b.end[1] - b.start[1], b.end[0] - b.start[0])
    d = abs(math.degrees(u - v)) % 180
    return min(d, 180 - d)


def _run_under(pairs) -> float:
    """mm of the hops in pairs [(hop, B.Cu track)] that lie within IN2_UNDER of their tracks"""
    run = 0.0
    for h in {id(h): h for h, _ in pairs}.values():
        tracks = [b for hh, b in pairs if hh is h]
        n = max(1, int(math.dist(h.start, h.end) / 0.02))
        for k in range(n):
            p = tuple(h.start[i] + (h.end[i] - h.start[i]) * (k + 0.5) / n for i in (0, 1))
            if any(_seg_dist(p, b.start, b.end) < IN2_UNDER + (h.width + b.width) / 2 for b in tracks):
                run += math.dist(h.start, h.end) / n
    return run


def test_in2_signal_hops_are_digital_and_keep_clear():
    pcb = layout.load("main2")
    zones = _zones()
    hops = [t for t in pcb.tracks if t.layer in ("In1.Cu", "In2.Cu")]
    assert all(t.layer == "In2.Cu" for t in hops), "a track on In1.Cu"
    digital = {p.net for ref in ("IC1", "U13") for p in pcb.footprints[ref].pads if p.net}
    digital -= SUPPLIES | nets.ANALOG | nets.SWITCHING
    assert not {t.net for t in hops} - digital, f"not digital on In2.Cu: {sorted({t.net for t in hops} - digital)}"
    noisy = {*nets.SWITCHING, *nets.ANALOG, *POWER}
    above = [t for t in pcb.tracks if t.layer == "B.Cu" and t.net != "GND" and math.dist(t.start, t.end) > 0]
    near, along = set(), {}
    for h in hops:
        for b in above:
            if b.net == h.net or _gap(h, b) >= IN2_UNDER or (b.net not in noisy and _angle(h, b) >= 89.0):
                continue
            if b.net not in noisy and {h.net, b.net} <= nets.SLOW_DIGITAL:
                along.setdefault((h.net, b.net, b.start, b.end), []).append((h, b))
                continue
            near.add(
                f"{h.net} {_gap(h, b):.2f} mm under {b.net} near {_xy(h.start)}"
                + ("" if b.net in noisy else f" (crossing at {_angle(h, b):.0f} deg)")
            )
    for (hn, bn, *_), pairs in along.items():
        run = _run_under(pairs)
        if run > nets.IN2_PARALLEL_MAX:
            near.add(f"{hn} runs {run:.1f} mm under {bn} near {_xy(pairs[0][0].start)}")
    assert not near, "\n".join(sorted(near))
    keep_off = [pts for n, layers, pts in zones if n != "GND" and "B.Cu" in layers]
    keep_off += [pts for n, layers, pts in zones if n in MCU_ISLANDS and "In2.Cu" in layers]
    inside = sorted({f"{h.net} at {_xy(p)}" for h in hops for p in _samples(h) if any(_inside(p, z) for z in keep_off)})
    assert not inside, "\n".join(inside)


# Hops are the exception where F.Cu and B.Cu have no room, not a routing layer: every millimetre of
# them is a slot in the ground under B.Cu (reports/main2-review/routing.md F6)
IN2_BUDGET = 200.0  # mm, all hops together


def test_in2_signal_hops_stay_short():
    pcb = layout.load("main2")
    total = sum(math.dist(t.start, t.end) for t in pcb.tracks if t.layer == "In2.Cu")
    assert total <= IN2_BUDGET, f"{total:.0f} mm of In2.Cu hops"


def test_no_other_track_runs_on_b_cu_over_the_vbat_pour():
    # the B.Cu VBAT pours under the bridges are their supply; a signal there would lose its
    # B.Cu-side ground and cut the pour
    pours = [pts for n, layers, pts in _zones() if n == "VBAT" and "B.Cu" in layers]
    assert pours, "no VBAT pour on B.Cu"
    pcb = layout.load("main2")
    problems = sorted(
        {
            f"{t.net} at {_xy(p)}"
            for t in pcb.tracks
            if t.layer == "B.Cu" and t.net not in {"VBAT", "GND"}
            for p in _samples(t)
            if any(_inside(p, poly) for poly in pours)
        }
    )
    assert not problems, "\n".join(problems[:40])


def _xy(p) -> str:
    x, y = mech.kicad_to_robot(S, p)
    return f"robot ({x:.2f}, {y:.2f})"


def test_switching_nodes_keep_clear_of_analog_tracks():
    # but for the escape stubs (from a pad's centre) at the parts that put a switching and an analog
    # pin side by side (nets.STUB_PARTS): the DRV8874 puts VREF and IPROPI (pins 5, 6) two pins
    # from OUT1 (pin 8, SLVSF66A pinout), the INA241 its Kelvin input IN+ beside VS; and the Kelvin
    # lines' own stubs off their shunt's sense pads (the owner's exemption, as
    # boards/main2/layout/route.py _bridge_stub())
    pcb = layout.load("main2")
    pins = [p.xy for ref in nets.STUB_PARTS for p in pcb.footprints[ref].pads]
    stub = lambda t: any(math.dist(e, q) < 0.01 for e in (t.start, t.end) for q in pins)  # noqa: E731
    sw = [t for t in pcb.tracks if t.net in nets.SWITCHING and not stub(t)]
    an = [t for t in pcb.tracks if t.net in nets.ANALOG and not stub(t)]
    problems = sorted(
        {
            f"{a.net} {a.layer} {_gap(a, s):.2f} mm from {s.net} near {_xy(a.start)}"
            for a in an
            for s in sw
            if a.layer == s.layer and _gap(a, s) < nets.ANALOG_GAP
        }
    )
    assert not problems, "\n".join(problems)


def _pad_gap(p, pad, node) -> float:
    """Distance (mm) from point p to the pad's copper: its rectangle in its own orientation, the
    corners rounded as drawn (a circle or oval all round)."""
    at = node.child("at").atoms()
    a = math.radians(float(at[2]) if len(at) > 2 else 0.0)
    dx, dy = p[0] - pad.xy[0], p[1] - pad.xy[1]
    u, v = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
    shape = node.atoms()[2]
    rr = node.child("roundrect_rratio")
    rc = float(rr.atoms()[0]) * min(pad.size) if rr and shape == "roundrect" else 0.0
    if shape in ("circle", "oval"):
        rc = min(pad.size) / 2
    hu, hv = pad.size[0] / 2 - rc, pad.size[1] / 2 - rc
    return math.hypot(max(abs(u) - hu, 0.0), max(abs(v) - hv, 0.0)) - rc


def _poly_gap(p, poly) -> float:
    """Distance (mm) from point p to a filled polygon (0 inside)."""
    if _inside(p, poly):
        return 0.0
    return min(_seg_dist(p, a, b) for a, b in zip(poly, poly[1:] + poly[:1], strict=True))


def _on(pad, layer: str) -> bool:
    return layer in pad.layers or "*.Cu" in pad.layers


# Where analog copper still runs within ANALOG_GAP of a switching node's pad or pour: the gap it may
# not shrink below (mm). Keys: (analog net, switching pad "REF.PAD" or "NET pour") for an analog track,
# (analog pad's net, switching net) for a switching track by an analog pad. Open item in the layout
# README; each is a pin pair the parts themselves put side by side, or a nose line beside the
# emitter sink, whose node moves only at a selector's edges and the DAC's steps, which settle before
# the receiver scan (firmware_changes.toml emitters: emitter_dac, emitter_slot_quiet).
SWITCHING_COPPER_EXEMPT: dict[tuple[str, str], float] = {
    # the INA241 puts IN+ (pin 8, Motor_R_Sense+) beside VS (pin 7, 3V3_A) (SBOSA30D pinout)
    ("3V3_A", "Motor_R_Sense+ pour"): 0.44,
    # the DRV8874 puts VREF and IPROPI two pins from OUT1 (SLVSF66A pinout); their resistors at the pins
    ("DRIVERS.MOTOR_L_IPROPI", "DRIVERS.MOTOR_L_OUT1"): 0.22,
    ("DRIVERS.MOTOR_R_VREF", "DRIVERS.MOTOR_R_OUT1"): 0.26,
    # the emitter sink's own loop: its op-amp's set-point and feedback beside Q9 and R83
    ("SENSORS.SINK_FB", "SENSORS.EMITTER_SINK"): 0.22,
    ("SENSORS.SINK_SET", "SENSORS.EMITTER_SINK"): 0.24,
    ("VDDA", "Q9.3"): 0.34,
    # the nose: receivers, their 3V3_A and the emitters' cathodes in the wall-sensor channels
    ("3V3_A", "SENSORS.EMITTER_SINK"): 0.29,
    ("3V3_A", "SENSORS.WALL1_LED_K"): 0.33,
    ("3V3_A", "W3.2"): 0.24,
    ("Wall_Sensor_0", "Q3.2"): 0.46,
    ("Wall_Sensor_0", "SENSORS.EMITTER_SINK"): 0.40,
    ("Wall_Sensor_1", "SENSORS.EMITTER_SINK"): 0.33,
    ("Wall_Sensor_1", "SENSORS.WALL1_LED_K"): 0.49,
    ("Wall_Sensor_2", "SENSORS.EMITTER_SINK"): 0.33,
    ("Wall_Sensor_2", "W2.2"): 0.34,
    ("Wall_Sensor_3", "SENSORS.EMITTER_SINK"): 0.18,
    # the right current's run past the buzzer's driver, its corridor beside the fan hole taken by the
    # ESP32-C5 link and the IMU's and encoders' lines (the buzzer is silent while the drive runs)
    ("Current_Sensor_Right", "R3.1"): 0.43,
}


def test_analog_keeps_clear_of_switching_pads_and_pours():
    """The rule above for the rest of the switching copper: no analog track within ANALOG_GAP of a
    switching node's pad or pour on its layer, and no switching track within ANALOG_GAP of an
    analog pad (ST AN2834 section 4.2.11; reports/main2-review/routing.md F7). The escape stubs at
    nets.STUB_PARTS and their pads stay out, as above."""
    pcb = layout.load("main2")
    pins = [p.xy for ref in nets.STUB_PARTS for p in pcb.footprints[ref].pads]
    stub = lambda t: any(math.dist(e, q) < 0.01 for e in (t.start, t.end) for q in pins)  # noqa: E731
    pads = [(ref, node, pad) for ref, node, pad in _pad_nodes() if pad.net and ref not in nets.STUB_PARTS]
    pours = [(n, layer, poly) for n in nets.SWITCHING for layer in ("F.Cu", "B.Cu") for poly in _fills(layer, n)]
    near = lambda t, c, r: _seg_dist(c, t.start, t.end) < r  # noqa: E731
    found: dict[tuple[str, str], tuple[float, str]] = {}

    def note(an: str, sw: str, gap: float, where) -> None:
        if gap < nets.ANALOG_GAP and gap < found.get((an, sw), (9.0, ""))[0]:
            found[(an, sw)] = (gap, _xy(where))

    for t in pcb.tracks:
        if stub(t) or t.net not in nets.ANALOG | nets.SWITCHING:
            continue
        other = nets.SWITCHING if t.net in nets.ANALOG else nets.ANALOG
        samples = list(_samples(t))
        for ref, node, pad in pads:
            if pad.net in other and _on(pad, t.layer) and near(t, pad.xy, max(pad.size) + 1.0):
                gap = min(_pad_gap(p, pad, node) for p in samples) - t.width / 2
                key = (t.net, f"{ref}.{pad.number}") if t.net in nets.ANALOG else (pad.net, t.net)
                note(*key, gap, t.start)
        if t.net in nets.ANALOG:
            x0, y0, x1, y1 = (
                min(t.start[0], t.end[0]),
                min(t.start[1], t.end[1]),
                max(t.start[0], t.end[0]),
                max(t.start[1], t.end[1]),
            )
            for n, layer, poly in pours:
                bx0, by0, bx1, by1 = _box(poly)
                if layer == t.layer and bx0 - 1 < x1 and x0 < bx1 + 1 and by0 - 1 < y1 and y0 < by1 + 1:
                    note(t.net, f"{n} pour", min(_poly_gap(p, poly) for p in samples) - t.width / 2, t.start)
    problems = [
        f"{an} {gap:.2f} mm from {sw} near {where}"
        for (an, sw), (gap, where) in sorted(found.items())
        if gap < SWITCHING_COPPER_EXEMPT.get((an, sw), nets.ANALOG_GAP) - 1e-3
    ]
    assert not problems, "\n".join(problems)


# The pins whose net follows a switch node (reports/main2-review/routing.md F6, circuits.md M4): the
# bridges' outputs and charge-pump flying capacitor (SLVSF66A pinout), the fan driver's outputs,
# low-side sources, bootstrap and charge pump (DS14341 pinout), the buck's switch node and
# bootstrap (L6981 pinout), and the INA241s' Kelvin inputs, at the shunt's OUT1 end.
SWITCH_FOLLOWERS = {
    "DRV8874": ("OUT1", "OUT2", "CPH", "CPL"),
    "STSPIN958": ("OUT1", "OUT2", "LSS1", "LSS2", "VBOOT", "CP1", "CP2"),
    "L6981": ("SW", "BOOT"),
    "INA241": ("IN+", "IN-"),
}


@pytest.mark.skipif(shutil.which("pcb") is None, reason="pcb not installed")
def test_switch_following_nets_are_classified():
    from .design import design

    d = design("main2")
    missing = sorted(
        {
            f"{ref}.{name}: {d.net(ref, name)}"
            for mpn, names in SWITCH_FOLLOWERS.items()
            for ref in d.refs(mpn)
            for name in names
            if d.net(ref, name).split("/")[-1] not in nets.SWITCHING
        }
    )
    assert not missing, "\n".join(missing)


# --- power paths: copper for their current (review A1, A4; routing.md F1, F3) -------------------


def ipc2221_width(amps: float, rise: float = 20.0, oz: float = 1.0) -> float:
    """External conductor width (mm) for a current at a temperature rise, IPC-2221 Fig. 6-4:
    I = 0.048 dT^0.44 A^0.725 (A in mil^2), 1 oz = 1.378 mil thick."""
    area = (amps / (0.048 * rise**0.44)) ** (1 / 0.725)
    return area / (1.378 * oz) * 0.0254


# Currents (A) the power paths carry: the 4S pack's limit through F1 (BAT_P, GND_BAT), each DCX10 L
# motor path, the fan driver's 3.86 A limit (boards/main2/Drivers.zen). A track farther than NECK
# from its net's pads is at least as wide as IPC-2221 asks at a 20 C rise and at least MIN_WIDTH;
# pours count as wide copper. A layer change holds ceil(I / VIA_AMPS) vias (a 0.3 mm via carries
# about 0.84 A at a 10 C rise on 1 oz: TI SLVA959B Table 3-1).
MOTOR_NETS = {f"DRIVERS.MOTOR_{s}_{n}" for s in "LR" for n in ("OUT1", "OUT2", "SHUNT", "TERMINAL")}
FAN_NETS = {"DRIVERS.FAN_OUT", "DRIVERS.FAN_LSS", "DRIVERS.FAN_MOTOR"}
CURRENT = {"BAT_P": 10.0, "GND_BAT": 10.0, **{n: 3.0 for n in MOTOR_NETS}, **{n: 4.0 for n in FAN_NETS}}
MIN_WIDTH = {**{n: 1.0 for n in MOTOR_NETS}, **{n: 1.4 for n in FAN_NETS}}
NECK = 1.5  # mm: a pin narrower than the path leaves by a neck this long at most
VIA_AMPS = 0.84
VIA_GROUP = 2.0  # mm between the vias of one layer change
# (part, pad, net of the vias, amps, mm from the pad's centre): the feeds where a pin or pour takes
# its current through vias. F1's VBAT side to the B.Cu pour; the fan's VS pour (DS14341 section 8:
# "numerous vias"); each DRV8874's VM island, 3-4 vias as the review asks (SLVSF66A 10.1 "thick
# metal"; the bridge's own 100 nF sits on the island too)
FEEDS = [
    ("F1", "2", "VBAT", 10.0, 4.0, None),
    ("IC6", "27", "VBAT", 4.0, 5.5, None),
    ("IC8", "11", "VBAT", 3.0, 4.5, 3),
    ("IC9", "11", "VBAT", 3.0, 4.5, 3),
]
DRAIN_REACH = 3.0  # mm from Q6's exposed pad: its ground vias


def _seg_dist(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = dx * dx + dy * dy
    u = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.dist(p, (a[0] + u * dx, a[1] + u * dy))


def _groups(points: list, reach: float) -> list[list]:
    groups: list[list] = []
    for p in points:
        near = [g for g in groups if any(math.dist(p, q) <= reach for q in g)]
        merged = [p] + [q for g in near for q in g]
        groups = [g for g in groups if g not in near] + [merged]
    return groups


def test_power_paths_carry_their_current():
    pcb = layout.load("main2")
    pads = {}
    for f in pcb.footprints.values():
        for p in f.pads:
            pads.setdefault(p.net, []).append(p)
    problems = []
    for t in pcb.tracks:
        if t.net not in CURRENT:
            continue
        need = max(ipc2221_width(CURRENT[t.net]), MIN_WIDTH.get(t.net, 0.0))
        if t.width >= need - 1e-3:
            continue
        # a neck: the whole track within NECK of one of its net's pads
        if any(
            max(math.dist(e, p.xy) for e in (t.start, t.end)) - max(p.size) / 2 <= NECK for p in pads.get(t.net, [])
        ):
            continue
        problems.append(f"{t.net} {t.layer} {t.width:.2f} mm < {need:.2f} mm near {_xy(t.start)}")
    for net, amps in CURRENT.items():
        need = math.ceil(amps / VIA_AMPS)
        for g in _groups([v.xy for v in pcb.vias if v.net == net], VIA_GROUP):
            if len(g) < need:
                problems.append(f"{net}: {len(g)} via(s) at {_xy(g[0])}, a layer change for {amps} A needs {need}")
    for ref, num, net, amps, reach, count in FEEDS:
        pad = pcb.footprints[ref].pads_named(num)[0]
        need = count or math.ceil(amps / VIA_AMPS)
        n = sum(1 for v in pcb.vias if v.net == net and math.dist(v.xy, pad.xy) <= reach)
        if n < need:
            problems.append(f"{ref}.{num}: {n} {net} vias within {reach} mm, needs {need}")
    # Q6's drain: the pack's current into the ground planes round its exposed pad
    q6 = pcb.footprints["Q6"]
    ep = max((p for p in q6.pads if p.net == "GND"), key=lambda p: p.size[0] * p.size[1])
    hx, hy = (ep.size[0] / 2, ep.size[1] / 2) if round(q6.rotation) % 180 == 0 else (ep.size[1] / 2, ep.size[0] / 2)
    near = sum(
        1
        for v in pcb.vias
        if v.net == "GND"
        and math.hypot(max(abs(v.xy[0] - ep.xy[0]) - hx, 0.0), max(abs(v.xy[1] - ep.xy[1]) - hy, 0.0)) <= DRAIN_REACH
    )
    if near < math.ceil(10.0 / VIA_AMPS):
        problems.append(
            f"Q6 drain: {near} GND vias within {DRAIN_REACH} mm of its pad, needs {math.ceil(10.0 / VIA_AMPS)}"
        )
    assert not problems, "\n".join(problems)


def test_nothing_but_the_fuse_on_the_unfused_battery_net():
    # F1 protects everything: BAT_P runs from J1 to F1 alone (not even a capacitor before the fuse)
    pcb = layout.load("main2")
    on = sorted(f"{f.ref}.{p.number}" for f in pcb.footprints.values() for p in f.pads if p.net == "BAT_P")
    assert on == ["F1.1", "J1.1"], on


def test_fan_sense_is_local():
    # DS14341 Rev 1 section 8: the sense resistor as close as possible to the pins, preferably on the
    # same layer. R31's LSS pad sits by an LSS pin, joined on F.Cu (no FAN_LSS via between them)
    pcb = layout.load("main2")
    lss = [p for p in pcb.footprints["IC6"].pads if p.net == "DRIVERS.FAN_LSS"]
    r31 = next(p for p in pcb.footprints["R31"].pads if p.net == "DRIVERS.FAN_LSS")
    pin = min(lss, key=lambda p: math.dist(p.xy, r31.xy))
    d = math.dist(pin.xy, r31.xy)
    assert d <= 2.5, f"R31's LSS pad {d:.2f} mm from IC6.{pin.number}"
    x0, x1 = sorted((pin.xy[0], r31.xy[0]))
    y0, y1 = sorted((pin.xy[1], r31.xy[1]))
    vias = [
        v
        for v in pcb.vias
        if v.net == "DRIVERS.FAN_LSS" and x0 - 0.5 <= v.xy[0] <= x1 + 0.5 and y0 - 0.5 <= v.xy[1] <= y1 + 0.5
    ]
    assert not vias, f"FAN_LSS vias between IC6.{pin.number} and R31: {[_xy(v.xy) for v in vias]}"


# The switch nodes (TI SLYT614 steps 1-2: SW copper small, without vias; ST AN5419 Table 2: the SMPS
# inductor close to VLXSMPS): F.Cu only, no via, no copper beyond the box of the net's pads grown by
# SWITCH_GROW, the tracks no longer than SWITCH_DETOUR x the distance between the farthest pads.
SWITCH_NODES = ("SMPS_LX", "REGULATORS.BUCK_SW")
SWITCH_GROW = 1.0  # mm
SWITCH_DETOUR = 1.5


def test_switch_nodes_are_compact():
    pcb = layout.load("main2")
    zones = _zones()
    problems = []
    for net in SWITCH_NODES:
        pads = [p.xy for f in pcb.footprints.values() for p in f.pads if p.net == net]
        xs, ys = [p[0] for p in pads], [p[1] for p in pads]
        box = (min(xs) - SWITCH_GROW, max(xs) + SWITCH_GROW, min(ys) - SWITCH_GROW, max(ys) + SWITCH_GROW)
        inside = lambda q, b=box: b[0] <= q[0] <= b[1] and b[2] <= q[1] <= b[3]  # noqa: E731
        tracks = [t for t in pcb.tracks if t.net == net]
        if any(v.net == net for v in pcb.vias):
            problems.append(f"{net}: a via")
        problems += [f"{net}: a track on {t.layer}" for t in tracks if t.layer != "F.Cu"]
        problems += [f"{net}: a pour on {layers}" for n, layers, _ in zones if n == net and layers != ["F.Cu"]]
        problems += [
            f"{net}: copper at {_xy(q)} outside its pads' box"
            for t in tracks
            for q in (t.start, t.end)
            if not inside(q)
        ]
        problems += [
            f"{net}: pour corner at {_xy(q)} outside its pads' box"
            for n, _, pts in zones
            if n == net
            for q in pts
            if not inside(q)
        ]
        span = max(math.dist(a, b) for a in pads for b in pads)
        length = sum(math.dist(t.start, t.end) for t in tracks)
        if length > SWITCH_DETOUR * span:
            problems.append(f"{net}: {length:.1f} mm of track for pads {span:.1f} mm apart")
    assert not problems, "\n".join(problems)


# --- stubs, detours, analog neighbours, track widths (review A6, A7, B3, C4) ------------------

# The connections the owner routes by hand (layout README, Open items): their partial routes end open
# until then, so their dangling ends are not stubs
HAND_ROUTED = {
    "Encoder_Right_ABI_B",
    "Wall_Sensor_PWM_2",
    "Button",
    "Fan_TOFF",
    "IMU_INT",
    "Encoder_Right_CSn",
    "Encoder_Left_ABI_A",
    "Motors_Enable",
    "Motors_nFault",
    "Switch_0",
    "Current_Sensor_Left",
}


@needs_kicad
def test_no_dangling_copper(tmp_path):
    # a track end or via that meets no copper of its net is an open stub, an antenna (TI SCAA082A);
    # KiCad's DRC flags them as track_dangling / via_dangling (reports/main2-review/routing.md F4)
    import json
    import re
    import subprocess

    from micras_pcb.tools import kicad_cli

    pcb = board_pcb("main2")
    for ext in (".kicad_pcb", ".kicad_pro", ".kicad_dru"):
        shutil.copy(pcb.with_suffix(ext), tmp_path / f"main2{ext}")
    report = tmp_path / "drc.json"
    cmd = [
        kicad_cli(),
        "pcb",
        "drc",
        "--refill-zones",
        "--format",
        "json",
        "-o",
        str(report),
        str(tmp_path / "main2.kicad_pcb"),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    found = sorted(
        f"{i['description']} at ({i['pos']['x']:.2f}, {i['pos']['y']:.2f})"
        for v in json.loads(report.read_text())["violations"]
        if v["type"] in ("track_dangling", "via_dangling")
        for i in v["items"]
        if re.search(r"\[(.*?)\]", i["description"]).group(1) not in HAND_ROUTED
    )
    assert not found, "\n".join(found)


def _span(points: list) -> float:
    """The length of the minimum spanning tree over the points (mm)."""
    inside, rest, total = [points[0]], list(points[1:]), 0.0
    while rest:
        d, q = min((math.dist(a, b), b) for a in inside for b in rest)
        total += d
        inside.append(q)
        rest.remove(q)
    return total


# routed length against the pads' spanning tree: a two-pad net at most DETOUR x span + DETOUR_ADD,
# an analog net at most ANALOG_DETOUR x span + ANALOG_ADD (reports/main2-review/routing.md F4)
DETOUR, DETOUR_ADD = 2.5, 10.0
ANALOG_DETOUR, ANALOG_ADD = 2.0, 3.0
# The nets that still run round, with the length they may not exceed (mm): their direct paths cross
# the STM32's escape rows or the corridor beside the fan hole, which have no free lane
# (Current_Sensor_Right's run from C102 to R78 past the rear tip is the ESP32-C5 link's and the
# IMU's and encoders' corridor, so it goes round by the DIP switch and the buzzer; the wall-sensor
# line and the emitter set-point leave the front-left face for the right side and the nose). Open
# item in the layout README.
ROUND_ABOUT = {
    "Current_Sensor_Right": 62.0,
    "Wall_Emitter_Set": 34.0,
    "Wall_Sensor_2": 46.5,
}


def test_no_detours():
    pcb = layout.load("main2")
    pads, length = {}, {}
    for f in pcb.footprints.values():
        for p in f.pads:
            if p.net:
                pads.setdefault(p.net, []).append(p.xy)
    for t in pcb.tracks:
        length[t.net] = length.get(t.net, 0.0) + math.dist(t.start, t.end)
    problems = []
    for net, ps in sorted(pads.items()):
        if net not in length or net in HAND_ROUTED:
            continue
        if net in nets.ANALOG:
            limit = ANALOG_DETOUR * _span(ps) + ANALOG_ADD
        elif len(ps) == 2:
            limit = DETOUR * _span(ps) + DETOUR_ADD
        else:
            continue
        limit = max(limit, ROUND_ABOUT.get(net, 0.0))
        if length[net] > limit:
            problems.append(f"{net}: {length[net]:.1f} mm routed, at most {limit:.1f}")
    assert not problems, "\n".join(problems)


# Analog tracks keep FAST_GAP (three track widths) from the fast digital lines on the same layer
# (reports/main2-review/routing.md F7; ST AN2834 sections 4.2.11-4.2.14), but where both leave
# neighbouring pins of the STM32 (a fine-pitch escape: each track has an end within ESCAPE_REACH of
# its pads). The pairs below still run closer, in the nose and round the STM32's escape rows, for at
# most the length given (mm of the analog track inside FAST_GAP): they may not grow, and no other pair
# may appear. Open item in the layout README; the firmware keeps the LED and SPI lines quiet during an
# emitter slot (firmware_changes.toml, emitter_slot_quiet).
FAST_GAP = 0.45  # mm
ESCAPE_REACH = 1.0  # mm
CLOSE_NEIGHBOURS = {
    ("3V3_A", "Encoder_Left_CSn"): 4.6,
    ("3V3_A", "Encoder_Right_ABI_B"): 16.4,
    ("SENSORS.CURRENT_L_AMP", "Encoder_Right_ABI_B"): 2.3,
    ("SENSORS.CURRENT_L_AMP", "SPI_SCK"): 0.9,
    ("SENSORS.SINK_FB", "Encoder_Left_CSn"): 0.1,
    ("VDDA", "Encoder_Left_ABI_A"): 1.2,
    ("VDDA", "Encoder_Left_CSn"): 1.8,
    ("Wall_Emitter_Set", "Encoder_Left_ABI_B"): 9.1,
    ("Wall_Emitter_Set", "Encoder_Right_ABI_B"): 2.2,
    ("Wall_Sensor_0", "Encoder_Left_ABI_B"): 0.1,
    ("Wall_Sensor_1", "Encoder_Left_ABI_B"): 3.9,
    ("Wall_Sensor_2", "LED_ARGB"): 0.3,
    ("Wall_Sensor_3", "LED_ARGB"): 3.2,
}


def _run_within(a, b, gap: float) -> float:
    """mm of track a whose copper lies within gap of track b's"""
    n = max(1, int(math.dist(a.start, a.end) / 0.02))
    inside = 0
    for k in range(n):
        p = tuple(a.start[i] + (a.end[i] - a.start[i]) * (k + 0.5) / n for i in (0, 1))
        inside += _seg_dist(p, b.start, b.end) < gap + (a.width + b.width) / 2
    return math.dist(a.start, a.end) * inside / n


def test_analog_keeps_clear_of_fast_digital():
    pcb = layout.load("main2")
    mcu = [p.xy for p in pcb.footprints["IC1"].pads]
    escape = lambda t: any(math.dist(e, q) < ESCAPE_REACH for e in (t.start, t.end) for q in mcu)  # noqa: E731
    an = [t for t in pcb.tracks if t.net in nets.ANALOG]
    fast = [t for t in pcb.tracks if t.net in nets.FAST_DIGITAL]
    runs, where = {}, {}
    for a in an:
        for f in fast:
            if a.layer == f.layer and _gap(a, f) < FAST_GAP and not (escape(a) and escape(f)):
                runs[(a.net, f.net)] = runs.get((a.net, f.net), 0.0) + _run_within(a, f, FAST_GAP)
                where.setdefault((a.net, f.net), f"{_gap(a, f):.2f} mm near {_xy(a.start)}")
    problems = [
        f"{a} runs {run:.1f} mm within {FAST_GAP} mm of {f} ({where[(a, f)]})"
        for (a, f), run in sorted(runs.items())
        if run > CLOSE_NEIGHBOURS.get((a, f), 0.0)
    ]
    assert not problems, "\n".join(problems)


# The capacitor of each ADC input's RC filter at the STM32's pin: it is the charge reservoir of the
# sample-and-hold, so the track between it and the pin stays short (ST AN2834 section 4.2.8).
ADC_FILTERS = {"Current_Sensor_Left": "C105", "Current_Sensor_Right": "C102"}
ADC_CAP_REACH = 3.0  # mm, pad centre to pad centre


@pytest.mark.xfail(
    strict=True,
    reason="no 0402 fits within 3 mm of IC1.14 or IC1.30 outside the escape rows (layout README, open items)",
)
def test_adc_filter_caps_at_the_pin():
    pcb = layout.load("main2")
    problems = []
    for net, ref in ADC_FILTERS.items():
        pin = next(p for p in pcb.footprints["IC1"].pads if p.net == net)
        pad = next(p for p in pcb.footprints[ref].pads if p.net == net)
        d = math.dist(pin.xy, pad.xy)
        if d > ADC_CAP_REACH:
            problems.append(f"{ref} {d:.1f} mm from IC1.{pin.number} ({net})")
    assert not problems, "\n".join(problems)


# Signal tracks are at least TRACK_FLOOR wide (margin over JLCPCB's 0.09 mm against over-etch,
# reports/main2-review/routing.md F14), but for a fine-pitch escape: a track both of whose ends lie
# within ESCAPE_TRACK of a pad narrower than FINE_PAD (the STM32's 0.4 mm pitch pins)
TRACK_FLOOR = 0.12  # mm
FINE_PAD = 0.3  # mm, the pad's smaller side
ESCAPE_TRACK = 0.6  # mm from the pad's edge


def test_track_width_floor():
    pcb = layout.load("main2")
    fine = [p for f in pcb.footprints.values() for p in f.pads if 0 < min(p.size) < FINE_PAD]
    near = lambda q: any(math.dist(q, p.xy) - max(p.size) / 2 <= ESCAPE_TRACK for p in fine)  # noqa: E731
    problems = [
        f"{t.net} {t.layer} {t.width:.3f} mm near {_xy(t.start)}"
        for t in pcb.tracks
        if t.width < TRACK_FLOOR - 1e-4 and not (near(t.start) and near(t.end))
    ]
    assert not problems, "\n".join(problems)


# --- the antenna, ground stitching, pour connections, vias in pads (routing review F2, F10-F12, F15) ---


@functools.cache
def _root():
    from micras_pcb import sexpr

    return sexpr.parse(board_pcb("main2").read_text())


def _pts(node) -> list[tuple[float, float]]:
    return [(float(a), float(b)) for a, b in (p.atoms()[:2] for p in node.child("pts").children("xy"))]


def _zone_net(z) -> str:
    n = z.child("net_name") or z.child("net")
    return n.atoms()[-1] if n else ""


def _fills(layer: str, net: str | None = None) -> list[list[tuple[float, float]]]:
    """The filled polygons of the board's zones on a copper layer (one per island), of one net."""
    out = []
    for z in _root().children("zone"):
        if z.child("keepout") or (net is not None and _zone_net(z) != net):
            continue
        for f in z.children("filled_polygon"):
            if f.child("layer").atoms()[0] == layer:
                out.append(_pts(f))
    return out


def _box(poly):
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def _raster(poly, step: float) -> set[tuple[int, int]]:
    """The grid points (i * step, j * step) inside the polygon (even-odd), row by row."""
    rows: dict[int, list[float]] = {}
    for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1], strict=True):
        if ay == by:
            continue
        lo, hi = (ay, by) if ay < by else (by, ay)
        for j in range(math.ceil(lo / step), math.floor(hi / step) + 1):
            y = j * step
            if lo <= y < hi:
                rows.setdefault(j, []).append(ax + (y - ay) * (bx - ax) / (by - ay))
    cells = set()
    for j, xs in rows.items():
        xs.sort()
        for a, b in zip(xs[::2], xs[1::2], strict=False):
            cells.update((i, j) for i in range(math.ceil(a / step), math.floor(b / step) + 1))
    return cells


def _touching(polys: list, tol: float = 0.01) -> list[tuple[int, int]]:
    """Pairs of polygons a vertex of one of which lies within tol of an edge of the other."""
    cell = 0.5
    buckets: dict = {}
    for k, poly in enumerate(polys):
        for a, b in zip(poly, poly[1:] + poly[:1], strict=True):
            for i in range(math.floor(min(a[0], b[0]) / cell), math.floor(max(a[0], b[0]) / cell) + 1):
                for j in range(math.floor(min(a[1], b[1]) / cell), math.floor(max(a[1], b[1]) / cell) + 1):
                    buckets.setdefault((i, j), []).append((k, a, b))
    pairs = set()
    for k, poly in enumerate(polys):
        for p in poly:
            for m, a, b in buckets.get((math.floor(p[0] / cell), math.floor(p[1] / cell)), ()):
                if m != k and (min(k, m), max(k, m)) not in pairs:
                    dx, dy = b[0] - a[0], b[1] - a[1]
                    n = dx * dx + dy * dy
                    u = 0.0 if n == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / n))
                    if math.dist(p, (a[0] + u * dx, a[1] + u * dy)) <= tol:
                        pairs.add((min(k, m), max(k, m)))
    return sorted(pairs)


def _board_polygon() -> list[tuple[float, float]]:
    """The board's outer outline (KiCad coordinates)."""
    els = mech.outline_elements(S, _root(), to=lambda s, p: p)
    groups, left = [], list(els)
    key = lambda p: (round(p[0], 4), round(p[1], 4))  # noqa: E731
    while left:
        g = [left.pop(0)]
        ends = {key(g[0].a), key(g[0].b)}
        grown = True
        while grown:
            grown = False
            for e in list(left):
                if key(e.a) in ends or key(e.b) in ends:
                    g.append(e)
                    left.remove(e)
                    ends |= {key(e.a), key(e.b)}
                    grown = True
        groups.append(g)
    return mech.chain(max(groups, key=len))


def _antenna_area() -> list[tuple[float, float]]:
    """U13's antenna keep-out on the board: the library footprint's rule area (its own frame) where
    U13 sits."""
    from micras_pcb import sexpr
    from micras_pcb.paths import ROOT

    lib = sexpr.parse((ROOT / "components/espressif/ESP32-C5-MINI-1/ESP32-C5-MINI-1.kicad_mod").read_text())
    local = _pts(next(z for z in lib.children("zone") if z.child("keepout")).child("polygon"))
    u13 = layout.load("main2").footprints["U13"]
    return [(u13.xy[0] + dx, u13.xy[1] + dy) for dx, dy in (layout._rotate(x, y, u13.rotation) for x, y in local)]


def test_antenna_area_is_copper_free_on_every_layer():
    """ESP32-C5-MINI-1 datasheet v1.4 Figure 11-1 and the ESP32-C5 Hardware Design Guidelines
    (Positioning a Module on a Base Board): nothing under the antenna on any layer. The board is cut
    away there (spec [antenna_notch]): no board, track, via, pad or pour inside U13's antenna area,
    taken from the module's footprint and U13's place; and the rule area U13 carries on the board
    is that area (the router and the pours keep out of it)."""
    area = _antenna_area()
    fp = next(f for f in _root().children("footprint") if f.prop("Reference") == "U13")
    stored = _pts(next(z for z in fp.children("zone") if z.child("keepout")).child("polygon"))
    assert sorted((round(x, 2), round(y, 2)) for x, y in stored) == sorted(
        (round(x, 2), round(y, 2)) for x, y in area
    ), f"U13's keep-out on the board {stored} is not its antenna area {area}"
    x0, y0, x1, y1 = _box(area)
    grid = [(x0 + (x1 - x0) * i / 30, y0 + (y1 - y0) * j / 10) for i in range(1, 30) for j in range(1, 10)]
    board = _board_polygon()
    assert not [p for p in grid if _inside(p, board)], "the antenna area is on the board"
    inside = lambda p: _inside(p, area)  # noqa: E731
    pcb = layout.load("main2")
    found = [f"track {t.net} {t.layer}" for t in pcb.tracks for p in _samples(t) if inside(p)]
    found += [f"via {v.net}" for v in pcb.vias if inside(v.xy)]
    found += [f"pad {f.ref}.{p.number}" for f in pcb.footprints.values() for p in f.pads if inside(p.xy)]
    for layer in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"):
        for poly in _fills(layer):
            if any(inside(p) for p in poly) or any(_inside(p, poly) for p in grid):
                found.append(f"pour on {layer}")
    assert not found, sorted(set(found))


def _anchors() -> list[tuple[float, float]]:
    """Where the ground reaches every layer: ground vias and through-hole ground pads."""
    pcb = layout.load("main2")
    pts = [v.xy for v in pcb.vias if v.net == "GND"]
    pts += [p.xy for f in pcb.footprints.values() for p in f.pads if p.net == "GND" and p.kind == "thru_hole"]
    return pts


STITCH_REACH = 4.0  # mm: lambda/20 at 2.4 GHz is 3-4 mm (TI SZZA009 2.4.2); route.py stitches to 3.0
STITCH_STEP = 0.5  # mm between sample points
STITCH_ISLAND = 2.0  # mm2


STITCH_RING = 0.6  # mm: route.py PRUNE_RING, the pour round a ground pad or track (its join)
# route.py PRUNE_SPARE: ground pads boxed in by other nets' tracks, whose only way to ground is the
# pour round them (no via fits beside them), which pruning leaves within this reach
STITCH_SPARE = {"C72.1": 4.5, "C8.1": 4.5}


def _rings(layer: str) -> set[tuple[int, int]]:
    """The sample points within STITCH_RING of a ground pad or track on the layer, and within
    STITCH_SPARE of a spared pad."""
    pcb = layout.load("main2")
    cells, s = set(), STITCH_STEP
    for f in pcb.footprints.values():
        for p in f.pads:
            if p.net == "GND" and layer in p.layers:
                r = math.hypot(*p.size) / 2 + STITCH_RING
                cells |= {
                    (i, j)
                    for i in range(math.floor((p.xy[0] - r) / s), math.ceil((p.xy[0] + r) / s) + 1)
                    for j in range(math.floor((p.xy[1] - r) / s), math.ceil((p.xy[1] + r) / s) + 1)
                    if math.dist((i * s, j * s), p.xy) <= r
                }
    for t in pcb.tracks:
        if t.net == "GND" and t.layer == layer:
            r = t.width / 2 + STITCH_RING
            x0, x1 = sorted((t.start[0], t.end[0]))
            y0, y1 = sorted((t.start[1], t.end[1]))
            for i in range(math.floor((x0 - r) / s), math.ceil((x1 + r) / s) + 1):
                for j in range(math.floor((y0 - r) / s), math.ceil((y1 + r) / s) + 1):
                    a, b, q = t.start, t.end, (i * s, j * s)
                    dx, dy = b[0] - a[0], b[1] - a[1]
                    n = dx * dx + dy * dy
                    u = 0.0 if n == 0 else max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / n))
                    if math.dist(q, (a[0] + u * dx, a[1] + u * dy)) <= r:
                        cells.add((i, j))
    for name, r in STITCH_SPARE.items():
        ref, num = name.split(".")
        (pad,) = pcb.footprints[ref].pads_named(num)
        cells |= {
            (i, j)
            for i in range(math.floor((pad.xy[0] - r) / s), math.ceil((pad.xy[0] + r) / s) + 1)
            for j in range(math.floor((pad.xy[1] - r) / s), math.ceil((pad.xy[1] + r) / s) + 1)
            if math.dist((i * s, j * s), pad.xy) <= r
        }
    return cells


def test_ground_pours_are_stitched():
    """Routing review F10: every island of outer-layer ground pour with STITCH_ISLAND or more of pour
    of its own (past the STITCH_RING round each ground pad and track, which is that pad's or
    track's join, and past STITCH_SPARE) has at least two ground vias or through-hole ground pads, and every such point of
    it where the other outer layer is ground too lies within STITCH_REACH of one (over another net's
    copper a via would cut that net)."""
    anchors = _anchors()
    cells = {L: [(poly, _raster(poly, STITCH_STEP)) for poly in _fills(L, "GND")] for L in ("F.Cu", "B.Cu")}
    union = {L: set().union(*(c for _p, c in cells[L])) for L in cells}
    problems = []
    for L, other in (("F.Cu", "B.Cu"), ("B.Cu", "F.Cu")):
        # islands: the fill polygons, merged where same-net pours overlap
        parent = list(range(len(cells[L])))

        def find(i, parent=parent):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        owner: dict = {}
        for k, (_poly, cs) in enumerate(cells[L]):
            for c in cs:
                if c in owner:
                    parent[find(k)] = find(owner[c])
                else:
                    owner[c] = k
        # and where their edges touch (pours of one net that meet are one piece of copper)
        for a, b in _touching([poly for poly, _c in cells[L]]):
            parent[find(a)] = find(b)
        groups: dict = {}
        for k in range(len(cells[L])):
            groups.setdefault(find(k), []).append(k)
        rings = _rings(L)
        for ks in groups.values():
            area_cells = set().union(*(cells[L][k][1] for k in ks)) - rings
            area = len(area_cells) * STITCH_STEP**2
            if area < STITCH_ISLAND:
                continue
            boxes = [(cells[L][k][0], _box(cells[L][k][0])) for k in ks]
            mine = [
                a
                for a in anchors
                if any(b[0] <= a[0] <= b[2] and b[1] <= a[1] <= b[3] and _inside(a, poly) for poly, b in boxes)
            ]
            x, y = (
                sum(c[0] for c in area_cells) / len(area_cells) * STITCH_STEP,
                sum(c[1] for c in area_cells) / len(area_cells) * STITCH_STEP,
            )
            where = f"{L} island at {_xy((x, y))} ({area:.1f} mm2)"
            if len(mine) < 2:
                problems.append(f"{where}: {len(mine)} ground via(s)")
            far = [
                c
                for c in area_cells & union[other]
                if all(math.dist((c[0] * STITCH_STEP, c[1] * STITCH_STEP), a) > STITCH_REACH for a in mine)
            ]
            if far:
                c = far[0]
                problems.append(
                    f"{where}: {len(far)} points over {STITCH_REACH} mm from a ground via, e.g. {_xy((c[0] * STITCH_STEP, c[1] * STITCH_STEP))}"
                )
    assert not problems, "\n".join(problems)


# The board-wide pours (the unnamed zones: ground on every layer, VBAT on B.Cu) join pads by thermal
# reliefs (routing review F11, R14), but the pads that carry current or heat, which join solid:
# mirrors boards/main2/layout/route.py relief()
RELIEF_GAP = 0.25  # mm
SMD_SPOKE, THT_SPOKE = 0.2, 0.4  # mm
RELIEF_SOLID_AREA = 1.2  # mm2
POWER_STAGES = {"IC6", "IC7", "IC8", "IC9", "Q6"}
RELIEF_STARVED = {
    "C8.1",
    "C29.1",
    "C30.1",
    "D4.1",
    "IC1.4",
    "R2.1",
    "R12.1",
    "R30.1",
    "SWD1.2",
}
ZONE_SOLID, ZONE_THERMAL = "2", "1"  # a pad's zone_connect in the .kicad_pcb


def _pad_nodes():
    """(reference, pad node, pad from layout.load) for every pad."""
    pcb = layout.load("main2")
    for fp in _root().children("footprint"):
        ref = fp.prop("Reference")
        for node, pad in zip(fp.children("pad"), pcb.footprints[ref].pads, strict=True):
            yield ref, node, pad


def _pad_area(pad, node=None) -> float:
    """The pad's area (mm2); a custom pad's is its largest primitive polygon's, if that is larger."""
    area = pad.size[0] * pad.size[1]
    if node is not None and node.atoms()[2] == "custom" and node.child("primitives"):
        for g in node.child("primitives").children("gr_poly"):
            q = _pts(g)
            s = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(q, q[1:] + q[:1], strict=True))
            area = max(area, abs(s) / 2)
    return area


def test_pour_connections():
    problems = []
    poured = set()
    named = []  # (net, layers, outline) of the power paths' own pours
    for z in _root().children("zone"):
        if z.child("keepout") or (z.child("attr") and z.child("attr").child("teardrop")):
            continue
        net, layers = _zone_net(z), (z.child("layers") or z.child("layer")).atoms()
        name = z.child("name").atoms()[0] if z.child("name") else ""
        if name:
            named.append((net, layers, _pts(z.child("polygon"))))
            continue
        poured.add(net)
        connect, fill = z.child("connect_pads"), z.child("fill")
        spoke = SMD_SPOKE if net == "GND" and layers[0] in ("F.Cu", "B.Cu") else THT_SPOKE
        if connect.atoms()[:1] in (["yes"], ["no"], ["thru_hole_only"]):
            problems.append(f"{net} pour on {layers}: pads join it {connect.atoms()[0]}, not by thermal relief")
        gap, width = (float(fill.child(k).atoms()[0]) for k in ("thermal_gap", "thermal_bridge_width"))
        if (gap, width) != (RELIEF_GAP, spoke):
            problems.append(f"{net} pour on {layers}: relief {gap} mm gap, {width} mm spokes")
    for ref, node, pad in _pad_nodes():
        if pad.net not in poured or pad.kind not in ("smd", "thru_hole"):
            continue
        zc = node.child("zone_connect").atoms()[0] if node.child("zone_connect") else None
        name = f"{ref}.{pad.number}"
        if pad.kind == "thru_hole":
            want = ZONE_SOLID if name in RELIEF_STARVED else ZONE_THERMAL
            bridge = node.child("thermal_bridge_width")
            if want == ZONE_THERMAL and (bridge is None or float(bridge.atoms()[0]) != THT_SPOKE):
                problems.append(f"{name}: through-hole pad without {THT_SPOKE} mm spokes")
        else:
            in_named = any(
                net == pad.net and any(L in pad.layers for L in layers) and _inside(pad.xy, poly)
                for net, layers, poly in named
            )
            solid = (
                ref in POWER_STAGES or name in RELIEF_STARVED or in_named or _pad_area(pad, node) >= RELIEF_SOLID_AREA
            )
            want = ZONE_SOLID if solid else ZONE_THERMAL
        if zc != want:
            problems.append(f"{name} ({pad.net}): zone connection {zc}, want {want}")
    assert not problems, "\n".join(problems)


EXPOSED_PAD = 2.0  # mm2
THERMAL_HOLE = 0.2  # mm: TI's PowerPAD via (SLVSF66A land pattern 4223595/B)
PASTE_CLEAR = 0.05  # mm from a via's hole to a paste aperture


def _pad_hit(pad, node, c, r: float) -> bool:
    """A circle (centre c, radius r) overlaps the pad's rectangle (its own orientation, corners
    rounded as drawn)."""
    at = node.child("at").atoms()
    a = math.radians(float(at[2]) if len(at) > 2 else 0.0)
    dx, dy = c[0] - pad.xy[0], c[1] - pad.xy[1]
    u, v = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
    rr = node.child("roundrect_rratio")
    rc = float(rr.atoms()[0]) * min(pad.size) if rr and node.atoms()[2] == "roundrect" else 0.0
    hu, hv = pad.size[0] / 2 - rc, pad.size[1] / 2 - rc
    return math.hypot(max(abs(u) - hu, 0.0), max(abs(v) - hv, 0.0)) - rc < r


def _paste_boxes(fp) -> list[tuple[float, float, float, float]]:
    """The footprint's paste apertures (local x0, y0, x1, y1): its paste graphics, paste-only pads and
    copper pads with paste of their own."""
    boxes = list(fp.paste_boxes)
    for q in fp.pads:
        if set(q.layers) & {"F.Paste", "*.Paste"}:
            hx, hy = (d / 2 * (1 + q.paste_ratio) + q.paste_margin for d in q.size)
            if min(hx, hy) > 0:
                boxes.append((q.local[0] - hx, q.local[1] - hy, q.local[0] + hx, q.local[1] + hy))
    return boxes


def test_vias_in_pads():
    """Routing review F12: a via opens into an SMD pad of its net only in an exposed pad. There, with
    no via-in-pad process (spec [pcb] via_in_pad = open), it is a 0.2 mm hole left open on both sides
    (TI SLUA271C 3.4.1: smaller vias lose less solder, back-side tenting traps air) and no paste
    aperture comes within PASTE_CLEAR of its hole: the pad's paste is split into windows round it
    (SLUA271C 4.4)."""
    pcb = layout.load("main2")
    vias = [
        (v, n, float(n.child("drill").atoms()[0]) / 2) for v, n in zip(pcb.vias, _root().children("via"), strict=True)
    ]
    problems, exposed = [], 0
    for ref, node, pad in _pad_nodes():
        if pad.kind != "smd" or "F.Cu" not in pad.layers:
            continue
        fp = pcb.footprints[ref]
        for v, n, r in vias:
            if v.net != pad.net or not _pad_hit(pad, node, v.xy, r):
                continue
            where = f"{v.net} via at {_xy(v.xy)} in {ref}.{pad.number}"
            if _pad_area(pad) <= EXPOSED_PAD:
                problems.append(where)
                continue
            exposed += 1
            tent = n.child("tenting")
            if 2 * r > THERMAL_HOLE + 1e-6 or (tent and "yes" in [c.atoms()[0] for c in tent.children()]):
                problems.append(f"{where}: {2 * r:.2f} mm hole, tented {tent and [c.atoms() for c in tent.children()]}")
            dx, dy = v.xy[0] - fp.xy[0], v.xy[1] - fp.xy[1]
            u, w = layout._rotate(dx, dy, -fp.rotation)
            for x0, y0, x1, y1 in _paste_boxes(fp):
                if math.hypot(max(x0 - u, 0, u - x1), max(y0 - w, 0, w - y1)) < r + PASTE_CLEAR:
                    problems.append(f"{where}: under paste")
                    break
    assert not problems, "\n".join(problems)
    assert exposed and S["pcb"]["via_in_pad"] == "open"


# The split-paste footprints main2 uses (open thermal vias): (file, exposed pad, its solder-mask
# opening if smaller than the copper pad)
SPLIT_PASTE = {
    "ti/DRV8874/Texas_PWP0016J_HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm_Mask2.46x3.55mm.kicad_mod": ("17", (2.46, 3.55)),
    "st/STSPIN958/QFN50P500X500X100-33N-D_SplitPaste.kicad_mod": ("33", None),
    "st/STM32H725RGV6/QFN-68-1EP_8x8mm_P0.4mm_EP6.5x6.5mm_SplitPaste.kicad_mod": ("69", None),
    "huashuo/HSBB3072/PRPAK-8_L3.0-W3.0-P0.65-BL-EP_SplitPaste.kicad_mod": ("3", None),
}
PASTE_COVERAGE = (0.50, 0.70)  # TI SLUA271C section 4.4


@pytest.mark.parametrize("path", sorted(SPLIT_PASTE))
def test_split_paste_keeps_off_the_via_sites(path):
    """The exposed pad's paste is windows covering PASTE_COVERAGE of its opening, none within
    PASTE_CLEAR of a thermal-via site's hole (0.2 mm circles on Cmts.User), and every site in the pad."""
    from micras_pcb import sexpr
    from micras_pcb.paths import ROOT

    root = sexpr.parse((ROOT / "components" / path).read_text())
    number, opening = SPLIT_PASTE[path]
    ep = max(
        (p for p in root.children("pad") if p.atoms()[0] == number and "F.Cu" in p.child("layers").atoms()),
        key=lambda p: math.prod(float(v) for v in p.child("size").atoms()),
    )
    assert "F.Paste" not in ep.child("layers").atoms(), "the exposed pad keeps a paste opening of its own"
    (cx, cy), size = (float(v) for v in ep.child("at").atoms()[:2]), [float(v) for v in ep.child("size").atoms()]
    w, h = opening or size
    x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2
    windows = []
    for p in root.children("pad"):
        if p.child("layers").atoms() == ["F.Paste"]:
            (px, py), (pw, ph) = (
                (float(v) for v in p.child("at").atoms()[:2]),
                (float(v) for v in p.child("size").atoms()),
            )
            if x0 <= px <= x1 and y0 <= py <= y1:
                windows.append((px - pw / 2, py - ph / 2, px + pw / 2, py + ph / 2))
    area = sum((b[2] - b[0]) * (b[3] - b[1]) for b in windows)
    assert PASTE_COVERAGE[0] <= area / (w * h) <= PASTE_COVERAGE[1], f"{area / (w * h):.0%} paste"
    sites = []
    for c in root.children("fp_circle"):
        if c.child("layer").atoms() == ["Cmts.User"]:
            (sx, sy), (ex, ey) = ((float(v) for v in c.child(k).atoms()) for k in ("center", "end"))
            if abs(math.hypot(ex - sx, ey - sy) - THERMAL_HOLE / 2) < 1e-6:
                sites.append((sx, sy))
    assert sites
    for sx, sy in sites:
        assert abs(sx - cx) <= size[0] / 2 and abs(sy - cy) <= size[1] / 2, f"site ({sx}, {sy}) off the pad"
        for b in windows:
            d = math.hypot(max(b[0] - sx, 0, sx - b[2]), max(b[1] - sy, 0, sy - b[3]))
            assert d >= THERMAL_HOLE / 2 + PASTE_CLEAR - 1e-9, f"site ({sx}, {sy}) {d:.3f} mm from a window"


def test_bridge_pads_have_a_ground_heat_path():
    """Routing review F15 (SLVSF66A section 10.1, maximize the copper on the thermal pad): B.Cu
    under each DRV8874's exposed pad is at least half ground pour."""
    pcb = layout.load("main2")
    fills = [(p, _box(p)) for p in _fills("B.Cu", "GND")]
    for ref in ("IC8", "IC9"):
        ep = max((p for p in pcb.footprints[ref].pads if p.net == "GND"), key=_pad_area)
        w, h = ep.size if pcb.footprints[ref].rotation % 180 == 0 else ep.size[::-1]
        pts = [(ep.xy[0] + w * (i / 20 - 0.5), ep.xy[1] + h * (j / 20 - 0.5)) for i in range(21) for j in range(21)]
        hit = sum(
            1 for q in pts if any(b[0] <= q[0] <= b[2] and b[1] <= q[1] <= b[3] and _inside(q, p) for p, b in fills)
        )
        assert hit / len(pts) >= 0.5, f"{ref}: {hit / len(pts):.0%} of its exposed pad over B.Cu ground"
