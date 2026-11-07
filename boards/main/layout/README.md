# Main board

The Micras main board: the STM32H725RGV6 controller, a 4S
battery input with its fuse, VSYS behind a Schottky, separate digital and analog 3.3 V rails, two
DRV8874 wheel bridges with in-line INA241 current sensing, the STSPIN958 fan driver, the IMU,
the joints for four wall-sensor boards (boards/wall) on a shared emitter current sink, the slots
for the two encoder boards, the
ESP32-C5 dual-band radio, debug probe and data link with its flashing pads, and the user
interface. The board has no USB; a programmer's 5 V pin on the flashing pads or the SWD pads
(5V_IN) powers it for flashing without the pack.

The design is [research/next-revision/README.md](../../../research/next-revision/README.md): its
design basis (maxon DCX 10 L 4.5 V motors on a 4S pack, no boost; no USB; no 5 V rail), the options it recommends, and its connection lists A.1-A.6. The blocks it keeps are
the v1 main board's (MicrasPCB e34fb9a, `boards/main`), with their designators; new parts continue each series (C80-C114, D14-D15, D17,
IC8-IC9, J2, L4-L6, Q9, R58-R97, U8-U13), and the designators of removed parts are not reused.

The board is 91.15 x 50 mm (x 47.6 to -43.55 in the robot frame), 4 layers, 1.04 mm, every part on the
top side. Its mechanics are [`spec/main.toml`](../../../spec/main.toml): the outline, the screw
holes, the encoder slots, the wall joints, the fan hole and its low-part ring, the antenna and switch
notches, the parts that mate with the robot or the outline (IC1 among them) and the zones the chassis
takes over the board (see [Layout](#layout)). The robot fills the smallest turning circle the parts
allow, 49.46 mm round the axle: the nose (its front edge 18.2 mm wide between 4 mm corner arcs, with long chamfers meeting the sides in 4 mm shoulder arcs) holds the diagonal
wall sensors at the front, IC1 behind them turned 45 deg and partly over the fan ring (spec `[ic1]`:
x 32.35, its courtyard 0.73 mm from the fan hole and 1.82 mm from the diagonal joints' courtyards, for its
decoupling; the ring's silk breaks at its pads), and the frontal sensors beside it at y +-19.8; the parts ahead
of the fan hole's centre keep about the committed board's density (39.1 %, 34.5 % on the committed
outline). The rear edge sits where U13's antenna corner reaches the same circle; the module alone
would allow a rear edge up to -41.3 (its courtyard behind the right drive block's rear screw boss).
The front-row LEDs (D1, D2, D4/R4, D5/R5) move back 5.9 mm with the front edge, in the same
arrangement (owner, 2026-11-03).

## Files

The board files are in `boards/main/` (this README sits in its `layout/` folder).

| File | Sheet instance | Contents |
|---|---|---|
| [`main.zen`](../main.zen) | root | IC1 (STM32H725RGV6) and its supply network (C1-C17, L1, R67), the ST-Link pads SWD1 (NRST on pad 1, 5V_IN on pad 5), M2 screw holes H1-H4 |
| [`Regulators.zen`](../Regulators.zen) | `REGULATORS` | J1 battery connector with its fuse F1 and TVS D15, battery switch SW4/Q6, battery measurement R44/R45, VSYS diodes D14 (from VBAT) and D17 (from 5V_IN), 3V3_D buck IC7, 3V3_A LDO U8 |
| [`Drivers.zen`](../Drivers.zen) | `DRIVERS` | IC8/IC9 (DRV8874) bridges for M2/M1 with their 10 mOhm shunts R65/R75 and 47 uH chokes L4/L5, IC6 (STSPIN958) fan driver for M3 with its shunt R31 and 4.7 uH choke L6 |
| [`Sensors.zen`](../Sensors.zen) | `SENSORS` | IC2 (LSM6DSV) IMU, U10/U11 (INA241A2) current amplifiers, wall joints W1-W4 (the wall boards' 2x3 joints: receiver output, GND, 3V3_A, 3V3_D, sink, PWM) with the receivers' 1 kOhm loads R14/R18/R22/R26, the emitter current sink U12/Q9/R83 with its DAC set-point, encoder slots EC1/EC2 |
| [`Peripherals.zen`](../Peripherals.zen) | `PERIPHERALS` | SW1 DIP switch, SW2/SW3 buttons, R42 BOOT0 pull-down, BZ1 buzzer, D1/D2 (WS2812C-2427-V6) status LEDs, D4/D5 LEDs |
| [`Esp.zen`](../Esp.zen) | `ESP` | U13 (ESP32-C5-MINI-1-N4) with its decoupling, EN RC, GPIO28 pull-up, flashing pads J2 (`components/micras/EspProgPads`, 5V_IN on pad 2), and the links to the MCU with their series resistors R86, R88, R95, R96 and the ESP_CSn pull-up R97 |
| [`passives.zen`](../passives.zen) | | value, package, rating and part number of every resistor, ceramic capacitor and LED line |
| [`schematic/`](../schematic) | | how each sheet is drawn (`micras-pcb sch`): the root with IC1, its supply domains, the SWD header and the module sheets, and one file per module sheet, each block in a titled frame |
| [`erc.toml`](../erc.toml) | | nets supplied from off the board (BAT_P, GND, GND_BAT, 5V_IN) or through a passive part (VBAT, VSYS, 3V3_D, the LDO input, VDDA), the PWR_FLAG role for ERC; the two ERC warnings the module sheets leave until a pcb release includes [diodeinc/pcb#1522](https://github.com/diodeinc/pcb/pull/1522) (see [Known faults](#known-faults)) |
| [`firmware_changes.toml`](../firmware_changes.toml) | | the firmware changes this board needs against the v1 firmware (see [Firmware changes](#firmware-changes)) |
| [`test/`](../test) | | `pcb test` benches: MCU and ESP links, power, drivers, peripherals |
| [`layout/`](.) | | this folder: the KiCad project; `main.kicad_sch` is the root sheet, with one sheet per module (`REGULATORS.kicad_sch`, ...); the `.kicad_pcb` holds placement and routing; `place.py` places every part, `route.py` pours the planes and routes the board and `silk.py` places the reference designators (see [Layout](#layout)) |
| [`spec/main.toml`](../../../spec/main.toml) | | mechanical interface: thickness, axle origin, outline, screw holes, encoder slots, wall joints, fan hole and fan ring, wheel, antenna and switch notches, the ESP32 module's, battery switch's and wall joints' positions, the chassis zones, the silkscreen it draws (fan ring, drive blocks); the via-in-pad order option |

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
5V_IN (a programmer's 5 V pin: J2 pad 2, SWD1 pad 5) ─ D17 B5819W ─ VSYS
      VSYS ─┬─ IC7 L6981C33 ─ 3V3_D: MCU VDD, ESP32, IMU, encoders, LEDs, emitters
            └─ R58 22 Ω + C80 10 µF ─ U8 ADP7142 3.3 V (EN = 3V3_D) ─ 3V3_A: VDDA (R67 0 Ω),
                  INA241 VS/REF1, phototransistor collectors, emitter-sink op-amp and its bias
```

- **VSYS** is VBAT behind D14, or 5V_IN behind D17, and feeds only the two regulators. D14 keeps
  5V_IN off VBAT, the bridges' bulk and the pack; D17 keeps the pack off the programmer.
- **No USB**: every rail comes from J1 but for flashing. 5V_IN takes a USB-serial adapter's or a
  clone ST-Link's 5 V pin (never its 3.3 V one) on J2 pad 2 or SWD1 pad 5 and runs the 3V3 rails
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
- **Current**: INA241A2 (gain 20) on each shunt, VS and REF1 on 3V3_A, REF2 on GND: 0.2 V/A
  around VDDA / 2, +7.25 / -8.15 A at 3V3_A 3.3 V, into PA6 (left, a fast ADC channel) and PC1 (right)
  through 150 Ohm (R78/R79, R_iso), with 1 nF X7R on the ADC line (C102 3.5 mm from PC1, C105
  beside R79, 21 mm of track from PA6); the firmware samples them
  for at least 0.7 us, so the ADC's kickback from a wall-sensor conversion settles below 1 mA.

## Fan

STSPIN958 in parallel half-bridge mode, PWM trimming, on TIM14 at 400 kHz: R31 25 mOhm, REF from
4.7k/2.0k on 3V3_D (current limit 3.94 A), RSR 1 kOhm (2 V/ns), 2 x 470 nF 50 V X7R 0805 +
2 x 10 uF 50 V on VS, CBOOT 1 uF 50 V X7R (the IC runs hot), and a 4.7 uH XGL5030-472 choke between FAN_OUT and the motor. Fan_PWM on PA7 (TIM14_CH1), Fan_TOFF on PB10; Fan_Enable on PB12, driven open drain and read back as the driver's nFAULT.

## Sensors

- **Wall sensors**: each sensor is a wall board (`boards/wall`) standing on a wall joint W1-W4
  (`components/micras/WallJoint`, no slot): a 2x3 1.27 mm straight header (HX PZ1.27-2x3P ZZ)
  straddles the wall board's bottom edge, its insulator sits on the main board and its long pins are
  soldered in the joint's 2x3 plated holes (0.70 mm drill, 1.10 mm pads), the pattern's centre
  under the wall board's mid-plane. Pad n is the header's pin n, odd pins in the front row: 1 the
  receiver output (Wall_Sensor_n), 2 GND, 3 3V3_A, 4 3V3_D, 5 EMITTER_SINK, 6 PWM
  (Wall_Sensor_PWM_n, the selector's TIM3 channel) (`tests/test_wall_joint.py`). Each joint's
  courtyard is the header's insulator and 0.25 mm, 4.31 x 3.9 mm; the wall board is a paddle (4.2 mm
  handle, 6.1 mm neck, 8.4 mm blade), and parts under its 8.4 x 1.99 mm overhang stay at or below
  2.55 mm (spec/wall.toml joint.under_blade); W1/W4's boards stand 1.0 mm inside the side edge (owner's
  choice). The frontal sensors W1/W4
  look forward from (33.5, +-19.8), the diagonal W2/W3 at 45 degrees from (37.91, +-7.37), ahead of
  IC1; every lens stays 1.0 mm or more inside the outline (W1 1.00 mm, W2 1.34 mm), so the board's
  edge meets a wall first, and no sensor stands in another's view; each sensor's printed case
  (MicrasHardware `micras/front.py`, the sensor caps: slid on from the front, the lenses and the
  wall board's front grown by the bore's 0.25 mm fit and the 0.8 mm wall, nothing behind the board)
  stays 0.3 mm from every other case (W1-W2 0.77 mm), 0.5 mm out of every other sensor's view
  (0.81 mm) and inside the outline (0.29 mm); under a case only parts up to 3.0 mm, and in a view
  corridor nothing above its lower edge less 0.5 mm (`tests/test_main_layout.py`) (spec/main.toml
  [w1]-[w4], tests/test_wall_joint.py). Each wall board carries its
  SFH 4550 emitter, from 3V3_D through 3.3 Ohm (which keeps a failed sink's current inside the
  emitter's pulse rating), and its AO3400A selector, AC-coupled as on the v1 main board (220 Ohm,
  220 nF, 22 kOhm pull-down, 1N4148WS clamp: a pin held high turns its emitter off within
  7.5-11 ms; `boards/wall`). The selectors' sources share the main board's constant-current sink
  on EMITTER_SINK: TLV9001 + AO3400A + 1.2 Ohm 0.1 %, its set-point the DAC on PA5 through 200k/20k
  (175 mA near code 3258, 223 mA full scale, 0 V at reset), compensated by 1 kOhm / 1 nF and biased
  off at a zero set-point by 200 kOhm from 3V3_A. The phototransistor collectors are on 3V3_A, and
  each receiver's 1 kOhm load sits on the main board at its ADC line (the phototransistor is a
  current source: the signal crosses the joint as a current).
- **IMU** and **encoder slots**: as on the v1 main board, on 3V3_D.

## ESP32 radio

- **ESP32-C5-MINI-1-N4** (U13), dual-band (2.4 and 5 GHz) Wi-Fi 6, on 3V3_D with 22 uF + 100 nF
  strapped to its 3V3 pin (Layout, The tab and the module's inner side) and 10 uF on its feed, EN
  RC 10 kOhm / 1 uF, GPIO28 (the boot strap) pulled up.
  Its PCB antenna overhangs the rear-right notch, the antenna's ground-point end (pin 1, the
  pad-62 corner) 0.7 mm from the right edge and 15 mm of board cut away beyond its open end
  (pin 45) (spec `[antenna_notch]`).
- **Flashing pads J2** (`components/micras/EspProgPads`: six plated holes, 2x3 at 1.27 mm, no part
  in the BOM), for a USB-serial adapter's wires soldered once, or a 2x3 1.27 mm header fitted by
  hand, in the ESP-Prog Program interface order: 1 EN, 2 5V_IN, 3 TX0 (GPIO11), 4 GND, 5 RX0
  (GPIO12), 6 GPIO28. Hold 6 low and pulse 1 for the ROM's UART download mode; the console is on
  3/5. Pad 2 takes the programmer's 5 V (an ESP-Prog with its jumper at 5 V, or a USB-serial
  adapter's 5 V pin) and powers the board through D17; no pad reaches 3V3_D. A fitted header has
  no shroud: a plug turned round puts the programmer's 5 V on pad 5 (RX0, the C5's GPIO12, no
  resistor) and its ground on pad 3 (TX0). The C5's inputs take at most VDD + 0.3 V (datasheet
  v1.4 Table 6-3), so that plug can destroy the module: the silkscreen marks pad 1 ("1") and pad 2
  ("5V") beside the pads; there are no protection parts. The pads sit at a board edge the robot
  leaves open, easy to reach.
- **Links to the MCU** (C5 GPIOs free of strapping and other roles, off with no pull at reset):
  SWDIO GPIO0 -> PA13, SWCLK GPIO1 -> PA14 (22 Ohm), NRST GPIO23 (open drain); SPI3 half-duplex
  on three wires, the MCU the master: ESP_SCK PC10 -> GPIO10 (R95 22 Ohm), ESP_DATA PC12
  (the MOSI pad, IOSWP = 0) <-> GPIO8 (R96 220 Ohm), ESP_CSn PC11 -> GPIO9 (R88 100 Ohm,
  R97 100 kOhm pull-up to 3V3_D), the resistors mid-line; ESP_Flow GPIO24 -> PA11, the C5's credit line. UART4
  is the fallback on PC10/PC11 with no board change.
- **ST-Link pads** SWD1, at a board edge the robot leaves open, out of the fan ring: five bare
  1.27 mm pitch pads, 1 NRST for the probe's RST wire, then the clone ST-Link lead's order, 2 SWDIO,
  3 GND, 4 SWCLK, 5 5V_IN (the probe's 5 V pin), for a probe when the ESP32-C5 cannot reach the
  MCU; the lead plugs on pads 2-5. A misplugged lead can put its 5 V on a pin rated for less
  (main.zen lists each case with DS13311 Tables 10-11): on SWCLK (lead on pads 1-4), on SWDIO
  (turned round, the C5's GPIO0 with no resistor), on NRST (turned round on pads 1-4: above the RST
  pin's 4.0 V and the C5's GPIO23's VDD + 0.3 V, datasheet v1.4 Table 6-3), or on GND with the
  probe's ground on 5V_IN (turned round on pads 3-6, which drives SWCLK below VSS); one contact past
  pad 5 puts it on no pad. Nothing protects the header (the owner's choice): the square pad 1 and
  "5V" at pad 5 set the lead's place and way round. BOOT0 stays low (R42): the MCU always starts
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
  and NRST to the C5 (PA13/PA14 and NRST also to the header SWD1).
- **Sensor bus**: SPI2 on PB13-PB15; chip selects Encoder_Left_CSn PA9, IMU_SPI_CSn PA8,
  Encoder_Right_CSn PB8; IMU_INT on PC7 (EXTI7, the IMU's INT1; INT2 unconnected).
- **Wall sensors**: selectors on TIM3 on the rows facing their emitters (PC9 CH4, PB0 CH3 on the
  left; PB4 CH1 Wall_Sensor_PWM_3, PB5 CH2 Wall_Sensor_PWM_2 on the right); the emitter DAC on PA5
  (DAC1_OUT2); Wall_Sensor_0 on PA4, Wall_Sensor_1 on PA3, Wall_Sensor_2 on PB1 and Wall_Sensor_3 on
  PC0. No wall input is a package neighbour of Fan_PWM (PA7, pin 26): its neighbours are
  Current_Sensor_Left (PA6) and Button (PC4).
- **ADC**: Current_Sensor_Left on PA6 (a fast channel), Current_Sensor_Right on PC1, each with an
  ADC1 and an ADC2 input; the battery divider on PC5 (ADC12_INP8).
- **Fan**: Fan_PWM on PA7 (TIM14_CH1), Fan_Enable on PB12 (open drain, its fault on EXTI12),
  Fan_TOFF on PB10.
- **User interface**: LED_ARGB on PA2 (TIM15_CH1, DMA on tim15_up), the buzzer on PB9
  (TIM17_CH1), LED_Red on PB2, Button on PC4 (EXTI4), Switch_0-3 on PH0, PH1, PC15 and PC14 (the MCU has
  no VBUS input).

Every GPIO of the VFQFPN68 is used.

## Firmware changes

[`firmware_changes.toml`](../firmware_changes.toml) lists what the firmware must change against
the v1 firmware (`firmware.toml`, from MicrasFirmware):
PH/EN drive at 100 kHz with TIM8 slaved to TIM1; Motors_Enable on PD2 as nSLEEP (1 ms wake);
Motors_nFault on PB6, sharing EXTI9_5 with IMU_INT; a stalled wheel cut within 5 s; INA241
sampling on TIM1 TRGO2 with dual injected ADC1/ADC2; the battery divider constant 11.0 on PC5 and
a "no pack" reading on 5V_IN; Switch_0 on PH0; the H7's HSI measured against the ESP32-C5's crystal
over the link (no crystal on the MCU), the C5 kept running in contest mode with its radio off; the
fan at 400 kHz with Fan_PWM on TIM14, its duty at most 88.8 %, Fan_TOFF (low during the limiter's
decay) sampled by DMA in step with the PWM, a start at 50 kHz, a jam rule at 400 kHz and a stop by
Fan_Enable (coast), Fan_Enable on PB12 open drain and its fault on EXTI12; the SPI3 half-duplex
link to the ESP32-C5 (ESP-IDF v6.0.3 or later, AFCNTR, the data line on the MOSI pad, /8 to start,
a turn-around with no driver overlap, UART4 as fallback) with ESP_Flow credits on PA11; the IMU and
encoder bus on SPI2, mode 1 for the encoders and mode 3 for the IMU; the gyroscope at +-2000 dps;
Button on PC4; the LEDs on TIM15 and the buzzer on TIM17; the C5's slow clock on its RC, its pulls
and its resync after an MCU reset; one wall emitter at a time on TIM3, with the emitter DAC on PA5
stepping with each selector and a code per emitter, and no LED, SPI or buzzer traffic during an
emitter's pulse and scan; the current channels sampled for at least 0.7 us; the WS2812C timing
(T0L/T1L at most 1 us); slow output edges on the buses and every free-running PWM pin; flashing
over Wi-Fi through the ESP32-C5's CMSIS-DAP-over-TCP or Black Magic probe, nRESET on its GPIO23
(open drain only, released before it is enabled), a 10 ms wait for NRST's slow rise, and the C5
held in reset (J2 pad 1 to pad 4) when an ST-Link uses SWD1; TIM1/TIM8/TIM14 frozen and the drive
enables cleared on a debug halt; the LSM6DSV's I2C disabled at boot and its interrupts all routed
to INT1.

## Layout

[`place.py`](place.py) places every part, [`route.py`](route.py) pours the planes and routes
the board, and [`silk.py`](silk.py) sizes and places the reference designators; their docstrings
give the rules they follow. The `.kicad_pcb` holds their result with
the connections they left routed by rip-up scripts and by hand, under the same rules. Every
connection is routed, and DRC, DFM and the layout tests pass.

- **Placement**: every part on the top side. The spec places what mates with the robot or the
  outline; the ESP32-C5-MINI-1 sits in the rear-right corner (spec `[u13]`), its pads on the board
  and its antenna over a notch cut out under it and beside it (see Antenna), each DRV8874 by
  its motor with its shunt, choke and bulk capacitors, the IMU between the encoder slots on the
  axle, the MCU and the wall-sensor channels in the nose, and the fan driver, DIP switch, buzzer
  and 3V3_A LDO beside the fan hole.
- **Rear-left corner** (beside SW4): the battery input. J1 sits by the left
  edge, its BAT_P pin behind its GND_BAT pin; its lead goes back to the pack over the low wall
  behind the left drive block (MicrasHardware `frame.py` cuts a `wire_slot` only in a full wall,
  15 mm in front of J1). F1 lies just behind the left drive block's zones (spec
  `[drive_blocks]` `body_left` and `clamp_left` end at x -22.2, F1 spans x -31 to -27), D15 and D14 beside it, Q6
  by the rear screw boss with its sources and gate toward the board's centre and its drain toward
  the edge, its gate network (R41, R43, C58, C114) in front of the gate: the chain R43 - R41 - C58 - C114 - Q6.1 runs
  below and inboard of R41's and C58's GND_BAT pads, which the GND_BAT pour reaches round SW4's front peg.
- **The 3V3_D buck** by the right wheel beside the fan hole, laid out as ST's application board (DS13554
  Rev 3 Figures 32-33: the inductor at the SW pin, the input capacitor at VIN, the BOOT and VCC
  capacitors at their pins, ground poured round them): L3 behind the chip, and IC7 turned so its SW
  pin (1) is the corner nearest L3's SW pad. The switch node is one 0.8 mm F.Cu track of 3.8 mm from
  pin 1 to L3, with no via (`test_switch_nodes_are_compact`). The SW/BOOT/VCC/FB row faces the right
  edge, C55 (BOOT) and C54 (VCC) under pins 1-3, and C56 (22 uF) under them on a 0.8 mm F.Cu strap from
  L3's output, beside the 3V3_D line forward along the edge that FB (pin 4) senses. The VIN row faces
  the fan hole: C53 (1 uF) lies across VIN (pin 7) and PGND (pin 8), inside the fan ring (1.25 mm high,
  the ring's limit, spec `[fan_ring]`), each pad 0.5 mm from its pin on a straight F.Cu track (VIN
  0.5 mm, PGND 0.6 mm wide), so the input loop is VIN - C53 - PGND on F.Cu alone, with a ground via
  between C53's pads. AGND (pin 6) runs up beside C53 to two ground vias. VSYS comes from C52 under
  the chip to EN (pin 5) and VIN, and on under the chip past PGND to R58; 3V3_A runs from C81 inboard of C53.
  The 3V3_A LDO (U8, C80, R58) sits inboard of L3, its output capacitor C81 between U8 and the fan
  hole beside C53, U8's 3V3_D (EN) line passing between C81's pads; C57 is
  L3's second 22 uF, on the 3V3_D trunk behind it.
- **The tab and the module's inner side**: the flashing header J2 sits in the tab between the two
  notches, its pads 17 mm from the antenna's open end (at least 10 mm) and reachable from the
  robot's rear, with the 10 uF C107 on U13's 3V3_D feed beside it; the EN RC (R89, C110) and the BOOT pull-up R90
  sit off the module's front-right side, because the right motor's OUT2 and TERMINAL paths pass
  under J2, and the B.Cu VBAT pour stops short of J2 so its lines reach the module on B.Cu. EN, TX0, RX0 and BOOT run inboard
  on B.Cu, past the notch's wall, to the module's pins 45/39/40/4. Ground vias fence the notch's
  inner wall (x -39.7, 0.4 mm from the cut, at 1.6-1.8 mm pitch from in front of the antenna's open
  end to the tab) and the tab's wall over the notch (y +6.5) (`route.py` `NOTCH_FENCE`). U13's 3V3
  pin (pin 3) and BOOT pin (pin 4) lie on the module's edge row, 0.6 mm from the board's edge: each
  leaves by a stub to vias inside the row and runs on B.Cu under the module. 3V3_D comes from L3's
  output patch on a 0.8 mm B.Cu feed under the module to two vias at pin 3, and a 1.0 mm B.Cu strap
  from those vias along the edge row joins the 22 uF C109 and 100 nF C108, which sit off the module's
  front-right corner with two vias each, 13-16 mm from the pin: no capacitor fits nearer it (the
  edge, the antenna end and the ground pads), and the module decouples its chip itself (datasheet
  Figure 8-1). SWCLK's series resistor R86 sits at the module's front end. The link's series
  resistors sit mid-line: R95 (ESP_SCK) and R96 (ESP_DATA), with the ESP_CSn pull-up R97 beside
  them, about 24 mm of track from the STM32's rear tip, and R88 (ESP_CSn) about 35 mm from it and
  37 mm from the module. The lines are electrically short at their edges (about 0.4 ns of line
  against 4.2 ns edges), so the resistors work anywhere along them (`Esp.zen`).
- **Planes**: In1.Cu is ground over the whole board; In2.Cu is ground but for the STM32's two supply
  islands, each only as big as its job (`route.py`): 3V3_D (`mcu_3v3_outline()`) is the square under
  the chip out to its pin tips with a tab to the via of each 3V3_D pin (VBAT, VDDSMPS, VDD); VCORE
  (`vcore_outline()`) is a band outside the pin tips' vias that only reaches VCORE's vias (VFBSMPS,
  VCAP1-3, C3-C7, L1) and stops either side of the chip's rear tip. By hand, the 3V3_D island's tab at
  VDD pin 9 also takes C12's via, and the VCORE band steps back round it. The signals' escape vias just
  past the pin tips sit between the two islands, and the lines that leave them on B.Cu run over the
  islands: B.Cu's reference plane is In2.Cu, so over an island a line's return runs in that island,
  not in In1.Cu's ground, which lies beyond In2.Cu and does not shield them. Over VCORE: Wall_Sensor_3
  9.4 mm, Wall_Sensor_2 8.6 mm, Battery_Voltage 5.0 mm, Current_Sensor_Left and Current_Sensor_Right
  2.4 mm each, the other wall lines 1.0-1.4 mm, and 1-7 mm of digital lines (the DIP switch,
  encoders, IMU, motor and buzzer lines); over 3V3_D only Wall_Sensor_1's 0.6 mm. Both islands are
  decoupled to ground at the STM32's pins (C3-C12), so a line over them couples into the islands'
  own noise (VCORE's SMPS ripple), not into a floating plane. B.Cu carries the VBAT pour over
  the power entry and both bridges, and no other net's track runs on B.Cu inside it.
- **Tracks**: F.Cu and B.Cu, octilinear. The power paths (`ROUTES` in `route.py`) are wide and
  locked; signals are mostly 0.12 mm (86 % of their length), 0.15 mm on some runs (11 %) and
  nowhere narrower, at 0.10-0.11 mm clearance. A switching net keeps 0.5 mm from an analog net on the same layer,
  tracks, pads and pours alike, but for the pin pairs and nose lines in Open items.
  No track or via ends open.
- **Round the fan hole**: the lines that pass the hole leave the STM32's two rear faces in pin order,
  each escape on its pin's normal to a via 0.8 or 1.25 mm past the pad (alternate pins), and run as
  two ordered streams per side on octagonal lanes concentric with the hole, 0.24 mm apart from a
  7.76 mm apothem out (`reports/scratch/agentC3/plan.png`): on the right, F.Cu SWCLK,
  Encoder_Right_ABI_A, ESP_SCK, ESP_CSn and ESP_DATA and B.Cu Encoder_Right_ABI_B, Motors_Enable,
  Motors_nFault, Motor_Right_PH and Encoder_Right_CSn; on the left, F.Cu ESP_Flow, Motor_Right_EN,
  Motor_Left_PH, Encoder_Left_CSn, the SPI2 bus (MOSI, MISO, SCK) and Fan_Enable, and B.Cu SWDIO,
  IMU_SPI_CSn, IMU_INT and Motor_Left_EN (the inner lane first). Behind the hole each stream
  peels off outer lane first, so no lane crosses another.
  Where a lane passes nearest the hole (the middle of each octagon face) the stacks step 6 um out
  over 0.6 mm with nested 45-degree jogs, so their copper keeps the DFM's 0.200 mm to the hole as
  the fab's tessellated arc puts it, and a pour keep-out (`no pour: fan hole edge`) holds the
  ground pours 0.25 mm off it.
- **SWD1** (the rear tab): the B.Cu VBAT pour's tab stops at x -39.1 (C111 stays on it) and its
  strip along the rear edge at x -36.0, so Reset and SWDIO leave pads 1-2 on B.Cu as nested Ls and
  run 0.24 mm apart along the rear edge outside the pour; SWCLK leaves pad 4 on F.Cu between C111's
  pads and between C84 and C87 to its run round the left side, clear of SW4's pins.
- **Nose** (`reports/scratch/agentC5/plan.png`): the crossings left to right are VBAT (C112 to R44,
  C96 and D14) and 3V3_A (W3, R67, W2, the left cluster) on F.Cu, and the emitter sink on a B.Cu
  lane at x 46.9 under the LED row (W2.5 out along x + y = 48, W3.5 in along y -6.92, 0.5 mm off
  the joints' analog pads); the LEDs' ground pads join the F.Cu pour, the LED row's 3V3_D comes on
  F.Cu from one via behind C96. B.Cu is then free from the STM32's tip to the LED row: LED_ARGB
  runs 8.8 mm straight to D1 with two vias, and Wall_Sensor_2 crosses in front of the tip on F.Cu
  (C11 sits by C10). Encoder_Left_ABI_A/B leave the tip on B.Cu under the front-left pad row past
  the left vertex; Wall_Sensor_PWM_0 (pin 42) runs in the free B.Cu slot of the left
  stream (between IMU_SPI_CSn and IMU_INT) and crosses the stream's B.Cu lanes square on an In2.Cu
  hop just outside the VCORE band (C6's ground joins C15's via).
- **Front-left face** (pins 18-34): the escape vias of pins 24-31 alternate 0.8 and 1.3 mm past the
  pads. Under the pad row on B.Cu (inside the STM32's outline, beside Encoder_Left_ABI_A/B) three
  lanes run to the left vertex, each pin's leg entering on its pin's normal, the tip-side pin
  innermost: Current_Sensor_Left (pin 25) on x + y = 36.2, Fan_PWM (pin 26) on 37.05 and Button
  (pin 27) on 37.75 (robot frame), Fan_PWM 0.48 mm from the analog line beside it (the legs, under
  the pads, are the pins' escapes). Past the vertex Button goes to SW2, Current_Sensor_Left to R79
  and C105 and Fan_PWM to the fan driver; at IC6 it rises inside 3V3_D's loop round pins 10-13 on a
  via 0.2 mm from the loop. Outside the row the wall lines leave forward and to the side
  (Wall_Sensor_1 from pin 20 to W2, Wall_Sensor_0 from pin 23 to W1, Wall_Sensor_2 from pin 30 in
  front of the tip to W3), with the emitter set-point (pin 24), the battery divider (pin 28),
  Wall_Sensor_PWM_1 (pin 29) and LED_Red (pin 31), crossing on F.Cu and B.Cu by vias outside the
  row. Fan_PWM and the buzzer keep 0.45 mm from every wall receiver's line, escapes included
  (`test_fan_and_buzzer_keep_clear_of_the_wall_sensors`).
  The fan driver's 3V3_D pins join on B.Cu above the fan motor's B.Cu band, which no track
  crosses.
- **Front-right quadrant** (`reports/scratch/agentC4/plan.png`): the DIP switch's lines (pins 2, 3,
  10, 11), Wall_Sensor_3 (pin 13) and Current_Sensor_Right (pin 14) leave the front-right face and the
  selectors' and the buzzer's lines (pins 59, 60, 65) the rear-right face, routed in one order
  (Current_Sensor_Right, Wall_Sensor_3, Wall_Sensor_2, Wall_Sensor_PWM_3, Switch_3 to Switch_0,
  Wall_Sensor_PWM_2, the buzzer): the switches and Wall_Sensor_3 run on B.Cu down the channel
  between the SMPS capacitor row and W3, step past D17/D14 and follow the emitter sink's B.Cu
  diagonal to W4 and into SW1's pads from inside; Switch_0 goes round W3's front;
  Current_Sensor_Right and Wall_Sensor_PWM_2 cross under the STM32's pad rows on B.Cu. The buzzer
  (a fast line, its TIM17 PWM) runs on B.Cu 0.45 mm or more beside Current_Sensor_Right from pin 65 to
  the tip, then in front of it to the right edge and R1.
  L1 sits 0.04 mm along the face from the row's grid so Switch_3's escape via clears its LX pad.
- **Long analog lines**: CURRENT_R_AMP and ESP_SCK_IO cross the fore-aft 3V3_A (F.Cu) and 5V_IN
  (B.Cu) lines behind the buck through a 2 mm jog in 5V_IN; CURRENT_L_AMP leaves U11's output pin
  through a notch in the B.Cu VBAT pour (`route.py` `VBAT_POUR`) and runs round the left side.
  3V3_A steps 0.225 mm in by U8 so LDO_IN keeps 0.3 mm from it.
- **IMU**: no via and no F.Cu track lies under the LSM6DSV's body but each pad's own stub, leaving it
  outward (ST TN1383 sections 3.3-3.5: copper under a MEMS sensor stresses it unevenly with
  temperature); the bus's vias sit past the body's edges, its branches to the encoders run on B.Cu,
  and ground pins 6-7 join outside the body to C25's ground via
  (`test_imu_body_is_free_of_vias_and_tracks`).
- **IMU and encoders' 3V3_D**: a 0.12 mm F.Cu feed (about 35 mA) round the left side from the fan
  driver's 3V3_D to the IMU's cluster, which the streams behind the hole cut off from the buck.
  SWCLK reaches R86 round the bridges (an In2.Cu hop, then B.Cu behind the buck), which leaves
  IC8's GND pin 7 its F.Cu link to the exposed pad.
- **Power copper**: the battery path is poured for 10 A: J1's BAT_P pin to F1 as a BAT_P pour round
  J1's GND_BAT pin, nothing else on BAT_P before the fuse, at least 2.9 mm wide from pin to pin
  (IPC-2221's external width for 10 A at a 45 C rise; the BAT_P, GND_BAT and VBAT pours are checked
  by a morphological opening, `tests/test_main_layout.py` `test_battery_pours_keep_their_width`); F1's VBAT side a pour with 21 vias to the
  B.Cu VBAT pour's left appendage, D15, D14 and IC9's bulk C93 on it; GND_BAT poured on F.Cu and
  B.Cu from J1 to Q6's sources and D15 with 24 vias; Q6's drain in a ground pour along the edge
  with its field of 12 vias. The battery switch's drive and its VBAT feed reach SW4 on B.Cu between the
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
  VM pin joins its 100 nF (C82, C91) and, past it, the VCP capacitor's VBAT pad (C88, C97) on F.Cu:
  three vias to the pour on the pin's own copper, one beside the pin and two at the VCP capacitor
  (`test_power_paths_carry_their_current` counts only vias joined to the pin by copper on its layer). The fan driver
  (STSPIN958) is turned so its power side faces the board's edge and its logic pins the fan hole
  (DS14341 Fig. 23). Its pins open into F.Cu pours: OUT1 (pins 31-32) to the choke L6, VS (pins
  27-30) up to the two 470 nF (C34, C35) 2.95 mm from the pins, with 6 vias behind them to a B.Cu VBAT pour that comes
  from the bridges' pour along the left wheel cut-out, OUT2 (pins 25-26), LSS1 (pins 1-2) and LSS2
  (pins 23-24, with R31's LSS pad 2.3 mm from pin 24 and the fan connector's return M3.2). OUT2 joins
  OUT1 and LSS1 joins LSS2 through 6 + 6 and 5 + 5 vias and two nested B.Cu pours under the power-side
  pins, outside the exposed pad and its nine thermal vias; L6's motor end reaches M3.1 through 5 vias
  and a B.Cu pour round the logic side. The pump and boot capacitors (C32, C33) sit at their rear
  pins; FAN_SR leaves pin 21 by a via between the LSS2 pour and R31, whose ground pad joins the
  button's ground pad. SMPS_LX runs straight to L1 on F.Cu and BUCK_SW to L3 (see The 3V3_D buck).
  R58 (the 3V3_A LDO's input RC) sits by C80 and U8, VSYS reaching it from under IC7 on F.Cu. R75 is turned so OUT1 enters its front pad
  straight from IC9 and MOTOR_L_SHUNT leaves its rear pad toward L5; R65's OUT1 pad is its rear one.
  Each INA241's Kelvin lines run as a pair: the far sense line crosses under the shunt's body on
  F.Cu, between the force pads, to a via beside the near one's, and both run on B.Cu 0.4 mm apart
  to the amplifier's corner; the loop they close, pad to pin and back, is 10.6 mm2 (R65) and
  8.8 mm2 (R75), set by the WSK2512's sense pads in opposite corners and IN+/IN- on opposite rows.
  The VBAT pour leaves a slot under R75's rear half for its pair; Reset keeps outside R65's.
- **In2.Cu hops**: an exception where F.Cu and B.Cu have no room, not a routing layer: 50 mm on
  13 nets (Boot, ESP_BOOT, ESP_SWCLK, ESP_Flow, Motor_Right_EN, Reset, the SPI2 bus, SWCLK, SWDIO,
  Switch_0, Wall_Sensor_PWM_0), 200 mm at most in all. A hop carries a digital line of the STM32 or the ESP32
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
  stages' pins (IC6, IC7, IC8, IC9, Q6), the pads inside the power paths' own pours, and 5 pads
  the pour reaches from one side only (`route.py` `relief()`, `RELIEF_STARVED`). The hand-soldered
  ground pins (the wall joints' pin 2, SWD1 pin 3, J2 pin 4) take their joins from
  `rules/jlcpcb.kicad_dru`: 0.25 mm gap, 0.4 mm spoke reliefs on B.Cu and the inner planes, so the
  iron heats the joint and not the planes, and solid on F.Cu, which the pour reaches from one side.
  Seven small parts whose pour pad the pour reaches from one side (R2, D4, C30, R30 on ground, C58
  and R41 on GND_BAT, R44 on VBAT) join it by one or more 0.2 mm spokes, one allowed (the rules'
  `min_resolved_spokes`), so both their pads heat alike in reflow
  (`test_small_parts_pads_heat_alike`). Under each
  DRV8874's exposed pad a 4.0 x 5.6 mm B.Cu ground island, cut out of the VBAT pour, takes the
  heat of its 12 thermal vias (SLVSF66A section 10.1); the VBAT pour flows round it to the VM vias.
- **Ground stitching** (`route.py` `stitch()`, `prune()`): 346 ground vias in all. Every point where both outer layers are ground lies within 4 mm of a ground via or
  through-hole ground pad (a twentieth of the 2.4 GHz wavelength, TI SZZA009), and every island of
  outer ground pour over 2 mm2 has at least two, but for the pour within 0.6 mm of a ground pad or
  track (its join) and within 4.5 mm of C72.1 and C8.1 (see Open items). A stitching via goes only where all
  four layers are ground round it, so it cuts no other net's copper, In2.Cu's islands and hops
  included; the ground that no via can reach is cut out by 15 pour keep-outs (`no pour:
  unstitched`), and three B.Cu pieces (under the STM32's front-left pad row, by W4 and between W2
  and the battery divider's lines) by three more (`no pour: island`).
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
  the wall boards' header pins 2.71 mm, against a 0.7-0.85 mm gap to the floor (MicrasHardware `Board.bottom_z` 1.2 mm,
  less the skates); M2 also lies under the rear skate (for MicrasHardware to clear).
  JLCPCB prints no paste on the parts the team solders itself (`assembly = "hand"` in
  `parts/jlc.toml`: IC1, IC2, IC6, IC7, U13 and D4; J1, M1-M3 and SW4 are through-hole): `make fab`
  plots the package's paste layers from a build copy of the board without their paste, footprints
  and layout untouched, and writes their paste alone, both faces with the outline, to
  `build/main/fab/main-team-stencil.zip`, outside the JLCPCB package, for a stencil the team orders
  or cuts (`tests/test_fab.py` checks both). Finish leaded HASL, green mask, white silkscreen
  (`main.zen`, `build/main/fab/main-order.txt`).
- **Countersinks**: the M2 screws come from under the board into 90 degree countersinks of 4.4 mm
  (spec `[countersink]`, MicrasHardware `params.Board.countersink_d`) that the owner cuts by hand,
  not fabricated: User.1 draws them and no fab output plots that layer
  (`tools/micras_pcb/jlc.py` `gerber_layers`; the drill files hold only holes). Keep-outs hold
  every layer's copper out of the cone with 0.4 mm to spare for the hand-cut cone: tracks, vias and
  pours 2.6 mm from each hole's centre on B.Cu and In2.Cu, 1.85 mm on In1.Cu; F.Cu keeps the hole's
  own clearance
  (`tests/test_main_layout.py` `test_countersinks_keep_the_copper_off`).

- **Fan ring and drive blocks on the silkscreen**: the fan's impeller shroud (MicrasHardware
  `micras/fan.py`) seals on a 27 mm ring round the fan hole (spec `[fan_ring]`): parts may sit in
  it, tracks and copper too, but none taller than 1.25 mm over the board (C53, the tallest)
  (`tests/test_main_layout.py` `test_parts_in_the_fan_ring_stay_low`, heights from the 3D models).
  `micras-pcb mech` draws the ring's edge on F.Silkscreen (0.15 mm), as on the v1 board, broken where
  IC1's pads lie under it (IC1, 0.995 mm high, straddles the ring) and over C5 (VCAP3's 100 nF, on the
  ring's line within 3 mm of pin 66; spec `[fan_ring]` `silk_breaks`), and the
  outline of each drive block's mounts (spec `[silkscreen]`: the union of the block's
  `[drive_blocks]` zones, its pads, the rings round its screw bosses, its body and, on the left,
  the ring round the left motor and its clamp; the motors, wheels and magnet cups are not drawn),
  straight 0.15 mm lines 0.3 mm in from the board's edge and off the spec-placed footprints' pads
  (encoder slots, screw holes, wall joints); a stub under 1 mm where a zone meets the edge is left
  out. Those lines are the spec's (generated, with stable UUIDs): no other pad may sit under them
  (`test_spec_silkscreen_keeps_off_every_pad`). They follow the zones, which follow the blocks 0.3 mm
  out: the left block from x 8.2 back to x -22.2 (y 0 to 23), the right one from x 8.2 back to
  x -19.2 (y -8 to -23).

## Known faults

These ERC and DRC warnings stay once the board is laid out:

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
  175 mA (Figure 2 or a measurement) and a cold check of the wall boards' AC-coupled selectors'
  margin; the firmware's DAC timing against the selectors.
- Fan: the REF setting for the chosen motor.
- Analog copper within 0.5 mm of a switching node's pad or pour: 2 pairs, 3V3_A 0.22 mm from Q9's
  drain pad (the op-amp's supply between Q9's gate and drain pads) and 0.23 mm from W3.5 (the wall
  joint puts 3V3_A, pin 3, 1.27 mm from the emitter sink, pin 5), both beside the emitter sink, whose
  node moves only at the selectors' edges and the DAC's steps, which settle before each receiver
  scan; `tests/test_main_layout.py` `SWITCHING_COPPER_EXEMPT` lists them with the gap they may not
  lose.
- Routing, round the escape rows: Current_Sensor_Right (62 mm: its run from C102 to R78 past the
  STM32's rear tip is the link's and the IMU's and encoders' corridor, so it goes round by the DIP
  switch and the buzzer), Wall_Emitter_Set and
  Wall_Sensor_2 are longer than the layout tests' detour rule; no analog line runs within 0.45 mm
  of a fast digital line on its layer outside the STM32's escapes. The ADC filter capacitor C102 sits
  3.5 mm from IC1.14 and C105 beside R79, 24 mm of track from IC1.25, where ST AN2834 section 4.2.8
  asks for the pin: the front-left face's lanes and escapes leave no 0402 spot within 3 mm of
  IC1.25 (the test is marked as an expected failure until they move).
- Routing: C72.1 (EC2's 100 nF) reaches ground only through the pour round it, boxed in by other
  nets' tracks (`PRUNE_SPARE`).
- Assembly: every through-hole lead trimmed to 0.5 mm or less (Ordering); M2's leads lie under
  MicrasHardware's rear skate.
- Silkscreen: the KiCad library passives (stdlib 0402-1210, 0603 LED) keep their 0.12 mm outlines;
  U13's outline and SW4's run past the board's edge (the module over its notch, the switch's
  lever at the cut corner), where the fab clips them. The reference designators are 0.5 mm high
  with a 0.125 mm stroke, each within 1 mm of its part's courtyard, clear of the mask openings, the
  other silkscreen and the edge, and off every part's body (`silk.py`); 11 of the 159 have no such
  spot (C2, C12, C21, C55, C84, C92, C114, L1, M1, R1, R31) and are hidden: the fab drawing
  (F.Fab) names every part.
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
