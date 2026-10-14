"""The owner's layout decisions on the review fixes, as a one-off pcbnew script (KiCad 10).

    python3 boards/main/layout/refine.py

Runs once, after fixes.py, on the layout as `make gen` leaves it with the JST SH footprint of P1
(placed by `pcb apply` where the pin header was). It reuses the helpers of fixes.py and its grid
router (router.py). Every coordinate is KiCad millimetres on the board's frame; the UUID prefixes
name items of that starting layout. The steps, in order:

- courtyards: clear the five connector courtyard overlaps (J1/C36, C36/SW4, M2/SW4, IC5/M1,
  U2/C37) with the smallest moves, passives first: C36, C37 and C23, R6, R7; then the switch SW4
  and the motor connectors M1 and M2 (IC5's pad 10 cannot move closer to the board corner), with
  C38 in the corner M1 frees;
- swd: the SWD connector P1 (JST SH side entry) on the left board edge, its mating face outwards,
  the fan connector M3 moved inwards to make room, the pin header's copper and labels removed;
- decoupling: C15 beside IC1 pad 51 (VDD) with its own ground via, in the strip under pads 46-51
  that SWDIO leaves by a via under pad 48; the USB pair's run there 0.2 mm further out;
- silkscreen: every reference designator on F.Silkscreen, clear of pads, of the other silkscreen
  and of the board edge, and P1's pin 1 and "SWD" labels;
router.py joins what is left unconnected (ROUTES) before the silkscreen step; then the zones are
refilled, the board saved and `pcb layout` syncs it.

    python3 boards/main/layout/refine.py --no-sync     # skip the `pcb layout` sync
    python3 boards/main/layout/refine.py --no-routes   # placement and hand copper only
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixes as fx
from fixes import fp, items, nudge, place, remove, track, via

ROOT = Path(__file__).resolve().parents[3]
LAYOUT = ROOT / "boards/main/layout/main.kicad_pcb"


# --- courtyards ------------------------------------------------------------------------------------

# (ref, dx, dy) in mm. The courtyards are the packages' (IPC-7351B, 0.5 mm round connector bodies);
# each move is the smallest that leaves 0.01-0.07 mm between courtyards.
COURTYARD_MOVES = [
    ("C36", -0.43, 0.0),  # J1/C36: the VBAT bulk capacitor towards the right motor's sense pair
    ("C23", -0.15, 0.0),  # C36's new left edge
    ("SW4", 0.09, 0.22),  # C36/SW4 and M2/SW4: the battery switch 0.22 mm rearwards, 0.09 mm out
    ("M2", -0.55, 0.0),  # M2/SW4: the right motor connector 0.55 mm inwards
    ("R6", -0.12, 0.0),  # M2's new left edge, against U2's
    ("R7", -0.12, 0.0),
    ("M1", 1.2, 0.0),  # IC5/M1: the left motor connector 1.2 mm inwards, C38's room below C37
    ("C37", -0.397, 0.0),  # U2/C37: the +20V bulk capacitor away from the USB-C receptacle
]


def courtyards() -> None:
    for ref, dx, dy in COURTYARD_MOVES:
        nudge(ref, dx, dy)
    # C38 (100 nF at the L6205's VS pins) leaves the gap between IC5 and C37, which C37 needs, for
    # the corner M1 frees: beside pin 14 (+20V), in the +20V pour, with a ground via of its own
    remove(items(["38a13563", "a91bd017", "f6cc0a23"]))
    place("C38", 136.19, 144.75, 90)
    track("+20V", "F", 0.3, "C38.2", "IC5.14")
    track("GND", "F", 0.3, "C38.1", (136.95, 145.3))
    via("GND", 136.95, 145.3)
    # a teardrop of the conversion left on M1's pad 2 under the old name of its net
    remove(items(["93956928"]))
    # the right motor's Motor_R_Sense+ run past M1 stays clear of M1's pad 2 at its new place
    remove(items(["d63c4605", "fb2171ed", "42dc770f"]))
    track("Motor_R_Sense+", "F", 0.6, (138.722, 147.972), (141.6, 147.972), (144.267, 145.305), (144.945, 145.305))
    # Motor_R_Sense+/- run between C36's pads: closer together, clear of its VBAT pad
    remove(items(["1a492e30", "2c3fe4ea", "257f1bad", "e3407ae6", "8f75f4a8", "dde61af9"]))
    track("Motor_R_Sense+", "F", 0.6, (162.649, 137.075), (162.45, 137.274), (162.45, 139.595), (161.963, 140.082))
    track("Motor_R_Sense-", "F", 0.6, (164.249, 137.177), (163.18, 137.75), (163.18, 139.6), (163.36, 139.78))
    track("Motor_R_Sense-", "F", 0.6, (163.36, 139.78), (163.36, 142.384))


# --- SWD connector ---------------------------------------------------------------------------------

# P1: JST SM05B-SRSS-TB, side entry. Rotated -90 degrees its mating face (+Y of the footprint)
# points at the left board edge (KiCad x = 123.5011): the reinforcement pads' outer edge sits
# 0.2 mm (the copper-to-edge rule) inside it and the body's mating face 0.4 mm inside it, so the
# plug's cable leaves the board sideways. Pin 1 is the top contact (KiCad y = 88.5).
P1_AT = (126.48, 90.5)
# M3, the fan connector, 1.95 mm inwards: P1's contact row needs the room.
M3_MOVE = (1.95, 0.0)


def swd() -> None:
    nudge("M3", *M3_MOVE)
    place("P1", *P1_AT, -90)
    # the pin header's SWD copper: SWDIO all the way from IC1 (routed afresh, see decoupling),
    # SWCLK's run along y = 88.4 and its stub, the Reset and SWD_VDD stubs to the old pads
    remove([t for t in fx.B.GetTracks() if t.GetNetname() == "SWDIO"])
    remove(items(["fa34c56d", "45be5608"]))  # SWCLK
    remove(items(["4e24445a"]))  # Reset
    remove(items(["a7c835f7", "ece2654f"]))  # SWD_VDD
    # the pin header's pin labels, front and back (CLK, IO, GND, 3V3)
    remove(items(["a8dd0e0a", "cf681865", "55f87799", "2828b971", "29bdc20a", "e943c563", "ff1aacdc", "a4d6930c"]))
    # pin 2 (GND) under the body to the upper reinforcement pad; both pads take a ground via
    track("GND", "F", 0.3, "P1.2", (126.3, 89.5), (125.0, 88.2))
    for y_mp, y_via in ((87.2, 87.6), (93.8, 93.4)):
        track("GND", "F", 0.3, (124.625, y_mp), (125.9, y_via))
        via("GND", 125.9, y_via)


# --- C15 at IC1 pad 51 -------------------------------------------------------------------------------


def decoupling() -> None:
    """C15 (100 nF, IC1 pad 51 VDD) stands in the strip under pads 46-51 that SWDIO leaves: its
    3V3 pad on the via that pad 51 already drops to, its GND pad on a via of its own beside it.
    The USB pair's straight run moves 0.2 mm further from it."""
    # C15's copper at its previous place
    remove(items(["306f9b21", "49c689d0", "4f201017", "56e08156", "9fe0cbd8", "7d9b6ed5", "1d9e65d1"]))
    remove(items(["07efb51c", "2955b2f7", "7d9fa3d4", "80330a86"]))
    # the USB pair's run under pads 46-47, 0.2 mm towards C6: the escapes run 0.2 mm further
    # along their diagonals, the straight runs move over
    for uuid, end, (dx, dy) in [
        ("e3d0d8ee", "start", (-0.2, 0.2)),  # USBD_N escape
        ("6ed397c6", "start", (-0.2, -0.2)),  # USBD_N run, x = 145.204 (bottom end, top end)
        ("6ed397c6", "end", (-0.2, 0.2)),
        ("a0bcccef", "start", (-0.2, -0.2)),
        ("8d48c509", "start", (-0.2, 0.2)),  # USBD_P escape
        ("43528f09", "start", (-0.2, -0.2)),  # USBD_P run, x = 145.556
        ("43528f09", "end", (-0.2, 0.2)),
        ("7df658c0", "start", (-0.2, -0.2)),
    ]:
        (t,) = items([uuid])
        get, put = (t.GetStart, t.SetStart) if end == "start" else (t.GetEnd, t.SetEnd)
        x, y = fx.xy(get())
        put(fx.pt(x + dx, y + dy))
    # VCAP2's capacitor C6 takes VCORE from the In2.Cu VCORE route instead of a B.Cu hop, which
    # leaves B.Cu under the strip to SWDIO: it drops to B.Cu below pad 48 and leaves under IC1
    remove(items(["9c4cc972", "520c724a", "8de70f23"]))
    track("VCORE", "In2", 0.4, (146.469, 81.929), (145.95, 81.75), (145.15, 81.75), (144.437, 82.552))
    track("SWDIO", "F", 0.2, "IC1.48", (145.9, 81.646), (145.83, 81.716), (145.83, 82.85))
    via("SWDIO", 145.83, 82.85)
    place("C15", 146.68, 83.68, 90)  # pad 2 (3V3) at y = 83.2, pad 1 (GND) at 84.16
    track("3V3", "F", 0.25, "C15.2", (146.644, 82.605))
    via("GND", 146.0, 83.55)
    track("GND", "F", 0.2, "C15.1", (146.0, 83.55))


