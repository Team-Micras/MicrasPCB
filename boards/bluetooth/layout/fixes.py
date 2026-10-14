"""Layout of the Bluetooth module's design review fixes, as a one-off pcbnew script (KiCad 10).

    python3 boards/bluetooth/layout/fixes.py [--no-sync]

Runs once on the previous revision's layout as boards/bluetooth/previous/transfer_layout.py
writes it (after `pcb layout --sync-footprints boards/bluetooth/bluetooth.zen` for the HM-19 and
plug courtyards), then `pcb layout` syncs the result. Every coordinate is KiCad millimetres in the
board's frame (spec/bluetooth.toml [kicad]). The steps, in order:

1. Signature (M6): USB1 pad 3 (CC1) to pad 4 (D+) and pad 11 (CC2) to pad 12 (D+), each a
   0.254 mm F.Cu track across the 0.4 mm gap of the adjacent pads.
2. RESETB pull-up (m17): R4 in the free strip between the HM-19's bottom edge and C2, pad 2
   straight down to C2's 3V3 pad, pad 1 under the module to U1 pad 11 from the inside of the
   pad row (the right edge leaves no room outside it). C2's reference moves to C2's right, where
   R4 now sits; R4's reference takes the size of the others (0.5 mm, 0.154 mm stroke).
3. The copper pours are refilled.

It is the record of the edit, not a fixed point: it refuses a layout that already has the
signature tracks. To rebuild the layout, run the transfer script, then this one, then `make gen`
and `make check`.
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


# --- 1. signature, 2. RESETB pull-up --------------------------------------------------------------


def signature() -> None:
    a, b = padxy("USB1", "3"), padxy("USB1", "4")
    for t in B.GetTracks():
        if {xy(t.GetStart()), xy(t.GetEnd())} == {a, b}:
            raise SystemExit("the layout already has the signature tracks: run the transfer script first")
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
