"""Every track of the main board at a multiple of 45 degrees, as a one-off pcbnew script (KiCad 10).

    python3 boards/main/layout/octilinear.py

Runs once, after rail_silk.py, on the layout it leaves. The previous revision's tracks (hand-routed
in Altium) all run at 0, 45 or 90 degrees; the copper that fixes.py, refine.py and usb_wall.py
route with the first version of router.py does not (it string-pulled each route to any angle), nor
do a few hand tracks of those scripts and of previous/rework.py. A segment is off when its end lies
more than 1 um from the nearest 45 degree line through its start (tests/test_layout.py). The steps,
in order:

- snap: a segment less than SNAP off the line has the end that can move (inside its pad, or with
  the tracks and via there) moved onto it, when every segment there stays on its line and clear;
- slide: a single segment between two pads, or a pad and a via, becomes one straight segment along
  a pad axis (a diagonal where no axis fits) by moving its pad ends within their pads;
- reroute: every other off segment is ripped up with the router-made connection it belongs to
  (back to the pads, vias and junctions where other copper continues; on a long hand track only
  the off segment and its short neighbours), with the vias left joining nothing, and routed again
  by router.py between the same copper, in the ripped copper's width: the escapes between IC1's
  0.4 mm pitch pads first, then the signals, then the supplies, longest first. Each new track
  keeps the board's clearances exactly (`clear`); a route more than DETOUR times longer than the
  ripped copper, or one that cuts another net's pour in two (more unconnected items after the
  pours are refilled), is tried again with the pours as obstacles, else the connection is put
  back as it was;
- dogleg: an off segment left becomes one straight segment again where its corner can slide along
  the track before it, else two segments, straight and 45 degrees, between the same ends (the
  In2.Cu VCORE track of previous/rework.py and refine.py, the wide supply tracks, the IC1
  escapes);
- chain dogleg: a chain of off segments left becomes the first clear two- or three-segment
  octilinear path between its ends;
- corners: the acute corner of the previous revision's copper that is left (Wall_Sensor_0's fork
  on F.Cu left of IC1) is squared: the branch to R14 joins the diagonal square to it;
then zero-length segments, vias that join a single layer and teardrops that reach no track or
via go, the zones are refilled, the board saved and `pcb layout` syncs it. The USB pair keeps its
geometry but for U6 pad 1's D+ escape, which stays one segment 6 um shorter (D+ 122.27 mm, D-
121.72 mm of track, as before within 0.01 mm).

    python3 boards/main/layout/octilinear.py --no-sync      # skip the `pcb layout` sync
    python3 boards/main/layout/octilinear.py BOARD OUT      # on a copy, no sync
"""

from __future__ import annotations

import collections
import itertools
import math
import sys
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "boards/main/previous"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixes as fx  # noqa: E402
import router  # noqa: E402
import transfer_layout as tl  # noqa: E402

LAYOUT = ROOT / "boards/main/layout/main.kicad_pcb"
TOL = 0.5e-3  # mm: an end further than this from the 45 degree line through the start is off (the test: 1 um)
SNAP = 0.025  # mm: off by less than this, the segment's end moves onto the line
NM = 1e6
COPPER = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
POWER = {"GND", "3V3", "VBAT", "+5V", "+20V", "VCORE", "VDDA", "SWD_VDD", "REGULATORS.VSYS"}
# octilinear unit steps in nm, (dx, dy)
UNITS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


# --- geometry ---------------------------------------------------------------------------------------


def miss(a, b) -> float:
    """mm between b and the nearest 45 degree line through a (a, b: VECTOR2I)."""
    dx, dy = (b.x - a.x) / NM, (b.y - a.y) / NM
    length = math.hypot(dx, dy)
    if length == 0:
        return 0.0
    off = abs((math.degrees(math.atan2(-dy, dx)) + 22.5) % 45 - 22.5)
    return length * math.sin(math.radians(off))


def is_off(t) -> bool:
    return t.GetClass() == "PCB_TRACK" and miss(t.GetStart(), t.GetEnd()) > TOL


def onto_line(a, b):
    """b moved onto the nearest 45 degree line through a, exactly in nm."""
    dx, dy = b.x - a.x, b.y - a.y
    k = round(math.degrees(math.atan2(dy, dx)) / 45) % 8
    ux, uy = UNITS[k]
    if ux == 0:
        return pcbnew.VECTOR2I(a.x, b.y)
    if uy == 0:
        return pcbnew.VECTOR2I(b.x, a.y)
    s = round((abs(dx) + abs(dy)) / 2)
    return pcbnew.VECTOR2I(a.x + ux * s, a.y + uy * s)


def cp(p) -> pcbnew.VECTOR2I:
    """A copy: GetStart()/GetEnd() return the track's own point, which follows SetStart/SetEnd."""
    return pcbnew.VECTOR2I(p.x, p.y)


def v2(p) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(round(p[0] * NM), round(p[1] * NM))


def same(a, b) -> bool:
    """One board item (SWIG proxies of it are not identical)."""
    return a.m_Uuid.AsString() == b.m_Uuid.AsString()


def segs():
    return [t for t in fx.B.GetTracks() if t.GetClass() == "PCB_TRACK"]


