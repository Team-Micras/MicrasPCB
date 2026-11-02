# L6205D

DMOS dual full-bridge motor driver (STMicroelectronics L6205D013TR, **SO20**), 8-52 V, 2.8 A rms
per bridge, with high-side overcurrent detection and thermal shutdown. Bare part: the charge pump,
enable networks and supply decoupling belong to the board. Evidence and datasheet references are
in the docstring of [`L6205D.zen`](L6205D.zen).

```python
L6205D = Module("github.com/Team-Micras/MicrasPCB/components/st/L6205D/L6205D.zen")

L6205D(
    name="IC5",
    VS=V20, GND=GND, VBOOT=VBOOT, VCP=VCP,
    IN1A=L_FW, IN2A=L_BW, ENA=MOTOR_EN,
    IN1B=R_FW, IN2B=R_BW, ENB=MOTOR_EN,
    OUT1A=A1, OUT2A=A2, SENSEA=GND,
    OUT1B=B1, OUT2B=B2, SENSEB=GND,
)
```

Reference prefix `IC`. MPN `L6205D013TR`, STMicroelectronics, LCSC C962257.

## Pinout (SO20, datasheet p.4)

| Pin | Name | Symbol type | io |
|---|---|---|---|
| 1 | IN1A | input | `IN1A` |
| 2 | IN2A | input | `IN2A` |
| 3 | SENSEA | passive | `SENSEA` |
| 4 | OUT1A | output | `OUT1A` |
| 5, 6, 15, 16 | GND | power_in | `GND` |
| 7 | OUT1B | output | `OUT1B` |
| 8 | SENSEB | passive | `SENSEB` |
| 9 | IN1B | input | `IN1B` |
| 10 | IN2B | input | `IN2B` |
| 11 | ENB | bidirectional (input + OCD open drain) | `ENB` |
| 12 | VBOOT | passive (fed by the external charge pump) | `VBOOT` |
| 13 | OUT2B | output | `OUT2B` |
| 14 | VSB | power_in | `VS` |
| 17 | VSA | power_in | `VS` |
| 18 | OUT2A | output | `OUT2A` |
| 19 | VCP | output | `VCP` |
| 20 | ENA | bidirectional (input + OCD open drain) | `ENA` |

VSA and VSB share the `VS` io because the datasheet requires them on the same supply (p.4).
`VS` declares the recommended 8-52 V range (p.2).

The PowerSO20 version (L6205PD) uses different pin numbers for the same functions (p.4): it does
not fit this symbol or footprint.

## Footprint

`SOIC127P1032X265-20N.kicad_mod`: SO20 wide body, 1.27 mm pitch, from the Micras Altium library
(MicrasLib), with its STEP model (`L6205D013TR.stp`) embedded. `pcb rectify check`: OK. Package
dimensions: datasheet p.20 (SO20).

Courtyard: an F.CrtYd rectangle around the body outline (User.13) and the pads, 0.25 mm, the
IPC-7351B nominal courtyard excess (KiCad Library Conventions F5.3).

## Design requirements (board side)

- Charge pump (p.8 Table 1, Figure 3): D1, D2 1N4148; CBOOT 220 nF from VBOOT to VS; RP 100 ohm
  and CP 10 nF in series from the diode node to VCP.
- ENA/ENB (p.4 note 6, p.8): REN 2.2-180 kohm (100 kohm recommended) in series from the driver,
  CEN to GND (5.6 nF recommended). Never drive EN directly: the OCD pulls it low.
- VS decoupling (p.12): 100-200 nF ceramic at VSA/VSB, plus bulk (Table 2: 100 uF).
- SENSEA/SENSEB (p.4, p.12): to power ground directly or through a sense resistor, short trace.
- Logic levels (p.5): VIH 2 V min, VIL 0.8 V max; 3.3 V logic is valid. Inputs -0.3 to 7 V (p.2).
- Operating limits (p.2): VS 8-52 V, IOUT 2.8 A rms, fsw up to 100 kHz, Tj -25 to 125 C.
- Thermal (p.3-4): the four GND pins carry the heat; Rth(j-a) 51 C/W with 6 cm2 of copper.
