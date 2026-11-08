"""The main board's layout against the robot: size, sides, and the chassis over the board.

spec/main.toml holds the owner's brief and the zones the chassis takes: the drive blocks, motors
and encoder boards (MicrasHardware's model). The parts' heights come from their 3D models.
"""

import functools
import itertools
import math
import shutil

import pytest
from micras_pcb import layout, mech, nets, spec
from micras_pcb.paths import board_pcb, has_layout

from .conftest import needs_kicad

pytestmark = pytest.mark.skipif(not has_layout("main"), reason="main has no layout yet")

S = spec.load("main") if has_layout("main") else {}


def _robot_box(box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """A KiCad box (x0, y0, x1, y1) in the robot frame: (x_min, x_max, y_min, y_max)."""
    (ax, ay), (bx, by) = (mech.kicad_to_robot(S, p) for p in ((box[0], box[1]), (box[2], box[3])))
    return min(ax, bx), max(ax, bx), min(ay, by), max(ay, by)


def _spec_placed() -> set[str]:
    """The footprints the spec places (screw holes, slots, switch, ESP32 module, wall sensors)."""
    from micras_pcb import sexpr

    paths = set(mech.placements(S)) | set(mech.slots(S))
    root = sexpr.parse(board_pcb("main").read_text())
    return {fp.prop("Reference") for fp in root.children("footprint") if fp.prop("Path") in paths}


def test_the_board_keeps_to_the_owner_maximum():
    # owner, 2026-10-17: at most 100 x 50 mm
    o = S["outline"]
    assert o["front"] - o["rear"] <= 100.0
    assert o["width"] <= 50.0
    pcb = layout.load("main")
    assert pcb.placed, "no Edge.Cuts outline"


def test_every_part_is_on_the_top_side():
    # the board rides 1.2 mm off the floor (MicrasHardware Board.bottom_z): no parts underneath
    pcb = layout.load("main")
    bottom = sorted(f.ref for f in pcb.footprints.values() if f.side != "top")
    assert not bottom, f"parts on the bottom side: {bottom}"


@needs_kicad
def test_parts_keep_under_the_chassis():
    """Each part's courtyard over a chassis zone stays at or below the zone's height; elsewhere at
    or below the open height (but for the parts the spec places: the wall sensors stand in the
    nose, where the chassis leaves room for them)."""
    pcb = layout.load("main")
    heights = _heights()
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


@functools.cache
def _heights() -> dict[str, float]:
    return layout.part_heights(board_pcb("main"), S["pcb"]["thickness"])


@needs_kicad
def test_parts_in_the_fan_ring_stay_low():
    """spec/main.toml [fan_ring]: the fan's shroud seals over a 27 mm ring round the fan hole; a part
    whose courtyard reaches into it stays at or below max_part_height (owner, 2026-11-03)."""
    pcb = layout.load("main")
    ring, c = S["fan_ring"], (S["fan_hole"]["x"], 0.0)
    r, hmax = ring["diameter"] / 2, ring["max_part_height"]
    problems = []
    for f in pcb.footprints.values():
        box = f.courtyard_box()
        if box is None:
            continue
        x0, x1, y0, y1 = _robot_box(box)
        near = (min(max(c[0], x0), x1), min(max(c[1], y0), y1))
        h = _heights().get(f.ref, 0.0)
        if math.dist(near, c) < r - 1e-6 and h > hmax + 1e-6:
            problems.append(f"{f.ref} ({h:.2f} mm) in the fan ring (parts up to {hmax} mm)")
    assert not problems, "\n".join(sorted(problems))


# owner 2026-11-03: the upright-board cap is sleeves round the lenses, no base on the main board; its
# lowest edge is the receiver's axis (spec/wall.toml [sensor] v, 7.5 mm) less the TPS601A flange's
# radius (2.9 mm) and the case's fit and wall (1.05 mm), 3.55 mm, less 0.5 mm
CASE_UNDER = 3.0  # mm
FINGER = {"SW1", "SW2", "SW3"}  # the DIP switch and the buttons: under no case and in no view, for a finger
VIEW_MARGIN = 0.5  # mm between a part and a sensor's view corridor above it


@needs_kicad
def test_parts_keep_under_the_wall_sensors_cases_and_views():
    """The wall sensors' printed cases and view corridors (tests/test_wall_joint.py: the case slid on
    from the front round the lenses, the corridor from the lens tip widening by the lens radius and
    5 deg a side): a part whose courtyard reaches under a case stays at or below CASE_UNDER, and one
    under a corridor stays VIEW_MARGIN below the corridor's lower edge there (the receiver's axis,
    spec/wall.toml [sensor] v, less the lens radius and the widening); the switches (FINGER) stay
    out of both, and a part under a wall board's blade (beside its handle, tests/test_wall_joint.py
    _strips) stays at or below spec/wall.toml joint.under_blade. The wall joints are the sensors'
    own."""
    from . import test_wall_joint as tw

    pcb = layout.load("main")
    axis = spec.load("wall")["sensor"]["v"]
    tan = math.tan(math.radians(tw.VIEW_HALF_DEG))
    sensors = tw._sensors()
    cases = {name: tw._case(face, a) for name, (face, a) in sensors.items()}
    strips = tw._strips()
    under_blade = spec.load("wall")["joint"]["under_blade"]
    problems = []
    for f in pcb.footprints.values():
        box = f.courtyard_box()
        if box is None or f.ref in sensors:
            continue
        h = _heights().get(f.ref, 0.0)
        x0, x1, y0, y1 = _robot_box(box)
        rect = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        grid = [(x0 + (x1 - x0) * i / 8, y0 + (y1 - y0) * j / 8) for i in range(9) for j in range(9)]
        for name, (face, a) in sensors.items():
            if (h > CASE_UNDER + 1e-6 or f.ref in FINGER) and not tw._apart(rect, cases[name]):
                problems.append(f"{f.ref} ({h:.2f} mm) under {name}'s case (parts up to {CASE_UNDER} mm, no switch)")
            if h > under_blade + 1e-6 and not tw._apart(rect, strips[name]):
                problems.append(f"{f.ref} ({h:.2f} mm) under {name}'s blade (parts up to {under_blade} mm)")
            d, n = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
            tip = (face[0] + tw.LED_TIP * d[0], face[1] + tw.LED_TIP * d[1])
            for p in grid:
                r = (p[0] - tip[0]) * d[0] + (p[1] - tip[1]) * d[1]
                if r < 0 or abs((p[0] - tip[0]) * n[0] + (p[1] - tip[1]) * n[1]) > tw.BODY_R + r * tan:
                    continue
                limit = axis - tw.BODY_R - r * tan - VIEW_MARGIN
                if h > limit + 1e-6 or f.ref in FINGER:
                    problems.append(
                        f"{f.ref} ({h:.2f} mm) in {name}'s view at ({p[0]:.1f}, {p[1]:.1f}) (up to {limit:.2f} mm)"
                    )
                    break
    assert not problems, "\n".join(problems)


def test_spec_silkscreen_keeps_off_every_pad():
    """The drive blocks' outlines and the fan ring (micras-pcb mech, mech.main_silk) are drawn over
    the board: no pad may sit under them (KiCad's silk_over_copper; the fab clips the silk). The
    spec keeps them off its own footprints' pads; the layout keeps every other pad off them."""
    from micras_pcb import sexpr

    pcb = layout.load("main")
    pts = []
    for e in mech.main_silk(S, sexpr.parse(board_pcb("main").read_text())):
        if isinstance(e, mech.Line):
            n = max(1, int(math.dist(e.a, e.b) / 0.05))
            pts += [(e.a[0] + (e.b[0] - e.a[0]) * k / n, e.a[1] + (e.b[1] - e.a[1]) * k / n) for k in range(n + 1)]
        else:
            pts += mech.sample(e, 400)
    pts = [mech.robot_to_kicad(S, p) for p in pts]
    problems = set()
    for f in pcb.footprints.values():
        for pad in f.pads:
            if _pad_distance(pad, pts) < mech.SILK_PAD - 1e-3:
                c = mech.kicad_to_robot(S, pad.xy)
                problems.add(f"{f.ref} pad {pad.number} at ({c[0]:.2f}, {c[1]:.2f})")
    assert not problems, "pads under the spec silkscreen:\n" + "\n".join(sorted(problems))


def _pad_distance(pad, pts) -> float:
    """The least distance from the points (KiCad frame) to the pad's rectangle (its size, turned by
    its angle; a round or rounded pad lies inside it)."""
    t = math.radians(pad.angle)
    c, s = math.cos(t), math.sin(t)
    w, h = pad.size[0] / 2, pad.size[1] / 2
    best = math.inf
    for x, y in pts:
        dx, dy = x - pad.xy[0], y - pad.xy[1]
        if abs(dx) > best + w + h or abs(dy) > best + w + h:
            continue
        u, v = dx * c - dy * s, dx * s + dy * c  # board to the pad's frame (layout._rotate inverted)
        best = min(best, math.hypot(max(abs(u) - w, 0.0), max(abs(v) - h, 0.0)))
    return best


# The LSM6DSV's body (components/st/LSM6DSV footprint: 3.0 x 2.5 mm, local x +-1.5, y +-1.25): no via
# and no F.Cu track inside it but each pad's own stub, leaving the pad outward along its long axis (ST
# TN1383 sections 3.3-3.5: routing or vias under a MEMS sensor stress it unevenly with temperature and
# shift its offsets; routing review RS-2). B.Cu may pass under it.
IMU_BODY = (1.5, 1.25)  # mm, half sizes in the footprint's frame


def test_imu_body_is_free_of_vias_and_tracks():
    pcb = layout.load("main")
    fp = pcb.footprints["IC2"]
    p0 = next(p for p in fp.pads if math.hypot(*p.local) > 0.5)
    gx, gy = p0.xy[0] - fp.xy[0], p0.xy[1] - fp.xy[1]
    phi = math.atan2(gy, gx) - math.atan2(p0.local[1], p0.local[0])

    def local(q):
        dx, dy = q[0] - fp.xy[0], q[1] - fp.xy[1]
        c, sn = math.cos(-phi), math.sin(-phi)
        return (dx * c - dy * sn, dx * sn + dy * c)

    def inside(q, grow=0.0):
        x, y = local(q)
        return abs(x) < IMU_BODY[0] + grow and abs(y) < IMU_BODY[1] + grow

    problems = []
    for v in pcb.vias:
        x, y = local(v.xy)
        dx, dy = max(abs(x) - IMU_BODY[0], 0.0), max(abs(y) - IMU_BODY[1], 0.0)
        if math.hypot(dx, dy) < v.size / 2:
            problems.append(f"{v.net} via at {_xy(v.xy)} under IC2's body")
    for t in pcb.tracks:
        if t.layer != "F.Cu":
            continue
        n = max(2, int(math.dist(t.start, t.end) / 0.02))
        pts = [tuple(t.start[i] + (t.end[i] - t.start[i]) * k / n for i in (0, 1)) for k in range(n + 1)]
        if not any(inside(q) for q in pts):
            continue
        # a pad's own outward stub: one end in the pad, the track along the pad's long axis, going out
        ok = False
        for pad in fp.pads:
            if pad.net != t.net:
                continue
            a, b = local(t.start), local(t.end)
            px, py = pad.local
            hx, hy = (pad.size[0] / 2, pad.size[1] / 2)
            if abs(round(pad.angle - fp.rotation) % 180) == 90:
                hx, hy = hy, hx
            for e, o in ((a, b), (b, a)):
                if abs(e[0] - px) <= hx + 1e-3 and abs(e[1] - py) <= hy + 1e-3:
                    along_x = hx > hy
                    straight = abs(o[1] - e[1]) < 1e-3 if along_x else abs(o[0] - e[0]) < 1e-3
                    out = abs(o[0]) > abs(e[0]) if along_x else abs(o[1]) > abs(e[1])
                    ok = ok or (straight and out)
        if not ok:
            problems.append(f"{t.net} F.Cu track {_xy(t.start)} -> {_xy(t.end)} under IC2's body")
    assert not problems, "\n".join(problems)


def test_imu_sits_at_the_rotation_centre_off_the_chassis_zones():
    """The owner (2026-11-03): the IMU IC2 stays at robot (0, 0), the axle's midpoint, where the robot
    turns in place; no chassis zone reaches its courtyard."""
    pcb = layout.load("main")
    imu = pcb.footprints["IC2"]
    assert math.dist(mech.kicad_to_robot(S, imu.xy), (0.0, 0.0)) < 1e-3
    x0, x1, y0, y1 = _robot_box(imu.courtyard_box())
    for name, (zx0, zx1, zy0, zy1, _h) in mech.keepout_zones(S):
        assert min(x1, zx1) <= max(x0, zx0) or min(y1, zy1) <= max(y0, zy0), f"IC2 under {name}"


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

    root = sexpr.parse(board_pcb("main").read_text())
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


# The STM32's supplies on In2.Cu (boards/main/layout/route.py, planes()): its 3V3_D and VCORE pins
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
    mcu = layout.load("main").footprints["IC1"].xy
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
    pcb = layout.load("main")
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
# 6, VDD pins 9, 22, 35, 51, 68: main.zen), so the escape rows past the pin tips are In2.Cu ground.
MCU_3V3_AREA_MAX = 90.0  # mm2 of outline (the full square past the pin tips was 109)


def test_3v3d_island_is_minimal():
    pcb = layout.load("main")
    zones = [pts for n, layers, pts in _zones() if n == "3V3_D" and "In2.Cu" in layers]
    assert len(zones) == 1, f"{len(zones)} 3V3_D islands on In2.Cu"
    poly = zones[0]
    area = abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1], strict=True))) / 2
    assert area <= MCU_3V3_AREA_MAX, f"3V3_D island {area:.0f} mm2"
    mcu = pcb.footprints["IC1"]
    tips = [v for v in pcb.vias if v.net == "3V3_D" and math.dist(v.xy, mcu.xy) < 6.2]  # at the pin tips
    assert len(tips) >= 7 and all(_inside(v.xy, poly) for v in tips), "a 3V3_D pin's via off its island"