def pads_at(p, layer, nc):
    return [
        q
        for f in fx.B.GetFootprints()
        for q in f.Pads()
        if q.GetNetCode() == nc and q.IsOnLayer(layer) and q.HitTest(p)
    ]


def via_at(p, nc, tol=1):
    for v in fx.B.GetTracks():
        if v.GetClass() == "PCB_VIA" and v.GetNetCode() == nc and (v.GetPosition() - p).EuclideanNorm() <= tol:
            return v
    return None


def new_track(net, layer, width, a, b):
    dirty()
    t = pcbnew.PCB_TRACK(fx.B)
    t.SetStart(a)
    t.SetEnd(b)
    t.SetWidth(width)
    t.SetLayer(layer)
    t.SetNet(net)
    fx.B.Add(t)
    return t


# --- snap ---------------------------------------------------------------------------------------------


def snap(r) -> int:
    """Move the free end of each nearly octilinear segment onto its line."""
    done = 0
    for t in segs():
        if not is_off(t) or miss(t.GetStart(), t.GetEnd()) > SNAP:
            continue
        s_, e_ = cp(t.GetStart()), cp(t.GetEnd())
        for fixed, moving, set_end in ((s_, e_, True), (e_, s_, False)):
            new = onto_line(fixed, moving)
            nc, layer = t.GetNetCode(), t.GetLayer()
            via = via_at(moving, nc)
            others = [
                (o, o.GetStart() == moving)
                for o in segs()
                if not same(o, t)
                and o.GetNetCode() == nc
                and (o.GetLayer() == layer or via is not None)
                and moving in (o.GetStart(), o.GetEnd())
            ]
            pads = pads_at(moving, layer, nc)
            if pads and not all(p.HitTest(new) for p in pads):
                continue
            ok = clear(nc, layer, t.GetWidth(), [fixed, new], r)
            for o, at_start in others:
                a, b = (new, o.GetEnd()) if at_start else (o.GetStart(), new)
                if miss(a, b) > 1e-6 or not clear(nc, o.GetLayer(), o.GetWidth(), [a, b], r):
                    ok = False
            if not ok:
                continue
            (t.SetEnd if set_end else t.SetStart)(new)
            for o, at_start in others:
                (o.SetStart if at_start else o.SetEnd)(new)
            if via is not None:
                via.SetPosition(new)
            done += 1
            break
    return done


# --- slide: single segments between pads and vias -----------------------------------------------------


CLEAR = 0.0995  # mm, copper to copper (rules/jlcpcb.kicad_dru: 0.10, less the coordinates' rounding)
HOLE_CLEAR = {"via": 0.2, "pth": 0.28}  # mm, hole to track (0.20 / 0.28)
EDGE_CLEAR = 0.2  # mm, copper to board edge (0.20)
DETOUR = 2.0  # a new route's length, at most, over the ripped copper's (plus 3 mm)


_EDGES = []


def _edges() -> list:
    """The board outline (and its cut-outs) as segments."""
    if not _EDGES:
        outl = pcbnew.SHAPE_POLY_SET()
        fx.B.GetBoardPolygonOutlines(outl, True)
        for k in range(outl.OutlineCount()):
            chains = [outl.Outline(k)] + [outl.Hole(k, h) for h in range(outl.HoleCount(k))]
            for ch in chains:
                _EDGES.extend(ch.CSegment(i) for i in range(ch.SegmentCount()))
    return _EDGES


_INDEX = {}


def dirty() -> None:
    """Items were added or removed: clear() rebuilds its index."""
    _INDEX.clear()


def _nearby(pts, grow):
    """Tracks, vias, pads and teardrops whose bounding box (grown by 2 mm, so items moved since
    the index was built stay found) meets the box of pts grown by grow (nm)."""
    import numpy as np

    if not _INDEX:
        objs = [("track", o) for o in fx.B.GetTracks()]
        objs += [("pad", p) for f in fx.B.GetFootprints() for p in f.Pads()]
        objs += [("zone", z) for z in fx.B.Zones() if _teardrop(z)]
        boxes = []
        for _, o in objs:
            bb = o.GetBoundingBox()
            boxes.append((bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))
        _INDEX["objs"], _INDEX["boxes"] = objs, np.array(boxes, dtype=np.float64)
    b = _INDEX["boxes"]
    xs, ys = [p.x for p in pts], [p.y for p in pts]
    g = grow + 2 * NM
    m = (b[:, 0] <= max(xs) + g) & (b[:, 2] >= min(xs) - g) & (b[:, 1] <= max(ys) + g) & (b[:, 3] >= min(ys) - g)
    return [_INDEX["objs"][i] for i in np.nonzero(m)[0]]


