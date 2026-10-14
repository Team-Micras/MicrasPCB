"""A small grid router for fixes.py: joins the copper islands of a net on F.Cu/B.Cu.

The board is rasterised at 0.05 mm per layer. A cell is free for a net when no copper of another
net, no hole and no board edge lies within the track's half width plus the clearance. Islands of
a net (pads, tracks, vias and pours that touch) are joined one at a time by a Dijkstra search
from the island's copper to any other island's copper, on 8-connected cells (45 degree tracks),
with vias where both outer layers and the inner layers leave room. Deterministic: the same board
gives the same tracks.
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
VIA_COST = 30  # in cells
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
        # distance to the board edge, in cells (approximate, by erosion steps)
        self.edge_dist = self._distance(~inside, 12)

    # --- raster helpers ---------------------------------------------------------------------------

    def ij(self, x, y):
        return round((y - self.y0) / RES), round((x - self.x0) / RES)

    def xy(self, i, j):
        return float(self.x0 + j * RES), float(self.y0 + i * RES)

    def _window(self, x0, y0, x1, y1):
        i0 = max(0, int((y0 - self.y0) / RES) - 1)
        i1 = min(self.ny, int((y1 - self.y0) / RES) + 2)
        j0 = max(0, int((x0 - self.x0) / RES) - 1)
        j1 = min(self.nx, int((x1 - self.x0) / RES) + 2)
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
                sh[si0:si1, sj0:sj1] = m[si0 - di : si1 - di, sj0 - dj : sj1 - dj]
                out |= sh
        return out

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

    # obstacles for a net: other nets' copper grown by r, holes, edge
    def blocked(self, netcode: int, half: float, clr: float = CLR) -> dict:
        """Cells a track of this net cannot use, per outer layer; "soft": other nets' pours, which
        give way to a track when refilled (dearer to cross); "inner"/"novia": where vias cannot go."""
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
                    rr = max(mm(t.Cast().GetWidth(layer)) / 2 + r, VIA_HOLE / 2 + 0.2 + half) + 0.03
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
                    g.poly_mask(p.GetEffectivePolygon(pcbnew.F_Cu, pcbnew.ERROR_OUTSIDE), VIA_D / 2 + CLR, novia_mask)
                if p.HasHole():
                    c = p.GetPosition()
                    hr = mm(max(p.GetDrillSize().x, p.GetDrillSize().y)) / 2
                    g.segment_mask((mm(c.x), mm(c.y)), (mm(c.x), mm(c.y)), hr + VIA_HOLE / 2 + 0.5, novia_mask)
        for t in b.GetTracks():
            if t.GetClass() == "PCB_VIA":
                c = t.GetPosition()
                g.segment_mask((mm(c.x), mm(c.y)), (mm(c.x), mm(c.y)), VIA_HOLE + 0.25, novia_mask)
        novia_mask |= g.edge_dist <= math.ceil((0.25 + VIA_D / 2) / RES)
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
            if z.GetNetCode() == netcode and not z.GetIsRuleArea():
                # a pour that fills nothing (a teardrop below the minimum width) is no copper
                if any(z.GetFilledPolysList(lay).OutlineCount() for lay in (*LAYERS, *INNER) if z.IsOnLayer(lay)):
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

    def island_cells(self, island, layer) -> np.ndarray:
        g = self.g
        m = np.zeros(g.gx.shape, bool)
        for kind, o in island:
            if kind == "zone":
                if o.IsOnLayer(layer):
                    g.poly_mask(o.GetFilledPolysList(layer), 0.0, m)
            elif kind == "pad":
                if o.IsOnLayer(layer):
                    g.poly_mask(o.GetEffectivePolygon(layer, pcbnew.ERROR_INSIDE), 0.0, m)
                    c = o.GetPosition()
                    i, j = g.ij(mm(c.x), mm(c.y))
                    m[i, j] = True
            elif kind == "via":
                c = o.GetPosition()
                g.segment_mask((mm(c.x), mm(c.y)), (mm(c.x), mm(c.y)), 0.1, m)
            elif o.GetLayer() == layer:
                # a track joins at its ends, where KiCad anchors its connections
                r = max(mm(o.GetWidth()) / 2 - 0.02, 0.01)
                for e in (o.GetStart(), o.GetEnd()):
                    g.segment_mask((mm(e.x), mm(e.y)), (mm(e.x), mm(e.y)), r, m)
        return m

    def route_net(self, netname: str, width: float = 0.2, margin: float = 6.0, layers=LAYERS, clr: float = CLR) -> list:
        """Join the net's islands; returns the new segments and vias as
        [(layer, (x0, y0), (x1, y1)) | ("via", (x, y))]."""
        b, g = self.b, self.g
        net = b.FindNet(netname)
        nc = net.GetNetCode()
        added = []
        for _ in range(60):
            islands = self.copper(nc)
            # an island is only F/B relevant if it has copper on an outer layer
            if len(islands) < 2:
                break
            # islands without outer-layer copper (an inner pour on its own) cannot be reached here
            outer = [isl for isl in islands if any(self.island_cells(isl, L).any() for L in layers)]
            if len(outer) < 2:
                break
            blk = self.blocked(nc, width / 2, clr)
            outer.sort(key=len)
            path = None
            # from the smallest island to any other; an island boxed in may still be reached from
            # another, so each island gets its turn as the source
            for k, src in enumerate(outer):
                tgt = [it for n_, isl in enumerate(outer) if n_ != k for it in isl]
                sm = {L: self.island_cells(src, L) for L in layers}
                tm = {L: self.island_cells(tgt, L) for L in layers}
                for mg in (margin, 2 * margin, 4 * margin, 8 * margin):
                    path = self._search(sm, tm, blk, layers, mg)
                    if path is not None:
                        break
                if path is not None:
                    break
            if path is None:
                raise RuntimeError(f"{netname}: no route between its islands")
            free_g = {L: (~blk[L] & ~blk[("soft", L)] & g.inside) | sm[L] | tm[L] for L in layers}
            for L, i, j in path:
                free_g[L][i, j] = True
            new = self._commit(self._smooth(path, free_g), net, width)
            added += new
        return added

    def _search(self, sm, tm, blk, layers, margin):
        g = self.g
        # window: the source island grown by the margin
        ys, xs = [], []
        for L in layers:
            ii, jj = np.nonzero(sm[L])
            ys += [ii.min(), ii.max()] if len(ii) else []
            xs += [jj.min(), jj.max()] if len(jj) else []
        if not ys:
            return None
        k = int(margin / RES)
        i0, i1 = max(0, min(ys) - k), min(g.ny, max(ys) + k + 1)
        j0, j1 = max(0, min(xs) - k), min(g.nx, max(xs) + k + 1)
        H, W = i1 - i0, j1 - j0
        nl = len(layers)
        free = np.zeros((nl, H, W), bool)
        target = np.zeros((nl, H, W), bool)
        start = np.zeros((nl, H, W), bool)
        cost = np.ones((nl, H, W))
        for li, L in enumerate(layers):
            free[li] = ~blk[L][i0:i1, j0:j1] & g.inside[i0:i1, j0:j1]
            cost[li][blk[("soft", L)][i0:i1, j0:j1]] = 6.0
            target[li] = tm[L][i0:i1, j0:j1]
            start[li] = sm[L][i0:i1, j0:j1]
        # own copper cells are always enterable
        free |= target | start
        via_ok = ~blk["novia"][i0:i1, j0:j1] & ~blk["inner"][i0:i1, j0:j1]
        rv = math.ceil((VIA_D / 2 + CLR - 0.0) / RES)  # via body within free cells of both layers
        if nl == 2:
            both = free[0] & free[1]
            # erode by the via radius minus the track half-width already counted (~2 cells)
            via_ok &= Grid._distance(~both, max(rv - 2, 0) + 1) > max(rv - 2, 0)
        dist = np.full((nl, H, W), np.inf)
        prev = np.full((nl, H, W), -1, dtype=np.int64)
        heap = []
        sl, si, sj = np.nonzero(start & free)
        for li, i, j in zip(sl, si, sj, strict=True):
            dist[li, i, j] = 0.0
            heapq.heappush(heap, (0.0, int(li), int(i), int(j)))
        steps = [
            (-1, 0, 1.0),
            (1, 0, 1.0),
            (0, -1, 1.0),
            (0, 1, 1.0),
            (-1, -1, 1.414),
            (-1, 1, 1.414),
            (1, -1, 1.414),
            (1, 1, 1.414),
        ]
        found = None
        while heap:
            d, li, i, j = heapq.heappop(heap)
            if d > dist[li, i, j]:
                continue
            if target[li, i, j] and not start[li, i, j]:
                found = (li, i, j)
                break
            for di, dj, c in steps:
                ni, nj = i + di, j + dj
                if 0 <= ni < H and 0 <= nj < W and free[li, ni, nj]:
                    if di and dj and not (free[li, i + di, j] or free[li, i, j + dj]):
                        continue
                    nd = d + c * cost[li, ni, nj]
                    if nd < dist[li, ni, nj]:
                        dist[li, ni, nj] = nd
                        prev[li, ni, nj] = (li * H + i) * W + j
                        heapq.heappush(heap, (nd, li, ni, nj))
            if nl == 2 and via_ok[i, j]:
                ol = 1 - li
                nd = d + VIA_COST
                if free[ol, i, j] and nd < dist[ol, i, j]:
                    dist[ol, i, j] = nd
                    prev[ol, i, j] = (li * H + i) * W + j
                    heapq.heappush(heap, (nd, ol, i, j))
        if found is None:
            return None
        cells = []
        cur = found
        while True:
            li, i, j = cur
            cells.append((layers[li], i + i0, j + j0))
            p = prev[li, i, j]
            if p < 0:
                break
            pl, rem = divmod(int(p), H * W)
            cur = (pl, rem // W, rem % W)
        cells.reverse()
        return cells

    def _smooth(self, cells, free_g):
        """String-pull each single-layer run: keep a cell only where the straight line from the
        last kept cell to the next one would leave the free cells."""

        def clear(layer, a, c):
            (i_a, j_a), (i_c, j_c) = a, c
            n = int(max(abs(i_c - i_a), abs(j_c - j_a)) * 2) + 1
            for k in range(n + 1):
                t = k / n
                i = round(i_a + (i_c - i_a) * t)
                j = round(j_a + (j_c - j_a) * t)
                if not free_g[layer][i, j]:
                    return False
            return True

        out = []
        k = 0
        while k < len(cells):
            layer = cells[k][0]
            m = k
            while m + 1 < len(cells) and cells[m + 1][0] == layer:
                m += 1
            run = cells[k : m + 1]
            kept = [run[0]]
            a = 0
            while a < len(run) - 1:
                b_ = len(run) - 1
                while b_ > a + 1 and not clear(layer, run[a][1:], run[b_][1:]):
                    b_ -= 1
                kept.append(run[b_])
                a = b_
            out += kept
            k = m + 1
        return out

    def _commit(self, cells, net, width):
        g, b = self.g, self.b
        out = []
        # split by layer; a layer change is a via at that cell
        runs = [[cells[0]]]
        for c in cells[1:]:
            if c[0] != runs[-1][-1][0]:
                runs.append([c])
            else:
                runs[-1].append(c)
        for k, run in enumerate(runs):
            layer = run[0][0]
            pts = [g.xy(i, j) for _, i, j in run]
            # keep corners only
            keep = [pts[0]]
            for a, m, c in zip(pts, pts[1:], pts[2:], strict=False):
                d1 = (round((m[0] - a[0]) / RES), round((m[1] - a[1]) / RES))
                d2 = (round((c[0] - m[0]) / RES), round((c[1] - m[1]) / RES))
                if d1 != d2:
                    keep.append(m)
            if len(pts) > 1:
                keep.append(pts[-1])
            for a, c in itertools.pairwise(keep):
                t = pcbnew.PCB_TRACK(b)
                t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(round(a[0], 4)), pcbnew.FromMM(round(a[1], 4))))
                t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(round(c[0], 4)), pcbnew.FromMM(round(c[1], 4))))
                t.SetWidth(pcbnew.FromMM(width))
                t.SetLayer(layer)
                t.SetNet(net)
                b.Add(t)
                out.append((layer, a, c))
            if k + 1 < len(runs):
                x, y = pts[-1]
                v = pcbnew.PCB_VIA(b)
                v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(round(x, 4)), pcbnew.FromMM(round(y, 4))))
                v.SetWidth(pcbnew.FromMM(VIA_D))
                v.SetDrill(pcbnew.FromMM(VIA_HOLE))
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetNet(net)
                b.Add(v)
                out.append(("via", (x, y)))
        return out
