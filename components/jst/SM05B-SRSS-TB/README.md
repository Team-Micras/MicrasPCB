# SM05B-SRSS-TB

JST SM05B-SRSS-TB(LF)(SN), SH series 5-pin 1.00 mm side-entry SMD header (LCSC C136657), as a
bare part. It mates with the JST SHR-05V-S(-B) housing. Evidence is in the docstring of
[`SM05B-SRSS-TB.zen`](SM05B-SRSS-TB.zen).

```python
SM05B = Module("github.com/Team-Micras/MicrasPCB/components/jst/SM05B-SRSS-TB/SM05B-SRSS-TB.zen")

SM05B(name="P1", P1=SWD_VDD, P2=GND, P3=SWDIO, P4=SWCLK, P5=NRST, MP=GND)
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

`JST_SH_SM05B-SRSS-TB_1x05-1MP_P1.00mm_Horizontal.kicad_mod` is the KiCad library footprint,
checked against the side-entry PC board layout of the JST SH catalogue p1: contacts 0.6 x 1.55 mm
at 1.00 mm pitch along X (pad 1 at x = -2), reinforcement pads 1.2 x 1.8 mm at x = +/-3.3
(0.7 mm beyond the outer contacts), 3.875 mm between the contact row and the reinforcement pads.
The body (F.Fab, 7.0 x 4.25 mm) has its mating face at +Y, on the reinforcement-pad side: place
that side on the board edge so the cable leaves the board sideways. The F.SilkS tick at pad 1
marks pin 1. The embedded STEP is KiCad's
`JST_SH_SM05B-SRSS-TB_1x05-1MP_P1.00mm_Horizontal.step` (`pcb rectify check`: OK).
