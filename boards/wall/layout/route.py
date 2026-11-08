"""Place and route the wall-sensor board (one-off pcbnew script; the .kicad_pcb is the source).

`micras-pcb mech wall` owns the outline and the locked W1 (the sensor) and J1 (the 2x3 header
straddling the bottom edge: pins 1, 3, 5 on front pads, 2, 4, 6 on back pads). This script puts
every SMD part on the back, draws the tracks, the GND vias and the GND pours of both layers, and
fills them. It starts from the generated layout and replaces every track, via and zone, so it can
be rerun:

    /usr/bin/python3 boards/wall/layout/route.py && make gen && make check

Coordinates are the spec frame (spec/wall.toml): u right seen from the front, v up from the main
board's top surface (the board's bottom edge at v 1.0); mm. The back face's free areas, between
the courtyards of J1 (its pads, up to v 3.95) and of W1's lead joints (|u| <= 2.27 at v
6.55-8.45 and 12.6-14.6), are the neck above the handle, the columns beside the
receiver's leads, the middle (v 8.45-12.6) and the top strip (v 14.6-16.8). The board is a paddle
(spec/wall.toml [outline]): the 4.2 mm handle holds only the header's pads, the neck (v 2.74-8.8)
and the 8.4 mm blade everything else.

- Front (F.Cu): the receiver and the sink. Wall_Sensor straight down from the TPS601A's emitter
  (left) to pin 1 under it; 3V3_A from its collector to pin 3; EMITTER_SINK from pin 5 up the
  handle, out through the neck to the blade's right side (0.88 mm from the collector's pad) and
  across the middle to a via beside Q1's source. The rest is the GND pour.
- Back (B.Cu): the emitter. PWM from pin 6 up the handle and out to R2 beside the receiver's
  collector lead, DRIVE up to C2 above it, the gate up the right side, across the top and down the
  centre between the emitter's leads to Q1's gate, with R3 and the clamp D1 in the top strip; Q1
  in the middle, its drain up to the SFH 4550's cathode; 3V3_D from pin 4 up the centre, between
  the receiver's leads (a quiet net), to R1 beside the emitter's anode, with C1 across pins 2 and
  4 above the handle. The rest is the GND pour; the board's name runs up the back's left side.
- Tracks 0.3 mm; tented 0.3 / 0.6 mm vias: the sink's, and GND vias joining the pours.
"""

from __future__ import annotations

import itertools
import sys
import tomllib
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[3]
PCB = ROOT / "boards/wall/layout/wall.kicad_pcb"
PRO = PCB.with_suffix(".kicad_pro")
SPEC = tomllib.loads((ROOT / "spec/wall.toml").read_text())
OX, OY = SPEC["kicad"]["origin_x"]["value"], SPEC["kicad"]["origin_y"]["value"]
WIDTH = 0.3
VIA_D, VIA_HOLE = 0.6, 0.3
HW = SPEC["outline"]["width"]["value"] / 2
BOTTOM = SPEC["outline"]["bottom"]["value"]
TOP = SPEC["outline"]["top"]["value"]
SIDE_U = 3.0  # the sink's (front) and the gate's (back) runs up the blade's right side: 0.85 mm from its edge

# Centre (u, v) of each SMD part on the back, and the pad layout it is turned to:
# (pad a, pad b, "up"|"right"): pad b lies straight above / right of pad a; None for Q1.
PARTS = {
    "Q1": ((-1.3, 10.5), None),  # drain (3) left, gate (1) above source (2) on the right: see turned()
    "R1": ((1.85, 10.0), ("2", "1", "up")),  # 3V3_D below, LED_A above
    "C1": ((-0.775, 5.35), ("1", "2", "right")),  # GND left (over pin 2), 3V3_D right (over pin 4)
    "R2": ((3.1, 7.3), ("2", "1", "up")),  # PWM below, DRIVE above, beside the receiver's collector
    "C2": ((3.1, 9.2), ("1", "2", "up")),  # DRIVE below, GATE above
    "D1": ((1.05, 15.65), ("1", "2", "right")),  # cathode (GATE) left, anode (GND) right
    "R3": ((-1.6, 15.65), ("1", "2", "right")),  # GND left, GATE right
}

