# Encoder board

One per wheel. An AS5047U magnetic angle sensor on a 9.6 x 14.1 mm, 2-layer, 0.79 mm board that
stands upright in a slot in the main board, facing the diametric magnet on the wheel axle. Supply
(3.3 V), SPI and the ABI quadrature outputs leave through the 8 edge pads of its tab, soldered to
the main board beside the slot.

The board replicates the MicrasEncoder Altium design (`hw_debug/modules/encoder`) part for part:
same designators, footprints, net names, placement, routing, pours, outline and silkscreen.
`micras-pcb previous compare encoder` checks the netlist against that design's connectivity
([`previous/board.json`](previous/board.json)); there are no declared changes.

## Files

| File | Contents |
|---|---|
| [`encoder.zen`](encoder.zen) | IC1 (AS5047U), C1, the edge tab J1, net names, stackup and rules |
| [`test/`](test) | `pcb test` bench of the board's circuit: one 3V3 supply from the tab, the 100 nF at the sensor, capacitor ratings |
| [`layout/`](layout) | KiCad project; the `.kicad_pcb` holds placement and routing |
| [`previous/`](previous) | the previous revision's snapshot, and [`transfer_layout.py`](previous/transfer_layout.py), which builds the layout from that revision |
| [`spec/encoder.toml`](../../spec/encoder.toml) | mechanical interface: thickness, outline, tab, sensor and tab positions |

## Circuit

| Designator | Part | Package | Notes |
|---|---|---|---|
| IC1 | ams OSRAM AS5047U-HTSM ([`components/ams/AS5047U`](../../components/ams/AS5047U)) | TSSOP-14, `SOP65P640X120-14N` | 3.3 V mode: VDD and VDD3V3 on 3V3, TEST on GND, U/V/W and I/PWM open (DS v1-00 Figure 4, Figure 11) |
| C1 | Yageo CC0603KRX7R9BB104, 100 nF 10 % 50 V X7R (LCSC C14663, JLCPCB basic) | 0603 (KiCad `C_0603_1608Metric`) | the 100 nF of DS Figure 11 on 3V3 |
| J1 | edge tab ([`components/micras/EncoderTab`](../../components/micras/EncoderTab)) | `ENCODER_CONN`, copper on the board | not in the BOM |

| Net | IC1 | J1 |
|---|---|---|
| `Encoder_CSn` | 1 CSn | 1 (bottom) |
| `SPI_SCK` | 2 CLK | 2 (bottom) |
| `SPI_MISO` | 3 MISO | 3 (bottom) |
| `SPI_MOSI` | 4 MOSI | 4 (bottom) |
| `3V3` | 11 VDD, 12 VDD3V3 (and C1 pad 1) | 5 (top) |
| `GND` | 5 TEST, 13 GND (and C1 pad 2) | 6 (top) |
| `Encoder_ABI_A` | 7 A | 7 (top) |
| `Encoder_ABI_B` | 6 B | 8 (top) |

The Altium schematic names a Fenghua 0603B104K500NT for C1 (LCSC C30926, a JLCPCB extended part);
the Yageo part has the same value, tolerance, rating, dielectric and package and is a basic part.
The firmware reads the angle over SPI and the ABI outputs; the index (I/PWM) and U, V, W outputs
stay open.

## Layout

From the Altium MicrasEncoder.PcbDoc, by [`previous/transfer_layout.py`](previous/transfer_layout.py):

- IC1 sits on the tab centre line with its centre 9.0 mm above the shoulder (the main board's top
  surface), pin 1 top left seen from the chip side; C1 4.5 mm below it, between the supply pins and
  the tab.
- SPI leaves IC1 pins 1-4 on the top, drops through four vias under the package and runs on the
  bottom (0.38 mm tracks) to the bottom tab pads; 3V3, A and B run on the top (0.254 mm) to the top
  pads.
- GND pours on both layers, joined by six vias along the sides; the copper connections keep the
  previous teardrops as plain zones (priority 100 and up, above the pours).
- Silkscreen: the pin names above the tab on each side, the designators, and the Micras logo on
  the bottom.
