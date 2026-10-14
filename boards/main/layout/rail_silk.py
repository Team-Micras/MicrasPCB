"""U6's rail capacitor and the owner's designator size, as a one-off pcbnew script (KiCad 10).

    python3 boards/main/layout/rail_silk.py

Runs once, after finish.py and `make gen` (with C79 in the netlist). Every coordinate is KiCad
millimetres; the UUID prefix names an item of that layout. The steps, in order:

- rail: C79 (100 nF, U6's VBUS-pin bypass, DocID 11265 Figure 18) stands upright in the strip
  between C43 and the R36-R38 column, above U6: its 3V3 pad on the 3V3 run that feeds U6 pin 5
  (4.5 mm of track to the pin, which the D+ run on the right and the receptacle below leave as the
  shortest way in), its GND pad 0.9 mm from R37's GND via, a through via to the In1.Cu plane;
- designators: every reference designator, and P1's "1" and "SWD" labels, at refine.REF_SIZE /
  refine.REF_STROKE (0.5 mm high, 0.125 mm stroke, the owner's choice); a text stays where it is
  while that spot is still clear (a smaller text inside its old box), the others and C79's take
  the nearest free spot by usb_wall.silkscreen's method;
then the zones are refilled, the board saved and `pcb layout` syncs it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "boards/main/previous"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixes as fx  # noqa: E402
import refine  # noqa: E402
import transfer_layout as tl  # noqa: E402
import usb_wall  # noqa: E402

LAYOUT = ROOT / "boards/main/layout/main.kicad_pcb"
RAIL_RUN = "f5315f85"  # 3V3 on F.Cu, (145.647, 133.0) to (147.2, 133.0), towards U6 pin 5
R37_GND_VIA = (146.216, 130.372)


def rail() -> None:
    fx.place("C79", 146.08, 131.75, 270)  # pad 2 (3V3) down at y = 132.23, pad 1 (GND) up
    assert fx.padxy("C79", "2")[1] > fx.padxy("C79", "1")[1]
    (run,) = fx.items([RAIL_RUN])
    fx.remove([run])
    fx.track("3V3", "F", 0.25, (145.647, 133.0), (146.08, 133.0), (147.2, 133.0))
    fx.track("3V3", "F", 0.25, "C79.2", (146.08, 133.0))
    fx.track("GND", "F", 0.25, "C79.1", R37_GND_VIA)


def designators() -> None:
    size = fx.mm(refine.REF_SIZE)
    for d in fx.B.GetDrawings():  # P1's labels, from refine.swd_labels
        if d.GetClass() == "PCB_TEXT" and d.GetLayer() == pcbnew.F_SilkS and d.GetText() in ("1", "SWD"):
            d.SetTextSize(pcbnew.VECTOR2I(size, size))
            d.SetTextThickness(fx.mm(refine.REF_STROKE))
    for f in fx.B.GetFootprints():
        if "MountingHole" in f.GetFPIDAsString():
            continue  # the screw holes carry no designator
        r = f.Reference()
        r.SetTextSize(pcbnew.VECTOR2I(size, size))
        r.SetTextThickness(fx.mm(refine.REF_STROKE))
    usb_wall.MOVED = ["C79"]
    hidden = usb_wall.silkscreen()
    if hidden:
        raise SystemExit("designators without a free spot: " + ", ".join(hidden))


def main() -> int:
    fx.B = pcbnew.LoadBoard(str(LAYOUT))
    rail()
    designators()
    pcbnew.ZONE_FILLER(fx.B).Fill(fx.B.Zones())
    pcbnew.SaveBoard(str(LAYOUT), fx.B)
    tl.pcb_layout()
    return 0


if __name__ == "__main__":
    sys.exit(main())
