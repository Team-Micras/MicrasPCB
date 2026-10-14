"""Layout of the Bluetooth module's design review fixes, as a one-off pcbnew script (KiCad 10).

    python3 boards/bluetooth/layout/fixes.py [--no-sync]

Runs once on the layout as the footprint update left it (`make gen`, then `pcb layout
--sync-footprints boards/bluetooth/bluetooth.zen` for the HM-19 and plug courtyards, on the
previous revision's placement and routing, see boards/bluetooth/previous/), then `pcb layout`
syncs the result. Every coordinate is KiCad millimetres in the board's frame
(spec/bluetooth.toml [kicad]). The steps, in order:

1. Outline: the seven 1-12 nm Edge.Cuts lines the Altium conversion left where the outline's arcs
   meet its lines are deleted, and a neighbour's end moves onto the other neighbour's (a line's
   end where the joint has one, else the arc's, keeping its midpoint): the outline closes on
   itself and keeps its shape.
2. Signature (M6): USB1 pad 3 (CC1) to pad 4 (D+) and pad 11 (CC2) to pad 12 (D+), each a
   0.254 mm F.Cu track across the 0.4 mm gap of the adjacent pads.
3. RESETB pull-up (m17): R4 in the free strip between the HM-19's bottom edge and C2, pad 2
   straight down to C2's 3V3 pad, pad 1 under the module to U1 pad 11 from the inside of the
   pad row (the right edge leaves no room outside it). C2's reference moves to C2's right, where
   R4 now sits; R4's reference takes the size of the others (0.5 mm, 0.154 mm stroke).
4. The copper pours are refilled.

Running it a second time fails on step 1 (no slivers left): it is not a fixed point, it is the
record of the edit. Run `make gen` and `make check` afterwards.
"""

from __future__ import annotations

import argparse
import itertools
import math
import subprocess
import sys
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[3]
LAYOUT = ROOT / "boards/bluetooth/layout/bluetooth.kicad_pcb"

B: pcbnew.BOARD = None
SLIVER = 0.0001  # mm: the conversion's slivers are 1-12 nm, the shortest real outline line 6 um
TRACK = 0.254  # the board's track width (Default net class)


def mm(v: float) -> int:
    return pcbnew.FromMM(v)


def pt(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x), mm(y))


def xy(p) -> tuple[float, float]:
    return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)


def fp(ref: str) -> pcbnew.FOOTPRINT:
    for f in B.GetFootprints():
        if f.GetReference() == ref:
            return f
    raise SystemExit(f"no footprint {ref}")


def pad(ref: str, num: str) -> pcbnew.PAD:
    for p in fp(ref).Pads():
        if p.GetNumber() == num:
            return p
    raise SystemExit(f"no pad {ref}.{num}")


def padxy(ref: str, num: str) -> tuple[float, float]:
    return xy(pad(ref, num).GetPosition())


def track(netname: str, *pts) -> None:
    """F.Cu segments through pts (each an (x, y) or a 'REF.PAD' string)."""
    net = B.FindNet(netname)
    if net is None:
        raise SystemExit(f"no net {netname}")
    q = [padxy(*p.split(".", 1)) if isinstance(p, str) else p for p in pts]
    for a, b in itertools.pairwise(q):
        if math.dist(a, b) < 1e-6:
            continue
        t = pcbnew.PCB_TRACK(B)
        t.SetStart(pt(*a))
        t.SetEnd(pt(*b))
        t.SetWidth(mm(TRACK))
        t.SetLayer(pcbnew.F_Cu)
        t.SetNet(net)
        B.Add(t)


# --- 1. outline ----------------------------------------------------------------------------------


def _ends(s) -> list:
    return [s.GetStart(), s.GetEnd()]


def _move_end(s, old: pcbnew.VECTOR2I, new: pcbnew.VECTOR2I) -> None:
    if s.GetShape() == pcbnew.SHAPE_T_ARC:
        mid = s.GetArcMid()
        a, b = s.GetStart(), s.GetEnd()
        s.SetArcGeometry(new if a == old else a, mid, new if b == old else b)
    elif s.GetStart() == old:
        s.SetStart(new)
    else:
        s.SetEnd(new)


def outline() -> None:
    edges = [d for d in B.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts and isinstance(d, pcbnew.PCB_SHAPE)]
    slivers = [s for s in edges if s.GetShape() == pcbnew.SHAPE_T_SEGMENT and pcbnew.ToMM(s.GetLength()) < SLIVER]
    if len(slivers) != 7:
        raise SystemExit(f"expected the 7 outline slivers of the conversion, found {len(slivers)}")
    for s in slivers:
        a, b = s.GetStart(), s.GetEnd()
        at_a = [e for e in edges if e is not s and a in _ends(e)]
        at_b = [e for e in edges if e is not s and b in _ends(e)]
        if len(at_a) != 1 or len(at_b) != 1:
            raise SystemExit(f"sliver at {xy(a)}: {len(at_a)} / {len(at_b)} neighbours")
        # move a line's end if the joint has a line; an arc keeps its midpoint
        if at_b[0].GetShape() == pcbnew.SHAPE_T_SEGMENT:
            _move_end(at_b[0], b, a)
        else:
            _move_end(at_a[0], a, b)
        edges.remove(s)
        B.Delete(s)


# --- 2. signature, 3. RESETB pull-up --------------------------------------------------------------


def signature() -> None:
    track("UART_RX", "USB1.3", "USB1.4")
    track("UART_RX", "USB1.11", "USB1.12")


def reset_pullup() -> None:
    r4 = fp("R4")
    r4.SetOrientation(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))
    # pad 2 above C2's 3V3 pad (KiCad R_0603_1608Metric: pads at +-0.825 mm)
    c2x = padxy("C2", "2")[0]
    r4.SetPosition(pt(c2x - 0.825, 106.65))
    ref, model = r4.Reference(), fp("R1").Reference()
    ref.SetAttributes(model)
    ref.SetLayer(model.GetLayer())
    ref.SetTextAngle(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))
    ref.SetPosition(pt(154.2, 106.65))
    c2 = fp("C2").Reference()
    c2.SetTextAngle(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))
    c2.SetPosition(pt(154.1, 108.31))
    track("3V3", "R4.2", "C2.2")
    x1 = padxy("R4", "1")[0]
    # clear of the GND via at (152.129, 104.55) and of U1 pad 10's 3V3
    track("RESETB", "R4.1", (x1, 104.7), (x1 + 2.754, 104.7 - 2.754), (x1 + 2.754, 101.504), "U1.11")


def fill() -> None:
    pcbnew.ZONE_FILLER(B).Fill(B.Zones())


def main() -> int:
    global B
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-sync", action="store_true", help="skip the final `pcb layout` sync")
    a = ap.parse_args()
    B = pcbnew.LoadBoard(str(LAYOUT))
    outline()
    signature()
    reset_pullup()
    fill()
    pcbnew.SaveBoard(str(LAYOUT), B)
    if not a.no_sync:
        env = dict(
            line.split("=", 1)
            for line in (ROOT / "versions.env").read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
        subprocess.run(
            ["pcb", f"+{env['PCB_TOOLCHAIN'].strip()}", "layout", "--no-open", "boards/bluetooth/bluetooth.zen"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
