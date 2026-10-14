"""ERC acceptance of boards/<board>/erc.toml supplies on a hierarchical schematic."""

from micras_pcb import checks
from micras_pcb.netlist import Netlist, Pin


def _power(ref: str, net: str, instance_ref: str | None = None) -> str:
    instances = (
        f'(instances (project "p" (path "/root/sheet" (reference "{instance_ref}") (unit 1))))' if instance_ref else ""
    )
    return f'(symbol (lib_id "{net}") (property "Reference" "{ref}") (property "Value" "{net}") (pin "1") {instances})'


def _sheet(file: str) -> str:
    return f'(sheet (property "Sheetname" "{file}") (property "Sheetfile" "{file}"))'


def _hierarchy(tmp_path):
    """root -> A (placed twice) -> B, with a power symbol on each sheet."""
    (tmp_path / "root.kicad_sch").write_text(
        f"(kicad_sch {_power('#PWR1', 'GND')} {_sheet('A.kicad_sch')} {_sheet('A.kicad_sch')})"
    )
    (tmp_path / "A.kicad_sch").write_text(
        f"(kicad_sch {_power('#PWR2', 'VBAT', instance_ref='#PWR9')} {_sheet('B.kicad_sch')})"
    )
    (tmp_path / "B.kicad_sch").write_text(f'(kicad_sch {_power("#PWR3", "VDDA")} (symbol (property "Reference" "R1")))')
    return tmp_path / "root.kicad_sch"


def test_sheets_follow_the_hierarchy_from_the_root(tmp_path):
    sheets = checks.schematic_sheets(_hierarchy(tmp_path))
    assert [p.name for p in sheets] == ["root.kicad_sch", "A.kicad_sch", "B.kicad_sch"]


def test_power_symbols_come_from_every_sheet(tmp_path):
    assert checks.power_symbols(_hierarchy(tmp_path)) == {
        "#PWR1": "GND",
        "#PWR2": "VBAT",
        "#PWR9": "VBAT",
        "#PWR3": "VDDA",
    }


def _undriven(description: str) -> dict:
    return {"type": "power_pin_not_driven", "items": [{"description": description}]}


def test_a_supplied_net_is_accepted_on_a_sub_sheet_power_symbol(tmp_path):
    nl = Netlist(nets={"VBAT": [Pin("U1", "3", "VIN", "power_in")], "V5V": [Pin("U2", "1", "VIN", "power_in")]})
    on_sub_sheet = _undriven("Symbol #PWR9 Pin 1 [Power input, Line]")
    on_part_pin = _undriven("Symbol U1 Pin 3 [Power input, Line]")
    not_supplied = _undriven("Symbol U2 Pin 1 [Power input, Line]")
    other = {"type": "label_dangling", "items": [{"description": "Label 'VBAT'"}]}

    kept, accepted = checks._accept_supplied(
        [on_sub_sheet, on_part_pin, not_supplied, other],
        {"VBAT": "the battery"},
        checks.power_symbols(_hierarchy(tmp_path)),
        nl,
    )

    assert kept == [not_supplied, other]
    assert accepted == ["  accepted power_pin_not_driven on VBAT: supplied by the battery"] * 2
