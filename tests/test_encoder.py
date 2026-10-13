"""Board-level checks on the generated encoder design (what pcb test cannot see)."""

import pytest
from micras_pcb import netlist

from .conftest import needs_kicad

# The joint with the main board: changing it breaks every main board built for it.
TAB_PINOUT = {
    "1": "SPI_CS",
    "2": "SPI_CLK",
    "3": "SPI_MISO",
    "4": "SPI_MOSI",
    "5": "3V3",
    "6": "GND",
    "7": "ENC_A",
    "8": "ENC_B",
}


@pytest.fixture(scope="module")
def nl():
    return netlist.load("encoder")


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
        if not any(p.type == "power_in" and p.ref.startswith("U") for p in pins):
            continue
        if name.lstrip("/") == "GND":
            continue
        assert any(p.ref.startswith("C") for p in pins), f"{name}: IC supply without a capacitor"


@needs_kicad
def test_no_single_pin_nets_except_declared_no_connects(nl):
    for name, pins in nl.nets.items():
        if len(pins) == 1:
            assert name.startswith("unconnected-"), f"{name} has one pin and is not a no-connect"
