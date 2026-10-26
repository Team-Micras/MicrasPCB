# Main board, second revision (main2)

The second revision of the Micras main board, as a schematic: the STM32H725RGV6 controller, a 4S
battery input with its fuse, a VSYS power path, separate digital and analog 3.3 V rails, two
DRV8874 wheel bridges with in-line INA241 current sensing, the STSPIN958 fan driver, the IMU,
four wall sensors on a shared emitter current sink, the slots for the two encoder boards, the
ESP32-S3 radio and debug probe on the USB-C port, and the user interface.

The design is [research/next-revision/README.md](../../../research/next-revision/README.md): its
design basis (maxon DCX 10 L 4.5 V motors on a 4S pack, no boost; USB-C to the ESP32 only; no
5 V rail), the options it recommends, and its connection lists A.1-A.6. The blocks it keeps are
`boards/main`'s, with their designators; new parts continue each series (C80-C114, D14-D16, IC8-IC9,
L4-L6, Q8-Q9, R56-R92, U8-U13), and the designators of removed parts are not reused.

The board is 100 x 50 mm, 4 layers, 1.04 mm, every part on the top side. Its mechanics are
[`spec/main2.toml`](../../../spec/main2.toml): the outline, the screw holes, the encoder slots, the
fan hole, the antenna and switch notches, the parts that mate with the robot or the outline and the
zones the chassis takes over the board (see [Layout](#layout)).

## Files

The board files are in `boards/main2/` (this README sits in its `layout/` folder).

| File | Sheet instance | Contents |
|---|---|---|
| [`main2.zen`](../main2.zen) | root | IC1 (STM32H725RGV6) and its supply network (C1-C17, L1, R67), the ST-Link header SWD1, M2 screw holes H1-H4 |
| [`Regulators.zen`](../Regulators.zen) | `REGULATORS` | J1 battery connector with its fuse F1 and TVS D15, battery switch SW4/Q6, battery measurement R44/R45, power path D14/Q8, 3V3_D buck IC7, 3V3_A LDO U8 |
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
| [`spec/main2.toml`](../../../spec/main2.toml) | | mechanical interface: thickness, axle origin, outline, screw holes, encoder slots, fan hole, wheel, antenna and switch notches, the ESP32 module's, battery switch's, USB-C's and wall sensors' positions, the chassis zones; the via-in-pad order option |

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
4S LiPo 12.0-16.8 V (17.4 V HV) ─ J1 ─ BAT_P ─ F1 12 A fuse ─ VBAT (D15 SMAJ18A to GND_BAT)
   pack - ─ GND_BAT ─ Q6 HSBB3072 (SW4, slew-limited) ─ GND
VBAT ─┬─ IC8/IC9 DRV8874 VM, IC6 STSPIN958 VS
      ├─ R44/R45 100k/20k ─ PC5 (Battery_Voltage, ratio 6.0)
      └─ D14 B5819W ─┐
USB VBUS (+5V) ─ Q8 AO3401A (gate follows VBAT, D16 clamp) ─┴─ VSYS 4.3-17.4 V
      VSYS ─┬─ IC7 L6981C33 ─ 3V3_D: MCU VDD, ESP32, IMU, encoders, LEDs, emitters
            └─ R58 22 Ω + C80 10 µF ─ U8 ADP7142 3.3 V (EN = 3V3_D) ─ 3V3_A: VDDA (R67 0 Ω),
                  INA241 VS/REF1, phototransistor collectors, emitter-sink op-amp and its bias
```

- **VSYS** is `OR(VBAT, VBUS)`, so the ESP32, the MCU (for SWD flashing) and VDDA run from USB
  alone with the bridges off. A 4S pack is always above VBUS, so the battery wins; D14 blocks
  VSYS to VBAT and Q8's body diode blocks VSYS to VBUS. With the pack on, Q8's gate sits at VBAT
  and its VGS at about +0.2 V (off); without it, the gate falls to GND (on). D16 (BZT52C10S,
  10 V zener, gate to VSYS) holds Q8's VGS inside its +-12 V when VBAT falls faster than VSYS
  (a VBAT short, the pack pulled or SW4 opened under load: -14 to -16 V without it).
- **USB attach capacitance**: C63 1 uF on VBUS; VSYS's 10 + 1 uF and LDO_IN's 10 uF (behind
  22 Ohm) also charge through Q8's body diode, 22 uF nominal against USB 2.0's 10 uF: accepted.
- **3V3_D**: the L6981C33 buck, as on the main board, now from VSYS; every capacitor on 3V3_D,
  the ESP32's 22 uF included, stays inside its 30.5-145 uF compensation window.
- **3V3_A**: the ADP7142ACPZN3.3 LDO from VSYS through 22 Ohm + 10 uF 1210, its EN on 3V3_D so VDDA
  never leads VDD; about 10 mA typical, 23 mA worst case, 0.32 W at the HV pack's top.
- **No 5 V rail**: VBUS (+5V, 4.4-5.5 V) feeds only Q8, its clamp D8 (SP1005-01ETG, 6 V
  stand-off, above Type-C's 5.5 V) and the ESP32's VBUS-sense divider.
- **Fuse**: F1, Littelfuse 0501012.WR1 (12 A fast-acting, 32 VDC, 150 A interrupting, 3.2 mOhm;
  a 1206 under the chassis's 1.5 mm zone), carries the whole battery current from J1 to VBAT: a
  short on the board opens it. It carries the 4 A rms budget with 2x margin at 75 C (8.2 A) and
  holds the 10.1 A summed peak limits at 75 C (10.2 A); it clears a 40 A partial fault in about
  6 s (the 20 A row: about 25 s). Turning the board on is under 0.01 A2s against its 20.3 A2s.
- **Battery switch**: Q6 as on the main board, its gate fed from VBAT through SW4; C58 100 nF
  gate-source and C114 1 nF gate-drain keep it off when the pack is plugged in (the board then
  sees no edge), and slew VBAT at about 0.06 V/us when SW4 closes, under the STSPIN958's
  0.5 V/us. SW4 is the SK-12D29-G060
  (DC 24 V, the main board's switch body with a 6.0 mm lever, its own footprint). The connector
  keys the polarity; a reversed pack forward-biases D15 through F1, which opens.
- **TVS**: D15 (SMAJ18A, 18 V standoff, 20-22.1 V breakdown) behind F1, VBAT to GND_BAT, so a
  TVS that fails short opens the fuse. With the
  pack pulled while the bridges brake, it holds VBAT near 21-23 V through Q6's channel (SW4 on) or
  its body diode (SW4 off), at most 24.2 V, below every rating on VBAT and VSYS (50 V MLCCs,
  Q6 and Q8's 30 V, the DRV8874's 40 V).
- **No electrolytics**: VBAT carries only ceramics, every 10 uF a 50 V X7R 1210 (61 uF effective
  at 16.8 V); the research's
  [VBAT capacitance](../../../research/next-revision/README.md#power-tree) compares the options and
  quantifies the VBAT overvoltage cases.

## Drivetrain and current sensing

- **Bridges**: one DRV8874PWPR per motor, PH/EN mode (PMODE = GND), PWM on EN and direction on
  PH (right PA8/PB8, left PC7/PC6), IMODE = GND (fixed off-time, automatic retry), ITRIP 2.97 A
  from RIPROPI 2.0 kOhm and VREF 2.67 V (4.7k/20k from 3V3_D). nSLEEP of both on Motors_Enable
  (PA10) with R49 100 kOhm to GND; nFAULT of both wire-ORed on Motors_nFault (PB2) with R60
  10 kOhm to 3V3_D. Per bridge: 100 nF + 4 x 10 uF 50 V X7R 1210 on VM, 100 nF VCP, 22 nF
  CPH-CPL.
- **Motor path**: OUT1 -> 10 mOhm WSK2512 4-terminal shunt -> 47 uH XAL7070-473 choke -> motor
  connector; OUT2 -> connector.
- **Current**: INA241A2 (gain 20) on each shunt, VS and REF1 on 3V3_A, REF2 on GND: 0.2 V/A
  around VDDA / 2, about +7.1 / -8.0 A, into PB1 (left, a fast ADC channel) and PC1 (right)
  through 150 Ohm (R78/R79, R_iso), with 1 nF C0G beside the resistor; the firmware samples them
  for at least 0.7 us, so the ADC's kickback from a wall-sensor conversion settles below 1 mA.

## Fan

STSPIN958 in parallel half-bridge mode, PWM trimming, on TIM12 at 400 kHz: R31 25 mOhm, REF from
4.7k/2.0k on 3V3_D (current limit 3.94 A), RSR 1 kOhm (2 V/ns), 2 x 470 nF 50 V X7R 0805 +
2 x 10 uF 50 V on VS, CBOOT 1 uF 50 V X7R (the IC runs hot), and a 4.7 uH XGL5030-472 choke between FAN_OUT and the motor. Fan_PWM PB15, Fan_Enable PB14, Fan_TOFF PB13 as on the main board.

## Sensors

- **Wall sensors**: the four SFH 4550 emitters run from 3V3_D through 3.3 Ohm each (which keeps
  a failed sink's current inside the emitter's pulse rating) into their
  AO3400A selectors, AC-coupled as on the main board (220 Ohm, 220 nF, 22 kOhm pull-down,
  1N4148WS clamp: a pin held high turns its emitter off within 7.5-11 ms), whose sources share
  one constant-current sink: TLV9001 + AO3400A + 1.2 Ohm 0.1 %, its set-point the DAC on PA5
  through 200k/20k (175 mA near code 3258, 223 mA full scale, 0 V at reset), compensated by
  1 kOhm / 1 nF and biased off at a zero set-point by 200 kOhm from 3V3_A. The phototransistor
  collectors are on 3V3_A.
- **IMU** and **encoder slots**: as on the main board, on 3V3_D.

## ESP32 and USB

- **ESP32-S3-MINI-1-N8** (U13) on 3V3_D with 22 uF + 10 uF + 100 nF, EN RC
  10 kOhm / 1 uF, GPIO0 pulled up. Recovery pads `ESP_EN` and `ESP_BOOT` (hold BOOT to GND and
  pulse EN after a crashed USB OTG application).
- **USB-C** D+/D- through U6 (USBLC6) and 22 Ohm series resistors to GPIO20/GPIO19 only: the PC
  sees the ESP32 (CMSIS-DAP v2, CDC and mass storage), never the MCU. CC 5.1 kOhm Rd; SBU open.
- **Links to the MCU**: SWDIO GPIO11 -> PA13, SWCLK GPIO12 -> PA14 (22 Ohm), NRST GPIO21
  (open drain; GPIO1-20 glitch at the ESP's power-up, ESP32-S3 datasheet Table 2-2), UART1
  GPIO17/18 <-> UART4 PA11/PA12 at up to 5 Mbaud (100 Ohm on the ESP's TX), flow control
  GPIO13 -> PA9.
- **The ESP's own lines**: VBUS sense on GPIO7
  through 22k/33k (3.30 V at 5.5 V), reported to the MCU over UART4.
- **ST-Link header** SWD1: bare 1.27 mm pitch pads, 1 GND, 2 SWDIO, 3 SWCLK (no supply, no NRST),
  for a probe when the ESP32 cannot reach the MCU. BOOT0 stays low (R42): the MCU always starts
  from flash.

## Pins

The MCU keeps the main board's pin map except: PA8 (TIM1_CH1) and PB8 carry EN and PH of the right
bridge, PC7 (TIM8_CH2) and PC6 the left's; PA11/PA12 carry UART4 to the ESP32 (no USB); PB2 reads
Motors_nFault; PA9 reads ESP_Flow; PA13/PA14 and NRST go to the ESP32 (PA13/PA14 also to the header
SWD1); PA5 is the emitter DAC (DAC1_OUT2), PC5 reads the battery divider (ADC12_INP8) and PH0 reads
Switch_0, the MCU having no VBUS input. For the routing, Current_Sensor_Left moves to PB1 (a fast
ADC channel), Wall_Sensor_0 to PA4 and Wall_Sensor_3 to PC0, each keeping an ADC1 and an ADC2 input;
and so that no line crosses the STM32's rear tip, the wall selectors move from TIM4 (PB6-PB9) to
TIM3 on the rows facing their emitters (PC9 CH4, PB0 CH3 on the left; PB4 CH1, PB5 CH2 on the
right), LED_ARGB to PB9 (TIM17_CH1), IMU_INT2 to PB6, Encoder_Right_CSn to PB7 and IMU_INT1 to PB10
(main2.zen, with the alternate functions' source). Every GPIO of the VFQFPN68 is now used.

## Firmware changes

[`firmware_changes.toml`](../firmware_changes.toml) lists what the firmware must change against
the v1 firmware (`boards/main/firmware.toml`), on top of the main board's own pending changes:
PH/EN drive at 100 kHz with TIM8 slaved to TIM1; Motors_Enable as nSLEEP (1 ms wake);
Motors_nFault on PB2; INA241 sampling on TIM1 TRGO2 with dual injected ADC1/ADC2; the battery
divider constant 6.0 on PC5; Switch_0 on PH0; the fan at 400 kHz; UART4 to the ESP32 at up to
5 Mbaud with ESP_Flow on PA9, USB power reported by the ESP32; one wall emitter at a time on TIM3, with
the emitter DAC on PA5 stepping with each selector and a code per emitter, and no LED or SPI
traffic during an emitter's pulse; the current channels sampled for at least 0.7 us; the WS2812C
timing (T0L/T1L at most 1 us); flashing through the ESP32's CMSIS-DAP with OpenOCD or probe-rs,
nRESET on the ESP's GPIO21; TIM1/TIM8/TIM12 frozen and the drive enables cleared on a debug halt;
the LSM6DSV's I2C disabled at boot.

## Layout

[`place.py`](place.py) places every part and [`route.py`](route.py) pours the planes and routes
the board; their docstrings give the rules they follow. The `.kicad_pcb` holds their result with
the connections they left routed by rip-up scripts and by hand, under the same rules. Every
connection is routed but the 11 listed under Open items.

- **Placement**: every part on the top side. The spec places what mates with the robot or the
  outline; the ESP32-S3-MINI-1 sits in the rear-left corner (spec `[u13]`), its pads on the board
  and its antenna over a notch cut out under it and beside it (see Antenna), each DRV8874 by
  its motor with its shunt, choke and bulk capacitors, the IMU between the encoder slots on the
  axle, the MCU and the wall-sensor channels in the nose, and the fan driver, DIP switch, buzzer
  and 3V3_A LDO beside the fan hole.
- **Planes**: In1.Cu is ground over the whole board; In2.Cu is ground but for the STM32's two supply
  islands, each only as big as its job (`route.py`): 3V3_D (`mcu_3v3_outline()`) is the square under
  the chip out to its pin tips with a tab to the via of each 3V3_D pin (VBAT, VDDSMPS, VDD); VCORE
  (`vcore_outline()`) is a band outside the pin tips' vias that only reaches VCORE's vias (VFBSMPS,
  VCAP1-3, C3-C7, L1) and stops either side of the chip's rear tip. The signals' escape vias just
  past the pin tips sit on In2.Cu ground, between the two islands. B.Cu carries the VBAT pour over
  the power entry and both bridges, and no other net's track runs on B.Cu inside it.
- **Tracks**: F.Cu and B.Cu, octilinear. The power paths (`ROUTES` in `route.py`) are wide and
  locked; signals are 0.15 mm, 0.12 mm where they leave a fine-pitch pin and nowhere narrower,
  at 0.10-0.11 mm clearance. A switching net keeps 0.5 mm from an analog net on the same layer.
  No track ends open but the partial routes of the hand-routed connections (Open items).
- **USB**: D+/D- leave the connector through U6, flowing straight through its pin pairs, to R84/R85
  (22 Ohm) side by side over U6's ESP32-side pins; from there a 0.25 mm pair with a 0.15 mm gap
  runs on B.Cu under the module's edge to its pins 23/24, crossing over once at the module end.
  D+ takes a meander under the module's edge for the length D- spends round the back of the
  connector's pins: the two are within 1.5 mm. Every USB track keeps 1 mm from the buck's switch
  node, bootstrap and L3, and 0.45 mm from 3V3_A (Espressif ESP32-S3 Hardware Design Guidelines,
  USB section).
- **Power copper**: the battery path is poured for 10 A: J1 (turned so its GND_BAT pin faces Q6)
  to F1 as a BAT_P pour, nothing else on BAT_P before the fuse; F1's VBAT side a pour with 13 vias to
  the B.Cu pour, D15 on it; GND_BAT poured on F.Cu and B.Cu from J1 to Q6's sources with 14 vias;
  Q6's drain in a ground pour with its via field. The motor paths are 1.0 mm (necks at the pins),
  the crossings by the connectors on B.Cu outside the VBAT pour with 4-via clusters. Each DRV8874's
  VM pin takes a short F.Cu island with its 100 nF (C82, C91) and 3-4 vias to the pour. The fan driver
  (STSPIN958) is turned so its power side faces the board's edge and its logic pins the fan hole
  (DS14341 Fig. 23): the VS strip runs out from pins 27-30 between OUT1 and OUT2 to the two 470 nF
  (C34, C35) and the bulk C99, with 5 vias to the B.Cu VBAT feed; OUT1 goes straight to L6 on F.Cu,
  OUT2 joins it through 5 + 5 vias and a B.Cu pour under the pins; LSS2 goes to R31 (its LSS pad
  1.8 mm from pin 24) and on to the fan connector's return M3.2, LSS1 joins it through 5 + 5 vias
  and a B.Cu pour under the chip's outer edge (the exposed pad keeps two rows of three thermal
  vias); the motor runs from L6.2 to M3.1 along the board's edge on B.Cu. VBAT reaches the fan on
  B.Cu from the bridges' pour along the left wheel cut-out (a 1.5 mm pour), and goes on round the
  fan block's front (0.4 mm) to the bulk C112 and C96 in front of the fan hole and the battery
  divider's R44. The logic pins drop to B.Cu at their tips, and VDD and nSTBY take C31 under them
  on F.Cu: the fan hole's rim stays free on both outer layers for the lines to the STM32. The switch nodes stay on F.Cu: SMPS_LX straight to L1, BUCK_SW a short pour
  from IC7's pin 1 to L3. R58 (the 3V3_A LDO's input RC) sits by C80 and U8, VSYS running to it
  along the right wheel cut-out beside CURRENT_R_AMP; the VBAT pour leaves a notch under R75 where
  Motor_L_Sense+ leaves the shunt on B.Cu (OUT1 and SHUNT close F.Cu round its pad).
- **In2.Cu hops**: an exception where F.Cu and B.Cu have no room, not a routing layer: 53 mm on
  seven nets (IMU_INT2, SPI_SCK, SPI_MISO, LED_ARGB, Motors_nFault, Motors_Enable,
  Wall_Sensor_PWM_2), 200 mm at most in all. A hop carries a digital line of the STM32 or the ESP32
  only; it keeps 0.25 mm (plan view) from every switching, analog and battery-side supply track on
  B.Cu (`nets.SWITCHING` includes the fan's low-side sources, bootstrap and charge pump, the
  bridges' charge pumps and the INA241s' Kelvin lines), stays off every B.Cu pour but ground and out
  of the STM32's islands, and leaves In2.Cu's ground in one piece but for pockets of 1.7 mm2 at
  most, each with its own ground via. Any other B.Cu track crosses a hop square, but for one
  exception: a hop of a slow digital line (`nets.SLOW_DIGITAL`) may run under another slow digital
  line's B.Cu track for at most `nets.IN2_PARALLEL_MAX` (1.5 mm) along each of its segments; the
  fast lines (`nets.FAST_DIGITAL`: SPI_SCK, LED_ARGB, the encoders, USB) never run along one. The
  longest such run is 1.0 mm (`tests/test_main2_layout.py`).
- **Antenna**: the board is cut away under the MINI-1's antenna and beside it (spec
  `[antenna_notch]`, 5.6 x 19.0 mm from the rear-left corner, R0.8 corners): its inner edge runs
  on the module's antenna boundary, 0.3 mm outside its ground pads, and its side stops 2.9 mm past
  the antenna's feed end, short of the USB-C's shell pads (Espressif: the board cut away below
  the antenna and on both sides; ESP32-S3 Hardware Design Guidelines, General Principles of PCB
  Layout for Modules; datasheet Figures 10-1 and 11-1). No copper, on any layer, is left under the
  antenna. The module's ground pads carry a via row at 0.85 mm along its ground edge, and four
  ground vias fence the notch's side wall by the USB-C. The 22 uF C109 sits beside the module's
  3V3 pin, the 100 nF C108 and 10 uF C107 on its 3V3_D feed beside U6, off the notch (the module
  decouples its chip itself, datasheet Figure 8-1).
- **Pours and pad joins**: F.Cu and B.Cu carry ground pours over what the tracks leave. The
  board-wide pours and planes (ground on every layer, VBAT on B.Cu) join pads by thermal reliefs,
  0.25 mm gap, 0.2 mm spokes on the outer ground pours and 0.4 mm on the planes and on every
  through-hole pad, so a small part's pour end heats as fast as its track end in reflow; the pads
  that carry current or heat join solid: exposed pads and every pad of 1.2 mm2 and more, the power
  stages' pins (IC6, IC7, IC8, IC9, Q6), the pads inside the power paths' own pours, and 13 pads
  the pour reaches from one side only (`route.py` `relief()`, `RELIEF_STARVED`). Under each
  DRV8874's exposed pad a 4.0 x 5.6 mm B.Cu ground island, cut out of the VBAT pour, takes the
  heat of its 12 thermal vias (SLVSF66A section 10.1); the VBAT pour flows round it to the VM vias.
- **Ground stitching** (`route.py` `stitch()`, `prune()`): 143 stitching vias (359 ground vias in
  all). Every point where both outer layers are ground lies within 4 mm of a ground via or
  through-hole ground pad (a twentieth of the 2.4 GHz wavelength, TI SZZA009), and every island of
  outer ground pour over 2 mm2 has at least two, but for the pour within 0.6 mm of a ground pad or
  track (its join) and within 4.5 mm of C72.1 (see Open items). A stitching via goes only where all
  four layers are ground round it, so it cuts no other net's copper, In2.Cu's islands and hops
  included; the ground that no via can reach is cut out by 21 pour keep-outs (`no pour:
  unstitched`).
- **Teardrops** on every pad and via.
- **Vias in pads**: only the exposed pads' thermal vias open into a pad, and the board is ordered
  without a via-in-pad process (spec `[pcb] via_in_pad = "open"`). They are 0.2 mm holes (TI's
  PowerPAD via, SLVSF66A land pattern 4223595/B), 0.45 mm copper, left open on both sides (tenting
  a pad's via from the back traps air, TI SLUA271C section 3.4.1), at the via sites each footprint
  draws on Cmts.User (`route.py` `thermal_vias()`): 12 per DRV8874 on TI's 1.2 mm grid, 6 in the
  STSPIN958's pad, 4 in the STM32's and 4 in Q6's drain pad. Each of these pads' paste is split into
  windows clear of the sites, 51-64 % of the pad (SLUA271C section 4.4: 50-70 %): the DRV8874's in
  its footprint, the STSPIN958's, the STM32's and the HSBB3072's in `_SplitPaste` variants (their
  modules' `paste = "split"`). The ADP7142's exposed pad has no vias and four paste windows; the
  ESP32 module's nine ground squares have no vias.
- **Vias**: 0.45/0.3 mm for power and planes, 0.35/0.2 mm for signals (the escapes between the
  STM32's 0.4 mm pitch pins), 0.45/0.2 mm for the thermal vias; a 0.2 mm hole is above JLCPCB's
  0.15 mm minimum and below its 0.3 mm preferred size, which KiCad's DRC reports as a warning.
  JLCPCB charges more for a 0.2 mm hole with copper under 0.45 mm (PCB Capabilities page,
  accessed 2026-10-25): the 0.35/0.2 mm signal vias take that order option; the thermal vias'
  0.45 mm copper does not.

## Open items

Each is a visible TODO in the sheet that owns it.

- Battery input: the B02B-PASK rating at about 5 A; which SW4 lever position is ON (the SK-12D29
  drawing does not say); the pack's short-circuit current against F1's 150 A interrupting rating.
- Emitter sink: a bench step across R83 to confirm the modelled response; the AO3400A's VGS at
  175 mA (Figure 2 or a measurement) and a cold check of the AC-coupled selectors' margin; the
  firmware's DAC timing against the selectors.
- Fan: the REF setting for the chosen motor.
- Routing: 11 connections on 9 nets are not routed: UART4_TX (pin 47's escape, boxed in by the SWDIO
  and UART4_RX vias and C6), IMU_INT1, Encoder_Right_CSn, Encoder_Left_ABI_A, SPI_SCK (EC2's join),
  Motors_Enable (two), Motors_nFault (two), Switch_0, and Current_Sensor_Left (pin 30 to R79,
  analog: no In2.Cu). They run between the STM32's escape rows and the parts behind the fan hole
  (the IMU, the encoder slots, the bridges' logic pins) or the DIP switch, where F.Cu and B.Cu are
  full and In2.Cu takes only square crossings under the encoders' and other lines.
- Routing, round the escape rows: Encoder_Right_ABI_B (168 mm for a 34 mm span: its pin faces the
  rear-right quadrant, whose lines fill both outer layers, so it runs round the nose), Wall_Emitter_Set,
  Wall_Sensor_2 and Wall_Sensor_PWM_2 are longer than the layout tests' detour rule, and 13 analog /
  fast-digital pairs run closer than 0.45 mm for 0.1-16 mm each (the longest: 3V3_A beside
  Encoder_Right_ABI_B, the emitter set-point beside Encoder_Left_ABI_B for 9 mm);
  `tests/test_main2_layout.py` lists them with the length they may not exceed. The ADC filter
  capacitors C102 and C105 sit 9-14 mm from their pins, where ST AN2834 section 4.2.8 asks for the
  pin: no 0402 fits within 3 mm of IC1.14 or IC1.30 outside the escape rows (the test is marked as
  an expected failure until they move).
- Routing, after the hand routing: rerun the pour joins, stitching and pruning (`route.py`
  `unprune()`, `relief()`, then `stitch()`, `prune()` and `teardrops()` on KiCad's refilled zones)
  so the new tracks' ground keeps its vias; C72.1 (EC2's 100 nF) reaches ground only through the pour round it,
  boxed in by SPI_MOSI and 3V3_D (`PRUNE_SPARE`).
- ADC pins: the CubeMX check of the ADC set-up on the swapped pins; R_iso + C_f stability.
- 3V3_A: the LDO's board-level thermal limit at about 0.33 W.
- 3V3_D: the L6981's slope-compensation bound (Eq. 38): read literally (ISLOPE = 1 A) it puts
  L3 below 0.4, as it does the datasheet's own 33 uH design; confirm ISLOPE or load-step the rail.
- Status LEDs: blue and green at 3.2-3.3 V (bench).
- ESP32: the antenna bench test in the chassis decides between the MINI-1 and the MINI-1U-N8
  (C2980299, external antenna, same footprint family).
