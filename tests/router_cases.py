"""Router test cases on small synthetic boards, run by tests/test_router.py under a Python that has
KiCad's pcbnew module and numpy (the layout scripts' interpreter):

    python3 tests/router_cases.py CASE

Prints one JSON object: the case's routes and the checks' findings.
"""

from __future__ import annotations

import itertools
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "boards/main/layout"))
import router

NM = 1e6
CLEAR = 0.0995  # mm: the board rule (rules/jlcpcb.kicad_dru: 0.10), less the coordinates' rounding


def v(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


class Synth:
    """A two-layer board W x H mm with nets, pads and tracks."""

    def __init__(self, w=20.0, h=15.0):
        self.b = pcbnew.BOARD()
        pts = [(0, 0), (w, 0), (w, h), (0, h)]
        for a, c in zip(pts, pts[1:] + pts[:1], strict=True):
            s = pcbnew.PCB_SHAPE(self.b)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(v(*a))
            s.SetEnd(v(*c))
            s.SetLayer(pcbnew.Edge_Cuts)
            s.SetWidth(pcbnew.FromMM(0.05))
            self.b.Add(s)
        self.nets = {}
        self.fp = pcbnew.FOOTPRINT(self.b)
        self.fp.SetReference("U1")
        self.b.Add(self.fp)
        self.n = 0

    def net(self, name):
        if name not in self.nets:
            n = pcbnew.NETINFO_ITEM(self.b, name)
            self.b.Add(n)
            self.nets[name] = n
        return self.nets[name]

    def pad(self, net, x, y, w=0.6, h=0.6, shape=pcbnew.PAD_SHAPE_RECT, angle=0.0):
        self.n += 1
        p = pcbnew.PAD(self.fp)
        p.SetNumber(str(self.n))
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(p.SMDMask())
        p.SetShape(pcbnew.F_Cu, shape)
        p.SetSize(pcbnew.F_Cu, v(w, h))
        p.SetPosition(v(x, y))
        if angle:
            p.SetOrientation(pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
        p.SetNet(self.net(net))
        self.fp.Add(p)
        return p

    def track(self, net, a, c, width=0.2, layer=pcbnew.F_Cu):
        t = pcbnew.PCB_TRACK(self.b)
        t.SetStart(v(*a))
        t.SetEnd(v(*c))
        t.SetWidth(pcbnew.FromMM(width))
        t.SetLayer(layer)
        t.SetNet(self.net(net))
        self.b.Add(t)
        return t


# --- checks --------------------------------------------------------------------------------------------


def findings(b, net, created, width):
    """Octilinear, no acute corner, the board's clearances, the width, one island."""
    out = []
    tracks = [o for k, o in created if k == "track"]
    vias = [o for k, o in created if k == "via"]
    for t in tracks:
        a, c = t.GetStart(), t.GetEnd()
        dx, dy = (c.x - a.x) / NM, (c.y - a.y) / NM
        L = math.hypot(dx, dy)
        off = abs((math.degrees(math.atan2(-dy, dx)) + 22.5) % 45 - 22.5)
        if L * math.sin(math.radians(off)) > 1e-3:
            out.append(f"off 45: {a.x / NM:.4f},{a.y / NM:.4f} -> {c.x / NM:.4f},{c.y / NM:.4f}")
        if abs(t.GetWidth() / NM - width) > 1e-6:
            out.append(f"width {t.GetWidth() / NM}")
    # corners between the net's segments, outside pads and vias
    nc = net.GetNetCode()
    segs = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetNetCode() == nc]
    ends = {}
    for t in segs:
        for p, q in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
            ends.setdefault((p.x, p.y, t.GetLayer()), []).append((q.x - p.x, q.y - p.y))
    covered = [o for o in b.GetTracks() if o.GetClass() == "PCB_VIA" and o.GetNetCode() == nc]
    pads = [p for f in b.GetFootprints() for p in f.Pads() if p.GetNetCode() == nc]
    for (x, y, layer), arms in ends.items():
        pt = pcbnew.VECTOR2I(int(x), int(y))
        if any((o.GetPosition() - pt).EuclideanNorm() <= o.GetWidth(layer) / 2 for o in covered):
            continue
        if any(p.IsOnLayer(layer) and p.HitTest(pt) for p in pads):
            continue
        for u, w_ in itertools.combinations(arms, 2):
            cos = (u[0] * w_[0] + u[1] * w_[1]) / (math.hypot(*u) * math.hypot(*w_))
            if math.degrees(math.acos(max(-1.0, min(1.0, cos)))) < 90 - 0.5:
                out.append(f"acute corner at {x / NM:.4f},{y / NM:.4f}")
    # clearances to other nets' copper
    cl = int(CLEAR * NM)
    others = [o for o in b.GetTracks() if o.GetNetCode() != nc]
    opads = [p for f in b.GetFootprints() for p in f.Pads() if p.GetNetCode() != nc]
    for o in tracks + vias:
        for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
            if o.GetClass() == "PCB_TRACK" and o.GetLayer() != layer:
                continue
            shape = o.GetEffectiveShape(layer)
            for x in others:
                if (x.GetClass() == "PCB_VIA" or x.GetLayer() == layer) and x.GetEffectiveShape(layer).Collide(
                    shape, cl
                ):
                    out.append(f"clearance to {x.GetNetname()} on layer {layer}")
            for p in opads:
                if p.IsOnLayer(layer) and p.GetEffectiveShape(layer).Collide(shape, cl):
                    out.append(f"clearance to pad {p.GetNumber()} ({p.GetNetname()}) on layer {layer}")
    return sorted(set(out))


def summary(r, b, net, created, added, width, t):
    return {
        "routes": [
            [a if isinstance(a, str) else int(a), *[list(map(lambda q: round(q, 4), p)) for p in rest]]
            for a, *rest in added
        ],
        "islands": len(r.copper(net.GetNetCode())),
        "findings": findings(b, net, created, width),
        "vias": sum(1 for k, _ in created if k == "via"),
        "length": round(sum(o.GetLength() for k, o in created if k == "track") / NM, 4),
        "seconds": round(t, 3),
        "stats": {k: v_ for k, v_ in r.stats.items() if isinstance(v_, int)},
    }


def route(s, name, width=0.2, **kw):
    """route_net on the board, keeping the items it made (for the checks)."""
    r = router.Router(s.b)
    before = {o.m_Uuid.AsString() for o in s.b.GetTracks()}
    t0 = time.time()
    try:
        added = r.route_net(name, width, **kw)
    except RuntimeError:
        added = None
    t = time.time() - t0
    net = s.net(name)
    made = [
        ("via" if o.GetClass() == "PCB_VIA" else "track", o)
        for o in s.b.GetTracks()
        if o.m_Uuid.AsString() not in before
    ]
    out = summary(r, s.b, net, made, added or [], width, t)
    out["routed"] = added is not None
    return out


# --- cases ---------------------------------------------------------------------------------------------


def case_bend():
    """Two pads out of line: a route with 45 degree corners."""
    s = Synth()
    s.pad("A", 3, 4, 1.0, 0.6)
    s.pad("A", 15, 9, 1.0, 0.6)
    s.pad("B", 9, 6.5, 0.6, 0.6)  # an obstacle on the way
    return route(s, "A")


def channel(s):
    """A wall of other nets' pads across the board on F.Cu with one gap a 0.2 mm track fits
    (0.2 + 2 x 0.12 clearance + a cell), and pads of a third net along both sides of it."""
    gap = 0.2 + 2 * router.CLR + 0.1
    pitch = 0.9
    y = 0.6
    xs = []
    x = 0.8
    while x < 19.5:
        xs.append(x)
        x += pitch
    mid = len(xs) // 2
    for k, x in enumerate(xs):
        if k == mid:
            continue
        s.pad("W", x, 7.5, 0.6, y)
    # the gap: the pads beside it moved apart to leave exactly the gap between their edges
    x0 = xs[mid]
    s.pad("W", x0 - (gap / 2 + 0.3) - 0.3, 7.5, 0.6, y)
    s.pad("W", x0 + (gap / 2 + 0.3) + 0.3, 7.5, 0.6, y)
    return x0


def case_centred():
    """join with a check (as the layout scripts call it): the route ends on the pads' centres."""
    s = Synth()
    a = s.pad("A", 3, 4, 1.0, 0.6)
    c = s.pad("A", 15, 9, 1.0, 0.6)
    s.pad("B", 9, 6.5, 0.6, 0.6)
    r = router.Router(s.b)
    net = s.net("A")
    src, tgt = r.copper(net.GetNetCode())
    added = r.join(net, 0.2, src, tgt, check=lambda created: not findings(s.b, net, created, 0.2))
    made = list(r.created)
    out = summary(r, s.b, net, made, added or [], 0.2, 0.0)
    out["pads"] = [[round(p.GetPosition().x / NM, 4), round(p.GetPosition().y / NM, 4)] for p in (a, c)]
    out["routed"] = added is not None
    return out


def case_channel():
    """F.Cu only: the route must thread the one gap in a wall of pads."""
    s = Synth()
    x0 = channel(s)
    s.pad("A", 3, 3, 0.6, 0.6)
    s.pad("A", 16, 12, 0.6, 0.6)
    out = route(s, "A", layers=(pcbnew.F_Cu,))
    out["gap_x"] = x0
    return out


def case_via():
    """A full-width wall of other nets' tracks on F.Cu: the route takes vias to B.Cu and back."""
    s = Synth()
    for k in range(4):
        y = 6.5 + 0.5 * k
        s.track(f"W{k}", (0.3, y), (19.7, y), 0.2)
    s.pad("A", 4, 3, 0.6, 0.6)
    s.pad("A", 14, 12, 0.6, 0.6)
    return route(s, "A")


def case_boxed():
    """A pad boxed in by a ring of another net's track on F.Cu, F.Cu only: no route, found fast."""
    s = Synth()
    ring = [(6, 4), (10, 4), (10, 8), (6, 8)]
    for a, c in zip(ring, ring[1:] + ring[:1], strict=True):
        s.track("W", a, c, 0.3)
    s.pad("A", 8, 6, 0.6, 0.6)
    s.pad("A", 16, 12, 0.6, 0.6)
    return route(s, "A", layers=(pcbnew.F_Cu,))


def case_dense():
    """A field of 0.9 mm pitch pads of other nets, edge to edge, with random gaps: the route must
    find its way through it, every 45 degree corner and clearance kept (the speed bound's case)."""
    s = Synth(20, 16)
    rng = np.random.default_rng(7)
    for i in range(14):
        for j in range(21):
            if rng.random() < 0.6:
                s.pad(f"N{(i * 21 + j) % 9}", 0.6 + j * 0.9, 2.2 + i * 0.9, 0.45, 0.45)
    s.pad("A", 1.5, 1.0, 0.6, 0.6)
    s.pad("A", 18.5, 15.2, 0.6, 0.6)
    return route(s, "A", width=0.15, clr=0.1, layers=(pcbnew.F_Cu,))


def case_search():
    """The search alone, on random grids: the octile and the obstacle-aware heuristics give
    the same cost as no heuristic at all (Dijkstra), so both never overestimate."""
    rng = np.random.default_rng(3)
    rows = []
    grids = []
    for k in range(12):
        H, W = 40 + 7 * k, 50 + 5 * k
        free = rng.random((2, H, W)) > 0.3 + 0.02 * k
        free[1] |= rng.random((H, W)) > 0.5
        cost = np.ones((2, H, W))
        cost[rng.random((2, H, W)) < 0.2] = 1.3
        cost[rng.random((2, H, W)) < 0.05] = 4.0
        target = np.zeros((2, H, W), bool)
        start = np.zeros((2, H, W), bool)
        ti, tj = rng.integers(0, H), rng.integers(0, W)
        target[k % 2, max(ti - 1, 0) : ti + 2, max(tj - 1, 0) : tj + 2] = True
        start[0, 2:4, 2:4] = True
        free |= target | start
        enter = np.full((2, H, W), 0xFF, np.uint8)
        leave = np.full((2, H, W), 0xFF, np.uint8)
        via = rng.random((H, W)) > 0.6
        grids.append((free, cost, target, start, enter, leave, via, 6 if k % 3 else 3))
    # walls across alternate layers: the route takes four vias
    H, W = 30, 100
    free = np.ones((2, H, W), bool)
    for x in (20, 60):
        free[0, :, x] = False
    for x in (40, 80):
        free[1, :, x] = False
    target = np.zeros((2, H, W), bool)
    start = np.zeros((2, H, W), bool)
    target[0, 14:16, 96:98] = True
    start[0, 14:16, 2:4] = True
    full = np.full((2, H, W), 0xFF, np.uint8)
    grids.append((free, np.ones((2, H, W)), target, start, full, full, np.ones((H, W), bool), 6))
    for free, cost, target, start, enter, leave, via, run in grids:
        H, W = free.shape[1:]
        costs = []
        for mode in ("zero", "octile", "geodesic"):
            st = {}
            heur = None
            if mode == "zero":
                z = [np.where(np.ones((H, W), bool), 0.0, 0.0) for _ in range(2)]
                heur = (z, z)
                rays = [[np.ones((H, W), bool)] * 8 for _ in range(2)]
            else:
                heur = router._heuristic(free, cost, target, via, mode == "geodesic")
                rays = None
            p = router._astar(free, cost, target, start, enter, leave, via, run, st, heur, rays)
            costs.append(None if p is None else round(router._path_cost(p, cost, run), 6))
        rows.append(costs)
    return {"costs": rows}


def case_determinism():
    """The same board twice: the same tracks."""
    a = case_via()
    b = case_via()
    return {"same": a["routes"] == b["routes"], "routes": a["routes"]}


if __name__ == "__main__":
    print(json.dumps(globals()[f"case_{sys.argv[1]}"]()))
