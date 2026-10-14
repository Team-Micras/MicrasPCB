# USBLC6-2SC6

STMicroelectronics USBLC6-2SC6 (LCSC C7519): two-line, very low capacitance (3.5 pF max) ESD
protection with a rail clamp, SOT23-6L, for USB 2.0 and similar data lines. Evidence is in the
docstring of [`USBLC6-2SC6.zen`](USBLC6-2SC6.zen).

```python
USBLC6_2SC6 = Module("github.com/Team-Micras/MicrasPCB/components/st/USBLC6-2SC6/USBLC6-2SC6.zen")

USBLC6_2SC6(name="U6", IO1=USB.D.P, IO2=USB.D.N, VBUS=V3V3, GND=GND)
```

Reference prefix `U`; component type `esd`.

- `VBUS` is the rail pin: the steering diodes of both lines meet there and the internal transil
  clamps it to GND (Figure 6). Connect it to the supply the protected lines swing to: a line
  more than a diode drop above that supply conducts into it (section 2.1).
- Place it at the connector with short tracks to the lines, the rail and GND (section 2.3).

## Pinout (DocID 11265 Rev 5, Figure 1, top view)

| Pad | Name | Symbol type | io |
|---|---|---|---|
| 1, 6 | I/O1 | passive | `IO1` |
| 2 | GND | power_in | `GND` |
| 3, 4 | I/O2 | passive | `IO2` |
| 5 | VBUS | power_in | `VBUS` |

## Footprint

`SOT-23-6_ST_USBLC6-2SC6.kicad_mod`: ST's SOT23-6L footprint (Figure 22): 0.60 x 1.20 mm pads,
0.95 mm pitch, rows 2.30 mm apart (1.10 mm inner gap, 3.50 mm outer), pads 1-3 down the left
side and 4-6 up the right side. Body 1.6 x 2.9 mm on F.Fab (Table 4: E 1.50-1.75, D 2.80-3.05
mm), F.CrtYd 0.25 mm (IPC-7351B nominal) around pads and body. The embedded STEP is KiCad's
`SOT-23-6.step` (JEDEC SOT-23-6 body, same pin 1 corner). `pcb rectify check`: OK.
