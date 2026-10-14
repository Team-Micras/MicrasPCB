# TPS2121

Texas Instruments TPS2121RUXR (LCSC C485916): 2.8-22 V, 4.5 A dual-input priority power mux with
ideal-diode switchover and reverse current blocking, VQFN-HR-12 2.0 x 2.5 mm. Bare part: the
current-limit resistor, the soft-start capacitor, the bypass capacitors and the mode straps
belong to the board. Evidence is in the docstring of [`TPS2121.zen`](TPS2121.zen).

```python
TPS2121 = Module("github.com/Team-Micras/MicrasPCB/components/ti/TPS2121/TPS2121.zen")

# VCOMP mode: the higher valid input powers OUT.
TPS2121(
    name="U4",
    IN1=VBAT,
    IN2=VBUS,
    OUT=VSYS,
    GND=GND,
    PR1=GND,
    CP2=GND,
    OV1=GND,
    OV2=GND,
    ST=GND,
    ILM=ILM,
    SS=SS,
)
```

Reference prefix `U`.

## Pinout (SLVSEA3F Figure 6-2 and Pin Functions, p4-5)

| Pad | Name | Symbol type | io |
|---|---|---|---|
| 1, 8 | OUT | power_out | `OUT` |
| 2 | IN2 | power_in | `IN2` |
| 3 | CP2 | input | `CP2` |
| 4 | OV2 | input | `OV2` |
| 5 | OV1 | input | `OV1` |
| 6 | PR1 | input | `PR1` |
| 7 | IN1 | power_in | `IN1` |
| 9 | ST | open_collector | `ST` |
| 10 | ILM | passive | `ILM` |
| 11 | SS | passive | `SS` |
| 12 | GND | power_in | `GND` |

## Footprint

`Texas_RUX0012A_VQFN-HR-12_2x2.5mm_P0.5mm.kicad_mod`, drawn from TI's RUX0012A drawings in
SLVSEA3F (4224010/A):

- Land pattern (p39, non-solder-mask-defined): OUT (1, 8), IN2 (2) and IN1 (7) are 1.05 x 0.4 mm
  pads centred at x = +/-0.675 mm, y = -0.35 mm (1, 8) and +0.35 mm (2, 7); the eight signal
  pads are 0.2 x 0.6 mm at x = -0.75, -0.25, 0.25, 0.75 mm, y = +1.15 mm (3-6, left to right) and
  y = -1.15 mm (12-9, left to right); 0.05 mm corner radius. Top view: pin 1 is the upper left
  long pad, numbering counter-clockwise.
- Paste: the pads themselves (p40 stencil: 100 % printed coverage, same apertures).
- Body 2.0 x 2.5 mm on F.Fab (p38: 1.9-2.1 x 2.4-2.6 mm), pin-1 corner chamfered; F.CrtYd
  0.25 mm (IPC-7351B nominal) around the pads.
- 3D model: `TPS2121_RUX0012A_body.step`, a body envelope only: a 2.0 x 2.5 x 1.0 mm box (the
  p38 nominal outline and 1 mm maximum height), written for this package because neither TI nor
  the KiCad library provide a RUX0012A model. It has no leads. `pcb rectify check`: OK.
