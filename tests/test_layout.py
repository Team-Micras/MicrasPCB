"""Layout checks on every board: decoupling next to its pin, the encoder joint's slot, fab hygiene.

The placement-dependent checks skip, with the reason, while a board's layout has no outline: until
then the footprints sit where the netlist sync packed them, which says nothing about the design.
"""

import math
import shutil
import tomllib

import pytest
from micras_pcb import layout, spec
from micras_pcb.paths import ROOT, boards

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
]
# Not listed: the AS5047U in 3.3 V mode. Its datasheet (v1-00 p11, Figure 11) asks "close to chip"
# only for the 1 uF of the 5 V LDO mode; the 3.3 V mode drawing just shows 100 nF on VDD.
# The datasheets give no number for "close". This project reads it as: the capacitor's nearest pad
# centre within 3 mm of the pin's pad centre, which puts an 0402 beside the pin with one via (the
# previous main board's LSM6DSV capacitors sit 2.1-2.5 mm from the part).
MAX_DECOUPLING_MM = 3.0

LAYOUT_BOARDS = boards()


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
            problems.append(f"{ref}: slot {w:.2f} mm wide for a {tab_t:.2f} mm thick encoder board (0.8 mm + 0.1 mm)")
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
    # paste opening is not soldered.
    missing = []
    for f in _assembled(board):
        bare = [p.number for p in f.pads if p.kind == "smd" and p.net and not set(p.layers) & layout.PASTE]
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
