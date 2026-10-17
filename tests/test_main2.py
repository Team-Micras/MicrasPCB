"""The main2 board (schematic only): power tree, analog rail, decoupling and the firmware contract.

main2 is research/next-revision/README.md entered in Zener. These tests read its generated
schematic (the netlist KiCad exports) and Zener's BOM; the layout-dependent checks (decoupling
distance, courtyards, DRC) join when the board has a layout.
"""

import shutil

import pytest
from micras_pcb import firmware

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
# Schottky diode (JCET B5817W-B5819W); the AO3401A on the power path conducts VBUS -> VSYS through
# its body diode (drain to source in a P-MOSFET) and through its channel only while its gate is
# below its source, which needs the battery off (Regulators.zen; boards/main2/test/test_power.zen
# battery_wins_over_usb).
ONE_WAY = {
    "B5819W": ("A", "K", "a Schottky diode blocks cathode to anode (VR 40 V)"),
    "AO3401A": ("D", "S", "the body diode blocks source to drain; the channel is off while the pack is on"),
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


def test_vsys_oring_never_back_feeds_the_battery_or_usb(d):
    # Research Power tree: VSYS = OR(VBAT, VBUS), and the battery side and the bridges are never
    # back-fed: nothing on VSYS (or the rails it makes) reaches VBAT, the pack, or the USB VBUS
    # (a sink must not drive VBUS, USB Type-C R2.0 section 4.5.2.2.3.1). Both sources reach VSYS.
    vbat, pack, vbus, vsys = d.net("IC8", "VM"), d.net("J1", "1"), d.net("U2", "VBUS"), d.net("IC7", "VIN")
    edges = _edges(d)
    back = _reach(edges, vsys)
    problems = [f"VSYS reaches {n} through {' -> '.join(back[n])}" for n in (vbat, pack, vbus) if n in back]
    for src in (vbat, vbus):
        if vsys not in _reach(edges, src):
            problems.append(f"{src} does not reach VSYS")
    usb = _reach(edges, vbus)
    problems += [f"USB VBUS reaches {n} through {' -> '.join(usb[n])}" for n in (vbat, pack) if n in usb]
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
    if active != sorted(["IC7", "D14", "Q8"]):
        problems.append(f"VSYS carries {active}: only the power path and the 3V3_D buck (the LDO through R58)")
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


def test_no_5v_rail(d):
    # Research Power tree: no 5 V rail. The USB VBUS (+5V) feeds only the power path Q8, its ESD
    # clamp and the two sense dividers; no other net carries 5 V.
    vbus = d.net("U2", "VBUS")
    active = sorted({r for r, _, _ in d.on(vbus) if d.kind(r) not in ("capacitor", "resistor")})
    assert active == ["D8", "Q8", "U2"], f"{vbus} feeds {active}"
    fives = [n for n in d.nets() if "5V" in n.upper() and n != vbus]
    assert not fives, f"5 V nets besides VBUS: {fives}"


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
    # PA5 reads VBAT through the divider; the firmware's constant must be its ratio.
    tap = d.net(MCU, "PA5")
    vbat = d.net("IC8", "VM")
    up = d.two_terminal("resistor", vbat, tap)
    down = d.two_terminal("resistor", tap, "GND")
    assert len(up) == 1 and len(down) == 1
    ratio = (d.value(up[0], "resistance") + d.value(down[0], "resistance")) / d.value(down[0], "resistance")
    assert FW["battery"]["channel"] == "pin"
    assert abs(FW["battery"]["divider"] / ratio - 1) < 0.01, f"firmware {FW['battery']['divider']}, board {ratio}"
