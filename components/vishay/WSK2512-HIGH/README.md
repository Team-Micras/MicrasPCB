# WSK2512-HIGH

Vishay Dale WSK2512 4-terminal (Kelvin) Power Metal Strip current-sense resistor, 2512, 1 W, in
the 5 mOhm to 0.2 Ohm band (TCR +-35 ppm/C). Bare part. Evidence is in the docstring of
[`WSK2512-HIGH.zen`](WSK2512-HIGH.zen); the 1-4.9 mOhm band has another land pattern and is
[`vishay/WSK2512-MID`](../WSK2512-MID).

```python
WSK2512_HIGH = Module("github.com/Team-Micras/MicrasPCB/components/vishay/WSK2512-HIGH/WSK2512-HIGH.zen")

# In-line motor shunt (research/next-revision A.3): force pads in the current path, sense pads to the INA241.
WSK2512_HIGH(name="R32", P1=MOTOR_R_OUT1, P2=MOTOR_R_CHOKE, S1=MOTOR_R_SENSE_P, S2=MOTOR_R_SENSE_N)
```

| `mpn` | Value | LCSC |
|---|---|---|
| `WSK2512R0100FEA` (default) | 10 mOhm 1 % | C3985410 |
| `WSK2512R0100DEA` | 10 mOhm 0.5 % | C1517461 |
| `WSK25125L000FEA` | 5 mOhm 1 % | C1517444 |

Reference prefix `R`; component type `resistor` with the generic's `resistance`, `power` and
`package` properties. The build fails if a sense terminal shares a net with a force terminal or
with the other sense terminal.

## Terminals (doc 30108, Electrical Connection)

| Pad | Terminal | io |
|---|---|---|
| 1 | I1, current | `P1` |
| 2 | E1, voltage sense of the I1 end | `S1` |
| 3 | E2, voltage sense of the I2 end | `S2` |
| 4 | I2, current | `P2` |

## Footprint

`Vishay_WSK2512_6332Metric_5mR-200mR.kicad_mod`, Vishay's Solder Pad Dimensions for 0.005 to
0.2 Ohm: force pads a = 2.29 mm long, l = 3.68 mm apart, 2.03 mm wide (b - c - d); sense pads
e = 1.70 x c = 0.76 mm, d = 0.51 mm from the force pad, flush with its outer end; b = 3.30 mm
across the pair. Pads 1-2 at the left end, 3-4 at the right, the sense pads in opposite corners as
the part's sense fingers. Paste and mask equal the pads (the board's mask expansion applies).
Body 6.35 x 3.18 mm with the T = 1.19 mm terminals on F.Fab, F.CrtYd 0.25 mm around the pads.
KiCad's `R_Shunt_Vishay_WSK2512_6332Metric_T1.19mm` has the same pads except 1.4 mm sense pads,
and its STEP is not shipped; the embedded STEP is Vishay's own model ("WSK2512 (0.005 to 0.2)",
doc 30323), centred, with the sense fingers on pads 2 and 3 (checked in a render).
`pcb rectify check`: OK.

## Design requirements (board side)

- Route the force pads as the current path and the sense pads as a separate pair to the
  amplifier, with no current-carrying copper between the sense pads.
- Power: 1 W at 70 C, derated to 0 at 170 C; 10 mOhm carries 10 A continuous at 70 C.
