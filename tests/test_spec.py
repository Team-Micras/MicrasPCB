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
    holes = [(p["x"], p["y"]) for p in mech.placements(main_spec).values()]
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


def test_main_layout_has_every_spec_feature(main_spec, main_layout):
    assert mech.features(main_spec, main_layout) == []
    assert mech.footprint_checks(main_spec, main_layout) == []


def test_main_layout_matches_the_spec(main_spec):
    text = board_pcb("main").read_text()
    new, changes, problems = mech.apply("main", text)
    assert (changes, problems) == ([], [])
    assert new == text


def test_main_mech_export_is_in_the_robot_frame(main_spec):
    m = mech.mech_json("main")
    xs = [p[0] for e in m["edge"] for k in ("start", "end") for p in [e[k]]]
    ys = [p[1] for e in m["edge"] for k in ("start", "end") for p in [e[k]]]
    assert max(xs) == pytest.approx(main_spec["outline"]["front"], abs=1e-3)
    assert min(xs) == pytest.approx(main_spec["outline"]["rear"], abs=1e-3)
    assert max(ys) - min(ys) == pytest.approx(main_spec["outline"]["width"], abs=1e-3)
    assert [h["name"] for h in m["holes"]] == ["H1", "H2", "H3", "H4"]
