"""The mechanical specs are well formed and their geometry is consistent."""

import itertools
import math
import tomllib

import pytest
from micras_pcb import mech, sexpr, spec
from micras_pcb.paths import ROOT, board_pcb

SPECS = sorted(p.stem for p in (ROOT / "spec").glob("*.toml"))


@pytest.mark.parametrize("board", SPECS)
def test_every_value_has_a_source(board):
    raw = tomllib.loads((ROOT / "spec" / f"{board}.toml").read_text())
    for section, values in raw.items():
        for key, v in values.items():
            assert isinstance(v, dict) and v.get("source"), f"{section}.{key} needs {{value, source}}"


def _ends(e):
    return e.a, e.b


def test_encoder_outline_is_closed():
    outline = mech.encoder_outline(spec.load("encoder"))
    for prev, nxt in zip(outline, [*outline[1:], outline[0]], strict=True):
        assert math.dist(_ends(prev)[1], _ends(nxt)[0]) < 1e-9


def test_encoder_outline_matches_spec_extents():
    s = spec.load("encoder")
    pts = [p for e in mech.encoder_outline(s) for p in mech.sample(e, 64)]
    us, vs = [p[0] for p in pts], [p[1] for p in pts]
    assert max(us) - min(us) == pytest.approx(s["outline"]["width"], abs=1e-6)
    assert max(vs) == pytest.approx(s["outline"]["top"], abs=1e-6)
    assert min(vs) == pytest.approx(-s["tab"]["depth"], abs=1e-6)


def test_sensor_fits_on_the_board():
    s = spec.load("encoder")
    # the SOP65P640X120-14N courtyard (User.15 in components/ams/AS5047U) is 7.85 x 5.6 mm
    assert s["sensor"]["v"] + 2.8 < s["outline"]["top"]
    assert abs(s["sensor"]["u"]) + 3.925 < s["outline"]["width"] / 2


def test_encoder_layout_matches_the_spec():
    text = board_pcb("encoder").read_text()
    new, changes, problems = mech.apply("encoder", text)
    assert (changes, problems) == ([], [])
    assert new == text


def test_encoder_features_catch_a_moved_outline():
    # the outline check is not vacuous: the layout shifted by 0.1 mm fails it
    s = spec.load("encoder")
    s["kicad"] = {**s["kicad"], "origin_x": s["kicad"]["origin_x"] + 0.1}
    problems = mech.encoder_features(s, sexpr.parse(board_pcb("encoder").read_text()))
    assert any("tab" in p for p in problems) and any("side" in p for p in problems)


def test_encoder_mech_export_is_the_layout_outline():
    s = spec.load("encoder")
    m = mech.mech_json("encoder")
    us, vs = [p[0] for p in m["outline"]], [p[1] for p in m["outline"]]
    assert max(us) - min(us) == pytest.approx(s["outline"]["width"], abs=1e-3)
    assert (max(vs), min(vs)) == pytest.approx((s["outline"]["top"], -s["tab"]["depth"]), abs=1e-3)
    assert m["thickness"] == s["pcb"]["thickness"]
    assert (m["sensor"]["u"], m["sensor"]["v"]) == (s["sensor"]["u"], s["sensor"]["v"])
    # counter-clockwise, no repeated points
    ring = [*m["outline"], m["outline"][0]]
    assert sum(a[0] * b[1] - b[0] * a[1] for a, b in itertools.pairwise(ring)) > 0
    assert all(a != b for a, b in itertools.pairwise(ring))


# ---------------------------------------------------------------------------------------------
# main board


@pytest.fixture(scope="module")
def main_spec():
    return spec.load("main")


@pytest.fixture(scope="module")
def main_layout():
    return sexpr.parse(board_pcb("main").read_text())


# JLCPCB PCB capabilities (jlcpcb.com/capabilities/pcb-capabilities, read 2026-10-14): board
# thickness below 1.0 mm +-0.1 mm; non-plated slots at least 1.0 mm wide. Milled outline +-0.1 mm:
# on the slot's width, and at each of its two ends (spec/main.toml encoder_slots.length). The spec
# draws the slot on a 0.1 mm grid.
JLC_THIN_BOARD_TOL = 0.1
JLC_OUTLINE_TOL = 0.1
JLC_MIN_SLOT = 1.0
SPEC_GRID = 0.1


