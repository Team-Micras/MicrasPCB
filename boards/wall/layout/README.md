# Wall-sensor board

One per wall sensor, four on a robot, all alike. An SFH 4550 IR emitter 6.1 mm above a TPS601A(F)
phototransistor, with the emitter's resistor and its selector, on a 2-layer, 0.79 mm board shaped
like a paddle (a 4.2 mm handle in the header, an 8.4 mm blade for the sensor, 16.0 mm high) that
stands upright on the main board, looking at the wall. Both optical parts sit
with their flanges on the board's front face and their leads straight through it, so the board sets
where they look. A 2x3 1.27 mm straight header straddles the board's bottom edge: the board stands
between its two rows with its edge on the insulator, the short pins soldered to pads on both faces,
and the long pins go down through the main board's plated holes, on which the insulator sits. The
board is ordered with PCBA: JLCPCB fits the SMD parts, all on the back face; the team solders the
sensor and the header by hand.

## Files

The board files are in `boards/wall/` (this README sits in its `layout/` folder); `spec/` is at the
repository root.

| File | Contents |
|---|---|
| [`wall.zen`](../wall.zen) | W1 (the sensor, upright), R1 and C1 (emitter supply), Q1, R2, C2, R3 and D1 (the emitter's selector and its AC-coupled gate), the header J1, net names, stackup and rules; the circuit's analysis in its docstring |
| [`schematic/`](../schematic) | how the sheet is drawn (`micras-pcb sch`) |
| [`test/`](../test) | `pcb test` bench of the board's circuit: J1's pin map, the emitter resistor and the selector on the cathode with its source on J1's sink pin, the AC-coupled gate (series capacitor from the PWM's resistor, pull-down, clamp, 3-10 ms), the decoupling, the receiver's output leaving unloaded |
| [`layout/`](.) | this folder: the KiCad project; the `.kicad_pcb` holds placement and routing; [`route.py`](route.py) is the script that placed the SMD parts and routed the board |
| [`spec/wall.toml`](../../../spec/wall.toml) | mechanical interface: thickness, outline, the sensor and header positions, the header's drawing numbers, the main board's holes |

## Circuit

| Designator | Part | Package | Notes |
|---|---|---|---|
| W1 | SFH 4550 (ams-OSRAM) over a TPS601A(F) (Toshiba) ([`components/micras/WallSensor`](../../../components/micras/WallSensor), mount `upright`) | through-hole, `WallSensor_SFH4550_TPS601A_Upright` | bought separately and hand-soldered, not in the BOM |
| R1 | UNI-ROYAL 0603WAF330KT5E, 3.3 Ohm 1 % 100 mW (LCSC C22979, extended) | 0603 | 3V3_D to the emitter's anode |
| C1 | Samsung CL10A105KB8NNNC, 1 uF 10 % 50 V X5R (LCSC C15849, basic) | 0603 | 3V3_D decoupling, across J1's GND and 3V3_D pins |
| Q1 | AOS AO3400A (LCSC C20917, basic) ([`components/aos/AO3400A`](../../../components/aos/AO3400A)) | SOT-23 | the emitter's selector: drain on the cathode, source on `EMITTER_SINK` |
| R2 | UNI-ROYAL 0402WGF2200TCE, 220 Ohm 1 % (LCSC C25091, basic) | 0402 | `PWM` to the gate network's drive node |
| C2 | Samsung CL05B224KO5NNNC, 220 nF 10 % 16 V X7R (LCSC C16772, basic) | 0402 | drive node to the gate (the AC coupling) |
| R3 | UNI-ROYAL 0402WGF2202TCE, 22 kOhm 1 % (LCSC C25768, basic) | 0402 | gate pull-down |
| D1 | JCET 1N4148WS (LCSC C2128, basic) ([`components/cj/1N4148WS`](../../../components/cj/1N4148WS)) | SOD-323 | gate clamp, anode on GND |
| J1 | Hanxia HX PZ1.27-2x3P ZZ, 2x03 1.27 mm straight header (LCSC C22438118) ([`components/hanxia/HX-PZ1.27-2x3P-ZZ`](../../../components/hanxia/HX-PZ1.27-2x3P-ZZ)) | straddle, `HX-PZ1.27-2x3P-ZZ_Straddle` | the joint to the main board; `assembly = "hand"` |

