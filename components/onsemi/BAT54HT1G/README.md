# BAT54HT1G

onsemi BAT54HT1G (LCSC C21107): Schottky barrier diode, 30 V, 200 mA, SOD-323. Evidence is in
the docstring of [`BAT54HT1G.zen`](BAT54HT1G.zen).

```python
BAT54HT1G = Module("github.com/Team-Micras/MicrasPCB/components/onsemi/BAT54HT1G/BAT54HT1G.zen")

BAT54HT1G(name="D13", A=SENSE, K=HOLD)
```

| Pad | Pin |
|---|---|
| 1 | K (cathode, marked by the silkscreen bar) |
| 2 | A (anode) |

## Footprint

`D_SOD-323.kicad_mod`: KiCad's `D_SOD-323` (IPC-7351 land, F.CrtYd included), unchanged, with
KiCad's `D_SOD-323.step` embedded, as in the 1N4148WS package. The datasheet (p1, case 477) gives
pin 1 as the cathode.

Why not the stdlib `Rectifier` generic: it has no `mpn`/`manufacturer` config, so its BOM line
has no MPN for `parts/jlc.toml` to map.
