"""The main2 board's circuit: power tree, analog rail, decoupling and the firmware contract.

main2 is research/next-revision/README.md entered in Zener. These tests read its generated
schematic (the netlist KiCad exports) and Zener's BOM; tests/test_main2_layout.py and the
layout-wide checks of tests/test_layout.py take its layout.
"""

import re
import shutil

import pytest
from micras_pcb import firmware, jlc
from micras_pcb.paths import ROOT

from .conftest import needs_kicad
from .design import design, function
from .test_layout import DECOUPLING, PER_PAD

pytestmark = [needs_kicad, pytest.mark.skipif(shutil.which("pcb") is None, reason="pcb not installed")]

BOARD = "main2"
MCU = "IC1"
# The v1 firmware contract with the main board's pending changes, then main2's own.
FIRMWARE = firmware.load("main")
CHANGES = firmware.load_changes("main") + firmware.load_changes(BOARD)
FW = firmware.apply_changes(FIRMWARE, CHANGES)


@pytest.fixture(scope="module")
def d():
    return design(BOARD)


def _fitted(d, ref: str) -> bool:
    return not d.bom.get(ref, {}).get("dnp")


# --- power tree -----------------------------------------------------------------------------------

# Parts that pass current one way only: MPN prefix -> (from pin, to pin, why). The B5819W is a
# Schottky diode (JCET B5817W-B5819W).
ONE_WAY = {
    "B5819W": ("A", "K", "a Schottky diode blocks cathode to anode (VR 40 V)"),
}
# Regulators: MPN prefix -> (input pin, output pin, reverse path from output to input or None).
REGULATORS = {
    "L6981": ("VIN", "VOUT/FB", "the high-side MOSFET's body diode conducts from SW to VIN (DS13554 Figure 19)"),
    "ADP7142": ("VIN", "VOUT", None),
}
# Parts that conduct DC both ways: inductors, ferrite beads, low-value resistors (links, input RCs).
LINK_OHMS = 100.0


def _edges(d):
    """net -> [(net, how)]: every DC path a supply can take across a part."""
    edges: dict[str, list[tuple[str, str]]] = {}

    def edge(a, b, how):
        if a and b and a != b:
            edges.setdefault(a, []).append((b, how))

    for mpn, (a, k, _) in ONE_WAY.items():
        for ref in d.refs(mpn):
            edge(d.net(ref, a), d.net(ref, k), f"{ref} {a}->{k}")
    for mpn, (pin_in, pin_out, reverse) in REGULATORS.items():
        for ref in d.refs(mpn):
            edge(d.net(ref, pin_in), d.net(ref, pin_out), f"{ref} {pin_in}->{pin_out}")
            if reverse:
                edge(d.net(ref, pin_out), d.net(ref, pin_in), f"{ref} {pin_out}->{pin_in} ({reverse})")
    for ref in d.refs("WSK2512"):  # 4-terminal shunts: the force pads carry the current
        edge(d.net(ref, "I1"), d.net(ref, "I2"), ref)
        edge(d.net(ref, "I2"), d.net(ref, "I1"), ref)
    for ref in d.bom:
        if not _fitted(d, ref):
            continue
        nets = sorted(set(d.nets_of(ref).values()))
        kind = d.kind(ref)
        low = kind == "resistor" and (d.value(ref, "resistance") or 1e9) <= LINK_OHMS
        if len(nets) == 2 and (kind in ("inductor", "ferritebead") or low):
            edge(nets[0], nets[1], ref)
            edge(nets[1], nets[0], ref)
    return edges


def _reach(edges, start):
    path = {start: []}
    todo = [start]
    while todo:
        n = todo.pop()
        for m, how in edges.get(n, []):
            if m not in path:
                path[m] = path[n] + [how]
                todo.append(m)
    return path


