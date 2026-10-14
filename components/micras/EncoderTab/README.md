# EncoderTab

The encoder board's edge tab: 8 pads (4 per side, 2.0 x 0.6 mm, 0.95 mm pitch) on a 5.0 x 1.0 mm
tab that solders into a slot in the main board ([`EncoderSlot`](../EncoderSlot)). Copper on the
PCB, not a purchased part, so it is excluded from the BOM and the placement file. Footprint
`ENCODER_CONN.kicad_mod`: the pads of the Altium EncoderLib ENCODER_CONN (MicrasEncoder.PcbDoc J1).

| Pad | Side | Signal | u (mm, chip side view) |
|---|---|---|---|
| 1 | bottom | CSn | +1.425 |
| 2 | bottom | CLK | +0.475 |
| 3 | bottom | MISO | -0.475 |
| 4 | bottom | MOSI | -1.425 |
| 5 | top | VDD (3.3 V) | +1.425 |
| 6 | top | GND | +0.475 |
| 7 | top | A | -0.475 |
| 8 | top | B | -1.425 |

The footprint origin is the pad centre line, 0.2 mm above the shoulder line (the main board's top
surface); the footprint's -X points into the slot, so the board places it at 90 degrees. The pads
run from 0.8 mm below the shoulder line to 1.2 mm above it and end 0.2 mm from the tab edge.
The board outline (tab, shoulder reliefs) is the encoder board's Edge.Cuts, checked against
`spec/encoder.toml`.
