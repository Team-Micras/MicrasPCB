# WallJoint

The main board's side of the joint with a wall-sensor board ([`boards/wall`](../../../boards/wall)):
6 plated holes at 1.27 x 1.27 mm for the long pins of the wall board's 2x03 straight header
([`HX-PZ1.27-2x3P-ZZ`](../../hanxia/HX-PZ1.27-2x3P-ZZ)), which straddles the wall board's bottom
edge; its insulator sits on the main board. Copper on the main board, not a purchased part, so it is
excluded from the BOM and the placement file. Evidence is in the docstring of
[`WallJoint.zen`](WallJoint.zen).

```python
WallJoint = Module("github.com/Team-Micras/MicrasPCB/components/micras/WallJoint/WallJoint.zen")

WallJoint(name="W1", PWM=Wall_Sensor_PWM_0, SINK=EMITTER_SINK, V3V3_D=V3V3_D, GND=GND, OUT=Wall_Sensor_0, V3V3_A=V3V3_A)
```

| Pad | Row, along the board (seen from the front) | Pin | Main board net |
|---|---|---|---|
| 1 | front, left | `OUT` | the receiver's output, `Wall_Sensor_n`, with its load at the ADC |
| 2 | back, left | `GND` | GND |
| 3 | front, middle | `3V3_A` | 3V3_A (the receiver's collector) |
| 4 | back, middle | `3V3_D` | 3V3_D (the emitter supply) |
| 5 | front, right | `SINK` | the shared emitter sink's drain, `EMITTER_SINK` |
| 6 | back, right | `PWM` | the selector's TIM3 channel, `Wall_Sensor_PWM_n` |

The receiver's output has only quiet neighbours (beside it, across the board and diagonally:
3V3_A, GND, 3V3_D); the switching pins sit at the other end.

## Footprint

`WallJoint_2x03_P1.27mm`: origin on the pattern's centre, under the wall board's mid-plane, the
sensor looking along -y (rotation 0: the robot's forward). Pads 1.10 mm (pad 1 square) on 0.70 mm
holes; odd pads in the front row (y = -0.635), even in the back row (y = +0.635), pins 1-2 at
x = +1.27 (the robot's right). F.CrtYd is the header's insulator (3.81 x 3.40 mm), on which
the wall board's 4.2 mm handle stands, plus 0.25 mm: 4.31 x 3.9 mm. Above it the wall board's
neck widens into its 8.4 mm blade, 3.06 mm or more over the main board outside the courtyard: F.Fab
draws the blade's overhang with its back-face parts (8.4 x 1.99 mm), under which main-board parts
stay at or below 2.55 mm
(`spec/wall.toml` `joint.under_blade`, `tests/test_main_layout.py`). The spec places each joint ([`spec/main.toml`](../../../spec/main.toml)
`[w1]`-`[w4]`, the wall board's mid-plane over the pattern's centre).

Properties `emitter_resistor` (3.3 Ohm, the wall board's R1) and `emitter_pulse_current`
(380 mA, the SFH 4550's rating) feed the main board's emitter checks
(`boards/main/test/test_sensors.zen`); `tests/test_wall.py` and `tests/test_wall_joint.py` hold them
to the wall board's.

## Test bench

[`test/test_WallJoint.zen`](test/test_WallJoint.zen): each pin on its net, not on the BOM, the
emitter resistor's value.
