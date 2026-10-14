"""Board-level checks on the generated encoder design (what pcb test cannot see)."""

import shutil

import pytest
from micras_pcb import jlc, netlist, paths, previous, sexpr

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


def test_declared_changes_are_the_spi_pulls():
    # the board keeps its previous revision's connectivity, plus the pulls the AS5047U asks for on
    # the SPI inputs the MCU releases in reset (DS v1-00 Figure 4 notes 1-3)
    assert [c.id for c in previous.load_changes("encoder")] == ["SPI-PULLS"]


def _expected(snap):
    return previous.apply_changes(previous.from_snapshot(snap), previous.load_changes("encoder"))


@needs_kicad
def test_connectivity_is_the_previous_board_with_its_declared_changes(snap, nl):
    report = previous.diff(_expected(snap), previous.from_netlist(nl))
    assert report.ok, str(report)


@needs_kicad
def test_nets_keep_their_previous_names(snap, nl):
    expected = _expected(snap)
    actual = {name.lstrip("/"): {(p.ref, p.pin) for p in pins} for name, pins in nl.nets.items()}
    named = [n for n in expected.nets if not n.startswith("unconnected-")]
    assert len(named) == 8
    for name in named:
        assert actual.get(name) == set(expected.nets[name]), name


# --- the layout -----------------------------------------------------------------------------------

# The project's minimum silkscreen text: 0.5 mm high, 0.15 mm stroke (the previous boards' pin
# labels, legible on the built boards). encoder.zen sets the height as KiCad's board minimum
# (min_text_height, checked by DRC); Zener does not set KiCad's minimum text thickness, so the
# stroke is checked here.
SILK_TEXT_MIN_HEIGHT_MM = 0.5
SILK_TEXT_MIN_STROKE_MM = 0.15
SILK = {"F.SilkS", "B.SilkS"}


def _silk_texts(root: sexpr.Node):
    """(text, height, stroke) of every visible silkscreen text: board texts, footprint texts and
    footprint fields."""
    nodes = root.children("gr_text")
    for fp in root.children("footprint"):
        nodes += fp.children("fp_text") + fp.children("property")
    for n in nodes:
        layer = n.child("layer")
        if layer is None or layer.atoms()[0] not in SILK:
            continue
        hide = n.child("hide")
        effects = n.child("effects")
        if (hide is not None and hide.atoms() == ["yes"]) or effects is None or effects.child("hide") is not None:
            continue
        text = n.atoms()[-1]
        if not text:
            continue
        font = effects.child("font")
        height = float(font.child("size").atoms()[1])
        stroke = float(font.child("thickness").atoms()[0]) if font.child("thickness") else height / 8
        yield text, height, stroke


def test_silkscreen_text_meets_the_project_minimum():
    root = sexpr.parse(paths.board_pcb("encoder").read_text())
    small = [
        f"{text!r} {h:.3f} mm high, {s:.3f} mm stroke"
        for text, h, s in _silk_texts(root)
        if h < SILK_TEXT_MIN_HEIGHT_MM - 1e-6 or s < SILK_TEXT_MIN_STROKE_MM - 1e-6
    ]
    assert not small, "\n".join(small)


@pytest.mark.skipif(shutil.which("pcb") is None, reason="pcb not installed")
def test_every_part_keeps_its_part_number(snap):
    bom = {m["designator"]: m.get("mpn") for line in jlc.design_bom("encoder") for m in line["members"]}
    for ref, part in snap["parts"].items():
        if not part["mpn"]:
            continue
        old, new = MPN_SWAPS.get(ref, (part["mpn"], part["mpn"]))
        assert part["mpn"] == old
        assert bom.get(ref) == new, ref
