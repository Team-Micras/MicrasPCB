"""The last pass on the main board's layout, as a one-off pcbnew script (KiCad 10).

    python3 boards/main/layout/finish.py

Runs once, after usb_wall.py and `make gen` (with R31-R33 on the 2512 land pattern). Every
coordinate is KiCad millimetres; the UUID prefixes name items of that layout. The steps, in order:

- settings: the settings of the Altium design that previous/transfer_layout.py gives a fresh
  transfer (see its docstring), from its own constants and functions: teardrop zones fill with a
  0.1 mm minimum width, the pours keep the Altium neck width (0.1 mm), the inner-layer pours
  relieve through-hole pads, the solder mask expands 0.02 mm, the LEDs D4/D5 have their datasheet
  heights in 3D, and the VBAT teardrops of the C1 chain that rework.py drops go. fixes.py,
  refine.py and usb_wall.py create copper with random UUIDs that the later ones name, so the
  chain does not replay on a new transfer; this applies the transfer's settings to its result.
  The pours fixes.py adds (the VSYS pour, the In2.Cu VBAT finger) keep their own settings;
- local: what the 2512 shunts' larger pads and courtyard touch: C33 (IC6's charge pump) turns and
  moves above C32, clear of R31's courtyard, and the SBU_DET_A via by R33's pad 2 moves 0.18 mm
  away from it; C69/C70 (EC1's supply capacitors) take 3V3 from EC1 pin 5's via, their own vias
  being in H2's In2.Cu void; D- gains three 0.8 mm bumps on B.Cu under the receptacle, which
  match it to D+ (the U6 detour and the turns make D+ longer);
- teardrops: a teardrop whose 0.1 mm fill touches nothing of its net (its track or via removed
  by an earlier script) goes, and so do the twin teardrops whose fills meet in a copper sliver
  (KiCad's copper_sliver check; found by removing each teardrop and re-running DRC);
- plane voids: the inner planes keep clear of the screw holes H1-H4 as transfer_layout.py's
  screw_hole_voids writes them;
then the zones are refilled, the board saved and `pcb layout` syncs it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "boards/main/previous"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixes as fx  # noqa: E402
import transfer_layout as tl  # noqa: E402
import usb_wall  # noqa: E402
from micras_pcb import sexpr  # noqa: E402

LAYOUT = ROOT / "boards/main/layout/main.kicad_pcb"
FIXES_POURS = {"b36b3480", "b4457722"}  # fixes.py: VSYS on B.Cu, the In2.Cu VBAT finger to U4
C1_TEARDROPS = {"7f402f92", "41cad02a"}  # VBAT teardrops on the C1 chain rework.py drops
# teardrops whose fills meet a twin's in a copper sliver
SLIVER_TEARDROPS = [
    "039ea097",
    "044c75c0",
    "0b414964",
    "0bf6e571",
    "148bc67c",
    "16e5f8f3",
    "3311fb9f",
    "38f3fc06",
    "569c9385",
    "8df50f70",
    "8e2781e6",
    "91a24496",
    "a3fe9ec4",
    "acb7b90b",
    "bfce9cce",
    "ce060783",
    "d4dfd47a",
    "f9ed3d77",
    "fa79d884",
    "fa963e48",
]


def settings() -> None:
    for z in list(fx.B.Zones()):
        uid = z.m_Uuid.AsString()[:8]
        if z.GetIsRuleArea() or uid in FIXES_POURS:
            continue
        if uid in C1_TEARDROPS:
            fx.drop([z])
            continue
        if z.GetAssignedPriority() >= tl.TEARDROP_PRIORITY:
            z.SetMinThickness(fx.mm(0.1))  # tl.TEARDROP_MIN_WIDTH
            continue
        layer = fx.B.GetLayerName(z.GetFirstLayer())
        z.SetMinThickness(fx.mm(tl.POUR_MIN_WIDTH[(layer, z.GetAssignedPriority())]))
        if layer in ("In1.Cu", "In2.Cu"):
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)  # tl.INNER_PADS
    for f in fx.B.GetFootprints():
        if f.GetReference() not in tl.LED_HEIGHT:
            continue
        models = f.Models()
        for k in range(len(models)):  # by index: iterating yields copies
            m = models[k]
            scale = m.m_Scale
            scale.z = round(tl.LED_HEIGHT[f.GetReference()] / tl.LED_MODEL_HEIGHT, 6)
            m.m_Scale = scale
    fx.B.GetDesignSettings().m_SolderMaskExpansion = fx.mm(0.02)


def _bump(x0: float, x1: float, y: float, h: float, c: float = 0.15) -> list[tuple[float, float]]:
    """A bump of height h upwards (towards -y) between x0 and x1 on a run at y, 45 degree corners."""
    return [(x0, y), (x0, y - h + c), (x0 + c, y - h), (x1 - c, y - h), (x1, y - h + c), (x1, y)]


def local() -> None:
    # C33: VBOOT (pad 2) left, VSPUMP (pad 1) right, in the free strip above C32
    fx.remove(fx.items(["69eb8d17", "6e605eb3", "36e0ce5e", "540c092f"]))
    fx.place("C33", 143.6, 121.6, 180)
    fx.track("DRIVERS.FAN_VBOOT", "F", 0.254, (142.864, 122.351), (143.12, 122.095), "C33.2")
    fx.track("DRIVERS.FAN_VSPUMP", "F", 0.254, (143.943, 124.35), (144.35, 123.943), (144.35, 121.85), "C33.1")
    # the SBU_DET_A via by R33's pad 2
    v, t1, t2 = fx.items(["ac223f8c", "4ac319e5", "7b95a550"])
    new = fx.pt(159.2, 125.879)
    v.SetPosition(new)
    t1.SetEnd(new)
    t2.SetStart(new)
    # C69/C70 3V3 from EC1.5's via, clear of H2's plane void
    fx.remove(fx.items(["c6602fbc", "2ff38cd6", "90f9f52a", "7e2831b2"]))
    fx.track("3V3", "F", 0.25, "C70.2", "C69.2", (157.98, 111.6), (157.518, 112.031))
    # D-: three bumps on its B.Cu run under the receptacle (y = 140.70), away from D+, below the
    # SBU contacts' B.Cu joint; each adds 2 x 0.8 - 1.172 x 0.15 = 1.42 mm
    (run,) = [
        t
        for t in fx.B.GetTracks()
        if t.GetNetname() == "USBD_N"
        and t.GetLayer() == fx.BK
        and abs(fx.xy(t.GetStart())[1] - 140.70) < 1e-3
        and abs(fx.xy(t.GetEnd())[1] - 140.70) < 1e-3
    ]
    (xa, _), (xb, _) = sorted([fx.xy(run.GetStart()), fx.xy(run.GetEnd())])
    fx.remove([run])
    pts = [(xa, 140.70)]
    for x0 in (148.4, 149.6, 150.8):
        pts += _bump(x0, x0 + 0.6, 140.70, 0.8)
    pts.append((xb, 140.70))
    fx.track("USBD_N", "B", 0.2248, *pts)
    usb_wall.MOVED = ["C33"]
    usb_wall.silkscreen()


def teardrops() -> None:
    fx.remove(fx.items(SLIVER_TEARDROPS))
    pcbnew.ZONE_FILLER(fx.B).Fill(fx.B.Zones())
    fx.B.BuildConnectivity()
    conn = fx.B.GetConnectivity()
    lone = []
    for z in fx.B.Zones():
        if z.GetIsRuleArea() or z.GetAssignedPriority() < tl.TEARDROP_PRIORITY:
            continue
        if not any(i.GetClass() in ("PCB_TRACK", "PCB_ARC", "PCB_VIA", "PAD") for i in conn.GetConnectedItems(z)):
            lone.append(z)
    fx.drop(lone)


def plane_voids() -> None:
    """The screw-hole voids of the inner planes, as transfer_layout.screw_hole_voids writes them."""
    text = LAYOUT.read_text()
    root = sexpr.parse(text)
    have = {z.child("uuid").atoms()[0] for z in root.children("zone") if z.child("uuid")}
    voids = [v for v in tl.screw_hole_voids() if sexpr.parse(v).child("uuid").atoms()[0] not in have]
    if voids:
        anchor = root.child("embedded_fonts") or root.children()[-1]
        at = sexpr.line_span(text, anchor)[0]
        LAYOUT.write_text(sexpr.splice(text, [(at, at, "".join(voids))]))


def main() -> int:
    fx.B = pcbnew.LoadBoard(str(LAYOUT))
    settings()
    local()
    teardrops()
    pcbnew.SaveBoard(str(LAYOUT), fx.B)
    plane_voids()
    b = pcbnew.LoadBoard(str(LAYOUT))
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(str(LAYOUT), b)
    tl.pcb_layout()
    return 0


if __name__ == "__main__":
    sys.exit(main())
