"""The JLCPCB order package: every assembled board fits JLCPCB's assembly line, alone or as its
panel; the panel keeps each board's outline, holds it by its blade's top edge only, and its BOM and
CPL place every part of every board; the order options are the board's.

JLCPCB PCB Assembly Capabilities (jlcpcb.com/capabilities/pcb-assembly-capabilities, accessed
2026-11-07), Economic PCBA: "Single PCB Size: 10x10mm - 470x500mm", "PCB Panel Size: 10x10mm -
250x250mm", "Delivery Format: Single PCB, Panel with mouse bites".
"""

import itertools
import math
import re
import shutil
import zipfile

import pytest
from micras_pcb import jlc, layout, order, panel, spec
from micras_pcb.paths import board_pcb, board_zen, layout_boards

from .conftest import needs_kicad

MIN_SIZE = 10.0
MAX_PANEL = 250.0
PANELS = [b for b in layout_boards() if panel.settings(b)]

needs_pcb = pytest.mark.skipif(shutil.which("pcb") is None, reason="pcb not installed")


def _size(box):
    x0, y0, x1, y1 = box
    return x1 - x0, y1 - y0


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Each panel board's panel, its CPL and the single board's CPL, as `micras-pcb fab` builds them."""
    out = {}
    for board in PANELS:
        d = tmp_path_factory.mktemp(board)
        rows, errors = jlc.jlc_bom(board)
        assert not errors, errors
        refs = {r for row in rows for r in row["Designator"].split(",")}
        pcbf = panel.build(board, d / "panel")
        out[board] = {
            "pcb_file": pcbf,
            "pcb": layout.load_file(pcbf),
            "refs": refs,
            "panel_cpl": jlc.cpl_rows(board, d, refs, pcbf),
            "cpl": jlc.cpl_rows(board, d, refs),
        }
    return out


@needs_kicad
@needs_pcb
@pytest.mark.parametrize("board", layout_boards())
def test_assembled_boards_fit_economic_pcba(board, built):
    rows, _ = jlc.jlc_bom(board)
    if not rows:
        pytest.skip(f"{board}: JLCPCB places no part")
    if spec.load(board)["pcb"]["assembly"] == "none":
        pytest.skip(f"{board}: not ordered with JLCPCB assembly (spec/{board}.toml pcb.assembly)")
    w, h = _size(layout.load(board).outline_box())
    if min(w, h) >= MIN_SIZE:
        return
    assert board in built, (
        f"{board}: {w:.2f} x {h:.2f} mm is under Economic PCBA's {MIN_SIZE:g} x {MIN_SIZE:g} mm single-board"
        f" minimum and spec/{board}.toml has no [panel]"
    )
    pw, ph = _size(built[board]["pcb"].outline_box())
    assert min(pw, ph) >= MIN_SIZE and max(pw, ph) <= MAX_PANEL, f"{board}: panel {pw:.2f} x {ph:.2f} mm"
    assert (round(pw, 2), round(ph, 2)) == pytest.approx(order.panel_size(board), abs=0.01), (
        "the order options' panel size (micras_pcb.order.panel_size) is not the built panel's"
    )


def _offsets(board, built):
    """Per panel board n: the CPL's offset of each part from its place on the single board."""
    single = {r["Designator"]: r for r in built[board]["cpl"]}
    xy = lambda r: (float(r["Mid X"][:-2]), float(r["Mid Y"][:-2]))  # noqa: E731
    out = {}
    for r in built[board]["panel_cpl"]:
        ref, n = panel.split_ref(r["Designator"])
        s = single[ref]
        assert (r["Rotation"], r["Layer"]) == (s["Rotation"], s["Layer"]), (
            f"{r['Designator']}: rotation/layer {r['Rotation']}/{r['Layer']}, on the board {s['Rotation']}/{s['Layer']}"
        )
        (px, py), (sx, sy) = xy(r), xy(s)
        out.setdefault(n, {})[ref] = (px - sx, py - sy)
    return out


