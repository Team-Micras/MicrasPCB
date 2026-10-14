# JVS25V100M6X4

JIERR JVS25V100M6X4 100 uF 25 V 20 % SMD aluminium electrolytic capacitor, D6.3 x 4.5 mm, as a
bare part. Datasheet: JIERR JVS series (LCSC C51953404), pages 1-2.

```python
JVS25V100M6X4 = Module("github.com/Team-Micras/MicrasPCB/components/jierr/JVS25V100M6X4/JVS25V100M6X4.zen")

JVS25V100M6X4(name="C37", POS=V20, NEG=GND)
```

Reference prefix: `C`. The component has `type="capacitor"` with `capacitance` and `voltage`
properties, like the stdlib `Capacitor`, and warns when the voltage between the `POS` and `NEG`
nets exceeds 25 V.

| Pin | Name | io |
|---|---|---|
| 1 | + | `POS` |
| 2 | - | `NEG` |

Ratings (page 1): 25 V rated; -55 to +105 C; tan delta <= 0.18 at 120 Hz (ESR about 2.4 Ohm at
120 Hz); leakage <= 0.01 CV or 3 uA; 1000 h at 105 C. Ripple current 54 mA at 120 Hz per the
LCSC listing (TODO: confirm against the page 2 table).

Footprint `CAP-SMD_BD6.3-L6.6-W6.6-LS7.3-FD_JVS25V100M6X4.kicad_mod`: the same land pattern as
the VT1C221M0605 (3.0 x 1.2 mm pads at 4.84 mm pitch; page 2 lists the 6.6 x 6.6 mm base and
7.3 mm land span for D6.3), from the Micras Altium library (MicrasMainBoard), with the
JVS25V100M6X4 STEP embedded. Pad 1 (+) sits on the chamfered side, next to the "+" mark.
`pcb rectify check` passes.
