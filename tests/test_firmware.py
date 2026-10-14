"""The main board against the firmware's view of it (boards/main/firmware.toml, from MicrasFirmware).

The firmware names every MCU pin it uses, the supply configuration it selects, how it reads the
battery and how hard it drives the loads whose ratings depend on it. A board that disagrees runs
the firmware into the wrong part, or burns a part the firmware drives as designed.
"""

import os
import shutil
from pathlib import Path

import pytest
from micras_pcb import firmware

from .conftest import needs_kicad
from .design import design, function

pytestmark = [needs_kicad, pytest.mark.skipif(shutil.which("pcb") is None, reason="pcb not installed")]

MCU = "IC1"
FW = firmware.load("main")
SOURCE = Path(os.environ.get("MICRAS_FIRMWARE", firmware.default_source()))


@pytest.mark.skipif(not (SOURCE / firmware.IOC).is_file(), reason="MicrasFirmware checkout not available")
def test_contract_matches_the_firmware():
    assert firmware.dumps(firmware.build(SOURCE.resolve())) == firmware.contract_path("main").read_text()


@pytest.fixture(scope="module")
def d():
    return design("main")


def _pin(label: str) -> str:
    return next(p for p, f in FW["pins"].items() if f.get("label") == label or f["signal"] == label)


def _net(d, label: str) -> str:
    return d.net(MCU, _pin(label))


def _reach(d, net: str) -> set[str]:
    """The net and the nets one series resistor away from it."""
    out = {net}
    for r in d.refs_on(net):
        if d.kind(r) == "resistor":
            out |= set(d.nets_of(r).values())
    return out


def _gpio_nets(d) -> dict[str, str]:
    """MCU GPIO pin name -> net, for pins wired to something."""
    out = {}
    for name, pins in d.nets().items():
        for p in pins:
            fn = function(p)
            if p.ref == MCU and fn[:1] == "P" and fn[1:2] in "ABCDEH" and len(pins) > 1:
                out[fn] = name
    return out


@pytest.fixture(scope="module")
def wired(d):
    return _gpio_nets(d)


def test_every_firmware_pin_is_wired(wired):
    # A pin the firmware configures but the board leaves open is a function that cannot work.
    missing = [p for p in FW["pins"] if p not in wired]
    assert not missing, f"the firmware uses {missing}, unconnected on the board"


def test_the_board_uses_no_pin_the_firmware_leaves_unconfigured(wired):
    # An MCU pin wired on the board but absent from the firmware stays in analog mode (RM0468
    # section 11.3.1): whatever it was meant to drive or read does nothing.
    extra = sorted(set(wired) - set(FW["pins"]))
    assert not extra, f"wired on the board, not configured by the firmware: {', '.join(extra)}"


def test_net_names_follow_the_firmware_labels(wired):
    # The board's net names are the firmware's pin labels (boards/main/layout/README.md), so a
    # reader can follow a signal from the code to the copper.
    wrong = [
        f"{pin}: board net {wired.get(pin)!r}, firmware label {f['label']!r}"
        for pin, f in FW["pins"].items()
        if "label" in f and wired.get(pin) != f["label"]
    ]
    assert not wrong, "\n".join(wrong)


