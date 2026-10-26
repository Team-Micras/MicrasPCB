# BZT52C10S

Diodes Incorporated BZT52C10S-7-F (LCSC C260895): 10 V zener diode, 200 mW, SOD-323, 1.2 mm high.
Evidence is in the docstring of [`BZT52C10S.zen`](BZT52C10S.zen). Datasheet: Diodes DS30093
Rev. 20-2 (BZT52C2V0S - BZT52C39S).

```python
BZT52C10S = Module("github.com/Team-Micras/MicrasPCB/components/diodes/BZT52C10S/BZT52C10S.zen")

# Clamps a P-MOSFET's VGS to -10 V: anode on the gate, cathode on the source.
BZT52C10S(name="D16", A=PATH_GATE, K=VSYS)
```

| Pad | Pin |
|---|---|
| 1 | K (cathode, marked by the silkscreen bar) |
| 2 | A (anode) |

Limits: VZ 9.4-10.6 V at IZT 5 mA, ZZT 20 Ohm; IR 0.1 uA max at 7 V; VF 0.9 V max at 10 mA;
PD 200 mW, RthJA 625 C/W; TJ -65 to 150 C.

## Footprint

`D_SOD-323.kicad_mod`: KiCad's `D_SOD-323` (IPC-7351 land, F.CrtYd included), unchanged, with
KiCad's `D_SOD-323.step` embedded, as `components/cj/1N4148WS`. Its pads (0.6 x 0.45 mm, 2.7 mm
overall) match the datasheet's suggested pad layout (X 0.59, Y 0.45, X1 2.70 mm).

Why not the stdlib `Zener` generic: it has no `mpn`/`manufacturer` config, so its BOM line has
no MPN for `parts/jlc.toml` to map.
