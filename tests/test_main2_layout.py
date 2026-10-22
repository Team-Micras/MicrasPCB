"""The second main board's layout against the robot: size, sides, and the chassis over the board.

spec/main2.toml holds the owner's brief and the zones the chassis takes: the drive blocks, motors
and encoder boards (MicrasHardware's model). The parts' heights come from their 3D models.
"""

import math

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
    """The footprints the spec places (screw holes, slots, switch, USB-C, wall sensors)."""
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


# Signal hops on In2.Cu (owner, 2026-10-21): where F.Cu and B.Cu leave no room, a digital line of
# the STM32 or the ESP32 crosses under on In2.Cu. A hop keeps IN2_UNDER (plan view) from every
# switching and analog track on B.Cu, which the 0.21 mm prepreg would couple it to, stays off the
# VBAT pour and out of the STM32's supply islands; In1.Cu carries no track.
IN2_UNDER = 0.25  # mm
SUPPLIES = {"GND", "3V3_D", "3V3_A", "VCORE", "VDDA", "VBAT", "VSYS", "+5V"}


def test_in2_signal_hops_are_digital_and_keep_clear():
    pcb = layout.load("main2")
    zones = _zones()
    hops = [t for t in pcb.tracks if t.layer in ("In1.Cu", "In2.Cu")]
    assert all(t.layer == "In2.Cu" for t in hops), "a track on In1.Cu"
    digital = {p.net for ref in ("IC1", "U13") for p in pcb.footprints[ref].pads if p.net}
    digital -= SUPPLIES | nets.ANALOG | nets.SWITCHING
    assert not {t.net for t in hops} - digital, f"not digital on In2.Cu: {sorted({t.net for t in hops} - digital)}"
    noisy = [t for t in pcb.tracks if t.layer == "B.Cu" and (t.net in nets.SWITCHING or t.net in nets.ANALOG)]
    near = sorted(
        {
            f"{h.net} {_gap(h, b):.2f} mm under {b.net} near {_xy(h.start)}"
            for h in hops
            for b in noisy
            if _gap(h, b) < IN2_UNDER
        }
    )
    assert not near, "\n".join(near)
    keep_off = [pts for n, layers, pts in zones if n == "VBAT" and "B.Cu" in layers]
    keep_off += [pts for n, layers, pts in zones if n in MCU_ISLANDS and "In2.Cu" in layers]
    inside = sorted({f"{h.net} at {_xy(p)}" for h in hops for p in _samples(h) if any(_inside(p, z) for z in keep_off)})
    assert not inside, "\n".join(inside)


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
    # but for a bridge's escape stubs (from a pad's centre): the DRV8874 puts VREF and IPROPI (pins
    # 5, 6) two pins from OUT1 (pin 8, SLVSF66A pinout), so the gap cannot hold at its pins (the
    # owner's exemption, as boards/main2/layout/route.py _bridge_stub())
    pcb = layout.load("main2")
    pins = [p.xy for ref in ("IC8", "IC9") for p in pcb.footprints[ref].pads]
    stub = lambda t: any(math.dist(e, q) < 0.01 for e in (t.start, t.end) for q in pins)  # noqa: E731
    sw = [t for t in pcb.tracks if t.net in nets.SWITCHING]
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
