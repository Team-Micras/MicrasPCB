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
| [`main.zen`](main.zen) | root | IC1 (STM32H725RGV6) and its supply network (C1-C17, L1, FB1), SWD connector P1, test points, M2 screw holes H1-H4, board stackup and rules |
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
| [`layout/`](layout) | | KiCad project; the `.kicad_pcb` holds placement and routing; `fixes.py` and `router.py` place and route the review fixes on it, `refine.py` the owner's layout decisions |
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

## SWD connector

P1 is a JST SH 5-pin side-entry header (SM05B-SRSS-TB, 1.00 mm pitch) on the left board edge,
its mating face outwards, so the probe cable (a JST SHR-05V-S housing) leaves the board
sideways. Pin 1 is the contact nearest the front of the robot, marked by the footprint's tick
and a "1" on the silkscreen.

| Pin | Net | Probe |
|---|---|---|
| 1 | SWD_VDD | the probe's 3.3 V (an ST-Link V2 clone drives it), into 3V3 through U5 |
| 2 | GND | GND |
| 3 | SWDIO | SWDIO (PA13) |
| 4 | SWCLK | SWCLK (PA14) |
| 5 | Reset | NRST, so the probe can connect under reset |

The two reinforcement pads are on GND.

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
[`layout/fixes.py`](layout/fixes.py) then places and routes the parts and connections the review
fixes add, on the layout as the footprint update leaves it, and runs once: it redraws the
encoder slots, places the new parts, removes the copper the changed nets contradict, spaces the
parts whose updated courtyards overlap, and routes what remains unconnected with
[`layout/router.py`](layout/router.py), a small grid router (0.05 mm grid, F.Cu/B.Cu, 0.12 mm
from other copper, deterministic). [`layout/refine.py`](layout/refine.py) runs once after it with
the owner's layout decisions: it clears the connector courtyard overlaps, places the JST SH
connector P1, brings C15 to IC1 pad 51 and puts the reference designators on the silkscreen.

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
  connector P1 at the sides.
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

The review fixes in the layout (KiCad coordinates):

- **Power mux U4** between J1/U2 and the buck IC7, R46 (ILM) and C61 (SS) at its pins, C62 at
  IN1, C63 at IN2. VSYS leaves U4 OUT through vias to a B.Cu pour that reaches IC7 pins 5/7 and
  C52/C53; an In2.Cu finger of the VBAT plane feeds IN1.
- **Battery divider**: R45 and C59 between the LED_ARGB and Button vias above IC1's top corner,
  R44 next to C18's VBAT pad; PA5 (pin 24) leaves IC1 in a 0.15 mm track beside pin 23's.
- **Wall_Sensor_2** (IC1 pin 25) runs from between W2's pads round R17 to the board's top edge,
  along it past the LEDs D1/D2/D5, and down to W3 and R22 (47 mm, top layer): the battery
  divider's track to VBAT closes the way past IC1's top corner it took before.
- **NRST and PH0**: NRST (pin 12) drops to B.Cu on the axis of the unused pin 11, PH0 (pin 10,
  USB_VBUS_Sense) a pitch further out; Current_Sensor_Left's B.Cu run passes between PH0's via and
  pin 9's 3V3 via in 0.15 mm.
- **SWD connector P1** at (126.48, 90.5), rotated -90 degrees: the mating face 0.4 mm and the
  reinforcement pads 0.22 mm inside the left board edge, the contacts at x = 128.48 (pin 1 at
  y = 88.5). The fan connector M3 sits 1.95 mm inwards of the Altium position to leave P1 room;
  U5/C64 sit below P1, R13 above it, D3 next to R1/R2. SWDIO runs to P1 on B.Cu from a via under
  IC1 pad 48.
- **Wall sensor drive** C73-C76/D9-D12 between each R11/R15/R19/R23 and its Q2-Q5; the 1206
  resistors R3/R13/R17/R21/R25 on their previous centres.
- **Motors_Enable** to U1 pad 11 crosses the rear half on B.Cu (R49 by R35); C65/C66 at IC5,
  C67/C68 at IC3/IC4 pin 6, C69/C70 at EC1, C71/C72 at EC2, U6/D8 at U2, Q7/F1 for SBU, R43/C58
  by Q6, FB1 in IC1's VDDA feed.
- **C6** (VCAP2) sits 2.8 mm from IC1 pin 49 and takes VCORE from the In2.Cu VCORE route through
  its via at (144.437, 82.552); C14/C17 (pin 35) lie across, clear of IC1's courtyard.
- **C15** (IC1 pad 51, VDD) stands 1.8 mm from the pad, in the strip under pads 46-51 between the
  USB pair and SWCLK: its 3V3 pad on pad 51's via, its GND pad on a via of its own.
