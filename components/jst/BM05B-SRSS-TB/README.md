# BM05B-SRSS-TB

JST BM05B-SRSS-TB(LF)(SN), SH series 5-pin 1.00 mm top-entry (vertical) SMD header (LCSC
C160391), as a bare part. It mates with the JST SHR-05V-S(-B) housing, plugged in from above.
Evidence is in the docstring of [`BM05B-SRSS-TB.zen`](BM05B-SRSS-TB.zen).

```python
BM05B = Module("github.com/Team-Micras/MicrasPCB/components/jst/BM05B-SRSS-TB/BM05B-SRSS-TB.zen")

BM05B(name="P1", P1=SWD_VDD, P2=GND, P3=SWDIO, P4=SWCLK, P5=NRST, MP=GND)
```

| Pad | io |
|---|---|
| 1 | `P1` |
| 2 | `P2` |
| 3 | `P3` |
| 4 | `P4` |
| 5 | `P5` |
| MP (two reinforcement pads) | `MP` |

- Config `prefix` (default `P`) sets the reference designator prefix.
- Ratings (JST SH catalogue p1): 1.0 A, 50 V AC/DC, -25 to +85 C, AWG #32 to #28.

## Footprint

`JST_SH_BM05B-SRSS-TB_1x05-1MP_P1.00mm_Vertical.kicad_mod` is the KiCad library footprint,
checked against the top-entry PC board layout of the JST SH catalogue p1: contacts 0.6 x 1.55 mm
at 1.00 mm pitch along X (pad 1 at x = -2, y = +1.325), reinforcement pads 1.2 x 1.8 mm at
x = +/-3.3, y = -1.2 (inner edges 0.7 mm beyond the outer contacts' centres), 4.2 mm from the
reinforcement pads' far edge to the contacts' far edge and 2.65 mm to their near edge. The body
(F.Fab, 7.0 x 2.9 mm, 4.25 mm high) takes the plug from above; the housing (8.0 mm wide with
protrusions) stands 6.3 mm above the board when mated, so keep that column clear. The F.SilkS
step at pad 1 marks pin 1. The embedded STEP is KiCad's
`JST_SH_BM05B-SRSS-TB_1x05-1MP_P1.00mm_Vertical.step`.
