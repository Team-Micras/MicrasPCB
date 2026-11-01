# B5819W

JCET (Jiangsu Changjiang Electronics Technology) B5819W (LCSC C8598, listed as "B5819W SL";
JLCPCB basic part): Schottky barrier diode, 40 V, 1 A, VF 0.6 V max at 1 A, SOD-123. Evidence is
in the docstring of [`B5819W.zen`](B5819W.zen).

```python
B5819W = Module("github.com/Team-Micras/MicrasPCB/components/cj/B5819W/B5819W.zen")

# OR-ing diodes into VSYS: from the pack, and from a programmer's 5 V pin.
B5819W(name="D14", A=VBAT, K=VSYS)
B5819W(name="D17", A=V5V_IN, K=VSYS)
```

| Pad | Pin |
|---|---|
| 1 | K (cathode, marked by the silkscreen bar) |
| 2 | A (anode) |

Ratings (datasheet p.1-2): VRRM 40 V; IO 1 A; IFSM 9 A; Pd 500 mW, RthJA 200 C/W; TJ 125 C max.
Reverse current is 1 mA max at 40 V and 25 C; typical at 17 V: about 12 uA (25 C), 0.11 mA
(75 C), 0.92 mA (100 C); at 1-5 V: 5-6 uA, 55-64 uA, 0.42-0.59 mA.

Integration note: as one of two OR-ing diodes into a rail (main2: D14 from VBAT and D17 from a
programmer's 5 V pin into VSYS), the diode on the absent source blocks with VR up to the other
source's voltage. Its leakage then flows into its anode's node; if nothing else drives that node
(main2's VBAT with only 5V_IN present), size the node's load for it: about 6 uA at 25 C and
0.14 mA at 85 C at a few volts. main2's 22 kOhm battery divider holds VBAT at 0.13 V at 25 C and
1.1 V at 70 C (boards/main2/Regulators.zen, VSYS).

## Footprint

`D_SOD-123.kicad_mod`: KiCad's `D_SOD-123` (IPC-7351 land, F.CrtYd included), unchanged, with
KiCad's `D_SOD-123.step` embedded (`pcb rectify check`: OK). The datasheet shows the SOD-123
package with the cathode bar but gives no outline or land pattern.

Why not the stdlib `Rectifier` generic: it has no `mpn`/`manufacturer` config, so its BOM line
has no MPN for `parts/jlc.toml` to map.