def test_vsys_never_back_feeds_the_battery(d):
    # Research Power tree: VBAT reaches VSYS through D14, and nothing on VSYS or the rails it makes
    # reaches VBAT or the pack. 5V_IN, a programmer's 5 V pin on J2 pin 2 and SWD1 pad 4, reaches
    # VSYS through D17 (Regulators.zen); D14 must stop it there, and D17 must keep VSYS (the pack)
    # off the programmer.
    vbat, pack, vsys = d.net("IC8", "VM"), d.net("J1", "1"), d.net("IC7", "VIN")
    v5 = d.net("J2", "2")
    edges = _edges(d)
    problems = []
    for start in (vsys, v5, d.net("SWD1", "4")):
        back = _reach(edges, start)
        problems += [f"{start} reaches {n} through {' -> '.join(back[n])}" for n in (vbat, pack) if n in back]
    if vsys not in _reach(edges, vbat):
        problems.append(f"{vbat} does not reach VSYS")
    if vsys not in _reach(edges, v5):
        problems.append(f"{v5} (J2 pin 2) does not reach VSYS")
    if d.net("SWD1", "4") != v5:
        problems.append(f"SWD1 pad 4 is on {d.net('SWD1', '4')}, not J2 pin 2's {v5}")
    for start in (vbat, vsys):
        if v5 in _reach(edges, start):
            problems.append(
                f"{start} reaches the programmer's 5 V ({v5}) through {' -> '.join(_reach(edges, start)[v5])}"
            )
    assert not problems, "\n".join(problems)


def test_swd_header_follows_the_clone_st_link_order(d):
    # The owner's clone ST-Link lead (main2.zen): pads 1 SWDIO, 2 GND, 3 SWCLK, 4 its 5 V pin. Plugged
    # turned round, or shifted one pad either way, the probe's 5 V pin never lands on GND.
    want = {1: d.net(MCU, "PA13"), 2: "GND", 3: d.net(MCU, "PA14"), 4: "5V_IN"}
    got = {pad: d.net("SWD1", str(pad)) for pad in want}
    assert got == want, f"SWD1 pads {got}, expected {want}"
    probe_5v = 4  # the lead's pins in the same order: 1 SWDIO, 2 GND, 3 SWCLK, 4 5V
    misplugs = {"turned round": 5 - probe_5v, "shifted +1": probe_5v + 1, "shifted -1": probe_5v - 1}
    on_gnd = [how for how, pad in misplugs.items() if got.get(pad) == "GND"]
    assert not on_gnd, f"the probe's 5 V lands on SWD1's GND pad when the lead is {on_gnd}"


def test_no_connector_pin_on_3v3(d):
    # A programmer's supply pin goes to 5V_IN only (behind D17): no connector or header pin sits on
    # a regulated 3.3 V rail, where a programmer's 3.3 V or 5 V would meet the regulators' outputs.
    problems = []
    for rail in (d.net("IC7", "VOUT/FB"), d.net("U8", "VOUT")):
        pins = sorted(f"{r} pin {pad}" for r, pad, _ in d.on(rail) if r.startswith(("J", "SWD")))
        if pins:
            problems.append(f"{rail} is on {pins}")
    assert not problems, "\n".join(problems)


def test_bridges_only_on_vbat(d):
    # Research Design basis: the bridges and the fan driver run straight from the switched pack
    # (VBAT), never from VSYS or a regulated rail; VSYS feeds only the two regulators.
    vbat = d.net("IC8", "VM")
    problems = []
    for ref in d.refs("DRV8874"):
        if d.net(ref, "VM") != vbat:
            problems.append(f"{ref} VM is on {d.net(ref, 'VM')}, not VBAT")
    for ref in d.refs("STSPIN958"):
        if d.net(ref, "VS") != vbat:
            problems.append(f"{ref} VS is on {d.net(ref, 'VS')}, not VBAT")
    vsys = d.net("IC7", "VIN")
    active = sorted({r for r, _, _ in d.on(vsys) if d.kind(r) not in ("capacitor", "resistor")})
    if active != sorted(["IC7", "D14", "D17"]):
        problems.append(f"VSYS carries {active}: only D14, D17 and the 3V3_D buck (the LDO through R58)")
    assert len(d.refs("DRV8874")) == 2 and len(d.refs("STSPIN958")) == 1
    assert not problems, "\n".join(problems)


