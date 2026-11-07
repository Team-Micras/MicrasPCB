"""Size and place the main board's reference designators on the silkscreen.

    /usr/bin/python3 boards/main/layout/silk.py              # KiCad's Python (pcbnew), from the repo root
    /usr/bin/python3 boards/main/layout/silk.py IN OUT       # read IN, write OUT (a trial on a copy)
    /usr/bin/python3 boards/main/layout/silk.py --size 0.6   # a trial text size (mm)

Every reference on F.Silkscreen becomes SIZE high with a STROKE line (the mounting holes' references
stay on F.Fab), at 0 or 90 degrees, within NEAR of its part's courtyard, on a spot that is

- never over an opening in the solder mask (pads, untented vias) nor nearer than SILK_GAP to one
  (JLCPCB clips silkscreen off exposed copper; KiCad's DRC reports it as silk_over_copper);
- never nearer than SILK_GAP to other silkscreen (the footprints' outlines and marks, the board's
  texts, the other references; DRC silk_overlap; min_silk_clearance in main.kicad_pro);
- never nearer than EDGE_GAP to the board edge or a cut-out (DRC silk_edge_clearance);
- never over a part's body (its F.Fab drawing): a label there is hidden once the board is assembled;

and, cheapest first, close to its part, nearer its own part than any other (so it names the right
one), over few courtyard margins and tented vias, upright before turned. The labels with the fewest
spots choose first; then a local search moves a label to another of its spots, evicting the labels
it clashes with to their cheapest spot still free, and keeps the moves that lower the total cost.
A label with no spot left is hidden: a label far from its part names the wrong one, and the fab
drawing (F.Fab) still names every part. Deterministic: the same board gives the same labels.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import numpy as np
import pcbnew
from PIL import Image, ImageDraw

PCB = Path(__file__).with_name("main.kicad_pcb")

SIZE = 0.5  # mm, the reference text height and width: the board's minimum (main.zen), the owner's choice so more labels fit
STROKE = 0.125  # mm, the board's minimum (rules/kicad-severities.toml): a quarter of SIZE, the stroke font's cap
SILK_GAP = 0.1  # mm, min_silk_clearance (main.kicad_pro), to other silkscreen and to mask openings
EDGE_GAP = 0.2  # mm, to the board edge and its cut-outs
RES = 0.05  # mm, raster cell
STEP = 2  # cells between candidate centres
OPTIONS = 40  # spots kept per label
SPREAD = 0.3  # mm between two kept spots of a label at the same angle
HIDDEN = 0.5  # mm2 of a body under a label that hides it: never chosen
NEAR = 1.0  # mm, the farthest a label may sit from its part's courtyard
LOST = 400.0  # cost of a label without a spot
T0, T1 = 20.0, 0.05  # annealing temperature, start and end

# cost weights
W_BODY = 40.0  # per mm2 of a part body under the label (hidden once assembled)
W_COURTYARD = 1.0  # per mm2 of a courtyard margin under the label (visible, but crowds the part)
W_DIST = 6.0  # per mm between the label and its part's courtyard
W_FOREIGN = 12.0  # the label's centre is nearer another part's courtyard than its own
W_VIA = 2.0  # per mm2 of tented via under the label
W_TURNED = 0.4  # a label at 90 degrees


def iu(v: float) -> int:
    return pcbnew.FromMM(v)


def mm(v: int) -> float:
    return pcbnew.ToMM(v)


def outlines(ps) -> list[tuple[list, list[list]]]:
    """A SHAPE_POLY_SET as (outline points, [hole points]) per polygon, in mm."""
    out = []
    for i in range(ps.OutlineCount()):
        o = ps.Outline(i)
        pts = [(mm(o.CPoint(k).x), mm(o.CPoint(k).y)) for k in range(o.PointCount())]
        holes = []
        for h in range(ps.HoleCount(i)):
            hl = ps.Hole(i, h)
            holes.append([(mm(hl.CPoint(k).x), mm(hl.CPoint(k).y)) for k in range(hl.PointCount())])
        out.append((pts, holes))
    return out


def shape(item, layer, clearance: float) -> list[tuple[list, list[list]]]:
    ps = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(ps, layer, iu(clearance), iu(0.005), pcbnew.ERROR_OUTSIDE)
    return outlines(ps)


class Raster:
    """Cells of RES mm over the board's bounding box (KiCad frame: column x, row y)."""

    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0 = x0, y0
        self.nx, self.ny = int((x1 - x0) / RES) + 1, int((y1 - y0) / RES) + 1

    def _px(self, p):
        return ((p[0] - self.x0) / RES - 0.5, (p[1] - self.y0) / RES - 0.5)

    def draw(self, polys) -> np.ndarray:
        im = Image.new("1", (self.nx, self.ny))
        d = ImageDraw.Draw(im)
        for pts, _hs in polys:
            if len(pts) >= 3:
                d.polygon([self._px(p) for p in pts], fill=1, outline=1)
        for _pts, hs in polys:
            for h in hs:
                if len(h) >= 3:
                    d.polygon([self._px(p) for p in h], fill=0)
        return np.array(im, dtype=bool)


