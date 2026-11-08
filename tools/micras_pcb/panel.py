"""Assembly panels: a board too small for JLCPCB's assembly line, repeated in a frame with KiKit.

A board whose spec has a [panel] section (spec/wall.toml) is ordered as that panel: `micras-pcb
fab` builds it into build/<board>/fab/panel/<board>-panel.kicad_pcb and writes the JLCPCB package
from it. The boards stand side by side, upright, as many as `columns`, `board_spacing` apart in a
frame `frame_width` wide; each hangs from the frame by one mouse-bite tab on the middle of its top
edge (tools/micras_pcb/kikit_tabs.py) and touches nothing else. KiKit renames each copy's parts
`<ref>_<n>` and their nets `Board_<n>-<net>`, n counting the boards from 0 (KiKit's
numbering). The drill/place origin is the panel's bottom-left corner.

KiKit draws the panel's outline from polygons, arcs as chords of 1/128 turn (3 um off the wall
board's 8.8 mm neck arcs; its arc reconstruction is worse, 15 um): `build` then puts back each
board's own Edge.Cuts items, moved to its place, the top edge cut where the tab meets it, so every
board keeps its outline exactly (tests/test_fab.py).
"""

from __future__ import annotations

import itertools
import math
import re
import subprocess
from pathlib import Path

from . import layout, mech, sexpr, spec
from .paths import ROOT, board_pcb
from .tools import kikit

TABS_PLUGIN = Path(__file__).with_name("kikit_tabs.py")
REF = "{orig}_{n}"
_COPY = re.compile(r"^(?P<ref>.+)_(?P<n>\d+)$")


def settings(board: str) -> dict | None:
    """The board's [panel] spec values, or None for a board ordered alone."""
    return spec.load(board).get("panel")


def copy_ref(ref: str, n: int) -> str:
    """The designator of part `ref` on the panel's board n (0 to columns - 1)."""
    return REF.format(orig=ref, n=n)


def split_ref(panel_ref: str) -> tuple[str, int] | None:
    """(board ref, board number) of a panel designator, None for the panel's own parts."""
    m = _COPY.match(panel_ref)
    return (m["ref"], int(m["n"])) if m else None


def kikit_args(board: str) -> list[str]:
    """`kikit panelize` options for the board's [panel] spec."""
    p = settings(board)
    if p is None:
        raise ValueError(f"spec/{board}.toml has no [panel]")
    mm = lambda v: f"{v}mm"  # noqa: E731
    return [
        "--layout",
        f"grid; rows: 1; cols: {p['columns']}; space: {mm(p['board_spacing'])}; renameref: {REF}",
        "--tabs",
        f"plugin; code: {TABS_PLUGIN}.TopTab; arg: {p['tab_width']}; fillet: 0mm",
        "--cuts",
        f"mousebites; drill: {mm(p['mousebite_drill'])}; spacing: {mm(p['mousebite_pitch'])};"
        f" offset: {mm(p['mousebite_offset'])}; prolong: {mm(p['mill_radius'])}",
        "--framing",
        f"frame; width: {mm(p['frame_width'])}; space: {mm(p['board_spacing'])}; cuts: none",
        "--tooling",
        f"3hole; hoffset: {mm(p['tooling_offset'])}; voffset: {mm(p['tooling_offset'])}; size: {mm(p['tooling_hole'])}",
        "--fiducials",
        f"3fid; hoffset: {mm(p['fiducial_inset'])}; voffset: {mm(p['tooling_offset'])};"
        f" coppersize: {mm(p['fiducial'])}; opening: {mm(p['fiducial_opening'])}",
        "--post",
        "origin: bl; reconstructarcs: false; refillzones: true",
        "--debug",
        "deterministic: true",
    ]


