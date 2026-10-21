"""Planes, plane vias and routing of the second main board, on the placement place.py leaves.

    /usr/bin/python3 boards/main2/layout/route.py      # KiCad's Python (pcbnew), from the repo root

Starts from the placed board: every track, via and board-level pour is removed first, so a rerun
gives the same copper. Stackup (boards/main2/main2.zen): F.Cu and B.Cu 1 oz, In1.Cu and In2.Cu
0.5 oz.

- In1.Cu and In2.Cu: ground planes over the whole board, so a track on either outer layer has an
  unbroken ground plane next to it for its return current (F.Cu over In1.Cu, B.Cu over In2.Cu);
  In2.Cu but for the STM32's supplies under and round it, 3V3_D inside VCORE.
- B.Cu: VBAT pours over the power entry and the two bridges with their bulk capacitors (no other
  net's track runs there), the lowest-priority ground pour everywhere else.
- F.Cu: the ground pour over what the tracks leave.
- Exposed pads on ground get thermal vias, and the ground pins facing them join them; every other
  pad over a plane or pour of its own net (GND, VBAT, the STM32's 3V3_D and VCORE) gets a via to
  it, on the nearest clear spot off the fine-pitch pins' rows.
- The STM32's pins leave first, straight out along their axes to staggered escape vias (signals,
  3V3_D, VCORE) or stubs (its ROUTES pins), before any other part's via takes the room; the
  bridges' logic pins drop to B.Cu the same way, past the pour's edge.
- `ROUTES`: the power paths, wide, by router.py (boards/main/layout), which draws octilinear
  tracks at one width: a pin narrower than its path leaves by a stub of its own width first, and
  each track is widened back where it has the room. They are locked, and Freerouting
  (versions.env) routes every other net round them through a Specctra session, on F.Cu and B.Cu
  only (the inner layers go to it as planes).
- KiCad's DRC, under the layout's rules, checks the result: the tracks in an error are removed
  and router.py routes their nets again, narrower, with whatever Freerouting left unconnected.

The ESP32-S3-MINI-1's antenna keep-out (its footprint's rule area) is fenced with temporary
copper while router.py runs, which does not read rule areas; Freerouting reads it as a keep-out.
"""

from __future__ import annotations

import itertools
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "boards/main/layout"))
import router  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
from micras_pcb import nets, tools  # noqa: E402

PCB = HERE / "main2.kicad_pcb"
OX, OY = 148.5011, 113.5036  # spec/main2.toml [kicad]
B: pcbnew.BOARD = None
F, BK, IN1, IN2 = pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu
LAYERS = {"F": F, "B": BK, "In1": IN1, "In2": IN2}
VIA_D, VIA_HOLE = 0.45, 0.3
# the signals' via in Freerouting (boards/main2/main2.zen): between the STM32's 0.4 mm pitch pins
ESCAPE_D, ESCAPE_HOLE = 0.35, 0.2
CU_GAP = 0.2  # via to other copper on the outer layers


def mm(v: float) -> int:
    return pcbnew.FromMM(v)


def pt(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x), mm(y))


def xy(p) -> tuple[float, float]:
    return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)


def robot(x: float, y: float) -> tuple[float, float]:
    """Robot frame (x forward, y left) to KiCad."""
    return OX - y, OY - x


def net(name: str) -> pcbnew.NETINFO_ITEM:
    n = B.FindNet(name)
    if n is None:
        raise SystemExit(f"no net {name}")
    return n


GRAVE: list = []  # what remove() took off the board: pcbnew frees an item Python lets go of twice


def remove(item) -> None:
    B.Remove(item)
    GRAVE.append(item)


def track(netname: str, layer: str, width: float, a, b) -> pcbnew.PCB_TRACK:
    t = pcbnew.PCB_TRACK(B)
    t.SetStart(pt(*a))
    t.SetEnd(pt(*b))
    t.SetWidth(mm(width))
    t.SetLayer(LAYERS[layer])
    t.SetNet(net(netname))
    B.Add(t)
    return t


def via(netname: str, x: float, y: float, d: float = VIA_D, hole: float = VIA_HOLE) -> pcbnew.PCB_VIA:
    v = pcbnew.PCB_VIA(B)
    v.SetPosition(pt(x, y))
    v.SetWidth(mm(d))
    v.SetDrill(mm(hole))
    v.SetLayerPair(F, BK)
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetNet(net(netname))
    v.SetFrontTentingMode(pcbnew.TENTING_MODE_TENTED)
    v.SetBackTentingMode(pcbnew.TENTING_MODE_TENTED)
    B.Add(v)
    return v


