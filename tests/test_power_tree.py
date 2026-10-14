"""The main board's power tree: one source per supply net, and no source feeding another's input.

Sources are the parts that put a supply on a net: regulators (by MPN), the connectors a supply
arrives on, and ORing parts (ideal diodes, power muxes) that pass a supply on from their inputs.
Each is listed with its datasheet behaviour when its output is held up by something else.
"""

import shutil

import pytest

from .conftest import needs_kicad
from .design import design

pytestmark = [needs_kicad, pytest.mark.skipif(shutil.which("pcb") is None, reason="pcb not installed")]

# MPN prefix -> (input pin, output pin, reverse path from output to input when the output is
# driven from elsewhere: the reason, or None when the part blocks it).
REGULATORS = {
    "L6981": (
        "VIN",
        "VOUT/FB",
        "the high-side MOSFET's body diode conducts from SW to VIN (DS13554 Figure 19; SW abs max VIN + 0.3 V, "
        "Table 3)",
    ),
    "CJA1117B": (
        "IN",
        "OUTPUT",
        "a 1117 conducts from output to input through its internal diode (AMS1117 p4 'Protection Diodes'; the "
        "CJA1117B datasheet is silent)",
    ),
    "TPS61178": ("VIN", "VOUT", None),
}
# Variants that also sink current from their output into their input while regulating, so they
# fight any other source on the output: MPN prefix -> the datasheet's description.
SINKING = {
    "L6981N": "the LNM variant sinks up to 1.75 A into VIN to regulate an output held above its set point "
    "(DS13554 Table 6, section 6.6.2)",
}
# ORing parts: MPN prefix -> (input pins, output pin, why the output cannot drive an input).
ORING = {
    "LM66100": (("VIN",), "VOUT", "an ideal diode with CE on VOUT blocks reverse current (SLVSEZ8A 8.3.2)"),
    "TPS2121": (
        ("IN1", "IN2"),
        "OUT",
        "each channel is a back-to-back FET pair with opposed body diodes (SLVSEA3F Figure 9-2), on only "
        "for the selected valid input: with no input above UVLO OUT is Hi-Z (Table 9-3), an off channel leaks "
        "at most 1 uA at 25 C, 5 uA to 85 C, for |VINx - VOUT| <= 5 V (Table 7.5, ILK), and the selected "
        "channel blocks a back-driven output (section 9.3.6)",
    ),
}
# Connectors a supply arrives on: (designator, pin, what drives it).
OFF_BOARD = [
    ("J1", "1", "the battery"),
    ("U2", "VBUS", "the USB host"),
    ("P1", "1", "the SWD probe (an ST-Link V2 clone drives 3.3 V on this pin)"),
]
# Off-board supply pins that must never be driven from the board.
NOT_DRIVEN = {
    ("U2", "VBUS"): "a USB sink must not drive VBUS (USB Type-C R2.0 section 4.5.2.2.3.1 p170), and a source "
    "only turns VBUS on from vSafe0V (section 4.5.2.2.8.2 p176)",
}


def _oring_check(d, ref, mpn):
    """An ORing part only blocks reverse current when wired for it: the LM66100's CE on VOUT."""
    if mpn == "LM66100":
        return d.net(ref, "3") == d.net(ref, "VOUT")  # pad 3: ~CE
    return True


def _sources(d):
    """net -> [(designator, description, blocks reverse current)] of everything that drives it."""
    out: dict[str, list[tuple[str, str, bool]]] = {}
    for mpn, (_, pin_out, _) in REGULATORS.items():
        for ref in d.refs(mpn):
            out.setdefault(d.net(ref, pin_out), []).append((ref, f"{d.mpn(ref)} output", False))
    for mpn, (pins_in, pin_out, why) in ORING.items():
        for ref in d.refs(mpn):
            ins = ", ".join(sorted({d.net(ref, p) for p in pins_in}))
            blocks = _oring_check(d, ref, mpn)
            what = f"{d.mpn(ref)} from {ins}: " + (why if blocks else "not wired to block reverse current")
            out.setdefault(d.net(ref, pin_out), []).append((ref, what, blocks))
    for ref, pin, what in OFF_BOARD:
        net = d.net(ref, pin)
        if net:
            out.setdefault(net, []).append((ref, what, False))
    return out


def test_each_supply_net_has_one_source():
    # Two regulated sources on one net fight: the higher one back-drives the other, and a
    # synchronous buck in forced PWM (L6981N, DS13554 section 6.6.2) sinks up to 1.75 A from the
    # other source. Parallel sources need ORing (ideal diodes or a power mux) in front of the net:
    # every source but one must block reverse current.
    d = design("main")
    problems = []
    for net, srcs in sorted(_sources(d).items()):
        if len(srcs) < 2:
            continue
        plain = [s for s in srcs if not s[2]]
        if len(plain) > 1:
            problems.append(
                f"{net} is driven by {len(plain)} sources with no ORing: "
                + "; ".join(f"{r} ({w})" for r, w, _ in plain)
            )
        for r, _, _ in plain:
            sink = next((why for prefix, why in SINKING.items() if (d.mpn(r) or "").startswith(prefix)), None)
            if sink:
                problems.append(f"{net}: {r} shares the net with {[s[0] for s in srcs if s[0] != r]}, and {sink}")
    assert not problems, "\n".join(problems)


