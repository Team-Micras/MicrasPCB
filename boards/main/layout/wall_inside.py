"""The wall sensors fully on the board, as a one-off pcbnew script (KiCad 10).

    python3 boards/main/layout/wall_inside.py                         # apply (option inward)
    python3 boards/main/layout/wall_inside.py --study                 # numbers only, writes nothing
    python3 boards/main/layout/wall_inside.py --pcb COPY --out OUT    # on a copy, no sync

Runs once, after swd_top.py, on the layout `make gen` leaves with the bare WallSensor footprint
in the library (components/micras/WallSensor: SFH 4550 over TPS601A, no casing). Its courtyard is
both bodies at their largest plus the pads, with 0.25 mm excess; a sensor is on the board when that
courtyard keeps the 0.20 mm board-edge clearance of rules/jlcpcb.kicad_dru from the Edge.Cuts
outline. W2 and W3 (front, 45 degrees) already do, 0.21 mm inside. W1 and W4 (side chamfers,
looking forward) overhung by 2.95 mm: the chamfer runs at 63.4 degrees to their look direction,
so a move back gains 0.447 mm of edge clearance per mm and a move inwards 0.894 mm per mm.
OPTIONS sets the inward shift (the owner's choice, `inward`: 3.3 mm, which keeps W4's pads clear
of the DIP switch SW1 below them); the script adds the least backward move that puts both
courtyards inside, rounded up to 0.01 mm and the same for W1 and W4 (0.45 mm). Every pair the
chamfer allows sits the same distance from it, so --study prints the same beams for all: the
board takes none of the emitter's +-3 or the receiver's +-10 degree cone.

The steps, in order:
- footprints: `pcb layout --sync-footprints` takes the bare footprint into W1-W4, then every other
  footprint gets its text back (the sync re-issues the UUID of every footprint graphic on the board,
  and D4/D5 differ from their library footprints), so the diff is W1-W4 and the embedded STEP;
- place: W1 and W4 to OPTIONS, the parts their courtyards overlapped to NEIGHBOURS (each channel's
  switch, clamp, resistors and capacitors around its sensor), W2 0.03 mm sideways with R17 and C74
  for W2's courtyard; stops without saving while a courtyard leaves the outline or overlaps;
- rip: the moved parts' nets lose their dead ends around the old and new places; another net's
  track that a moved pad now touches is cut out within 1.2 mm of the part's pads (the switch bus
  under W4, Wall_Sensor_2 and WALL1_LED_K by R17, VBAT, WALL2_GATE);
- reroute: each cut-out connection routed again between its own ends (router.py, octilinear.py's
  checks: the board's clearances, at most twice the old length plus 3 mm, no pour cut in two), the
  ones nearest the moved pads first;
- vias: a via into the In1.Cu GND or In2.Cu 3V3 plane beside each SMD pad of those nets;
- route: the moved parts' nets joined again until each is in as many pieces as before, signals
  before supplies and the longest first; a net that finds no way has the routes this script drew
  across it ripped up, goes first, and those follow;
then octilinear.py's cleanup, the moved parts' designators take free spots (usb_wall.silkscreen's
method), the zones are refilled, the board saved and `pcb layout` syncs it.
"""

from __future__ import annotations

