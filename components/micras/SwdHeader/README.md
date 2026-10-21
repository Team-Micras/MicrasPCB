# SwdHeader

SWD header for an ST-Link: three bare through-hole pads at 1.27 mm pitch, 1 GND, 2 SWDIO,
3 SWCLK (the middle three contacts of boards/main's SWD connector, in the same order). Copper on
the PCB, not a purchased part: a 1.27 mm pitch header, or the probe's wires, is soldered by hand,
so it is excluded from the BOM and the placement file.

```python
SwdHeader = Module("github.com/Team-Micras/MicrasPCB/components/micras/SwdHeader/SwdHeader.zen")

SwdHeader(name="SWD", prefix="SWD", GND=GND, SWDIO=SWDIO, SWCLK=SWCLK)  # designator SWD1
```

| Pad | io |
|---|---|
| 1 (square) | `GND` |
| 2 | `SWDIO` |
| 3 | `SWCLK` |

- Config `prefix` (default `J`) sets the reference designator prefix.
- No probe supply and no NRST: the target powers itself, and the probe connects under its normal
  reset (or the board's reset button).

## Footprint

`PinHeader_1x03_P1.27mm_Vertical.kicad_mod` is KiCad's library footprint of that name
(kicad-footprint-generator) with its pads grown from 1.0 to 1.05 mm, for a 0.2 mm ring on the
0.65 mm drills (JLCPCB's PTH minimum is 0.18 mm, rules/jlcpcb.kicad_dru); pad 1 square, 1.27 mm
pitch. It embeds KiCad's PinHeader_1x03_P1.27mm_Vertical STEP (`pcb embed-step`): nothing is
assembled there, but the chassis checks see the height of the header soldered in.