def _open_length(length: float, radius: float, thickness: float) -> float:
    """Length of a round-ended slot open to a board of this thickness standing in it: the straight
    part plus what each end circle leaves at the board's half thickness."""
    return length - 2 * radius + 2 * math.sqrt(radius**2 - (thickness / 2) ** 2)


def test_encoder_tab_fits_the_main_board_slots(main_spec):
    enc, slot = spec.load("encoder"), main_spec["encoder_slots"]
    # The tab stands in the slot: its width along the slot, the encoder board's thickness across
    # it. It is soldered to the slot's pads, which fix its position, so the slot only has to let
    # it in at the worst case of both boards' tolerances, and be no larger than that needs.
    r, t, tab = slot["corner_radius"], enc["pcb"]["thickness"], enc["tab"]["width"]
    w, length = slot["width"], slot["length"]
    t_max = t + JLC_THIN_BOARD_TOL
    # worst case: the slot milled 0.1 mm narrow and 0.1 mm short at each end, the board thick
    assert w - JLC_OUTLINE_TOL >= t_max - 1e-9, "the thickest encoder board does not enter the narrowest slot"
    assert _open_length(length - 2 * JLC_OUTLINE_TOL, r, t_max) >= tab - 1e-9, (
        "the tab does not enter the shortest slot"
    )
    # no larger than that: one grid step less fails, or the slot is at JLCPCB's minimum width
    assert w <= JLC_MIN_SLOT + 1e-9 or w - SPEC_GRID - JLC_OUTLINE_TOL < t_max
    assert _open_length(length - SPEC_GRID - 2 * JLC_OUTLINE_TOL, r, t_max) < tab
    # the tab is not deeper than the main board is thick, so it does not stick out below
    assert enc["tab"]["depth"] <= main_spec["pcb"]["thickness"]


def test_slots_are_symmetric_about_the_axle(main_spec):
    centres = sorted(mech.slots(main_spec).values())
    assert centres == [(0.0, -main_spec["encoder_slots"]["y"]), (0.0, main_spec["encoder_slots"]["y"])]


def test_screw_holes_are_symmetric_and_on_the_board(main_spec, main_layout):
    holes = [(p["x"], p["y"]) for path, p in mech.placements(main_spec).items() if path.startswith("H")]
    assert len(holes) == 4
    assert sorted(holes) == sorted((x, -y) for x, y in holes)
    outline = [p for e in mech.outline_elements(main_spec, main_layout) for p in mech.sample(e, 64)]
    r = main_spec["holes"]["diameter"] / 2
    for h in holes:
        assert min(math.dist(h, p) for p in outline) > r + 0.5, f"hole {h} too close to the board edge"


def test_hole_diameter_is_the_mounting_hole_footprint(main_spec):
    fp = sexpr.parse((ROOT / "components/micras/MountingHole/MountingHole_2.4mm_NPTH.kicad_mod").read_text())
    (pad,) = fp.children("pad")
    assert float(pad.child("drill").atoms()[0]) == main_spec["holes"]["diameter"]


def test_main_layout_has_every_spec_footprint(main_spec, main_layout):
    # the spec draws the outline (mech.OUTLINES); the encoder slot footprints sit on their slots and
    # the screw holes have the spec's drill
    assert mech.footprint_checks(main_spec, main_layout) == []


def test_main_layout_matches_the_spec(main_spec):
    text = board_pcb("main").read_text()
    new, changes, problems = mech.apply("main", text)
    assert (changes, problems) == ([], [])
    assert new == text


def test_zone_order_is_canonical_whatever_order_kicad_saves():
    # KiCad saves the teardrop zones (no UUID) interleaved with the others in a new order each time:
    # the teardrops moved to the front in reverse, the rest kept, come back as the layout has them.
    text = board_pcb("main").read_text()
    root = sexpr.parse(text)
    spans = [sexpr.line_span(text, z) for z in root.children("zone")]
    kept = [text[a:b] for (a, b), z in zip(spans, root.children("zone"), strict=True) if z.child("uuid")]
    tears = [text[a:b] for (a, b), z in zip(spans, root.children("zone"), strict=True) if not z.child("uuid")]
    assert tears, "the main board has teardrops"
    scrambled = sexpr.splice(text, [(a, b, s) for (a, b), s in zip(spans, [*tears[::-1], *kept], strict=True)])
    assert scrambled != text
    assert mech.zone_order(scrambled) == text


