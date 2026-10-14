# VT1C221M0605

ACMECON VT1C221M0605 220 uF 16 V 20 % SMD aluminium electrolytic capacitor, D6.3 x 5.4 mm, as a
bare part. Datasheet: ACMECON VT series product data sheet v1.0 (2023-07-27), page 1.

```python
VT1C221M0605 = Module("github.com/Team-Micras/MicrasPCB/components/acmecon/VT1C221M0605/VT1C221M0605.zen")

VT1C221M0605(name="C36", POS=VBAT, NEG=GND)
```

Reference prefix: `C`. The component has `type="capacitor"` with `capacitance` and `voltage`
properties, like the stdlib `Capacitor`, and warns when the voltage between the `POS` and `NEG`
nets exceeds 16 V.

| Pin | Name | io |
|---|---|---|
| 1 | + | `POS` |
| 2 | - | `NEG` |

Ratings (page 1): 16 V rated, 18.4 V surge; -55 to +105 C; tan delta <= 0.20 at 120 Hz (ESR
about 1.2 Ohm at 120 Hz); ripple 72 mA rms at 120 Hz, 105 C; leakage <= 35.2 uA.

Footprint `CAP-SMD_BD6.3-L6.6-W6.6-LS7.3-FD.kicad_mod`: 3.0 x 1.2 mm pads at 4.84 mm pitch for
the 6.6 x 6.6 mm base, from the Micras Altium library (MicrasMainBoard). Pad 1 (+) sits on the
chamfered side of the outline, next to the "+" silkscreen mark. The VT1C221M0605 STEP is
embedded. `pcb rectify check` passes.

One package per part: the JVS25V100M6X4 (`components/jierr/JVS25V100M6X4`) uses the same land
pattern with its own STEP (4.5 mm tall), rating and manufacturer.
