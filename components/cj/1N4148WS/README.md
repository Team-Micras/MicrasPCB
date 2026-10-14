# 1N4148WS

JCET (Jiangsu Changjiang Electronics Technology) 1N4148WS (LCSC C2128, JLCPCB basic part): fast
switching diode, 100 V, 150 mA, trr 4 ns, SOD-323. Evidence is in the docstring of
[`1N4148WS.zen`](1N4148WS.zen).

```python
D1N4148WS = Module("github.com/Team-Micras/MicrasPCB/components/cj/1N4148WS/1N4148WS.zen")

D1N4148WS(name="D9", A=GND, K=GATE)
```

| Pad | Pin |
|---|---|
| 1 | K (cathode, marked by the silkscreen bar) |
| 2 | A (anode) |

## Footprint

`D_SOD-323.kicad_mod`: KiCad's `D_SOD-323` (IPC-7351 land, F.CrtYd included), unchanged, with
KiCad's `D_SOD-323.step` embedded (`pcb rectify check`: OK). The datasheet shows the SOD-323
package with the cathode band but gives no land pattern.

Why not the stdlib `Rectifier` generic: it has no `mpn`/`manufacturer` config, so its BOM line
has no MPN for `parts/jlc.toml` to map.
