# WSK2512-MID

Vishay Dale WSK2512 4-terminal (Kelvin) Power Metal Strip current-sense resistor, 2512, 1 W, in
the 1 to 4.9 mOhm band. Bare part. Evidence is in the docstring of
[`WSK2512-MID.zen`](WSK2512-MID.zen); the 5 mOhm to 0.2 Ohm band has another land pattern and is
[`vishay/WSK2512-HIGH`](../WSK2512-HIGH).

```python
WSK2512_MID = Module("github.com/Team-Micras/MicrasPCB/components/vishay/WSK2512-MID/WSK2512-MID.zen")

# Battery shunt (research/next-revision A.3): VBAT after the switch through the force pads, INA228 on the sense pads.
WSK2512_MID(name="R60", P1=VBAT, P2=VBAT_LOAD, S1=BAT_SENSE_P, S2=BAT_SENSE_N)
```

| `mpn` | Value | LCSC |
|---|---|---|
| `WSK25122L000FEA` (default) | 2 mOhm 1 %, TCR +-250 ppm/C | C3997408 |

At 2 mOhm the TCR is +-250 ppm/C (1-2.9 mOhm; +-75 ppm/C from 3 mOhm): up to 1 % over a 40 K
rise. The INA228 can compensate it from its die temperature (SHUNT_TEMPCO, SLYS021A 7.3.5) when
the shunt sits next to it.

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

`Vishay_WSK2512_6332Metric_1mR-4m9R.kicad_mod`, Vishay's Solder Pad Dimensions for 0.0005 to
0.0049 Ohm: force pads a = 3.30 mm long, l = 1.65 mm apart, 2.03 mm wide (b - c - d); sense pads
e = 1.70 x c = 0.76 mm, d = 0.51 mm from the force pad, flush with its outer end; b = 3.30 mm
across the pair. Pads 1-2 at the left end, 3-4 at the right, the sense pads in opposite corners as
the part's sense fingers. Paste and mask equal the pads (the board's mask expansion applies).
Body 6.35 x 3.18 mm with the T = 2.21 mm terminals on F.Fab, F.CrtYd 0.25 mm around the pads.
KiCad's `R_Shunt_Vishay_WSK2512_6332Metric_T2.21mm` has the same pads except 1.4 mm sense pads,
and its STEP is not shipped; the embedded STEP is Vishay's own model ("WSK2512 (0.001 to
0.0049)", doc 30323), centred, with the sense fingers on pads 2 and 3 (checked in a render).
`pcb rectify check`: OK.

## Design requirements (board side)

- Route the force pads as the current path and the sense pads as a separate pair to the
  INA228, with no current-carrying copper between the sense pads.
- Power: 1 W at 70 C, derated to 0 at 170 C; 2 mOhm carries 22 A continuous at 70 C.
