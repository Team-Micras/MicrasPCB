"""The wall sensors fully on the board, as a one-off pcbnew script (KiCad 10). DRAFT: not run yet.

    python3 boards/main/layout/wall_inside.py --study                 # numbers only, writes nothing
    python3 boards/main/layout/wall_inside.py --study --pcb COPY      # the same on another copy
    python3 boards/main/layout/wall_inside.py [--option inward|back]  # apply (default: inward)

The bare WallSensor footprint (components/micras/WallSensor: SFH 4550 over TPS601A, no casing)
has a courtyard: both bodies at their largest plus the pads, with 0.25 mm excess. A sensor is on
the board when that courtyard keeps the 0.20 mm board-edge clearance of rules/jlcpcb.kicad_dru
from the Edge.Cuts outline. W2 and W3 (front, 45 degrees) already do, 0.21 mm inside, and stay
(W2's courtyard overlaps C74 and R17 there); W1 and W4 (side chamfers, looking forward) do not: the chamfer runs at 63.4 degrees to their look direction, so moving back
along it gains 0.447 mm of edge clearance per mm and moving inwards 0.894 mm per mm. OPTIONS sets
the inward shift (mirrored on W1 and W4, robot y towards 0); the script computes the least backward
move that puts the courtyard inside, rounded up to 0.01 mm. Every inward/back pair it allows sits
the same distance from the chamfer, so the beams are the same for all of them (--study prints
them: the board blocks none of either cone).

The steps, in order:
- footprints: `pcb layout --sync-footprints` takes the bare footprint into W1-W4, then every other
  footprint gets its text back (the sync re-issues the UUID of every footprint graphic on the board,
  and D4/D5 differ from their library footprints), so the diff is W1-W4 and the embedded STEP;
- move: W1 and W4 to OPTIONS; their tracks to the old pads go, and so does other-net copper that
  the new pads would touch;
- neighbours: NEIGHBOURS re-places the parts the new courtyards overlap (filled in when this runs,
  on the layout of the time: --study lists them);
- check: stops without saving while a wall-sensor courtyard leaves the outline or overlaps another
  courtyard;
then router.py reconnects the nets whose copper went (ROUTES), the moved parts' designators take
free spots (usb_wall.silkscreen's method), the zones are refilled, the board saved and `pcb layout`
syncs it.
"""

from __future__ import annotations

import math
import random
import re
import subprocess
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))
import fixes as fx  # noqa: E402
from micras_pcb import sexpr  # noqa: E402

LAYOUT = ROOT / "boards/main/layout/main.kicad_pcb"
LIB = ROOT / "components/micras/WallSensor"
FOOTPRINT = "WallSensor_SFH4550_TPS601A_THT"
WALLS = ("W1", "W2", "W3", "W4")
EDGE = 0.20  # rules/jlcpcb.kicad_dru "jlc: copper to board edge"
CU_CLEAR = 0.20  # the new pads' holes to other copper (fixes.CU_GAP)
# Lens tips in the footprint frame (the sensor looks along -y), optical axis height above the board top
# and half angle (WallSensor.zen; SFH 4550 v1.9 p.5, TPS601A(F) p.2).
BEAMS = {"emitter": ((0.0, -6.28), 9.75, 3.0), "receiver": ((0.0, -6.055), 3.25, 10.0)}
# Inward shift of W1 and W4 (mm). back: along the look direction, plus the 0.3 mm W4's TPS601A key tab
# needs from the side edge (its courtyard is 3.57 mm wide on that side), mirrored on W1; inward: the
# side sensors move towards the middle and 0.46 mm back, clear of P1 (SWD) and SW1 (DIP switch).
OPTIONS = {"back": 0.3, "inward": 3.3}
MOVE = ("W1", "W4")
# ref -> (x, y, rotation) for the parts the new courtyards overlap; filled in when this script runs.
NEIGHBOURS: dict[str, tuple[float, float, float]] = {}
AXLE = (148.5011, 113.5036)  # spec/main.toml [kicad] origin: robot x = AXLE_y - y, robot y = AXLE_x - x


# --- footprints -----------------------------------------------------------------------------------


