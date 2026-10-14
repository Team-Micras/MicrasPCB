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

## Design notes

Outline, tab, pinout and sensor position follow the Altium MicrasEncoder.PcbDoc
(hw_debug/modules/encoder), so the board fits the existing main board.

- The 100 nF decoupling capacitor is Yageo CC0603KRX7R9BB104 (LCSC C14663), a JLCPCB basic part,
  so it carries no extended-part fee.
- The capacitor sits on the 3V3 trace 5.5 mm from the package centre, between the supply pins and
  the tab.
- Vias are 0.3 mm drill / 0.6 mm pad, JLCPCB's no-surcharge drill. The pours keep 0.3 mm from the
  board edge, which clears DFM at the tab reliefs.
- The index (I/PWM) and U, V, W outputs are left unconnected: the firmware reads the angle over
  SPI and the ABI outputs.

## Open items

- [ ] Check the U1 and C1 placement rotations in JLCPCB's assembly preview, then set
      `rotation_verified = true` in `parts/jlc.toml` (correct `rotation` first if needed).
- [ ] The schematic review (`hw_debug/schematic_review.md` m19) asks for 1 uF + 100 nF at the
      main board's encoder connectors: a main-board item, not this board.
- [ ] MicrasHardware hard-codes `Board.encoder_pcb_t = 0.77`; the spec says 0.80. Point it
      at `build/encoder/encoder_mech.json` (or the release asset) instead of a copied number.
