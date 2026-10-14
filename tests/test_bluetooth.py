"""The Bluetooth module: against its previous revision, and its joint with the main board's USB-C U2.

The plug USB1 mates the main board's receptacle U2 contact by contact: GND, VBUS, D+ and D- land on
the same function either side up; CC1/CC2 and SBU1/SBU2 swap when the plug is turned over (USB
Type-C R2.0 Table 3-5 p69: the receptacle's A and B rows). Both orientations are checked.
"""

import math
import shutil

import pytest
from micras_pcb import firmware, mech, netlist, previous, sexpr, spec
from micras_pcb.paths import ROOT, board_pcb

from .conftest import needs_kicad
from .design import design, function

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

PLUG, RECEPTACLE, MCU = "USB1", "U2", "IC1"
FLIP = {"CC1": "CC2", "CC2": "CC1", "SBU1": "SBU2", "SBU2": "SBU1"}


@pytest.fixture(scope="module")
def snap():
    return previous.load("bluetooth")


# --- the previous revision ----------------------------------------------------------------------


def test_no_declared_changes():
    assert previous.load_changes("bluetooth") == []


@needs_kicad
def test_connectivity_is_the_previous_board(snap):
    report = previous.diff(previous.from_snapshot(snap), previous.from_netlist(netlist.load("bluetooth")))
    assert report.ok, str(report)


@needs_kicad
def test_named_nets_keep_their_names(snap):
    nl = netlist.load("bluetooth")
    actual = {name.lstrip("/"): {(p.ref, p.pin) for p in pins} for name, pins in nl.nets.items()}
    old = previous.from_snapshot(snap)
    named = [n for n in old.nets if not n.startswith(("Net", "unconnected-"))]
    assert sorted(named) == ["3V3", "GND", "UART_RX", "UART_TX"]
    for name in named:
        assert actual.get(name) == set(old.nets[name]), name


@needs_kicad
@needs_pcb
def test_every_part_keeps_its_part_number(snap):
    d = design("bluetooth")
    for ref, part in snap["parts"].items():
        old, new = MPN_SWAPS.get(ref, (part["mpn"], NEW_MPNS.get(ref, part["mpn"])))
        assert part["mpn"] == old, ref
        assert d.mpn(ref) == new, ref


# --- the joint with the main board --------------------------------------------------------------


def _contacts(d, ref: str) -> dict[str, set[str]]:
    """Contact function -> the nets on it ('D+' -> {'UART_RX'})."""
    out: dict[str, set[str]] = {}
    for name, pins in d.nets().items():
        for p in pins:
            if p.ref == ref:
                out.setdefault(function(p), set()).add(name)
    return out


def _mated(orientation: str) -> list[tuple[str, str, str]]:
    """(contact, module net, main board net) for every contact the plug mates."""
    plug, rec = _contacts(design("bluetooth"), PLUG), _contacts(design("main"), RECEPTACLE)
    out = []
    for contact, nets in plug.items():
        if contact == "SHELL":
            continue
        other = FLIP.get(contact, contact) if orientation == "flipped" else contact
        for a in nets:
            for b in rec[other]:
                out.append((contact, a, b))
    return out


def _mcu_pin(d, net: str) -> tuple[str, str] | None:
    """The MCU pin on the net, directly or through one series resistor: (pin, resistor or '')."""
    for p in d.nets()[net]:
        if p.ref == MCU:
            return function(p), ""
    for r in d.refs_on(net):
        if d.kind(r) != "resistor":
            continue
        other = next(n for n in d.nets_of(r).values() if n != net)
        for p in d.nets()[other]:
            if p.ref == MCU:
                return function(p), r
    return None


@needs_kicad
@needs_pcb
def test_plug_and_receptacle_carry_the_same_contacts():
    plug = set(_contacts(design("bluetooth"), PLUG)) - {"SHELL"}
    rec = set(_contacts(design("main"), RECEPTACLE)) - {"SHIELD"}
    assert plug == rec


@needs_kicad
@needs_pcb
@pytest.mark.parametrize("orientation", ["normal", "flipped"])
def test_uart_crosses_to_the_firmware_uart(orientation):
    # HM-19 UART_TX must reach the MCU pin the firmware uses as UART RX, and UART_RX the TX pin
    # (boards/main/firmware.toml: PA11 UART4_RX, PA12 UART4_TX).
    bt, main, fw = design("bluetooth"), design("main"), firmware.load("main")
    want = {"UART_TX": "_RX", "UART_RX": "_TX"}
    problems = []
    for pin, suffix in want.items():
        module_net = bt.net("U1", pin)
        # the plug-side net is the other end of the module's series resistor
        series = [r for r in bt.refs_on(module_net) if bt.kind(r) == "resistor"]
        assert len(series) == 1, f"U1 {pin}: series resistors {series}"
        plug_net = next(n for n in bt.nets_of(series[0]).values() if n != module_net)
        for contact, a, b in _mated(orientation):
            if a != plug_net:
                continue
            found = _mcu_pin(main, b)
            signal = fw["pins"].get(found[0], {}).get("signal", "") if found else ""
            if not signal.endswith(suffix):
                problems.append(f"U1 {pin} via {series[0]} and {contact} reaches {found} ({signal or 'no signal'})")
    assert not problems, "\n".join(problems)