def test_firmware_signals_reach_their_parts(d):
    """Each firmware function lands on the part pin that performs it."""
    problems = []

    def expect(label, ref, pin, why):
        target = d.net(ref, pin)
        if target not in _reach(d, _net(d, label)):
            problems.append(f"{label} ({_pin(label)}) does not reach {ref} {pin}: {why}")

    for side in ("Left", "Right"):
        # one bridge per motor: its inputs on the motor's two PWM channels
        fw, bw = _net(d, f"Motor_{side}_PWM_FW"), _net(d, f"Motor_{side}_PWM_BW")
        bridge = next((b for b in "AB" if d.net("IC5", f"IN1{b}") == fw), None)
        if bridge is None or d.net("IC5", f"IN2{bridge}") != bw:
            problems.append(f"Motor_{side}_PWM_FW/BW do not drive IN1/IN2 of one L6205 bridge")
            continue
        # the firmware reads that motor's current on Current_Sensor_<side>: the amplifier whose
        # output is on that pin must sense the shunt in series with this bridge's output
        amp = next(r for r in d.refs("TSC2020") if d.net(r, "OUT") == _net(d, f"Current_Sensor_{side}"))
        sensed = {d.net(amp, "IN+"), d.net(amp, "IN-")}
        outputs = {d.net("IC5", f"OUT1{bridge}"), d.net("IC5", f"OUT2{bridge}")}
        if not sensed & outputs:
            problems.append(
                f"Current_Sensor_{side} ({_pin(f'Current_Sensor_{side}')}) reads {amp}, which senses {sorted(sensed)}, "
                f"not the {side.lower()} motor's bridge {bridge} ({sorted(outputs)})"
            )
        # the encoder of the same wheel: CSn and A/B on one slot
        cs, a = _net(d, f"Encoder_{side}_CSn"), _net(d, f"Encoder_{side}_ABI_A")
        slot = [r for r in d.refs_on(cs) if r.startswith("EC")]
        if not slot or d.net(slot[0], "7") != a or d.net(slot[0], "8") != _net(d, f"Encoder_{side}_ABI_B"):
            problems.append(f"Encoder_{side}_CSn and Encoder_{side}_ABI_A/B are not on one encoder slot")
    expect("Motors_Enable", "IC5", "ENA", "the firmware enables the bridges on this pin")
    for n in range(4):
        # emitter n's switch and receiver n in the same wall sensor
        gate_nets = _reach(d, _net(d, f"Wall_Sensor_PWM_{n}"))
        fet = [r for r in d.refs("AO3400A") if d.net(r, "G") in gate_nets]
        sensor = [w for w in d.refs_on(d.net(fet[0], "D")) if w.startswith("W")] if fet else []
        if not sensor or d.net(sensor[0], "PT_E") != _net(d, f"Wall_Sensor_{n}"):
            problems.append(f"Wall_Sensor_PWM_{n} and Wall_Sensor_{n} are not the emitter and receiver of one sensor")
    expect("Fan_PWM", "IC6", "PWM1", "the fan speed PWM")
    expect("Fan_Enable", "IC6", "EN/~{FAULT}", "the fan enable / fault line")
    expect("Fan_TOFF", "IC6", "TOFF", "the current-limiter flag")
    expect("IMU_SPI_CSn", "IC2", "CS", "the IMU chip select")
    expect("IMU_INT1", "IC2", "INT1", "")
    expect("IMU_INT2", "IC2", "INT2", "")
    expect("SPI3_SCK", "IC2", "SCL", "SPI3 is the IMU and encoder bus")
    expect("SPI3_MOSI", "IC2", "SDA", "")
    expect("SPI3_MISO", "IC2", "SDO/SA0", "")
    expect("LED_ARGB", "D1", "DI", "the first addressable LED's data input")
    # UART4 to the Bluetooth module on the USB-C receptacle: the module receives on D+ and
    # transmits on D- (MicrasBluetoothModule netlist, hw_debug/review_research/04 section 9)
    expect("UART4_TX", "U2", "D+", "the Bluetooth module's RX")
    expect("UART4_RX", "U2", "D-", "the Bluetooth module's TX")
    expect("DEBUG_JTMS-SWDIO", "P1", "3", "the SWD header")
    expect("DEBUG_JTCK-SWCLK", "P1", "4", "the SWD header")
    assert not problems, "\n".join(problems)


def test_supply_configuration_matches_the_wiring(d):
    # The firmware selects its supply with PWR_CR3 once per power-on (RM0468 section 6.8.4); a
    # selection the board does not wire cuts the core supply (AN5419 Figure 5, Direct SMPS:
    # VFBSMPS and every VCAP on one node).
    assert FW["supply"]["source"] == "PWR_DIRECT_SMPS_SUPPLY", "only the Direct SMPS wiring is described here"
    core = {d.net(MCU, p) for p in ("VFBSMPS", "VCAP1", "VCAP2", "VCAP3")}
    assert len(core) == 1, f"the firmware selects Direct SMPS, but VFBSMPS/VCAP are on {sorted(core)}"


# ADC inputs of the free and analog pins (DS13311 Rev 5 Table 8, VFQFPN68).
ADC_PINS = {"PA4", "PA5", "PA6", "PC4", "PB1", "PC0", "PC1"}