# Parts allowed on the analog rail and the pins they may use there (research Power tree, 3V3_A
# loads: VDDA, the INA241 VS and REF1, the phototransistor collectors, the emitter-sink op-amp and
# its set-point divider).
ANALOG_LOADS = {
    "INA241": {"VS", "REF1"},
    "TLV9001": {"V+"},
    "ADP7142": {"VOUT", "SENSE/ADJ"},
}


def test_analog_rail_feeds_only_analog_loads(d):
    a = d.net("U8", "VOUT")
    problems = []
    for ref, _pad, fn in sorted(d.on(a)):
        kind = d.kind(ref)
        if kind in ("capacitor", "resistor"):
            continue
        mpn = d.mpn(ref) or ""
        allowed = next((pins for prefix, pins in ANALOG_LOADS.items() if mpn.startswith(prefix)), None)
        if d.nl.parts[ref].value == "WallSensor":
            allowed = {"PT_C"}
        if allowed is None or fn not in allowed:
            problems.append(f"{ref} ({mpn or d.nl.parts[ref].value}) pin {fn} is on the analog rail {a}")
    # VDDA through the 0 Ohm link, and nothing digital behind it
    vdda = d.net(MCU, "VDDA")
    for ref, _pad, fn in sorted(d.on(vdda)):
        if d.kind(ref) not in ("capacitor", "resistor") and not (ref == MCU and fn == "VDDA"):
            problems.append(f"{ref} {fn} is on VDDA")
    assert d.net("U13", "3V3") != a and d.net(MCU, "VDD") != a
    assert not problems, "\n".join(problems)


def test_no_usb_and_no_5v_rail(d):
    # Research Design basis: the board has no USB and no 5 V rail; every supply comes from J1. The
    # one 5 V net is 5V_IN, a programmer's 5 V pin into VSYS through D17, which feeds nothing else.
    usb = sorted(n for n in d.nets() if re.search(r"USB|VBUS|5V", n.upper()) and n != "5V_IN")
    assert not usb, f"USB or 5 V nets on the board: {usb}"
    on_5v = sorted(r for r, _, _ in d.on("5V_IN"))
    assert on_5v == ["D17", "J2", "SWD1"], f"5V_IN reaches {on_5v}: only J2, SWD1 and D17"
    connectors = sorted(r for r in d.nl.parts if r.startswith("J"))
    assert connectors == ["J1", "J2"], f"connectors {connectors}: J1 (the pack) and J2 (the radio's header) only"


# --- decoupling present on the schematic (its distance is test_layout's, once there is a layout) --


def test_listed_decoupling_is_on_the_schematic(d):
    problems = []
    for mpn, names, count, (lo, hi), source in DECOUPLING:
        for ref in d.refs(mpn):
            pads = [p for name in names for p in d.pads(ref, name)]
            if not pads:
                problems.append(f"{ref} has no pin named {'/'.join(names)}")
                continue
            rail = d.net(ref, pads[0])
            caps = [
                c
                for c in d.two_terminal("capacitor", rail, "GND")
                if _fitted(d, c) and lo <= (d.value(c, "capacitance") or 0) <= hi
            ]
            need = len(pads) if count is PER_PAD else count
            if len(caps) < need:
                problems.append(f"{ref} {'/'.join(names)} ({rail}): {len(caps)} of {need} capacitors; {source}")
    assert not problems, "\n".join(problems)


# --- the firmware contract -------------------------------------------------------------------------


def _gpio_nets(d) -> dict[str, str]:
    out = {}
    for name, pins in d.nets().items():
        for p in pins:
            fn = function(p)
            if p.ref == MCU and fn[:1] == "P" and fn[1:2] in "ABCDEH" and len(pins) > 1:
                out[fn] = name
    return out


