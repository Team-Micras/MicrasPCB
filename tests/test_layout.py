"""Layout checks on every board: decoupling next to its pin, the encoder joint's slot, fab hygiene.

The placement-dependent checks skip, with the reason, while a board's layout has no outline: until
then the footprints sit where the netlist sync packed them, which says nothing about the design. A
schematic-only board (no layout file, Project(layout = False)) is not listed at all.
"""

import json
import math
import shutil
import tomllib

import pytest
from micras_pcb import layout, sexpr, spec
from micras_pcb.paths import ROOT, board_pcb, layout_boards, layout_dir

from .conftest import needs_kicad
from .design import design

needs_pcb = pytest.mark.skipif(shutil.which("pcb") is None, reason="pcb not installed")

# Decoupling the datasheets ask to sit at the pin ("as close as possible", "near", "close to"):
# (MPN prefix, pin names, count, capacitance range in F, source). count None: one capacitor per pad
# (the STM32's five VDD pads); a number: that many capacitors at the pin group.
PER_PAD = None
DECOUPLING = [
    (
        "STM32H725",
        ("VDD",),
        PER_PAD,
        (90e-9, 110e-9),
        "AN5419 Rev 3 Table 2 p7: 100 nF per VDD pin, as close as possible",
    ),
    ("STM32H725", ("VDDA",), 1, (90e-9, 110e-9), "AN5419 Table 2 p7: 100 nF as close as possible to VDDA"),
    ("STM32H725", ("VBAT",), 1, (90e-9, 110e-9), "AN5419 Table 2 p7: 100 nF close to the VBAT pin"),
    ("STM32H725", ("VCAP1",), 1, (90e-9, 110e-9), "AN5419 Figure 5 p10: 100 nF close to each VCAP pin"),
    ("STM32H725", ("VCAP2",), 1, (90e-9, 110e-9), "AN5419 Figure 5 p10: 100 nF close to each VCAP pin"),
    ("STM32H725", ("VCAP3",), 1, (90e-9, 110e-9), "AN5419 Figure 5 p10: 100 nF close to each VCAP pin"),
    ("LSM6DSV", ("Vdd",), 1, (90e-9, 110e-9), "DS13476 Rev 5 Table 2 note 1, Figure 27: 100 nF as near as possible"),
    ("LSM6DSV", ("Vdd_IO",), 1, (90e-9, 110e-9), "DS13476 Rev 5 Table 2 note 1, Figure 27: 100 nF as near as possible"),
    (
        "TSC2020",
        ("VCC",),
        1,
        (90e-9, 110e-9),
        "DS14393 Rev 7 section 5.11: 100 nF as close as possible to the supply pins",
    ),
    (
        "L6205",
        ("VSA", "VSB"),
        1,
        (90e-9, 220e-9),
        "L6205 p12: 100-200 nF ceramic between VSA/VSB and ground near the L6205",
    ),
    ("STSPIN958", ("VS",), 2, (420e-9, 520e-9), "DS14341 Rev 1 section 8, Table 12: 2 x 470 nF close to the VS pins"),
    ("STSPIN958", ("VDD",), 1, (198e-9, 242e-9), "DS14341 Rev 1 section 8, Table 12: 220 nF close to VDD"),
    (
        "INA241",
        ("VS",),
        1,
        (90e-9, 110e-9),
        "SBOSA30D sections 8.3.1, 8.4.1: 0.1 uF as close as possible to the supply and ground pins",
    ),
    ("INA228", ("VS",), 1, (90e-9, 110e-9), "SLYS021A sections 9, 10.1: 0.1 uF as close as possible to VS and GND"),
    (
        "DRV8874",
        ("VM",),
        1,
        (90e-9, 110e-9),
        "SLVSF66A Table 1, section 10.1: CVM1 0.1 uF from VM to GND close to the pins",
    ),
    (
        "ADP7142",
        ("VIN",),
        1,
        (2.2e-6, 22e-6),
        "ADP7142 Rev H Table 2, p20: >= 2.2 uF input capacitor close to the pins",
    ),
    (
        "ADP7142",
        ("VOUT",),
        1,
        (2.2e-6, 22e-6),
        "ADP7142 Rev H Table 2, p20: >= 2.2 uF output capacitor close to the pins",
    ),
]
# Not listed: the AS5047U in 3.3 V mode. Its datasheet (v1-00 p11, Figure 11) asks "close to chip"
# only for the 1 uF of the 5 V LDO mode; the 3.3 V mode drawing just shows 100 nF on VDD.
# The datasheets give no number for "close". This project reads it as: the capacitor's nearest pad
# centre within 3 mm of the pin's pad centre, which puts an 0402 beside the pin with one via (the
# previous main board's LSM6DSV capacitors sit 2.1-2.5 mm from the part).
MAX_DECOUPLING_MM = 3.0

