# AO3401A

-30 V, -4 A P-channel MOSFET in SOT-23 (Alpha & Omega Semiconductor AO3401A), rated down to
-2.5 V gate drive. Bare part: gate drive and load belong to the board. Evidence and datasheet
references are in the docstring of [`AO3401A.zen`](AO3401A.zen).

```python
AO3401A = Module("github.com/Team-Micras/MicrasPCB/components/aos/AO3401A/AO3401A.zen")

AO3401A(name="Q7", G=SWITCH_GATE, S=V3V3, D=LOAD)
```

Reference prefix `Q`. MPN `AO3401A`, Alpha & Omega Semiconductor, LCSC C15127 (JLCPCB basic part).

## Pinout (datasheet p.1, SOT23 top view)

| Pad | Name | Symbol type | io | Pad position (mm) |
|---|---|---|---|---|
| 1 | G | input | `G` | (-0.9375, -0.95) |
| 2 | S | passive | `S` | (-0.9375, 0.95) |
| 3 | D | passive | `D` | (0.9375, 0) |

The body diode conducts from drain to source; an off switch blocks source to drain only.

## Footprint

`SOT-23.kicad_mod`: KiCad's SOT-23 (JEDEC TO-236 variant AB, IPC-7351 land, F.CrtYd included),
unchanged, with KiCad's `SOT-23.step` embedded (`pcb rectify check`: OK). The AOS datasheet
gives the package as SOT23 without a land pattern.

## Ratings (datasheet p.1-2)

- VDS -30 V, VGS +-12 V; ID -4 A (TA 25 C), -3.2 A (TA 70 C); PD 1.4 W (TA 25 C).
- VGS(th) -0.5 to -1.3 V. RDS(on) max 50 mohm at VGS -10 V, 60 mohm at -4.5 V, 85 mohm at
  -2.5 V.
- RthJA 125 C/W max steady state.