- IC1 and J1 are locked where `spec/encoder.toml` puts them. The drill and placement origin of
  the fab outputs is the Altium origin, the tab's bottom left corner.

The KiCad library footprint of C1 is fitted on the previous 0603 pads (75 um rms off, the KiCad
pads being 0.15 mm further apart). Regenerate the layout from the previous revision with:

```sh
MICRAS_PREVIOUS=~/codes/hw_debug python3 boards/encoder/previous/transfer_layout.py
make gen && make check
```

## Mechanics

[`spec/encoder.toml`](../../spec/encoder.toml): origin at the tab centre on the shoulder line, u to
the right seen from the chip side, v up. The Edge.Cuts outline is layout geometry; `micras-pcb
mech encoder` checks its features (9.6 mm width, 13.1 mm top with 1 mm corner radii, 8.0 mm
shoulder, the tapers to 7.457 mm, the 5.0 x 1.0 mm tab with 0.1 mm reliefs) and exports the layout
outline to `build/encoder/encoder_mech.json`. The stackup is the PcbDoc's: 0.70 mm core, 35 um
copper and 10 um mask a side, 0.79 mm; it is ordered as JLCPCB's 0.8 mm 2-layer board.

The joint with the main board (`tests/test_joint.py`, `tests/test_layout.py`): the tab pads carry
the slot pads' signals (`components/micras/EncoderSlot`), face them pad for pad (0.95 mm pitch,
0.6 mm wide) and run from 0.8 mm into the slot to 1.2 mm above the main board's surface.

## Known faults

The board keeps its previous revision's layout and footprints, so the layout checks fail where
those have faults. Each failing check, its cause and the fix:

| Check (gate) | Cause | Fix |
|---|---|---|
| `test_every_assembled_footprint_has_a_courtyard[encoder]` (pytest) | IC1's footprint from the Altium EncoderLib draws its courtyard on User.15 (Altium mechanical layer 15), so KiCad's courtyard checks do not see it | move the outline to F.CrtYd in `components/ams/AS5047U` |
| `invalid_outline` (drc, layout-check; error) | a 1 nm Edge.Cuts line at the top right corner, KiCad (153.3011, 98.953604) to (153.3011, 98.953605), between the corner arc and the right side, left by the Altium conversion; KiCad reads the outline as malformed | delete the line (the outline geometry is unchanged) |
| `copper_sliver` (drc, warning) | the two SPI_MOSI teardrops at IC1 pad 4 overlap and leave a sliver between their outlines on F.Cu; the teardrops are plain zones, which KiCad does not exempt from the sliver test | merge or trim the two outlines |
| `text_height` (drc, warning) | the pin names (B, A, GND, 3V3 on the top; CSn, SCK, MISO, MOSI on the bottom) are 0.5 mm high, below KiCad's 0.6 mm default | larger texts, or lower the board's text limit |

Requirements without a check, and why:

- AS5047U DS v1-00 p4 note 1: a floating digital input is not allowed. CSn, CLK and MOSI are
  driven only by the main board's MCU, whose pins are in analog mode during reset (RM0468 11.3.1),
  and neither board pulls them; the datasheet asks for the pull-up on CSn and the pull-downs on CLK
  and MOSI only when SPI is not used (notes 2 and 3), so no check enforces them.
- The design review (`hw_debug/schematic_review.md` m19) asks for 1 uF + 100 nF at the main
  board's encoder slots, since the encoder board's 100 nF sits at the end of the joint: a main
  board item.

## Open items

- [ ] Solder mask colour and surface finish: not recorded in the Altium design; the board uses
      the 2-layer defaults until they are confirmed.
- [ ] Check the IC1 and C1 placement rotations in JLCPCB's assembly preview, then set
      `rotation_verified = true` in `parts/jlc.toml` (correct `rotation` first if needed).
- [ ] MicrasHardware models the board as a 9.6 x 13.1 mm rectangle, 0.77 mm thick, with the
      5.0 x 4.4 mm package body turned 90 degrees from the board's (D 5.0 mm runs along v): point it
      at `build/encoder/encoder_mech.json` instead of copied numbers.
- [ ] Fix the [known faults](#known-faults).
