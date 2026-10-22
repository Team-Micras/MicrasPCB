# 0501020.WR1

Littelfuse 0501020.WR1 (LCSC C207007): fast-acting fuse, 20 A, 32 VDC, 501 series, 1206 package,
0.835 mm high. Evidence is in the docstring of [`0501020.zen`](0501020.zen). Datasheet:
Littelfuse 501 Series, revised 08/20/15.

```python
FUSE_20A = Module("github.com/Team-Micras/MicrasPCB/components/littelfuse/0501020/0501020.zen")

# In series with the battery's + terminal.
FUSE_20A(name="F1", P1=BAT_P, P2=VBAT)
```

| Pad | Pin |
|---|---|
| 1 | P1 |
| 2 | P2 |

The fuse has no polarity.

Properties: `current_rating` 20 A, `voltage_rating` 32 V, `interrupting_current` 150 A (at
32 VDC), `cold_resistance` 2.0 mOhm, `melting_i2t` 54.76 A2s (at 1 ms), `continuous_derating`
0.80; `type = "fuse"`.

Ratings (20 A row and series characteristics): at 100 % of the rating it holds 4 hours minimum,
at 350 % it opens within 5 s. Continuously it carries at most 80 % of the rating, times the
temperature re-rating (0.85 at 75 C): 16 A at 25 C, 13.6 A at 75 C.

## Footprint

`Fuse_Littelfuse_501_1206.kicad_mod`: KiCad's `Fuse_1206_3216Metric` with the pads of the
datasheet's recommended pad layout (two 1.0 x 1.8 mm pads 1.5 mm apart, 3.5 mm overall, in place
of KiCad's 1.25 x 1.75 mm at +-1.4 mm) and the courtyard 0.25 mm round them, with its Datasheet
and Description set. The embedded `0501020.step` was written for this package with CadQuery from
the drawing's nominal dimensions (body 3.20 x 1.63 x 0.835 mm, 0.52 mm terminations). `pcb
rectify check`: OK.
