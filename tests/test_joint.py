"""The board-to-board joint: the main board's encoder slots against the encoder board's tab.

Slot pad n is soldered to tab pad n (components/micras/EncoderSlot). Each side names its signals
its own way, so both are reduced to the signal's role and compared pad by pad. The pads must also
meet: the tab pads (encoder layout, spec/encoder.toml frame) against the slot pads (EncoderSlot
footprint, as the main board places it).
"""

import shutil

import pytest
from micras_pcb import firmware, layout, sexpr, spec
from micras_pcb.paths import ROOT

from .conftest import needs_kicad
from .design import design
from .test_encoder import TAB_PINOUT

pytestmark = [needs_kicad, pytest.mark.skipif(shutil.which("pcb") is None, reason="pcb not installed")]

# Encoder board net -> role (boards/encoder/encoder.zen).
ENCODER_ROLES = {
    "Encoder_CSn": "CSn",
    "SPI_SCK": "SCK",
    "SPI_MISO": "MISO",
    "SPI_MOSI": "MOSI",
    "3V3": "3V3",
    "GND": "GND",
    "Encoder_ABI_A": "A",
    "Encoder_ABI_B": "B",
}
# Firmware signal or label on the MCU pin -> role.
FIRMWARE_ROLES = {"SPI3_SCK": "SCK", "SPI3_MISO": "MISO", "SPI3_MOSI": "MOSI"}


def _role(d, fw, net: str) -> str:
    if net in ("3V3", "GND"):
        return net
    for pin, f in fw["pins"].items():
        if d.net("IC1", pin) != net:
            continue
        if f["signal"] in FIRMWARE_ROLES:
            return FIRMWARE_ROLES[f["signal"]]
        label = f.get("label", "")
        for suffix, role in (("_CSn", "CSn"), ("_ABI_A", "A"), ("_ABI_B", "B")):
            if label.startswith("Encoder_") and label.endswith(suffix):
                return role
    return f"? ({net})"


@pytest.mark.parametrize("slot", ["EC1", "EC2"])
def test_slot_pinout_is_the_encoder_tab_pinout(slot):
    d = design("main")
    fw = firmware.load("main")
    want = {pad: ENCODER_ROLES[net] for pad, net in TAB_PINOUT.items()}
    got = {pad: _role(d, fw, d.net(slot, pad)) for pad in TAB_PINOUT}
    assert got == want, f"{slot} pads carry {got}, the encoder tab expects {want}"


def test_each_slot_is_one_encoder():
    # CSn, A and B of a slot belong to the same wheel in the firmware (Encoder_<side>_*).
    d = design("main")
    fw = firmware.load("main")
    labels = {d.net("IC1", p): f.get("label", "") for p, f in fw["pins"].items()}
    for slot in ("EC1", "EC2"):
        sides = set()
        for pad in ("1", "7", "8"):
            label = labels.get(d.net(slot, pad), "")
            sides.add(label.split("_")[1] if label.startswith("Encoder_") else "?")
        assert len(sides) == 1, f"{slot}: CSn/A/B belong to {sides}"


# --- the joint's geometry ---------------------------------------------------------------------

SLOT_FOOTPRINT = ROOT / "components/micras/EncoderSlot/EncoderSlot_2x4_P0.95mm.kicad_mod"


def _slot_pads() -> dict[str, tuple[tuple[float, ...], tuple[float, ...]]]:
    """Slot pad n -> (centre, size) in the EncoderSlot footprint: the slot along y, the encoder
    board's chip side towards +x."""
    fp = sexpr.parse(SLOT_FOOTPRINT.read_text())
    return {
        p.atoms()[0]: (tuple(map(float, p.child("at").atoms()[:2])), tuple(map(float, p.child("size").atoms()[:2])))
        for p in fp.children("pad")
    }


def _tab_pads() -> dict[str, tuple[float, float, float, float, str]]:
    """Tab pad n -> (u, v, width along u, length along v, side) in spec/encoder.toml's frame."""
    s = spec.load("encoder")
    c = s["connector"]
    fp = layout.load("encoder").footprints[c["path"].split(".")[0]]
    assert fp.rotation == c["rotation"] == 90  # the footprint's x along v, its y along u
    out = {}
    for p in fp.pads:
        u, v = p.xy[0] - s["kicad"]["origin_x"], s["kicad"]["origin_y"] - p.xy[1]
        out[p.number] = (u, v, p.size[1], p.size[0], "top" if "F.Cu" in p.layers else "bottom")
    return out


def test_tab_pads_face_the_slot_pads():
    # EncoderSlot: seen from the chip side, tab pad 5 (u = +1.425) lands on slot pad 5 at y = -1.425;
    # the chip side (tab pads 5-8) faces +x, the bottom side (pads 1-4) -x.
    slot, tab = _slot_pads(), _tab_pads()
    assert sorted(slot) == sorted(tab) == [str(n) for n in range(1, 9)]
    problems = []
    for n, (u, _, width, _, side) in tab.items():
        (x, y), (_, slot_width) = slot[n]
        if abs(y + u) > 0.01:
            problems.append(f"pad {n}: tab at u = {u:.3f}, slot at y = {y:.3f} (want {-u:.3f})")
        if abs(width - slot_width) > 0.01:
            problems.append(f"pad {n}: tab pad {width} mm wide, slot pad {slot_width} mm")
        if (x > 0) != (side == "top"):
            problems.append(f"pad {n}: tab pad on the {side} side, slot pad at x = {x}")
    assert not problems, "; ".join(problems)


def test_tab_pads_reach_across_the_main_board_surface():
    # The solder fillet joins a slot pad (on the main board's top surface, v = 0) to the tab pad
    # standing in the slot: each tab pad runs from inside the slot to above the shoulder, and stops
    # short of the tab edge by JLCPCB's copper-to-edge minimum (rules/jlcpcb.kicad_dru, 0.2 mm).
    depth = spec.load("encoder")["tab"]["depth"]
    for n, (_, v, _, length, _) in _tab_pads().items():
        low, high = v - length / 2, v + length / 2
        assert low < 0 < high, f"pad {n} spans v = {low:.2f} to {high:.2f}, not across the shoulder line"
        assert low >= -depth + 0.2 - 1e-6, f"pad {n} ends {low + depth:.2f} mm from the tab edge"
