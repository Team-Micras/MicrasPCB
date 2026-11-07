"""The wall boards on the main board: the joint's pinout and pad positions, and where the sensors
sit in the nose (inside the outline, out of each other's view).

Frames: the robot frame for the main board (spec/main.toml), the wall board's spec/wall.toml for
its own numbers.
"""

import itertools
import math
import re

import pytest
from micras_pcb import layout, mech, spec
from micras_pcb.paths import ROOT

from .conftest import needs_kicad
from .design import design

WALL = spec.load("wall")
MAIN = spec.load("main")

# The joint by role, pad n of the main board's joint = pin n of the wall board's header J1
# (components/micras/WallJoint; boards/wall/wall.zen): changing it breaks every board built for it.
ROLES = {"1": "output", "2": "GND", "3": "3V3_A", "4": "3V3_D", "5": "sink", "6": "pwm"}
WALL_NETS = {
    "PWM": "pwm",
    "EMITTER_SINK": "sink",
    "3V3_D": "3V3_D",
    "GND": "GND",
    "Wall_Sensor": "output",
    "3V3_A": "3V3_A",
}
# Each joint's selector on its TIM3 channel and its receiver on its ADC line
# (boards/main/firmware_changes.toml, emitters; boards/main/test/test_sensors.zen CHANNELS).
CHANNELS = {
    "W1": ("PC9", "Wall_Sensor_0"),
    "W2": ("PB0", "Wall_Sensor_1"),
    "W3": ("PB5", "Wall_Sensor_2"),
    "W4": ("PB4", "Wall_Sensor_3"),
}
SINK_FET = "Q9"
R_LOAD = 1e3  # the receiver's load at the ADC (boards/main/Sensors.zen, Receiver n)
PITCH, ROW_PITCH = WALL["header"]["pitch"], WALL["header"]["row_pitch"]  # HX PZ1.27-2x3P ZZ

LENS_MARGIN = 1.0  # mm: every lens inside the main board's outline (its edge meets a wall first)
VIEW_HALF_DEG = 5.0  # deg: a sensor's view corridor, from its lens, widening this much a side
VIEW_GAP = 0.5  # mm: no other wall board or lens nearer a sensor's view corridor
LED_TIP, BODY_R, FLANGE_R, FLANGE_T = 9.0, 2.55, 2.95, 0.95  # SFH 4550 at its largest (SFH-DS p.10)


def _sensors():
    """name -> (front face centre, look direction in radians), robot frame."""
    out = {}
    for path, (c, look) in mech.wall_joints(MAIN).items():
        a = math.radians(look)
        d = (math.cos(a), math.sin(a))
        half = WALL["pcb"]["thickness"] / 2
        out[path.split(".")[1]] = ((c[0] + d[0] * half, c[1] + d[1] * half), a)
    return out


def _body(face, a):
    """Plan-view points of a wall board (its blade, the widest part) and its emitter's lens (the
    larger one) at their largest."""
    d, n = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))

    def at(s, t):
        return (face[0] + s * d[0] + t * n[0], face[1] + s * d[1] + t * n[1])

    hw, th = WALL["outline"]["width"] / 2, WALL["pcb"]["thickness"]
    return [at(s, t) for s in (0.0, -th) for t in (-hw, hw)] + _lenses(face, a)


def _lenses(face, a):
    """Plan-view points of a sensor's lenses at their largest: the SFH 4550's flange, body and dome,
    which cover the TPS601A's below it."""
    d, n = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))

    def at(s, t):
        return (face[0] + s * d[0] + t * n[0], face[1] + s * d[1] + t * n[1])

    pts = [at(s * FLANGE_T / 4, t) for s in range(5) for t in (-FLANGE_R, FLANGE_R)]
    dome = LED_TIP - BODY_R
    pts += [at(s * dome / 24, t) for s in range(25) for t in (-BODY_R, BODY_R)]
    pts += [
        at(dome + BODY_R * math.cos(math.radians(k)), BODY_R * math.sin(math.radians(k))) for k in range(-90, 91, 10)
    ]
    return pts


