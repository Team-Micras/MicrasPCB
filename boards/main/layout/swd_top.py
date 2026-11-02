"""The top-entry SWD connector, as a one-off pcbnew script (KiCad 10).

    python3 boards/main/layout/swd_top.py

Runs once, after octilinear.py and `make gen` with P1 on the JST BM05B-SRSS-TB top-entry footprint
(`pcb layout` replaces the side-entry footprint in place and leaves the copper of the old pads).
The previous revision had an upright 2.54 mm pin header at this spot, so an upright plug fits the
chassis. Every coordinate is KiCad millimetres on the board's frame. The steps, in order:

- place: P1 on the left board edge where the side-entry header was, its contact row along the
  edge and facing inwards (pin 1 at the rear), the reinforcement pads 0.2 mm (the copper-to-edge
  rule) inside the edge; the fan connector M3 stays where it is (the old spot,
  1.95 mm to the left, would overlap P1's courtyard);
- copper: the signal vias the new footprint covers go with their tracks, the tracks left on
  nothing by the old pads go, back to where other copper continues (a via they ran to stays), and router.py routes P1's five nets again: SWDIO, SWCLK and Reset
  first (0.2 mm), then SWD_VDD (0.25 mm) and GND (0.3 mm);
- cleanup: octilinear.py's (vias joining one layer, teardrops on nothing);
- silkscreen: P1's "1" and "SWD" labels (refine.py's method) at 0.5 mm / 0.125 mm, and the
  designators the new copper covers;
then the zones are refilled, the board saved and `pcb layout` syncs it.

    python3 boards/main/layout/swd_top.py --no-sync     # skip the `pcb layout` sync
"""

from __future__ import annotations

import sys
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "boards/main/previous"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixes as fx  # noqa: E402
import octilinear as oc  # noqa: E402
import refine  # noqa: E402
import router  # noqa: E402
import transfer_layout as tl  # noqa: E402
import usb_wall  # noqa: E402

LAYOUT = ROOT / "boards/main/layout/main.kicad_pcb"
# P1 (JST SH BM05B-SRSS-TB, top entry): footprint contacts at local y = +1.325, reinforcement pads
# at y = -1.2 (1.8 mm long): 2.1 mm from the centre to either pad row's outer edge. The left board
# edge runs at x = 123.5011 here, so the centre sits 0.25 mm (0.2 mm rule plus margin) + 2.1 mm in.
P1_AT = (125.85, 90.5)
NETS = [
    ("SWDIO", 0.2, 0.1),
    ("SWCLK", 0.2, 0.1),
    ("Reset", 0.2, 0.1),
    ("SWD_VDD", 0.25, router.CLR),
    ("GND", 0.3, router.CLR),
]


def place() -> None:
    """P1 with its contacts towards the board's inside (+x), so its tracks leave inwards; that
    puts pin 1 at the rear (+y), the reinforcement pads by the edge."""
    fx.place("P1", *P1_AT, 90)
    (x1, y1), (x5, y5) = fx.padxy("P1", "1"), fx.padxy("P1", "5")
    mp = [fx.xy(p.GetPosition()) for p in fx.fp("P1").Pads() if p.GetNumber() == "MP"]
    assert x1 > P1_AT[0] and abs(x1 - x5) < 1e-6 and y1 > y5 and all(x < P1_AT[0] for x, _ in mp)


