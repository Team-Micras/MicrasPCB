"""Layout of the main board's design review fixes, as a one-off pcbnew script (KiCad 10).

    python3 boards/main/layout/fixes.py

Runs once on the layout as the footprint update left it (`pcb layout --sync-footprints` on the
previous revision's placement and routing, see boards/main/previous/, then `make gen` for the
0402 ferrite bead FB1 and the trimmed USB-C ground pads of U2), then `pcb layout` syncs the
result. Every coordinate is KiCad millimetres on the board's frame (spec/main.toml [kicad]); the
UUID prefixes name items of that starting layout. The steps, in order: the board outline and the
encoder slots, the power mux U4, the new parts' placement, the copper the changed nets contradict,
the courtyard spacing, the silkscreen, the plane vias of the new parts, then router.py joins what
is left unconnected, net by net in ROUTES order.

    python3 boards/main/layout/fixes.py --no-sync     # skip the `pcb layout` sync
    python3 boards/main/layout/fixes.py --no-routes   # placement and hand copper only
"""

from __future__ import annotations

import itertools
import math
import subprocess
import sys
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[3]
LAYOUT = ROOT / "boards/main/layout/main.kicad_pcb"

B: pcbnew.BOARD = None  # the board being edited
F, BK, IN1, IN2 = pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu
LAYERS = {"F": pcbnew.F_Cu, "B": pcbnew.B_Cu, "In1": pcbnew.In1_Cu, "In2": pcbnew.In2_Cu}


# --- helpers -------------------------------------------------------------------------------------


def mm(v: float) -> int:
    return pcbnew.FromMM(v)


def pt(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x), mm(y))


def xy(p) -> tuple[float, float]:
    return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)


def net(name: str) -> pcbnew.NETINFO_ITEM:
    n = B.FindNet(name)
    if n is None:
        raise SystemExit(f"no net {name}")
    return n


def fp(ref: str) -> pcbnew.FOOTPRINT:
    f = B.FindFootprintByReference(ref)
    if f is None:
        raise SystemExit(f"no footprint {ref}")
    return f


def pad(ref: str, num: str) -> pcbnew.PAD:
    for p in fp(ref).Pads():
        if p.GetNumber() == num:
            return p
    raise SystemExit(f"no pad {ref}.{num}")


def padxy(ref: str, num: str) -> tuple[float, float]:
    return xy(pad(ref, num).GetPosition())


def place(ref: str, x: float, y: float, rot: float) -> None:
    f = fp(ref)
    f.SetOrientation(pcbnew.EDA_ANGLE(rot, pcbnew.DEGREES_T))
    f.SetPosition(pt(x, y))


def track(netname: str, layer: str, width: float, *pts) -> None:
    """A chain of straight segments through pts (each an (x, y) or a 'ref.pad' string)."""
    q = [padxy(*p.split(".", 1)) if isinstance(p, str) else p for p in pts]
    for a, b in itertools.pairwise(q):
        if math.dist(a, b) < 1e-6:
            continue
        t = pcbnew.PCB_TRACK(B)
        t.SetStart(pt(*a))
        t.SetEnd(pt(*b))
        t.SetWidth(mm(width))
        t.SetLayer(LAYERS[layer])
        t.SetNet(net(netname))
        B.Add(t)


def via(netname: str, x: float, y: float, size: float = 0.45, drill: float = 0.3) -> None:
    v = pcbnew.PCB_VIA(B)
    v.SetPosition(pt(x, y))
    v.SetWidth(mm(size))
    v.SetDrill(mm(drill))
    v.SetLayerPair(F, BK)
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetNet(net(netname))
    v.SetFrontTentingMode(pcbnew.TENTING_MODE_TENTED)
    v.SetBackTentingMode(pcbnew.TENTING_MODE_TENTED)
    B.Add(v)


def items(uuids: list[str]) -> list:
    """Tracks, vias and zones by UUID prefix (each prefix must match exactly one item)."""
    found = []
    pool = list(B.GetTracks()) + list(B.Zones()) + list(B.GetDrawings())
    for u in uuids:
        m = [i for i in pool if i.m_Uuid.AsString().startswith(u)]
        if len(m) != 1:
            raise SystemExit(f"uuid {u}: {len(m)} matches")
        found.append(m[0])
    return found


GRAVEYARD = []  # removed items stay referenced: their SWIG proxies do not own them


def drop(objs: list) -> None:
    for o in objs:
        GRAVEYARD.append(o)
        B.Remove(o)


def is_teardrop(z) -> bool:
    return z.GetAssignedPriority() >= 100


def teardrops_at(item) -> list:
    """The teardrop zones (plain zones of priority 100 and up, see previous/transfer_layout.py)
    that sit on a track's ends or a via."""
    if item.GetClass() == "PCB_VIA":
        ends, layers = [item.GetPosition()], [F, BK, IN1, IN2]
    else:
        ends, layers = [item.GetStart(), item.GetEnd()], [item.GetLayer()]
    out = []
    for z in B.Zones():
        if not is_teardrop(z) or z.GetNetCode() != item.GetNetCode():
            continue
        if not any(z.IsOnLayer(lay) for lay in layers):
            continue
        outline = z.Outline()
        if any(outline.Contains(e, -1, mm(0.02)) for e in ends):
            out.append(z)
    return out


def remove(objs: list) -> None:
    """Remove tracks/vias with the teardrops on them, and any other listed item."""
    gone = set()
    for o in objs:
        if o.GetClass() in ("PCB_TRACK", "PCB_VIA", "PCB_ARC"):
            for z in teardrops_at(o):
                if z.m_Uuid.AsString() not in gone:
                    gone.add(z.m_Uuid.AsString())
                    drop([z])
        if o.m_Uuid.AsString() not in gone:
            gone.add(o.m_Uuid.AsString())
            drop([o])


