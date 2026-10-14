"""Board-level checks on the generated encoder design (what pcb test cannot see)."""

import shutil

import pytest
from micras_pcb import jlc, netlist, previous

from .conftest import needs_kicad

# The joint with the main board: changing it breaks every main board built for it.
TAB_PINOUT = {
    "1": "Encoder_CSn",
    "2": "SPI_SCK",
    "3": "SPI_MISO",
    "4": "SPI_MOSI",
    "5": "3V3",
    "6": "GND",
    "7": "Encoder_ABI_A",
    "8": "Encoder_ABI_B",
}

# Passives ordered as an equivalent JLCPCB basic part: designator -> (previous MPN, MPN).
# C1: 100 nF 10 % 50 V X7R 0603 both (Fenghua C30926 extended, Yageo C14663 basic).
MPN_SWAPS = {"C1": ("0603B104K500NT", "CC0603KRX7R9BB104")}


@pytest.fixture(scope="module")
def nl():
    return netlist.load("encoder")


@pytest.fixture(scope="module")
def snap():
    return previous.load("encoder")


def _tab_ref(nl):
    return next(r for r, p in nl.parts.items() if p.value == "EncoderTab")


@needs_kicad
def test_tab_pinout_is_the_main_board_contract(nl):
    tab = _tab_ref(nl)
    got = {p.pin: name.lstrip("/") for name, pins in nl.nets.items() for p in pins if p.ref == tab}
    assert got == TAB_PINOUT


@needs_kicad
def test_every_ic_supply_pin_has_a_capacitor_on_its_net(nl):
    for name, pins in nl.nets.items():
        if not any(p.type == "power_in" and p.ref.startswith(("U", "IC")) for p in pins):
            continue
        if name.lstrip("/") == "GND":
            continue
        assert any(p.ref.startswith("C") for p in pins), f"{name}: IC supply without a capacitor"


@needs_kicad
def test_no_single_pin_nets_except_declared_no_connects(nl):
    for name, pins in nl.nets.items():
        if len(pins) == 1:
            assert name.startswith("unconnected-"), f"{name} has one pin and is not a no-connect"


# --- the previous revision (boards/encoder/previous/board.json) ------------------------------


def test_no_declared_changes():
    # the board replicates its previous revision: no connectivity change
    assert previous.load_changes("encoder") == []


@needs_kicad
def test_connectivity_is_the_previous_board(snap, nl):
    report = previous.diff(previous.from_snapshot(snap), previous.from_netlist(nl))
    assert report.ok, str(report)


@needs_kicad
def test_nets_keep_their_previous_names(snap, nl):
    expected = previous.from_snapshot(snap)
    actual = {name.lstrip("/"): {(p.ref, p.pin) for p in pins} for name, pins in nl.nets.items()}
    named = [n for n in expected.nets if not n.startswith("unconnected-")]
    assert len(named) == 8
    for name in named:
        assert actual.get(name) == set(expected.nets[name]), name


@pytest.mark.skipif(shutil.which("pcb") is None, reason="pcb not installed")
def test_every_part_keeps_its_part_number(snap):
    bom = {m["designator"]: m.get("mpn") for line in jlc.design_bom("encoder") for m in line["members"]}
    for ref, part in snap["parts"].items():
        if not part["mpn"]:
            continue
        old, new = MPN_SWAPS.get(ref, (part["mpn"], part["mpn"]))
        assert part["mpn"] == old
        assert bom.get(ref) == new, ref