def test_main_mech_export_is_in_the_robot_frame(main_spec):
    m = mech.mech_json("main")
    xs = [p[0] for e in m["edge"] for k in ("start", "end") for p in [e[k]]]
    ys = [p[1] for e in m["edge"] for k in ("start", "end") for p in [e[k]]]
    assert max(xs) == pytest.approx(main_spec["outline"]["front"], abs=1e-3)
    assert min(xs) == pytest.approx(main_spec["outline"]["rear"], abs=1e-3)
    assert max(ys) - min(ys) == pytest.approx(main_spec["outline"]["width"], abs=1e-3)
    assert [h["name"] for h in m["holes"]] == ["H1", "H2", "H3", "H4"]


# --- the outline the spec draws, the antenna notch ------------------------------------------------

MAIN = spec.load("main")
U13_FOOTPRINT = ROOT / "components/espressif/ESP32-C5-MINI-1/ESP32-C5-MINI-1.kicad_mod"
EDGE_CLEARANCE = 0.2  # mm, copper to board edge (rules/jlcpcb.kicad_dru)


def _main_board() -> list[tuple[float, float]]:
    """The main board's outline (robot frame) as a polygon: the largest closed loop of the elements."""
    els = mech.main_outline(MAIN)
    loops, left = [], list(els)
    while left:
        group, ends = [left.pop(0)], None
        ends = {_key(group[0].a), _key(group[0].b)}
        grown = True
        while grown:
            grown = False
            for e in list(left):
                if _key(e.a) in ends or _key(e.b) in ends:
                    group.append(e)
                    left.remove(e)
                    ends |= {_key(e.a), _key(e.b)}
                    grown = True
        loops.append(group)
    board = max(loops, key=len)
    return mech.chain(board)


def _key(p):
    return round(p[0], 6), round(p[1], 6)