def clear(nc, layer, width, pts, r) -> bool:
    """Segments through pts (VECTOR2I) of this net, layer and width (nm) keep the board's
    clearances to other nets' tracks, vias, pads and teardrops, to holes and to the edge
    (pours of other nets give way)."""
    segs_ = [pcbnew.SHAPE_SEGMENT(a, b, int(width)) for a, b in itertools.pairwise(pts) if a != b]
    seg_lines = [pcbnew.SEG(a, b) for a, b in itertools.pairwise(pts) if a != b]
    cl = int(CLEAR * NM)
    for kind, o in _nearby(pts, width + 1 * NM):
        if o.GetNetCode() == nc and not (kind == "pad" and o.HasHole()):
            continue
        if kind == "track":
            if o.GetClass() == "PCB_VIA":
                hole = (o.GetDrillValue() / 2 + HOLE_CLEAR["via"] * NM + width / 2) ** 2
                if any(s.SquaredDistance(o.GetPosition()) < hole for s in seg_lines):
                    return False
            elif o.GetLayer() != layer:
                continue
            shape = o.GetEffectiveShape(layer)
            if any(shape.Collide(s, cl) for s in segs_):
                return False
        elif kind == "pad":
            if o.HasHole() and o.GetNetCode() != nc:
                d = max(o.GetDrillSize().x, o.GetDrillSize().y) / 2 + HOLE_CLEAR["pth"] * NM + width / 2
                if any(s.SquaredDistance(o.GetPosition()) < d * d for s in seg_lines):
                    return False
            if o.GetNetCode() == nc or not o.IsOnLayer(layer):
                continue
            shape = o.GetEffectiveShape(layer)
            if any(shape.Collide(s, cl) for s in segs_):
                return False
        elif o.IsOnLayer(layer):
            fill = o.GetFilledPolysList(layer)
            if any(fill.Collide(s, int(cl + width / 2)) for s in seg_lines):
                return False
    # the board edge
    lim = (EDGE_CLEAR * NM + width / 2) ** 2
    return not any(e.SquaredDistance(s) < lim for e in _edges() for s in seg_lines)


def slide(r) -> int:
    """A segment from a pad to a pad or a via becomes octilinear by moving its pad ends."""
    done = 0
    for t in segs():
        if not is_off(t):
            continue
        nc, layer = t.GetNetCode(), t.GetLayer()
        ends = [cp(t.GetStart()), cp(t.GetEnd())]
        loose = [e for e in ends if not pads_at(e, layer, nc)]
        if any(
            not same(o, t) and o.GetNetCode() == nc and (e in (o.GetStart(), o.GetEnd())) for o in segs() for e in loose
        ):
            continue  # another track continues from an end outside a pad
        kinds = []
        for e in ends:
            v, p = via_at(e, nc, tol=1000), pads_at(e, layer, nc)
            kinds.append(("via", v) if v is not None else ("pad", p[0]) if p else None)
        if None in kinds or all(k[0] == "via" for k in kinds):
            continue
        best = None
        (ka, a_), (kb, b_) = kinds
        pa, pb = ends
        for k in range(8):
            ux, uy = UNITS[k]
            n = math.hypot(ux, uy)
            u = (ux / n, uy / n)
            axis_pad = a_ if ka == "pad" else b_
            deg = (axis_pad.GetOrientation().AsDegrees() - math.degrees(math.atan2(-uy, ux))) % 90
            on_axis = min(deg, 90 - deg) < 0.5
            d = ((pb.x - pa.x) * u[0] + (pb.y - pa.y) * u[1]) / NM
            if d <= 0.05:
                continue
            step = pcbnew.VECTOR2I(round(u[0] * d * NM), round(u[1] * d * NM))
            # keep one end and put the other on the line from it; or move both pads' ends
            cands = []
            if kb == "pad":
                cands.append((pa, onto_line(pa, pa + step)))
            if ka == "pad":
                cands.append((onto_line(pb, pb - step), pb))
            if ka == "pad" and kb == "pad":
                na = pcbnew.VECTOR2I(round((pa.x + pb.x - step.x) / 2), round((pa.y + pb.y - step.y) / 2))
                cands.append((na, onto_line(na, na + step)))
            for na, nb in cands:
                if (ka == "pad" and not a_.HitTest(na)) or (ka == "via" and na != pa):
                    continue
                if (kb == "pad" and not b_.HitTest(nb)) or (kb == "via" and nb != pb):
                    continue
                if not clear(nc, layer, t.GetWidth(), [na, nb], r):
                    continue
                cost = (na - pa).EuclideanNorm() + (nb - pb).EuclideanNorm() + (0 if on_axis else 0.3 * NM)
                if best is None or cost < best[0]:
                    best = (cost, na, nb)
        if best is not None:
            t.SetStart(best[1])
            t.SetEnd(best[2])
            done += 1
    return done


# --- reroute: the router-made connections -------------------------------------------------------------


def chains() -> list[list]:
    """Each off segment with the tracks it continues through (ends where exactly two tracks of
    its net meet on its layer, outside pads and vias), in order."""
    ends = collections.defaultdict(list)
    for t in segs():
        for p in (t.GetStart(), t.GetEnd()):
            ends[(p.x, p.y, t.GetLayer(), t.GetNetCode())].append(t)

    def stop(p, layer, nc):
        return pads_at(p, layer, nc) or via_at(p, nc, tol=230_000)

    seen, out = set(), []
    for t in segs():
        if not is_off(t) or t.m_Uuid.AsString() in seen:
            continue
        chain = [t]
        seen.add(t.m_Uuid.AsString())
        for p0 in (t.GetStart(), t.GetEnd()):
            cur, p = t, p0
            while True:
                others = [o for o in ends[(p.x, p.y, cur.GetLayer(), cur.GetNetCode())] if not same(o, cur)]
                if len(others) != 1 or stop(p, cur.GetLayer(), cur.GetNetCode()):
                    break
                nxt = others[0]
                if nxt.m_Uuid.AsString() in seen:
                    break
                seen.add(nxt.m_Uuid.AsString())
                chain.insert(0, nxt) if p0 == t.GetStart() else chain.append(nxt)
                cur, p = nxt, (nxt.GetEnd() if nxt.GetStart() == p else nxt.GetStart())
        out.append(chain)
    return out


