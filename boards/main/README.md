# Main board

The Micras micromouse main board: a 50 x 90 mm, 4-layer, 1.04 mm board. It carries the STM32H725RGV6 controller, the battery input and power conversion, the
two locomotion motor bridges and the fan driver, the IMU, four wall sensors, the slots for the
two encoder boards, and the user interface.

The circuit is the MicrasMainBoard Altium design's, with the findings of its design review
(`hw_debug/schematic_review.md`) fixed. Parts of that design keep their designators, and parts the
fixes add continue each series (C58-C76, D8-D12, FB1, Q7, R43-R49, U4-U6). `micras-pcb previous
compare main` checks the netlist and its net names against that design's connectivity
([`previous/board.json`](previous/board.json)) plus the changes declared in
[`changes.toml`](changes.toml), one per review item.

## Files

| File | Sheet instance | Contents |
|---|---|---|
| [`main.zen`](main.zen) | root | IC1 (STM32H725RGV6) and its supply network (C1-C17, L1, FB1), SWD header P1, test points, M2 screw holes H1-H4, board stackup and rules |
| [`Regulators.zen`](Regulators.zen) | `REGULATORS` | J1 battery connector, battery switch SW4/Q6, battery measurement, power mux U4, 3V3 buck IC7, 20 V boost U1, SWD probe ideal diode U5 |
| [`Drivers.zen`](Drivers.zen) | `DRIVERS` | IC5 (L6205D) bridges for M1/M2 with shunts R32/R33, IC6 (STSPIN958) fan driver for M3 with shunt R31 |
| [`Sensors.zen`](Sensors.zen) | `SENSORS` | IC2 (LSM6DSV) IMU, IC3/IC4 (TSC2020) current amplifiers, wall sensors W1-W4 with Q2-Q5, encoder slots EC1/EC2 |
| [`Peripherals.zen`](Peripherals.zen) | `PERIPHERALS` | SW1 DIP switch, SW2/SW3/SW5 buttons, BZ1 buzzer, D1/D2 addressable LEDs, D4/D5 LEDs, U2 USB-C with its ESD protection, VBUS sensing and switched SBU supply |
| [`passives.zen`](passives.zen) | | value, package, rating and part number of every resistor, ceramic capacitor, LED and ferrite line |
| [`changes.toml`](changes.toml) | | connectivity, net-name and part-number changes against the previous revision, each with its review item |
| [`erc.toml`](erc.toml) | | nets supplied from off the board (VBAT, GND, +5V, SWD_VDD) or through a passive part (VDDA), the PWR_FLAG role for ERC |
| [`firmware.toml`](firmware.toml) | | the firmware's pin map, supply setting, battery channel and drive duties, from MicrasFirmware (`micras-pcb firmware snapshot`) |
| [`firmware_changes.toml`](firmware_changes.toml) | | the firmware changes this board needs (see [Firmware changes](#firmware-changes)) |
| [`test/`](test) | | `pcb test` benches of the board's circuit: MCU, power, drivers, peripherals |
| [`layout/`](layout) | | KiCad project; the `.kicad_pcb` holds placement and routing |
| [`previous/`](previous) | | the previous revision's connectivity snapshot, and the scripts that build the layout from that revision (`transfer_layout.py`, `rework.py`) |
| [`spec/main.toml`](../../spec/main.toml) | | mechanical interface: thickness, axle origin, extents, screw holes, encoder slots, USB-C peg holes, fan hole, wheel notches |

Each sheet's docstring describes its circuit with the datasheet figure, table or equation behind
each value.

## Power

```text
J1 battery ──[SW4/Q6, slew-limited]── VBAT ──┬── U1 TPS61178 boost (EN = Motors_Enable) ── +20V ── IC5 bridges
                                             ├── IC6 fan driver, D1/D2 LEDs, R44/R45 ── PA5
                                             └── U4 TPS2121 IN1 ─┐
U2 USB-C VBUS (+5V) ─────────────────────────── U4 TPS2121 IN2 ─┴── VSYS ── IC7 L6981C33 buck ── 3V3
P1 pin 1 (SWD_VDD) ── U5 LM66100 ideal diode ──────────────────────────────────────────────────── 3V3
3V3 ── FB1 ── VDDA
```

| Net | Source | Range | Loads |
|---|---|---|---|
| `VBAT` | 3S LiPo on J1, switched by SW4/Q6 | 9.9-12.6 V | boost U1, fan driver IC6, LEDs D1/D2, battery divider, mux U4 IN1 |
| `GND_BAT` | pack minus on J1 | | switched to `GND` by Q6 |
| `+5V` | USB-C VBUS | 4.4-5.25 V | mux U4 IN2, VBUS divider R47/R48, gate of Q7 |
| `VSYS` | mux U4: the higher of VBAT and +5V | 4.4-12.6 V | buck IC7 only |
| `3V3` | buck IC7 (L6981C33), or the SWD probe through U5 | 3.3 V | MCU, IMU, amplifiers, sensors, encoders, buzzer, logic of the drivers, the Bluetooth module on SBU |
| `SWD_VDD` | the SWD probe on P1 pin 1 | 3.3 V | U5 |
| `+20V` | boost U1 (TPS61178), while Motors_Enable is high | 18.19-19.42 V | locomotion bridges IC5 |
| `VDDA` | 3V3 through FB1 | 3.3 V | MCU analog supply and ADC reference |
| `VCORE` | the MCU's on-chip SMPS through L1 | 0.95-1.40 V | MCU core (VFBSMPS, VCAP1-3) |

Power modes:

- **Battery**: SW4 turns Q6 on (R43/C58 hold VBAT's rise to 2.7 V/ms), which connects the pack
  minus to `GND`. U4 passes VBAT to the buck, which makes 3V3; the boost makes +20V while the
  firmware enables the motors.
- **USB**: VBUS reaches the buck through U4 (1.5 A of 3V3). VBAT stays at 0 V, so the boost, the
  bridges, the fan driver and the addressable LEDs are off: the motors cannot run.
- **SWD probe**: the probe's 3.3 V reaches 3V3 through U5 (an ST-Link V2 clone drives its 3.3 V
  regulator on this pin). The buck's body diode lifts VSYS, which U4 keeps from VBAT and +5V:
  VBAT stays at 0 V, and the motors cannot run.

With two sources at once each one blocks the other: U4 selects the battery over USB, U5 conducts
only while the probe's supply is above 3V3, and the L6981C33 neither sinks current nor switches
while 3V3 is above its set point (DS13554 sections 6.4.1, 6.6.1). `tests/test_power_tree.py`
checks the tree: one regulated source per net besides ORing parts, no regulator's reverse path
reaching a load, and no debug supply reaching the battery net.

## MCU supply

The VFQFPN68 STM32H725 has no VDDLDO pin: the core always runs from the on-chip SMPS, in the
"Direct SMPS supply" of ST AN5419 Figure 5 (p10). VLXSMPS drives L1 (2.2 uH), whose output is
`VCORE`; VFBSMPS and the three VCAP pins all sit on `VCORE`, with 2 x 10 uF at the inductor
(C3, C4) and 100 nF at each VCAP pin (C7, C6, C5), as AN5419 Table 2 (p7-8) requires. The
firmware selects `PWR_DIRECT_SMPS_SUPPLY` to match.

VBAT (pin 1), the backup-domain supply, is on 3V3 with C8 100 nF and C9 1 uF at the pin: with no
backup battery, AN5419 Table 2 ties VBAT to VDD. The pin's range is 1.2-3.6 V (DS13311 Table 13
p116), absolute maximum 4.0 V (Table 10 p114).

VDDA (pin 16) is the ADC reference on this package (DS13311 Figures 46-47 note 1). It comes from
3V3 through the ferrite bead FB1, with C11 1 uF and C10 100 nF at the pin (AN5419 Table 2).

## Signals

Net names are the firmware's pin labels (`Motor_Left_PWM_FW`, `Encoder_Left_CSn`,
`Wall_Sensor_0`, ...; `tests/test_firmware.py` checks them). Nets local to a sheet carry the
sheet's prefix (`REGULATORS.BOOST_FB`). The IMU and both encoder boards share
`SPI_SCK`/`SPI_MISO`/`SPI_MOSI`, each with its own chip select.