def _inside(p, poly) -> bool:
    x, y = p
    hit = False
    for (x0, y0), (x1, y1) in zip(poly, [*poly[1:], poly[0]], strict=True):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def _edge_distance(p, poly) -> float:
    def seg(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = dx * dx + dy * dy
        u = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
        return math.dist(p, (a[0] + u * dx, a[1] + u * dy))

    return min(seg(a, b) for a, b in zip(poly, [*poly[1:], poly[0]], strict=True))


def _u13_to_robot(u: float, v: float) -> tuple[float, float]:
    """A point of U13's footprint (KiCad footprint frame) on the board, in the robot frame."""
    p = MAIN["u13"]
    a = math.radians(p["rotation"])
    kx, ky = mech.robot_to_kicad(MAIN, (p["x"], p["y"]))
    return mech.kicad_to_robot(MAIN, (kx + u * math.cos(a) + v * math.sin(a), ky - u * math.sin(a) + v * math.cos(a)))


def _u13_footprint():
    root = sexpr.parse(U13_FOOTPRINT.read_text())
    keepout = next(z for z in root.children("zone") if z.child("keepout"))
    area = [tuple(float(v) for v in xy.atoms()) for xy in keepout.child("polygon").child("pts").children("xy")]
    pads = []
    for pad in root.children("pad"):
        (u, v, *_), (w, h) = (float(a) for a in pad.child("at").atoms()), (float(a) for a in pad.child("size").atoms())
        pads.append((pad.atoms()[0], [(u + su * w / 2, v + sv * h / 2) for su in (1, -1) for sv in (1, -1)]))
    return area, pads


def test_main_outline_is_one_closed_loop():
    board = _main_board()
    assert len(board) > 100
    o = MAIN["outline"]
    xs, ys = [p[0] for p in board], [p[1] for p in board]
    assert max(xs) == pytest.approx(o["front"], abs=1e-6)
    assert min(xs) == pytest.approx(o["rear"], abs=1e-6)
    assert (min(ys), max(ys)) == (pytest.approx(-o["width"] / 2, abs=1e-6), pytest.approx(o["width"] / 2, abs=1e-6))


def test_main_antenna_notch_cuts_the_board_away_under_the_antenna():
    """ESP32-C5 Hardware Design Guidelines (Positioning a Module on a Base Board): no board under the
    module's antenna; the footprint's keep-out (the 5.85 mm antenna area, ESP32-C5-MINI-1 datasheet
    v1.4 Figure 11-1) lies in the notch, the module's pads on the board, at least the edge
    clearance in."""
    board = _main_board()
    area, pads = _u13_footprint()
    corners = [_u13_to_robot(u, v) for u, v in area]
    cx, cy = (sum(c[0] for c in corners) / len(corners), sum(c[1] for c in corners) / len(corners))
    # the keep-out's corners, a hair towards its centre, and a grid over it: all off the board
    xs, ys = [c[0] for c in corners], [c[1] for c in corners]
    grid = [
        (min(xs) + (max(xs) - min(xs)) * i / 20, min(ys) + (max(ys) - min(ys)) * j / 40)
        for i in range(21)
        for j in range(41)
    ]
    inner = [(x + (cx - x) * 1e-3, y + (cy - y) * 1e-3) for x, y in [*corners, *grid]]
    on_board = [p for p in inner if _inside(p, board) and _edge_distance(p, board) > 1e-3]
    assert not on_board, f"antenna area on the board at {on_board[:3]}"
    for name, pts in pads:
        for p in (_u13_to_robot(u, v) for u, v in pts):
            assert _inside(p, board), f"U13 pad {name} off the board at {p}"
            assert _edge_distance(p, board) >= EDGE_CLEARANCE - 1e-6, f"U13 pad {name} at {p}: too near the edge"


CHASSIS = ROOT / "spec/main_chassis.json"
U13_HEIGHT = 2.4  # mm, ESP32-C5-MINI-1 datasheet v1.4 Table 1-1


def _board_spans(x: float, board) -> list[tuple[float, float]]:
    """The y intervals of the board polygon on the line through x."""
    ys = sorted(
        a[1] + (x - a[0]) * (b[1] - a[1]) / (b[0] - a[0])
        for a, b in zip(board, [*board[1:], board[0]], strict=True)
        if (a[0] > x) != (b[0] > x)
    )
    return list(zip(ys[0::2], ys[1::2], strict=True))


def test_drive_block_zones_hold_the_model():
    """spec/main_chassis.json (tools/chassis_shadow.py, from MicrasHardware's model) gives, for every
    0.1 mm point of the board under a drive block, motor or wheel, the height a part may reach there and
    keep Layout.clearance from it. Every such point on the board lies in a [drive_blocks] zone no
    higher than that."""
    import json

    data = json.loads(CHASSIS.read_text())
    assert data["clearance"] == 0.3
    zones = [z for _, z in mech.keepout_zones(MAIN)]
    board = _main_board()
    problems = []
    for x, runs in data["allowed"]:
        here = [z for z in zones if z[0] - 1e-6 <= x <= z[1] + 1e-6]
        spans = _board_spans(x, board)
        for y0, y1, tenths in runs:
            cover = sorted((z[2], z[3]) for z in here if z[4] <= tenths / 10 + 1e-9)
            for b0, b1 in spans:
                lo, hi = max(y0, b0 + 1e-3), min(y1, b1 - 1e-3)
                for c0, c1 in cover:
                    if c0 > lo + 1e-6:
                        break
                    lo = max(lo, c1)
                if lo < hi - 1e-6:
                    problems.append(f"x {x}: y {lo:.2f}..{hi:.2f} allows {tenths / 10} mm, no zone that low")
    assert not problems, "\n".join(problems[:20])


def test_u13_keeps_behind_the_low_chassis_zones():
    """U13's courtyard (the footprint's F.CrtYd: 8.0 mm a side, 13.9 mm behind and 8.0 mm ahead of
    its centre) overlaps no chassis zone lower than the module: the rear edge is at or behind the
    module's bound."""
    u = MAIN["u13"]
    assert u["rotation"] == 180
    x0, x1, y0, y1 = u["x"] - 13.9, u["x"] + 8.0, u["y"] - 8.0, u["y"] + 8.0
    for name, z in mech.keepout_zones(MAIN):
        if z[4] < U13_HEIGHT:
            overlap = min(x1, z[1]) - max(x0, z[0]) > 1e-6 and min(y1, z[3]) - max(y0, z[2]) > 1e-6
            assert not overlap, f"U13's courtyard runs into {name} (parts up to {z[4]} mm)"


def _antenna_corners() -> list[tuple[float, float]]:
    """U13's antenna end corners: 13.6 mm behind its centre (footprint F.Fab), 7.7 mm a side (15.4 mm
    module, ESP32-C5-MINI-1 datasheet v1.4 Figure 10-1); rotation 180 turns the antenna rearwards."""
    u = MAIN["u13"]
    return [(u["x"] - 13.6, u["y"] - 7.7), (u["x"] - 13.6, u["y"] + 7.7)]


def test_the_robot_fills_its_turning_circle():
    """The owner (2026-11-03): the turning circle is the nose's (the farthest outline point ahead of
    the axle); every outline point and U13's antenna corners lie within it, and the rear edge sits
    where the antenna's outer corner reaches it, so both ends fill the same circle."""
    pts = [p for e in mech.main_perimeter(MAIN) for p in mech.sample(e, 256)]
    r = max(math.hypot(*p) for p in pts if p[0] > 0)
    assert max(math.hypot(*p) for p in pts) <= r + 1e-6, (
        "an outline point behind the axle reaches past the nose's circle"
    )
    ant = max(math.hypot(*p) for p in _antenna_corners())
    assert ant <= r + 1e-6, f"U13's antenna reaches {ant:.2f} mm, past the nose's {r:.2f} mm"
    assert ant >= r - 0.1, f"the rear could move {r - ant:.2f} mm back: the antenna corner is inside the circle"


IC1_FOOTPRINT = ROOT / "components/st/STM32H725RGV6/QFN-68-1EP_8x8mm_P0.4mm_EP6.5x6.5mm_SplitPaste.kicad_mod"


def _ic1_courtyard() -> list[tuple[float, float]]:
    """IC1's courtyard (its footprint's F.CrtYd) where spec [ic1] places it, in the robot frame."""
    ic = MAIN["ic1"]
    root = sexpr.parse(IC1_FOOTPRINT.read_text())
    rect = next(r for r in root.children("fp_rect") if r.child("layer").atoms() == ["F.CrtYd"])
    (u0, v0), (u1, v1) = (tuple(float(x) for x in rect.child(k).atoms()) for k in ("start", "end"))
    a = math.radians(ic["rotation"])
    kx, ky = mech.robot_to_kicad(MAIN, (ic["x"], ic["y"]))
    return [
        mech.kicad_to_robot(MAIN, (kx + u * math.cos(a) + v * math.sin(a), ky - u * math.sin(a) + v * math.cos(a)))
        for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))
    ]