def zone(netname: str, layer: str, pts: list, priority: int) -> None:
    """A solid pour (robot-frame corners): 0.2 mm clearance, 0.25 mm minimum width, pads joined
    solid, islands removed."""
    z = pcbnew.ZONE(B)
    z.SetLayer(LAYERS[layer])
    z.SetNet(net(netname))
    o = z.Outline()
    o.NewOutline()
    for p in pts:
        o.Append(*(mm(v) for v in robot(*p)))
    z.SetAssignedPriority(priority)
    z.SetLocalClearance(mm(0.2))
    z.SetMinThickness(mm(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    B.Add(z)


def rect(x0, x1, y0, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


# ---------------------------------------------------------------------------------------------
# planes

BOARD = rect(-47.0, 54.0, -25.5, 25.5)  # the outline clips every pour

# B.Cu VBAT: the battery input (R59, D14, rear right) and the middle, under both bridges and the
# capacitors behind them (C82-C84, C88, C91, C97): the bridges' supply loop (VM, the bottom pin
# rows) closes there. It stops at the bridges' logic pins (x > -8.6): their tracks drop to B.Cu
# there and pass under the OUT1 paths, and B.Cu ahead stays the IMU's and the encoders'. The other
# bulk capacitors (place.py BULK: C85, C86, C92 at the rear, C87, C93-C96, C111, C112 along the fan
# hole) take VBAT by track
VBAT_POUR = [
    (-8.6, 13.0),  # the middle: bridges, capacitors (x -24.5..-8.6, y -12.5..13)
    (-24.5, 13.0),
    (-24.5, -5.0),
    (-30.5, -5.0),  # D14, C95 (x -30.5..-24.5, y -11..-5)
    (-30.5, -11.0),
    (-28.0, -11.0),
    (-28.0, -19.5),  # R59, D14 (x -28..-17, y -19.5..-11)
    (-17.0, -19.5),
    (-17.0, -12.5),
    (-8.6, -12.5),
]


# In2.Cu round the STM32 (IC1): its 3V3_D pins alternate with its VCORE pins on all four sides, and
# the two nets, as tracks, would ring it on both outer layers and leave its 0.4 mm pitch pins no way
# out. On In2 they nest instead: 3V3_D under the chip and out past its pin tips, VCORE round that
# (under the capacitors round the chip); each pin's via, at its tip, lands in its own (owner,
# 2026-10-18: In2 is ground everywhere else, as on the previous board's power layer)
MCU = "IC1"
MCU_3V3 = 0.8  # mm past the pin tips: a via at each 3V3_D pin's tip
MCU_VCORE = 3.0  # mm past that: VCORE's ring
FANOUT_MAX_OF = {MCU: 2.0}  # a VCORE pin's via, past the 3V3_D island


def pin_square(ref: str, grow: float) -> list:
    """Robot-frame corners of the square round ref's pins, turned with it, grown by grow mm."""
    f = B.FindFootprintByReference(ref)
    (cx, cy), a = xy(f.GetPosition()), math.radians(f.GetOrientationDegrees())
    ca, sa = math.cos(a), math.sin(a)
    h = 0.0
    for p in f.Pads():
        poly = p.GetEffectivePolygon(F)
        for i in range(poly.OutlineCount()):
            o = poly.Outline(i)
            for k in range(o.PointCount()):
                x, y = pcbnew.ToMM(o.CPoint(k).x) - cx, pcbnew.ToMM(o.CPoint(k).y) - cy
                h = max(h, abs(x * ca - y * sa), abs(x * sa + y * ca))
    h += grow
    corners = [(u * h, v * h) for u, v in ((1, 1), (1, -1), (-1, -1), (-1, 1))]
    return [(OY - (cy - u * sa + v * ca), OX - (cx + u * ca + v * sa)) for u, v in corners]


def planes() -> None:
    zone("GND", "In1", BOARD, 0)
    zone("GND", "In2", BOARD, 0)
    zone("VCORE", "In2", pin_square(MCU, MCU_3V3 + MCU_VCORE), 1)
    zone("3V3_D", "In2", pin_square(MCU, MCU_3V3), 2)
    zone("VBAT", "B", VBAT_POUR, 1)


def pours() -> None:
    """The outer-layer ground pours, after the routing: they fill what the tracks leave."""
    zone("GND", "F", BOARD, 0)
    zone("GND", "B", BOARD, 0)


# ---------------------------------------------------------------------------------------------
# plane vias

_outline = None


def board_outline() -> pcbnew.SHAPE_POLY_SET:
    global _outline
    if _outline is None:
        _outline = pcbnew.SHAPE_POLY_SET()
        B.GetBoardPolygonOutlines(_outline, True)
    return _outline


_edges = None


def edge_segments() -> list:
    global _edges
    if _edges is None:
        o = board_outline()
        chains = [o.Outline(0)] + [o.Hole(0, h) for h in range(o.HoleCount(0))]
        _edges = [ch.CSegment(i) for ch in chains for i in range(ch.SegmentCount())]
    return _edges


def near(items, c, r):
    out = []
    for i in items:
        bb = i.GetBoundingBox()
        x0, y0 = xy(bb.GetOrigin())
        x1, y1 = xy(bb.GetEnd())
        if x0 - r <= c[0] <= x1 + r and y0 - r <= c[1] <= y1 + r:
            out.append(i)
    return out


KEEPOUTS: list[pcbnew.SHAPE_POLY_SET] = []  # footprints' rule areas (the antenna's)


def via_spot_ok(c, netname: str, own_pad, seg_from, plane, w: float = 0.3) -> bool:
    """A through via of `netname` at c, and a fan-out track to it from seg_from, clear of every
    other net on the outer layers, of the holes, the edge and the keep-outs, on its plane."""
    centre = pt(*c)
    if not board_outline().Contains(centre, -1, 0):
        return False
    if any(s.Distance(centre) < mm(VIA_D / 2 + 0.25) for s in edge_segments()):
        return False
    if any(k.Collide(centre, mm(VIA_D / 2 + 0.1)) for k in KEEPOUTS):
        return False
    circle = pcbnew.SHAPE_CIRCLE(centre, mm(VIA_D / 2))
    seg = pcbnew.SHAPE_SEGMENT(pt(*seg_from), centre, mm(w))  # the fan-out track
    for f in near(B.GetFootprints(), c, 3.0):
        for p in near(f.Pads(), c, 2.0):
            same = p.GetNetname() == netname
            if p.HasHole():
                hd = pcbnew.ToMM(max(p.GetDrillSize().x, p.GetDrillSize().y))
                if math.dist(xy(p.GetPosition()), c) < hd / 2 + VIA_HOLE / 2 + 0.45:
                    return False
            for layer in (F, BK):
                if not p.IsOnLayer(layer):
                    continue
                shape = p.GetEffectiveShape(layer)
                if p is own_pad:
                    if shape.Collide(circle, mm(0.05)):
                        return False
                    continue
                if shape.Collide(circle, mm(0.1 if same else CU_GAP)):
                    return False
                if layer == F and not same and shape.Collide(seg, mm(SIGNAL_CLR)):
                    return False
    for t in near(B.GetTracks(), c, 2.0):
        same = t.GetNetname() == netname
        if t.GetClass() == "PCB_VIA":
            if math.dist(xy(t.GetPosition()), c) < VIA_D + 0.2:
                return False
            continue
        if same:
            continue
        if t.GetEffectiveShape(t.GetLayer()).Collide(circle, mm(CU_GAP)):
            return False
        if t.GetLayer() == F and t.GetEffectiveShape(F).Collide(seg, mm(0.12)):
            return False
    # the via's whole pad over its own plane: an island's edge is another net's island
    return _on_plane(c, VIA_D, *plane)


def fanout(p: pcbnew.PAD, layer) -> bool:
    """A via next to the pad, on the nearest clear spot over its plane, with a track at a multiple
    of 45 degrees from a point on the pad's long axis: 0.3 mm, or the pad's width if narrower (a
    0.4 mm pitch pin's track runs out between its neighbours')."""
    n = p.GetNetname()
    c0 = xy(p.GetPosition())
    sz = p.GetSize()
    w = min(0.3, pcbnew.ToMM(min(sz.x, sz.y)))
    half = (max(pcbnew.ToMM(sz.x), pcbnew.ToMM(sz.y)) - min(pcbnew.ToMM(sz.x), pcbnew.ToMM(sz.y))) / 2
    a = math.radians(p.GetOrientationDegrees()) + (0 if sz.x >= sz.y else math.pi / 2)
    if p.GetOrientationDegrees() % 90:
        half = 0.0  # a skewed pad: from its centre only
    starts = [
        (round(c0[0] + s * math.cos(a), 3), round(c0[1] - s * math.sin(a), 3))
        for k in range(-int(half / 0.1), int(half / 0.1) + 1)
        for s in [0.1 * k]
    ]
    spots = []
    for s in starts:
        for k in range(8):
            d = (math.cos(k * math.pi / 4), math.sin(k * math.pi / 4))
            r = 0.2
            while r <= FANOUT_MAX_OF.get(p.GetParentFootprint().GetReference(), FANOUT_MAX):
                c = (round(s[0] + r * d[0], 3), round(s[1] + r * d[1], 3))
                spots.append((math.dist(c, c0), s, c))
                r += 0.05
    # a spot beside another net's fine-pitch pin (its row's way out) comes last
    fine = [
        q.GetEffectiveShape(F)
        for g in near(B.GetFootprints(), c0, FANOUT_MAX + 2.0)
        for q in g.Pads()
        if q.GetNetname() != n and q.IsOnLayer(F) and pcbnew.ToMM(min(q.GetSize().x, q.GetSize().y)) < FINE_PIN
    ]
    spots = [(d + (10.0 if any(q.Collide(pt(*c), mm(PIN_ROW)) for q in fine) else 0.0), s, c) for d, s, c in spots]
    for _, s, c in sorted(spots):
        if via_spot_ok(c, n, p, s, (layer, n), w):
            track(n, "F", w, s, c)
            via(n, *c)
            return True
    return False


FINE_PIN = 0.5  # mm: a pad narrower than this is a fine-pitch pin
PIN_ROW = 1.0  # mm round a fine-pitch pin its neighbours' tracks need


PLANE_NETS = {"GND": IN1, "VBAT": BK, "3V3_D": IN2, "VCORE": IN2}
FANOUT_MAX = 1.4  # mm from the pad centre: a longer stub blocks more than it serves
# Parts whose supply pads take a via of their own: chips, transistors, inductors, diodes,
# capacitors, connectors. A resistor's GND pad reaches the outer-layer ground pours; its supply
# pad is routed to the nearest supply copper.
VIA_PARTS = ("IC", "U", "Q", "L", "D", "C", "M", "J", "SW", "BZ")


THERMAL_PITCH = 1.2  # mm between thermal vias (TI SLMA002, PowerPAD: 1.0-1.2 mm, 0.3 mm holes)
THERMAL_EDGE = 0.45  # mm from a via's centre to the exposed pad's edge
# the STM32's exposed pad is its ground, not its heat path (it dissipates well under 1 W): a 3 x 3 grid
# leaves B.Cu under it to the tracks leaving its 68 pins
THERMAL_PITCH_OF = {"IC1": 2.4}


def thermal_vias() -> int:
    """A grid of vias in every exposed pad on GND (the largest pad of a chip or transistor, over
    2 mm2), to the ground planes: the DRV8874s' and STSPIN958's PowerPADs carry their heat out
    this way."""
    n = 0
    for f in B.GetFootprints():
        if not f.GetReference().startswith(("IC", "U", "Q")):
            continue
        for p in f.Pads():
            if p.GetNetname() != "GND" or p.HasHole():
                continue
            bb = p.GetBoundingBox()
            (x0, y0), (x1, y1) = xy(bb.GetOrigin()), xy(bb.GetEnd())
            if (x1 - x0) * (y1 - y0) < 2.0:
                continue
            pitch = THERMAL_PITCH_OF.get(f.GetReference(), THERMAL_PITCH)
            cols = []
            for lo, hi in ((x0, x1), (y0, y1)):
                k = max(1, int((hi - lo - 2 * THERMAL_EDGE) / pitch) + 1)
                step = (hi - lo - 2 * THERMAL_EDGE) / (k - 1) if k > 1 else 0.0
                cols.append([lo + THERMAL_EDGE + i * step if k > 1 else (lo + hi) / 2 for i in range(k)])
            for x in cols[0]:
                for y in cols[1]:
                    if p.HitTest(pt(x, y)):
                        via("GND", round(x, 3), round(y, 3))
                        n += 1
    return n


# (ref, pad): the ground pins ep_ground() joined to their exposed pad, the STM32's pins mcu_escape() led out
TIED: set[tuple[str, str]] = set()


def ep_ground() -> None:
    """Every ground pin of a chip with a ground exposed pad (thermal_vias()) that faces it across
    a short gap joins it, with a track of the pin's width, instead of taking a via at its outer
    end: there, the via would take the room the neighbouring pins leave by (the STM32's 3V3_D
    and VCORE vias, the DRV8874s' charge-pump and control pins)."""
    for f in B.GetFootprints():
        if not f.GetReference().startswith(("IC", "U", "Q")):
            continue
        ep = max(f.Pads(), key=lambda p: p.GetSize().x * p.GetSize().y)
        bb = ep.GetBoundingBox()
        (x0, y0), (x1, y1) = xy(bb.GetOrigin()), xy(bb.GetEnd())
        if ep.GetNetname() != "GND" or (x1 - x0) * (y1 - y0) < 2.0:
            continue
        c = xy(ep.GetPosition())
        for p in f.Pads():
            if p.GetNetname() != "GND" or ep.HitTest(p.GetPosition()):
                continue  # the exposed pad, and the pads on it
            a = xy(p.GetPosition())
            sz = p.GetSize()
            half = pcbnew.ToMM(max(sz.x, sz.y)) / 2
            # inward along the pin, at most REACH past its inner end
            t = math.radians(p.GetOrientationDegrees()) + (0 if sz.x >= sz.y else math.pi / 2)
            u = (math.cos(t), -math.sin(t))
            if u[0] * (c[0] - a[0]) + u[1] * (c[1] - a[1]) < 0:
                u = (-u[0], -u[1])
            k = half
            while k < half + EP_REACH and not ep.HitTest(pt(a[0] + k * u[0], a[1] + k * u[1])):
                k += 0.05
            if k >= half + EP_REACH:
                continue
            b = (round(a[0] + (k + 0.1) * u[0], 3), round(a[1] + (k + 0.1) * u[1], 3))
            track("GND", "F", pcbnew.ToMM(min(sz.x, sz.y)), a, b)
            TIED.add((f.GetReference(), p.GetNumber()))


EP_REACH = 0.6  # mm from a pin's inner end to its exposed pad


# The STM32's escape: each pin leaves straight out along its axis, before any other part's via
# or track takes the room in front of its row, to a 0.35 mm via (main2.zen) on one of three rows
# past the pin tips, staggered so a track out of the far rows passes between the near rows' vias
# (0.4 mm pitch: 0.15 mm from a 0.15 mm track to a via). 3V3_D's vias take the near row, inside
# its In2 island; VCORE's go past the far row, onto its ring; VDDA and SMPS_LX (ROUTES) leave
# by a stub past the rows, for router.py to go on from.
ESCAPE_ROWS = (0.3, 0.65, 1.0)  # mm from the pin tip to the via's centre
ESCAPE_W = 0.15
ESCAPE_REACH = {"3V3_D": (0.3,), "VCORE": (1.35, 1.7, 2.05, 2.4)}
ESCAPE_STUB = 1.6  # mm past the tip: a ROUTES pin's stub, clear of the rows


def _escape_ok(n: str, own, a, c, d: float | None, w: float = ESCAPE_W) -> bool:
    """A track of n from a to c, w wide (and a via of diameter d at c), clear of every other net."""
    centre = pt(*c)
    seg = pcbnew.SHAPE_SEGMENT(pt(*a), centre, mm(w))
    circle = pcbnew.SHAPE_CIRCLE(centre, mm(d / 2)) if d else None
    for f in near(B.GetFootprints(), c, 3.0):
        for p in near(f.Pads(), c, 2.0):
            if p is own or p.GetNetname() == n:
                continue
            if p.HasHole() and math.dist(xy(p.GetPosition()), c) < 1.0:
                return False
            for layer in (F, BK):
                if not p.IsOnLayer(layer):
                    continue
                s = p.GetEffectiveShape(layer)
                if (circle and s.Collide(circle, mm(SIGNAL_CLR))) or (layer == F and s.Collide(seg, mm(SIGNAL_CLR))):
                    return False
    for t in near(B.GetTracks(), c, 2.0):
        if t.GetNetname() == n:
            continue
        if t.GetClass() == "PCB_VIA":
            r = pcbnew.ToMM(t.GetWidth(F)) / 2
            if (d and math.dist(xy(t.GetPosition()), c) < r + d / 2 + SIGNAL_CLR) or seg.Collide(
                pcbnew.SHAPE_CIRCLE(t.GetPosition(), mm(r)), mm(SIGNAL_CLR)
            ):
                return False
            continue
        s = t.GetEffectiveShape(t.GetLayer())
        if (circle and s.Collide(circle, mm(SIGNAL_CLR))) or (t.GetLayer() == F and s.Collide(seg, mm(SIGNAL_CLR))):
            return False
    return True


def _on_plane(c, d: float, layer, netname: str) -> bool:
    """A via of diameter d at c lies wholly on netname's fill on layer."""
    pts = [pt(*c)] + [
        pt(c[0] + d / 2 * math.cos(k * math.pi / 4), c[1] + d / 2 * math.sin(k * math.pi / 4)) for k in range(8)
    ]
    return any(
        z.GetNetname() == netname
        and z.IsOnLayer(layer)
        and not z.GetIsRuleArea()
        and all(z.GetFilledPolysList(layer).Contains(q) for q in pts)
        for z in near(B.Zones(), c, 0.5)
    )


def _axis(p, c0) -> tuple:
    """A pad's centre, half length and its long axis's unit vector, pointing away from c0."""
    a = xy(p.GetPosition())
    sz = p.GetSize()
    half = pcbnew.ToMM(max(sz.x, sz.y)) / 2
    t = math.radians(p.GetOrientationDegrees()) + (0 if sz.x >= sz.y else math.pi / 2)
    u = (math.cos(t), -math.sin(t))
    if u[0] * (a[0] - c0[0]) + u[1] * (a[1] - c0[1]) < 0:
        u = (-u[0], -u[1])
    return a, half, u


def mcu_escape() -> list[str]:
    """The STM32's pins out along their axes (ESCAPE_ROWS); returns the pins left to the routers."""
    pcbnew.ZONE_FILLER(B).Fill(B.Zones())
    f = B.FindFootprintByReference(MCU)
    c0 = xy(f.GetPosition())
    pins: dict[str, int] = {}
    for g in B.GetFootprints():
        for p in g.Pads():
            pins[p.GetNetname()] = pins.get(p.GetNetname(), 0) + 1
    # the supplies first: their rows are fixed, a signal's row is the first free one of the three
    order = {"3V3_D": 0, "VCORE": 0, "VDDA": 0, "SMPS_LX": 0}
    pads = sorted(f.Pads(), key=lambda p: (order.get(p.GetNetname(), 1), int(p.GetNumber())))
    missed, links = [], []
    for p in pads:
        n = p.GetNetname()
        if not n or (MCU, p.GetNumber()) in TIED or pins[n] < 2 or n == "GND":
            continue
        a, half, u = _axis(p, c0)
        out = lambda r: (round(a[0] + (half + r) * u[0], 3), round(a[1] + (half + r) * u[1], 3))  # noqa: E731,B023
        if n in WIDE and n not in PLANE_NETS:
            if _escape_ok(n, p, a, out(ESCAPE_STUB), None):
                track(n, "F", ESCAPE_W, a, out(ESCAPE_STUB))
                TIED.add((MCU, p.GetNumber()))
            else:
                missed.append(f"{p.GetNumber()} {n}")
            continue
        k = int(p.GetNumber()) % len(ESCAPE_ROWS)
        rows = ESCAPE_REACH.get(n, ESCAPE_ROWS[k:] + ESCAPE_ROWS[:k])
        for r in rows:
            c = out(r)
            if _escape_ok(n, p, a, c, ESCAPE_D) and (n not in PLANE_NETS or _on_plane(c, ESCAPE_D, PLANE_NETS[n], n)):
                track(n, "F", ESCAPE_W, a, c)
                via(n, *c, ESCAPE_D, ESCAPE_HOLE)
                TIED.add((MCU, p.GetNumber()))
                break
        else:
            if n in CAP_LINK:
                links.append((n, p, a, out))
            else:
                missed.append(f"{p.GetNumber()} {n}")
    # the capacitor links last: drawn first, a link crossed its neighbouring signal pins' rows and
    # left them no via (SWDIO beside VCAP2, Wall_Sensor_PWM_3 beside VCAP3)
    for n, p, a, out in links:
        if _cap_link(n, p, a, out):
            TIED.add((MCU, p.GetNumber()))
        else:
            missed.append(f"{p.GetNumber()} {n}")
    return missed


# The STM32's fan-out: each signal's escape via goes on out along its pin's axis on B.Cu, past
# the capacitors round the chip, and is locked before Freerouting. Without it the nets whose pins
# face away from their parts (17 of 47: the chip sits in the nose, nearly everything is behind it)
# were routed round the chip through the escape rows, and sealed off the vias of nets not yet
# routed; with it, nothing crosses the escape zone on B.Cu, and each net starts past the ring
FANOUT = 4.0  # mm past the pin tip, at most
FANOUT_MIN = 1.6  # mm: shorter, the track would not clear the far via row (ESCAPE_ROWS)


def _clear_bk(n: str, a, b, w: float) -> bool:
    """A B.Cu track of n from a to b, w wide, clear of every other net's copper and hole, of the
    edge, the keep-outs and the VBAT pour."""
    seg = pcbnew.SHAPE_SEGMENT(pt(*a), pt(*b), mm(w))
    c = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    reach = math.dist(a, b) / 2 + 1.5
    if any(seg.Collide(pcbnew.SHAPE_SEGMENT(e.A, e.B, 0), mm(0.25)) for e in edge_segments()):
        return False
    poly = _pour()[0]
    if any(k.Collide(seg, mm(SIGNAL_CLR)) for k in KEEPOUTS) or poly.Collide(seg, mm(SIGNAL_CLR)):
        return False
    for f in near(B.GetFootprints(), c, reach):
        for p in near(f.Pads(), c, reach):
            if p.GetNetname() == n:
                continue
            if p.HasHole() and p.GetEffectiveHoleShape().Collide(seg, mm(HOLE_TRACK)):
                return False
            if p.IsOnLayer(BK) and p.GetEffectiveShape(BK).Collide(seg, mm(SIGNAL_CLR)):
                return False
    for t in near(B.GetTracks(), c, reach):
        if t.GetNetname() == n:
            continue
        if t.GetClass() == "PCB_VIA":
            if t.GetEffectiveShape(BK).Collide(seg, mm(SIGNAL_CLR)):
                return False
            if seg.Collide(pcbnew.SHAPE_CIRCLE(t.GetPosition(), mm(pcbnew.ToMM(t.GetDrill()) / 2)), mm(HOLE_TRACK)):
                return False
        elif t.GetLayer() == BK and t.GetEffectiveShape(BK).Collide(seg, mm(SIGNAL_CLR)):
            return False
    return True


def mcu_fanout() -> int:
    """The STM32's signals out from their escape vias along their pins' axes on B.Cu (FANOUT), as
    far as each is clear; returns how many."""
    f = B.FindFootprintByReference(MCU)
    c0 = xy(f.GetPosition())
    made = 0
    for p in f.Pads():
        n = p.GetNetname()
        if not n or n in WIDE or n in PLANE_NETS or n == "GND":
            continue
        a, half, u = _axis(p, c0)
        v = next(
            (t for t in near(B.GetTracks(), a, half + 1.5) if t.GetClass() == "PCB_VIA" and t.GetNetname() == n),
            None,
        )
        if v is None:
            continue
        c = xy(v.GetPosition())
        r = FANOUT
        while r >= FANOUT_MIN:
            e = (round(a[0] + (half + r) * u[0], 3), round(a[1] + (half + r) * u[1], 3))
            if _clear_bk(n, c, e, ESCAPE_W):
                track(n, "B", ESCAPE_W, c, e).SetLocked(True)
                made += 1
                break
            r -= 0.25
    return made


CAP_LINK = ("VCORE",)  # supplies whose pin, with no room for its via, joins its capacitor instead
CAP_LINK_MAX = 3.5  # mm from the pin to the capacitor's pad


def _dogleg(m, b) -> list:
    """The octilinear paths from m to b: a diagonal and a straight run, in either order."""
    dx, dy = b[0] - m[0], b[1] - m[1]
    k = min(abs(dx), abs(dy))
    diag = (math.copysign(k, dx), math.copysign(k, dy))
    first = (round(m[0] + diag[0], 3), round(m[1] + diag[1], 3))
    second = (round(b[0] - diag[0], 3), round(b[1] - diag[1], 3))
    return [[m, first, b], [m, second, b]]


def _cap_link(n: str, p: pcbnew.PAD, a, out) -> bool:
    """A supply pin with no room for its via joins the nearest capacitor pad of its net: straight
    out past the neighbouring pins, then octilinear to the pad. The capacitor's own pad reaches
    the plane (plane_vias(), or the routers)."""
    caps = [
        q
        for g in B.GetFootprints()
        if g.GetReference().startswith("C")
        for q in g.Pads()
        if q.GetNetname() == n and math.dist(xy(q.GetPosition()), a) < CAP_LINK_MAX
    ]
    for q in sorted(caps, key=lambda q: math.dist(xy(q.GetPosition()), a)):
        b = xy(q.GetPosition())
        for w in (0.25, 0.2, ESCAPE_W):
            # straight out past the signal pins' via rows (ESCAPE_ROWS) before it turns
            for r in (0.3, 0.6, 0.9, 1.35, 1.7):
                for path in _dogleg(out(r), b):
                    pts = [a, *path]
                    segs = [(u, v) for u, v in itertools.pairwise(pts) if u != v]
                    if all(_escape_ok(n, p, u, v, None, w) and _escape_ok(n, q, v, u, None, w) for u, v in segs):
                        for u, v in segs:
                            track(n, "F", w, u, v)
                        return True
    return False


NECK_MAX = 1.5  # mm past the pin tip


def necks() -> int:
    """A power path's pin narrower than its track, between other nets' pins (a fine-pitch chip's),
    leaves by a stub of its own width straight out past them, for router.py to go on from at the
    path's width: router.py draws a net at one width, and the whole path would fall to FINE."""
    widths = {n: w for n, w, _ in ROUTES if n != "GND"}
    made = 0
    for f in B.GetFootprints():
        c0 = xy(f.GetPosition())
        for p in f.Pads():
            n = p.GetNetname()
            w = widths.get(n)
            minor = pcbnew.ToMM(min(p.GetSize().x, p.GetSize().y))
            if not w or minor >= w or (f.GetReference(), p.GetNumber()) in TIED or not p.IsOnLayer(F):
                continue
            if p.GetOrientationDegrees() % 90 or math.dist(xy(p.GetPosition()), c0) < 0.1:
                continue
            a, half, u = _axis(p, c0)
            out = lambda r: (round(a[0] + (half + r) * u[0], 3), round(a[1] + (half + r) * u[1], 3))  # noqa: E731,B023
            if _escape_ok(n, p, a, out(0.0), None, w):
                continue  # the path's width reaches the pad
            r = 0.05
            while r <= NECK_MAX and _escape_ok(n, p, a, out(r), None, minor):
                if _escape_ok(n, p, out(r), out(r), None, w):
                    track(n, "F", minor, a, out(r))
                    made += 1
                    break
                r += 0.05
    return made


# The bridges' logic pins (DRV8874 1-6: EN, PH, nSLEEP, nFAULT, VREF, IPROPI) face the B.Cu VBAT
# pour on one side and their OUT1 path on F.Cu on the other: each drops to B.Cu by a via just past
# its tip (0.65 mm pitch: one row), before the power paths, which then pass beyond the vias
BRIDGES = ("IC8", "IC9")
BRIDGE_LOGIC = ("1", "2", "3", "4", "5", "6")
BRIDGE_ROWS = (0.4, 0.75)  # mm from the pin tip to the via's centre
# The fan driver's PWM pin (STSPIN958 pin 11) sits between its 3V3_D and GND pins, with C31 just
# past their tips: it drops to B.Cu by a via of its own, the same way
DROPS = {**{ref: (BRIDGE_LOGIC, BRIDGE_ROWS) for ref in BRIDGES}, "IC6": (("11",), (0.35, 0.55, 0.75))}


def bridge_escape() -> list[str]:
    """The bridges' logic pins (and the fan driver's PWM pin) down to B.Cu (DROPS); returns the
    pins left to the routers."""
    missed = []
    for ref, (nums, rows) in DROPS.items():
        f = B.FindFootprintByReference(ref)
        c0 = xy(f.GetPosition())
        for num in nums:
            p = f.FindPadByNumber(num)
            n = p.GetNetname()
            a, half, u = _axis(p, c0)
            for r in rows:
                c = (round(a[0] + (half + r) * u[0], 3), round(a[1] + (half + r) * u[1], 3))
                if _escape_ok(n, p, a, c, ESCAPE_D):
                    track(n, "F", ESCAPE_W, a, c)
                    via(n, *c, ESCAPE_D, ESCAPE_HOLE)
                    TIED.add((ref, num))
                    break
            else:
                missed.append(f"{ref}.{num} {n}")
    return missed


JOINS: list[tuple[str, float, tuple, tuple]] = []  # join_neighbours(): (net, width, a, b)


def join_neighbours() -> int:
    """A chip's neighbouring pins on one net (the fan driver's VS pins, ...) joined pad to pad, by
    a track of the pins' width straight across the gap between them."""
    made = 0
    for f in B.GetFootprints():
        if not f.GetReference().startswith(("IC", "U", "Q")):
            continue
        pads = [p for p in f.Pads() if p.GetNetname() and p.IsOnLayer(F) and not p.HasHole()]
        for i, p in enumerate(pads):
            for q in pads[i + 1 :]:
                if p.GetNetname() != q.GetNetname() or p.GetNetname() in ("GND",):
                    continue
                a, b = xy(p.GetPosition()), xy(q.GetPosition())
                w = pcbnew.ToMM(min(p.GetSize().x, p.GetSize().y, q.GetSize().x, q.GetSize().y))
                if math.dist(a, b) > 0.8 or w >= FINE_PIN:
                    continue
                seg = pcbnew.SHAPE_SEGMENT(pt(*a), pt(*b), mm(w))
                if any(o is not p and o is not q and o.GetEffectiveShape(F).Collide(seg, mm(SIGNAL_CLR)) for o in pads):
                    continue
                track(p.GetNetname(), "F", w, a, b)
                JOINS.append((p.GetNetname(), w, a, b))
                made += 1
    return made


def rejoin() -> int:
    """The joins of join_neighbours() a Freerouting session dropped, back."""
    have = {(t.GetNetname(), xy(t.GetStart()), xy(t.GetEnd())) for t in B.GetTracks() if t.GetLayer() == F}
    made = 0
    for n, w, a, b in JOINS:
        if (n, a, b) not in have and (n, b, a) not in have:
            track(n, "F", w, a, b)
            made += 1
    return made


def plane_vias() -> list[str]:
    pcbnew.ZONE_FILLER(B).Fill(B.Zones())
    missed = []
    # the STM32 first, its VCORE pins before the rest: their vias go furthest out, past 3V3_D's
    fps = sorted(B.GetFootprints(), key=lambda f: f.GetReference() != MCU)
    for f in fps:
        ref = f.GetReference()
        if not ref.startswith(VIA_PARTS) or ref.startswith("GND"):
            continue
        for p in sorted(f.Pads(), key=lambda p: p.GetNetname() != "VCORE"):
            if (ref, p.GetNumber()) in TIED:
                continue  # ep_ground(), mcu_escape()
            layer = PLANE_NETS.get(p.GetNetname())
            if layer is None or not p.IsOnLayer(F) or p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue
            if p.HasHole():
                continue  # a plated hole reaches the planes itself
            if not any(
                z.GetNetname() == p.GetNetname() and z.IsOnLayer(layer) and z.Outline().Contains(p.GetPosition())
                for z in B.Zones()
            ):
                continue  # off its net's pours: routed
            # a pad with a via of its own net already within reach (or in it) shares it
            if any(
                t.GetClass() == "PCB_VIA"
                and t.GetNetname() == p.GetNetname()
                and (math.dist(xy(t.GetPosition()), xy(p.GetPosition())) < 1.0 or p.HitTest(t.GetPosition()))
                for t in near(B.GetTracks(), xy(p.GetPosition()), 1.2)
            ):
                continue
            if not fanout(p, layer):
                missed.append(f"{f.GetReference()}.{p.GetNumber()} {p.GetNetname()}")
    return missed


# ---------------------------------------------------------------------------------------------
# routing

# (net, track width mm, clearance mm or None): the power paths first, then the signals
ROUTES = [
    # the ground pads that took no plane via (a fine-pitch pin beside an exposed pad, a pad boxed
    # in) join the nearest ground copper; Freerouting would only offer them a via of their own
    ("GND", 0.3, None),
    ("BAT_P", 1.0, None),
    ("GND_BAT", 1.0, None),
    *[(f"DRIVERS.MOTOR_{s}_{n}", 0.8, None) for s in "RL" for n in ("OUT1", "OUT2", "SHUNT", "TERMINAL")],
    *[(f"DRIVERS.FAN_{n}", 0.8, None) for n in ("OUT", "MOTOR", "LSS")],
    ("VSYS", 0.5, None),
    ("REGULATORS.BUCK_SW", 0.6, None),
    ("VBAT", 0.6, None),
    ("+5V", 0.4, None),
    ("SENSORS.EMITTER_SINK", 0.4, None),
    ("3V3_A", 0.3, None),
    ("REGULATORS.LDO_IN", 0.3, None),
    ("VCORE", 0.2, None),  # stubs to 0.2 mm pins: its In2 island carries the current
    ("SMPS_LX", 0.3, None),
    ("VDDA", 0.3, None),
]
WIDE = {n for n, *_ in ROUTES}
NARROW = 0.4  # then a power path that cannot keep its width tries this
FINE = 0.12  # and a net that cannot leave a fine-pitch pad at its width this


def keepouts() -> None:
    for f in B.GetFootprints():
        for z in f.Zones():
            if z.GetIsRuleArea():
                KEEPOUTS.append(z.Outline())


def _bar(layer, x0: float, x1: float, y: float) -> pcbnew.PCB_TRACK:
    t = pcbnew.PCB_TRACK(B)
    t.SetStart(pt(x0, y))
    t.SetEnd(pt(x1, y))
    t.SetWidth(mm(0.6))
    t.SetLayer(layer)
    t.SetNet(B.FindNet("ESP.U13.NC_ESP32-S3-MINI-1_IO1"))
    B.Add(t)
    return t


def fence() -> list:
    """Temporary copper over the keep-outs, which the router reads as obstacles."""
    made = []
    for o in KEEPOUTS:
        bb = o.BBox()
        x0, y0 = xy(bb.GetOrigin())
        x1, y1 = xy(bb.GetEnd())
        for layer in (F, BK):
            y = y0
            while y <= y1:
                made.append(_bar(layer, x0, x1, y))
                y += 0.5
    return made


def _pour():
    """The B.Cu VBAT pour's outline, and its bounding box's corners."""
    poly = pcbnew.SHAPE_POLY_SET()
    poly.NewOutline()
    for p in VBAT_POUR:
        poly.Append(*(mm(v) for v in robot(*p)))
    bb = poly.BBox()
    return poly, xy(bb.GetOrigin()), xy(bb.GetEnd())


def _gap(box, a, b, r) -> float:
    """Distance from the rectangle box (x0, y0, x1, y1) to the segment a-b of half-width r."""
    x0, y0, x1, y1 = box
    clamp = lambda q: (min(max(q[0], x0), x1), min(max(q[1], y0), y1))  # noqa: E731

    def seg(p, a, b):
        (ax, ay), (bx, by) = a, b
        d = (bx - ax) ** 2 + (by - ay) ** 2
        t = 0 if d == 0 else max(0, min(1, ((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / d))
        return math.dist(p, (ax + t * (bx - ax), ay + t * (by - ay)))

    def cross():
        # Liang-Barsky: does the segment enter the box?
        t0, t1, (dx, dy) = 0.0, 1.0, (b[0] - a[0], b[1] - a[1])
        for d, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
            if d == 0 and q < 0:
                return False
            if d < 0:
                t0 = max(t0, q / d)
            elif d > 0:
                t1 = min(t1, q / d)
        return t0 <= t1

    if cross():
        return 0
    # apart, the closest pair lies on an end of the segment or a corner of the box
    ends = [math.dist(q, clamp(q)) for q in (a, b)]
    corners = [seg(c, a, b) for c in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
    return max(0, min(ends + corners) - r)


def pour_keepout() -> str:
    """The B.Cu VBAT pour as Specctra keepouts for Freerouting, in strips 0.25 mm high round the
    copper already in it (vias, B.Cu tracks and pads): every other net's track and via stays off
    the pour, and the pour's own copper is no violation. Freerouting has no keepout for tracks
    alone, and reads a pour on a signal layer as no obstacle."""
    poly, (x0, y0), (x1, y1) = _pour()
    step, keep = 0.25, SIGNAL_CLR + 0.01
    items = []
    for t in B.GetTracks():
        a, b = xy(t.GetStart()), xy(t.GetEnd())
        if t.GetClass() == "PCB_VIA":
            items.append((a, a, t.GetWidth(F) / 2e6))
        elif t.GetLayer() == BK:
            items.append((a, b, t.GetWidth() / 2e6))
    for f in B.GetFootprints():
        for p in f.Pads():
            if p.IsOnLayer(BK):
                bb = p.GetBoundingBox()
                (bx0, by0), (bx1, by1) = xy(bb.GetOrigin()), xy(bb.GetEnd())
                r = min(bx1 - bx0, by1 - by0) / 2
                c = ((bx0 + bx1) / 2, (by0 + by1) / 2)
                h = (max(0, (bx1 - bx0) / 2 - r), max(0, (by1 - by0) / 2 - r))
                items.append(((c[0] - h[0], c[1] - h[1]), (c[0] + h[0], c[1] + h[1]), r))
    items = [i for i in items if x0 - 1 < i[0][0] < x1 + 1 and y0 - 1 < i[0][1] < y1 + 1]
    um = lambda v: round(v * 1000)  # noqa: E731
    out = []
    y = y0
    while y < y1:
        run = None
        for k in range(int((x1 - x0) / step) + 1):
            box = (x0 + step * k, y, x0 + step * (k + 1), y + step)
            ok = all(poly.Contains(pt(cx, cy)) for cx in box[::2] for cy in box[1::2])
            ok = ok and all(_gap(box, *i) >= keep for i in items)
            if ok:
                run = (run or box)[:2] + box[2:]
            if run and (not ok or k == int((x1 - x0) / step)):
                out.append(f'(keepout "vbat" (rect B.Cu {um(run[0])} {-um(run[3])} {um(run[2])} {-um(run[1])}))')
                run = None
        y += step
    return "\n    ".join(out)


def pour_fence() -> list:
    """Temporary copper over the B.Cu VBAT pour, kept 0.3 mm inside it: no other net's track
    crosses the pour, nor its via."""
    poly, (x0, y0), (x1, y1) = _pour()

    def inside(x, y):
        return all(poly.Contains(pt(x + dx, y + dy)) for dx, dy in ((0, 0), (-0.3, 0), (0.3, 0), (0, -0.3), (0, 0.3)))

    made = []
    y = y0 + 0.3
    while y <= y1 - 0.3:
        run = None
        for k in range(int((x1 - x0) / 0.1) + 2):
            x = x0 + 0.1 * k
            if inside(x, y):
                run = (run or (x, x))[0], x
            elif run:
                made.append(_bar(BK, *run, y))
                run = None
        y += 0.5
    return made


def _halo(name: str, clr: float) -> list:
    """Temporary copper over the tracks of the other kind (the switching nodes' for an analog net,
    the analog nets' for a switching node), wide enough that a route clr from it keeps ANALOG_GAP
    from them; but for the tracks off a pin of the net's own parts (a bridge's VREF pin beside its
    OUT pins), which would cover the pin."""
    other = nets.SWITCHING if name in nets.ANALOG else nets.ANALOG if name in nets.SWITCHING else set()
    made = []
    if not other:
        return made
    own = [p for f in B.GetFootprints() if any(q.GetNetname() == name for q in f.Pads()) for p in f.Pads()]
    for t in list(B.GetTracks()):
        if t.GetClass() == "PCB_TRACK" and t.GetNetname() in other:
            if any(p.HitTest(e) for p in own for e in (t.GetStart(), t.GetEnd())):
                continue
            h = pcbnew.PCB_TRACK(B)
            h.SetStart(t.GetStart())
            h.SetEnd(t.GetEnd())
            h.SetWidth(t.GetWidth() + mm(2 * (nets.ANALOG_GAP - clr)))
            h.SetLayer(t.GetLayer())
            h.SetNet(t.GetNet())
            B.Add(h)
            made.append(h)
    return made


def route(r, name: str, width: float, clr: float, pour: list) -> bool:
    """One net by router.py, ANALOG_GAP from the other kind (_halo()); VBAT with the pour fence
    lifted (the pour is its own)."""
    if name == "VBAT":
        for t in pour:
            remove(t)
        pour.clear()
    halo = _halo(name, clr)
    try:
        r.route_net(name, width, clr=clr)
        return True
    except RuntimeError:
        return False
    finally:
        for t in halo:
            remove(t)
        if name == "VBAT":
            pour += pour_fence()


LOCAL = 4.0  # mm: a two-pin net this short, from a fine-pitch chip's pin, is routed first


def local_nets() -> list[str]:
    """The two-pin nets from a fine-pitch chip's pin to a part beside it (a charge pump's
    capacitor, a pull-up), shortest first: routed before the power paths, which would otherwise
    take the gap between the chip and its parts. Not the analog nets: routed after the switching
    paths, they keep ANALOG_GAP from them (_halo()) instead of taking their way out (a bridge's
    IPROPI beside its OUT1)."""
    pads: dict[str, list] = {}
    for f in B.GetFootprints():
        for p in f.Pads():
            pads.setdefault(p.GetNetname(), []).append(p)
    out = []
    for n, ps in pads.items():
        if len(ps) != 2 or not n or "NC_" in n or n in WIDE or n in PLANE_NETS or n == "GND":
            continue
        if n in nets.ANALOG:
            continue
        d = math.dist(xy(ps[0].GetPosition()), xy(ps[1].GetPosition()))
        fine = any(
            p.GetParentFootprint().GetReference().startswith(("IC", "U", "Q"))
            and pcbnew.ToMM(min(p.GetSize().x, p.GetSize().y)) < FINE_PIN
            for p in ps
        )
        if fine and d <= LOCAL:
            out.append((d, n))
    return [n for _, n in sorted(out)]


# Signal nets routed before the power paths, which would wall in their pins: the battery shunt's
# Kelvin sense pair (R59's sense pads sit between BAT_P's tracks and the VBAT pour) and the
# battery switch's gate (Q6's gate pin, between its GND_BAT pins and their track to J1)
EARLY = ("REGULATORS.BAT_SENSE_P", "REGULATORS.BAT_SENSE_N", "REGULATORS.BAT_SW_GATE")
# Parts whose pins the power paths keep off on B.Cu: the encoders' pads take their signals' vias
# beside them, so VBAT does not run under them
CLEAR_BELOW = ("EC1", "EC2")
CLEAR_GROW = 0.6  # mm round the part's pads


def clear_below() -> list:
    """Temporary B.Cu copper over the CLEAR_BELOW parts, for the power paths to route round."""
    made = []
    for ref in CLEAR_BELOW:
        f = B.FindFootprintByReference(ref)
        if f is None:
            continue
        boxes = [p.GetBoundingBox() for p in f.Pads()]
        x0 = min(xy(bb.GetOrigin())[0] for bb in boxes) - CLEAR_GROW
        y0 = min(xy(bb.GetOrigin())[1] for bb in boxes) - CLEAR_GROW
        x1 = max(xy(bb.GetEnd())[0] for bb in boxes) + CLEAR_GROW
        y1 = max(xy(bb.GetEnd())[1] for bb in boxes) + CLEAR_GROW
        y = y0
        while y <= y1:
            made.append(_bar(BK, x0, x1, y))
            y += 0.5
    return made


def power_routes() -> list[str]:
    """The local nets (local_nets()) and the EARLY ones, then the ROUTES nets with router.py, each
    at its width, or narrower where its pads leave no room; locked, so Freerouting routes round
    them."""
    pcbnew.ZONE_FILLER(B).Fill(B.Zones())
    tmp, pour = fence() + clear_below(), pour_fence()
    r = router.Router(B)
    for name in [*local_nets(), *(n for n in EARLY if B.FindNet(n) is not None)]:
        route(r, name, SIGNAL_W, SIGNAL_CLR, pour) or route(r, name, FINE, SIGNAL_CLR, pour)
    failed = []
    for name, width, clr in ROUTES:
        if B.FindNet(name) is None:
            continue
        steps = [width] + [v for v in (NARROW, FINE) if v < width]
        if not any(route(r, name, v, clr or SIGNAL_CLR, pour) for v in steps):
            failed.append(name)
    for t in tmp + pour:
        remove(t)
    for t in B.GetTracks():
        t.SetLocked(True)
    return failed


def _seg_clear(t, w: float) -> bool:
    """Track t at width w keeps clear of every other net (the switching-analog gap from the analog
    nets), of the holes, the edge and the keep-outs."""
    n, layer = t.GetNetname(), t.GetLayer()
    a, b = xy(t.GetStart()), xy(t.GetEnd())
    c, reach = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), math.dist(a, b) / 2 + w / 2 + 1.0
    seg = pcbnew.SHAPE_SEGMENT(t.GetStart(), t.GetEnd(), mm(w))
    pair = (n in nets.SWITCHING, n in nets.ANALOG)

    def gap(other: str) -> float:
        if (pair[0] and other in nets.ANALOG) or (pair[1] and other in nets.SWITCHING):
            return nets.ANALOG_GAP
        return SIGNAL_CLR

    if any(seg.Collide(pcbnew.SHAPE_SEGMENT(e.A, e.B, 0), mm(0.25)) for e in edge_segments()):
        return False
    if any(k.Collide(pt(*q), mm(w / 2 + 0.1)) for k in KEEPOUTS for q in (a, b, c)):
        return False
    for f in near(B.GetFootprints(), c, reach + 2.0):
        for p in near(f.Pads(), c, reach):
            if p.GetNetname() == n:
                continue
            if p.HasHole() and p.GetEffectiveHoleShape().Collide(seg, mm(0.35)):
                return False
            if p.IsOnLayer(layer) and p.GetEffectiveShape(layer).Collide(seg, mm(gap(p.GetNetname()))):
                return False
    for o in near(B.GetTracks(), c, reach):
        if o.GetNetname() == n or not (o.GetClass() == "PCB_VIA" or o.GetLayer() == layer):
            continue
        if o.GetEffectiveShape(layer).Collide(seg, mm(gap(o.GetNetname()))):
            return False
    return True


FAT_PIECE = 0.5  # mm: a track that cannot widen all along is widened in pieces this long


def _widen(t, w: float) -> bool:
    for v in [w] + [v for v in (0.6, NARROW, 0.3, 0.2) if v < w]:
        if mm(v) > t.GetWidth() and _seg_clear(t, v):
            t.SetWidth(mm(v))
            return True
    return False


def _on_fine_pin(t) -> bool:
    """t ends on a fine-pitch pin: it stays the pin's width (a neck, a join of neighbours)."""
    for c in (xy(t.GetStart()), xy(t.GetEnd())):
        for f in near(B.GetFootprints(), c, 0.0):
            for p in f.Pads():
                fine = pcbnew.ToMM(min(p.GetSize().x, p.GetSize().y)) < FINE_PIN
                if fine and p.IsOnLayer(t.GetLayer()) and p.HitTest(pt(*c)):
                    return True
    return False


def fatten() -> int:
    """Every power path's track back to its width (or the widest of a few below it) where it has
    the room: router.py routes a net at one width, so a path that had to leave a fine-pitch pin
    narrower is narrow all its length. A long track pinched at one spot is cut in pieces, and
    only the pieces at the pinch stay narrow."""
    widths = {n: w for n, w, _ in ROUTES}
    made = 0
    for t in list(B.GetTracks()):
        w = widths.get(t.GetNetname())
        if t.GetClass() == "PCB_VIA" or not w or t.GetWidth() >= mm(w) or _on_fine_pin(t):
            continue
        if _widen(t, w):
            made += 1
            continue
        a, b = xy(t.GetStart()), xy(t.GetEnd())
        k = int(math.dist(a, b) / FAT_PIECE)
        if k < 2:
            continue
        pts = [(round(a[0] + (b[0] - a[0]) * i / k, 4), round(a[1] + (b[1] - a[1]) * i / k, 4)) for i in range(k + 1)]
        name, layer, width, locked = t.GetNetname(), t.GetLayer(), t.GetWidth(), t.IsLocked()
        remove(t)
        for p, q in itertools.pairwise(pts):
            piece = track(name, "F" if layer == F else "B", pcbnew.ToMM(width), p, q)
            piece.SetLocked(locked)
            made += _widen(piece, w)
    return made


# router.py's rules: 0.15 mm signals; 0.13 mm from other copper, so a track keeps the board's
# 0.2 mm from a via's hole (0.45 mm via: 0.225 mm pad, 0.15 mm hole radius) with 5 um to spare: a
# 0.28 mm pitch, against JLCPCB's 0.1 / 0.1 mm (main2.zen)
SIGNAL_W, SIGNAL_CLR = 0.15, 0.13
# Freerouting's: the board's 0.1 mm from tracks and pads (a 0.25 mm pitch), its vias drawn wide
# enough that the 0.1 mm from their copper is HOLE_TRACK from their hole; they come back their size
FR_CLR = 0.1
HOLE_TRACK = 0.2  # mm, via hole to track (rules/jlcpcb.kicad_dru)
FR_PASSES = 12  # each pass after the first costs 3-5 min and connects a few more


def class_width(net: str) -> float:
    return next((w for n, w, _ in ROUTES if n == net), 0.3 if net in {"GND", "3V3_D"} else SIGNAL_W)


def _classes(dsn: str) -> str:
    """The session's net classes: ROUTES' nets that router.py left (at their widths), GND, and the
    signals; the nets without a second pin are left out."""
    # the board's 0.45 mm via (router.py's), not the net class's default; the signals' 0.35 mm one
    via = f"Via[0-3]_{round(VIA_D * 1000)}:{round(VIA_HOLE * 1000)}_um"
    assert f'(padstack "{via}"' in dsn, via
    small = f"Via[0-3]_{round(ESCAPE_D * 1000)}:{round(ESCAPE_HOLE * 1000)}_um"
    shapes = "".join(f"(shape (circle {L} {round(ESCAPE_D * 1000)}))" for L in ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"))
    dsn = dsn.replace(f'(padstack "{via}"', f'(padstack "{small}" {shapes} (attach off))\n    (padstack "{via}"', 1)
    dsn = dsn.replace(f'(via "{via}")', f'(via "{via}" "{small}")', 1)
    a = dsn.index("(class kicad_default")
    depth, i = 0, a
    while True:
        c = dsn[i]
        depth += c == "("
        depth -= c == ")"
        i += 1
        if depth == 0:
            break
    pins = {}
    for f in B.GetFootprints():
        for p in f.Pads():
            if p.GetNetname():
                pins[p.GetNetname()] = pins.get(p.GetNetname(), 0) + 1
    # one class per (width, kind): the switching nodes keep ANALOG_GAP from the analog nets
    kind = lambda n: "sw" if n in nets.SWITCHING else "an" if n in nets.ANALOG else "x"  # noqa: E731
    groups: dict[tuple[float, str], list[str]] = {}
    for n, k in pins.items():
        if k < 2 or "NC_" in n:
            continue
        w = class_width(n)
        groups.setdefault((w, kind(n)), []).append(n)
    um = lambda v: round(v * 1000)  # noqa: E731
    out, names = [], {}
    for k, ((w, kd), members) in enumerate(sorted(groups.items())):
        names[f"c{k}"] = kd
        nets_ = " ".join(f'"{n}"' for n in sorted(members))
        out.append(
            f'(class c{k} {nets_} (circuit (use_via "{small if w <= SIGNAL_W else via}")) (rule (width {um(w)}) (clearance {um(FR_CLR)})))'
        )
    for s in (c for c, kd in names.items() if kd == "sw"):
        for a_ in (c for c, kd in names.items() if kd == "an"):
            out.append(f"(class_class (classes {s} {a_}) (rule (clearance {um(nets.ANALOG_GAP)})))")
    dsn = dsn[:a] + "\n    ".join(out) + dsn[i:]
    dsn = _wide_vias(dsn)
    # the inner layers are ground planes only: KiCad exports them as signal layers
    dsn = re.sub(r"(\(layer In[12]\.Cu\s+\(type )signal\)", r"\1power)", dsn)
    # Freerouting crosses a pour on a signal layer: the VBAT pours are kept out of B.Cu's tracks
    pour = re.search(r"\(plane VBAT \(polygon B\.Cu 0[^)]*\)\)", dsn)
    return dsn[: pour.end()] + "\n    " + pour_keepout() + dsn[pour.end() :]


WIDE_VIAS: dict[tuple[int, int], int] = {}  # (drawn diameter, hole) -> diameter, in um


def _wide_vias(dsn: str) -> str:
    """Every via padstack's circles drawn wide enough that FR_CLR from them keeps HOLE_TRACK from
    the hole; WIDE_VIAS maps them back."""
    for m in reversed(list(re.finditer(r'\(padstack "Via\[0-3\]_(\d+):(\d+)_um"', dsn))):
        d, h = int(m[1]), int(m[2])
        wide = max(d, round(h + 2000 * (HOLE_TRACK - FR_CLR)))
        if wide == d:
            continue
        WIDE_VIAS[(wide, h)] = d
        end = dsn.index("(attach", m.start())
        dsn = dsn[: m.start()] + re.sub(rf"(\(circle \S+ ){d}\b", rf"\g<1>{wide}", dsn[m.start() : end]) + dsn[end:]
    return dsn


def _narrow_vias() -> int:
    """The vias of a Freerouting session back to their size (_wide_vias()); how many."""
    made = 0
    for t in B.GetTracks():
        if t.GetClass() == "PCB_VIA":
            key = (round(pcbnew.ToMM(t.GetWidth(F)) * 1000), round(pcbnew.ToMM(t.GetDrill()) * 1000))
            if key in WIDE_VIAS:
                t.Padstack().SetMode(pcbnew.PADSTACK.MODE_NORMAL)  # one size on every layer
                t.SetWidth(mm(WIDE_VIAS[key] / 1000))
                made += 1
    return made


def _hold(p: pcbnew.PAD) -> pcbnew.ZONE:
    """A B.Cu keep-out (no tracks, no vias) over pad p, grown by the signals' clearance."""
    shape = p.GetEffectivePolygon(F).CloneDropTriangulation()
    shape.Inflate(mm(SIGNAL_CLR), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, mm(0.01))
    z = pcbnew.ZONE(B)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(True)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowZoneFills(False)
    z.SetDoNotAllowFootprints(False)
    z.SetLayer(BK)
    z.Outline().AddOutline(shape.Outline(0))
    B.Add(z)
    return z


def freerouting() -> None:
    """Every net not yet routed, by Freerouting, from a Specctra design of the board; its session
    replaces the board's tracks (the locked ones come back as they were). The vias inside a pad
    of their own net (the thermal vias) stay out of it: Freerouting reads a via on a pad as a
    violation, and routes round the whole part. A B.Cu keep-out over their pad holds their room."""
    inpad, held = [], []
    for t in list(B.GetTracks()):
        if t.GetClass() == "PCB_VIA":
            c = xy(t.GetPosition())
            pads = [p for f in near(B.GetFootprints(), c, 0.0) for p in f.Pads()]
            host = next((p for p in pads if p.GetNetname() == t.GetNetname() and p.HitTest(t.GetPosition())), None)
            if host is not None:
                inpad.append((t.GetNetname(), c))
                remove(t)
                if host not in held:
                    held.append(host)
    holds = [_hold(p) for p in held]
    with tempfile.TemporaryDirectory() as d:
        dsn, ses = Path(d) / "main2.dsn", Path(d) / "main2.ses"
        if not pcbnew.ExportSpecctraDSN(B, str(dsn)):
            raise SystemExit("Specctra export failed")
        dsn.write_text(_classes(dsn.read_text()))
        cmd = [*tools.freerouting(), "-de", str(dsn), "-do", str(ses), "-mp", str(FR_PASSES)]
        # no fanout pass: it puts a via beside every SMD pin it can, and the STM32's pins are led
        # out already (mcu_escape())
        cmd += ["--gui.enabled=false", "--usage_and_diagnostic_data.disable_analytics=true"]
        cmd += ["--router.fanout.enabled=false"]
        subprocess.run(cmd, check=True, cwd=d, env=os.environ | {"JAVA_TOOL_OPTIONS": "-Djava.awt.headless=true"})
        if not ses.exists():
            raise SystemExit("Freerouting wrote no session")
        if not pcbnew.ImportSpecctraSES(B, str(ses)):
            raise SystemExit("Specctra session import failed")
    print(f"vias narrowed: {_narrow_vias()} {WIDE_VIAS}", flush=True)
    for z in holds:
        remove(z)
    for n, c in inpad:
        via(n, *c)
    for t in B.GetTracks():
        t.SetLocked(False)


def finish(narrow: dict[str, float], only: set[str] | None = None) -> list[str]:
    """What Freerouting left unconnected (of the nets in only, if given), by router.py: each net
    at its class's width (or the narrower one clean() gave it), or at FINE."""
    pcbnew.ZONE_FILLER(B).Fill(B.Zones())
    tmp, pour = fence(), pour_fence()
    r = router.Router(B)
    pins: dict[str, list] = {}
    for f in B.GetFootprints():
        for p in f.Pads():
            if p.GetNetname():
                pins.setdefault(p.GetNetname(), []).append(xy(p.GetPosition()))

    def span(n: str) -> float:  # half the perimeter of the net's pads' box
        xs, ys = [q[0] for q in pins[n]], [q[1] for q in pins[n]]
        return max(xs) - min(xs) + max(ys) - min(ys)

    # the power paths first (they have the fewest ways through), then the shortest first: a long
    # net finds its way round them, a short one has no way round
    names = [n for n, ps in pins.items() if len(ps) > 1 and "NC_" not in n and (only is None or n in only)]
    failed = []
    for name in sorted(names, key=lambda n: (n not in WIDE, span(n), n)):
        w = narrow.get(name, class_width(name))
        if not (route(r, name, w, SIGNAL_CLR, pour) or route(r, name, FINE, SIGNAL_CLR, pour)):
            failed.append(name)
    for t in tmp + pour:
        remove(t)
    return failed


def drc() -> dict:
    """KiCad's DRC report (errors only) on the board as it stands, under the layout's rules."""
    pcbnew.ZONE_FILLER(B).Fill(B.Zones())
    with tempfile.TemporaryDirectory() as d:
        pcb, report = Path(d) / PCB.name, Path(d) / "drc.json"
        B.Save(str(pcb))
        # the save writes KiCad's default project beside the board: the layout's replaces it
        for ext in (".kicad_pro", ".kicad_dru"):
            shutil.copy(PCB.with_suffix(ext), pcb.with_suffix(ext))
        cmd = [tools.kicad_cli(), "pcb", "drc", "--format", "json", "--severity-error", "-o", str(report), str(pcb)]
        subprocess.run(cmd, check=True, capture_output=True)
        return json.loads(report.read_text())


def _bridge_stub(t) -> bool:
    """t ends at the centre of a bridge's pin (its escape stub): the DRV8874 puts VREF and IPROPI (pins 5, 6) two pins from OUT1
    (pin 8, SLVSF66A pinout), so its escape stub cannot keep ANALOG_GAP from OUT1's path (the
    owner's exemption, as in tests/test_main2_layout.py)."""
    ends = (xy(t.GetStart()), xy(t.GetEnd()))
    for ref in BRIDGES:
        f = B.FindFootprintByReference(ref)
        if any(math.dist(e, xy(p.GetPosition())) < 0.01 for p in f.Pads() for e in ends):
            return True
    return False


def _near_switching() -> list:
    """The analog nets' tracks less than ANALOG_GAP from a switching node's track on their layer
    (but for a bridge's escape stubs, _bridge_stub())."""
    tracks = [t for t in B.GetTracks() if t.GetClass() == "PCB_TRACK"]
    sw = [t for t in tracks if t.GetNetname() in nets.SWITCHING]
    out = []
    for a in (t for t in tracks if t.GetNetname() in nets.ANALOG and not _bridge_stub(t)):
        shape = a.GetEffectiveShape(a.GetLayer())
        gap = mm(nets.ANALOG_GAP) - 1  # 1 nm: a track at the gap is clear
        if any(s.GetLayer() == a.GetLayer() and shape.Collide(s.GetEffectiveShape(s.GetLayer()), gap) for s in sw):
            out.append(a)
    return out


def _over_pour() -> list:
    """The B.Cu tracks of other nets with a point inside the VBAT pour's outline (sampled every
    0.1 mm, as tests/test_main2_layout.py does): Freerouting's keep-out strips leave the pour's
    edges up to a strip open."""
    poly = _pour()[0]
    out = []
    for t in B.GetTracks():
        if t.GetClass() != "PCB_TRACK" or t.GetLayer() != BK or t.GetNetname() in ("VBAT", "GND"):
            continue
        a, b = xy(t.GetStart()), xy(t.GetEnd())
        k = max(1, int(math.dist(a, b) / 0.1))
        if any(poly.Contains(pt(a[0] + (b[0] - a[0]) * i / k, a[1] + (b[1] - a[1]) * i / k)) for i in range(k + 1)):
            out.append(t)
    return out


def clean() -> set[str]:
    """Removes one track or via of each DRC error (an unlocked one, of a signal, the narrowest,
    before the power paths), every track on the ground planes' layers, the analog tracks too near
    a switching node (_near_switching()) and the other nets' B.Cu tracks on the VBAT pour
    (_over_pour()); returns their nets. router.py ends a track anywhere inside its pad, so a wide
    track across a row of fine-pitch pins can reach the next pin: its net is routed again
    narrower."""
    items = {t.m_Uuid.AsString(): t for t in B.GetTracks()}
    gone = {u for u, t in items.items() if t.GetClass() != "PCB_VIA" and t.GetLayer() in (IN1, IN2)}
    gone |= {t.m_Uuid.AsString() for t in _near_switching() + _over_pour()}
    for v in drc()["violations"]:
        cands = [items[i["uuid"]] for i in v["items"] if i["uuid"] in items]
        if cands and not any(t.m_Uuid.AsString() in gone for t in cands):
            t = min(
                cands,
                key=lambda t: (
                    t.IsLocked(),
                    t.GetNetname() in WIDE,
                    t.GetNetname() in PLANE_NETS or t.GetNetname() == "GND",
                    t.GetWidth(F) if t.GetClass() == "PCB_VIA" else t.GetWidth(),
                ),
            )
            gone.add(t.m_Uuid.AsString())
    cut = set()
    for u in gone:
        cut.add(items[u].GetNetname())
        remove(items[u])
    return cut


TINY = 1000  # nm: a track this short is a router's leftover, with no direction of its own


def _covered(c: pcbnew.VECTOR2I, layer: int) -> bool:
    """c in a via, or in the inscribed circle of a pad on the layer: tests/test_layout.py's rule."""
    if any(t.GetClass() == "PCB_VIA" and t.HitTest(c) for t in near(B.GetTracks(), xy(c), 0.5)):
        return True
    for f in near(B.GetFootprints(), xy(c), 0.0):
        for p in f.Pads():
            r = min(p.GetSize().x, p.GetSize().y) / 2
            if p.IsOnLayer(layer) and math.dist((c.x, c.y), (p.GetPosition().x, p.GetPosition().y)) <= r:
                return True
    return False


def _corner_once() -> int:
    """One change at each acute corner (square_corners()); how many."""
    arms: dict[tuple, list] = {}
    for t in B.GetTracks():
        if t.GetClass() == "PCB_TRACK" and t.GetLength() > 0:
            for e in (t.GetStart(), t.GetEnd()):
                arms.setdefault((t.GetNetname(), t.GetLayer(), e.x, e.y), []).append(t)
    touched: set[str] = set()
    made = 0
    for (_, layer, x, y), ts in arms.items():
        if len(ts) < 2 or any(t.m_Uuid.AsString() in touched for t in ts):
            continue
        c = pcbnew.VECTOR2I(x, y)
        far = [t.GetEnd() if t.GetStart() == c else t.GetStart() for t in ts]
        u = [((o.x - x) / math.dist((x, y), (o.x, o.y)), (o.y - y) / math.dist((x, y), (o.x, o.y))) for o in far]
        pairs = [(i, j) for i in range(len(ts)) for j in range(i + 1, len(ts))]
        cos = {(i, j): u[i][0] * u[j][0] + u[i][1] * u[j][1] for i, j in pairs}
        if all(v <= 1e-6 for v in cos.values()) or _covered(c, layer):
            continue
        same = [(i, j) for i, j in pairs if cos[(i, j)] > 1 - 1e-6]
        back = [(i, j) for i, j in pairs if cos[(i, j)] < -1 + 1e-6 and ts[i].GetWidth() == ts[j].GetWidth()]
        if same:  # doubled back: the shorter arm lies on the longer
            i, j = same[0]
            gone = ts[i] if ts[i].GetLength() < ts[j].GetLength() else ts[j]
            touched |= {t.m_Uuid.AsString() for t in ts}
            remove(gone)
            made += 1
        elif len(ts) > 2 and back:  # a straight run through the corner: one track, the rest tee onto it
            i, j = back[0]
            if ts[i].GetStart() == c:
                ts[i].SetStart(far[j])
            else:
                ts[i].SetEnd(far[j])
            touched |= {t.m_Uuid.AsString() for t in ts}
            remove(ts[j])
            made += 1
        elif len(ts) == 2:  # cut square to the longer arm, d from the corner
            i = 0 if ts[0].GetLength() >= ts[1].GetLength() else 1
            j = 1 - i
            w = min(ts[0].GetWidth(), ts[1].GetWidth())
            d = max(w, mm(0.1))
            reach = d / cos[(0, 1)]  # along the other arm
            if d >= ts[i].GetLength() or reach >= ts[j].GetLength():
                continue
            p = pcbnew.VECTOR2I(round(x + u[i][0] * d), round(y + u[i][1] * d))
            q = pcbnew.VECTOR2I(round(x + u[j][0] * reach), round(y + u[j][1] * reach))
            for t, e in ((ts[i], p), (ts[j], q)):
                if t.GetStart() == c:
                    t.SetStart(e)
                else:
                    t.SetEnd(e)
            cut = track(ts[i].GetNetname(), "F" if layer == F else "B", pcbnew.ToMM(w), xy(p), xy(q))
            cut.SetStart(p)
            cut.SetEnd(q)
            touched |= {t.m_Uuid.AsString() for t in ts}
            made += 1
    return made


def square_corners() -> int:
    """No acute corner off a pad or via (tests/test_layout.py, acid traps): a leftover a few nm
    long goes, its neighbours joined across it; a track doubled back on another loses its shorter
    arm; a straight run through a corner becomes one track; the acute corner of two tracks left is
    cut by a track square to the longer, so its corners are 90 and 90 + the angle. Returns how
    many it changed."""
    made = 0
    for t in [t for t in B.GetTracks() if t.GetClass() == "PCB_TRACK" and 0 < t.GetLength() < TINY]:
        a, b = t.GetStart(), t.GetEnd()
        for o in B.GetTracks():
            if o is not t and o.GetClass() == "PCB_TRACK" and o.GetNetname() == t.GetNetname():
                if o.GetStart() == b:
                    o.SetStart(a)
                if o.GetEnd() == b:
                    o.SetEnd(a)
        remove(t)
        made += 1
    for _ in range(4):
        step = _corner_once()
        made += step
        if not step:
            break
    return made


def clear() -> None:
    for t in list(B.GetTracks()):
        remove(t)
    for z in list(B.Zones()):
        remove(z)


def main() -> int:
    global B
    B = pcbnew.LoadBoard(str(PCB))
    clear()
    keepouts()
    planes()
    print(f"thermal vias: {thermal_vias()}", flush=True)
    ep_ground()
    print(f"neighbouring pins joined: {join_neighbours()}", flush=True)
    print("STM32 pins not led out:", *mcu_escape(), sep="\n  ", flush=True)
    print("bridge pins not led out:", *bridge_escape(), sep="\n  ", flush=True)
    missed = plane_vias()
    print(f"plane vias missed: {len(missed)}", *missed, sep="\n  ", flush=True)
    print(f"STM32 signals fanned out: {mcu_fanout()}", flush=True)
    print(f"power pins necked: {necks()}", flush=True)
    failed = power_routes()
    print(f"power paths left to Freerouting: {len(failed)}", *failed, sep="\n  ", flush=True)
    print(f"power tracks widened: {fatten()}", flush=True)
    freerouting()
    print(f"neighbouring pins joined again: {rejoin()}", flush=True)
    print(f"power tracks widened: {fatten()}", flush=True)
    B.Save(str(PCB))  # a checkpoint: Freerouting's passes take most of the run
    # router.py finishes; what breaks a rule is removed and routed again, narrower
    narrow: dict[str, float] = {}
    only = None
    for _ in range(4):
        cut = clean()
        print(f"tracks removed for DRC errors on: {len(cut)}", *sorted(cut), sep="\n  ", flush=True)
        if only is not None and not cut:
            break
        for n in cut:
            narrow[n] = max(FINE, narrow.get(n, class_width(n)) * 0.6)
        finish(narrow, only)
        only = cut
    print(f"acute corners squared: {square_corners()}", flush=True)
    print(f"vias narrowed late: {_narrow_vias()}", flush=True)
    # what the last pass broke is removed, and left unconnected
    print("tracks removed for DRC errors, not routed again:", *sorted(clean()), sep="\n  ", flush=True)
    report = drc()
    print(f"DRC errors: {len(report['violations'])}, unconnected: {len(report['unconnected_items'])}", flush=True)
    nets_left = sorted(
        {i["description"].split("[")[1].split("]")[0] for u in report["unconnected_items"] for i in u["items"]}
    )
    print("nets not routed:", *nets_left, sep="\n  ", flush=True)
    pours()
    pcbnew.ZONE_FILLER(B).Fill(B.Zones())
    B.Save(str(PCB))
    return 0


if __name__ == "__main__":
    sys.exit(main())