| J1 pin | Face, along the edge (seen from the front) | Net | On this board | On the main board ([`WallJoint`](../../../components/micras/WallJoint) pad) |
|---|---|---|---|---|
| 1 | front, left | `Wall_Sensor` | W1 pad 4, the TPS601A emitter, straight above | the ADC input and its 1 kOhm load, `Wall_Sensor_n` |
| 2 | back, left | `GND` | C1, both pours | GND |
| 3 | front, middle | `3V3_A` | W1 pad 3, the TPS601A collector | 3V3_A |
| 4 | back, middle | `3V3_D` | C1, R1 | 3V3_D |
| 5 | front, right | `EMITTER_SINK` | Q1 source | the shared constant-current sink's drain (Q9) |
| 6 | back, right | `PWM` | R2 | the selector's TIM3 channel, `Wall_Sensor_PWM_n` |

The receiver's output takes one corner: beside it, across the board and diagonally sit only quiet
nets (3V3_A, GND, 3V3_D); the switching pins take the far corner pair (`tests/test_wall.py`).

The circuit is the main board's wall-sensor channel; the analysis is in
[`wall.zen`](../wall.zen)'s docstring. The board holds what belongs at the sensor: the emitter
resistor, which limits a failed sink's current within the SFH 4550's pulse rating and leaves the
selector its headroom, its 1 uF, and the selector with its AC-coupled gate, so a PWM pin held high
cannot keep the emitter on (the gate decays with 22 kOhm x 220 nF = 4.8 ms). The shared
constant-current sink and the receiver's 1 kOhm load stay on the main board. The phototransistor
is a current source, so with its load at the ADC the signal crosses the joint as a current and a
ground offset between the boards does not reach the reading. The emitter's pulse current enters
on `3V3_D` and leaves on `EMITTER_SINK`, never through the GND the receiver shares.

## Layout

Coordinates in the spec frame: u right seen from the front, v up from the main board's top
surface; the board's bottom edge is at v 1.0, on the header's insulator.

- W1 and J1 are locked where `spec/wall.toml` puts them: the TPS601A axis 7.5 mm above the main
  board's top surface, the SFH 4550 axis 13.6 mm, J1's origin on the bottom edge's middle. Seen
  from the front, pin 1 of every part is on the left: the SFH cathode with its flange flat, the
  TPS601A emitter with its key tab, J1 pin 1 (square pad, a silk bar above it).
- J1's pads: 0.70 x 2.60 mm at u -1.27, 0, +1.27, from 0.2 mm above the bottom edge to v 3.8, odd
  pins on the front, even on the back. The 2.30 mm pins end at v 3.3 (+-0.2); the TPS601A flange
  bottoms at v 4.6 on the centre line and 4.89 over the outer pins, so it clears the front joints by
  0.8 mm or more, and a key tab pointing down at pin 1 would keep 0.93 mm from its pad.
- Front (F.Cu), under the flanges, no parts: `Wall_Sensor` straight down from the TPS601A's
  emitter to pin 1, `3V3_A` from its collector to pin 3, `EMITTER_SINK` from pin 5 up the handle,
  out through the neck to the blade's right side (0.88 mm from the collector's pad, 0.85 mm from the edge) and
  across the middle to a via beside Q1's source. The rest is the GND pour.
- Back (B.Cu), every SMD part, all on the blade (the handle holds only J1's pads): `PWM` from
  pin 6 up the handle and out to R2 beside the receiver's collector lead, C2 above it, the gate up
  the right side (0.95 mm from the edge), across the top and down the centre between the emitter's
  leads to Q1's gate, with R3 and D1 in the top strip; Q1 in the middle, its drain pad 1.28 mm
  from the left edge, its drain up to the SFH 4550's cathode; C1 across pins 2 and 4 in the
  neck; `3V3_D` from pin 4 up the centre, between the receiver's leads, to R1 beside the
  emitter's anode. The rest is the GND pour.
- The receiver's output keeps 0.5 mm or more of copper-free gap from every switched net (`PWM`,
  `DRIVE`, `GATE`, `LED_K`, `EMITTER_SINK`) on its layer, and no switched
  track runs over or under it (1.55 mm on the front, 0.97 mm on the back at the nearest; `tests/test_wall.py`).
