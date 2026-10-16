"""Every board's schematic fits its pages: each sheet's symbols, labels (with their text), wires and
sheet symbols lie inside that sheet's paper, so the exported PDF and KiCad Prism show the whole
circuit.

`pcb apply` grows a generated sheet's paper up to A0 and places what does not fit to the right of
the page (pcb-kicad-sch placement.rs); it only warns. A symbol's extent is its body graphics and
pin ends, rotated and mirrored as KiCad places them, plus its visible fields' anchors.
"""

from __future__ import annotations

import pytest
from micras_pcb import sexpr
from micras_pcb.checks import schematic_sheets
from micras_pcb.paths import board_sch, boards

# KiCad's named paper sizes in mm, landscape (common/page_info.cpp).
PAPER = {
    "A5": (210, 148),
    "A4": (297, 210),
    "A3": (420, 297),
    "A2": (594, 420),
    "A1": (841, 594),
    "A0": (1189, 841),
    "A": (279.4, 215.9),
    "B": (431.8, 279.4),
    "C": (558.8, 431.8),
    "D": (863.6, 558.8),
    "E": (1117.6, 863.6),
    "USLetter": (279.4, 215.9),
    "USLegal": (355.6, 215.9),
    "USLedger": (431.8, 279.4),
    "GERBER": (812.8, 812.8),
}
EPS = 1e-6


def paper_size(sch: sexpr.Node) -> tuple[float, float]:
    paper = sch.child("paper")
    atoms = paper.atoms() if paper else ["A4"]
    if atoms[0] == "User":
        w, h = float(atoms[1]), float(atoms[2])
    else:
        w, h = PAPER[atoms[0]]
    return (h, w) if "portrait" in atoms else (w, h)


def _xy(node: sexpr.Node | None) -> tuple[float, float]:
    a = node.atoms()
    return float(a[0]), float(a[1])


def _body_points(unit: sexpr.Node) -> list[tuple[float, float]]:
    """A library unit's graphics and pin ends, in library coordinates (y up)."""
    pts = []
    for g in unit.children():
        if g.head == "rectangle":
            pts += [_xy(g.child("start")), _xy(g.child("end"))]
        elif g.head == "polyline" or g.head == "bezier":
            pts += [_xy(p) for p in g.child("pts").children("xy")]
        elif g.head == "arc":
            pts += [_xy(g.child(k)) for k in ("start", "mid", "end")]
        elif g.head == "circle":
            (cx, cy), r = _xy(g.child("center")), float(g.child("radius").atoms()[0])
            pts += [(cx - r, cy - r), (cx + r, cy + r)]
        elif g.head == "pin":
            at = g.child("at").atoms()
            x, y, angle = float(at[0]), float(at[1]), float(at[2]) if len(at) > 2 else 0.0
            length = float(g.child("length").atoms()[0])
            dx, dy = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}[int(angle) % 360]
            pts += [(x, y), (x + dx * length, y + dy * length)]
    return pts


def _units(lib: sexpr.Node, unit: int) -> list[sexpr.Node]:
    """The sub-symbols drawn for a unit: "<name>_<unit>_<style>", unit 0 common to all, style 1."""
    found = []
    for sub in lib.children("symbol"):
        u, style = sub.atoms()[0].rsplit("_", 2)[1:]
        if int(u) in (0, unit) and int(style) in (0, 1):
            found.append(sub)
    return found


def symbol_extent(sym: sexpr.Node, libs: dict[str, sexpr.Node]) -> list[tuple[float, float]]:
    """A placed symbol's body and pin points, and its visible fields' anchors, in sheet coordinates."""
    at = sym.child("at").atoms()
    x0, y0, rot = float(at[0]), float(at[1]), int(float(at[2]) if len(at) > 2 else 0) % 360
    mirror = sym.child("mirror").atoms()[0] if sym.child("mirror") else None
    unit = int(sym.child("unit").atoms()[0]) if sym.child("unit") else 1
    pts = []
    for lx, ly in [p for u in _units(libs[sym.child("lib_id").atoms()[0]], unit) for p in _body_points(u)]:
        # KiCad flips the library's y axis, rotates by the symbol's angle, then mirrors (as pcb's
        # pcb-kicad-sch symbol.rs transform_vector).
        x, y = lx, -ly
        x, y = {0: (x, y), 90: (y, -x), 180: (-x, -y), 270: (-y, x)}[rot]
        if mirror == "x":
            y = -y
        elif mirror == "y":
            x = -x
        pts.append((x0 + x, y0 + y))
    for field in sym.children("property"):
        hidden = field.child("hide") and field.child("hide").atoms() == ["yes"]
        if not hidden and field.atoms()[1].strip() and field.child("at"):
            pts.append(_xy(field.child("at")))
    return pts


# pcb-kicad-sch compose.rs: a label's text is estimated at 0.8 em a character, and a global or
# hierarchical label's shape adds 2.54 mm.
LABEL_EM = 0.8
LABEL_SHAPE = 2.54


def label_extent(item: sexpr.Node) -> list[tuple[float, float]]:
    """A label's anchor and the far end of its text, which runs along the label's angle."""
    at = item.child("at").atoms()
    x, y, angle = float(at[0]), float(at[1]), int(float(at[2]) if len(at) > 2 else 0) % 360
    font = item.child("effects").child("font").child("size") if item.child("effects") else None
    size = float(font.atoms()[1]) if font else 1.27
    length = len(item.atoms()[0]) * size * LABEL_EM + (LABEL_SHAPE if item.head != "label" else 0)
    dx, dy = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}[angle]
    return [(x, y), (x + dx * length, y + dy * length)]


