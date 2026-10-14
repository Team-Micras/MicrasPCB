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
| 1 | CSn | -1.16 | -1.425 | 1 (bottom side) |
| 2 | CLK | -1.16 | -0.475 | 2 |
| 3 | MISO | -1.16 | +0.475 | 3 |
| 4 | MOSI | -1.16 | +1.425 | 4 |
| 5 | VDD (3.3 V) | +1.16 | -1.425 | 5 (top, chip side) |
| 6 | GND | +1.16 | -0.475 | 6 |
| 7 | A | +1.16 | +0.475 | 7 |
| 8 | B | +1.16 | +1.425 | 8 |

Pads are 1.0 x 0.6 mm. The encoder board's chip side faces +X.

Integration notes:

- **The slot is not in the footprint.** It is a 0.90 x 5.10 mm rectangle on the board's Edge.Cuts,
  centred on the footprint origin, long along Y; the footprint only draws it on F.Fab. The board's
  `spec/` file must place the slot together with this footprint.
- Fit: the encoder tab is 5.0 mm wide and the encoder board 0.80 mm thick (`spec/encoder.toml`), so
  the slot leaves 0.05 mm per end and 0.05 mm per side as drawn (square corners). A milled slot gets
  rounded ends, which shortens the full-width length available to the tab.
- `VDD` is declared 3.0-3.6 V: the AS5047U's 3.3 V mode range (AS5047U DS Figure 6).
- `MISO` is typed tri-state in the symbol (the AS5047U releases it while CSn is high), `A`/`B` as
  outputs and `CSn`/`CLK`/`MOSI` as inputs, as seen from the main board.
