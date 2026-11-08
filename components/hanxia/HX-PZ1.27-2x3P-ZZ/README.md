# HX-PZ1.27-2x3P-ZZ

Hanxia HX PZ1.27-2x3P ZZ (LCSC C22438118): 2x03 pin header, 1.27 mm pitch, straight. Bare part,
footprinted as a straddle (edge) mount: a 0.8 mm board stands between its two rows with its bottom
edge on the insulator, the short pins soldered to SMD pads on both faces, and the long pins go down
into a 2x03 1.27 mm hole pattern on the board below. Any board with that pattern takes the module.
Evidence is in the docstring of [`HX-PZ1.27-2x3P-ZZ.zen`](HX-PZ1.27-2x3P-ZZ.zen).

```python
HX_PZ127_2x3 = Module("github.com/Team-Micras/MicrasPCB/components/hanxia/HX-PZ1.27-2x3P-ZZ/HX-PZ1.27-2x3P-ZZ.zen")

HX_PZ127_2x3(name="J1", P1=WALL_SENSOR, P2=GND, P3=V3V3_A, P4=V3V3_D, P5=EMITTER_SINK, P6=PWM)
```

Pins `P1`-`P6`: 1, 3, 5 along the front row (pin 1 at x = -1.27 mm, square pad), 2, 4, 6 behind
them. Reference prefix `J`.

| Drawing (rev A, 2023-07-18) | Value |
|---|---|
| pins | 0.40 mm square, 1.27 +-0.1 mm along the rows, rows 1.27 mm apart |
| pin lengths | 2.30 +-0.2 mm above the insulator (on the upright board), 3.90 +-0.2 mm below (into the board below) |
| insulator | 3.81 +-0.3 x 3.40 x 1.00 mm |
| recommended holes | 0.65 mm at 1.27 x 1.27 mm |
| between the rows | 1.27 - 0.40 = 0.87 mm, for a 0.8 mm board (0.7-0.9 mm at JLCPCB's +-0.1 mm) |

## Files

- `HX-PZ1.27-2x3P-ZZ.kicad_sym`: KiCad 10 symbol, odd pins left, even pins right, names hidden.
- `HX-PZ1.27-2x3P-ZZ_Straddle.kicad_mod`: the upright board's side: 0.70 x 2.60 mm SMD pads at
  1.27 mm, odd pins on F.Cu and even pins on B.Cu, from 0.2 mm above the board's bottom edge to
  0.3 mm past the longest pin; origin on the bottom edge between the rows; the insulator below the
  edge and the pins on the Fab layers. Its 3D model is embedded.
- [`model.py`](model.py): builds that model from the drawing (build123d); run it, then
  `pcb embed-step`, as its docstring says. The STEP itself is not kept.

The board below drills its own 2x03 pattern (the Micras main board:
[`components/micras/WallJoint`](../../micras/WallJoint)).

## Test bench

[`test/test_HX-PZ1.27-2x3P-ZZ.zen`](test/test_HX-PZ1.27-2x3P-ZZ.zen): the orderable part and each
pin on its own net.
