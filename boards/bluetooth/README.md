# Bluetooth module

The Micras Bluetooth module: a 16 x 25 mm, 2-layer, 0.79 mm board with an HM-19 Bluetooth Low
Energy module (TI CC2640R2F) and a vertical USB-C plug. It plugs into the main board's USB-C
receptacle U2 and stands upright behind the robot, and gives the firmware a wireless UART
(MicrasFirmware `bluetooth_design.md`: UART4, 115 200 8N1, no flow control).

The circuit replicates the MicrasBluetoothModule Altium design part for part: every part keeps its
designator, and `micras-pcb previous compare bluetooth` checks the netlist against that design's
connectivity ([`previous/board.json`](previous/board.json)); [`changes.toml`](changes.toml)
declares no change.

## Files

| File | Contents |
|---|---|
| [`bluetooth.zen`](bluetooth.zen) | the circuit (U1 HM-19, USB1 plug, R1-R3, C1, C2, D1, OP1), board stackup and rules |
| [`erc.toml`](erc.toml) | 3V3 and GND come from the main board through the plug (the PWR_FLAG role for ERC) |
| [`changes.toml`](changes.toml) | connectivity changes against the previous revision: none |
| [`test/`](test) | `pcb test` bench of the circuit: HM-19 application circuit, LED current, USB-C SBU, RESETB |
| [`layout/`](layout) | KiCad project; the `.kicad_pcb` holds placement and routing |
| [`previous/`](previous) | the previous revision's snapshot and [`transfer_layout.py`](previous/transfer_layout.py), which builds the layout from it |
| [`spec/bluetooth.toml`](../../spec/bluetooth.toml) | mechanics: thickness, outline extents, plug and HM-19 positions, mating with the main board's U2 |

`tests/test_bluetooth.py` checks the board against its previous revision, its joint with the main
board, and the spec.

## Circuit

The HM-19 application circuit of its datasheet (JNHuaMao "HM Bluetooth module datasheet" V107,
section 6.5); the docstring of [`bluetooth.zen`](bluetooth.zen) cites each value.

| Part | Function |
|---|---|
| U1 | HM-19, VCC 2.1-3.7 V (V107 section 3), pins 9 and 10 on 3V3 |
| C1, C2 | 10 uF 35 V X5R and 100 nF 50 V X7R on 3V3 |
| R1 | 1 kOhm from HM-19 UART_TX (pin 2) to the plug's D- contacts (net `UART_TX`) |
| R2 | 1 kOhm from HM-19 UART_RX (pin 4) to the plug's D+ contacts (net `UART_RX`) |
| R3, D1 | the "System LED" output PIO1 (pin 15) through 680 Ohm to a blue 0603 LED: about 0.6 mA |
| OP1 | open pad (bottom side) from PIO0 (pin 16, the key) to GND |
| USB1 | USB-C plug: 3V3 on SBU1/SBU2, UART on D+/D-, GND; VBUS and CC1/CC2 open |

RESETB, RTS, CTS, KEY (pin 8), PIO2 and PIO3 are open, as in the vendor schematic.

## Interface with the main board

The plug mates the main board's U2 (GT-USB-7010ASV) contact by contact. The plug joins both D+
contacts, both D- contacts and SBU1 with SBU2, and U2 joins them the same way, so the module works
either side up (`tests/test_bluetooth.py` checks both orientations).

| Contacts | Module | Main board |
|---|---|---|
| SBU1, SBU2 (A8, B8) | `3V3`: U1 VCC, C1, C2 | `PERIPHERALS.SBU_PWR`, fed from 3V3 through the PTC fuse F1 (KASML010) |
| D- (A7, B7) | `UART_TX`: R1 from HM-19 UART_TX | R8 33 Ohm to `USBD_N`, MCU PA11 = UART4_RX (C22 18 pF to GND) |
| D+ (A6, B6) | `UART_RX`: R2 to HM-19 UART_RX | R9 33 Ohm to `USBD_P`, MCU PA12 = UART4_TX (C23 18 pF to GND, R10 1.5 kOhm to 3V3) |
| GND, shell | `GND` | `GND` |
| VBUS (A4, A9, B4, B9) | open | `+5V`, the USB LDO U3's input |
| CC1, CC2 (A5, B5) | open | R6, R7 5.1 kOhm Rd to GND |