import math
import random
import re
import subprocess
import sys
import time
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
CU_CLEAR = 0.12  # the moved pads to other nets' copper: router.py's clearance
# Lens tips in the footprint frame (the sensor looks along -y), optical axis height above the board top
# and half angle (WallSensor.zen; SFH 4550 v1.9 p.5, TPS601A(F) p.2).
BEAMS = {"emitter": ((0.0, -6.28), 9.75, 3.0), "receiver": ((0.0, -6.055), 3.25, 10.0)}
# Inward shift of W1 and W4 (mm). back: along the look direction, plus the 0.3 mm W4's TPS601A key tab
# needs from the side edge (its courtyard is 3.57 mm wide on that side), mirrored on W1; inward: the
# side sensors move towards the middle and 0.45 mm back, clear of P1 (SWD) and SW1 (DIP switch).
OPTIONS = {"back": 0.3, "inward": 3.3}
MOVE = ("W1", "W4")
# ref -> (x, y, rotation): the parts the new courtyards overlap, and where they go.
NEIGHBOURS: dict[str, tuple[float, float, float]] = {
    # W1: channel 0's switch, clamp, pull-down and the 1 uF to the free corner left of the sensor, the
    # emitter resistor below its pads, the load resistor and gate capacitor in a column right of them;
    # channel 1's clamp above SW3, the Reset capacitor beside the sensor
    "R13": (130.95, 85.05, 0),
    "Q2": (125.85, 82.25, -90),
    "D9": (125.7, 85.1, 0),
    "R12": (128.0, 85.06, 90),
    "C26": (126.05, 79.8, 0),
    "R14": (133.35, 80.75, 90),
    "C73": (133.35, 82.65, 90),
    "C21": (133.642, 78.86, 90),
    "D10": (135.75, 74.6, 0),
    # W2 stays on the board as it is, 0.03 mm sideways (away from R17); its courtyard needs R17 0.06 mm
    # out and 0.12 mm back (R44 above it keeps its place) and C74 0.06 mm out
    "W2": (138.2941, 65.955, 45),
    "R17": (144.1576, 66.9923, 135),
    "C74": (137.798, 70.725, 45),
    # W4: SW2 0.35 mm up (D12 with it) for the emitter resistor under it, channel 3's switch, load and
    # pull-down in the free corner right of the sensor, its gate resistor left of it, its gate
    # capacitor above SW2 by the clamp, its 1 uF at the emitter resistor's 3V3 end, and channel 2's
    # gate resistor above the sensor
    "SW2": (160.439, 80.312, 180),
    "D12": (159.6, 76.8, 90),
    "R25": (161.1, 83.42, 180),
    "R23": (163.9, 80.75, -90),
    "C76": (161.6, 77.3, 180),
    "R24": (171.4, 79.4, 0),
    "R26": (171.4, 78.35, 0),
    "Q5": (171.2, 81.9, 90),
    "C29": (157.9, 83.45, 90),
    "R19": (163.15, 73.85, 90),
}
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


def targets(inward: float) -> dict[str, tuple[float, float]]:
    """W1 and W4 mirrored: both `inward` and back by the larger of their least moves."""
    back = {}
    for ref in MOVE:
        x0, y0 = fx.xy(fx.fp(ref).GetPosition())
        x, y = target(ref, inward)
        back[ref] = (x - x0) * -look(ref)[0] + (y - y0) * -look(ref)[1]
    d = max(back.values())
    out = {}
    for ref in MOVE:
        x, y = fx.xy(fx.fp(ref).GetPosition())
        x += inward if x < AXLE[0] else -inward
        out[ref] = (round(x - d * look(ref)[0], 4), round(y - d * look(ref)[1], 4))
    return out


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
            # KiCad's DRC counts courtyards that touch
            i = pcbnew.SHAPE_POLY_SET(poly)
            i.Inflate(fx.mm(0.002), pcbnew.CORNER_STRATEGY_CHAMFER_ALL_CORNERS, fx.mm(0.001))
            i.BooleanIntersection(c)
            if i.OutlineCount() and i.Area() > 0:
                out.append(g.GetReference())
    return sorted(set(out))


def copper_hits(ref: str) -> list:
    """Tracks and vias of other nets within CU_CLEAR of ref's pads, and other parts' pads."""
    f = fx.fp(ref)
    tracks, pads = [], []
    for p in f.Pads():
        for lay in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
            if not p.IsOnLayer(lay):
                continue
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
        at = targets(OPTIONS[option])[ref] if ref in MOVE else now
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