# B.Cu over In2.Cu's moats (owner, 2026-11-08): In2.Cu is B.Cu's reference plane (B.Cu sits 0.21 mm
# over it, 0.5 mm of core over In1.Cu: main.zen, stackup), so a B.Cu track's return current runs in
# the In2.Cu copper under it. Where the track passes from one In2.Cu net to another (GND, the STM32's
# 3V3_D and VCORE islands) that return must leave the plane and go round by the islands' decoupling
# capacitors: a loop the size of the detour, which radiates and couples (TI SPRAAR7J section 2.4: no
# traces over voids or plane splits). A line from under the STM32 crosses at least once (3V3_D to GND)
# and twice where VCORE's band rings the chip; every analog and encoder line keeps to that but the
# battery divider (3) and Wall_Sensor_2 (2), and each crossing spans only the fill clearance's gap,
# not a moat (route.py MCU_3V3_SPANS bridges the islands' 0.8 mm gap under the left encoder's A/B
# lines). Crossings: changes of In2.Cu net along a net's chained B.Cu segments, voids (moats,
# antipads) skipped.
MOAT_CROSSINGS = {
    "Battery_Voltage": 3,
    "Current_Sensor_Left": 2,
    "Current_Sensor_Right": 2,
    "Encoder_Left_ABI_A": 2,
    "Encoder_Left_ABI_B": 2,
    "Encoder_Right_CSn": 1,
    "Wall_Sensor_1": 1,
    "Wall_Sensor_2": 2,
    "Wall_Sensor_3": 1,
}
MOAT_GAP_MAX = 0.3  # mm of void a crossing may span (the fill clearance's gap is 0.12-0.24 mm)


def test_analog_and_encoder_lines_keep_to_their_in2_plane():
    pcb = layout.load("main")
    step = 0.05
    islands = {n: [(poly, _box(poly)) for poly in _fills("In2.Cu", n)] for n in sorted(MCU_ISLANDS)}
    boxes = [b for v in islands.values() for _p, b in v]
    near = (
        min(b[0] for b in boxes) - 1.5,
        min(b[1] for b in boxes) - 1.5,
        max(b[2] for b in boxes) + 1.5,
        max(b[3] for b in boxes) + 1.5,
    )
    # In2.Cu ground near the islands, as filled intervals per row (the ground fill is one large polygon)
    edges = [
        (a, b)
        for poly in _fills("In2.Cu", "GND")
        for a, b in zip(poly, poly[1:] + poly[:1], strict=True)
        if max(a[1], b[1]) >= near[1] and min(a[1], b[1]) <= near[3]
    ]
    rows = {}
    for j in range(int((near[3] - near[1]) / step) + 1):
        y = near[1] + j * step
        rows[j] = sorted(
            a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]) for a, b in edges if (a[1] > y) != (b[1] > y)
        )

    def plane(p):
        for n, polys in islands.items():
            if any(b[0] <= p[0] <= b[2] and b[1] <= p[1] <= b[3] and _inside(p, poly) for poly, b in polys):
                return n
        if not (near[0] <= p[0] <= near[2] and near[1] <= p[1] <= near[3]):
            return "GND"  # away from the islands only ground's edges (antipads, hops) are met
        xs = rows[round((p[1] - near[1]) / step)]
        return "GND" if sum(x < p[0] for x in xs) % 2 else None

    watched = {t.net for t in pcb.tracks if t.net in nets.ANALOG or t.net.startswith("Encoder_")}
    problems = []
    for net in sorted(watched):
        segs = [(t.start, t.end) for t in pcb.tracks if t.net == net and t.layer == "B.Cu"]
        key = lambda p: (round(p[0], 3), round(p[1], 3))  # noqa: E731
        ends: dict = {}
        for i, (a, b) in enumerate(segs):
            ends.setdefault(key(a), []).append(i)
            ends.setdefault(key(b), []).append(i)
        seen, found = set(), []
        # walk each chain of segments from its ends, the plane under the track carried along it
        starts = [p for p, ix in ends.items() if len(ix) == 1] + list(ends)
        for p0 in starts:
            for i0 in ends[p0]:
                stack = [(i0, p0, None, None)]
                while stack:
                    i, frm, last, last_at = stack.pop()
                    if i in seen:
                        continue
                    seen.add(i)
                    a, b = segs[i] if key(segs[i][0]) == frm else segs[i][::-1]
                    n = max(1, int(math.dist(a, b) / step))
                    for k in range(n + 1):
                        q = (a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
                        s = plane(q)
                        if s is None:
                            continue
                        if last is not None and s != last:
                            found.append((last, s, q, math.dist(q, last_at)))
                        last, last_at = s, q
                    stack += [(j, key(b), last, last_at) for j in ends[key(b)] if j not in seen]
        limit = MOAT_CROSSINGS.get(net, 0)
        if len(found) > limit:
            problems.append(
                f"{net}: {len(found)} crossings (at most {limit}): {', '.join(f'{x}->{y} at {_xy(q)}' for x, y, q, _g in found)}"
            )
        problems += [f"{net}: {x}->{y} over a {g:.2f} mm gap at {_xy(q)}" for x, y, q, g in found if g > MOAT_GAP_MAX]
    assert not problems, "\n".join(problems)


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
    pcb = layout.load("main")
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
# them is a slot in the ground under B.Cu
IN2_BUDGET = 200.0  # mm, all hops together


def test_in2_signal_hops_stay_short():
    pcb = layout.load("main")
    total = sum(math.dist(t.start, t.end) for t in pcb.tracks if t.layer == "In2.Cu")
    assert total <= IN2_BUDGET, f"{total:.0f} mm of In2.Cu hops"


def test_no_other_track_runs_on_b_cu_over_the_vbat_pour():
    # the B.Cu VBAT pours under the bridges are their supply; a signal there would lose its
    # B.Cu-side ground and cut the pour
    pours = [pts for n, layers, pts in _zones() if n == "VBAT" and "B.Cu" in layers]
    assert pours, "no VBAT pour on B.Cu"
    pcb = layout.load("main")
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
    # boards/main/layout/route.py _bridge_stub())
    pcb = layout.load("main")
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
    # the emitter sink's op-amp supply passes between Q9's gate and drain pads (SOT-23, the transistor
    # the sink's loop drives), the only way from U12 to W1.3 that crosses neither the sink's B.Cu run
    # nor its gate and output links
    ("3V3_A", "Q9.3"): 0.22,
    # the wall joint puts 3V3_A (pin 3) 1.27 mm from the emitter sink (pin 5); 3V3_A leaves W3.3 past
    # W3.5 between VBAT's run to C96 and the DIP switch's lines up the nose (x 40.6, 41.0)
    ("3V3_A", "W3.5"): 0.23,
}


def test_analog_keeps_clear_of_switching_pads_and_pours():
    """The rule above for the rest of the switching copper: no analog track within ANALOG_GAP of a
    switching node's pad or pour on its layer, and no switching track within ANALOG_GAP of an
    analog pad (ST AN2834 section 4.2.11). The escape stubs at nets.STUB_PARTS and their pads stay
    out, as above."""
    pcb = layout.load("main")
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