- **Courtyards**: no two courtyards overlap. Against the Altium positions, the parts below moved
  to clear them (KiCad mm; robot frame in brackets, x forward, y left):

  | Part | KiCad x, y (from) | KiCad x, y (to) | Robot x, y (to) |
  |---|---|---|---|
  | M1 left motor connector | 138.001, 146.575 | 139.201, 146.575 | -33.071, 9.300 |
  | M2 right motor connector | 160.501, 146.575 | 159.951, 146.575 | -33.071, -11.450 |
  | SW4 battery switch | 168.988, 143.344 | 169.078, 143.564 | -30.060, -20.577 |
  | M3 fan connector | 132.473, 90.318 | 134.423, 90.318 | 23.186, 14.078 |
  | P1 SWD connector (JST SH) | | 126.480, 90.500 | 23.004, 22.021 |
  | C36 VBAT bulk | 163.099, 138.701 | 162.669, 138.701 | -25.197, -14.168 |
  | C37 +20V bulk | 141.128, 140.162 | 140.731, 140.162 | -26.658, 7.770 |
  | C38 L6205 VS 100 nF | 136.436, 140.606 | 136.190, 144.750 | -31.246, 12.311 |

  C23, R6 and R7 moved 0.12-0.15 mm sideways. J1, U2 and IC5 keep their positions; IC5's pad 10
  is 0.2 mm (the copper-to-edge rule) from the rear-left corner arc. MicrasHardware takes the
  board's components from the board STEP (`make review`), so it must re-export
  `ref/board.step` and `ref/board_boxes.json` and re-run `tools/check_layout.py`.
- **Clean-up**: the outline's six 1-10 nm lines, the zero-length tracks, stubs left by the changed
  nets, and teardrops that left copper slivers against a twin are gone. U2's outer GND pads are
  1.19 mm long, 0.22 mm from the USB-C peg holes.
- **Silkscreen**: every reference designator is on F.Silkscreen, 0.6 mm high with a 0.15 mm stroke,
  clear of pads, of other silkscreen and of the board edge, off the part bodies wherever a spot
  allows (C64's sits on U5). The 0.15 mm stroke is the one the owner found legible on a
  fabricated board (0.154 mm at 0.5 mm high); KiCad's stroke font caps the stroke at a quarter of
  the text size, so 0.6 mm is the smallest size that carries it. The board allows 0.5 mm / 0.15 mm text
  (`main.zen` Silkscreen, `rules/kicad-severities.toml`), an accepted trade-off against JLCPCB's
  legibility guarantee from 1.0 mm high and 0.153 mm stroke.

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

The layout passes every layout gate: copper, connections, courtyards, DFM, decoupling at the pin,
silkscreen text size. These findings stay:

| Check (gate) | Fault | Why it stays |
|---|---|---|
| `silk_overlap`, `silk_over_copper` (drc, warnings) | package artwork on its own outline (the W1-W4 "C"/"E" and SW1 "ON" marks), outlines of neighbouring parts touching (D9/R14, D11/D12, D4/R4, D5/R5, R13/W1, R17/W2), and the board artwork (the slogans, arcs and circles) under parts (C58, C63, C65/C66, C69/C70, D3, M3, Q7, R48, R49, the test points) | cosmetic: JLCPCB clips silkscreen at pads, and no reference designator is among them |
| `silk_edge_clearance` (drc, warning) | SW4's outline crosses the rear notch's edge | the battery switch overhangs the board edge by design, its lever outwards |
| Wall_Sensor_2's route (no gate) | 47 mm along the top edge instead of the short way past IC1's top corner | pins 23 (Wall_Sensor_3), 24 (PA5) and 25 (Wall_Sensor_2) escape side by side and both wall sensor lines run to the right, so the battery divider on PA5 can only be reached across one of them. A via in the 0.4 mm pitch fan-out does not fit (0.45 / 0.3 mm vias, 0.2 mm hole to track), and B.Cu around IC1's top corner is filled by the Button, LED_ARGB, Switch_0-3, Reset and WALL1_LED_A runs, so the crossing needs those re-layered first |
| U6's branch (no gate) | the USB ESD array U6 sits beside the receptacle on branches of D+ (about 18 mm, three vias) and D- (about 7 mm, two vias), not in line | an in-line (flow-through) U6 needs room between U2 and R8/R9 that the boost output capacitors C48-C51, F1, D8 and C36 take; the branch is far shorter than a wavelength at full speed (12 Mbit/s). The pair from IC1 to R8/R9 is the Altium design's coupled pair (0.2248 / 0.127 mm, 90 Ohm on this stack), 94.5 and 95.8 mm long |

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
- [ ] Wall_Sensor_2's short route past IC1's top corner: re-layer the B.Cu runs there (see
      [Known faults](#known-faults)) and hop PA5 or Wall_Sensor_2, or keep the top-edge route.
- [ ] U6 in line with D+/D- at the receptacle: needs space next to U2 (see
      [Known faults](#known-faults)).
- [ ] MicrasHardware: re-export `ref/board.step` and `ref/board_boxes.json` from this board and
      re-run `tools/check_layout.py` (M1, M2, M3, SW4 and P1 moved, see [Layout](#layout)); keep
      the left edge clear for the SWD cable at x = 23 mm.
- [ ] Bench: confirm the L6981C33 does not lift VSYS above the probe's 3.3 V in the SWD probe mode
      (the datasheet is silent on a back-powered output; review C3), and the SBU supply turning off
      with a USB host attached.