WORK = 2.0  # mm around the moved parts (old and new places) where their nets' dead ends are peeled
PLANES = {"GND": "In1", "3V3": "In2"}  # the inner-layer planes; an SMD pad of these nets gets a via
WIDTH = 0.2  # mm, a net's new tracks when none of its own were ripped
NEAR = 4.0  # mm: a supply pad left on its own joins its net's copper within this distance


def _box(refs: list[str], grow: float) -> pcbnew.BOX2I:
    box = None
    for ref in refs:
        bb = fx.fp(ref).GetCourtyard(pcbnew.F_CrtYd).BBox()
        if box is None:
            box = pcbnew.BOX2I(bb.GetOrigin(), bb.GetSize())
        else:
            box.Merge(bb)
    box.Inflate(fx.mm(grow))
    return box


def place(moves: dict[str, tuple[float, float]]) -> list[pcbnew.BOX2I]:
    """W1/W4 and NEIGHBOURS to their places; the boxes (old and new courtyards, grown by WORK)
    whose copper is reworked."""
    refs = [*MOVE, *NEIGHBOURS]
    for f in fx.B.GetFootprints():
        f.BuildCourtyardCaches()
    boxes = [_box([r], WORK) for r in refs]
    for ref in MOVE:
        fx.fp(ref).SetPosition(fx.pt(*moves[ref]))
    for ref, (x, y, rot) in NEIGHBOURS.items():
        fx.place(ref, x, y, rot)
    for f in fx.B.GetFootprints():
        f.BuildCourtyardCaches()
    boxes += [_box([r], WORK) for r in refs]
    return boxes


def _in(boxes, p) -> bool:
    return any(b.Contains(p) for b in boxes)


def _chains(hits: list) -> list:
    """The hit segments with the tracks they continue through (to the pads, vias and junctions
    where their net's copper branches), so a crossing connection is rerouted whole."""
    import collections

    import octilinear as oc

    ends = collections.defaultdict(list)
    for t in oc.segs():
        for p in (t.GetStart(), t.GetEnd()):
            ends[(p.x, p.y, t.GetLayer(), t.GetNetCode())].append(t)
    seen, out = set(), []
    for t in hits:
        if t.GetClass() != "PCB_TRACK" or t.m_Uuid.AsString() in seen:
            continue
        seen.add(t.m_Uuid.AsString())
        out.append(t)
        for p0 in (t.GetStart(), t.GetEnd()):
            cur, p = t, p0
            while True:
                nc, layer = cur.GetNetCode(), cur.GetLayer()
                others = [o for o in ends[(p.x, p.y, layer, nc)] if not oc.same(o, cur)]
                if len(others) != 1 or oc.pads_at(p, layer, nc) or oc.via_at(p, nc, tol=230_000):
                    break
                nxt = others[0]
                if nxt.m_Uuid.AsString() in seen:
                    break
                seen.add(nxt.m_Uuid.AsString())
                out.append(nxt)
                cur, p = nxt, (nxt.GetEnd() if nxt.GetStart() == p else nxt.GetStart())
    return out


WINDOW = 1.2  # mm around a moved part's pads: a crossing track is ripped and routed again inside it
STEP = 10_000  # nm, where a crossing track may be cut
MINKEEP = 300_000  # nm, the shortest piece of a cut track kept (router.MINRUN)


def _trim(chain: list, windows: list, whole: list[str]) -> list:
    """The parts of the chain's segments inside the windows, as segments of their own (a segment
    that runs out of a window is cut there, on its own line, so what stays keeps its angle); the
    segments named in `whole` go entirely."""
    out = []
    for t in chain:
        a, b = oc_cp(t.GetStart()), oc_cp(t.GetEnd())
        dx, dy = b.x - a.x, b.y - a.y
        n = max(abs(dx), abs(dy))
        if n == 0 or t.m_Uuid.AsString() in whole:
            out.append(t)
            continue
        at = _stepper(a, dx, dy, n)
        inside = [k for k in range(0, n + 1, STEP) if any(w.Contains(at(k)) for w in windows)]
        if not inside:
            continue
        k0, k1 = max(min(inside) - STEP, 0), min(max(inside) + STEP, n)
        k0 = 0 if k0 < MINKEEP else k0
        k1 = n if n - k1 < MINKEEP else k1
        if k0 == 0 and k1 == n:
            out.append(t)
            continue
        p0, p1 = at(k0) if k0 else a, at(k1) if k1 < n else b
        if k0:
            t.SetEnd(p0)
            mid = _seg(t, p0, p1)
        else:
            t.SetEnd(p1)
            mid = t
        if k1 < n:
            _seg(t, p1, b)
        out.append(mid)
    return out