# --- silkscreen ------------------------------------------------------------------------------------

# Reference designators with the stroke of the previous board's (0.5 mm high, 0.154 mm stroke on
# the Altium board, which the owner read on the fabricated board): KiCad's stroke font caps the
# stroke at a quarter of the character size, so 0.6 mm is the smallest size that carries the
# board's 0.15 mm minimum stroke (boards/main/main.zen Silkscreen, rules/kicad-severities.toml).
REF_SIZE, REF_STROKE = 0.6, 0.15
SILK_GAP = 0.1  # silkscreen to silkscreen, to exposed copper and to the board edge (KiCad's DRC)


class SilkSpace:
    """What a reference designator must keep clear of: pads (their mask openings), every other
    silkscreen item, the board edge and holes. Shapes are kept with their bounding boxes so a
    candidate is only tested against its neighbours."""

    def __init__(self, board: pcbnew.BOARD):
        self.items = []  # (bbox in mm (x0, y0, x1, y1), SHAPE, owner ref or None)
        for f in board.GetFootprints():
            for p in f.Pads():
                if p.IsOnLayer(pcbnew.F_Cu) or p.HasHole():
                    self._add(p.GetEffectiveShape(pcbnew.F_Cu), p.GetBoundingBox(), None)
            for g in f.GraphicalItems():
                if g.GetLayer() == pcbnew.F_SilkS and (g.GetClass() != "PCB_TEXT" or g.IsVisible()):
                    self._add(g.GetEffectiveShape(pcbnew.F_SilkS), g.GetBoundingBox(), f.GetReference())
            for fld in f.GetFields():
                if fld.GetLayer() == pcbnew.F_SilkS and fld.IsVisible() and not fld.IsReference():
                    self._add(fld.GetEffectiveShape(pcbnew.F_SilkS), fld.GetBoundingBox(), f.GetReference())
        for d in board.GetDrawings():
            if d.GetLayer() == pcbnew.F_SilkS:
                self._add(d.GetEffectiveShape(pcbnew.F_SilkS), d.GetBoundingBox(), None)
        outline = pcbnew.SHAPE_POLY_SET()
        board.GetBoardPolygonOutlines(outline, True)
        self.outline = outline
        self.edges = []
        for chain in [outline.Outline(0)] + [outline.Hole(0, h) for h in range(outline.HoleCount(0))]:
            self.edges += [chain.CSegment(i) for i in range(chain.SegmentCount())]

    def _add(self, shape, bbox, owner):
        box = (
            pcbnew.ToMM(bbox.GetLeft()),
            pcbnew.ToMM(bbox.GetTop()),
            pcbnew.ToMM(bbox.GetRight()),
            pcbnew.ToMM(bbox.GetBottom()),
        )
        self.items.append((box, shape, owner))

    def free(self, text) -> bool:
        shape = text.GetEffectiveShape(pcbnew.F_SilkS)
        bb = text.GetBoundingBox()
        x0, y0 = pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop())
        x1, y1 = pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())
        for corner in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            if not self.outline.Contains(fx.pt(*corner)):
                return False
        gap = pcbnew.FromMM(SILK_GAP)
        for e in self.edges:
            if shape.Collide(e, gap):
                return False
        m = SILK_GAP + 0.05
        for (a0, b0, a1, b1), other, _ in self.items:
            if a1 < x0 - m or a0 > x1 + m or b1 < y0 - m or b0 > y1 + m:
                continue
            if shape.Collide(other, gap):
                return False
        return True

    def take(self, text) -> None:
        self._add(text.GetEffectiveShape(pcbnew.F_SilkS), text.GetBoundingBox(), None)


