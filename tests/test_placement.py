"""Schematic placement (micras-pcb sch): the placement files in boards/<board>/schematic/ name
only what their sheets have (parts without an entry are drafted, tests/test_autoplace.py), and
every placed sheet reads cleanly: no two texts overlap, no text sits
on a symbol body or is crossed by a wire, no two bodies overlap, no wire runs through a body, and
nothing runs past the page border or into the title block (micras_pcb.schlint).

`make gen` places each sheet and fails unless KiCad's netlist of the placed schematic equals the
one of pcb's; CI then checks that `make gen` changes nothing.
"""

from __future__ import annotations

import pytest
from micras_pcb import placement, schlint
from micras_pcb.checks import schematic_sheets
from micras_pcb.paths import board_sch, boards
from micras_pcb.schematic import DOWN, GRID, LEFT, RIGHT, UP, Sheet, Symbol


@pytest.mark.parametrize("board", boards())
def test_placement_entries_name_what_their_sheets_have(board):
    """Each entry, wire and hint names a part or pin on its sheet, each sheet symbol holds its
    pins, and each sheet is placed."""
    found = placement.unplaced(board, missing_ok=True)
    assert not found, "\n".join(found)


@pytest.mark.parametrize("board", boards())
def test_sheets_read_cleanly(board):
    """No overlapping texts, bodies or wires on any sheet of the board's schematic."""
    problems = []
    for path in schematic_sheets(board_sch(board)):
        problems += [f"{path.name}: {p}" for p in schlint.problems(path)]
    shown = problems[:40] + ([f"and {len(problems) - 40} more"] if len(problems) > 40 else [])
    assert not problems, "\n".join(shown)


LIB = (
    '(lib_symbols (symbol "R" (symbol "R_0_1" (rectangle (start -1 2) (end 1 -2)))'
    ' (symbol "R_1_1" (pin passive line (at 0 3.81 270) (length 1.81) (name "~") (number "1"))'
    ' (pin passive line (at 0 -3.81 90) (length 1.81) (name "~") (number "2")))))'
)


def _sym(ref: str, x: float, y: float, rot: int = 0) -> str:
    return (
        f'(symbol (lib_id "R") (at {x} {y} {rot}) (unit 1) (uuid "u{ref}")'
        f' (property "Reference" "{ref}" (at {x + 2} {y} 0) (effects (font (size 1.27 1.27)) (justify left)))'
        f' (pin "1" (uuid "p1{ref}")) (pin "2" (uuid "p2{ref}")))'
    )


def _sheet(tmp_path, items: str):
    path = tmp_path / "s.kicad_sch"
    path.write_text(f'(kicad_sch (paper "A4") {LIB} {items})')
    return path


def test_pins_follow_the_symbols_rotation(tmp_path):
    sh = Sheet.load(_sheet(tmp_path, _sym("R1", 100, 100, 90)))
    pins = {p.number: p for p in sh.symbols[0].pins()}
    # library pin 1 at (0, 3.81), above the body; rotated 90 degrees counterclockwise, to the left
    assert pins["1"].at == pytest.approx((96.19, 100))
    assert pins["1"].out == LEFT
    assert pins["2"].out == RIGHT


def test_overlaps_are_reported(tmp_path):
    clean = _sheet(tmp_path, _sym("R1", 100, 100) + _sym("R2", 120, 100))
    assert schlint.problems(clean) == []
    path = _sheet(
        tmp_path,
        _sym("R1", 100, 100)
        + _sym("R2", 101, 100)  # bodies overlap
        + '(label "NET" (at 95 80 0) (effects (font (size 1.27 1.27)) (justify left bottom)))'
        + '(label "NET2" (at 96 80 0) (effects (font (size 1.27 1.27)) (justify left bottom)))'
        + "(wire (pts (xy 90 100) (xy 110 100)))",  # through both bodies
    )
    found = schlint.problems(path)
    assert any("body of R1 overlaps body of R2" in f for f in found)
    assert any("label NET overlaps text label NET2" in f for f in found)
    assert any("crosses body of R1" in f for f in found)


def test_wires_leave_and_enter_pins_along_their_axis():
    a, b = (0.0, 0.0), (10 * GRID, 5 * GRID)
    assert placement._route(a, b, RIGHT, None) == [a, (b[0], a[1]), b]
    assert placement._route(a, b, UP, None) == [a, (a[0], b[1]), b]
    assert placement._route(a, b, None, DOWN) == [a, (b[0], a[1]), b]
    assert placement._route(a, (0.0, 3.0), RIGHT, None) == [a, (0.0, 3.0)]


def test_field_justification_reads_on_the_page(tmp_path):
    sh = Sheet.load(_sheet(tmp_path, _sym("R1", 100, 100)))
    s = sh.symbols[0]
    assert placement._stored_justify("left", s, 0) == "left"
    rotated = Symbol(s.node, s.lib, s.at, 90, None)
    # KiCad turns the field with the symbol and keeps the text readable: the stored justification
    # is the mirror of the one wanted on the page (pcb-kicad-sch stored_field_justify)
    assert placement._stored_justify("left", rotated, 90) == "right"
    assert placement._stored_justify("left", Symbol(s.node, s.lib, s.at, 270, None), 90) == "left"
    assert placement._stored_justify("left", Symbol(s.node, s.lib, s.at, 0, "y"), 0) == "right"


def test_a_wire_between_two_nets_is_refused(tmp_path):
    path = _sheet(tmp_path, _sym("R1", 100, 100) + _sym("R2", 120, 100))
    spec = placement.Spec(
        parts={"R1": placement.PartSpec((100.33, 100.33)), "R2": placement.PartSpec((120.65, 100.33))},
        chains=[["R1.1", "R2.1"]],
    )
    placer = placement.Placer("test", path, path.read_text(), spec, {"R1.1": "A", "R2.1": "B"})
    placer.place()
    assert any("joins pins of different nets" in p for p in placer.problems)