def _stepper(a, dx: int, dy: int, n: int):
    """The point k nm along a segment from a (its larger axis step), exactly on its line when diagonal."""
    sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
    if abs(abs(dx) - abs(dy)) <= 1000:
        return lambda k: pcbnew.VECTOR2I(a.x + sx * k, a.y + sy * k)
    return lambda k: pcbnew.VECTOR2I(a.x + round(dx * k / n), a.y + round(dy * k / n))


def _pads_box(ref: str) -> pcbnew.BOX2I:
    box = None
    for p in fx.fp(ref).Pads():
        bb = p.GetBoundingBox()
        if box is None:
            box = pcbnew.BOX2I(bb.GetOrigin(), bb.GetSize())
        else:
            box.Merge(bb)
    box.Inflate(fx.mm(WINDOW))
    return box


def oc_cp(p) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(p.x, p.y)


def _seg(t, a, b):
    import octilinear as oc

    return oc.new_track(t.GetNet(), t.GetLayer(), t.GetWidth(), a, b)


def rip(boxes: list[pcbnew.BOX2I]) -> tuple[dict[str, float], list[dict]]:
    """Clear the copper of the new places. The moved parts' nets lose every dead end inside the
    boxes, back to where other copper continues (routed again by `route`); another net's
    connection that crosses a moved pad is ripped whole, between the pads, vias and junctions it
    joins (routed again by `reroute`). Returns the moved parts' nets with the widest track each
    lost, and the crossing connections."""
    import octilinear as oc

    refs = [*MOVE, *NEIGHBOURS]
    own = {p.GetNetname() for r in refs for p in fx.fp(r).Pads() if p.GetNetname()}
    lost: dict[str, float] = {n: 0.0 for n in own}

    def gone(objs: list) -> None:
        for o in objs:
            if o.GetClass() == "PCB_TRACK":
                lost[o.GetNetname()] = max(lost.get(o.GetNetname(), 0.0), pcbnew.ToMM(o.GetWidth()))
        oc._rip(objs)

    # a net whose every pad is on a moved part is routed afresh: all its copper goes
    moved = {p.m_Uuid.AsString() for r in refs for p in fx.fp(r).Pads()}
    local = {
        n
        for n in own
        if n not in oc.POWER
        and all(p.m_Uuid.AsString() in moved for f in fx.B.GetFootprints() for p in f.Pads() if p.GetNetname() == n)
    }
    gone([t for t in fx.B.GetTracks() if t.GetNetname() in local])
    per_ref = {ref: [h for h in copper_hits(ref) if not isinstance(h, str)] for ref in refs}
    gone(list({h.m_Uuid.AsString(): h for hs in per_ref.values() for h in hs if h.GetNetname() in own}.values()))
    # own-net vias too near a moved pad's hole (JLCPCB 0.45 mm hole to hole, rules/jlcpcb.kicad_dru)
    holes = [p for r in refs for p in fx.fp(r).Pads() if p.HasHole()]
    gone(
        [
            v
            for v in fx.B.GetTracks()
            if v.GetClass() == "PCB_VIA"
            and v.GetNetname() in own
            and any(
                pcbnew.ToMM((v.GetPosition() - p.GetPosition()).EuclideanNorm())
                < pcbnew.ToMM(v.GetDrillValue() + p.GetDrillSize().x) / 2 + 0.46
                for p in holes
            )
        ]
    )
    vias, cut = [], []
    for ref, hs in per_ref.items():
        crossing = [h for h in hs if h.GetNetname() not in own]
        if not crossing:
            continue
        # vias of other nets that the new pads hit go with the tracks on them
        vs = [h for h in crossing if h.GetClass() == "PCB_VIA"]
        vias += vs
        on_vias = [
            t
            for t in oc.segs()
            if any(t.GetNetCode() == v.GetNetCode() and v.GetPosition() in (t.GetStart(), t.GetEnd()) for v in vs)
        ]
        window = _pads_box(ref)
        chain = _chains([*[h for h in crossing if h.GetClass() == "PCB_TRACK"], *on_vias])
        cut += [t for t in _trim(chain, [window], [t.m_Uuid.AsString() for t in on_vias]) if t not in cut]
    conns = oc.connections(cut)
    pads = [p for r in refs for p in fx.fp(r).Pads()]
    for c in conns:
        c["vias"] += [v for v in vias if v.GetNetCode() == c["tracks"][0].GetNetCode()]
        c["terms"] = {u: x for u, x in c["terms"].items() if not any(oc.same(x[1], v) for v in vias)}
        c["width"] = max(pcbnew.ToMM(t.GetWidth()) for t in c["tracks"])
        c["length"] = sum(t.GetLength() for t in c["tracks"])
        c["box"] = oc._bbox([e for t in c["tracks"] for e in (t.GetStart(), t.GetEnd())])
        # how close the crossing came to the moved pads: the nearest goes round them first
        c["near"] = min(
            (
                pcbnew.ToMM(pcbnew.SEG(t.GetStart(), t.GetEnd()).Distance(p.GetPosition()))
                for t in c["tracks"]
                for p in pads
                if p.IsOnLayer(t.GetLayer())
            ),
            default=9.0,
        )
    for c in conns:
        oc._rip(c["tracks"] + c["vias"])
    while True:
        dead = [
            t
            for t in fx.B.GetTracks()
            if t.GetClass() == "PCB_TRACK"
            and t.GetNetname() in own
            and any(_in(boxes, e) and _free(t, e) for e in (t.GetStart(), t.GetEnd()))
        ]
        if not dead:
            break
        gone(dead)
    return lost, conns


