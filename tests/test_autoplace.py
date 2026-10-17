"""Drafted schematic placement (micras_pcb.autoplace): each placement rule on small synthetic
sheets, and every board drafted whole from its Zener source.

The synthetic sheets are what `pcb apply` writes, reduced: parts anywhere, each pin's label or
power symbol at the pin, and a netlist naming each pin's net.
"""

from __future__ import annotations

import pytest
from micras_pcb import autoplace, placement, schlint
from micras_pcb.checks import schematic_sheets
from micras_pcb.paths import board_sch, boards
from micras_pcb.schematic import DOWN, GRID, LEFT, RIGHT, UP, Sheet

FONT = "(effects (font (size 1.27 1.27)))"

LIB = f"""(lib_symbols
 (symbol "R" (pin_names (offset 0) (hide yes))
  (property "Reference" "R" (at 1.27 0 90) {FONT}) (property "Value" "R" (at 2.54 0 90) {FONT})
  (symbol "R_0_1" (rectangle (start -0.762 1.778) (end 0.762 -1.778)))
  (symbol "R_1_1" (pin passive line (at 0 2.54 270) (length 0.762) (name "~") (number "1"))
   (pin passive line (at 0 -2.54 90) (length 0.762) (name "~") (number "2"))))
 (symbol "U" (pin_names (offset 0.508))
  (property "Reference" "U" (at 0 7.62 0) {FONT}) (property "Value" "U" (at 0 -7.62 0) {FONT})
  (symbol "U_0_1" (rectangle (start -5.08 5.08) (end 5.08 -5.08)))
  (symbol "U_1_1"
   (pin input line (at -7.62 2.54 0) (length 2.54) (name "IN") (number "1"))
   (pin output line (at 7.62 2.54 180) (length 2.54) (name "OUT") (number "2"))
   (pin power_in line (at 0 7.62 270) (length 2.54) (name "VDD") (number "3"))
   (pin power_in line (at 0 -7.62 90) (length 2.54) (name "GND") (number "4"))
   (pin input line (at -7.62 -2.54 0) (length 2.54) (name "EN") (number "5"))
   (pin output line (at 7.62 -2.54 180) (length 2.54) (name "FB") (number "6"))))
 (symbol "VCC" (power) (pin_names (offset 0) (hide yes))
  (property "Reference" "#PWR" (at 0 -3.81 0) (hide yes) {FONT}) (property "Value" "VCC" (at 0 3.556 0) {FONT})
  (symbol "VCC_0_1" (polyline (pts (xy -0.762 1.27) (xy 0 2.54) (xy 0.762 1.27))) (polyline (pts (xy 0 0) (xy 0 2.54))))
  (symbol "VCC_1_1" (pin power_in line (at 0 0 90) (length 0) (hide yes) (name "VCC") (number "1"))))
 (symbol "GND" (power) (pin_names (offset 0) (hide yes))
  (property "Reference" "#PWR" (at 0 -6.35 0) (hide yes) {FONT}) (property "Value" "GND" (at 0 -3.81 0) {FONT})
  (symbol "GND_0_1" (polyline (pts (xy 0 0) (xy 0 -1.27) (xy 1.27 -1.27) (xy 0 -2.54) (xy -1.27 -1.27) (xy 0 -1.27))))
  (symbol "GND_1_1" (pin power_in line (at 0 0 270) (length 0) (hide yes) (name "GND") (number "1")))))
"""

PIN_AT = {  # pin offsets (mm, page coordinates, symbol at rot 0)
    "R": {"1": (0, -2.54), "2": (0, 2.54)},
    "U": {
        "1": (-7.62, -2.54),
        "2": (7.62, -2.54),
        "3": (0, -7.62),
        "4": (0, 7.62),
        "5": (-7.62, 2.54),
        "6": (7.62, 2.54),
    },
}