def build(board: str, out: Path) -> Path:
    """Panelise the board's layout into out/<board>-panel.kicad_pcb (a KiCad project of its own)."""
    out.mkdir(parents=True, exist_ok=True)
    pcb = out / f"{board}-panel.kicad_pcb"
    run = subprocess.run(
        [*kikit(), "panelize", *kikit_args(board), str(board_pcb(board)), str(pcb)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if run.returncode != 0 or not pcb.is_file():
        raise RuntimeError(f"kikit panelize failed for {board}:\n{run.stdout}{run.stderr}")
    exact_outlines(board, pcb)
    return pcb


def _on(pt: tuple[float, float], e, tol: float) -> bool:
    """The point lies on outline element e (a mech Line or Arc) within tol."""
    pts = layout.arc_points(e.a, e.mid, e.b, 128) if isinstance(e, mech.Arc) else [e.a, e.b]
    for (ax, ay), (bx, by) in itertools.pairwise(pts):
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((pt[0] - ax) * dx + (pt[1] - ay) * dy) / L))
        if math.hypot(pt[0] - ax - t * dx, pt[1] - ay - t * dy) <= tol:
            return True
    return False


def exact_outlines(board: str, pcb: Path, tol: float = 0.01) -> int:
    """Replace KiKit's chords of each board's outline in the panel by the board's own Edge.Cuts
    items, moved to the board's place; the top edge stops where the tab meets it. Returns how many
    items it drew."""
    p = settings(board)
    single = layout.load(board)
    x0, y0, x1, _ = single.outline_box()
    cx, half = (x0 + x1) / 2, p["tab_width"] / 2
    ident = lambda _s, q: q  # noqa: E731
    own = mech.outline_elements({}, sexpr.parse(board_pcb(board).read_text()), to=ident)
    text = pcb.read_text()
    root = sexpr.parse(text)
    placed = layout.parse(text)
    ref = min(r for r, f in single.footprints.items() if f.pads)
    copies = []
    for k in range(p["columns"]):
        f, g = single.footprints[ref], placed.footprints[copy_ref(ref, k)]
        if abs(f.rotation - g.rotation) > 1e-6:
            raise RuntimeError(f"{board}: the panel turned board {k}; exact_outlines places boards upright only")
        dx, dy = g.xy[0] - f.xy[0], g.xy[1] - f.xy[1]
        move = lambda q, dx=dx, dy=dy: (q[0] + dx, q[1] + dy)  # noqa: E731
        els = []
        for e in own:
            if isinstance(e, mech.Line) and abs(e.a[1] - y0) < 1e-6 and abs(e.b[1] - y0) < 1e-6:
                # the top edge, cut by the tab: from each end to the tab's side nearer it
                for end in (e.a, e.b):
                    side = cx - half if end[0] < cx else cx + half
                    els.append(mech.Line(move(end), move((side, y0))))
            elif isinstance(e, mech.Arc):
                els.append(mech.Arc(move(e.a), move(e.mid), move(e.b)))
            else:
                els.append(mech.Line(move(e.a), move(e.b)))
        copies.append(els)
    every = [e for els in copies for e in els]
    edits = []
    for n in mech.edge_items(root):
        ends = [mech._xy_of(n.child(c)) for c in ("start", "mid", "end") if n.child(c)]
        if n.head == "gr_line":
            ends.append(((ends[0][0] + ends[1][0]) / 2, (ends[0][1] + ends[1][1]) / 2))
        if all(any(_on(q, e, tol) for e in every) for q in ends):
            edits.append((*sexpr.line_span(text, n), ""))
    items = "".join(
        mech._edge_item({}, e, f"panel/{k}/{j}", to=ident) for k, els in enumerate(copies) for j, e in enumerate(els)
    )
    close = text.rstrip().rfind(")")
    edits.append((close, close, items))
    pcb.write_text(sexpr.splice(text, edits))
    loose = open_ends(layout.load_file(pcb))
    if loose:
        raise RuntimeError(f"{board}: the panel's outline is open at {loose[:6]}: a tab or cut where none belongs?")
    return len(every)


def open_ends(pcb: layout.Board, digits: int = 4) -> list[tuple[float, float]]:
    """Edge.Cuts end points not shared by exactly two items: the outline's breaks and T-joints."""
    ends: dict[tuple[float, float], int] = {}
    for kind, pts, _ in pcb.edge_shapes:
        if kind in ("gr_circle", "gr_rect", "gr_poly"):
            continue
        for q in (pts[0], pts[2] if kind == "gr_arc" else pts[1]):
            key = (round(q[0], digits), round(q[1], digits))
            ends[key] = ends.get(key, 0) + 1
    return sorted(q for q, c in ends.items() if c != 2)