def test_declared_firmware_changes_are_still_pending():
    stale = firmware.stale_changes(FIRMWARE, firmware.load_changes(BOARD))
    assert not stale, "\n".join(stale)


def test_every_firmware_pin_is_wired(d):
    missing = [p for p in FW["pins"] if p not in _gpio_nets(d)]
    assert not missing, f"the firmware uses {missing}, unconnected on the board"


def test_the_board_uses_no_pin_the_firmware_leaves_unconfigured(d):
    extra = sorted(set(_gpio_nets(d)) - set(FW["pins"]))
    assert not extra, f"wired on the board, not configured by the firmware: {', '.join(extra)}"


def test_net_names_follow_the_firmware_labels(d):
    wired = _gpio_nets(d)
    wrong = [
        f"{pin}: board net {wired.get(pin)!r}, firmware label {f['label']!r}"
        for pin, f in FW["pins"].items()
        if "label" in f and wired.get(pin) != f["label"]
    ]
    assert not wrong, "\n".join(wrong)


def test_battery_divider_matches_the_firmware(d):
    # PC5 reads VBAT through the divider; the firmware's constant must be its ratio.
    tap = d.net(MCU, "PC5")
    vbat = d.net("IC8", "VM")
    up = d.two_terminal("resistor", vbat, tap)
    down = d.two_terminal("resistor", tap, "GND")
    assert len(up) == 1 and len(down) == 1
    ratio = (d.value(up[0], "resistance") + d.value(down[0], "resistance")) / d.value(down[0], "resistance")
    assert FW["battery"]["channel"] == "pin"
    assert abs(FW["battery"]["divider"] / ratio - 1) < 0.01, f"firmware {FW['battery']['divider']}, board {ratio}"


# research/next-revision/calculations/current_sense/ina241_riso_out.txt, section 4: the sampling time
# from which the ADC kickback error stays under 1 mA, per (R_iso, C_f), in every corner of TI's
# INA241A2 model (C_f +-5 %, ADC switch resistance 50-1000 Ohm, 2-10 pF on the pin, VCM 0-16.8 V, the
# model's output impedance and Figure 6-24's). The INA241's output impedance (about 55 Ohm at 1 MHz)
# makes the pin ring, so R_iso x C_f alone does not give it; another pair needs a rerun of
# ina241_riso.py. The table is for 0.2 V/A (INA241A2, 20 V/V, on 10 mOhm).
KICKBACK_SETTLED = {(100.0, 1e-9): 0.87e-6, (150.0, 1e-9): 0.64e-6}
INA241A2_GAIN = 20.0  # SBOSA30D: the A2 gain, V/V


def test_current_sampling_time_settles_the_adc_kickback(d):
    # The wall sensors and the battery share ADC1/ADC2 with the motor currents, so the 4 pF sample
    # capacitor (DS13311 Table 84) arrives charged to another channel's voltage and kicks C_f; the
    # firmware's minimum sampling time must cover the simulated settling of the board's R_iso + C_f.
    t_s = FW["adc"]["current_sampling_time_min_us"] * 1e-6
    problems = []
    for amp in d.refs("INA241"):
        out = d.net(amp, "OUT")
        iso = [r for r in d.bom if d.kind(r) == "resistor" and out in d.nets_of(r).values() and _fitted(d, r)]
        assert len(iso) == 1, f"{amp} OUT: expected one R_iso, found {iso}"
        pin = next(n for n in d.nets_of(iso[0]).values() if n != out)
        caps = [c for c in d.two_terminal("capacitor", pin, "GND") if _fitted(d, c)]
        assert len(caps) == 1, f"{pin}: expected one C_f, found {caps}"
        shunt = next(r for r in d.refs("WSK2512") if d.net(r, "E1") == d.net(amp, "IN+"))
        volts_per_amp = INA241A2_GAIN * d.value(shunt, "resistance")
        assert abs(volts_per_amp - 0.2) < 1e-6, f"{amp}: {volts_per_amp} V/A, the kickback table is for 0.2 V/A"
        r_iso, c_f = d.value(iso[0], "resistance"), d.value(caps[0], "capacitance")
        key = next((k for k in KICKBACK_SETTLED if abs(k[0] - r_iso) < 0.5 and abs(k[1] / c_f - 1) < 0.01), None)
        if key is None:
            problems.append(
                f"{pin} ({iso[0]} {r_iso:g} Ohm, {caps[0]} {c_f * 1e9:g} nF): not simulated (ina241_riso.py)"
            )
        elif t_s < KICKBACK_SETTLED[key]:
            problems.append(
                f"{pin} ({iso[0]} {r_iso:g} Ohm, {caps[0]} {c_f * 1e9:g} nF): {t_s * 1e6:g} us of sampling, the kickback "
                f"settles under 1 mA only from {KICKBACK_SETTLED[key] * 1e6:g} us"
            )
    assert len(d.refs("INA241")) == 2
    assert not problems, "\n".join(problems)