- 0.3 mm tracks; tented 0.3 / 0.6 mm vias: the sink's, and three joining the GND pours. The SMD
  parts' designators on B.Fab; the board's name runs up the back's left side.
- Shape (spec/wall.toml `[outline]`): the handle, 4.2 mm wide (J1's outer pads 0.48 mm from its
  edges; within the main board's 4.31 mm joint courtyard, the insulator plus its margin), runs
  straight from the bottom edge (v 1.0) to v 2.74. The neck is one smooth S-curve a side over
  6.1 mm, up to v 8.8: a 1.0 mm inside arc (JLCPCB mills 0.5 mm), then an 8.8 mm outside arc
  tangent to the 8.4 mm blade's side. The TPS601A flange stays 1.12 mm inside the outline at every
  height; the SFH 4550's keeps 1.25 mm from the sides and 0.45 mm from the top edge. The neck is as
  long as the flange and the main board allow: lower, the blade would come down onto the main
  board's 2.5 mm capacitors beside W1/W4's joints.
- Copper to edge: J1's pads 0.48 mm, the handle's tracks 0.68 mm, R2 0.50 mm, the GND vias
  0.65 mm or more, C1 1.12 mm.
- Stackup: the encoder board's, 0.70 mm FR-4 core and 35 um copper, 0.79 mm with Zener's 10 um
  mask a side; ordered as JLCPCB's 0.8 mm 2-layer board.

## Mechanics

[`spec/wall.toml`](../../../spec/wall.toml): origin on the main board's top surface under the
middle of the bottom edge, u right seen from the front, v up. `micras-pcb mech wall` draws the
outline: the handle's straight bottom edge at v 1.0 with square corners, the neck's arcs into the
8.4 mm blade, 17.0 mm high with 1.0 mm top corners. It exports `build/wall/wall_mech.json`: the outline, the two optical axes and
the joint (pins, rows, insulator, pin ends).

The joint (Hanxia drawing HX PZ1.27-2x3P ZZ rev A, 2023-07-18): 0.40 mm square pins at 1.27 mm,
the rows 1.27 mm apart, so 0.87 mm between them for the board: 0.04 mm a side at 0.79 mm; at
JLCPCB's +-0.1 mm a 0.9 mm board presses the rows 0.03 mm apart and a 0.7 mm one leaves 0.085 mm a
side for the solder. The insulator, 3.81 x 3.40 x 1.00 mm, sits on the main board under the
handle and reaches 1.3 mm in front of the front face. The main board's joint courtyard is the
insulator (4.31 x 3.9 mm with its margin); outside it the blade's overhang runs 3.06 mm or more
over the main board, and main-board parts under it stay at or below 2.55 mm. The 2.30 mm pins clamp the board; the
3.90 mm pins go through the main board's 0.70 mm holes (1.10 mm pads) and come out 2.86 mm below
it. The main board's 2x3 pattern has its centre under this board's mid-plane, its front row (odd
pins) ahead (components/micras/WallJoint).

Assembly: JLCPCB fits the back's SMD parts. Then solder W1's two parts from the back. Slide the
board between the header's rows down to the insulator, square it, and solder the six pins to their
pads on both faces. Stand the header's long pins in the main board's holes with the insulator flat
on it, square the board against a jig, solder the pins under the main board and trim them to
0.5 mm or less (the main board rides 0.7-0.85 mm off the floor, `boards/main/layout/README.md`).

## Known faults

None: the wall board passes every gate of `make check` (build, warnings, its test bench,
layout-check, ERC, LVS, DRC, DFM, its pytests, parts).

## Open items

- [ ] The insulator's 1.00 mm height carries no tolerance on the drawing (its title block gives
      X.XX +-0.20): the optical axes move with it. Measure a part.
- [ ] MicrasHardware's sensor caps hold the bent-lead sensors: point them at
      `build/wall/wall_mech.json`; the header's insulator stands 1.0 mm high and 1.3 mm in front
      of the board.
- [ ] Check the TPS601A key tab's direction on a real part (the courtyard takes it up-left; the
      board also clears it pointing down).
- [ ] Check each SMD part's rotation once in JLCPCB's placement preview (`rotation_verified` in
      `parts/jlc.toml`).