def _poly_distance(p, q) -> float:
    """The distance between two disjoint convex polygons (0 when they meet)."""
    if any(_inside(v, q) for v in p) or any(_inside(v, p) for v in q):
        return 0.0
    return min(
        min(mech._seg_distance(v, a, b) for a, b in zip(poly, [*poly[1:], poly[0]], strict=True))
        for v, poly in [*((v, q) for v in p), *((v, p) for v in q)]
    )


def test_ic1_has_its_room_at_the_front():
    """spec [ic1]: the MCU centred at the front on the centre line, as the owner wants it, turned 45
    deg and partly over the fan ring (it is 0.995 mm high; the ring's silk breaks at its pads,
    test_spec_silkscreen_draws_the_fan_ring). Its courtyard keeps [ic1] hole_gap from the fan hole's
    edge and [ic1] block from every wall joint's courtyard, the room for its decoupling, and that room
    lies on the board."""
    from .test_wall_joint import _courtyards

    ic = MAIN["ic1"]
    assert ic["y"] == 0.0 and ic["rotation"] % 90 == 45
    cy = _ic1_courtyard()
    fan, hole = (MAIN["fan_hole"]["x"], 0.0), MAIN["fan_hole"]["diameter"] / 2
    edge = [
        (p[0] + (q[0] - p[0]) * k / 40, p[1] + (q[1] - p[1]) * k / 40)
        for p, q in zip(cy, [*cy[1:], cy[0]], strict=True)
        for k in range(40)
    ]
    gap = min(math.dist(p, fan) for p in edge) - hole
    assert gap >= ic["hole_gap"] - 1e-6, f"IC1's courtyard {gap:.2f} mm from the fan hole"
    for name, wall in _courtyards().items():
        d = _poly_distance(cy, wall)
        assert d >= ic["block"] - 1e-6, f"{name} {d:.2f} mm from IC1's courtyard"
    board = _main_board()
    m = ic["block"]
    c = (ic["x"], ic["y"])
    room = [(c[0] + (p[0] - c[0]) * (1 + m / 4.68), c[1] + (p[1] - c[1]) * (1 + m / 4.68)) for p in cy]
    for p, q in zip(room, [*room[1:], room[0]], strict=True):
        for k in range(20):
            r = (p[0] + (q[0] - p[0]) * k / 20, p[1] + (q[1] - p[1]) * k / 20)
            assert _inside(r, board) and _edge_distance(r, board) >= mech.SILK_EDGE - 1e-6, (
                f"IC1's room runs off the board at {r}"
            )