# Firmware rules the hardware does not enforce (behaviour key -> words it must name).
FIRMWARE_RULES = {
    # a debug halt: the timers freeze and the drive enables drop (Drivers.zen, R49 covers reset only)
    "debug_halt": ["TIM1", "TIM8", "TIM12", "Motors_Enable", "Fan_Enable"],
    # the IMU shares SPI_SCK/SPI_MOSI with the encoders and decodes them as I2C while deselected
    "imu_interface": ["I2C_I3C_disable", "IF_CFG"],
    # Wall_Emitter_Set runs beside LED_ARGB and the encoder chip selects (Sensors.zen)
    "emitter_slot_quiet": ["LED_ARGB", "SPI_SCK", "Encoder_Right_CSn", "Encoder_Left_CSn"],
    # the current channels share ADC1/ADC2 with the walls and the battery
    "current_sampling_time": ["adc.current_sampling_time_min_us"],
    # the link needs the C5's 3-wire spi_slave_hd mode (Esp.zen)
    "radio_firmware": ["v6.0.3", "SPI_SLAVE_HD_3WIRE_MODE"],
    # SPI2 keeps its pins driven between transfers, swaps its data pin, starts slow (Esp.zen)
    "link_spi": ["AFCNTR = 1", "MasterKeepIOState", "Init.IOSwap", "/8"],
    # the half-duplex data line is never driven from both ends (R96, RM0468 Figure 643 note 3), the
    # select is released before the MCU drives again (AFCNTR), and the master ends each DMA buffer
    # (ESP-IDF spi_slave_hd protocol)
    "link_protocol": [
        "command and address",
        "dummy",
        "never overlap",
        "releases ESP_CSn before it sets HDDIR = 1",
        "WR_DONE (CMD7)",
        "CMD8",
    ],
    # the C5 recovers the link after the MCU resets, closing buffers with commands, not ESP_CSn
    "link_resync": ["MCU reset", "ESP_CSn", "WR_DONE (CMD7)", "CMD8", "CMD9"],
    # the fan driver's fault comes back on its enable pin, low for about 0.5 ms (R27 x C30 from
    # 0.4 V to VIH(EN), Drivers.zen, DS14341 section 5.7 and Figure 15)
    "fan_fault_interrupt": ["EXTI10", "EXTI15_10", "falling", "0.5 ms", "VIH(EN)"],
    # the C5 drives NRST open drain and must never drive it high (DS13311 Table 61)
    "probe_pins": ["GPIO23", "open-drain", "never push-pull", "set to 1", "350 ns"],
    # GPIO0/GPIO1 carry SWD, not the 32 kHz crystal
    "radio_clock": ["XTAL_32K", "internal RC"],
    # the C5's link clock input and its UART-fallback receiver
    "radio_pulls": ["GPIO10"],
    # INT2 is unconnected: everything goes to INT1 (Sensors.zen)
    "imu_interrupt": ["INT2_on_INT1", "rising"],
    # on 5V_IN alone the bridges have no supply and the battery reads near 0 V (Regulators.zen)
    "battery_absent": ["5V_IN", "Motors_Enable", "Fan_Enable"],
}


