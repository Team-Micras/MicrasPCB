# B5819W

JCET (Jiangsu Changjiang Electronics Technology) B5819W (LCSC C8598, listed as "B5819W SL";
JLCPCB basic part): Schottky barrier diode, 40 V, 1 A, VF 0.6 V max at 1 A, SOD-123. Evidence is
in the docstring of [`B5819W.zen`](B5819W.zen).

```python
B5819W = Module("github.com/Team-Micras/MicrasPCB/components/cj/B5819W/B5819W.zen")

# VBAT -> VSYS OR-ing diode of the power path.
B5819W(name="D2", A=VBAT, K=VSYS)
```

| Pad | Pin |
|---|---|
| 1 | K (cathode, marked by the silkscreen bar) |
| 2 | A (anode) |

Ratings (datasheet p.1-2): VRRM 40 V; IO 1 A; IFSM 9 A; Pd 500 mW, RthJA 200 C/W; TJ 125 C max.
Reverse current is 1 mA max at 40 V and 25 C; typical at 17 V: about 12 uA (25 C), 0.12 mA
(75 C), 1.2 mA (100 C).

Integration note: in the VBAT/VBUS OR-ing the diode blocks only while USB powers VSYS and the
pack is off or missing (VR near 5 V). Its leakage then flows into the switched VBAT node, which
holds the bridges and the battery-voltage divider: about 6 uA at 25 C into the 120 kOhm
R44/R45 divider reads as up to 0.7 V of phantom battery voltage on USB alone, more when the board
is warm (inference from the typical curve; the bridges' sleep current lowers it).

## Footprint

`D_SOD-123.kicad_mod`: KiCad's `D_SOD-123` (IPC-7351 land, F.CrtYd included), unchanged, with
KiCad's `D_SOD-123.step` embedded (`pcb rectify check`: OK). The datasheet shows the SOD-123
package with the cathode bar but gives no outline or land pattern.

Why not the stdlib `Rectifier` generic: it has no `mpn`/`manufacturer` config, so its BOM line
has no MPN for `parts/jlc.toml` to map.
