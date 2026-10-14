"""The previous-revision snapshot and the connectivity comparator (no hw_debug, KiCad or board needed)."""

import os
import shutil
from pathlib import Path

import pytest
from micras_pcb import previous
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


def test_names_do_not_matter():
    renamed = {f"/{k.lower()}": v for k, v in BASE.items()}
    assert diff(from_snapshot(SNAP), conn(renamed)).ok


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


# --- the committed snapshot of the previous main board ---------------------------------------


@pytest.fixture(scope="module")
def snap():
    return previous.load("main")


def _range(prefix, a, b):
    return {f"{prefix}{i}" for i in range(a, b + 1)}


# the JLCPCB BOM's designators (MicrasMainBoard-BOM-jlc.csv, 144 lines)
BOM = (
    {"BZ1", "C60", "F1", "J1", "P1"}
    | _range("C", 1, 57)
    | _range("D", 1, 7)
    | _range("EC", 1, 2)
    | _range("IC", 1, 7)
    | _range("L", 1, 3)
    | _range("M", 1, 3)
    | _range("Q", 1, 6)
    | _range("R", 1, 42)
    | _range("SW", 1, 5)
    | _range("U", 1, 3)
    | _range("W", 1, 4)
)


def test_snapshot_has_every_footprint(snap):
    assert len(snap["parts"]) + len(snap["unnamed"]) == 154
    assert len(snap["unnamed"]) == 4
    for hole in snap["unnamed"].values():
        assert [(p["type"], p["drill"]) for p in hole["pads"]] == [("np_thru_hole", 2.4)]


def test_every_bom_designator_is_present(snap):
    assert len(BOM) == 144
    assert {r for r, p in snap["parts"].items() if p["in_jlc_bom"]} == BOM
    # PCB-only test points (no symbol, not assembled)
    assert set(snap["parts"]) - BOM == {"20V", "FAN_ENABLE", "FAN_OVERCURRENT", "FAN_PWM", "IMU_INT1", "IMU_INT2"}


def test_board_facts(snap):
    b = snap["board"]
    assert b["copper_layers"] == 4
    assert [la["name"] for la in b["layers"]] == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
    (x0, y0), (x1, y1) = b["edge_cuts_bbox"]["min"], b["edge_cuts_bbox"]["max"]
    assert (x1 - x0, y1 - y0) == pytest.approx((50.0, 90.0), abs=1e-4)


def test_sense_minus_nets_are_separate(snap):
    """The converted schematic merges them (conversion artifact); the PCB keeps them apart."""
    p = snap["parts"]
    assert p["R32"]["pads"]["1"] == "Motor_R_Sense-"
    assert p["R33"]["pads"]["1"] == "Motor_L_Sense-"
    assert frozenset({("R32", "1"), ("R33", "1")}) not in groups(snap)
    assert not any({("R32", "1"), ("R33", "1")} <= g for g in groups(snap))


def test_mcu_supply_pins_as_the_review_describes(snap):
    """DS13311 Table 8 (VFQFPN68): VBAT 1, VLXSMPS 5, VDDSMPS 6, VFBSMPS 7, VCAP 33/49/66, VDD 68."""
    ic1 = snap["parts"]["IC1"]["pads"]
    assert ic1["1"] == "VBAT"  # review C1
    assert ic1["68"] == "3V3"
    vcore = [ic1[n] for n in ("7", "33", "49", "66")]
    assert len(set(vcore)) == 4  # review C2: VCAP1-3 and VFBSMPS on separate nets
    assert {r for r, _ in from_snapshot(snap).nets[ic1["5"]]} == {"IC1", "L1"}


DECLARED = """
[[change]]
id = "C1"
review = "hw_debug/schematic_review.md C1"
summary = "MCU VBAT pin on 3V3 instead of the battery net"
move = { "IC1.1" = "IC1.68" }

[[change]]
id = "C2"
review = "hw_debug/schematic_review.md C2"
summary = "VCAP1-3 and VFBSMPS tied: ST AN5419 Fig. 5 Direct SMPS"
merge = [["IC1.7", "IC1.33", "IC1.49", "IC1.66"]]

[[change]]
id = "M3"
summary = "Battery divider into PA5"
isolate = ["IC1.24"]
add_parts = { R50 = { "1" = "net:VBAT", "2" = "new:VBAT_SENSE" }, R51 = { "1" = "new:VBAT_SENSE", "2" = "net:GND" } }
remove_parts = ["U3"]
rename_parts = { "20V" = "TP1" }
"""


