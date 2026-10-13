# EncoderTab

The encoder board's edge tab: 8 pads (4 per side, 0.6 x 2.0 mm, 0.95 mm pitch) on a 5.0 x 1.0 mm
tab that solders into a slot in the main board. Copper on the PCB, not a purchased part, so it is
excluded from the BOM and the placement file.

| Pad | Side | Signal |
|---|---|---|
| 1 | bottom | CSn |
| 2 | bottom | CLK |
| 3 | bottom | MISO |
| 4 | bottom | MOSI |
| 5 | top | VDD (3.3 V) |
| 6 | top | GND |
| 7 | top | A |
| 8 | top | B |

The footprint origin is the tab centre on the shoulder line (the main board's top surface), with +Y
pointing into the slot. The board outline itself is generated from `spec/encoder.toml`.
