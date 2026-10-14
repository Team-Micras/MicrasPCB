# Bluetooth module

The Micras Bluetooth module: a 16 x 25 mm, 2-layer, 0.79 mm board with an HM-19 Bluetooth Low
Energy module (TI CC2640R2F) and a vertical USB-C plug. It plugs into the main board's USB-C
receptacle U2 and stands upright behind the robot, and gives the firmware a wireless UART
(MicrasFirmware `bluetooth_design.md`: UART4, 115 200 8N1, no flow control).

The circuit is the MicrasBluetoothModule Altium design with two changes from the design review
(`hw_debug/schematic_review.md`): the plug's CC contacts carry the module's signature (M6), and
R4 pulls the HM-19's RESETB up (m17). Every part keeps its designator, and `micras-pcb previous
compare bluetooth` checks the netlist against that design's connectivity
([`previous/board.json`](previous/board.json)) plus the changes in
[`changes.toml`](changes.toml).

## Files

| File | Contents |
|---|---|
| [`bluetooth.zen`](bluetooth.zen) | the circuit (U1 HM-19, USB1 plug, R1-R4, C1, C2, D1, OP1), board stackup and rules |
| [`erc.toml`](erc.toml) | 3V3 and GND come from the main board through the plug (the PWR_FLAG role for ERC) |
| [`changes.toml`](changes.toml) | connectivity changes against the previous revision: the CC signature (M6), the RESETB pull-up (m17) |
| [`test/`](test) | `pcb test` bench of the circuit: HM-19 application circuit, LED current, USB-C signature, SBU and VBUS, RESETB |
| [`layout/`](layout) | KiCad project; the `.kicad_pcb` holds placement and routing; [`fixes.py`](layout/fixes.py) is the pcbnew script that made the review fixes in it |
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
| R4 | 10 kOhm from RESETB (pin 11) to 3V3: the CC2640R2F's RESET_N has no internal pull-up (SWRS204C Table 7-1) |
| OP1 | open pad (bottom side) from PIO0 (pin 16, the key) to GND |
| USB1 | USB-C plug: 3V3 on SBU1/SBU2, UART on D+/D-, GND, CC1 and CC2 on D+ (the signature); VBUS open |

RTS, CTS, KEY (pin 8), PIO2 and PIO3 are open, as in the vendor schematic.

## Interface with the main board

The plug mates the main board's U2 (GT-USB-7010ASV) contact by contact. The plug joins both D+
contacts, both D- contacts and SBU1 with SBU2, and U2 joins them the same way, so the module works
either side up (`tests/test_bluetooth.py` checks both orientations).

| Contacts | Module | Main board |
|---|---|---|
| SBU1, SBU2 (A8, B8) | `3V3`: U1 VCC, C1, C2 | `PERIPHERALS.SBU_PWR`: 3V3 through a switch and the PTC fuse F1 (KASML010), on while the main board reads the signature |
| D- (A7, B7) | `UART_TX`: R1 from HM-19 UART_TX | to MCU PA11 = UART4_RX |
| D+ (A6, B6) | `UART_RX`: R2 to HM-19 UART_RX | from MCU PA12 = UART4_TX |
| CC1, CC2 (A5, B5) | `UART_RX` (the signature) | R6, R7 5.1 kOhm Rd to GND, and the signature detector |
| GND, shell | `GND` | `GND` |
| VBUS (A4, A9, B4, B9) | open | `+5V`, the main board's USB power input |

The UART crosses correctly: the module transmits on D- into the MCU's receiver PA11, and receives
on D+ from PA12. With 1 kOhm in series per line on the module, the RC with the main board's
D+/D- capacitance (tens of pF) is tens of ns, against 8.68 us per bit at 115 200 baud.

### The signature (review M6)

USB Type-C reserves SBU for specified uses: a port leaves it open or pulls it down by at least
950 kOhm (Type-C R2.0 section 4.3 p139, Table 4-28 p236), and a full-featured cable wires it
through to a host's Alternate Mode or an audio accessory's microphone. So the main board may put
3V3 on SBU only when the module, and nothing else, is in its receptacle. The module identifies
itself on CC:

- **Module.** Both CC contacts are on its D+ contacts, so the signature shows either side up.
- **Main board.** D+ is the MCU's UART4 TX (PA12), which idles high once the firmware has started
  UART4 (at boot, `MX_UART4_Init`). Through the module it pulls the main board's CC contacts,
  each 5.1 kOhm Rd to GND, to the TX level: about 3.2 V, at least 2.87 V (STM32H725 DS13311
  Table 56: VOH >= VDD - 0.4 V; 3V3 >= 3.27 V). No Type-C partner makes that: across a sink's Rd
  a source makes at most 2.04 V (Table 4-36, vRd-Connect, +-10 % Rd; 2.18 V with +-20 %,
  Table 4-35), and cables and accessories only add Ra or Rd to GND. The main board's detector
  holds the peak of its CC1 through the UART's low bits, compares it with a threshold between the
  two (about 2.3 V, ratiometric to 3V3), and switches 3V3 onto SBU through F1 only above it. Its
  Rd stays as it is, so it is still a USB Type-C sink and its USB power input is unchanged.
- **Cost.** PA12 drives the two Rd in parallel, 2.55 kOhm (1.3 mA), while the module is plugged
  in. The module is unpowered until the firmware starts UART4, and loses power about a quarter of
  a second after PA12 stops driving (an MCU reset), as the detector's hold decays. Until the
  detector switches on (a few ms), PA12 also feeds a little current into the unpowered HM-19's
  UART_RX pin through R2.
- **Elsewhere.** Plugged into another USB-C port the module gets no supply (its VBUS is open and
  a host never drives SBU) and does nothing.

The main board's side is in its own pull request (the review fixes, #13).

## Board

2 copper layers, 35 um copper on a 0.7 mm FR-4 core, 0.79 mm with mask, from the Altium layer
stack. Design rules: 0.1 mm clearance, 0.254 mm track, 0.6 / 0.3 mm and 0.5 / 0.3 mm vias, 0.2 mm
copper to edge, the Altium JLCPCB rule set; `rules/jlcpcb.kicad_dru` adds JLCPCB's limits on top.

## Layout

The layout is the Altium MicrasBluetoothModule.PcbDoc's, in the same KiCad coordinates, built by
[`previous/transfer_layout.py`](previous/transfer_layout.py) from KiCad's conversion of that PCB;
running the script again changes nothing.

- **Top**: U1 near the top edge, with the antenna end of the module (the 7 mm above pad 1, V107
  6.6) 5.5 mm beyond the board's top edge; R2, R1, R3, D1, C2, C1 in a row below it, R4 above C2;
  USB1 at the bottom, in the narrow neck, with its CC pads joined to the adjacent D+ pads. RESETB
  runs from R4 under the module to U1 pad 11 from the inside of the pad row. GND pour.
- **Bottom**: OP1 at the top, the MICRAS logo in silkscreen, the routing that crosses the plug's
  rows. GND pour.
- The outline narrows from 16 mm to the plug's width towards the bottom edge.
- Resistors, capacitors and D1 use KiCad's generic footprints, each centred on its pads' positions
  in the Altium footprint: pad centres within 75 um of the Altium ones (the 0603 pad pitches
  differ). The teardrops of the Altium design are plain copper zones (priorities 100 and up),
  as on the main board: KiCad 10 orders zones by UUID and does not save a teardrop's UUID.
- Silkscreen: the reference designators are 0.5 mm high with a 0.15 mm stroke, the size the team
  reads on the previous boards, and the board's minimum text height is 0.5 mm
  (`bluetooth.zen`, `Silkscreen(minimum_text_height=0.5)`). JLCPCB recommends 1.0 mm text, so
  these may print less sharply; that is accepted.

## Mechanics

[`spec/bluetooth.toml`](../../spec/bluetooth.toml) places the board frame on the plug centre and
exports `build/bluetooth/bluetooth_mech.json` (outline polygon, plug, HM-19, and where the board
sits in the robot). Mated, the module's component side faces the main board's rear edge at the USB
notch: the plug axis is on U2's axis (robot y = -1.75 mm) at 1.68 mm above the main board's top
surface (U2 drawing, CH), and the component side at robot x = -35.60 mm, 1.5 mm behind the notch
edge (x = -34.1 mm). That x follows from the receptacle drawing's mated dimensions (6.65 mm plug
shell, 1.85 mm Ref from the plug overmold to the receptacle face) and the plug's 8.65 mm height.

## Known faults

ERC, LVS, previous, DRC, DFM, the warnings gate and the module's test benches pass. One check
still fails, on the main board's side of the joint:

| Check (gate) | Fault | Requirement | Fix |
|---|---|---|---|
| `test_uart_rx_is_held_with_the_module_unplugged` (pytest) | with the module unplugged PA11 (UART4_RX) ends at an open contact: the firmware sets no pull and the main board has no resistor (m17) | a UART input idles high; a floating input feeds noise bytes to the circular DMA | 100 kOhm from PA11 to 3V3 on the main board (its review fixes, #13) |

The main board's own checks (`usb_c_sbu_open`, M6) pass once its signature detector is in.

Requirements without a check, and why:

- The key (m17): the HM-19 datasheet puts the system key on pin 8 in its pin table and on PIO0
  (pin 16, where OP1 is) in its schematic and AT commands. Bridging OP1 for over 1000 ms in
  standby restores the factory settings, which the firmware's AT set-up relies on; `AT+SYSK0`
  makes the key only cancel, so send it when setting the module up. Which pin the fitted module
  uses needs a bench test.
- F1 against the module current (m17): F1 holds 50 mA at 85 C (KASML010), the HM-19 datasheet
  quotes 50 mA; no source gives the temperature inside the robot. At 50 mA the module still gets
  over 3.1 V: 3.27 V minimum, F1 up to 2 Ohm (0.1 V), the switch and contacts under 15 mV,
  against its 2.1 V minimum (V107 section 3).
- Hot plugging: C1 (10 uF) charges from the main board's 3V3 through F1 when the switch turns on
  and can dip 3V3; plug the module with the power off.
- Decoupling distance: the vendor schematic gives no distance for C1/C2.
- Mated depth: derived from the receptacle drawing, not measured.

## Open items

- [ ] Solder mask colour and surface finish: not recorded in the Altium design; the board uses the
      2-layer defaults until they are confirmed.
- [ ] Check every part's placement rotation in JLCPCB's assembly preview, then set
      `rotation_verified = true` in `parts/jlc.toml`.
- [ ] The HM-19 (LCSC C9900145630) has no stock at JLCPCB: source and consign it.
- [ ] Measure the mated position on the robot and correct `spec/bluetooth.toml` [mating].
- [ ] Bench test: the main board switches SBU on with the module in either orientation, and
      off with a USB host, a C-to-C cable and an audio adapter.
