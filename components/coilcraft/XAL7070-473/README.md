# XAL7070-473

Coilcraft XAL7070-473MEC 47 uH 20 % shielded power inductor (XAL7070, 7.2 x 7.5 x 7.0 mm, about
2.1 g), as a bare part: the series choke of a wheel motor (DCX 10 L 4.5 V) behind a DRV8874 at
100 kHz. Datasheet: Coilcraft XAL7070 series, Document 856 (revised 02/25/26). Evidence is in the
docstring of [`XAL7070-473.zen`](XAL7070-473.zen).

```python
XAL7070 = Module("github.com/Team-Micras/MicrasPCB/components/coilcraft/XAL7070-473/XAL7070-473.zen")

XAL7070(name="L4", P1=MOTOR_R_SHUNT, P2=MOTOR_R_A)
```

Reference prefix `L`. io `P1` = pad 1, `P2` = pad 2 (electrically non-polar). MPN
`XAL7070-473MEC` (C = 7" machine-ready reel), LCSC C3911413 (extended; 0 in stock on
2026-10-15).

| Property | Value | Source |
|---|---|---|
| inductance | 47 uH +-20 % (1 MHz) | Doc 856-2 |
| isat | 4.2 A, 30 % inductance drop, 25 C | Doc 856-2, note 5 |
| irms | 3.1 A (20 C rise), 4.1 A (40 C rise) | Doc 856-2, note 6 |
| dcr | 84.41 mOhm typ, 97.07 mOhm max | Doc 856-2 |
| current | 4.1 A, the lower of Irms (40 C) and Isat | - |
| operating voltage | 60 V | Doc 856-1 |
| mass | 1.9-2.3 g | Doc 856-1 |

## Why this part

Requirement (next-revision proposal, Drivetrain and "Series choke with a motor"): 47 uH,
shielded, Isat above ITRIP 3 A plus the 0.41-0.62 A blanking overshoot (about 3.6 A), DCR as low
as practical (each 100 mOhm costs about 0.1 W at 1 A rms), 1-1.5 A rms continuous, smallest and
lightest. Candidates (datasheet tables; Isat definitions differ by vendor, so the drop is given):

| MPN | DCR typ / max (mOhm) | Isat (A) | Irms (A) | Size L x W x H (mm) | Mass | LCSC | Source |
|---|---|---|---|---|---|---|---|
| **Coilcraft XAL7070-473MEC** | 84.4 / 97.1 | 4.2 @ 30 % | 3.1 (20 C), 4.1 (40 C) | 7.2 x 7.5 x 7.0 | 1.9-2.3 g | C3911413, 0 stock | Doc 856 |
| Coilcraft XAL7050-473MEC | 105 / 120 | 3.5 @ 30 % (short) | 2.5 / 3.5 | 7.2 x 7.5 x 5.0 | 1.50-1.55 g | none found | Coilcraft part page |
| Coilcraft XAL8080-473 | 64.7 / 71.8 | 4.4 @ 30 % | 3.5 / 4.8 | 8.1 x 8.6 x 8.0 | 3 g | C5184068 (listed as -473MEB) | Coilcraft part page |
| Coilcraft XGL6060-473MEC | 97.0 / 107 | 2.5 @ 20 %, 3.2 @ 30 % (short) | 2.7 / 3.7 | 6 x 6 class | 1.41-1.56 g | - | Coilcraft part page |
| Bourns SRP7050WA-470M | 156 / 171.6 | 4.1 @ 30 % | 3.2 (40 C) | 7.9 x 7.3 x 5.2 | not published | C19947705 | SRP7050WA datasheet |
| Bourns SRP1038A-470M | 145 / 167 | 4.5 @ 20 % | 3 (40 C) | 11.0 x 10.0 x 3.8 | not published | C3220907 | SRP1038A datasheet |
| Bourns SRP1050WA-470M | 89 / 103 | 5.5 @ 30 % | 4.2 (40 C) | 11.0 x 10.1 x 5.1 | not published | C19947672 | SRP1050WA datasheet |
| TDK SPM6545VT-470M-D | 229 typ | 3.0 @ 20 %, 4.2 @ 30 % | 2.1 (40 C) | 7.0 x 6.5 x 4.5 | 1.0 g | C1015819 | TDK spec (LCSC copy) |

Not available at 47 uH: Vishay IHLP-4040DZ-01 (tops out at 22 uH, Doc 34193) and Wurth WE-XHMI
(33 uH). Sunlord MWSA 47 uH listings give Isat 2-3.1 A.

The XAL7070-473 is the lowest-DCR part of 8 mm or less that meets the Isat target (17 % margin
at 30 % drop) with 2 x the rms requirement at a 20 C rise. Its costs are the 7.0 mm height and
about 2.1 g per motor: check the height against the chassis. Fallbacks on the same land pattern:
XAL7050-473 (5.0 mm, about 1.5 g) if the height does not fit, at Isat 3.5 A, just under the target.
For mass first, the TDK SPM6545VT-470M-D (1.0 g, in stock) at 229 mOhm and 3.0 A at 20 % drop
(its own footprint).

## Footprint

`L_Coilcraft_XAL7070-XXX.kicad_mod`: the KiCad library footprint, which matches Coilcraft's
recommended land pattern (part-page drawing): two 1.92 x 6.50 mm pads at 4.82 mm centre pitch
(2.90 mm gap, 6.74 mm outer span). F.Fab body 7.7 x 8.0 mm (the maximum outline); F.CrtYd 0.25 mm
around it. The embedded STEP `XAL7070-473MEC.step` was written for this package from the drawing's
nominal dimensions (body 7.2 x 7.5 x 7.0 mm, bottom terminals 1.45 x 6.0 mm, 3.37 mm apart); the
Coilcraft model is behind a login. `pcb rectify check`: OK.

The top bar marks the start (short) lead, "Connect high dv/dt here for lowest EMI": put that end
on the bridge side (DRV8874 OUT, through the shunt) when placing.

## DC bias and losses

Coilcraft's saturation SPICE model of the part (XAL7070-473_sat: L 41.781 uH, Is 9.6419 A,
a 0.6669) keeps 95 / 87 / 79 / 69 / 57 % of the zero-current inductance at 1 / 2 / 3 / 4.2 / 6 A, a
soft saturation with the datasheet's 30 % drop at Isat. Core loss from Coilcraft's power-inductor
loss tool, recorded for the XAL7070-102 to -682: P = C x f(MHz) x dIpp^2.1 mW, independent of the
DC current below 0.5 MHz, C / L(uH)^1.05 = 24-33 across the series, so 1400-1900 extrapolated to
this part. On main2 (DCX 10 L at 100 kHz): at most 1.11 A pp of ripple, at most 467 mW of core
loss with that coefficient doubled, +15 K at 26.5 K/W with the DCR at a 1.0 A rms run
(`research/next-revision/calculations/drivetrain/choke_check.py`).
