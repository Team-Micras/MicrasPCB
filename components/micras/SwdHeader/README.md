# SwdHeader

SWD header for an ST-Link: bare through-hole pads at 1.27 mm pitch. By default three pads, 1 GND,
2 SWDIO, 3 SWCLK (the middle three contacts of the v1 main board's SWD connector, MicrasPCB
e34fb9a, in the same order);
with `supply = True` four pads in the 4-pin order of a clone ST-Link's 1.27 mm SWD lead, 1 SWDIO,
2 GND, 3 SWCLK, 4 VDD, VDD taking the probe's supply pin; with `reset = True` too, five pads, the
probe's reset first and then the lead's four: 1 NRST, 2 SWDIO, 3 GND, 4 SWCLK, 5 VDD. Copper on the PCB, not a purchased part:
a 1.27 mm pitch header, or the probe's wires, is soldered by hand, so it is excluded from the BOM
and the placement file.

```python
SwdHeader = Module("github.com/Team-Micras/MicrasPCB/components/micras/SwdHeader/SwdHeader.zen")

SwdHeader(name="SWD", prefix="SWD", GND=GND, SWDIO=SWDIO, SWCLK=SWCLK)  # designator SWD1
SwdHeader(name="SWD", prefix="SWD", supply=True, GND=GND, SWDIO=SWDIO, SWCLK=SWCLK, VDD=V5V_IN)
SwdHeader(name="SWD", prefix="SWD", supply=True, reset=True, NRST=RESET, GND=GND, SWDIO=SWDIO, SWCLK=SWCLK, VDD=V5V_IN)
```

| Pad | default | `supply = True` | `supply = True`, `reset = True` |
|---|---|---|---|
| 1 (square) | `GND` | `SWDIO` | `NRST` |
| 2 | `SWDIO` | `GND` | `SWDIO` |
| 3 | `SWCLK` | `SWCLK` | `GND` |
| 4 | – | `VDD` | `SWCLK` |
| 5 | – | – | `VDD` |

- Config `prefix` (default `J`) sets the reference designator prefix.
- Config `supply` (default `False`) selects the four-pad variant (symbol `SwdHeader4`, footprint
  `PinHeader_1x04_P1.27mm_Vertical`) in the clone ST-Link's order, so its lead plugs on pin 1 to
  pad 1. Turned round, or shifted one pad either way, the probe's 5 V never lands on GND. The two
  variants number their pads differently: switching a board between them re-routes the header.
  What `VDD` feeds, and its protection, is the board's.
- Config `reset` (default `False`, needs `supply`) selects the five-pad variant (symbol
  `SwdHeader5`, footprint `PinHeader_1x05_P1.27mm_Vertical`): pad 1 takes the probe's RST wire,
  and the 4-pin lead plugs on pads 2-5. Its misplugs: on pads 1-4, 5 V on SWCLK; on pads 3-6
  (one contact past pad 5), 5 V on no pad; turned round on pads 2-5, 5 V on SWDIO; turned round on
  pads 1-4, 5 V on NRST with the grounds together; turned round on pads 3-6, 5 V on GND with the
  probe's ground on VDD. What each does to a board is the board's to say (the main board:
  `boards/main/main.zen`).
- Without `reset`, no NRST: the probe connects under its normal reset (or the board's reset button).

## Footprints

`PinHeader_1x03_P1.27mm_Vertical.kicad_mod`, `PinHeader_1x04_P1.27mm_Vertical.kicad_mod` and
`PinHeader_1x05_P1.27mm_Vertical.kicad_mod` are KiCad's library footprints of those names
(kicad-footprint-generator) with their silkscreen lines widened from 0.12 to 0.15 mm (JLCPCB's
minimum) and their pads grown from 1.0 to 1.05 mm, for a 0.2 mm ring on the 0.65 mm drills (JLCPCB's PTH minimum is 0.18 mm,
rules/jlcpcb.kicad_dru); pad 1 square with the silkscreen's pin-1 corner beside it, 1.27 mm pitch,
pads numbered along the row. Each embeds KiCad's STEP of the same name (`pcb embed-step`): nothing
is assembled there, but the chassis checks see the height of the header soldered in. A board
labels the pads on its own silkscreen (the main board: "5V" at the VDD pad, pad 5).