def pcb_layout(*flags: str) -> None:
    env = dict(
        line.split("=", 1)
        for line in (ROOT / "versions.env").read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    subprocess.run(
        ["pcb", f"+{env['PCB_TOOLCHAIN'].strip()}", "layout", *flags, "--no-open", "boards/main/main.zen"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )


def _footprints(text: str) -> dict[str, sexpr.Node]:
    return {n.prop("Reference"): n for n in sexpr.parse(text).children("footprint")}


def footprints() -> None:
    """The bare WallSensor footprint into W1-W4, every other footprint as it was."""
    before = LAYOUT.read_text()
    pcb_layout("--sync-footprints")
    after = LAYOUT.read_text()
    old, new = _footprints(before), _footprints(after)
    if set(old) != set(new):
        raise SystemExit(f"the footprint sync changed the parts: {sorted(set(old) ^ set(new))}")
    uuid = re.compile(r'\(uuid "[^"]+"\)')
    edits, drift = [], []
    for ref, n in new.items():
        if ref in WALLS:
            continue
        was = before[old[ref].start : old[ref].end]
        now = after[n.start : n.end]
        if was != now:
            edits.append((n.start, n.end, was))
            if uuid.sub("", was) != uuid.sub("", now):
                drift.append(ref)
    LAYOUT.write_text(sexpr.splice(after, edits))
    if drift:
        print("kept as they were (they differ from their library footprints):", ", ".join(sorted(drift)))


# --- geometry -------------------------------------------------------------------------------------

_lib = None


def courtyard(ref: str, at: tuple[float, float]) -> pcbnew.SHAPE_POLY_SET:
    """The bare footprint's courtyard with ref's orientation at `at`."""
    global _lib
    if _lib is None:
        _lib = pcbnew.FootprintLoad(str(LIB), FOOTPRINT)
    f = fx.fp(ref)
    _lib.SetOrientation(f.GetOrientation())
    _lib.SetPosition(fx.pt(*at))
    _lib.BuildCourtyardCaches()
    return pcbnew.SHAPE_POLY_SET(_lib.GetCourtyard(pcbnew.F_CrtYd))


def _vertices(poly: pcbnew.SHAPE_POLY_SET) -> list:
    o = poly.Outline(0)
    return [o.CPoint(i) for i in range(o.PointCount())]


def edge_margin(poly: pcbnew.SHAPE_POLY_SET) -> float:
    """Least distance of the polygon to the board edge, negative where it is outside."""
    outline = fx._board_outline()
    m = math.inf
    for p in _vertices(poly):
        d = min(pcbnew.ToMM(s.Distance(p)) for s in fx._edge_segments())
        m = min(m, d if outline.Contains(p) else -d)
    for s in fx._edge_segments():  # an outline corner inside the polygon
        if poly.Contains(s.A):
            m = min(m, -0.001)
    return m


def look(ref: str) -> tuple[float, float]:
    """The look direction on the sheet (footprint -y)."""
    t = math.radians(fx.fp(ref).GetOrientationDegrees())
    return -math.sin(t), -math.cos(t)


def local(ref: str, at: tuple[float, float], p: tuple[float, float]) -> tuple[float, float]:
    t = math.radians(fx.fp(ref).GetOrientationDegrees())
    return at[0] + p[0] * math.cos(t) + p[1] * math.sin(t), at[1] - p[0] * math.sin(t) + p[1] * math.cos(t)


def target(ref: str, inward: float) -> tuple[float, float]:
    """W1/W4 shifted `inward` towards the middle and back by the least move (0.01 mm steps) that puts
    the courtyard EDGE inside the outline."""
    x, y = fx.xy(fx.fp(ref).GetPosition())
    x += inward if x < AXLE[0] else -inward
    bx, by = -look(ref)[0], -look(ref)[1]
    lo, hi = 0.0, 15.0
    if edge_margin(courtyard(ref, (x, y))) >= EDGE:
        return round(x, 4), round(y, 4)
    if edge_margin(courtyard(ref, (x + hi * bx, y + hi * by))) < EDGE:
        raise SystemExit(f"{ref}: no backward move up to {hi} mm fits with {inward} mm inwards")
    while hi - lo > 0.001:
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if edge_margin(courtyard(ref, (x + mid * bx, y + mid * by))) >= EDGE else (mid, hi)
    d = math.ceil(hi * 100) / 100
    return round(x + d * bx, 4), round(y + d * by, 4)


def axis_to_edge(apex: tuple[float, float], d: tuple[float, float]) -> float:
    outline = fx._board_outline()
    s = 0.0
    while outline.Contains(fx.pt(apex[0] + d[0] * s, apex[1] + d[1] * s)):
        s += 0.01
    return s


def cone_on_board(apex, h: float, half: float, d, n: int = 20000) -> float:
    """Share of a cone (uniform in solid angle, horizontal axis d, apex h above the board top) whose
    rays land on the board top inside the outline."""
    outline = fx._board_outline()
    rng = random.Random(1)
    c0, hit = math.cos(math.radians(half)), 0
    for _ in range(n):
        cz = 1 - rng.random() * (1 - c0)
        s = math.sqrt(1 - cz * cz)
        ph = rng.random() * 2 * math.pi
        down = s * math.sin(ph)
        if down >= 0:
            continue
        t = h / -down
        if t > 200:  # lands far beyond the board
            continue
        side = s * math.cos(ph)
        g = (apex[0] + (d[0] * cz - d[1] * side) * t, apex[1] + (d[1] * cz + d[0] * side) * t)
        hit += outline.Contains(fx.pt(*g))
    return hit / n


def robot(p: tuple[float, float]) -> tuple[float, float]:
    return round(AXLE[1] - p[1], 4), round(AXLE[0] - p[0], 4)


# --- what a placement touches -----------------------------------------------------------------------


def overlaps(ref: str, poly: pcbnew.SHAPE_POLY_SET) -> list[str]:
    out = []
    for g in fx.B.GetFootprints():
        if g.GetReference() == ref:
            continue
        for lay in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            c = g.GetCourtyard(lay)
            if not c.OutlineCount():
                continue
            i = pcbnew.SHAPE_POLY_SET(poly)
            i.BooleanIntersection(c)
            if i.OutlineCount() and i.Area() > 1e8:  # 1e-4 mm2
                out.append(g.GetReference())
    return sorted(set(out))


def copper_hits(ref: str) -> list:
    """Tracks and vias of other nets within CU_CLEAR of ref's pads, and other parts' pads."""
    f = fx.fp(ref)
    tracks, pads = [], []
    for p in f.Pads():
        for lay in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
            sh = p.GetEffectiveShape(lay)
            for t in fx.B.GetTracks():
                if t.GetNetname() == p.GetNetname() or t in tracks:
                    continue
                if t.GetClass() != "PCB_VIA" and t.GetLayer() != lay:
                    continue
                if sh.Collide(t.GetEffectiveShape(lay), fx.mm(CU_CLEAR)):
                    tracks.append(t)
            for g in fx.B.GetFootprints():
                if g.GetReference() == ref:
                    continue
                for q in g.Pads():
                    other = q.GetNetname() != p.GetNetname() and q.IsOnLayer(lay)
                    if other and sh.Collide(q.GetEffectiveShape(lay), fx.mm(CU_CLEAR)):
                        pads.append(f"{g.GetReference()}.{q.GetNumber()}")
    return tracks + sorted(set(pads))


def own_copper(ref: str) -> list:
    """ref's own-net tracks and vias with an end on one of its pads."""
    f = fx.fp(ref)
    out = []
    for p in f.Pads():
        for t in fx.B.GetTracks():
            if t.GetNetname() != p.GetNetname():
                continue
            ends = [t.GetPosition()] if t.GetClass() == "PCB_VIA" else [t.GetStart(), t.GetEnd()]
            if any(p.HitTest(e) for e in ends) and t not in out:
                out.append(t)
    return out


# --- study ----------------------------------------------------------------------------------------


def study(option: str) -> dict[str, tuple[float, float]]:
    moves = {}
    for ref in WALLS:
        f = fx.fp(ref)
        now = fx.xy(f.GetPosition())
        at = target(ref, OPTIONS[option]) if ref in MOVE else now
        moves[ref] = at
        d = look(ref)
        print(f"== {ref}: ({now[0]:.4f}, {now[1]:.4f}) rotation {f.GetOrientationDegrees():g}")
        print(f"   courtyard to the edge now {edge_margin(courtyard(ref, now)):+.3f} mm")
        if at != now:
            back = (at[0] - now[0]) * -d[0] + (at[1] - now[1]) * -d[1]
            side = math.dist(at, now) ** 2 - back**2
            print(
                f"   option {option}: to ({at[0]:.4f}, {at[1]:.4f}), {back:.2f} mm back and "
                f"{math.sqrt(max(side, 0)):.2f} mm inwards; courtyard to the edge "
                f"{edge_margin(courtyard(ref, at)):+.3f} mm"
            )
        print(f"   robot frame (x, y): {robot(now)} -> {robot(at)}")
        for name, (p, h, half) in BEAMS.items():
            apex = local(ref, at, p)
            ax = axis_to_edge(apex, d)
            print(
                f"   {name}: lens tip {robot(apex)}, {h} mm up; the axis leaves the board {ax:.2f} mm ahead "
                f"({math.degrees(math.atan2(h, ax)) if ax else 90:.1f} deg below the axis); "
                f"board under +-{half:g} deg: {100 * cone_on_board(apex, h, half, d):.2f} %, "
                f"+-{2 * half:g} deg: {100 * cone_on_board(apex, h, 2 * half, d):.2f} %"
            )
        print(f"   courtyard overlaps there: {', '.join(overlaps(ref, courtyard(ref, at))) or 'none'}")
        if at != now:
            f.SetPosition(fx.pt(*at))
            hits = copper_hits(ref)
            f.SetPosition(fx.pt(*now))
            names = sorted({h if isinstance(h, str) else h.GetNetname() for h in hits})
            print(f"   other copper within {CU_CLEAR} mm of the moved pads: {len(hits)} items ({', '.join(names)})")
    return moves


# --- apply ----------------------------------------------------------------------------------------


def apply(moves: dict[str, tuple[float, float]]) -> dict[str, float]:
    """Move W1/W4 and NEIGHBOURS, clear the copper in the way; the nets to reconnect, with the widest
    track each had there."""
    nets: dict[str, float] = {}

    def gone(tracks: list) -> None:
        for t in tracks:
            if t.GetClass() != "PCB_VIA":
                nets[t.GetNetname()] = max(nets.get(t.GetNetname(), 0.0), pcbnew.ToMM(t.GetWidth()))
            else:
                nets.setdefault(t.GetNetname(), 0.0)
        fx.remove(tracks)

    for ref in MOVE:
        gone(own_copper(ref))
        fx.fp(ref).SetPosition(fx.pt(*moves[ref]))
    for ref, (x, y, rot) in NEIGHBOURS.items():
        gone(own_copper(ref))
        fx.place(ref, x, y, rot)
    for ref in [*MOVE, *NEIGHBOURS]:
        gone([h for h in copper_hits(ref) if not isinstance(h, str)])
    problems = []
    for ref in WALLS:
        at = fx.xy(fx.fp(ref).GetPosition())
        if edge_margin(courtyard(ref, at)) < EDGE - 1e-3:
            problems.append(f"{ref}: courtyard within {EDGE} mm of the edge")
        if hit := overlaps(ref, courtyard(ref, at)):
            problems.append(f"{ref}: courtyard overlaps {', '.join(hit)} (set NEIGHBOURS)")
    for ref in [*MOVE, *NEIGHBOURS]:
        if pads := [h for h in copper_hits(ref) if isinstance(h, str)]:
            problems.append(f"{ref}: pads within {CU_CLEAR} mm of {', '.join(pads)}")
    if problems:
        raise SystemExit("not saved:\n  " + "\n  ".join(problems))
    return nets


def main() -> int:
    args = sys.argv[1:]
    option = args[args.index("--option") + 1] if "--option" in args else "inward"
    if option not in OPTIONS:
        raise SystemExit(f"--option: one of {', '.join(OPTIONS)}")
    pcb = Path(args[args.index("--pcb") + 1]) if "--pcb" in args else LAYOUT
    if "--study" in args:
        fx.B = pcbnew.LoadBoard(str(pcb))
        study(option)
        return 0
    footprints()
    fx.B = pcbnew.LoadBoard(str(LAYOUT))
    moves = study(option)
    nets = apply(moves)
    import router
    import usb_wall

    pcbnew.ZONE_FILLER(fx.B).Fill(fx.B.Zones())
    r = router.Router(fx.B)
    failed = []
    for name, width in nets.items():
        try:
            r.route_net(name, width or 0.15)
        except RuntimeError as e:
            failed.append(str(e))
    usb_wall.MOVED = [*MOVE, *NEIGHBOURS]
    hidden = usb_wall.silkscreen()
    if hidden:
        print("designators without a free spot (hidden):", ", ".join(hidden))
    pcbnew.ZONE_FILLER(fx.B).Fill(fx.B.Zones())
    pcbnew.SaveBoard(str(LAYOUT), fx.B)
    if failed:
        print("\n".join(failed))
        return 1
    pcb_layout()
    return 0


if __name__ == "__main__":
    sys.exit(main())
