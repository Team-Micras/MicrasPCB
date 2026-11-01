"""Planes, plane vias and routing of the second main board, on the placement place.py leaves.

    /usr/bin/python3 boards/main2/layout/route.py      # KiCad's Python (pcbnew), from the repo root

Starts from the placed board: every track, via and board-level pour is removed first, so a rerun
gives the same copper. Stackup (boards/main2/main2.zen): F.Cu and B.Cu 1 oz, In1.Cu and In2.Cu
0.5 oz.

- In1.Cu and In2.Cu: ground planes over the whole board, so a track on either outer layer has an
  unbroken ground plane next to it for its return current (F.Cu over In1.Cu, B.Cu over In2.Cu);
  In2.Cu but for the STM32's supplies under and round it: 3V3_D under it, VCORE in a band round
  that which reaches its vias and stops either side of the chip's rear tip.
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

- After the routing: the outer ground pours; thermal reliefs on the board-wide pours with solid
  joins where current or heat flows (relief()); a B.Cu ground island under each bridge's exposed
  pad (heat_islands()); ground stitching vias (stitch()).

The ESP32-C5-MINI-1's antenna keep-out (its footprint's rule area) is fenced with temporary
copper while router.py runs, which does not read rule areas; Freerouting reads it as a keep-out.
The board is cut away under the antenna (spec [antenna_notch]).
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

# B.Cu VBAT: the battery input in the rear-left corner (F1's VBAT side and its via field, D14, D15,
# the bulk C93) and the middle, under both bridges and the capacitors behind them (C82-C84, C88, C91,
# C97): the bridges' supply loop (VM, the bottom pin rows) closes there. It stops at the bridges'
# logic pins (x > -8.6): their tracks drop to B.Cu there and pass under the OUT1 paths, and B.Cu
# ahead stays the IMU's and the encoders'. The battery input's part ends 2 mm short of the GND_BAT
# pour (y 18 to 20.2): the battery switch's drive line and its VBAT feed pass there on B.Cu. The
# other bulk capacitors (place.py BULK: C92 by the right wheel cut-out, C87, C111 behind the fan
# hole, C96 and C112 in front of it) take VBAT by track. The fan driver's feed is a B.Cu pour from
# the pour's front corner along the left wheel cut-out to the fan's VS strip, outside the fan hole's
# rim, which the lines to the STM32 keep on both outer layers
VBAT_POUR = [
    (-8.6, 13.0),  # the middle: bridges, capacitors (x -24.5..-8.6, y -12.5..13)
    (-11.6, 13.0),  # a notch under R75 (x -13..-11.6, y 8.5..13): Motor_L_Sense+ leaves the shunt's
    (-11.6, 8.5),  # sense pad on B.Cu there, the OUT1 path and the SHUNT path closing F.Cu round it
    (-13.0, 8.5),
    (-13.0, 13.0),
    (-22.4, 13.0),
    (-22.4, 18.0),  # F1's VBAT pad, its vias, D15 (x -28.6..-22.4, y 11..18)
    (-28.6, 18.0),
    (-28.6, 11.0),
    (-30.5, 11.0),  # D14, C93 (x -30.5..-24.5, y 7..11), behind M1's B.Cu terminal crossing
    (-30.5, 7.0),
    (-24.5, 7.0),
    (-24.5, -12.5),
    (-8.6, -12.5),
]


# In2.Cu round the STM32 (IC1): its 3V3_D pins alternate with its VCORE pins on all four sides, and
# the two nets, as tracks, would ring it on both outer layers and leave its 0.4 mm pitch pins no way
# out. On In2 they nest instead: 3V3_D under the chip and out past its pin tips, VCORE round that;
# each pin's via, at its tip, lands in its own (owner, 2026-10-18: In2 is ground everywhere else, as
# on the previous board's power layer)
MCU = "IC1"
MCU_3V3 = 0.8  # mm past the pin tips: a via at each 3V3_D pin's tip
# VCORE's island (owner, 2026-10-24) is only as big as its job: a band round the 3V3_D island that
# reaches the vias of VFBSMPS (pin 7) and VCAP1-3 (pins 33, 49, 66; main2.zen, DS13311 pinout), of
# their capacitors C5-C7 and of the SMPS output (L1, C3, C4), and joins them. Each face goes out to
# its own reach (mm, in |dx| + |dy| from the chip's centre: the faces run at 45 degrees as the chip
# sits, place.py) about 1 mm past its furthest VCORE via, and the band stops either side of the
# rear tip, where no VCORE via sits, so In2.Cu's ground and the digital hops pass between the chip and
# the fan hole and over the escape rows round it.
VCORE_REACH = {"rear_left": 10.9, "front_left": 9.8, "front_right": 11.0, "rear_right": 10.5, "right_vertex": 11.63}
VCORE_TIP = (1.4, -2.5)  # robot y where the rear-left and rear-right arms end
VCORE_INNER = 7.4  # the band's inner edge (|dx| + |dy|): outside the 3V3_D vias at the pin tips
# 3V3_D's island (owner, 2026-10-25) is the square under the chip out to its pin tips, with a tab to
# each 3V3_D pin's via: (mm past the via's edge, mm either side of the pin)
MCU_3V3_TAB = (0.35, 0.55)
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


def vcore_outline() -> list:
    """VCORE's In2.Cu island (robot frame): the band VCORE_REACH describes round IC1's centre, from
    VCORE_INNER (just outside the pin tips' 3V3_D vias) out, open at the rear tip."""
    f = B.FindFootprintByReference(MCU)
    kx, ky = xy(f.GetPosition())
    cx, cy = OY - ky, OX - kx
    r, (tl, tr), inner = VCORE_REACH, VCORE_TIP, VCORE_INNER
    rl, fl, fr, rr, rv = r["rear_left"], r["front_left"], r["front_right"], r["rear_right"], r["right_vertex"]
    d = [
        (-(rl - tl), tl),  # the rear-left arm's end, on its face
        (0, rl),
        (0, fl),  # along the rear-left face to the left vertex, in to the front-left face
        (fl, 0),
        (fr, 0),  # to the front vertex, out to the front-right face
        (0, -fr),
        (0, -rv),  # to the right vertex, out round C3's via
        (-(rv - 7.0), -7.0),
        (-(rr - 7.0), -7.0),  # back along the rear-right face, in
        (-(rr + tr), tr),
        (-(inner + tr), tr),  # to the rear-right arm's end, in to the band's inner edge
        (0, -inner),
        (inner, 0),
        (0, inner),  # the inner edge round the front
        (-(inner - tl), tl),  # back to the rear-left arm's end
    ]
    return [(cx + u, cy + v) for u, v in d]


def mcu_3v3_outline() -> list:
    """3V3_D's In2.Cu island (robot frame): the square under IC1 out to its pin tips, with a tab out
    to each 3V3_D pin's via at the tip (ESCAPE_REACH): VBAT (pin 1), VDDSMPS (pin 6) and VDD (pins 9,
    22, 35, 51, 68), all on 3V3_D (main2.zen; DS13311 pinout). Built in the chip's frame and turned
    with it, so the outline is octilinear as the chip sits."""
    f = B.FindFootprintByReference(MCU)
    kx, ky = xy(f.GetPosition())
    a = math.radians(f.GetOrientationDegrees())
    ca, sa = math.cos(a), math.sin(a)
    h = 0.0  # the pins' reach from the centre, in the chip's frame (as pin_square())
    pins = []
    for p in f.Pads():
        px, py = xy(p.GetPosition())
        u, v = (px - kx) * ca - (py - ky) * sa, (px - kx) * sa + (py - ky) * ca
        if p.GetNetname() == "3V3_D":
            pins.append((u, v))
        poly = p.GetEffectivePolygon(F)
        for i in range(poly.OutlineCount()):
            o = poly.Outline(i)
            for k in range(o.PointCount()):
                x, y = pcbnew.ToMM(o.CPoint(k).x) - kx, pcbnew.ToMM(o.CPoint(k).y) - ky
                h = max(h, abs(x * ca - y * sa), abs(x * sa + y * ca))
    out = h + ESCAPE_REACH["3V3_D"][0] + ESCAPE_D / 2 + MCU_3V3_TAB[0]  # the tab's outer edge
    half = MCU_3V3_TAB[1]
    shape = pcbnew.SHAPE_POLY_SET()

    def rect(u0, u1, v0, v1):
        c = pcbnew.SHAPE_LINE_CHAIN()
        for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1)):
            c.Append(mm(u), mm(v))
        c.SetClosed(True)
        s = pcbnew.SHAPE_POLY_SET()
        s.AddOutline(c)
        return s

    shape.Append(rect(-h, h, -h, h))
    for u, v in pins:
        if abs(u) >= abs(v):  # a pin on a +-u face: its tab runs out along u
            s = math.copysign(1, u)
            tab = rect(min(s * (h - 0.5), s * out), max(s * (h - 0.5), s * out), v - half, v + half)
        else:
            s = math.copysign(1, v)
            tab = rect(u - half, u + half, min(s * (h - 0.5), s * out), max(s * (h - 0.5), s * out))
        shape.BooleanAdd(tab)
    shape.Simplify()
    o = shape.Outline(0)
    pts = []
    for k in range(o.PointCount()):
        u, v = pcbnew.ToMM(o.CPoint(k).x), pcbnew.ToMM(o.CPoint(k).y)
        x, y = kx + u * ca + v * sa, ky - u * sa + v * ca
        pts.append((OY - y, OX - x))
    return pts


