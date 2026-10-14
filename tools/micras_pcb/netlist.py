"""Read the netlist KiCad exports from a generated schematic (kicad-cli sch export netlist)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import sexpr
from .paths import board_sch, build_dir
from .tools import kicad_cli


@dataclass
class Part:
    ref: str
    value: str
    footprint: str
    fields: dict[str, str]
    in_bom: bool = True
    dnp: bool = False

    def get(self, name: str) -> str | None:
        """Field lookup ignoring case (pcb title-cases property names: 'LCSC Part #' -> 'Lcsc Part #')."""
        low = {k.lower(): v for k, v in self.fields.items()}
        return low.get(name.lower())


@dataclass
class Pin:
    ref: str
    pin: str
    function: str
    type: str


@dataclass
class Netlist:
    parts: dict[str, Part] = field(default_factory=dict)
    nets: dict[str, list[Pin]] = field(default_factory=dict)

    def net_of(self, ref: str, pin: str) -> str | None:
        for name, pins in self.nets.items():
            if any(p.ref == ref and p.pin == pin for p in pins):
                return name
        return None

    def pins_of(self, ref: str) -> dict[str, str]:
        """pin function (name) -> net, for one part."""
        return {p.function or p.pin: name for name, pins in self.nets.items() for p in pins if p.ref == ref}


def export(board: str) -> Path:
    out = build_dir(board) / f"{board}.net"
    subprocess.run(
        [kicad_cli(), "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(out), str(board_sch(board))],
        check=True,
        capture_output=True,
    )
    return out


def design_net_name(kicad_name: str) -> str:
    """The design's name of a KiCad net. KiCad prefixes a net named by a sheet-local label with
    its sheet path ("/" on the root sheet, "/REGULATORS/" on a module sheet) and writes a "/"
    inside a name as {slash}, so the name is what follows the last "/"."""
    return kicad_name.rsplit("/", 1)[-1]


def parse(path: Path) -> Netlist:
    """The netlist, with each net under its design name (`design_net_name`)."""
    root = sexpr.parse(path.read_text())
    nl = Netlist()
    for comp in root.child("components").children("comp"):
        ref = comp.child("ref").atoms()[0]
        fields = {
            f.child("name").atoms()[0]: (f.atoms()[0] if f.atoms() else "")
            for f in (comp.child("fields").children("field") if comp.child("fields") else [])
        }
        for p in comp.children("property"):
            name = p.child("name").atoms()[0]
            val = p.child("value").atoms()[0] if p.child("value") else ""
            fields.setdefault(name, val)
        flags = {p.child("name").atoms()[0] for p in comp.children("property")}
        nl.parts[ref] = Part(
            ref=ref,
            value=comp.child("value").atoms()[0] if comp.child("value") else "",
            footprint=comp.child("footprint").atoms()[0] if comp.child("footprint") else "",
            fields=fields,
            in_bom="exclude_from_bom" not in flags,
            dnp="dnp" in flags,
        )
    for net in root.child("nets").children("net"):
        kicad_name = net.child("name").atoms()[0]
        name = design_net_name(kicad_name)
        if name in nl.nets:
            raise ValueError(f"{path}: two nets are named {name} once the sheet path is dropped ({kicad_name})")
        nl.nets[name] = [
            Pin(
                n.child("ref").atoms()[0],
                n.child("pin").atoms()[0],
                n.child("pinfunction").atoms()[0] if n.child("pinfunction") else "",
                n.child("pintype").atoms()[0] if n.child("pintype") else "",
            )
            for n in net.children("node")
        ]
    return nl


def load(board: str) -> Netlist:
    return parse(export(board))
