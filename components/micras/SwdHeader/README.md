# SwdHeader

SWD header for an ST-Link: bare through-hole pads at 1.27 mm pitch. By default three pads, 1 GND,
2 SWDIO, 3 SWCLK (the middle three contacts of boards/main's SWD connector, in the same order);
with `supply = True` four pads in the 4-pin order of a clone ST-Link's 1.27 mm SWD lead, 1 SWDIO,
2 GND, 3 SWCLK, 4 VDD, VDD taking the probe's supply pin. Copper on the PCB, not a purchased part:
a 1.27 mm pitch header, or the probe's wires, is soldered by hand, so it is excluded from the BOM
and the placement file.

```python
SwdHeader = Module("github.com/Team-Micras/MicrasPCB/components/micras/SwdHeader/SwdHeader.zen")

SwdHeader(name="SWD", prefix="SWD", GND=GND, SWDIO=SWDIO, SWCLK=SWCLK)  # designator SWD1
SwdHeader(name="SWD", prefix="SWD", supply=True, GND=GND, SWDIO=SWDIO, SWCLK=SWCLK, VDD=V5V_IN)
```

| Pad | default | `supply = True` |
|---|---|---|
| 1 (square) | `GND` | `SWDIO` |
| 2 | `SWDIO` | `GND` |
| 3 | `SWCLK` | `SWCLK` |
| 4 | – | `VDD` |

- Config `prefix` (default `J`) sets the reference designator prefix.
- Config `supply` (default `False`) selects the four-pad variant (symbol `SwdHeader4`, footprint
  `PinHeader_1x04_P1.27mm_Vertical`) in the clone ST-Link's order, so its lead plugs on pin 1 to
  pad 1. Turned round, or shifted one pad either way, the probe's 5 V never lands on GND. The two
  variants number their pads differently: switching a board between them re-routes the header.
  What `VDD` feeds, and its protection, is the board's.
- No NRST: the probe connects under its normal reset (or the board's reset button).

## Footprints

`PinHeader_1x03_P1.27mm_Vertical.kicad_mod` and `PinHeader_1x04_P1.27mm_Vertical.kicad_mod` are
KiCad's library footprints of those names (kicad-footprint-generator) with their pads grown from
1.0 to 1.05 mm, for a 0.2 mm ring on the 0.65 mm drills (JLCPCB's PTH minimum is 0.18 mm,
rules/jlcpcb.kicad_dru); pad 1 square with the silkscreen's pin-1 corner beside it, 1.27 mm pitch,
pads numbered along the row. Each embeds KiCad's STEP of the same name (`pcb embed-step`): nothing
is assembled there, but the chassis checks see the height of the header soldered in. A board
labels the pads on its own silkscreen (main2: "5V" at pad 4).