def sat(m: np.ndarray) -> np.ndarray:
    s = np.zeros((m.shape[0] + 1, m.shape[1] + 1), np.int32)
    s[1:, 1:] = m.astype(np.int32).cumsum(0).cumsum(1)
    return s


def box_sum(s, r0, c0, r1, c1):
    """Sum of the cells in rows r0..r1-1 and columns c0..c1-1 (clipped to the raster)."""
    r0, r1 = np.clip(r0, 0, s.shape[0] - 1), np.clip(r1, 0, s.shape[0] - 1)
    c0, c1 = np.clip(c0, 0, s.shape[1] - 1), np.clip(c1, 0, s.shape[1] - 1)
    return s[r1, c1] - s[r0, c1] - s[r1, c0] + s[r0, c0]


def dilate(m: np.ndarray, k: int) -> np.ndarray:
    s = sat(m)
    r, c = np.mgrid[0 : m.shape[0], 0 : m.shape[1]]
    return box_sum(s, r - k, c - k, r + k + 1, c + k + 1) > 0


def courtyard(f):
    """The courtyard's polygons and bounding box (mm); the footprint's box without one."""
    f.BuildCourtyardCaches()
    ps = f.GetCourtyard(pcbnew.F_CrtYd)
    if ps.IsEmpty():
        bb = f.GetBoundingBox(False)
        x0, y0, x1, y1 = mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())
        return [([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], [])], (x0, y0, x1, y1)
    polys = outlines(ps)
    pts = np.array([p for o, _ in polys for p in o])
    return polys, (*pts.min(0), *pts.max(0))


def body(f):
    """The part's body in plan: the convex hull of its F.Fab drawing (its courtyard without one)."""
    pts = []
    for it in f.GraphicalItems():
        if it.GetLayer() == pcbnew.F_Fab and not isinstance(it, pcbnew.PCB_TEXT):
            pts += [p for o, _ in shape(it, pcbnew.F_Fab, 0.0) for p in o]
    if len(pts) < 3:
        return courtyard(f)[0]
    return [(hull(pts), [])]


def hull(pts):
    """Convex hull (Andrew's monotone chain)."""
    pts = sorted(set(pts))

    def half(seq):
        h = []
        for p in seq:
            while (
                len(h) >= 2
                and (h[-1][0] - h[-2][0]) * (p[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0]) <= 0
            ):
                h.pop()
            h.append(p)
        return h

    lo, hi = half(pts), half(reversed(pts))
    return lo[:-1] + hi[:-1]


def rect_gap(px, py, b):
    """Distance from points to a box (0 inside)."""
    dx = np.maximum(np.maximum(b[0] - px, px - b[2]), 0)
    dy = np.maximum(np.maximum(b[1] - py, py - b[3]), 0)
    return np.hypot(dx, dy)


