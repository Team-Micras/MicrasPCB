# YSPIA0645-220M

YJYCOIN YSPIA0645-220M 22 uH 20 % molded power inductor, 6.5 x 6.0 x 4.5 mm, as a bare part.
Datasheet: YJYCOIN SMD Power Inductors YSPIA0645 series (LCSC C2839926), page 2.

```python
YSPIA0645 = Module("github.com/Team-Micras/MicrasPCB/components/yjycoin/YSPIA0645-220M/YSPIA0645-220M.zen")

YSPIA0645(name="L3", P1=SW, P2=V3V3)
```

Reference prefix: `L`. io `P1` = pad 1, `P2` = pad 2 (non-polar).

| Property | Value | Source |
|---|---|---|
| inductance | 22 uH +-20 % | page 2 (100 kHz), page 1 tolerance code M |
| current | 2.8 A (heat rating, 40 C rise; Isat 4.5 A) | page 2 |
| dcr | 130 mOhm max (100 typ) | page 2 |

Footprint `IND-SMD_L6.5-W6.0.kicad_mod`: 2.15 x 3.5 mm pads at 5.35 mm pitch, which is the
datasheet land (F 3.5, G 7.5, H 3.2 mm, page 2); from the Micras Altium library
(MicrasMainBoard). The embedded STEP is the Vishay IHLP-2525CZ model (about 3 mm tall), not this
4.5 mm part: mechanical clearance checks must use the 4.5 mm datasheet height.
`pcb rectify check` passes.
