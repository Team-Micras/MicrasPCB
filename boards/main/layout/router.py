"""A small grid router for the layout scripts: joins the copper islands of a net on F.Cu/B.Cu
with octilinear tracks, drawn as a hand-routed board's.

The board is rasterised at 0.05 mm per layer. A cell is free for a net when no copper of another
net, no hole and no board edge lies within the track's half width plus the clearance. Islands of
a net (pads, tracks, vias and pours that touch) are joined one at a time by an A* search from the
island's copper to any other island's copper, over (layer, cell, direction) states:

- tracks run at 0, 45 and 90 degrees only, and turn by 45 degrees (BEND45) or 90 degrees (BEND90,
  dearer, so corners are 45 degree chamfers where there is room); never sharper, so no corner is
  acute; each turn starts a run of at least MINRUN, so there are no small jogs or staircases;
- a route leaves and enters a rectangular pad along the pad's axes, a track end at 90 degrees or
  more to the tracks there, the middle of a straight track square to it;
- cells beside obstacles cost more, so tracks keep off pads where there is room; other nets' pours
  give way (dearer to cross); a via costs VIA_COST.

The found route keeps its directions; its ends move onto the anchors (a via's centre, a track's
end, a pad's centre line, a track's centre line) by changing run lengths only. Deterministic: the
same board gives the same tracks.
"""

from __future__ import annotations

import heapq
import itertools
import math

import numpy as np
import pcbnew
from matplotlib.path import Path as MPath

RES = 0.05
CLR = 0.12  # copper clearance kept by new tracks and vias (the board rule is 0.1 mm)
HOLE_CLR = 0.28  # plated hole to track (rules/jlcpcb.kicad_dru)
VIA_D, VIA_HOLE = 0.45, 0.3
VIA_COST = 60  # in cells (3 mm of track)
BEND45 = 10.0  # a 45 degree turn, in cells
BEND90 = 24.0  # a 90 degree turn: dearer than two 45 degree ones
MINRUN = 0.3  # mm of straight run after each turn
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)
INNER = (pcbnew.In1_Cu, pcbnew.In2_Cu)


def mm(v):
    return pcbnew.ToMM(v)