def test_battery_voltage_is_measurable(d):
    # The firmware reports the battery voltage (proxy::Battery). The pack must reach an ADC pin
    # through a divider that keeps the pin within VDDA (3.3 V) at the full 12.6 V pack. The VBAT
    # pin is on 3V3 (AN5419 Table 2; absolute maximum 4.0 V, DS13311 Table 10), so the internal
    # VBAT/4 channel the firmware reads (firmware.toml [battery]) no longer sees the pack.
    vbat = d.net("J1", "1")
    found = []
    for r in d.refs_on(vbat):
        if d.kind(r) != "resistor":
            continue
        tap = next(n for n in d.nets_of(r).values() if n != vbat)
        pins = [function(p) for p in d.nets()[tap] if p.ref == MCU]
        down = d.two_terminal("resistor", tap, "GND")
        if pins and pins[0] in ADC_PINS and down:
            rt, rb = d.value(r, "resistance"), d.value(down[0], "resistance")
            found.append((pins[0], 12.6 * rb / (rt + rb)))
    assert found, (
        f"the battery ({vbat}) reaches no ADC pin through a divider; the firmware reads it on the "
        f"{FW['battery']['channel']} channel / {FW['battery']['divider']:g}, and IC1 VBAT is on {d.net(MCU, 'VBAT')}"
    )
    assert all(v <= 3.3 for _, v in found), f"divided battery voltage above VDDA: {found}"


# SFH 4550 Version 1.9 (2022-08-09): VF 1.5 V typ at 100 mA (p5), IF 100 mA DC max (p4).
SFH4550_VF = 1.5
SFH4550_IF_DC = 0.100
# FUET-5030 specification p2: coil 12 +- 3 Ohm; the inductance is not given, so the DC case bounds
# the current at low tones.
BUZZER_COIL_MIN = 9.0


def _emitters(d):
    """(sensor, series resistor, LED current at VF typ) per wall sensor."""
    out = []
    for w in sorted(r for r, p in d.nl.parts.items() if p.value == "WallSensor"):
        anode = d.net(w, "LED_A")
        rs = [r for r in d.refs_on(anode) if d.kind(r) == "resistor"]
        ohms = d.value(rs[0], "resistance")
        out.append((w, rs[0], (3.3 - SFH4550_VF) / ohms))
    assert len(out) == 4, f"expected the four wall sensors, found {[w for w, _, _ in out]}"
    return out


def test_wall_emitter_resistors_at_the_firmware_duty(d):
    # Average dissipation of each emitter resistor at the firmware's duty (firmware.toml [drive],
    # from target.hpp emitter_duty_cycle) against its rating; LED current from VF typ.
    duty = FW["drive"]["wall_emitter"]
    over = []
    for w, r, i in _emitters(d):
        p = i * i * d.value(r, "resistance") * duty
        if p > d.value(r, "power"):
            over.append(
                f"{r} ({w}): {i * 1e3:.0f} mA at {duty:.1%} duty is {p * 1e3:.0f} mW, rated {d.value(r, 'power') * 1e3:.0f} mW"
            )
    assert not over, "\n".join(over)


def test_wall_emitters_survive_a_gate_held_high(d):
    # A timer output left high (firmware fault, a reset of the timer with its compare at full
    # scale) keeps the emitter on. Unless the gate is AC-coupled, the LED then carries DC, which
    # must stay within the SFH 4550's 100 mA DC rating (p4).
    over = []
    for w, r, i in _emitters(d):
        fet = [q for q in d.refs("AO3400A") if d.net(q, "D") == d.net(w, "LED_K")]
        # DC-coupled: the gate reaches the MCU pin through resistors only (no series capacitor)
        dc_coupled = bool(_reach(d, d.net(fet[0], "G")) & set(_gpio_nets(d).values()))
        if dc_coupled and i > SFH4550_IF_DC:
            over.append(f"{w}: {i * 1e3:.0f} mA DC through {r} with {fet[0]}'s gate held high, above 100 mA")
    assert not over, "\n".join(over)


def test_buzzer_resistor_at_the_firmware_duty(d):
    # The firmware drives the buzzer at 50 % duty at any tone (firmware.toml [drive], micras-lib
    # Buzzer::play). At low tones the coil current approaches 3.3 V / (coil + R).
    duty = FW["drive"]["buzzer"]
    coil = d.net("BZ1", "-")
    rs = [r for r in d.refs_on(coil) if d.kind(r) == "resistor"]
    assert rs, "no series resistor on the buzzer coil"
    r = rs[0]
    ohms = d.value(r, "resistance")
    i = 3.3 / (BUZZER_COIL_MIN + ohms)
    p = i * i * ohms * duty
    assert p <= d.value(r, "power"), (
        f"{r}: {i * 1e3:.0f} mA through a {BUZZER_COIL_MIN:g} Ohm coil at {duty:.0%} duty dissipates {p * 1e3:.0f} mW, "
        f"rated {d.value(r, 'power') * 1e3:.0f} mW"
    )