def reroute(conns: list[dict]) -> list[str]:
    """Each crossing connection routed again between its own pads, vias and junctions, no more
    than octilinear.DETOUR times its old length (plus 3 mm), cutting no pour."""
    import octilinear as oc
    import router

    pcbnew.ZONE_FILLER(fx.B).Fill(fx.B.Zones())
    r = router.Router(fx.B)
    check = oc._checker(r)
    for c in conns:
        c["net"] = c["tracks"][0].GetNet()
        c["tracks"] = [_Len(c["length"])]
    todo = sorted(conns, key=lambda c: (c["net"].GetNetname() in oc.POWER, c["near"]))
    for _ in range(2):  # what fails is tried again once the others are in
        left = []
        for c in todo:
            before = oc._unconnected(c["box"])
            ok = any(oc._route(r, c, c["net"], c["width"], check, c["box"], before, hard) for hard in (False, True))
            oc.dirty()
            print(f"  {c['net'].GetNetname()} {c['width']:g} mm: {'routed' if ok else 'failed'}", flush=True)
            if not ok:
                left.append(c)
        todo = left
    return [f"{c['net'].GetNetname()}: crossing connection not routed" for c in todo]


class _Len:
    """Stands in for the ripped tracks in octilinear._route's detour check."""

    def __init__(self, length):
        self.length = length

    def GetLength(self):
        return self.length


def _directions(p: pcbnew.PAD) -> list[float]:
    """Fan-out angles from a pad: along its long axis first, then across, then the diagonals."""
    a = p.GetOrientation().AsDegrees()
    long_x = p.GetSize().x >= p.GetSize().y
    axes = [a, a + 180] if long_x else [a + 90, a + 270]
    return axes + [x + 90 for x in axes] + [a + 45 + 90 * k for k in range(4)]