def planes() -> None:
    zone("GND", "In1", BOARD, 0)
    zone("GND", "In2", BOARD, 0)
    zone("VCORE", "In2", vcore_outline(), 1)
    zone("3V3_D", "In2", mcu_3v3_outline(), 2)
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
# The thermal vias are left open on both sides, with no via-in-pad process (spec [pcb] via_in_pad):
# 0.2 mm holes, TI's PowerPAD via (SLVSF66A land pattern 4223595/B), which lose less solder than
# larger ones (TI SLUA271C 3.4.1), untented (tenting a pad's via from the back traps air, SLUA271C
# 3.4.1); the exposed pads' paste is split into windows clear of them. A footprint that draws its
# via sites (0.2 mm circles on Cmts.User, in the windows' lanes) takes its vias there; any other
# exposed pad a grid.
THERMAL_D, THERMAL_HOLE = 0.45, 0.2
THERMAL_SITE = 0.2  # mm: a Cmts.User circle this wide marks a via site


def thermal_sites(f: pcbnew.FOOTPRINT) -> list[tuple[float, float]]:
    """The thermal-via sites the footprint draws, on the board (KiCad mm)."""
    out = []
    for g in f.GraphicalItems():
        circle = g.GetLayer() == pcbnew.Cmts_User and g.GetShape() == pcbnew.SHAPE_T_CIRCLE
        if circle and abs(pcbnew.ToMM(g.GetRadius()) * 2 - THERMAL_SITE) < 1e-3:
            out.append(xy(g.GetCenter()))
    return out


