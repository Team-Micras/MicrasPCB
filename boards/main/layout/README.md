# Main board

The Micras micromouse main board: a 50 x 90 mm, 4-layer, 1.04 mm board. It carries the STM32H725RGV6 controller, the battery input and power conversion, the
two locomotion motor bridges and the fan driver, the IMU, four wall sensors, the slots for the
two encoder boards, and the user interface.

The circuit is the MicrasMainBoard Altium design's, with the findings of its design review
(`hw_debug/schematic_review.md`) fixed. Parts of that design keep their designators, and parts the
fixes add continue each series (C58-C78, D8-D13, FB1, Q7, R43-R55, U4-U7). `micras-pcb previous
compare main` checks the netlist and its net names against that design's connectivity
([`previous/board.json`](../previous/board.json)) plus the changes declared in
[`changes.toml`](../changes.toml), one per review item.

## Files

The board files are in `boards/main/` (this README sits in its `layout/` folder);
`spec/` is at the repository root.

| File | Sheet instance | Contents |
|---|---|---|
| [`main.zen`](../main.zen) | root | IC1 (STM32H725RGV6) and its supply network (C1-C17, L1, FB1), SWD connector P1, test points, M2 screw holes H1-H4, board stackup and rules |
| [`Regulators.zen`](../Regulators.zen) | `REGULATORS` | J1 battery connector, battery switch SW4/Q6, battery measurement, power mux U4, 3V3 buck IC7, 20 V boost U1, SWD probe ideal diode U5 |
| [`Drivers.zen`](../Drivers.zen) | `DRIVERS` | IC5 (L6205D) bridges for M1/M2 with shunts R32/R33, IC6 (STSPIN958) fan driver for M3 with shunt R31 |
| [`Sensors.zen`](../Sensors.zen) | `SENSORS` | IC2 (LSM6DSV) IMU, IC3/IC4 (TSC2020) current amplifiers, wall sensors W1-W4 with Q2-Q5, encoder slots EC1/EC2 |
| [`Peripherals.zen`](../Peripherals.zen) | `PERIPHERALS` | SW1 DIP switch, SW2/SW3/SW5 buttons, BZ1 buzzer, D1/D2 addressable LEDs, D4/D5 LEDs, U2 USB-C with its ESD protection and VBUS sensing, the SBU supply for the Bluetooth module and its signature detector U7 |
| [`passives.zen`](../passives.zen) | | value, package, rating and part number of every resistor, ceramic capacitor, LED and ferrite line |
| [`changes.toml`](../changes.toml) | | connectivity, net-name and part-number changes against the previous revision, each with its review item |
| [`erc.toml`](../erc.toml) | | nets supplied from off the board (VBAT, GND, +5V, SWD_VDD) or through a passive part (VDDA), the PWR_FLAG role for ERC |
| [`firmware.toml`](../firmware.toml) | | the firmware's pin map, supply setting, battery channel and drive duties, from MicrasFirmware (`micras-pcb firmware snapshot`) |
| [`firmware_changes.toml`](../firmware_changes.toml) | | the firmware changes this board needs (see [Firmware changes](#firmware-changes)) |
| [`test/`](../test) | | `pcb test` benches of the board's circuit: MCU, power, drivers, peripherals |
| [`layout/`](.) | | this folder: the KiCad project; the `.kicad_pcb` holds placement and routing; `fixes.py` and `router.py` place and route the review fixes on it, `refine.py` and `usb_wall.py` the owner's layout decisions, `finish.py` the previous revision's pour and teardrop settings on the result, `rail_silk.py` U6's rail capacitor and the designator size, `octilinear.py` every track at 0/45/90 degrees, `swd_top.py` the top-entry SWD connector |
| [`previous/`](../previous) | | the previous revision's connectivity snapshot, and the scripts that build the layout from that revision (`transfer_layout.py`, `rework.py`) |
| [`spec/main.toml`](../../../spec/main.toml) | | mechanical interface: thickness, axle origin, extents, screw holes, encoder slots, USB-C peg holes, fan hole, wheel notches |

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
| `+5V` | USB-C VBUS | 4.4-5.25 V | mux U4 IN2, VBUS divider R47/R48, TVS D8 |
| `VSYS` | mux U4: the higher of VBAT and +5V | 4.4-12.6 V | buck IC7 only |
| `3V3` | buck IC7 (L6981C33), or the SWD probe through U5 | 3.3 V | MCU, IMU, amplifiers, sensors, encoders, buzzer, logic of the drivers, the Bluetooth module on SBU (while its signature is on CC), U6's rail |
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
  regulator on this pin). VBAT stays at 0 V, and the motors cannot run. The buck's high-side body
  diode (DS13554 Figure 19) lifts VSYS to 3V3 less a diode drop, about 2.6-2.9 V, as the owner
  measured on the previous board; this is known and accepted:
  - U4 keeps VSYS from VBAT and +5V. With neither input above its UVLO (2.4-2.8 V, SLVSEA3F
    Table 7.5) its output is Hi-Z (Table 9-3), and each channel is a back-to-back FET pair with
    opposed body diodes (Figure 9-2) that leaks at most 1 uA at 25 C, 5 uA up to 85 C, for
    |VINx - VOUT| <= 5 V (Table 7.5, ILK). Into the VBAT divider R44/R45 (127 kOhm) and the VBUS
    divider R47/R48 (115 kOhm) that is at most 0.13 V at 25 C and 0.64 V at 85 C, below every
    UVLO there (the boost's VIN UVLO rises at 2.6 V typical, SLVSDA7E section 7.5).
  - VSYS carries only C52/C53 (11 uF) besides U4 and IC7. The probe charges them once, about
    30 uC on top of the 237 uC of 3V3's 71.8 uF, through IC7's diode while 3V3 ramps (U5 has no
    current limit; the probe's regulator sets the ramp). After that it supplies only U4's
    leakage and IC7's input current, microamps.
  - IC7 is outside its datasheet in this state: SW sits above VIN + 0.3 V (DS13554 Table 3,
    absolute maximum) while the body diode conducts, and VSYS is below the 3.5 V minimum input
    but within the 2.3-3.3 V spread of the VCC UVLO rising threshold (Table 6), with EN on VSYS.
    The bench item under [Open items](#open-items) checks that it stays off.
  `tests/test_power_tree.py::test_debug_supply_back_feed_stops_at_the_mux` follows every path
  that conducts from the probe and the USB VBUS (regulators both ways where they have a reverse
  path, ORing parts forwards, inductors and ferrites) and fails if one reaches another off-board
  supply.

With two sources at once each one blocks the other: U4 selects the battery over USB, U5 conducts
only while the probe's supply is above 3V3, and the L6981C33 neither sinks current nor switches
while 3V3 is above its LCM threshold, 1.8 % over its set point (DS13554 sections 6.4.1, 6.6.1). `tests/test_power_tree.py`
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

## USB-C and the Bluetooth module

U2 is a USB 2.0 device port (Rd 5.1 kOhm on CC1/CC2, VBUS into the mux U4) and the socket of the
Bluetooth module (`boards/bluetooth`), whose HM-19 talks to UART4 on the D+/D- contacts (PA12 TX,
PA11 RX) and takes its supply from SBU. D+/D- run on plain copper from U2 to the MCU: the PHY has
the D+ pull-up and the driver impedance (DS13311 Table 118 note 2). U6 (USBLC6-2SC6) clamps both
lines at the receptacle, in line: each line enters U6 on one pad and leaves on its twin (pads 6/1
for D+, 4/3 for D-; DocID 11265 Rev 5, Figure 18). C79 100 nF bypasses its 3V3 rail pin to GND
(Figure 18: CBUS = 100 nF). PA11 idles high with the module unplugged
through the firmware's pull-up (see [Firmware changes](#firmware-changes)).

SBU carries 3V3 only while the module is plugged in: USB Type-C R2.0 section 4.3 (Table 4-28)
wants SBU open for every other partner. The module joins its CC contacts to its D+ contacts, so
UART4 TX, idle high, holds U2's CC1 at 2.87 V or more; a Type-C source makes at most 2.04 V across
Rd (Table 4-36). The detector in `Peripherals.zen` tells them apart:

| Part | Role |
|---|---|
| R50 10 kOhm, D13 BAT54H, C77 1 uF, R51 1 MOhm | peak hold of CC1 (SBU_DET), tau 1 s, through the UART's low bits |
| R52 100 kOhm / R53 200 kOhm, R54 1 MOhm | reference: two thirds of 3V3, with hysteresis |
| U7 TLV7041, C78 100 nF | comparator: open drain, low above the reference; high impedance during its power-on reset |
| R55 100 kOhm, Q7 AO3401A, F1 KASML010 | Q7 off by default (gate pulled to 3V3); U7 pulls the gate low, and 3V3 reaches SBU through F1 |

The bench `main_peripherals sbu_signature_detector` computes the thresholds from the resistor
values: on at 2.24-2.29 V, off at 2.04-2.08 V, against 2.04 V from a source and 2.39-2.60 V from
the module (idle, and receiving 0x00 bytes); `usb_c_sbu_open` checks the topology.

## SWD connector

P1 is a JST SH 5-pin top-entry header (BM05B-SRSS-TB, 1.00 mm pitch) by the left board edge,
where the previous revision had its upright 2.54 mm pin header, so the probe cable (a JST
SHR-05V-S housing) plugs in from above and fits the chassis as that header's did. Its contacts
face the board's inside; pin 1 is the contact nearest the rear of the robot, marked by the
footprint's step and a "1" on the silkscreen.

| Pin | Net | Probe |
|---|---|---|
| 1 | SWD_VDD | the probe's 3.3 V (an ST-Link V2 clone drives it), into 3V3 through U5 |
| 2 | GND | GND |
| 3 | SWDIO | SWDIO (PA13) |
| 4 | SWCLK | SWCLK (PA14) |
| 5 | Reset | NRST, so the probe can connect under reset |

The two reinforcement pads are on GND.

## Firmware changes

The board needs three changes in MicrasFirmware, declared in
[`firmware_changes.toml`](../firmware_changes.toml) (the firmware tests apply them):

- **Battery voltage (C1)**: read PA5 (ADC1/ADC2 channel 19, `ADCx_INP19`, label
  `Battery_Voltage`), analog with no pull, and scale by 127 / 27 = 4.7037, instead of the
  internal VBAT/4 channel on ADC3: the VBAT pin is on 3V3. PA5 stops being `Encoder_Left_ABI_I`
  (`S_TIM2_ETR` with `GPIO_PULLUP` in `cube/micras_v0.ioc`): the encoder's index output is not
  connected, and a 30-50 kOhm pull (DS13311 Table 55) would load the divider's 21 kOhm tap.
- **VBUS sensing (M11)**: configure PH0 (`PH0-OSC_IN`) as a GPIO input, no pull, label
  `USB_VBUS_Sense`; a USB device stack reads it.
- **UART4 RX pull-up (m17)**: PA11 (`UART4_RX`) with `GPIO_PULLUP`, so the receiver idles high
  while the Bluetooth module is unplugged; a USB device stack takes the pin without the pull.

Nothing else changes for the firmware: the boost follows `Motors_Enable`, which the firmware
already drives before every run, and the SBU supply follows UART4 TX's idle level, which the
firmware sets from `MX_UART4_Init` at boot.

## Board

4 copper layers, 1 oz outer and 0.5 oz inner copper, 0.2104 mm prepreg (Dk 4.4) and 0.5 mm core
(Dk 4.48), from the Altium layer stack: 1.0212 mm of copper and dielectric. The KiCad stackup adds
Zener's fixed 10 um solder mask a side, 1.0412 mm (`spec/main.toml`); Altium's 15.24 um resist
makes the same stack 1.0517 mm. The board is ordered as JLCPCB's 1.0 mm 4-layer board. Design
rules: 0.1 mm clearance, 0.254 mm default track, 0.45 / 0.3 mm vias (0.5 / 0.3 and 0.8 / 0.4 mm
also used), 0.2 mm copper to edge, 0.02 mm solder mask expansion, all from the Altium design
rules; `rules/jlcpcb.kicad_dru` adds JLCPCB's limits on top. The drill and placement origin of the
fab outputs is the Altium origin, the rear edge centre at KiCad (148.501075, 150.00362).
Finish: ENIG, black solder mask, white silkscreen (`main.zen` Stackup).

## Layout

The layout is the Altium MicrasMainBoard.PcbDoc's, in the same KiCad coordinates: MicrasHardware
and the firmware place the board by them, with the wheel-axle midpoint (between the encoder slots)
at KiCad (148.5011, 113.5036). [`previous/transfer_layout.py`](../previous/transfer_layout.py)
builds it from the KiCad conversion of that PCB and [`previous/rework.py`](../previous/rework.py)
adds the copper of the declared changes C1 and C2; running the script again changes nothing.
[`layout/fixes.py`](fixes.py) then places and routes the parts and connections the review
fixes add, on the layout as the footprint update leaves it, and runs once: it redraws the
encoder slots, places the new parts, removes the copper the changed nets contradict, spaces the
parts whose updated courtyards overlap, and routes what remains unconnected with
[`layout/router.py`](router.py), a small grid router (0.05 mm grid, F.Cu/B.Cu, 0.12 mm
from other copper, deterministic) that draws as the hand-routed board: tracks at 0, 45 and 90
degrees, few corners, 45 degree chamfers where there is room, pads entered along their axes. [`layout/refine.py`](refine.py) runs once after it with
the owner's layout decisions: it clears the connector courtyard overlaps, places the JST SH
connector P1, brings C15 to IC1 pad 51 and puts the reference designators on the silkscreen.
[`layout/usb_wall.py`](usb_wall.py) then puts U6 in line with D+/D-, lays out the SBU
detector and gives Wall_Sensor_2 its short path over IC1's top corner, and
[`layout/finish.py`](finish.py) gives the result the zone and mask settings that
`previous/transfer_layout.py` gives a fresh transfer, clears what the 2512 shunts' pads touch and
removes the teardrops that are left on their own or make copper slivers;
[`layout/rail_silk.py`](rail_silk.py) places U6's rail capacitor C79 and sets every
reference designator to 0.5 mm / 0.125 mm, and [`layout/octilinear.py`](octilinear.py) redraws
every track the earlier scripts left at another angle: each such connection is ripped up back to
its pads, vias and junctions and routed again between the same copper (or, where the router finds
no clean path, given a two- or three-segment octilinear path), and [`layout/swd_top.py`](swd_top.py)
puts the top-entry SWD connector P1 where the side-entry one was and routes its nets, and
[`layout/wall_inside.py`](wall_inside.py) puts the bare wall sensors fully on the board (below).
Each runs once.

Routing rule: every track is a straight segment at a multiple of 45 degrees, with no arcs and no
corner under 90 degrees outside a pad or via, as on the Altium board
(`tests/test_layout.py::test_tracks_are_octilinear_without_acute_corners`).

| Layer | Use |
|---|---|
| F.Cu | every part (the board is single-sided), signal routing, power pours (VBAT, +20V, GND_BAT, 3V3, GND, fan outputs) |
| In1.Cu | solid GND plane |
| In2.Cu | power planes: 3V3 under the MCU and most of the front half; VBAT, +20V and +5V behind it, VBAT reaching forward on the right to the buck IC7; the VCORE route |
| B.Cu | signal routing |

Where things are, in the robot frame (x forward, y left, from the axle midpoint; `spec/main.toml`):

- **Front** (x 30-54 mm): IC1 at x = 37, the wall sensors W1-W4 at the front corners (fully on
  the board), the LEDs
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
current-sense shunts R31-R33 keep the Altium land pattern and model
([`components/micras/R2512`](../../../components/micras/R2512): 1.45 x 3.45 mm pads). D4 and D5 carry
KiCad's LED model scaled to their datasheet heights, 0.80 mm (NCD0603Y2) and 0.60 mm (KT-0603R),
so the 3D export has the fitted parts' height.

Zones, as `previous/transfer_layout.py` sets them from the Altium polygons and rules:

- The teardrops of the Altium design are plain copper zones (priorities 100 and up, above every
  pour): KiCad 10 does not save a teardrop zone's UUID and orders zones by UUID, so a board with
  teardrop zones changes on every save. They fill with a 0.1 mm minimum width, JLCPCB's minimum
  copper feature, which leaves out only their thinnest cusps.
- The pours drop copper narrower than 0.1 mm (the Altium polygons' neck width). In1.Cu and
  In2.Cu join through-hole pads with thermal reliefs, four 0.254 mm spokes across a 0.254 mm gap,
  and vias solidly; F.Cu and B.Cu join everything solidly (Altium rules PolygonConnect and
  PolygonConnect_Top/BottomLayer).
- In1.Cu and In2.Cu stay 1.559 mm and 2.074 mm from each screw hole's centre, as the Altium pours
  do: a copper-pour keepout per hole and layer.
- U2's peg-hole keepouts cover all four copper layers.

The Edge.Cuts outline is the Altium one without its six duplicated vertices (lines of 1-10 nm,
which KiCad reads as a malformed outline); the lines next to them meet within 10 nm of where they
did.

The review fixes in the layout (KiCad coordinates):

- **Power mux U4** between J1/U2 and the buck IC7, R46 (ILM) and C61 (SS) at its pins, C62 at
  IN1, C63 at IN2. VSYS leaves U4 OUT through vias to a B.Cu pour that reaches IC7 pins 5/7 and
  C52/C53; an In2.Cu finger of the VBAT plane feeds IN1.
- **IC1's top corner**: pins 23 (Wall_Sensor_3), 24 (PA5) and 25 (Wall_Sensor_2) escape side by
  side, and both wall-sensor lines run over the corner to the right. Wall_Sensor_2 steps north
  between Wall_Sensor_1 and PA5's escape, runs up IC1's top-left side outside PA5 and
  Wall_Sensor_3, over the corner under the Button and Reset vias, down the top-right side between
  Wall_Sensor_3 and R21, and between W3's pads 1 and 2 to pad 4: 30 mm to W3 and R22, on F.Cu.
  PA5's 0.15 mm track runs up between the two wall-sensor lines to via A (147.1, 67.8), steps
  under Wall_Sensor_2 on a 0.94 mm B.Cu jumper to via B (147.1, 66.86) and reaches the battery
  divider above the corner: R44 (VBAT, from C19's VBAT pad), R45 and C59 in a row at
  y = 65.45, 7.5 mm of track from pad 24 to C59. To make the room, Switch_0's B.Cu run turns
  along the switch bus square, LED_ARGB's via sits at (145.85, 66.9), the Button and Reset hops
  across the switch bus sit at x = 148.05 and 148.63, R21 is 0.15 mm further along its axis, D5
  0.15 mm nearer the front edge, and Wall_Sensor_3's run down the top-right side 0.1 mm inwards.
  The vias over the switch bus keep JLCPCB's 0.2 mm via-hole-to-track rule.
- **USB-C**: U6 sits left of the receptacle above its contacts. D+ and D- leave U2's contacts
  into U6's pads 6 and 4, leave its pads 1 and 3 through two vias, run on B.Cu down U2's left side
  and along between its shell pads, and come back to F.Cu through two vias in the strip right of
  U2 into the coupled run to IC1 (0.2248 / 0.127 mm, 90 Ohm on this stack). Three 0.8 mm bumps
  on D-'s B.Cu run match the pair: 122.8 / 124.5 mm (D+ / D-) through U2's A-row contacts,
  123.8 / 122.0 mm through the B row. U6's 3V3 pad takes the feed from above down the package's
  centre line, its GND pad a via under the body. C79, U6's rail capacitor, stands above U6
  between C43 and the R36-R38 column, on that feed 4.5 mm of track from pad 5 (the D+ run right
  of U6 and the receptacle below leave no shorter way in); its GND pad joins R37's GND via,
  0.9 mm away. D8 sits in the strip right of U2, with vias to
  the In2.Cu +5V plane and In1.Cu; R50 below the pair's vias, on CC1 from R6.
- **SBU supply**: F1 sits right of Q7; SBU_PWR runs from the SBU contacts' B.Cu joint along under
  the receptacle, up the strip right of it and on to F1. U7 with R52-R54 and C78 sits between
  EC1 and the USB pair, SBU_VREF (6.6 mm) under U7's body; the hold C77/R51/D13 below it, on
  SBU_DET (9.7 mm) down the column's right side; R55 above Q7's gate. SBU_DET_A runs from R50 to
  D13 (22 mm, four vias), the one long detector net.
- **NRST and PH0**: NRST (pin 12) drops to B.Cu on the axis of the unused pin 11, PH0 (pin 10,
  USB_VBUS_Sense) a pitch further out; Current_Sensor_Left's B.Cu run passes between PH0's via and
  pin 9's 3V3 via in 0.15 mm.
- **SWD connector P1** (top entry) at (125.85, 90.5), rotated 90 degrees: the reinforcement
  pads 0.25 mm inside the left board edge, the contacts at x = 127.175 facing inwards (pin 1 at
  y = 92.5). The fan connector M3 sits 1.95 mm inwards of the Altium position (its old spot would
  overlap P1's courtyard); U5/C64 sit below P1, D3 next to R1/R2. SWDIO runs to P1
  on B.Cu from a via under IC1 pad 48. `layout/swd_top.py` places it and routes its nets.
- **Wall sensors**: W1-W4 are the bare SFH 4550 over the TPS601A, without the casing
  ([`components/micras/WallSensor`](../../../components/micras/WallSensor)), and sit fully on the
  board: each courtyard (both bodies at their largest and the pads, plus 0.25 mm) keeps the
  0.20 mm board-edge clearance. W2 and W3, looking diagonally over the front corners, are 0.23 and
  0.21 mm inside (W2 0.03 mm sideways for its courtyard against R17). W1 and W4, looking forward
  over the side chamfers, are 3.3 mm further inwards and 0.45 mm further back, mirrored (the
  owner's choice of the moves the chamfer allows; 3.3 mm keeps W4's pads above the DIP switch
  SW1): robot (36.270, +/-18.200), lens tips at x = 42.550 (emitter, 9.75 mm above the board top)
  and 42.325 (receiver, 3.25 mm). The board takes none of the emitter's +-3 degree or the
  receiver's +-10 degree cone: the axes leave it 4.6 and 4.8 mm ahead of the lens tips (W1/W4),
  1.0 and 1.2 mm (W2/W3). Each channel's parts sit around its sensor: Q2, D9, R12 and C26 in the
  corner left of W1, R13 below its pads, R14 and C73 right of them; Q5, R24 and R26 in the corner
  right of W4, R23 left of its pads, R25 under SW2 (0.35 mm up, D12 with it) with C29 at its 3V3
  end, C76 above SW2 by D12; C73-C76/D9-D12 between each R11/R15/R19/R23 and its Q2-Q5. The
  switch bus Switch_0-3 runs on B.Cu left of W4's pads, and VBAT, Wall_Sensor_2, WALL1_LED_K and
  WALL2_GATE step round the moved parts. `layout/wall_inside.py` places them and routes their
  nets.
- **Motors_Enable** to U1 pad 11 crosses the rear half on B.Cu (R49 by R35); C65/C66 at IC5,
  C67/C68 at IC3/IC4 pin 6, C69/C70 at EC1 (3V3 from EC1 pin 5's via, clear of H2's In2.Cu
  void), C71/C72 at EC2, Q7 for SBU, R43/C58 by Q6, FB1 in IC1's VDDA feed. C33 (IC6's charge
  pump) stands above C32, clear of the 2512 shunt R31's courtyard.
- **C6** (VCAP2) sits 2.8 mm from IC1 pin 49 and takes VCORE from the In2.Cu VCORE route through
  its via at (144.437, 82.552); C14/C17 (pin 35) lie across, clear of IC1's courtyard.
- **C15** (IC1 pad 51, VDD) stands 1.8 mm from the pad, in the strip under pads 46-51 between the
  USB pair and SWCLK: its 3V3 pad on pad 51's via, its GND pad on a via of its own.
- **Courtyards and moves**: no two courtyards overlap. Against the Altium positions, the parts
  below moved, to clear a courtyard or for the layout above (KiCad mm; robot frame x forward,
  y left):

  | Part | KiCad x, y (from) | KiCad x, y (to) | Robot x, y (to) |
  |---|---|---|---|
  | M1 left motor connector | 138.001, 146.575 | 139.201, 146.575 | -33.071, 9.300 |
  | M2 right motor connector | 160.501, 146.575 | 159.951, 146.575 | -33.071, -11.450 |
  | SW4 battery switch | 168.988, 143.344 | 169.078, 143.564 | -30.060, -20.577 |
  | M3 fan connector | 132.473, 90.318 | 134.423, 90.318 | 23.186, 14.078 |
  | P1 SWD connector (JST SH, top entry) | | 125.850, 90.500 | 23.004, 22.651 |
  | C36 VBAT bulk | 163.099, 138.701 | 162.669, 138.701 | -25.197, -14.168 |
  | C37 +20V bulk | 141.128, 140.162 | 140.731, 140.162 | -26.658, 7.770 |
  | C38 L6205 VS 100 nF | 136.436, 140.606 | 136.190, 144.750 | -31.246, 12.311 |
  | U6 USB ESD array | 145.050, 134.750 | 146.900, 134.780 | -21.276, 1.601 |
  | D8 VBUS TVS | 148.300, 133.900 | 157.250, 138.700 | -25.196, -8.749 |
  | F1 SBU fuse | 147.993, 135.907 | 167.100, 126.850 | -13.346, -18.599 |
  | C33 fan charge pump | 144.284, 123.338 | 143.600, 121.600 | -8.096, 4.901 |
  | R44 battery divider | 149.200, 65.600 | 145.630, 65.450 | 48.054, 2.871 |
  | R45 battery divider | 146.850, 66.250 | 146.570, 65.450 | 48.054, 1.931 |
  | C59 battery divider | 145.750, 65.520 | 147.510, 65.450 | 48.054, 0.991 |
  | R21 W3 emitter resistor | 151.777, 66.061 | 151.883, 65.955 | 47.549, -3.382 |
  | D5 power LED | 152.810, 62.243 | 152.810, 62.093 | 51.411, -4.309 |
  | W1 wall sensor (left, looks forward) | 127.001, 76.784 | 130.301, 77.234 | 36.270, 18.200 |
  | W4 wall sensor (right, looks forward) | 170.001, 76.784 | 166.701, 77.234 | 36.270, -18.200 |
  | W2 wall sensor (left diagonal) | 138.315, 65.934 | 138.294, 65.955 | 47.549, 10.207 |
  | Q2 W1 emitter switch | 131.457, 84.222 | 125.850, 82.250 | 31.254, 22.651 |
  | D9 / R12 / C26 W1 clamp, pull-down, 1 uF | 131.700, 77.700 / 131.532, 80.793 / 130.100, 81.600 | 125.700, 85.100 / 128.000, 85.060 / 126.050, 79.800 | 28.404, 22.801 / 28.444, 20.501 / 33.704, 22.451 |
  | R13 W1 emitter resistor | 126.500, 84.530 | 130.950, 85.050 | 28.454, 17.551 |
  | R14 / C73 W1 load, gate capacitor | 131.532, 79.777 / 131.532, 81.809 | 133.350, 80.750 / 133.350, 82.650 | 32.754, 15.151 / 30.854, 15.151 |
  | C21 Reset capacitor | 133.642, 77.614 | 133.642, 78.860 | 34.644, 14.859 |
  | D10 W2 clamp | 131.500, 72.900 | 135.750, 74.600 | 38.904, 12.751 |
  | R17 / C74 W2 emitter resistor, gate capacitor | 144.030, 66.950 / 137.758, 70.685 | 144.158, 66.992 / 137.798, 70.725 | 46.511, 4.343 / 42.779, 10.703 |
  | R19 W3 gate resistor | 166.000, 71.800 | 163.150, 73.850 | 39.654, -14.649 |
  | SW2 button / D12 W4 clamp | 160.439, 80.662 / 159.600, 77.000 | 160.439, 80.312 / 159.600, 76.800 | 33.192, -11.938 / 36.704, -11.099 |
  | Q5 W4 emitter switch | 164.376, 77.087 | 171.200, 81.900 | 31.604, -22.699 |
  | R24 / R26 W4 pull-down, load | 166.400, 80.815 / 164.400, 80.815 | 171.400, 79.400 / 171.400, 78.350 | 34.104, -22.899 / 35.154, -22.899 |
  | R23 / C76 W4 gate resistor, capacitor | 164.400, 79.765 / 166.400, 79.765 | 163.900, 80.750 / 161.600, 77.300 | 32.754, -15.399 / 36.204, -13.099 |
  | R25 / C29 W4 emitter resistor, 1 uF | 165.600, 82.550 / 164.376, 74.801 | 161.100, 83.420 / 157.900, 83.450 | 30.084, -12.599 / 30.054, -9.399 |

  R6 and R7 moved 0.12 mm sideways; the SBU detector's parts are new (see above). J1, U2 and
  IC5 keep their positions; IC5's pad 10
  is 0.2 mm (the copper-to-edge rule) from the rear-left corner arc. MicrasHardware takes the
  board's components from the board STEP (`make review`), so it must re-export
  `ref/board.step` and `ref/board_boxes.json` and re-run `tools/check_layout.py`.
- **Clean-up**: the outline's six 1-10 nm lines, the zero-length tracks, stubs left by the changed
  nets, and teardrops that left copper slivers against a twin are gone. U2's outer GND pads are
  1.19 mm long, 0.22 mm from the USB-C peg holes.
- **Silkscreen**: every reference designator is on F.Silkscreen, 0.5 mm high with a 0.125 mm
  stroke (the owner's choice), clear of pads, of other silkscreen and of the board edge, off the
  part bodies wherever a spot allows (C64's sits on U5). The board's minimum is the same
  0.5 mm / 0.125 mm (`main.zen` Silkscreen, `rules/kicad-severities.toml`; KiCad's stroke font
  caps the stroke at a quarter of the text size), an accepted trade-off against JLCPCB's
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

## Differences from the Altium board

Apart from C1 and C2, the board's copper, mask, paste, drills and outline match the Altium
MicrasMainBoard's own Gerbers (its CAMtastic output) except where KiCad, JLCPCB's rules or the
generic parts set them otherwise:

| What | This board | Altium board | Why |
|---|---|---|---|
| Pour to board edge, fan hole, encoder slots and peg holes | 0.21 mm | 0.19-0.20 mm | `rules/jlcpcb.kicad_dru`: JLCPCB's 0.2 mm routed-edge clearance ("Outline" table) plus 10 um for the fill's arc approximation |
| Inner-plane gap around a 0.45 / 0.3 mm via | 0.125 mm, 0.2 mm from the hole | 0.100 mm, 0.175 mm from the hole | JLCPCB capabilities, "Traces": inner-layer via hole to copper 0.2 mm. Between the five via pairs 0.76 mm apart (at (148.9, 110.9), (148.0, 66.9), (142.2, 80.8), (145.2, 86.5) and (151.0, 71.8)) the inner planes would be 0.06 mm wide, below the 0.1 mm neck width, and are not poured (0.11 mm wide on the Altium board) |
| Pour shapes elsewhere | KiCad's fill | Altium's fill | the same outlines, clearances and neck width; the fills differ in a few spots of under 0.03 mm2 each |
| Teardrop cusps | thinner than 0.1 mm left out | drawn to a point | JLCPCB's 0.1 mm minimum copper feature |
| Generic footprint pads (short x long side) | R0402 0.54 x 0.64, R0603 0.80 x 0.95, C0402 0.56 x 0.62, C0603 0.90 x 0.95, C0805 1.00 x 1.45, C1206 1.15 x 1.80, LED0603 0.875 x 0.95 mm, rounded corners | R0402 0.54 x 0.566, R0603 0.806 x 0.864, C0402 0.60 x 0.62, C0603 0.80 x 0.90, C0805 0.97 x 1.47, C1206 1.07 x 1.82, LED0603 0.80 x 0.80 mm, square | KiCad's IPC-7351 library footprints for the generic passives; same pad centres within 0.12 mm |
| Paste of the generic passives | aperture = pad (R0402: 0.54 x 0.64 mm, area ratio 1.2 for a 0.12 mm stencil) | custom stencil regions inside the pads (R0402: 0.58 mm square) | KiCad's library defaults, above IPC-7525's 0.66 area ratio for release; about 10 % more paste on the 0402 resistors |
| Mask of the generic passives | the board's 0.02 mm expansion | 0.0508 mm on the passive pads | KiCad's library footprints carry no local margin |
| Silkscreen of the generic passives | KiCad's outlines (fewer lines, no box around 0402s) | Altium's pad boxes | KiCad's library footprints |
| Wall sensors | the bare SFH 4550 and TPS601A, fully on the board; silkscreen: their outline, the lead area and the C/E labels | a casing over both, overhanging the board edge at W1/W4, its silkscreen a hatched body clipped at the edge | the owner's choice: no casing, every sensor on the board ([`components/micras/WallSensor`](../../../components/micras/WallSensor)) |
| Texts | KiCad stroke font | Altium fonts | same strings, sizes and positions |
| Passive 3D models | KiCad library models: C0402 0.50, C0805 1.25, C1206 1.60, R0603 0.45 mm tall | 0.55, 1.45, 1.80, 0.56 mm | KiCad's generic models (D4 and D5 are scaled to their datasheets, above) |
| Solder mask thickness | 10 um a side (1.0412 mm board) | 15.24 um (1.0517 mm) | Zener's stackup has no mask thickness setting; JLCPCB applies its own |

## Known faults

The board passes every gate: build, warnings, the Zener benches, layout sync, ERC, LVS, previous,
DRC (no errors), DFM, pytest and parts. These DRC warnings stay:

| Check (gate) | Fault | Why it stays |
|---|---|---|
| `silk_overlap`, `silk_over_copper` (drc, warnings) | package artwork on its own outline (the W1-W4 "C"/"E" and SW1 "ON" marks), outlines of neighbouring parts touching (D9/R14, D11/D12, D4/R4, D5/R5, R13/W1, R17/W2, R44/R45/C59), and the board artwork (the slogans, the frame lines, the arcs and circles) under parts (C58, C63, C65/C66, C69/C70, D3, M3, Q7, R48, R49, the test points, and the SBU detector U7, C77, C78, D13, R51, R52, R55 with F1, which sit on the "SUCUMBINDO SINCE 2024" frame) | cosmetic: JLCPCB clips silkscreen at pads, and no reference designator is among them |
| `silk_edge_clearance` (drc, warning) | SW4's outline crosses the rear notch's edge | the battery switch overhangs the board edge by design, its lever outwards |

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
- Bluetooth module RESETB pull-up (m17): on the module (boards/bluetooth). PA11's pull-up is a
  firmware setting, which `tests/test_bluetooth.py` checks in the declared firmware changes.
- High-side battery switch (m6): the low-side switch works; the battery reading is valid while it
  is on.

## Open items

- [ ] Check every part's placement rotation in JLCPCB's assembly preview, then set
      `rotation_verified = true` in `parts/jlc.toml`.
- [ ] Check U4's TPS2121 footprint against TI's land pattern before ordering.
- [ ] MicrasHardware: re-export `ref/board.step` and `ref/board_boxes.json` from this board and
      re-run `tools/check_layout.py` (the parts in the table under [Layout](#layout) moved, and
      the SBU detector's are new); keep the space above P1 (robot x = 23 mm, y = 22.7 mm) clear
      for the top-entry SWD plug, 6.3 mm above the board when mated.
- [ ] Wall sensors (W1, W2, W4 moved, no casing; see [Layout](#layout)): MicrasHardware
      `micras/front.py` SENSORS (W1/W4 at (36.270, +/-18.200), W2 at (47.549, 10.207)) and OUTLINE
      (the casing outline its sensor caps stand on), and the caps themselves; MicrasFirmware
      `sim/robot.toml` (emitter and receiver points, the cap collision boxes and cylinders),
      `config/targets/v1/robot.hpp` `wall_sensors` (W1/W4 at (0.04244, +/-0.0182)), then the
      wall-sensor gains and `reference_readings` calibrated again on the bench.
- [ ] Bench: in the SWD probe mode, VSYS at 3V3 less a diode drop and no switching on IC7's SW
      node (DS13554 does not cover VIN below 3.5 V with the output held up; see
      [Power](#power)); SBU switching on with the module either way up, and staying off with a
      USB host, a C-to-C cable and an audio adapter.
