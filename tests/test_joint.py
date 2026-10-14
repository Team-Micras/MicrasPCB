"""The board-to-board joint: the main board's encoder slots against the encoder board's tab.

Slot pad n is soldered to tab pad n (components/micras/EncoderSlot). Each side names its signals
its own way, so both are reduced to the signal's role and compared pad by pad.
"""

import shutil

import pytest
from micras_pcb import firmware

from .conftest import needs_kicad
from .design import design
from .test_encoder import TAB_PINOUT

pytestmark = [needs_kicad, pytest.mark.skipif(shutil.which("pcb") is None, reason="pcb not installed")]

# Encoder board net -> role (boards/encoder/encoder.zen).
ENCODER_ROLES = {
    "SPI_CS": "CSn",
    "SPI_CLK": "SCK",
    "SPI_MISO": "MISO",
    "SPI_MOSI": "MOSI",
    "3V3": "3V3",
    "GND": "GND",
    "ENC_A": "A",
    "ENC_B": "B",
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
