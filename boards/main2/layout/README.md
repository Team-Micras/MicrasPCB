# Main board, second revision (main2)

The second revision of the Micras main board, as a schematic: the STM32H725RGV6 controller, a 4S
battery input with its monitor, a VSYS power path, separate digital and analog 3.3 V rails, two
DRV8874 wheel bridges with in-line INA241 current sensing, the STSPIN958 fan driver, the IMU,
four wall sensors on a shared emitter current sink, the slots for the two encoder boards, the
ESP32-S3 radio and debug probe on the USB-C port, and the user interface.

The design is [research/next-revision/README.md](../../../research/next-revision/README.md): its
design basis (maxon DCX 10 L 4.5 V motors on a 4S pack, no boost; USB-C to the ESP32 only; no
5 V rail), the options it recommends, and its connection lists A.1-A.6. The blocks it keeps are
`boards/main`'s, with their designators; new parts continue each series (C80-C110, D14, IC8-IC9,
L4-L6, Q8-Q9, R56-R92, U8-U13), and the designators of removed parts are not reused.

The board is **schematic only**: its Zener root declares `Project(layout = False)`, so `make gen`
writes the KiCad schematic and no `.kicad_pcb`, and the layout gates (LVS, DRC, DFM, layout
pytest, the fab gerbers and CPL, the 3D outputs) skip it with that reason. Placement and routing
are human-led and not started.

## Files

The board files are in `boards/main2/` (this README sits in its `layout/` folder).

