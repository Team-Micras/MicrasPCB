"""The previous-revision snapshot and the connectivity comparator (no hw_debug, KiCad or board needed)."""

import os
import shutil
from pathlib import Path

import pytest
from micras_pcb import netlist, previous
from micras_pcb.previous import ChangeError, Connectivity, apply_changes, diff, from_snapshot, groups, parse_changes

# --- the comparator on a small synthetic board ------------------------------------------------

# U1 (4 pads) with decoupling C1, a divider R1/R2, and U1.4 unconnected.
SNAP = {
    "parts": {
        "U1": {"pads": {"1": "VCC", "2": "GND", "3": "SIG", "4": None}},
        "C1": {"pads": {"1": "VCC", "2": "GND"}},
        "R1": {"pads": {"1": "VCC", "2": "SIG"}},
        "R2": {"pads": {"1": "SIG", "2": "GND"}},
    }
}


def conn(nets: dict[str, list[str]], parts=None) -> Connectivity:
    """A board from {net: ["REF.PAD", ...]}."""
    pads = {k: frozenset(tuple(p.split(".", 1)) for p in v) for k, v in nets.items()}
    refs = parts if parts is not None else {r for g in pads.values() for r, _ in g}
    return Connectivity(set(refs), pads)


def _netlist(nets: dict[str, list[str]]) -> netlist.Netlist:
    nl = netlist.Netlist()
    for name, pads in nets.items():
        nl.nets[name] = [netlist.Pin(*p.split(".", 1), "", "passive") for p in pads]
        for p in pads:
            nl.parts.setdefault(p.split(".")[0], None)
    return nl


BASE = {"VCC": ["U1.1", "C1.1", "R1.1"], "GND": ["U1.2", "C1.2", "R2.2"], "SIG": ["U1.3", "R1.2", "R2.1"]}


def changed(toml: str) -> Connectivity:
    return apply_changes(from_snapshot(SNAP), parse_changes(toml))


def test_snapshot_connectivity():
    c = from_snapshot(SNAP)
    assert c.parts == {"U1", "C1", "R1", "R2"}
    assert c.nets["unconnected-(U1-Pad4)"] == {("U1", "4")}
    assert groups(SNAP) == groups(conn(BASE))


def test_no_change_is_equal():
    rep = diff(apply_changes(from_snapshot(SNAP), []), conn(BASE, {"U1", "C1", "R1", "R2"}))
    assert rep.ok, str(rep)


def test_names_are_compared():
    # the root sheet's "/" is not part of the name; anything else is
    assert diff(from_snapshot(SNAP), previous.from_netlist(_netlist({f"/{k}": v for k, v in BASE.items()}))).ok
    rep = diff(from_snapshot(SNAP), conn({"SUPPLY": BASE["VCC"], "GND": BASE["GND"], "SIG": BASE["SIG"]}))
    assert rep.renamed == [("VCC", "SUPPLY")]
    assert "renamed: net VCC is SUPPLY" in str(rep)


def test_automatic_names_are_not_compared():
    snap = {
        "parts": {
            r: {"pads": {k: ("NetR1_2" if v == "SIG" else v) for k, v in p["pads"].items()}}
            for r, p in SNAP["parts"].items()
        }
    }
    assert diff(from_snapshot(snap), conn(BASE)).ok


def test_rename_nets():
    exp = changed('[[change]]\nid = "X"\nsummary = "s"\nrename_nets = { VCC = "SUPPLY" }')
    assert "VCC" not in exp.nets and exp.nets["SUPPLY"] == {("U1", "1"), ("C1", "1"), ("R1", "1")}
    assert diff(exp, conn({"SUPPLY": BASE["VCC"], "GND": BASE["GND"], "SIG": BASE["SIG"]})).ok


def test_rename_nets_swaps_two_names():
    exp = changed('[[change]]\nid = "X"\nsummary = "s"\nrename_nets = { VCC = "SIG", SIG = "VCC" }')
    assert exp.nets["SIG"] == {("U1", "1"), ("C1", "1"), ("R1", "1")}
    assert exp.nets["VCC"] == {("U1", "3"), ("R1", "2"), ("R2", "1")}


def test_move_to_the_net_of_another_pad():
    exp = changed('[[change]]\nid = "X"\nsummary = "s"\nmove = { "U1.3" = "U1.1" }')
    assert {("U1", "3"), ("U1", "1")} <= exp.nets["VCC"]
    assert ("U1", "3") not in exp.nets["SIG"]
    actual = conn({"VCC": ["U1.1", "C1.1", "R1.1", "U1.3"], "GND": BASE["GND"], "SIG": ["R1.2", "R2.1"]})
    assert diff(exp, actual).ok
    assert not diff(from_snapshot(SNAP), actual).ok