def test_declared_changes_on_the_snapshot(snap):
    exp = apply_changes(from_snapshot(snap), parse_changes(DECLARED))
    net = exp.net_of()
    assert net[("IC1", "1")] == net[("IC1", "68")] == "3V3"
    assert ("IC1", "1") not in exp.nets["VBAT"]
    assert len({net[("IC1", n)] for n in ("7", "33", "49", "66")}) == 1
    assert {("C5", "2"), ("C6", "2"), ("C7", "2"), ("L1", "1")} <= exp.nets[net[("IC1", "7")]]
    assert exp.nets["VBAT_SENSE"] == {("R50", "2"), ("R51", "1")}
    assert "U3" not in exp.parts and "TP1" in exp.parts and "20V" not in exp.parts
    # the C1 move alone shows as one split and one join against the previous board
    rep = diff(
        from_snapshot(snap),
        apply_changes(from_snapshot(snap), parse_changes(DECLARED.split('[[change]]\nid = "C2"')[0])),
    )
    assert [n for n, _ in rep.splits] == ["VBAT"] and [n for n, _ in rep.joins] == ["3V3"]


def test_snapshot_formatting_is_stable(snap):
    assert previous.dumps(snap) == previous.snapshot_path("main").read_text()


SOURCE = Path(os.environ.get("MICRAS_PREVIOUS", previous.default_source()))


@pytest.mark.skipif(not (SOURCE / previous.PCB_FILE).is_file(), reason="previous revision (hw_debug) not available")
def test_snapshot_matches_its_sources():
    assert previous.dumps(previous.build_snapshot(SOURCE.resolve())) == previous.snapshot_path("main").read_text()


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


# --- the committed snapshot of the previous Bluetooth module ---------------------------------


@pytest.fixture(scope="module")
def bt_snap():
    return previous.load("bluetooth")


def test_bluetooth_snapshot_parts(bt_snap):
    assert list(bt_snap["parts"]) == ["C1", "C2", "D1", "OP1", "R1", "R2", "R3", "U1", "USB1"]
    assert bt_snap["unnamed"] == {}
    p = bt_snap["parts"]
    # LCSC-library parts carry "Manufacturer Part" and "Supplier Part", Altium-library ones
    # "Manufacturer_Part_Number"; UTF-8 values come through ("1kΩ")
    assert (p["USB1"]["mpn"], p["USB1"]["lcsc"]) == ("918-118A2021Y40006", "C399938")
    assert (p["R1"]["mpn"], p["R1"]["value"]) == ("RC0603FR-071KL", "1kΩ")
    assert p["U1"]["mpn"] is None and p["OP1"]["side"] == "bottom"


def test_bluetooth_connectivity_as_the_review_describes(bt_snap):
    """hw_debug/review_research/04_sensors_peripherals.md section 9: HM-19 UART_TX (pin 2) through R1
    to both plug D- contacts, UART_RX (pin 4) through R2 to both D+, 3V3 from both SBU contacts,
    VBUS and CC open, PIO1 to the LED through R3, PIO0 to OP1, RESETB open."""
    pads = {(r, n): net for r, part in bt_snap["parts"].items() for n, net in part["pads"].items()}
    conn = from_snapshot(bt_snap)
    assert conn.nets["UART_TX"] == {("R1", "1"), ("USB1", "5"), ("USB1", "13")}
    assert conn.nets["UART_RX"] == {("R2", "1"), ("USB1", "4"), ("USB1", "12")}
    assert pads[("R1", "2")] == pads[("U1", "2")] and pads[("R2", "2")] == pads[("U1", "4")]
    assert {("USB1", "6"), ("USB1", "14"), ("U1", "9"), ("U1", "10")} <= conn.nets["3V3"]
    assert all(pads[("USB1", n)] is None for n in ("2", "3", "7", "10", "11", "15"))
    assert pads[("U1", "15")] == pads[("R3", "1")] and pads[("R3", "2")] == pads[("D1", "2")]
    assert pads[("U1", "16")] == pads[("OP1", "1")] and pads[("OP1", "2")] == pads[("D1", "1")] == "GND"
    assert pads[("U1", "11")] is None


def test_bluetooth_board_facts(bt_snap):
    b = bt_snap["board"]
    assert b["copper_layers"] == 2 and b["thickness"] == 0.79
    (x0, y0), (x1, y1) = b["edge_cuts_bbox"]["min"], b["edge_cuts_bbox"]["max"]
    assert (x1 - x0, y1 - y0) == pytest.approx((16.0, 25.0), abs=1e-4)


def test_bluetooth_snapshot_formatting_is_stable(bt_snap):
    assert previous.dumps(bt_snap) == previous.snapshot_path("bluetooth").read_text()


@pytest.mark.skipif(
    not (SOURCE / previous.SOURCES["bluetooth"].pcb).is_file() or shutil.which("kicad-cli") is None,
    reason="previous revision (hw_debug) or kicad-cli not available",
)
def test_bluetooth_snapshot_matches_its_sources():
    text = previous.dumps(previous.build_snapshot(SOURCE.resolve(), "bluetooth"))
    assert text == previous.snapshot_path("bluetooth").read_text()