def plane_vias(refs: list[str]) -> list[str]:
    """A via into its plane next to every SMD pad of a plane net that is on nothing of its net."""
    import octilinear as oc

    placed = []
    for ref in refs:
        for p in fx.fp(ref).Pads():
            if p.HasHole() or p.GetNetname() not in PLANES:
                continue
            fx.B.BuildConnectivity()
            if any(o.GetClass() in ("PCB_TRACK", "PCB_VIA") for o in fx.B.GetConnectivity().GetConnectedItems(p)):
                continue
            c0 = fx.xy(p.GetPosition())
            spot = None
            for r in [0.55 + 0.05 * k for k in range(20)]:
                for a in _directions(p):
                    t = math.radians(a)
                    c = (round(c0[0] + r * math.cos(t), 4), round(c0[1] - r * math.sin(t), 4))
                    if fx.via_spot_ok(
                        c, p.GetNetname(), p, seg_from=c0, plane=(PLANES[p.GetNetname()], p.GetNetname())
                    ):
                        spot = c
                        break
                if spot:
                    break
            if spot is None:  # router.py joins it to its net's copper nearby
                continue
            fx.track(p.GetNetname(), "F", 0.25, c0, spot)
            fx.via(p.GetNetname(), *spot)
            oc.dirty()
            placed.append(f"{ref}.{p.GetNumber()}")
    return placed


def pieces_now(names) -> dict[str, int]:
    """How many pieces (islands) each net's copper is in."""
    import router

    r = router.Router(fx.B)
    return {n: len(r.copper(fx.B.FindNet(n).GetNetCode())) for n in names if fx.B.FindNet(n)}


def route(lost: dict[str, float], boxes, pieces: dict[str, int]) -> list[str]:
    """Each net the rework left in pieces, joined again (router.py, octilinear, the board's
    clearances checked): signals first, narrowest first, then the supplies."""
    import octilinear as oc
    import router

    pcbnew.ZONE_FILLER(fx.B).Fill(fx.B.Zones())
    r = router.Router(fx.B)
    check = oc._checker(r)

    def spread(name: str) -> float:
        pads = [fx.xy(p.GetPosition()) for f in fx.B.GetFootprints() for p in f.Pads() if p.GetNetname() == name]
        return max((math.dist(a, b) for a in pads for b in pads), default=0.0)

    def join(name: str) -> bool:
        net = fx.B.FindNet(name)
        w = lost[name] or WIDTH
        for _ in range(30):
            islands = r.copper(net.GetNetCode())
            if len(islands) < 2:
                return True
            if len(islands) <= pieces.get(name, 1):
                return True  # as many pieces as before the rework
            # every piece but the largest, the ones here first
            big = max(islands, key=len)
            local = sorted(
                (isl for isl in islands if isl is not big),
                key=lambda isl: (not any(_in(boxes, _at(o)) for _, o in isl), len(isl)),
            )
            out = None
            for src in local:
                tgt = [it for isl in islands if isl is not src for it in isl]
                if name in oc.POWER:  # a supply joins the copper of its own nearby, not the whole net
                    near = oc._bbox([_at(o) for _, o in src])
                    reach = fx.mm(NEAR)
                    tgt = [
                        (k, o)
                        for k, o in tgt
                        if k != "zone"
                        and near[0].x - reach <= _at(o).x <= near[1].x + reach
                        and near[0].y - reach <= _at(o).y <= near[1].y + reach
                    ]
                out = r.join(net, w, src, tgt, clr=0.1 if w <= 0.15 else router.CLR, check=check)
                oc.dirty()
                if out is not None:
                    made.setdefault(name, []).extend(o for _, o in r.created)
                    break
            if out is None:
                print(
                    f"  {name}: no route from", ", ".join(_name(k, o) for isl in local for k, o in isl[:3]), flush=True
                )
                return False
        return False

    def pieces_box(name: str):
        nc = fx.B.FindNet(name).GetNetCode()
        islands = r.copper(nc)
        big = max(islands, key=len)
        pts = [_at(o) for isl in islands if isl is not big for _, o in isl]
        pts += [p.GetPosition() for _, p in big if _ == "pad"]
        box = pcbnew.BOX2I(oc._bbox(pts)[0], oc._bbox(pts)[1] - oc._bbox(pts)[0])
        box.Inflate(fx.mm(1.0))
        return box

    made: dict[str, list] = {}
    # signals before the supplies; the longest (to IC1) first, while there is room
    todo = sorted(lost, key=lambda n: (n in oc.POWER, -spread(n), n))
    left = []
    for n in todo:
        t0 = time.time()
        ok = join(n)
        print(f"  {n}: {'joined' if ok else 'not joined'} ({time.time() - t0:.0f} s)", flush=True)
        if not ok:
            left.append(n)
    failed = []
    for n in left:
        # rip up what this script routed across the failed net's pieces, route it, then the others again
        box = pieces_box(n)
        victims = [
            v
            for v, objs in made.items()
            if v != n and v not in oc.POWER and any(box.Intersects(o.GetBoundingBox()) for o in objs)
        ]
        for v in victims:
            fx.drop(made.pop(v))
        oc.dirty()
        print(f"  {n}: ripped {', '.join(victims)} to route it first", flush=True)
        for m in [n, *victims]:
            ok = join(m)
            print(f"  {m}: {'joined' if ok else 'not joined'}", flush=True)
            if not ok:
                failed.append(f"{m}: not joined")
    return failed


