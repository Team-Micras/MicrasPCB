"""The main board against its previous revision: same parts, same nets, except the declared changes."""

import re
import shutil

import pytest
from micras_pcb import jlc, netlist, previous

from .conftest import needs_kicad

# The functional changes (C1, C2), the designator renames the toolchain forces (TP) and the screw
# holes that the previous board had as footprints without a designator (H).
CHANGE_IDS = ["C1", "C2", "TP", "H"]

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


def test_declared_changes_are_c1_c2_the_test_point_renames_and_the_holes(snap, changes):
    assert [c.id for c in changes] == CHANGE_IDS
    c1, c2, tp, holes = changes
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


@needs_kicad
def test_named_nets_keep_their_names(snap, changes, nl):
    expected = previous.apply_changes(previous.from_snapshot(snap), changes)
    actual = {name.lstrip("/"): {(p.ref, p.pin) for p in pins} for name, pins in nl.nets.items()}
    named = [n for n in expected.nets if not AUTO_NAMED.match(n) and not n.startswith("unconnected-")]
    assert len(named) == 54  # every named net of the previous board
    for name in named:
        assert actual.get(name) == set(expected.nets[name]), name


@needs_kicad
def test_vcore_ties_vfbsmps_and_every_vcap_with_their_capacitors(nl):
    vcore = {(p.ref, p.pin) for p in nl.nets["VCORE"]}
    assert {("IC1", n) for n in ("7", "33", "49", "66")} <= vcore
    assert {("C5", "2"), ("C6", "2"), ("C7", "2"), ("C3", "2"), ("C4", "2"), ("L1", "1")} <= vcore


@pytest.mark.skipif(shutil.which("pcb") is None, reason="pcb not installed")
def test_every_part_keeps_its_part_number(snap):
    bom = {m["designator"]: m.get("mpn") for line in jlc.design_bom("main") for m in line["members"]}
    for ref, part in snap["parts"].items():
        if not part["mpn"]:
            continue
        old, new = MPN_RENAMES.get(ref, (part["mpn"], part["mpn"]))
        assert part["mpn"] == old
        assert bom.get(ref) == new, ref