def tracks_where(netname: str | None = None, box=None, layer: str | None = None, vias: bool = True) -> list:
    """Tracks (and vias) of a net, with an end (or the via) inside box (x0, y0, x1, y1)."""
    out = []
    for t in B.GetTracks():
        if netname is not None and t.GetNetname() != netname:
            continue
        is_via = t.GetClass() == "PCB_VIA"
        if is_via and not vias:
            continue
        if layer is not None and not is_via and t.GetLayer() != LAYERS[layer]:
            continue
        if layer is not None and is_via:
            continue
        ends = [t.GetPosition()] if is_via else [t.GetStart(), t.GetEnd()]
        if box is None or any(box[0] <= xy(e)[0] <= box[2] and box[1] <= xy(e)[1] <= box[3] for e in ends):
            out.append(t)
    return out


def renet(objs: list, netname: str) -> None:
    """Move tracks/vias/zones (and the teardrops on tracks and vias) to another net."""
    n = net(netname)
    for o in objs:
        if o.GetClass() in ("PCB_TRACK", "PCB_VIA", "PCB_ARC"):
            for z in teardrops_at(o):
                z.SetNet(n)
        o.SetNet(n)


def zone(netname: str, layer: str, pts: list, priority: int) -> None:
    """A solid copper pour with the board's pour settings (0.1 mm clearance, 0.25 mm minimum width,
    pads connected solid, as the previous revision's pours)."""
    z = pcbnew.ZONE(B)
    z.SetLayer(LAYERS[layer])
    z.SetNet(net(netname))
    o = z.Outline()
    o.NewOutline()
    for p in pts:
        o.Append(mm(p[0]), mm(p[1]))
    z.SetAssignedPriority(priority)
    z.SetLocalClearance(mm(0.1))
    z.SetMinThickness(mm(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    B.Add(z)


VIA_D, VIA_HOLE = 0.45, 0.3
CU_GAP = 0.2  # via and fan-out track to other nets: the JLCPCB via-hole-to-track rule with margin
_outline = None


def _board_outline() -> pcbnew.SHAPE_POLY_SET:
    global _outline
    if _outline is None:
        _outline = pcbnew.SHAPE_POLY_SET()
        B.GetBoardPolygonOutlines(_outline, True)
    return _outline


_edges = None


def _edge_segments() -> list:
    global _edges
    if _edges is None:
        chains = [_board_outline().Outline(0)]
        chains += [_board_outline().Hole(0, h) for h in range(_board_outline().HoleCount(0))]
        _edges = [ch.CSegment(i) for ch in chains for i in range(ch.SegmentCount())]
    return _edges


def _near(items_, c, r):
    """Items whose bounding box comes within r mm of point c."""
    out = []
    for i in items_:
        bb = i.GetBoundingBox()
        x0, y0 = xy(bb.GetOrigin())
        x1, y1 = xy(bb.GetEnd())
        if x0 - r <= c[0] <= x1 + r and y0 - r <= c[1] <= y1 + r:
            out.append(i)
    return out


def via_spot_ok(c, netname: str, own_pad, seg_from=None, plane=None) -> bool:
    """A through via of `netname` at c (and a fan-out track from seg_from to c) keeps clear of
    every other net on the outer layers, of every other hole, and of any pad but its own; with
    `plane` = (layer, net), the inner-layer pour of that net covers c."""
    centre = pt(*c)
    if not _board_outline().Contains(centre, -1, 0):
        return False
    # keep VIA_D/2 + 0.25 from the edge (outline and cut-outs)
    if any(s.Distance(centre) < mm(VIA_D / 2 + 0.25) for s in _edge_segments()):
        return False
    circle = pcbnew.SHAPE_CIRCLE(centre, mm(VIA_D / 2))
    seg = None
    if seg_from is not None:
        seg = pcbnew.SHAPE_SEGMENT(pt(*seg_from), centre, mm(0.25))
    for f in B.GetFootprints():
        for p in _near(f.Pads(), c, 2.0):
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
                if seg is not None and layer == F and not same and shape.Collide(seg, mm(0.12)):
                    return False
    for t in _near(B.GetTracks(), c, 2.0):
        same = t.GetNetname() == netname
        if t.GetClass() == "PCB_VIA":
            if math.dist(xy(t.GetPosition()), c) < VIA_D + 0.2:
                return False
            continue
        if same:
            continue
        if t.GetLayer() not in (F, BK):
            if t.GetEffectiveShape(t.GetLayer()).Collide(circle, mm(0.2)):
                return False
            continue
        if t.GetEffectiveShape(t.GetLayer()).Collide(circle, mm(CU_GAP)):
            return False
        if seg is not None and t.GetLayer() == F and t.GetEffectiveShape(F).Collide(seg, mm(0.12)):
            return False
    for z in _near(B.Zones(), c, 2.0):
        if z.GetNetname() == netname or z.GetIsRuleArea():
            continue
        for layer in (F, BK):
            if z.IsOnLayer(layer) and z.GetFilledPolysList(layer).Collide(circle, mm(0.1)):
                # a pour of another net: the via would only be cleared out of it if the pour
                # is a plane; on the outer layers keep off the pour's copper
                return False
            if seg is not None and layer == F and z.IsOnLayer(F) and z.GetFilledPolysList(F).Collide(seg, mm(0.1)):
                return False
    if plane is not None:
        layer, pnet = plane
        if not any(
            z.GetNetname() == pnet
            and z.IsOnLayer(LAYERS[layer])
            and z.GetFilledPolysList(LAYERS[layer]).Contains(centre)
            for z in _near(B.Zones(), c, 0.5)
        ):
            return False
    return True


def fanout(ref: str, num: str, plane: str | None = None, rmin: float = 0.55, rmax: float = 1.8) -> tuple[float, float]:
    """A via next to a pad, on the nearest clear spot, with a 0.25 mm track to the pad centre.
    `plane`: the inner layer whose pour of the pad's net the via must land on (In1 for GND)."""
    p = pad(ref, num)
    n = p.GetNetname()
    c0 = xy(p.GetPosition())
    pl = None
    if plane is not None:
        pl = (plane, n)
    r = rmin
    while r <= rmax + 1e-9:
        steps = 24
        for k in range(steps):
            a = 2 * math.pi * k / steps
            c = (round(c0[0] + r * math.cos(a), 3), round(c0[1] + r * math.sin(a), 3))
            if via_spot_ok(c, n, p, seg_from=c0, plane=pl):
                track(n, "F", 0.25, c0, c)
                via(n, *c)
                return c
        r += 0.05
    raise SystemExit(f"fanout {ref}.{num}: no via spot within {rmax} mm")


def nudge(ref: str, dx: float, dy: float) -> None:
    """Move a part by (dx, dy) and its copper with it: the ends of tracks and the vias on its pads
    follow, the teardrops on its pads go."""
    f = fp(ref)
    pads = list(f.Pads())
    for t in list(B.GetTracks()):
        if t.GetClass() == "PCB_VIA":
            continue
        for get, put in ((t.GetStart, t.SetStart), (t.GetEnd, t.SetEnd)):
            if any(
                p.GetNetCode() == t.GetNetCode() and p.GetEffectiveShape(t.GetLayer()).Collide(get(), 0)
                for p in pads
                if p.IsOnLayer(t.GetLayer())
            ):
                x, y = xy(get())
                put(pt(x + dx, y + dy))
    gone = []
    for z in B.Zones():
        if is_teardrop(z) and any(
            p.GetNetCode() == z.GetNetCode() and z.Outline().Collide(p.GetPosition(), mm(0.6)) for p in pads
        ):
            gone.append(z)
    drop(gone)
    x, y = xy(f.GetPosition())
    f.SetPosition(pt(x + dx, y + dy))


def in_box(item, box) -> bool:
    ends = [item.GetPosition()] if item.GetClass() == "PCB_VIA" else [item.GetStart(), item.GetEnd()]
    return all(box[0] <= xy(e)[0] <= box[2] and box[1] <= xy(e)[1] <= box[3] for e in ends)


# --- outline --------------------------------------------------------------------------------------

# 1-10 nm Edge.Cuts lines between outline arcs and lines, left by the Altium conversion
# (KiCad DRC invalid_outline): each is removed and its neighbours joined at one point.
TINY_EDGES = ["c351aa03", "c8113230", "f067f998", "a07bf7ad", "30e9e1b9", "ad6a194c"]

# The encoder slots of spec/main.toml [encoder_slots]: 5.8 x 1.0 mm, R0.5 ends, long along the
# KiCad y axis, centred on the EncoderSlot footprints.
SLOT_RECTS = [
    ["99766d22", "71d048d5", "a3ea20a4", "d2b2cc52"],  # EC2, x 141.151105-142.051105
    ["7e342c76", "b225b7aa", "7f0da1b4", "bc70c4df"],  # EC1, x 154.951105-155.851105
]


def outline() -> None:
    tiny = items(TINY_EDGES)
    joins = [(xy(t.GetStart()), xy(t.GetEnd())) for t in tiny]
    drop(tiny)
    for a, b in joins:  # the shapes that ended on b now end on a
        for d in B.GetDrawings():
            if d.GetLayer() != pcbnew.Edge_Cuts:
                continue
            if math.dist(xy(d.GetStart()), b) < 1e-4:
                d.SetStart(pt(*a))
            if math.dist(xy(d.GetEnd()), b) < 1e-4:
                d.SetEnd(pt(*a))
    # the silkscreen brackets at the slot ends: their legs stop clear of the longer slots
    for leg in items(["957c25a8", "400c69d2", "f2eaeae5", "d66f3859"]):
        leg.SetStart(pt(xy(leg.GetStart())[0], 110.55))
    for leg in items(["cbe2c0ed", "2e6a0efa", "b8620878", "f4388c6d"]):
        leg.SetEnd(pt(xy(leg.GetEnd())[0], 116.457))
    s = spec_slot()
    for rect in SLOT_RECTS:
        lines = items(rect)
        xs = [xy(p)[0] for d in lines for p in (d.GetStart(), d.GetEnd())]
        cx = (min(xs) + max(xs)) / 2
        drop(lines)
        cy = s["cy"]
        half, r = s["length"] / 2, s["width"] / 2
        y0, y1 = cy - half + r, cy + half - r
        for x in (cx - r, cx + r):
            seg = pcbnew.PCB_SHAPE(B, pcbnew.SHAPE_T_SEGMENT)
            seg.SetStart(pt(x, y0))
            seg.SetEnd(pt(x, y1))
            seg.SetLayer(pcbnew.Edge_Cuts)
            seg.SetWidth(mm(0.05))
            B.Add(seg)
        for yc, sign in ((y0, -1), (y1, 1)):
            arc = pcbnew.PCB_SHAPE(B, pcbnew.SHAPE_T_ARC)
            arc.SetArcGeometry(pt(cx - r, yc), pt(cx, yc + sign * r), pt(cx + r, yc))
            arc.SetLayer(pcbnew.Edge_Cuts)
            arc.SetWidth(mm(0.05))
            B.Add(arc)


def encoder_pads() -> None:
    """The EncoderSlot pads moved out to x = +/-1.21 mm: the tracks that ended on their old centres
    (nearer the slot) end on the new ones."""
    for ref in ("EC1", "EC2"):
        for p in fp(ref).Pads():
            box = p.GetBoundingBox()
            for t in B.GetTracks():
                if t.GetClass() == "PCB_VIA" or t.GetLayer() != F or t.GetNetCode() != p.GetNetCode():
                    continue
                for get, put in ((t.GetStart, t.SetStart), (t.GetEnd, t.SetEnd)):
                    if box.Contains(get()) and get() != p.GetPosition():
                        put(p.GetPosition())
    # Encoder_Right_ABI_B passes under EC1's slot end: 0.03 mm further from it
    for t in tracks_where("Encoder_Right_ABI_B", (154.8, 116.6, 156.1, 116.8), "F", vias=False):
        for get, put in ((t.GetStart, t.SetStart), (t.GetEnd, t.SetEnd)):
            x, y = xy(get())
            if abs(y - 116.730) < 0.01:
                put(pt(x, 116.76))


def spec_slot() -> dict:
    sys.path.insert(0, str(ROOT / "tools"))
    from micras_pcb import spec

    s = spec.load("main")
    e = s["encoder_slots"]
    return {"cy": s["kicad"]["origin_y"], "length": e["length"], "width": e["width"]}


# --- power mux U4 and VSYS (review C3) ------------------------------------------------------------


def power_mux() -> None:
    """U4 (TPS2121) where the removed USB LDO U3 sat, in front of the buck IC7.

    IN2 (+5V) takes the 0.6 mm +5V feed that came up from the In2.Cu +5V channel for U3; IN1 (VBAT)
    drops through a via to an In2.Cu VBAT finger grown from the VBAT plane under the buck; OUT
    (VSYS) drops through two vias to a B.Cu pour that runs back to the buck's input pour (the
    F.Cu pour of IC7 pins 5/7 with C52/C53, now VSYS) and its six vias.
    """
    # U3's copper: its GND and 3V3 pours, the vias under U4, the +5V feed's last bends
    remove(items(["1d05b808", "1ee1f6e7"]))
    remove(items(["4e2e8c07", "231d6400", "a1d0343a", "0ddb9112", "85339aa8", "38abad7a", "6af53224"]))
    remove(items(["9ebb5470", "e01cca36", "77911bb9", "7e4c9875", "e25bba18"]))

    place("U4", 163.4, 88.3, 0)  # OUT pins 1/8 on top row side, IN2 left, IN1 right
    place("C61", 162.95, 85.55, 270)  # SS
    place("R46", 164.0, 85.55, 270)  # ILM
    place("C62", 164.3, 90.9, 0)  # IN1
    place("C63", 159.9, 88.6, 0)  # IN2

    # +5V: the feed up x = 161.074, C63 on it, into pin 2
    track("+5V", "F", 0.6, (161.074, 92.981), (161.074, 88.65))
    track("+5V", "F", 0.4, (161.074, 88.65), "U4.2")
    track("+5V", "F", 0.4, "C63.2", (161.074, 88.6))
    track("GND", "F", 0.3, "C63.1", (159.6, 88.0), (160.185, 87.139))
    # C57 (3V3 bulk) keeps a via of each net
    track("GND", "F", 0.3, "C57.1", (160.185, 87.139))
    track("3V3", "F", 0.3, "C57.2", (161.5, 84.3))
    via("3V3", 161.5, 84.3)
    # VSYS: a via beside each OUT pin
    track("REGULATORS.VSYS", "F", 0.4, "U4.1", (161.7, 87.75))
    via("REGULATORS.VSYS", 161.7, 87.75)
    track("REGULATORS.VSYS", "F", 0.4, "U4.8", (165.05, 87.95))
    via("REGULATORS.VSYS", 165.05, 87.95)
    # VBAT: via to In2.Cu, C62 beside it
    track("VBAT", "F", 0.4, "U4.7", (164.8, 88.65), (165.05, 89.15))
    via("VBAT", 165.05, 89.15)
    track("VBAT", "F", 0.3, "C62.2", (165.05, 90.9), (165.05, 89.15))
    # GND pins: the bottom row joined, vias below it and beside the top row's two GND pins
    track("GND", "F", 0.2, "U4.3", "U4.6")
    for x in (162.675, 164.175):
        track("GND", "F", 0.25, (x, 89.45), (x, 90.25))
        via("GND", x, 90.25)
    track("GND", "F", 0.25, "C62.1", (164.175, 90.25))
    track("GND", "F", 0.2, "U4.12", (162.25, 86.55))
    via("GND", 162.25, 86.55)
    track("GND", "F", 0.2, "U4.9", (164.7, 86.6))
    via("GND", 164.7, 86.6)
    # soft start and current limit
    track("REGULATORS.MUX_SS", "F", 0.2, "C61.2", "U4.11")
    track("REGULATORS.MUX_ILM", "F", 0.2, "R46.2", "U4.10")
    track("GND", "F", 0.25, "C61.1", (162.4, 84.5))
    via("GND", 162.4, 84.5)
    track("GND", "F", 0.25, "R46.1", "C61.1")

    # In2.Cu: a VBAT finger from the plane under the buck up to the IN1 via
    zone("VBAT", "In2", [(164.45, 88.65), (165.65, 88.65), (165.65, 96.2), (164.45, 96.2)], 29)
    # B.Cu: VSYS from the OUT vias to the buck's input vias
    zone(
        "REGULATORS.VSYS",
        "B",
        [(161.2, 87.2), (165.6, 87.2), (165.6, 90.4), (172.9, 90.4), (172.9, 103.2), (171.6, 104.6), (161.2, 104.6)],
        30,
    )
    # the buck's input pour (IC7 pins 5/7, C52, C53) and its vias leave VBAT
    box = (168.3, 98.5, 173.4, 104.8)
    renet([t for t in tracks_where("VBAT", box) if in_box(t, box)], "REGULATORS.VSYS")
    renet(items(["207a4ad6"]), "REGULATORS.VSYS")


# --- placement ------------------------------------------------------------------------------------


def placement() -> None:
    """Every new part, and the parts that changed size or had to make room. Courtyards do not
    overlap; the wall sensor bodies (User.13 of W1-W4, lying over the board) stay clear."""
    # SWD header: 1x05, one pitch towards the rear so that pad 5 (NRST) and R13 above it clear W1;
    # U5 with C64 in the pocket below it, by the board edge
    place("P1", 126.123, 97.684, 90)
    place("U5", 125.3, 101.35, 90)
    place("C64", 125.3, 103.7, 0)
    # W1: R13 (1206) under W1's LED anode pad; C73 where R11 was (its pad 2 on the gate track),
    # R11 on the PWM track below SW5
    place("R13", 126.5, 84.53, 0)
    place("C73", 131.532, 81.809, 180)
    place("R11", 134.15, 84.65, 270)
    # W2, W3: C74/C75 where R15/R19 were, pad 2 on the gate side; R15/R19 move up their PWM tracks
    place("C74", 137.758, 70.685, 45)
    place("C75", 164.223, 68.347, 135)
    # W4: R25 (1206) below a two-row block of R23/C76 and R26/R24
    place("R25", 165.6, 82.55, 180)
    place("R23", 164.4, 79.765, 180)
    place("C76", 166.4, 79.765, 0)
    place("R26", 164.4, 80.815, 180)
    place("R24", 166.4, 80.815, 0)
    # decoupling at the current amplifiers and encoder slots
    place("C67", 159.9, 117.25, 0)
    place("C68", 157.65, 117.25, 0)
    place("C69", 157.5, 111.0, 0)
    place("C70", 157.5, 110.0, 0)
    place("C71", 139.5, 116.0, 0)
    place("C72", 138.1, 115.7, 90)
    # clamp diodes beside their gates; R15/R19 up their PWM tracks
    place("D9", 131.7, 77.7, 90)
    place("D10", 131.5, 72.9, 90)
    place("D11", 161.5, 75.1, 90)
    place("D12", 159.6, 77.0, 90)
    place("R15", 136.4, 72.6, 0)
    place("R19", 166.0, 71.8, 90)
    place("C26", 130.1, 81.6, 90)
    # buzzer flyback diode below R1/R2
    place("D3", 135.7, 102.0, 90)
    # VDDA ferrite left of IC1, VBUS divider by U4's +5V feed; the battery divider above IC1's
    # top corner: R45 and C59 between the LED_ARGB and Button vias, R44 by C18's VBAT pad
    place("FB1", 148.0, 69.05, 90)
    place("R45", 146.85, 66.25, 270)
    place("C59", 145.75, 65.52, 270)
    place("R44", 149.2, 65.6, 270)
    place("R47", 162.3, 91.3, 0)
    place("R48", 158.6, 87.4, 0)
    # rear: Motors_Enable pull-down by R35, L6205 bulk ceramics by IC5, SBU switch below the
    # right wheel notch, battery switch slew parts by Q6
    place("R49", 127.0, 129.0, 0)
    place("C65", 133.6, 130.9, 0)
    place("C66", 134.6, 128.2, 90)
    place("Q7", 164.2, 127.0, 0)
    place("C58", 164.4, 131.7, 90)
    place("R43", 162.5, 133.7, 90)
    # USB: ESD array and VBUS TVS left of the receptacle, by the SBU fuse
    place("U6", 145.05, 134.75, 0)
    place("D8", 148.3, 133.9, 0)


# --- copper of the changed connections --------------------------------------------------------------


def rework() -> None:
    """Remove the copper that the new connections and footprints contradict, keep and rename what
    still serves; the new connections are routed afterwards (see `routes`)."""
    # Teardrops of the conversion left on a net name the circuit no longer has (Motor_Enable):
    # they sit on 3V3 and signal tracks, so they go.
    remove(items(["2023a6a5", "27ed42a5", "ee4245c8", "a74178a4", "c65b8099", "fd3c0bd0"]))
    # teardrops that leave copper slivers against a twin or a neighbour (C24 pad 2, the SPI_MOSI and
    # SPI_SCK vias by EC2, the ground vias by C18 and by IC3)
    remove(items(["1dd40cdc", "fa2cac55", "ed7c15e9", "0d7b03a6", "77c0bd5b"]))
    # zero-length tracks of the conversion
    drop([t for t in B.GetTracks() if t.GetClass() == "PCB_TRACK" and t.GetStart() == t.GetEnd()])

    # P1 (one half pitch rearwards, 5 pads): SWDIO/SWCLK lose their bends to the old pad places;
    # C26 and R13 leave their old places (vias included); D3 leaves for BZ1's side
    remove(items(["2d19303c", "a931754d", "d860a0af", "cce95ca0", "cc40f657", "b76c3a4a", "bc4cb0d3"]))
    remove(items(["0029a351", "15a27d06", "68146b70", "e2b790b4", "5f75b9bb", "883e58da", "caae30ce", "59ed46c1"]))
    remove(items(["7891dd88", "8d9728d8", "c4a3d392", "b30ac846", "b4499c88", "d2b59759"]))
    remove(items(["4e7191f4", "62b2f596", "76a720b0", "845a6518", "53dc555c", "6b3ac802", "51f0a263"]))
    remove(items(["bcc634ea", "d7bf6376", "7644a99c"]))
    # R3 (1206): the drain track reaches the new pad 1
    track("PERIPHERALS.BUZZER_DRAIN", "F", 0.254, (128.028, 102.105), "R3.1")
    # and the coil track ends at pad 2's centre, not past it
    remove(items(["83ba9499"]))
    items(["fbb71ae2"])[0].SetStart(pt(128.033, 99.892))

    # W1 (review M14): R11.1 drives C73; the old PWM run from R11 to the bend becomes the drive
    # net, R11 sits on the vertical PWM track below SW5
    renet(items(["30888c49", "134021df"]), "SENSORS.WALL0_DRIVE")
    remove(items(["4fb84326"]))
    track("SENSORS.WALL0_DRIVE", "F", 0.254, (134.15, 82.313), "R11.1")
    track("Wall_Sensor_PWM_0", "F", 0.254, "R11.2", (134.15, 86.123))
    # W2: C74 where R15 was, R15 under the PWM via
    remove(items(["122f39ef", "a8609b85", "6b12ffa5", "aff7839f"]))
    track("Wall_Sensor_PWM_1", "F", 0.254, (136.944, 71.899), "R15.2")
    # W3: C75 where R19 was; R19 on the PWM route (routed later)
    remove(items(["7d33b327", "291c87fd", "7c229479", "7ee12d89"]))
    # W4: PWM, gate, ground and LED tracks of the old column
    remove(items(["be05b1b6", "340de70c", "6becb2bf", "7186ada3"]))
    (pwm3,) = items(["f6358b6a"])  # the PWM run along y = 82.821 stops clear of R25 pad 2
    pwm3.SetEnd(pt(163.1, 82.821))
    remove(items(["d4730599", "ef2c93a3", "c888bbbd"]))
    remove(items(["810d0ac9", "a9cf194d", "e5f124e8", "ef02ddda", "161ceed9"]))
    remove(items(["d6e76a59", "c05a1975", "0a273bff", "585b8148", "e12f889a", "23c098c9", "67a30dd4", "585158d0"]))
    track("SENSORS.WALL3_GATE", "F", 0.254, (166.799, 79.275), "C76.2", "R24.2")
    track("SENSORS.WALL3_DRIVE", "F", 0.254, "R23.1", "C76.1")
    track("GND", "F", 0.254, "R26.1", (165.265, 80.789), "R24.1")
    track("SENSORS.WALL3_LED_A", "F", 0.3, "R25.1", "W4.1")
    track("3V3", "F", 0.3, "R25.2", (164.1, 84.0))
    via("3V3", 164.1, 84.0)

    # U1 pin 11 leaves VBAT for Motors_Enable (review C4): VBAT reaches pin 12 alone
    # VBAT reaches pin 12 round the right of a via that takes pin 11 to B.Cu; the 1 mm VBAT
    # trunk below starts lower to leave the via room
    remove(items(["071160fd", "57dcc525"]))
    (trunk,) = items(["c3179e4e"])
    trunk.SetEnd(pt(153.919, 131.0))
    track("VBAT", "F", 0.25, "U1.12", (153.45, 129.442))
    track("VBAT", "F", 0.3, (153.45, 129.442), (154.15, 129.442), (154.15, 131.0))
    track("Motors_Enable", "F", 0.2, "U1.11", (153.55, 130.1))
    via("Motors_Enable", 153.55, 130.1)
    # IC6 pin 12 (PWM2/PH) on GND (review M7): off the 3V3 pair, onto the exposed pad
    remove(items(["d0b56043", "33826d4b"]))
    track("GND", "F", 0.25, "IC6.12", (139.708, 122.3))
    # C60 pad 2 on GND (review M1): off the 3V3 track
    remove(items(["f29e5d32", "251c883d", "ac5f954a", "462f39d5"]))
    # R17 (1206): LED_Red and the W2 cathode track reroute around it
    remove(items(["696fb3d5", "89700584", "09acc35e", "c8df10f5", "32b1e267"]))
    remove(items(["ed6a1821", "c5d4978d", "e89bb280", "be86d549"]))
    # R21 (1206): Wall_Sensor_2 reroutes around it, and leaves the battery divider the way past
    # the top corner of IC1: it runs round the W2 sensor and along the board's top edge to W3 and
    # R22, so its stub towards IC1 goes
    remove(items(["eb7a8a9e", "51ca3f92", "c6e066e7", "0fb2ff4f", "ff237a9c"]))
    # its way north passes east of D4, whose ground via moves to the board edge
    remove(items(["26df05c0", "dd99b5bc", "b7fe773b"]))
    # LED_ARGB's diagonal above R17 moves 0.3 mm towards R17, to make room for R45 and C59
    remove(items(["8c5fa8c7"]))
    track("LED_ARGB", "F", 0.254, (146.596, 67.454), (146.17, 67.454), (144.691, 65.975), (144.691, 65.549))
    # VBAT vias that joined nothing but the previous battery divider, and R17 pad 1's stub
    remove(items(["5889a8c2", "4bdf666e", "31c67517", "81208e71", "cb5833f5"]))
    remove(items(["2751e94a", "af7a3cc6", "c41270a5", "78ba3d0c", "7a547829"]))
    remove(items(["4a11517b"]))
    via("GND", 142.75, 60.75)
    track("GND", "F", 0.25, "D4.1", (142.75, 60.75))
    # and leaves IC1 pin 25 afresh, so pin 24 (PA5, Battery_Voltage) can escape beside it
    remove(items(["e00933a8", "db399006", "8206d8f2", "199df628", "33ca1abf"]))
    # and IC1 pin 12 (NRST) leaves by a shorter way, so pin 10 (PH0, USB_VBUS_Sense) can escape
    remove(items(["add6828f", "c348de82", "7cd6dbb9", "64980332", "c0d64271", "241cc7fa"]))
    # pins 12 (NRST) and 10 (PH0) share the room beyond pin 11, which is unused: NRST drops to
    # B.Cu on pin 11's axis, PH0 a pitch further out; Current_Sensor_Left's B.Cu run under them
    # makes way and is routed again
    remove(items(["4ee6f300", "f156cf9b", "7df2f87e"]))
    track("Reset", "F", 0.15, "IC1.12", (150.419, 72.602), (150.938, 72.628))
    via("Reset", 150.938, 72.628)
    track("Reset", "B", 0.2, (150.938, 72.628), (150.4, 72.75), (149.644, 71.899))
    track("USB_VBUS_Sense", "F", 0.1, "IC1.10", (151.3, 72.85), (151.48, 72.42))
    via("USB_VBUS_Sense", 151.48, 72.42)
    # Current_Sensor_Left's B.Cu run passes between PH0's via and pin 9's 3V3 via, in 0.15 mm
    track("Current_Sensor_Left", "B", 0.15, (150.742, 72.078), (151.54, 71.985), (151.685, 71.985), (154.049, 74.349))
    items(["590c0437"])[0].SetStart(pt(154.049, 74.349))
    # pins 24 (PA5) and 25 fan out side by side in 0.15 mm tracks between pin 23's track and
    # pin 26's via; pin 27's track turns 0.4 mm further out to leave them a lane each
    remove(items(["da1c11ae", "84a1bfb4"]))
    (ws1,) = items(["85fe4b8e"])
    ws1.SetEnd(pt(143.4, 71.02))
    track("Wall_Sensor_1", "F", 0.254, "IC1.27", (143.4, 72.443), (143.4, 71.02))
    track(
        "Battery_Voltage", "F", 0.15, "IC1.24", (145.557, 72.903), (145.468, 72.744), (144.29, 71.565), (144.29, 70.77)
    )
    # pin 25's track turns out between W2's pads and round R17 to the board's top edge, along
    # which it runs to W3's track to R22
    track(
        "Wall_Sensor_2",
        "F",
        0.15,
        "IC1.25",
        (145.08, 72.992),
        (145.21, 72.865),
        (143.89, 71.545),
        (143.89, 71.055),
        (142.15, 69.315),
        (142.15, 68.3),
        (142.62, 67.08),
        (141.67, 66.14),
        (143.07, 64.75),
        (144.27, 63.54),
        (144.27, 61.0),
    )
    track("Wall_Sensor_2", "F", 0.2, (144.27, 61.0), (144.72, 60.55), (160.3, 60.55), (160.3, 65.41), (160.653, 65.764))
    # U6/D8: the boost ground pour keeps its other vias
    remove(items(["202dd94c", "ac3744af", "da620ed6", "e2e04a35", "fa31bfec"]))
    # battery switch slew (review M5): SW4 pin 3 and its B.Cu run to the gate become the drive
    # net into R43; R41, C58 and Q6 stay on the gate
    remove(items(["a8737146"]))
    renet(items(["16ca1700", "cf10b0d8"]), "REGULATORS.BAT_SW_DRIVE")
    remove(items(["8061f63f", "97ec2cb7", "a31eed46", "a0c36002"]))
    # SBU supply (review M6): the 3V3 run from the In2.Cu via feeds Q7, Q7 feeds F1; the stub to
    # the removed D+ pull-up R10 goes
    remove(items(["d1d80021", "516c5ae3", "6a3a734e", "177d5c60", "ad3567f2", "40af513c"]))
    renet(items(["8c288d7a", "bb00d2fe", "612413fa", "52d83b06", "fc6491b2", "f22b2893"]), "3V3")
    remove(items(["9f379165"]))
    # LED_Red's B.Cu run north from IC1 pin 36 is routed afresh round W2
    remove(items(["cac27aa6", "f9eaedd2"]))


# --- courtyards ----------------------------------------------------------------------------------


def spacing() -> None:
    """Clear the courtyard overlaps: the updated footprints carry KiCad's generic courtyards, wider
    than the previous layout's spacing. The smallest moves found that keep every pad clear of other
    nets; connectors, switches, IC1, IC5 and BZ1 stay where they are."""
    for ref, dx, dy in [
        ("R35", 0.0, -0.05),
        ("D7", 0.1, 0.0),  # D6's neighbours
        ("C20", -0.05, 0.0),
        ("Q5", 0.0, -0.4),
        ("C29", 0.0, -0.4),  # SW2
        ("R3", -0.3, 0.4),
        ("Q1", 0.0, 0.1),  # P1, BZ1
        ("C48", -0.15, 0.0),
        ("C50", 0.15, 0.0),
        ("C49", 0.3, 0.0),  # the boost output row
        ("C46", -0.29, 0.0),
        ("C47", -0.14, -0.2),
        ("C45", 0.0, -0.2),
        ("C44", 0.15, -0.15),  # the boost input row, U1
        ("C4", -0.05, 0.0),
        ("C8", 0.3, 0.0),
        ("C9", 0.3, 0.0),  # IC1's
        ("R40", 0.15, 0.0),
        ("R21", 0.0, 0.08),
        ("C28", 0.3, 0.2),
        ("C37", 0.0, -0.19),
        ("C15", -0.05, 0.0),  # M1; C6, below
    ]:
        nudge(ref, dx, dy)
    # IC1 pin 35's capacitors turn across, C14 below C17, clear of IC1's corner: C14 feeds the pin,
    # C17 sits on the 3V3 via
    remove(items(["2e4aa534", "c6075bb8", "b87be225", "c146dfd6", "c489b14a", "5c176b63"]))
    place("C17", 140.6, 76.5, 180)
    place("C14", 141.0, 77.5, 0)
    track("3V3", "F", 0.254, "C14.2", (141.9, 77.128), "IC1.35")
    track("GND", "F", 0.254, "C14.1", (140.5, 78.122))
    track("3V3", "F", 0.254, "C17.2", (140.246, 75.709))
    # C6 (VCAP2, IC1 pin 49) moves up to its B.Cu hop's via, 2.8 mm from the pin; Motors_Enable's
    # via steps back to the end of its escape to make room
    remove(items(["7a8ed55a", "60bf015d", "0045d6e0", "7f3e4188", "ee86dfa6"]))
    (me_via,) = items(["184645ce"])
    me_via.SetPosition(pt(144.559, 81.29))
    track("Motors_Enable", "B", 0.254, (144.559, 81.29), (144.511, 81.678))
    place("C6", 143.85, 81.95, 0)
    track("VCORE", "F", 0.2, "C6.2", (144.437, 82.552))


def silkscreen() -> None:
    """The reference designators leave the silkscreen: at the board's density they could only be
    0.5 mm high (under JLCPCB's 0.8 mm minimum) and they lie over pads and each other. The
    assembly drawing (F.Fab) and the review renders keep them."""
    for f in B.GetFootprints():
        r = f.Reference()
        if r.IsVisible() and r.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            r.SetVisible(False)


# --- plane connections of the new parts ----------------------------------------------------------

# (ref, pad, inner layer whose pour the via lands on); In1.Cu is the ground plane, In2.Cu carries
# 3V3 under most of the board and +20V behind the axle
FANOUT = [
    *[
        (r, p, "In1")
        for r, p in [
            ("R49", "1"),
            ("C26", "1"),
            ("D10", "2"),
            ("D9", "2"),
            ("C66", "1"),
            ("C65", "1"),
            ("C64", "1"),
            ("U5", "2"),
            ("U5", "5"),
            ("C71", "1"),
            ("C72", "1"),
            ("C60", "2"),
            ("U6", "2"),
            ("C69", "1"),
            ("C70", "1"),
            ("C67", "1"),
            ("C68", "1"),
            ("R48", "1"),
            ("D12", "2"),
            ("D11", "2"),
            ("C58", "1"),
            ("D8", "1"),
        ]
    ],
    *[
        (r, p, "In2")
        for r, p in [
            ("R13", "2"),
            ("C26", "2"),
            ("BZ1", "1"),
            ("FB1", "1"),
            ("U5", "3"),
            ("U5", "6"),
            ("C72", "2"),
            ("C71", "2"),
            ("C69", "2"),
            ("C70", "2"),
            ("C67", "2"),
            ("C68", "2"),
            ("C65", "2"),
            ("C66", "2"),
        ]
    ],
]


# pads joined to a neighbouring pad of the same net instead of a via of their own
JOINS = [("C72.1", "C71.1")]


def plane_vias() -> None:
    pcbnew.ZONE_FILLER(B).Fill(B.Zones())
    failed = []
    for ref, num, layer in FANOUT:
        if f"{ref}.{num}" in dict(JOINS):
            continue
        try:
            fanout(ref, num, layer)
        except SystemExit as e:
            failed.append(str(e))
    for a, b in JOINS:
        track(pad(*a.split(".")).GetNetname(), "F", 0.25, a, b)
    # pads joined to existing copper of their net next to them
    track("3V3", "F", 0.3, "R17.2", (143.5, 66.419))  # R17's 3V3 track
    track("+5V", "F", 0.25, "R47.1", (161.074, 91.3))  # U4's +5V feed
    if failed:
        raise SystemExit("\n".join(failed))


# --- routing of the remaining connections ---------------------------------------------------------

# net, track width (mm): the supplies first, then the signals; router.py joins each net's copper
# islands on F.Cu/B.Cu, 0.12 mm from other copper
ROUTES = [
    # the wall sensor drives and gates, short and local, first
    *[
        (n, 0.2)
        for n in [
            "SENSORS.WALL0_GATE",
            "SENSORS.WALL0_LED_A",
            "SENSORS.WALL1_DRIVE",
            "SENSORS.WALL1_GATE",
            "SENSORS.WALL2_DRIVE",
            "SENSORS.WALL2_GATE",
            "Wall_Sensor_PWM_2",
            "SENSORS.WALL3_GATE",
            "Wall_Sensor_PWM_3",
            "Wall_Sensor_3",
        ]
    ],
    ("VBAT", 0.3),  # the LEDs D1/D2 and the battery divider at the front
    # escapes between IC1's 0.4 mm pitch pads: 0.15 mm tracks at the board's 0.1 mm clearance
    ("Battery_Voltage", 0.15, 0.1),
    ("Wall_Sensor_2", 0.15, 0.1),
    ("USB_VBUS_Sense", 0.15, 0.1),
    ("Motors_Enable", 0.2),  # U1's enable, across the boost stage, before the supplies fill it
    # supplies
    ("+5V", 0.3),  # D8 at VBUS, Q7's gate
    ("3V3", 0.25),
    ("GND", 0.25),
    *[
        (n, 0.2)
        for n in [
            "REGULATORS.BAT_SW_DRIVE",
            "REGULATORS.BAT_SW_GATE",
            "PERIPHERALS.USB_CONN_D_P",
            "PERIPHERALS.USB_CONN_D_N",
            "PERIPHERALS.SBU_SW",
            "PERIPHERALS.BUZZER_COIL",
            "SWD_VDD",
            "SWCLK",
            "SWDIO",
            "VDDA",
            "LED_Red",
            "SENSORS.WALL1_LED_K",
            "SENSORS.WALL2_LED_A",
            "Reset",
        ]
    ],
]


def routes() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import router

    pcbnew.ZONE_FILLER(B).Fill(B.Zones())
    r = router.Router(B)
    failed = []
    for name, width, *clr in ROUTES:
        try:
            r.route_net(name, width, clr=clr[0] if clr else router.CLR)
        except RuntimeError as e:
            failed.append(str(e))
    return failed


# --- run -------------------------------------------------------------------------------------------


def main() -> int:
    global B
    B = pcbnew.LoadBoard(str(LAYOUT))
    outline()
    encoder_pads()
    power_mux()
    placement()
    rework()
    spacing()
    silkscreen()
    plane_vias()
    failed = [] if "--no-routes" in sys.argv else routes()
    pcbnew.ZONE_FILLER(B).Fill(B.Zones())
    pcbnew.SaveBoard(str(LAYOUT), B)
    if failed:
        print("\n".join(failed))
        return 1
    if "--no-sync" not in sys.argv:
        env = dict(
            line.split("=", 1)
            for line in (ROOT / "versions.env").read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
        subprocess.run(
            ["pcb", f"+{env['PCB_TOOLCHAIN'].strip()}", "layout", "--no-open", "boards/main/main.zen"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