# A schematic-only board (no .kicad_pcb yet) has nothing to check here.
LAYOUT_BOARDS = layout_boards()


def _placed(board: str) -> layout.Board:
    pcb = layout.load(board)
    if not pcb.placed:
        pytest.skip(f"{board}: the layout has no Edge.Cuts outline yet (placement not done)")
    return pcb


def _match(groups: list[list[str]]) -> dict[int, str]:
    """Maximum matching of pin groups to distinct capacitors (groups[i] lists acceptable capacitors)."""
    owner: dict[str, int] = {}

    def augment(i: int, seen: set[str]) -> bool:
        for cap in groups[i]:
            if cap in seen:
                continue
            seen.add(cap)
            if cap not in owner or augment(owner[cap], seen):
                owner[cap] = i
                return True
        return False

    for i in range(len(groups)):
        augment(i, set())
    return {i: cap for cap, i in owner.items()}


def decoupling_findings(board: str, pcb: layout.Board) -> list[str]:
    """Every listed pin (group) gets its own capacitor within MAX_DECOUPLING_MM; one capacitor
    serves one pin of a part."""
    d = design(board)
    problems = []
    for ref in sorted({r for mpn, *_ in DECOUPLING for r in d.refs(mpn)}):
        wants = []  # (description, source, [(distance, cap)] in range on the pin's rail)
        for mpn, names, count, (lo, hi), source in DECOUPLING:
            if ref not in d.refs(mpn):
                continue
            numbers = [n for name in names for n in d.pads(ref, name)]
            if not numbers:
                problems.append(f"{ref} has no pin named {'/'.join(names)}")
                continue
            for group in [[n] for n in numbers] if count is PER_PAD else [numbers] * count:
                rail = d.net(ref, group[0])
                pads = [p for n in group for p in pcb.footprints[ref].pads_named(n)]
                options = []
                for cap in d.two_terminal("capacitor", rail, "GND"):
                    value = d.value(cap, "capacitance")
                    if value is not None and lo <= value <= hi and cap in pcb.footprints:
                        dist = min(math.dist(a.xy, c.xy) for a in pads for c in pcb.footprints[cap].pads if c.net)
                        options.append((dist, cap))
                wants.append((f"{ref} {'/'.join(names)} (pad {', '.join(group)}, {rail})", source, sorted(options)))
        matched = _match([[cap for dist, cap in opts if dist <= MAX_DECOUPLING_MM] for _, _, opts in wants])
        for i, (where, source, options) in enumerate(wants):
            if i in matched:
                continue
            if not options:
                problems.append(f"{where}: no capacitor of the required value; {source}")
            else:
                dist, cap = options[0]
                problems.append(
                    f"{where}: no capacitor of its own within {MAX_DECOUPLING_MM} mm (nearest {cap} at {dist:.1f} mm); {source}"
                )
    return problems


@needs_kicad
@needs_pcb
@pytest.mark.parametrize("board", LAYOUT_BOARDS)
def test_decoupling_sits_at_its_pin(board):
    pcb = _placed(board)
    problems = decoupling_findings(board, pcb)
    assert not problems, "\n".join(problems)


# --- the encoder joint: the encoder board's tab in the main board's slots ------------------------

# JLCPCB PCB capabilities (jlcpcb.com/capabilities/pcb-capabilities, read 2026-10-14):
# "The minimum Non-Plated Slot Width is 1.0mm, please draw the slot outline in the mechanical
# layer (GM1 or GKO)"; "Rectangular holes and slots without rounded corners are not supported";
# board thickness below 1.0 mm: +-0.1 mm. A slot is milled by a cutter no wider than the slot, so
# its corners come out with a radius of at least half the 1.0 mm minimum width.
JLC_MIN_SLOT_MM = 1.0
JLC_THIN_BOARD_TOL_MM = 0.1