class SheetBuilder:
    """A sheet as pcb writes it: parts in a row, each pin's net drawn at the pin."""

    def __init__(self):
        self.items, self.pin_net, self.n = [], {}, 0

    def part(self, ref: str, lib: str, nets: dict[str, str], value: str = "") -> SheetBuilder:
        x, y = 30.48 + 25.4 * (self.n % 8), 30.48 + 25.4 * (self.n // 8)
        self.n += 1
        self.items.append(
            f'(symbol (lib_id "{lib}") (at {x} {y} 0) (unit 1) (uuid "u-{ref}")'
            f' (property "Reference" "{ref}" (at {x + 2} {y} 0) {FONT})'
            f' (property "Value" "{value or lib}" (at {x + 2} {y + 2} 0) {FONT})'
            + "".join(f' (pin "{p}" (uuid "p-{ref}-{p}"))' for p in PIN_AT[lib])
            + ")"
        )
        for pin, net in nets.items():
            dx, dy = PIN_AT[lib][pin]
            at = (round(x + dx, 4), round(y + dy, 4))
            self.pin_net[f"{ref}.{pin}"] = net
            if net in ("VCC", "GND"):
                k = len(self.items)
                self.items.append(
                    f'(symbol (lib_id "{net}") (at {at[0]} {at[1]} 0) (unit 1) (uuid "pw{k}")'
                    f' (property "Reference" "#PWR{k}" (at {at[0]} {at[1]} 0) (hide yes) {FONT})'
                    f' (property "Value" "{net}" (at {at[0]} {at[1]} 0) {FONT}) (pin "1" (uuid "pwp{k}")))'
                )
            elif net.startswith("/"):  # a sheet port: a global label
                self.items.append(
                    f'(global_label "{net[1:]}" (shape input) (at {at[0]} {at[1]} 0)'
                    f' (effects (font (size 1.27 1.27)) (justify left)) (uuid "g-{ref}-{pin}"))'
                )
            else:
                self.items.append(
                    f'(label "{net}" (at {at[0]} {at[1]} 0) (effects (font (size 1.27 1.27))'
                    f' (justify left bottom)) (uuid "l-{ref}-{pin}"))'
                )
        return self

    def write(self, tmp_path, name="s"):
        path = tmp_path / f"{name}.kicad_sch"
        items = "\n".join(f"\t{i}" for i in self.items)
        path.write_text(f'(kicad_sch (version 20250114)\n\t(paper "A4")\n{LIB}\n{items}\n)\n')
        return path


def _draft(tmp_path, b: SheetBuilder, hand=None, hints=None, monkeypatch=None):
    path = b.write(tmp_path)
    if hints is not None:
        zen = tmp_path / "m.zen"
        zen.write_text(f'"""Test module."""\n\nSCHEMATIC_HINTS = {hints!r}\n')
        monkeypatch.setattr(autoplace, "sheet_module", lambda board, sheet: zen)
    d = autoplace.draft_sheet("test", path, path.read_text(), b.pin_net, hand or {})
    return path, d


def _placed(tmp_path, path, b, d, hand=None):
    """The sheet placed from hand entries plus the draft, written next to it."""
    data = placement._merge(hand or {}, d.data)
    placer = placement.Placer("test", path, path.read_text(), placement.spec_from_data(data, "s.toml"), b.pin_net)
    out = tmp_path / "placed.kicad_sch"
    out.write_text(placer.place())
    assert not placer.problems, placer.problems
    return out, placer


def _parts(d) -> dict:
    """{ref: (absolute at, block)} of a draft, in grid units."""
    out = {}
    for blk in d.data["block"]:
        for ref, e in blk.get("parts", {}).items():
            at = e["at"] if isinstance(e, dict) else e
            out[ref] = ((blk["at"][0] + at[0], blk["at"][1] + at[1]), blk, e)
    return out


def _pins(placed_path) -> dict:
    return {p.id: p for s in Sheet.load(placed_path).parts() for p in s.pins()}


def _wired(placed_path, a: str, b: str) -> bool:
    """Pins a and b are joined by wires on the placed sheet."""
    sh = Sheet.load(placed_path)
    from micras_pcb.schematic import islands

    for isl in islands(sh):
        ids = {p.id for p in isl.pins}
        if a in ids:
            return b in ids
    return False


def ic_with(b: SheetBuilder, ref="U1", vdd="VCC") -> SheetBuilder:
    return b.part(ref, "U", {"1": "/IN", "2": "/OUT", "3": vdd, "4": "GND", "5": f"{ref}_EN", "6": f"{ref}_FB"})


def test_decoupling_capacitor_hangs_from_the_supply_pin(tmp_path):
    b = ic_with(SheetBuilder()).part("C1", "R", {"1": "VCC", "2": "GND"}, "100nF")
    path, d = _draft(tmp_path, b)
    placed, _ = _placed(tmp_path, path, b, d)
    pins = _pins(placed)
    assert _wired(placed, "U1.3", "C1.1"), "the capacitor is wired to the pin it decouples"
    assert pins["C1.1"].out == UP and pins["C1.2"].out == DOWN, "supply on top, ground at the bottom"
    vdd, cap = pins["U1.3"].at, pins["C1.1"].at
    assert abs(vdd[0] - cap[0]) + abs(vdd[1] - cap[1]) < 30 * GRID, "beside the pin"


def test_pulls_stand_at_their_pins(tmp_path):
    b = (
        ic_with(SheetBuilder())
        .part("R1", "R", {"1": "VCC", "2": "U1_EN"}, "10k")
        .part("R2", "R", {"1": "U1_FB", "2": "GND"}, "10k")
    )
    path, d = _draft(tmp_path, b)
    placed, _ = _placed(tmp_path, path, b, d)
    pins = _pins(placed)
    assert _wired(placed, "U1.5", "R1.2") and _wired(placed, "U1.6", "R2.1")
    assert pins["R1.1"].out == UP, "a pull-up stands with its supply on top"
    assert pins["R2.2"].out == DOWN, "a pull-down stands with ground at the bottom"
    assert pins["R1.1"].at[0] < pins["U1.1"].at[0], "EN's pull on EN's side (left)"
    assert pins["R2.1"].at[0] > pins["U1.2"].at[0], "FB's pull on FB's side (right)"


def test_series_parts_lie_down(tmp_path):
    b = ic_with(SheetBuilder()).part("R1", "R", {"1": "U1_FB", "2": "U1_EN"}, "1k")
    path, d = _draft(tmp_path, b)
    placed, _ = _placed(tmp_path, path, b, d)
    pins = _pins(placed)
    assert {pins["R1.1"].out, pins["R1.2"].out} == {LEFT, RIGHT}


def test_supplies_point_up_and_grounds_down(tmp_path):
    b = ic_with(SheetBuilder()).part("C1", "R", {"1": "VCC", "2": "GND"})
    path, d = _draft(tmp_path, b)
    placed, _ = _placed(tmp_path, path, b, d)
    for s in Sheet.load(placed).symbols:
        if s.power:
            tip = s.page((0.0, 2.54) if s.value == "VCC" else (0.0, -2.54))
            if s.value == "VCC":
                assert tip[1] < s.at[1], "a supply symbol points up"
            else:
                assert tip[1] > s.at[1], "a ground symbol points down"


def test_blocks_follow_connectivity(tmp_path):
    b = ic_with(SheetBuilder(), "U1").part("R1", "R", {"1": "VCC", "2": "U1_EN"})
    b = ic_with(b, "U2").part("R2", "R", {"1": "VCC", "2": "U2_EN"})
    b.part("R3", "R", {"1": "/OUT", "2": "GND"})  # a pull on a port both ICs share
    _, d = _draft(tmp_path, b)
    blocks = {frozenset(blk["parts"]) for blk in d.data["block"] if blk.get("parts")}
    assert frozenset({"U1", "R1"}) in blocks
    assert frozenset({"U2", "R2"}) in blocks
    assert frozenset({"R3"}) in blocks, "a pull on a net shared by blocks gets a block of its own"
    shared = next(blk for blk in d.data["block"] if "R3" in blk.get("parts", {}))
    assert shared["title"].startswith("Shared nets")


def test_decoupling_joins_the_part_before_it_in_the_source(tmp_path, monkeypatch):
    b = ic_with(SheetBuilder(), "U1")
    b = ic_with(b, "U2").part("C1", "R", {"1": "VCC", "2": "GND"})
    path = b.write(tmp_path)
    zen = tmp_path / "m.zen"
    zen.write_text('"""M."""\nU("U1")\nU("U2")\nC("C1")\n')
    monkeypatch.setattr(autoplace, "sheet_module", lambda board, sheet: zen)
    d = autoplace.draft_sheet("test", path, path.read_text(), b.pin_net, {})
    blk = next(blk for blk in d.data["block"] if "C1" in blk["parts"])
    assert "U2" in blk["parts"]
    zen.write_text('"""M."""\nU("U1")\nC("C1")\nU("U2")\n')
    d = autoplace.draft_sheet("test", path, path.read_text(), b.pin_net, {})
    blk = next(blk for blk in d.data["block"] if "C1" in blk["parts"])
    assert "U1" in blk["parts"]


def test_repeated_blocks_are_laid_out_alike(tmp_path):
    b = SheetBuilder()
    for i in (1, 2, 3):
        ic_with(b, f"U{i}").part(f"R{i}", "R", {"1": "VCC", "2": f"U{i}_EN"}).part(
            f"C{i}", "R", {"1": f"U{i}_FB", "2": "GND"}
        )
    _, d = _draft(tmp_path, b)
    parts = _parts(d)
    rel = [
        {
            k[0]: (parts[k][0][0] - parts[f"U{i}"][0][0], parts[k][0][1] - parts[f"U{i}"][0][1])
            for k in (f"R{i}", f"C{i}")
        }
        for i in (1, 2, 3)
    ]
    assert rel[0] == rel[1] == rel[2]
    sizes = {tuple(parts[f"U{i}"][1]["size"]) for i in (1, 2, 3)}
    assert len(sizes) == 1, "one frame size"
    ys = {parts[f"U{i}"][1]["at"][1] for i in (1, 2, 3)}
    assert len(ys) == 1, "side by side"


def test_draft_reads_cleanly_on_the_smallest_paper(tmp_path):
    b = ic_with(SheetBuilder()).part("C1", "R", {"1": "VCC", "2": "GND"}).part("R1", "R", {"1": "VCC", "2": "U1_EN"})
    path, d = _draft(tmp_path, b)
    placed, _ = _placed(tmp_path, path, b, d)
    assert schlint.problems(placed) == []
    assert d.data["paper"] == "A5"


def test_draft_is_deterministic(tmp_path):
    b = ic_with(SheetBuilder()).part("C1", "R", {"1": "VCC", "2": "GND"}).part("R1", "R", {"1": "U1_FB", "2": "U1_EN"})
    _, d1 = _draft(tmp_path, b)
    _, d2 = _draft(tmp_path, b)
    assert d1.data == d2.data
    t1 = placement.toml_text(d1.data, "x")
    assert placement.toml_text(d2.data, "x") == t1


def test_hand_entries_are_never_moved(tmp_path):
    b = ic_with(SheetBuilder()).part("C1", "R", {"1": "VCC", "2": "GND"}).part("R1", "R", {"1": "VCC", "2": "U1_EN"})
    hand = {"paper": "A4", "block": [{"title": "Mine", "at": [40, 40], "size": [40, 40], "parts": {"U1": [20, 20]}}]}
    path, d = _draft(tmp_path, b, hand)
    assert set(d.auto) == {"C1", "R1"}
    assert "U1" not in _parts(d), "the draft does not place what the hand did"
    placed, _ = _placed(tmp_path, path, b, d, hand)
    u1 = next(s for s in Sheet.load(placed).parts() if s.ref == "U1")
    assert u1.at == pytest.approx((60 * GRID, 60 * GRID))
    assert schlint.problems(placed) == [], "drafted blocks go around the hand's"
    for blk in d.data["block"]:
        x, y = blk["at"]
        w, h = blk["size"]
        assert x >= 80 + 2 or y >= 80 + 2 or x + w <= 40 - 2 or y + h <= 40 - 2


def test_placement_file_keeps_hand_text_and_replaces_drafts():
    hand = '# Mine.\npaper = "A4"\n\n[[block]]\ntitle = "Mine"\nat = [10, 10]\nparts.U1 = [1, 2]\n'
    draft = {"block": [{"title": "D", "auto": True, "at": [50, 10], "size": [10, 10], "parts": {"R1": {"at": [2, 3]}}}]}
    once = placement.with_draft(hand, draft, "b", "s")
    assert once.startswith(hand.rstrip("\n"))
    assert "auto = true" in once and "parts.R1 = [2, 3]" in once
    twice = placement.with_draft(once, draft, "b", "s")
    assert twice == once, "redrafting replaces the earlier draft"
    adopted = once.replace("auto = true\n", "")
    kept = placement.with_draft(adopted, {"block": []}, "b", "s")
    assert "parts.R1 = [2, 3]" in kept, "a draft without its auto line is a hand entry"
    data = __import__("tomllib").loads(once)
    assert placement.spec_from_data(data, "s.toml").auto == {"R1"}


def test_hints_steer_titles_blocks_and_flow(tmp_path, monkeypatch):
    b = ic_with(SheetBuilder()).part("R1", "R", {"1": "VCC", "2": "U1_EN"}).part("R2", "R", {"1": "U1_FB", "2": "GND"})
    hints = {"titles": {"U1": "The IC"}, "blocks": [{"title": "Pulls", "parts": ["R2"]}], "flow": {"R1": "right"}}
    _, d = _draft(tmp_path, b, hints=hints, monkeypatch=monkeypatch)
    titles = {blk["title"]: set(blk["parts"]) for blk in d.data["block"]}
    assert titles["The IC"] == {"U1", "R1"}
    assert titles["Pulls"] == {"R2"}
    parts = _parts(d)
    assert parts["R1"][0][0] > parts["U1"][0][0], "flow puts R1 right of its anchor"


def test_hints_are_a_literal_dict_pcb_ignores(tmp_path):
    zen = tmp_path / "m.zen"
    zen.write_text(
        '"""Doc."""\n\nX = 1\n\n# placement only\nSCHEMATIC_HINTS = {\n    "titles": {"U1": "A"},  # why\n'
        '    "flow": {"R1": "left"},\n}\n'
    )
    hints = autoplace.read_hints(zen)
    assert hints == {"titles": {"U1": "A"}, "flow": {"R1": "left"}}
    assert autoplace.hint_problems(hints, {"U1"}) == ["SCHEMATIC_HINTS names parts the sheet does not have: R1"]
    zen.write_text('SCHEMATIC_HINTS = {"colour": "red"}\n')
    with pytest.raises(ValueError):
        autoplace.read_hints(zen)


def test_pack_goes_around_what_is_there():
    spots = autoplace.pack([(20, 10), (20, 10)], [(10, 10, 40, 40)], "A4")
    for x, y in spots:
        assert x >= 42 or y >= 42
    assert autoplace.choose_paper([(150, 100)], [], None)[0] == "A4"
    assert autoplace.choose_paper([(200, 130)], [], None)[0] == "A3", "clear of the title block"


@pytest.mark.parametrize("board", boards())
def test_every_board_drafts_cleanly_from_scratch(board, tmp_path):
    """Each sheet drafted whole from the Zener source alone: KiCad's netlist of it equals pcb's
    (place_board fails otherwise), and nothing overlaps or leaves the page."""
    with placement.preserved_layout(board):
        status, stats = placement.place_board(board, tmp_path, everything=True)
    assert status == 0
    problems = []
    for path in schematic_sheets(tmp_path / board_sch(board).name):
        problems += [f"{path.name}: {p}" for p in schlint.problems(path)]
    assert not problems, "\n".join(problems[:40])
    assert all(a == n for a, n in stats.values()), stats


def test_signal_flows_left_to_right(tmp_path):
    """A part driving the IC's input (a left-side pin) goes to its left, wired straight."""
    b = ic_with(SheetBuilder(), "U1")
    b.part("U2", "U", {"1": "/X", "2": "U1_IN", "3": "VCC", "4": "GND", "5": "U2_EN", "6": "U2_FB"})
    b.pin_net["U1.1"] = "U1_IN"
    b.items = [i.replace('global_label "IN" (shape input) (at 22.86', 'label "U1_IN" (at 22.86') for i in b.items]
    path, d = _draft(tmp_path, b)
    placed, _ = _placed(tmp_path, path, b, d)
    pins = _pins(placed)
    assert pins["U2.2"].at[0] < pins["U1.1"].at[0]
    assert _wired(placed, "U1.1", "U2.2")


def test_sheet_pins_face_the_root_and_follow_the_module(tmp_path, monkeypatch):
    """A module's sheet pins: those the root sheet's parts use on the left, those only other
    modules use on the right, each side in the module's io() order."""
    b = ic_with(SheetBuilder(), "U1")  # U1 IN and OUT carry the global labels IN and OUT
    pins = [("OUT", 55.88), ("Z", 58.42), ("IN", 60.96)]
    sheet = (
        '(sheet (at 150 50) (size 20 20) (uuid "s1")'
        f' (property "Sheetname" "MOD" (at 150 49 0) {FONT}) (property "Sheetfile" "MOD.kicad_sch" (at 150 71 0) {FONT})'
        + "".join(f' (pin "{n}" passive (at 150 {y} 180) (uuid "sp{n}") {FONT})' for n, y in pins)
        + ")"
    )
    b.items.append(sheet)
    for n, y in pins:
        b.items.append(f'(global_label "{n}" (shape input) (at 150 {y} 180) {FONT} (uuid "gl{n}"))')
    path = b.write(tmp_path)
    zen = tmp_path / "Mod.zen"
    zen.write_text('"""Mod."""\nZ = io(Net)\nIN = io(Net)\nOUT = io(Net)\n')
    monkeypatch.setattr(autoplace, "sheet_module", lambda board, sheet: zen)
    m = autoplace.Model("test", path, path.read_text(), b.pin_net)
    (sym,) = autoplace.sheet_symbols(m, "test", ["MOD"])
    assert sym["left"] == ["IN", "OUT"]
    assert sym["right"] == ["Z"]
    assert sym["size"][1] >= 2 * (len(sym["left"]) + 1)
