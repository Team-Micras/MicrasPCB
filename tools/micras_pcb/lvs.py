"""Layout versus schematic: the generated schematic and the PCB must connect the same pads.

Both come from the Zener netlist, but through different writers, and they name nets differently
(KiCad prefixes schematic-local nets with "/", and the two name unconnected pins their own way).
So this compares connectivity, not names: each net becomes the set of (ref, pad) it joins, and
the two sides must produce the same sets. KiCad's --schematic-parity compares names, which
only reports that naming difference.
"""

from __future__ import annotations

from . import netlist, sexpr
from .paths import board_pcb


def schematic_groups(board: str) -> set[frozenset]:
    nl = netlist.load(board)
    return {frozenset((p.ref, p.pin) for p in pins) for pins in nl.nets.values()}


def pcb_groups(board: str) -> set[frozenset]:
    root = sexpr.parse(board_pcb(board).read_text())
    nets: dict[str, set] = {}
    for fp in root.children("footprint"):
        ref = fp.prop("Reference")
        for pad in fp.children("pad"):
            num = pad.atoms()[0]
            net = pad.child("net")
            if num == "" or net is None:
                continue
            nets.setdefault(net.atoms()[-1], set()).add((ref, num))
    return {frozenset(v) for v in nets.values()}


def run(board: str) -> int:
    sch, pcb = schematic_groups(board), pcb_groups(board)
    # a single-pad net is an unconnected pin on either side, whatever it is called
    sch_multi = {g for g in sch if len(g) > 1}
    pcb_multi = {g for g in pcb if len(g) > 1}
    only_sch, only_pcb = sch_multi - pcb_multi, pcb_multi - sch_multi
    sch_pads = set().union(*sch) if sch else set()
    pcb_pads = set().union(*pcb) if pcb else set()
    missing = sorted(sch_pads - pcb_pads)
    for g in sorted(only_sch, key=sorted):
        print(f"  schematic only: {sorted(g)}")
    for g in sorted(only_pcb, key=sorted):
        print(f"  PCB only:       {sorted(g)}")
    for p in missing:
        print(f"  pad missing from the PCB: {p}")
    bad = bool(only_sch or only_pcb or missing)
    summary = "FAILED" if bad else f"clean ({len(sch_multi)} nets)"
    print(f"{board}: LVS {summary}")
    return 1 if bad else 0