# The pins whose net follows a switch node: the bridges' outputs and charge-pump flying capacitor
# (SLVSF66A pinout), the fan driver's outputs, low-side sources, bootstrap and charge pump (DS14341
# pinout), the buck's switch node and bootstrap (L6981 pinout), and the INA241s' Kelvin inputs, at
# the shunt's OUT1 end.
SWITCH_FOLLOWERS = {
    "DRV8874": ("OUT1", "OUT2", "CPH", "CPL"),
    "STSPIN958": ("OUT1", "OUT2", "LSS1", "LSS2", "VBOOT", "CP1", "CP2"),
    "L6981": ("SW", "BOOT"),
    "INA241": ("IN+", "IN-"),
}


@pytest.mark.skipif(shutil.which("pcb") is None, reason="pcb not installed")
def test_switch_following_nets_are_classified():
    from .design import design

    d = design("main")
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
# motor path, the fan driver's 3.86 A limit (boards/main/Drivers.zen). A track farther than NECK
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
# (part, pad, net of the vias, amps, mm from the pad's centre, count): the feeds where a pin or pour
# takes its current through vias. F1's VBAT side to the B.Cu pour; the fan's VS pour (DS14341 section
# 8: "numerous vias"); each DRV8874's VM island, 3 vias as the reviews ask (SLVSF66A 10.1 "thick
# metal"; routing review RP1: 3.23 A through one via before). Only vias joined to the pin by copper
# on its own layer count (tracks, pads and the zone fills of the net).
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