def _inside(p, poly):
    x, y = p
    c = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1], strict=True):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def test_wall_sensors_sit_inside_the_outline():
    poly = mech.chain(mech.main_perimeter(MAIN))
    edges = list(zip(poly, poly[1:] + poly[:1], strict=True))
    for name, (face, a) in _sensors().items():
        worst = min(
            min(mech._seg_distance(p, u, v) for u, v in edges) if _inside(p, poly) else -1.0 for p in _body(face, a)
        )
        assert worst >= LENS_MARGIN, f"{name}: its board or lens comes {worst:.2f} mm from the outline"


def test_wall_sensors_keep_out_of_each_others_view():
    sensors = _sensors()
    for name, (face, a) in sensors.items():
        d, n = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
        tip = (face[0] + LED_TIP * d[0], face[1] + LED_TIP * d[1])
        for other, (oface, oa) in sensors.items():
            if other == name:
                continue
            for p in _body(oface, oa):
                r = (p[0] - tip[0]) * d[0] + (p[1] - tip[1]) * d[1]
                if r < 0:
                    continue
                t = abs((p[0] - tip[0]) * n[0] + (p[1] - tip[1]) * n[1])
                gap = t - (BODY_R + r * math.tan(math.radians(VIEW_HALF_DEG)))
                assert gap >= VIEW_GAP, f"{other} sits {gap:.2f} mm from {name}'s view at {p}"


@needs_kicad
def test_wall_header_pins_have_the_joint_roles():
    w = design("wall")
    got = {pin: WALL_NETS.get(w.net("J1", pin), w.net("J1", pin)) for pin in ROLES}
    assert got == ROLES


@needs_kicad
def test_main_board_joints_carry_the_joint_roles():
    m = design("main")
    sink, v3d, v3a = m.net(SINK_FET, "D"), m.net("IC1", "VDD"), m.net("U12", "V+")
    for joint, (tim3, adc) in CHANNELS.items():
        got = {pad: m.net(joint, pad) for pad in ROLES}
        want = {"1": adc, "2": "GND", "3": v3a, "4": v3d, "5": sink, "6": m.net("IC1", tim3)}
        assert got == want, f"{joint}: {got}"
        assert want["5"].split(".")[-1] == "EMITTER_SINK" and (want["4"], want["3"]) == ("3V3_D", "3V3_A"), want
        loads = [r for r in m.two_terminal("resistor", adc, "GND") if m.value(r, "resistance") == pytest.approx(R_LOAD)]
        assert len(loads) == 1, f"{joint}: {adc} needs one 1 kOhm load to GND, found {loads}"


@needs_kicad
def test_joint_values_are_the_wall_boards():
    # The main board's emitter checks read the wall board's emitter resistor and SFH 4550 rating
    # from the joint (components/micras/WallJoint): they must be the wall board's.
    joint = (ROOT / "components/micras/WallJoint/WallJoint.zen").read_text()
    sensor = (ROOT / "components/micras/WallSensor/WallSensor.zen").read_text()
    r1 = design("wall").value("R1", "resistance")
    assert f'"emitter_resistor": Resistance("{r1:g}Ohm")' in joint
    rating = re.search(r'"emitter_pulse_current": Current\("(\d+)mA"\)', sensor).group(1)
    assert f'"emitter_pulse_current": Current("{rating}mA")' in joint