def test_main_antenna_notch_keeps_off_the_chassis_zones():
    x0, x1, y0, y1 = mech.notch_box(MAIN, "antenna_notch")
    for name, (zx0, zx1, zy0, zy1, _h) in mech.keepout_zones(MAIN):
        assert min(x1, zx1) <= max(x0, zx0) or min(y1, zy1) <= max(y0, zy0), f"the antenna notch cuts into {name}"
    # one notch in each rear corner, with rear edge left between them for the power input
    _, _, sy0, sy1 = mech.notch_box(MAIN, "switch_notch")
    assert {MAIN["antenna_notch"]["side"], MAIN["switch_notch"]["side"]} == {"left", "right"}
    assert y1 < sy0 or sy1 < y0, "the antenna and switch notches overlap"


def test_main_antenna_notch_follows_espressifs_keepout_figure():
    """ESP32-C5 Hardware Design Guidelines, Keepout Zone for ESP32-C5 Module's Antenna: at most 2 mm
    from the antenna's ground-point side (the C5-MINI-1's pin-1 end, spec [antenna_notch]) to the
    board's side edge, at least 15 mm of board cut away beyond its open end (the pin-45 end), the
    antenna end at most 1 mm inside the board's edge line, and the cut as deep as the antenna area
    (the footprint's keep-out)."""
    o, u = MAIN["outline"], MAIN["u13"]
    _, x1, y0, y1 = mech.notch_box(MAIN, "antenna_notch")
    area, pads = _u13_footprint()
    corners = [_u13_to_robot(a, b) for a, b in area]
    xs, ys = [c[0] for c in corners], [c[1] for c in corners]
    pad = {name: [_u13_to_robot(a, b) for a, b in pts] for name, pts in pads}
    pin1_y = sum(p[1] for p in pad["1"]) / 4
    pin45_y = sum(p[1] for p in pad["45"]) / 4
    edge = -o["width"] / 2 if pin1_y < pin45_y else o["width"] / 2  # the side edge the pin-1 end faces
    gnd_side, open_side = (min(ys), max(ys)) if edge < 0 else (max(ys), min(ys))
    assert MAIN["antenna_notch"]["side"] == ("right" if edge < 0 else "left")
    assert abs(gnd_side - edge) <= 2.0, "the antenna's ground-point (pin-1) side is more than 2 mm from the edge"
    beyond = (y1 - open_side) if edge < 0 else (open_side - y0)
    assert beyond >= 15.0 - 1e-6, f"{beyond:.2f} mm cut away beyond the open (pin-45) end, under 15 mm"
    assert min(xs) - o["rear"] <= 1.0, "the antenna end is more than 1 mm inside the rear edge"
    assert x1 >= max(xs) - 1e-6, "the notch is shallower than the antenna area"
    assert u["rotation"] == 180


# --- the silkscreen the spec draws: the fan ring and the drive blocks' outlines ------------------


def test_fan_ring_is_around_the_fan_hole_on_the_board():
    r, hole = MAIN["fan_ring"]["diameter"] / 2, MAIN["fan_hole"]["diameter"] / 2
    assert r > hole
    board, c = _main_board(), (MAIN["fan_hole"]["x"], 0.0)
    ring = [(c[0] + r * math.cos(t / 64 * math.tau), r * math.sin(t / 64 * math.tau)) for t in range(64)]
    assert all(_inside(p, board) for p in ring), "the fan ring runs off the board"


def test_spec_silkscreen_draws_the_fan_ring(main_layout):
    """The ring's edge is drawn all round, but where a spec-placed footprint's pad (IC1 straddles the
    ring) or a pad of a part [fan_ring] silk_breaks names would sit under it: every arc on the circle,
    off every such pad by SILK_PAD, and every point of the circle drawn unless it is within 1 mm of
    where a line must stop."""
    arcs = [e for e in mech.main_silk(MAIN, main_layout) if isinstance(e, mech.Arc)]
    c, r = (MAIN["fan_hole"]["x"], 0.0), MAIN["fan_ring"]["diameter"] / 2
    pads = mech.spec_pads(MAIN, main_layout, MAIN["fan_ring"].get("silk_breaks", ()))
    assert arcs
    drawn = []
    for a in arcs:
        for p in (a.a, a.mid, a.b):
            assert math.dist(p, c) == pytest.approx(r, abs=1e-9)
        for p in mech.sample(a, 200):
            assert all(math.dist(p, pc) >= pr + mech.SILK_PAD - 1e-3 for pc, pr in pads), f"ring silk over a pad at {p}"
            drawn.append(p)
    for k in range(720):
        p = (c[0] + r * math.cos(k * math.tau / 720), r * math.sin(k * math.tau / 720))
        if any(math.dist(p, pc) < pr + mech.SILK_PAD + 1.0 for pc, pr in pads):
            continue
        assert min(math.dist(p, q) for q in drawn) < 0.2, f"the ring's edge is not drawn at {p}"