def rip_plan() -> list:
    """The tracks to rip: a whole chain when it is short or off in more than one segment (the
    router's), else the off segment and its neighbours up to 2 mm (a hand track's one bad turn)."""
    rips = []
    for ch in chains():
        offs = [k for k, t in enumerate(ch) if is_off(t)]
        if len(offs) >= 2 or sum(t.GetLength() for t in ch) / NM <= 6.0:
            rips += ch
        else:
            k = offs[0]
            rips += [ch[n] for n in (k - 1, k, k + 1) if 0 <= n < len(ch) and (n == k or ch[n].GetLength() / NM <= 2.0)]
    return rips


def _kind(o) -> str:
    return {"PAD": "pad", "PCB_VIA": "via", "PCB_TRACK": "track", "ZONE": "zone"}.get(o.GetClass(), "")


def _teardrop(o) -> bool:
    return o.GetClass() == "ZONE" and o.GetAssignedPriority() >= tl.TEARDROP_PRIORITY


def in_pour(v) -> bool:
    """A pour of the via's net (not a teardrop) holds it on some layer."""
    return any(
        z.GetNetCode() == v.GetNetCode()
        and not z.GetIsRuleArea()
        and not _teardrop(z)
        and z.IsOnLayer(lay)
        and z.GetFilledPolysList(lay).Collide(v.GetPosition(), v.GetWidth(lay) // 2)
        for z in fx.B.Zones()
        for lay in COPPER
    )


def _touching(o, p, layer, reach):
    """Copper of o's net at point p on a layer, within reach (nm): pads, vias, tracks, pours."""
    nc, out = o.GetNetCode(), []
    for kind, x in _nearby([p, p], reach):
        if x.GetNetCode() != nc or same(x, o):
            continue
        on = (
            x.IsOnLayer(layer)
            if kind == "pad"
            else kind == "track" and (x.GetClass() == "PCB_VIA" or x.GetLayer() == layer)
        )
        if on and x.GetEffectiveShape(layer).Collide(p, int(reach)):
            out.append(x)
    out += [
        z
        for z in fx.B.Zones()
        if z.GetNetCode() == nc
        and not z.GetIsRuleArea()
        and not _teardrop(z)
        and z.IsOnLayer(layer)
        and z.GetFilledPolysList(layer).Collide(p, int(reach))
    ]
    return out


def connections(rips) -> list[dict]:
    """The ripped tracks grouped into connections: tracks whose copper meets at an end, or that
    meet at a via left with nothing else to join, are one; each with the copper its ends touch."""
    uid = {t.m_Uuid.AsString(): t for t in rips}
    touch = {}  # track -> items at its ends
    for u, t in uid.items():
        touch[u] = [x for e in (t.GetStart(), t.GetEnd()) for x in _touching(t, e, t.GetLayer(), t.GetWidth() // 2)]
    # a via is left with nothing to join when everything on it is ripped
    dead_vias = {}
    for items in touch.values():
        for v in items:
            if v.GetClass() != "PCB_VIA" or v.m_Uuid.AsString() in dead_vias:
                continue
            on = [
                x
                for layer in COPPER
                for x in _touching(v, v.GetPosition(), layer, v.GetWidth(pcbnew.F_Cu) // 2)
                if x.GetClass() != "PCB_TRACK" or x.GetLayer() == layer
            ]
            if all(x.m_Uuid.AsString() in uid for x in on):
                dead_vias[v.m_Uuid.AsString()] = (v, on)
    parent = {u: u for u in [*uid, *dead_vias]}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    terms = collections.defaultdict(dict)
    for u, items in touch.items():
        for x in items:
            xu = x.m_Uuid.AsString()
            if xu in parent:
                parent[find(xu)] = find(u)
            elif _kind(x):
                terms[u][xu] = (_kind(x), x)
    for u, (_, on) in dead_vias.items():
        for x in on:
            parent[find(x.m_Uuid.AsString())] = find(u)
    conns = collections.defaultdict(lambda: {"tracks": [], "terms": {}, "vias": []})
    for u, t in uid.items():
        c = conns[find(u)]
        c["tracks"].append(t)
        c["terms"].update(terms[u])
    for u, (v, _) in dead_vias.items():
        conns[find(u)]["vias"].append(v)
    return list(conns.values())


def _width(c) -> float:
    ws = [t.GetWidth() for t in c["tracks"] if is_off(t)] or [t.GetWidth() for t in c["tracks"]]
    return round(max(ws) / NM, 4)


def _groups(r, nc, items) -> list[list]:
    """The items grouped by the island of the net each belongs to now."""
    where = {}
    for n, isl in enumerate(r.copper(nc)):
        for _, o in isl:
            where[o.m_Uuid.AsString()] = n
    groups = collections.defaultdict(list)
    for k, o in items:
        if o.m_Uuid.AsString() in where:
            groups[where[o.m_Uuid.AsString()]].append((k, o))
    return list(groups.values())


def _rip(objs) -> list:
    """Remove tracks and vias with the teardrops on them; returns everything removed."""
    gone = {}
    for o in objs:
        for z in fx.teardrops_at(o):
            gone[z.m_Uuid.AsString()] = z
        gone[o.m_Uuid.AsString()] = o
    fx.drop(list(gone.values()))
    dirty()
    return list(gone.values())


def _checker(r):
    def check(created) -> bool:
        return all(
            clear(o.GetNetCode(), o.GetLayer(), o.GetWidth(), [o.GetStart(), o.GetEnd()], r)
            for k, o in created
            if k == "track"
        ) and all(_via_clear(o) for k, o in created if k == "via")

    return check


def _via_clear(v) -> bool:
    """A new via keeps the board's clearances on the outer layers and from other holes."""
    p, nc, cl = v.GetPosition(), v.GetNetCode(), int(CLEAR * NM)
    others = [o for o in fx.B.GetTracks() if o.GetNetCode() != nc]
    pads = [q for f in fx.B.GetFootprints() for q in f.Pads() if q.GetNetCode() != nc]
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        shape = v.GetEffectiveShape(layer)
        near = [o for o in others if o.GetClass() == "PCB_VIA" or o.GetLayer() == layer]
        near += [q for q in pads if q.IsOnLayer(layer)]
        if any(o.GetEffectiveShape(layer).Collide(shape, cl) for o in near):
            return False
    gap = 0.2 * NM + v.GetDrillValue() / 2
    return not any(
        o.GetClass() == "PCB_VIA"
        and not same(o, v)
        and (o.GetPosition() - p).EuclideanNorm() < gap + o.GetDrillValue() / 2
        for o in fx.B.GetTracks()
    )


def reroute(r) -> list:
    """Each off connection in turn: ripped up and routed again between the same copper; put back
    as it was when the router cannot route it (the dogleg step takes its off segments)."""
    conns = connections(rip_plan())
    keys = {}
    for n, c in enumerate(conns):
        w = _width(c)
        keys[n] = (w > 0.15, c["tracks"][0].GetNetname() in POWER, -sum(t.GetLength() for t in c["tracks"]), w)
    check = _checker(r)
    failed = []
    for n in sorted(keys, key=lambda n: keys[n][:3]):
        c = conns[n]
        net, w = c["tracks"][0].GetNet(), keys[n][3]
        start = cp(c["tracks"][0].GetStart())
        box = _bbox([o for t in c["tracks"] for o in (t.GetStart(), t.GetEnd())])
        removed = _rip(c["tracks"] + c["vias"])
        before = _unconnected(box)
        for hard in (False, True):
            ok = _route(r, c, net, w, check, box, before, hard)
            if ok:
                break
        print(f"  {net.GetNetname()} {w} mm: {'routed' if ok else 'failed'}", flush=True)
        if not ok:
            for o in removed:
                fx.B.Add(o)
            dirty()
            _unconnected(box)
            failed.append(f"{net.GetNetname()} {w} mm at {start.x / NM:.2f}, {start.y / NM:.2f}")
    return failed


def _route(r, c, net, w, check, box, before, hard) -> bool:
    """Route a ripped connection; with hard, other nets' pours are obstacles (a route across one
    may cut it in two). False, with the new copper removed, when it cannot."""
    r.hard_pours = hard
    try:
        made, joins = [], 0
        while True:
            groups = _groups(r, net.GetNetCode(), list(c["terms"].values()) + made)
            if len(groups) < 2:
                break
            groups.sort(key=len)
            out = None
            for k, src in enumerate(groups):
                tgt = [it for m, g in enumerate(groups) if m != k for it in g]
                out = r.join(net, w, src, tgt, clr=0.1 if w <= 0.15 else router.CLR, check=check)
                if out is not None:
                    break
            if out is None:
                break
            dirty()
            made += r.created
            joins += 1
        ok = len(groups) < 2
        # no long way round: at most DETOUR times the ripped copper's length, plus 3 mm
        old = sum(t.GetLength() for t in c["tracks"])
        new = sum(o.GetLength() for k, o in made if k == "track")
        if ok and new > DETOUR * old + 3 * NM:
            ok = False
        # a route across another net's pour may cut it in two: then the board has more unconnected
        # items than the joins account for
        if ok and joins:
            box = _bbox([box[0], box[1], *[e for k, o in made if k == "track" for e in (o.GetStart(), o.GetEnd())]])
            ok = _unconnected(box) <= before - joins
        if not ok:
            fx.drop([o for _, o in made])
            dirty()
            _unconnected(box)  # the pours flow back where the route was
        return ok
    finally:
        r.hard_pours = False


def _bbox(pts) -> tuple:
    xs, ys = [p.x for p in pts], [p.y for p in pts]
    return pcbnew.VECTOR2I(min(xs), min(ys)), pcbnew.VECTOR2I(max(xs), max(ys))


def _unconnected(box) -> int:
    """The board's unconnected items, with the pours within 3 mm of box refilled first."""
    g = 3 * NM
    zones = [
        z
        for z in fx.B.Zones()
        if not z.GetIsRuleArea()
        and (bb := z.GetBoundingBox()).GetLeft() <= box[1].x + g
        and bb.GetRight() >= box[0].x - g
        and bb.GetTop() <= box[1].y + g
        and bb.GetBottom() >= box[0].y - g
    ]
    pcbnew.ZONE_FILLER(fx.B).Fill(zones)
    fx.B.BuildConnectivity()
    return fx.B.GetConnectivity().GetUnconnectedCount(False)


# --- dogleg: what the router cannot replace -----------------------------------------------------------


def _step(a, b):
    """The octilinear unit step (dx, dy) from a to b, if a-b is octilinear."""
    dx, dy = b.x - a.x, b.y - a.y
    if (dx == 0 and dy == 0) or miss(a, b) > TOL:
        return None
    return (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)


def _arms(p, layer, nc, skip):
    """Unit steps (dx, dy) leaving p along the other segments of the net ending there."""
    out = []
    for o in segs():
        if (skip is not None and same(o, skip)) or o.GetNetCode() != nc or o.GetLayer() != layer:
            continue
        if o.GetStart() == p:
            out.append((o, o.GetEnd(), True))
        elif o.GetEnd() == p:
            out.append((o, o.GetStart(), False))
    return out


def _square(u, arms_from_p) -> bool:
    """A segment leaving p along u keeps 90 degrees or more to every arm there."""
    return all(u[0] * s[0] + u[1] * s[1] <= 0 for s in arms_from_p)


def dogleg(r) -> list:
    """Each off segment left: its corner slides along the track before it (one straight segment
    again), or it becomes two segments, straight and 45 degrees, between the same ends."""
    left = []
    for t in segs():
        if not is_off(t):
            continue
        nc, layer = t.GetNetCode(), t.GetLayer()
        p, q = cp(t.GetStart()), cp(t.GetEnd())
        done = False
        # a free corner (one other octilinear track, no pad or via) slides along that track
        for a, b, set_start in ((p, q, True), (q, p, False)):
            arms = _arms(a, layer, nc, t)
            if len(arms) != 1 or pads_at(a, layer, nc) or via_at(a, nc, tol=230_000):
                continue
            o, far, o_starts_here = arms[0]
            wv = _step(a, far)
            if wv is None:
                continue
            for k in range(8):
                u = UNITS[k]
                cr = wv[0] * u[1] - wv[1] * u[0]
                if cr == 0:
                    continue
                s = ((b.x - a.x) * u[1] - (b.y - a.y) * u[0]) / cr
                a2 = pcbnew.VECTOR2I(round(a.x + s * wv[0]), round(a.y + s * wv[1]))
                if _step(far, a2) != (-wv[0], -wv[1]) or _step(a2, b) is None:
                    continue  # the track before would vanish or turn back
                if not _square(_step(a2, b), [wv]):
                    continue
                if not clear(nc, layer, t.GetWidth(), [far, a2, b], r):
                    continue
                (o.SetStart if o_starts_here else o.SetEnd)(a2)
                (t.SetStart if set_start else t.SetEnd)(a2)
                done = True
                break
            if done:
                break
        if done:
            continue
        # two segments: the straight part first or the 45 degree part first
        dx, dy = q.x - p.x, q.y - p.y
        sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
        if abs(dx) > abs(dy):
            straight, diag = pcbnew.VECTOR2I(dx - sx * abs(dy), 0), pcbnew.VECTOR2I(sx * abs(dy), dy)
        else:
            straight, diag = pcbnew.VECTOR2I(0, dy - sy * abs(dx)), pcbnew.VECTOR2I(dx, sy * abs(dx))
        arms_p = [_step(p, f) for _, f, _ in _arms(p, layer, nc, t)]
        arms_q = [_step(q, f) for _, f, _ in _arms(q, layer, nc, t)]
        free_p = bool(pads_at(p, layer, nc) or via_at(p, nc, tol=230_000))
        free_q = bool(pads_at(q, layer, nc) or via_at(q, nc, tol=230_000))
        best = None
        for first in (straight, diag):
            k = p + first
            u1, u2 = _step(p, k), _step(k, q)
            if u1 is None or u2 is None:
                continue
            ok_p = free_p or (None not in arms_p and _square(u1, arms_p))
            ok_q = free_q or (None not in arms_q and _square((-u2[0], -u2[1]), arms_q))
            if not (ok_p and ok_q) or not clear(nc, layer, t.GetWidth(), [p, k, q], r):
                continue
            # prefer the corner that continues the track before it
            score = -sum(1 for s in arms_p if s == (-u1[0], -u1[1])) - sum(1 for s in arms_q if s == u2)
            if best is None or score < best[0]:
                best = (score, k)
        if best is None:
            left.append(f"{t.GetNetname()} {fx.B.GetLayerName(layer)} ({p.x / NM:.3f}, {p.y / NM:.3f})")
            continue
        t.SetEnd(best[1])
        new_track(t.GetNet(), layer, t.GetWidth(), best[1], q)
    return left


def _octi_paths(p, q):
    """Octilinear paths from p to q (VECTOR2I): two segments (straight then 45 degrees, or the
    other way round), then three (the 45 degree part between two straight parts, or the other
    way round, split at a quarter, half and three quarters)."""
    dx, dy = q.x - p.x, q.y - p.y
    sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
    if abs(dx) >= abs(dy):
        straight, diag = pcbnew.VECTOR2I(dx - sx * abs(dy), 0), pcbnew.VECTOR2I(sx * abs(dy), dy)
    else:
        straight, diag = pcbnew.VECTOR2I(0, dy - sy * abs(dx)), pcbnew.VECTOR2I(dx, sy * abs(dx))
    out = [[p, p + straight, q], [p, p + diag, q]]
    for f in (0.5, 0.25, 0.75):
        s1 = pcbnew.VECTOR2I(round(straight.x * f), round(straight.y * f))
        k = round(abs(diag.x) * f)
        d1 = pcbnew.VECTOR2I(k * ((diag.x > 0) - (diag.x < 0)), k * ((diag.y > 0) - (diag.y < 0)))
        out.append([p, p + s1, p + s1 + diag, q])
        out.append([p, p + d1, p + d1 + straight, q])
    return [[a for k, a in enumerate(path) if k == 0 or a != path[k - 1]] for path in out]


def chain_dogleg(r) -> list:
    """Each chain of off segments left (through bare joints) becomes the first clear octilinear
    path of two or three segments between the chain's ends (a pad end may move to the pad's
    centre)."""
    left = []
    for ch in chains():
        offs = [t for t in ch if is_off(t)]
        if not offs:
            continue
        first, last = ch[0], ch[-1]
        nc, layer, width = first.GetNetCode(), first.GetLayer(), max(t.GetWidth() for t in ch)
        # the chain's two ends, in order
        a = first.GetStart() if len(ch) == 1 or first.GetEnd() in (ch[1].GetStart(), ch[1].GetEnd()) else first.GetEnd()
        b = (
            last.GetEnd()
            if len(ch) == 1 or last.GetStart() in (ch[-2].GetStart(), ch[-2].GetEnd())
            else last.GetStart()
        )
        a, b = cp(a), cp(b)
        ends = []
        for e in (a, b):
            pads = pads_at(e, layer, nc)
            ends.append([e] + ([cp(pads[0].GetPosition())] if pads and pads[0].GetPosition() != e else []))
        skip = {x.m_Uuid.AsString() for x in ch}
        arms = [
            [_step(e, f) for o, f, _ in _arms(e, layer, nc, first) if o.m_Uuid.AsString() not in skip] for e in (a, b)
        ]
        free_end = [bool(pads_at(e, layer, nc) or via_at(e, nc, tol=230_000)) for e in (a, b)]
        done = False
        for pa in ends[0]:
            for pb in ends[1]:
                for path in _octi_paths(pa, pb):
                    steps = [_step(u, v) for u, v in itertools.pairwise(path)]
                    if None in steps:
                        continue
                    if any(_turn(s1, s2) > 2 for s1, s2 in itertools.pairwise(steps)):
                        continue
                    if not free_end[0] and (None in arms[0] or not _square(steps[0], arms[0])):
                        continue
                    if not free_end[1] and (None in arms[1] or not _square((-steps[-1][0], -steps[-1][1]), arms[1])):
                        continue
                    if not clear(nc, layer, width, path, r):
                        continue
                    net = first.GetNet()
                    fx.remove(ch)
                    for u, v in itertools.pairwise(path):
                        new_track(net, layer, width, u, v)
                    done = True
                    break
                if done:
                    break
            if done:
                break
        if not done:
            left.append(f"{first.GetNetname()} {fx.B.GetLayerName(layer)} ({a.x / NM:.3f}, {a.y / NM:.3f})")
    return left


def _turn(s1, s2) -> int:
    """Turn between two unit steps, in 45 degree units (0: straight on, 4: back)."""
    k1, k2 = UNITS.index(s1), UNITS.index(s2)
    d = (k2 - k1) % 8
    return min(d, 8 - d)


# --- corners --------------------------------------------------------------------------------------------


def acute() -> list:
    """Corners below 90 degrees between segments of a net ending at one point outside pads and vias,
    as tests/test_layout.py finds them: (point, layer, net, [(segment, far end)])."""
    ends = collections.defaultdict(list)
    for t in segs():
        if t.GetStart() == t.GetEnd():
            continue
        for a, b in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
            ends[(a.x, a.y, t.GetLayer(), t.GetNetCode())].append((t, b))
    out = []
    for (x, y, layer, nc), arms in ends.items():
        p = pcbnew.VECTOR2I(x, y)
        if len(arms) < 2 or pads_at(p, layer, nc) or via_at(p, nc, tol=230_000):
            continue
        for (_, b1), (_, b2) in itertools.combinations(arms, 2):
            u = (b1.x - x, b1.y - y)
            v = (b2.x - x, b2.y - y)
            cos = (u[0] * v[0] + u[1] * v[1]) / (math.hypot(*u) * math.hypot(*v))
            if math.degrees(math.acos(max(-1.0, min(1.0, cos)))) < 89.9:
                out.append((p, layer, nc, arms))
                break
    return out


# Wall_Sensor_0's fork left of IC1 (F.Cu): from W1 pad 4 the track turns 45 degrees towards IC1 at
# (129.439, 79.890), where the branch to R14 pad 2 goes on straight, 45 degrees from it
WALL0_BRANCH = ["cbda8e00", "b09d2b84"]  # (129.439, 79.890) -> (130.986, 79.890) -> R14 pad 2


def corners(r) -> None:
    """The branch to R14 joins the diagonal square to it instead (the router's T join)."""
    fx.remove(fx.items(WALL0_BRANCH))
    net = fx.B.FindNet("Wall_Sensor_0")
    island = next(
        isl
        for isl in r.copper(net.GetNetCode())
        if not any(
            o.GetParentFootprint() and o.GetParentFootprint().GetReference() == "R14" for k, o in isl if k == "pad"
        )
    )
    r14 = [("pad", fx.pad("R14", "2"))]
    if r.join(net, 0.254, r14, island) is None:
        raise SystemExit("Wall_Sensor_0: no square join from R14 pad 2")


def cleanup() -> None:
    """Zero-length segments, vias that join nothing on a second layer (a route that now stays on
    one layer passes their spot), and teardrops whose fill touches nothing of their net any more
    (finish.py's rule)."""
    fx.remove([t for t in segs() if t.GetStart() == t.GetEnd()])
    dirty()
    lone_vias = []
    for v in fx.B.GetTracks():
        if v.GetClass() != "PCB_VIA" or in_pour(v):
            continue
        r = v.GetWidth(pcbnew.F_Cu) // 2
        layers = {
            layer
            for layer in COPPER
            for x in _touching(v, v.GetPosition(), layer, r)
            if x.GetClass() != "PCB_VIA" and (x.GetClass() != "PCB_TRACK" or x.GetLayer() == layer)
        }
        if len(layers) < 2 and not _acute_at(v.GetPosition(), v.GetNetCode()):
            lone_vias.append(v)
    fx.remove(lone_vias)
    dirty()
    pcbnew.ZONE_FILLER(fx.B).Fill(fx.B.Zones())
    # a teardrop joins a track or via to what it sits on: one that reaches no track or via of its
    # net (its track rerouted) goes
    lone = []
    for z in fx.B.Zones():
        if z.GetIsRuleArea() or not _teardrop(z):
            continue
        reached = False
        for lay in COPPER:
            if not z.IsOnLayer(lay):
                continue
            fill = z.GetFilledPolysList(lay)
            for o in fx.B.GetTracks():
                if o.GetNetCode() != z.GetNetCode():
                    continue
                if o.GetClass() == "PCB_VIA":
                    reached |= fill.Collide(o.GetPosition(), o.GetWidth(lay) // 2)
                elif o.GetLayer() == lay:
                    reached |= fill.Collide(pcbnew.SEG(o.GetStart(), o.GetEnd()), o.GetWidth() // 2)
        if not reached:
            lone.append(z)
    fx.drop(lone)
    dirty()


def _acute_at(p, nc) -> bool:
    """Tracks of the net ending at p would meet at under 90 degrees without a via there."""
    for layer in COPPER:
        arms = [_unit_nm(p, f) for o, f, _ in _arms(p, layer, nc, None)]
        if any(a[0] * b[0] + a[1] * b[1] > 0.02 for a, b in itertools.combinations(arms, 2)):
            return True
    return False


def _unit_nm(a, b):
    d = math.hypot(b.x - a.x, b.y - a.y)
    return ((b.x - a.x) / d, (b.y - a.y) / d)


def summary() -> str:
    ts = segs()
    off = [t for t in ts if is_off(t)]
    vias = sum(1 for t in fx.B.GetTracks() if t.GetClass() == "PCB_VIA")
    arcs = sum(1 for t in fx.B.GetTracks() if t.GetClass() == "PCB_ARC")
    return (
        f"{len(ts)} segments, {sum(t.GetLength() for t in ts) / NM:.1f} mm; off 45: {len(off)}, "
        f"{sum(t.GetLength() for t in off) / NM:.1f} mm; arcs {arcs}; vias {vias}; acute corners {len(acute())}"
    )


# --- run ------------------------------------------------------------------------------------------------


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    src, dst = (Path(args[0]), Path(args[1])) if args else (LAYOUT, LAYOUT)
    fx.B = pcbnew.LoadBoard(str(src))
    print("before:", summary())
    r = router.Router(fx.B)
    print("snap:", snap(r))
    print("slide:", slide(r))
    failed = reroute(r)
    print("reroute: router could not join", failed)
    left = dogleg(r)
    print("dogleg: left", left)
    cleanup()
    left = chain_dogleg(r)
    print("chain dogleg: left", left)
    corners(r)
    cleanup()
    print("after:", summary())
    pcbnew.SaveBoard(str(dst), fx.B)
    if dst == LAYOUT and "--no-sync" not in sys.argv:
        tl.pcb_layout()
    return 1 if left or acute() else 0


if __name__ == "__main__":
    sys.exit(main())
