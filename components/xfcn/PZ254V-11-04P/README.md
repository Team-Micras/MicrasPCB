# PZ254V-11-04P

1x04 male pin header, 2.54 mm pitch, vertical, through hole (XFCN PZ254V-11-04P, LCSC C2691448).

```python
PZ254V_11_04P = Module("github.com/Team-Micras/MicrasPCB/components/xfcn/PZ254V-11-04P/PZ254V-11-04P.zen")

PZ254V_11_04P(name="P1", P1=V3V3, P2=GND, P3=SWDIO, P4=SWCLK)
```

| Pad | io |
|---|---|
| 1 (rounded square) | `P1` |
| 2 | `P2` |
| 3 | `P3` |
| 4 | `P4` |

- Config `prefix` (default `P`) sets the reference designator prefix, so the header can be `P1`
  or `J1`. A refdes-like instance name is kept only when it starts with this prefix.
- The stdlib `PinHeader` generic is not used here: its prefix is fixed to `J` and its footprint
  has 1.7 mm pads.

## Footprint

`PinHeader_1x04_P2.54mm_Vertical_D1.8mm.kicad_mod` is the Altium MicrasLib footprint
`HDR MALE 1x4` of the Micras main board: 1.0 mm drills, 1.8 mm pads (pad 1 rounded square, the
others round), pads along +X from pad 1 at the origin. Pitch, drill and numbering match KiCad's
`PinHeader_1x04_P2.54mm_Vertical` (pads along +Y there, 1.7 mm). The outline is drawn on F.SilkS
and B.Fab; there is no F.CrtYd courtyard. The embedded STEP is
`Pin Header 1x4 TH Pitch 2.54mm.stp`. `pcb rectify check`: model transform OK.