def _joined_vias(pcb, pad, net: str, layer: str) -> list:
    """The net's vias joined to the pad by its copper on the layer: tracks, the net's other pads there and
    its zone fills, grown from the pad."""
    segs = [t for t in pcb.tracks if t.net == net and t.layer == layer]
    pads = [p for f in pcb.footprints.values() for p in f.pads if p.net == net and layer in p.layers]
    fills = [(q, _box(q)) for q in _fills(layer, net)]
    pr = lambda p: max(p.size) / 2  # noqa: E731
    reached_pts = [pad.xy]
    done_s, done_p, done_f = set(), {id(pad)}, set()
    grow = True
    while grow:
        grow = False
        for i, t in enumerate(segs):
            if i in done_s:
                continue
            if (
                any(_seg_dist(q, t.start, t.end) <= t.width / 2 + 0.01 for q in reached_pts)
                or any(math.dist(e, p.xy) <= pr(p) for e in (t.start, t.end) for p in pads if id(p) in done_p)
                or any(_inside(e, fills[k][0]) for e in (t.start, t.end) for k in done_f)
            ):
                done_s.add(i)
                reached_pts.extend([t.start, t.end])
                grow = True
        for p in pads:
            if id(p) not in done_p and any(math.dist(q, p.xy) <= pr(p) for q in reached_pts):
                done_p.add(id(p))
                reached_pts.append(p.xy)
                grow = True
        for k, (q, bb) in enumerate(fills):
            if k not in done_f and any(
                bb[0] <= r[0] <= bb[2] and bb[1] <= r[1] <= bb[3] and _inside(r, q) for r in reached_pts
            ):
                done_f.add(k)
                reached_pts.extend(q[:: max(1, len(q) // 50)])
                grow = True
    out = []
    for v in pcb.vias:
        if v.net != net:
            continue
        r = v.size / 2
        if (
            any(_seg_dist(v.xy, segs[i].start, segs[i].end) <= segs[i].width / 2 + r for i in done_s)
            or any(math.dist(v.xy, p.xy) <= pr(p) for p in pads if id(p) in done_p)
            or any(_inside(v.xy, fills[k][0]) for k in done_f)
        ):
            out.append(v)
    return out


def test_power_paths_carry_their_current():
    pcb = layout.load("main")
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
        joined = _joined_vias(pcb, pad, net, "F.Cu" if "F.Cu" in pad.layers else pad.layers[0])
        n = sum(1 for v in joined if math.dist(v.xy, pad.xy) <= reach)
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
    pcb = layout.load("main")
    on = sorted(f"{f.ref}.{p.number}" for f in pcb.footprints.values() for p in f.pads if p.net == "BAT_P")
    assert on == ["F1.1", "J1.1"], on


def test_fan_sense_is_local():
    # DS14341 Rev 1 section 8: the sense resistor as close as possible to the pins, preferably on the
    # same layer. R31's LSS pad sits by an LSS pin, joined on F.Cu (no FAN_LSS via between them)
    pcb = layout.load("main")
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
    pcb = layout.load("main")
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

# Connections left for routing by hand (layout README, Open items), whose partial routes end open: none
HAND_ROUTED: set[str] = set()


@pytest.fixture(scope="module")
def drc_violations(tmp_path_factory) -> list[dict]:
    """KiCad's DRC of the main board (zones refilled), its violations as kicad-cli reports them."""
    import json
    import subprocess

    from micras_pcb.tools import kicad_cli

    d = tmp_path_factory.mktemp("drc")
    pcb = board_pcb("main")
    for ext in (".kicad_pcb", ".kicad_pro", ".kicad_dru"):
        shutil.copy(pcb.with_suffix(ext), d / f"main{ext}")
    report = d / "drc.json"
    cmd = [
        kicad_cli(),
        "pcb",
        "drc",
        "--refill-zones",
        "--format",
        "json",
        "-o",
        str(report),
        str(d / "main.kicad_pcb"),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return json.loads(report.read_text())["violations"]


@needs_kicad
def test_no_dangling_copper(drc_violations):
    # a track end or via that meets no copper of its net is an open stub, an antenna (TI SCAA082A);
    # KiCad's DRC flags them as track_dangling / via_dangling
    import re

    found = sorted(
        f"{i['description']} at ({i['pos']['x']:.2f}, {i['pos']['y']:.2f})"
        for v in drc_violations
        if v["type"] in ("track_dangling", "via_dangling")
        for i in v["items"]
        if re.search(r"\[(.*?)\]", i["description"]).group(1) not in HAND_ROUTED
    )
    assert not found, "\n".join(found)


TEXT_ITEMS = ("Reference field", "Footprint text", "Text")  # kicad-cli's descriptions of silkscreen texts


def _owner(description: str) -> str | None:
    """The footprint a DRC item belongs to ("Segment of SW1 on F.Silkscreen" -> "SW1")."""
    import re

    m = re.search(r" of (\S+)", description)
    return m.group(1) if m else None


@needs_kicad
def test_silkscreen_texts_clear_pads_edges_and_other_silkscreen(drc_violations):
    # boards/main/layout/silk.py places every reference clear of the solder mask openings (JLCPCB clips
    # silkscreen off exposed copper), the board edge and the other silkscreen; the footprints' own
    # legends (SW4's ON, the wall joints' marks) keep off them too. KiCad's DRC reports a text that
    # is not as silk_over_copper, silk_edge_clearance or silk_overlap; a footprint's legend over its
    # own outline is the library's drawing (SW1's ON), not a clash
    found = sorted(
        f"{v['type']}: {', '.join(i['description'] for i in v['items'])}"
        for v in drc_violations
        if v["type"] in ("silk_over_copper", "silk_edge_clearance", "silk_overlap")
        and any(i["description"].startswith(TEXT_ITEMS) for i in v["items"])
        and not (v["type"] == "silk_overlap" and len({_owner(i["description"]) for i in v["items"]}) == 1)
    )
    assert not found, "\n".join(found)


LABEL_NEAR = 1.2  # mm, boards/main/layout/silk.py NEAR: the farthest a label's box sits from its part's courtyard
LABEL_SIZE = 0.6  # mm, silk.py USER_SIZE, the largest label
LABEL_SLACK = 0.05  # mm, a text's anchor against the centre of its strokes, which silk.py places


@functools.cache
def _silk_tables() -> dict:
    """silk.py's label tables (UNNAMED, USER, SILENT), read from its source: it needs pcbnew to run."""
    import ast

    src = (board_pcb("main").parent / "silk.py").read_text()
    out = {}
    for node in ast.parse(src).body:
        name = node.targets[0] if isinstance(node, ast.Assign) else None
        if isinstance(name, ast.Name) and name.id in ("UNNAMED", "USER", "SILENT"):
            out[name.id] = ast.literal_eval(node.value)
    return out


def _hidden_field(prop) -> bool:
    effects = prop.child("effects")
    hidden = prop.child("hide") is not None and prop.child("hide").atoms()[:1] in ([], ["yes"])
    return hidden or (effects is not None and "hide" in effects.atoms())


def _labels() -> list[tuple[str, float, float]]:
    """(part, x, y) of every label on the silkscreen: the shown references and the user labels."""
    pcb, user = layout.load("main"), {v: k for k, v in _silk_tables()["USER"].items()}
    out = []
    for fp in _root().children("footprint"):
        ref = fp.prop("Reference")
        prop = next(p for p in fp.children("property") if p.atoms()[:1] == ["Reference"])
        if _hidden_field(prop) or prop.child("layer").atoms()[0] not in ("F.SilkS", "F.Silkscreen"):
            continue
        f = pcb.footprints[ref]
        dx, dy = layout._rotate(*(float(a) for a in prop.child("at").atoms()[:2]), f.rotation)
        out.append((ref, f.xy[0] + dx, f.xy[1] + dy))
    for t in _root().children("gr_text"):
        if t.atoms()[0] in user and t.child("layer").atoms()[0] in ("F.SilkS", "F.Silkscreen"):
            x, y = (float(a) for a in t.child("at").atoms()[:2])
            out.append((user[t.atoms()[0]], x, y))
    return out


def test_every_designator_is_shown_by_its_part():
    # Every part is named on the board's silkscreen, the mounting holes aside (the owner, 2026-11-07),
    # within silk.py's reach of its part: by its reference, or for the parts a user handles by what they
    # are for (silk.py USER: BAT, MOT R, RST, ...); the big ICs (UNNAMED) and the user parts that need no
    # label (SILENT: SW4's ON legend, the DIP switch's own marks, the LEDs, the buzzer) carry none (the
    # owner, 2026-11-08). silk.py hides a label it cannot fit, which this catches
    pcb, t = layout.load("main"), _silk_tables()
    bare = t["UNNAMED"] | set(t["USER"]) | t["SILENT"]
    where: dict[str, list] = {}
    for part, x, y in _labels():
        where.setdefault(part, []).append((x, y))
    problems = []
    for fp in _root().children("footprint"):
        ref = fp.prop("Reference")
        if fp.atoms()[0].split(":")[-1].startswith("MountingHole"):
            continue
        prop = next(p for p in fp.children("property") if p.atoms()[:1] == ["Reference"])
        if ref in bare and not _hidden_field(prop):
            problems.append(f"{ref}: its reference is shown, but silk.py names it otherwise or not at all")
        want = 0 if ref in t["UNNAMED"] | t["SILENT"] else 1
        if len(where.get(ref, [])) != want:
            problems.append(f"{ref}: {len(where.get(ref, []))} labels on the silkscreen, {want} expected")
            continue
        box = pcb.footprints[ref].courtyard_box()
        for x, y in where.get(ref, []) if box else []:
            gap = math.hypot(max(box[0] - x, x - box[2], 0), max(box[1] - y, y - box[3], 0))
            reach = LABEL_NEAR + 5 * LABEL_SIZE / 2 + 0.1  # the box's gap plus half the longest label
            if gap > reach:
                problems.append(f"{ref}: its label {gap:.1f} mm from its courtyard, at most {reach:.1f}")
    assert not problems, "\n".join(problems)


def _body_hulls() -> dict[str, list[tuple[float, float]]]:
    """Each part's body seen from above (the convex hull of its F.Fab drawing, its courtyard without one)."""
    pcb, out = layout.load("main"), {}
    for fp in _root().children("footprint"):
        ref = fp.prop("Reference")
        if fp.atoms()[0].split(":")[-1].startswith("MountingHole"):
            continue
        pts = []
        for head in ("fp_line", "fp_rect", "fp_poly", "fp_arc", "fp_circle"):
            for g in fp.children(head):
                if g.child("layer") is None or g.child("layer").atoms()[0] != "F.Fab":
                    continue
                q = [tuple(float(a) for a in g.child(k).atoms()[:2]) for k in ("start", "mid", "end") if g.child(k)]
                if g.child("pts"):
                    q += [tuple(float(a) for a in p.atoms()[:2]) for p in g.child("pts").children("xy")]
                if head == "fp_rect" and len(q) == 2:
                    q += [(q[0][0], q[1][1]), (q[1][0], q[0][1])]
                if head == "fp_circle" and g.child("center") and g.child("end"):
                    (cx, cy), (ex, ey) = (tuple(float(a) for a in g.child(k).atoms()[:2]) for k in ("center", "end"))
                    r = math.dist((cx, cy), (ex, ey))
                    q = [(cx + r * math.cos(a * math.pi / 8), cy + r * math.sin(a * math.pi / 8)) for a in range(16)]
                pts += q
        f = pcb.footprints[ref]
        if len(pts) < 3:
            pts = list(f.courtyard)
        pts = [(f.xy[0] + dx, f.xy[1] + dy) for dx, dy in (layout._rotate(x, y, f.rotation) for x, y in pts)]
        if len(pts) >= 3:
            out[ref] = _convex(pts)
    return out


def _convex(pts):
    pts = sorted(set(pts))

    def half(seq):
        h = []
        for p in seq:
            while (
                len(h) >= 2
                and (h[-1][0] - h[-2][0]) * (p[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0]) <= 0
            ):
                h.pop()
            h.append(p)
        return h

    return half(pts)[:-1] + half(list(reversed(pts)))[:-1]


def _to_hull(p, hull) -> float:
    """Distance from a point to a convex polygon (counter-clockwise in a y-up sense), 0 inside."""
    inside = all(
        (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0
        for a, b in zip(hull, hull[1:] + hull[:1], strict=True)
    )
    if inside:
        return 0.0
    best = math.inf
    for a, b in zip(hull, hull[1:] + hull[:1], strict=True):
        ex, ey = b[0] - a[0], b[1] - a[1]
        t = max(0.0, min(1.0, ((p[0] - a[0]) * ex + (p[1] - a[1]) * ey) / max(ex * ex + ey * ey, 1e-12)))
        best = min(best, math.hypot(p[0] - a[0] - t * ex, p[1] - a[1] - t * ey))
    return best


def test_labels_name_their_nearest_similar_part():
    # A label names the part nearest to it among the parts it could be taken for (the same kind of
    # reference, C with C, R with R, or the same footprint: the battery and motor connectors), and a
    # part's nearest such label is its own (the owner, 2026-11-08), distances from the label's centre to
    # the part's body. boards/main/layout/silk.py holds both when it places the labels
    kind = {fp.prop("Reference"): fp.atoms()[0].split(":")[-1] for fp in _root().children("footprint")}

    def similar(a, b):
        return a.rstrip("0123456789") == b.rstrip("0123456789") or kind[a] == kind[b]

    hulls, labels = _body_hulls(), _labels()
    problems = []
    for part, x, y in labels:
        own = _to_hull((x, y), hulls[part])
        for other, h in hulls.items():
            if other != part and similar(other, part):
                d = _to_hull((x, y), h)
                if d + LABEL_SLACK < own:
                    problems.append(
                        f"{part}'s label at {_xy((x, y))} is {d:.2f} mm from {other}, {own:.2f} from {part}"
                    )
    mine = {part: _to_hull((x, y), hulls[part]) for part, x, y in labels}
    for part, x, y in labels:
        for other in mine:
            if other != part and similar(other, part):
                d = _to_hull((x, y), hulls[other])
                if d + LABEL_SLACK < mine[other]:
                    problems.append(f"{other}'s nearest label is {part}'s ({d:.2f} mm), its own {mine[other]:.2f} mm")
    assert not problems, "\n".join(problems)


@needs_kicad
def test_no_via_drill_or_diameter_warnings(drc_violations):
    # rules/jlcpcb.kicad_dru warns below JLCPCB's preferred via hole (0.20 mm) and below its free
    # via class (0.45 mm copper for a 0.2-0.25 mm hole): every via stays in the cheapest process
    found = sorted(
        f"{v['type']}: {', '.join(i['description'] for i in v['items'])}"
        for v in drc_violations
        if v["type"] in ("drill_out_of_range", "via_diameter")
    )
    assert not found, f"{len(found)} via warnings:\n" + "\n".join(found[:20])


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
# an analog net at most ANALOG_DETOUR x span + ANALOG_ADD
DETOUR, DETOUR_ADD = 2.5, 10.0
ANALOG_DETOUR, ANALOG_ADD = 2.0, 3.0
# The nets that still run round, with the length they may not exceed (mm): their direct paths cross
# the STM32's escape rows or the corridor beside the fan hole, which have no free lane
# (Current_Sensor_Right's run from C102 to R78 past the rear tip is the ESP32-C5 link's and the
# IMU's and encoders' corridor, so it goes round by the DIP switch and the buzzer; the wall-sensor
# line leaves the front-left face for the right side and the nose). Open item in the layout README.
ROUND_ABOUT = {
    "Current_Sensor_Right": 62.0,
    "Wall_Sensor_2": 46.5,
}


def test_no_detours():
    pcb = layout.load("main")
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
# (ST AN2834 sections 4.2.11-4.2.14), but where both leave
# neighbouring pins of the STM32 (a fine-pitch escape: each track has an end within ESCAPE_REACH of
# its pads). CLOSE_NEIGHBOURS would list a pair allowed to run closer, for at most the length given (mm
# of the analog track inside FAST_GAP); the board needs none.
FAST_GAP = 0.45  # mm
ESCAPE_REACH = 1.0  # mm
CLOSE_NEIGHBOURS: dict[tuple[str, str], float] = {}


def _run_within(a, b, gap: float) -> float:
    """mm of track a whose copper lies within gap of track b's"""
    n = max(1, int(math.dist(a.start, a.end) / 0.02))
    inside = 0
    for k in range(n):
        p = tuple(a.start[i] + (a.end[i] - a.start[i]) * (k + 0.5) / n for i in (0, 1))
        inside += _seg_dist(p, b.start, b.end) < gap + (a.width + b.width) / 2
    return math.dist(a.start, a.end) * inside / n


def test_fan_and_buzzer_keep_clear_of_the_wall_sensors():
    """The fan's 400 kHz PWM and the buzzer's drive keep FAST_GAP from every wall receiver's line, its
    escape included: the receivers' 1 kOhm loads take no capacitor, so a fast edge beside them lands in
    a conversion (routing review RS-1; ST AN2834 section 4.2.11). Their pins are no package neighbours
    of a wall input (boards/main/main.zen, ADC lines)."""
    pcb = layout.load("main")
    receivers = {f"Wall_Sensor_{k}" for k in range(4)}
    walls = [t for t in pcb.tracks if t.net in receivers]
    problems = set()
    for f in (t for t in pcb.tracks if t.net in ("Fan_PWM", "Buzzer")):
        for w in walls:
            if f.layer == w.layer and _gap(f, w) < FAST_GAP:
                problems.add(f"{f.net} {_gap(f, w):.2f} mm from {w.net} on {f.layer} near {_xy(f.start)}")
    pins = {p.number: p.net for p in pcb.footprints["IC1"].pads}
    for p, n in pins.items():
        if n in ("Fan_PWM", "Buzzer"):
            for q in (str(int(p) - 1), str(int(p) + 1)):
                if pins.get(q) in receivers:
                    problems.add(f"IC1.{q} ({pins[q]}) beside {n} (IC1.{p})")
    assert not problems, "\n".join(sorted(problems))


def test_analog_keeps_clear_of_fast_digital():
    pcb = layout.load("main")
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
# mm, pad centre to pad centre: the reach each one has, which may not grow (owner, 2026-11-08). C105
# sits just outside pins 25-26's escape vias, 1.9 mm from IC1.25, its stub 0.75 mm from the pin's
# escape via; C102 3.5 mm from IC1.14, past the front-right face's escapes (layout README, open items)
ADC_CAP_REACH = {"Current_Sensor_Left": 2.0, "Current_Sensor_Right": 3.6}


def test_adc_filter_caps_at_the_pin():
    pcb = layout.load("main")
    problems = []
    for net, ref in ADC_FILTERS.items():
        pin = next(p for p in pcb.footprints["IC1"].pads if p.net == net)
        pad = next(p for p in pcb.footprints[ref].pads if p.net == net)
        d = math.dist(pin.xy, pad.xy)
        if d > ADC_CAP_REACH[net]:
            problems.append(f"{ref} {d:.1f} mm from IC1.{pin.number} ({net}), at most {ADC_CAP_REACH[net]}")
    assert not problems, "\n".join(problems)


# Signal tracks are at least TRACK_FLOOR wide (margin over JLCPCB's 0.09 mm against over-etch),
# but for a fine-pitch escape: a track both of whose ends lie
# within ESCAPE_TRACK of a pad narrower than FINE_PAD (the STM32's 0.4 mm pitch pins)
TRACK_FLOOR = 0.12  # mm
FINE_PAD = 0.3  # mm, the pad's smaller side
ESCAPE_TRACK = 0.6  # mm from the pad's edge


def test_track_width_floor():
    pcb = layout.load("main")
    fine = [p for f in pcb.footprints.values() for p in f.pads if 0 < min(p.size) < FINE_PAD]
    near = lambda q: any(math.dist(q, p.xy) - max(p.size) / 2 <= ESCAPE_TRACK for p in fine)  # noqa: E731
    problems = [
        f"{t.net} {t.layer} {t.width:.3f} mm near {_xy(t.start)}"
        for t in pcb.tracks
        if t.width < TRACK_FLOOR - 1e-4 and not (near(t.start) and near(t.end))
    ]
    assert not problems, "\n".join(problems)


# --- the ESP32-C5's supply: its track resistance from the buck ---------------------------------

# The module draws 426 mA peaks transmitting (5 GHz 802.11a, ESP32-C5-MINI-1 datasheet v1.4 Table
# 6-5) and asks for a supply of at least 0.6 A at 3.0-3.6 V (Table 6-2); its local capacitors
# C107/C108 sit 13 mm from pin 3, so the feed's own resistance is what the pin sees between their
# refills. 0.1 Ohm keeps the drop under 60 mV at 0.6 A (the 0.18 mm feed it replaced had 0.14 Ohm).
RADIO_FEED = ("L3", "2", "U13", "3", "3V3_D")
RADIO_FEED_MAX_OHM = 0.10
CU_RHO = 1.72e-8  # Ohm m, annealed copper at 20 C
CU_OUTER = 35e-6  # m, 1 oz outer copper (main.zen stackup); the inner layers carry 0.5 oz
CU_INNER = 17.5e-6
VIA_OHM = 0.0012  # a 0.2-0.3 mm via through the 1.0 mm board, 18 um plating (IPC-6012 class 2)


def _feed_resistance(pcb, src, dst, net) -> tuple[float, list[str]]:
    """The least series resistance over the net's tracks and vias from pad src to pad dst
    (Dijkstra; pours are left out, so it bounds the real path from above)."""
    import heapq

    def key(layer, q):
        return (layer, round(q[0], 3), round(q[1], 3))

    edges: dict = {}

    def link(a, b, r, what):
        edges.setdefault(a, []).append((b, r, what))
        edges.setdefault(b, []).append((a, r, what))

    ends = []
    for tr in pcb.tracks:
        if tr.net != net or tr.kind != "segment" or tr.width <= 0:
            continue
        cu = CU_OUTER if tr.layer in ("F.Cu", "B.Cu") else CU_INNER
        length = math.dist(tr.start, tr.end) * 1e-3
        a, b = key(tr.layer, tr.start), key(tr.layer, tr.end)
        link(a, b, CU_RHO * length / (tr.width * 1e-3 * cu), f"{tr.layer} {tr.width} mm")
        ends += [(tr.layer, tr.start, a), (tr.layer, tr.end, b)]
    layers = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
    for v in pcb.vias:
        if v.net == net:
            for la, lb in itertools.pairwise(layers):
                link(key(la, v.xy), key(lb, v.xy), VIA_OHM / 3, "via")
            for layer, q, k in ends:  # a track ending inside the via's copper
                if math.dist(q, v.xy) <= v.size / 2 and k != key(layer, v.xy):
                    link(k, key(layer, v.xy), 0.0, "via")
    for f in pcb.footprints.values():  # the path may pass through a capacitor's pad (C57, C109)
        for pad in f.pads:
            if pad.net != net:
                continue
            for layer, q, k in ends:
                if (layer in pad.layers or "*.Cu" in pad.layers) and math.dist(q, pad.xy) <= max(pad.size) / 2:
                    link(("pad", f.ref, pad.number), k, 0.0, "pad")
    start, goal = ("pad", *src), ("pad", *dst)
    best, heap = {start: 0.0}, [(0.0, start)]
    while heap:
        r, n = heapq.heappop(heap)
        if n == goal:
            return r, []
        if r > best.get(n, math.inf):
            continue
        for m, dr, _ in edges.get(n, []):
            if r + dr < best.get(m, math.inf):
                best[m] = r + dr
                heapq.heappush(heap, (r + dr, m))
    return math.inf, [f"no track path from {src} to {dst}"]


def test_radio_feed_resistance():
    pcb = layout.load("main")
    a_ref, a_pad, b_ref, b_pad, net = RADIO_FEED
    r, missing = _feed_resistance(pcb, (a_ref, a_pad), (b_ref, b_pad), net)
    assert not missing, missing
    assert r <= RADIO_FEED_MAX_OHM, (
        f"{net} from {a_ref}.{a_pad} to {b_ref}.{b_pad}: {r * 1000:.0f} mOhm of track and vias "
        f"(at most {RADIO_FEED_MAX_OHM * 1000:.0f}): widen the feed"
    )


# --- the antenna, ground stitching, pour connections, vias in pads (routing review F2, F10-F12, F15) ---


@functools.cache
def _root():
    from micras_pcb import sexpr

    return sexpr.parse(board_pcb("main").read_text())


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
    u13 = layout.load("main").footprints["U13"]
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
    pcb = layout.load("main")
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
    pcb = layout.load("main")
    pts = [v.xy for v in pcb.vias if v.net == "GND"]
    pts += [p.xy for f in pcb.footprints.values() for p in f.pads if p.net == "GND" and p.kind == "thru_hole"]
    return pts


STITCH_REACH = 4.0  # mm: lambda/20 at 2.4 GHz is 3-4 mm (TI SZZA009 2.4.2); route.py stitches to 3.0
STITCH_STEP = 0.5  # mm between sample points
STITCH_ISLAND = 2.0  # mm2


STITCH_RING = 0.6  # mm: route.py PRUNE_RING, the pour round a ground pad or track (its join)
# route.py PRUNE_SPARE: ground pads boxed in by other nets' tracks, whose only way to ground is the
# pour round them (no via fits beside them), which pruning leaves within this reach
STITCH_SPARE = {"C8.1": 4.5}


def _rings(layer: str) -> set[tuple[int, int]]:
    """The sample points within STITCH_RING of a ground pad or track on the layer, and within
    STITCH_SPARE of a spared pad."""
    pcb = layout.load("main")
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
# mirrors boards/main/layout/route.py relief()
RELIEF_GAP = 0.25  # mm
SMD_SPOKE, THT_SPOKE = 0.2, 0.4  # mm
RELIEF_SOLID_AREA = 1.2  # mm2
POWER_STAGES = {"IC6", "IC7", "IC8", "IC9", "Q6"}
RELIEF_STARVED = {"C8.1", "C29.1", "IC1.4"}
# the hand-soldered ground pins: inherited from rules/jlcpcb.kicad_dru, relieved on the inner planes and
# B.Cu, solid on F.Cu (routing review RP2); the small parts' one-spoke pads (RP3)
HAND_GROUND = {"W1.2", "W2.2", "W3.2", "W4.2", "SWD1.3", "J2.4", "J3.1"}
ONE_SPOKE = {"R2.1", "D4.1", "C30.1", "R30.1", "C58.1", "R41.1", "R44.1"}
RELIEF_RING = 0.8  # share of the ring in the relief's gap a plane may still cover (its spokes)
ZONE_SOLID, ZONE_THERMAL = "2", "1"  # a pad's zone_connect in the .kicad_pcb


def _pad_nodes():
    """(reference, pad node, pad from layout.load) for every pad."""
    pcb = layout.load("main")
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
        name = f"{ref}.{pad.number}"
        zc = node.child("zone_connect").atoms()[0] if node.child("zone_connect") else None
        if name in ONE_SPOKE:
            bridge = node.child("thermal_bridge_width")
            if zc != ZONE_THERMAL or bridge is None or float(bridge.atoms()[0]) != SMD_SPOKE:
                problems.append(f"{name}: wants a thermal relief with {SMD_SPOKE} mm spokes, found {zc}")
            continue
        if pad.net not in poured or pad.kind not in ("smd", "thru_hole"):
            continue
        if name in HAND_GROUND:
            if zc is not None:
                problems.append(f"{name}: wants the rules' connection (no pad override), found {zc}")
            continue
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
    rules = (board_pcb("main").parent / "main.kicad_dru").read_text()
    for ref in sorted({n.split(".")[0] for n in HAND_GROUND}):
        if f"A.memberOfFootprint('{ref}')" not in rules:
            problems.append(f"{ref}: no hand-soldered ground rule in main.kicad_dru")
    # the fills: each hand-soldered ground pin's ring in the relief's gap is mostly free on the inner planes
    pcb = layout.load("main")
    for name in sorted(HAND_GROUND):
        ref, num = name.split(".")
        pad = pcb.footprints[ref].pads_named(num)[0]
        r = max(pad.size) / 2 + RELIEF_GAP / 2
        ring = [
            (pad.xy[0] + r * math.cos(k * math.pi / 36), pad.xy[1] + r * math.sin(k * math.pi / 36)) for k in range(72)
        ]
        for layer in ("In1.Cu", "In2.Cu"):
            fills = [(q, _box(q)) for q in _fills(layer, "GND")]
            hit = sum(
                1
                for q in ring
                if any(b[0] <= q[0] <= b[2] and b[1] <= q[1] <= b[3] and _inside(q, f) for f, b in fills)
            )
            if not 0 < hit / len(ring) <= RELIEF_RING:
                problems.append(f"{name} on {layer}: {hit / len(ring):.0%} of its relief ring is ground (want spokes)")
    assert not problems, "\n".join(problems)


# Tombstoning (routing review RP3): a two-pad 0201-0603 part's pads heat alike in reflow when the copper
# of their own nets round them is alike: the share of a 0.3 mm ring round each pad (F.Cu) that is its
# net's copper (tracks, pads, zone fills) may differ by TOMBSTONE_SHARE at most between its two pads.
TOMBSTONE_RING = 0.3  # mm
TOMBSTONE_SHARE = 0.5
TOMBSTONE_STEP = 0.05  # mm between samples


def test_small_parts_pads_heat_alike():
    pcb = layout.load("main")
    tracks = {}
    for t in pcb.tracks:
        if t.layer == "F.Cu":
            tracks.setdefault(t.net, []).append(t)
    fills: dict[str, list] = {}
    pads = {}
    for f in pcb.footprints.values():
        for q in f.pads:
            if "F.Cu" in q.layers:
                pads.setdefault(q.net, []).append(q)

    def rect(q):
        hx, hy = q.size[0] / 2, q.size[1] / 2
        if round(q.angle) % 180 == 90:
            hx, hy = hy, hx
        return hx, hy

    def copper(net, c):
        for t in tracks.get(net, []):
            if _seg_dist(c, t.start, t.end) <= t.width / 2:
                return True
        for q in pads.get(net, []):
            hx, hy = rect(q)
            if abs(c[0] - q.xy[0]) <= hx and abs(c[1] - q.xy[1]) <= hy:
                return True
        if net not in fills:
            fills[net] = [(f, _box(f)) for f in _fills("F.Cu", net)]
        return any(b[0] <= c[0] <= b[2] and b[1] <= c[1] <= b[3] and _inside(c, f) for f, b in fills[net])

    problems = []
    for f in pcb.footprints.values():
        if f.side != "top" or not any(k in f.lib_id for k in ("0201", "0402", "0603")):
            continue
        smd = [q for q in f.pads if q.kind == "smd"]
        if len(smd) != 2 or round(f.rotation) % 90:
            continue
        share = []
        for q in smd:
            hx, hy = rect(q)
            k = int((max(hx, hy) + TOMBSTONE_RING) / TOMBSTONE_STEP) + 1
            pts = [
                (q.xy[0] + i * TOMBSTONE_STEP, q.xy[1] + j * TOMBSTONE_STEP)
                for i in range(-k, k + 1)
                for j in range(-k, k + 1)
            ]
            ring = [
                c
                for c in pts
                if not (abs(c[0] - q.xy[0]) <= hx and abs(c[1] - q.xy[1]) <= hy)
                and abs(c[0] - q.xy[0]) <= hx + TOMBSTONE_RING
                and abs(c[1] - q.xy[1]) <= hy + TOMBSTONE_RING
            ]
            share.append(sum(copper(q.net, c) for c in ring) / len(ring))
        if abs(share[0] - share[1]) > TOMBSTONE_SHARE:
            problems.append(f"{f.ref}: its pads' rings are {share[0]:.0%} and {share[1]:.0%} their nets' copper")
    assert not problems, "\n".join(problems)


EXPOSED_PAD = 2.0  # mm2
# Exposed pads under EXPOSED_PAD that still take thermal vias at their footprint's sites: the ADP7142's
# 1.0 x 1.6 mm pad (its 72.1 C/W, Rev. K Table 4, is for a JEDEC 4-layer board, pad tied to the plane)
SMALL_EXPOSED = {("U8", "7")}
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
    pcb = layout.load("main")
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
            if _pad_area(pad) <= EXPOSED_PAD and (ref, pad.number) not in SMALL_EXPOSED:
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


# JLCPCB's standard via option (PCB Capabilities, Drilling, accessed 2026-11-07): "0.2mm or 0.25mm hole
# size with via diameter less than 0.45mm, will cost more" (and any hole under 0.2 mm). Every via on
# the board therefore has 0.45 mm copper, or a 0.3 mm hole (spec/main.toml [pcb] via_drill).
STANDARD_VIA = (0.45, 0.3)  # mm: copper with a 0.2-0.25 mm hole, or the hole alone


def test_vias_take_jlcpcbs_standard_option():
    problems = [
        f"{v.net} via at {_xy(v.xy)}: {v.drill:g} mm hole in {v.size:g} mm copper"
        for v in layout.load("main").vias
        if v.drill < 0.2 - 1e-6 or (v.size < STANDARD_VIA[0] - 1e-6 and v.drill < STANDARD_VIA[1] - 1e-6)
    ]
    assert not problems, f"{len(problems)} vias take JLCPCB's paid via option:\n" + "\n".join(problems)


# The split-paste footprints the board uses (open thermal vias): (file, exposed pad, its solder-mask
# opening if smaller than the copper pad)
SPLIT_PASTE = {
    "ti/DRV8874/Texas_PWP0016J_HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm_Mask2.46x3.55mm.kicad_mod": ("17", (2.46, 3.55)),
    "st/STSPIN958/QFN50P500X500X100-33N-D_SplitPaste.kicad_mod": ("33", None),
    "st/STM32H725RGV6/QFN-68-1EP_8x8mm_P0.4mm_EP6.5x6.5mm_SplitPaste.kicad_mod": ("69", None),
    "huashuo/HSBB3072/PRPAK-8_L3.0-W3.0-P0.65-BL-EP_SplitPaste.kicad_mod": ("3", None),
    "adi/ADP7142/LFCSP-6-1EP_2x2mm_P0.65mm_EP1x1.6mm.kicad_mod": ("7", None),
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


# Exposed pads whose every thermal-via site holds a ground via: the STSPIN958's (the board's hottest part,
# 2.0 W bound and 2.7 W in a stall, boards/main/Drivers.zen; its third lane once lay under the FAN_LSS
# join) and the ADP7142's (Rev. K Table 4 72.1 C/W against Table 6 182.8 C/W on 25 mm2 of copper)
ALL_SITES = {"IC6": 9, "U8": 2}


@pytest.mark.parametrize("ref", sorted(ALL_SITES))
def test_exposed_pad_via_sites_all_hold_a_via(ref):
    pcb = layout.load("main")
    fp = pcb.footprints[ref]
    node = next(n for n in _root().children("footprint") if n.prop("Reference") == ref)
    sites = []
    for c in node.children("fp_circle"):
        if c.child("layer").atoms() == ["Cmts.User"]:
            (sx, sy), (ex, ey) = ((float(v) for v in c.child(k).atoms()) for k in ("center", "end"))
            if abs(math.hypot(ex - sx, ey - sy) - THERMAL_HOLE / 2) < 1e-6:
                dx, dy = layout._rotate(sx, sy, fp.rotation)
                sites.append((fp.xy[0] + dx, fp.xy[1] + dy))
    assert len(sites) == ALL_SITES[ref], f"{ref}: {len(sites)} via sites drawn"
    empty = [s for s in sites if not any(v.net == "GND" and math.dist(v.xy, s) < 0.05 for v in pcb.vias)]
    assert not empty, f"{ref}: no ground via at sites {[_xy(s) for s in empty]}"


# The INA241s' Kelvin lines (INA241 README, SBOSA30D 8.4.1; WSK2512 README: the sense pads as a separate pair
# to the amplifier): the loop they close, sense pad to pin along each line and pin 8 to pin 1 across the
# amplifier and back across the shunt, stays under KELVIN_LOOP (the pads sit in opposite corners of the
# WSK2512 and IN+/IN- on opposite rows of the VSSOP-8, so some loop is left). Routed apart, 4 mm or more
# between the two lines, each loop was about 25 mm2.
KELVIN = {"R": ("R65", "U10"), "L": ("R75", "U11")}
KELVIN_LOOP = 12.0  # mm2


def _route(pcb, net: str, a, b) -> list[tuple[float, float]]:
    """The points of the net's tracks from the end nearest a to the end nearest b (ends within 10 um
    join, so a via joins its layers' tracks)."""
    adj: dict = {}
    for t in pcb.tracks:
        if t.net == net:
            adj.setdefault(t.start, set()).add(t.end)
            adj.setdefault(t.end, set()).add(t.start)
    for p in adj:
        adj[p] |= {q for q in adj if q != p and math.dist(p, q) < 0.01}
    start, goal = (min(adj, key=lambda q: math.dist(q, p)) for p in (a, b))
    prev, todo = {start: None}, [start]
    while todo:
        q = todo.pop(0)
        for r in adj[q] - prev.keys():
            prev[r] = q
            todo.append(r)
    assert goal in prev, f"{net}: no track path between its pads"
    out, q = [], goal
    while q is not None:
        out.append(q)
        q = prev[q]
    return out[::-1]


@pytest.mark.parametrize("side", sorted(KELVIN))
def test_kelvin_lines_run_as_a_pair(side):
    pcb = layout.load("main")
    shunt, amp = (pcb.footprints[r] for r in KELVIN[side])
    loop = []
    for sign in ("+", "-"):
        net = f"Motor_{side}_Sense{sign}"
        s = next(p.xy for p in shunt.pads if p.net == net)
        i = next(p.xy for p in amp.pads if p.net == net)
        path = [s, *_route(pcb, net, s, i), i]
        loop += path if sign == "+" else path[::-1]
    area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(loop, loop[1:] + loop[:1], strict=True))) / 2
    assert area <= KELVIN_LOOP, f"{shunt.ref} -> {amp.ref}: the Kelvin lines close {area:.1f} mm2"


def test_bridge_pads_have_a_ground_heat_path():
    """Routing review F15 (SLVSF66A section 10.1, maximize the copper on the thermal pad): B.Cu
    under each DRV8874's exposed pad is at least half ground pour."""
    pcb = layout.load("main")
    fills = [(p, _box(p)) for p in _fills("B.Cu", "GND")]
    for ref in ("IC8", "IC9"):
        ep = max((p for p in pcb.footprints[ref].pads if p.net == "GND"), key=_pad_area)
        w, h = ep.size if pcb.footprints[ref].rotation % 180 == 0 else ep.size[::-1]
        pts = [(ep.xy[0] + w * (i / 20 - 0.5), ep.xy[1] + h * (j / 20 - 0.5)) for i in range(21) for j in range(21)]
        hit = sum(
            1 for q in pts if any(b[0] <= q[0] <= b[2] and b[1] <= q[1] <= b[3] and _inside(q, p) for p, b in fills)
        )
        assert hit / len(pts) >= 0.5, f"{ref}: {hit / len(pts):.0%} of its exposed pad over B.Cu ground"


# --- Countersinks (spec/main.toml [countersink]): the screws' 90 deg countersinks, cut by hand from
# the bottom side, keep every layer's copper out of their cone: keep-outs (tracks, vias and pours)
# of clearance_outer on B.Cu and In2.Cu and clearance_in1 on In1.Cu round each screw hole, and the
# countersink drawn on User.1, a layer the fab outputs never plot. The keep-outs reach CONE_MARGIN past
# the cone at each layer's height (routing review RP4: the countersinks are cut by hand).
CSK = S.get("countersink", {})
CSK_LAYER = "User.1"
CONE_MARGIN = 0.4  # mm
IN1_DEPTH = 0.035 + 0.2104 + 0.0175 + 0.5  # mm from the bottom face to In1.Cu's middle (main.zen stackup)


def _screw_holes() -> dict[str, tuple[float, float]]:
    return {
        v["path"].split(".")[0]: (v["x"], v["y"])
        for v in S.values()
        if isinstance(v, dict) and v.get("path", "").startswith("H")
    }


def _keepouts() -> list[tuple[list[str], set[str], list[tuple[float, float]]]]:
    """Rule areas: (layers, what they forbid, outline points in the robot frame)."""
    out = []
    for z in _root().children("zone"):
        k = z.child("keepout")
        if not k:
            continue
        banned = {c.head for c in k.children() if c.atoms() == ["not_allowed"]}
        layers = (z.child("layers") or z.child("layer")).atoms()
        out.append((layers, banned, [mech.kicad_to_robot(S, p) for p in _pts(z.child("polygon"))]))
    return out


def _covers(poly, c, r: float) -> bool:
    """The polygon holds the whole disc of radius r round c."""
    if not _inside(c, poly):
        return False
    return all(_seg_dist(c, a, b) >= r - 0.002 for a, b in zip(poly, poly[1:] + poly[:1], strict=True))


# --- milled edges: JLCPCB routes edges to +-0.2 mm (regular), so copper at the 0.2 mm minimum may be
# cut where nothing else holds it off (team review, 2026-11-08) ---------------------------------------

SLOT_KEEP = 0.3  # mm from an encoder slot's milled edge to a track or via (its joint pads excepted)
INNER_EDGE = 0.5  # mm from every routed edge to the inner planes (rules/jlcpcb.kicad_dru)


def _slot_gap(q, a, c) -> float:
    """Distance from the segment a-c to the stadium slot whose centre line is q[0]-q[1], radius q[2]."""
    (s0, s1, r) = q
    best = math.inf
    n = max(1, int(math.dist(a, c) / 0.01))
    for k in range(n + 1):
        p = (a[0] + (c[0] - a[0]) * k / n, a[1] + (c[1] - a[1]) * k / n)
        best = min(best, mech._seg_distance(p, s0, s1) - r)
    return best


def test_tracks_and_vias_keep_off_the_encoder_slots():
    pcb = layout.load("main")
    sl = S["encoder_slots"]
    half, r = sl["length"] / 2 - sl["width"] / 2, sl["width"] / 2
    slots = []
    for key in ("right_path", "left_path"):
        ref = sl[key].split(".")[-2]  # "SENSORS.EC1.SLOT" -> EC1
        assert "EncoderSlot" in pcb.footprints[ref].lib_id, f"{ref} is no encoder slot"
        # the slot's long axis runs along the robot's x, KiCad's y
        x, y = pcb.footprints[ref].xy
        slots.append(((x, y - half), (x, y + half), r))
    problems = []
    for tr in pcb.tracks:
        if tr.kind != "segment":
            continue
        for q in slots:
            if math.dist(tr.start, q[0]) > 9 and math.dist(tr.end, q[0]) > 9:
                continue
            gap = _slot_gap(q, tr.start, tr.end) - tr.width / 2
            if gap < SLOT_KEEP - 1e-3:
                problems.append(f"{tr.net} {tr.layer} track {_xy(tr.start)}-{_xy(tr.end)}: {gap:.3f} mm")
    for v in pcb.vias:
        for q in slots:
            gap = _slot_gap(q, v.xy, v.xy) - v.size / 2
            if gap < SLOT_KEEP - 1e-3:
                problems.append(f"{v.net} via {_xy(v.xy)}: {gap:.3f} mm")
    assert not problems, f"copper within {SLOT_KEEP} mm of an encoder slot:\n" + "\n".join(problems)


def test_inner_planes_keep_off_the_routed_edges():
    # the rule is what holds them (KiCad refills and checks under it); this keeps the rule
    import re

    rules = (board_pcb("main").parent / "main.kicad_dru").read_text()
    m = re.search(
        r'\(rule "pours: inner planes to board edge"\s*\(condition "([^"]*)"\)\s*\(constraint edge_clearance \(min ([0-9.]+)mm\)\)\)',
        rules,
    )
    assert m, "no inner-plane edge rule in main.kicad_dru (rules/jlcpcb.kicad_dru)"
    assert "In1.Cu" in m.group(1) and "In2.Cu" in m.group(1), m.group(1)
    assert float(m.group(2)) >= INNER_EDGE, f"inner planes {m.group(2)} mm from the edge, under {INNER_EDGE}"


def test_countersinks_keep_the_copper_off():
    keepouts = _keepouts()
    pcb = layout.load("main")
    need = {"B.Cu": CSK["clearance_outer"], "In2.Cu": CSK["clearance_outer"], "In1.Cu": CSK["clearance_in1"]}
    assert CSK["clearance_outer"] >= CSK["diameter"] / 2 + CONE_MARGIN - 1e-6, "B.Cu keep-out under the cone + margin"
    # a 90 deg cone narrows by its depth: its radius at In1.Cu
    assert CSK["clearance_in1"] >= CSK["diameter"] / 2 - IN1_DEPTH + CONE_MARGIN - 1e-6, (
        "In1.Cu keep-out under the cone + margin"
    )
    problems = []
    for h, c in _screw_holes().items():
        for layer, r in need.items():
            if not any(
                layer in layers and {"tracks", "vias", "copperpour"} <= banned and _covers(poly, c, r)
                for layers, banned, poly in keepouts
            ):
                problems.append(f"{h}: no {layer} keep-out of {r} mm (tracks, vias, pours)")
        ck = mech.robot_to_kicad(S, c)
        for t in pcb.tracks:
            if t.layer in need and _seg_dist(ck, t.start, t.end) - t.width / 2 < need[t.layer]:
                problems.append(f"{h}: {t.net} track on {t.layer} inside the countersink's clearance")
        for v in pcb.vias:
            if math.dist(ck, v.xy) - v.size / 2 < CSK["clearance_outer"]:
                problems.append(f"{h}: {v.net} via inside the countersink's clearance")
    assert not problems, "\n".join(problems)


def test_countersinks_are_drawn_but_never_fabricated():
    from micras_pcb import jlc

    circles = []
    for g in _root().children("gr_circle"):
        if g.child("layer").atoms() == [CSK_LAYER]:
            c, e = (
                mech.kicad_to_robot(S, (float(a), float(b)))
                for a, b in (g.child(k).atoms()[:2] for k in ("center", "end"))
            )
            circles.append((c, math.dist(c, e)))
    for h, c in _screw_holes().items():
        assert any(math.dist(c, q) < 1e-3 and abs(2 * r - CSK["diameter"]) < 1e-3 for q, r in circles), (
            f"{h}: no countersink on {CSK_LAYER}"
        )
    assert CSK["fabricated"] is False
    # the gerbers plot only copper, mask, paste, silk and the outline; the drill files only holes
    assert CSK_LAYER not in jlc.gerber_layers("main")
    pcb = layout.load("main")
    big = [
        f"{f.ref}.{p.number}"
        for f in pcb.footprints.values()
        for p in f.pads
        if p.kind in ("thru_hole", "np_thru_hole") and max(p.size) >= CSK["diameter"] - 1e-6 and p.net is None
    ]
    assert not big, f"pads as large as the countersink would drill it: {big}"


# --- The battery entry's through-hole pins (J1, SW4) carry the pack's 10 A and its switching
# edges: other nets' tracks and vias keep BATTERY_PIN_GAP from them (the review's 3V3_A ran 0.17 mm
# from J1.1 and SW4.2).
BATTERY_PARTS = ("J1", "SW4")
BATTERY_NETS = {"BAT_P", "GND_BAT", "VBAT", "REGULATORS.BAT_SW_DRIVE", "GND"}
BATTERY_PIN_GAP = 0.5  # mm


def test_battery_entry_pins_keep_other_nets_clear():
    pcb = layout.load("main")
    pins = [(f"{r}.{p.number}", p) for r in BATTERY_PARTS for p in pcb.footprints[r].pads if p.kind == "thru_hole"]
    problems = []
    for name, p in pins:
        own = {p.net} | BATTERY_NETS
        rad = max(p.size) / 2
        for t in pcb.tracks:
            if t.net not in own and ("*.Cu" in p.layers or t.layer in p.layers):
                g = _seg_dist(p.xy, t.start, t.end) - t.width / 2 - rad
                if g < BATTERY_PIN_GAP:
                    problems.append(f"{t.net} {t.layer} {g:.2f} mm from {name} near {_xy(t.start)}")
        for v in pcb.vias:
            if v.net not in own and (g := math.dist(p.xy, v.xy) - v.size / 2 - rad) < BATTERY_PIN_GAP:
                problems.append(f"{v.net} via {g:.2f} mm from {name} at {_xy(v.xy)}")
    assert not problems, "\n".join(problems)


# --- The battery path's pours carry the pack's 10 A (layout README, Power copper): between the
# terminals below, each pour keeps a path at least POUR_NECK wide, measured by a morphological
# opening of the pour's fill (and the net's tracks) with the terminals' pads added back. POUR_NECK
# is IPC-2221's external 1 oz width for 10 A at a 45 C rise (ipc2221_width): the necks are short
# (a few mm, the pour on both sides spreads their heat), where the long-run 20 C width (4.7 mm)
# would be too strict, but a neck to a track's width (the review found 0.5 mm on BAT_P) is not.
POUR_NECK = ipc2221_width(10.0, rise=45.0)
POUR_PATHS = [  # (net, layer, from pad, to pad)
    ("BAT_P", "F.Cu", ("J1", "1"), ("F1", "1")),
    ("GND_BAT", "F.Cu", ("J1", "2"), ("Q6", "2")),
    ("VBAT", "F.Cu", ("F1", "2"), ("D15", "1")),
]
NECK_STEP = 0.05  # mm raster


def _chamfer(win: tuple[int, int, int, int], zero) -> dict:
    """Chamfer distance (cells) over the window from the cells where zero(cell) holds."""
    i0, j0, i1, j1 = win
    d = {(i, j): 0.0 if zero((i, j)) else 1e9 for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)}
    diag = math.sqrt(2)
    fwd = ((-1, 0, 1.0), (0, -1, 1.0), (-1, -1, diag), (-1, 1, diag))
    bwd = ((1, 0, 1.0), (0, 1, 1.0), (1, 1, diag), (1, -1, diag))
    for steps, irange, jrange in (
        (fwd, range(i0, i1 + 1), range(j0, j1 + 1)),
        (bwd, range(i1, i0 - 1, -1), range(j1, j0 - 1, -1)),
    ):
        for i in irange:
            for j in jrange:
                v = d[(i, j)]
                if v == 0.0:
                    continue
                for di, dj, w in steps:
                    q = d.get((i + di, j + dj))
                    if q is not None and q + w < v:
                        v = q + w
                d[(i, j)] = v
    return d


def _neck_ok(net: str, layer: str, a, b, width: float) -> bool:
    pcb = layout.load("main")
    pa = pcb.footprints[a[0]].pads_named(a[1])[0]
    pb = pcb.footprints[b[0]].pads_named(b[1])[0]
    m = 4.0
    x0, y0 = min(pa.xy[0], pb.xy[0]) - m, min(pa.xy[1], pb.xy[1]) - m
    x1, y1 = max(pa.xy[0], pb.xy[0]) + m, max(pa.xy[1], pb.xy[1]) + m
    s = NECK_STEP
    win = (math.ceil(x0 / s), math.ceil(y0 / s), math.floor(x1 / s), math.floor(y1 / s))
    inwin = lambda c: win[0] <= c[0] <= win[2] and win[1] <= c[1] <= win[3]  # noqa: E731
    cu = set()
    for poly in _fills(layer, net):
        bx = _box(poly)
        if bx[2] < x0 or bx[0] > x1 or bx[3] < y0 or bx[1] > y1:
            continue
        cu |= {c for c in _raster(poly, s) if inwin(c)}
    for t in pcb.tracks:
        if t.net == net and t.layer == layer:
            for q in _samples(t, s):
                r = int(t.width / 2 / s)
                ci, cj = round(q[0] / s), round(q[1] / s)
                cu |= {
                    (ci + di, cj + dj)
                    for di in range(-r, r + 1)
                    for dj in range(-r, r + 1)
                    if di * di + dj * dj <= r * r
                }
    cu = {c for c in cu if inwin(c)}
    pads = set()
    ends = []
    for f in pcb.footprints.values():
        for p in f.pads:
            if p.net != net or not ("*.Cu" in p.layers or layer in p.layers):
                continue
            w, h = p.size if round(f.rotation) % 180 == 0 else p.size[::-1]
            cells = {
                (i, j)
                for i in range(math.ceil((p.xy[0] - w / 2) / s), math.floor((p.xy[0] + w / 2) / s) + 1)
                for j in range(math.ceil((p.xy[1] - h / 2) / s), math.floor((p.xy[1] + h / 2) / s) + 1)
            }
            pads |= cells
            if p is pa or p is pb:
                ends.append(cells)
    r = width / 2 / s
    inner = _chamfer(win, lambda c: c not in cu)
    core = {c for c, v in inner.items() if v > r}
    reach = _chamfer(win, lambda c: c in core)
    opened = {c for c in cu if reach[c] <= r} if core else set()
    ok = opened | pads
    start, goal = ends[0], ends[1]
    seen, todo = set(start), list(start)
    while todo:
        i, j = todo.pop()
        for q in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
            if q in ok and q not in seen:
                if q in goal:
                    return True
                seen.add(q)
                todo.append(q)
    return False


@pytest.mark.parametrize("net,layer,a,b", POUR_PATHS)
def test_battery_pours_keep_their_width(net, layer, a, b):
    assert _neck_ok(net, layer, a, b, POUR_NECK), f"{net} on {layer} necks under {POUR_NECK:.2f} mm between {a} and {b}"


# --- Analog tracks keep NOISY_GAP from the battery-side supplies on the same layer (VBAT and VSYS
# carry the bridges' and the fan's PWM ripple): a run closer than that may not exceed NOISY_RUN.
NOISY_GAP = 0.3  # mm
NOISY_RUN = 1.0  # mm


def test_analog_keeps_clear_of_noisy_supplies():
    pcb = layout.load("main")
    an = [t for t in pcb.tracks if t.net in nets.ANALOG]
    sup = [t for t in pcb.tracks if t.net in nets.NOISY_SUPPLY]
    runs = {}
    for a in an:
        for f in sup:
            if a.layer == f.layer and _gap(a, f) < NOISY_GAP:
                runs[(a.net, f.net)] = runs.get((a.net, f.net), 0.0) + _run_within(a, f, NOISY_GAP)
    problems = [
        f"{a} runs {r:.1f} mm within {NOISY_GAP} mm of {f}" for (a, f), r in sorted(runs.items()) if r > NOISY_RUN
    ]
    assert not problems, "\n".join(problems)


# The ESP32-C5's USB pair (Esp.zen, USB pads): Espressif's PCB Layout Design, USB, asks for a
# differential pair "in parallel at equal lengths", 90 Ohm, with as few vias as possible over a
# continuous ground. On this stackup the board's differential-pair rule (main.zen: 0.2248 mm at a
# 0.127 mm gap, v1's USB pair) is the 90 Ohm pair; the pair runs on F.Cu over In1.Cu's ground
# with no via. USB_SKEW_MAX: 0.25 mm of length, about 1.5 ps, under 0.1 % of a full-speed edge
# (4-20 ns, USB 2.0 Full-speed Source Electrical Characteristics); the layout has 0.05 mm.
USB_PAIR = {"ESP.USB_DN": ("J3.2", "U13.23"), "ESP.USB_DP": ("J3.3", "U13.24")}
USB_WIDTH, USB_PITCH = 0.2248, 0.2248 + 0.127
USB_SKEW_MAX = 0.25  # mm
USB_LENGTH_MAX = 12.0  # mm, each line, J3 to the module (the layout: 10.4)
USB_COUPLED_MIN = 7.0  # mm, side by side at the pair's pitch (the layout: 8.1)
USB_DRILL_MIN, USB_PAD_MIN = 0.6, 1.0  # mm: J3's holes take a 28-30 AWG wire (components/micras/UsbPads)


def _pad(pcb, ref_pad: str):
    ref, num = ref_pad.split(".")
    return next(p for p in pcb.footprints[ref].pads if p.number == num)


def test_usb_pair_is_short_matched_and_via_free():
    pcb = layout.load("main")
    problems, lengths, segs = [], {}, {}
    for net, ends in USB_PAIR.items():
        tracks = [t for t in pcb.tracks if t.net == net]
        segs[net] = tracks
        problems += [f"{net}: a via at {_xy(v.xy)}" for v in pcb.vias if v.net == net]
        problems += [f"{net}: a track on {t.layer} at {_xy(t.start)}" for t in tracks if t.layer != "F.Cu"]
        problems += [
            f"{net}: {t.width:.4f} mm wide at {_xy(t.start)}" for t in tracks if abs(t.width - USB_WIDTH) > 1e-4
        ]
        lengths[net] = sum(math.dist(t.start, t.end) for t in tracks)
        # one chain of tracks from the pad on J3 to the module's pin
        key = lambda p: (round(p[0], 4), round(p[1], 4))  # noqa: E731
        adj: dict = {}
        for t in tracks:
            adj.setdefault(key(t.start), set()).add(key(t.end))
            adj.setdefault(key(t.end), set()).add(key(t.start))
        a, b = (_pad(pcb, e) for e in ends)
        inside = lambda p, pad: all(abs(p[i] - pad.xy[i]) <= pad.size[i] / 2 + 1e-6 for i in (0, 1))  # noqa: E731
        start = [p for p in adj if inside(p, a)]
        seen, todo = set(start), list(start)
        while todo:
            for q in adj[todo.pop()] - seen:
                seen.add(q)
                todo.append(q)
        if not start or not any(inside(p, b) for p in seen):
            problems.append(f"{net}: no track chain from {ends[0]} to {ends[1]}")
        if lengths[net] > USB_LENGTH_MAX:
            problems.append(f"{net}: {lengths[net]:.2f} mm long (at most {USB_LENGTH_MAX})")
    skew = abs(lengths["ESP.USB_DN"] - lengths["ESP.USB_DP"])
    if skew > USB_SKEW_MAX:
        problems.append(f"D- {lengths['ESP.USB_DN']:.3f} mm, D+ {lengths['ESP.USB_DP']:.3f} mm: {skew:.3f} mm apart")
    coupled = 0.0  # mm of D- alongside D+ at the pair's pitch (parallel segments, overlap of their spans)
    for n in segs["ESP.USB_DN"]:
        for p in segs["ESP.USB_DP"]:
            lp = math.dist(p.start, p.end)
            if lp == 0 or _angle(n, p) >= 1.0:
                continue
            u = ((p.end[0] - p.start[0]) / lp, (p.end[1] - p.start[1]) / lp)
            rel = [(q[0] - p.start[0], q[1] - p.start[1]) for q in (n.start, n.end)]
            if any(abs(abs(r[0] * u[1] - r[1] * u[0]) - USB_PITCH) > 0.005 for r in rel):
                continue
            s0, s1 = sorted(r[0] * u[0] + r[1] * u[1] for r in rel)
            coupled += max(0.0, min(s1, lp) - max(s0, 0.0))
    if coupled < USB_COUPLED_MIN:
        problems.append(
            f"the pair runs side by side at {USB_PITCH:.3f} mm for {coupled:.1f} mm (at least {USB_COUPLED_MIN})"
        )
    assert not problems, "\n".join(problems)


def test_usb_pads_stay_reachable():
    # J3 takes a cable's wires put in from the top and soldered on the bottom (owner, 2026-11-08): its
    # pads are plated holes open on both sides (EspProgPads' geometry: drill USB_DRILL_MIN or more,
    # pad USB_PAD_MIN or more), under no other part's courtyard on either side, its own courtyard
    # clear of every other part's
    pcb = layout.load("main")
    j3 = pcb.footprints["J3"]
    assert j3.side == "top"
    nodes = {pad.number: (node, pad) for ref, node, pad in _pad_nodes() if ref == "J3"}
    assert {n: p.net for n, (_node, p) in nodes.items()} == {"1": "GND", "2": "ESP.USB_DN", "3": "ESP.USB_DP"}
    problems = []
    for n, (node, p) in sorted(nodes.items()):
        drill = float(node.child("drill").atoms()[0]) if node.child("drill") else 0.0
        both = {"*.Cu", "*.Mask"} <= set(p.layers) or {"F.Cu", "B.Cu", "F.Mask", "B.Mask"} <= set(p.layers)
        if p.kind != "thru_hole" or drill < USB_DRILL_MIN or min(p.size) < USB_PAD_MIN or not both:
            problems.append(f"J3.{n}: {p.kind}, drill {drill} mm, pad {min(p.size)} mm, layers {p.layers}")
    own = j3.courtyard_box()
    for ref, f in pcb.footprints.items():
        box = f.courtyard_box()
        if ref == "J3" or box is None:
            continue
        e = 0.001  # mm: courtyards that touch (C110's meets J3's) do not overlap
        if own[0] < box[2] - e and box[0] < own[2] - e and own[1] < box[3] - e and box[1] < own[3] - e:
            problems.append(f"{ref}'s courtyard ({f.side}) over J3's")
    assert not problems, "\n".join(problems)