class Label:
    def __init__(self, f, R: Raster):
        self.f, self.ref = f, f.Reference()
        self.name = f.GetReference()
        self.polys, self.box = courtyard(f)
        # half extents and the offset from the text position to its box centre, per angle
        self.geom = {}
        for ang in (0, 90):
            self.ref.SetTextAngleDegrees(ang)
            pos = self.ref.GetPosition()
            bb = self.ref.GetBoundingBox()
            c = bb.GetCenter()
            self.geom[ang] = (mm(bb.GetWidth()) / 2, mm(bb.GetHeight()) / 2, mm(c.x - pos.x), mm(c.y - pos.y))
        self.at = None  # (x, y, angle, cost terms) of the box centre

    def cells(self, R, x, y, ang, grow=0.0):
        hw, hh = self.geom[ang][0] + grow, self.geom[ang][1] + grow
        c0 = np.floor((x - hw - R.x0) / RES).astype(int)
        c1 = np.ceil((x + hw - R.x0) / RES).astype(int)
        r0 = np.floor((y - hh - R.y0) / RES).astype(int)
        r1 = np.ceil((y + hh - R.y0) / RES).astype(int)
        return r0, c0, r1, c1

    def apply(self):
        x, y, ang = self.at[:3]
        _hw, _hh, ox, oy = self.geom[ang]
        self.ref.SetTextAngleDegrees(ang)
        self.ref.SetPosition(pcbnew.VECTOR2I(iu(x - ox), iu(y - oy)))