def _end_free(t, e) -> bool:
    """Nothing of the track's net is at its end e (a pad, a via, another track, a pour)."""
    nc, layer = t.GetNetCode(), t.GetLayer()
    if oc.pads_at(e, layer, nc):
        return False
    for o in fx.B.GetTracks():
        if o.GetNetCode() != nc or oc.same(o, t):
            continue
        if o.GetClass() == "PCB_VIA":
            if (o.GetPosition() - e).EuclideanNorm() <= o.GetWidth(pcbnew.F_Cu) / 2:
                return False
        elif o.GetLayer() == layer and o.HitTest(e, o.GetWidth() // 2):
            return False
    return not any(
        z.GetNetCode() == nc and z.IsOnLayer(layer) and not oc._teardrop(z) and z.HitTestFilledArea(layer, e)
        for z in fx.B.Zones()
    )


def clear_under() -> int:
    """P1's signal nets' vias under the new footprint (its courtyard grown by 0.3 mm), which the
    side-entry layout put by its contacts, and the tracks that end there."""
    names = {n for n, *_ in NETS if n != "GND"}
    box = fx.fp("P1").GetCourtyard(pcbnew.F_CrtYd).BBox()
    box.Inflate(fx.mm(0.3))
    gone = [
        t
        for t in fx.B.GetTracks()
        if t.GetNetname() in names
        and (
            box.Contains(t.GetPosition())
            if t.GetClass() == "PCB_VIA"
            else t.GetLayer() == pcbnew.F_Cu and (box.Contains(t.GetStart()) or box.Contains(t.GetEnd()))
        )
    ]
    vias = [v for v in gone if v.GetClass() == "PCB_VIA"]
    gone += [
        t
        for t in fx.B.GetTracks()
        if t.GetClass() == "PCB_TRACK"
        and any(t.GetNetCode() == v.GetNetCode() and v.GetPosition() in (t.GetStart(), t.GetEnd()) for v in vias)
        and not any(oc.same(t, g) for g in gone)
    ]
    oc._rip(gone)
    return len(gone)


def peel() -> int:
    """Remove P1's nets' tracks with an end on nothing (the old pads' stubs), until none is left;
    the vias they ran to stay, for the new tracks to join."""
    names = {n for n, *_ in NETS}
    gone = 0
    while True:
        dead = [
            t
            for t in fx.B.GetTracks()
            if t.GetClass() == "PCB_TRACK"
            and t.GetNetname() in names
            and any(_end_free(t, e) for e in (t.GetStart(), t.GetEnd()))
        ]
        if not dead:
            return gone
        oc._rip(dead)
        gone += len(dead)


def copper() -> list[str]:
    pcbnew.ZONE_FILLER(fx.B).Fill(fx.B.Zones())
    r = router.Router(fx.B)
    check = oc._checker(r)
    failed = []
    for name, width, clr in NETS:
        net = fx.B.FindNet(name)
        p1 = [("pad", p) for p in fx.fp("P1").Pads() if p.GetNetCode() == net.GetNetCode()]
        for pad in p1:
            # each of P1's pads joins the rest of its net
            islands = r.copper(net.GetNetCode())
            mine = next(isl for isl in islands if any(o.m_Uuid.AsString() == pad[1].m_Uuid.AsString() for _, o in isl))
            rest = [it for isl in islands if isl is not mine for it in isl]
            if not rest:
                continue
            if r.join(net, width, mine, rest, clr=clr, check=check) is None:
                failed.append(f"{name}: P1 pad {pad[1].GetNumber()}")
            oc.dirty()
    return failed


def silkscreen() -> None:
    labels = [
        d
        for d in fx.B.GetDrawings()
        if d.GetClass() == "PCB_TEXT" and d.GetLayer() == pcbnew.F_SilkS and d.GetText() in ("1", "SWD")
    ]
    fx.drop(labels)
    space = refine.SilkSpace(fx.B)
    courtyards = []
    for f in fx.B.GetFootprints():
        poly = pcbnew.SHAPE_POLY_SET(f.GetCourtyard(pcbnew.F_CrtYd))
        if poly.OutlineCount():
            poly.Deflate(fx.mm(0.25), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, fx.mm(0.01))
            courtyards.append((f.GetReference(), poly))
    refine.swd_labels(space, courtyards)
    usb_wall.MOVED = ["P1"]
    hidden = usb_wall.silkscreen()
    if hidden:
        raise SystemExit("designators without a free spot: " + ", ".join(hidden))


def main() -> int:
    fx.B = pcbnew.LoadBoard(str(LAYOUT))
    place()
    print("under P1:", clear_under())
    print("peeled:", peel())
    failed = copper()
    oc.cleanup()  # the vias the old stubs ran to and the new tracks no longer use
    silkscreen()
    pcbnew.ZONE_FILLER(fx.B).Fill(fx.B.Zones())
    pcbnew.SaveBoard(str(LAYOUT), fx.B)
    if failed:
        print("\n".join(failed))
        return 1
    if "--no-sync" not in sys.argv:
        tl.pcb_layout()
    return 0


if __name__ == "__main__":
    sys.exit(main())
