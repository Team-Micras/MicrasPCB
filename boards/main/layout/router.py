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

The search finds the cheapest such route. Its heuristic never overestimates the cost left: the
octile distance to the target copper (plus BEND45 where a state's direction cannot run straight
into it), or, for a search that has expanded GEO_AFTER states, the least cost around the
obstacles on each layer with the vias between them. Free regions that cannot reach the target at
all are never entered, and a search whose source lies in none stops before it starts.

The found route keeps its directions; its ends move onto the anchors (a via's centre, a track's
end, a pad's centre line, a track's centre line) by changing run lengths only. Deterministic: the
same board gives the same tracks.

Speed: the rasters cover each search's window only, from the board's geometry read once per call
(pad and pour polygons cached while unchanged), with vectorised numpy: capsules (tracks, vias,
holes, polygon edges) in batches, polygons by an even-odd scanline fill, growth by a separable
disc dilation; a net's obstacles are kept while only its own tracks change, and KiCad's
connectivity is rebuilt only when an item changed (the board itself follows the items added and
removed). The A* runs over flat step tables.
"""

from __future__ import annotations

import array
import heapq
import itertools
import math

import numpy as np
import pcbnew

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
DIAG = 1.414  # the cost of a diagonal step, in cells
GEO_AFTER = 30000  # states a search expands before it takes the obstacle-aware heuristic


def mm(v):
    return pcbnew.ToMM(v)


# --- vectorised rasterisation --------------------------------------------------------------------------
#
# A window is (i0, i1, j0, j1): rows i0..i1-1, columns j0..j1-1 of the board grid; a window's array
# has shape (i1 - i0, j1 - j0). Cell (i, j) has its centre at (x0 + j * RES, y0 + i * RES).


def _grow(win, k, grid):
    i0, i1, j0, j1 = win
    return max(0, i0 - k), min(grid[0], i1 + k), max(0, j0 - k), min(grid[1], j1 + k)


def _crop(arr, awin, win, fill=0):
    """arr (over awin) restricted to win; cells of win outside awin read fill."""
    if awin == win:
        return arr
    i0, i1, j0, j1 = win
    a0, a1, b0, b1 = awin
    if a0 <= i0 and i1 <= a1 and b0 <= j0 and j1 <= b1:
        return arr[i0 - a0 : i1 - a0, j0 - b0 : j1 - b0]
    out = np.full((i1 - i0, j1 - j0), fill, arr.dtype)
    r0, r1, c0, c1 = max(i0, a0), min(i1, a1), max(j0, b0), min(j1, b1)
    if r0 < r1 and c0 < c1:
        out[r0 - i0 : r1 - i0, c0 - j0 : c1 - j0] = arr[r0 - a0 : r1 - a0, c0 - b0 : c1 - b0]
    return out


def _dilate(m, k):
    """m grown by a disc of k cells (every offset with di^2 + dj^2 <= k^2), as Grid._dilate did
    offset by offset, here per row of the disc with a running count along the rows."""
    if k <= 0 or not m.any():
        return m.copy()
    H, W = m.shape
    cs = np.zeros((H, W + 1), np.int32)
    np.cumsum(m, axis=1, out=cs[:, 1:])
    out = np.zeros_like(m)
    cols = np.arange(W)
    rows_cache = {}
    for di in range(-k, k + 1):
        w = math.isqrt(k * k - di * di)
        h = rows_cache.get(w)
        if h is None:
            lo = np.clip(cols - w, 0, W)
            hi = np.clip(cols + w + 1, 0, W)
            h = rows_cache[w] = (cs[:, hi] - cs[:, lo]) > 0
        # out[i] |= h[i - di]
        if di >= 0:
            out[di:] |= h[: H - di]
        else:
            out[: H + di] |= h[-di:]
    return out


def _l1(m, kmax):
    """Distance in cells (4-neighbour steps) from each cell to the nearest set cell of m, capped
    at kmax + 1."""
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


class Grid:
    def __init__(self, board: pcbnew.BOARD):
        self.b = board
        bb = board.GetBoardEdgesBoundingBox()
        self.x0, self.y0 = mm(bb.GetLeft()) - 0.5, mm(bb.GetTop()) - 0.5
        self.nx = int((mm(bb.GetWidth()) + 1.0) / RES) + 1
        self.ny = int((mm(bb.GetHeight()) + 1.0) / RES) + 1
        self.shape = (self.ny, self.nx)
        self.full = (0, self.ny, 0, self.nx)
        outl = pcbnew.SHAPE_POLY_SET()
        board.GetBoardPolygonOutlines(outl, True)
        self.outline = outl
        inside = self.fill(self.full, [_chain(outl.Outline(0))])
        for h in range(outl.HoleCount(0)):
            inside &= ~self.fill(self.full, [_chain(outl.Hole(0, h))])
        self.inside = inside
        # distance to the board edge, in cells (Euclidean, rounded up; 13 beyond 12 cells)
        self.edge_dist = self._euclid(~inside, 12)

    # --- raster helpers ---------------------------------------------------------------------------

    def ij(self, x, y):
        return round((y - self.y0) / RES), round((x - self.x0) / RES)

    def xy(self, i, j):
        return float(self.x0 + j * RES), float(self.y0 + i * RES)

    def window(self, x0, y0, x1, y1, grow=0.0):
        """The cells whose centres can lie in the box (mm) grown by grow."""
        i0 = max(0, int((y0 - grow - self.y0) / RES) - 1)
        i1 = min(self.ny, int((y1 + grow - self.y0) / RES) + 2)
        j0 = max(0, int((x0 - grow - self.x0) / RES) - 1)
        j1 = min(self.nx, int((x1 + grow - self.x0) / RES) + 2)
        return i0, i1, j0, j1

    def capsule_cells(self, win, xa, ya, xb, yb, rad):
        """The cells of win whose centres lie within rad of the segment (xa, ya)-(xb, yb), for
        arrays of segments: (rows, cols, segment index), window-relative."""
        xa, ya, xb, yb, rad = (np.asarray(v, np.float64).ravel() for v in (xa, ya, xb, yb, rad))
        empty = (np.zeros(0, np.intp),) * 3
        if not len(xa):
            return empty
        wi0, wi1, wj0, wj1 = win
        idx = np.arange(len(xa))
        # split long segments, so every stencil stays small (their union is the same capsule)
        L = np.hypot(xb - xa, yb - ya)
        n = np.maximum(1, np.ceil(L / 0.5)).astype(np.intp)
        if n.max() > 1:
            rep = np.repeat(idx, n)
            k = np.arange(len(rep)) - np.repeat(np.cumsum(n) - n, n)
            f0, f1 = k / n[rep], (k + 1) / n[rep]
            ax, ay, bx, by = xa[rep], ya[rep], xb[rep], yb[rep]
            dx, dy = bx - ax, by - ay
            last = k == n[rep] - 1
            xa, ya = ax + f0 * dx, ay + f0 * dy
            xb, yb = np.where(last, bx, ax + f1 * dx), np.where(last, by, ay + f1 * dy)
            rad, idx = rad[rep], idx[rep]
        r0 = np.floor((np.minimum(ya, yb) - rad - self.y0) / RES).astype(np.intp)
        r1 = np.ceil((np.maximum(ya, yb) + rad - self.y0) / RES).astype(np.intp)
        c0 = np.floor((np.minimum(xa, xb) - rad - self.x0) / RES).astype(np.intp)
        c1 = np.ceil((np.maximum(xa, xb) + rad - self.x0) / RES).astype(np.intp)
        r0, r1 = np.maximum(r0, wi0), np.minimum(r1, wi1 - 1)
        c0, c1 = np.maximum(c0, wj0), np.minimum(c1, wj1 - 1)
        keep = (r0 <= r1) & (c0 <= c1)
        if not keep.any():
            return empty
        xa, ya, xb, yb, rad, idx, r0, r1, c0, c1 = (v[keep] for v in (xa, ya, xb, yb, rad, idx, r0, r1, c0, c1))
        rows, cols, which = [], [], []
        # stencils in buckets of their size (rounded up to 4 cells), in batches of about a
        # million cells
        si = (r1 - r0 + 4) // 4 * 4
        sj = (c1 - c0 + 4) // 4 * 4
        key = si * 4096 + sj
        order = np.argsort(key, kind="stable")
        ks, starts = np.unique(key[order], return_index=True)
        ends = [*starts[1:], len(order)]
        for kk, st, en in zip(ks, starts, ends, strict=True):
            Si, Sj = int(kk) // 4096, int(kk) % 4096
            step = max(1, (1 << 20) // (Si * Sj))
            for s0 in range(st, en, step):
                q = order[s0 : min(en, s0 + step)]
                ii = r0[q, None] + np.arange(Si)  # (n, Si)
                jj = c0[q, None] + np.arange(Sj)
                vi = ii <= r1[q, None]
                vj = jj <= c1[q, None]
                sy = (self.y0 + ii * RES)[:, :, None]
                sx = (self.x0 + jj * RES)[:, None, :]
                a0, a1 = xa[q, None, None], ya[q, None, None]
                dx, dy = (xb - xa)[q, None, None], (yb - ya)[q, None, None]
                L2 = dx * dx + dy * dy
                if (L2 > 0).all():
                    t = np.clip(((sx - a0) * dx + (sy - a1) * dy) / L2, 0, 1)
                    d = np.hypot(sx - (a0 + t * dx), sy - (a1 + t * dy))
                elif not (L2 > 0).any():
                    d = np.hypot(sx - a0, sy - a1)
                else:
                    with np.errstate(invalid="ignore", divide="ignore"):
                        t = np.where(
                            L2 > 0, np.clip(((sx - a0) * dx + (sy - a1) * dy) / np.where(L2 > 0, L2, 1), 0, 1), 0
                        )
                    d = np.hypot(sx - (a0 + t * dx), sy - (a1 + t * dy))
                hit = (d <= rad[q, None, None]) & vi[:, :, None] & vj[:, None, :]
                nq, a, b = np.nonzero(hit)
                rows.append(ii[nq, a] - wi0)
                cols.append(jj[nq, b] - wj0)
                which.append(idx[q][nq])
        return np.concatenate(rows), np.concatenate(cols), np.concatenate(which)

    def capsules(self, win, segs, out=None):
        """segs: (n, 5) [xa, ya, xb, yb, radius]; sets the cells within radius of a segment."""
        i0, i1, j0, j1 = win
        if out is None:
            out = np.zeros((i1 - i0, j1 - j0), bool)
        if len(segs):
            s = np.asarray(segs, np.float64)
            r, c, _ = self.capsule_cells(win, s[:, 0], s[:, 1], s[:, 2], s[:, 3], s[:, 4])
            out[r, c] = True
        return out

    def fill(self, win, rings):
        """The cells of win whose centres lie inside the rings (each an (n, 2) array of mm), by
        the even-odd rule (a polygon's outlines and holes together, or a fractured fill)."""
        i0, i1, j0, j1 = win
        H, W = i1 - i0, j1 - j0
        rings = [r for r in rings if len(r) >= 3]
        if not rings or H <= 0 or W <= 0:
            return np.zeros((max(H, 0), max(W, 0)), bool)
        a = np.concatenate(rings)
        b = np.concatenate([np.roll(r, -1, axis=0) for r in rings])
        xa, ya, xb, yb = a[:, 0], a[:, 1], b[:, 0], b[:, 1]
        ylo, yhi = np.minimum(ya, yb), np.maximum(ya, yb)
        r0 = np.maximum(np.floor((ylo - self.y0) / RES).astype(np.intp), i0)
        r1 = np.minimum(np.ceil((yhi - self.y0) / RES).astype(np.intp), i1 - 1)
        n = np.maximum(r1 - r0 + 1, 0)
        keep = (n > 0) & (ya != yb)
        if not keep.any():
            return np.zeros((H, W), bool)
        xa, ya, xb, yb, ylo, yhi, r0, n = (v[keep] for v in (xa, ya, xb, yb, ylo, yhi, r0, n))
        e = np.repeat(np.arange(len(n)), n)
        rows = np.arange(len(e)) - np.repeat(np.cumsum(n) - n, n) + r0[e]
        cy = self.y0 + rows * RES
        on = (ylo[e] <= cy) & (cy < yhi[e])
        e, rows, cy = e[on], rows[on], cy[on]
        x = xa[e] + (cy - ya[e]) * (xb[e] - xa[e]) / (yb[e] - ya[e])
        # a crossing at x toggles the cells whose centres lie left of it
        c = np.clip(np.ceil((x - self.x0) / RES).astype(np.intp) - j0, 0, W)
        cnt = np.bincount((rows - i0) * (W + 1) + c, minlength=H * (W + 1)).reshape(H, W + 1)
        tog = np.cumsum(cnt[:, ::-1], axis=1)[:, ::-1]
        return (tog[:, 1:] & 1).astype(bool)

    def fill_into(self, win, rings, out, bbox=None, value=True):
        """Fill the rings into out (over win), computing only their bounding box's cells."""
        if bbox is None:
            pts = np.concatenate(rings)
            bbox = (pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max())
        sub = self.window(*bbox)
        i0, i1, j0, j1 = win
        s0, s1, t0, t1 = max(sub[0], i0), min(sub[1], i1), max(sub[2], j0), min(sub[3], j1)
        if s0 >= s1 or t0 >= t1:
            return
        m = self.fill((s0, s1, t0, t1), rings)
        out[s0 - i0 : s1 - i0, t0 - j0 : t1 - j0][m] = value

    # compatibility: full-grid masks, as before
    def segment_mask(self, a, b, r, mask, value=True):
        rr, cc, _ = self.capsule_cells(self.full, [a[0]], [a[1]], [b[0]], [b[1]], [r])
        mask[rr, cc] = value

    def poly_mask(self, sps: pcbnew.SHAPE_POLY_SET, grow: float, mask, value=True):
        for k in range(sps.OutlineCount()):
            ring = _chain(sps.Outline(k))
            if len(ring) < 3:
                continue
            m = np.zeros(self.shape, bool)
            self.fill_into(self.full, [ring] + [_chain(sps.Hole(k, h)) for h in range(sps.HoleCount(k))], m)
            if grow > 0:
                m = _dilate(m, math.ceil(grow / RES))
                self.capsules(self.full, _edges(ring, grow), m)
            mask[m] = value

    @staticmethod
    def _dilate(m, k):
        return _dilate(m, k)

    @staticmethod
    def _distance(m, kmax):
        return _l1(m, kmax)

    @staticmethod
    def _euclid(m, kmax):
        """Distance in cells from each cell to the nearest set cell of m, rounded up, capped at
        kmax + 1: exact, separably (the nearest set cell along each column, then across)."""
        big = kmax + 1
        v = np.full(m.shape, big, np.int32)  # rows to the nearest set cell in the column, <= kmax
        v[m] = 0
        for di in range(1, kmax + 1):
            v[di:][m[:-di]] = np.minimum(v[di:][m[:-di]], di)
            v[:-di][m[di:]] = np.minimum(v[:-di][m[di:]], di)
        v2 = np.where(v <= kmax, v * v, 10**6).astype(np.int64)
        d2 = v2.copy()
        for dj in range(1, kmax + 1):
            dd = dj * dj
            d2[:, dj:] = np.minimum(d2[:, dj:], v2[:, :-dj] + dd)
            d2[:, :-dj] = np.minimum(d2[:, :-dj], v2[:, dj:] + dd)
        d = np.sqrt(d2.astype(np.float64))
        d[d > kmax] = big
        return np.ceil(d - 1e-9).astype(np.int16)


def _chain(ch) -> np.ndarray:
    """A SHAPE_LINE_CHAIN's points, in mm."""
    pts = ch.CPoints()
    if not len(pts):
        return np.zeros((0, 2))
    return np.array([(p.x, p.y) for p in pts], np.float64) / 1e6


def _rings(sps) -> tuple[list, list]:
    """A SHAPE_POLY_SET's outlines and holes, in mm: (rings of each outline with its holes, outlines)."""
    polys, outlines = [], []
    for k in range(sps.OutlineCount()):
        o = _chain(sps.Outline(k))
        if len(o) < 3:
            continue
        polys.append([o] + [_chain(sps.Hole(k, h)) for h in range(sps.HoleCount(k))])
        outlines.append(o)
    return polys, outlines


def _edges(ring, r) -> np.ndarray:
    """A ring's edges as capsules of radius r."""
    b = np.roll(ring, -1, axis=0)
    return np.c_[ring, b, np.full(len(ring), r)]


def _bbox(rings):
    pts = np.concatenate(rings)
    return pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()


def _meets(bbox, win_mm) -> bool:
    return bbox[0] <= win_mm[2] and bbox[2] >= win_mm[0] and bbox[1] <= win_mm[3] and bbox[3] >= win_mm[1]


# --- the board's copper, read once per call ------------------------------------------------------------


class _Copper:
    """Geometry of the board's tracks, vias, pads and pours in mm, re-read on every snapshot();
    the polygons of pads and pours stay cached while their item is unchanged."""

    def __init__(self, board):
        self.b = board
        self._pads = {}  # id -> (signature, data)
        self._fills = {}  # (id, layer) -> (signature, (polys, outlines, bbox))

    def tracks(self):
        """Arrays: kind (0 track, 1 via, 2 arc), x0, y0, x1, y1, width, layer, net, drill, via width
        on F.Cu and on B.Cu."""
        rows, ptrs = [], []
        for t in self.b.GetTracks():
            cls = t.GetClass()
            ptrs.append(int(t.this))
            if cls == "PCB_VIA":
                v = t.Cast()
                p = v.GetPosition()
                rows.append(
                    (
                        1,
                        p.x,
                        p.y,
                        p.x,
                        p.y,
                        0,
                        -1,
                        v.GetNetCode(),
                        v.GetDrillValue(),
                        v.GetWidth(pcbnew.F_Cu),
                        v.GetWidth(pcbnew.B_Cu),
                    )
                )
            else:
                a, c = t.GetStart(), t.GetEnd()
                rows.append(
                    (
                        2 if cls == "PCB_ARC" else 0,
                        a.x,
                        a.y,
                        c.x,
                        c.y,
                        t.GetWidth(),
                        t.GetLayer(),
                        t.GetNetCode(),
                        0,
                        0,
                        0,
                    )
                )
                if cls == "PCB_ARC":  # an arc as two chords through its middle
                    m = t.Cast().GetMid()
                    rows[-1] = (0, a.x, a.y, m.x, m.y, t.GetWidth(), t.GetLayer(), t.GetNetCode(), 0, 0, 0)
                    rows.append((0, m.x, m.y, c.x, c.y, t.GetWidth(), t.GetLayer(), t.GetNetCode(), 0, 0, 0))
                    ptrs.append(ptrs[-1])
        self.rows = dict(zip(ptrs, rows, strict=True))  # (the arcs' first chords drop out: the second has their end)
        a = np.array(rows, np.float64).reshape(-1, 11)
        out = {
            "kind": a[:, 0].astype(np.int8),
            "x0": a[:, 1] / 1e6,
            "y0": a[:, 2] / 1e6,
            "x1": a[:, 3] / 1e6,
            "y1": a[:, 4] / 1e6,
            "w": a[:, 5] / 1e6,
            "layer": a[:, 6].astype(np.int64),
            "net": a[:, 7].astype(np.int64),
            "drill": a[:, 8] / 1e6,
            "vwF": a[:, 9] / 1e6,
            "vwB": a[:, 10] / 1e6,
        }
        return out

    def pads(self):
        """Per pad: a dict with net, position, hole, layers and its effective polygons."""
        out, seen = [], set()
        for f in self.b.GetFootprints():
            for p in f.Pads():
                key = int(p.this)
                seen.add(key)
                pos = p.GetPosition()
                sig = (
                    pos.x,
                    pos.y,
                    p.GetOrientation().AsDegrees(),
                    p.GetNetCode(),
                    p.GetShape(pcbnew.F_Cu),
                    p.GetSize(pcbnew.F_Cu).x,
                    p.GetSize(pcbnew.F_Cu).y,
                    p.GetLayerSet().FmtHex(),
                )
                hit = self._pads.get(key)
                if hit is None or hit[0] != sig:
                    hole = p.HasHole()
                    d = {
                        "pad": p,
                        "net": p.GetNetCode(),
                        "c": (pos.x / 1e6, pos.y / 1e6),
                        "hole": hole,
                        "pth": p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH,
                        "hr": max(p.GetDrillSize().x, p.GetDrillSize().y) / 2e6 if hole else 0.0,
                        "on": {L: p.IsOnLayer(L) for L in LAYERS},
                        "poly": {},
                    }
                    hit = self._pads[key] = (sig, d)
                d = hit[1]
                d["pad"] = p
                d["ptr"] = key
                out.append(d)
        for key in list(self._pads):
            if key not in seen:
                del self._pads[key]
        return out

    @staticmethod
    def pad_poly(d, layer, error=pcbnew.ERROR_OUTSIDE):
        """(polys, outlines, bbox) of the pad's effective polygon on a layer."""
        key = (layer, error)
        got = d["poly"].get(key)
        if got is None:
            polys, outlines = _rings(d["pad"].GetEffectivePolygon(layer, error))
            got = d["poly"][key] = (polys, outlines, _bbox(outlines) if outlines else None)
        return got

    def zone_fill(self, z, layer):
        """(polys, outlines, bbox) of a pour's fill on a layer, cached while it is unchanged."""
        f = z.GetFilledPolysList(layer)
        sig = (f.OutlineCount(), f.FullPointCount(), f.Area())
        key = (int(z.this), layer)
        hit = self._fills.get(key)
        if hit is None or hit[0] != sig:
            polys, outlines = _rings(f)
            hit = self._fills[key] = (sig, (polys, outlines, _bbox(outlines) if outlines else None))
        return hit[1]

    def pad_inside(self, p, layer):
        """(polys, outlines, bbox) of a pad's effective polygon on a layer (ERROR_INSIDE), cached
        while the pad is unchanged."""
        hit = self._pads.get(int(p.this))
        pos = p.GetPosition()
        if hit is None or hit[0][:4] != (pos.x, pos.y, p.GetOrientation().AsDegrees(), p.GetNetCode()):
            polys, outlines = _rings(p.GetEffectivePolygon(layer, pcbnew.ERROR_INSIDE))
            return polys, outlines, _bbox(outlines) if outlines else None
        return self.pad_poly(hit[1], layer, pcbnew.ERROR_INSIDE)

    def zones(self, layers):
        """Per pour (rule areas left out): a dict with net, priority and, per layer it is on, its
        fill as (polys, outlines, bbox)."""
        out, seen = [], set()
        for z in self.b.Zones():
            if z.GetIsRuleArea():
                continue
            zid = int(z.this)
            d = {"zone": z, "net": z.GetNetCode(), "prio": z.GetAssignedPriority(), "fill": {}, "sig": {}}
            for L in layers:
                if not z.IsOnLayer(L):
                    continue
                f = z.GetFilledPolysList(L)
                sig = (f.OutlineCount(), f.FullPointCount(), f.Area())
                seen.add((zid, L))
                hit = self._fills.get((zid, L))
                if hit is None or hit[0] != sig:
                    polys, outlines = _rings(f)
                    hit = self._fills[(zid, L)] = (sig, (polys, outlines, _bbox(outlines) if outlines else None))
                d["fill"][L] = hit[1]
                d["sig"][L] = sig
            out.append(d)
        for key in list(self._fills):
            if key[1] in layers and key not in seen:
                del self._fills[key]
        return out


# --- the router ------------------------------------------------------------------------------------------


class Router:
    def __init__(self, board: pcbnew.BOARD):
        self.b = board
        self.g = Grid(board)
        self.cu = _Copper(board)
        self.created = []
        self.graveyard = []  # removed items stay referenced: their SWIG proxies do not own them
        self.hard_pours = False  # other nets' pours as obstacles, not as dearer cells
        self.stats = {"searches": 0, "expanded": 0}
        self._bcache = {}  # (net, half width, clearance) -> (digest of the other copper, blocked())
        self._hcache = {}  # the heuristic's arrays of the join being searched
        self._centred = False
        self.plane_edges = self._plane_edges()

    def _plane_edges(self) -> np.ndarray:
        """Cells where a via's clearance hole in an inner-layer pour would leave a sliver: within
        a via's radius, a pour's clearance and the narrowest copper feature (0.09 mm, the PDK) of
        the outline of an inner-layer pour (where two pours meet, or a pour ends)."""
        g = self.g
        r = VIA_D / 2 + 0.25 + 0.09
        segs = []
        for layer in INNER:
            for z in self.b.Zones():
                if z.GetIsRuleArea() or not z.IsOnLayer(layer):
                    continue
                outline = z.Outline()  # the drawn outline: the fill's is fractured around holes
                for k in range(outline.OutlineCount()):
                    ring = _chain(outline.Outline(k))
                    if len(ring):
                        segs.append(_edges(ring, r))
        return g.capsules(g.full, np.concatenate(segs) if segs else np.zeros((0, 5)))

    # obstacles for a net: other nets' copper grown by r, holes, edge
    def blocked(self, netcode: int, half: float, clr: float = CLR, box=None) -> dict:
        """Cells a track of this net cannot use, per outer layer; "soft": other nets' pours, which
        give way to a track when refilled (dearer to cross); "inner"/"novia": where vias cannot go.
        With box (i0, i1, j0, j1), only that window, grown by 1.5 mm, is computed: the arrays
        cover the window "win" (the whole grid without a box)."""
        g = self.g
        win = g.full if box is None else _grow(box, int(1.5 / RES), g.shape)
        tr = self.cu.tracks()
        pads = self.cu.pads()
        zones = self.cu.zones(LAYERS)
        # the net's own tracks do not change its obstacles (its vias do: no via beside a via), so
        # the joins of one net reuse them while nothing else changed
        keep = (tr["net"] != netcode) | (tr["kind"] == 1)
        sig = hash(
            (
                b"".join(a[keep].tobytes() for a in tr.values()),
                tuple((d["c"], d["net"]) for d in pads),
                tuple((z["net"], z["prio"], tuple(sorted(z["sig"].items()))) for z in zones),
            )
        )
        key = (netcode, half, clr)
        hit = self._bcache.get(key)
        if hit is not None and hit[0] == sig and _within(win, hit[1]["win"]):
            return hit[1]
        out = self._blocked(netcode, half, clr, win, tr, pads, zones)
        self._bcache[key] = (sig, out)
        while len(self._bcache) > 6:
            self._bcache.pop(next(iter(self._bcache)))
        return out

    def _blocked(self, netcode: int, half: float, clr: float, win, tr, pads, zones) -> dict:
        g = self.g
        r = half + clr
        i0, i1, j0, j1 = win
        shape = (i1 - i0, j1 - j0)
        # the window in mm, grown by the largest reach of any copper into it
        reach = 3.0
        wmm = (g.x0 + j0 * RES - reach, g.y0 + i0 * RES - reach, g.x0 + j1 * RES + reach, g.y0 + i1 * RES + reach)
        near = (
            (np.minimum(tr["x0"], tr["x1"]) <= wmm[2])
            & (np.maximum(tr["x0"], tr["x1"]) >= wmm[0])
            & (np.minimum(tr["y0"], tr["y1"]) <= wmm[3])
            & (np.maximum(tr["y0"], tr["y1"]) >= wmm[1])
        )
        other = near & (tr["net"] != netcode)
        isvia = tr["kind"] == 1
        pads = [
            d
            for d in pads
            if abs(d["c"][0] - (wmm[0] + wmm[2]) / 2) <= (wmm[2] - wmm[0]) / 2 + 5
            and abs(d["c"][1] - (wmm[1] + wmm[3]) / 2) <= (wmm[3] - wmm[1]) / 2 + 5
        ]
        k = math.ceil(r / RES)
        # polygons are filled over the window grown by the dilation, so growth from outside counts
        fwin = _grow(win, k + 1, g.shape)
        out = {"win": win}
        holes = []
        for d in pads:
            if d["hole"] and (d["net"] != netcode or not d["pth"]):
                extra = HOLE_CLR if d["pth"] else 0.2
                holes.append((*d["c"], *d["c"], d["hr"] + extra + half))
        for layer in LAYERS:
            caps = list(holes)
            v = other & isvia
            vw = tr["vwF"] if layer == pcbnew.F_Cu else tr["vwB"]
            rr = np.maximum(vw[v] / 2 + r, tr["drill"][v] / 2 + 0.2 + half) + 0.03
            caps_v = np.c_[tr["x0"][v], tr["y0"][v], tr["x0"][v], tr["y0"][v], rr]
            t = other & ~isvia & (tr["layer"] == layer)
            caps_t = np.c_[tr["x0"][t], tr["y0"][t], tr["x1"][t], tr["y1"][t], tr["w"][t] / 2 + r]
            hard_int = np.zeros((fwin[1] - fwin[0], fwin[3] - fwin[2]), bool)
            soft_int = np.zeros_like(hard_int)
            edges_h, edges_s = [], []
            for d in pads:
                if d["net"] == netcode and netcode > 0:
                    continue
                if not d["on"][layer]:
                    continue
                polys, outlines, bb = self.cu.pad_poly(d, layer)
                if bb is None or not _meets(bb, wmm):
                    continue
                for poly in polys:
                    g.fill_into(fwin, poly, hard_int)
                for o in outlines:
                    edges_h.append(_edges(o, r))
            for z in zones:
                if z["net"] == netcode or layer not in z["fill"]:
                    continue
                polys, outlines, bb = z["fill"][layer]
                if bb is None or not _meets(bb, wmm):
                    continue
                # teardrops (priority 100 and up) stay; pours yield to the new track
                hard = z["prio"] >= 100
                for poly in polys:
                    g.fill_into(fwin, poly, hard_int if hard else soft_int)
                for o in outlines:
                    (edges_h if hard else edges_s).append(_edges(o, r))
            m = _crop(_dilate(hard_int, k), fwin, win)
            m = m.copy() if m.base is not None else m
            allcaps = [np.asarray(caps, np.float64).reshape(-1, 5), caps_v, caps_t, *edges_h]
            g.capsules(win, np.concatenate(allcaps), m)
            soft = _crop(_dilate(soft_int, k), fwin, win)
            soft = soft.copy() if soft.base is not None else soft
            if edges_s:
                g.capsules(win, np.concatenate(edges_s), soft)
            m |= g.edge_dist[i0:i1, j0:j1] <= math.ceil((0.2 + half) / RES)
            out[layer] = m
            out[("soft", layer)] = soft & ~m
        # inner-layer tracks constrain vias
        t = other & ~isvia & np.isin(tr["layer"], INNER)
        out["inner"] = g.capsules(
            win, np.c_[tr["x0"][t], tr["y0"][t], tr["x1"][t], tr["y1"][t], tr["w"][t] / 2 + VIA_HOLE / 2 + 0.2]
        )
        # vias: no SMD pad, no other hole closer than the hole-to-hole rules
        grow = VIA_D / 2 + CLR
        kv = math.ceil(grow / RES)
        own_int = np.zeros((fwin[1] - fwin[0], fwin[3] - fwin[2]), bool)
        oth_int = np.zeros_like(own_int)
        caps = []
        for d in pads:
            if d["on"][pcbnew.F_Cu] and not d["hole"]:
                polys, outlines, bb = self.cu.pad_poly(d, pcbnew.F_Cu)
                if bb is None or not _meets(bb, wmm):
                    continue
                # a via may sit beside its own net's pad, not in it
                own = d["net"] == netcode and netcode > 0
                for poly in polys:
                    g.fill_into(fwin, poly, own_int if own else oth_int)
                if not own:
                    caps += [_edges(o, grow) for o in outlines]
            if d["hole"]:
                caps.append(np.array([[*d["c"], *d["c"], d["hr"] + VIA_HOLE / 2 + 0.5]]))
        v = near & isvia
        caps.append(np.c_[tr["x0"][v], tr["y0"][v], tr["x0"][v], tr["y0"][v], np.full(v.sum(), VIA_HOLE + 0.25)])
        novia = _crop(own_int | _dilate(oth_int, kv), fwin, win).copy()
        g.capsules(win, np.concatenate(caps), novia)
        novia |= g.edge_dist[i0:i1, j0:j1] <= math.ceil((0.25 + VIA_D / 2) / RES)
        novia |= self.plane_edges[i0:i1, j0:j1]
        out["novia"] = novia
        assert m.shape == shape
        return out

    _built = None

    def _connectivity(self):
        """KiCad's connectivity, rebuilt where it may be out of date. The board keeps it up to date
        itself when items are added or removed, not when an item changes: so it is rebuilt when a
        track, via, pad or pour fill that was there at the last build differs now."""
        self.cu.tracks()
        tracks = self.cu.rows
        pads = {d["ptr"]: (d["c"], d["net"]) for d in self.cu.pads()}
        zones = {
            (int(z["zone"].this), L): (z["net"], sig)
            for z in self.cu.zones((*LAYERS, *INNER))
            for L, sig in z["sig"].items()
        }
        last = self._built
        stale = last is None
        if not stale:
            t0, p0, z0 = last
            stale = (
                any(t0.get(k, v) != v for k, v in tracks.items())
                or any(p0.get(k, v) != v for k, v in pads.items())
                or any(z0.get(k) != v for k, v in zones.items())
            )
        if stale:
            self.b.BuildConnectivity()
            self.stats["builds"] = self.stats.get("builds", 0) + 1
        self._built = (tracks, pads, zones)
        return self.b.GetConnectivity()

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
        multi = set()
        for z in b.Zones():
            # a pour that fills nothing (a teardrop below the minimum width) is no copper
            if z.GetNetCode() != netcode or z.GetIsRuleArea():
                continue
            n = sum(z.GetFilledPolysList(lay).OutlineCount() for lay in (*LAYERS, *INNER) if z.IsOnLayer(lay))
            if n:
                if n > 1:
                    multi.add(len(items))
                items.append(("zone", z))
        conn = self._connectivity()
        index = {o.m_Uuid.AsString(): k for k, (_, o) in enumerate(items)}
        parent = list(range(len(items)))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        # KiCad returns an item's whole cluster: one call per cluster is enough, but for a pour
        # with several islands (which may lie in several clusters)
        covered = [False] * len(items)
        for k, (_, o) in enumerate(items):
            if covered[k] and k not in multi:
                continue
            covered[k] = True
            for other in conn.GetConnectedItems(o):
                j = index.get(other.m_Uuid.AsString())
                if j is not None:
                    parent[find(k)] = find(j)
                    covered[j] = True
        groups = {}
        for k in range(len(items)):
            groups.setdefault(find(k), []).append(items[k])
        return list(groups.values())

    # --- where a route may start and end -----------------------------------------------------------

    def anchors(self, island, layer, win=None):
        """The island's copper on a layer as cells, each naming the anchor a route ends on there:
        a mask, an owner index per cell (-1: none) and the anchors, each (kind, data, dirs) with
        dirs the 8-bit set of directions a route may enter by (leave by: the opposite ones), and
        the window (i0, i1, j0, j1) the arrays cover (the whole grid without win)."""
        g = self.g
        win = g.full if win is None else win
        i0, i1, j0, j1 = win
        H, W = i1 - i0, j1 - j0
        wmm = (g.x0 + (j0 - 2) * RES, g.y0 + (i0 - 2) * RES, g.x0 + (j1 + 1) * RES, g.y0 + (i1 + 1) * RES)
        owner = np.full((H, W), -1, np.int32)
        out = []
        caps = []  # (xa, ya, xb, yb, r, anchor index)

        def add(anchor):
            out.append(anchor)
            return len(out) - 1

        def paint(rows, cols, n):
            if len(rows):
                np.maximum.at(owner, (rows, cols), n)

        # own-net track ends, the directions their tracks leave each end by, the narrowest there
        leave, narrow = {}, {}
        tracks = []
        for kind, o in island:
            if kind == "track" and o.GetLayer() == layer:
                a, b = _pt(o.GetStart()), _pt(o.GetEnd())
                if a == b:
                    continue
                w = mm(o.GetWidth())
                tracks.append((a, b, w))
                for p, q in ((a, b), (b, a)):
                    key = (round(p[0], 4), round(p[1], 4))
                    leave.setdefault(key, []).append(_unit(p, q))
                    narrow[key] = min(narrow.get(key, 9.0), w)
        # lowest priority first: pours, track middles, track ends, vias, pads
        for kind, o in island:
            if kind == "zone" and o.IsOnLayer(layer):
                n = add(("zone", None, ALL))
                polys, outlines, _ = self.cu.zone_fill(o, layer)
                for poly in polys:
                    if _meets(_bbox(poly[:1]), wmm):
                        m = np.zeros((H, W), bool)
                        g.fill_into(win, poly, m)
                        rr, cc = np.nonzero(m)
                        paint(rr, cc, n)
        for a, b, w in tracks:
            ins = 0.3
            if math.dist(a, b) < 2 * ins + 0.1 or w < 0.12:
                continue
            u = _unit(a, b)
            # a T joins a straight middle square to it (no acute angle on either side)
            dirs = _bits(k for k in range(8) if abs(DIRS[k][0] * u[0] + DIRS[k][1] * u[1]) < 0.02)
            if dirs:
                e0, e1 = (a[0] + u[0] * ins, a[1] + u[1] * ins), (b[0] - u[0] * ins, b[1] - u[1] * ins)
                caps.append((*e0, *e1, max(w / 2 - 0.04, 0.01), add(("mid", (a, b), dirs))))
        for p, us in leave.items():
            # a route joining a track end keeps 90 degrees or more to every track there
            dirs = _bits(k for k in range(8) if all(DIRS[k][0] * u[0] + DIRS[k][1] * u[1] > -0.02 for u in us))
            caps.append((*p, *p, min(max(narrow[p] / 2 - 0.03, 0.03), 0.06), add(("end", p, dirs))))
        for kind, o in island:
            if kind == "via":
                c = _pt(o.GetPosition())
                caps.append((*c, *c, 0.06, add(("via", c, ALL))))
        if caps:
            cp = np.array(caps, np.float64)
            rr, cc, k = g.capsule_cells(win, cp[:, 0], cp[:, 1], cp[:, 2], cp[:, 3], cp[:, 4])
            paint(rr, cc, cp[k, 5].astype(np.int32))
        for kind, o in island:
            if kind == "pad" and o.IsOnLayer(layer):
                c = _pt(o.GetPosition())
                # rectangular pads are entered along their axes, round ones from any side
                deg = o.GetOrientation().AsDegrees() % 90
                if o.GetShape(layer) == pcbnew.PAD_SHAPE_CIRCLE or min(deg % 45, 45 - deg % 45) > 0.5:
                    dirs = ALL
                else:
                    dirs = _bits(range(round(deg / 45) % 2, 8, 2))
                n = add(("pad", (c, o), dirs))
                polys, outlines, bb = self.cu.pad_inside(o, layer)
                if outlines and _meets(bb, wmm):
                    m = np.zeros((H, W), bool)
                    for poly in polys:
                        g.fill_into(win, poly, m)
                    rr, cc = np.nonzero(m)
                    paint(rr, cc, n)
                ci, cj = g.ij(*c)
                if i0 <= ci < i1 and j0 <= cj < j1:
                    paint(np.array([ci - i0]), np.array([cj - j0]), n)
        m = owner >= 0
        return m, owner, out, win

    def island_cells(self, island, layer) -> np.ndarray:
        return self.anchors(island, layer, self._extent(island))[0]

    def _extent(self, items, grow=0.5):
        """The window over the items' copper (their bounding boxes, grown by grow mm)."""
        g = self.g
        xs, ys = [], []
        for _, o in items:
            bb = o.GetBoundingBox()
            xs += [bb.GetLeft(), bb.GetRight()]
            ys += [bb.GetTop(), bb.GetBottom()]
        if not xs:
            return (0, 0, 0, 0)
        return g.window(min(xs) / 1e6, min(ys) / 1e6, max(xs) / 1e6, max(ys) / 1e6, grow)

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
            outer.sort(key=len)
            new = None
            # from the smallest island to any other; an island boxed in may still be reached from
            # another, so each island gets its turn as the source
            for k, src in enumerate(outer):
                tgt = [it for n_, isl in enumerate(outer) if n_ != k for it in isl]
                new = self.join(net, width, src, tgt, layers, clr, margin, minrun, vias)
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
        swin = self._extent(src)
        sa = {L: self.anchors(src, L, swin) for L in layers}
        box = self._join_box(sa, tgt, layers, 2 * margin + 1.0)
        if box is None:
            return None
        sa = {L: self.anchors(src, L, box) for L in layers}
        ta = {L: self.anchors(tgt, L, box) for L in layers}
        # a route the check rejects (the raster is approximate) is tried again further out; with a
        # check, a pair the router cannot join at clr is tried at the board's 0.1 mm
        tries = [clr, clr + 0.04, clr + 0.08] if check else [clr]
        while tries:
            c = tries.pop(0)
            b_ = blk if blk is not None and c == clr else None
            path, skip = None, False
            self._hcache = {}
            for mg, run in dict.fromkeys(((margin, minrun), (margin, min(minrun, 0.15)), (2 * margin, minrun))):
                if skip and mg == margin:
                    continue
                # the obstacles over this search's window (the wider window's only when it is tried)
                win = self._box(sa, ta, layers, mg)
                if win is None:
                    break
                if b_ is None or not _within(win, b_["win"]):
                    b_ = self.blocked(net.GetNetCode(), width / 2, c, win)
                path = self._search(sa, ta, b_, layers, mg, run, vias)
                if path is not None:
                    break
                # no way in this window even ignoring the turn rules: a shorter run cannot help
                skip = self._unreachable
            if path is None:
                tries = [0.1] if check and c > 0.1 and c == clr else []
                continue
            # the end correction spread three ways, until one passes the check; with a check, the
            # ends on pads move onto the pads' centres first (a hand-routed track ends there)
            fits = [(m, True) for m in FITS] + [(m, False) for m in FITS] if check else [(FITS[0], False)]
            same = set()  # modes whose centred tracks were the plain ones
            for mode, centre in fits:
                if not centre and mode in same:
                    continue
                out = self._commit(path, sa, ta, net, width, mode, centre)
                if centre and not self._centred:
                    same.add(mode)
                if check is None or check(self.created):
                    return out
                for _, o in self.created:
                    self.b.Remove(o)
                    self.graveyard.append(o)
                self.created = []
        return None

    def _join_box(self, sa, tgt, layers, margin):
        """join's window: the source copper and the target cell nearest to its centre (the
        target copper rasterised in growing windows around it), grown by margin."""
        g = self.g
        ys, xs = self._src_extent(sa, layers)
        if not ys:
            return None
        ci, cj = (min(ys) + max(ys)) / 2, (min(xs) + max(xs)) / 2
        R = 40
        while True:
            win = (max(0, int(ci) - R), min(g.ny, int(ci) + R + 2), max(0, int(cj) - R), min(g.nx, int(cj) + R + 2))
            ta = {L: self.anchors(tgt, L, win) for L in layers}
            best = self._nearest(ta, layers, ci, cj)
            # nothing outside the window lies nearer than R cells
            if (best is not None and best[0] <= R * R) or win == g.full:
                break
            R *= 2
        if best is not None:
            ys.append(best[1])
            xs.append(best[2])
        k = int(margin / RES)
        return max(0, min(ys) - k), min(g.ny, max(ys) + k + 1), max(0, min(xs) - k), min(g.nx, max(xs) + k + 1)

    @staticmethod
    def _src_extent(sa, layers):
        ys, xs = [], []
        for L in layers:
            m, _, _, (i0, _, j0, _) = sa[L]
            ii, jj = np.nonzero(m)
            ys += [int(ii.min()) + i0, int(ii.max()) + i0] if len(ii) else []
            xs += [int(jj.min()) + j0, int(jj.max()) + j0] if len(jj) else []
        return ys, xs

    @staticmethod
    def _nearest(ta, layers, ci, cj):
        best = None
        for L in layers:
            m, _, _, (i0, _, j0, _) = ta[L]
            ii, jj = np.nonzero(m)
            if len(ii):
                ii, jj = ii + i0, jj + j0
                n = int(np.argmin((ii - ci) ** 2 + (jj - cj) ** 2))
                d = (ii[n] - ci) ** 2 + (jj[n] - cj) ** 2
                if best is None or d < best[0]:
                    best = (d, int(ii[n]), int(jj[n]))
        return best

    def _box(self, sa, ta, layers, margin):
        """The search window: the source copper and the target cell nearest to it, grown by margin."""
        g = self.g
        ys, xs = self._src_extent(sa, layers)
        if not ys:
            return None
        ci, cj = (min(ys) + max(ys)) / 2, (min(xs) + max(xs)) / 2
        best = self._nearest(ta, layers, ci, cj)
        if best is not None:
            ys.append(best[1])
            xs.append(best[2])
        k = int(margin / RES)
        return max(0, min(ys) - k), min(g.ny, max(ys) + k + 1), max(0, min(xs) - k), min(g.nx, max(xs) + k + 1)

    _unreachable = False

    def _search(self, sa, ta, blk, layers, margin, minrun, vias=True):
        """A* over (layer, cell, direction): straight steps, 45 and 90 degree turns that each start
        a run of at least minrun, vias; never a sharper turn. Returns [(layer, i, j, dir)]."""
        g = self.g
        self._unreachable = False
        win = self._box(sa, ta, layers, margin)
        if win is None:
            return None
        i0, i1, j0, j1 = win
        H, W = i1 - i0, j1 - j0
        nl = len(layers)
        free = np.zeros((nl, H, W), bool)
        target = np.zeros((nl, H, W), bool)
        start = np.zeros((nl, H, W), bool)
        enter = np.zeros((nl, H, W), np.uint8)
        leave = np.zeros((nl, H, W), np.uint8)
        cost = np.ones((nl, H, W))
        bw = blk["win"]
        for li, L in enumerate(layers):
            free[li] = ~_crop(blk[L], bw, win, True) & g.inside[i0:i1, j0:j1]
            soft = _crop(blk[("soft", L)], bw, win, False)
            if self.hard_pours:
                free[li] &= ~soft
            # keep off obstacles where there is room: a hand-routed track does not hug them
            near = _l1(~free[li], 2) <= 2
            cost[li][near] = 1.3
            cost[li][soft] = 4.0
            tm, tow, tan, tw = ta[L]
            target[li] = _crop(tm, tw, win, False)
            town = _crop(tow, tw, win, -1)
            dirs = np.array([a[2] for a in tan] + [0], np.uint8)
            enter[li] = dirs[town]
            sm, sow, san, sw = sa[L]
            start[li] = _crop(sm, sw, win, False)
            sown = _crop(sow, sw, win, -1)
            dirs = np.array([_opposite(a[2]) for a in san] + [0], np.uint8)
            leave[li] = dirs[sown]
            # own copper is enterable where it is a via, a track end or a pad's centre; elsewhere (a
            # pad, a track's middle, a pour) only where other copper leaves room
            for ow, an in ((town, tan), (sown, san)):
                core = np.array([a[0] in ("via", "end") for a in an] + [False])
                free[li] |= core[ow]
                for a in an:
                    if a[0] == "pad":
                        i, j = g.ij(*a[1][0])
                        if i0 <= i < i1 and j0 <= j < j1:
                            free[li, i - i0, j - j0] = True
        target &= ~start
        if not target.any():
            return None
        via_ok = ~_crop(blk["novia"], bw, win, True) & ~_crop(blk["inner"], bw, win, True)
        rv = math.ceil((VIA_D / 2 + CLR) / RES)
        if nl == 2 and vias:
            both = free[0] & free[1] & ~start.any(0) & ~target.any(0)
            via_ok &= _l1(~both, max(rv - 2, 0) + 1) > max(rv - 2, 0)
        else:
            via_ok[:] = False
        run = max(1, round(minrun / RES))
        # the heuristic's arrays, shared by the searches of this window and obstacles
        key = (id(blk), win, self.hard_pours)
        hc = self._hcache.get(key) if self._hcache.get("blk") is blk else None
        if hc is None:
            self._hcache = {"blk": blk}
            rays = [_rays(target[li], enter[li]) for li in range(nl)]
            hc = self._hcache[key] = {"rays": rays, "octile": _heuristic(free, cost, target, via_ok, False)}
        st = self.stats
        path = _astar(free, cost, target, start, enter, leave, via_ok, run, st, hc["octile"], hc["rays"], GEO_AFTER)
        if path is None and st["last"] == "budget":
            # a hard search: the obstacles' detours bound it better (dearer to compute)
            if "geo" not in hc:
                hc["geo"] = _heuristic(free, cost, target, via_ok, True)
            st["geodesic"] = st.get("geodesic", 0) + 1
            path = _astar(free, cost, target, start, enter, leave, via_ok, run, st, hc["geo"], hc["rays"])
        if path is None:
            self._unreachable = st.get("last") == "unreachable"
            return None
        states = path
        # drop the wander inside the source copper: start at the cell the route leaves it from
        k = 0
        for n_, (li, i, j, _dr) in enumerate(states):
            if start[li, i, j]:
                k = n_
        states = states[k:]
        return [(layers[li], i + i0, j + j0, dr) for li, i, j, dr in states]

    # --- geometry ----------------------------------------------------------------------------------

    def _commit(self, states, sa, ta, net, width, mode="all", centre=False):
        """Tracks and vias of a found route, octilinear: the cells' corners, the ends moved onto
        the anchors (a pad's centre line, a via's centre, a track's end or centre line) by
        changing run lengths, never directions; with centre, onto a pad's centre where the runs
        allow it (self._centred tells whether one moved)."""
        g, b = self.g, self.b
        self.created = []
        self._centred = False
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
        a_src = _anchor_at(sa[L0], i0_, j0_)
        a_tgt = _anchor_at(ta[L1], i1_, j1_)
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
            # with centre, a pad's end moves onto the pad's centre (run lengths again)
            if centre and last and a_tgt[0] == "pad" and fe is None:
                pts, ok = _centred(pts, dirs, a_tgt[1][0], mode, at_start=False)
                self._centred |= ok
            if centre and first and a_src[0] == "pad" and fs is None:
                pts, ok = _centred(pts, dirs, a_src[1][0], mode, at_start=True)
                self._centred |= ok
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


def _within(win, outer) -> bool:
    return win is not None and outer[0] <= win[0] and win[1] <= outer[1] and outer[2] <= win[2] and win[3] <= outer[3]


def _anchor_at(A, i, j):
    _, owner, anchors, (i0, _, j0, _) = A
    return anchors[owner[i - i0, j - j0]]


# --- the search --------------------------------------------------------------------------------------------

UNREACHED = 1e5  # heuristic values at or above this: the target cannot be reached


def _octile(target):
    """Octile distance (straight step 1, diagonal DIAG) from each cell to the nearest set cell of
    target, ignoring obstacles: an exact chamfer distance in two sweeps (down, then up), each row
    taking the row before it and then running along itself both ways. The sweeps run along the
    longer side (fewer, longer rows)."""
    if target.shape[0] > target.shape[1]:
        return _octile(target.T).T.copy()
    H, W = target.shape
    h = np.where(target, 0.0, 1e9)
    if not target.any():
        return h
    cols = np.arange(W, dtype=np.float64)
    rows = np.nonzero(target.any(1))[0]
    lo, hi = int(rows[0]), int(rows[-1])
    # rows before the first target row only get values from the up sweep, and the other way round
    for order in (range(lo, H), range(hi, -1, -1)):
        prev = None
        for i in order:
            row = h[i]
            if prev is not None:
                p = h[prev]
                cand = p + 1.0
                np.minimum(cand[1:], p[:-1] + DIAG, out=cand[1:])
                np.minimum(cand[:-1], p[1:] + DIAG, out=cand[:-1])
                np.minimum(row, cand, out=row)
            # along the row, both ways: h[j] = min_k h[k] + |j - k|
            np.minimum(row, np.minimum.accumulate(row - cols) + cols, out=row)
            np.minimum(row, np.minimum.accumulate((row + cols)[::-1])[::-1] - cols, out=row)
            prev = i
    return h


def _rays(target, enter):
    """Per direction d: whether the ray from each cell runs into a target cell that may be entered
    by d, ignoring obstacles (a target further along its row, column or diagonal), or the cell is a
    target. A state whose direction misses needs a turn (BEND45 at least) on its layer."""
    H, W = target.shape
    out = []
    ii_, jj_ = np.mgrid[0:H, 0:W]
    for d in range(8):
        di, dj = STEPS[d]
        ok = target & (((enter >> d) & 1) == 1)
        ii, jj = np.nonzero(ok)
        if not len(ii):
            out.append(target.copy())
            continue
        if di == 0:  # along a row: a target further along it
            key, pos, kq, pq, n = ii_, jj_ * dj, ii, jj * dj, H
        elif dj == 0:
            key, pos, kq, pq, n = jj_, ii_ * di, jj, ii * di, W
        elif di == dj:  # the diagonal i - j constant
            key, pos, kq, pq, n = ii_ - jj_ + (W - 1), ii_ * di, ii - jj + (W - 1), ii * di, H + W - 1
        else:  # the anti-diagonal i + j constant
            key, pos, kq, pq, n = ii_ + jj_, ii_ * di, ii + jj, ii * di, H + W - 1
        far = np.full(n, -(10**9), np.int64)
        np.maximum.at(far, kq, pq)
        out.append((far[key] > pos) | target)
    return out


def _union(n, a, b):
    """Connected components of n nodes joined by the edges (a, b): each node's smallest member."""
    lab = np.arange(n)
    if not len(a):
        return lab
    while True:
        la, lb = lab[a], lab[b]
        m = np.minimum(la, lb)
        new = lab.copy()
        np.minimum.at(new, la, m)
        np.minimum.at(new, lb, m)
        while True:
            nn = new[new]
            if np.array_equal(nn, new):
                break
            new = nn
        if np.array_equal(new, lab):
            return lab
        lab = new


def _runs(free):
    """The free cells' row runs: an index per cell (-1 blocked), the count, and the pairs of runs
    that touch between neighbouring rows (8-neighbour: diagonal steps between blocked cells count,
    a relaxation of the search's rule)."""
    H, W = free.shape
    left = np.zeros_like(free)
    left[:, 1:] = free[:, :-1]
    starts = free & ~left
    n = int(starts.sum())
    rid = np.where(free, (np.cumsum(starts.ravel()) - 1).reshape(H, W), -1)
    si, sj = np.nonzero(starts)
    a, b = [], []
    # two runs of neighbouring rows touch where one's first cell touches the other
    for di in (-1, 1):
        for dj in (-1, 0, 1):
            ni, nj = si + di, sj + dj
            ok = (ni >= 0) & (ni < H) & (nj >= 0) & (nj < W)
            nb = rid[ni[ok], nj[ok]]
            m = nb >= 0
            a.append(rid[si[ok], sj[ok]][m])
            b.append(nb[m])
    return rid, n, np.concatenate(a), np.concatenate(b)


def _reach(free, target, via):
    """Per layer, the cells from which the target can be reached on that layer alone, and the
    cells from which it can be reached at all (through vias where via is set): free 8-neighbour
    regions, ignoring the search's turn rules (so it never says no where a route exists)."""
    nl = free.shape[0]
    rids, ns, ea, eb, off = [], [], [], [], 0
    for li in range(nl):
        rid, n, a, b = _runs(free[li])
        rids.append(rid)
        ns.append(n)
        ea.append(a + off)
        eb.append(b + off)
        off += n
    a, b = np.concatenate(ea), np.concatenate(eb)
    # one spare label past the last run: a layer without a free cell indexes it, masked out below
    lab = np.append(_union(off, a, b), -1)
    same, anyl = [], []
    tl = [np.unique(lab[rids[li][target[li] & free[li]] + sum(ns[:li])]) for li in range(nl)]
    for li in range(nl):
        r = rids[li]
        cell = np.where(r >= 0, lab[np.maximum(r, 0) + sum(ns[:li])], -1)
        same.append((r >= 0) & np.isin(cell, tl[li]))
    if nl == 2 and via.any():
        m = via & free[0] & free[1]
        va = rids[0][m]
        vb = rids[1][m] + ns[0]
        lab2 = np.append(_union(off, np.concatenate([a, va]), np.concatenate([b, vb])), -1)
        tall = np.unique(np.concatenate([lab2[rids[li][target[li] & free[li]] + sum(ns[:li])] for li in range(nl)]))
        for li in range(nl):
            r = rids[li]
            cell = np.where(r >= 0, lab2[np.maximum(r, 0) + sum(ns[:li])], -1)
            anyl.append((r >= 0) & np.isin(cell, tall))
    else:
        anyl = [np.zeros_like(s) for s in same]
    return same, anyl


def _path_cost(path, cost, run):
    """The search's cost of a route [(layer, i, j, dir)] (for tests and benchmarks)."""
    total = 0.0
    for (l0, i0, j0, d0), (l1, i1, j1, d1) in itertools.pairwise(path):
        if l0 != l1:
            total += VIA_COST
            continue
        if d0 != 8 and d1 != d0:
            t = (d1 - d0) % 8
            total += BEND45 if min(t, 8 - t) == 1 else BEND90
        di, dj = STEPS[d1]
        n = max(abs(i1 - i0), abs(j1 - j0))
        for s in range(1, n + 1):
            total += (DIAG if di and dj else 1.0) * cost[l1, i0 + di * s, j0 + dj * s]
    return total


BIG = 2e5  # the cost of entering a blocked cell, in the distance transforms


def _geodesic(cost, seeds, init=None):
    """Least cost from each cell to the seeds over 8-neighbour steps, entering a cell costing its
    cost (DIAG times it diagonally; BIG where blocked): down and up sweeps (each row from the row
    before it, then along itself both ways) until nothing changes. init: the seeds' values (0
    without). Values of UNREACHED and more: no way."""
    if cost.shape[0] > cost.shape[1]:
        return _geodesic(cost.T, seeds.T, None if init is None else init.T).T.copy()
    H, W = cost.shape
    h = np.full((H, W), 1e12)
    if init is None:
        h[seeds] = 0.0
    else:
        h[seeds] = init[seeds]
    if not seeds.any():
        return h
    P = np.cumsum(cost, axis=1)
    E = P - cost
    c2 = DIAG * cost
    acc = np.minimum.accumulate
    rows = np.nonzero(seeds.any(1))[0]
    lo, hi = int(rows[0]), int(rows[-1])
    for i in range(lo, hi + 1):
        row, e, p = h[i], E[i], P[i]
        np.minimum(row, acc(row - e) + e, out=row)
        np.minimum(row, acc((row + p)[::-1])[::-1] - p, out=row)
    first = True
    while True:
        old = h.copy()
        for order in (range(1, H), range(H - 2, -1, -1)) if not first else (range(lo + 1, H), range(H - 2, -1, -1)):
            q = order.start - order.step
            for i in order:
                p = h[q]
                a = p + cost[q]
                d = p + c2[q]
                np.minimum(a[1:], d[:-1], out=a[1:])
                np.minimum(a[:-1], d[1:], out=a[:-1])
                row, e, pp = h[i], E[i], P[i]
                np.minimum(row, a, out=row)
                np.minimum(row, acc(row - e) + e, out=row)
                np.minimum(row, acc((row + pp)[::-1])[::-1] - pp, out=row)
                q = i
        first = False
        if not (old - h > 1e-4).any():
            return h


def _heuristic(free, cost, target, via_ok, geodesic):
    """Lower bounds of the cost left, per layer: on the layer alone (h0) and with at least one via
    (hv); INF where there is no way. Octile distances inside the free regions that reach the
    target, or (geodesic) the least cost around the obstacles, with the vias' cost."""
    nl = free.shape[0]
    INF = float("inf")
    vias = nl == 2 and bool(via_ok.any())
    tg = [target[li] & free[li] for li in range(nl)]
    if not geodesic:
        oc = [_octile(tg[li]) for li in range(nl)]
        same, anyl = _reach(free, target, via_ok if vias else np.zeros(free.shape[1:], bool))
        h0 = [np.where(same[li], oc[li], INF) for li in range(nl)]
        if vias:
            both = np.minimum(oc[0], oc[1]) + VIA_COST
            hv = [np.where(anyl[li], both, INF) for li in range(nl)]
        else:
            hv = [np.full(free.shape[1:], INF) for _ in range(nl)]
        return h0, hv
    c = [np.where(free[li], cost[li], BIG) for li in range(nl)]
    h0 = [_geodesic(c[li], tg[li]) for li in range(nl)]
    hv = [np.full(free.shape[1:], 1e12) for _ in range(nl)]
    if vias:
        m = via_ok & free[0] & free[1]
        d = [np.minimum(h0[li], hv[li]) for li in range(nl)]
        # round k bounds the routes with k vias at most; those with more cost (k + 1) vias and
        # their octile distance at least
        rounds = 2
        for _ in range(rounds):
            new = [_geodesic(c[li], m & (d[1 - li] < UNREACHED), d[1 - li] + VIA_COST) for li in range(nl)]
            done = all(not (hv[li] - new[li] > 1e-4).any() for li in range(nl))
            hv = [np.minimum(hv[li], new[li]) for li in range(nl)]
            d = [np.minimum(h0[li], hv[li]) for li in range(nl)]
            if done:
                break
        else:
            # routes with more vias: wherever the target can be reached at all
            oc = np.minimum(_octile(tg[0]), _octile(tg[1])) + (rounds + 1) * VIA_COST
            _, anyl = _reach(free, target, via_ok)
            hv = [np.where(anyl[li], np.minimum(hv[li], oc), hv[li]) for li in range(nl)]
    out0 = [np.where(h < UNREACHED, np.maximum(h - 1e-4, 0.0), INF) for h in h0]
    outv = [np.where(h < UNREACHED, np.maximum(h - 1e-4, 0.0), INF) for h in hv]
    return out0, outv


def _astar(free, cost, target, start, enter, leave, via_ok, run, stats, heur=None, rays=None, budget=None):
    """The cheapest route from a start cell to a target cell; [(layer, i, j, dir)] or None.

    States (layer, cell, direction; direction 8 at a start or after a via). Moves: one step
    straight on; a 45 or 90 degree turn and a run of `run` cells (cut short where it enters the
    target); a via. The heuristic, per state: the lower bound of the cost left on its layer
    (heur's h0), plus BEND45 when its direction does not run into the target, or the bound with a
    via (heur's hv), whichever is less; never more than the cost left (admissible), so the first
    target state taken is a cheapest route. Regions that cannot reach the target are never
    entered. heur: (h0, hv) per layer, octile bounds by default (_heuristic); rays: _rays per
    layer. With budget, a search that expands more states stops (stats["last"] = "budget")."""
    nl, H, W = free.shape
    Wp = W + 2
    Np = (H + 2) * Wp
    INF = float("inf")
    stats["searches"] = stats.get("searches", 0) + 1
    if heur is None:
        heur = _heuristic(free, cost, target, via_ok, False)
    if rays is None:
        rays = [_rays(target[li], enter[li]) for li in range(nl)]
    h0a, hva = heur
    reach = np.zeros((nl, H, W), bool)
    for li in range(nl):
        reach[li] = (h0a[li] < INF) | (hva[li] < INF)
    seeds = [(li, i, j) for li, i, j in zip(*np.nonzero(start & free & reach), strict=True)]
    if not seeds:
        stats["last"] = "unreachable"
        return None
    vias = nl == 2 and bool(via_ok.any())

    def pad(a, val):
        out = np.full((H + 2, Wp), val, a.dtype)
        out[1:-1, 1:-1] = a
        return out.ravel()

    OFF = [di * Wp + dj for di, dj in STEPS]
    STEPV = [DIAG if di and dj else 1.0 for di, dj in STEPS]
    A, C, H0, HV, TG, VT, HIT = [], [], [], [], [], [], []
    for li in range(nl):
        fr = pad(free[li] & reach[li], False)  # a cell that cannot reach the target is never entered
        st = pad(start[li], False)
        tg = pad(target[li], False)
        en = pad(enter[li], 0)
        lv = pad(leave[li], 0)
        Al = []
        for d in range(8):
            off = OFF[d]
            ok = np.roll(fr, -off)
            di, dj = STEPS[d]
            if di and dj:
                # the corner rule looks at the free cells as they are
                fo = pad(free[li], False)
                ok &= np.roll(fo, -di * Wp) | np.roll(fo, -dj)
            nst = np.roll(st, -off)
            ok &= ~(st & ~nst & (((lv >> d) & 1) == 0))
            nt = np.roll(tg, -off)
            ne = ((np.roll(en, -off) >> d) & 1) == 1
            Al.append(np.where(~ok, 0, np.where(~nt, 1, np.where(ne, 2, 3))).astype(np.uint8).tobytes())
        A.append(Al)
        # memoryviews: indexing them gives Python floats, without a list's copy
        C.append(memoryview(pad(cost[li].astype(np.float64), 1.0)).cast("B").cast("d"))
        H0.append(memoryview(pad(h0a[li].astype(np.float64), INF)).cast("B").cast("d"))
        HV.append(memoryview(pad(hva[li].astype(np.float64), INF)).cast("B").cast("d"))
        TG.append(tg.tobytes())
        VT.append(pad(via_ok & free[1 - li] & reach[1 - li], False).tobytes() if vias else bytes(Np))
        HIT.append([pad(r, False).tobytes() for r in rays[li]])

    best = array.array("d", [INF]) * (nl * Np * 9)
    prev = {}
    heap = []
    for li, i, j in seeds:
        c = (i + 1) * Wp + (j + 1)
        s = (li * Np + c) * 9 + 8
        best[s] = 0.0
        heap.append((min(H0[li][c], HV[li][c]), 0.0, s))
    heapq.heapify(heap)
    pop, push = heapq.heappop, heapq.heappush
    # per direction: the moves (new direction, bend cost, cells), straight on first
    MOVES = [
        [(d, 0.0, 1)] + [((d + k) % 8, BEND45 if abs(k) == 1 else BEND90, run) for k in (1, -1, 2, -2)]
        for d in range(8)
    ]
    MOVES.append([(d, 0.0, 1) for d in range(8)])
    MOVES = [[(nd, bend, n, OFF[nd], STEPV[nd]) for nd, bend, n in m] for m in MOVES]
    RUNS = [{} for _ in range(nl)]  # (cell, direction) -> (end cell, cost) of a turn's run, or -1
    found = None
    expanded = 0
    limit = budget if budget is not None else -1
    while heap:
        _, ng, s = pop(heap)
        g = -ng
        if g > best[s]:
            continue
        expanded += 1
        if expanded == limit:
            break
        lc, dr = divmod(s, 9)
        li = 1 if lc >= Np else 0
        c = lc - li * Np
        if TG[li][c]:
            found = s
            break
        Al, Cl, H0l, HVl, Hit, runs = A[li], C[li], H0[li], HV[li], HIT[li], RUNS[li]
        base9 = li * Np * 9
        for nd, bend, n, off, stv in MOVES[dr]:
            Ad = Al[nd]
            if n == 1:
                a = Ad[c]
                if a != 1 and a != 2:
                    continue
                cur = c + off
                gg = g + bend + stv * Cl[cur]
            else:
                key = c * 8 + nd
                r_ = runs.get(key)
                if r_ is None:
                    cur = c
                    rc = 0.0
                    for _ in range(n):
                        a = Ad[cur]
                        if a == 0 or a == 3:
                            break
                        cur += off
                        rc += stv * Cl[cur]
                        if a == 2:
                            break
                    r_ = runs[key] = (-1, 0.0) if a == 0 or a == 3 else (cur, rc)
                cur, rc = r_
                if cur < 0:
                    continue
                gg = g + bend + rc
            ns = base9 + cur * 9 + nd
            if gg < best[ns]:
                hh = H0l[cur]
                if not Hit[nd][cur]:
                    hh += BEND45
                hv = HVl[cur]
                if hv < hh:
                    hh = hv
                best[ns] = gg
                prev[ns] = s
                push(heap, (gg + hh, -gg, ns))
        # a via onto the other layer
        if dr != 8 and VT[li][c]:
            ol = 1 - li
            gg = g + VIA_COST
            ns = (ol * Np + c) * 9 + 8
            if gg < best[ns]:
                best[ns] = gg
                prev[ns] = s
                push(heap, (gg + min(H0[ol][c], HV[ol][c]), -gg, ns))
    stats["expanded"] = stats.get("expanded", 0) + expanded
    if found is None:
        stats["last"] = "budget" if expanded == limit else "exhausted"
        return None
    stats["last"] = "found"
    states = [found]
    while states[-1] in prev:
        states.append(prev[states[-1]])
    states.reverse()
    out = []
    for s in states:
        lc, dr = divmod(s, 9)
        li = 1 if lc >= Np else 0
        c = lc - li * Np
        out.append((li, c // Wp - 1, c % Wp - 1, dr))
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


def _centred(pts, dirs, c, mode, at_start):
    """The route's end (its start with at_start) moved onto a pad's centre c by changing run
    lengths only; (points, True), or the points unchanged and False where that needs a run to
    turn round, a corner run to get shorter than MINRUN (or than it was), or the run into the
    pad to get shorter than 0.15 mm (or than it was)."""
    if at_start:
        rp = [list(p) for p in pts[::-1]]
        rd = [(d + 4) % 8 for d in dirs[::-1]]
    else:
        rp, rd = [list(p) for p in pts], list(dirs)
    end = rp[-1]
    r = (c[0] - end[0], c[1] - end[1])
    if math.hypot(*r) < 1e-6:
        return pts, False
    new = _fit(rp, rd, r, move=False, mode=mode)
    if math.dist(new[-1], c) > 1e-6:
        return pts, False
    old_l = [math.dist(a, b) for a, b in itertools.pairwise(rp)]
    new_l = [math.dist(a, b) for a, b in itertools.pairwise(new)]
    for k, (lo, ln) in enumerate(zip(old_l, new_l, strict=True)):
        least = min(lo, 0.15) if k == len(old_l) - 1 else min(lo, MINRUN)
        if ln < least - 1e-6:
            return pts, False
    return (new[::-1] if at_start else new), True


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
