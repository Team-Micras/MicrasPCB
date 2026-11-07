"""The robot's boards together (micras-pcb assembly): each wall and encoder board placed on the main
board from the specs, its joint's pads on the main board's, and KiCad's export of the assembly where
the placements say, clear of the main board and its parts.

Frames: the robot frame (spec/main.toml) for the main board; a daughterboard's model frame is its
spec frame (u, v) with KiCad's 3D z through its thickness (micras_pcb.assembly).
"""

import math

import pytest
from micras_pcb import assembly, mech, sexpr, spec
from micras_pcb.paths import BUILD, board_pcb

from .conftest import needs_kicad

MAIN, WALL, ENC = spec.load("main"), spec.load("wall"), spec.load("encoder")
WALL_PATHS = sorted(mech.wall_joints(MAIN))
SLOT_PATHS = sorted(mech.slots(MAIN))
TOL = 1e-6


@pytest.fixture(scope="module")
def boards():
    roots = {b: sexpr.parse(board_pcb(b).read_text()) for b in ("main", *assembly.DAUGHTERS)}
    return roots, {b: assembly.stack(r) for b, r in roots.items()}


@pytest.fixture(scope="module")
def models(boards):
    return {m.placement.path: m for m in assembly.models(MAIN, boards[0]["main"], boards[1])}


def test_stackups_are_the_specs_thicknesses(boards):
    for b, st in boards[1].items():
        assert st.total == pytest.approx(spec.load(b)["pcb"]["thickness"], abs=TOL), b


def test_every_joint_carries_its_board(models):
    assert {p: m.placement.board for p, m in models.items()} == {
        **dict.fromkeys(WALL_PATHS, "wall"),
        **dict.fromkeys(SLOT_PATHS, "encoder"),
    }


@pytest.mark.parametrize("path", WALL_PATHS)
def test_wall_board_stands_on_its_joint(models, boards, path):
    """The sensor axes where the exported mechanics put them (build/main/main_mech.json's
    wall_sensors: the front face over the joint, the axes over the main board's top), the front
    facing the look direction, the handle's bottom edge on the header's insulator."""
    st, m = boards[1]["wall"], models[path]
    sensor = {s["name"]: s for s in mech.mech_json("main")["wall_sensors"]}[path.split(".")[1]]
    u = WALL["sensor"]["u"]
    for v, key in (
        (WALL["sensor"]["v"], "receiver_z"),
        (WALL["sensor"]["v"] + WALL["sensor"]["led_above"], "emitter_z"),
    ):
        p = assembly.apply(m.to_robot, (u, v, st.front))
        assert p[:2] == pytest.approx(sensor["front_face"], abs=1e-4), (path, key)
        assert p[2] == pytest.approx(sensor[key], abs=1e-4), (path, key)
    a = math.radians(sensor["look_deg"])
    normal = [m.to_robot[i][2] for i in range(3)]
    assert normal == pytest.approx([math.cos(a), math.sin(a), 0.0], abs=TOL), path
    edge = assembly.apply(m.to_robot, (0.0, WALL["outline"]["bottom"], st.mid))
    assert edge[2] == pytest.approx(MAIN["pcb"]["thickness"] + WALL["header"]["insulator_height"], abs=TOL), path


@pytest.mark.parametrize("path", SLOT_PATHS)
def test_encoder_board_stands_in_its_slot(models, boards, path):
    """The shoulder on the main board's top over the slot, the tab inside the main board's
    thickness, the chip facing out toward its wheel, the board's footprint on the main board (its
    shoulder, both faces) inside its spec/main.toml [encoder_boards] zone."""
    st, m = boards[1]["encoder"], models[path]
    centre = mech.slots(MAIN)[path]
    shoulder = assembly.apply(m.to_robot, (0.0, 0.0, st.mid))
    assert shoulder == pytest.approx((*centre, MAIN["pcb"]["thickness"]), abs=TOL), path
    tab = assembly.apply(m.to_robot, (0.0, -ENC["tab"]["depth"], st.mid))
    assert 0.0 <= tab[2] <= MAIN["pcb"]["thickness"], f"{path}: the tab reaches out of the slot"
    chip = assembly.apply(m.to_robot, (ENC["sensor"]["u"], ENC["sensor"]["v"], st.front))
    assert (chip[1] - centre[1]) * centre[1] > 0, f"{path}: the chip faces the robot's middle, not its wheel"
    side = "left" if path == MAIN["encoder_slots"]["left_path"] else "right"
    x0, x1, y0, y1, _ = MAIN["encoder_boards"][side]
    w = ENC["outline"]["base_width"] / 2
    for u in (-w, w):
        for z in (st.back, st.front):
            p = assembly.apply(m.to_robot, (u, 0.0, z))
            assert x0 <= p[0] <= x1 and y0 <= p[1] <= y1, f"{path}: the board leaves its [encoder_boards] zone"


def test_kicad_model_transforms_reproduce_the_placements(models, boards):
    """The offset and rotation written on each footprint, through KiCad's model transform and the
    footprint's place on the board, put the daughterboard where the placement says."""
    roots, stacks = boards
    for path, m in models.items():
        fp = assembly.by_path(roots["main"], path)
        got = assembly.mul(assembly.footprint_frame(fp, stacks["main"]), assembly.model_matrix(m.rotate, m.offset))
        want = assembly.mul(assembly.robot_to_kicad(MAIN, stacks["main"]), m.to_robot)
        assert [v for row in got for v in row] == pytest.approx([v for row in want for v in row], abs=1e-5), path


def test_attach_adds_one_model_per_joint(models, boards, tmp_path):
    roots = boards[0]
    text = board_pcb("main").read_text()
    added = {m.placement.ref: (tmp_path / f"{m.placement.board}.step", m) for m in models.values()}
    copy = sexpr.parse(assembly.attach(text, roots["main"], added))
    fps = {fp.prop("Reference"): fp for fp in copy.children("footprint")}
    for ref, (step, m) in added.items():
        model = fps[ref].children("model")[-1]
        assert model.atoms() == [str(step)], ref
        assert [float(a) for a in model.child("offset").child("xyz").atoms()] == pytest.approx(m.offset, abs=1e-6)
        assert [float(a) for a in model.child("rotate").child("xyz").atoms()] == pytest.approx(m.rotate, abs=1e-6)
    assert len(copy.children("footprint")) == len(roots["main"].children("footprint"))


@pytest.mark.parametrize("path", WALL_PATHS)
def test_wall_header_pins_meet_the_joint_holes(models, boards, path):
    """Pin n of the wall board's header J1 (its row beside the face its pad is on) over hole n of
    the joint: the pinout the two boards share (tests/test_wall_joint.py ROLES)."""
    assert assembly.mating(MAIN, boards[0], [models[path]], boards[1]) == []


@pytest.mark.parametrize("path", SLOT_PATHS)
def test_encoder_tab_mates_with_its_slot(models, boards, path):
    """Tab pad n of the encoder board, standing chip out as the spec has it, on the side of the slot
    and at the place along it of the slot's pad n (components/micras/EncoderSlot)."""
    assert assembly.mating(MAIN, boards[0], [models[path]], boards[1]) == []


@needs_kicad
def test_export_places_the_boards_as_computed():
    """KiCad's glTF export of the assembly (models only, no copper) holds each daughterboard where
    its placement says, none reaching into the main board outside its joint or into a part's model."""
    found = assembly.build(BUILD / "main" / "assembly-test", full=False)
    assert found["placed"] == []
    assert found["clashes"] == []