def _thermal_via(x: float, y: float) -> pcbnew.PCB_VIA:
    v = via("GND", round(x, 4), round(y, 4), THERMAL_D, THERMAL_HOLE)
    v.SetFrontTentingMode(pcbnew.TENTING_MODE_NOT_TENTED)
    v.SetBackTentingMode(pcbnew.TENTING_MODE_NOT_TENTED)
    return v


THERMAL_GAP = 0.12  # mm, a thermal via's copper to another net's (rules/jlcpcb.kicad_dru: 0.1 mm)


def _blocked(c, r: float, gap: float = THERMAL_GAP) -> bool:
    """A via of radius r at c would come within gap of another net's track, pad or via on any
    layer, or cut a power path's own pour (a named zone of another net)."""
    v = pt(*c)
    for t in near(B.GetTracks(), c, r + gap + 1.0):
        if t.GetNetname() != "GND" and any(
            t.IsOnLayer(L) and t.GetEffectiveShape(L).Collide(v, mm(r + gap)) for L in (F, BK, IN1, IN2)
        ):
            return True
    for f in B.GetFootprints():
        for p in f.Pads():
            on = [L for L in (F, BK) if p.IsOnLayer(L)]
            if on and p.GetNetname() != "GND" and p.GetEffectivePolygon(on[0]).Collide(v, mm(r + gap)):
                return True
    return any(
        z.GetZoneName() and not z.GetIsRuleArea() and z.GetNetname() != "GND" and z.Outline().Collide(v, mm(r + gap))
        for z in B.Zones()
        if not z.IsTeardropArea()
    )


def thermal_vias(only: set[str] | None = None) -> int:
    """Vias in every exposed pad on GND (the largest pad of a chip or transistor, over 2 mm2), to the
    ground planes: the DRV8874s' and STSPIN958's PowerPADs carry their heat out this way. At the
    footprint's via sites (those clear of other nets' copper), else on a grid. A footprint whose
    exposed pad is split into ground squares (the ESP32-C5-MINI-1's nine, datasheet Figure 11-1)
    draws its sites in the gaps between them: a site off every pad that touches two ground pads
    takes its via there, tented on top."""
    n = 0
    for f in B.GetFootprints():
        if not f.GetReference().startswith(("IC", "U", "Q")) or (only is not None and f.GetReference() not in only):
            continue
        sites = thermal_sites(f)
        ground = [p for p in f.Pads() if p.GetNetname() == "GND" and not p.HasHole()]
        for x, y in sites:
            c = pt(x, y)
            if any(p.HitTest(c) for p in f.Pads()):
                continue  # a site in a pad: below
            touching = [p for p in ground if p.GetEffectiveShape(F).Collide(c, mm(THERMAL_D / 2 + 0.05))]
            if len(touching) >= 2 and not _blocked((x, y), THERMAL_D / 2):
                # off the pads, in the solder mask between them: tented on top, so the reflowed
                # solder of the squares beside it has no open hole to wick into
                _thermal_via(x, y).SetFrontTentingMode(pcbnew.TENTING_MODE_TENTED)
                n += 1
        for p in f.Pads():
            if p.GetNetname() != "GND" or p.HasHole():
                continue
            bb = p.GetBoundingBox()
            (x0, y0), (x1, y1) = xy(bb.GetOrigin()), xy(bb.GetEnd())
            if (x1 - x0) * (y1 - y0) < 2.0:
                continue
            if sites:
                for x, y in sites:
                    if p.HitTest(pt(x, y)) and not _blocked((x, y), THERMAL_D / 2):
                        _thermal_via(x, y)
                        n += 1
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
                        _thermal_via(x, y)
                        n += 1
    return n


def rethermal() -> tuple[int, int]:
    """Replace the vias in the exposed pads by thermal_vias() (after a footprint changes its sites):
    returns (removed, placed)."""
    gone, refs = 0, set()
    for f in B.GetFootprints():
        if not thermal_sites(f):
            continue
        refs.add(f.GetReference())
        sites = thermal_sites(f)
        for t in list(B.GetTracks()):  # the vias at sites between pads
            if (
                t.GetClass() == "PCB_VIA"
                and t.GetNetname() == "GND"
                and any(math.dist(xy(t.GetPosition()), s) < 0.05 for s in sites)
            ):
                remove(t)
                gone += 1
        for p in f.Pads():
            if p.GetNetname() != "GND" or p.HasHole():
                continue
            shape = p.GetEffectivePolygon(F)
            if shape.Area() / 1e12 < 2.0:
                continue
            for t in list(B.GetTracks()):
                if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND" and shape.Contains(t.GetPosition()):
                    remove(t)
                    gone += 1
    return gone, thermal_vias(refs)


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
# The fan driver's logic pins (STSPIN958 11 PWM, 14 EN, 15 REF, 16 TOFF) face the fan hole between its
# 3V3_D and GND pins: they drop to B.Cu by vias of their own, the same way, so that VDD and nSTBY
# reach C31 under them on F.Cu
DROPS = {**{ref: (BRIDGE_LOGIC, BRIDGE_ROWS) for ref in BRIDGES}, "IC6": (("11", "14", "15", "16"), (0.5, 0.75))}


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
    ("5V_IN", 0.4, None),
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
    t.SetNet(B.FindNet("ESP.U13.NC_ESP32-C5-MINI-1_IO2"))
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