def test_move_to_a_named_and_a_new_net():
    exp = changed(
        '[[change]]\nid = "X"\nsummary = "s"\nmove = { "U1.4" = "net:GND" }\n'
        '[[change]]\nid = "Y"\nsummary = "s"\nmove = { "R1.2" = "new:MID", "R2.1" = "new:MID" }'
    )
    assert ("U1", "4") in exp.nets["GND"]
    assert exp.nets["MID"] == {("R1", "2"), ("R2", "1")}
    assert exp.nets["SIG"] == {("U1", "3")}


def test_merge():
    exp = changed('[[change]]\nid = "C2"\nsummary = "s"\nmerge = [["U1.3", "U1.1", "U1.4"]]')
    assert exp.nets["SIG"] == {
        ("U1", "3"),
        ("R1", "2"),
        ("R2", "1"),
        ("U1", "1"),
        ("C1", "1"),
        ("R1", "1"),
        ("U1", "4"),
    }
    assert "VCC" not in exp.nets


def test_isolate():
    exp = changed('[[change]]\nid = "X"\nsummary = "s"\nisolate = ["U1.3"]')
    assert exp.nets["unconnected-(U1-Pad3)"] == {("U1", "3")}
    assert frozenset({("U1", "3")}) not in groups(exp)


def test_add_remove_and_rename_parts():
    exp = changed(
        '[[change]]\nid = "X"\nsummary = "s"\nremove_parts = ["R2"]\nrename_parts = { R1 = "R9" }\n'
        'add_parts = { C2 = { "1" = "net:VCC", "2" = "U1.2" }, TP1 = { "1" = "U1.4" } }'
    )
    assert exp.parts == {"U1", "C1", "R9", "C2", "TP1"}
    assert exp.nets["SIG"] == {("U1", "3"), ("R9", "2")}
    assert ("C2", "1") in exp.nets["VCC"] and ("C2", "2") in exp.nets["GND"]
    assert exp.nets["unconnected-(U1-Pad4)"] == {("U1", "4"), ("TP1", "1")}


@pytest.mark.parametrize(
    "toml",
    [
        'move = { "U1.9" = "U1.1" }',  # unknown pad
        'move = { "U1.1" = "U7.1" }',  # unknown target pad
        'move = { "U1.1" = "net:VDD" }',  # unknown net
        'move = { "U1.1" = "new:GND" }',  # new: on an existing net
        'merge = [["U1.1", "X1.1"]]',
        'isolate = ["U1"]',  # not REF.PAD
        'remove_parts = ["Q1"]',
        'rename_parts = { R1 = "R2" }',  # target exists
        'add_parts = { R1 = { "1" = "net:GND" } }',  # exists
        'add_parts = { R3 = { "1" = "R9.1" } }',
        'rename_nets = { VDD = "SUPPLY" }',  # unknown net
        'rename_nets = { VCC = "GND" }',  # target exists and is not renamed away
        'rename_nets = { VCC = "X", SIG = "X" }',  # two nets onto one name
    ],
)
def test_bad_references_are_errors(toml):
    with pytest.raises(ChangeError):
        changed(f'[[change]]\nid = "X"\nsummary = "s"\n{toml}')


@pytest.mark.parametrize(
    "toml",
    [
        '[[change]]\nsummary = "s"\nmove = { "U1.1" = "U1.2" }',  # no id
        '[[change]]\nid = "X"\nmove = { "U1.1" = "U1.2" }',  # no summary
        '[[change]]\nid = "X"\nsummary = "s"',  # no action
        '[[change]]\nid = "X"\nsummary = "s"\nmvoe = { "U1.1" = "U1.2" }',  # typo
        '[[change]]\nid = "X"\nsummary = "s"\nmerge = [["U1.1"]]',
        '[[change]]\nid = "X"\nsummary = "s"\nisolate = ["U1.1"]\n[[change]]\nid = "X"\nsummary = "t"\nisolate = ["U1.3"]',
        "change = 1\nother = 2",
    ],
)
def test_malformed_changes_are_errors(toml):
    with pytest.raises(ChangeError):
        parse_changes(toml)


def test_diff_names_split_and_joined_pads():
    # the new board moved U1.3 onto VCC and lost C1
    actual = conn({"VCC": ["U1.1", "R1.1", "U1.3"], "GND": ["U1.2", "R2.2"], "SIG": ["R1.2", "R2.1"]})
    rep = diff(from_snapshot(SNAP), actual)
    assert rep.only_expected == ["C1"] and rep.only_actual == []
    splits = dict(rep.splits)
    assert splits["SIG"] == {"SIG": {("R1", "2"), ("R2", "1")}, "VCC": {("U1", "3")}}
    assert splits["VCC"]["(pad absent on the new board)"] == {("C1", "1")}
    assert dict(rep.joins)["VCC"] == {"SIG": {("U1", "3")}, "VCC": {("U1", "1"), ("R1", "1")}}
    text = str(rep)
    assert "part missing from the new board: C1" in text
    assert "split: expected net SIG" in text and "joined: new net VCC" in text