def _slot_outline(pcb: layout.Board, ref: str) -> tuple[float, float, float] | None:
    """(width, length, drawn corner radius) of the Edge.Cuts cut-out at an EncoderSlot footprint."""
    fp = pcb.footprints[ref]
    cx, cy = fp.xy
    t = math.radians(fp.rotation)
    near, radius = [], 0.0
    for kind, pts, r in pcb.edge_shapes:
        if all(math.dist(p, (cx, cy)) < 4.0 for p in pts):
            for x, y in pts:
                dx, dy = x - cx, y - cy
                near.append((dx * math.cos(t) - dy * math.sin(t), dx * math.sin(t) + dy * math.cos(t)))
            if kind == "gr_arc" and r:
                radius = max(radius, r)
    if not near:
        return None
    xs, ys = [p[0] for p in near], [p[1] for p in near]
    return max(xs) - min(xs), max(ys) - min(ys), radius


def slot_findings(pcb: layout.Board, refs: list[str]) -> list[str]:
    enc = spec.load("encoder")
    tab_w = enc["tab"]["width"]
    tab_t = enc["pcb"]["thickness"] + JLC_THIN_BOARD_TOL_MM
    problems = []
    for ref in refs:
        found = _slot_outline(pcb, ref)
        if found is None:
            problems.append(f"{ref}: no Edge.Cuts slot at the footprint")
            continue
        w, length, drawn_r = found
        r = max(drawn_r, JLC_MIN_SLOT_MM / 2)
        if w < JLC_MIN_SLOT_MM - 1e-6:
            problems.append(f"{ref}: slot {w:.2f} mm wide, below JLCPCB's {JLC_MIN_SLOT_MM} mm minimum non-plated slot")
        if w < tab_t - 1e-6:
            problems.append(
                f"{ref}: slot {w:.2f} mm wide for a {tab_t:.2f} mm thick encoder board (spec thickness + 0.1 mm)"
            )
        # the tab's corner (tab_w / 2, tab_t / 2) must lie inside the slot's rounded end
        cx, cy = length / 2 - r, w / 2 - r
        ex, ey = max(tab_w / 2 - cx, 0.0), max(tab_t / 2 - cy, 0.0)
        if tab_w > length or math.hypot(ex, ey) > r + 1e-6:
            problems.append(
                f"{ref}: a {length:.2f} x {w:.2f} mm slot with {r:.2f} mm milled corners does not take the "
                f"{tab_w} x {tab_t:.2f} mm encoder tab (spec/encoder.toml)"
            )
    return problems


@needs_kicad
@needs_pcb
def test_encoder_slots_take_the_encoder_tab():
    pcb = _placed("main")
    refs = sorted(r for r, f in pcb.footprints.items() if "EncoderSlot" in f.lib_id)
    assert refs, "no EncoderSlot footprints on the main board"
    problems = slot_findings(pcb, refs)
    assert not problems, "\n".join(problems)


# --- fab and assembly hygiene, every footprint --------------------------------------------------


def _assembled(board: str) -> list[layout.Footprint]:
    return [f for f in layout.load(board).footprints.values() if f.assembled and f.ref and not f.ref.startswith("#")]


@pytest.mark.parametrize("board", LAYOUT_BOARDS)
def test_every_assembled_footprint_has_a_courtyard(board):
    # IPC-7351 courtyard: KiCad's DRC checks courtyard overlap (and JLCPCB's placement spacing)
    # only for footprints that draw one on F.CrtYd/B.CrtYd.
    missing = sorted(f.ref for f in _assembled(board) if not (f.graphic_layers & layout.COURTYARD))
    assert not missing, f"no courtyard on F.CrtYd/B.CrtYd: {', '.join(missing)}"


@pytest.mark.parametrize("board", LAYOUT_BOARDS)
def test_every_smd_pad_of_an_assembled_part_has_paste(board):
    # Reflow assembly prints paste through the stencil (F.Paste/B.Paste); an SMD pad without a
    # paste opening is not soldered. A pad's own opening counts unless a negative paste margin
    # cancels it; a paste shape drawn on the footprint over the pad counts too (Q6, U2 draw theirs).
    missing = []
    for f in _assembled(board):
        bare = [p.number for p in f.pads if p.kind == "smd" and p.net and not f.pasted(p)]
        if bare:
            missing.append(f"{f.ref} pads {sorted(set(bare))}")
    assert not missing, f"SMD pads without paste: {'; '.join(missing)}"


