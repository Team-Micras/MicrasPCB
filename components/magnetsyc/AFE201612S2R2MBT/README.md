# AFE201612S2R2MBT

Magnetsyc AFE201612S2R2MBT 2.2 uH 20 % molded power inductor, 0806 (2.0 x 1.6 x 1.2 mm), as a
bare part. Datasheet: Magnetsyc AFE2016 series Rev.01 (LCSC C41347750), page 3 table.

```python
AFE201612S2R2MBT = Module("github.com/Team-Micras/MicrasPCB/components/magnetsyc/AFE201612S2R2MBT/AFE201612S2R2MBT.zen")

AFE201612S2R2MBT(name="L1", P1=VCAP, P2=VLXSMPS)
```

Reference prefix: `L`. io `P1` = pad 1, `P2` = pad 2 (non-polar).

| Property | Value | Source |
|---|---|---|
| inductance | 2.2 uH +-20 % | page 3 |
| current | 2.7 A (Isat, L drop about 30 %; Irms 2.9 A) | page 3 "Max" column, notes 3-4 |
| dcr | 90 mOhm max (77 typ) | page 3 |

The component has `type="inductor"` and these properties, like the stdlib `Inductor`.

Footprint `IND-SMD_L2.0-W1.6-B.kicad_mod`: 1.0 x 1.7 mm pads at 1.7 mm pitch, from the Micras
Altium library (MicrasMainBoard), with a generic 2.0 x 1.6 mm STEP. `pcb rectify check` passes.