def test_diff_reports_a_pad_joining_from_unconnected():
    actual = conn({**BASE, "GND": [*BASE["GND"], "U1.4"]})
    rep = diff(from_snapshot(SNAP), actual)
    assert not rep.splits
    assert dict(rep.joins)["GND"]["unconnected-(U1-Pad4) (unconnected)"] == {("U1", "4")}


def test_a_single_pin_net_is_unconnected_whatever_its_name():
    # Zener names a no-connect pin's net (here "U1.NC_4"), and a lone pin may sit on a named net:
    # neither connects anything, so both equal the previous board's netless pad.
    assert diff(from_snapshot(SNAP), conn({**BASE, "U1.NC_4": ["U1.4"]})).ok
    assert diff(from_snapshot(SNAP), conn({**BASE, "SPARE": ["U1.4"]})).ok
    # ... but a previous single-pin net that now joins others is a difference
    rep = diff(from_snapshot(SNAP), conn({**BASE, "SIG": [*BASE["SIG"], "U1.4"]}))
    assert list(dict(rep.joins)) == ["SIG"]


def test_extra_part_is_a_difference_unless_declared():
    actual = conn({**BASE, "GND": [*BASE["GND"], "C9.2"], "VCC": [*BASE["VCC"], "C9.1"]})
    assert diff(from_snapshot(SNAP), actual).only_actual == ["C9"]
    exp = changed('[[change]]\nid = "X"\nsummary = "s"\nadd_parts = { C9 = { "1" = "U1.1", "2" = "U1.2" } }')
    assert diff(exp, actual).ok


SOURCE = Path(os.environ.get("MICRAS_PREVIOUS", previous.default_source()))


# --- the committed snapshot of the previous encoder board ------------------------------------

# Encoder.netlist.txt, the Altium netlist export of the previous encoder board.
ENCODER_NETS = {
    "Encoder_CSn": {("IC1", "1"), ("J1", "1")},
    "SPI_SCK": {("IC1", "2"), ("J1", "2")},
    "SPI_MISO": {("IC1", "3"), ("J1", "3")},
    "SPI_MOSI": {("IC1", "4"), ("J1", "4")},
    "GND": {("C1", "2"), ("IC1", "13"), ("IC1", "5"), ("J1", "6")},
    "Encoder_ABI_B": {("IC1", "6"), ("J1", "8")},
    "Encoder_ABI_A": {("IC1", "7"), ("J1", "7")},
    "3V3": {("C1", "1"), ("IC1", "11"), ("IC1", "12"), ("J1", "5")},
}


@pytest.fixture(scope="module")
def encoder_snap():
    return previous.load("encoder")


def test_encoder_snapshot_parts(encoder_snap):
    assert list(encoder_snap["parts"]) == ["C1", "IC1", "J1"]
    assert encoder_snap["unnamed"] == {}
    p = encoder_snap["parts"]
    assert (p["IC1"]["mpn"], p["IC1"]["manufacturer"]) == ("AS5047U-HTSM", "ams OSRAM")
    assert (p["C1"]["mpn"], p["C1"]["value"]) == ("0603B104K500NT", "100nF")
    assert p["J1"]["mpn"] is None  # the edge tab: copper on the board


def test_encoder_snapshot_nets_are_the_altium_netlist(encoder_snap):
    conn = from_snapshot(encoder_snap)
    assert groups(conn) == {frozenset(v) for v in ENCODER_NETS.values()}
    for name, pads in ENCODER_NETS.items():
        assert conn.nets[name] == pads
    # AS5047U DS v1-00 Figure 4: W/PWM 8, V 9, U 10 and I/PWM 14 left open
    assert [n for n, net in encoder_snap["parts"]["IC1"]["pads"].items() if net is None] == ["8", "9", "10", "14"]


def test_encoder_board_facts(encoder_snap):
    b = encoder_snap["board"]
    assert b["copper_layers"] == 2 and b["thickness"] == 0.79
    (x0, y0), (x1, y1) = b["edge_cuts_bbox"]["min"], b["edge_cuts_bbox"]["max"]
    assert (x1 - x0, y1 - y0) == pytest.approx((9.6, 14.1), abs=1e-4)


def test_encoder_snapshot_formatting_is_stable(encoder_snap):
    assert previous.dumps(encoder_snap) == previous.snapshot_path("encoder").read_text()


@pytest.mark.skipif(
    not (SOURCE / previous.SOURCES["encoder"].pcb).is_file() or shutil.which("kicad-cli") is None,
    reason="previous revision (hw_debug) or kicad-cli not available",
)
def test_encoder_snapshot_matches_its_sources():
    text = previous.dumps(previous.build_snapshot(SOURCE.resolve(), "encoder"))
    assert text == previous.snapshot_path("encoder").read_text()
