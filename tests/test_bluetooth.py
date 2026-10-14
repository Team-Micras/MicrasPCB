"""The Bluetooth module: against its previous revision, and its joint with the main board's USB-C U2.

The plug USB1 mates the main board's receptacle U2 contact by contact: GND, VBUS, D+ and D- land on
the same function either side up; CC1/CC2 and SBU1/SBU2 swap when the plug is turned over (USB
Type-C R2.0 Table 3-5 p69: the receptacle's A and B rows). Both orientations are checked.

The module identifies itself to the main board with its CC contacts on its D+ contacts (review M6,
boards/bluetooth/bluetooth.zen): the main board's UART TX, idle high, then holds the main board's
CC above any level a USB Type-C source makes across a sink's Rd.
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
            # the data contacts; the CC contacts on D+ are the signature (test_signature_*)
            if a != plug_net or contact not in ("D+", "D-"):
                continue
            found = _mcu_pin(main, b)
            signal = fw["pins"].get(found[0], {}).get("signal", "") if found else ""
            if not signal.endswith(suffix):
                problems.append(f"U1 {pin} via {series[0]} and {contact} reaches {found} ({signal or 'no signal'})")
    assert not problems, "\n".join(problems)


def _supply_path(d, net: str, target: str = "3V3", hops: int = 3) -> list[str] | None:
    """The parts from net to the target supply through series parts: a two-pad part (resistor,
    fuse, ferrite) or a MOSFET's drain and source. None if there is no such path."""
    paths = [(net, [])]
    for _ in range(hops):
        nxt = []
        for n, path in paths:
            for r in sorted(d.refs_on(n) - {RECEPTACLE, *path}):
                pads = {function(p): name for name, pins in d.nets().items() for p in pins if p.ref == r}
                if len(pads) == 2:
                    ends = set(pads.values())
                elif {"D", "S"} <= set(pads):
                    ends = {pads["D"], pads["S"]}
                else:
                    continue
                if n not in ends:
                    continue
                for other in ends - {n}:
                    if other == target:
                        return [*path, r]
                    nxt.append((other, [*path, r]))
        paths = nxt
    return None


@needs_kicad
@needs_pcb
@pytest.mark.parametrize("orientation", ["normal", "flipped"])
def test_module_supply_and_ground_mate(orientation):
    # The module's VCC net mates the main board's SBU contacts, which the main board feeds from
    # 3V3 (through F1, and the switch that the module's signature turns on); GND mates GND.
    bt, main = design("bluetooth"), design("main")
    vcc = bt.net("U1", "VCC")
    for contact, a, b in _mated(orientation):
        if a == "GND":
            assert b == "GND", f"{contact}: module GND on main board {b}"
        if a == vcc:
            path = _supply_path(main, b)
            assert path, f"{contact}: module {vcc} on main board {b}, which no series path feeds from 3V3"


# --- the signature (review M6) ------------------------------------------------------------------

# USB Type-C R2.0 Table 4-36: vRd-Connect max 2.04 V, the highest CC voltage a source makes across a
# +-10 % Rd (Table 4-35: 2.18 V with +-20 %). Table 4-25: Rd = 5.1 kOhm.
VRD_MAX = 2.18
RD = 5.1e3
# STM32H725 DS13311 Table 56: VOH >= VDD - 0.4 V at 8 mA (CMOS port); the main board's 3V3 is the
# L6981C33's 3.27 V minimum (DS13554 Rev 3 p6: VFB 3.27-3.33 V at 25 C).
VOH_MIN = 3.27 - 0.4


@needs_kicad
@needs_pcb
@pytest.mark.parametrize("orientation", ["normal", "flipped"])
def test_signature_reaches_both_main_board_cc_contacts(orientation):
    # The module's CC contacts meet the main board's CC1 and CC2 either side up; each must land on
    # a CC net with its Rd, and the module's side of them must be the net its D+ contact is on.
    bt, main = design("bluetooth"), design("main")
    dp = bt.net(PLUG, "D+")
    cc = {contact: b for contact, a, b in _mated(orientation) if contact in ("CC1", "CC2") and a == dp}
    assert set(cc) == {"CC1", "CC2"}, f"module CC contacts on D+ ({dp}): {sorted(cc)}"
    for contact, b in cc.items():
        rd = main.two_terminal("resistor", b, "GND")
        assert rd, f"{contact}: main board net {b} has no Rd to GND"


@needs_kicad
@needs_pcb
def test_signature_level_is_above_any_source():
    # The main board's UART TX drives its CC contacts through the module (D+ to CC1 and CC2) and
    # whatever series resistance the main board has on D+; with the TX at its minimum high level
    # the CC voltage must still exceed every level a USB Type-C source makes across Rd.
    bt, main, fw = design("bluetooth"), design("main"), firmware.load("main")
    tx = next(pin for pin, f in fw["pins"].items() if f["signal"] == "UART4_TX")
    mcu_net = main.net(MCU, tx)
    # D+ at the receptacle: the MCU net itself or one series resistor away
    rec_dp = main.net(RECEPTACLE, "D+")
    series = 0.0
    if rec_dp != mcu_net:
        rs = [r for r in main.two_terminal("resistor", rec_dp, mcu_net)]
        assert len(rs) == 1, f"U2 D+ ({rec_dp}) reaches {tx} ({mcu_net}) through {rs}"
        series = main.value(rs[0], "resistance")
    rds = [
        main.value(r, "resistance")
        for c in ("CC1", "CC2")
        for r in main.two_terminal("resistor", main.net(RECEPTACLE, c), "GND")
    ]
    assert len(rds) == 2, f"Rd on the main board's CC contacts: {rds}"
    load = 1 / sum(1 / r for r in rds)
    level = VOH_MIN * load / (load + series)
    assert level > VRD_MAX + 0.3, f"signature at {level:.2f} V, a source reaches {VRD_MAX} V"
    assert bt.net(PLUG, "CC1") == bt.net(PLUG, "CC2") == bt.net(PLUG, "D+")


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
