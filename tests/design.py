"""A board as the design tests see it: connectivity from KiCad's netlist, part data from Zener's BOM.

d = design("main")
d.net("IC1", "VBAT")          # net name of a pin (by pin function or pad number)
d.on("3V3")                   # {(ref, pad, function)} on a net
d.mpn("IC7"), d.value("C56", "capacitance")   # 'L6981N33DR', 0.00022
"""

from __future__ import annotations

import functools
from dataclasses import dataclass

from micras_pcb import jlc, netlist


def function(pin: netlist.Pin) -> str:
    """The pin's name: KiCad's netlist writes it as "<name>_<pad>" ("VCC_6")."""
    suffix = "_" + pin.pin
    return pin.function[: -len(suffix)] if pin.function.endswith(suffix) else pin.function


@dataclass
class Design:
    board: str
    nl: netlist.Netlist
    bom: dict[str, dict]

    def mpn(self, ref: str) -> str | None:
        return self.bom.get(ref, {}).get("mpn")

    def refs(self, mpn_prefix: str) -> list[str]:
        return sorted(r for r, m in self.bom.items() if (m.get("mpn") or "").startswith(mpn_prefix))

    def value(self, ref: str, quantity: str, which: str = "nominal") -> float | None:
        q = self.bom.get(ref, {}).get(quantity)
        return float(q[which]) if q else None

    def kind(self, ref: str) -> str:
        return (self.bom.get(ref, {}).get("component_type") or "").lower()

    def nets(self) -> dict[str, list[netlist.Pin]]:
        return {n.lstrip("/"): pins for n, pins in self.nl.nets.items()}

    def net(self, ref: str, pin: str) -> str | None:
        """Net of a pin given by function name (first match) or pad number."""
        for name, pins in self.nets().items():
            if any(p.ref == ref and (function(p) == pin or p.pin == pin) for p in pins):
                return name
        return None

    def pads(self, ref: str, name: str) -> list[str]:
        return sorted({p.pin for pins in self.nl.nets.values() for p in pins if p.ref == ref and function(p) == name})

    def on(self, net: str) -> set[tuple[str, str, str]]:
        return {(p.ref, p.pin, function(p)) for p in self.nets().get(net, [])}

    def refs_on(self, net: str) -> set[str]:
        return {r for r, _, _ in self.on(net)}

    def nets_of(self, ref: str) -> dict[str, str]:
        """pad number -> net."""
        return {p.pin: n for n, pins in self.nets().items() for p in pins if p.ref == ref}

    def two_terminal(self, kind: str, a: str, b: str) -> list[str]:
        """Parts of a kind ('capacitor', 'resistor', ...) with their two pads on nets a and b."""
        out = []
        for ref in self.bom:
            if self.kind(ref) != kind:
                continue
            nets = sorted(set(self.nets_of(ref).values()))
            if sorted({a, b}) == nets:
                out.append(ref)
        return sorted(out)


@functools.cache
def design(board: str) -> Design:
    bom = {m["designator"]: m for line in jlc.design_bom(board) for m in line["members"]}
    return Design(board, netlist.load(board), bom)