So the main board cannot tell the module from a USB cable: both arrive on the same receptacle,
the module with nothing on VBUS or CC, and the main board drives 3V3 onto SBU whatever is plugged
in. The UART crosses correctly: the module transmits on D- into the MCU's receiver PA11, and
receives on D+ from PA12. Series resistance per line is 1 kOhm + 33 Ohm; with the 18 pF the RC is
about 24 ns, against 8.68 us per bit at 115 200 baud.

## Board

2 copper layers, 35 um copper on a 0.7 mm FR-4 core (Dk 4.5), from the Altium layer stack; with
Zener's fixed 10 um solder mask a side it is 0.79 mm (Altium's 12.7 um resist makes 0.7954 mm),
ordered as JLCPCB's 0.8 mm board. Design rules: 0.1 mm clearance, 0.254 mm track, 0.6 / 0.3 mm
and 0.5 / 0.3 mm vias, 0.2 mm copper to edge, 0.02 mm solder mask expansion, the Altium JLCPCB
rule set; `rules/jlcpcb.kicad_dru` adds JLCPCB's limits on top.

## Layout

The layout is the Altium MicrasBluetoothModule.PcbDoc's, in the same KiCad coordinates, built by
[`previous/transfer_layout.py`](previous/transfer_layout.py) from KiCad's conversion of that PCB;
running the script again changes nothing.

- **Top**: U1 near the top edge, with the antenna end of the module (the 7 mm above pad 1, V107
  6.6) 5.5 mm beyond the board's top edge; R2, R1, R3, D1, C2, C1 in a row below it; USB1 at the
  bottom, in the narrow neck. GND pour.
- **Bottom**: OP1 at the top, the MICRAS logo in silkscreen, the routing that crosses the plug's
  rows. GND pour.
- The outline narrows from 16 mm to the plug's width towards the bottom edge.
- Resistors, capacitors and D1 use KiCad's generic footprints, each centred on its pads' positions
  in the Altium footprint: pad centres within 75 um of the Altium ones (the 0603 pad pitches
  differ). D1 carries KiCad's LED model scaled to the SMLD12BN1W's 0.55 mm height (ROHM
  datasheet p. 1). The teardrops of the Altium design are plain copper zones (priorities 100 and
  up), as on the main board: KiCad 10 orders zones by UUID and does not save a teardrop's UUID.
  They fill with a 0.1 mm minimum width, JLCPCB's minimum copper feature.
- The GND pours keep the Altium polygons' neck widths (copper narrower than 0.1 mm, 0.3 mm in the
  top pour around the plug, is not poured) and join pads solidly.
- The Edge.Cuts outline is the Altium one without its seven duplicated vertices (lines of 1-12 nm,
  which KiCad reads as a malformed, self-intersecting outline); the lines next to them meet within
  12 nm of where they did.

## Differences from the Altium board

There is no Gerber output of the Altium design to compare with; against KiCad's conversion of the
PcbDoc, the board differs in:

| What | This board | Altium board | Why |
|---|---|---|---|
| Pour to board edge | 0.21 mm | 0.23 mm | the KiCad fill under `rules/jlcpcb.kicad_dru`: JLCPCB's 0.2 mm routed-edge clearance plus 10 um for the fill's arc approximation |
| R1-R3, C1, C2, D1 | KiCad's generic 0603 footprints: pads R 0.80 x 0.95, C 0.90 x 0.95, LED 0.875 x 0.95 mm, their centres within 75 um of the Altium ones; KiCad's silkscreen (no box around the parts, 6.2 mm2 less ink; D1's polarity mark an outline closed on the cathode side) | pads R 0.85 x 1.0, C 0.8 x 0.9, LED 0.8 x 0.8 mm; full boxes, a triangle on D1 | the stdlib generics' footprints |
| Passive 3D models | KiCad library models: R 0.45 mm tall, C 0.8 mm wide; D1 0.55 mm | R 0.56 mm, C 0.9 mm wide, D1 0.6 mm | KiCad's generic models (D1 scaled to its datasheet) |
| Teardrop cusps | thinner than 0.1 mm left out | drawn to a point | JLCPCB's 0.1 mm minimum copper feature |
| Solder mask thickness | 10 um a side | 12.7 um | Zener's stackup has no mask thickness setting |

## Mechanics

[`spec/bluetooth.toml`](../../spec/bluetooth.toml) places the board frame on the plug centre and
exports `build/bluetooth/bluetooth_mech.json` (outline polygon, plug, HM-19, and where the board
sits in the robot). Mated, the module's component side faces the main board's rear edge at the USB
notch: the plug axis is on U2's axis (robot y = -1.75 mm) at 1.68 mm above the main board's top
surface (U2 drawing, CH), and the component side at robot x = -35.60 mm, 1.5 mm behind the notch
edge (x = -34.1 mm). That x follows from the receptacle drawing's mated dimensions (6.65 mm plug
shell, 1.85 mm Ref from the plug overmold to the receptacle face) and the plug's 8.65 mm height.