def test_no_source_back_feeds_another_supply():
    # When another source holds a regulator's output up, current flows back into the regulator's
    # input through the path listed in REGULATORS. Its input net must then carry nothing but its
    # own input capacitors and ORing outputs, or the other source powers every load there: with
    # 3V3 from USB or the probe, a VBAT-fed buck lifts VBAT to about 2.6-2.9 V and starts the
    # boost (hw_debug/schematic_review.md C3, bench test G17); with the battery on, 3V3 reaches
    # the USB VBUS, which a sink must not drive (USB Type-C R2.0 section 4.5.2.2.3.1 p170).
    d = design("main")
    sources = _sources(d)
    oring = {r for mpn in ORING for r in d.refs(mpn)}
    problems = []
    for mpn, (pin_in, pin_out, reverse) in REGULATORS.items():
        if reverse is None:
            continue
        for ref in d.refs(mpn):
            out, inp = d.net(ref, pin_out), d.net(ref, pin_in)
            others = [r for r, _, _ in sources.get(out, []) if r != ref]
            if not others:
                continue
            loads = sorted({p.ref for p in d.nets()[inp] if p.ref != ref and p.type == "power_in"})
            driven = [why for (r, pin), why in NOT_DRIVEN.items() if d.net(r, pin) == inp]
            through = sorted({p.ref for p in d.nets()[inp] if p.ref in oring and p.ref != ref})
            leaky = [r for r in through if not any(s[0] == r and s[2] for s in sources.get(inp, []))]
            what = [f"powers {', '.join(loads)}"] if loads else []
            what += [f"drives the connector's {inp}: {why}" for why in driven]
            what += [f"reaches {r}'s input" for r in leaky]
            if what:
                problems.append(
                    f"{ref}: {', '.join(others)} also drive {out}, and {reverse}; so {inp} " + "; ".join(what)
                )
    assert not problems, "\n".join(problems)


def test_debug_supplies_do_not_reach_the_motor_supplies():
    # The board runs from USB or the SWD probe for debugging with the motors unpowered
    # (hw_debug/schematic_review.md, operating modes b and c). Every path from the USB VBUS and
    # the probe's pin to the battery net must block: through ORing parts only, never into VBAT.
    d = design("main")
    vbat = d.net("J1", "1")
    oring_in = {}
    for mpn, (pins_in, pin_out, _) in ORING.items():
        for ref in d.refs(mpn):
            for p in pins_in:
                oring_in.setdefault(d.net(ref, p), []).append((ref, d.net(ref, pin_out)))
    problems = []
    for ref, pin, what in OFF_BOARD[1:]:
        net = d.net(ref, pin)
        if net == vbat:
            problems.append(f"{ref} {pin} ({what}) is on the battery net {vbat}")
        for part, out in oring_in.get(net, []):
            if out == vbat:
                problems.append(f"{ref} {pin} ({what}) reaches {vbat} through {part}")
    assert not problems, "\n".join(problems)


# Parts that conduct DC both ways between their two pads.
DC_THROUGH = ("inductor", "ferritebead")


def test_debug_supply_back_feed_stops_at_the_mux():
    # In a debug mode a supply reaches nets beyond the one it feeds by every path that conducts
    # current: forwards through ORing parts and regulators, backwards through a regulator's
    # reverse path (REGULATORS) and an ORing part not wired to block, and through inductors and
    # ferrite beads. With the SWD probe alone, 3V3 lifts VSYS through IC7's high-side body diode
    # (DS13554 Figure 19) to about 2.6-2.9 V; U4 has no input above UVLO then and holds OUT Hi-Z
    # (SLVSEA3F Table 9-3), so VSYS must end there. Neither debug supply may reach another
    # off-board supply: the battery net would start the boost (hw_debug/schematic_review.md C3),
    # and a sink must not drive VBUS (NOT_DRIVEN).
    d = design("main")
    edges: dict[str, list[tuple[str, str]]] = {}

    def edge(a, b, how):
        if a and b and a != b:
            edges.setdefault(a, []).append((b, how))

    for mpn, (pin_in, pin_out, reverse) in REGULATORS.items():
        for ref in d.refs(mpn):
            edge(d.net(ref, pin_in), d.net(ref, pin_out), f"{ref} {pin_in}->{pin_out}")
            if reverse:
                edge(d.net(ref, pin_out), d.net(ref, pin_in), f"{ref} {pin_out}->{pin_in} ({reverse})")
    for mpn, (pins_in, pin_out, _) in ORING.items():
        for ref in d.refs(mpn):
            for p in pins_in:
                edge(d.net(ref, p), d.net(ref, pin_out), f"{ref} {p}->{pin_out}")
                if not _oring_check(d, ref, mpn):
                    edge(d.net(ref, pin_out), d.net(ref, p), f"{ref} {pin_out}->{p}, not wired to block")
    for ref in d.bom:
        if d.kind(ref) in DC_THROUGH:
            nets = sorted(set(d.nets_of(ref).values()))
            if len(nets) == 2:
                edge(nets[0], nets[1], ref)
                edge(nets[1], nets[0], ref)
    supplies = {d.net(r, pin): what for r, pin, what in OFF_BOARD}
    problems = []
    for ref, pin, what in OFF_BOARD[1:]:
        start = d.net(ref, pin)
        path = {start: []}
        todo = [start]
        while todo:
            n = todo.pop()
            for m, how in edges.get(n, []):
                if m not in path:
                    path[m] = path[n] + [how]
                    todo.append(m)
        for net, other in supplies.items():
            if net != start and net in path:
                problems.append(f"{what} reaches {net} ({other}) through " + " -> ".join(path[net]))
    assert not problems, "\n".join(problems)
