# PZ254V-11-05P

1x05 male pin header, 2.54 mm pitch, vertical, through hole (XFCN PZ254V-11-05P, LCSC C492404).
Evidence is in the docstring of [`PZ254V-11-05P.zen`](PZ254V-11-05P.zen).

```python
PZ254V_11_05P = Module("github.com/Team-Micras/MicrasPCB/components/xfcn/PZ254V-11-05P/PZ254V-11-05P.zen")

PZ254V_11_05P(name="P1", P1=PROBE_3V3, P2=GND, P3=SWDIO, P4=SWCLK, P5=NRST)
```

| Pad | io |
|---|---|
| 1 (rounded square) | `P1` |
| 2 | `P2` |
| 3 | `P3` |
| 4 | `P4` |
| 5 | `P5` |

- Config `prefix` (default `P`) sets the reference designator prefix, so the header can be `P1`
  or `J1`. A refdes-like instance name is kept only when it starts with this prefix.
- The stdlib `PinHeader` generic is not used here: its prefix is fixed to `J` and its footprint
  has 1.7 mm pads.

## Footprint

`PinHeader_1x05_P2.54mm_Vertical_D1.8mm.kicad_mod`: five 1.8 mm pads on 1.0 mm drills, 2.54 mm
pitch, pad 1 (rounded square) at the origin and the others along +X: the pad and drill of the
PZ254V-11-04P footprint (Altium MicrasLib `HDR MALE 1x4`) at five positions. The XFCN drawing
recommends a 1.02 mm hole for the 0.64 mm square pin. Insulator outline 12.70 x 2.50 mm on
F.SilkS and F.Fab (from x = -1.27 mm), F.CrtYd 0.5 mm around it (IPC-7351B connector courtyard).
The embedded STEP is KiCad's `PinHeader_1x05_P2.54mm_Vertical.step`, rotated -90 degrees about Z
so its pins run along +X from pad 1 (checked on a VRML export of the footprint; `pcb rectify
check`: OK).