## Known faults

The board keeps its previous revision's circuit and layout, so the design checks fail where that
revision has faults. Each failing check, the fault behind it (with its item in the design review,
`hw_debug/schematic_review.md`, and `hw_debug/review_research/04_sensors_peripherals.md` section
9), the requirement it breaks, and the fix.

| Check (gate) | Fault | Requirement | Fix |
|---|---|---|---|
| `bluetooth` `usb_c_sbu_not_a_supply` (test) | the module takes its supply from SBU1/SBU2 and leaves VBUS and CC open; the main board drives 3V3 on SBU for it (M6). The main board cannot tell the module from a cable, so a USB-C host or accessory on the same receptacle gets 3V3 on its SBU path | Type-C R2.0 Table 3-5 note 3 (p69): SBU1/SBU2 not connected unless required for a specified purpose; section 4.3 (p139), Table 4-28: open or at least 950 kOhm to GND. The main board's `usb_c_sbu_open` bench fails on the same fault | a dedicated connector for the module, or SBU power through a load switch the MCU turns on only with the module present (review M6); the main and module sides change together |
| `bluetooth` `module_reset_not_floating` (test) | HM-19 RESETB (pin 11) is open (m17) | CC2640R2F SWRS204C Table 7-1: RESET_N "No internal pullup"; the HM-19 datasheet (V107 6.8) does not say whether the module adds one | 10-100 kOhm from RESETB to 3V3, or RESETB to a spare contact so the MCU can reset the module |
| `test_uart_rx_is_held_with_the_module_unplugged` (pytest) | with the module unplugged PA11 (UART4_RX) ends at an open contact: the firmware sets no pull and the main board has no resistor (m17) | a UART input idles high; a floating input feeds noise bytes to the circular DMA | `GPIO_PULLUP` on PA11 in the firmware, or 100 kOhm to 3V3 on the main board |
| `test_every_assembled_footprint_has_a_courtyard[bluetooth]` (pytest) | the HM-19 and plug footprints from the Altium library draw no courtyard (the HM-19 outline is on User.15) | F.CrtYd courtyards for KiCad's overlap check | add F.CrtYd outlines in `components/jnhuamao/HM-19` and `components/jing-extension/918-118A2021Y40006` |
| `text_height` (drc, warning) | 9: the Altium reference texts are 0.5 mm high | KiCad's 0.6 mm default minimum | larger texts, or lower the board's text limit |
| `copper_sliver` (drc, warning) | 1: a teardrop outline overrunning its track on F.Cu; the teardrops are plain zones, which KiCad does not exempt from the sliver test | no copper sliver | trim the outline |

ERC, LVS, previous, DRC and layout-check (warnings only), DFM and the warnings gate pass.

Requirements without a check, and why:

- The key (m17): the HM-19 datasheet puts the system key on pin 8 in its pin table and on PIO0
  (pin 16, where OP1 is) in its schematic and AT commands. Bridging OP1 for over 1000 ms in
  standby restores the factory settings, which the firmware's AT set-up relies on; `AT+SYSK0`
  makes the key only cancel. Which pin the fitted module uses needs a bench test.
- F1 against the module current (m17): F1 holds 50 mA at 85 C (KASML010), the HM-19 datasheet
  quotes 50 mA; no source gives the temperature inside the robot.
- Hot plugging: C1 (10 uF) charges from the main board's 3V3 through F1 alone and can dip 3V3;
  plug the module with the power off.
- Decoupling distance: the vendor schematic gives no distance for C1/C2.
- Mated depth: derived from the receptacle drawing, not measured.

## Open items

- [ ] Solder mask colour and surface finish: not recorded in the Altium design; the board uses the
      2-layer defaults until they are confirmed.
- [ ] Check every part's placement rotation in JLCPCB's assembly preview, then set
      `rotation_verified = true` in `parts/jlc.toml`.
- [ ] The HM-19 (LCSC C9900145630) has no stock at JLCPCB: source and consign it.
- [ ] Measure the mated position on the robot and correct `spec/bluetooth.toml` [mating].
- [ ] Fix the [known faults](#known-faults).
