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
| [`firmware.toml`](firmware.toml) | | the firmware's pin map, supply setting, battery channel and drive duties, from MicrasFirmware (`micras-pcb firmware snapshot`) |
| [`test/`](test) | | `pcb test` benches of the board's circuit: MCU, power, drivers, peripherals |
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

## Known faults

The board keeps its previous revision's circuit, so the design checks fail where that circuit is
wrong. Each failing check, the fault behind it (with its item in the design review,
`hw_debug/schematic_review.md`), the requirement it breaks, and the fix. Every fix listed keeps
the board's functions.

| Check (gate) | Fault | Requirement | Fix |
|---|---|---|---|
| `main_mcu` `boot0_pulled_down_without_supply_coupling` (test) | C60 (100 nF) runs from BOOT0 to 3V3: the 3V3 ramp holds BOOT0 high past reset release, so the MCU starts the system bootloader, which drives PA9/PA10 (motor) and PA2 (buzzer) (M1) | BOOT0 10 kOhm to VSS (AN5419 Figure 19); sampled after the 377-550 us reset temporisation (DS13311 Table 20, RM0468 2.6) | C60 to GND, or remove it |
| `main_mcu` `debug_header_carries_reset` (test) | P1 has 3V3, GND, SWDIO, SWCLK only: no connect-under-reset (m7) | AN5419 Figure 21: the debug connector's nSRST on NRST | 5-pin header with NRST |
| `main_mcu` `usb_data_lines_without_external_parts` (test) | R10 1.5 kOhm D+ pull-up to 3V3; R8/R9 33 Ohm in series with D-/D+ (M11) | DS13311 Table 118: pull-up and driver impedance (28-44 Ohm) internal, no series resistors; AN4879 3.1.1: pull-up only with VBUS | remove R10; R8/R9 0 Ohm |
| `main_mcu` `usb_vbus_sensing` (test) | VBUS reaches no MCU pin (M11) | AN4879 2.6: VBUS sensing mandatory on a self-powered device; 2.6.1 divider | 33 kOhm / 82 kOhm from VBUS to PH0 or PH1 |
| `main_power` `buck_output_capacitance` (test) | 268.7 uF on 3V3, 220 uF of it in C56 (m1) | DS13554 Eq. 42/43: 30.5-145 uF for the internal compensation | C56 to 2 x 22 uF |
| `main_power` `boost_output_voltage` (test), warnings | R39/R40 2 MOhm / 130 kOhm set +20V to 18.97-20.32 V (m2) | SLVSDA7E 7.3: VOUT at most 20 V; OVP from 20.5 V | 1.00 MOhm / 71.5 kOhm (17.95 V) |
| `main_power` `boost_feedback_divider_current` (test) | RDOWN R40 is 130 kOhm (m2) | SLVSDA7E 9.2.4: RDOWN below 100 kOhm | as above |
| `main_power` `boost_inductor_ripple` (test) | L2 1 uH at 1.16 MHz (R36 150 kOhm) ripples 4.22 A at 9.9 V (M4) | SLVSDA7E 9.2.4.1: below 4 A, Eq. 2-3 and 5 | R36 140 kOhm (3.96 A), or a larger inductance |
| `main_power` `boost_enable_not_from_its_input` (test) | U1 EN on VBAT: the boost starts from the 2.6-2.9 V back-fed VBAT, so the motors are powered from USB or the probe (C4) | the board keeps the motor supply off in the debug modes; SLVSDA7E 7.5: UVLO 2.7 V, EN 0.4/1.2 V | EN from PH0/PH1 (800 kOhm internal pull-down), or a VBAT divider |
| `main_power` `ldo_input_capacitor` (test) | nothing on +5V at U3 (M3, m5) | LM1117 9.2.2.1.1: 10 uF on the input (the CJA1117B datasheet is silent) | 10 uF on +5V |
| `main_power` `ldo_output_capacitor_esr` (test) | only ceramics on U3's output (M3) | LM1117 9.2.2.1.3: output ESR 0.3-22 Ohm; AMS1117: 22 uF tantalum | 22 uF tantalum or polymer at U3, or a ceramic-stable regulator |
| `main_power` `battery_switch_slew` (test) | SW4 ties Q6's gate straight to VBAT: VBAT steps onto the fan driver (M5) | DS14341 Table 1: dVS/dt at most 0.5 V/us | 100 kOhm in series with the gate and 47 nF from gate to drain (about 2.7 V/ms) |
| `main_drivers` `l6205_enable_off_in_reset` (test) | Motor_Enable floats while the MCU is in reset (m12) | RM0468 11.3.1: pins in analog mode in reset; L6205 Figure 4: no input pull | 10-100 kOhm from Motor_Enable to GND |
| `main_drivers` `stspin958_phase_matches_load` (test) | PWM2/PH on 3V3 with M3 between OUT and LSS (M7) | DS14341 5.6.2.2, Figure 14: that load wiring pairs with PH = 0 | PWM2/PH to GND |
| `main_peripherals` `usb_c_sbu_open` (test) | SBU1/SBU2 carry 3V3 through F1 for the Bluetooth module (M6) | Type-C R2.0 4.3, Table 4-28: SBU open or at least 950 kOhm to GND | power the module through its own connector |
| `main_peripherals` `usb_esd_protection` (test) | no ESD part on D+, D-, VBUS (M12, m5) | AN4879 2.3, Table 11: USBLC6-2 on D+/D-, ESDA7P60-1U1M on VBUS, at the receptacle | add both |
| `test_each_supply_net_has_one_source` (pytest) | IC7, U3 and the probe on P1 all drive 3V3 (C5) | one source per net, or ORing; DS13554 6.6.2: the L6981N sinks up to 1.75 A | one 3V3 regulator fed through ideal diodes from the battery and VBUS; P1 pin 1 as a sense line |
| `test_no_source_back_feeds_another_supply` (pytest) | 3V3 reaches VBAT through IC7 (U1 and IC6 powered from USB or the probe) and +5V through U3 (C3, C5) | DS13554 Figure 19, Table 3; Type-C R2.0 4.5.2.2.3.1: a sink does not drive VBUS | as above, with the buck on its own input node (L6981C33 does not sink) |
| `test_net_names_follow_the_firmware_labels` (pytest) | PA10 `Motor_Enable` (firmware `Motors_Enable`), PB12 `LED_Blue` (`LED_Red`, a yellow LED), PB13 `Fan_Overcurrent` (`Fan_TOFF`), PC0/PC1 `Current_Sensor_Right`/`_Left` swapped (m14, m15) | net names are the firmware's pin labels | rename the nets (the previous-revision comparison then needs the renames declared) |
| `test_battery_voltage_is_measurable` (pytest) | no path from the pack to an ADC pin: the firmware reads the VBAT pin's internal channel, and VBAT is on 3V3 (C1) | the firmware's battery reading; VBAT pin absolute maximum 4.0 V (DS13311 Table 10) | 100 kOhm / 27 kOhm + 100 nF into PA5 (2.68 V at 12.6 V); firmware on ADC1/2 channel 19 |
| `test_wall_emitter_resistors_at_the_firmware_duty` (pytest) | R13/R17/R21/R25 (10 Ohm 0603, 100 mW) dissipate 121 mW at the firmware's 37.5 % duty (M14) | resistor rating | 1206 resistors |
| `test_wall_emitters_survive_a_gate_held_high` (pytest) | a gate held high puts 180 mA DC through the SFH 4550 (M14) | SFH 4550 p4: 100 mA DC | AC-couple each gate (series capacitor with the 10 kOhm pull-down) |
| `test_buzzer_resistor_at_the_firmware_duty` (pytest) | R3 (10 Ohm 0603) dissipates 151 mW at 50 % duty with a 9 Ohm coil (m16) | resistor rating; FUET-5030 coil 12 +- 3 Ohm | 0805 or 1206 resistor |
| `test_every_assembled_footprint_has_a_courtyard[main]` (pytest) | the 38 footprints from the Altium library draw their courtyard on User layers | F.CrtYd/B.CrtYd courtyards for KiCad's overlap check | move the outlines to F.CrtYd in each component package |
| `test_every_smd_pad_of_an_assembled_part_has_paste[main]` (pytest) | U3's SOT-89 tab and centre lead (custom pad 2) has no F.Paste opening | reflow needs paste on every SMD pad | add F.Paste to the pad in `components/cj/CJA1117B` |
| warnings | D1/D2 (WS2815C-2020, VDD 9.5-13.5 V) on 3V3: the LEDs never light (M13); +20V above 20 V (m2, as above) | WS2815C-2020-4P V1.0 p3 | supply D1/D2 from VBAT, or a 5 V LED with a 5 V rail and level shifter |

