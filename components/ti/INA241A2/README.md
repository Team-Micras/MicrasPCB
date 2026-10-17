# INA241A2

Texas Instruments INA241A2IDGKR (LCSC C36752877): bidirectional current-sense amplifier, gain
20 V/V, input common mode -5 to 110 V independent of its 2.7-20 V supply, with enhanced PWM
rejection for in-line motor sensing up to 125 kHz; VSSOP-8 (DGK). Bare part: the VS bypass
capacitor, the shunt and the output filter belong to the board. Evidence is in the docstring of
[`INA241A2.zen`](INA241A2.zen).

```python
INA241A2 = Module("github.com/Team-Micras/MicrasPCB/components/ti/INA241A2/INA241A2.zen")

# In-line motor current, mid-supply output (SBOSA30D 7.4.3.2, Figure 7-6): REF1 on VS, REF2 on GND,
# zero current at VS / 2, ratiometric with the ADC supply.
INA241A2(name="U8", VS=V3V3_A, GND=GND, IN_P=MOTOR_R_SENSE_P, IN_N=MOTOR_R_SENSE_N, REF1=V3V3_A, REF2=GND, OUT=MOTOR_R_CURRENT)
Capacitor(name="C80", P1=GND, P2=V3V3_A, **C_100N_0402)  # VS bypass at pins 6-2 (8.3.1)
```

Reference prefix `U`. `VS` declares the 2.7-20 V operating range (section 6.3). The package
fails the build when a net with a declared voltage puts IN+ or IN- outside -5 to 110 V, or REF1 or
REF2 outside 0 V to VS.

## Pinout (SBOSA30D Table 5-1, DGK)

| Pin | Name | Symbol pin | Symbol type | io |
|---|---|---|---|---|
| 1 | IN- | IN- | input | `IN_N` |
| 2 | GND | GND | power_in | `GND` |
| 3 | REF2 | REF2 | input | `REF2` |
| 4 | NC ("Reserved. Connect to ground.") | RSVD | passive | `GND` |
| 5 | OUT | OUT | output | `OUT` |
| 6 | VS | VS | power_in | `VS` |
| 7 | REF1 | REF1 | input | `REF1` |
| 8 | IN+ | IN+ | input | `IN_P` |

`VOUT = 20 x (VIN+ - VIN-) + (VREF1 + VREF2) / 2` (equation 1): with IN+ on the driver side of
the shunt, a positive output means current from the bridge to the motor.

## Footprint

`Texas_DGK0008A_VSSOP-8_3x3mm_P0.65mm.kicad_mod`, the land pattern of TI's DGK0008A example board
layout (4214862/A, in SBOSA30D): eight 1.4 x 0.45 mm pads with 0.05 mm corner radius, 0.65 mm pitch,
rows 4.4 mm apart centre to centre, pins 1-4 down the left side and 5-8 up the right side (top
view); non-solder-mask-defined (the board's mask expansion applies); paste equal to the pads (TI's
stencil example). Body 3 x 3 mm on F.Fab with the pin 1 chamfer, F.CrtYd 0.25 mm around pads and
body. The package is JEDEC MO-187 variation AA, so the embedded STEP is KiCad's
`VSSOP-8_3x3mm_P0.65mm.step` (same pin 1 corner and pad order). `pcb rectify check`: OK.

## Design requirements (board side)

- VS bypass (8.3.1, 8.4.1): 0.1 uF from VS to GND as close as possible to pins 6 and 2.
- Shunt (8.4.1): Kelvin (4-wire) connection; IN+/IN- straight to the sense pads, no series
  resistors (the 25-45 uA input bias current turns any into an error).
- REF1/REF2 (7.4.3): supply, ground or a low-impedance reference; a resistor divider needs a
  buffer for a single-ended output (7.4.3.4).
- Output (6.5): at most 1 nF directly on OUT; a larger ADC capacitor needs a series isolation
  resistor. Linear output from GND + 50 mV to VS - 200 mV: with 10 mOhm at VS = 3.3 V, +7.25 /
  -8.0 A.
- PWM (7.3.1.1): output held for 1 us after a common-mode edge; full rejection up to 125 kHz or
  edges at least 3 us apart. Sample away from the edges (settling 1 us to 1 %).