@needs_kicad
@needs_pcb
@pytest.mark.parametrize("orientation", ["normal", "flipped"])
def test_module_supply_and_ground_mate(orientation):
    # The module's VCC net mates the main board's SBU contacts, fed from 3V3 through the fuse F1 and
    # the switch Q7 (review M6: off while a host powers VBUS); GND mates GND.
    bt, main = design("bluetooth"), design("main")
    vcc = bt.net("U1", "VCC")
    for contact, a, b in _mated(orientation):
        if a == "GND":
            assert b == "GND", f"{contact}: module GND on main board {b}"
        if a == vcc:
            feeds = _sources(main, b)
            assert feeds == {"3V3"}, f"{contact}: module {vcc} on main board {b}, fed from {feeds}"


def _sources(d, net: str) -> set[str]:
    """The board nets that feed a sheet-local net (PERIPHERALS.*) through series parts (a fuse, a
    resistor: not a capacitor) and switches (a transistor's drain on the net, fed from its source),
    followed upstream through the sheet's local nets."""
    out, seen, todo = set(), {net}, [net]
    while todo:
        n = todo.pop()
        if not n.startswith("PERIPHERALS."):
            out.add(n)
            continue
        for ref, _, name in d.on(n):
            if ref == RECEPTACLE or d.kind(ref) == "capacitor":
                continue
            pads = d.nets_of(ref)
            ups = [m for m in pads.values() if m != n] if len(pads) == 2 else []
            if name == "D" and d.net(ref, "S"):
                ups = [d.net(ref, "S")]
            for m in ups:
                if m not in seen:
                    seen.add(m)
                    todo.append(m)
    return out


@needs_kicad
@needs_pcb
def test_uart_rx_is_held_with_the_module_unplugged():
    # With the module unplugged the MCU's UART RX input (PA11) ends at an open contact, and an input
    # without a pull floats, so the receiver collects noise bytes (hw_debug/schematic_review.md m17,
    # review_research/04 section 9: PA11 has no GPIO_PuPd). The firmware's pin map or the board
    # must hold it high (the UART idle level).
    main, fw = design("main"), firmware.load("main")
    problems = []
    for pin, f in sorted(fw["pins"].items()):
        if not f["signal"].startswith("UART") or not f["signal"].endswith("_RX"):
            continue
        net = main.net(MCU, pin)
        pulled = f.get("pull") == "up" or main.two_terminal("resistor", net, "3V3")
        if not pulled:
            problems.append(f"{pin} ({f['signal']}, {net}) has no pull-up in the firmware or on the board")
    assert not problems, "\n".join(problems)


# --- mechanics ----------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def bt_spec():
    return spec.load("bluetooth")


def test_mating_matches_the_main_board_receptacle(bt_spec):
    # spec/bluetooth.toml [mating] copies U2's position from the main board's layout: fail on drift.
    m, main = bt_spec["mating"], spec.load("main")
    root = sexpr.parse(board_pcb("main").read_text())
    (u2,) = [fp for fp in root.children("footprint") if fp.prop("Reference") == RECEPTACLE]
    assert "GT-USB-7010ASV" in u2.atoms()[0]
    at = u2.child("at").atoms()
    assert len(at) == 2 or float(at[2]) == 0, "U2 rotated: the mouth is no longer behind it in -x"
    x, y = mech.kicad_to_robot(main, (float(at[0]), float(at[1])))
    assert (x, y) == pytest.approx((m["receptacle_x"], m["receptacle_y"]), abs=1e-5)
    # the receptacle body (User.15 outline of the footprint) ends at the mouth, mouth_offset behind
    fp = sexpr.parse((ROOT / "components/g-switch/GT-USB-7010ASV/USB-C_G-Switch_GT-USB-7010ASV.kicad_mod").read_text())
    ys = [
        float(n.child(k).atoms()[1])
        for n in fp.children()
        if n.head and n.head.startswith("fp_") and n.child("layer") and n.child("layer").atoms() == ["User.15"]
        for k in ("start", "end")
        if n.child(k)
    ]
    assert max(ys) == pytest.approx(m["mouth_offset"], abs=1e-5)


def test_module_stands_clear_of_the_main_board(bt_spec):
    # The module's component side faces the main board's rear edge at the USB notch; it must stay
    # behind that edge, or the HM-19 and the passives hit the main board.
    origin = mech.mech_json("bluetooth")["robot"]["origin"]
    main = spec.load("main")
    root = sexpr.parse(board_pcb("main").read_text())
    y = bt_spec["mating"]["receptacle_y"]
    edge = min(p[0] for e in mech.outline_elements(main, root) for p in mech.sample(e, 32) if abs(p[1] - y) < 2.0)
    assert origin[0] < edge, f"module face at x = {origin[0]:.3f}, main board edge at {edge:.3f}"


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
