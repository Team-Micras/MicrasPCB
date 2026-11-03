# Main board

The Micras main board: the STM32H725RGV6 controller, a 4S
battery input with its fuse, VSYS behind a Schottky, separate digital and analog 3.3 V rails, two
DRV8874 wheel bridges with in-line INA241 current sensing, the STSPIN958 fan driver, the IMU,
four wall sensors on a shared emitter current sink, the slots for the two encoder boards, the
ESP32-C5 dual-band radio, debug probe and data link with its flashing header, and the user
interface. The board has no USB; a programmer's 5 V pin on the flashing header or the SWD pads
(5V_IN) powers it for flashing without the pack.

The design is [research/next-revision/README.md](../../../research/next-revision/README.md): its
design basis (maxon DCX 10 L 4.5 V motors on a 4S pack, no boost; no USB; no 5 V rail), the options it recommends, and its connection lists A.1-A.6. The blocks it keeps are
the v1 main board's (MicrasPCB e34fb9a, `boards/main`), with their designators; new parts continue each series (C80-C114, D14-D15, D17,
IC8-IC9, J2, L4-L6, Q9, R58-R97, U8-U13), and the designators of removed parts are not reused.

The board is 100 x 50 mm, 4 layers, 1.04 mm, every part on the top side. Its mechanics are
[`spec/main.toml`](../../../spec/main.toml): the outline, the screw holes, the encoder slots, the
fan hole, the antenna and switch notches, the parts that mate with the robot or the outline and the
zones the chassis takes over the board (see [Layout](#layout)).

## Files

The board files are in `boards/main/` (this README sits in its `layout/` folder).

| File | Sheet instance | Contents |
|---|---|---|
| [`main.zen`](../main.zen) | root | IC1 (STM32H725RGV6) and its supply network (C1-C17, L1, R67), the ST-Link header SWD1 (with 5V_IN on pad 4), M2 screw holes H1-H4 |
| [`Regulators.zen`](../Regulators.zen) | `REGULATORS` | J1 battery connector with its fuse F1 and TVS D15, battery switch SW4/Q6, battery measurement R44/R45, VSYS diodes D14 (from VBAT) and D17 (from 5V_IN), 3V3_D buck IC7, 3V3_A LDO U8 |
| [`Drivers.zen`](../Drivers.zen) | `DRIVERS` | IC8/IC9 (DRV8874) bridges for M2/M1 with their 10 mOhm shunts R65/R75 and 47 uH chokes L4/L5, IC6 (STSPIN958) fan driver for M3 with its shunt R31 and 4.7 uH choke L6 |
| [`Sensors.zen`](../Sensors.zen) | `SENSORS` | IC2 (LSM6DSV) IMU, U10/U11 (INA241A2) current amplifiers, wall sensors W1-W4 with their AC-coupled selectors Q2-Q5 and the emitter current sink U12/Q9/R83 with its DAC set-point, encoder slots EC1/EC2 |
| [`Peripherals.zen`](../Peripherals.zen) | `PERIPHERALS` | SW1 DIP switch, SW2/SW3 buttons, R42 BOOT0 pull-down, BZ1 buzzer, D1/D2 (WS2812C-2020-V6) status LEDs, D4/D5 LEDs |
| [`Esp.zen`](../Esp.zen) | `ESP` | U13 (ESP32-C5-MINI-1-N4) with its decoupling, EN RC, GPIO28 pull-up, flashing header J2 (5V_IN on pin 2), and the links to the MCU with their series resistors R86, R88, R95, R96 and the ESP_CSn pull-up R97 |
| [`passives.zen`](../passives.zen) | | value, package, rating and part number of every resistor, ceramic capacitor and LED line |
| [`schematic/`](../schematic) | | how each sheet is drawn (`micras-pcb sch`): the root with IC1, its supply domains, the SWD header and the module sheets, and one file per module sheet, each block in a titled frame |
| [`erc.toml`](../erc.toml) | | nets supplied from off the board (BAT_P, GND, GND_BAT, 5V_IN) or through a passive part (VBAT, VSYS, 3V3_D, the LDO input, VDDA), the PWR_FLAG role for ERC; the two ERC warnings the module sheets leave until a pcb release includes [diodeinc/pcb#1522](https://github.com/diodeinc/pcb/pull/1522) (see [Known faults](#known-faults)) |
| [`firmware_changes.toml`](../firmware_changes.toml) | | the firmware changes this board needs against the v1 firmware (see [Firmware changes](#firmware-changes)) |
| [`test/`](../test) | | `pcb test` benches: MCU and ESP links, power, drivers, peripherals |
| [`layout/`](.) | | this folder: the KiCad project; `main.kicad_sch` is the root sheet, with one sheet per module (`REGULATORS.kicad_sch`, ...); the `.kicad_pcb` holds placement and routing; `place.py` places every part, `route.py` pours the planes and routes the board and `silk.py` places the reference designators (see [Layout](#layout)) |
| [`spec/main.toml`](../../../spec/main.toml) | | mechanical interface: thickness, axle origin, outline, screw holes, encoder slots, fan hole, wheel, antenna and switch notches, the ESP32 module's, battery switch's and wall sensors' positions, the chassis zones; the via-in-pad order option |

Each module is its own sheet of the KiCad schematic (`Project(..., layout=False)` in its `.zen`),
its signal ports named after the nets they carry where those names are identifiers, as on the
v1 main board. `SENSORS` takes the shared SPI bus once (`SPI_SCK`, `SPI_MISO`, `SPI_MOSI`) with
each device's chip select, not one `Spi` port per device, so it has 26 sheet pins instead of 32:
pcb 0.4.81 places the sheet symbols on the root one by one in the order of their names, each as
near the page centre as the earlier ones leave room, by their boxes alone, and the 32-pin symbol
fits only against the page's left edge, where its pin labels run past the page. At 26 pins it sits
right of `ESP`, and `tests/test_schematic.py` checks that every label stays on its page. Each sheet's docstring describes its circuit with the datasheet figure, table or
equation behind each value; [`tests/test_main.py`](../../../tests/test_main.py) checks the power tree, the analog
rail, the decoupling and the firmware contract on the generated netlist.

## Power

```text
4S LiPo 12.0-16.8 V (17.4 V HV) ─ J1 ─ BAT_P ─ F1 12 A fuse ─ VBAT (D15 SMAJ18A to GND_BAT)
   pack - ─ GND_BAT ─ Q6 HSBB3072 (SW4, slew-limited) ─ GND
VBAT ─┬─ IC8/IC9 DRV8874 VM, IC6 STSPIN958 VS
      ├─ R44/R45 20k/2k ─ PC5 (Battery_Voltage, ratio 11.0)
      └─ D14 B5819W ─ VSYS 11.4-17.4 V (3.8-5.0 V on 5V_IN alone)
5V_IN (a programmer's 5 V pin: J2 pin 2, SWD1 pad 4) ─ D17 B5819W ─ VSYS
      VSYS ─┬─ IC7 L6981C33 ─ 3V3_D: MCU VDD, ESP32, IMU, encoders, LEDs, emitters
            └─ R58 22 Ω + C80 10 µF ─ U8 ADP7142 3.3 V (EN = 3V3_D) ─ 3V3_A: VDDA (R67 0 Ω),
                  INA241 VS/REF1, phototransistor collectors, emitter-sink op-amp and its bias
```

- **VSYS** is VBAT behind D14, or 5V_IN behind D17, and feeds only the two regulators. D14 keeps
  5V_IN off VBAT, the bridges' bulk and the pack; D17 keeps the pack off the programmer.
- **No USB**: every rail comes from J1 but for flashing. 5V_IN takes a USB-serial adapter's or a
  clone ST-Link's 5 V pin (never its 3.3 V one) on J2 pin 2 or SWD1 pad 4 and runs the 3V3 rails
  without the pack: 0.19-0.25 A while flashing, VSYS 3.8 V or more, where the buck still
  regulates; the bridges and the fan stay unpowered and VBAT reads near 0 V (Regulators.zen,
  VSYS). On the bench, a current-limited supply at 12-16.8 V goes into J1 (a lead with the pack's
  JST PA plug) with SW4 on; with the motors and the fan disabled, set the limit just above what
  the 3V3 rails draw.
- **3V3_D**: the L6981C33 buck, as on the v1 main board, now from VSYS; every capacitor on 3V3_D,
  the ESP32's 22 uF included, stays inside its 30.5-145 uF compensation window.
- **3V3_A**: the ADP7142ACPZN3.3 LDO from VSYS through 22 Ohm + 10 uF 1210, its EN on 3V3_D so VDDA
  never leads VDD; about 10 mA typical, 23 mA worst case, 0.32 W at the HV pack's top.
- **No 5 V rail** (5V_IN is a programming input, not a rail).
- **Battery voltage**: R44/R45 20k/2k into PC5 with C59 100 nF: 1.58 V at 17.4 V and 2.20 V at
  D15's 24.2 V clamp, under PC5's 4.0 V absolute maximum (a ratio of 6 reaches 4.03-4.10 V there).
- **Fuse**: F1, Littelfuse 0501012.WR1 (12 A fast-acting, 32 VDC, 150 A interrupting, 3.2 mOhm;
  a 1206 under the chassis's 1.5 mm zone), carries the whole battery current from J1 to VBAT: a
  short on the board opens it. It carries the 4 A rms budget with 2x margin at 75 C (8.2 A) and
  holds the 10.1 A summed peak limits at 75 C (10.2 A); it clears a 40 A partial fault in about
  6 s (the 20 A row: about 25 s). Turning the board on is under 0.01 A2s against its 20.3 A2s.
- **Battery switch**: Q6 as on the v1 main board, its gate fed from VBAT through SW4; C58 100 nF
  gate-source and C114 1 nF gate-drain keep it off when the pack is plugged in (the board then
  sees no edge), and slew VBAT at about 0.06 V/us when SW4 closes, under the STSPIN958's
  0.5 V/us. SW4 is the SK-12D29-G060
  (DC 24 V, the v1 main board's switch body with a 6.0 mm lever, its own footprint). The connector
  keys the polarity; a reversed pack forward-biases D15 through F1, which opens.
- **TVS**: D15 (SMAJ18A, 18 V standoff, 20-22.1 V breakdown) behind F1, VBAT to GND_BAT, so a
  TVS that fails short opens the fuse. With the
  pack pulled while the bridges brake, it holds VBAT near 21-23 V through Q6's channel (SW4 on) or
  its body diode (SW4 off), at most 24.2 V, below every rating on VBAT and VSYS (50 V MLCCs,
  Q6's 30 V, the DRV8874's 40 V).
- **No electrolytics**: VBAT carries only ceramics, every 10 uF a 50 V X7R 1210 (61 uF effective
  at 16.8 V); the research's
  [VBAT capacitance](../../../research/next-revision/README.md#power-tree) compares the options and
  quantifies the VBAT overvoltage cases.

## Drivetrain and current sensing

- **Bridges**: one DRV8874PWPR per motor, PH/EN mode (PMODE = GND), PWM on EN and direction on
  PH (right PA10/PB6, left PC6/PA12), IMODE = GND (fixed off-time, automatic retry), ITRIP 2.97 A
  from RIPROPI 2.0 kOhm and VREF 2.67 V (4.7k/20k from 3V3_D). nSLEEP of both on Motors_Enable
  (PB7) with R49 100 kOhm to GND; nFAULT of both wire-ORed on Motors_nFault (PD2) with R60
  10 kOhm to 3V3_D. Per bridge: 100 nF + 4 x 10 uF 50 V X7R 1210 on VM, 100 nF VCP, 22 nF
  CPH-CPL.
- **Motor path**: OUT1 -> 10 mOhm WSK2512 4-terminal shunt -> 47 uH MTQH707050S470M choke -> motor
  connector; OUT2 -> connector.
- **Current**: INA241A2-Q1 (gain 20) on each shunt, VS and REF1 on 3V3_A, REF2 on GND: 0.2 V/A
  around VDDA / 2, about +7.1 / -8.0 A, into PB1 (left, a fast ADC channel) and PC1 (right)
  through 150 Ohm (R78/R79, R_iso), with 1 nF X7R beside the resistor; the firmware samples them
  for at least 0.7 us, so the ADC's kickback from a wall-sensor conversion settles below 1 mA.

## Fan

STSPIN958 in parallel half-bridge mode, PWM trimming, on TIM14 at 400 kHz: R31 25 mOhm, REF from
4.7k/2.0k on 3V3_D (current limit 3.94 A), RSR 1 kOhm (2 V/ns), 2 x 470 nF 50 V X7R 0805 +
2 x 10 uF 50 V on VS, CBOOT 1 uF 50 V X7R (the IC runs hot), and a 4.7 uH XAL5030-472 choke between FAN_OUT and the motor. Fan_PWM on PA7 (TIM14_CH1), Fan_TOFF on PB10; Fan_Enable on PB12, driven open drain and read back as the driver's nFAULT.

## Sensors

- **Wall sensors**: the four SFH 4550 emitters run from 3V3_D through 3.3 Ohm each (which keeps
  a failed sink's current inside the emitter's pulse rating) into their
  AO3400A selectors, AC-coupled as on the v1 main board (220 Ohm, 220 nF, 22 kOhm pull-down,
  1N4148WS clamp: a pin held high turns its emitter off within 7.5-11 ms), whose sources share
  one constant-current sink: TLV9001 + AO3400A + 1.2 Ohm 0.1 %, its set-point the DAC on PA5
  through 200k/20k (175 mA near code 3258, 223 mA full scale, 0 V at reset), compensated by
  1 kOhm / 1 nF and biased off at a zero set-point by 200 kOhm from 3V3_A. The phototransistor
  collectors are on 3V3_A.
- **IMU** and **encoder slots**: as on the v1 main board, on 3V3_D.

## ESP32 radio

- **ESP32-C5-MINI-1-N4** (U13), dual-band (2.4 and 5 GHz) Wi-Fi 6, on 3V3_D with 22 uF + 100 nF
  strapped to its 3V3 pin (Layout, The tab and the module's inner side) and 10 uF on its feed, EN
  RC 10 kOhm / 1 uF, GPIO28 (the boot strap) pulled up.
  Its PCB antenna overhangs the rear-right notch, the antenna's ground-point end (pin 1, the
  pad-62 corner) 0.7 mm from the right edge and 15 mm of board cut away beyond its open end
  (pin 45) (spec `[antenna_notch]`).
- **Flashing header J2** (HC-PZ127-7.2L-2x3PS, 2x3 1.27 mm SMD), wired as the ESP-Prog Program
  interface: 1 EN, 2 5V_IN, 3 TX0 (GPIO11), 4 GND, 5 RX0 (GPIO12), 6 GPIO28. Hold 6 low and pulse
  1 for the ROM's UART download mode; the console is on 3/5. Pin 2 takes the programmer's 5 V (an
  ESP-Prog with its jumper at 5 V, or a USB-serial adapter's 5 V pin) and powers the board through
  D17; no connector pin reaches 3V3_D. J2 has no shroud: a plug turned round puts the programmer's
  5 V on pad 5 (RX0, the C5's GPIO12, no resistor) and its ground on pad 3 (TX0). The C5's inputs
  take at most VDD + 0.3 V (datasheet v1.4 Table 6-3), so that plug can destroy the module: the
  silkscreen marks pad 1 ("1") and pad 2 ("5V") beside the header; there are no protection parts.
- **Links to the MCU** (C5 GPIOs free of strapping and other roles, off with no pull at reset):
  SWDIO GPIO0 -> PA13, SWCLK GPIO1 -> PA14 (22 Ohm), NRST GPIO23 (open drain); SPI3 half-duplex
  on three wires, the MCU the master: ESP_SCK PC10 -> GPIO10 (R95 22 Ohm at PC10), ESP_DATA PC12
  (the MOSI pad, IOSWP = 0) <-> GPIO8 (R96 220 Ohm at the C5), ESP_CSn PC11 -> GPIO9 (R88 100 Ohm
  at the C5, R97 100 kOhm pull-up to 3V3_D); ESP_Flow GPIO24 -> PA11, the C5's credit line. UART4
  is the fallback on PC10/PC11 with no board change.
- **ST-Link header** SWD1: bare 1.27 mm pitch pads in a clone ST-Link lead's order, 1 SWDIO, 2 GND,
  3 SWCLK, 4 5V_IN (the probe's 5 V pin; no NRST), for a probe when the ESP32-C5 cannot reach the
  MCU. Turned round or shifted one pad, the probe's 5 V never lands on GND, but it lands on a link
  line: turned round on SWDIO (pad 1, the C5's GPIO0 with no resistor), shifted toward pad 1 on
  SWCLK (pad 3, GPIO1 behind R86's 22 Ohm), above the C5's VDD + 0.3 V (datasheet v1.4 Table 6-3);
  "5V" marks pad 4 and the square pad is pad 1. BOOT0 stays low (R42): the MCU always starts
  from flash.

## Pins

The MCU keeps the v1 main board's pin map except where the layout needs another row (main.zen has
the full map and the alternate functions' source). Each line leaves the STM32 from the row facing
its part, and the lines that pass the fan hole leave the rear faces in the order of their routes
round it, so no line crosses the rear tip and no two escapes cross there:

- **Motors**: right bridge EN on PA10 (TIM1_CH3) and PH on PB6, left bridge EN on PC6 (TIM8_CH1,
  gated by TIM1 over ITR0) and PH on PA12; Motors_Enable on PB7, Motors_nFault on PD2 (EXTI2).
- **ESP32-C5 link**: PC10 (SPI3_SCK), PC12 (SPI3 data) and PC11 (chip select) on the rear-right
  row toward the module, UART4 as its fallback on PC10/PC11; ESP_Flow on PA11 (EXTI11); PA13/PA14
  and NRST to the C5 (PA13/PA14 also to the header SWD1).
- **Sensor bus**: SPI2 on PB13-PB15; chip selects Encoder_Left_CSn PA9, IMU_SPI_CSn PA8,
  Encoder_Right_CSn PB8; IMU_INT on PC7 (EXTI7, the IMU's INT1; INT2 unconnected).
- **Wall sensors**: selectors on TIM3 on the rows facing their emitters (PC9 CH4, PB0 CH3 on the
  left; PB4 CH1 Wall_Sensor_PWM_3, PB5 CH2 Wall_Sensor_PWM_2 on the right); the emitter DAC on PA5
  (DAC1_OUT2); Wall_Sensor_0 on PA4 and Wall_Sensor_3 on PC0.
- **ADC**: Current_Sensor_Left on PB1 (a fast channel), Current_Sensor_Right on PC1, each with an
  ADC1 and an ADC2 input; the battery divider on PC5 (ADC12_INP8).
- **Fan**: Fan_PWM on PA7 (TIM14_CH1), Fan_Enable on PB12 (open drain, its fault on EXTI12),
  Fan_TOFF on PB10.
- **User interface**: LED_ARGB on PA2 (TIM15_CH1, DMA on tim15_up), the buzzer on PB9
  (TIM17_CH1), LED_Red on PB2, Button on PA3, Switch_0-3 on PH0, PH1, PC15 and PC14 (the MCU has
  no VBUS input).

Every GPIO of the VFQFPN68 is used.

## Firmware changes

[`firmware_changes.toml`](../firmware_changes.toml) lists what the firmware must change against
the v1 firmware (`firmware.toml`, from MicrasFirmware):
PH/EN drive at 100 kHz with TIM8 slaved to TIM1; Motors_Enable as nSLEEP (1 ms wake);
Motors_nFault on PD2; INA241 sampling on TIM1 TRGO2 with dual injected ADC1/ADC2; the battery
divider constant 11.0 on PC5 and a "no pack" reading on 5V_IN; Switch_0 on PH0; the fan at 400 kHz
with Fan_PWM on TIM14 and Fan_Enable on PB12 open drain and its fault on EXTI12; the SPI3
half-duplex link to the ESP32-C5 (ESP-IDF v6.0.3 or later, AFCNTR, the data line on the MOSI pad,
/8 to start, a turn-around with no driver overlap, UART4 as fallback) with ESP_Flow credits on PA11;
the IMU and encoder bus on SPI2; Button on PA3; the LEDs on TIM15 and the buzzer on TIM17; the C5's slow clock on its RC, its pulls
and its resync after an MCU reset;
one wall emitter at a time on TIM3, with
the emitter DAC on PA5 stepping with each selector and a code per emitter, and no LED or SPI
traffic during an emitter's pulse; the current channels sampled for at least 0.7 us; the WS2812C
timing (T0L/T1L at most 1 us); flashing over Wi-Fi through the ESP32-C5's CMSIS-DAP-over-TCP or
Black Magic probe, nRESET on its GPIO23 (open drain only, released before it is enabled);
TIM1/TIM8/TIM14 frozen and the drive enables cleared on a debug halt; the LSM6DSV's I2C disabled
at boot and its interrupts all routed to INT1.

## Layout

[`place.py`](place.py) places every part, [`route.py`](route.py) pours the planes and routes
the board, and [`silk.py`](silk.py) sizes and places the reference designators; their docstrings
give the rules they follow. The `.kicad_pcb` holds their result with
the connections they left routed by rip-up scripts and by hand, under the same rules. Every
connection is routed.

- **Placement**: every part on the top side. The spec places what mates with the robot or the
  outline; the ESP32-C5-MINI-1 sits in the rear-right corner (spec `[u13]`), its pads on the board
  and its antenna over a notch cut out under it and beside it (see Antenna), each DRV8874 by
  its motor with its shunt, choke and bulk capacitors, the IMU between the encoder slots on the
  axle, the MCU and the wall-sensor channels in the nose, and the fan driver, DIP switch, buzzer
  and 3V3_A LDO beside the fan hole.
- **Rear-left corner** (beside SW4): the battery input and the 3V3_D buck. J1 sits by the left
  edge, its BAT_P pin behind its GND_BAT pin; its lead goes back to the pack over the low wall
  behind the left drive block (MicrasHardware `frame.py` cuts a `wire_slot` only in a full wall,
  15 mm in front of J1). F1 lies just behind the left drive block's tail zone (spec
  `[drive_blocks]` `tail_left` starts at x -22, F1 spans x -31 to -27), D15 and D14 beside it, Q6
  by the rear screw boss with its sources and gate toward the board's centre and its drain toward
  the edge, its gate network (R41, R43, C58, C114) in front of the gate. The buck IC7 sits in
  front of the tab, between SW4 and the module: its VIN/EN row faces SW4 with C53 at VIN (pin 7)
  and C52 (input bulk) beside it, its SW pin (1) faces L3 across a 3.8 x 2.2 mm BUCK_SW pour, C55
  (BOOT) and C54 (VCC) at their pins on that side (DS13554 Figure 32, the application board, puts
  them beside the chip); L3 against C54/C55's courtyard, its 3V3_D pad 4.85 mm from the antenna's
  open end; C56/C57 at L3's output on a short 3V3_D patch at the module's inner corner.
- **The tab and the module's inner side**: the flashing header J2 sits in the tab between the two
  notches, its pads 17 mm from the antenna's open end (at least 10 mm) and reachable from the
  robot's rear, with the EN RC (R89, C110) and the 10 uF C107 on U13's 3V3_D feed beside it; the
  BOOT pull-up R90 and the 5V_IN diode D17 sit in front of IC7. EN, TX0, RX0 and BOOT run inboard
  on B.Cu, past the notch's wall, to the module's pins 45/39/40/4. Ground vias fence the notch's
  inner wall (x -39.7, 0.4 mm from the cut, at 1.6-1.8 mm pitch from in front of the antenna's open
  end to the tab) and the tab's wall over the notch (y +6.5) (`route.py` `NOTCH_FENCE`). U13's 3V3
  pin (pin 3) and BOOT pin (pin 4) lie on the module's edge row, 0.6 mm from the board's edge: each
  leaves by a stub to vias inside the row and runs on B.Cu under the module. 3V3_D comes from L3's
  output patch on a 0.8 mm B.Cu feed under the module to two vias at pin 3, and a 1.0 mm B.Cu strap
  from those vias along the edge row joins the 22 uF C109 and 100 nF C108, which sit off the module's
  front-right corner with two vias each, 13-16 mm from the pin: no capacitor fits nearer it (the
  edge, the antenna end and the ground pads), and the module decouples its chip itself (datasheet
  Figure 8-1). The series resistors of the link (R86, R88, R96) and the ESP_CSn pull-up R97 sit at
  the module's front end, R97 on a via to the B.Cu 3V3_D run there; R95 sits beside PC10 (ESP_SCK's
  driver), in line with its escape off the STM32's rear tip.
- **Planes**: In1.Cu is ground over the whole board; In2.Cu is ground but for the STM32's two supply
  islands, each only as big as its job (`route.py`): 3V3_D (`mcu_3v3_outline()`) is the square under
  the chip out to its pin tips with a tab to the via of each 3V3_D pin (VBAT, VDDSMPS, VDD); VCORE
  (`vcore_outline()`) is a band outside the pin tips' vias that only reaches VCORE's vias (VFBSMPS,
  VCAP1-3, C3-C7, L1) and stops either side of the chip's rear tip. The signals' escape vias just
  past the pin tips sit between the two islands; the lines that leave them on B.Cu cross over the
  islands' edges (Wall_Sensor_2, Wall_Sensor_3, Current_Sensor_Left, Current_Sensor_Right and
  Wall_Emitter_Set among them), with In1.Cu's solid ground between them and the islands. B.Cu carries the VBAT pour over
  the power entry and both bridges, and no other net's track runs on B.Cu inside it.
- **Tracks**: F.Cu and B.Cu, octilinear. The power paths (`ROUTES` in `route.py`) are wide and
  locked; signals are 0.15 mm, 0.12 mm where they leave a fine-pitch pin and nowhere narrower,
  at 0.10-0.11 mm clearance. A switching net keeps 0.5 mm from an analog net on the same layer,
  tracks, pads and pours alike, but for the pin pairs and nose lines in Open items.
  No track or via ends open.
- **The ESP32-C5 link**: ESP_SCK, ESP_CSn and ESP_DATA leave the STM32's rear-right row (pins
  54-56) on F.Cu, R95 in line with the clock's escape, and run as a bus along the fan hole's right
  side, through the right half of the waist between the encoder slot EC1 and the board's edge and
  past the right bridge to the module's front end (60-66 mm, 4 vias on ESP_SCK_IO, 2 on ESP_CSn, 6 on
  ESP_DATA). The lines that leave the rear tip for the right side cross under them on B.Cu (SWCLK
  and Motor_Right_EN along the hole, IMU_SPI_CSn and Encoder_Right_ABI_A from vias beside their
  pins). ESP_Flow (108 mm, 14 vias) and SWDIO's SWD1-to-module leg (72 mm) go behind the fan hole on
  B.Cu, down the right side and on F.Cu between the bridges or round the VBAT pour's front-right
  corner to the module. Behind the hole's right side the right stream peels off in pin order as
  nested laterals in front of EC1 (Encoder_Right_CSn to EC1.1, Motors_Enable and Motor_Right_PH on
  B.Cu under EC1's inner row), and Reset crosses it with one square In2.Cu hop. The IMU and encoder bus (SPI2, pins 37-39) leaves the rear-left row on F.Cu, 0.12 mm
  wide between C14 and the fan driver's and the left motor's vias, and runs round the hole's left
  side to EC2, IC2 and EC1.
- **Power copper**: the battery path is poured for 10 A: J1's BAT_P pin to F1 as a BAT_P pour round
  J1's GND_BAT pin, nothing else on BAT_P before the fuse, at least 2.9 mm wide from pin to pin
  (IPC-2221's external width for 10 A at a 45 C rise; the BAT_P, GND_BAT and VBAT pours are checked
  by a morphological opening, `tests/test_main_layout.py` `test_battery_pours_keep_their_width`); F1's VBAT side a pour with 21 vias to the
  B.Cu VBAT pour's left appendage, D15, D14 and IC9's bulk C93 on it; GND_BAT poured on F.Cu and
  B.Cu from J1 to Q6's sources and D15 with 24 vias; Q6's drain in a ground pour along the edge
  with its via field. The battery switch's drive and its VBAT feed reach SW4 on B.Cu between the
  VBAT appendage and the GND_BAT pour; 5V_IN crosses them on F.Cu behind J1, out of the BAT_P pour,
  and 3V3_A on F.Cu in front of SW4's pins. No other net's track or via comes within 0.5 mm of J1's
  or SW4's pins. VSYS (D14, D17, C52) feeds IC7 on F.Cu and runs on B.Cu
  along the module's inner side, past its front-right corner and along the right wheel cut-out to
  R58 (a 0.3-0.6 mm feed for the 3V3_A LDO); U13's 3V3_D runs from L3's patch under the module
  (B.Cu) to its 3V3 pin, on to its capacitors and out at the module's front-right corner to the
  board's 3V3_D; 3V3_A reaches U11 from U10 round the rear (behind the module's front row, along
  the antenna notch's wall, through the tab beside J2, on F.Cu in front of SW4's pins and on B.Cu
  along the left edge beside the GND_BAT pour). 5V_IN runs from
  J2 pin 2 and D17 to SWD1 pad 4 along the left wheel cut-out, 0.3-0.4 mm but 0.15-0.2 mm for
  about 14 mm between SWD1 and the left encoder slot, where it passes between the IMU's and the
  encoders' lines (0.13 ohm of track in all, 32 mV at the 0.25 A of flashing, 1 oz copper). The
  motor paths are 1.0 mm (necks at the pins),
  the crossings by the connectors on B.Cu outside the VBAT pour with 4-via clusters. Each DRV8874's
  VM pin takes a short F.Cu island with its 100 nF (C82, C91) and 3-4 vias to the pour. The fan driver
  (STSPIN958) is turned so its power side faces the board's edge and its logic pins the fan hole
  (DS14341 Fig. 23): the VS strip runs out from pins 27-30 between OUT1 and OUT2 to the two 470 nF
  (C34, C35) and the bulk C99, with 6 vias to the B.Cu VBAT feed; OUT1 goes straight to L6 on F.Cu,
  OUT2 joins it through 5 + 5 vias and a B.Cu pour under the pins; LSS2 goes to R31 (its LSS pad
  1.8 mm from pin 24) and on to the fan connector's return M3.2, LSS1 joins it through 5 + 5 vias
  and a B.Cu pour beside the exposed pad's outer edge (the pad keeps all nine thermal vias),
  FAN_OUT's B.Cu pour beyond it, its front vias out of the ground path from C35 to the pad on
  In1.Cu; the motor runs from L6.2 to M3.1 along the board's edge on B.Cu. VBAT reaches the fan on
  B.Cu from the bridges' pour along the left wheel cut-out (a 1.5 mm pour, 1.1 mm at its
  narrowest), and goes on round the
  fan block's front (0.4 mm) to the bulk C112 and C96 in front of the fan hole and the battery
  divider's R44. The logic pins drop to B.Cu at their tips, and VDD and nSTBY take C31 under them
  on F.Cu: the fan hole's rim stays free on both outer layers for the lines to the STM32. The switch nodes stay on F.Cu: SMPS_LX straight to L1, BUCK_SW a short pour
  from IC7's pin 1 past C55 to L3. R58 (the 3V3_A LDO's input RC) sits by C80 and U8, VSYS running to it
  along the right wheel cut-out beside CURRENT_R_AMP. R75 is turned so OUT1 enters its front pad
  straight from IC9 and MOTOR_L_SHUNT leaves its rear pad toward L5; R65's OUT1 pad is its rear one.
  Each INA241's Kelvin lines run as a pair: the far sense line crosses under the shunt's body on
  F.Cu, between the force pads, to a via beside the near one's, and both run on B.Cu 0.4 mm apart
  to the amplifier's corner; the loop they close, pad to pin and back, is 10.6 mm2 (R65) and
  8.8 mm2 (R75), set by the WSK2512's sense pads in opposite corners and IN+/IN- on opposite rows.
  The VBAT pour leaves a slot under R75's rear half for its pair; Reset keeps outside R65's.
- **In2.Cu hops**: an exception where F.Cu and B.Cu have no room, not a routing layer: 14 mm on
  five nets (LED_ARGB, Motor_Left_EN, Reset, Switch_0, Wall_Sensor_PWM_0), 200 mm at most in all. A hop carries a digital line of the STM32 or the ESP32
  only; it keeps 0.25 mm (plan view) from every switching, analog and battery-side supply track on
  B.Cu (`nets.SWITCHING` includes the fan's low-side sources, bootstrap and charge pump, the
  bridges' charge pumps and the INA241s' Kelvin lines), stays off every B.Cu pour but ground and out
  of the STM32's islands, and leaves In2.Cu's ground in one piece but for pockets of 1.7 mm2 at
  most, each with its own ground via. Any other B.Cu track crosses a hop square, but for one
  exception: a hop of a slow digital line (`nets.SLOW_DIGITAL`) may run under another slow digital
  line's B.Cu track for at most `nets.IN2_PARALLEL_MAX` (1.5 mm) along each of its segments; the
  fast lines (`nets.FAST_DIGITAL`: SPI_SCK, LED_ARGB, the encoders, the ESP32-C5 link's clock and
  data, the fan's and the bridges' PWM lines) never run along one. The
  longest such run is 1.0 mm (`tests/test_main_layout.py`).
- **Antenna**: the board is cut away under the MINI-1's antenna and beside it (spec
  `[antenna_notch]`, 6.4 x 31.1 mm from the rear-right corner to y +6.1, R0.8 corners): its inner
  edge runs on the module's antenna boundary, 0.3 mm outside its ground pads, the antenna's
  ground-point (pin-1) side 0.7 mm from the right edge, and the cut runs 15 mm past its open
  (pin-45) end (ESP32-C5 Hardware Design Guidelines, Keepout Zone for ESP32-C5 Module's Antenna;
  datasheet Figures 10-1 and 11-1). No copper, on any layer, is left under the antenna. The
  module's ground pads along its ground edge (pins 46-60, by the antenna's feed) each take a via
  just inside the pad row, pins 1-2 by the ground point two more, and ground vias fence the notch's
  inner wall from in front of the antenna's open end to the tab, and the tab's wall over the notch
  (`route.py` `NOTCH_FENCE`, see The tab and the module's inner side). The module's capacitors
  C109 and C108 sit off its front-right corner and C107 by J2, all off the notch. The board's U13
  carries the footprint's antenna keep-out (on every copper layer) where its antenna is.
- **Pours and pad joins**: F.Cu and B.Cu carry ground pours over what the tracks leave. The
  board-wide pours and planes (ground on every layer, VBAT on B.Cu) join pads by thermal reliefs,
  0.25 mm gap, 0.2 mm spokes on the outer ground pours and 0.4 mm on the planes and on every
  through-hole pad, so a small part's pour end heats as fast as its track end in reflow; the pads
  that carry current or heat join solid: exposed pads and every pad of 1.2 mm2 and more, the power
  stages' pins (IC6, IC7, IC8, IC9, Q6), the pads inside the power paths' own pours, and 9 pads
  the pour reaches from one side only (`route.py` `relief()`, `RELIEF_STARVED`). Under each
  DRV8874's exposed pad a 4.0 x 5.6 mm B.Cu ground island, cut out of the VBAT pour, takes the
  heat of its 12 thermal vias (SLVSF66A section 10.1); the VBAT pour flows round it to the VM vias.
- **Ground stitching** (`route.py` `stitch()`, `prune()`): 441 ground vias in all. Every point where both outer layers are ground lies within 4 mm of a ground via or
  through-hole ground pad (a twentieth of the 2.4 GHz wavelength, TI SZZA009), and every island of
  outer ground pour over 2 mm2 has at least two, but for the pour within 0.6 mm of a ground pad or
  track (its join) and within 4.5 mm of C72.1 and C8.1 (see Open items). A stitching via goes only where all
  four layers are ground round it, so it cuts no other net's copper, In2.Cu's islands and hops
  included; the ground that no via can reach is cut out by 25 pour keep-outs (`no pour:
  unstitched`), and a 2 mm2 strip of F.Cu ground behind the right bridge that only one via
  reaches by one more (`no pour: island`).
  Two B.Cu keep-outs (`analog_keepoff`, fills only) hold the FAN_LSS pour 0.5 mm off
  CURRENT_L_AMP's B.Cu run beside the fan driver.
  One more keep-out on In2.Cu (`no pour: sliver`) drops a 7 um sliver of ground between the
  antipads of SWD1's pads 3-4 and a via beside them (JLCPCB's minimum feature width).
- **Teardrops** on every pad and via.
- **Vias in pads**: only the exposed pads' thermal vias open into a pad, and the board is ordered
  without a via-in-pad process (spec `[pcb] via_in_pad = "open"`). They are 0.2 mm holes (TI's
  PowerPAD via, SLVSF66A land pattern 4223595/B), 0.45 mm copper, left open on both sides (tenting
  a pad's via from the back traps air, TI SLUA271C section 3.4.1), at the via sites each footprint
  draws on Cmts.User (`route.py` `thermal_vias()`): 12 per DRV8874 on TI's 1.2 mm grid, 9 in the
  STSPIN958's pad, 4 in the STM32's, 4 in Q6's drain pad and 2 in the ADP7142's. Each of these pads' paste is split into
  windows clear of the sites, 51-64 % of the pad (SLUA271C section 4.4: 50-70 %): the DRV8874's in
  its footprint, the STSPIN958's, the STM32's and the HSBB3072's in `_SplitPaste` variants (their
  modules' `paste = "split"`), and the ADP7142's in its footprint (five windows, 54 %); the
  ESP32-C5 module's footprint draws 12 sites in the gaps between its nine ground squares (datasheet
  Figure 11-1, "Via for thermal pad"), off the squares themselves: those vias are tented on F.Cu, so
  the mask web between the squares stays and their solder has no open hole beside it, and open on
  B.Cu. Each square takes paste over its whole 1.2 mm (64 % of the 4.5 mm grid); the datasheet
  asks only for "the correct amount" (section 9: too much lifts the module off its signal pads).
- **Vias**: 0.45/0.3 mm for power and planes, 0.35/0.2 mm for signals (the escapes between the
  STM32's 0.4 mm pitch pins), 0.45/0.2 mm for the thermal vias; a 0.2 mm hole is above JLCPCB's
  0.15 mm minimum and below its 0.3 mm preferred size, which KiCad's DRC reports as a warning.
  JLCPCB charges more for a 0.2 mm hole with copper under 0.45 mm (PCB Capabilities page,
  accessed 2026-10-25): the 0.35/0.2 mm signal vias take that order option; the thermal vias'
  0.45 mm copper does not.
- **Ordering**: as a single board or on rails joined by breakaway tabs (mouse bites), not V-cut:
  SW4's pads are 0.20 mm from the outline, C100's and C103's 0.24 mm and U13's pad 46 0.30 mm,
  inside JLCPCB's 0.40 mm copper clearance to a V-score (`rules/jlcpcb-pdk.toml`
  `jlc.copper.minimum_vscore_clearance`), and snapping a scored rail beside an MLCC cracks it.
  Order note (assembly): trim every through-hole lead to 0.5 mm or less under the board after
  soldering. As fitted, J1's and M1-M3's leads stand 1.96 mm below the board, SW4's 1.17 mm and
  W1-W4's 0.41 mm, against a 0.7-0.85 mm gap to the floor (MicrasHardware `Board.bottom_z` 1.2 mm,
  less the skates); M2 also lies under the rear skate (for MicrasHardware to clear).
- **Countersinks**: the M2 screws come from under the board into 90 degree countersinks of 4.4 mm
  (spec `[countersink]`, MicrasHardware `params.Board.countersink_d`) that the owner cuts by hand,
  not fabricated: User.1 draws them and no fab output plots that layer
  (`tools/micras_pcb/jlc.py` `gerber_layers`; the drill files hold only holes). Keep-outs hold
  every layer's copper out of the cone: tracks, vias and pours 2.3 mm from each hole's centre on
  B.Cu and In2.Cu, 1.6 mm on In1.Cu; F.Cu keeps the hole's own clearance
  (`tests/test_main_layout.py` `test_countersinks_keep_the_copper_off`).

## Known faults

The board passes every gate, with 0 unconnected items and no DRC error. These ERC and DRC warnings
stay:

| Check (gate) | Fault | Why it stays |
|---|---|---|
| `drill_out_of_range` (drc, warning) | the 0.35 / 0.2 mm signal vias and the 0.45 / 0.2 mm thermal vias: a 0.2 mm hole under the 0.3 mm of the `jlc: via hole (preferred)` rule | above JLCPCB's 0.15 mm minimum, the board's choice for the escapes between the STM32's 0.4 mm pitch pins and for the open thermal vias (see [Layout](#layout), Vias); the `jlc: via hole` rule at error severity holds the 0.15 mm minimum |
| `silk_overlap`, `silk_over_copper` (drc, warning) | package artwork on its own outline and on the copper beside it, and outlines of neighbouring parts touching (the KiCad library passives keep their 0.12 mm outlines) | cosmetic: JLCPCB clips silkscreen at pads, and no reference designator is among them |
| `silk_edge_clearance` (drc, warning) | U13's outline over the antenna notch and SW4's at the switch notch run past the board's edge | the module overhangs its notch and the switch's lever sits at the cut corner by design; the fab clips the silkscreen at the edge |
| `same_local_global_label` (erc, warning) | pcb 0.4.81 labels a net that crosses a module sheet with a global label on the root and on the sheet, beside the sheet pin and the hierarchical label ([diodeinc/pcb#1520](https://github.com/diodeinc/pcb/issues/1520)): 48 warnings. The placement keeps the global label at each pin and draws the hierarchical one in the sheet's ports column (`boards/main/schematic/`) | the netlist is right (LVS passes); `erc.toml` accepts this rule at warning severity, with this reason, and nothing else. It goes away with a pcb release that includes [diodeinc/pcb#1522](https://github.com/diodeinc/pcb/pull/1522), which generates the sheet pins and hierarchical labels alone; then the `[accepted_warning]` table goes too |

## Open items

Each is a visible TODO in the sheet that owns it.

- Battery input: the B02B-PASK rating at about 5 A; which SW4 lever position is ON (the SK-12D29
  drawing does not say); the pack's short-circuit current against F1's 150 A interrupting rating.
- Emitter sink: a bench step across R83 to confirm the modelled response; the AO3400A's VGS at
  175 mA (Figure 2 or a measurement) and a cold check of the AC-coupled selectors' margin; the
  firmware's DAC timing against the selectors.
- Fan: the REF setting for the chosen motor.
- Analog copper within 0.5 mm of a switching node's pad or pour: 17 pairs, 0.18-0.49 mm, each a
  pin pair the parts put side by side (the INA241's IN+ beside VS, the DRV8874's VREF and IPROPI
  beside OUT1, the emitter sink's op-amp beside Q9), a nose line beside the emitter sink, whose
  node moves only at the selectors' edges and the DAC's steps, which settle before each receiver
  scan, or Current_Sensor_Right beside the buzzer driver's drain (R3.1, silent while the drive runs); `tests/test_main_layout.py` `SWITCHING_COPPER_EXEMPT` lists them with the gap they may
  not lose.
- Routing, round the escape rows: Current_Sensor_Right (62 mm: its run from C102 to R78 past the
  STM32's rear tip is the link's and the IMU's and encoders' corridor, so it goes round by the DIP
  switch and the buzzer, 0.43 mm from the buzzer driver's drain pad R3.1), Wall_Emitter_Set and
  Wall_Sensor_2 are longer than the layout tests' detour rule, and 18 analog /
  fast-digital pairs run closer than 0.45 mm for 0.1-16 mm each (the longest: 3V3_A beside
  Encoder_Right_ABI_B, the emitter set-point beside Encoder_Left_ABI_B for 9 mm; Fan_PWM, whose
  pin PA7 sits between the ADC pins 23-28, leaves the STM32 beside Battery_Voltage for 6.0 mm and
  Wall_Sensor_0 for 6.6 mm before a via site frees it);
  `tests/test_main_layout.py` lists them with the length they may not exceed. The ADC filter
  capacitors C102 and C105 sit 9-14 mm from their pins, where ST AN2834 section 4.2.8 asks for the
  pin: no 0402 fits within 3 mm of IC1.14 or IC1.30 outside the escape rows (the test is marked as
  an expected failure until they move).
- Routing: C72.1 (EC2's 100 nF) reaches ground only through the pour round it, boxed in by other
  nets' tracks (`PRUNE_SPARE`).
- Assembly: every through-hole lead trimmed to 0.5 mm or less (Ordering); M2's leads lie under
  MicrasHardware's rear skate.
- Buck: L3's 3V3_D pad sits 4.85 mm from the antenna's open end, against C54/C55, with M1/M2's
  courtyards in front and the notch behind. Further inboard means moving IC7, C53 and C54/C55 as
  well, at most 0.8 mm more (SW4's courtyard), and C53 then takes ESP_BOOT's only F.Cu lane
  between it and SW4's peg hole.
- Silkscreen: the KiCad library passives (stdlib 0402-1210, 0603 LED) keep their 0.12 mm outlines;
  U13's outline and SW4's run past the board's edge (the module over its notch, the switch's
  lever at the cut corner), where the fab clips them. The reference designators are 0.7 mm high
  with a 0.15 mm stroke, each within 1 mm of its part's courtyard, clear of the mask openings, the
  other silkscreen and the edge, and off every part's body (`silk.py`); 61 of the 190 have no such
  spot (the passives round the MCU and in the nose) and are hidden: the fab drawing (F.Fab) names
  every part.
- STM32 SMPS: C1/C2 sit 3.8-4.6 mm from VDDSMPS and C3/C4 6.5-7.1 mm from L1 and VFBSMPS (AN5419
  Rev 3 Table 2 asks for them "close"); `tests/test_layout.py` holds them to those reaches.
- VBAT bulk: C87, C92, C111 and C36 sit in the middle, off a 0.4 mm B.Cu spur of the pour, where the
  2.5 mm 1210 clears the drive blocks' 1.5 mm zones.
- JLCPCB rotations: unverified until the order's assembly preview.
- ADC pins: the CubeMX check of the ADC set-up on the swapped pins; R_iso + C_f stability.
- 3V3_A: the LDO's board-level thermal limit at about 0.33 W.
- 3V3_D: the L6981's slope-compensation bound (Eq. 38): read literally (ISLOPE = 1 A) it puts
  L3 below 0.4, as it does the datasheet's own 33 uH design; confirm ISLOPE or load-step the rail.
  On 5V_IN the duty reaches 0.87 and the loop needs ISLOPE above 0.177 A at fSW's 360 kHz
  minimum (0.22 A with L3 at -20 %), which both readings of the datasheet give.
- Status LEDs: blue and green at 3.2-3.3 V (bench).
- ESP32-C5: a range test in the chassis (a laptop and iperf, Espressif's end-product test) checks
  the antenna over the floor; the fallback is the ESP32-C5-WROOM-1U with a ground-independent
  dipole (a different footprint).