@needs_kicad
@needs_pcb
@pytest.mark.parametrize("board", PANELS)
def test_panel_cpl_places_every_part_of_every_board(board, built):
    b = built[board]
    n = panel.settings(board)["columns"]
    names = [r["Designator"] for r in b["panel_cpl"]]
    want = sorted(panel.copy_ref(ref, k) for ref in b["refs"] for k in range(n))
    assert sorted(names) == want, "the panel's CPL must hold each placed part once per board"
    offsets = _offsets(board, built)
    p = panel.settings(board)
    w, _ = _size(layout.load(board).outline_box())
    first = None
    for k in range(n):
        moves = set(offsets[k].values())
        spread = max(math.dist(a, c) for a in moves for c in moves)
        assert spread < 1e-3, f"board {k} of the panel: its parts moved apart from their places ({moves})"
        dx, dy = next(iter(moves))
        if first is None:
            first = (dx, dy)
        assert (dx - first[0], dy - first[1]) == pytest.approx((k * (w + p["board_spacing"]), 0.0), abs=1e-3)


def _dist_to_shape(pt, shape):
    kind, pts, _ = shape
    if kind == "gr_arc":
        a, m, c = pts[:3]
        arc = layout.arc_points(a, m, c, 256)
        return min(_dist_to_segment(pt, p, q) for p, q in itertools.pairwise(arc))
    return _dist_to_segment(pt, pts[0], pts[1])


