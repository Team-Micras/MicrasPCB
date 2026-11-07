# SMAJ18A

Zhuhai Hongjiacheng SMAJ18A (LCSC C19077538, a JLCPCB Preferred Extended part): unidirectional TVS
diode, 400 W (10/1000 us), 18 V standoff, VBR 20.0-22.1 V, VC 29.2 V at 13.7 A, DO-214AC (SMA). The
same ratings as the Littelfuse SMAJ18A (C148219). Evidence is in the docstring of
[`SMAJ18A.zen`](SMAJ18A.zen). Datasheet: Hongjiacheng SMAJ series, Rev 2.2.

```python
SMAJ18A = Module("github.com/Team-Micras/MicrasPCB/components/hongjiacheng/SMAJ18A/SMAJ18A.zen")

# Across the battery connector: cathode on the pack's +, anode on its -.
SMAJ18A(name="D15", K=BAT_P, A=GND_BAT)
```

| Pad | Pin |
|---|---|
| 1 | K (cathode, the colour band) |
| 2 | A (anode) |

Properties: `reverse_standoff_voltage` 18 V, `breakdown_voltage` 20-22.1 V (at 1 mA),
`clamping_voltage` 29.2 V (at 13.7 A), `peak_pulse_power` 400 W; `type = "tvs"`.

Ratings (p1-p2): PPPM 400 W (10/1000 us); PM(AV) 1.0 W on an infinite heat sink at TL 75 C; IFSM
40 A; RthJL 30 C/W, RthJA 120 C/W on 5 x 5 mm pads; IR 1 uA max at 18 V; TJ 150 C. It fails short
when over-specified.

## Footprint

`D_SMA.kicad_mod`: KiCad's `D_SMA` (pads 2.5 x 1.8 mm at +-2.0 mm, F.CrtYd included), with its
Datasheet and Description set, and KiCad's `D_SMA.step` embedded (`pcb rectify check`: OK). The
datasheet draws no land pattern; the KiCad land takes every lead in the package's tolerances
(p2: leads 4.70-5.30 mm overall, 0.76-1.52 mm long, 1.25-1.65 mm wide). The body is up to
2.41 mm high (p2, D).

Why a package and not the stdlib `Tvs` generic: the generic's footprint is the same `D_SMA`, but
it carries no breakdown voltage, which the board's test bench reads.