@pytest.mark.parametrize("board", LAYOUT_BOARDS)
def test_every_assembled_footprint_has_an_embedded_3d_model(board):
    # The STEP and GLB outputs (make review) and MicrasHardware's import need every part's body;
    # models are embedded in the footprint (pcb embed-step), so they travel with the board.
    pcb = layout.load(board)
    problems = []
    for f in _assembled(board):
        if not f.models:
            problems.append(f"{f.ref}: no 3D model")
        for m in f.models:
            if m.startswith("kicad-embed://") and m.removeprefix("kicad-embed://") not in pcb.embedded_files:
                problems.append(f"{f.ref}: {m} is not embedded in the board")
    assert not problems, "\n".join(problems)


# --- silkscreen text ------------------------------------------------------------------------------

SILK_LAYERS = {"F.SilkS", "B.SilkS", "F.Silkscreen", "B.Silkscreen"}


def _hidden(node: sexpr.Node) -> bool:
    for n in (node, node.child("effects")):
        if n is None:
            continue
        if "hide" in n.atoms():
            return True
        h = n.child("hide")
        if h is not None and h.atoms()[:1] in ([], ["yes"]):
            return True
    return False


def _silk_texts(node: sexpr.Node, owner: str = ""):
    """(where, text, height, width, stroke) of every visible silkscreen text: board texts,
    footprint texts and footprint fields."""
    for child in node.children():
        if child.head == "footprint":
            yield from _silk_texts(child, child.prop("Reference") or "?")
        elif child.head in ("gr_text", "fp_text", "property"):
            layer = child.child("layer")
            font = child.child("effects") and child.child("effects").child("font")
            if layer is None or layer.atoms()[0] not in SILK_LAYERS or font is None or _hidden(child):
                continue
            h, w = (float(v) for v in font.child("size").atoms()[:2])
            t = float(font.child("thickness").atoms()[0]) if font.child("thickness") else h * 0.15
            text = child.atoms()[{"property": -1, "fp_text": 1}.get(child.head, 0)]
            where = f"{owner} " if owner else "board "
            yield where + child.head, text, h, w, t


# The board's silkscreen limits, written into its .kicad_pro: the height by Zener
# (<board>.zen Silkscreen), the stroke by `micras-pcb rules` (rules/kicad-severities.toml
# [design.<board>]). KiCad's stroke font draws a text's stroke at most a quarter of its smaller
# size, so the stroke that reaches the Gerbers is min(thickness, size / 4).
@pytest.mark.parametrize("board", ["main", "bluetooth"])
def test_silkscreen_text_meets_the_board_minimum(board):
    rules = json.loads((layout_dir(board) / f"{board}.kicad_pro").read_text())["board"]["design_settings"]["rules"]
    min_h, min_t = rules["min_text_height"], rules["min_text_thickness"]
    problems = []
    for where, text, h, w, t in _silk_texts(sexpr.parse(board_pcb(board).read_text())):
        stroke = min(t, min(h, w) / 4)
        if min(h, w) < min_h - 1e-6 or stroke < min_t - 1e-6:
            problems.append(f"{where} {text!r}: {h} x {w} mm, stroke {stroke:.3f} mm (minimum {min_h} mm, {min_t} mm)")
    assert not problems, "\n".join(problems)


def test_jlc_part_data_is_complete():
    # parts/jlc.toml: every entry carries what `make fab` and `make parts-online` need.
    raw = tomllib.loads((ROOT / "parts" / "jlc.toml").read_text())["parts"]
    problems = []
    for mpn, e in raw.items():
        if not str(e.get("lcsc", "")).startswith("C") or not str(e["lcsc"])[1:].isdigit():
            problems.append(f"{mpn}: lcsc {e.get('lcsc')!r} is not an LCSC number")
        if e.get("type") not in ("basic", "extended"):
            problems.append(f"{mpn}: type {e.get('type')!r}")
        if not isinstance(e.get("rotation", 0), int | float) or not isinstance(e.get("rotation_verified"), bool):
            problems.append(f"{mpn}: rotation / rotation_verified missing")
        if not e.get("source"):
            problems.append(f"{mpn}: no source")
    assert not problems, "\n".join(problems)