class Grid:
    def __init__(self, board: pcbnew.BOARD):
        self.b = board
        bb = board.GetBoardEdgesBoundingBox()
        self.x0, self.y0 = mm(bb.GetLeft()) - 0.5, mm(bb.GetTop()) - 0.5
        self.nx = int((mm(bb.GetWidth()) + 1.0) / RES) + 1
        self.ny = int((mm(bb.GetHeight()) + 1.0) / RES) + 1
        outl = pcbnew.SHAPE_POLY_SET()
        board.GetBoardPolygonOutlines(outl, True)
        self.outline = outl
        gx = self.x0 + np.arange(self.nx) * RES
        gy = self.y0 + np.arange(self.ny) * RES
        self.gx, self.gy = np.meshgrid(gx, gy)
        o = outl.Outline(0)
        poly = [(mm(o.CPoint(k).x), mm(o.CPoint(k).y)) for k in range(o.PointCount())]
        pts = np.c_[self.gx.ravel(), self.gy.ravel()]
        inside = MPath(poly).contains_points(pts).reshape(self.gx.shape)
        for h in range(outl.HoleCount(0)):
            ho = outl.Hole(0, h)
            hp = [(mm(ho.CPoint(k).x), mm(ho.CPoint(k).y)) for k in range(ho.PointCount())]
            inside &= ~MPath(hp).contains_points(pts).reshape(self.gx.shape)
        self.inside = inside
        # distance to the board edge, in cells (Euclidean, rounded up; 13 beyond 12 cells)
        self.edge_dist = self._euclid(~inside, 12)

    # --- raster helpers ---------------------------------------------------------------------------

    def ij(self, x, y):
        return round((y - self.y0) / RES), round((x - self.x0) / RES)

    def xy(self, i, j):
        return float(self.x0 + j * RES), float(self.y0 + i * RES)

    clip = None  # (i0, i1, j0, j1): rasterise only inside this window

    def _window(self, x0, y0, x1, y1):
        i0 = max(0, int((y0 - self.y0) / RES) - 1)
        i1 = min(self.ny, int((y1 - self.y0) / RES) + 2)
        j0 = max(0, int((x0 - self.x0) / RES) - 1)
        j1 = min(self.nx, int((x1 - self.x0) / RES) + 2)
        if self.clip is not None:
            i0, i1 = max(i0, self.clip[0]), min(i1, self.clip[1])
            j0, j1 = max(j0, self.clip[2]), min(j1, self.clip[3])
        return i0, i1, j0, j1

    def segment_mask(self, a, b, r, mask, value=True):
        i0, i1, j0, j1 = self._window(
            min(a[0], b[0]) - r, min(a[1], b[1]) - r, max(a[0], b[0]) + r, max(a[1], b[1]) + r
        )
        if i0 >= i1 or j0 >= j1:
            return
        sx, sy = self.gx[i0:i1, j0:j1], self.gy[i0:i1, j0:j1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        if L2 == 0:
            d = np.hypot(sx - a[0], sy - a[1])
        else:
            t = np.clip(((sx - a[0]) * dx + (sy - a[1]) * dy) / L2, 0, 1)
            d = np.hypot(sx - (a[0] + t * dx), sy - (a[1] + t * dy))
        sel = d <= r
        mask[i0:i1, j0:j1][sel] = value

    def poly_mask(self, sps: pcbnew.SHAPE_POLY_SET, grow: float, mask, value=True):
        for k in range(sps.OutlineCount()):
            o = sps.Outline(k)
            poly = [(mm(o.CPoint(q).x), mm(o.CPoint(q).y)) for q in range(o.PointCount())]
            if len(poly) < 3:
                continue
            xs, ys = [p[0] for p in poly], [p[1] for p in poly]
            i0, i1, j0, j1 = self._window(min(xs) - grow, min(ys) - grow, max(xs) + grow, max(ys) + grow)
            if i0 >= i1 or j0 >= j1:
                continue
            sub = np.c_[self.gx[i0:i1, j0:j1].ravel(), self.gy[i0:i1, j0:j1].ravel()]
            m = MPath(poly).contains_points(sub).reshape(i1 - i0, j1 - j0)
            for h in range(sps.HoleCount(k)):
                ho = sps.Hole(k, h)
                hp = [(mm(ho.CPoint(q).x), mm(ho.CPoint(q).y)) for q in range(ho.PointCount())]
                m &= ~MPath(hp).contains_points(sub).reshape(i1 - i0, j1 - j0)
            if grow > 0:
                m = self._dilate(m, math.ceil(grow / RES))
                # the polygon's edges, grown, also catch thin features the cell centres miss
                for q in range(len(poly)):
                    self.segment_mask(poly[q], poly[(q + 1) % len(poly)], grow, mask, value)
            mask[i0:i1, j0:j1][m] = value

    @staticmethod
    def _dilate(m, k):
        out = m.copy()
        for di in range(-k, k + 1):
            for dj in range(-k, k + 1):
                if di * di + dj * dj > k * k:
                    continue
                sh = np.zeros_like(m)
                si0, si1 = max(0, di), m.shape[0] + min(0, di)
                sj0, sj1 = max(0, dj), m.shape[1] + min(0, dj)
                if si1 <= si0 or sj1 <= sj0:
                    continue
                sh[si0:si1, sj0:sj1] = m[si0 - di : si1 - di, sj0 - dj : sj1 - dj]
                out |= sh
        return out

    @staticmethod
    def _euclid(m, kmax):
        """Distance in cells from each cell to the nearest set cell of m, rounded up, capped at kmax + 1."""
        d = np.full(m.shape, float(kmax + 1))
        for di in range(-kmax, kmax + 1):
            for dj in range(-kmax, kmax + 1):
                r = math.hypot(di, dj)
                if r > kmax:
                    continue
                sh = np.zeros_like(m)
                si0, si1 = max(0, di), m.shape[0] + min(0, di)
                sj0, sj1 = max(0, dj), m.shape[1] + min(0, dj)
                sh[si0:si1, sj0:sj1] = m[si0 - di : si1 - di, sj0 - dj : sj1 - dj]
                d[sh & (d > r)] = r
        return np.ceil(d - 1e-9).astype(np.int16)

    @staticmethod
    def _distance(m, kmax):
        d = np.full(m.shape, kmax + 1, dtype=np.int16)
        cur = m.copy()
        d[cur] = 0
        for k in range(1, kmax + 1):
            nxt = cur.copy()
            nxt[1:, :] |= cur[:-1, :]
            nxt[:-1, :] |= cur[1:, :]
            nxt[:, 1:] |= cur[:, :-1]
            nxt[:, :-1] |= cur[:, 1:]
            d[nxt & ~cur] = k
            cur = nxt
        return d


class Router:
    def __init__(self, board: pcbnew.BOARD):
        self.b = board
        self.g = Grid(board)
        self.created = []
        self.graveyard = []  # removed items stay referenced: their SWIG proxies do not own them
        self.hard_pours = False  # other nets' pours as obstacles, not as dearer cells
        self.plane_edges = self._plane_edges()

    def _plane_edges(self) -> np.ndarray:
        """Cells where a via's clearance hole in an inner-layer pour would leave a sliver: within
        a via's radius, a pour's clearance and the narrowest copper feature (0.09 mm, the PDK) of
        the outline of an inner-layer pour (where two pours meet, or a pour ends)."""
        g = self.g
        band = np.zeros(g.gx.shape, bool)
        r = VIA_D / 2 + 0.25 + 0.09
        for layer in INNER:
            for z in self.b.Zones():
                if z.GetIsRuleArea() or not z.IsOnLayer(layer):
                    continue
                outline = z.Outline()  # the drawn outline: the fill's is fractured around holes
                for k in range(outline.OutlineCount()):
                    o = outline.Outline(k)
                    pts = [(mm(o.CPoint(q).x), mm(o.CPoint(q).y)) for q in range(o.PointCount())]
                    for a, c in zip(pts, pts[1:] + pts[:1], strict=True):
                        g.segment_mask(a, c, r, band)
        return band

    # obstacles for a net: other nets' copper grown by r, holes, edge
    def blocked(self, netcode: int, half: float, clr: float = CLR, box=None) -> dict:
        """Cells a track of this net cannot use, per outer layer; "soft": other nets' pours, which
        give way to a track when refilled (dearer to cross); "inner"/"novia": where vias cannot go.
        With box (i0, i1, j0, j1), only that window is computed (the rest reads as free)."""
        # rasterise 1.5 mm beyond the window, so the growth of copper outside it is right inside
        k = int(1.5 / RES)
        self.g.clip = None if box is None else (box[0] - k, box[1] + k, box[2] - k, box[3] + k)
        try:
            return self._blocked(netcode, half, clr)
        finally:
            self.g.clip = None

    def _blocked(self, netcode: int, half: float, clr: float) -> dict:
        g, b = self.g, self.b
        r = half + clr
        out = {}
        for layer in LAYERS:
            m = np.zeros(g.gx.shape, bool)
            soft = np.zeros(g.gx.shape, bool)
            for t in b.GetTracks():
                if t.GetNetCode() == netcode:
                    continue
                if t.GetClass() == "PCB_VIA":
                    c = t.GetPosition()
                    rr = max(mm(t.Cast().GetWidth(layer)) / 2 + r, mm(t.Cast().GetDrillValue()) / 2 + 0.2 + half) + 0.03
                    g.segment_mask((mm(c.x), mm(c.y)), (mm(c.x), mm(c.y)), rr, m)
                elif t.GetLayer() == layer:
                    g.segment_mask(
                        (mm(t.GetStart().x), mm(t.GetStart().y)),
                        (mm(t.GetEnd().x), mm(t.GetEnd().y)),
                        mm(t.GetWidth()) / 2 + r,
                        m,
                    )
            for f in b.GetFootprints():
                for p in f.Pads():
                    if p.HasHole():
                        c = p.GetPosition()
                        hr = mm(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2
                        extra = HOLE_CLR if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH else 0.2
                        if p.GetNetCode() != netcode or p.GetAttribute() != pcbnew.PAD_ATTRIB_PTH:
                            g.segment_mask((mm(c.x), mm(c.y)), (mm(c.x), mm(c.y)), hr + extra + half, m)
                    if p.GetNetCode() == netcode and netcode > 0:
                        continue
                    if p.IsOnLayer(layer):
                        g.poly_mask(p.GetEffectivePolygon(layer, pcbnew.ERROR_OUTSIDE), r, m)
            for z in b.Zones():
                if z.GetNetCode() == netcode or z.GetIsRuleArea() or not z.IsOnLayer(layer):
                    continue
                # teardrops (priority 100 and up) stay; pours yield to the new track
                g.poly_mask(z.GetFilledPolysList(layer), r, m if z.GetAssignedPriority() >= 100 else soft)
            m |= g.edge_dist <= math.ceil((0.2 + half) / RES)
            out[layer] = m
            out[("soft", layer)] = soft & ~m
        # inner-layer tracks constrain vias
        inner = np.zeros(g.gx.shape, bool)
        for t in b.GetTracks():
            if t.GetClass() != "PCB_VIA" and t.GetLayer() in INNER and t.GetNetCode() != netcode:
                g.segment_mask(
                    (mm(t.GetStart().x), mm(t.GetStart().y)),
                    (mm(t.GetEnd().x), mm(t.GetEnd().y)),
                    mm(t.GetWidth()) / 2 + VIA_HOLE / 2 + 0.2,
                    inner,
                )
        out["inner"] = inner
        # vias: no SMD pad, no other hole closer than the hole-to-hole rules
        novia_mask = np.zeros(g.gx.shape, bool)
        for f in b.GetFootprints():
            for p in f.Pads():
                if p.IsOnLayer(pcbnew.F_Cu) and not p.HasHole():
                    # a via may sit beside its own net's pad, not in it
                    grow = 0.0 if p.GetNetCode() == netcode and netcode > 0 else VIA_D / 2 + CLR
                    g.poly_mask(p.GetEffectivePolygon(pcbnew.F_Cu, pcbnew.ERROR_OUTSIDE), grow, novia_mask)
                if p.HasHole():
                    c = p.GetPosition()
                    hr = mm(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2
                    g.segment_mask((mm(c.x), mm(c.y)), (mm(c.x), mm(c.y)), hr + VIA_HOLE / 2 + 0.5, novia_mask)
        for t in b.GetTracks():
            if t.GetClass() == "PCB_VIA":
                c = t.GetPosition()
                g.segment_mask((mm(c.x), mm(c.y)), (mm(c.x), mm(c.y)), VIA_HOLE + 0.25, novia_mask)
        novia_mask |= g.edge_dist <= math.ceil((0.25 + VIA_D / 2) / RES)
        novia_mask |= self.plane_edges
        out["novia"] = novia_mask
        return out

    def copper(self, netcode: int) -> list:
        """The net's copper as islands of (kind, item), from KiCad's own connectivity."""
        b = self.b
        items = []
        for f in b.GetFootprints():
            for p in f.Pads():
                if p.GetNetCode() == netcode:
                    items.append(("pad", p))
        for t in b.GetTracks():
            if t.GetNetCode() == netcode:
                items.append(("via" if t.GetClass() == "PCB_VIA" else "track", t))
        for z in b.Zones():
            # a pour that fills nothing (a teardrop below the minimum width) is no copper
            if (
                z.GetNetCode() == netcode
                and not z.GetIsRuleArea()
                and any(z.GetFilledPolysList(lay).OutlineCount() for lay in (*LAYERS, *INNER) if z.IsOnLayer(lay))
            ):
                items.append(("zone", z))
        b.BuildConnectivity()
        conn = b.GetConnectivity()
        index = {o.m_Uuid.AsString(): k for k, (_, o) in enumerate(items)}
        parent = list(range(len(items)))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for k, (_, o) in enumerate(items):
            for other in conn.GetConnectedItems(o):
                j = index.get(other.m_Uuid.AsString())
                if j is not None:
                    parent[find(k)] = find(j)
        groups = {}
        for k in range(len(items)):
            groups.setdefault(find(k), []).append(items[k])
        return list(groups.values())

    # --- where a route may start and end -----------------------------------------------------------

    def anchors(self, island, layer):
        """The island's copper on a layer as cells, each naming the anchor a route ends on there:
        a mask, an owner index per cell (-1: none) and the anchors, each (kind, data, dirs) with
        dirs the 8-bit set of directions a route may enter by (leave by: the opposite ones)."""
        g = self.g
        owner = np.full(g.gx.shape, -1, np.int32)
        out = []

        def add(anchor):
            out.append(anchor)
            return len(out) - 1

        # own-net track ends, the directions their tracks leave each end by, the narrowest there
        leave, narrow = {}, {}
        for kind, o in island:
            if kind == "track" and o.GetLayer() == layer:
                a, b = _pt(o.GetStart()), _pt(o.GetEnd())
                if a == b:
                    continue
                for p, q in ((a, b), (b, a)):
                    key = (round(p[0], 4), round(p[1], 4))
                    leave.setdefault(key, []).append(_unit(p, q))
                    narrow[key] = min(narrow.get(key, 9.0), mm(o.GetWidth()))
        # lowest priority first: pours, track middles, track ends, vias, pads
        for kind, o in island:
            if kind == "zone" and o.IsOnLayer(layer):
                g.poly_mask(o.GetFilledPolysList(layer), 0.0, owner, add(("zone", None, ALL)))
        for kind, o in island:
            if kind != "track" or o.GetLayer() != layer:
                continue
            a, b = _pt(o.GetStart()), _pt(o.GetEnd())
            w, ins = mm(o.GetWidth()), 0.3
            if math.dist(a, b) < 2 * ins + 0.1 or w < 0.12:
                continue
            u = _unit(a, b)
            # a T joins a straight middle square to it (no acute angle on either side)
            dirs = _bits(k for k in range(8) if abs(DIRS[k][0] * u[0] + DIRS[k][1] * u[1]) < 0.02)
            if dirs:
                ends = (a[0] + u[0] * ins, a[1] + u[1] * ins), (b[0] - u[0] * ins, b[1] - u[1] * ins)
                g.segment_mask(*ends, max(w / 2 - 0.04, 0.01), owner, add(("mid", (a, b), dirs)))
        for p, us in leave.items():
            # a route joining a track end keeps 90 degrees or more to every track there
            dirs = _bits(k for k in range(8) if all(DIRS[k][0] * u[0] + DIRS[k][1] * u[1] > -0.02 for u in us))
            g.segment_mask(p, p, min(max(narrow[p] / 2 - 0.03, 0.03), 0.06), owner, add(("end", p, dirs)))
        for kind, o in island:
            if kind == "via":
                c = _pt(o.GetPosition())
                g.segment_mask(c, c, 0.06, owner, add(("via", c, ALL)))
        for kind, o in island:
            if kind == "pad" and o.IsOnLayer(layer):
                c = _pt(o.GetPosition())
                # rectangular pads are entered along their axes, round ones from any side
                deg = o.GetOrientation().AsDegrees() % 90
                if o.GetShape() == pcbnew.PAD_SHAPE_CIRCLE or min(deg % 45, 45 - deg % 45) > 0.5:
                    dirs = ALL
                else:
                    dirs = _bits(range(round(deg / 45) % 2, 8, 2))
                n = add(("pad", (c, o), dirs))
                g.poly_mask(o.GetEffectivePolygon(layer, pcbnew.ERROR_INSIDE), 0.0, owner, n)
                owner[g.ij(*c)] = n
        m = owner >= 0
        return m, owner, out

    def island_cells(self, island, layer) -> np.ndarray:
        return self.anchors(island, layer)[0]

    # --- routing -----------------------------------------------------------------------------------

    def route_net(
        self,
        netname: str,
        width: float = 0.2,
        margin: float = 6.0,
        layers=LAYERS,
        clr: float = CLR,
        minrun: float = MINRUN,
        vias: bool = True,
    ) -> list:
        """Join the net's islands; returns the new segments and vias as
        [(layer, (x0, y0), (x1, y1)) | ("via", (x, y))]."""
        b = self.b
        net = b.FindNet(netname)
        nc = net.GetNetCode()
        added = []
        for _ in range(60):
            islands = self.copper(nc)
            if len(islands) < 2:
                break
            # islands without outer-layer copper (an inner pour on its own) cannot be reached here
            outer = [isl for isl in islands if any(self.island_cells(isl, L).any() for L in layers)]
            if len(outer) < 2:
                break
            blk = self.blocked(nc, width / 2, clr)
            outer.sort(key=len)
            new = None
            # from the smallest island to any other; an island boxed in may still be reached from
            # another, so each island gets its turn as the source
            for k, src in enumerate(outer):
                tgt = [it for n_, isl in enumerate(outer) if n_ != k for it in isl]
                new = self.join(net, width, src, tgt, layers, clr, margin, minrun, vias, blk)
                if new is not None:
                    break
            if new is None:
                raise RuntimeError(f"{netname}: no route between its islands")
            added += new
        return added

    def join(
        self, net, width, src, tgt, layers=LAYERS, clr=CLR, margin=6.0, minrun=MINRUN, vias=True, blk=None, check=None
    ) -> list | None:
        """One route from the copper items src to the copper items tgt (each [(kind, item)], kinds
        as copper() gives them); returns the new segments and vias, or None. self.created lists the
        new items as (kind, item). check(created) -> bool accepts or rejects a found route."""
        sa = {L: self.anchors(src, L) for L in layers}
        ta = {L: self.anchors(tgt, L) for L in layers}
        # a route the check rejects (the raster is approximate) is tried again further out
        box = self._box(sa, ta, layers, 2 * margin + 1.0)
        if box is None:
            return None
        # a route the check rejects (the raster is approximate) is tried again further out; with a
        # check, a pair the router cannot join at clr is tried at the board's 0.1 mm
        tries = [clr, clr + 0.04, clr + 0.08] if check else [clr]
        while tries:
            c = tries.pop(0)
            b_ = blk if blk is not None and c == clr else self.blocked(net.GetNetCode(), width / 2, c, box)
            path = None
            for mg, run in dict.fromkeys(((margin, minrun), (margin, min(minrun, 0.15)), (2 * margin, minrun))):
                path = self._search(sa, ta, b_, layers, mg, run, vias)
                if path is not None:
                    break
            if path is None:
                tries = [0.1] if check and c > 0.1 and c == clr else []
                continue
            # the end correction spread three ways, until one passes the check
            for mode in FITS if check else FITS[:1]:
                out = self._commit(path, sa, ta, net, width, mode)
                if check is None or check(self.created):
                    return out
                for _, o in self.created:
                    self.b.Remove(o)
                    self.graveyard.append(o)
                self.created = []
        return None

    def _box(self, sa, ta, layers, margin):
        """The search window: the source copper and the target cell nearest to it, grown by margin."""
        g = self.g
        ys, xs = [], []
        for L in layers:
            ii, jj = np.nonzero(sa[L][0])
            ys += [ii.min(), ii.max()] if len(ii) else []
            xs += [jj.min(), jj.max()] if len(jj) else []
        if not ys:
            return None
        ci, cj = (min(ys) + max(ys)) / 2, (min(xs) + max(xs)) / 2
        best = None
        for L in layers:
            ii, jj = np.nonzero(ta[L][0])
            if len(ii):
                n = int(np.argmin((ii - ci) ** 2 + (jj - cj) ** 2))
                d = (ii[n] - ci) ** 2 + (jj[n] - cj) ** 2
                if best is None or d < best[0]:
                    best = (d, int(ii[n]), int(jj[n]))
        if best is not None:
            ys.append(best[1])
            xs.append(best[2])
        k = int(margin / RES)
        return max(0, min(ys) - k), min(g.ny, max(ys) + k + 1), max(0, min(xs) - k), min(g.nx, max(xs) + k + 1)

    def _search(self, sa, ta, blk, layers, margin, minrun, vias=True):
        """A* over (layer, cell, direction): straight steps, 45 and 90 degree turns that each start
        a run of at least minrun, vias; never a sharper turn. Returns [(layer, i, j, dir)]."""
        g = self.g
        win = self._box(sa, ta, layers, margin)
        if win is None:
            return None
        i0, i1, j0, j1 = win
        H, W = i1 - i0, j1 - j0
        nl = len(layers)
        sl = np.s_[i0:i1, j0:j1]
        free = np.zeros((nl, H, W), bool)
        target = np.zeros((nl, H, W), bool)
        start = np.zeros((nl, H, W), bool)
        enter = np.zeros((nl, H, W), np.uint8)
        leave = np.zeros((nl, H, W), np.uint8)
        cost = np.ones((nl, H, W))
        for li, L in enumerate(layers):
            free[li] = ~blk[L][sl] & g.inside[sl]
            if self.hard_pours:
                free[li] &= ~blk[("soft", L)][sl]
            # keep off obstacles where there is room: a hand-routed track does not hug them
            near = Grid._distance(~free[li], 2) <= 2
            cost[li][near] = 1.3
            cost[li][blk[("soft", L)][sl]] = 4.0
            tm, tow, tan = ta[L]
            target[li] = tm[sl]
            dirs = np.array([a[2] for a in tan] + [0], np.uint8)
            enter[li] = dirs[tow[sl]]
            sm, sow, san = sa[L]
            start[li] = sm[sl]
            dirs = np.array([_opposite(a[2]) for a in san] + [0], np.uint8)
            leave[li] = dirs[sow[sl]]
            # own copper is enterable where it is a via, a track end or a pad's centre; elsewhere (a
            # pad, a track's middle, a pour) only where other copper leaves room
            for ow, an in ((tow, tan), (sow, san)):
                core = np.array([a[0] in ("via", "end") for a in an] + [False])
                free[li] |= core[ow[sl]]
                for a in an:
                    if a[0] == "pad":
                        i, j = g.ij(*a[1][0])
                        if i0 <= i < i1 and j0 <= j < j1:
                            free[li, i - i0, j - j0] = True
        target &= ~start
        if not target.any():
            return None
        via_ok = ~blk["novia"][sl] & ~blk["inner"][sl]
        rv = math.ceil((VIA_D / 2 + CLR) / RES)
        if nl == 2 and vias:
            both = free[0] & free[1] & ~start.any(0) & ~target.any(0)
            via_ok &= Grid._distance(~both, max(rv - 2, 0) + 1) > max(rv - 2, 0)
        else:
            via_ok[:] = False
        # heuristic: Chebyshev distance to the nearest target cell on any layer (admissible)
        h = Grid._distance(target.any(0), H + W).astype(np.float64)
        run = max(1, round(minrun / RES))
        INF = float("inf")
        dist = np.full((nl, H, W, 9), INF)
        prev = {}
        heap = []
        for li, i, j in zip(*np.nonzero(start & free), strict=True):
            dist[li, i, j, 8] = 0.0
            heapq.heappush(heap, (h[i, j], 0.0, int(li), int(i), int(j), 8))
        found = None
        free_l = [free[li] for li in range(nl)]
        while heap:
            _, d, li, i, j, dr = heapq.heappop(heap)
            if d > dist[li, i, j, dr]:
                continue
            if target[li, i, j]:
                found = (li, i, j, dr)
                break
            fl, cl = free_l[li], cost[li]
            insrc = start[li, i, j]
            for nd in range(8):
                if dr == 8:
                    turn, n = 0, 1
                else:
                    turn = (nd - dr) % 8
                    turn = min(turn, 8 - turn)
                    if turn > 2:
                        continue
                    n = 1 if turn == 0 else run
                di, dj = STEPS[nd]
                step = 1.414 if di and dj else 1.0
                nd_cost = d + (BEND45 if turn == 1 else BEND90 if turn == 2 else 0.0)
                ci, cj, src = i, j, insrc
                ok = True
                for _s in range(n):
                    ni, nj = ci + di, cj + dj
                    if not (0 <= ni < H and 0 <= nj < W) or not fl[ni, nj]:
                        ok = False
                        break
                    if di and dj and not (fl[ci + di, cj] or fl[ci, cj + dj]):
                        ok = False
                        break
                    if src and not start[li, ni, nj] and not (leave[li, ci, cj] >> nd) & 1:
                        ok = False  # leaves its pad or track off its axes
                        break
                    nd_cost += step * cl[ni, nj]
                    ci, cj, src = ni, nj, start[li, ni, nj]
                    if target[li, ci, cj]:
                        if not (enter[li, ci, cj] >> nd) & 1:
                            ok = False
                        break
                if not ok:
                    continue
                if nd_cost < dist[li, ci, cj, nd]:
                    dist[li, ci, cj, nd] = nd_cost
                    prev[(li, ci, cj, nd)] = (li, i, j, dr)
                    heapq.heappush(heap, (nd_cost + h[ci, cj], nd_cost, li, ci, cj, nd))
            if via_ok[i, j] and dr != 8:
                ol = 1 - li
                nd_cost = d + VIA_COST
                if free[ol, i, j] and nd_cost < dist[ol, i, j, 8]:
                    dist[ol, i, j, 8] = nd_cost
                    prev[(ol, i, j, 8)] = (li, i, j, dr)
                    heapq.heappush(heap, (nd_cost + h[i, j], nd_cost, ol, i, j, 8))
        if found is None:
            return None
        states = [found]
        while states[-1] in prev:
            states.append(prev[states[-1]])
        states.reverse()
        # drop the wander inside the source copper: start at the cell the route leaves it from
        k = 0
        for n_, (li, i, j, _dr) in enumerate(states):
            if start[li, i, j]:
                k = n_
        states = states[k:]
        return [(layers[li], i + i0, j + j0, dr) for li, i, j, dr in states]

    # --- geometry ----------------------------------------------------------------------------------

    def _commit(self, states, sa, ta, net, width, mode="all"):
        """Tracks and vias of a found route, octilinear: the cells' corners, the ends moved onto
        the anchors (a pad's centre line, a via's centre, a track's end or centre line) by
        changing run lengths, never directions."""
        g, b = self.g, self.b
        self.created = []
        # pieces per layer: corner points of the runs
        pieces = [[states[0]]]
        for s in states[1:]:
            if s[0] != pieces[-1][-1][0]:
                pieces.append([s])
            else:
                pieces[-1].append(s)
        polys = []
        for piece in pieces:
            pts = [g.xy(piece[0][1], piece[0][2])]
            dirs = []
            for _s, (_, i2, j2, dr2) in itertools.pairwise(piece):
                if dirs and dirs[-1] == dr2:
                    pts[-1] = g.xy(i2, j2)
                else:
                    dirs.append(dr2)
                    pts.append(g.xy(i2, j2))
            polys.append((piece[0][0], pts, dirs))
        L0, i0_, j0_ = states[0][0], states[0][1], states[0][2]
        L1, i1_, j1_ = states[-1][0], states[-1][1], states[-1][2]
        a_src = sa[L0][2][sa[L0][1][i0_, j0_]]
        a_tgt = ta[L1][2][ta[L1][1][i1_, j1_]]
        fixed_prev = None
        out_polys = []
        for n_, (layer, pts, dirs) in enumerate(polys):
            first, last = n_ == 0, n_ == len(polys) - 1
            pts = [list(p) for p in pts]
            if not dirs:  # a via straight onto the next layer's anchor
                p = fixed_prev or pts[0]
                out_polys.append((layer, [tuple(p)]))
                fixed_prev = p
                continue
            fs = fixed_prev if not first else (a_src[1] if a_src[0] in ("via", "end") else None)
            fe = a_tgt[1] if last and a_tgt[0] in ("via", "end") else None
            if fs is not None:
                dx, dy = fs[0] - pts[0][0], fs[1] - pts[0][1]
                pts = [[x + dx, y + dy] for x, y in pts]
            if fe is not None:
                r = (fe[0] - pts[-1][0], fe[1] - pts[-1][1])
                # change run lengths (the runs keep their place); only a straight run moves across
                pts = _fit(pts, dirs, r, move=fs is None, mode=mode)
            if first:
                pts = _to_line(pts, dirs, a_src, at_start=True)
            if last:
                pts = _to_line(pts, dirs, a_tgt, at_start=False)
            fixed_prev = pts[-1]
            out_polys.append((layer, [tuple(p) for p in pts]))
        out = []
        for n_, (layer, pts) in enumerate(out_polys):
            for a, c in itertools.pairwise(pts):
                if math.dist(a, c) < 1e-4:
                    continue
                t = pcbnew.PCB_TRACK(b)
                t.SetStart(_v(a))
                t.SetEnd(_v(c))
                t.SetWidth(pcbnew.FromMM(width))
                t.SetLayer(layer)
                t.SetNet(net)
                b.Add(t)
                self.created.append(("track", t))
                out.append((layer, a, c))
            if n_ + 1 < len(out_polys):
                x, y = pts[-1]
                v = pcbnew.PCB_VIA(b)
                v.SetPosition(_v((x, y)))
                v.SetWidth(pcbnew.FromMM(VIA_D))
                v.SetDrill(pcbnew.FromMM(VIA_HOLE))
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetNet(net)
                b.Add(v)
                self.created.append(("via", v))
                out.append(("via", (x, y)))
        return out


# --- octilinear helpers ------------------------------------------------------------------------------

# direction k: (di, dj) in cells (i down, j right); DIRS: unit (x, y)
STEPS = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)]
DIRS = [(dj / math.hypot(di, dj), di / math.hypot(di, dj)) for di, dj in STEPS]
ALL = 0xFF


def _bits(ks) -> int:
    v = 0
    for k in ks:
        v |= 1 << k
    return v


def _opposite(bits: int) -> int:
    """The directions a route leaves by, from the ones it may enter by."""
    return _bits((k + 4) % 8 for k in range(8) if (bits >> k) & 1)


def _pt(p):
    return (mm(p.x), mm(p.y))


def _v(p):
    return pcbnew.VECTOR2I(pcbnew.FromMM(round(p[0], 4)), pcbnew.FromMM(round(p[1], 4)))


def _unit(a, b):
    d = math.dist(a, b)
    return ((b[0] - a[0]) / d, (b[1] - a[1]) / d)


FITS = ("all", "last", "first")  # the runs a route's end correction is spread over


def _fit(pts, dirs, r, move=False, mode="all"):
    """Move the last point by r, changing run lengths only (least change, weighted by length):
    over every run ("all"), or over the last (or first) run and the nearest run not parallel to
    it, so only the corners there move. When every run is parallel, the part of r across them
    stays (the end lands off centre), or with move the whole route shifts by it."""
    lens = [math.dist(a, c) for a, c in itertools.pairwise(pts)]
    us = [DIRS[d] for d in dirs]
    w = [max(L, 0.05) for L in lens]
    if mode != "all" and len(dirs) > 1:
        order = list(range(len(dirs)))[:: -1 if mode == "last" else 1]
        pick = [order[0], *[k for k in order[1:] if dirs[k] % 4 != dirs[order[0]] % 4][:1]]
        w = [wk if k in pick else 1e-9 for k, wk in enumerate(w)]
    # A W A^T
    m00 = sum(wk * u[0] * u[0] for wk, u in zip(w, us, strict=True))
    m01 = sum(wk * u[0] * u[1] for wk, u in zip(w, us, strict=True))
    m11 = sum(wk * u[1] * u[1] for wk, u in zip(w, us, strict=True))
    det = m00 * m11 - m01 * m01
    if abs(det) < 1e-9:
        if move:
            return [[x + r[0], y + r[1]] for x, y in pts]
        u = us[0]
        along = r[0] * u[0] + r[1] * u[1]
        dl = [wk * along / sum(w) for wk in w]
    else:
        l0 = (m11 * r[0] - m01 * r[1]) / det
        l1 = (-m01 * r[0] + m00 * r[1]) / det
        dl = [wk * (u[0] * l0 + u[1] * l1) for wk, u in zip(w, us, strict=True)]
    if any(L + d < 0.02 for L, d in zip(lens, dl, strict=True)):
        return pts
    out = [pts[0]]
    for L, d, u in zip(lens, dl, us, strict=True):
        x, y = out[-1]
        out.append([x + u[0] * (L + d), y + u[1] * (L + d)])
    return out


def _to_line(pts, dirs, anchor, at_start):
    """Lengthen or shorten the end run onto a pad's centre (along the run) or a track's centre line."""
    kind, data, _ = anchor
    k = 0 if at_start else -1
    u = DIRS[dirs[k]]
    p = pts[k]
    q = pts[1] if at_start else pts[-2]
    if kind == "pad":
        (cx, cy), pad = data
        s = (cx - p[0]) * u[0] + (cy - p[1]) * u[1]
        np_ = [p[0] + s * u[0], p[1] + s * u[1]]
        if not pad.HitTest(_v(np_)):
            return pts
    elif kind == "mid":
        a, c = data
        t = _unit(a, c)
        n = (-t[1], t[0])
        den = u[0] * n[0] + u[1] * n[1]
        if abs(den) < 1e-6:
            return pts
        s = ((a[0] - p[0]) * n[0] + (a[1] - p[1]) * n[1]) / den
        np_ = [p[0] + s * u[0], p[1] + s * u[1]]
    else:
        return pts
    # the run keeps its direction and some length
    a_, c_ = (np_, q) if at_start else (q, np_)
    if (c_[0] - a_[0]) * u[0] + (c_[1] - a_[1]) * u[1] < 0.02:
        return pts
    pts = list(pts)
    pts[k] = np_
    return pts
