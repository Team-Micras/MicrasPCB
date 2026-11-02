# AO3400A

30 V, 5.7 A N-channel MOSFET in SOT-23 (Alpha & Omega Semiconductor AO3400A), rated down to
2.5 V gate drive. Bare part: gate resistor, gate pull-down and load belong to the board.
Evidence and datasheet references are in the docstring of [`AO3400A.zen`](AO3400A.zen).

```python
AO3400A = Module("github.com/Team-Micras/MicrasPCB/components/aos/AO3400A/AO3400A.zen")

AO3400A(name="Q2", G=GATE, S=GND, D=EMITTER_LOW)
```

Reference prefix `Q`. MPN `AO3400A`, Alpha & Omega Semiconductor, LCSC C20917 (JLCPCB basic part).

## Pinout (datasheet p.1, SOT23 top view)

| Pad | Name | Symbol type | io | Pad position (mm) |
|---|---|---|---|---|
| 1 | G | input | `G` | (1, 0.95) |
| 2 | S | passive | `S` | (1, -0.95) |
| 3 | D | passive | `D` | (-1, 0) |

## Footprint

`SOT-23-3_L2.9-W1.3-P1.90-LS2.4-BR.kicad_mod`: SOT-23-3, 2.9 x 1.3 mm body, from the Micras
Altium library (MicrasLib). Its land is KiCad's SOT-23 rotated 180 degrees (pads 1 and 2 on the
+x side, pad 3 on the -x side), so a placement taken from a KiCad-standard SOT-23 needs 180
degrees added. The embedded STEP (`DMN6075S-7.stp`) is a JEDEC SOT-23 body from another vendor's
part, aligned to this land (`pcb rectify check`: OK); there is no AOS model.

Courtyard: an F.CrtYd rectangle around the body outline (User.15) and the pads, 0.25 mm, the
IPC-7351B nominal courtyard excess (KiCad Library Conventions F5.3).

## Ratings (datasheet p.1-2)

- VDS 30 V, VGS +-12 V; ID 5.7 A (TA 25 C), 4.7 A (TA 70 C); PD 1.4 W (TA 25 C).
- VGS(th) 0.65-1.45 V. RDS(on) max 32 mohm at VGS 4.5 V, 48 mohm at VGS 2.5 V.
- RthJA 125 C/W max steady state.
