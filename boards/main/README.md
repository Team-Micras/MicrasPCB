# Main board

The Micras micromouse main board: a 50 x 90 mm, 4-layer, 1.04 mm board. It carries the STM32H725RGV6 controller, the battery input and power conversion, the
two locomotion motor bridges and the fan driver, the IMU, four wall sensors, the slots for the
two encoder boards, and the user interface.

The circuit replicates the MicrasMainBoard Altium design part for part: every part keeps its
designator, and `micras-pcb previous compare main` checks the netlist against that design's
connectivity ([`previous/board.json`](previous/board.json)) plus the changes declared in
[`changes.toml`](changes.toml).

## Files

| File | Sheet instance | Contents |
|---|---|---|
| [`main.zen`](main.zen) | root | IC1 (STM32H725RGV6) and its supply network (C1-C17, L1), SWD header P1, test points, board stackup and rules |
| [`Regulators.zen`](Regulators.zen) | `REGULATORS` | J1 battery connector, battery switch SW4/Q6/R41, 3V3 buck IC7, 20 V boost U1, USB LDO U3 |
| [`Drivers.zen`](Drivers.zen) | `DRIVERS` | IC5 (L6205D) bridges for M1/M2 with shunts R32/R33, IC6 (STSPIN958) fan driver for M3 with shunt R31 |
| [`Sensors.zen`](Sensors.zen) | `SENSORS` | IC2 (LSM6DSV) IMU, IC3/IC4 (TSC2020) current amplifiers, wall sensors W1-W4 with Q2-Q5, encoder slots EC1/EC2 |
| [`Peripherals.zen`](Peripherals.zen) | `PERIPHERALS` | SW1 DIP switch, SW2/SW3/SW5 buttons, BZ1 buzzer, D1/D2 addressable LEDs, D4/D5 LEDs, U2 USB-C |
| [`passives.zen`](passives.zen) | | value, package, rating and part number of every resistor, ceramic capacitor and LED line |
| [`changes.toml`](changes.toml) | | connectivity changes against the previous revision |
| [`erc.toml`](erc.toml) | | nets supplied from off the board (VBAT, GND), the PWR_FLAG role for ERC |
| [`layout/`](layout) | | KiCad project; the `.kicad_pcb` holds placement and routing |

Each sheet's docstring describes its circuit with the datasheet figure, table or equation behind
each value.

## Power

| Net | Source | Range | Loads |
|---|---|---|---|
| `VBAT` | 3S LiPo on J1 | 9.9-12.6 V | buck IC7, boost U1, fan driver IC6 |
| `GND_BAT` | pack minus on J1 | | switched to `GND` by Q6 |
| `3V3` | buck IC7 (L6981N33) and USB LDO U3 (CJA1117B-3.3) in parallel | 3.3 V | MCU, IMU, amplifiers, sensors, encoders, LEDs, logic of the drivers |
| `+5V` | USB-C VBUS | 5 V | U3 |
| `+20V` | boost U1 (TPS611781) | 19.63 V typ, 18.99-20.32 V | locomotion bridges IC5 |
| `VCORE` | the MCU's on-chip SMPS through L1 | 0.95-1.40 V | MCU core (VFBSMPS, VCAP1-3) |

Power modes:

- **Battery**: SW4 turns Q6 on, which connects the pack minus to `GND`; the buck makes 3V3 and
  the boost makes +20V from `VBAT`.
- **USB**: VBUS feeds U3, which makes 3V3.
- **Debugger**: P1 pin 1 is on 3V3, so an SWD probe can power the logic.

In the USB and debugger modes 3V3 also reaches `VBAT` backwards through IC7, and from there the
boost and the fan driver: the design review (`hw_debug/schematic_review.md` C3-C5) describes
this and the bench measurements.

## MCU supply

The VFQFPN68 STM32H725 has no VDDLDO pin: the core always runs from the on-chip SMPS, in the
"Direct SMPS supply" of ST AN5419 Figure 5 (p10). VLXSMPS drives L1 (2.2 uH), whose output is
`VCORE`; VFBSMPS and the three VCAP pins all sit on `VCORE`, with 2 x 10 uF at the inductor
(C3, C4) and 100 nF at each VCAP pin (C7, C6, C5), as AN5419 Table 2 (p7-8) requires. The
firmware selects `PWR_DIRECT_SMPS_SUPPLY` to match.

VBAT (pin 1), the backup-domain supply, is on 3V3 with C8 100 nF and C9 1 uF at the pin: with no
backup battery, AN5419 Table 2 ties VBAT to VDD. The pin's range is 1.2-3.6 V (DS13311 Table 13
p116), absolute maximum 4.0 V (Table 10 p114).

## Signals

Net names follow the firmware's pin map (`Motor_Left_PWM_FW`, `Encoder_Left_CSn`, `Wall_Sensor_0`,
...). Nets local to a sheet carry the sheet's prefix (`REGULATORS.BOOST_FB`). The IMU and both
encoder boards share `SPI_SCK`/`SPI_MISO`/`SPI_MOSI`, each with its own chip select.

| Function | MCU pins |
|---|---|
| Locomotion PWM, enable | PC7, PC9 (left), PA8, PA9 (right); PA10 enable |
| Motor current | PC1 (left, IC3), PC0 (right, IC4) |
| Fan | PB15 PWM, PB14 enable/fault, PB13 current-limit flag |
| Wall sensors | PB6-PB9 emitter PWM; PB1, PC4, PA6, PA4 receiver ADC |
| Encoders | PA3/PC14 CSn, PA0/PA1 and PB3/PA15 ABI A/B (left/right) |
| IMU | PD2 CS, PB5/PB4 INT1/INT2 |
| SPI | PC10 SCK, PC11 MISO, PC12 MOSI |
| USB / Bluetooth UART | PA11 D-, PA12 D+ |
| User interface | PA7 button, PC5/PB0/PB2/PB10 DIP switch, PA2 buzzer, PC6 ARGB LEDs, PB12 yellow LED |
| Debug | PA13 SWDIO, PA14 SWCLK on P1 |

PA5, PC15, PH0 and PH1 are unused.

## Board

4 copper layers, 1 oz outer and 0.5 oz inner copper, 0.2104 mm prepreg and 0.5 mm core, 1.0412
mm finished, from the Altium layer stack. Design rules: 0.1 mm clearance, 0.254 mm default track,
0.45 / 0.3 mm vias (0.5 / 0.3 and 0.8 / 0.4 mm also used), 0.2 mm copper to edge, all from the
Altium design rules; `rules/jlcpcb.kicad_dru` adds JLCPCB's limits on top.

## Open items

- [ ] Placement, routing, zones, the outline (`spec/main.toml`), the encoder slots and USB-C peg
      holes in Edge.Cuts, and the four M2 screw holes: the layout transfer from the previous
      revision.
- [ ] Solder mask colour and surface finish: not recorded in the Altium design; the board uses
      the 4-layer defaults until they are confirmed.
- [ ] Check every part's placement rotation in JLCPCB's assembly preview, then set
      `rotation_verified = true` in `parts/jlc.toml`.
- [ ] The design review (`hw_debug/schematic_review.md`) lists the faults this board shares with
      the previous revision; `pcb build` reports two of them as range warnings: +20V can exceed
      the TPS61178's 20 V recommended maximum (m2) and the WS2815C LEDs need 9.5-13.5 V, not 3V3
      (M13).
