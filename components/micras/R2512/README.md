# R2512

A 2512 (6332 metric) chip resistor on the land pattern of the Micras Altium library: the stdlib
`Resistor` generic with the MicrasLib `RESC6432X89N` footprint in place of KiCad's
`R_2512_6332Metric`. The main board's current-sense shunts R31-R33 use it, so their routing lands
on the pads it was drawn for.

```python
R2512 = Module("github.com/Team-Micras/MicrasPCB/components/micras/R2512/R2512.zen")

R2512(name="R31", P1=FAN_LSS, P2=GND, value="50mOhm 1%", mpn="HoLLR2512-3W-50mR-1%", manufacturer="Milliohm", power="3W")
```

| Pad | io |
|---|---|
| 1 | `P1` |
| 2 | `P2` |

Configs: `value` (resistance), `mpn`, `manufacturer`, `power`, `voltage`, as on the stdlib
generic; the component type is `resistor` and its properties (`value`, `package`, `resistance`)
are the generic's, so board tests and the BOM read it the same way. Reference prefix: `R`.

## Footprint

`RESC6432X89N.kicad_mod` is the MicrasLib footprint of the MicrasMainBoard shunts:

| | This land pattern | KiCad `R_2512_6332Metric` |
|---|---|---|
| Pads | 1.45 x 3.45 mm, square corners | 1.225 x 3.35 mm, rounded |
| Pad centres | 5.8 mm apart | 5.925 mm apart |
| Copper per pad | 5.00 mm2 | 4.10 mm2 |

Paste and mask openings equal the pads (the board's mask expansion applies). The courtyard is the
Altium outline, 0.25-0.275 mm around the pads, on F.CrtYd; the 6.35 x 3.18 mm body outline is on
User.13 and the silkscreen is a centre line between the pads. The embedded STEP is the Altium
library's (Vishay WSL2512 body, 0.64 mm tall).
