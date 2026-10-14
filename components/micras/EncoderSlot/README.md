# EncoderSlot

The main board's side of the joint with an encoder board ([`EncoderTab`](../EncoderTab)): 8 top-side
pads, 4 on each side of a slot the encoder board's tab stands in. Copper and a cut-out on the main
board, not a purchased part, so it is excluded from the BOM and the placement file. Evidence is in
the docstring of [`EncoderSlot.zen`](EncoderSlot.zen).

```python
load("@stdlib/interfaces.zen", "Spi")
EncoderSlot = Module("github.com/Team-Micras/MicrasPCB/components/micras/EncoderSlot/EncoderSlot.zen")

EncoderSlot(name="EC1", VDD=V3V3, GND=GND, SPI=Spi(CS=ENC_R_CS, CLK=SCK, MISO=MISO, MOSI=MOSI), A=ENC_R_A, B=ENC_R_B)
```

| Pad | Signal | x (mm) | y (mm) | Mates encoder tab pad |
|---|---|---|---|---|
| 1 | CSn | -1.21 | -1.425 | 1 (bottom side) |
| 2 | CLK | -1.21 | -0.475 | 2 |
| 3 | MISO | -1.21 | +0.475 | 3 |
| 4 | MOSI | -1.21 | +1.425 | 4 |
| 5 | VDD (3.3 V) | +1.21 | -1.425 | 5 (top, chip side) |
| 6 | GND | +1.21 | -0.475 | 6 |
| 7 | A | +1.21 | +0.475 | 7 |
| 8 | B | +1.21 | +1.425 | 8 |

Pads are 1.0 x 0.6 mm. The encoder board's chip side faces +X.

Integration notes:

- **The slot is not in the footprint.** It is a 1.0 x 5.8 mm slot with fully rounded ends (0.5 mm
  radius) on the board's Edge.Cuts, centred on the footprint origin, long along Y; the footprint only
  draws it on F.Fab. The board's `spec/` file must place the slot together with this footprint.
- Slot size: JLCPCB mills non-plated slots at least 1.0 mm wide, so the ends are rounded with at
  least a 0.5 mm radius (jlcpcb.com/capabilities/pcb-capabilities). The 0.80 mm encoder board
  (`spec/encoder.toml`, +0.1 mm thickness tolerance) fits the width, and the 5.0 mm tab's corners lie
  0.46 mm from the end-radius centres, inside the 0.5 mm radius. The 8.0 mm shoulder of the encoder
  board rests on the main board 1.1 mm beyond each slot end.
- Pad inner edges sit 0.21 mm from the slot walls (JLCPCB copper to board edge: 0.20 mm,
  `rules/jlcpcb.kicad_dru`); pitch and pad size match the encoder tab, so encoder boards built to
  `spec/encoder.toml` mate unchanged.
- `VDD` is declared 3.0-3.6 V: the AS5047U's 3.3 V mode range (AS5047U DS Figure 6).
- `MISO` is typed tri-state in the symbol (the AS5047U releases it while CSn is high), `A`/`B` as
  outputs and `CSn`/`CLK`/`MOSI` as inputs, as seen from the main board.