| Function | MCU pins |
|---|---|
| Locomotion PWM, enable | PC7, PC9 (left), PA8, PA9 (right); PA10 `Motors_Enable` (bridges and boost) |
| Motor current | PC0 `Current_Sensor_Left` (IC4, shunt R32, left motor M1), PC1 `Current_Sensor_Right` (IC3, R33, right motor M2) |
| Fan | PB15 PWM, PB14 enable/fault, PB13 `Fan_TOFF` (current-limiter flag) |
| Wall sensors | PB6-PB9 emitter PWM; PB1, PC4, PA6, PA4 receiver ADC |
| Encoders | PA3/PC14 CSn, PA0/PA1 and PB3/PA15 ABI A/B (left/right) |
| IMU | PD2 CS, PB5/PB4 INT1/INT2 |
| SPI | PC10 SCK, PC11 MISO, PC12 MOSI |
| USB / Bluetooth UART | PA11 D-, PA12 D+; PH0 `USB_VBUS_Sense` |
| Battery | PA5 `Battery_Voltage` (VBAT x 27 / 127) |
| User interface | PA7 button, PC5/PB0/PB2/PB10 DIP switch, PA2 buzzer, PC6 ARGB LEDs, PB12 `LED_Red` (the yellow LED D4) |
| Debug | PA13 SWDIO, PA14 SWCLK, NRST on P1 |

