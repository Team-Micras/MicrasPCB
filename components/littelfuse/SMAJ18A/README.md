# SMAJ18A

Littelfuse SMAJ18A (LCSC C148219): unidirectional TVS diode, 400 W (10/1000 us), 18 V standoff,
VBR 20.0-22.1 V, VC 29.2 V at 13.7 A, DO-214AC (SMA). Evidence is in the docstring of
[`SMAJ18A.zen`](SMAJ18A.zen). Datasheet: Littelfuse SMAJ series, revised 11/20/15.

```python
SMAJ18A = Module("github.com/Team-Micras/MicrasPCB/components/littelfuse/SMAJ18A/SMAJ18A.zen")

# Across the battery connector: cathode on the pack's +, anode on its -.
SMAJ18A(name="D15", K=BAT_P, A=GND_BAT)
```

| Pad | Pin |
|---|---|
| 1 | K (cathode, the colour band) |
| 2 | A (anode) |

Properties: `reverse_standoff_voltage` 18 V, `breakdown_voltage` 20-22.1 V (at 1 mA),
`clamping_voltage` 29.2 V (at 13.7 A), `peak_pulse_power` 400 W; `type = "tvs"`.

Ratings (p1-p2): PPPM 400 W (10/1000 us); PD 3.3 W on an infinite heat sink at TL 50 C; RthJL
30 C/W, RthJA 120 C/W on 5 x 5 mm pads; IR 1 uA max at 18 V; TJ 150 C. It fails short when
over-specified.

## Footprint

`D_SMA.kicad_mod`: KiCad's `D_SMA` (pads 2.5 x 1.8 mm at +-2.0 mm, F.CrtYd included), with its
Datasheet and Description set, and KiCad's `D_SMA.step` embedded (`pcb rectify check`: OK). The
datasheet's solder pads (p5) ask for at least 2.1 x 1.8 mm per pad and at most 2.3 mm between
them; the KiCad land has 2.5 x 1.8 mm pads 1.5 mm apart.

Why a package and not the stdlib `Tvs` generic: the generic's footprint is the same `D_SMA`, but
it carries no breakdown voltage, which the board's test bench reads.