# Signal nets routed before the power paths, which would wall in their pins: the battery switch's
# gate (Q6's gate pin, between its GND_BAT pins and their track to J1)
EARLY = ("REGULATORS.BAT_SW_GATE",)
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
        # KiCad refills the zones under the .kicad_dru (as `micras-pcb drc` does): pcbnew's filler
        # reads only the board's 0.20 mm edge minimum, not the pours' 0.21 mm rule
        cmd = [
            tools.kicad_cli(),
            "pcb",
            "drc",
            "--refill-zones",
            "--format",
            "json",
            "--severity-error",
            "-o",
            str(report),
            str(pcb),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return json.loads(report.read_text())


def _bridge_stub(t) -> bool:
    """t ends at the centre of a pin of a part that puts a switching and an analog pin side by side
    (nets.STUB_PARTS: the DRV8874s' VREF and IPROPI two pins from OUT1, SLVSF66A pinout; the INA241s'
    Kelvin input beside VS; the shunts' sense pads): its escape stub cannot keep ANALOG_GAP (the
    owner's exemption, as in tests/test_main2_layout.py)."""
    ends = (xy(t.GetStart()), xy(t.GetEnd()))
    for ref in nets.STUB_PARTS:
        f = B.FindFootprintByReference(ref)
        if any(math.dist(e, xy(p.GetPosition())) < 0.01 for p in f.Pads() for e in ends):
            return True
    return False


def _near_switching() -> list:
    """The analog nets' tracks less than ANALOG_GAP from a switching node's track on their layer
    (but for the escape stubs of either, _bridge_stub())."""
    tracks = [t for t in B.GetTracks() if t.GetClass() == "PCB_TRACK"]
    sw = [t for t in tracks if t.GetNetname() in nets.SWITCHING and not _bridge_stub(t)]
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


# ---------------------------------------------------------------------------------------------
# after the routing: pad connections, the bridges' heat islands, ground stitching

# Pads in the board-wide pours (the ground pours and planes, the B.Cu VBAT pour) join them by thermal
# reliefs, so the pour end of a small part heats as fast as its track end in reflow (no tombstoning)
# and a through-hole pad can be soldered by hand (reports/main2-review/routing.md R14: 0.10-0.20 mm
# spokes for SMD, 0.30-0.50 mm for through-hole; the JLCPCB thermal relief design guide). The pads
# that carry current or heat join solid (a pad override): every SMD pad of RELIEF_SOLID_AREA and
# more (exposed pads, the bulk capacitors, the large passives), every ground pin of the power stages
# (POWER_STAGES) and every pad inside one of the power paths' own pours (the named zones, solid
# throughout), and the pads the pour reaches from one side only (RELIEF_STARVED: no room for two
# spokes, KiCad's minimum).
RELIEF_GAP = 0.25  # mm
SMD_SPOKE = 0.2  # mm
THT_SPOKE = 0.4  # mm
RELIEF_SOLID_AREA = 1.2  # mm2: an 0805 pad (1.0 x 1.45 mm) and larger
POWER_STAGES = ("IC6", "IC7", "IC8", "IC9", "Q6")  # fan driver, buck, bridges, battery switch
RELIEF_STARVED = {"C8.1", "C29.1", "C30.1", "D4.1", "IC1.4", "R2.1", "R12.1", "R30.1", "SWD1.2"}
GROUND_LAYERS = {F: "F", BK: "B", IN1: "In1", IN2: "In2"}


def board_pours() -> list:
    """The board-wide pours and planes: the unnamed zones (ground on every layer, VBAT on B.Cu)."""
    return [z for z in B.Zones() if not z.GetIsRuleArea() and not z.IsTeardropArea() and not z.GetZoneName()]


def _in_named_pour(p: pcbnew.PAD) -> bool:
    for z in B.Zones():
        if z.GetIsRuleArea() or z.IsTeardropArea() or not z.GetZoneName() or z.GetNetCode() != p.GetNetCode():
            continue
        for layer in (F, BK):
            if p.IsOnLayer(layer) and z.IsOnLayer(layer) and z.Outline().Contains(p.GetPosition()):
                return True
    return False


def solid_pad(p: pcbnew.PAD) -> bool:
    """An SMD pad that joins the board-wide pours solid."""
    if p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
        return False
    ref = p.GetParentFootprint().GetReference()
    if ref in POWER_STAGES or f"{ref}.{p.GetNumber()}" in RELIEF_STARVED or _in_named_pour(p):
        return True
    return p.GetEffectivePolygon(F if p.IsOnLayer(F) else BK).Area() / 1e12 >= RELIEF_SOLID_AREA


def relief() -> int:
    """Thermal reliefs on the board-wide pours and planes, a solid override on the pads that need
    it; returns the pads joined solid."""
    pours = board_pours()
    for z in pours:
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetThermalReliefGap(mm(RELIEF_GAP))
        z.SetThermalReliefSpokeWidth(
            mm(THT_SPOKE if z.GetLayer() in (IN1, IN2) or z.GetNetname() != "GND" else SMD_SPOKE)
        )
    nets_poured = {z.GetNetCode() for z in pours}
    solid = 0
    for f in B.GetFootprints():
        for p in f.Pads():
            if p.GetNetCode() not in nets_poured:
                continue
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                starved = f"{f.GetReference()}.{p.GetNumber()}" in RELIEF_STARVED
                p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL if starved else pcbnew.ZONE_CONNECTION_THERMAL)
                p.SetLocalThermalSpokeWidthOverride(mm(THT_SPOKE))
            elif p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                full = solid_pad(p)
                p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL if full else pcbnew.ZONE_CONNECTION_THERMAL)
                solid += full
    return solid