| File | Sheet instance | Contents |
|---|---|---|
| [`main2.zen`](../main2.zen) | root | IC1 (STM32H725RGV6) and its supply network (C1-C17, L1, R67), test pads (IMU, fan, the SWD backstop), M2 screw holes H1-H4 |
| [`Regulators.zen`](../Regulators.zen) | `REGULATORS` | J1 battery connector, battery switch SW4/Q6, battery monitor U9 (INA228) with its 2 mOhm shunt R59, battery measurement R44/R45, power path D14/Q8, 3V3_D buck IC7, 3V3_A LDO U8 |
| [`Drivers.zen`](../Drivers.zen) | `DRIVERS` | IC8/IC9 (DRV8874) bridges for M2/M1 with their 10 mOhm shunts R65/R75 and 47 uH chokes L4/L5, IC6 (STSPIN958) fan driver for M3 with its shunt R31 and 4.7 uH choke L6 |
| [`Sensors.zen`](../Sensors.zen) | `SENSORS` | IC2 (LSM6DSV) IMU, U10/U11 (INA241A2) current amplifiers, wall sensors W1-W4 with their selectors Q2-Q5 and the emitter current sink U12/Q9/R83, encoder slots EC1/EC2 |
| [`Peripherals.zen`](../Peripherals.zen) | `PERIPHERALS` | SW1 DIP switch, SW2/SW3/SW5 buttons, BZ1 buzzer, D1/D2 (WS2812C-2020-V6) status LEDs, D4/D5 LEDs, U2 USB-C with its ESD protection U6/D8 and the MCU's VBUS sensing |
| [`Esp.zen`](../Esp.zen) | `ESP` | U13 (ESP32-S3-MINI-1-N8) with its decoupling, EN RC, GPIO0 pull-up and recovery pads, USB series resistors, links to the MCU, VBUS sensing |
| [`passives.zen`](../passives.zen) | | value, package, rating and part number of every resistor, ceramic capacitor and LED line |
| [`erc.toml`](../erc.toml) | | nets supplied from off the board (BAT_P, GND, GND_BAT, +5V) or through a passive part (VBAT, VSYS, 3V3_D, the LDO input, VDDA), the PWR_FLAG role for ERC; the two ERC warnings the module sheets leave until a pcb release includes [diodeinc/pcb#1522](https://github.com/diodeinc/pcb/pull/1522) (as on the [main board](../../main/layout/README.md#known-faults)) |
| [`firmware_changes.toml`](../firmware_changes.toml) | | the firmware changes this board needs against the v1 firmware (see [Firmware changes](#firmware-changes)) |
| [`test/`](../test) | | `pcb test` benches: MCU and ESP links, power, drivers, peripherals |
| [`layout/`](.) | | this folder: the generated KiCad schematic project; `main2.kicad_sch` is the root sheet, with one sheet per module (`REGULATORS.kicad_sch`, ...) |

Each module is its own sheet of the KiCad schematic (`Project(..., layout=False)` in its `.zen`),
its signal ports named after the nets they carry where those names are identifiers, as on the
main board. pcb 0.4.81 packs the five sheet symbols on the root by their boxes alone, so the root
labels at SENSORS' pins run up to 11 mm past the page's left edge (open the root in KiCad to read
them); `tests/test_schematic.py` expects this until a pcb release includes
[diodeinc/pcb#1522](https://github.com/diodeinc/pcb/pull/1522). Each sheet's docstring describes its circuit with the datasheet figure, table or
equation behind each value; [`tests/test_main2.py`](../../../tests/test_main2.py) checks the power tree, the analog
rail, the decoupling and the firmware contract on the generated netlist.

## Power

```text
4S LiPo 12.0-16.8 V (17.4 V HV) ─ J1 ─ BAT_P ─ R59 2 mΩ (U9 INA228, I²C to the ESP32) ─ VBAT
   pack - ─ GND_BAT ─ Q6 HSBB3072 (SW4, slew-limited) ─ GND
VBAT ─┬─ IC8/IC9 DRV8874 VM, IC6 STSPIN958 VS
      ├─ R44/R45 100k/20k ─ PA5 (Battery_Voltage, ratio 6.0)
      └─ D14 B5819W ─┐
USB VBUS (+5V) ─ Q8 AO3401A (gate follows VBAT) ─┴─ VSYS 4.3-17.4 V
      VSYS ─┬─ IC7 L6981C33 ─ 3V3_D: MCU VDD, ESP32, IMU, encoders, LEDs, emitters, INA228
            └─ R58 22 Ω + C80 10 µF ─ U8 ADP7142 3.3 V (EN = 3V3_D) ─ 3V3_A: VDDA (R67 0 Ω),
                  INA241 VS/REF1, phototransistor collectors, emitter-sink op-amp and set-point
```

- **VSYS** is `OR(VBAT, VBUS)`, so the ESP32, the MCU (for SWD flashing) and VDDA run from USB
  alone with the bridges off. A 4S pack is always above VBUS, so the battery wins; D14 blocks
  VSYS to VBAT and Q8's body diode blocks VSYS to VBUS. With the pack on, Q8's gate sits at VBAT
  and its VGS at about +0.2 V (off); without it, the gate falls to GND (on).
- **3V3_D**: the L6981C33 buck, as on the main board, now from VSYS; every capacitor on 3V3_D,
  the ESP32's optional 22 uF included, stays inside its 30.5-145 uF compensation window.
- **3V3_A**: the ADP7142ACPZN3.3 LDO from VSYS through 22 Ohm + 10 uF, its EN on 3V3_D so VDDA
  never leads VDD; about 10 mA typical, 23 mA worst case, 0.32 W at the HV pack's top.
- **No 5 V rail**: VBUS feeds only Q8, its clamp D8 and the two VBUS-sense dividers.
- **Battery switch**: Q6 and SW4 as on the main board; Q6 gives no reverse-polarity protection.

## Drivetrain and current sensing

- **Bridges**: one DRV8874PWPR per motor, PH/EN mode (PMODE = GND), PWM on EN and direction on
  PH (right PA8/PA9, left PC7/PC9), IMODE = GND (fixed off-time, automatic retry), ITRIP 2.97 A
  from RIPROPI 2.0 kOhm and VREF 2.68 V (5.6k/24k from 3V3_D). nSLEEP of both on Motors_Enable
  (PA10) with R49 100 kOhm to GND; nFAULT of both wire-ORed on Motors_nFault (PC15) with R60
  10 kOhm to 3V3_D. Per bridge: 100 nF + 4 x 10 uF 50 V X7R + 100 uF 25 V on VM, 100 nF VCP,
  22 nF CPH-CPL.
- **Motor path**: OUT1 -> 10 mOhm WSK2512 4-terminal shunt -> 47 uH XAL7070-473 choke -> motor
  connector; OUT2 -> connector. Each choke has a 2512 0 Ohm alternative across it, DNP: the choke
  is fitted until the motor's inductance at 100 kHz is measured.
- **Current**: INA241A2 (gain 20) on each shunt, VS and REF1 on 3V3_A, REF2 on GND: 0.2 V/A
  around VDDA / 2, about +7.1 / -8.0 A, into PC0 (left) and PC1 (right) through 100 Ohm with
  1 nF C0G at the pin. A DNP 0 Ohm from each DRV8874 IPROPI to the same ADC net lets the first
  prototype compare the driver's mirror (fit it and remove the 100 Ohm).
- **Battery current**: the INA228 on R59 (+-20.48 A at ADCRANGE = 1), read by the ESP32.

## Fan

STSPIN958 in parallel half-bridge mode, PWM trimming, on TIM12 at 400 kHz: R31 25 mOhm, REF from
22k/9.1k on 3V3_D (current limit 3.86 A), RSR 1 kOhm (2 V/ns), 2 x 470 nF 50 V + 2 x 10 uF 50 V
on VS, and a 4.7 uH XGL5030-472 choke between FAN_OUT and the motor with its 2512 0 Ohm
alternative (DNP). Fan_PWM PB15, Fan_Enable PB14, Fan_TOFF PB13 as on the main board.

## Sensors

- **Wall sensors**: the four SFH 4550 emitters run from 3V3_D through 3.3 Ohm each into their
  AO3400A selectors (DC gate drive from Wall_Sensor_PWM_n through 220 Ohm, 10 kOhm pull-down),
  whose sources share one constant-current sink: TLV9001 + AO3400A + 1.2 Ohm 0.1 %, set to
  175 mA by a 10k/680 divider of 3V3_A. The phototransistor collectors are on 3V3_A.
- **IMU** and **encoder slots**: as on the main board, on 3V3_D.

## ESP32 and USB

- **ESP32-S3-MINI-1-N8** (U13) on 3V3_D with 10 uF + 100 nF (22 uF optional, DNP), EN RC
  10 kOhm / 1 uF, GPIO0 pulled up. Recovery pads `ESP_EN` and `ESP_BOOT` (hold BOOT to GND and
  pulse EN after a crashed USB OTG application).
- **USB-C** D+/D- through U6 (USBLC6) and 22 Ohm series resistors to GPIO20/GPIO19 only: the PC
  sees the ESP32 (CMSIS-DAP v2, CDC and mass storage), never the MCU. CC 5.1 kOhm Rd; SBU open.
- **Links to the MCU**: SWDIO GPIO11 -> PA13, SWCLK GPIO12 -> PA14 (22 Ohm), NRST GPIO13
  (open drain), BOOT0 GPIO14 through 1 kOhm (R42 keeps it low), UART1 GPIO17/18 <-> UART4
  PA11/PA12 at up to 5 Mbaud (100 Ohm on the ESP's TX), flow control GPIO21 -> PH1.
- **The ESP's own lines**: INA228 I²C on GPIO8/9 with ALERT on GPIO10; VBUS sense on GPIO7
  through 22k/33k (3.15 V at 5.25 V).
- **SWD backstop**: test pads SWDIO, SWCLK, NRST and GND on the MCU side.

## Pins

The MCU keeps the main board's pin map except: PA8/PA9 and PC7/PC9 carry EN/PH of the right and
left bridges; PA11/PA12 carry UART4 to the ESP32 (no USB); PC15 reads Motors_nFault; PH1 reads
ESP_Flow; PA13/PA14 and NRST go to the ESP32 instead of the SWD connector. Every GPIO of the
VFQFPN68 is now used.

## Firmware changes

[`firmware_changes.toml`](../firmware_changes.toml) lists what the firmware must change against
the v1 firmware (`boards/main/firmware.toml`), on top of the main board's own pending changes:
PH/EN drive at 100 kHz with TIM3 slaved to TIM1; Motors_Enable as nSLEEP (1 ms wake);
Motors_nFault on PC15; INA241 sampling on TIM1 TRGO2 with dual injected ADC1/ADC2; the battery
divider constant 6.0; the fan at 400 kHz; UART4 to the ESP32 at up to 5 Mbaud with ESP_Flow on
PH1; one wall emitter at a time; the WS2812C timing (T0L/T1L at most 1 us); flashing through the
ESP32's CMSIS-DAP with OpenOCD or probe-rs.

## Layout

Not started. When placement starts, the root's `Project(layout = False)` becomes the main board's
`Board(...)` (the same 4-layer 1.0 mm JLCPCB stackup and rules), a `spec/main2.toml` takes the
mechanical interface, and the layout gates apply. Placement notes from the research, all
decisions for the owner:

- **ESP32**: the rear-left corner with the PCB antenna 5.05 mm beyond the rear edge, its feed
  end at the corner; this needs the screw hole M1 moved, the corner squared and the left drive
  block about 1 mm forward. No copper on any layer under the antenna (the footprint carries the
  keep-out), dense GND vias along its edge, the bridges and the USB/UART lines away from it.
- **Bridges**: each DRV8874 next to its motor connector with its shunt, choke and INA241; tight
  OUT -> shunt -> choke -> motor loops; size the battery input, Q6, the VBAT plane and the bridge
  supply for about 6 A peak and 3-4 A rms.
- **Analog**: U8 near VDDA and away from the IMU; 3V3_A as its own trace to VDDA, the INA241s
  and the sensors; the emitter loop and the 1.2 Ohm sink Kelvin-connected, away from VDDA/VSSA;
  no motor, emitter or ESP return current through the analog ground.
- **Chokes**: shielded parts away from the AS5047U encoders and the IMU.

## Open items

Each is a visible TODO in the sheet that owns it.

- Battery input: reverse-polarity protection and a TVS; a switch rated for the 4S pack in place
  of SW4 (12 V DC); the B02B-PASK rating at about 5 A.
- Bridge bulk: a low-ESR polymer capacitor (the research's 100-220 uF) needs a component
  package; the 25 V electrolytic stands in, with four ceramics per bridge for the ripple.
- Choke 0 Ohm alternatives: the 2512 jumper's current rating.
- Emitter sink: the set-point is always on (the research asks it off between pulses); a
  selector held on puts 175 mA DC through an emitter; the TLV9001 loop's step response with
  Q9's gate.
- Fan: the REF setting for the chosen motor.
- Current inputs: the CubeMX check of the fast-ADC-channel swap; R_iso + C_f stability.
- 3V3_A: the LDO's board-level thermal limit at about 0.33 W.
- Status LEDs: blue and green at 3.2-3.3 V (bench).
- ESP32: the antenna bench test in the chassis decides between the MINI-1 and the MINI-1U-N8
  (C2980299, external antenna, same footprint family).