PC15 and PH1 are unused.

## Firmware changes

The board needs two changes in MicrasFirmware, declared in
[`firmware_changes.toml`](firmware_changes.toml) (the firmware tests apply them):

- **Battery voltage (C1)**: read PA5 (ADC1/ADC2 channel 19, `ADCx_INP19`, label
  `Battery_Voltage`) and scale by 127 / 27 = 4.7037, instead of the internal VBAT/4 channel on
  ADC3: the VBAT pin is on 3V3.
- **VBUS sensing (M11)**: configure PH0 (`PH0-OSC_IN`) as a GPIO input, no pull, label
  `USB_VBUS_Sense`; a USB device stack reads it.

Nothing else changes for the firmware: the boost follows `Motors_Enable`, which the firmware
already drives before every run.

## Board

4 copper layers, 1 oz outer and 0.5 oz inner copper, 0.2104 mm prepreg and 0.5 mm core, 1.0412
mm finished, from the Altium layer stack. Design rules: 0.1 mm clearance, 0.254 mm default track,
0.45 / 0.3 mm vias (0.5 / 0.3 and 0.8 / 0.4 mm also used), 0.2 mm copper to edge, all from the
Altium design rules; `rules/jlcpcb.kicad_dru` adds JLCPCB's limits on top.

## Layout

