# 05010xx.WR1

Littelfuse 501 series fast-acting fuses, 1206 package, 0.835 mm high, 32 VDC, 150 A interrupting:
0501010.WR1 (10 A, LCSC C207003), 0501012.WR1 (12 A, C207005), 0501015.WR1 (15 A, C410346) and
0501020.WR1 (20 A, C207007). Evidence is in the docstring of [`05010xx.zen`](05010xx.zen).
Datasheet: Littelfuse 501 Series, Revised 12/14/17.

```python
FUSE_501 = Module("github.com/Team-Micras/MicrasPCB/components/littelfuse/05010xx/05010xx.zen")

# In series with the battery's + terminal.
FUSE_501(name="F1", rating="12A", P1=BAT_P, P2=VBAT)
```

| Pad | Pin |
|---|---|
| 1 | P1 |
| 2 | P2 |

The fuse has no polarity.

`rating` (`10A`, `12A`, `15A`, `20A`; default `20A`) picks the row. Properties: `current_rating`,
`voltage_rating` 32 V, `interrupting_current` 150 A (at 32 VDC), `cold_resistance`, `melting_i2t`
(A2s, at 1 ms), `continuous_derating` 0.80, and `opening_current_100s` / `_1s` / `_10ms`: the
current that opens the row in that time, digitised from the Average Time Current Curves' vector paths;
`type = "fuse"`.

| Rating | Resistance | Melting I2t (1 ms) | Continuous at 25 C / 75 C | Opens in 100 s / 1 s / 10 ms |
|---|---|---|---|---|
| 10 A | 3.62 mOhm | 10.4 A2s | 8.0 / 6.8 A | 25 / 32 / 54 A |
| 12 A | 3.11 mOhm | 20.3 A2s | 9.6 / 8.2 A | 28 / 37 / 67 A |
| 15 A | 2.50 mOhm | 39.7 A2s | 12.0 / 10.2 A | 32 / 45 / 94 A |
| 20 A | 1.94 mOhm | 86.4 A2s | 16.0 / 13.6 A | 40 / 60 / 141 A |

At 100 % of the rating every row holds 4 hours minimum, at 350 % it opens within 5 s. The
continuous current is 80 % of the rating times the temperature re-rating (0.85 at 75 C).

## Footprint

`Fuse_Littelfuse_501_1206.kicad_mod`: KiCad's `Fuse_1206_3216Metric` with the pads of the
datasheet's recommended pad layout (two 1.0 x 1.8 mm pads 1.5 mm apart, 3.5 mm overall, in place
of KiCad's 1.25 x 1.75 mm at +-1.4 mm) and the courtyard 0.25 mm round them, with its Datasheet
and Description set. The embedded STEP (`0501020.step`, the same body for every row) was written
for this package with CadQuery from the drawing's nominal dimensions (body 3.20 x 1.63 x 0.835 mm,
0.52 mm terminations). `pcb rectify check`: OK.
