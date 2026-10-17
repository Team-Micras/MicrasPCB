# Encoder board

One per wheel. An AS5047U magnetic angle sensor on a 9.6 x 14.1 mm, 2-layer, 0.79 mm board that
stands upright in a slot in the main board, facing the diametric magnet on the wheel axle. Supply
(3.3 V), SPI and the ABI quadrature outputs leave through the 8 edge pads of its tab, soldered to
the main board beside the slot.

The board is the MicrasEncoder Altium design (`hw_debug/modules/encoder`): its designators,
footprints, net names, outline, pours, sensor and tab placement, SPI and ABI routing and
silkscreen, plus three pull resistors the AS5047U asks for on its SPI inputs (R1-R3, see
[Circuit](#circuit)). `micras-pcb previous compare encoder` checks the netlist against that
design's connectivity ([`previous/board.json`](../previous/board.json)) with the change declared in
[`changes.toml`](../changes.toml).

## Files

The board files are in `boards/encoder/` (this README sits in its `layout/` folder);
`spec/` is at the repository root.

| File | Contents |
|---|---|
| [`encoder.zen`](../encoder.zen) | IC1 (AS5047U), C1, R1-R3, the edge tab J1, net names, stackup and rules |
| [`schematic/`](../schematic) | how the sheet is drawn (`micras-pcb sch`): the tab wired to the sensor, the SPI pulls |
| [`test/`](../test) | `pcb test` bench of the board's circuit: one 3V3 supply from the tab, the 100 nF at the sensor, the SPI input pulls, capacitor ratings |
| [`changes.toml`](../changes.toml) | the connectivity this board adds to the previous revision's (R1-R3) |
| [`layout/`](.) | this folder: the KiCad project; the `.kicad_pcb` holds placement and routing; [`fixes.py`](fixes.py) and [`fork.py`](fork.py) (the 3V3 fork at IC1 squared) are the scripts that turned the previous layout into this one |
| [`previous/`](../previous) | the previous revision's snapshot, and [`transfer_layout.py`](../previous/transfer_layout.py), which builds the previous layout from that revision |
| [`spec/encoder.toml`](../../../spec/encoder.toml) | mechanical interface: thickness, outline, tab, sensor and tab positions |

## Circuit

| Designator | Part | Package | Notes |
|---|---|---|---|
| IC1 | ams OSRAM AS5047U-HTSM ([`components/ams/AS5047U`](../../../components/ams/AS5047U)) | TSSOP-14, `SOP65P640X120-14N` | 3.3 V mode: VDD and VDD3V3 on 3V3, TEST on GND, U/V/W and I/PWM open (DS v1-00 Figure 4, Figure 11) |
| C1 | Yageo CC0603KRX7R9BB104, 100 nF 10 % 50 V X7R (LCSC C14663, JLCPCB basic) | 0603 (KiCad `C_0603_1608Metric`) | the 100 nF of DS Figure 11 on 3V3 |
| R1 | Uni-Royal 0402WGF1002TCE, 10 kOhm 1 % (LCSC C25744, JLCPCB basic) | 0402 (KiCad `R_0402_1005Metric`) | CSn pull-up to 3V3 (DS Figure 4 notes 1, 2) |
| R2 | Uni-Royal 0402WGF1003TCE, 100 kOhm 1 % (LCSC C25741, JLCPCB basic) | 0402 | CLK pull-down (DS Figure 4 notes 1, 3) |
| R3 | Uni-Royal 0402WGF1003TCE, 100 kOhm 1 % (LCSC C25741, JLCPCB basic) | 0402 | MOSI pull-down (DS Figure 4 notes 1, 3) |
| J1 | edge tab ([`components/micras/EncoderTab`](../../../components/micras/EncoderTab)) | `ENCODER_CONN`, copper on the board | not in the BOM |

| Net | IC1 | J1 |
|---|---|---|
| `Encoder_CSn` | 1 CSn (and R1 pad 2) | 1 (bottom) |
| `SPI_SCK` | 2 CLK (and R2 pad 1) | 2 (bottom) |
| `SPI_MISO` | 3 MISO | 3 (bottom) |
| `SPI_MOSI` | 4 MOSI (and R3 pad 1) | 4 (bottom) |
| `3V3` | 11 VDD, 12 VDD3V3 (and C1 pad 1, R1 pad 1) | 5 (top) |
| `GND` | 5 TEST, 13 GND (and C1 pad 2, R2 pad 2, R3 pad 2) | 6 (top) |
| `Encoder_ABI_A` | 7 A | 7 (top) |
| `Encoder_ABI_B` | 6 B | 8 (top) |

The Altium schematic names a Fenghua 0603B104K500NT for C1 (LCSC C30926, a JLCPCB extended part);
the Yageo part has the same value, tolerance, rating, dielectric and package and is a basic part.
The firmware reads the angle over SPI and the ABI outputs; the index (I/PWM) and U, V, W outputs
stay open.

A floating digital input is not allowed (DS Figure 4 note 1). CSn, CLK and MOSI are driven only by
the main board's MCU, whose pins are in analog mode, released, during and just after reset (RM0468
Rev 3 section 11.3.1 p511), so the board pulls them as notes 2 and 3 ask: R1 holds CSn high, the
sensor deselected; R2 and R3 hold CLK and MOSI low, CLK at its SPI mode 1 idle level (DS Figure 18).
The pulls sit on this board, with the part that needs them, so they hold with any host. SPI_SCK and
SPI_MOSI are shared by both encoder boards and the IMU, whose SCL and SDA inputs have no pull-up
by default (LSM6DSV DS13476 Rev 5 Table 22), so nothing on the bus fights the pull-downs; with both
boards fitted the two 100 kOhm pull-downs act in parallel, 50 kOhm, 66 uA while the MCU drives a
line high. R1's 10 kOhm loads the
MCU's chip-select pin with 0.33 mA while it is low. The bench `spi_inputs_held` checks the three
pulls and their range.

## Layout

The layout is the Altium MicrasEncoder.PcbDoc's, transferred by
[`previous/transfer_layout.py`](../previous/transfer_layout.py), with the 3V3 route, C1 and R1-R3
placed by [`layout/fixes.py`](fixes.py):

- IC1 sits on the tab centre line with its centre 9.0 mm above the shoulder (the main board's top
  surface), pin 1 top left seen from the chip side.
- SPI leaves IC1 pins 1-4 on the top, drops through four vias under the package and runs on the
  bottom (0.38 mm tracks) to the bottom tab pads; A and B run on the top (0.254 mm) to the top
  pads.
- 3V3 runs on the top (0.254 mm) straight up from its tab pad to IC1 pins 11 and 12, over the
  bottom-side Encoder_CSn track. C1 sits right of it below IC1, pad 1 on the track, 4.0 mm from
  pin 11 (pad centres), as close as the courtyards allow.
- R3 and R2 sit above the bottom-side SPI_MOSI and SPI_SCK tracks, between IC1 and the tab, each
  with a via onto its track; R1 sits right of the 3V3 track, below C1, with a via and a short
  bottom-side track to Encoder_CSn. The vias of R2 and R3 touch the lower edge of the
  bottom-side logo; like the four SPI vias under the logo, they are tented.
- GND pours on both layers, joined by six vias along the sides, with the Altium polygons' neck
  widths (copper narrower than 0.1 mm on the top, 0.4 mm on the bottom is not poured, which keeps
  the bottom pour out of the channels between the SPI tracks) and solid pad connections. The
  copper connections keep the previous teardrops as plain zones (priority 100 and up, above the
  pours), one per track end, filled with a 0.1 mm minimum width, JLCPCB's minimum copper feature.
- Silkscreen: the pin names above the tab on each side and the IC1, C1 and J1 designators, all
  0.5 mm high with a 0.125 mm stroke (the owner's choice), and the Micras logo on the bottom. R1-R3 carry their designators on F.Fab only:
  beside an 0402 on this board a 0.5 mm label cannot keep the 0.1 mm silkscreen clearance.
- IC1 and J1 are locked where `spec/encoder.toml` puts them. The drill and placement origin of
  the fab outputs is the Altium origin, the tab's bottom left corner.
- The Edge.Cuts outline is the Altium one without its duplicated vertex (a 1 nm line at the top
  right corner, which KiCad reads as a malformed outline).

The board's silkscreen text minimum is 0.5 mm high with a 0.125 mm stroke, the owner's choice
(the height in `encoder.zen`, the stroke in `rules/kicad-severities.toml`, both checked by DRC and
by `tests/test_encoder.py`); JLCPCB recommends 1.0 mm. Regenerate the layout from the previous revision with:

```sh
MICRAS_PREVIOUS=~/codes/hw_debug python3 boards/encoder/previous/transfer_layout.py
python3 boards/encoder/layout/fixes.py
python3 boards/encoder/layout/fork.py
make gen && make check
```

## Mechanics

[`spec/encoder.toml`](../../../spec/encoder.toml): origin at the tab centre on the shoulder line, u to
the right seen from the chip side, v up. The Edge.Cuts outline is layout geometry; `micras-pcb
mech encoder` checks its features (9.6 mm width, 13.1 mm top with 1 mm corner radii, 8.0 mm
shoulder, the tapers to 7.457 mm, the 5.0 x 1.0 mm tab with 0.1 mm reliefs) and exports the layout
outline to `build/encoder/encoder_mech.json`. The stackup is the PcbDoc's: 0.70 mm FR-4 core
(Dk 4.5) and 35 um copper; with Zener's fixed 10 um solder mask a side it is 0.79 mm (Altium's
12.7 um resist makes 0.7954 mm). It is ordered as JLCPCB's 0.8 mm 2-layer board, ENIG finish,
black solder mask and white silkscreen (Zener's 2-layer defaults, the owner's choice). Solder mask
expansion 0.02 mm, the Altium rule.

## Differences from the Altium board

Apart from the fixes of the [layout](#layout) (the 3V3 route, C1 moved, R1-R3 with their tracks and
vias, one of the two SPI_MOSI teardrops at IC1 pad 4 removed, the IC1 and C1 designators moved, IC1's
courtyard on F.CrtYd), the board's copper, mask, paste, drills and outline match the Altium
MicrasEncoder's own Gerbers (its CAMtastic output) except:

| What | This board | Altium board | Why |
|---|---|---|---|
| Pour to board edge | 0.21 mm | 0.195 mm | `rules/jlcpcb.kicad_dru`: JLCPCB's 0.2 mm routed-edge clearance plus 10 um for the fill's arc approximation |
| C1 | KiCad `C_0603_1608Metric`: 0.90 x 0.95 mm pads; KiCad silkscreen and 3D model (0.8 mm wide) | 0.75 x 0.94 mm pads, Altium's pad box and model (0.9 mm wide) | the stdlib generic capacitor's footprint |
| Teardrop cusps | thinner than 0.1 mm left out (the 3V3 teardrop at (150.1, 102.1) is that thin all over and has no copper) | drawn to a point | JLCPCB's 0.1 mm minimum copper feature |
| Texts | KiCad stroke font | Altium fonts | same strings, sizes and positions |
| Solder mask thickness | 10 um a side | 12.7 um | Zener's stackup has no mask thickness setting |

The joint with the main board (`tests/test_joint.py`, `tests/test_layout.py`): the tab pads carry
the slot pads' signals (`components/micras/EncoderSlot`), face them pad for pad (0.95 mm pitch,
0.6 mm wide) and run from 0.8 mm into the slot to 1.2 mm above the main board's surface. J1's
pads carry paste openings on both sides, so assembly pre-tins the tab pads for that joint.

## Known faults

None: the encoder board passes every gate of `make check` (build, warnings, its test benches,
layout-check, ERC, LVS, previous, DRC, DFM, its pytests, parts).

Requirements without a check on this board, and why:

- The design review (`hw_debug/schematic_review.md` m19) asks for 1 uF + 100 nF at the main
  board's encoder slots, since the encoder board's 100 nF sits at the end of the joint: a main
  board item.

## Open items

- [ ] Check the IC1, C1 and R1-R3 placement rotations in JLCPCB's assembly preview, then set
      `rotation_verified = true` in `parts/jlc.toml` (correct `rotation` first if needed).
- [ ] MicrasHardware models the board as a 9.6 x 13.1 mm rectangle, 0.77 mm thick, with the
      5.0 x 4.4 mm package body turned 90 degrees from the board's (D 5.0 mm runs along v): point it
      at `build/encoder/encoder_mech.json` instead of copied numbers.