The layout is the Altium MicrasMainBoard.PcbDoc's, in the same KiCad coordinates: MicrasHardware
and the firmware place the board by them, with the wheel-axle midpoint (between the encoder slots)
at KiCad (148.5011, 113.5036). [`previous/transfer_layout.py`](previous/transfer_layout.py)
builds it from the KiCad conversion of that PCB and [`previous/rework.py`](previous/rework.py)
adds the copper of the declared changes C1 and C2; running the script again changes nothing.
The parts and connections the review fixes add are in the layout but not yet placed or routed
(see [Known faults](#known-faults)).

| Layer | Use |
|---|---|
| F.Cu | every part (the board is single-sided), signal routing, power pours (VBAT, +20V, GND_BAT, 3V3, GND, fan outputs) |
| In1.Cu | solid GND plane |
| In2.Cu | power planes: 3V3 under the MCU and most of the front half; VBAT, +20V and +5V behind it, VBAT reaching forward on the right to the buck IC7; the VCORE route |
| B.Cu | signal routing |

Where things are, in the robot frame (x forward, y left, from the axle midpoint; `spec/main.toml`):

- **Front** (x 30-54 mm): IC1 at x = 37, the wall sensors W1-W4 at the front corners, the LEDs
  D1/D2/D4/D5 on the front edge, the buttons SW2/SW3/SW5.
- **Middle** (x -10 to 30 mm): the IMU IC2 on the axle midpoint, the encoder slots EC1/EC2 at
  y = -/+6.9, the wheel notches on both sides, the fan hole at x = 17.5 with the fan connector M3
  and the buzzer BZ1 beside it, the 3V3 buck IC7/L3 front right, the DIP switch SW1 and the SWD
  header P1 at the sides.
- **Rear** (x below -5 mm): the current amplifiers IC3/IC4 and the shunts R31-R33 behind the axle,
  the fan driver IC6, the boost U1/L2, the bridge IC5 with the motor connectors M1/M2 at the rear
  corners, the battery connector J1 with the switch SW4/Q6 rear right, the USB-C receptacle U2 on
  the rear edge.
- **Screw holes** H1-H4 (2.4 mm, M2) at (2.5, +/-11.75) and (-15.5, +/-19.25).

Resistors, ceramic capacitors and the LEDs D4/D5 use KiCad's generic footprints, each centred on
its pads' positions in the Altium footprint: the routing lands on the same pad centres, up to
0.12 mm from a pad's centre where the KiCad pad pitch differs (0805/1206 capacitors). The
teardrops of the Altium design are plain copper zones (priorities 100 and up, above every pour):
KiCad 10 does not save a teardrop zone's UUID and orders zones by UUID, so a board with teardrop
zones changes on every save.

Copper of the changes C1 and C2 (KiCad coordinates, as in `rework.py`):

- **VBAT pin on 3V3 (C1).** IC1 pad 1 with C8 and C9 sits on a short top-layer cluster that reaches
  the In2.Cu 3V3 plane through the via at (155.105, 75.582); a 0.2 mm top-layer bridge joins pad 1
  to pad 68 (VDD) across the package corner, 0.2 mm from pads 2 and 67.
- **VCORE (C2).** L1, C3 and C4 feed VFBSMPS (pad 7) on the top layer. A 0.5 mm In2.Cu route
  carries the core current from the via beside C3/C4 to the three VCAP pins: down to a via on the
  VCAP3 (pad 66, C5) track, under the package along y = 77.06 between the exposed pad's ground
  vias, with a branch to VCAP2's via pair (pad 49, C6), and 0.4 mm on the last 2.7 mm to a via on
  the VCAP1 (pad 33, C7) track. It runs as a tree, so the 3V3 plane flows around it. The VCAP3 via
  keeps 0.13 mm from the bottom-layer Encoder_Right_CSn track, the widest spot between the pad 66
  and pad 68 tracks.

## Known faults

The circuit passes every circuit-level gate (build, warnings, ERC, LVS, previous, parts, the
power-tree and firmware tests) except one bench, which no change on this board can satisfy:

| Check (gate) | Fault | Requirement | Why it stays |
|---|---|---|---|
| `main_peripherals` `usb_c_sbu_open` (test) | SBU1/SBU2 carry 3V3 through Q7 and F1 for the Bluetooth module (M6) | Type-C R2.0 section 4.3, Table 4-28: SBU open or at least 950 kOhm to GND, in every state | The Bluetooth module (MicrasBluetoothModule) takes its supply from SBU and leaves VBUS and CC open, so the board cannot tell it from a cable before powering it. Q7 removes the supply whenever a USB host powers VBUS; it remains while a host debounces the attach (VBUS is applied only after Rd is seen, Type-C R2.0 4.5.2.2.8.2), on an unpowered host and on an accessory. Compliance needs the module to change (its own connector, or power from VBUS). |

The layout still holds the previous revision's placement and copper; the circuit's new parts and
connections are not placed or routed yet. The layout gates (`layout-check`, `drc`, `dfm`) and the
layout tests fail on these:

| Check (gate) | Cause | Fix |
|---|---|---|
| `unconnected_items` (drc) | the 35 new parts (C58, C59, C61-C76, D8-D12, FB1, Q7, R43-R49, U4-U6) sit off the board, and the new nets (VSYS, VDDA, SWD_VDD, Battery_Voltage, USB_VBUS_Sense, the wall gate drive nets, BAT_SW_DRIVE, SBU_SW, the mux ILM/SS) have no copper | place and route them; see the placement notes below |
| `shorting_items`, `clearance`, `hole_clearance`, `solder_mask_bridge`, `pth_inside_courtyard` (drc); copper clearance (dfm) | previous copper on pads whose net changed (C60 pad 2 on a 3V3 track, IC6 pad 12, U1 pad 11 on VBAT, IC7 pads 5/7 and C52/C53 on VBAT, C10/C11/IC1 pad 16 on 3V3, C18/C19/D1/D2 VDD on 3V3, F1 pad 1 on 3V3, SW4 pad 3 on the gate track, R11/R15/R19/R23 pad 1 on the gate tracks); the 1206 footprints of R3/R13/R17/R21/R25 reaching neighbouring copper (R13 onto C26, R17 onto the LED_Red track and via); P1 pad 5 on GND copper and vias, inside the R13/C26 courtyards | reroute those nets; move the parts clear |
| orphaned copper | six track/via items on `Motor_Enable`, a net the circuit no longer has (`pcb apply`: "orphaned_net") | put them on `Motors_Enable` or reroute |
| `lib_footprint_mismatch` (drc) | 42 footprints differ from their packages: the packages gained courtyards, paste fixes, edge-clear silkscreen (W1-W4), SW1 texts, and the EncoderSlot pads moved | update the footprints from the packages (keeps position and nets) |
| `test_every_assembled_footprint_has_a_courtyard[main]` (pytest) | the board's copies of the Altium-library footprints predate their packages' F.CrtYd courtyards | as above |
| `test_main_layout_has_every_spec_feature`, `test_main_layout_matches_the_spec` (pytest), `micras-pcb mech --check` (layout-check) | Edge.Cuts still has the 0.9 x 5.1 mm encoder slot rectangles; `spec/main.toml` asks for 1.0 x 5.8 mm slots with R0.5 ends | redraw both slots: straight sides x = centre +/- 0.5 mm from y 111.1036 to 115.9036, R0.5 end arcs through y 110.6036 and 116.4036; centres (155.401105, 113.5036) for EC1 and (141.601105, 113.5036) for EC2 |
| `test_encoder_slots_take_the_encoder_tab` (pytest) | as above | as above |
| `test_decoupling_sits_at_its_pin[main]` (pytest) | C15 sits 5.0 mm from IC1 pad 51 (VDD) and C6 3.7 mm from pad 49 (VCAP2); C67/C68 (IC3/IC4 VCC) are not placed. The board's reading of "close" is 3 mm | move C15 and C6; place C67 at IC3 pin 6, C68 at IC4 pin 6 |
| `invalid_outline` (drc) | Edge.Cuts has six 1-10 nm lines between arcs and lines of the outline, left by the Altium conversion | delete the six lines (the outline geometry is unchanged) |
| `tracks_crossing` (drc), `track_dangling` (drc, warning) | zero-length track segments from the conversion (GND, 3V3, USBD_N, USBD_P, Boot) | delete the zero-length segments |
| `copper_edge_clearance` (drc); board-edge-to-copper (dfm) | U2's GND pads A1B12 and B1A12 sit 0.175 and 0.190 mm from the USB-C peg holes, below JLCPCB's 0.2 mm | trim the two pads, or move the peg holes per the GT-USB-7010ASV drawing |
| `courtyards_overlap` (drc) | KiCad's generic R/C courtyards are wider than the previous footprints' spacing (C44-C47, C48-C51, R39/R40, C3/C4), and the 1206 resistors' courtyards | space the parts |
| copper feature width (dfm), `copper_sliver` (drc, warning) | teardrop outlines overrunning their tracks | trim the teardrop outlines |
| `silk_edge_clearance`, `silk_overlap`, `silk_over_copper`, `text_height`, `text_thickness` (drc, warnings) | the previous layout's reference texts (0.5 mm high) and package silkscreen, until the footprints are updated | update the footprints, move and enlarge the texts |
| `padstack` (drc, warning) | U2, Q6 and SW4 pads with a -100 mm paste margin, in the board's copies of the footprints (the packages take their paste from the drawn apertures only) | update the footprints |

Placement notes for the new parts:

- **Power mux U4** (VQFN-HR 2 x 2.5 mm) with R46 (ILM) and C61 (SS) at its pins, C62 at IN1, C63
  at IN2: between J1/U2 and the buck IC7, on the VBAT and +5V pours; VSYS is a new, wide net from
  U4 OUT (pads 1, 8) to IC7 pins 5/7 and C52/C53, which leave VBAT.
- **U5** (SC-70-6) with C64 next to P1: P1 pin 1 becomes SWD_VDD, U5 VOUT/CE on 3V3.
- **P1** is a 1x05 header (pads along the footprint's +X from pad 1, pad 5 = NRST, 2.54 mm
  beyond pad 4). Pad 5 lands on R13/C26 and GND copper at the board's left edge: shift P1 by
  1.27 mm towards D3 and move C26/R13 (or D3), then route Reset to pad 5.
- **R43** (gate series) between SW4 pad 3 and Q6's gate track, **C58** from Q6 gate to Q6 drain
  (GND), next to Q6.
- **R44/R45/C59** (battery divider) near IC1 pad 24 (PA5), R44 fed from VBAT.
- **FB1** in the VDDA feed of IC1 pad 16, C10/C11 stay at the pin on the VDDA side.
- **U6** (SOT-23-6) at U2's D+/D- pins, rail pin to 3V3; **D8** (SOD-882) at U2's VBUS pins;
  **R47/R48** from VBUS to IC1 pad 10 (PH0); **Q7** (SOT-23) between 3V3 and F1 pad 1.
- **R49** on Motors_Enable at IC1 pad 45 / R35; U1 pad 11 leaves VBAT for Motors_Enable.
- **C65/C66** (0805) within 3 mm of IC5 VSA/VSB (pins 17, 14); **C67/C68** at IC3/IC4 pin 6;
  **C69/C70** at EC1 pad 5, **C71/C72** at EC2 pad 5.
- **C73-C76** (0402) and **D9-D12** (SOD-323) between each R11/R15/R19/R23 and its Q2-Q5 gate:
  R1x pad 1 drives the capacitor, and the gate net is the capacitor's other pad, R12/R16/R20/
  R24 and the clamp's cathode.
- Footprints of a new size, sitting where the previous ones were: R3, R13, R17, R21, R25 (1206),
  C56 (0805), P1 (1x05); the EncoderSlot pads are at x = +/-1.21 mm once the footprints are
  updated.

Requirements without a check, and why:

- Boost current limit against J1 (m3): no source bounds the motors' peak current. R37 56 kOhm
  (13.3 A typ) keeps the limit above it; a lower limit could cut the acceleration current.
- L2 saturation against the boost current limit: the XAL6030-102 package does not know whether
  its 23 A is the saturation current (TODO in its docstring).
- L6981 slope compensation (Eq. 38): with Eq. 13 read literally, ST's own 22 uH evaluation set-up
  fails it too, so the reading is not reliable enough for a gate.
- Capacitor voltage derating: the ratings are checked against the worst-case net voltage
  (`capacitor_voltage_ratings`); no sourced derating factor is applied. C36 (16 V on 12.6 V) and
  C37 (25 V on 19.4 V) are within their ratings: neither USB nor the probe can lift VBAT or +20V
  (the over-voltage of review section 2.3 needs a back-fed VBAT).
- PC14 as an encoder chip select (m8): with VBAT on 3V3 the review finds it acceptable (keep the
  cable within 30 pF); moving it needs a firmware change.
- Bluetooth module RESETB pull-up and PA11 pull-up (m17): the first is on the module, the second
  a firmware setting.
- High-side battery switch (m6): the low-side switch works; the battery reading is valid while it
  is on.

## Open items

- [ ] Solder mask colour and surface finish: not recorded in the Altium design; the board uses
      the 4-layer defaults until they are confirmed.
- [ ] Check every part's placement rotation in JLCPCB's assembly preview, then set
      `rotation_verified = true` in `parts/jlc.toml`.
- [ ] Place and route the new parts and fix the layout faults above.
- [ ] Bench: confirm the L6981C33 does not lift VSYS above the probe's 3.3 V in the SWD probe mode
      (the datasheet is silent on a back-powered output; review C3), and the SBU supply turning off
      with a USB host attached.