def main(src: Path, dst: Path) -> int:
    board = pcbnew.LoadBoard(str(src))
    edge = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(edge, True)
    bpolys = outlines(edge)
    allpts = np.array([p for o, _ in bpolys for p in o])
    (bx0, by0), (bx1, by1) = allpts.min(0), allpts.max(0)
    R = Raster(bx0 - 1, by0 - 1, bx1 + 1, by1 + 1)

    fps = sorted(board.GetFootprints(), key=lambda f: f.GetReference())
    for f in fps:
        r = f.Reference()
        if r.GetLayer() == pcbnew.F_SilkS:
            r.SetVisible(True)  # a label hidden by an earlier run gets another chance
            r.SetTextSize(pcbnew.VECTOR2I(iu(SIZE), iu(SIZE)))
            r.SetTextThickness(iu(STROKE))
            r.SetKeepUpright(True)
    labels = [Label(f, R) for f in fps if f.Reference().GetLayer() == pcbnew.F_SilkS]

    # what a label may never touch: off the board, mask openings, other silkscreen
    hard = dilate(~R.draw(bpolys), round(EDGE_GAP / RES))
    mask_open, silk = [], []
    for f in fps:
        for p in f.Pads():
            if p.IsOnLayer(pcbnew.F_Mask) or p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                exp = mm(p.GetSolderMaskExpansion(pcbnew.F_Mask)) if p.IsOnLayer(pcbnew.F_Mask) else 0.0
                lay = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.F_Mask
                mask_open += shape(p, lay, SILK_GAP + max(exp, 0.0))
                if p.HasHole():
                    d = mm(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2 + SILK_GAP
                    c = p.GetPosition()
                    cx, cy = mm(c.x), mm(c.y)
                    mask_open.append(
                        ([(cx + d * math.cos(t), cy + d * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 32)], [])
                    )
        for it in list(f.GraphicalItems()) + [fl for fl in f.GetFields() if fl.IsVisible() and not fl.IsReference()]:
            if it.GetLayer() == pcbnew.F_SilkS:
                silk += shape(it, pcbnew.F_SilkS, SILK_GAP)
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.F_SilkS:
            silk += shape(d, pcbnew.F_SilkS, SILK_GAP)
    tented = []
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            if t.IsTented(pcbnew.F_Mask):
                tented += shape(t, pcbnew.F_Cu, 0.0)
            else:
                mask_open += shape(t, pcbnew.F_Cu, SILK_GAP)
    hard |= R.draw(mask_open) | R.draw(silk)
    s_hard = sat(hard)
    s_court = sat(R.draw([p for f in fps for p in courtyard(f)[0]]))
    s_body = sat(R.draw([p for f in fps for p in body(f)]))
    s_via = sat(R.draw(tented))
    boxes = {f.GetReference(): courtyard(f)[1] for f in fps}

    def candidates(lb: Label):
        x0, y0, x1, y1 = lb.box
        out = []
        for ang in (0, 90):
            hw, hh = lb.geom[ang][:2]
            xs = np.arange(x0 - NEAR - hw, x1 + NEAR + hw + 1e-9, STEP * RES)
            ys = np.arange(y0 - NEAR - hh, y1 + NEAR + hh + 1e-9, STEP * RES)
            X, Y = np.meshgrid(xs, ys)
            X, Y = X.ravel(), Y.ravel()
            r0, c0, r1, c1 = lb.cells(R, X, Y, ang)
            ok = (r0 >= 0) & (c0 >= 0) & (r1 < R.ny) & (c1 < R.nx)
            X, Y, r0, c0, r1, c1 = X[ok], Y[ok], r0[ok], c0[ok], r1[ok], c1[ok]
            h = box_sum(s_hard, r0, c0, r1, c1)
            court = box_sum(s_body, r0, c0, r1, c1) * RES * RES
            margin = box_sum(s_court, r0, c0, r1, c1) * RES * RES
            via = box_sum(s_via, r0, c0, r1, c1) * RES * RES
            # gap between the label's box and its courtyard's box
            dx = np.maximum(np.maximum(x0 - (X + hw), (X - hw) - x1), 0)
            dy = np.maximum(np.maximum(y0 - (Y + hh), (Y - hh) - y1), 0)
            dist = np.hypot(dx, dy)
            own = rect_gap(X, Y, lb.box)
            near = [
                b
                for n, b in boxes.items()
                if n != lb.name
                and b[0] < x1 + NEAR + 3
                and b[2] > x0 - NEAR - 3
                and b[1] < y1 + NEAR + 3
                and b[3] > y0 - NEAR - 3
            ]
            other = np.full(len(X), np.inf)
            for b in near:
                other = np.minimum(other, rect_gap(X, Y, b))
            foreign = other < own - 0.05
            cost = (
                W_BODY * court
                + W_COURTYARD * margin
                + W_DIST * dist
                + W_FOREIGN * foreign
                + W_VIA * via
                + (W_TURNED if ang else 0.0)
            )
            out.append((ang, X, Y, h, cost, court, dist, foreign))
        return out

    # each label's best spots, at least SPREAD apart: free of hard obstacles, not hidden under a body
    options: list[list[tuple]] = []
    for lb in labels:
        rows = []
        for ang, X, Y, h, cost, court, dist, foreign in candidates(lb):
            ok = (h == 0) & (court <= HIDDEN) & (dist <= NEAR)
            for i in np.flatnonzero(ok):
                rows.append(
                    (float(cost[i]), ang, float(X[i]), float(Y[i]), float(court[i]), float(dist[i]), bool(foreign[i]))
                )
        rows.sort()
        kept = []
        for r in rows:
            if all(k[1] != r[1] or abs(k[2] - r[2]) + abs(k[3] - r[3]) >= SPREAD for k in kept):
                kept.append(r)
                if len(kept) == OPTIONS:
                    break
        options.append(kept)

    # every pair of spots of two labels closer than SILK_GAP: they cannot both be taken
    spots, owner = [], []
    for li, (lb, opts) in enumerate(zip(labels, options, strict=True)):
        for o in opts:
            hw, hh = lb.geom[o[1]][:2]
            g = SILK_GAP / 2
            spots.append((o[2] - hw - g, o[3] - hh - g, o[2] + hw + g, o[3] + hh + g))
            owner.append(li)
    first = np.cumsum([0] + [len(o) for o in options])
    grid: dict[tuple[int, int], list[int]] = {}
    for s, (x0, y0, x1, y1) in enumerate(spots):
        for gx in range(int(x0 // 2), int(x1 // 2) + 1):
            for gy in range(int(y0 // 2), int(y1 // 2) + 1):
                grid.setdefault((gx, gy), []).append(s)
    clash: list[set[int]] = [set() for _ in spots]
    for cell in grid.values():
        for i in cell:
            a = spots[i]
            for j in cell:
                if j > i and owner[j] != owner[i]:
                    b2 = spots[j]
                    if a[0] < b2[2] and b2[0] < a[2] and a[1] < b2[3] and b2[1] < a[3]:
                        clash[i].add(j)
                        clash[j].add(i)
    clash = [sorted(c) for c in clash]

    # one spot (or none) per label, never two clashing: the labels with the fewest spots choose first,
    # each its cheapest free spot; then a local search moves a label to another of its spots, evicting
    # the labels it clashes with, which take their cheapest spot still free (or none), and keeps the
    # move when the total cost (LOST for a label without a spot) drops, or by annealing
    rng = random.Random(1)
    n = len(labels)
    cost_of = [o[0] for opts in options for o in opts]
    pick = [-1] * n
    hits = [0] * len(spots)  # how many labels' spots clash with each spot

    def take(i, s):
        pick[i] = s
        if s >= 0:
            for j in clash[s]:
                hits[j] += 1

    def drop(i):
        s = pick[i]
        if s >= 0:
            for j in clash[s]:
                hits[j] -= 1
        pick[i] = -1

    def cheapest_free(i):
        for s in range(first[i], first[i + 1]):
            if hits[s] == 0:
                return s
        return -1

    def energy_of(s):
        return LOST if s < 0 else cost_of[s]

    for i in sorted(range(n), key=lambda i: (len(options[i]), labels[i].name)):
        take(i, cheapest_free(i))

    steps = 40 * n * OPTIONS
    for k in range(steps):
        temp = T0 * (T1 / T0) ** (k / steps)
        lost_now = [i for i in range(n) if pick[i] < 0 and options[i]]
        i = rng.choice(lost_now) if lost_now and rng.random() < 0.3 else rng.randrange(n)
        if not options[i]:
            continue
        s = first[i] + rng.randrange(len(options[i]))
        if s == pick[i]:
            continue
        before = {i: pick[i]}
        evicted = sorted({owner[j] for j in clash[s] if pick[owner[j]] == j})
        for e in evicted:
            before[e] = pick[e]
        e0 = sum(energy_of(v) for v in before.values())
        drop(i)
        for e in evicted:
            drop(e)
        take(i, s)
        for e in evicted:
            take(e, cheapest_free(e))
        d = sum(energy_of(pick[v]) for v in before) - e0
        if d <= 0 or rng.random() < math.exp(-d / temp):
            continue
        for v in before:  # undo
            drop(v)
        for v, sv in before.items():
            take(v, sv)

    for i, lb in enumerate(labels):
        if pick[i] >= 0:
            c, ang, x, y, court, dist, foreign = options[i][pick[i] - first[i]]
            lb.at = (x, y, ang, {"cost": c, "court": court, "dist": dist, "foreign": foreign})

    hidden, ambiguous = [], []
    for lb in labels:
        if lb.at is None:
            hidden.append(lb.name)
            lb.ref.SetVisible(False)  # no room by its part: the fab drawing (F.Fab) still names it
            continue
        lb.apply()
        if lb.at[3]["foreign"]:
            ambiguous.append(lb.name)
    board.Save(str(dst))
    print(f"{len(labels) - len(hidden)} of {len(labels)} references shown, {SIZE} mm high")
    if hidden:
        print(f"hidden, no room within {NEAR} mm of the part ({len(hidden)}): {', '.join(hidden)}")
    if ambiguous:
        print(f"shown, but as near another part as their own ({len(ambiguous)}): {', '.join(ambiguous)}")
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--size" in argv:  # a trial size (mm), stroke kept
        i = argv.index("--size")
        SIZE = float(argv[i + 1])
        del argv[i : i + 2]
    args = [Path(a) for a in argv]
    src, dst = (args[0], args[1]) if len(args) == 2 else (PCB, PCB)
    sys.exit(main(src, dst))