def _item_points(item: sexpr.Node, label_text: bool) -> list[tuple[float, float]]:
    if item.head == "wire" or item.head == "bus":
        return [_xy(p) for p in item.child("pts").children("xy")]
    if item.head == "sheet":
        (x, y), (w, h) = _xy(item.child("at")), _xy(item.child("size"))
        return [(x, y), (x + w, y + h)]
    if item.head.endswith("label") and label_text:
        return label_extent(item)
    return [_xy(item.child("at"))]


def outside_page(path, label_text: bool = True) -> list[str]:
    """What lies outside a sheet's paper: '<item> at (x, y)' for each item, the worst point. Without
    label_text, a label counts by its anchor alone."""
    sch = sexpr.parse(path.read_text())
    w, h = paper_size(sch)
    libs = {s.atoms()[0]: s for s in sch.child("lib_symbols").children("symbol")} if sch.child("lib_symbols") else {}
    bad = []
    heads = ("symbol", "label", "global_label", "hierarchical_label", "wire", "bus", "junction", "no_connect", "sheet")
    for item in sch.children():
        if item.head not in heads:
            continue
        if item.head == "symbol":
            pts = symbol_extent(item, libs)
            name = f"symbol {item.prop('Reference')} ({item.child('lib_id').atoms()[0]})"
        else:
            pts = _item_points(item, label_text)
            text = item.atoms()[0] if item.head.endswith("label") else (item.prop("Sheetname") or "")
            name = f"{item.head} {text}".strip()
        off = [(x, y) for x, y in pts if x < -EPS or y < -EPS or x > w + EPS or y > h + EPS]
        if off:
            x, y = max(off, key=lambda p: max(-p[0], -p[1], p[0] - w, p[1] - h))
            bad.append(f"{name} at ({x:.1f}, {y:.1f})")
    return bad


# Boards whose label text runs past a page edge, with the reason; each is a strict xfail, so the
# entry must go once the labels fit.
LABEL_TEXT_PAST_THE_PAGE: dict[str, str] = {
    "main2": (
        "pcb 0.4.81 packs the five module sheet symbols on the root by their boxes alone, so the"
        " root labels at SENSORS' pins run up to 11 mm past the left edge (diodeinc/pcb#1520);"
        " diodeinc/pcb#1522 spaces the sheet symbols clear of their pin labels"
    ),
}


def _problems(board: str, label_text: bool) -> list[str]:
    problems = []
    for path in schematic_sheets(board_sch(board)):
        w, h = paper_size(sexpr.parse(path.read_text()))
        bad = outside_page(path, label_text)
        if bad:
            shown = "; ".join(bad[:8]) + (f"; and {len(bad) - 8} more" if len(bad) > 8 else "")
            problems.append(f"{path.name} ({w:.0f} x {h:.0f} mm): {len(bad)} item(s) off the page: {shown}")
    return problems


@pytest.mark.parametrize("board", boards())
def test_schematic_fits_its_pages(board):
    """Each sheet of the board's schematic holds its symbols, label anchors, wires and sheet
    symbols inside its paper."""
    problems = _problems(board, label_text=False)
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(
    "board",
    [
        pytest.param(b, marks=pytest.mark.xfail(reason=LABEL_TEXT_PAST_THE_PAGE[b], strict=True))
        if b in LABEL_TEXT_PAST_THE_PAGE
        else b
        for b in boards()
    ],
)
def test_label_text_fits_its_pages(board):
    """Each label's text, not only its anchor, stays inside its sheet's paper."""
    problems = _problems(board, label_text=True)
    assert not problems, "\n".join(problems)


def test_an_item_past_the_paper_is_reported(tmp_path):
    lib = (
        '(lib_symbols (symbol "R" (symbol "R_0_1" (rectangle (start -1 2) (end 1 -2)))'
        ' (symbol "R_1_1" (pin passive line (at 0 3.81 270) (length 1.27)))))'
    )
    on = '(symbol (lib_id "R") (at 100 100 0) (unit 1) (property "Reference" "R1" (at 102 100 0)))'
    # Rotated 90 degrees, the pin's far end (library (0, 3.81)) lands at x = 295 - 3.81.
    off = '(symbol (lib_id "R") (at 295 100 90) (unit 1) (property "Reference" "R2" (at 297 100 0)))'
    (tmp_path / "a.kicad_sch").write_text(
        f'(kicad_sch (paper "A4") {lib} {on} {off} (label "N" (at 300 50 0)) (wire (pts (xy 10 10) (xy 10 20))))'
    )
    assert outside_page(tmp_path / "a.kicad_sch") == ["label N at (301.0, 50.0)"]
    # A label inside the page whose text runs past its left edge (2 characters at 0.8 em).
    (tmp_path / "c.kicad_sch").write_text('(kicad_sch (paper "A4") (label "AB" (at 1 50 180)))')
    assert outside_page(tmp_path / "c.kicad_sch") == ["label AB at (-1.0, 50.0)"]
    assert outside_page(tmp_path / "c.kicad_sch", label_text=False) == []
    (tmp_path / "b.kicad_sch").write_text(f'(kicad_sch (paper "A4") {lib} {off.replace("90", "270")})')
    assert outside_page(tmp_path / "b.kicad_sch") == ["symbol R2 (R) at (298.8, 100.0)"]
