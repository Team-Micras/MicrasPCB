"""The Bluetooth module: against its previous revision, its layout against its spec, its mech export.

The module plugs into the USB-C receptacle U2 of the v1 main board (MicrasPCB e34fb9a, boards/main),
whose tests there check the joint contact by contact in both orientations, the UART pins, the supply
and the CC signature (review M6). The main board in this repository has no USB-C receptacle, so the
joint is not checked here.
"""

import math
import shutil

import pytest
from micras_pcb import mech, netlist, previous, spec
from micras_pcb.paths import board_pcb

from .conftest import needs_kicad
from .design import design

needs_pcb = pytest.mark.skipif(shutil.which("pcb") is None, reason="pcb not installed")

# Parts the board orders under a JLCPCB-basic equivalent (same value, package, rating or better;
# parts/jlc.toml says which), old part number -> new.
MPN_SWAPS = {
    "R1": ("RC0603FR-071KL", "0603WAF1001T5E"),
    "R2": ("RC0603FR-071KL", "0603WAF1001T5E"),
    "R3": ("RC0603FR-07680RL", "0603WAF6800T5E"),
    "C2": ("0603B104K500NT", "CC0603KRX7R9BB104"),
}
# U1 has no part number on the previous revision; OP1 is bare copper.
NEW_MPNS = {"U1": "HM-19"}


@pytest.fixture(scope="module")
def snap():
    return previous.load("bluetooth")


# --- the previous revision ----------------------------------------------------------------------


def test_declared_changes():
    # Each change names its design review item (hw_debug/schematic_review.md).
    changes = previous.load_changes("bluetooth")
    assert [c.id for c in changes] == ["M6", "m17"]


@pytest.fixture(scope="module")
def expected(snap):
    """The previous board's connectivity with boards/bluetooth/changes.toml applied."""
    return previous.apply_changes(previous.from_snapshot(snap), previous.load_changes("bluetooth"))


@needs_kicad
def test_connectivity_is_the_previous_board_with_its_changes(expected):
    report = previous.diff(expected, previous.from_netlist(netlist.load("bluetooth")))
    assert report.ok, str(report)


@needs_kicad
def test_named_nets_keep_their_names(snap, expected):
    nl = netlist.load("bluetooth")
    actual = {name.lstrip("/"): {(p.ref, p.pin) for p in pins} for name, pins in nl.nets.items()}
    old = previous.from_snapshot(snap)
    named = [n for n in old.nets if not n.startswith(("Net", "unconnected-"))]
    assert sorted(named) == ["3V3", "GND", "UART_RX", "UART_TX"]
    for name in [*named, "RESETB"]:
        assert actual.get(name) == set(expected.nets[name]), name


@needs_kicad
@needs_pcb
def test_every_part_keeps_its_part_number(snap):
    d = design("bluetooth")
    for ref, part in snap["parts"].items():
        old, new = MPN_SWAPS.get(ref, (part["mpn"], NEW_MPNS.get(ref, part["mpn"])))
        assert part["mpn"] == old, ref
        assert d.mpn(ref) == new, ref


# --- mechanics ----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def bt_spec():
    return spec.load("bluetooth")


def test_bluetooth_layout_matches_the_spec():
    text = board_pcb("bluetooth").read_text()
    new, changes, problems = mech.apply("bluetooth", text)
    assert (changes, problems) == ([], [])
    assert new == text


def test_bluetooth_mech_export(bt_spec):
    m = mech.mech_json("bluetooth")
    us, vs = [p[0] for p in m["outline"]], [p[1] for p in m["outline"]]
    o = bt_spec["outline"]
    assert (min(us), max(us), min(vs), max(vs)) == pytest.approx(
        (o["left"], o["right"], o["bottom"], o["top"]), abs=1e-3
    )
    assert m["thickness"] == bt_spec["pcb"]["thickness"]
    assert math.isclose(m["robot"]["origin"][2], spec.load("main")["pcb"]["thickness"] + 1.68)