The layout is not placed yet, so `layout-check` (its DRC: unrouted nets, overlapping parts),
`drc` and `dfm` fail on main for that reason alone, and two tests skip until the board has an
outline: `test_decoupling_sits_at_its_pin[main]` (every decoupling capacitor the datasheets ask
for at a pin, within 3 mm) and `test_encoder_slots_take_the_encoder_tab` (the slot against the
encoder tab, JLCPCB's 1.0 mm minimum non-plated slot and its rounded milling).

Requirements without a check, and why:

- VDDA through a ferrite (m9): AN5419 Table 2 allows it ("can be connected through a ferrite
  bead"), it does not require it.
- 1 uF + 100 nF at EC1/EC2 (m19): the AS5047U asks for 100 nF at the chip, which the encoder
  board has.
- Ceramics of several uF at the L6205 (M8): the L6205 datasheet asks for 100-200 nF near the pins
  plus bulk, which the board has; the ripple current depends on motor currents no document gives.
- Boost current limit against J1 (m3): no source bounds it; the 3 A JST PA rating is below the
  fan driver's own 5 A limit, so the bound is the battery harness, not the boost.
- L2 saturation against the boost current limit: the XAL6030-102 package does not know whether
  its 23 A is the saturation current (TODO in its docstring).
- L6981 slope compensation (Eq. 38): with Eq. 13 read literally, ST's own 22 uH evaluation set-up
  fails it too, so the reading is not reliable enough for a gate.
- Capacitor voltage derating: the ratings are checked against the worst-case net voltage
  (`capacitor_voltage_ratings`); no sourced derating factor is applied.

## Open items

- [ ] Placement, routing, zones, the outline (`spec/main.toml`), the encoder slots and USB-C peg
      holes in Edge.Cuts, and the four M2 screw holes: the layout transfer from the previous
      revision.
- [ ] Solder mask colour and surface finish: not recorded in the Altium design; the board uses
      the 4-layer defaults until they are confirmed.
- [ ] Check every part's placement rotation in JLCPCB's assembly preview, then set
      `rotation_verified = true` in `parts/jlc.toml`.
- [ ] Fix the [known faults](#known-faults).
