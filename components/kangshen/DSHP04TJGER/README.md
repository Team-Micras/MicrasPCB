# DSHP04TJGER

Kangshen DSHP04TJGER (LCSC C3293150): 4-position SPST DIP switch, SMD J-lead, 1.27 mm pitch, 25 mA at
24 VDC switching. Evidence is in the docstring of [`DSHP04TJGER.zen`](DSHP04TJGER.zen).

```python
DipSwitch = Module("github.com/Team-Micras/MicrasPCB/components/kangshen/DSHP04TJGER/DSHP04TJGER.zen")

DipSwitch(
    name="SW1",
    S1_A=SWITCH_0, S2_A=SWITCH_1, S3_A=SWITCH_2, S4_A=SWITCH_3,
    S1_B=GND, S2_B=GND, S3_B=GND, S4_B=GND,
)
```

Switch n is between `Sn_A` (pad n, row 1-4) and `Sn_B` (pad 9-n, the facing pad on row 5-8):

| Switch | `Sn_A` pad | `Sn_B` pad |
|---|---|---|
| 1 | 1 | 8 |
| 2 | 2 | 7 |
| 3 | 3 | 6 |
| 4 | 4 | 5 |

The datasheet numbers the pins in pairs (switch n between its pins 2n-1 and 2n); the footprint numbers
them by row, which is what the symbol follows. The STEP model prints 1-4 over pads 1-4 and "ON" on
the pad 5-8 side; the datasheet drawing does not tie the body marks to pads.

`pcb rectify check` flags the STEP model as offset by 0.33 mm (proposed fix: offset
(-0.056, 0.325, 0.95) mm). A KiCad render shows the body centred on the pads, so the model transform
is kept as is.

The silkscreen "ON" marks over the switch levers are 0.6 mm high with a 0.1 mm stroke, the
boards' minimum text height (0.6 mm) and above their minimum stroke (0.08 mm).

Courtyard: an F.CrtYd rectangle around the body outline (User.15) and the pads, 0.25 mm, the
IPC-7351B nominal courtyard excess (KiCad Library Conventions F5.3).
