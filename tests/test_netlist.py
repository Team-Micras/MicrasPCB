"""Net names from a KiCad netlist of a hierarchical schematic."""

import pytest
from micras_pcb import netlist


def _netlist(tmp_path, *names: str):
    nets = " ".join(f'(net (code "{i}") (name "{n}") (node (ref "R{i}") (pin "1")))' for i, n in enumerate(names))
    path = tmp_path / "board.net"
    path.write_text(f"(export (components) (nets {nets}))")
    return path


def test_net_names_drop_the_sheet_path(tmp_path):
    nl = netlist.parse(
        _netlist(tmp_path, "GND", "/Fan_Enable", "/REGULATORS/REGULATORS.MUX_SS", "unconnected-(U5-N{slash}C-Pad4)")
    )
    assert list(nl.nets) == ["GND", "Fan_Enable", "REGULATORS.MUX_SS", "unconnected-(U5-N{slash}C-Pad4)"]
    assert nl.net_of("R2", "1") == "REGULATORS.MUX_SS"


def test_two_sheets_cannot_share_a_local_net_name(tmp_path):
    with pytest.raises(ValueError, match="two nets are named SIG"):
        netlist.parse(_netlist(tmp_path, "/A/SIG", "/B/SIG"))
