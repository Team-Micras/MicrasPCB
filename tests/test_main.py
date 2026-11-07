"""The main board against its previous revision: same parts, nets and net names, except the declared changes."""

import re
import shutil

import pytest
from micras_pcb import jlc, netlist, previous

from .conftest import needs_kicad

# The replication's changes: the functional changes (C1, C2), the designator renames the toolchain
# forces (TP) and the screw holes that the previous board had as footprints without a designator
# (H). Then the fixes of the design review's findings, each under its review item.
CHANGE_IDS = ["C1", "C2", "TP", "H"]
FIX_IDS = [
    "M5",
    "C1-battery",
    "C3",
    "m7",
    "C5",
    "C4",
    "m12",
    "M1",
    "M7",
    "M11",
    "M12",
    "M6",
    "M13",
    "m9",
    "M8",
    "M9",
    "m19",
    "M14",
    "m16",
    "m1",
    "m2",
    "M4",
    "m14",
    "m15",
]
# Net renames: the firmware's pin labels (m14) and the motor each current-sense net measures (m15).
NET_RENAMES = {
    "Fan_Overcurrent": "Fan_TOFF",
    "LED_Blue": "LED_Red",
    "Motor_Enable": "Motors_Enable",
    "Current_Sensor_Left": "Current_Sensor_Right",
    "Current_Sensor_Right": "Current_Sensor_Left",
    "Motor_L_Sense+": "Motor_R_Sense+",
    "Motor_R_Sense+": "Motor_L_Sense+",
    "Motor_L_Sense-": "Motor_R_Sense-",
    "Motor_R_Sense-": "Motor_L_Sense-",
}

# Test points: a designator is prefix + number, so the ones without a trailing number gain a 1.
TP_RENAMES = {"FAN_PWM": "FAN_PWM1", "FAN_ENABLE": "FAN_ENABLE1", "FAN_OVERCURRENT": "FAN_OVERCURRENT1", "20V": "20V1"}

# Old part numbers that the board orders under their orderable code.
MPN_RENAMES = {"IC6": ("STSPIN958", "STSPIN958TR")}

AUTO_NAMED = re.compile(r"Net[A-Z]+\d+_\d+$")  # Altium's names for unnamed nets ("NetR25_1")


@pytest.fixture(scope="module")
def snap():
    return previous.load("main")


@pytest.fixture(scope="module")
def changes():
    return previous.load_changes("main")


@pytest.fixture(scope="module")
def nl():
    return netlist.load("main")


def test_declared_changes_are_c1_c2_the_test_point_renames_the_holes_and_the_review_fixes(snap, changes):
    assert [c.id for c in changes] == CHANGE_IDS + FIX_IDS
    assert all(c.review for c in changes[len(CHANGE_IDS) :]), "every fix cites its review item"
    c1, c2, tp, holes = changes[: len(CHANGE_IDS)]
    # C1: VBAT pin to 3V3 (pad 68 is VDD on 3V3), with its two capacitors.
    assert c1.move == {"IC1.1": "IC1.68", "C8.2": "IC1.68", "C9.2": "IC1.68"}
    assert not (c1.merge or c1.isolate or c1.add_parts or c1.remove_parts or c1.rename_parts)
    # C2: VFBSMPS and VCAP1-3 on one net.
    assert c2.merge == [["IC1.7", "IC1.33", "IC1.49", "IC1.66"]]
    assert not (c2.move or c2.isolate or c2.add_parts or c2.remove_parts or c2.rename_parts)
    assert tp.rename_parts == TP_RENAMES
    assert not (tp.move or tp.merge or tp.isolate or tp.add_parts or tp.remove_parts)
    # H: one padless part per unnamed footprint of the previous board, connecting nothing.
    assert holes.add_parts == {f"H{i}": {} for i in range(1, len(snap["unnamed"]) + 1)}
    assert not (holes.move or holes.merge or holes.isolate or holes.remove_parts or holes.rename_parts)


def test_c1_moves_exactly_the_vbat_pin_and_its_capacitors(snap, changes):
    before = previous.from_snapshot(snap).net_of()
    after = previous.apply_changes(previous.from_snapshot(snap), changes).net_of()
    moved = {p for p in before if p in after and before[p] != after[p] and after[p] == "3V3"}
    assert moved == {("IC1", "1"), ("C8", "2"), ("C9", "2")}
    assert all(before[p] == "VBAT" for p in moved)


@needs_kicad
def test_connectivity_is_the_previous_board_plus_the_declared_changes(snap, changes, nl):
    expected = previous.apply_changes(previous.from_snapshot(snap), changes)
    report = previous.diff(expected, previous.from_netlist(nl))
    assert report.ok, str(report)


def test_declared_net_renames(changes):
    renames = {old: new for c in changes for old, new in c.rename_nets.items()}
    assert renames == NET_RENAMES


@needs_kicad
def test_named_nets_keep_their_names(snap, changes, nl):
    expected = previous.apply_changes(previous.from_snapshot(snap), changes)
    actual = {name.lstrip("/"): {(p.ref, p.pin) for p in pins} for name, pins in nl.nets.items()}
    named = [n for n in expected.nets if previous.named(n)]
    old_named = [n for n in previous.from_snapshot(snap).nets if previous.named(n)]
    assert len(old_named) == 54  # every named net of the previous board
    assert {NET_RENAMES.get(n, n) for n in old_named} - set(named) == {"+5V"} - set(named)
    for name in named:
        if len(expected.nets[name]) > 1:
            assert actual.get(name) == set(expected.nets[name]), name


@needs_kicad
def test_vcore_ties_vfbsmps_and_every_vcap_with_their_capacitors(nl):
    vcore = {(p.ref, p.pin) for p in nl.nets["VCORE"]}
    assert {("IC1", n) for n in ("7", "33", "49", "66")} <= vcore
    assert {("C5", "2"), ("C6", "2"), ("C7", "2"), ("C3", "2"), ("C4", "2"), ("L1", "1")} <= vcore


@pytest.mark.skipif(shutil.which("pcb") is None, reason="pcb not installed")
def test_every_part_keeps_its_part_number(snap, changes):
    # The previous board's part numbers, except the ones a declared change replaces (part_numbers)
    # and the parts it leaves unfitted (dnp).
    members = [m for line in jlc.design_bom("main") for m in line["members"]]
    bom = {m["designator"]: m.get("mpn") for m in members}
    assert {m["designator"] for m in members if m.get("dnp")} == previous.dnp_parts(changes)
    declared = previous.part_numbers(snap, changes)
    for ref, part in snap["parts"].items():
        if not part["mpn"] or ref not in declared:
            continue
        old, new = MPN_RENAMES.get(ref, (part["mpn"], declared[ref]))
        assert part["mpn"] == old
        assert bom.get(ref) == new, ref