@needs_kicad
def test_main_board_joint_pads_meet_the_header():
    """Pad n sits in the front row (odd, ROW_PITCH / 2 ahead of the joint's centre along the look
    direction) or the back row (even), at t = -1.27, 0, +1.27 mm for pins 1-2, 3-4, 5-6, t to the
    robot's left of the look direction: the header's pin 1 is on the wall board's left seen from
    the front."""
    pcb = layout.load("main")
    for path, (c, look) in mech.wall_joints(MAIN).items():
        ref = path.split(".")[1]
        a = math.radians(look)
        d, n = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
        pads = pcb.footprints[ref].pads
        assert sorted(p.number for p in pads) == sorted(ROLES), f"{ref}: pads {[p.number for p in pads]}"
        for p in pads:
            x, y = mech.kicad_to_robot(MAIN, p.xy)
            s = (x - c[0]) * d[0] + (y - c[1]) * d[1]
            t = (x - c[0]) * n[0] + (y - c[1]) * n[1]
            k = int(p.number)
            assert s == pytest.approx(ROW_PITCH / 2 * (1 if k % 2 else -1), abs=1e-3), f"{ref} pad {p.number}"
            assert t == pytest.approx(PITCH * ((k - 1) // 2 - 1), abs=1e-3), f"{ref} pad {p.number}"


WALL_JOINT_FP = ROOT / "components/micras/WallJoint/WallJoint_2x03_P1.27mm.kicad_mod"


def test_joint_footprint_is_the_specs():
    """The joint's holes and pads are spec/wall.toml [joint]'s, and its courtyard is the header's
    insulator, on which the wall board's handle stands, plus 0.25 mm (the blade above it is
    _strips()'s)."""
    from micras_pcb import sexpr

    root = sexpr.parse(WALL_JOINT_FP.read_text())
    h, j = WALL["header"], WALL["joint"]
    for pad in root.children("pad"):
        assert float(pad.child("drill").atoms()[0]) == pytest.approx(j["drill"])
        assert float(pad.child("size").atoms()[0]) == pytest.approx(j["pad"])
    xs, ys = zip(*_courtyard_local(root), strict=True)
    assert max(xs) == pytest.approx(h["insulator_length"] / 2 + 0.25) and min(xs) == pytest.approx(-max(xs))
    assert max(ys) == pytest.approx(h["insulator_width"] / 2 + 0.25) and min(ys) == pytest.approx(-max(ys))
    assert WALL["outline"]["handle_width"] / 2 <= max(xs), "the handle overhangs the courtyard"


def _courtyard_local(root):
    """The joint footprint's F.CrtYd rectangle as its four corners, footprint frame."""
    rect = next(r for r in root.children("fp_rect") if r.child("layer").atoms() == ["F.CrtYd"])
    (u0, v0), (u1, v1) = (tuple(float(a) for a in rect.child(k).atoms()) for k in ("start", "end"))
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


def _courtyards():
    """name -> each wall joint's courtyard (the WallJoint footprint's F.CrtYd: the header's
    insulator, on which the wall board's handle stands) in the robot frame."""
    from micras_pcb import sexpr

    local = _courtyard_local(sexpr.parse(WALL_JOINT_FP.read_text()))
    out = {}
    for path, (c, look) in mech.wall_joints(MAIN).items():
        a = math.radians(look)
        d, n = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
        # footprint u runs to the robot's right of the look direction, v rearwards (KiCad's y down)
        out[path.split(".")[1]] = [(c[0] - v * d[0] - u * n[0], c[1] - v * d[1] - u * n[1]) for u, v in local]
    return out


def _strips():
    """name -> the wall board's blade over each joint in plan (robot frame): as wide as the blade,
    from its front face to its back-face parts; beside the joint's courtyard it stands spec/wall.toml
    joint.under_blade + 0.5 mm or more over the main board, so the main board's parts under it stay
    at or below joint.under_blade."""
    out = {}
    hw, th, back = WALL["outline"]["width"] / 2, WALL["pcb"]["thickness"], WALL["joint"]["back_parts"]
    for path, (c, look) in mech.wall_joints(MAIN).items():
        a = math.radians(look)
        d, n = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
        local = [(-hw, th / 2), (hw, th / 2), (hw, -th / 2 - back), (-hw, -th / 2 - back)]  # (t, s)
        out[path.split(".")[1]] = [(c[0] + s_ * d[0] + t * n[0], c[1] + s_ * d[1] + t * n[1]) for t, s_ in local]
    return out


def test_wall_sensors_look_where_the_firmware_expects():
    """The frontal pair at y +-19.8 looking forward (the owner, 2026-11-03; the firmware reads the
    positions from build/main/main_mech.json), the diagonal pair at +-45 deg, mirror images."""
    w = {k: MAIN[k] for k in ("w1", "w2", "w3", "w4")}
    assert (w["w1"]["y"], w["w1"]["rotation"], w["w4"]["rotation"]) == (19.8, 0, 0)
    assert (w["w2"]["rotation"], w["w3"]["rotation"]) == (45, -45)
    for a, b in (("w1", "w4"), ("w2", "w3")):
        assert (w[a]["x"], w[a]["y"]) == (w[b]["x"], -w[b]["y"]), f"{a} and {b} are not mirror images"


def test_wall_boards_keep_off_the_fan_ring_and_the_chassis_zones():
    """The fan's shroud seals on the ring round the fan hole (spec [fan_ring]) and the chassis stands
    on its zones: no wall board or header inside either."""
    c, r = (MAIN["fan_hole"]["x"], 0.0), MAIN["fan_ring"]["diameter"] / 2
    for name, poly in _courtyards().items():
        edges = list(zip(poly, poly[1:] + poly[:1], strict=True))
        assert not _inside(c, poly) and min(mech._seg_distance(c, a, b) for a, b in edges) >= r, (
            f"{name} in the fan ring"
        )
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        for zone, (x0, x1, y0, y1, _h) in mech.keepout_zones(MAIN):
            # convex polygon against a rectangle: apart if a rectangle side or a polygon side separates them
            corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            apart = max(xs) <= x0 or min(xs) >= x1 or max(ys) <= y0 or min(ys) >= y1
            for a, b in edges:
                nx, ny = b[1] - a[1], a[0] - b[0]
                side = [(q[0] - a[0]) * nx + (q[1] - a[1]) * ny for q in corners]
                inner = [(q[0] - a[0]) * nx + (q[1] - a[1]) * ny for q in poly]
                apart |= (min(side) >= -1e-9 and max(inner) <= 1e-9) or (max(side) <= 1e-9 and min(inner) >= -1e-9)
            assert apart, f"{name} stands in the chassis zone {zone}"


def test_wall_joints_sit_on_the_board():
    """The header's insulator and the wall board stand on the main board: each joint's courtyard
    lies inside the outline, so its holes keep far more than the copper-to-edge clearance."""
    poly = mech.chain(mech.main_perimeter(MAIN))
    edges = list(zip(poly, poly[1:] + poly[:1], strict=True))
    for name, court in _courtyards().items():
        worst = min(min(mech._seg_distance(p, a, b) for a, b in edges) if _inside(p, poly) else -1.0 for p in court)
        assert worst >= 0.0, f"{name}'s joint reaches {-worst:.2f} mm past the outline"


def test_wall_boards_keep_off_each_other():
    """No two wall joints' courtyards (the boards with their headers) overlap."""
    for (a, p), (b, q) in itertools.combinations(_courtyards().items(), 2):
        assert _apart(p, q), f"{a} and {b} overlap"


def _hull(pts):
    pts = sorted(set(pts))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def test_wall_boards_and_lenses_keep_off_each_other():
    """The lenses stand 7.5-13.6 mm up, under the wall boards' 17 mm tops: in plan, no sensor's board
    and lens (at their largest) comes within VIEW_GAP of another's, wherever they are."""
    hulls = {name: _hull(_body(face, a)) for name, (face, a) in _sensors().items()}
    for (a, p), (b, q) in itertools.combinations(hulls.items(), 2):
        gap = min(
            min(mech._seg_distance(v, s, t) for s, t in zip(poly, [*poly[1:], poly[0]], strict=True))
            for v, poly in [*((v, q) for v in p), *((v, p) for v in q)]
        )
        assert _apart(p, q) and gap >= VIEW_GAP, f"{a} and {b}: {gap:.2f} mm apart"


def _apart(p, q) -> bool:
    """Two convex polygons are disjoint: one side of either separates them."""
    for poly in (p, q):
        for u, v in zip(poly, [*poly[1:], poly[0]], strict=True):
            nx, ny = v[1] - u[1], u[0] - v[0]
            pa = [(w[0] - u[0]) * nx + (w[1] - u[1]) * ny for w in p]
            qa = [(w[0] - u[0]) * nx + (w[1] - u[1]) * ny for w in q]
            if max(pa) <= min(qa) + 1e-9 or max(qa) <= min(pa) + 1e-9:
                return True
    return False


# The printed case round each sensor (MicrasHardware micras/front.py at 6b48d17, the sensor caps):
# it slides on from the front and wraps the lenses, its bore fitting them with FrontParams.fit
# 0.25 mm and its wall 0.8 mm thick. The cap is sleeves round the lenses with no base (the owner,
# 2026-11-03): in plan the hull of the lenses at their largest grown by both, 8.0 mm across
# whatever the wall board's width, and nothing behind the board's front face. The cases must not
# conflict: apart from each other, out of the other sensors' views, and inside the main board's
# outline (its edge still meets a wall first).
CASE_GROW = 0.25 + 0.8  # mm: FrontParams.fit + the case's wall (front.py)
CASE_GAP = 0.3  # mm between two cases


def _case(face, a):
    """Plan-view outline of a sensor's case (a convex polygon, robot frame)."""
    d = (math.cos(a), math.sin(a))
    ring = [(CASE_GROW * math.cos(2 * math.pi * k / 48), CASE_GROW * math.sin(2 * math.pi * k / 48)) for k in range(48)]
    grown = _hull([(x + u, y + v) for x, y in _hull(_lenses(face, a)) for u, v in ring])
    s = [(p[0] - face[0]) * d[0] + (p[1] - face[1]) * d[1] for p in grown]
    out = []  # the hull clipped to the half-plane in front of the board's front face
    for k, p in enumerate(grown):
        q, sp, sq = grown[(k + 1) % len(grown)], s[k], s[(k + 1) % len(grown)]
        if sp >= 0:
            out.append(p)
        if (sp >= 0) != (sq >= 0):
            t = sp / (sp - sq)
            out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    # no zero-length sides: _apart takes each side's normal as a separating axis
    return [p for k, p in enumerate(out) if math.dist(p, out[k - 1]) > 1e-6]


def _poly_gap(p, q) -> float:
    return min(
        min(mech._seg_distance(v, s, t) for s, t in zip(poly, [*poly[1:], poly[0]], strict=True))
        for v, poly in [*((v, q) for v in p), *((v, p) for v in q)]
    )


def test_sensor_cases_keep_off_each_other():
    cases = {name: _case(face, a) for name, (face, a) in _sensors().items()}
    for (a, p), (b, q) in itertools.combinations(cases.items(), 2):
        gap = _poly_gap(p, q)
        assert _apart(p, q) and gap >= CASE_GAP, f"the cases of {a} and {b}: {gap:.2f} mm apart"


def test_sensor_cases_keep_out_of_each_others_view():
    sensors = _sensors()
    for name, (face, a) in sensors.items():
        d, n = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
        tip = (face[0] + LED_TIP * d[0], face[1] + LED_TIP * d[1])
        for other, (oface, oa) in sensors.items():
            if other == name:
                continue
            for p in _case(oface, oa):
                r = (p[0] - tip[0]) * d[0] + (p[1] - tip[1]) * d[1]
                if r < 0:
                    continue
                t = abs((p[0] - tip[0]) * n[0] + (p[1] - tip[1]) * n[1])
                gap = t - (BODY_R + r * math.tan(math.radians(VIEW_HALF_DEG)))
                assert gap >= VIEW_GAP, f"{other}'s case sits {gap:.2f} mm from {name}'s view at {p}"


def test_sensor_cases_sit_inside_the_outline():
    poly = mech.chain(mech.main_perimeter(MAIN))
    edges = list(zip(poly, poly[1:] + poly[:1], strict=True))
    for name, (face, a) in _sensors().items():
        worst = min(
            min(mech._seg_distance(p, u, v) for u, v in edges) if _inside(p, poly) else -1.0 for p in _case(face, a)
        )
        assert worst >= 0.0, f"{name}'s case reaches {worst:.2f} mm past the outline"