def trim_stubs(nets: set[str], boxes) -> int:
    """Dead ends the rework left inside the boxes: a track whose free end runs past the copper that
    joins it is cut back to that copper (on its own line); one that joins nothing there goes; a via
    of these nets that joins no track or pad (only a plane) goes."""
    import octilinear as oc

    n = 0
    while True:
        dead = [
            (t, e)
            for t in oc.segs()
            if t.GetNetname() in nets
            for e in (oc.cp(t.GetStart()), oc.cp(t.GetEnd()))
            if _in(boxes, e) and _free(t, e)
        ]
        if not dead:
            break
        for t, e in dead:
            other = oc.cp(t.GetEnd()) if e == t.GetStart() else oc.cp(t.GetStart())
            touch = [
                p
                for o in fx.B.GetTracks()
                if o.GetNetCode() == t.GetNetCode() and not oc.same(o, t)
                for p in ([o.GetPosition()] if o.GetClass() == "PCB_VIA" else [o.GetStart(), o.GetEnd()])
                if (o.GetClass() == "PCB_VIA" or o.GetLayer() == t.GetLayer()) and t.HitTest(p, 1000) and p != other
            ]
            q = oc.onto_line(other, min(touch, key=lambda p: (p - e).EuclideanNorm())) if touch else None
            if q is not None and (q - other).EuclideanNorm() >= 10_000:
                (t.SetStart if e == t.GetStart() else t.SetEnd)(q)
            else:
                oc._rip([t])
            n += 1
        oc.dirty()
    return n


