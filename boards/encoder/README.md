# Encoder board

One per wheel. An AS5047U magnetic angle sensor on a 9.6 x 14.1 mm, 2-layer, 0.8 mm board that
stands upright in a slot in the main board, facing the diametric magnet on the wheel axle. Supply
(3.3 V), SPI and the ABI quadrature outputs leave through the 8 edge pads of its tab, soldered to
the main board beside the slot.

- Circuit: [`encoder.zen`](encoder.zen), with the sensor package
  [`components/ams/AS5047U`](../../components/ams/AS5047U) and the tab
  [`components/micras/EncoderTab`](../../components/micras/EncoderTab).
- Mechanics: [`spec/encoder.toml`](../../spec/encoder.toml) (outline, tab, sensor centre 9.0 mm
  above the main board).
- Layout: [`layout/encoder.kicad_pcb`](layout/encoder.kicad_pcb). SPI drops through vias under
  the package and runs on the bottom to the bottom tab pads; 3V3, GND, A and B run on the top to
  the top pads; GND pours on both sides.

## Changes from the Altium revision (hw_debug/modules/encoder)

Same outline, tab, pinout, sensor position and circuit, so it fits the existing main board.

| Change | Why |
|---|---|
| 100 nF capacitor is C14663 (Yageo CC0603KRX7R9BB104, JLCPCB basic) instead of C30926 (FH 0603B104K500NT, extended) | no extended-part fee at JLCPCB; same value, package, dielectric and rating |
| Capacitor 5.5 mm from the package centre instead of 4.5 mm below it, on the 3V3 trace | room for the new routing; still between the supply pins and the tab |
| New routing; vias 0.3/0.6 mm; pours keep 0.3 mm from the edge | JLCPCB no-surcharge drill; DFM finding at the tab reliefs |
| Index (I/PWM), U, V, W outputs explicitly no-connect | unchanged behaviour; the firmware uses SPI + ABI |

## Open items

- [ ] Check the U1 and C1 placement rotations in JLCPCB's assembly preview, then set
      `rotation_verified = true` in `parts/jlc.toml` (correct `rotation` first if needed).
- [ ] The schematic review (`hw_debug/schematic_review.md` m19) asks for 1 uF + 100 nF at the
      main board's encoder connectors: a main-board item, not this board.
- [ ] MicrasHardware still hard-codes `Board.encoder_pcb_t = 0.77`; the spec says 0.80. Point it
      at `build/encoder/encoder_mech.json` (or the release asset) instead of a copied number.
