# MTQH707050S470M

MetalLions MTQH707050S470MGT 47 uH 20 % molded power inductor (MTQH707050S, 7.2 x 7.0 x 5.0 mm),
as a bare part: the series choke of a wheel motor (DCX 10 L 4.5 V) behind a DRV8874 at 100 kHz.
Datasheet: MetalLions MTQH707050S Series, Molded Power Inductors (LCSC copy, no revision number).
Evidence is in the docstring of [`MTQH707050S470M.zen`](MTQH707050S470M.zen).

```python
MTQH707050S470M = Module("github.com/Team-Micras/MicrasPCB/components/metallions/MTQH707050S470M/MTQH707050S470M.zen")

MTQH707050S470M(name="L4", P1=MOTOR_R_SHUNT, P2=MOTOR_R_A)
```

Reference prefix `L`. io `P1` = pad 1, `P2` = pad 2 (electrically non-polar). MPN
`MTQH707050S470MGT` (G = gray coating, T = tape; the datasheet's B, black, is the same part
electrically), LCSC C53235274 (extended).

| Property | Value | Source |
|---|---|---|
| inductance | 47 uH +-20 % (1 MHz, 1.0 Vrms) | p2, notes 2 |
| isat | 4.5 A rated, 5.3 A typ, 30 % inductance drop, 25 C | p2, note 4 |
| irms | 3.0 A rated, 3.3 A typ, 40 C rise | p2, note 3 |
| dcr | 120 mOhm typ, 140 mOhm max | p2 |
| current | 3.0 A, the lower of Irms and Isat | - |
| operating range | -55 to +125 C including self-heating | p1, notes 5-6 |
| rated voltage, mass, SRF, core loss | not published | - |

The table heads its current columns "Typical" and "Max", the "Max" values lying below the typical
ones (Irms 3.3 / 3.0 A, Isat 5.3 / 4.5 A): this package takes them as the rated (minimum) values.

## Why this part

Requirement (next-revision proposal, Drivetrain and "Series choke with a motor"): 47 uH,
shielded, Isat above the ITRIP band's top plus the blanking overshoot (4.17 A), 1-1.5 A rms
continuous, small and light, and fitted by JLCPCB's assembly from stock. The MTQH707050S470MGT
meets the Isat target at its rated 4.5 A (8 % margin; 5.3 A typical), carries 2 x the rms
requirement at a 40 C rise, is 5.0 mm tall, and is stocked at LCSC (677 on 2026-11-02, US$0.54
each). Its costs against the Coilcraft XAL7070-473MEC (Doc 856: 97 mOhm max, Isat 4.2 A, Irms
4.1 A, 7.0 mm tall, 0 stock at LCSC): 44 % more DCR (140 mOhm max), no published core loss, rated
voltage or mass.

## Footprint

`L_MetalLions_MTQH707050S.kicad_mod` keeps the Coilcraft XAL7070 land on which the main board's
L4/L5 were routed: two 1.92 x 6.50 mm pads at 4.82 mm centre pitch. The MTQH's bottom terminals
(p1 Dimensions) are E 2.30 +-0.2 mm wide, G 2.6 +-0.2 mm apart and run across the whole 7.0 mm
width, so they cover 1.3-3.6 mm from the centre and +-3.5 mm along the terminal; each pad
(1.45-3.37 mm, +-3.25 mm) lies entirely under its terminal, also at the drawing's tolerance
limits (inner terminal edge at most 1.4 mm, outer at least 3.5 mm, width at least 6.8 mm).
MetalLions' own land (p1: A 7.50, B 2.40, C 7.30 mm, i.e. 2.55 x 7.30 mm pads at 4.95 mm pitch)
covers the whole terminal and reaches past it; the XAL7070 land wets about 78 % of each terminal
(12.5 of 16.1 mm2) and leaves no toe, which trades joint area for the unchanged routing.

F.Fab: the maximum body outline, 7.4 x 7.2 mm. F.SilkS and F.CrtYd are the XAL7070's
(7.92 x 8.22 mm silk, 8.2 x 8.5 mm courtyard), larger than the MTQH needs, so the placement is
unchanged. The embedded STEP `MTQH707050S470MGT.step` was written for this package from the p1
drawing (body 7.2 x 7.0 x 5.0 mm, bottom terminals 2.30 x 6.9 mm, 2.6 mm apart): the EasyEDA model
of C53235274 is a generic 7.0 x 7.0 x 3.0 mm body (`IND-SMD_L7.0-W7.0_SD7030`), not this part's
5.0 mm height. `pcb rectify check`: OK.

The dot on the top marks pin 1 (p2, Structure); the datasheet does not say which end starts the
winding.

## DC bias and losses

The p2 Current Characteristic plot (typical) keeps 97.5 / 94.6 / 89.8 / 84.4 / 78.4 / 72.1 % of the
48.8 uH zero-current inductance at 1 / 2 / 3 / 4 / 5 / 6 A, a soft saturation; its 30 % point
(about 6.4 A) is beyond the table's 5.3 A typical. The wheel-choke check
(`research/next-revision/calculations/drivetrain/choke_check.py`) fits Coilcraft's saturation
form to that plot and compresses its current axis so the 30 % drop falls at the rated 4.5 A, on
the -20 % part. Thermal resistance from the table: a 40 C rise at the rated 3.0 A with the 120
mOhm typical DCR at 65 C, 32 K/W (the plot's 22.7 K at 3 A gives 19 K/W). MetalLions publishes
no core loss: the check shows how much core loss the part can take before it passes the
datasheet's 125 C part limit, not what it is.