def test_firmware_contract_names_the_rules_the_hardware_leaves_open():
    missing = [
        f"behaviour.{key}: missing, or does not name {[w for w in words if w not in FW['behaviour'].get(key, '')]}"
        for key, words in FIRMWARE_RULES.items()
        if any(w not in FW["behaviour"].get(key, "") for w in words)
    ]
    assert not missing, "\n".join(missing)


# --- sourcing: every extended passive is a stated decision ----------------------------------------


def _fitted_lines():
    return [[m for m in line["members"] if not m.get("dnp")] for line in jlc.design_bom(BOARD)]


def test_extended_passives_say_why():
    # JLCPCB charges a loading fee per extended part and order; a resistor or capacitor has a basic
    # part in most values, so an extended one carries why_extended in parts/jlc.toml.
    db = jlc.parts_db()
    missing = sorted(
        {
            f"{m['mpn']} ({', '.join(x['designator'] for x in members)})"
            for members in _fitted_lines()
            if members
            for m in members[:1]
            if m.get("component_type") in ("Resistor", "Capacitor")
            and db.get(m["mpn"], {}).get("type") == "extended"
            and not db[m["mpn"]].get("why_extended")
        }
    )
    assert not missing, "extended passives without why_extended in parts/jlc.toml:\n" + "\n".join(missing)


# Parts whose MPNs differ only by package or vendor do one job: one MPN per board (MPN prefix).
FAMILIES = ["1N4148W"]


def _rating(m: dict) -> tuple:
    """What a passive is to the circuit: its kind, value, package and the ratings that matter."""

    def nominal(q):
        return float(m[q]["nominal"]) if m.get(q) else None

    if m.get("component_type") == "Resistor":
        return ("R", nominal("resistance"), m.get("package"), m["resistance"]["min"], nominal("power"))
    return ("C", nominal("capacitance"), m.get("package"), nominal("voltage"), m.get("dielectric"))


def test_no_duplicate_function_mpns():
    # One MPN per function on the board: two MPNs with the same value, package and ratings, or two
    # members of one part family, are two reels (and possibly two fees) for one job.
    first = [members[0] for members in _fitted_lines() if members]
    problems = []
    seen: dict[tuple, str] = {}
    for m in first:
        if m.get("component_type") not in ("Resistor", "Capacitor"):
            continue
        key = _rating(m)
        if key in seen and seen[key] != m["mpn"]:
            problems.append(f"{seen[key]} and {m['mpn']} are both {key}")
        seen.setdefault(key, m["mpn"])
    for prefix in FAMILIES:
        mpns = sorted({m["mpn"] for m in first if (m.get("mpn") or "").startswith(prefix)})
        if len(mpns) > 1:
            problems.append(f"{prefix} family on the board as {mpns}")
    assert not problems, "\n".join(problems)


# --- documentation names only parts the board has --------------------------------------------------

RESEARCH = ROOT / "research" / "next-revision" / "README.md"
# A designator as the board's prefixes write it, standing alone (not in a path, a link anchor or a
# part number); "H7..." is the MCU family (STM32H7, H725), not a mounting hole.
DESIGNATOR = re.compile(r"(?<![\w./-])(R|C|L|D|Q|U|IC|J|M|SW|F|BZ|W|EC|H|TP|SWD)(\d{1,3})(?![\w])")


def test_research_names_only_parts_on_the_board(d):
    # research/next-revision/README.md describes main2 as built: a designator it names must be a
    # part of the board's netlist, so a removed or renamed part cannot linger in the description.
    absent = {}
    for n, line in enumerate(RESEARCH.read_text().splitlines(), 1):
        for m in DESIGNATOR.finditer(line):
            ref = m.group(0)
            if not ref.startswith("H7") and ref not in d.nl.parts:
                absent.setdefault(ref, []).append(n)
    assert not absent, "\n".join(f"{ref}: line {', '.join(map(str, lines))}" for ref, lines in sorted(absent.items()))