def _free(t, e) -> bool:
    """Nothing of the track's net touches its end e (pads, vias, tracks and pours within its half
    width, as KiCad's connectivity counts them)."""
    import octilinear as oc

    return not oc._touching(t, e, t.GetLayer(), t.GetWidth() // 2)


def lone_vias(nets: set[str], boxes) -> int:
    """Vias of these nets in the boxes that join no pad or track, only pours (KiCad: via_dangling)."""
    import octilinear as oc

    pcbnew.ZONE_FILLER(fx.B).Fill(fx.B.Zones())
    oc.dirty()
    lone = [
        v
        for v in fx.B.GetTracks()
        if v.GetClass() == "PCB_VIA"
        and v.GetNetname() in nets
        and _in(boxes, v.GetPosition())
        and not any(
            oc._touching(v, v.GetPosition(), layer, v.GetWidth(layer) // 2) for layer in (pcbnew.F_Cu, pcbnew.B_Cu)
        )
    ]
    oc._rip(lone)
    return len(lone)


def _name(kind: str, o) -> str:
    if kind == "pad":
        return f"{o.GetParentFootprint().GetReference()}.{o.GetNumber()}"
    x, y = fx.xy(_at(o))
    return f"{kind} ({x:.2f}, {y:.2f})"


def _at(o) -> pcbnew.VECTOR2I:
    return o.GetPosition() if not hasattr(o, "GetStart") or o.GetClass() == "PCB_VIA" else o.GetStart()


def _nets() -> set[str]:
    """The moved parts' nets: the nets the rework can leave in pieces (crossing nets are rerouted
    between their own ends)."""
    return {p.GetNetname() for r in [*MOVE, *NEIGHBOURS] for p in fx.fp(r).Pads() if p.GetNetname()}


def checks() -> list[str]:
    problems = []
    for ref in WALLS:
        at = fx.xy(fx.fp(ref).GetPosition())
        if edge_margin(courtyard(ref, at)) < EDGE - 1e-3:
            problems.append(f"{ref}: courtyard within {EDGE} mm of the edge")
    for ref in [*WALLS, *NEIGHBOURS]:
        f = fx.fp(ref)
        f.BuildCourtyardCaches()
        if hit := overlaps(ref, pcbnew.SHAPE_POLY_SET(f.GetCourtyard(pcbnew.F_CrtYd))):
            problems.append(f"{ref}: courtyard overlaps {', '.join(hit)}")
    return problems


def main() -> int:
    import octilinear as oc
    import usb_wall

    args = sys.argv[1:]
    option = args[args.index("--option") + 1] if "--option" in args else "inward"
    if option not in OPTIONS:
        raise SystemExit(f"--option: one of {', '.join(OPTIONS)}")
    pcb = Path(args[args.index("--pcb") + 1]) if "--pcb" in args else LAYOUT
    if "--study" in args:
        fx.B = pcbnew.LoadBoard(str(pcb))
        study(option)
        return 0
    if pcb == LAYOUT:
        footprints()
    fx.B = pcbnew.LoadBoard(str(pcb))
    moves = targets(OPTIONS[option])
    pcbnew.ZONE_FILLER(fx.B).Fill(fx.B.Zones())
    pieces_before = pieces_now(_nets())
    boxes = place(moves)
    if problems := checks():
        raise SystemExit("not saved:\n  " + "\n  ".join(problems))
    lost, conns = rip(boxes)
    pieces = pieces_before
    print("moved parts' nets:", ", ".join(f"{n} {w:g}" for n, w in sorted(lost.items())))
    print("crossing connections:", ", ".join(sorted({c["tracks"][0].GetNetname() for c in conns})))
    failed = reroute(conns)
    print("plane vias:", ", ".join(plane_vias([*MOVE, *NEIGHBOURS])))
    oc.cleanup()  # teardrops and vias the ripped copper left on nothing
    failed += route(lost, boxes, pieces)
    windows = [_pads_box(r) for r in [*MOVE, *NEIGHBOURS]]
    print("stubs trimmed:", trim_stubs({*lost, *(c["net"].GetNetname() for c in conns)}, [*boxes, *windows]))
    oc.cleanup()
    print("lone vias removed:", lone_vias(set(lost), boxes))
    usb_wall.MOVED = [*MOVE, *NEIGHBOURS]
    hidden = usb_wall.silkscreen()
    if hidden:
        print("designators without a free spot (hidden):", ", ".join(hidden))
    pcbnew.ZONE_FILLER(fx.B).Fill(fx.B.Zones())
    out = Path(args[args.index("--out") + 1]) if "--out" in args else pcb
    pcbnew.SaveBoard(str(out), fx.B)
    print("after:", oc.summary())
    if failed:
        print("\n".join(failed))
        return 1
    if out == LAYOUT and "--no-sync" not in args:
        pcb_layout()
    return 0


if __name__ == "__main__":
    sys.exit(main())