def _on_union_boundary(p, rects, eps=1e-4) -> bool:
    """p lies on the boundary of the rectangles' union: of the four points eps diagonally off it (off
    every zone edge through p), some are inside the union and some outside."""

    def inside(q):
        return any(r[0] < q[0] < r[1] and r[2] < q[1] < r[3] for r in rects)

    round_p = [inside((p[0] + dx * eps, p[1] + dy * eps)) for dx in (-1, 1) for dy in (-1, 1)]
    return any(round_p) and not all(round_p)


@pytest.mark.parametrize("side", ["left", "right"])
def test_drive_block_silk_is_the_union_of_its_zones(side, main_layout):
    """[silkscreen] drive_block_<side>: the outline is the boundary of the union of the named
    [drive_blocks] zones (the motors left out, owner 2026-11-03), each line on it, and every point
    of that boundary drawn but where it meets the board's edge (SILK_EDGE in) or a spec-placed
    footprint's pad (SILK_PAD off)."""
    names = MAIN["silkscreen"][f"drive_block_{side}"]
    assert set(names) <= set(MAIN["drive_blocks"]), "a name that is no [drive_blocks] zone"
    assert not [n for n in names if "motor" in n], "the motors are not drawn"
    rects = [MAIN["drive_blocks"][n] for n in names]
    lines = mech.drive_block_outlines(MAIN, main_layout)[side]
    assert lines
    for ln in lines:
        assert ln.a[0] == pytest.approx(ln.b[0], abs=1e-9) or ln.a[1] == pytest.approx(ln.b[1], abs=1e-9)
        for k in range(11):
            p = (ln.a[0] + (ln.b[0] - ln.a[0]) * k / 10, ln.a[1] + (ln.b[1] - ln.a[1]) * k / 10)
            assert _on_union_boundary(p, rects), f"{side} block silk at {p} is not on its zones' outline"
    # every boundary point clear of the edge and the pads is drawn
    board, pads = _main_board(), mech.spec_pads(MAIN, main_layout)
    missed = []
    for r in rects:
        for a, b in (
            ((r[0], r[2]), (r[1], r[2])),
            ((r[1], r[2]), (r[1], r[3])),
            ((r[1], r[3]), (r[0], r[3])),
            ((r[0], r[3]), (r[0], r[2])),
        ):
            n = max(1, int(math.dist(a, b) / 0.25))
            for k in range(n + 1):
                p = (a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
                if not _on_union_boundary(p, rects) or not _inside(p, board):
                    continue
                if _edge_distance(p, board) < mech.SILK_EDGE + 1.0 or any(
                    math.dist(p, c) < pr + mech.SILK_PAD + 1.0 for c, pr in pads
                ):
                    continue  # near where the line stops (a stub under 1 mm is dropped)
                if not any(mech._seg_distance(p, ln.a, ln.b) < 1e-6 for ln in lines):
                    missed.append(p)
    assert not missed, f"{side} block outline not drawn at {missed[:5]}"


def test_spec_silkscreen_keeps_off_the_spec_pads_and_the_edge(main_layout):
    board, pads = _main_board(), mech.spec_pads(MAIN, main_layout)
    for side, lines in mech.drive_block_outlines(MAIN, main_layout).items():
        for ln in lines:
            for k in range(41):
                p = (ln.a[0] + (ln.b[0] - ln.a[0]) * k / 40, ln.a[1] + (ln.b[1] - ln.a[1]) * k / 40)
                assert _inside(p, board) and _edge_distance(p, board) >= mech.SILK_EDGE - 1e-3, f"{side} at {p}"
                for c, r in pads:
                    assert math.dist(p, c) >= r + mech.SILK_PAD - 1e-3, f"{side} silk at {p} over the pad at {c}"