# J1's pads (u, v): pin n at u = -1.27, 0, +1.27 for pins 1-2, 3-4, 5-6 (odd front, even back),
# their centres half way up the 2.6 mm pads; W1's leads from the spec.
PAD_V = BOTTOM + 0.2 + 1.3
J = {n: (round(-1.27 + 1.27 * ((n - 1) // 2), 4), PAD_V) for n in range(1, 7)}
PT_V = SPEC["sensor"]["v"]["value"]
LED_V = PT_V + SPEC["sensor"]["led_above"]["value"]
LED_A, LED_K = (1.27, LED_V), (-1.27, LED_V)
PT_C, PT_E = (1.27, PT_V), (-1.27, PT_V)
SINK_VIA = (0.8, 9.55)  # beside Q1's source, between it and R1
TRUNK_V = 8.5  # v where 3V3_D turns from the centre to R1, above the receiver's collector pad
GATE_V = 14.8  # v of the gate's run across the top, above the emitter's leads


def tracks(pad):
    """(net, layer, points) of every track; pad(ref, number) is a pad's (u, v)."""
    q_d, q_g, q_s = pad("Q1", "3"), pad("Q1", "1"), pad("Q1", "2")
    r1_3v3, r1_led = pad("R1", "2"), pad("R1", "1")
    c1_3v3 = pad("C1", "2")
    r2_pwm, r2_drv = pad("R2", "2"), pad("R2", "1")
    c2_drv, c2_gate = pad("C2", "1"), pad("C2", "2")
    d1_k, r3_gate = pad("D1", "1"), pad("R3", "2")
    sink_up = 5.0  # where the sink leaves pin 5's line for the blade's side, above the shoulder
    pwm_up = r2_pwm[1] - (r2_pwm[0] - J[6][0])  # where PWM leaves pin 6's line, 45 deg to R2
    return [
        # front: the receiver, and the sink up the right edge
        ("Wall_Sensor", "F.Cu", [J[1], PT_E]),
        ("3V3_A", "F.Cu", [J[3], (0.0, PT_C[1] - PT_C[0]), PT_C]),
        (
            "EMITTER_SINK",
            "F.Cu",
            [J[5], (J[5][0], sink_up), (SIDE_U, sink_up + SIDE_U - J[5][0]), (SIDE_U, SINK_VIA[1]), SINK_VIA],
        ),
        # back: the emitter
        ("EMITTER_SINK", "B.Cu", [SINK_VIA, q_s]),
        ("PWM", "B.Cu", [J[6], (J[6][0], pwm_up), r2_pwm]),
        ("DRIVE", "B.Cu", [r2_drv, c2_drv]),
        (
            "GATE",
            "B.Cu",
            [c2_gate, (c2_gate[0], GATE_V - 0.3), (c2_gate[0] - 0.3, GATE_V), (0.0, GATE_V)],
        ),
        ("GATE", "B.Cu", [(0.0, GATE_V), (0.0, q_g[1] - q_g[0]), q_g]),
        ("GATE", "B.Cu", [(0.0, GATE_V), d1_k]),
        ("GATE", "B.Cu", [d1_k, r3_gate]),
        ("LED_K", "B.Cu", [q_d, (q_d[0], LED_K[1] - (LED_K[0] - q_d[0])), LED_K]),
        ("3V3_D", "B.Cu", [J[4], c1_3v3]),
        ("3V3_D", "B.Cu", [c1_3v3, (0.0, TRUNK_V), (r1_3v3[0], TRUNK_V), r1_3v3]),
        ("LED_A", "B.Cu", [r1_led, (r1_led[0], LED_A[1] - (r1_led[0] - LED_A[0])), LED_A]),
    ]


# GND vias joining the back pour to the front's: in the neck's left, beside the emitter's
# cathode lead and in the top strip.
GND_VIAS = [(-2.7, 5.9), (-3.2, 12.8), (-3.2, 14.9)]
LABEL = (-3.6, 10.7)  # the board's name on the back silkscreen, up the blade's left side


def mm(v: float) -> int:
    return pcbnew.FromMM(v)


def pt(u: float, v: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(OX + u), mm(OY - v))


def main() -> int:
    pro = PRO.read_bytes()  # Board.Save() rewrites the project file: keep the generated one
    b = pcbnew.LoadBoard(str(PCB))
    layers = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}
    nets = b.GetNetsByName()
    fps = {f.GetReference(): f for f in b.GetFootprints()}

    # removed last-in-first-out, the board deleting each (a SWIG zone proxy cannot be handed back)
    for item in [*b.GetTracks(), *b.Zones()][::-1]:
        b.Delete(item)

    def pad(ref: str, num: str) -> tuple[float, float]:
        p = fps[ref].FindPadByNumber(num).GetPosition()
        return round(pcbnew.ToMM(p.x) - OX, 4), round(OY - pcbnew.ToMM(p.y), 4)

    def turned(ref: str, rule) -> bool:
        if rule is None:  # Q1: drain left of the centre, gate straight above source on the right
            c, d, g, s = PARTS[ref][0], pad(ref, "3"), pad(ref, "1"), pad(ref, "2")
            return d[0] < c[0] and abs(g[0] - s[0]) < 1e-3 and g[1] > s[1] and g[0] > c[0]
        a, c = pad(ref, rule[0]), pad(ref, rule[1])
        if rule[2] == "up":
            return c[1] > a[1] and abs(c[0] - a[0]) < 1e-3
        return c[0] > a[0] and abs(c[1] - a[1]) < 1e-3

    for ref, (at, rule) in PARTS.items():
        f = fps[ref]
        if not f.IsFlipped():
            f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        f.SetPosition(pt(*at))
        f.Reference().SetLayer(pcbnew.B_Fab)
        for rot in (0, 90, 180, 270):
            f.SetOrientationDegrees(rot)
            if turned(ref, rule):
                break
        else:
            raise SystemExit(f"{ref}: no rotation gives its pad layout")

    for name, layer, pts in tracks(pad):
        for a, c in itertools.pairwise(pts):
            if a == c:
                continue
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(pt(*a))
            t.SetEnd(pt(*c))
            t.SetWidth(mm(WIDTH))
            t.SetLayer(layers[layer])
            t.SetNet(nets[name])
            b.Add(t)
    for net, (u, v) in [("EMITTER_SINK", SINK_VIA), *(("GND", at) for at in GND_VIAS)]:
        via = pcbnew.PCB_VIA(b)
        via.SetPosition(pt(u, v))
        via.SetWidth(mm(VIA_D))
        via.SetDrill(mm(VIA_HOLE))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetNet(nets[net])
        via.SetFrontTentingMode(pcbnew.TENTING_MODE_TENTED)
        via.SetBackTentingMode(pcbnew.TENTING_MODE_TENTED)
        b.Add(via)

    for layer in ("F.Cu", "B.Cu"):
        z = pcbnew.ZONE(b)
        z.SetLayer(layers[layer])
        z.SetNet(nets["GND"])
        o = z.Outline()
        o.NewOutline()
        for u, v in ((-HW, BOTTOM), (HW, BOTTOM), (HW, TOP), (-HW, TOP)):
            o.Append(mm(OX + u), mm(OY - v))
        z.SetAssignedPriority(0)
        z.SetLocalClearance(mm(0.2))
        z.SetMinThickness(mm(0.2))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        z.SetZoneName(f"GND {layer[0]}")
        b.Add(z)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())

    keep = []  # removed items stay referenced until the board is saved (SWIG)
    for old in [d for d in b.GetDrawings() if d.GetClass() == "PCB_TEXT" and d.GetText() == "MICRAS WALL"]:
        keep.append(old)
        b.Remove(old)
    text = pcbnew.PCB_TEXT(b)
    text.SetText("MICRAS WALL")
    text.SetLayer(pcbnew.B_SilkS)
    text.SetTextSize(pcbnew.VECTOR2I(mm(0.6), mm(0.6)))
    text.SetTextThickness(mm(0.12))
    text.SetMirrored(True)
    text.SetTextAngleDegrees(90)
    text.SetPosition(pt(*LABEL))
    b.Add(text)

    b.Save(str(PCB))
    PRO.write_bytes(pro)
    return 0


if __name__ == "__main__":
    sys.exit(main())
