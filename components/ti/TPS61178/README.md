# TPS61178

TI TPS61178x 20 V 10 A fully integrated synchronous boost converter, 13-pin VQFN-HR (RNW), as a
bare part. Frequency, current-limit, feedback and compensation parts belong to the board.
Evidence and datasheet references are in the docstring of [`TPS61178.zen`](TPS61178.zen).
Datasheet: TI SLVSDA7E.

```python
TPS61178 = Module("github.com/Team-Micras/MicrasPCB/components/ti/TPS61178/TPS61178.zen")

TPS61178(
    name="U1", VIN=VBAT, EN=VBAT, VOUT=V20, VCC=VCC, GND=GND, SW=SW, BST=BST,
    FB=FB, COMP=COMP, FREQ=FREQ, ILIMIT=ILIMIT, DISDRV=NotConnected(),
)
```

| Config | Values | Meaning |
|---|---|---|
| `mpn` | `TPS611781RNWR` (default), `TPS61178RNWR` | forced PWM or auto PFM at light load (section 5, p3); same pins |

Reference prefix: `U`.

## Pinout (section 6, p3)

| Pin | Name | Type | io | Notes |
|---|---|---|---|---|
| 1 | FREQ/SYNC | input | `FREQ` | RFREQ to AGND or external clock; must not float |
| 2 | AGND | power_in | `GND` | |
| 3 | ILIMIT | input | `ILIMIT` | RLIMIT to AGND |
| 4 | COMP | output | `COMP` | compensation network to AGND |
| 5 | FB | input | `FB` | feedback divider |
| 6 | PGND | power_in | `GND` | |
| 7 | SW | passive | `SW` | switching node |
| 8 | VOUT | power_out | `VOUT` | |
| 9 | DISDRV | output | `DISDRV` | load-disconnect P-FET gate; `NotConnected()` when unused |
| 10 | VCC | power_out | `VCC` | internal 6 V regulator, > 1 uF to ground |
| 11 | EN | input | `EN` | 800 kOhm internal pull-down |
| 12 | VIN | power_in | `VIN` | |
| 13 | BST | passive | `BST` | >= 0.1 uF to SW |

`VIN` is `Power(2.7 V to 20 V)` and `VOUT` is `Power(4.5 V to 20 V)` (section 7.3, p4); `VCC` is
`Power(6 V)` (section 7.5, p5).

## Design equations

| Eq. | Rule |
|---|---|
| 1 (p12) | RLIMIT[kOhm] = 745 / ILIMIT[A]; TPS611781 about 0.8 A lower (p13); minimum about 1.6 A below typical (p17) |
| 2-3 (p13-14) | 1 / fSW = 3 * 1.8 pF * RFREQ + 50 ns |
| 4 (p17-18) | VOUT = 1.198 V * (1 + RUP / RDOWN); RDOWN <= 200 kOhm (section 7.3), < 100 kOhm recommended |
| 5 (p18) | dIL = VIN * D / (L * fSW) below 4 A peak-to-peak (p19) |
| 8-10 (p19) | IPEAK = IIN + dIL / 2 below the inductor saturation current |

Limits for the checks: VOUT below the 20 V recommended maximum and the 20.5 V minimum OVP
threshold (section 7.5); effective inductance 0.47 to 3.3 uH (section 7.3).

## Footprint

`RNW0013A.kicad_mod`: TI RNW0013A land pattern from the Micras Altium library (MicrasMainBoard),
one pad per pin (PGND, SW and VOUT are 0.25 x 3.4 mm bars under the body), with the
TPS611781RNWR STEP embedded. `pcb rectify check` passes.