# The bridges' exposed pads (DRV8874, GND) reach B.Cu through their thermal vias: a ground island
# there, cut out of the VBAT pour, spreads their heat on the bottom copper as TI's 4-layer thermal
# model has it (SLVSF66A section 10.1: maximize the copper attached to the thermal pad; routing
# review F15). The VBAT pour flows round it to the VM vias by pin 11.
HEAT_GROW = 0.3  # mm round the exposed pad


def heat_islands() -> list[str]:
    made = []
    for z in list(B.Zones()):
        if z.GetZoneName().startswith("heat "):
            remove(z)
    for ref in BRIDGES:
        f = B.FindFootprintByReference(ref)
        ep = max((p for p in f.Pads() if p.GetNetname() == "GND"), key=lambda p: p.GetEffectivePolygon(F).Area())
        bb = ep.GetEffectivePolygon(F).BBox()
        (x0, y0), (x1, y1) = xy(bb.GetOrigin()), xy(bb.GetEnd())
        g = HEAT_GROW
        z = pcbnew.ZONE(B)
        z.SetLayer(BK)
        z.SetNet(net("GND"))
        o = z.Outline()
        o.NewOutline()
        for x, y in ((x0 - g, y0 - g), (x1 + g, y0 - g), (x1 + g, y1 + g), (x0 - g, y1 + g)):
            o.Append(mm(x), mm(y))
        z.SetZoneName(f"heat {ref}")
        z.SetAssignedPriority(2)  # over the VBAT pour (1)
        z.SetLocalClearance(mm(0.2))
        z.SetMinThickness(mm(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        B.Add(z)
        made.append(ref)
    return made


# Ground stitching (routing review F10, R12): every point where both outer layers are poured with
# ground within STITCH_REACH of a ground via or through-hole ground pad, which at 2.4 GHz is a
# twentieth of a wavelength (TI SZZA009 section 2.4.2: lambda/20 for a stitching pitch), and every
# island of outer ground pour with at least two. A stitching via goes where all four layers are
# ground round it (its pad inside the ground fill of each), so it cuts no other net's pour or plane,
# In2.Cu's islands and hops included, and keeps clear of every pad and hole; an island of F.Cu
# ground over the B.Cu VBAT pour, which has no such spot, takes its two through that pour. The antenna notch (spec [antenna_notch])
# gets a fence along its inner walls (ESP32-C5 Hardware Design Guidelines: dense ground vias near
# the antenna), 0.4 mm from the cut and 1.6-1.75 mm apart: along the inner wall (x -39.7) from in
# front of the antenna's open end to the tab, and along the tab's wall over the notch (y +6.5); the
# module's ground edge (pins 46-60, beside the antenna's feed) carries a via under each of its pads.
STITCH_REACH = 3.0  # mm
STITCH_STEP = 0.25  # mm between candidate spots
STITCH_SAMPLE = 0.5  # mm between the pours' sample points
STITCH_HOLE_GAP = 0.45  # mm from a stitching via's hole to a pad's hole (JLC hole to hole 0.45 mm)
STITCH_VIA_GAP = 0.25  # mm from a stitching via's hole to another via's (rules/jlcpcb.kicad_dru 0.2 mm)
STITCH_PAD_GAP = 0.05  # mm from a stitching via's hole to a ground pad: never a via in a pad
STITCH_ISLAND = 2.0  # mm2: smaller islands are left as they are
NOTCH_FENCE = [  # robot frame
    *[(-39.7, y) for y in (-8.25, -6.5, -4.75, -3.0, -1.25, 0.5, 2.25, 4.0, 5.65)],
    *[(x, 6.5) for x in (-45.6, -44.0, -42.4, -40.8)],
]


def _ground_fill(layer) -> pcbnew.SHAPE_POLY_SET:
    s = pcbnew.SHAPE_POLY_SET()
    for z in B.Zones():
        if z.GetNetname() == "GND" and not z.GetIsRuleArea() and z.IsOnLayer(layer):
            s.BooleanAdd(z.GetFilledPolysList(layer))
    s.Simplify()
    return s


def _parts(s: pcbnew.SHAPE_POLY_SET) -> list:
    """Each outline of s with its holes, and its bounding box (mm)."""
    out = []
    for i in range(s.OutlineCount()):
        one = pcbnew.SHAPE_POLY_SET()
        one.AddOutline(s.Outline(i))
        for h in range(s.HoleCount(i)):
            one.AddHole(s.CHole(i, h))
        bb = one.BBox()
        out.append((one, (*xy(bb.GetOrigin()), *xy(bb.GetEnd())), one.Area() / 1e12))
    return out


def _find(parts: list, c) -> int | None:
    v = pt(*c)
    for k, (one, (x0, y0, x1, y1), _a) in enumerate(parts):
        if x0 <= c[0] <= x1 and y0 <= c[1] <= y1 and one.Contains(v):
            return k
    return None


def _disk(c, r: float) -> pcbnew.SHAPE_POLY_SET:
    s = pcbnew.SHAPE_POLY_SET()
    s.NewOutline()
    for k in range(24):
        a = 2 * math.pi * k / 24
        s.Append(
            mm(c[0] + r * math.cos(a) / math.cos(math.pi / 24)), mm(c[1] + r * math.sin(a) / math.cos(math.pi / 24))
        )
    return s


def stitch() -> tuple[int, list[str]]:
    """Ground stitching vias, the power vias' size first, then the signals' where those do not fit;
    returns how many were added and the points and islands left short."""
    n, _ = _stitch(VIA_D, VIA_HOLE)
    m, short = _stitch(ESCAPE_D, ESCAPE_HOLE)
    return n + m, short


def _stitch(d: float, hole: float) -> tuple[int, list[str]]:
    import heapq
    from collections import defaultdict

    # the fills KiCad's DRC leaves (kicad-cli, under the .kicad_dru) when the board carries them:
    # pcbnew's own filler drops islands it cannot see joined through a pad's relief
    if not all(z.IsFilled() for z in B.Zones() if not z.GetIsRuleArea()):
        B.BuildConnectivity()
        pcbnew.ZONE_FILLER(B).Fill(B.Zones())
    r = d / 2
    fills = {L: _ground_fill(L) for L in (F, BK, IN1, IN2)}
    vbat = pcbnew.SHAPE_POLY_SET()  # the board-wide VBAT pour on B.Cu, as `keep` reaches round it
    vbat_pours = [z for z in board_pours() if z.GetNetname() == "VBAT"]

    # where a via of this size keeps CU_GAP from every other net's copper on every layer, inside the
    # board's edge clearance; `loose` also lets it through the B.Cu VBAT pour
    err = mm(0.005)
    keep = mm(r + CU_GAP)
    other = pcbnew.SHAPE_POLY_SET()
    for t in B.GetTracks():
        if t.GetNetname() != "GND":
            for L in (F, BK, IN1, IN2):
                if t.IsOnLayer(L):
                    t.TransformShapeToPolygon(other, L, keep, err, pcbnew.ERROR_OUTSIDE)
    for f in B.GetFootprints():
        for p in f.Pads():
            if p.GetNetname() != "GND":
                for L in (F, BK, IN1, IN2):
                    if p.IsOnLayer(L) and p.FlashLayer(L):
                        p.TransformShapeToPolygon(other, L, keep, err, pcbnew.ERROR_OUTSIDE)
    pour = pcbnew.SHAPE_POLY_SET()
    for z in B.Zones():
        if z.GetIsRuleArea() or z.GetNetname() == "GND":
            continue
        for L in (F, BK, IN1, IN2):
            if z.IsOnLayer(L):
                s = z.GetFilledPolysList(L).CloneDropTriangulation()
                s.Inflate(keep, pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, err)
                (vbat if z in vbat_pours else pour).BooleanAdd(s)
    loose = board_outline().CloneDropTriangulation()
    loose.Deflate(mm(r + 0.2), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, err)
    loose.BooleanSubtract(other)
    loose.BooleanSubtract(pour)
    legal = loose.CloneDropTriangulation()
    legal.BooleanSubtract(vbat)
    forbid = pcbnew.SHAPE_POLY_SET()  # the ground pads, and every hole's reach
    anchors = []
    for f in B.GetFootprints():
        for p in f.Pads():
            for L in (F, BK):
                if p.IsOnLayer(L) and p.GetNetname() == "GND":
                    g = p.GetEffectivePolygon(L).CloneDropTriangulation()
                    g.Inflate(mm(hole / 2 + STITCH_PAD_GAP), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, err)
                    forbid.BooleanAdd(g)
            if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                dh = max(p.GetDrillSize().x, p.GetDrillSize().y) / 2e6
                forbid.BooleanAdd(_disk(xy(p.GetPosition()), dh + STITCH_HOLE_GAP + hole / 2))
                if p.GetNetname() == "GND" and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                    anchors.append(xy(p.GetPosition()))
    for t in B.GetTracks():
        if t.GetClass() == "PCB_VIA":
            forbid.BooleanAdd(_disk(xy(t.GetPosition()), t.GetDrillValue() / 2e6 + STITCH_VIA_GAP + hole / 2))
            if t.GetNetname() == "GND":
                anchors.append(xy(t.GetPosition()))
    legal.BooleanSubtract(forbid)
    loose.BooleanSubtract(forbid)
    spots = _parts(legal)

    def ok(c) -> bool:
        return _find(spots, c) is not None

    isl = {L: _parts(fills[L]) for L in (F, BK)}
    points = []  # (x, y, layer, island)
    for L in (F, BK):
        for k, (one, (x0, y0, x1, y1), area) in enumerate(isl[L]):
            if area < STITCH_ISLAND:
                continue
            x = x0
            while x <= x1:
                y = y0
                while y <= y1:
                    v = pt(x, y)
                    if one.Contains(v) and fills[BK if L == F else F].Contains(v):
                        points.append((x, y, L, k))
                    y += STITCH_SAMPLE
                x += STITCH_SAMPLE

    def grid(parts):
        out = []  # (x, y, F island, B island)
        for one, (x0, y0, x1, y1), _a in parts:
            x = math.ceil(x0 / STITCH_STEP) * STITCH_STEP
            while x <= x1:
                y = math.ceil(y0 / STITCH_STEP) * STITCH_STEP
                while y <= y1:
                    if one.Contains(pt(x, y)):
                        out.append((x, y, _find(isl[F], (x, y)), _find(isl[BK], (x, y))))
                    y += STITCH_STEP
                x += STITCH_STEP
        return out

    cands = grid(spots)
    n_strict = len(cands)
    cands += [c for c in grid(_parts(loose)) if c[3] is None]  # over the VBAT pour: islands' second via only

    anchor_of = {F: defaultdict(list), BK: defaultdict(list)}

    def anchor(c, kf=None, kb=None):
        for L, k in ((F, kf), (BK, kb)):
            k = _find(isl[L], c) if k is None else k
            if k is not None:
                anchor_of[L][k].append(c)

    for a in anchors:
        anchor(a)
    placed = []
    dead = set()

    def add(j):
        x, y, kf, kb = cands[j]
        via("GND", x, y, d, hole)
        placed.append((x, y))
        anchor((x, y), kf, kb)
        for i in near_c[(int(x // cell), int(y // cell))]:
            if math.dist(cands[i][:2], (x, y)) < hole + STITCH_VIA_GAP:
                dead.add(i)

    cell = STITCH_REACH
    near_c = defaultdict(list)
    for j, c in enumerate(cands):
        bx, by = int(c[0] // cell), int(c[1] // cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                near_c[(bx + dx, by + dy)].append(j)
    # the fence first
    for q in NOTCH_FENCE:
        c = robot(*q)
        j = min(range(len(cands)), key=lambda i: math.dist(cands[i][:2], c), default=None)
        if j is not None and math.dist(cands[j][:2], c) < 0.2 and j not in dead:
            add(j)

    def covered(p) -> bool:
        return any(math.dist(p[:2], a) <= STITCH_REACH for a in anchor_of[p[2]][p[3]])

    open_ = {i for i, p in enumerate(points) if not covered(p)}
    reach = defaultdict(list)  # candidate -> open points it covers
    by_point = defaultdict(list)
    for i in open_:
        x, y, L, k = points[i]
        for j in near_c[(int(x // cell), int(y // cell))]:
            c = cands[j]
            if j < n_strict and (c[2] if L == F else c[3]) == k and math.dist(c[:2], (x, y)) <= STITCH_REACH:
                reach[j].append(i)
                by_point[i].append(j)
    count = {j: len(v) for j, v in reach.items()}
    heap = [(-n, j) for j, n in count.items()]
    heapq.heapify(heap)
    while heap:
        n, j = heapq.heappop(heap)
        if j in dead or -n != count[j]:
            if j not in dead and count[j] > 0:
                heapq.heappush(heap, (-count[j], j))
            continue
        if count[j] == 0:
            break
        add(j)
        for i in reach[j]:
            if i in open_:
                open_.discard(i)
                for j2 in by_point[i]:
                    count[j2] -= 1
    # at least two per island; one in any smaller pocket that joins a ground pad or track, which the
    # pour reached through a pad's relief or not at all
    joins = {L: set() for L in (F, BK)}
    for L in (F, BK):
        for f in B.GetFootprints():
            for p in f.Pads():
                if p.GetNetname() == "GND" and p.IsOnLayer(L):
                    g = p.GetEffectivePolygon(L)
                    joins[L].update(k for k, (one, _bb, _a) in enumerate(isl[L]) if one.Collide(g))
        for t in B.GetTracks():
            if t.GetNetname() == "GND" and t.GetClass() != "PCB_VIA" and t.GetLayer() == L:
                for c in (t.GetStart(), t.GetEnd()):
                    k = _find(isl[L], xy(c))
                    if k is not None:
                        joins[L].add(k)
    for L in (F, BK):
        for k, (_one, _bb, area) in enumerate(isl[L]):
            need = 2 if area >= STITCH_ISLAND else (1 if k in joins[L] else 0)
            while len(anchor_of[L][k]) < need:
                mine = [j for j, c in enumerate(cands) if j not in dead and (c[2] if L == F else c[3]) == k]
                if not mine:
                    break
                have = anchor_of[L][k]
                add(max(mine, key=lambda j: min((math.dist(cands[j][:2], a) for a in have), default=0)))
    left = [f"{GROUND_LAYERS[points[i][2]]} ({OY - points[i][1]:.1f}, {OX - points[i][0]:.1f})" for i in sorted(open_)]
    short = [
        f"{GROUND_LAYERS[L]} island at ({OY - (bb[1] + bb[3]) / 2:.1f}, {OX - (bb[0] + bb[2]) / 2:.1f}), "
        f"{area:.1f} mm2: {len(anchor_of[L][k])} via(s)"
        for L in (F, BK)
        for k, (_one, bb, area) in enumerate(isl[L])
        if area >= STITCH_ISLAND and len(anchor_of[L][k]) < 2
    ]
    return len(placed), left + short


# What stitching cannot reach goes (routing review F10: remove the islands that cannot take their
# vias): an island of outer ground pour that takes fewer than two vias, and the part of an island,
# where both outer layers are ground, farther than STITCH_PRUNE from every via, are cut out by a
# pour keep-out on that layer; in the latter the pour round each ground pad and track stays, and
# none is cut where it is a pad's only way to ground (PRUNE_SPARE). A single-via island 12-15 mm long resonates
# near 2.4 GHz.
STITCH_PRUNE = 3.8  # mm: under the layout test's 4.0 mm
PRUNE_MIN = 0.1  # mm2: smaller slivers are left to the fill's own minimum width
PRUNED = "no pour: unstitched"
# ground pads whose only way to ground is pour that pruning would cut (robot frame): the pour within
# PRUNE_SPARE_R of them stays
PRUNE_SPARE = {"C72.1": (-2.28, 9.3), "C8.1": (38.64, -6.16)}
PRUNE_SPARE_R = 4.5  # mm
PRUNE_RING = 0.6  # mm of pour kept round each ground pad and track: its relief or solid join


def _keepout(layer, piece: pcbnew.SHAPE_POLY_SET) -> None:
    z = pcbnew.ZONE(B)
    z.SetIsRuleArea(True)
    z.SetLayer(layer)
    z.SetDoNotAllowZoneFills(True)
    z.SetDoNotAllowTracks(False)
    z.SetDoNotAllowVias(False)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    z.SetZoneName(PRUNED)
    o = z.Outline()
    for i in range(piece.OutlineCount()):
        o.NewOutline()
        c = piece.Outline(i)
        for k in range(c.PointCount()):
            o.Append(c.CPoint(k).x, c.CPoint(k).y)
    B.Add(z)


def unprune() -> int:
    """Remove the pour keep-outs prune() made (before stitching again on fresh fills)."""
    gone = [z for z in B.Zones() if z.GetIsRuleArea() and z.GetZoneName() == PRUNED]
    for z in gone:
        remove(z)
    return len(gone)


def prune() -> int:
    """Pour keep-outs over the ground KiCad's fills leave unstitched; returns how many were added
    (the board must carry KiCad's fills: run after `kicad-cli pcb drc --refill-zones --save-board`)."""
    anchors = [t.GetPosition() for t in B.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"]
    anchors += [
        p.GetPosition()
        for f in B.GetFootprints()
        for p in f.Pads()
        if p.GetNetname() == "GND" and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
    ]
    fills = {L: _ground_fill(L) for L in (F, BK)}
    joins = {L: pcbnew.SHAPE_POLY_SET() for L in (F, BK)}  # a ground pad's or track's own copper
    for L in (F, BK):
        for f in B.GetFootprints():
            for p in f.Pads():
                if p.GetNetname() == "GND" and p.IsOnLayer(L):
                    joins[L].BooleanAdd(p.GetEffectivePolygon(L))
        for t in B.GetTracks():
            if t.GetNetname() == "GND" and t.GetClass() != "PCB_VIA" and t.GetLayer() == L:
                t.TransformShapeToPolygon(joins[L], L, 0, mm(0.005), pcbnew.ERROR_OUTSIDE)
        joins[L].Inflate(mm(PRUNE_RING), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, mm(0.005))
    made = 0
    for L, other in ((F, BK), (BK, F)):
        for one, _bb, area in _parts(fills[L]):
            if area < STITCH_ISLAND:
                continue
            mine = [a for a in anchors if one.Contains(a)]
            cut = one.CloneDropTriangulation()
            if len(mine) >= 2:
                cut.BooleanIntersection(fills[other])
                for a in mine:
                    cut.BooleanSubtract(_disk(xy(a), STITCH_PRUNE))
                cut.BooleanSubtract(joins[L])  # the pour round each ground pad and track stays
            for q in PRUNE_SPARE.values():
                cut.BooleanSubtract(_disk(robot(*q), PRUNE_SPARE_R))
            cut.Simplify()
            for piece, _b, a in _parts(cut):
                if a >= PRUNE_MIN:
                    piece.Inflate(mm(0.05), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, mm(0.005))
                    _keepout(L, piece)
                    made += 1
    return made


def teardrops() -> int:
    """Teardrops enabled on every pad and via; KiCad draws them when it refills the zones
    (`kicad-cli pcb drc --refill-zones --save-board`). Returns the items enabled."""
    n = 0
    for t in B.GetTracks():
        if t.GetClass() == "PCB_VIA":
            t.SetTeardropsEnabled(True)
            n += 1
    for f in B.GetFootprints():
        for p in f.Pads():
            p.SetTeardropsEnabled(True)
            n += 1
    return n


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
    print(f"pads joined solid: {relief()}", flush=True)
    print("heat islands under:", *heat_islands(), flush=True)
    n, short = stitch()
    print(f"stitching vias: {n}", *short, sep="\n  ", flush=True)
    pcbnew.ZONE_FILLER(B).Fill(B.Zones())
    print(f"unstitched pour cut out: {prune()}", flush=True)
    print(f"teardrops enabled on: {teardrops()} pads and vias", flush=True)
    pcbnew.ZONE_FILLER(B).Fill(B.Zones())
    B.Save(str(PCB))
    return 0


if __name__ == "__main__":
    sys.exit(main())
