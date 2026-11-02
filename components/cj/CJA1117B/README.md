# CJA1117B

JCET CJA1117B-3.3 1 A low-dropout linear regulator, fixed 3.3 V, SOT-89-3, as a bare part.
Evidence and datasheet references are in the docstring of [`CJA1117B.zen`](CJA1117B.zen).
Datasheet: JCET CJA1117B-XXX rev. E (March 2016).

```python
CJA1117B = Module("github.com/Team-Micras/MicrasPCB/components/cj/CJA1117B/CJA1117B.zen")

CJA1117B(name="U3", VIN=V5, VOUT=V3V3, GND=GND)
```

Reference prefix: `U`.

## Pinout (page 1)

| Pin | Name | Type | io |
|---|---|---|---|
| 1 | ADJ/GND | power_in | `GND` |
| 2 | OUTPUT (and tab) | power_out | `VOUT` |
| 3 | IN | power_in | `VIN` |

`VIN` is `Power(4.8 V to 15 V)`: 15 V is the recommended maximum (page 2) and 4.8 V the lowest
input at which the output is specified (page 3). `VOUT` is `Power(3.234 V to 3.366 V)`
(page 3, 10 mA to 1 A).

## Requirements for the board

- Output capacitor: the JCET datasheet states none. For the same 1117 architecture, TI LM1117
  (SNOS412Q section 9.2.2.1.3, p15) requires 0.3 to 22 Ohm ESR on the output capacitor, and the
  AMS1117 datasheet asks for 22 uF solid tantalum. A check can take the LM1117 ESR window as the
  requirement.
- Thermal: RthJA 250 C/W (page 2), so P = (VIN - VOUT) * IOUT must keep TJ <= 125 C.
- Dropout 1.3 V max at 1 A (page 3).

## Footprint

`SOT-89-3_L4.5-W2.5-P1.50-LS4.2-BR.kicad_mod`: SOT-89-3 land pattern from the Micras Altium
library (MicrasMainBoard) with a generic SOT-89-3 STEP. Pads:

- 1 and 3: 1.575 x 0.672 mm leads;
- 2: a custom polygon covering the tab and the centre lead, with a paste opening of the same
  shape, plus a 0.38 mm round anchor pad at the tab centre. Both carry pad number 2, so the whole
  tab is on the OUTPUT net.

Courtyard: F.CrtYd rectangle around the body outline (User.15) and the pads with the IPC-7351B
nominal (density level B) courtyard excess of 0.25 mm.

`pcb rectify check` reports a 0.33 mm in-plane model offset; a KiCad 3D render shows the model
leads and tab on their pads, so the transform is kept.
