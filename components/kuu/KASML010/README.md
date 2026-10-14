# KASML010

Polymer PTC resettable fuse in 0402 (KUU KASML010, LCSC C42441131): 0.10 A hold, 0.30 A trip at
25 C, 6 Vdc max, 40 A max fault current. Datasheet facts and citations are in the docstring of
[`KASML010.zen`](KASML010.zen).

```python
KASML010 = Module("github.com/Team-Micras/MicrasPCB/components/kuu/KASML010/KASML010.zen")

KASML010(name="F1", P1=V3V3, P2=PROTECTED)
```

| Pad | Pin | io |
|---|---|---|
| 1 | 1 | `P1` |
| 2 | 2 | `P2` |

- Not polarized. The symbol uses the reference prefix `F`.
- Hold and trip currents derate with temperature: 0.06 A hold / 0.18 A trip at 70 C, 0.05 A /
  0.15 A at 85 C (datasheet section 3). Size the protected load against the hold current at the
  board's ambient temperature.
- Keep the voltage across the fuse at or below 6 V (Vmax).

## Footprint

`Fuse_0402.kicad_mod` is the Altium MicrasLib footprint `F0402` of the Micras main board: two
0.5 x 0.8 mm pads at x = +/-0.45 mm. Body graphics are on User.15 (Altium mechanical layer);
there is no F.CrtYd courtyard. The embedded STEP is `F0402.step`. `pcb rectify check`: model
transform OK.
