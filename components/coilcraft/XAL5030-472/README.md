# XAL5030-472

Coilcraft XAL5030-472MEC 4.7 uH 20 % shielded power inductor (XAL5030, 5.28 x 5.48 x 3.1 mm,
about 0.5 g), as a bare part: the series choke of the fan motor behind the STSPIN958 at 400 kHz.
Datasheet: Coilcraft XAL50xx series, Document 908 (908-1 revised 06/23/23). Evidence is in the
docstring of [`XAL5030-472.zen`](XAL5030-472.zen).

```python
XAL5030 = Module("github.com/Team-Micras/MicrasPCB/components/coilcraft/XAL5030-472/XAL5030-472.zen")

XAL5030(name="L6", P1=FAN_OUT, P2=FAN_MOTOR)
```

Reference prefix `L`. io `P1` = pad 1, `P2` = pad 2 (electrically non-polar). MPN
`XAL5030-472MEC` (C = 7" machine-ready reel), LCSC C7432409 (extended).

| Property | Value | Source |
|---|---|---|
| inductance | 4.7 uH +-20 % (1 MHz) | Doc 908-1 |
| isat | 6.7 A at 30 % drop, 25 C | Doc 908-1, note 5 |
| isat_20 | 5.0 A at 20 % drop | Doc 908-2 L vs Current plot, scaled to the 6.7 A Isat |
| irms | 4.3 A (20 C rise), 5.9 A (40 C rise) | Doc 908-1, note 6 |
| dcr | 36.00 mOhm typ, 40.00 mOhm max | Doc 908-1 |
| current | 5.9 A, the lower of Irms (40 C) and Isat (30 %) | - |
| operating voltage | 0-60 V | Doc 908-1 |
| mass | 0.44-0.51 g | Doc 908-1 |

## Why this part

Requirement (next-revision proposal, Fan): 4.7-10 uH shielded, at most a 20 % drop at the REF
current limit (3.65-4.31 A on the board), about 5 x 5 mm or smaller, low DCR, and fitted by
JLCPCB's assembly. Candidates (datasheet tables):

| MPN | L (uH) | DCR typ / max (mOhm) | Isat (A) | Irms (A) | Size (mm) | Mass | LCSC | Source |
|---|---|---|---|---|---|---|---|---|
| **Coilcraft XAL5030-472MEC** | 4.7 | 36.0 / 40.0 | 5.0 @ 20 % (plot), 6.7 @ 30 % | 4.3 / 5.9 | 5.28 x 5.48 x 3.1 | 0.44-0.51 g | C7432409, 11 stock on 2026-11-02 | Doc 908 |
| Coilcraft XGL5030-472MEC | 4.7 | 21.9 / 24.5 | 4.8 @ 20 %, 6.7 @ 30 % | 6.3 / 8.5 | 5.28 x 5.48 x 3.1 | 0.46-0.52 g | C3911503, 0 stock | Doc 1576 |
| Coilcraft XAL5050-682MEC | 6.8 | 26.8 / 29.5 | 6.0 @ 30 % | 4.7 / 6.4 | 5.28 x 5.48 x 5.1 | 0.74-0.80 g | C2942217 | Doc 908 |
| Wurth 74439334047 (WE-XHMI) | 4.7 | 22.9 / 27.96 | 3.3 @ 10 %, 7.5 @ 30 % | 6.8 (40 K) | 5.55 x 5.35 x 3.0 | not given | C27410786, 0 stock | WE datasheet |
| Bourns SRP5030TA-4R7M | 4.7 | 50 / 53 | 6 @ 20 % | 4.6 (40 C) | 5.7 x 5.2 x 2.8 | not given | C2047088, 0 stock | SRP5030TA datasheet |

Too low: XGL4030/XAL4030/XEL4030-472 (Isat 4.4-4.6 A at 30 %), XGL5030-103 (10 uH, 4.5 A at
30 %), Sunlord MWSA0503S-4R7 (about 4.5 A, 60 mOhm per its listing).

The XAL5030-472 is the stocked part of the 5 x 5 x 3 mm class: it holds its inductance better
under bias than the XGL5030-472 (20 % drop at about 5.0 A against 4.8 A) at 1.6 x its DCR and
0.7 x its Irms, both with margin at the fan's 2.5 A running current. The XGL5030-472MEC is a
drop-in alternative on this footprint (same body, terminals and land) where it is stocked.

## Footprint

`L_Coilcraft_XAL5030-XXX.kicad_mod`: the KiCad library footprint, two 1.18 x 4.70 mm pads at
3.31 mm centre pitch (2.13 mm gap, 4.49 mm outer span), the XGL5030's recommended land.
Doc 908-4 recommends 4.25 mm long pads for the XAL5030-472 (terminals A 4.18 mm long); the 4.70 mm
pads reach 0.26 mm past each terminal end. F.Fab body 5.48 x 5.68 mm (the maximum outline);
F.CrtYd 0.25 mm around it. The embedded STEP `XAL5030-472MEC.step` was written for this package
from the Doc 908-4 drawing (body 5.28 x 5.48 x 3.1 mm, the maximum height; bottom terminals
1.0 x 4.18 mm, 2.31 mm apart): the EasyEDA model of C7432409 is 5.1 mm tall (an XAL5050) and the
Coilcraft model is behind a login. `pcb rectify check`: OK.

The top bar marks the start (short) lead, "Connect high dv/dt here for lowest EMI": put that end
on the STSPIN958 output when placing.

## DC bias and losses

The Doc 908-2 L vs Current plot of the 4.7 uH part keeps 97.7 / 95.0 / 91.5 / 87.2 / 82.2 / 76.6 %
of its zero-current inductance at 1 / 2 / 3 / 4 / 5 / 6 A and falls 30 % at about 7.0 A.
Coilcraft's saturation form fitted to it (Is 12.7 A, a 0.87) with the current axis compressed so
the 30 % drop lands on the table's 6.7 A falls 20 % at 5.05 A and 10 % at 3.25 A. Core loss from
Coilcraft's power-inductor loss tool for this part: 99.5 mW x dIpp^1.635 at 0.408 MHz, independent
of the DC current and nearly linear in frequency; part temperature rise 31.9 K/W. On the main board
(drone fan at 400 kHz): at most 2.7 A pp of ripple and 0.49 W of core loss; from a 40 C board
the part reaches 66 C at 2.5 A and 86 C with the 4.31 A REF limit held
(`research/next-revision/calculations/fan/fan_choke_check.py`).
