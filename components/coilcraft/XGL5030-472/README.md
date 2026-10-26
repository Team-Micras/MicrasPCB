# XGL5030-472

Coilcraft XGL5030-472MEC 4.7 uH 20 % shielded power inductor (XGL5030, 5.28 x 5.48 x 3.1 mm,
about 0.5 g), as a bare part: the series choke of the fan motor behind the STSPIN958 at 400 kHz.
Datasheet: Coilcraft XGL5030 series, Document 1576 (revised 02/19/26). Evidence is in the
docstring of [`XGL5030-472.zen`](XGL5030-472.zen).

```python
XGL5030 = Module("github.com/Team-Micras/MicrasPCB/components/coilcraft/XGL5030-472/XGL5030-472.zen")

XGL5030(name="L5", P1=FAN_OUT, P2=FAN_MOTOR)
```

Reference prefix `L`. io `P1` = pad 1, `P2` = pad 2 (electrically non-polar). MPN
`XGL5030-472MEC` (C = 7" machine-ready reel), LCSC C3911503 (extended; 0 in stock on
2026-10-15).

| Property | Value | Source |
|---|---|---|
| inductance | 4.7 uH +-20 % (1 MHz) | Doc 1576-2 |
| isat | 6.7 A at 30 % drop (4.8 A at 20 %, 3.1 A at 10 %), 25 C | Doc 1576-2 |
| irms | 6.3 A (20 C rise), 8.5 A (40 C rise) | Doc 1576-2 |
| dcr | 21.9 mOhm typ, 24.5 mOhm max | Doc 1576-2 |
| current | 6.7 A, the lower of Irms (40 C) and Isat (30 %) | - |
| operating voltage | 80 V | Doc 1576-1 |
| mass | 0.46-0.52 g | Doc 1576-1 |

At a 5 A fan limit the inductance is down a little over 20 % (about 3.7 uH).

## Why this part

Requirement (next-revision proposal, Fan): 4.7-10 uH shielded, Isat at or above the REF current
limit (3-5 A), about 5 x 5 mm or smaller, lowest DCR. Candidates (datasheet tables):

| MPN | L (uH) | DCR typ / max (mOhm) | Isat (A) | Irms (A) | Size (mm) | Mass | LCSC | Source |
|---|---|---|---|---|---|---|---|---|
| **Coilcraft XGL5030-472MEC** | 4.7 | 21.9 / 24.5 | 4.8 @ 20 %, 6.7 @ 30 % | 6.3 / 8.5 | 5.28 x 5.48 x 3.1 | 0.46-0.52 g | C3911503, 0 stock | Doc 1576 |
| Coilcraft XAL5030-472MEC | 4.7 | 36.0 / 40.0 | 6.7 @ 30 % | 4.3 / 5.9 | 5.28 x 5.48 x 3.1 | 0.44-0.51 g | C7432409, 1174 stock | Doc 908 (XAL50xx) |
| Coilcraft XAL5050-682MEC | 6.8 | 26.8 / 29.5 | 6.0 @ 30 % | 4.7 / 6.4 | 5.28 x 5.48 x 5.1 | 0.74-0.80 g | C2942217 | Doc 908 |
| Coilcraft XGL5030-682MEC | 6.8 | 28.6 / 32.1 | 3.9 @ 20 %, 5.5 @ 30 % | 5.4 / 7.3 | 5.28 x 5.48 x 3.1 | - | not searched | Doc 1576 |
| Wurth 74439334047 (WE-XHMI) | 4.7 | 22.9 / 27.96 | 3.3 @ 10 %, 7.5 @ 30 % | 6.8 (40 K) | 5.55 x 5.35 x 3.0 | not given | C27410786, 0 stock | WE datasheet |
| Bourns SRP5030TA-4R7M | 4.7 | 50 / 53 | 6 @ 20 % | 4.6 (40 C) | 5.7 x 5.2 x 2.8 | not given | C2047088, 0 stock | SRP5030TA datasheet |

Too low: XGL4030/XAL4030/XEL4030-472 (Isat 4.4-4.6 A at 30 %), XGL5030-103 (10 uH, 4.5 A at
30 %), Sunlord MWSA0503S-4R7 (about 4.5 A, 60 mOhm per its listing).

The XGL5030-472 has the lowest DCR of the 5 x 5 x 3 mm parts and the highest Irms, meets 5 A at a
30 % drop, and is the same Coilcraft family as the XAL6030 in this registry. **Drop-in
alternative: XAL5030-472MEC** (LCSC C7432409, in stock): the same body, land pattern and Isat, at
40 mOhm max DCR and 5.9 A Irms; it can be fitted on this footprint unchanged.

## Footprint

`L_Coilcraft_XAL5030-XXX.kicad_mod`: the KiCad library footprint, which matches Coilcraft's
recommended land pattern for both the XGL5030 and the XAL5030 (part-page drawings): two
1.18 x 4.70 mm pads at 3.31 mm centre pitch (2.13 mm gap, 4.49 mm outer span). F.Fab body
5.48 x 5.68 mm (the maximum outline); F.CrtYd 0.25 mm around it. The embedded STEP
`XGL5030-472MEC.step` was written for this package from the drawing's nominal dimensions (body
5.28 x 5.48 x 3.1 mm, bottom terminals 1.0 x 4.2 mm, 2.31 mm apart); the Coilcraft model is
behind a login, and the EasyEDA model of C7432409 is 5.1 mm tall (an XAL5050). `pcb rectify
check`: OK.

The top bar marks the start (short) lead, "Connect high dv/dt here for lowest EMI": put that end
on the STSPIN958 output when placing.

## DC bias and losses

Coilcraft's saturation SPICE model of the part (XGL5030-472_sat: L 4.4984 uH, Is 13.0461 A,
a 0.7097) keeps 92 / 87 / 81 / 77 / 66 % of the zero-current inductance at 2 / 3 / 4 / 4.8 / 6.7 A,
slightly below the datasheet's 10 / 20 / 30 % points. Core loss from Coilcraft's power-inductor
loss tool for this part: 71.6 mW x dIpp^1.99 at 0.408 MHz, independent of the DC current and
linear in frequency; part temperature rise 25.3 K/W. On main2 (drone fan at 400 kHz): at most
2.8 A pp of ripple and 0.53 W of core loss, +17 K with the DCR at 2.5 A
(`research/next-revision/calculations/fan/fan_choke_check.py`). Coilcraft's Power Inductor tool
(2.5 A with 2.8 A pp at 400 kHz, 40 C ambient, 2026-10-25) agrees: 673 mW in all, 57 C, 4.0 uH at
the 3.9 A peak.
