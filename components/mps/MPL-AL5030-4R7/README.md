# MPL-AL5030-4R7

MPS MPL-AL5030-4R7 4.7 uH 20 % molded power inductor (5.5 x 5.3 x 2.9 mm, flat-wire winding), as a
bare part: the series choke of the fan motor behind the STSPIN958 at 400 kHz. Datasheet: MPS
MPL-AL5030-4R7 Rev. 1.1 (8/6/2019). Evidence is in the docstring of
[`MPL-AL5030-4R7.zen`](MPL-AL5030-4R7.zen).

```python
MPL_AL5030 = Module("github.com/Team-Micras/MicrasPCB/components/mps/MPL-AL5030-4R7/MPL-AL5030-4R7.zen")

MPL_AL5030(name="L6", P1=FAN_OUT, P2=FAN_MOTOR)
```

Reference prefix `L`. io `P1` = pad 1, the start of winding (the dot on the top), `P2` = pad 2;
electrically non-polar, but MPS lays the start of winding on the switch node (fewer emissions, less
audible noise). MPN `MPL-AL5030-4R7`, LCSC C3222781 (extended).

| Property | Value | Source |
|---|---|---|
| inductance | 4.7 uH +-20 % (100 kHz, 100 mA) | p1 |
| isat | 8 A at 30 % drop, 25 C and 100 C (typ) | p1, p5 |
| isat_20 | 4.5 A: the p2 curve crosses 3.76 uH (-20 % from 4.7 uH) at 4.55 A | p2 Inductance vs. Current |
| irms | 5.3 A (IR, 40 K rise on a single-layer 30 x 50 mm board) | p1 |
| dcr | 33 mOhm typ, 36.5 mOhm max | p1 |
| current | 5.3 A, the lower of IR and Isat (30 %) | - |
| resonance | 22 MHz typ | p1 |
| operating temperature | -40 to +155 C, including the rise | p1 |

The p2 inductance curve falls faster than the table's Isat suggests: -19 % at 4.31 A, -24 % at
5.3 A and -30 % at 6.7 A, not 8 A. Design to the curve.

## Footprint

`L_MPS_MPL-AL5030.kicad_mod`: two 1.18 x 4.70 mm pads at 3.31 mm centre pitch (2.13 mm gap,
4.49 mm outer span), the land of the Coilcraft XAL5030/XGL5030 family, which the main board's L6
copper already uses. MPS's land pattern (p4: A 4.70, B 2.0, C 4.50 mm) is 1.25 x 4.70 mm pads at
3.25 mm pitch: the same length and outer edge (2.245 against 2.25 mm from the centre); its pads
reach 0.065 mm further inward. The nominal terminals (1.10 mm wide, 2.30 mm apart, so 1.15-2.25 mm
from the centre, 4.30 mm long) sit on these pads with 1.095 of their 1.10 mm width; at the
tolerance extremes the terminal's inner edge (1.025 mm at the narrowest gap) can overhang the pad
by 0.04 mm and its outer edge (2.575 mm at the widest) runs past it by 0.33 mm, as it would on
MPS's own land. F.Fab body 5.50 x 5.70 mm (the maximum outline) with the start-of-winding dot at
pad 1; silkscreen and F.CrtYd as the Coilcraft land's (courtyard 0.24 mm around the maximum
outline). `pcb rectify check`: OK.

The embedded STEP `MPL-AL5030-4R7.step` was written for this package with CadQuery from the p4
drawing: the nominal 5.30 x 5.50 mm body at the 3.1 mm maximum height (so the board's
height checks see the worst case), the two 1.10 x 4.30 mm terminals 2.30 mm apart, and the dot
over pad 1. No vendor model was found: MPS's product page sits behind a bot challenge and
DigiKey lists no CAD model for the part (2026-11-08).

## Losses

MPS publishes no loss model or loss data for the MPL-AL. The research bounds the core loss from
MPS's small-signal Q curve (p3) and Coilcraft's loss-tool data for its composite-powder 5030
4.7 uH chokes; on the main board (drone fan at 400 kHz, at most 2.74 A pp of ripple) the estimate
is 0.27 W and the bound 1.04 W, and L6 stays at or below 121 C from a 40 C board with the bound and
the limiter's 4.31 A held, under the part's 155 C and the board's 125 C
(`research/next-revision/calculations/fan/fan_choke_check.py`).
