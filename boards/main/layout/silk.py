"""Size and place the main board's reference designators on the silkscreen.

    /usr/bin/python3 boards/main/layout/silk.py              # KiCad's Python (pcbnew), from the repo root
    /usr/bin/python3 boards/main/layout/silk.py IN OUT       # read IN, write OUT (a trial on a copy)
    /usr/bin/python3 boards/main/layout/silk.py --size 0.6   # a trial text size (mm)

Every reference goes on F.Silkscreen (the wall joints' footprints keep theirs on F.Fab; the mounting
holes' references stay there) and becomes SIZE high with a STROKE line, at 0, 90, 45 or 135 degrees (the
owner, 2026-11-08), within NEAR of its part's courtyard, on a spot that is

- never over an opening in the solder mask (pads, untented vias) nor nearer than SILK_GAP to one
  (JLCPCB clips silkscreen off exposed copper; KiCad's DRC reports it as silk_over_copper);
- never nearer than SILK_GAP to other silkscreen (the footprints' outlines and marks, the board's
  texts, the other references; DRC silk_overlap; min_silk_clearance in main.kicad_pro);
- never nearer than EDGE_GAP to the board edge or a cut-out (DRC silk_edge_clearance);
- never over a part's body (its F.Fab drawing): a label there is hidden once the board is assembled;

and, cheapest first, with its centre as near its part's centre as it can be, which puts it along the
part's side (the owner, 2026-11-08), nearer its own part than any other (so it names the right one),
over few courtyard margins and tented vias, parallel to the part's sides (upright before turned) before
askew. Each angle is searched in its own frame, turned with the label, so a 45 degree label is
checked against its own outline, not its bounding box. The labels with the fewest
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

SIZE = 0.4  # mm, the reference text height and width: the board's minimum (main.zen), the owner's choice (2026-11-07: every
# label on the board, a little smaller than the v1 board's 0.5 mm)
STROKE = 0.1  # mm, the board's minimum (rules/kicad-severities.toml): a quarter of SIZE, the stroke font's cap
SILK_GAP = 0.1  # mm, min_silk_clearance (main.kicad_pro), to other silkscreen and to mask openings
EDGE_GAP = 0.2  # mm, to the board edge and its cut-outs
RES = 0.05  # mm, raster cell
STEP = 2  # cells between candidate centres
OPTIONS = 40  # spots kept per label
SPREAD = 0.3  # mm between two kept spots of a label at the same angle
HIDDEN = 0.5  # mm2 of a body under a label that hides it: never chosen
NEAR = 1.2  # mm, the farthest a label may sit from its part's courtyard (1.0 leaves C12 in the STM32's 45 deg row without a spot)
LOST = 400.0  # cost of a label without a spot
T0, T1 = 20.0, 0.05  # annealing temperature, start and end

# cost weights
W_BODY = 40.0  # per mm2 of a part body under the label (hidden once assembled)
W_COURTYARD = 1.0  # per mm2 of a courtyard margin under the label (visible, but crowds the part)
W_CENTRE = 6.0  # per mm between the label's centre and its part's centre, beyond the label's nearest spot
W_FOREIGN = 12.0  # the label's centre is nearer another part's courtyard than its own
W_VIA = 2.0  # per mm2 of tented via under the label
W_TURNED = 0.4  # a label parallel to its part's sides but not upright (90 degrees, or 45/135 on a part at 45)
W_ASKEW = 1.5  # a label at 45 degrees to its part's sides
ANGLES = (0, 90, 45, 135)  # degrees, counterclockwise as KiCad turns text; 135 is drawn upright (-45)


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


def axes(ang: float):
    """The label's frame: u along the text, v across it (KiCad's frame, y down; ang counterclockwise)."""
    a = math.radians(ang)
    return (math.cos(a), -math.sin(a)), (math.sin(a), math.cos(a))


def to_frame(polys, ang):
    (ux, uy), (vx, vy) = axes(ang)

    def t(pts):
        return [(x * ux + y * uy, x * vx + y * vy) for x, y in pts]

    return [(t(o), [t(h) for h in hs]) for o, hs in polys]


def box_to_hull(cx, cy, hw, hh, P):
    """Distance from axis-aligned boxes (centres cx, cy; half extents hw, hh) to a convex polygon P
    (K x 2), 0 where they overlap (separating axes)."""
    P = np.asarray(P, float)
    sep = (P[:, 0].max() < cx - hw) | (P[:, 0].min() > cx + hw) | (P[:, 1].max() < cy - hh) | (P[:, 1].min() > cy + hh)
    Q = np.roll(P, -1, axis=0)
    E = Q - P
    n = np.stack([E[:, 1], -E[:, 0]], 1)
    n /= np.maximum(np.hypot(n[:, 0], n[:, 1]), 1e-12)[:, None]
    pp = P @ n.T  # (K vertices, K normals)
    lo, hi = pp.min(0), pp.max(0)
    c = cx[:, None] * n[:, 0] + cy[:, None] * n[:, 1]
    r = hw * np.abs(n[:, 0]) + hh * np.abs(n[:, 1])
    sep |= ((c - r > hi) | (c + r < lo)).any(1)
    # vertices of the polygon to the boxes, corners of the boxes to the polygon's edges
    d = np.hypot(
        np.maximum(np.abs(P[:, 0] - cx[:, None]) - hw, 0), np.maximum(np.abs(P[:, 1] - cy[:, None]) - hh, 0)
    ).min(1)
    L2 = np.maximum((E**2).sum(1), 1e-12)
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        px, py = cx + sx * hw, cy + sy * hh
        t = np.clip(((px[:, None] - P[:, 0]) * E[:, 0] + (py[:, None] - P[:, 1]) * E[:, 1]) / L2, 0, 1)
        d = np.minimum(d, np.hypot(px[:, None] - P[:, 0] - t * E[:, 0], py[:, None] - P[:, 1] - t * E[:, 1]).min(1))
    return np.where(sep, d, 0.0)


class Label:
    def __init__(self, f):
        self.f, self.ref = f, f.Reference()
        self.name = f.GetReference()
        self.polys, self.box = courtyard(f)
        self.centre = ((self.box[0] + self.box[2]) / 2, (self.box[1] + self.box[3]) / 2)
        self.hull = hull([p for o, _ in self.polys for p in o])
        self.angle = f.GetOrientationDegrees() % 90  # the part's sides, modulo 90
        # the text's half extents along and across it (upright), and the offset from the text position to
        # its centre per angle (KiCad turns the text about its position)
        self.ref.SetTextAngleDegrees(0)
        bb = self.ref.GetBoundingBox()
        self.half = (mm(bb.GetWidth()) / 2, mm(bb.GetHeight()) / 2)
        self.off = {}
        for ang in ANGLES:
            self.ref.SetTextAngleDegrees(ang)
            pos, c = self.ref.GetPosition(), self.ref.GetBoundingBox().GetCenter()
            self.off[ang] = (mm(c.x - pos.x), mm(c.y - pos.y))
        self.at = None  # (x, y, angle, cost terms) of the text's centre

    def turn(self, ang) -> float:
        par = min((ang - self.angle) % 90, (self.angle - ang) % 90) < 1.0
        return 0.0 if ang == 0 and par else W_TURNED if par else W_ASKEW

    def cells(self, R, x, y):
        hw, hh = self.half
        c0 = np.floor((x - hw - R.x0) / RES).astype(int)
        c1 = np.ceil((x + hw - R.x0) / RES).astype(int)
        r0 = np.floor((y - hh - R.y0) / RES).astype(int)
        r1 = np.ceil((y + hh - R.y0) / RES).astype(int)
        return r0, c0, r1, c1

    def apply(self):
        x, y, ang = self.at[:3]
        ox, oy = self.off[ang]
        self.ref.SetTextAngleDegrees(ang)
        self.ref.SetPosition(pcbnew.VECTOR2I(iu(x - ox), iu(y - oy)))


def main(src: Path, dst: Path) -> int:
    board = pcbnew.LoadBoard(str(src))
    edge = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(edge, True)
    bpolys = outlines(edge)
    fps = sorted(board.GetFootprints(), key=lambda f: f.GetReference())
    for f in fps:
        r = f.Reference()
        if r.GetLayer() == pcbnew.F_Fab and not f.GetFPIDAsString().split(":")[-1].startswith("MountingHole"):
            r.SetLayer(pcbnew.F_SilkS)  # the wall joints' footprints keep their reference on F.Fab
        if r.GetLayer() == pcbnew.F_SilkS:
            r.SetVisible(True)  # a label hidden by an earlier run gets another chance
            r.SetTextSize(pcbnew.VECTOR2I(iu(SIZE), iu(SIZE)))
            r.SetTextThickness(iu(STROKE))
            r.SetKeepUpright(True)
    labels = [Label(f) for f in fps if f.Reference().GetLayer() == pcbnew.F_SilkS]

    # what a label may never touch: off the board, mask openings, other silkscreen
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
    courts = [p for f in fps for p in courtyard(f)[0]]
    bodies = [p for f in fps for p in body(f)]
    boxes = {f.GetReference(): courtyard(f)[1] for f in fps}

    # per angle, the obstacles in the label's frame (u along the text, v across it), where the label is a box
    frames = {}
    for ang in ANGLES:
        fb = to_frame(bpolys, ang)
        pts = np.array([p for o, _ in fb for p in o])
        (fx0, fy0), (fx1, fy1) = pts.min(0), pts.max(0)
        R = Raster(fx0 - 1, fy0 - 1, fx1 + 1, fy1 + 1)
        hard = dilate(~R.draw(fb), round(EDGE_GAP / RES))
        hard |= R.draw(to_frame(mask_open, ang)) | R.draw(to_frame(silk, ang))
        frames[ang] = (
            R,
            sat(hard),
            sat(R.draw(to_frame(courts, ang))),
            sat(R.draw(to_frame(bodies, ang))),
            sat(R.draw(to_frame(tented, ang))),
        )

    def candidates(lb: Label):
        x0, y0, x1, y1 = lb.box
        hw, hh = lb.half
        near = [
            b
            for n, b in boxes.items()
            if n != lb.name
            and b[0] < x1 + NEAR + 3
            and b[2] > x0 - NEAR - 3
            and b[1] < y1 + NEAR + 3
            and b[3] > y0 - NEAR - 3
        ]
        out = []
        for ang in ANGLES:
            R, s_hard, s_court, s_body, s_via = frames[ang]
            (ux, uy), (vx, vy) = axes(ang)
            P = np.array([(x * ux + y * uy, x * vx + y * vy) for x, y in lb.hull])
            (px0, py0), (px1, py1) = P.min(0), P.max(0)
            us = np.arange(px0 - NEAR - hw, px1 + NEAR + hw + 1e-9, STEP * RES)
            vs = np.arange(py0 - NEAR - hh, py1 + NEAR + hh + 1e-9, STEP * RES)
            U, V = np.meshgrid(us, vs)
            U, V = U.ravel(), V.ravel()
            r0, c0, r1, c1 = lb.cells(R, U, V)
            ok = (r0 >= 0) & (c0 >= 0) & (r1 < R.ny) & (c1 < R.nx)
            U, V, r0, c0, r1, c1 = U[ok], V[ok], r0[ok], c0[ok], r1[ok], c1[ok]
            h = box_sum(s_hard, r0, c0, r1, c1)
            court = box_sum(s_body, r0, c0, r1, c1) * RES * RES
            margin = box_sum(s_court, r0, c0, r1, c1) * RES * RES
            via = box_sum(s_via, r0, c0, r1, c1) * RES * RES
            dist = box_to_hull(U, V, hw, hh, P)  # the label's gap to its courtyard
            X, Y = U * ux + V * vx, U * uy + V * vy  # the label's centre on the board
            centre = np.hypot(X - lb.centre[0], Y - lb.centre[1])
            own = rect_gap(X, Y, lb.box)
            other = np.full(len(X), np.inf)
            for b in near:
                other = np.minimum(other, rect_gap(X, Y, b))
            foreign = other < own - 0.05
            cost = W_BODY * court + W_COURTYARD * margin + W_FOREIGN * foreign + W_VIA * via + lb.turn(ang)
            out.append((ang, X, Y, h, cost, centre, court, dist, foreign))
        return out

    # each label's best spots, at least SPREAD apart: free of hard obstacles, not hidden under a body; the
    # centre's distance counts from the nearest spot the label has, so a large part costs no more
    options: list[list[tuple]] = []
    for lb in labels:
        cands = candidates(lb)
        oks = [(h == 0) & (court <= HIDDEN) & (dist <= NEAR) for _a, _X, _Y, h, _c, _ce, court, dist, _f in cands]
        best = min((float(c[5][ok].min()) for c, ok in zip(cands, oks, strict=True) if ok.any()), default=0.0)
        rows = []
        for (ang, X, Y, _h, cost, centre, court, dist, foreign), ok in zip(cands, oks, strict=True):
            for i in np.flatnonzero(ok):
                rows.append(
                    (
                        float(cost[i] + W_CENTRE * (centre[i] - best)),
                        ang,
                        float(X[i]),
                        float(Y[i]),
                        float(court[i]),
                        float(dist[i]),
                        bool(foreign[i]),
                    )
                )
        rows.sort()
        kept = []
        for r in rows:
            if all(k[1] != r[1] or abs(k[2] - r[2]) + abs(k[3] - r[3]) >= SPREAD for k in kept):
                kept.append(r)
                if len(kept) == OPTIONS:
                    break
        options.append(kept)

    # every pair of spots of two labels closer than SILK_GAP: they cannot both be taken (turned boxes,
    # separating axes)
    spots, owner = [], []
    g = SILK_GAP / 2
    for li, (lb, opts) in enumerate(zip(labels, options, strict=True)):
        hw, hh = lb.half[0] + g, lb.half[1] + g
        for o in opts:
            u, v = axes(o[1])
            ex = hw * abs(u[0]) + hh * abs(v[0])
            ey = hw * abs(u[1]) + hh * abs(v[1])
            spots.append((o[2], o[3], u, v, hw, hh, (o[2] - ex, o[3] - ey, o[2] + ex, o[3] + ey)))
            owner.append(li)
    first = np.cumsum([0] + [len(o) for o in options])

    def overlap(a, b) -> bool:
        dx, dy = b[0] - a[0], b[1] - a[1]
        for ax in (a[2], a[3], b[2], b[3]):
            ra = a[4] * abs(a[2][0] * ax[0] + a[2][1] * ax[1]) + a[5] * abs(a[3][0] * ax[0] + a[3][1] * ax[1])
            rb = b[4] * abs(b[2][0] * ax[0] + b[2][1] * ax[1]) + b[5] * abs(b[3][0] * ax[0] + b[3][1] * ax[1])
            if abs(dx * ax[0] + dy * ax[1]) >= ra + rb:
                return False
        return True

    grid: dict[tuple[int, int], list[int]] = {}
    for si, sp in enumerate(spots):
        x0, y0, x1, y1 = sp[6]
        for gx in range(int(x0 // 2), int(x1 // 2) + 1):
            for gy in range(int(y0 // 2), int(y1 // 2) + 1):
                grid.setdefault((gx, gy), []).append(si)
    clash: list[set[int]] = [set() for _ in spots]
    for cell in grid.values():
        for i in cell:
            a = spots[i]
            for j in cell:
                if j > i and owner[j] != owner[i] and j not in clash[i]:
                    b2 = spots[j]
                    boxes_meet = a[6][0] < b2[6][2] and b2[6][0] < a[6][2] and a[6][1] < b2[6][3] and b2[6][1] < a[6][3]
                    if boxes_meet and overlap(a, b2):
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
        STROKE = min(STROKE, SIZE / 4)
        del argv[i : i + 2]
    if "--near" in argv:  # a trial search radius (mm)
        i = argv.index("--near")
        NEAR = float(argv[i + 1])
        del argv[i : i + 2]
    args = [Path(a) for a in argv]
    src, dst = (args[0], args[1]) if len(args) == 2 else (PCB, PCB)
    sys.exit(main(src, dst))