def _dist_to_segment(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _samples(shape, n=24):
    kind, pts, _ = shape
    if kind == "gr_arc":
        return layout.arc_points(*pts[:3], n)
    (ax, ay), (bx, by) = pts[:2]
    return [(ax + (bx - ax) * i / n, ay + (by - ay) * i / n) for i in range(n + 1)]


@needs_kicad
@needs_pcb
@pytest.mark.parametrize("board", PANELS)
def test_panel_keeps_each_board_outline_but_its_top_tab(board, built):
    """Every point of the board's outline (spec/<board>.toml [outline], drawn by micras-pcb mech) is
    on the panel's outline, moved to its board's place, but where the tab meets the blade's top edge:
    no tab or bridge anywhere else, the handle's bottom edge and the header's pads free."""
    b, p = built[board], panel.settings(board)
    single = layout.load(board)
    x0, y0, x1, _ = single.outline_box()
    cx = (x0 + x1) / 2
    half_tab = p["tab_width"] / 2 + p["mill_radius"]
    pts = [q for s in single.edge_shapes for q in _samples(s)]
    shapes = b["pcb"].edge_shapes
    ref = sorted(b["refs"])[0]
    for k in range(p["columns"]):
        fp, pfp = single.footprints[ref].xy, b["pcb"].footprints[panel.copy_ref(ref, k)].xy
        dx, dy = pfp[0] - fp[0], pfp[1] - fp[1]
        off = []
        for x, y in pts:
            if abs(y - y0) < 1e-6 and abs(x - cx) <= half_tab + 1e-6:
                continue  # where the tab meets the top edge
            d = min(_dist_to_shape((x + dx, y + dy), s) for s in shapes)
            if d > 0.002:
                off.append(((round(x, 3), round(y, 3)), round(d, 4)))
        assert not off, f"{board}, panel board {k}: outline points off the panel's outline (point, mm): {off[:8]}"


@needs_kicad
@needs_pcb
@pytest.mark.parametrize("board", PANELS)
def test_panel_outline_is_closed(board, built):
    """Closed loops only: a tab KiKit put anywhere but the top edge would end on a board's redrawn
    outline (micras_pcb.panel.exact_outlines) and leave a T-joint."""
    assert not panel.open_ends(built[board]["pcb"])


@needs_kicad
@needs_pcb
@pytest.mark.parametrize("board", PANELS)
def test_mouse_bites_only_on_the_blade_top(board, built):
    """JLCPCB's mouse bites (spec [panel]) on each board's top edge, inside the outline, over the tab."""
    b, p = built[board], panel.settings(board)
    w, _ = _size(layout.load(board).outline_box())
    bites = [f for r, f in b["pcb"].footprints.items() if r.startswith("KiKit_MB")]
    holes = sorted(f.xy for f in bites)
    assert len(holes) >= p["columns"] * math.floor(p["tab_width"] / p["mousebite_pitch"])
    for f in bites:
        assert f.pads[0].size[0] == pytest.approx(p["mousebite_drill"])
    pb = b["pcb"]
    px0, py0, _, _ = pb.outline_box()
    top = py0 + p["frame_width"] + p["board_spacing"]  # the boards' top edges on the panel
    centres = [
        px0 + p["frame_width"] + p["board_spacing"] + w / 2 + k * (w + p["board_spacing"]) for k in range(p["columns"])
    ]
    for x, y in holes:
        assert y == pytest.approx(top + p["mousebite_offset"], abs=1e-3), f"mouse bite at ({x}, {y}): not on a top edge"
        assert min(abs(x - c) for c in centres) <= p["tab_width"] / 2 + p["mill_radius"] + 1e-3, (
            f"mouse bite at ({x}, {y}): beyond the tab"
        )
    pitches = [q[0] - h[0] for h, q in itertools.pairwise(holes) if q[0] - h[0] < 2]
    assert all(p["mousebite_pitch"] - 1e-3 <= d <= p["mousebite_pitch"] + 0.1 for d in pitches), pitches


# The JLCPCB via option: PCB Capabilities (Drilling, accessed 2026-11-07), "0.1mm or 0.15mm hole size
# with any size via diameter, and 0.2mm or 0.25mm hole size with via diameter less than 0.45mm, will
# cost more".
@pytest.mark.parametrize(
    ("drill", "diameter", "option"),
    [
        (0.3, 0.6, "0.3mm/(0.4/0.45mm)"),
        (0.3, 0.4, "0.3mm/(0.4/0.45mm)"),
        (0.2, 0.45, "0.3mm/(0.4/0.45mm)"),
        (0.25, 0.4, "0.25mm/(0.35/0.4mm)"),
        (0.2, 0.35, "0.2mm/(0.3/0.35mm)"),
        (0.15, 0.6, "0.15mm/(0.25/0.3mm)"),
    ],
)
def test_via_class_follows_jlcpcbs_surcharge_rule(drill, diameter, option):
    assert order.via_class(drill, diameter) == option


@pytest.mark.parametrize("board", layout_boards())
def test_spec_via_class_is_the_boards_smallest_via(board):
    s = spec.load(board)["pcb"]
    recorded = (s["via_drill"], s["via_diameter"])
    actual = order.smallest_via(board)
    assert recorded == pytest.approx(actual), (
        f"spec/{board}.toml pcb.via_drill/via_diameter {recorded} but the layout's smallest via is {actual}"
        f" (JLCPCB option {order.via_class(*actual)}): update the spec, the order and the quote follow it"
    )


@pytest.mark.parametrize("board", layout_boards())
def test_order_options_are_the_zener_stackup(board):
    """The finish and colours the order and quote use are the board's stackup, which Zener's
    Board() writes when it sets them."""
    st = order.stackup(board)
    zen = board_zen(board).read_text()
    for field, key in (("copper_finish", "finish"), ("solder_mask_color", "mask"), ("silk_screen_color", "silk")):
        m = re.search(rf'{field}\s*=\s*"([^"]+)"', zen)
        if m:
            assert st[key] == m.group(1), f"{board}: {board_pcb(board).name} has {key} {st[key]}, the .zen {m.group(1)}"
    o = order.options(board)
    assert o["finish"] in order.JLC_FINISH and o["mask"] in order.JLC_COLOURS


# Every board takes leaded HASL (the owner, 2026-11-07: the v1 main board, with the same VFQFPN68 MCU
# and LGA IMU, was ordered with HASL at JLCPCB and worked).
FINISH = "HAL SnPb"


@pytest.mark.parametrize("board", layout_boards())
def test_every_board_is_leaded_hasl(board):
    assert order.stackup(board)["finish"] == FINISH, (
        f"{board}: finish {order.stackup(board)['finish']!r}, every Micras board takes {FINISH!r} (leaded HASL)"
    )


# --- paste: JLCPCB prints none on the parts the team solders itself ---------------------------------
#
# JLCPCB prints paste through every stencil opening, so a hand part's pads would come back with
# reflowed solder on them. `make fab` plots the JLCPCB package's paste from a copy of the board (or
# panel) without the hand parts' paste, and writes the hand parts' paste alone as the team's stencil.

_COORD = re.compile(r"(?:X(-?\d+))?(?:Y(-?\d+))?(?:I-?\d+J-?\d+)?D0?([123])\*")


def _gerber_features(text: str) -> list[list[tuple[float, float]]]:
    """Each flash (one point) and each region or stroke (its vertices), in gerber mm."""
    fs = re.search(r"%FSLAX(\d)(\d)Y(\d)(\d)\*%", text)
    assert fs and "%MOMM*%" in text, "expected a metric KiCad gerber"
    scale = 10 ** int(fs.group(2))
    feats, region, path, x, y = [], False, [], 0.0, 0.0
    for line in text.splitlines():
        if line.startswith("G36"):
            region, path = True, []
            continue
        if line.startswith("G37"):
            feats.append(path)
            region, path = False, []
            continue
        m = _COORD.search(line)
        if not m or line.startswith("%"):
            continue
        x = int(m.group(1)) / scale if m.group(1) else x
        y = int(m.group(2)) / scale if m.group(2) else y
        op = m.group(3)
        if op == "3":
            feats.append([(x, y)])
        elif region:
            path.append((x, y))
        elif op == "2":
            path = [(x, y)]
        else:
            path.append((x, y))
            feats.append(list(path))
    return feats


def _paste_points(zpath, origin) -> list[list[tuple[float, float]]]:
    """The paste features of both faces' gerbers in the zip, in the board's KiCad frame (y down)."""
    ox, oy = origin
    out = []
    with zipfile.ZipFile(zpath) as z:
        for name in z.namelist():
            if "_Paste." in name:
                out += [[(ox + gx, oy - gy) for gx, gy in f] for f in _gerber_features(z.read(name).decode())]
    return out


def _in_pad(pt, pad, tol=0.005) -> bool:
    t = math.radians(-pad.angle)
    dx, dy = pt[0] - pad.xy[0], pt[1] - pad.xy[1]
    lx, ly = dx * math.cos(t) + dy * math.sin(t), -dx * math.sin(t) + dy * math.cos(t)
    return abs(lx) <= pad.size[0] / 2 + tol and abs(ly) <= pad.size[1] / 2 + tol


def _hits(feats, pad) -> bool:
    """A paste feature lies on the pad: a flash on it, or a region's vertex or centre inside it."""
    for f in feats:
        cx, cy = sum(p[0] for p in f) / len(f), sum(p[1] for p in f) / len(f)
        if any(_in_pad(p, pad, -0.005) for p in [*f, (cx, cy)]):
            return True
    return False


def _origin(pcb_file):
    m = re.search(r"\(aux_axis_origin (-?[\d.]+) (-?[\d.]+)\)", pcb_file.read_text())
    return (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)


def _copper_pads(fp):
    return [p for p in fp.pads if set(p.layers) & {"F.Cu", "B.Cu", "*.Cu"} and min(p.size) > 0]


@pytest.fixture(scope="module")
def paste_fab(tmp_path_factory, built):
    """Per board with hand parts: the JLCPCB gerbers of the board, and of its panel if it has one,
    and the team's stencil, as `micras-pcb fab` writes them (built on first use)."""
    cache = {}

    def get(board):
        if board in cache:
            return cache[board]
        hand = jlc.hand_refs(board)
        if not hand:
            pytest.skip(f"{board}: no part is soldered by hand")
        d = tmp_path_factory.mktemp(f"{board}-paste")
        rows, _ = jlc.jlc_bom(board)
        jlc_refs = {r for row in rows for r in row["Designator"].split(",")}
        entry = {
            "hand": hand,
            "single": (jlc.gerbers(board, d / "single", hand), board_pcb(board), layout.load(board), hand, jlc_refs),
            "stencil": jlc.team_stencil(board, d / "stencil", hand),
        }
        if board in built:
            n = panel.settings(board)["columns"]
            pf = built[board]["pcb_file"]
            hand_copies = {panel.copy_ref(r, k) for r in hand for k in range(n)}
            jlc_copies = {panel.copy_ref(r, k) for r in jlc_refs for k in range(n)}
            entry["panel"] = (
                jlc.gerbers(pf, d / "panel", hand_copies),
                pf,
                built[board]["pcb"],
                hand_copies,
                jlc_copies,
            )
        cache[board] = entry
        return entry

    return get


def _variants(entry):
    return [entry["single"], *([entry["panel"]] if "panel" in entry else [])]


@needs_kicad
@needs_pcb
@pytest.mark.parametrize("board", layout_boards())
def test_jlc_paste_skips_the_hand_parts(board, paste_fab):
    for zpath, pcbf, pcb, hand, jlc_refs in _variants(paste_fab(board)):
        feats = _paste_points(zpath, _origin(pcbf))
        pasted_hand = sorted(
            f"{ref}.{p.number}"
            for ref in hand
            if ref in pcb.footprints
            for p in _copper_pads(pcb.footprints[ref])
            if _hits(feats, p)
        )
        assert not pasted_hand, f"{zpath.name}: JLCPCB's paste covers pads of hand-soldered parts: {pasted_hand}"
        missing = sorted(
            ref
            for ref in jlc_refs
            if ref in pcb.footprints
            and any(pcb.footprints[ref].pasted(p) for p in _copper_pads(pcb.footprints[ref]))
            and not any(_hits(feats, p) for p in _copper_pads(pcb.footprints[ref]) if pcb.footprints[ref].pasted(p))
        )
        assert not missing, f"{zpath.name}: no paste on JLCPCB-placed parts {missing}"


@needs_kicad
@needs_pcb
@pytest.mark.parametrize("board", layout_boards())
def test_team_stencil_has_exactly_the_hand_parts(board, paste_fab):
    e = paste_fab(board)
    pcb, pcbf = layout.load(board), board_pcb(board)
    pasted = lambda ref: any(pcb.footprints[ref].pasted(p) for p in _copper_pads(pcb.footprints[ref]))  # noqa: E731
    want = sorted(ref for ref in e["hand"] if ref in pcb.footprints and pasted(ref))
    if not want:
        assert e["stencil"] is None, f"{board}: a team stencil with no hand part to paste"
        return
    assert e["stencil"] is not None and e["stencil"].name == f"{board}-team-stencil.zip"
    with zipfile.ZipFile(e["stencil"]) as z:
        assert any("Edge_Cuts" in n for n in z.namelist()), "the team stencil has no outline to align it"
    feats = _paste_points(e["stencil"], _origin(pcbf))
    got = sorted(ref for ref, fp in pcb.footprints.items() if any(_hits(feats, p) for p in _copper_pads(fp)))
    assert got == want, f"{board}: the team stencil pastes {got}, the hand parts with paste are {want}"


@pytest.mark.parametrize(
    ("kicad", "offset", "bottom", "want"),
    [
        (0, 0, False, 0),
        (-90, 270, False, 180),  # IC8: KiCad -90 with the DRV8874's 270 offset
        (90, 180, False, 270),  # U12
        (0, 0, True, 180),  # the wall board's Q1 and D1 (JLC preview, 2026-11-08)
        (90, 0, True, 90),
        (90, 90, True, 0),
    ],
)
def test_cpl_rotation_turns_bottom_parts_the_other_way(kicad, offset, bottom, want):
    """jlc_rotation: top parts add the offset; bottom parts, which JLCPCB mirrors, take 180 minus both."""
    assert jlc.jlc_rotation(kicad, offset, bottom) == want
