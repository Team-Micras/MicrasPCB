# Main board, second revision (main2)

The second revision of the Micras main board, as a schematic: the STM32H725RGV6 controller, a 4S
battery input with its monitor, a VSYS power path, separate digital and analog 3.3 V rails, two
DRV8874 wheel bridges with in-line INA241 current sensing, the STSPIN958 fan driver, the IMU,
four wall sensors on a shared emitter current sink, the slots for the two encoder boards, the
ESP32-S3 radio and debug probe on the USB-C port, and the user interface.

The design is [research/next-revision/README.md](../../../research/next-revision/README.md): its
design basis (maxon DCX 10 L 4.5 V motors on a 4S pack, no boost; USB-C to the ESP32 only; no
5 V rail), the options it recommends, and its connection lists A.1-A.6. The blocks it keeps are
`boards/main`'s, with their designators; new parts continue each series (C80-C112, D14-D15, IC8-IC9,
L4-L6, Q8-Q9, R56-R92, U8-U13), and the designators of removed parts are not reused.

The board is 100 x 50 mm, 4 layers, 1.04 mm, every part on the top side. Its mechanics are
[`spec/main2.toml`](../../../spec/main2.toml): the outline, the screw holes, the encoder slots, the
fan hole, the switch notch, the parts that mate with the robot and the zones the chassis takes over
the board (see [Layout](#layout)).

## Files

The board files are in `boards/main2/` (this README sits in its `layout/` folder).

| File | Sheet instance | Contents |
|---|---|---|
| [`main2.zen`](../main2.zen) | root | IC1 (STM32H725RGV6) and its supply network (C1-C17, L1, R67), the ST-Link header SWD1, M2 screw holes H1-H4 |
| [`Regulators.zen`](../Regulators.zen) | `REGULATORS` | J1 battery connector with its TVS D15, battery switch SW4/Q6, battery monitor U9 (INA228) with its 2 mOhm shunt R59, battery measurement R44/R45, power path D14/Q8, 3V3_D buck IC7, 3V3_A LDO U8 |
| [`Drivers.zen`](../Drivers.zen) | `DRIVERS` | IC8/IC9 (DRV8874) bridges for M2/M1 with their 10 mOhm shunts R65/R75 and 47 uH chokes L4/L5, IC6 (STSPIN958) fan driver for M3 with its shunt R31 and 4.7 uH choke L6 |
| [`Sensors.zen`](../Sensors.zen) | `SENSORS` | IC2 (LSM6DSV) IMU, U10/U11 (INA241A2) current amplifiers, wall sensors W1-W4 with their AC-coupled selectors Q2-Q5 and the emitter current sink U12/Q9/R83 with its DAC set-point, encoder slots EC1/EC2 |
| [`Peripherals.zen`](../Peripherals.zen) | `PERIPHERALS` | SW1 DIP switch, SW2/SW3 buttons, R42 BOOT0 pull-down, BZ1 buzzer, D1/D2 (WS2812C-2020-V6) status LEDs, D4/D5 LEDs, U2 USB-C with its ESD protection U6/D8 |
| [`Esp.zen`](../Esp.zen) | `ESP` | U13 (ESP32-S3-MINI-1-N8) with its decoupling, EN RC, GPIO0 pull-up and recovery pads, USB series resistors, links to the MCU, VBUS sensing |
| [`passives.zen`](../passives.zen) | | value, package, rating and part number of every resistor, ceramic capacitor and LED line |
| [`schematic/`](../schematic) | | how each sheet is drawn (`micras-pcb sch`): the root with IC1, its supply domains, the SWD header and the module sheets, and one file per module sheet, each block in a titled frame |
| [`erc.toml`](../erc.toml) | | nets supplied from off the board (BAT_P, GND, GND_BAT, +5V) or through a passive part (VBAT, VSYS, 3V3_D, the LDO input, VDDA), the PWR_FLAG role for ERC; the two ERC warnings the module sheets leave until a pcb release includes [diodeinc/pcb#1522](https://github.com/diodeinc/pcb/pull/1522) (as on the [main board](../../main/layout/README.md#known-faults)) |
| [`firmware_changes.toml`](../firmware_changes.toml) | | the firmware changes this board needs against the v1 firmware (see [Firmware changes](#firmware-changes)) |
| [`test/`](../test) | | `pcb test` benches: MCU and ESP links, power, drivers, peripherals |
| [`layout/`](.) | | this folder: the KiCad project; `main2.kicad_sch` is the root sheet, with one sheet per module (`REGULATORS.kicad_sch`, ...); the `.kicad_pcb` holds placement and routing; `place.py` places every part and `route.py` pours the planes and routes the board (see [Layout](#layout)) |
| [`spec/main2.toml`](../../../spec/main2.toml) | | mechanical interface: thickness, axle origin, outline, screw holes, encoder slots, fan hole, wheel and switch notches, the battery switch, USB-C and wall sensors' positions, the chassis zones |

Each module is its own sheet of the KiCad schematic (`Project(..., layout=False)` in its `.zen`),
its signal ports named after the nets they carry where those names are identifiers, as on the
main board. `SENSORS` takes the shared SPI bus once (`SPI_SCK`, `SPI_MISO`, `SPI_MOSI`) with
each device's chip select, not one `Spi` port per device, so it has 26 sheet pins instead of 32:
pcb 0.4.81 places the sheet symbols on the root one by one in the order of their names, each as
near the page centre as the earlier ones leave room, by their boxes alone, and the 32-pin symbol
fits only against the page's left edge, where its pin labels run past the page. At 26 pins it sits
right of `ESP`, and `tests/test_schematic.py` checks that every label stays on its page. Each sheet's docstring describes its circuit with the datasheet figure, table or
equation behind each value; [`tests/test_main2.py`](../../../tests/test_main2.py) checks the power tree, the analog
rail, the decoupling and the firmware contract on the generated netlist.

## Power

```text
4S LiPo 12.0-16.8 V (17.4 V HV) ─ J1 (D15 SMAJ18A across it) ─ BAT_P ─ R59 2 mΩ (U9 INA228, I²C to the ESP32) ─ VBAT
   pack - ─ GND_BAT ─ Q6 HSBB3072 (SW4, slew-limited) ─ GND
VBAT ─┬─ IC8/IC9 DRV8874 VM, IC6 STSPIN958 VS
      ├─ R44/R45 100k/20k ─ PC5 (Battery_Voltage, ratio 6.0)
      └─ D14 B5819W ─┐
USB VBUS (+5V) ─ Q8 AO3401A (gate follows VBAT) ─┴─ VSYS 4.3-17.4 V
      VSYS ─┬─ IC7 L6981C33 ─ 3V3_D: MCU VDD, ESP32, IMU, encoders, LEDs, emitters, INA228
            └─ R58 22 Ω + C80 10 µF ─ U8 ADP7142 3.3 V (EN = 3V3_D) ─ 3V3_A: VDDA (R67 0 Ω),
                  INA241 VS/REF1, phototransistor collectors, emitter-sink op-amp and its bias
```

- **VSYS** is `OR(VBAT, VBUS)`, so the ESP32, the MCU (for SWD flashing) and VDDA run from USB
  alone with the bridges off. A 4S pack is always above VBUS, so the battery wins; D14 blocks
  VSYS to VBAT and Q8's body diode blocks VSYS to VBUS. With the pack on, Q8's gate sits at VBAT
  and its VGS at about +0.2 V (off); without it, the gate falls to GND (on).
- **3V3_D**: the L6981C33 buck, as on the main board, now from VSYS; every capacitor on 3V3_D,
  the ESP32's optional 22 uF included, stays inside its 30.5-145 uF compensation window.
- **3V3_A**: the ADP7142ACPZN3.3 LDO from VSYS through 22 Ohm + 10 uF, its EN on 3V3_D so VDDA
  never leads VDD; about 10 mA typical, 23 mA worst case, 0.32 W at the HV pack's top.
- **No 5 V rail**: VBUS feeds only Q8, its clamp D8 and the ESP32's VBUS-sense divider.
- **Battery switch**: Q6 as on the main board; SW4 is the SK-12D29-G060 (DC 24 V, the main board's
  switch body with a 6.0 mm lever, its own footprint). No reverse-polarity protection: the connector
  keys the polarity.
- **TVS**: D15 (SMAJ18A, 18 V standoff, 20-22.1 V breakdown) across J1, BAT_P to GND_BAT. With the
  pack pulled while the bridges brake, it holds VBAT near 21-23 V through Q6's channel (SW4 on) or
  its body diode (SW4 off), below the 25 V MLCCs on VSYS and the DRV8874's 40 V.
- **No electrolytics**: VBAT carries only ceramics (56 uF effective at 16.8 V); the research's
  [VBAT capacitance](../../../research/next-revision/README.md#power-tree) compares the options and
  quantifies the VBAT overvoltage cases.

## Drivetrain and current sensing

- **Bridges**: one DRV8874PWPR per motor, PH/EN mode (PMODE = GND), PWM on EN and direction on
  PH (right PA8/PA9, left PC7/PC9), IMODE = GND (fixed off-time, automatic retry), ITRIP 2.97 A
  from RIPROPI 2.0 kOhm and VREF 2.68 V (5.6k/24k from 3V3_D). nSLEEP of both on Motors_Enable
  (PA10) with R49 100 kOhm to GND; nFAULT of both wire-ORed on Motors_nFault (PB2) with R60
  10 kOhm to 3V3_D. Per bridge: 100 nF + 4 x 10 uF 50 V X7R 1206 + 2 x 10 uF 50 V X7R 1210 (the
  bulk) on VM, 100 nF VCP, 22 nF CPH-CPL.
- **Motor path**: OUT1 -> 10 mOhm WSK2512 4-terminal shunt -> 47 uH XAL7070-473 choke -> motor
  connector; OUT2 -> connector. Each choke has a 2512 0 Ohm alternative across it, DNP: the choke
  is fitted until the motor's inductance at 100 kHz is measured.
- **Current**: INA241A2 (gain 20) on each shunt, VS and REF1 on 3V3_A, REF2 on GND: 0.2 V/A
  around VDDA / 2, about +7.1 / -8.0 A, into PC0 (left) and PC1 (right) through 100 Ohm with
  1 nF C0G at the pin.
- **Battery current**: the INA228 on R59 (+-20.48 A at ADCRANGE = 1), read by the ESP32.

## Fan

STSPIN958 in parallel half-bridge mode, PWM trimming, on TIM12 at 400 kHz: R31 25 mOhm, REF from
22k/9.1k on 3V3_D (current limit 3.86 A), RSR 1 kOhm (2 V/ns), 2 x 470 nF 50 V + 2 x 10 uF 50 V
on VS, and a 4.7 uH XGL5030-472 choke between FAN_OUT and the motor. Fan_PWM PB15, Fan_Enable PB14, Fan_TOFF PB13 as on the main board.

## Sensors

- **Wall sensors**: the four SFH 4550 emitters run from 3V3_D through 3.3 Ohm each into their
  AO3400A selectors, AC-coupled as on the main board (220 Ohm, 220 nF, 22 kOhm pull-down,
  1N4148WS clamp: a pin held high turns its emitter off within 7.5-11 ms), whose sources share
  one constant-current sink: TLV9001 + AO3400A + 1.2 Ohm 0.1 %, its set-point the DAC on PA5
  through 200k/20k (175 mA near code 3258, 223 mA full scale, 0 V at reset), compensated by
  1 kOhm / 1 nF and biased off at a zero set-point by 200 kOhm from 3V3_A. The phototransistor
  collectors are on 3V3_A.
- **IMU** and **encoder slots**: as on the main board, on 3V3_D.

## ESP32 and USB

- **ESP32-S3-MINI-1-N8** (U13) on 3V3_D with 10 uF + 100 nF (22 uF optional, DNP), EN RC
  10 kOhm / 1 uF, GPIO0 pulled up. Recovery pads `ESP_EN` and `ESP_BOOT` (hold BOOT to GND and
  pulse EN after a crashed USB OTG application).
- **USB-C** D+/D- through U6 (USBLC6) and 22 Ohm series resistors to GPIO20/GPIO19 only: the PC
  sees the ESP32 (CMSIS-DAP v2, CDC and mass storage), never the MCU. CC 5.1 kOhm Rd; SBU open.
- **Links to the MCU**: SWDIO GPIO11 -> PA13, SWCLK GPIO12 -> PA14 (22 Ohm), NRST GPIO13
  (open drain), UART1 GPIO17/18 <-> UART4
  PA11/PA12 at up to 5 Mbaud (100 Ohm on the ESP's TX), flow control GPIO21 -> PB0.
- **The ESP's own lines**: INA228 I²C on GPIO8/9 with ALERT on GPIO10; VBUS sense on GPIO7
  through 22k/33k (3.15 V at 5.25 V), reported to the MCU over UART4.
- **ST-Link header** SWD1: bare 1.27 mm pitch pads, 1 GND, 2 SWDIO, 3 SWCLK (no supply, no NRST),
  for a probe when the ESP32 cannot reach the MCU. BOOT0 stays low (R42): the MCU always starts
  from flash.

## Pins

The MCU keeps the main board's pin map except: PA8/PA9 and PC7/PC9 carry EN/PH of the right and
left bridges; PA11/PA12 carry UART4 to the ESP32 (no USB); PB2 reads Motors_nFault; PB0 reads
ESP_Flow; PA13/PA14 and NRST go to the ESP32 (PA13/PA14 also to the header SWD1); PA5 is the emitter
DAC (DAC1_OUT2), PC5 reads the battery divider (ADC12_INP8) and PH0 reads Switch_0, the MCU having
no VBUS input. Every GPIO of the VFQFPN68 is now used.

## Firmware changes

[`firmware_changes.toml`](../firmware_changes.toml) lists what the firmware must change against
the v1 firmware (`boards/main/firmware.toml`), on top of the main board's own pending changes:
PH/EN drive at 100 kHz with TIM3 slaved to TIM1; Motors_Enable as nSLEEP (1 ms wake);
Motors_nFault on PB2; INA241 sampling on TIM1 TRGO2 with dual injected ADC1/ADC2; the battery
divider constant 6.0 on PC5; Switch_0 on PH0; the fan at 400 kHz; UART4 to the ESP32 at up to
5 Mbaud with ESP_Flow on PB0, USB power reported by the ESP32; one wall emitter at a time, with
the emitter DAC on PA5 stepping with each selector and a code per emitter; the WS2812C timing (T0L/T1L at most 1 us); flashing through the
ESP32's CMSIS-DAP with OpenOCD or probe-rs.

## Layout

[`place.py`](place.py) places every part and [`route.py`](route.py) pours the planes and routes
the board; their docstrings give the rules they follow. The `.kicad_pcb` holds their result with
hand-routed corrections on top.

- **Placement**: every part on the top side. The spec places what mates with the robot; the
  ESP32-S3-MINI-1 sits in the rear-left corner with its antenna on the rear edge, each DRV8874 by
  its motor with its shunt, choke and bulk capacitors, the IMU between the encoder slots on the
  axle, the MCU and the wall-sensor channels in the nose, and the fan driver, DIP switch, buzzer
  and 3V3_A LDO beside the fan hole.
- **Planes**: In1.Cu is ground over the whole board; In2.Cu is ground but for the STM32's 3V3_D
  and VCORE islands under and round it; B.Cu carries the VBAT pour over the power entry and both
  bridges, and no other net's track runs on B.Cu inside it.
- **Tracks**: F.Cu and B.Cu only, octilinear. The power paths (`ROUTES` in `route.py`) are wide
  and locked; signals are 0.15 mm, 0.12 mm where they leave a fine-pitch pin, at 0.10-0.11 mm
  clearance. A switching net keeps 0.5 mm from an analog net on the same layer.
- **Vias**: 0.45/0.3 mm for power and planes, 0.35/0.2 mm for signals (the escapes between the
  STM32's 0.4 mm pitch pins); a 0.2 mm hole is above JLCPCB's 0.15 mm minimum and below its
  0.3 mm preferred size, which KiCad's DRC reports as a warning.
- **Not routed yet**: 12 connections, which KiCad's DRC lists as unconnected: ESP_Flow and
  UART4_TX to the ESP32; Encoder_Left_CSn and Encoder_Left_ABI_B to EC2; Encoder_Right_CSn to EC1;
  Motors_Enable (STM32 to R49, and IC8 to IC9); Motors_nFault (STM32 to R60); Switch_0 to SW1;
  Wall_Sensor_3 to W4; SINK_OUT (U12 to C113); WALL1_LED_K (Q3 to W2). The F.Cu and B.Cu ground
  pours, the ground stitching and the teardrops come after them.

## Open items

Each but the routing (see [Layout](#layout)) is a visible TODO in the sheet that owns it.

- Routing: the 12 unconnected connections, then the outer ground pours, stitching and teardrops.
- Battery input: the B02B-PASK rating at about 5 A; which SW4 lever position is ON (the SK-12D29
  drawing does not say).
- Choke 0 Ohm alternatives: the 2512 jumper's current rating.
- Emitter sink: a bench step across R83 to confirm the modelled response; the AO3400A's VGS at
  175 mA (Figure 2 or a measurement) and a cold check of the AC-coupled selectors' margin; the
  firmware's DAC timing against the selectors.
- Fan: the REF setting for the chosen motor.
- Current inputs: the CubeMX check of the fast-ADC-channel swap; R_iso + C_f stability.
- 3V3_A: the LDO's board-level thermal limit at about 0.33 W.
- Status LEDs: blue and green at 3.2-3.3 V (bench).
- ESP32: the antenna bench test in the chassis decides between the MINI-1 and the MINI-1U-N8
  (C2980299, external antenna, same footprint family).