def _courtyard_box(f):
    bb = f.GetCourtyard(pcbnew.F_CrtYd).BBox()
    if bb.GetWidth() == 0:
        bb = f.GetBoundingBox(False)
    return (
        pcbnew.ToMM(bb.GetLeft()),
        pcbnew.ToMM(bb.GetTop()),
        pcbnew.ToMM(bb.GetRight()),
        pcbnew.ToMM(bb.GetBottom()),
    )


def _candidates(f, text):
    """Text centres and angles near the part, nearest first: the previous board's spot, then a
    0.1 mm grid around the courtyard out to 3 mm, both readings, ordered by the distance from the
    text's edge to the courtyard's (then to the part's centre)."""
    x0, y0, x1, y1 = _courtyard_box(f)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    out = [(0.0, (fx.xy(text.GetPosition()), text.GetTextAngleDegrees()))]
    for angle in (0.0, 90.0):
        text.SetTextAngle(pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
        bb = text.GetBoundingBox()
        hw, hh = pcbnew.ToMM(bb.GetWidth()) / 2, pcbnew.ToMM(bb.GetHeight()) / 2
        reach = 3.0
        nx = int((x1 - x0 + 2 * (hw + reach)) / 0.1) + 1
        ny = int((y1 - y0 + 2 * (hh + reach)) / 0.1) + 1
        for i in range(nx):
            x = x0 - hw - reach + 0.1 * i
            for j in range(ny):
                y = y0 - hh - reach + 0.1 * j
                # gap between the text's box and the courtyard's box (negative: over the part)
                gx = max(x0 - (x + hw), (x - hw) - x1)
                gy = max(y0 - (y + hh), (y - hh) - y1)
                gap = max(gx, gy)
                rank = gap + 1.0 if gap < 0 else gap  # over the part only after 1 mm around it
                rank += 0.01 * math.hypot(x - cx, y - cy) + (0.05 if angle else 0.0)
                out.append((rank, ((x, y), angle)))
    out.sort(key=lambda c: c[0])
    return [c[1] for c in out]


def _over_a_body(text, courtyards) -> bool:
    """The text lies over a part's body (its courtyard less the 0.25 mm assembly margin), where the
    assembled part would hide it."""
    shape = text.GetEffectiveShape(pcbnew.F_SilkS)
    return any(poly.Collide(shape, 0) for _, poly in courtyards)


def silkscreen() -> list[str]:
    """Every reference designator on F.Silkscreen at REF_SIZE / REF_STROKE, clear of pads, of the
    other silkscreen and of the board edge: on its previous board's spot where that is free, else
    the nearest free spot off every part's body, else the nearest free spot. Returns the parts without a free spot (their designator stays hidden)."""
    space = SilkSpace(fx.B)
    courtyards = []
    for f in fx.B.GetFootprints():
        poly = pcbnew.SHAPE_POLY_SET(f.GetCourtyard(pcbnew.F_CrtYd))
        if poly.OutlineCount():
            poly.Deflate(fx.mm(0.25), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, fx.mm(0.01))
            courtyards.append((f.GetReference(), poly))
    swd_labels(space, courtyards)
    unplaced = []
    # small parts first: they have the fewest spots
    order = sorted(fx.B.GetFootprints(), key=lambda f: (_area(f), f.GetReference()))
    for f in order:
        if "MountingHole" in f.GetFPIDAsString():
            continue  # the screw holes carry no designator
        r = f.Reference()
        r.SetLayer(pcbnew.F_SilkS)
        r.SetTextSize(pcbnew.VECTOR2I(fx.mm(REF_SIZE), fx.mm(REF_SIZE)))
        r.SetTextThickness(fx.mm(REF_STROKE))
        r.SetKeepUpright(True)
        r.SetVisible(True)
        best = None
        for strict in (True, False):
            for (x, y), angle in _candidates(f, r):
                r.SetTextAngle(pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
                r.SetPosition(fx.pt(round(x, 3), round(y, 3)))
                if not space.free(r):
                    continue
                if strict and _over_a_body(r, courtyards):
                    continue
                best = ((round(x, 3), round(y, 3)), angle)
                break
            if best:
                break
        if best is None:
            r.SetVisible(False)
            unplaced.append(f.GetReference())
            continue
        r.SetTextAngle(pcbnew.EDA_ANGLE(best[1], pcbnew.DEGREES_T))
        r.SetPosition(fx.pt(*best[0]))
        space.take(r)
    return unplaced


def _board_text(text: str, x: float, y: float, angle: float) -> pcbnew.PCB_TEXT:
    t = pcbnew.PCB_TEXT(fx.B)
    t.SetText(text)
    t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(pcbnew.VECTOR2I(fx.mm(REF_SIZE), fx.mm(REF_SIZE)))
    t.SetTextThickness(fx.mm(REF_STROKE))
    t.SetTextAngle(pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    t.SetPosition(fx.pt(x, y))
    fx.B.Add(t)
    return t


def swd_labels(space: SilkSpace, courtyards: list) -> None:
    """P1's pin 1 numbered beside its contact (the footprint's tick marks it too), and "SWD" by the
    connector; the pinout is in boards/main/README.md."""
    pin1 = fx.padxy("P1", "1")
    one = _board_text("1", pin1[0] + 1.3, pin1[1], 0.0)
    for dx in (1.3, 1.4, 1.5, 1.2, 1.6):
        one.SetPosition(fx.pt(pin1[0] + dx, pin1[1]))
        if space.free(one):
            break
    else:
        raise SystemExit("no free spot for P1's pin 1 label")
    space.take(one)
    label = _board_text("SWD", *fx.xy(fp("P1").GetPosition()), 90.0)
    spots = [c for strict in (True, False) for c in ((strict, c) for c in _candidates(fp("P1"), label)[1:])]
    for strict, ((x, y), angle) in spots:
        label.SetTextAngle(pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
        label.SetPosition(fx.pt(round(x, 3), round(y, 3)))
        if space.free(label) and not (strict and _over_a_body(label, courtyards)):
            break
    else:
        raise SystemExit("no free spot for the SWD label")
    space.take(label)


def _area(f) -> float:
    x0, y0, x1, y1 = _courtyard_box(f)
    return (x1 - x0) * (y1 - y0)


# --- routing ---------------------------------------------------------------------------------------

ROUTES = [
    ("SWDIO", 0.2, 0.1),
    ("SWCLK", 0.2, 0.1),
    ("Reset", 0.2, 0.1),
    ("SWD_VDD", 0.25),
    ("3V3", 0.25),
    ("GND", 0.25),
]


def routes() -> list[str]:
    import router

    pcbnew.ZONE_FILLER(fx.B).Fill(fx.B.Zones())
    r = router.Router(fx.B)
    failed = []
    for name, width, *clr in ROUTES:
        try:
            r.route_net(name, width, clr=clr[0] if clr else router.CLR)
        except RuntimeError as e:
            failed.append(str(e))
    return failed


# --- run -------------------------------------------------------------------------------------------


def main() -> int:
    fx.B = pcbnew.LoadBoard(str(LAYOUT))
    courtyards()
    swd()
    decoupling()
    failed = [] if "--no-routes" in sys.argv else routes()
    hidden = silkscreen()
    if hidden:
        print("designators without a free spot (hidden):", ", ".join(hidden))
    pcbnew.ZONE_FILLER(fx.B).Fill(fx.B.Zones())
    pcbnew.SaveBoard(str(LAYOUT), fx.B)
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
