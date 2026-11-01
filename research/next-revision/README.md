# Next main-board revision: design

Research for the second revision of the `main` board. The design is entered in Zener as the board
[`main2`](../../boards/main2/layout/README.md) (schematic and layout), with the option this document
recommends wherever it lists several, the datasheet checks as test benches, and the open items
below as visible TODOs in its sheets; `boards/main` stays the current board. Every hardware number
below carries its source; values marked
*computed* come from the scripts in [calculations/](calculations/), and *inference* marks a
conclusion that no datasheet states directly. Open items are kept as visible **TODO**s.

- [Design basis](#design-basis)
- [Architecture](#architecture)
- [Parts](#parts)
- [The owner's questions](#the-owners-questions)
- [Series choke with a motor: downsides](#series-choke-with-a-motor-downsides)
- [What does not make sense, and why](#what-does-not-make-sense-and-why)
- [Bench measurements before committing](#bench-measurements-before-committing)
- [Open decisions](#open-decisions)
- [Gaps and TODOs](#gaps-and-todos)
- [Calculations](#calculations)
- [Sources](#sources)
- [Appendix: prototype connection lists](#appendix-prototype-connection-lists)

## Design basis

Fixed by the owner:

| Decision | Consequence |
|---|---|
| Drive motors: maxon **DCX 10 L 4.5 V**, one per wheel | 2.9 Ω, 0.045 mH, kt 3.52 mNm/A, 2710 rpm/V, 0.648 A continuous, 14,300 rpm maximum, τw 3.94 s, 11 g ([maxon p100]) |
| Battery: **4S LiPo**, bridges straight from the switched pack, **no boost** | Pack 12.0-16.8 V (17.4 V with HV cells); the TPS61178 boost and its parts go |
| **No USB** on the board | Every rail comes from J1 (a bench supply into J1 on the bench), but for flashing: a programmer's 5 V pin on J2 or SWD1 (5V_IN, through D17) runs the 3V3 rails without the pack; the radio flashes over its UART0 header J2 and over the air; no H7 USB or DFU path |
| The **ESP32-C5 replaces the HM-19 module and the SWD connector** | It flashes the H7 over SWD with NRST as a Wi-Fi debug probe, carries the H7's link (SPI3, UART4 as a fallback on the same pins) and relays 5 GHz Wi-Fi telemetry; the bare SWD1 pads take an ST-Link |
| Digital 3V3 from the **L6981C33 buck**; analog 3V3_A from a **battery-side LDO** | No 5 V rail; the status LEDs become a 3.3 V part |
| Fan: a generic, not yet chosen **drone-class brushed coreless motor** (high rpm, low R), PWM preferably about **400 kHz**, **no buck** | The STSPIN958 stays, reconfigured |

The motor fits because the DCX 10 L 4.5 V on 4S is traction-limited at every bus voltage. At G =
4.27 for 4 m/s it holds the traction limit for 100 % of a 60 s run at the measured 1.47 N of suction
and 22 % at the 4 N fan target, and it needs only about 9.4 V (1.47 N) or 14.2 V (4 N) at 4 m/s, so
a sagged 4S pack still drives it (drivetrain/extra.py, vreq.py). The 45th All-Japan classic winner
ran "DCX10L-4.5" on a 4S 14.8 V 180 mAh pack with TB67H450FNG drivers at 90 g ([NTF TechCA41]).

On 4S the pack absorbs regenerated energy (through Q6's body diode if Q6 is off), and peak pack
current is about 4.5-5 A, against about 6-7 A for 3S plus a boost (inference; boost efficiency
assumed 90 %). The TPS61178 could not stay anyway: recommended VOUT tops out at 20 V and OVP at
20.5-21.5 V; boosting 16.8 V to 18.8 V needs a 10.6 % duty, below its 16.7 % minimum on-time at
1.24 MHz; in auto-PFM it cannot sink current ([TPS61178] §7.3, §7.7, §8.4).

## Architecture

```text
4S LiPo 12.0-16.8 V (17.4 V HV) ─ J1 + ─ F1 0501012 12 A fuse ─ VBAT;  J1 − ─ GND_BAT ─ Q6 HSBB3072 (SW4, slew-limited low-side switch) ─ GND
   [reverse polarity: keyed connector only]  [TVS D15 SMAJ18A from VBAT to GND_BAT, behind F1]
   VBAT ─┬─ DRV8874 (right) ─ WSK2512 10 mΩ ─ XAL7070-473 47 µH ─ DCX 10 L 4.5 V   INA241A2 on the shunt
         ├─ DRV8874 (left)  ─ WSK2512 10 mΩ ─ XAL7070-473 47 µH ─ DCX 10 L 4.5 V   INA241A2 on the shunt
         ├─ STSPIN958, 400 kHz, REF limit ─ XGL5030-472 4.7 µH ─ fan motor
         ├─ R44/R45 20k/2k ─ PC5 (battery voltage)
         └─ D14 B5819W Schottky 40 V ─ VSYS (11.4-17.4 V; 3.8-5.0 V on 5V_IN alone)
   5V_IN (a programmer's 5 V pin: J2 pin 2, SWD1 pad 4) ─ D17 B5819W ─┘
                                          ├─ L6981C33 ─ 3V3_D: H7 VDD/VDDSMPS, ESP32-C5-MINI-1, encoders, IMU,
                                          │              WS2812C-2020-V6 ×2, IR emitters (3.3 Ω each) → AC-coupled selectors → CC sink
                                          └─ 22 Ω + 10 µF ─ ADP7142ACPZN3.3 (EN = 3V3_D) ─ 3V3_A:
                                                 VDDA (1 µF + 100 nF), INA241A2 VS + REF1, phototransistor collectors,
                                                 emitter-sink op-amp (set-point from the DAC on PA5)
ESP32-C5 ─ SWDIO GPIO0 / SWCLK GPIO1 / NRST GPIO23 ─ H7;  ESP_Flow GPIO24 ─ PA9
ESP32-C5 ─ SPI3 half-duplex (H7 master): SCK GPIO10 ─ PC10, DATA GPIO8 ─ PC12, CSn GPIO9 ─ PC11  (UART4 fallback on PC10/PC11)
ESP32-C5 UART0 TX0/RX0, EN, GPIO28, 5V_IN ─ J2 2 × 3 1.27 mm header (ESP-Prog Program interface)
H7 SWDIO / SWCLK, 5V_IN ─ SWD1 bare 1.27 mm pads (clone ST-Link order: 1 SWDIO, 2 GND, 3 SWCLK, 4 5V)
DRV8874 nFAULT ×2 wire-OR ─ PB2
```

### Power tree

- **VSYS** is VBAT behind D14, a B5819W 40 V 1 A Schottky (C8598, JLC basic; loss ≈ 0.32 V ×
  0.13 A ≈ 40 mW at 14.8 V, JCET B5817W-B5819W p2), ahead of both regulators: 11.4-17.4 V, the
  pack less D14's 0.6 V maximum drop (p1). D14 blocks VSYS → VBAT, so nothing on VSYS reaches
  VBAT, the bridges' bulk, the battery divider or the pack. It also keeps a VBAT driven below GND
  (D15 forward with a pack forced in reversed, until F1 opens) off the regulators' inputs. The
  B5819W's typical curves (JCET p2): VF 0.32 V at 25 °C and 0.23 V at 100 °C at the 0.13 A it
  carries; reverse 5-6 µA at 25 °C, 55-64 µA at 75 °C, 0.42-0.59 mA at 100 °C at 1-5 V.
- **Programming power, 5V_IN**: a USB-serial adapter's or a clone ST-Link's 5 V pin (USB VBUS,
  4.40-5.25 V, USB 2.0 Table 7-7) on J2 pin 2 or SWD1 pad 4 feeds VSYS through D17, a second
  B5819W, so the board flashes without the pack; its 3.3 V pin goes nowhere (a 3.3 V pin on 5V_IN
  leaves VSYS at about 3.0 V, under the L6981's 3.5 V: the buck may still start, its VCC rising
  threshold being 2.3-3.3 V ([L6981] Table 6), and run in dropout, 3V3_D about 2.8-2.9 V, below the
  C5's 3.0 V; nothing is damaged). Computed
  ([power_path_checks.py](calculations/power_tree/power_path_checks.py) section 2,
  [calc_power_tree.py](calculations/power_tree/calc_power_tree.py) section 6):
  - 5V_IN draws 0.19 A flashing the C5 over J2 (its Wi-Fi off), 0.25 A flashing the H7 over SWD1
    with the C5's Wi-Fi associated, 0.53 A at the C5's 5 GHz TX peak (Table 6-5, rated at 100 %
    duty; the L6981 at an assumed 85 %): the flashing cases sit inside a USB port's 500 mA.
  - VSYS is 4.38-4.40 V on a 4.75 V port, 3.80 V at worst (a 4.40 V port, D17 at its 0.6 V
    maximum), about 5.0 V at most (a 5.25 V port, D17 about 0.25 V at a light load). The L6981's
    duty limit, 1 − 185 ns × 440 kHz = 0.919 ([L6981] Table 6, Eq. 45 with RDSON +20 % and L3's
    DCR), keeps 3V3_D regulated from 3.72 V at the flashing load and 3.86 V at the TX peak; the
    current loop needs ISLOPE ≥ 0.177 A at that duty and fSW's 360 kHz minimum, 0.22 A with L3 at
    −20 %, which it has ([l6981_slope.py](calculations/power_tree/l6981_slope.py)). The ADP7142
    regulates 3V3_A from LDO_IN 4.16 V typical (about 20 mV typical dropout at 10 mA, [ADP7142]
    Figure 22, the 3.3 V part's curve; Table 1's dropout limits are for VOUT = 5 V); at the worst
    corner LDO_IN is 3.30 V and 3V3_A about 3.27 V typical, not guaranteed: analog readings on
    5V_IN are for checking only.
  - The programmer's own fuse and lead drop part of its VBUS before the board: below the margins
    above, the buck runs at its maximum duty and 3V3_D follows VSYS, about 3.2 V at VSYS 3.6 V,
    still enough to flash (the H7 runs from 1.62 V, the C5 from 3.0 V).
  - At plug-in the programmer's 5 V charges VSYS's 11 µF and LDO_IN's 10 µF through D17, about
    21 µF against the 10 µF USB 2.0 §7.2.4.1 allows a device at attach, then the buck's 1.0-1.6 ms
    soft start ([L6981] Table 6) charges 3V3_D at about 0.3 A from 5V_IN: under a port's 500 mA, so
    no fuse trips, and the programmer's VBUS only dips briefly.
  - With the pack in, D17 blocks up to the 24.2 V clamp (61 % of its 40 V); its reverse current
    (12 µA at 25 °C) goes into the programmer's 5 V rail. Without the pack, D14 leaks into VBAT,
    which the battery divider's 22 kΩ holds at 0.13 V at 25 °C, 1.1 V at 70 °C and 3.42 V at 85 °C;
    with the pack in and SW4 off, Q6's off-state leakage adds about 0.5 V (IDSS is specified only
    at 25 °C), about 3.9 V: the DRV8874s (UVLO 4.3 V min) stay off. The STSPIN958's VS turn-on has
    a 5.05 V maximum and no minimum, so it is not counted on: its output stays Hi-Z with EN/nFAULT
    low, or on its low side with PWM1 held low by its internal pull-down ([STSPIN958] Tables 5 and
    11), and the firmware keeps Fan_Enable low and reads "no pack"
    (`boards/main2/firmware_changes.toml`, battery).
- **Bench power without a pack**: a current-limited supply at 12-16.8 V into J1 (a lead with the
  pack's JST PA plug) with SW4 on; the board starts as from the pack. With the motors and the fan
  disabled, a limit just above what the 3V3 rails draw keeps a fault on VBAT from taking the
  supply's full current, and D15 clamps the supply's hot plug (VBAT overvoltage, below).
- **Battery input** (Regulators.zen): J1 is a JST PA header, 3 A AC/DC with AWG #22 leads, 10 mΩ
  max per contact, −25 to +85 °C including its own rise (JST PA catalogue): the battery path's
  3 A rms firmware limit sits inside it, its 5-6 A peaks last under 1 s. F1 interrupts 150 A at
  32 VDC ([Littelfuse 501] note 1). A 4S pack's short circuit is one cell's, VCELL / RCELL: the
  lowest ohmic resistance published for cells of the pack's class is 52.8 mΩ (a 1S 180 mAh cell;
  1S cells of 100-220 mAh measure 52.8-131 mΩ, [Takeyuta Lab]), so 4.35 V gives 82 A at most,
  before the leads, J1 and F1. 150 A would need cells under 29 mΩ, the class of 300 mAh and
  larger high-rate packs. SW4's ON position is the lever at pin 3 (B): the slider's contact
  rides under the lever, and the SK-12D29-GXXX drawing's end view and SCHEMATIC show the same
  pairing; a reversed reading would only swap the silkscreen's ON and OFF. Q6's model in
  vbat_bulk.py is fitted to the HSBB3072's typical curves (Fig. 1, 2, 4, 7; within 0.1 V of the
  Miller plateau and 15 % of RDS(on)).
- **3V3_D**: the L6981C33 stays (1.5 A, 3.5-38 V, output network 30.5-145 µF at 3.3 V; [L6981]
  §8.4.3). Its LCM light-load step (+1.8 %, §6.4.1) no longer reaches the ADC, because the analog
  loads are on their own rail. The ESP32-C5 adds up to 426 mA of 5 GHz TX peak and asks for a
  supply of at least 0.6 A ([ESP32-C5-MINI-1] Tables 6-2, 6-5); 22 µF + 100 nF at the module
  (Figure 9-1) and 10 µF on its feed keep the 3V3 total at about 104 µF, inside the 145 µF window.
- **3V3_A**: an HV LDO fed from VSYS through **22 Ω + 10 µF**: the **ADP7142ACPZN3.3** (fixed
  3.3 V, 2.7-40 V, 44 V abs max, 11 µVrms, 68 dB at 100 kHz and 50 dB at 1 MHz, 80 µA ground
  current at 10 mA; LFCSP 72 °C/W, TSOT 170 °C/W, so the LFCSP; [ADP7142] Rev K Tables 1-4) on
  the board. The **TPS7A4901** (adjustable 1.194-33 V, 3-36 V, 15.4 µVrms, ≥ 52 dB 10 Hz-400 kHz,
  dropout 260 mV at 100 mA, ≥ 2.2 µF ceramic output; [TPS7A49] p1, §6.4, §6.5) is the cheaper
  alternative; it takes another footprint (HVSSOP-8) and a feedback divider, and the ADP7142's
  heat, EN thresholds and drift below leave no reason to change.
  - **Loads**: VDDA (the ADCs and, on VFQFPN68, VREF+), both INA241A2 VS and REF1, the four
    phototransistor collectors, the emitter-sink op-amp and its bias: **9.7 mA typical,
    22.5 mA worst case** (all receivers saturated), +0.65 mA if the IMU moves here
    (power_tree/calc_power_tree.py §1, from DS13311 Tables 84/87/90, SBOSA30D §6.5, SBOS833R §7.10).
    Table 84's VDDA currents are per ADC and guaranteed by design for every package (its note 3,
    BGA and one ADC, covers only the sampling rate), so ADC1 and ADC2 count twice: 1.44 mA
    single-ended, 2.88 mA if both ran differential; the set-point DAC (buffer off) adds 20 µA on
    VDDA and 160 µA on VREF+, which is VDDA on the VFQFPN68 (Table 90).
  - **Heat**: about 113 mW at 10 mA from 14.8 V and 320-330 mW at 22.5 mA from 17.4 V. In the
    ADP7142's LFCSP that is +27 K at 83.9 °C/W, the 500 mm² row of [ADP7142] Rev K Table 6 (71.7 °C/W
    at 1000 mm², 182.8 °C/W on minimum traces; Table 4's JEDEC 4-layer board 72.1 °C/W): the
    exposed pad sits on the F.Cu GND pour with two vias to the In1/In2 GND planes, more copper than
    that row, so the junction stays at 112 °C at an 85 °C ambient, inside the 125 °C limit. Rev K's
    Figures 53-54 draw the 500 mm² line steeper, about 143 °C/W: 131 °C at 85 °C, 19 K below the
    150 °C shutdown and inside 125 °C up to a 79 °C ambient. Keep the LDO away from the IMU.
  - **Drift**: 3.24-3.36 V over load, line and temperature (±1.8 %, Table 1), −1.2/+1.5 % to 85 °C.
    No tempco is guaranteed; the typical curve (Figure 16, VOUT = 3.3 V) moves about −0.1 % from
    25 to 65 °C and −0.12 % to 85 °C, so the ±0.2 % residual after a room-temperature calibration
    (Q1) holds on the typical part with 2× margin. A guaranteed bound needs the firmware to track
    VDDA with VREFINT (DS13311 Table 21: 70 ppm/°C max, ±0.28 % over a 40 K swing).
  - **Input filter**: the 22 Ω drops 0.5 V at the 23 mA worst-case load, leaving the LDO at 10.9 V
    or more. The RC keeps the 100 kHz motor ripple out of the LDO, whose PSRR is lower there than at
    kHz (power-tree study §9).
  - **Sequencing**: the LDO EN on 3V3_D, so 3V3_A starts after VDD. While VDD is below VDDmin, VDDA
    must stay below VDD + 300 mV; at power-down VDD may fall below the others only if the energy
    left is below 1 mJ (DS13311 §3.7.1, Figure 2). The ADP7142's EN turns on at 1.30 V at most and off
    at 1.06 V at least (Rev K Table 1); the TPS7A4901's at 2.1 V and 0.4 V ([TPS7A49] §6.5).
  - **VDDA pin**: 1 µF + 100 nF (AN5419 Table 2). FB1 (600 Ω, 340 mΩ DCR) becomes a 0 Ω link or a
    ≤ 50 mΩ bead: its DCR times the ADC current step is about 0.24 mV = 5 LSB at each scan start
    (inference; the bead is not in the model).
  - **Ratiometry**: INA241 REF1 and VS sit on the same 3V3_A node as VDDA, and the emitter-sink
    set-point comes from the DAC, whose reference is VREF+ = VDDA, so wall and current readings are
    ratiometric to the ADC reference (power-tree study §1).
- **Documented alternative for 3V3_A**: a forced-PWM **TPS560430X3FDBVR** (fixed 3.3 V, 1.1 MHz,
  4-36 V, SOT-23-6) with the datasheet 12 µH / 22 µF network, then a damped LC (2.2 µH ≤ 50 mΩ,
  22 µF, and a 0.33 Ω + 47 µF damping leg), EN on 3V3_D ([TPS560430] Table 1, §7.5). It must stay a
  forced-PWM part (LMR43610MB3 with MODE forcing FPWM, or TPS62933F, also qualify): a PFM/LCM buck
  skips pulses at 10 mA. The trade, from the switching-level model (power-tree study §4-§5,
  power_tree/out/summary.txt; LSB = LSB16 at full scale, 50.35 µV):

  | | LDO from VSYS (recommended) | Forced-PWM buck + damped LC (alternative) |
  |---|---|---|
  | Loss | ≈ 113 mW (10 mA, 14.8 V); 328 mW worst (23 mA, 17.4 V) | ≈ 50-60 mW; ≈ 70 mW worst |
  | VDDA in-window rms | **0.3 LSB** (incl. 15.4 µVrms LDO noise) | 0.8 LSB |
  | Scan-mean spread (25 windows) | **1.4 LSB** | 1.8 LSB |
  | Lit − dark | **0.6 LSB** | 1.7 LSB |
  | Battery → VDDA at 100 kHz | −101 dB | −102 dB |
  | Parts | LDO, 22 Ω, 10 µF in, output cap (+ FB divider, CNR/SS, CFF for the TPS7A4901): 6-8 | buck, 12 µH, CIN, CBOOT, 22 µF, 2.2 µH, 22 µF, 0.33 Ω + 47 µF: 9 |
  | Area (estimate) | ≈ 35-45 mm² | ≈ 55-65 mm² |
  | BOM (LCSC, qty 10) | ADP7142ACPZN3.3 $2.88 (C659360) or TPS7A4901DGNR $1.26 (C16430) | TPS560430X3F $1.19 (C2071721) + ≈ $0.3-0.5 passives |
  | Risks | the input RC must keep the 100 kHz motor ripple out (LDO PSRR is lower there); package thermal at ≈ 0.33 W: 112 °C at an 85 °C ambient in the ADP7142's LFCSP (Heat, above) | must stay forced PWM; damping must be right (series damping gives a 60 LSB lit/dark shift); another switching hot loop near the analog section |

  The model's LDO case used 47 Ω; at ≤ 22 Ω the window spread, which comes from that pre-resistor,
  roughly halves (inference, power-tree study §4). At 10-20 mA the buck saves only 0.06-0.26 W, so the
  LDO is the quieter, smaller and simpler rail.
- **No 5 V rail** (5V_IN is a programming input into VSYS, not a rail): the ESP is on 3V3_D, the LEDs are 3.3 V parts, the INA241 runs from 2.7 V, the
  DRV8874 and STSPIN958 regulate internally from VM, and the emitters are on 3V3_D.
- **4S ratings**: C36 (16 V) becomes ≥ 25 V; SW4 (MK-12D18-G040, DC 12 V) becomes the G-Switch SK-12D29-G060
  (DC 24 V 1 A, 1.38× the 17.4 V HV pack; the same 8.6 × 3.6 mm body with a 6.0 mm black lever; three
  pins at 2.0 mm pitch and two frame legs, so a new footprint; `components/g-switch/SK-12D29-G060`);
  R44/R45 (100k/27k gives 3.57-3.70 V, above VDDA) becomes 20k/2k on PC5, 1.58 V at 17.4 V and
  2.20 V at D15's 24.2 V clamp (firmware constant 11.0): a ratio of 6 (10k/2k or 100k/20k) puts
  4.03-4.10 V on PC5 at the clamp, above the 4.0 V absolute maximum of its TT_ha pad ([DS13311]
  Tables 10-11), and 22 kΩ holds VBAT near 0 V on 5V_IN alone where 120 kΩ lets it float to VSYS
  above about 50 °C ([power_path_checks.py](calculations/power_tree/power_path_checks.py) section
  2); its 1.82 kΩ Thevenin source holds the ADC sample with C59 100 nF;
  25 V capacitors sit at 67 % of rating on 4S (drivetrain study §4).
- **Battery switch**: Q6 HSBB3072 stays: VDS 30 V (1.79× margin at 16.8 V), VGS = VBAT/2 = 6-8.4 V,
  0.61-0.97 W at 16 A. It gives **no reverse-polarity protection**: its body diode conducts with
  the pack reversed (driver study Q6); the connector keys the polarity.
- **VBAT capacitance, all ceramic** (calculations/power_tree/vbat_bulk.py): the board carries
  only ceramics, a choice on merit. Liquid electrolytics are out (the owner's rule); solid polymer,
  aluminium or tantalum, is allowed where it makes the better circuit, and is weighed below. On
  VBAT the bulk does four jobs; with a 4S pack and the slew-limited Q6 the ceramics cover each:
  - *100 kHz ripple*: the bridges draw I·√(D(1−D)) each; the ceramics carry it (0.2-0.4 A rms per
    part, against 2.6 A for a 10 °C rise on the 1206's Samsung curve; the 1210 has the larger body). An electrolytic adds almost
    nothing at 100 kHz: its ohm-level ESR leaves it 0.15 A.
  - *Damping the pack leads against the ceramics*: the pack's own 0.1-0.3 Ω (the 0.5-1.5 V sag at
    5 A) is above the LC's characteristic impedance (42-73 mΩ at 100-300 nH), so the source does not
    ring (Q ≤ 0.72). A bench supply on 1 m leads (1 µH, 30 mΩ) does (Q ≈ 4); keep bench leads short.
  - *Hot plug and switch-on*: Q6 sits between the pack and the capacitors and stays off at
    plug-in: C58 100 nF from gate to source holds the gate at 0.3-0.4 V against the edge that C114
    1 nF and Crss couple from the drain, so the board sees no edge (0.002 V/µs) and the pack charges
    only Q6's output capacitance (its VDS rings to 22-24 V, under D15's clamp). With only a
    gate-drain capacitor (the main board's C58) the edge turned Q6 on at 3.3-3.6 V and the
    ceramics charged at 89-135 A, slewing VBAT at 1.3-2.0 V/µs, above the STSPIN958's 0.5 V/µs
    dVS/dt absolute maximum (DS14341 Table 1). Closing SW4 starts VBAT after 1.7 ms and ramps it in
    0.40 ms (0.042 V/µs; C114 + Crss set the Miller slew); opening it under a 5.8 A load starts
    the fall after 12.9 ms and takes 2.1 ms: no inductive kick on Q6. A 2.2 µF gate-source
    capacitor instead also keeps Q6 off but delays switch-off by 270 ms (vbat_bulk.py section 8,
    with Q6's model fitted to the HSBB3072's typical curves).
  - *Regeneration*: with the pack connected it takes the braking energy (through Q6's body diode
    when Q6 is off). With the pack pulled while the firmware brakes, no capacitor bank absorbs it
    (see VBAT overvoltage below).

  Options per bridge, as the bulk beside the four 10 µF 50 V X7R 1206 at each DRV8874 (the board's
  VBAT also has the fan's two 1206). VBAT ripple: both bridges at 3 A, D = 0.5, in phase (the
  worst case; the interleave is untested) plus the fan at 2.5 A, 0.1 Ω pack on 100 nH, 16.8 V;
  the power-tree model assumed 150 mV pp (300 mV in its HV case). Prices JLCPCB 2026-10-17, qty 1:

  | Bulk per bridge | VBAT C at 16.8 V (board) | Ripple pp | Bulk ripple current | Area (body) | Height | Cost per bridge | Damping, ratings | LCSC |
  |---|---|---|---|---|---|---|---|---|
  | Main board: JVS25V100M6X4 100 µF 25 V on +20V (L6205), VT1C221M0605 220 µF 16 V on VBAT (fan) | – | – | 54 mA / 72 mA rated at 120 Hz | 6.6 × 6.6 mm base each (61 mm² courtyard) | 4.5 / 5.4 mm | $0.08 / $0.04 | tan δ 0.18-0.20 at 120 Hz (1.2-2.4 Ω); no 100 kHz ESR given | C51953404 / C22383774 |
  | JVS25V100M6X4 100 µF 25 V electrolytic | 232 µF | 453 mV | 0.15 A (54 mA rated at 120 Hz) | 43.6 mm² base | 4.5 mm | $0.08 | damps everything (Q ≤ 0.35 on the pack; bench peak 0.33 Ω); 1.4× the HV pack | C51953404 |
  | None (the four 1206 only) | 32 µF | 493 mV | – | 0 | – | 0 | Q 0.55-0.95 on the pack; bench Q 5.5 (0.97 Ω peak) | – |
  | 2 × CL32B106KBJNNNE 10 µF 50 V X7R 1210 | 56 µF | 285 mV (79 mV interleaved) | 0.37 A rms per part | 16 mm² (2 × 3.2 × 2.5) | 2.5 mm | $0.66 | Q 0.41-0.72 on the pack; bench Q 4.2 (0.56 Ω peak); 50 V, 2.9× the HV pack | C138687, 79 k stock |
  | **Chosen: the four 1206 replaced by 4 × CL32B106KBJNNNE 1210 per bridge, the fan's two 1210 too (no 1206 on VBAT)** | **61 µF** | **265 mV** (77 mV interleaved) | **0.34 A rms per part** | **32 mm² per bridge (against 36.5 mm² for 4 × 1206 + 2 × 1210)** | **2.5 mm** | **$1.32** | **Q 0.40-0.69 on the pack; bench Q 4.0 (0.52 Ω peak); one 10 µF part on the board** | **C138687** |
  | 4 × CL32B106KBJNNNE 1210 | 81 µF | 198 mV | 0.25 A rms | 32 mm² | 2.5 mm | $1.32 | bench Q 3.5 | C138687 |
  | Panasonic 25TQC33MYF 33 µF 25 V polymer tantalum | 98 µF | 212 mV | 0.88 A rms (1.4 A rated at 100 kHz) | 31.4 mm² (7.3 × 4.3) | 1.9 mm | $0.94 | ESR 60 mΩ ≈ Z0: damps the bench too (0.24 Ω peak); 25 V, used at 70 % on the HV pack (Kyocera-AVX TCJ: 80 % of Vr ≥ 16 V up to 85 °C, less above); transients must stay ≤ 25 V (Panasonic TQC); fails short | C191808, 4.3 k stock |
  | Panasonic 25TQC100MD3 100 µF 25 V polymer tantalum | 232 µF | 183 mV | 1.0 A rms (1.6 A rated) | 31.4 mm² | 2.8 mm | $2.50 | as above (bench 0.10 Ω peak) | C3018702, 4.6 k stock |
  | Hybrid: ceramics + R-C damping leg | – | – | – | – | – | – | a damping leg needs about 4× the ceramic capacitance (≈ 130-220 µF) behind R ≈ Z0 (0.1-0.2 Ω): an electrolytic- or polymer-sized part, or 30-60 more MLCCs; a small R-C does not damp | – |
  | The chosen ceramics + 1 × JIERR MA35V47M6X6 47 µF 35 V solid-polymer aluminium on VBAT | 108 µF | 176 mV (64 mV interleaved) | 1.10 A rms (2.65 A rated at 100 kHz) | 6.6 × 6.6 mm base | 6.0 mm | $0.14 | ESR 35 mΩ: bench Q 3.0 (0.25 Ω peak); 35 V, 69 % at the 24.2 V clamp; leakage ≤ 500 µA ([JIERR MA]) | C46550468, 36 k stock |
  | The chosen ceramics + 1 × JIERR MA35V100M6X8 100 µF 35 V solid-polymer aluminium | 161 µF | 152 mV (63 mV) | 1.43 A rms (2.9 A rated) | 6.6 × 6.6 mm base | 7.7 mm | $0.22 | ESR 30 mΩ: bench Q 2.5 (0.16 Ω peak); leakage ≤ 700 µA | C46550467, 64 k stock |
  | The chosen ceramics + 1 × Panasonic OS-CON 35SVPF22M 22 µF 35 V | 83 µF | 202 mV (65 mV) | 0.77 A rms (2.6 A rated) | 6.3 mm can | 5.9 mm | $1.21 | ESR 35 mΩ: bench Q 3.4 (0.36 Ω peak) | C88142, 725 stock |

  KEMET T521 25 V polymers (T521V226M025ATE040, T521D476M025ATE065) have no JLCPCB stock; 35 V
  polymers come at 10-15 µF (Panasonic 35TQC, 120-150 mΩ) or in 4.1 mm E cases (Kyocera-AVX
  TCJE476M035). The 1210 holds twice the 1206's capacitance at 16.8 V (6.1 against 3.2 µF, Samsung
  DC-bias curves: −39 % against −68 %) in a third more area, so four 1210 do the work of four 1206
  and two 1210 in less area and with one part number; two per bridge already bring the ripple
  inside the 300 mV of the analog-rail model's HV case at a sixth of the electrolytic's footprint
  and half its height, rated at 50 V. What the ceramics give up: the damping of a bench supply on
  long leads, and some milliseconds of regeneration hold-up.

  The 35 V solid-polymer aluminium parts JLCPCB stocks (the JIERR MA series, "aluminum solid
  capacitors"; Panasonic OS-CON SVPF; hybrid polymer parts, which hold liquid electrolyte, are
  not counted) clear the 24.2 V clamp with margin, which the 25 V polymer tantalums do not. One of
  them on VBAT next to the ten 1210 parts trims the in-phase ripple from 265 to 152-202 mV, the
  interleaved from 77 to 63-65 mV, and a bench supply's Q from 4.0 to 2.5-3.4; it doubles the
  time to 25 V with the pack pulled under braking (3.1 to 4.3-8.5 ms), which D15 clamps anyway.
  None of these is needed: the ripple reaches VDDA about 100 dB down (R58/C80 and the LDO's
  PSRR), the pack itself does not ring (Q ≤ 0.69), and Q6 holds the bank off at plug-in, so a
  bench supply's leads never ring against it then. Against that, the part is a 6.6 mm square can
  6-7.7 mm high, which fits only off the drive blocks' zones (8 mm there, spec/main2.toml), it
  adds up to 0.5-0.7 mA of leakage on the pack (0.2 CV or 500 µA, [JIERR MA]). So the board
  stays all ceramic; the polymer rows are in vbat_bulk.py should a bench supply
  on long leads become the normal way to run the robot.
- **VBAT overvoltage and the TVS** (calculations/power_tree/vbat_bulk.py). The lowest ratings on VBAT
  and VSYS: Q6 HSBB3072 (30 V VDS, with the pack connected), then 40 V (DRV8874 VM abs max, B5819W),
  42 V (L6981 VIN), 44 V (ADP7142), 62 V (STSPIN958 VS). Per case:
  - *Hot plug*: none from the pack (VBAT ≤ 17.4 V, Q6 VDS ≤ 3.4 V); 24.2 V from a bench supply on
    1 m leads (23.5 V with D15, the SMAJ18A).
  - *SW4 off, or Q6 turning off under load*: none; the back-EMF of a coasting DCX 10 L 4.5 V is at
    most 5.3 V at 14,300 rpm, far below the pack, so the bridges' body diodes never charge VBAT, and
    Q6's turn-off is slewed over tens of ms (no L·di/dt).
  - *Pack pulled while the firmware brakes*: each motor can push at most E²/(4R) = 1.9 W into VBAT
    at full speed (3.8 W for both; 3.2 W net of a 0.6 W logic load), from 0.64-1.07 J of kinetic
    energy (76-130 g at 4 m/s). The board's 61 µF of ceramics reach 25 V in 3.1 ms, 30 V in 5.7 ms
    and the DRV8874's 40 V in 12 ms (the electrolytics bought 12-47 ms); a stop lasts hundreds of ms.

  The TVS: **D15, SMAJ18A** (Littelfuse; VR 18 V above the 17.4 V pack, IR 1 µA max, VBR
  20.0-22.1 V, VC 29.2 V at 13.7 A, 400 W 10/1000 µs, 3.3 W on an infinite heatsink; DO-214AC
  4.8-5.3 × 2.4-2.8 × 1.9-2.3 mm, about 18 mm² with its pads; LCSC C148219, $0.11) from VBAT
  (cathode) to GND_BAT, behind the fuse F1, so a TVS that fails short opens F1. With the pack pulled
  under braking its current runs VBAT → D15 → GND_BAT and back to GND through Q6: the channel with SW4 on, the body diode with SW4 off (GND_BAT → GND is
  its forward direction). For 0.15-2 A of braking current VBAT settles at 21.2-22.4 V with SW4 on
  and 21.9-23.1 V with SW4 off (simulated at a 21 V knee; up to 1.1 V more at the 22.1 V VBR
  maximum), under every rating above, for the few hundred ms of a stop (about 1 J at most). D15
  also clamps Q6's VDS and a bench hot plug. The SOD-123FL SMF18A (200 W, RθJA 220 °C/W; 3.9 ×
  2.0 × 1.1 mm, C409420, $0.12) has the same voltages in half the area but marginal heat capacity
  for 1 J over a stop.

### Drivetrain

- **Bridges**: 2 × **DRV8874PWPR**, one HTSSOP-16 per motor, next to its motor connector with its
  shunt and amplifier ([DRV8874]). Comparison with the L6205D and the DRV8262: [Q4](#q4-l6205d-vs-drv8874-vs-drv8262).
- **Mode**: PH/EN (**PMODE = GND**). The timer PWM goes on EN and the direction on PH: EN = 0 is the
  low-side brake (Table 3), so the bridge alternates drive and low-side slow decay, the low-side
  mirror sees the current continuously, and the ripple is half that of drive/coast. In PWM mode
  IN1 = IN2 = 0 is coast (Hi-Z) and IN1 = IN2 = 1 is brake (Table 4); in coast the current
  recirculates through the body diodes and IPROPI reads nothing. Same two MCU pins per motor.
- **PWM**: 100 kHz, unipolar sign-magnitude, centre-aligned. Right motor EN on TIM1_CH1 (PA8),
  left EN on TIM8_CH2 (PC7), TIM8 slaved to TIM1 over ITR0 and the bridges interleaved 180°,
  which roughly halves the summed input ripple. In centre-aligned mode a 180° shift moves one
  bridge's on-centre onto the other's off-centre, so a trigger at CNT = 0 and CNT = ARR still lands
  on a phase centre of each bridge (inference, untested). The PH pins are GPIOs (PB8 right, PC6
  left) and LED_ARGB moves to TIM17_CH1 (PB9), freeing TIM8 (main2.zen layout pin swaps).
- **Why 100 kHz**: the DRV8874 ceiling is 100 kHz, and the INA241's PWM rejection "holds the output
  for 1 µs ... up to a PWM frequency of 125 kHz or if common-mode transient edges are separated by a
  3 µs interval or more" ([INA241] §7.3.1.1). At 200 kHz no phase reaches the 4 µs centre window
  (1 µs hold plus 1 µs settling each side) at mid duty. The edge response is characterised only at
  VS = 5 V and a 48 V step (Figure 7-1); TI's PSpice model (without the hold) at main2's VS 3.3 V and
  a 0-16.8 V edge in 150 ns settles within 6 mA from 1 µs on, and at the phase centres leaves the
  AC-CMRR tail of Figure 6-8's 105 dB plateau: 3.3 mA at D 0.5, 1.3 mA on the long phase at D 0.2/0.8,
  cancelling in the duty-weighted mean of the two centres (current_sense/ina241_edge.py).
- **Current limit**: ITRIP = VREF / (RIPROPI × AIPROPI), set to **2.5-3 A** with RIPROPI 2.0 kΩ 1 %
  (0.9 V/A), VREF = 2.25-2.7 V (computed; VREF 0-3.6 V, IIPROPI ≤ 3 mA; [DRV8874] §6.3, §7.3.3). The
  board uses 4.7 kΩ / 20 kΩ from 3V3_D: VREF 2.67 V, ITRIP 2.97 A typical (`boards/main2/Drivers.zen`).
  **IMODE = GND**: fixed off-time with auto-retry, nFAULT only for real faults. The 25 µs off-time
  ends at the next input edge ("if the state of the ... control pin inputs changes during the tOFF
  time, the remainder of the tOFF time is ignored", §7.3.3.2.1), so with a 100 kHz input the
  chopping ends at the next PWM edge. Cycle-by-cycle mode (IMODE 20 kΩ or 62 kΩ, Table 6) pulses
  nFAULT low at every chop (Figure 14), which would hit the Motors_nFault EXTI (PB2) at up to 100 kHz
  (inference). With 3V3_D's 3.284-3.346 V, 1 % resistors and AERR ±5.5 % the ITRIP band is
  2.76-3.23 A. The mirror's sensing low side conducts in drive and in brake, so the sense delay
  tDELAY never applies (§7.3.3.1) and the comparator follows the current within tBLK + tDEG.
- **Minimum pulse**: the DRV8874 specifies none. Both edges are delayed alike (tPD 400 ns) and swing
  in tRISE/tFALL 150 ns, so an EN pulse under about 0.3 µs (3 % duty, 0.5 V at 16.8 V) does not
  reach full swing; the firmware rounds such duties to 0 or leaves them to the current loop on the
  INA241 (`boards/main2/firmware_changes.toml`, drive).
- **OCP**: 6 A minimum, 10 A typical, no maximum, 3 µs deglitch (§6.5). Unregulated at 16.8 V the
  motor would draw 5.42 A at stall and 7.12 A in a full-speed reversal through a DRV8874
  (drivers/q4_drivers.py), so ITRIP, not OCP, holds the current. In a full-speed reversal at
  17.4 V the current overshoots the band's 3.23 A top by 0.94 A during tBLK + tDEG (1.7 µs, typical
  only) at maxon's 0.3·L with the choke at −20 % and DC-biased, and by at most 2.25 A with that
  timing × 1.5 and the motor's inductance left out: 5.48 A, under the OCP minimum and inside the
  INA241's +7.25 A (drivetrain/choke_check.py).
- **Thermal**: 0.70 W per bridge at the 1.0 A rms run limit (hot maximum RDS(on)): +18 K over a
  60 s run (ZθJA ≈ 26 °C/W at 60 s, [DRV8874] Figure 25, read) and +25 K steady on the JEDEC
  36.0 °C/W (Figure 21: 31-32 °C/W on a 4-layer 1 oz board with 2-4 cm² of top copper; main2's inner
  planes are 0.5 oz). A stall held at 3.23 A (about 4.2 W) gains +63 K in 1 s and +88 K in 10 s and
  reaches the 160 °C TSD minimum from 40 °C only after about a minute.
- **Choke**: **XAL7070-473MEC 47 µH** per motor. An ironless winding's inductance falls with
  frequency: maxon gives "30-80 %" of the 1 kHz datasheet value at 50-100 kHz and designs with 0.3
  ([maxon chokes] p7), Portescap "as low as 20 % of the catalogue value" at 100 kHz ([Portescap
  PWM]). Over 0.2-1.0·L, the choke from nominal to −20 % biased at 3 A (Coilcraft's saturation
  model of the part) and 12-17.4 V, at 100 kHz and D = 0.5 (drivetrain/choke_check.py):

  | | 1.0 · L | 0.3 · L | 0.2 · L |
  |---|---|---|---|
  | 16.8 V, 47 µH at 0 A | 0.45 A pp, 0.05 W | 0.69 A pp, 0.12 W | 0.75 A pp, 0.14 W |
  | 17.4 V, 37.6 µH biased at 3 A | 0.58 A pp, 0.08 W | 1.00 A pp, 0.24 W | 1.11 A pp, 0.30 W |

  The DCX 10 L continuous loss budget is about 1.28 W at its 600 s thermal limit (drivetrain/extra.py);
  at the worst corner the ripple takes 0.32 A rms of the 1.0 A rms run limit. The choke heats
  +15 K at that limit (105 mW in the DCR, at most 467 mW of core loss; [Coilcraft loss data]).
  Downsides of the choke: [below](#series-choke-with-a-motor-downsides).
- **Firmware limits** (drivetrain study §5): 2.5-3 A peak per motor in hardware (ITRIP), 1.0 A rms per
  motor over a 60 s run (0.86 A over 120 s) from 25 °C, ripple included, and about 5-6 A peak and
  3 A rms on the battery path. About 31 % duty at no load keeps the motor under 14,300 rpm at
  16.8 V, so the wheel speed command is capped at about 4 m/s at G ≈ 4.27 (or 4.6 m/s at 3.7:1).
  The pack sags 0.5-1.5 V at 5 A (assumed 4 × cell IR + 3.4 mΩ), so the bridges see about
  11.5-16.8 V and the duty feed-forward scales by the measured VBAT.
- **Bridge decoupling**: per bridge, 4 × 10 µF X7R 50 V 1210 (two within a few mm, two as bulk),
  no electrolytic ([VBAT capacitance](#power-tree)); 0.1 µF at VM. The input ripple
  is I·√(D(1−D)), about 1-1.2 A rms per bridge at 2.4 A (drivetrain study §5, driver study Q6). Size the battery input, Q6, the VBAT plane and the
  bridge supply for about 6 A peak and 3-4 A rms; each motor trace for about 3 A peak and 1-1.5 A rms.
- **Motor safety in reset**: nSLEEP of both bridges on Motors_Enable (PA10) with the R49 100 kΩ
  pull-down, so the bridges sleep while the H7 is in reset or halted for SWD flashing.
- **Motor order**: DCX 10 L 4.5 V, precious-metal brushes with CLL, article **DCX10L01EBKL531**
  (ball bearings) or **DCX10L01EBSL531** (sleeve bearings): 2.9 Ω, 0.0453 mH, 2710 rpm/V, 11 g,
  £96.35 each for 1-4 ([maxon DCX10L01EBKL531], [maxon DCX10L01EBSL531]); configurable articles,
  configured online (shaft lengths, flange, terminals) before ordering. The drawing ([maxon p100])
  gives **25.2 mm max** from the flange face to the rear of the can, plus 1.95 mm max of terminals,
  a Ø6 mm × 2.35 mm front boss with a 5.5 × 0.5 mm metric thread and a 5.6 mm front shaft: 5.2 mm longer than
  MicrasHardware's `Motor.body_l` = 20 (the 1020). With the current blocks (`micras/params.py`,
  `motor_front_y` 14.355) the left can's rear moves from y −5.6 to −10.8 mm and its terminals to
  −12.8 mm, into block_R's body (|y| ≥ 12 mm), and the right motor's rear likewise reaches block_L;
  the spec's `left_motor_can` zone (y −6 to 0 at 3.7 mm) would extend to about y −13. MicrasHardware
  must take `body_l` 25.2 and `rear_l` 1.95 and reshape the blocks before the board's zones are
  final (inference from the model).
- **Brush wear**: every DCX 10 L has precious-metal brushes, which maxon recommends for low
  continuous currents and advises against for start/stop and reversing duty ([maxon key info]).
  maxon publishes no wear figure at 4-5 × the rated current: service life is 1000-3000 h under
  average requirements, from over 20,000 h to under 100 h at the extremes, and "the CLL concept
  increases service life at higher loads" ([maxon DC technology]). Micromouse duty is minutes per
  run (tens of hours a season, inference), inside even the extreme figure; the motors are ordered
  with CLL and kept as spares. Portescap notes that an external inductance raises the electro-erosion
  of precious-metal commutators (∝ L·I², [Portescap PWM]); maxon "strongly" recommends the choke
  for CLL motors on a PWM stage ([maxon chokes] p1), and "the CLL concept suppresses spark
  generation to a large extent" ([maxon DC technology]).

### Current sensing

- **Per motor**: an in-line **Vishay WSK2512 10 mΩ 4-terminal** shunt between the bridge output and
  the motor, read by an **INA241A2IDGKR** (gain 20, −5…110 V common mode, Vos ±15 µV max, GERR
  ±0.01 % max, 1.1 MHz, 1 µs settling to 1 %; [INA241] §6.5). Range +7.25 / −8.0 A, linear and
  signed; 90 mW in the shunt at 3 A rms. The shunt must be a true 4-terminal part: 0.1 mΩ of shared
  copper is a 1 % gain error at 10 mΩ.
- **Accuracy**: ±(0.2-0.4 % + 3.5 mA) after a zero calibration with the bridge braking and a
  per-board one-point gain calibration (current_sense/q1_error_table.py). Details and the comparison
  with the driver mirrors: [Q1](#q1-ina241-vs-the-drivers-integrated-current-sensors).
- **Sampling**: TIM1 TRGO2 = Update fires at CNT = 0 and CNT = ARR and triggers ADC1 + ADC2 in dual
  injected-simultaneous mode (the mode ES0491 2.10.11 exempts from cross-instance interference),
  optional JOVSE ×4. Each sample is tagged mid-on or mid-off by the TIM1 DIR bit. Both centres are
  valid at 0.4 ≤ D ≤ 0.6 at 100 kHz; outside that the firmware uses the long phase's centre, biased by
  −3.5 to +9 mA at the datasheet L and up to ±21 mA at 0.3·L (exponential ripple curvature; a
  firmware ripple model can correct it). Offset + linearity calibration at boot, zero with the bridge
  braking at each `prepare()`, per-board gain in flash; no wall-sensor conversion overlapping the
  injected samples ([RM0468] §28.4; [DS13311] Tables 84-86). The wall sensors and the battery
  divider share ADC1/ADC2 with the currents, so the 4 pF sample capacitor arrives at another
  channel's voltage and kicks the 1 nF C_f by up to 13 mV (66 mA). The INA241's output impedance
  (about 55 Ω at 1 MHz, [INA241] Figure 6-24) makes the pin ring back rather than settle as
  R_iso·C_f: with TI's INA241A2 model, a 150 Ω R_iso keeps the error under 1 mA from 0.64 µs on in
  every corner (0.87 µs with 100 Ω), so PB1/PC1 sample for at least 0.7 µs
  ([current_sense/ina241_riso.py](calculations/current_sense/ina241_riso.py);
  `boards/main2/firmware_changes.toml`, current; [DS13311] Table 84). The model also confirms the
  output's stability: 1 nF straight on OUT, the datasheet's limit, peaks 4.2 dB; behind 150 Ω the pin
  is flat to 0.93 MHz without overshoot. The held sample trails the shunt current by the trigger
  latency, the sampling time and the 0.35 µs delay of the INA241 and R_iso·C_f at 100 kHz: the mid-on and mid-off samples
  weighted by D and 1 − D cancel that lag, a single centre carries the ripple slope times it.
- **Driver mirror**: RIPROPI + VREF set the DRV8874's internal ITRIP and need no MCU pin; IPROPI goes
  only to RIPROPI (R61/R71), where a probe can read it on the bench.
- **Battery current**: not measured. F1 fuses the battery path, and the PC5 divider gives VBAT for
  the duty feed-forward.
- **Rework test on the current board**: the INA241 pinout matches the TSC2020 MiniSO-8 except pin 4,
  which must go to ground; pin 3 is already ground, so a 3-4 solder bridge swaps the main board's two
  TSC2020 for INA241A2 (pending a check of the DGK land pattern).

### Fan

- **STSPIN958**, parallel half-bridge mode, **400 kHz** on TIM14 (ARR 687), on three MCU pins
  (Fan_PWM PA7 on TIM14_CH1, Fan_Enable PB10 driven open drain and read back as nFAULT, Fan_TOFF
  PA12). It is the only integrated single-bridge
  driver found with PWM up to 500 kHz, a cycle-by-cycle current limiter, synchronous freewheeling and
  integrated protection (OC, OT 150 °C, UVLO, EN/nFAULT) ([STSPIN958]; fan study §3).
- **Load model**: a drone-class coreless motor, R 0.2-1.2 Ω, kv 13-17k rpm/V for 1S, operating at
  1-4 A (fan study §1). No drone motor publishes its inductance, and no measurement with a stated
  method was found; the makers that publish it bound it: scaled by L ∝ 1/kv² to 13,000-20,000 rpm/V,
  the DCX 10 L 1.5 V (5 µH at 7870 rpm/V) and the Faulhaber 1024 K, 0816 K and 0615 N windings give
  0.6-14 µH at 1 kHz, and the ironless drop at the PWM frequency (0.2-1.0, [maxon chokes],
  [Portescap PWM]) leaves 0.12-14 µH at 400 kHz; a 2S motor has about 4 × that. A 1S motor on
  16.8 V runs at D = 22 %, and a locked rotor draws 13-50 A from 16.8 V (upper bound, battery IR
  excluded), so the REF limiter is also the soft start.
- **Changes**: R31 → 20-25 mΩ 1206 1 W; REF from R28 = 4.7 kΩ and R29 = 2.0 kΩ on 3V3_D: 0.985 V,
  I_peak = V_REF / (R_sense · 10) = 3.94 A (3.65-4.31 A over the tolerances); RSR 5.6 kΩ → 1-2.2 kΩ
  (1.2-2 V/ns), which cuts the switching loss 2-3.3× at 400 kHz; C36 → at least 25 V, or 2 × 10 µF
  50 V X7R 1210 at VS plus the shared VBAT bulk; C34/C35 470 nF → 50 V X7R 0805; C33 → 1 µF 50 V
  X7R 0805 (X7R beside the hot driver); L6 **XGL5030-472MEC 4.7 µH** shielded choke (5.3 × 5.5 ×
  3.1 mm, Isat 4.8 A at 20 %).
- **REF for the chosen motor** (fan/fan_choke_check.py §4): with I_run its running current at the
  highest duty the fan will use, I_peak = max(1.5 × I_run, (I_run + h) / 0.925), h the ripple
  half-amplitude at the lowest plausible inductance (1.05 A for 1S, 1.4 A for 2S); V_REF =
  I_peak × 0.25 V/A; R29 = 4.7 kΩ × V_REF / (3.3 V − V_REF), the next E24 value up. The band's top
  (× 1.093) stays at or below L6's 4.8 A: I_run up to 2.9 A (1S) or 2.66 A (2S). 2.0 kΩ suits a 1S
  motor running at up to 2.5 A; a 2S motor at 2.5 A takes 2.2 kΩ.
- **Ripple and limiter over the motor range** (fan/fan_choke_check.py §1-2; L6 at −20 % and DC-biased
  with Coilcraft's saturation model, R 0.2-1.2 Ω, 17.4 V): at 400 kHz the ripple stays within
  2.1 A pp (1S) and 2.8 A pp (2S), at most 0.76 W of ripple heat in the motor and 0.53 W of core
  loss in L6 (Coilcraft's loss-tool data for the part; +17 K with the DCR at 2.5 A). A locked rotor
  defeats the cycle-by-cycle limiter at 400 kHz for a low-resistance motor: the on-time cannot fall
  below the limiter's blanking (unpublished; 280-500 ns taken), so a 0.2-0.5 Ω stall averages
  5-13 A and may trip the 7 A overcurrent shutdown. At 50 kHz every case up to 500 ns of blanking
  stays below 7 A (peaks 4.8-5.7 A), so the fan starts at 50 kHz.
- **STSPIN958 heat** (§3): RDS(on) against temperature, the dead time and the VS operating current are
  unpublished ([STSPIN958] Rev 1, the only revision found); bound by the silicon mobility law (1.95×
  at 125 °C), 300 ns of body-diode conduction per edge, 10 mA and 45 °C/W, from 40 °C: 2.0 W and
  Tj 132 °C at 2.5 A (typical, with the DRV8874's +25 % at 125 °C, 100 ns, 7 mA and 35.8 °C/W:
  1.1 W, 80 °C). Holding the 4.31 A top of the REF band, a stall, reaches 137 °C typical and the
  150 °C shutdown in the bound; the board at the pad stays about P × 17.4 °C/W (RthJB) below the
  junction, 97 °C at the 2.5 A bound, inside C33's X7R range.
- **Firmware**: duty = V_cmd / VBAT, never below the 11.2 % floor set by the 280 ns minimum pulse at
  400 kHz except at 0; start from rest at 50 kHz with the duty ramp and move to 400 kHz once TOFF
  stops asserting; TOFF without a break at 50 kHz means a jammed fan, and EN/nFAULT is the fault
  flag (`boards/main2/firmware_changes.toml`, fan).
- **Above about 3 A continuous**: the fallback is a discrete synchronous half-bridge, a TPS28225
  driver (adaptive 14 ns dead time, VIN ≤ 27 V, VDD 4.5-8.8 V) with 2 × CSD17578Q3A (30 V, 9.4 mΩ at
  4.5 V) and a 10-20 mΩ low-side shunt read by a TLV3201/TLV7031 comparator that pulls EN low
  cycle-by-cycle. It loses 0.49 W at 4 A against 2.13 W for the STSPIN958, but has no thermal
  shutdown, and its limiter and blanking must be designed and bench-validated (fan study §5). Its VDD
  needs a 4.5-8.8 V supply this power tree does not have (**TODO**).

### IR emitters and status LEDs

- **Emitters** from 3V3_D through one shared op-amp + N-FET + 1.2 Ω sink (175 mA at 0.21 V), with
  3.3 Ω per emitter. The set-point is the DAC on PA5 (DAC1_OUT2, output buffer off) through a
  200 kΩ / 20 kΩ divider: ratiometric to VDDA, adjustable per emitter (58 µA per code, 223 mA full
  scale), 0 V at reset; a 1 kΩ / 1 nF integrator compensates the loop into the AO3400A's 630 pF,
  and 200 kΩ from 3V3_A to IN- turns the sink off at a zero set-point. At VF max (1.79 V at
  175 mA) and the 3V3_D minimum less droop (3.229 V) the selector and the sink FET keep 0.65 V;
  ≈ 0.1 W average in the sink FET, 15 mW per resistor at the firmware's 15 % per emitter
  (power-tree study §6; SFH 4550 VF 1.5 V typ / 1.7 V max at 100 mA, datasheet p5). The AO3400A
  selectors keep the main board's AC-coupled gates (220 Ω, 220 nF, 22 kΩ, 1N4148WS clamp): the
  selector works as a source follower in series with the sink, so the gate's droop over a pulse
  does not reach the current, and a pin held high turns its emitter off within 7.5 ms. The DAC
  must step with each selector (up at or after its rising edge, to 0 at or before its falling
  edge); then, with TI's TLV9002 model and the AO3400A fitted to its datasheet, the pulse settles
  to 1 % in 7.4-13 µs without overshoot, and a gate of twice the datasheet's capacitance
  overshoots to at most 233 mA and settles in 18 µs, all before the scan at 75 µs
  ([emitter/emitter_sink.py](calculations/emitter/emitter_sink.py); `boards/main2/Sensors.zen`).
  Kelvin-connect the 1.2 Ω and keep the emitter loop compact and away from VDDA/VSSA. Op-amp:
  TLV9001 (IQ 60 µA typ, 1 MHz, 2 V/µs; `components/ti/TLV9001`). The DAC's 10.3-16 kΩ output
  resistance ([DS13311] Table 90) bounds its drift after a calibration to ±1.3 % of the current.
  The emitter brightness falls −0.5 %/K (SFH 4550), so firmware temperature compensation is worth
  considering. The receivers cannot drive the ADC out of range (the follower stops at
  3V3_A − VCE(sat)); ambient light takes their headroom: about 11 % of full scale for a typical
  TPS601A on a wall under 500 lux of halogen light, 41 % under 1500 lux, while a rank C part
  saturates there ([emitter/ambient_light.py](calculations/emitter/ambient_light.py)); the
  firmware treats a dark reading above 80 % as a blind sensor. 3V3_A carries no emitter current,
  so a pulse moves VDDA by at most 1.1 mV (ADP7142 Figure 38 scaled to a 5 mA step).
- **Status LEDs**: **WS2812C-2020-V6** (C55109522; WS2812B-2020-V6 C52917434 second) on 3V3_D with
  100 nF each. VDD 3.3-5.3 V, DIN VIH 0.55·VDD, so PB9 drives it directly; same GRB protocol and
  firmware ([WS2812C-2020-V6 V1.1] p.1-4; its tables are at 5 V). Each 5 mA channel sink holds full
  current from 0.4 V across it (the Chinese V1.1 p.5 curve), so a channel is full while its VF is
  at most VDD − 0.4 V, 2.884 V at the rail's 3.284 V minimum. Worldsemi gives no per-colour VF; a
  comparable InGaN RGB part reads 2.76 V blue and 2.88 V green at 5 mA (Everlight EAST1616RGBA4,
  typical curves), so red and blue stay at 5 mA and green sits at the knee (about 4.1 mA, −18 %,
  for a die 0.1 V higher). In a 50-60 mV dip of 3V3_D green loses about 10 % for the dip's
  duration. Colours stay recognisable, slightly short of green at worst; no addressable LED of
  this size rates a lower supply in its electrical table (SK6805-EC20, XL-2020RGBC-2812B 3.5 V,
  SK6812-EC20 3.7 V), so the WS2812C stays (`boards/main2/Peripherals.zen`).

### ESP32 radio

- **ESP32-C5-MINI-1-N4** (15.4 × 21.3 × 2.4 mm, 4 MB flash, 22 GPIOs, PCB antenna, FCC
  2AC7Z-ESPC5MINI1 and CE; [ESP32-C5-MINI-1] Table 1-1, Figure 10-1; ESP certificates): Espressif's
  dual-band (2.4 and 5 GHz, 5180-5885 MHz) Wi-Fi 6 module with a 240 MHz RISC-V core
  ([ESP32-C5-MINI-1] Features, Table 7-7). On 3V3_D with 22 µF + 100 nF at its 3V3 pin and 10 µF
  on its feed (Figure 9-1), EN on a 10 kΩ / 1 µF RC (section 9), GPIO28, the boot strap, pulled up
  by R90 (schematic checklist, Strapping Pins). The other strapping pins (GPIO2, GPIO3, GPIO7,
  GPIO25-GPIO27) stay open at their defaults (Tables 4-1 to 4-7).
- **No USB**: the radio flashes over the air and, for recovery, over its UART0 header **J2**
  (HC-PZ127-7.2L-2x3PS, 2 × 3 1.27 mm SMD) wired as Espressif's ESP-Prog Program interface: 1 EN,
  2 VDD (5V_IN), 3 TX0 (GPIO11), 4 GND, 5 RX0 (GPIO12), 6 GPIO28 ([ESP-Prog] Program Interface).
  The module carries the 499 Ω the checklist asks on U0TXD inside its shield (Figure 8-1). Holding
  pin 6 low and pulsing pin 1 enters the ROM's UART download mode, which only burned eFuses defeat.
  Pin 2 takes the programmer's 5 V into VSYS through D17, which powers the whole board without the
  pack and blocks with it (Power tree, programming power); no connector pin reaches 3V3_D.
- **H7 data link**: SPI3 in half-duplex on three wires, the H7 the master: ESP_SCK on PC10
  (SPI3_SCK), ESP_DATA on PC12 (the MOSI pad, IOSWP = 0, SPI_CFG2 COMM = 11, [RM0468] §55.4.2
  and §55.4.4), ESP_CSn on PC11 (a GPIO), the C5 an ESP-IDF spi_slave_hd slave in 3-wire and DMA
  append mode. The link takes SPI3, whose pins sit on the H7's rear-right row toward the C5, and
  the IMU and encoder bus moves to SPI2 (PB13-PB15): SPI2's clock and data pins are all on the other
  rows ([DS13311] Table 9). R95, 22 Ω at PC10, terminates the clock at its driver; R96, 220 Ω at the C5 on the
  data line, limits the current to 15 mA, under the 20 mA per pin ([DS13311] Table 11), if both ends
  drive it at a direction change ([RM0468] Figure 643 note 3), which the firmware's turn-around
  avoids (`boards/main2/firmware_changes.toml`, link); its RC with the line, about 3 ns, is 11 % of
  the half clock at the 15.6 MHz start and 22 % at 31.25 MHz, the fastest step under the C5's
  40 MHz slave limit (`boards/main2/Esp.zen`); R97
  100 kΩ holds ESP_CSn high while neither end drives it. ESP_Flow (GPIO24 → PA9,
  EXTI9) carries the C5's credits: the H7 starts a transfer only when the C5 has a buffer queued.
  UART4 is the fallback on the same pins, up to 5 Mbaud (PC10 UART4_TX into the C5's U1RXD on
  GPIO10, its U1TXD on GPIO9 through R88 100 Ω into PC11 UART4_RX), against the "8 floats at 8 kHz"
  stream of 256 kB/s (MicrasFirmware `bluetooth_design.md` §7). With a laptop on 5 GHz Wi-Fi the
  air carries about 20 Mbit/s of TCP ([ESP-IDF Wi-Fi performance]).
- **Pins**: every H7 line lands on a C5 GPIO free of any restriction (no strapping, pad-JTAG, UART0,
  USB or flash role; [ESP32-C5] §2.3.5, priority 2): SWDIO GPIO0, SWCLK GPIO1 (through R86 22 Ω),
  ESP_DATA GPIO8, ESP_CSn GPIO9, ESP_SCK GPIO10, NRST GPIO23 (open drain), ESP_Flow GPIO24. At reset
  each has its input and output off and no pull ([ESP32-C5 TRM] Table 8.13-1), and neither the
  datasheet nor the TRM lists a power-up glitch on any C5 pin, so none drives NRST or a link line
  before the firmware does (`boards/main2/Esp.zen`).
- **Flashing**: SWD with connect-under-reset (NRST), no system bootloader and no BOOT0. The H725's
  bootloader UART/SPI/I²C pins all carry motors, the buzzer, sensors or the sensor bus, and PA10 is
  Motors_Enable ([AN2606] Table 133). The H7 flash is a single 1 MB bank of eight 128 kB sectors;
  the radio's 4 MB holds two OTA slots of about 1.4 MB with a staged H7 image beside them. The 164 kB
  image takes about 2.2 s to erase and 0.67 s to program (typical; [DS13311] Table 48), so a flash
  takes about 3-4 s (computed). BOOT0 stays low through R42, and SW3 is the manual reset.
- **Flashing and recovery by wire** (no pack needed, 5V_IN powers the board):
  - The C5: any USB-serial adapter with 3.3 V logic on J2 (TX0 pin 3, RX0 pin 5, GND pin 4, its
    5 V pin, never its 3.3 V one, on pin 2), or an ESP-Prog with its PROG PWR SEL jumper at 5 V on
    the 1.27 mm Program cable. Boot: GPIO28 (pin 6) low and a pulse on EN (pin 1), which the
    ESP-Prog's DTR/RTS do for esptool; with a plain adapter, hold pin 6 to GND by hand, tap pin 1
    to GND, and tell esptool not to reset. Then `idf.py flash` or `esptool write_flash`.
  - The H7: a clone ST-Link on SWD1, whose pads follow the clone's 1.27 mm 4-pin lead: 1 SWDIO,
    2 GND, 3 SWCLK, 4 its 5 V pin (never its 3.3 V pin), so the lead plugs on pin 1 to pad 1 (the
    square pad); turned round or shifted one pad, its 5 V never lands on GND, and nothing else
    protects the header (the owner's choice). OpenOCD (`interface/stlink.cfg`,
    `target/stm32h7x.cfg`) or STM32CubeProgrammer flashes it. SWD1 carries no NRST: if the running firmware keeps the core from
    answering, hold SW3 (reset) while the probe connects and release it (connect under reset by
    hand).
- **Debug probe**: over Wi-Fi only, CMSIS-DAP over TCP (bkuschak/cmsis_dap_tcp_esp32, "Tested with
  ESP32 S3, C3, and C6", up to 200 KB/s SRAM, ~6 MHz SWD; its GPIO code is ESP-IDF's portable
  layer, so a C5 port is small work, inference) for OpenOCD's `cmsis-dap backend tcp` (master only,
  last tag v0.12.0, 2023), or a Black Magic Probe port for the C5 (BareMetalTestLab/blackmagic-esp32-c5,
  GDB on TCP). The H725 accepts SWCLK up to 71 MHz ([DS13311] Table 124). STM32CubeProgrammer has no
  path, so `make flash` moves to OpenOCD or GDB; the host runs the H7 flash algorithm, so the radio
  carries no STM32 code (`boards/main2/firmware_changes.toml`, flash). The SWD1 pads take an
  ST-Link when the radio cannot reach the H7, or at a venue without Wi-Fi.
- **Contests**: All Japan (NTF), UKMARS and Minos, IEEE Regions 1 and 2, APEC and Portugal (UTAD)
  forbid control or assistance into a running mouse and ask it to be autonomous or self-contained;
  none names transmit-only telemetry, but judges may read the wording strictly, and RoboCore
  (Brazil) and RoboChallenge allow only a remote start. The firmware therefore has a contest mode
  with the radio fully off for the whole maze allocation, telemetry logged on board
  (`boards/main2/firmware_changes.toml`, contest). Outside it the radio runs 5 GHz only on channels
  36-48, the only DFS-free channels in every target country.
- **Placement**: the rear-right corner, the antenna area over a notch in the rear edge
  (`boards/main2/Esp.zen`, `spec/main2.toml`); see [ESP32 form factor](#esp32-form-factor). Keep
  the UART lines, J2 and its header pins away from the antenna, with ground copper and vias round
  them ([ESP layout]).
- **Not on the board**: the main board's SWD connector P1 and its SWD_VDD OR-ing (the bare SWD1
  pads remain for an ST-Link), the SBU supply chain for the HM-19 and the HM-19 board itself (the
  `bluetooth` board), and the USB-C receptacle with its ESD, CC and VBUS parts.

### ESP32 form factor

**Solder the module, not the bare chip: ESP32-C5-MINI-1-N4 in the rear-right corner, its PCB antenna
over a notch cut out of the rear edge.** The module is a shielded, certified radio that needs no RF
design. A chip-down C5 needs its crystal capacitors and every RF matching value tuned on the
finished board with RF instruments ([ESP schematic], Clock Source, RF Tuning), and loses the
module's certificates.

| | C5-MINI-1-N4 | C5-MINI-1U-N4 | C5-WROOM-1 / -1U | ESP32-C5HF4 chip-down |
|---|---|---|---|---|
| Size (mm) | 15.4 × 21.3 × 2.4, antenna area 5.85 | 15.4 × 15.4 × 2.4 + antenna connector | 18.0 × 27.5 × 3.3, antenna area 6.5 / 18.0 × 21.2 | QFN48 6 × 6 |
| Inside | chip, 48 MHz crystal, 4 MB flash, diplexer, match, antenna, shield | same, connector | same, 4-32 MB flash, up to 8 MB PSRAM | chip and 4 MB flash |
| Board adds | 22 µF + 0.1 µF, EN RC | + antenna, cable | as MINI-1 | crystal and load capacitors, two CLC matches, a diplexer, about 30 passives, antenna |
| GPIO (the board uses 10) | 22 | 22 | up to 22 | 29 less flash pins |
| RF certificates (ESP certificates) | FCC 2AC7Z-ESPC5MINI1, CE | none listed | FCC 2AC7Z-ESPC5WROOM1, IC 21098-ESPC5WROOM1, CE, MIC, KC, Anatel (WROOM-1) | none |
| JLCPCB (Extended), qty 1, read 2026-10-31 | C54951860, 0 in stock | not listed | WROOM-1-N16R8 C54951859; WROOM-1U-N8R8 C54951858 | C54951939 |
| Fits this board | rear-right, over the notch | rear-right | only with the rear motor connectors and the buck moved | rear-right, plus an antenna keep-out |

Sources: [ESP32-C5-MINI-1] Tables 1-1, 1-2, Figures 8-1, 10-1, 10-2; [ESP32-C5-WROOM-1] Tables
1-1, 1-2, Figure 10-1; [ESP32-C5] Table 1-1; [ESP schematic]; Espressif certificate listing;
JLCPCB parts library.

**Placement on this board** (`spec/main2.toml` [u13], [antenna_notch]):

```text
          front: wall sensors + H7 (analog front end)
         ┌───────────────────────┐
         │ C2      fan Ø27 ring  │   sides: wheels, drive motors 4.6 mm from the edge,
  wheel  │▒▒▒▒ drive blocks ▒▒▒▒▒│   battery cells overhanging 27-38 mm above
         │▒▒▒▒ (parts ≤ 1.5 mm)▒▒│
         │SW4  J1  IC7  M2  [ESP]│   rear zone x < −23: open sky, ≥ 18 mm from motors and battery
         └────────────────────   ┘
          notch x −46.5…−40.1, y −25…6.1: the antenna area x −46.0…−40.15, y −24.3…−8.9
```

- The robot has no top cover, so height never decides; the drive blocks (parts ≤ 1.5 mm over
  x −22…13.5) and the fan's Ø27 part-free ring do.
- **Rear-right corner**: metal-free for 18.1 mm, open sky. The module sits at x −32.4, y −16.6,
  turned 180°, its pads from x −40.1 to −24.7 on the board, its 5.85 mm antenna area beyond them
  over the notch, its antenna end 0.5 mm inside the rear edge's line. The C5-MINI-1's antenna has
  its ground point at the module's pin-1 end (the pad-62 corner) and its open, loaded end at the
  pin-45 end (Espressif's STEP model, parts ANT-C5-MINI-1-top and ANT-C5-MINI-1-buttom; the
  datasheet v1.4 cover image; the [ESP layout] "GND Point" figure on the ESP32-C5-WROOM-1's
  antenna, the same design mirrored): the pin-1 end faces the right edge 0.7 mm away, the open end
  the board centre. Espressif's keep-out figure asks for at most 2 mm from the ground-point side to
  the board's side edge, at least 15 mm of board cut away beyond the open end and the antenna end
  at most 1 mm inside the board's edge line ([ESP layout], Keepout Zone for ESP32-C5 Module's
  Antenna): the notch is 6.4 mm deep and 31.1 mm wide, from the right edge to y +6.1, 15 mm past
  the module's inner side. Dense ground vias run along the module's ground edge and the notch.
- The battery switch SW4 and its notch take the rear-left corner (boards/main's notch, mirrored),
  and the power input (J1, F1, D15, Q6) and the 3V3_D buck move beside it; the chassis's rear zones
  are mirror images (`spec/main2.toml` [drive_blocks] tail_left/tail_right, rear bosses), and the
  battery basket's wire slots sit at the rear of both side walls (MicrasHardware `frame.py`), so
  the pack's leads reach J1 on either side.
- Keep the DRV8874 bridges out of the rear-right corner; the WROOM modules fit only with the rear
  motor connectors and the buck moved.

**MINI-1 rather than MINI-1U, on the evidence** (no bench test): every metal part sits 18.1 mm or
more from the antenna (drive blocks 18.1 mm, the left motor's can, past the centre line, 23 mm,
H4 25 mm, LiPo 35 mm), beyond
Espressif's 15 mm ([ESP layout]) and Silicon Labs' 10 mm (BGM220P datasheet §7.2); only the floor
(2.2-3 mm below) is closer, and no published measurement quantifies that detuning. At 5 GHz the
same distances are 0.33-0.64 wavelengths, so metal detunes it less than at 2.4 GHz (inference).
The link has room for the floor: at 20 m the lowest 802.11a power, 15.5 dBm at 54 Mbit/s, arrives
at 5.825 GHz at −58.3 dBm against −90.5 dBm sensitivity at 12 Mbit/s, 32.2 dB of margin, 27.2 dB at
24 Mbit/s ([esp/link_budget.py](calculations/esp/link_budget.py); [ESP32-C5-MINI-1] Tables 7-8 and
7-10). The MINI-1U adds a cable and a mount on a robot that crashes and lists no certificate.

### H7 pin budget

The H725 VFQFPN68 uses every GPIO. The ESP32-C5 takes SWD (PA13/PA14), NRST and the link on PC10,
PC11 and PC12 (SPI3, UART4 as the fallback), and ESP_Flow on PA9. The IMU and encoder bus moves to
SPI2 on PB13-PB15, Fan_PWM to PA7 (TIM14_CH1), Button to PA11 and Fan_TOFF to PA12. PB14 leaves
Fan_Enable for the bus: Fan_Enable moves to PB10, the IMU's INT1 input, and the IMU's INT1 alone drives one line,
IMU_INT on PB6 (INT2 unconnected, its interrupts moved onto INT1). The DIP switch sits on PH0, PH1, PC15 and PC14 (plain inputs with the internal
pull-ups; no HSE or LSE crystal), and the PH/EN bridges need one PWM pin each instead of two,
which frees the pins of the two new lines, Motors_nFault (PB2) and ESP_Flow (PA9). Every pin's
alternate function, and the one-function-per-timer split, checks against ST's STM32_open_pin_data
database, and STM32CubeMX 6.18.1 loads and generates the whole timer, DMA, DAC and dual-ADC set-up
without a conflict (`boards/main2/main2.zen`, pin map check).

| Need | Pins | Resolution |
|---|---|---|
| ESP ↔ H7 link | 3 | PC10 SPI3_SCK (AF6), PC12 SPI3_MOSI pad as the half-duplex data line (AF6, IOSWP = 0), PC11 ESP_CSn (GPIO); UART4_TX/RX (AF8) on PC10/PC11 as the fallback; DMAMUX1 inputs 61/62 (spi3_rx_dma, spi3_tx_dma, [RM0468] Table 118) |
| IMU and encoder bus | 3 | PB13 SPI2_SCK, PB14 SPI2_MISO, PB15 SPI2_MOSI (AF5); DMAMUX1 inputs 39/40 (spi2_rx_dma, spi2_tx_dma) |
| ESP ↔ H7 flow control | 1 | PA9 (ESP_Flow, EXTI9, from the C5's GPIO24, internal pull-down): the C5's credits |
| Fan enable | 1, moved | PB10, open drain with R27 39 kΩ / C30 10 nF, read back as the STSPIN958's nFAULT |
| IMU interrupts | 1 for two | PB6 (IMU_INT, EXTI6, no pull): INT1 alone, push-pull and active high at its defaults; INT2 unconnected (an output forced to ground, DS13476 Rev 5 Table 22), its interrupts moved onto INT1 with CTRL4 INT2_on_INT1 (Table 58) |
| Motor fault | 1 | PB2 (Motors_nFault, EXTI2), both DRV8874 nFAULT wire-ORed (open drain; IMODE = GND so it does not chatter) |
| Current inputs | 2, by swapping | No direct channel is free. Current_Sensor_Left on PB1 (ADC1/2 INP5, a fast channel), Current_Sensor_Right on PC1 (ADC1/2 INP11, slow; one conversion per centre still fits); Wall_Sensor_0 on PA4 and Wall_Sensor_3 on PC0. Each keeps an ADC1 and an ADC2 input: ADC1 converts PB1 and ADC2 PC1 in dual injected-simultaneous mode on TIM1 TRGO2, the walls and the battery run on ADC1's regular group ([RM0468] §28.4.32, Table 227; `boards/main2/firmware_changes.toml`, current) |
| IPROPI | 0 | ITRIP only |
| Emitter set-point DAC | 1 | PA5 (DAC1_OUT2; PA4, DAC1_OUT1, carries Wall_Sensor_0, so DAC channel 1 stays off the pad, MODE1 = 011, [RM0468] Table 266). TIM4, freed by the selectors' move to TIM3, triggers the DAC in step with TIM3 (the DAC has no TIM3 trigger, [RM0468] Tables 264 and 355). The battery divider moves to PC5 (ADC12_INP8, slow channel, DS13311 Table 85) and Switch_0 to PH0 (a plain FT input with the internal pull-up; no HSE crystal) |

An LQFP100 package (STM32H725VG) would relieve this budget and bring out VREF+, but its I/O and
footprint are not analysed.

## Parts

New or changed parts; JLC numbers and prices as queried on 2026-10-15 (stock is not blocking).

| Block | Part | Change | Key data | Source |
|---|---|---|---|---|
| Motors | maxon DCX 10 L 4.5 V × 2, CLL, DCX10L01EBKL531 (ball) / DCX10L01EBSL531 (sleeve), configured online | new; 25.2 mm max flange to rear + 1.95 mm terminals, 5.2 mm longer than MicrasHardware's `Motor.body_l` = 20 ([Drivetrain](#drivetrain)) | 2.9 Ω, 45.3 µH, kt 3.52 mNm/A, 0.648 A cont., 14,300 rpm, 11 g | [maxon p100], [maxon DCX10L01EBKL531] |
| Battery | 4S 150-300 mAh: four 1S 300 mAh cells (~28 g) or a 4S pack (22-36 g) | new; IR unmeasured | HV or non-HV cells | drivetrain study §4-§5 |
| Battery switch | HSBB3072 (Q6) | keep | 30 V VDS, VGS = VBAT/2 | repo `components/huashuo/HSBB3072` |
| Reverse polarity, TVS | none (the connector keys the polarity); TVS D15 SMAJ18A from VBAT to GND_BAT, behind F1 | new | VR 18 V, VBR 20-22.1 V, VC 29.2 V at 13.7 A; C148219 $0.11 | [VBAT overvoltage](#power-tree) |
| VSYS diode | B5819W 40 V 1 A Schottky (D14), VBAT → VSYS | replaces the TPS2121 mux | VF 0.6 V max at 1 A; blocks the J2 back-feed into VBAT; C8598 basic | [Power tree](#power-tree) |
| Digital 3V3 | L6981C33 | keep | 1.5 A, 3.5-38 V, 30.5-145 µF window; C5268096 shows 1 in stock | [L6981] |
| Analog 3V3_A | ADP7142ACPZN3.3 (LFCSP) or TPS7A4901DGNR, behind 22 Ω + 10 µF | new | 40 V / 36 V, 11 / 15.4 µVrms; C659360 $2.88 / C16430 $1.26 | [ADP7142] Rev K; [TPS7A49] |
| Analog 3V3_A, alternative | TPS560430X3FDBVR + 12 µH + damped LC | documented alternative | forced PWM 1.1 MHz, 4-36 V; C2071721 $1.19 | [TPS560430] |
| Motor drivers | DRV8874PWPR × 2 | replaces L6205D | 0.2 Ω HS+LS, 6 A peak, OCP 6 A min, 100 kHz, LS IPROPI 450 µA/A; C1855818, 25,990 stock, $1.01 / $0.66 | [DRV8874] |
| Motor driver, alternative | DRV8262DDWR × 1 | if > 6 A or the stall margin proves short | 0.1 Ω, 8 A dual peak, 60 V; C22427252, $9.77 / $6.98 | [DRV8262] |
| Motor chokes | XAL7070-473MEC 47 µH shielded (Isat 4.2 A, 97 mΩ max, 7.2 × 7.5 × 7.0 mm, 1.9-2.3 g) × 2; fan: XGL5030-472MEC 4.7 µH (5.3 × 5.5 × 3.1 mm) | new; 7.0 mm (7.13 mm with unreflowed terminations) within the 8.0 mm open height and the 7.2 mm `left_tail` zone of `spec/main2.toml` | 0.05-0.30 W ripple heat in the motor at 100 kHz; choke +15 K at the run limit | drivetrain/choke_check.py, fan/fan_choke_check.py |
| Motor shunts | WSK2512R0100FEA (±1 %, C3985410, 4955 stock) or WSK2512R0100DEA (±0.5 %, C1517461, 0 stock) × 2 | replaces the 40 mΩ 2-pad 2512 | 4-terminal, ±35 ppm/K | [WSK2512] |
| Current amplifiers | INA241A2IDGKR × 2 | replaces TSC2020 | ±15 µV, ±0.01 %, 1 µs hold, ≤ 125 kHz PWM; C36752877, 2 stock, $5.71-4.08 | [INA241] |
| Battery fuse | Littelfuse 0501012.WR1 (F1), 12 A fast-acting, 1206 | new | 32 VDC, 150 A interrupting, 3.11 mΩ, melting I²t 20.34 A²s ([Littelfuse 501], Revised 12/14/17); 8.2 A continuous at 75 °C, holds the 10.1 A summed limits; a 4S pack of ≤ 180 mAh cells shorts at 82 A at most (Battery input, Gaps) | `boards/main2/Regulators.zen` |
| Bridge decoupling | 4 × CL32B106KBJNNNE 10 µF X7R 50 V 1210 per bridge (and 2 at the fan), all ceramic on merit (VBAT capacitance) | new | 265 mV pp worst case at 100 kHz; C138687 $0.33 | calculations/power_tree/vbat_bulk.py |
| Fan driver | STSPIN958 (keep); R31 20-25 mΩ 1206; RSR 1-2.2 kΩ; C36 ≥ 25 V; C34/C35 50 V X7R 0805; C33 X7R; L6 XGL5030-472 4.7 µH | modify | 5.05-58 V, 500 kHz, 280 ns min pulse; C20033901, 0 stock, $4.23 | [STSPIN958], fan study §5 |
| Fan fallback | TPS28225DR + 2 × CSD17578Q3A + TLV3201/TLV7031 + shunt | only above ~3 A | TPS28225DR C52897 $0.85; CSD17578Q3A $0.42 | fan study §3 |
| Emitter drive | TLV9001 + AO3400A + 1.2 Ω 0.1 % sense; 3.3 Ω per emitter; AC-coupled selector gates (220 nF, 22 kΩ, 1N4148WS) | new | 175 mA (DAC set-point on PA5, 223 mA full scale) | power-tree study §6; emitter/emitter_sink.py |
| Status LEDs | WS2812C-2020-V6 × 2 | replaces WS2815C-2020 (needs 9.5-13.5 V) | 3.3-5.3 V, 5 mA per colour; C55109522 | [WS2812C-2020-V6] |
| Radio / probe | ESP32-C5-MINI-1-N4, rear-right corner, antenna over the rear-right notch | replaces HM-19 and P1 | 2.4 + 5 GHz Wi-Fi 6, 426 mA TX peak, ≥ 0.6 A supply; C54951860, 0 stock (read 2026-10-31) | [ESP32-C5-MINI-1], [ESP32 form factor](#esp32-form-factor) |
| Radio header | J2 HC-PZ127-7.2L-2x3PS, 2 × 3 1.27 mm SMD, ESP-Prog Program interface | new | 5.5 mm over the board; C27985144 | [ESP-Prog]; `components/hong-cheng/HC-PZ127-7.2L-2x3PS` |
| Link resistors | R95 22 Ω 0402 at PC10 (SPI clock), R96 220 Ω 0402 at the C5 (data line), R97 100 kΩ ESP_CSn pull-up | new | 0402WGF220JTCE C25092, 0402WGF2200TCE C25091, 0402WGF1003TCE C25741, basic | [RM0468] Figure 643 note 3, [DS13311] Table 11 |
| Switches, divider | SW4 → SK-12D29-G060 (DC 24 V 1 A, 6.0 mm lever, new footprint; ON with the lever at pin 3, B); R44/R45 20k/2k | modify | C2848877, 531 stock, $0.13; firmware constant 11.0 | drivetrain study §4; `components/g-switch/SK-12D29-G060` |
| VDDA filter | FB1 → 0 Ω or ≤ 50 mΩ bead | modify | – | power-tree study §9 |
| Removed | TPS61178 + 1 µH + 7 capacitors; L6205D and its parts; 2 × TSC2020; 2 × 40 mΩ shunts; the SWD connector P1 and its SWD_VDD OR-ing; the HM-19's SBU supply chain; the USB-C receptacle and its ESD, CC and VBUS parts; WS2815C ×2 | remove | – | – |

## The owner's questions

### Q1. INA241 vs the drivers' integrated current sensors

**Short answer: yes, it is worth it.** Uncalibrated, the INA241 chain is about 3-9× more precise than
the DRV8874 mirror in mA at every operating point (about 6× at 0.1 A). Against a DRV8874 calibrated
per board and per direction it is only about 2× better at ≥ 0.5 A and equal at 0.1 A, *typically*;
but only the INA241's figures are bounded by datasheet maxima, and it measures signed current
continuously through zero and through braking. It costs about $10 per board and no extra pins or
area against today.

Error at the period-mean current, ΔT = 40 K, shared VDDA term included (±1.5 % uncalibrated, assumed
±0.2 % after calibration) (current_sense/q1_error_table.py, from [INA241] §6.5, [WSK2512],
[DS13311] Table 86, [DRV8874] §6.5 and Fig. 8/9, [DRV8262] §5.5):

| Path | 0.1 A | 0.5 A | 1 A | 3 A |
|---|---|---|---|---|
| INA241A2 + WSK2512, uncalibrated | ±6.1 mA (6.1 %) | ±12.5 mA (2.5 %) | ±20.4 mA (2.0 %) | ±52 mA (1.7 %) |
| INA241A2 + WSK2512, zero cal + 1-point gain cal | **±3.6 mA (3.6 %)** | **±4.7 mA (0.9 %)** | **±6.0 mA (0.6 %)** | **±11 mA (0.4 %)** |
| DRV8874 IPROPI, uncalibrated (AERR max) | ±32 mA (32 %) | ±39 mA (7.9 %) | ±64 mA (6.4 %) | ±175 mA (5.8 %) |
| DRV8874 IPROPI, 2-point cal per direction (typical, not guaranteed) | ±2.5 mA (2.5 %) | ±6.5 mA (1.3 %) | ±11.5 mA (1.2 %) | ±32 mA (1.1 %) |
| DRV8262 IPROPI, uncalibrated, if "rated" = 8 A | not specified | not specified | ±122 mA (12 %) | ±218 mA (7.3 %) |
| DRV8262 IPROPI, uncalibrated, if "rated" = 5 A | not specified | ±61 mA (12 %) | ±73 mA (7.3 %) | ±133 mA (4.4 %) |

- **The datasheet terms.** INA241A2: Vos ±15 µV max, GERR ±0.01 % max, CMRR 150 dB min, 1 µs to 1 %.
  DRV8874: AIPROPI 450 µA/A; AERR ±30 mA below 0.4 A, ±7.5 % at 0.4-1 A, ±6 % at 1-2 A, ±5.5 % at 2-4 A.
  DRV8262: AIPROPI 212 µA/A; AERR ±12 / 7 / 4 % at 10-20 / 20-40 / 40-100 % of a "rated" current the
  table does not define, nothing below 10 %, where the cruise currents (0.5-0.8 A) sit.
- **What a calibrated DRV8874 still lacks.** TI gives no drift, repeatability, noise or VM limit for
  IPROPI. The typical gain drifts 120-200 ppm/K (Fig. 8/9; 0.5-0.8 % over the 20-55 K a run warms the
  driver); OUT1 and OUT2 differ by about 0.5 % because different FETs sense each direction.
- **What each sensor sees.** The INA241 sees the winding current over the whole period, signed,
  whatever the decay mode. The DRV8874 mirror reads only drain-to-source current in the low-side
  FETs: continuous in the commanded direction with drive/low-side-brake PWM, but for a current
  opposing the command it reads 0 in the drive phase and |I| in the brake phase, and nothing in
  coast. Its output is clamped near VREF, so it cannot measure above ITRIP.
- **The mirror sign is recoverable.** With a forward command and a negative mean, the on-centre
  sample reads 0 and the off-centre sample reads |I|, so firmware takes the command's sign if the
  on-centre sample exceeds about 30 mA, and the opposite sign if only the off-centre one does. It
  fails below about 30 mA, in coast, and when the off-phase is shorter than tDELAY + settling, which
  at 100 kHz needs D ≤ 0.68: braking at high duty, where it matters most. Without it, an averaged
  mirror reads +450 to +560 mA high for a −0.3 A regenerative current (current_sense/q1_sampling.py).
- **Centre sampling is needed for the mirrors too.** An RC-averaged mirror rectifies the ripple below
  the zero-crossing current (112-228 mA mean at the datasheet L, 167-345 mA at 0.3·L) and reads
  +14 to +68 mA high at 0.1 A.
- **What the control needs** (inference). 1 mA per motor ≈ 1.19 mN of wheel force; a 30 mA error on
  both motors is about 0.9 m/s² on a 76 g robot, about 3 % of the 31 m/s² traction limit at 1.47 N.
  Torque feed-forward and stall detection work with a calibrated mirror; the inner current loop and
  system identification at cruise currents of order 0.1 A are where the INA241's ±3.6 mA matters.
- **Cost.** 2 × INA241A2IDGKR + 2 × WSK2512 + 6 passives: about $9.6-13.7 per board (TSC2020IYST is
  $3.43-2.38; RIPROPI-only about $0.01). 61 mm² per motor, 122 mm² for two, against 115 mm² for
  the main board's two 40 mΩ shunts, two TSC2020 and their capacitors (drivers/area.py,
  area_board.py). Two ADC pins either way.
- **If only feed-forward, limiting and stall detection are wanted**, a calibrated DRV8874 IPROPI,
  centre-sampled with the sign inference, is good enough and saves about $10 and the in-line
  common-mode risk (the in-line node swings 0 ↔ 16.8 V at 90-120 V/µs). The DRV8262's IPROPI is not a
  measurement: unspecified below 0.5-0.8 A, no drift data.

### Q2. The compromise of an ESP32 without USB OTG

**Short answer: the board has no USB, so OTG buys nothing; the ESP32-C5 does every job over Wi-Fi
and its UART0 header.** OTG mattered only for a wired USB debug probe, console and drive on one
cable. The chips without OTG (C3, C5, C6) have only the fixed-function USB-Serial/JTAG: one CDC
serial port with fixed descriptors plus a JTAG interface for the ESP's own CPU (non-OTG study Q2.1).
Without a USB port on the board, each wired function has a cover:

| Function | Cover on main2 |
|---|---|
| H7 debug probe | CMSIS-DAP over TCP or Black Magic over Wi-Fi ([ESP32 radio](#esp32-radio)); an ST-Link on the SWD1 pads with no Wi-Fi |
| H7 console and telemetry | the link to the radio, bridged to TCP; logs stored on board and offloaded after a contest allocation |
| Radio flashing and recovery | OTA (two slots with rollback); the ROM's UART download mode through J2 (GPIO28 low, an EN pulse), which no application can disable |
| Power on the bench | a current-limited supply into J1 with SW4 on |

| | ESP32-S3 | ESP32-C5 | ESP32-C6 | ESP32-C3 |
|---|---|---|---|---|
| CPU | 2 × LX7 240 MHz, 1329.92 CoreMark | 1 × RISC-V 240 MHz, 820.19 | 1 × RISC-V 160 MHz, 496.66 | 1 × RISC-V 160 MHz, 483.27 |
| Wi-Fi | 2.4 GHz b/g/n | 2.4 + 5 GHz Wi-Fi 6 | 2.4 GHz Wi-Fi 6 | 2.4 GHz b/g/n |
| USB | OTG FS + USJ (one shared PHY) | USJ only | USJ only | USJ only |
| UART | 3, ≤ 5 Mbps | 2 HP + LP, ≤ 5 MBaud | 2 HP + LP, ≤ 5 MBaud | 2, ≤ 5 Mbps |
| Module | MINI-1 15.4 × 20.5 mm, 39 GPIO | MINI-1 15.4 × 21.3 mm, 22 GPIO | MINI-1 13.2 × 16.6 mm, 22 GPIO | MINI-1 13.2 × 16.6 mm, 15 GPIO |
| Module Wi-Fi TX peak | 355 mA | 338 mA (2.4 GHz), 426 mA (5 GHz) | 382 mA | 350 mA |

Sources: chip datasheets (S3 v2.2, C5 v1.5, C6 v1.5, C3 v2.4), module datasheets (S3-MINI-1 v1.7,
C5-MINI-1 v1.4, C6-MINI-1 v1.5, C3-MINI-1 v2.2), TRMs, ESP-IDF `soc_caps.h` (non-OTG study Q2.4).

The C5 is the choice: the only one with 5 GHz for crowded 2.4 GHz venues, the fastest RISC-V core of
the three, and a module that fits the corner at 426 mA of TX peak (≥ 0.6 A supply). Its SPI2 slave
in half-duplex carries the H7 link beyond the 5 Mbaud of any of their UARTs.

### Q3. The fan driver

**Short answer: yes, the STSPIN958 stays, and it is the best integrated option, but reconfigured for a
drone motor on 4S: 400 kHz, a 20-25 mΩ shunt, REF at 1.5 × the running current, a faster slew rate,
a ≥ 25 V C36 and a 4.7 µH choke.** Above about 3 A continuous a discrete synchronous half-bridge
(TPS28225) is better; no buck is needed in either case (fan study).

Why: a 1S-2S motor on 16.8 V runs at 22-44 % duty, a locked rotor draws 13-50 A, and the ripple loss
scales as R/(L·f)², so the driver needs a high PWM rate, a hardware cycle-by-cycle limit (the soft
start) and synchronous freewheeling (a Schottky carries 78 % of the cycle at 1S duty: 1.7 W, +120 °C
at 4 A). Ripple for a 1S motor at D = 0.22 and R 0.4 Ω (fan study §2):

| Motor L | 100 kHz | 200 kHz | 400 kHz | 500 kHz |
|---|---|---|---|---|
| 1 µH | 22 App / 16 W | 13 App / 5.9 W | 7.1 App / 1.7 W | 5.7 App / 1.1 W |
| 3 µH | 9.3 App / 2.9 W | 4.8 App / 0.76 W | 2.4 App / 0.19 W | 1.9 App / 0.12 W |
| 5 µH | 5.7 App / 1.1 W | 2.9 App / 0.28 W | 1.4 App / 0.07 W | 1.2 App / 0.04 W |
| 2 µH + 10 µH choke | 2.4 App / 0.19 W | 1.2 App / 0.05 W | 0.6 App / 0.01 W | – |

400-500 kHz alone is enough only for motors of about 4-5 µH or more; for 1-3 µH a 4.7-10 µH choke is
needed even at 400-500 kHz. The STSPIN958's 280 ns minimum pulse sets an 11.2 % (1.88 V) floor at
400 kHz and 14 % (2.35 V) at 500 kHz, which caps the useful rate for a 1S motor at about 400 kHz.

Driver loss, junction rise and motor ripple loss at 16.8 V, 1S motor (3 µH, 0.4 Ω, D 0.22) (fan study §3):

| Driver @ f | 1 A | 2 A | 4 A |
|---|---|---|---|
| **STSPIN958**, 2 V/ns, 400 kHz | 0.23 W, +8 °C / 0.19 W | 0.63 W, +23 °C / 0.19 W | 2.13 W, +76 °C / 0.19 W |
| STSPIN958, 0.6 V/ns (today's 5.6 kΩ), 400 kHz | 0.36 W / 0.19 W | 0.89 W / 0.19 W | 2.66 W, +95 °C / 0.19 W |
| DRV8412 PFB, 400 kHz | 0.32 W / 0.19 W | 0.88 W / 0.19 W | 2.91 W, +71 °C / 0.19 W |
| DRV8874 + 22 µH choke, 100 kHz | 0.63 W / 0.04 W | 1.90 W, +60 °C / 0.04 W | 6.5 W, fails |
| DRV8262 + 10 µH choke, 200 kHz | 0.48 W / 0.04 W | 1.15 W / 0.04 W | 3.09 W, +58 °C / 0.04 W |
| Low-side FET + SS34 + UCC27517A, 400 kHz | 0.49 W / 0.19 W | 0.96 W (SS34 +63 °C) | 1.92 W (SS34 +120 °C) |
| **TPS28225 + 2 × CSD17578Q3A**, 400 kHz | 0.09 W / 0.19 W | 0.19 W / 0.19 W | 0.49 W, +29 °C / 0.19 W |

- **DRV8412**: electrically the cleanest (500 kHz, 14 ns edges, cycle-by-cycle limit), but it needs a
  10.8-13.2 V GVDD/VDD, takes 2.7× the area, wastes three half-bridges and its limiter starts at
  7.4 A.
- **DRV8874 / DRV8256 / DRV8262**: 100-200 kHz, so a 10-22 µH choke rated for the limit current; the
  DRV8874 at 100 kHz with a 3 µH motor peaks at 6.6 A at 2 A mean, above its 6 A minimum IOCP.
- **TB67H450FNG / DRV8251A / DRV8876**: 3.0 / 4.1 / 3.5 A ratings and 0.45-0.8 Ω; the TB67H450's
  3.6 µs blanking leaves no regulation at 400 kHz (inference).
- Searched and rejected for 20-25 kHz ceilings: IFX9201, DRV8243-Q1, DRV8000-Q1, NCV7535. No
  integrated brushed-DC bridge from MPS, Allegro, onsemi or Infineon at ≥ 400 kHz was found.
- The STSPIN958's drawbacks: $4.23 and 0 JLC stock, the 280 ns minimum pulse, and +76 °C at 4 A
  (JEDEC RθJA).

### Q4. L6205D vs DRV8874 vs DRV8262

**Short answer: replace the L6205D with 2 × DRV8874.** The L6205D does not belong on 4S with this
motor: 3.1× the DRV8874's bridge resistance, no current regulation, an overcurrent detector that
trips inside the motor's stall and reversal currents and stops both wheels, and a junction above
125 °C in a 60 s run. The DRV8262 runs cooler and has more margin, but costs about 5× as much, takes
one central 143 mm² package, and its 200 kHz is unusable with the INA241. It stays the documented
alternative for a motor needing more than 6 A; with the DCX 10 L the bound reversal peak is 5.48 A
(drivetrain/choke_check.py).

Datasheet values ([L6205] p2-6, 9-11, 15-16, 20; [DRV8874] §6.1-6.5, §7.3, Fig. 6-9, 25; [DRV8262]
§1, §5.1-5.5, §6.3-6.11, Table 5-1, Table 6-1); losses at 16.8 V, 100 kHz, 0.69 A pp ripple included
(drivers/q4_drivers.py; the L6205 edge time is an assumed 100 ns, the datasheet gives 40-250 ns):

| | L6205D (SO20, today) | DRV8874PWPR (× 2) | DRV8262DDWR (× 1, dual) |
|---|---|---|---|
| VS operating / abs max | 8-52 V / 60 V | 4.5-37 V / 40 V | 4.5-60 V / 70 V |
| RDS(on) HS + LS, 25 °C typ / max | 0.62 / 0.74 Ω | 0.20 / 0.24 Ω | 0.10 / 0.12 Ω |
| RDS(on) hot | 1.00 typ / 1.12 max Ω at 125 °C | ≈ 0.25 Ω at 125 °C | 0.147 typ / 0.184 max Ω at 125 °C |
| Continuous / peak current | 2.8 A rms / 7.1 A < 1 ms | thermally limited / 6 A | 5 A rms per bridge / 8 A dual |
| Overcurrent threshold | 4.0 / 5.6 / 7.1 A (min/typ/max), sum of both HS | 6 A min / 10 A typ per FET | 8 A min per FET |
| Overcurrent behaviour | EN pulled low for tDISABLE; ENA = ENB here, so both wheels stop | 3 µs deglitch, bridge off, retry 2 ms or latched; nFAULT | 2.1 µs deglitch, only the faulty bridge off, retry 4.1 ms or latched; nFAULT |
| Current regulation | none | ITRIP, fixed off-time 25 µs truncated at the next input edge | ITRIP, off-time 7/16/24/32 µs truncated at the next input edge |
| Integrated sense | none | LS mirror 450 µA/A | HS mirror 212 µA/A × 2 |
| Max PWM | 100 kHz | 100 kHz | 200 kHz |
| Dead time; duty distortion at 100 kHz (computed) | 0.5-1 µs; ≈ 10 % (1.7 V, ≈ 0.58 A at stall) | 100 ns; ≈ 1 % | 300 ns; ≈ 3 % |
| Loss per bridge at 0.5 / 1 / 3 A, typ 25 °C | 0.42 / 1.09 / 6.8 W | 0.24 / 0.53 / 2.7 W | 0.19 / 0.39 / 1.7 W |
| Same, max hot | 0.75 / 1.93 / 12.2 W | 0.34 / 0.70 / 3.6 W | 0.24 / 0.50 / 2.5 W |
| Loss share of bridge output at D 0.5 (0.5 / 1 / 3 A) | 10 / 13 / 27 % | 6 / 6 / 11 % | 5 / 5 / 7 % |
| Run: both motors 1.0 A rms | 2.2 W typ → Tj ≈ 136 °C, above 125 °C | +25 K | +22 K |
| 1 s stall at 3 A, both motors | would reach TSD (inference by proxy, no Zth published) | 3.6 W × 15 °C/W → +55 K | 4.9 W × 4.7 °C/W → +23 K |
| Unregulated stall / reversal at 16.8 V | 4.77 / 6.27 A, inside the OCD window | regulated at ITRIP | regulated at ITRIP |
| Bridge drop at the 2.14 A traction current (4 N) | 1.33 V | 0.43 V | 0.21 V |
| RθJA | 51 °C/W with 6 cm² copper | 36.0 °C/W (JEDEC) | 22.2 °C/W (JEDEC) |
| Package, driver block area for two motors | SOIC-20W; 198 mm² as built | 2 × HTSSOP-16 (45 mm² each); 111 mm² | HTSSOP-44 with a 13 × 5 via pad; 162 mm² |
| MCU pins | 4 PWM + 1 EN, no fault readback | 2 per motor + nSLEEP + nFAULT = 6 | 4 IN + nSLEEP + nFAULT = 6 |
| JLC part, stock, price 1 / 100 | C962257, 1304, $3.88 / $2.49 | C1855818, 25,990, $1.01 / $0.66 each | C22427252, 1717, $9.77 / $6.98 |

Practical differences (inference, driver comparison study Q4.5): below top speed all three
accelerate the same, because the traction limit is the motor's; on a sagged pack (≈ 12-13 V) the
L6205 loses traction-limited acceleration near top speed first. With ITRIP, plugging is held at
2.5-3 A by hardware every cycle; on the L6205 the firmware must model the back-EMF to avoid tripping
both wheels. Two DRV8874s sit next to their motor connectors with short motor loops and split heat;
the DRV8262 must sit centrally and run both motor pairs across the board. The DRV8874's 1 % duty
distortion keeps voltage feed-forward nearly linear without compensation.

### Q5. Is a second buck or an LDO needed for the analog rail?

**Short answer: the analog rail needs no buck. A 40 V LDO fed from the battery-side node is not only
acceptable but the better choice; one buck (digital 3V3) is enough.** What the ADC needs is an analog
rail that the digital, radio and emitter currents do not flow through, and a regulator that does not
skip pulses at the rail's ~10 mA load. An HV LDO from VSYS through 22 Ω + 10 µF does both, with no
switching node near the analog section, and is the quietest option in the model (power-tree study §4-§5).

| Architecture | VDDA in-window rms | Scan-mean spread | Lit − dark | Verdict |
|---|---|---|---|---|
| HV LDO from VSYS (TPS7A49 class, 47 Ω + 10 µF in the model) | **0.3 LSB** | 1.4 LSB | 0.6 LSB | **chosen**; 0.09-0.33 W of heat, 6-8 parts |
| Forced-PWM buck + damped LC | 0.8 LSB | 1.8 LSB | 1.7 LSB | documented alternative; 9 parts, a hot loop near the analog section |
| Forced-PWM buck, no filter | 7.9 LSB | 0.2 LSB | 0.2 LSB | out: twice the ADC's own noise |
| PFM buck + damped LC | 5.9 LSB | 13.7 LSB | 2.5 LSB | out: skips pulses, regulates 1.9 % high |
| 5 V PFM buck → TPS7A20-class LDO | 0.8 LSB | 0.0 LSB | 0.0 LSB | out: most parts, and nothing else needs 5 V |
| 3V3_D → bead + 10 µF | 90 LSB | 577 LSB | 59 LSB | out: ESP bursts and emitter pulses pass straight through |

All passing cases sit below the ADC's own ≈ 4 LSB16 rms (ENOB 12.2 bits, [DS13311] Table 86) and far
below the INA241 chain's 15-26 LSB16 rms, so the choice is about heat, parts and layout risk. At
10-20 mA a buck saves only 0.06-0.26 W. Also out: an LDO from 3V3_D to a 3.3 V rail (no headroom),
and the TPS62912/13 (VIN 17 V recommended, 18 V abs max, below 17.4 V HV cells). The layout matters
more than the regulator: shared ground costs 3.4 LSB per mΩ for an emitter pulse, 5.2 LSB for an ESP
TX step and 48 LSB for one motor bridge (power-tree study §2), so the emitter, ESP and motor return
currents must not share copper with the VDDA/VSSA return and the receiver load resistors.

## Series choke with a motor: downsides

A choke in series with a wheel motor (XAL7070-473, 47 µH) or the fan (XGL5030-472, 4.7 µH) trades
PWM ripple against these costs; both are fitted.

- **Size, height and mass.** A shielded part rated for the current is the largest passive near each
  motor and adds mass to a 76 g robot. The wheel choke is the XAL7070-473 (7.2 × 7.5 × 7.0 mm,
  1.9-2.3 g each), the fan's the XGL5030-472 (5.3 × 5.5 × 3.1 mm). Heights: 7.0 mm (7.13 mm with
  unreflowed terminations) and 3.1 mm, within the 8.0 mm open height of `spec/main2.toml`; the
  XAL7070 also fits the 7.2 mm `left_tail` zone and no lower zone.
- **Saturation current.** Both parts saturate softly (Coilcraft's saturation models): the XAL7070-473
  keeps 79 % of its inductance at the 3 A ITRIP, 69 % at its 4.2 A Isat and 60 % at the 5.48 A bound
  peak of a full-speed reversal; the XGL5030-472 keeps 77 % at 4.8 A and 66 % at 6.7 A. The
  wheel peaks stay under the DRV8874's 6 A OCP minimum ([Drivetrain](#drivetrain)), the fan's
  under the STSPIN958's 7 A once it starts at 50 kHz ([Fan](#fan)).
- **DCR and core loss.** The DCR adds to the 2.9 Ω loop: each 100 mΩ costs 0.1 W at 1 A rms
  and adds 3.4 % to the loop resistance (computed). Coilcraft's Power Inductor tool (40 °C ambient, 2026-10-25) gives the
  losses outright: a wheel choke (XAL7070-473, 100 kHz, 1.1 A pp) takes 330 mW in all and reaches
  49 °C at a 1.0 A run current, 799 mW and 63 °C at 2.5 A; L6 (XGL5030-472, 400 kHz, 2.8 A pp,
  2.5 A) 673 mW and 57 °C. The models' bounds sit at or above these: at most 467 mW of core loss
  per wheel choke (the series' loss-tool coefficient extrapolated to 47 µH and doubled; 276-309 mW
  from the part's Document 267 SPICE model, drivetrain/choke_spice_loss.py), +15 K at 1.0 A with
  the DCR, and at most 0.53 W in L6, +17 K (drivetrain/choke_check.py, fan/fan_choke_check.py).
- **Stray field.** Use a shielded part, keep it away from the AS5047U magnetic encoders and the IMU,
  and keep the bridge → shunt → choke → motor loop tight (inference).
- **Slower current.** The electrical time constant grows from 15.5 µs (motor alone, datasheet L) to
  about 32 µs, (45 + 47 µH) / 2.9 Ω, DCR ignored (computed). That is irrelevant for the fan and
  acceptable for the wheel loop: still about three PWM periods, below one 10-20 kHz loop period
  (inference).
- **Stored energy is negligible.** ½·L·I² = 0.21 mJ at 47 µH and 3 A (computed), against 7.9 mJ in
  the 56 µF of VBAT ceramics at 16.8 V.
- **Current sensing gets smoother.** The ripple halves (0.93 → 0.46 A pp at the datasheet L), the
  ripple becomes close to triangular, and a phase-centre sample then equals the period mean.
- **No capacitor across the motor.** A capacitor at the motor terminals forms an LC with the choke;
  for example 47 µH with 100 nF resonates at about 73 kHz (computed, the 100 nF is an example value),
  next to the 100 kHz PWM. Remove motor suppression capacitors, or design a damped filter. maxon
  recommends chokes for motors with CLL, its internal capacitor disk ([maxon chokes]).
- **Brush-bounce sparking.** The choke keeps current flowing when a brush lifts, so the commutator
  may arc more (inference; Portescap: electro-erosion ∝ L·I², [Portescap PWM]). maxon recommends
  the choke for its CLL motors on PWM ([maxon chokes] p1), and the CLL "suppresses spark generation
  to a large extent" ([maxon DC technology]): the DCX 10 L is ordered with CLL
  ([Drivetrain](#drivetrain)).

## What does not make sense, and why

| Idea | Why not | Basis |
|---|---|---|
| DCX 8 M "4.5 V winding" | It does not exist (2.4/4.2/6/7.2/9/12 V only) | [maxon p98] |
| DCX 8 M 4.2 V on 14.8-20 V | 3.3-4.8× over its 17,300 rpm limit at no load, stall 6-8× rated, ripple over its ~0.6 W loss budget at 100 kHz, 3-15 % of a 60 s run at the traction limit, 19-34 V needed for traction at 4 m/s | drivetrain study §1, §3 |
| A lower DCX 8 M winding "for current" | km = kt/√R is nearly the same across windings (0.91-0.97 mNm/√W) | drivetrain study §1 |
| A boost to 20-24 V on 4S | The TPS61178 cannot exceed 20 V, pulse-skips at 4S and cannot sink regen; 24 V breaks the TPS2121 and 25 V-capacitor margins | drivetrain study §4 |
| L6205D on 4S | No current regulation, OCD at 4.0-7.1 A inside the 4.77 A stall / 6.27 A reversal, both wheels stop on a trip, Tj ≈ 136 °C in a run | [Q4](#q4-l6205d-vs-drv8874-vs-drv8262) |
| PWM between drive and coast (IN/IN, one input held at 0) | Doubles the ripple, current through the body diodes, IPROPI blind; use PH/EN with PWM on EN | [DRV8874] Tables 3-4 |
| Cycle-by-cycle IMODE with nFAULT on an EXTI | nFAULT pulses at every chop, up to 100 kHz of interrupts | [DRV8874] Table 6, Fig. 14 |
| 200 kHz motor PWM with in-line INA241 sensing | Beyond the 125 kHz rejection spec, no 4 µs centre window at mid duty, above the DRV8874's 100 kHz | [INA241] §7.3.1.1 |
| Driver IPROPI as the precise measurement | ±30 mA / ±5.5-7.5 % (DRV8874), unspecified below 10 % of rated (DRV8262), drain-to-source only, clamped at ITRIP | [Q1](#q1-ina241-vs-the-drivers-integrated-current-sensors) |
| Hall sensors or isolated ΣΔ for motor current | Hundreds of mA rms of noise and ±60 mA offsets, or isolation the robot does not need | current-sensing study §3 |
| Automotive bridges (DRV824x-Q1, VNH7070AS, IFX9201) | 20-25 kHz PWM ceilings | driver study Q1 |
| DRV8212/DRV8411, A4950/A5950, TB67H451, STSPIN948 for the wheels | Too low a voltage rating, or 3-10× the resistance | driver study Q1 |
| Discrete DRV8714 + MOSFET bridges for the wheels | Only worth it above about 8 A peaks | driver study Q2 |
| A buck pre-regulator for the fan | The STSPIN958 at 400 kHz with its REF limit runs the motor from 4S directly | fan study |
| A 100-200 kHz bridge (DRV8874/DRV8256/DRV8262) or a TB67H450/DRV8251A for the fan | Needs a 10-22 µH choke, peaks above IOCP, or too low a current rating | fan study §4 |
| Low-side FET + Schottky for the fan above ~2 A | The Schottky carries 78 % of the cycle: +120 °C at 4 A | fan study §2 |
| WS2815C on 4S, or on 3.3 V | 9.5-13.5 V supply range | WS2815C-2020 datasheet via the repo |
| Bigger 3V3 capacitors | The L6981's internal compensation fixes the droop at about 22 mV per 170 mA step up to the 145 µF limit | 3V3 study §2 |
| A 5 V rail (5 V buck + LDO) | Nothing needs 5 V; the most parts for no measurable gain | power-tree study §3 |
| 3V3_A from 3V3_D (bead, RC or LDO) | Bursts pass through (90 LSB rms); an LDO has no headroom | power-tree study §3-§4 |
| A PFM/LCM buck on the analog rail | Skips pulses at 10 mA: 13.7 LSB spread, 1.9 % high | power-tree study §4 |
| TPS62912/13 for any 4S rail | VIN 17 V recommended / 18 V abs max | power-tree study §3 |
| Emitters from VBAT through a resistor or a sink | 1.2-1.8 W of heat; a resistor alone drifts 170 → 117 mA over the discharge | power-tree study §6, 3V3 study §4 |
| VREFBUF or an external VREF+ on VFQFPN68 | VREF+ is bonded to VDDA | [DS13311] Table 8 |
| A precision reference on VDDA | Per-board gain calibration and VREFINT cover the absolute accuracy | 3V3 study §3 |
| ESP32-C3/C6, or P4 | C3/C6: 2.4 GHz only and nothing gained over the C5; P4: no radio | [Q2](#q2-the-compromise-of-an-esp32-without-usb-otg) |
| A chip-down C5 or a chip antenna | Its crystal and RF match, or the chip antenna's match, must be tuned on the finished board with RF instruments, and it loses the module's certificates | [ESP32 form factor](#esp32-form-factor) |
| H7 flashing through the system bootloader UART/SPI | Its pins carry motors, the buzzer and the sensor bus; PA10 is Motors_Enable | [AN2606] Table 133 |
| A/B images in H7 flash | One 1 MB bank | [RM0468] |
| A battery current monitor (INA228) on the H7 | No free I²C pins; F1 fuses the battery path and PC5 reads its voltage | pin budget |

## Bench measurements before committing

On the current board (priority 1 first):

| Priority | Measurement | Decides | Method |
|---|---|---|---|
| 1 | Current sensor with the post-`bd1eedd` firmware (micras-lib, 2026-10-05: before it the compiler folded the DMA buffer and `get_current_raw` read a constant −2.0625 A) | Whether the in-line architecture is sound, and the size of each analog error | current-sensing study §1 steps 1-10: raw ADC at rest against a DMM at TSC OUT (1.65 V ± 7 mV); pin check; DC gain at both common modes into a 10-20 Ω power resistor; Kelvin check; scope the PWM artefact at 10-90 % duty both ways; ±40 % torque sweep; ADC2 triggered from the timer; rail-noise A/B; linearity calibration |
| 2 | INA241A2 swapped onto the main board's TSC2020 footprints | Whether the common-mode artefact disappears | Bridge pin 4 to pin 3, repeat steps 5-7 |
| 4 | Run profile (time at peak torque), downforce at the new fan voltage, tyre µ, gear efficiency | Thermal budget, ITRIP and RMS limits | Firmware logging, scale |

On breakouts and dev boards:

| Priority | Measurement | Decides | Method |
|---|---|---|---|
| 4 | Half-duplex SPI link bit errors against the SCK prescaler | The link clock | C5 devkit as an spi_slave_hd slave, an STM32H7 board as master, 22 Ω on SCK at the master and 100 Ω on data at the slave, CRC-checked frames |

On the first prototype: the INA241 against a current probe on the motor lead (and against the
DRV8874's IPROPI, read with a probe across RIPROPI).

## Open decisions

| Decision | Options | Notes |
|---|---|---|
| Gear and top speed | 4 m/s at G ≈ 4.27 / about 4.6 m/s at 3.7:1 / 6 m/s (needs 18.7 V at 4 N, above 4S) | – |
| Battery | four 1S cells / a 4S pack; HV or non-HV charging | – |
| Motor driver | 2 × DRV8874 (on the board) / DRV8262 | DRV8262 if more than 6 A is needed; the DRV8874's bound reversal peak is 5.48 A (drivetrain/choke_check.py) |
| Current measurement | INA241A2 + WSK2512 (on the board) / calibrated DRV8874 IPROPI only | Q1; IPROPI sets ITRIP and is readable with a probe across RIPROPI |
| Fan motor and driver | STSPIN958 (≤ ~3 A continuous) / TPS28225 half-bridge (above) | Fan motor not chosen |
| Radio module | C5-MINI-1-N4 (on the board) / C5-WROOM-1 | the WROOM-1 if Brazilian (Anatel) or Japanese (MIC) coverage must be clean; it fits only with the rear motor connectors and the buck moved |
| Toolchain | CMSIS-DAP through OpenOCD (master) or probe-rs | ST-Link and CubeProgrammer workflows are lost |
| Backstops | SWD1 pads (1 SWDIO, 2 GND, 3 SWCLK, 4 5V_IN, a clone ST-Link's order) for an ST-Link; SW3 (NRST); BOOT0 held low by R42 | – |

## Gaps and TODOs

- **Motors**: maxon publishes no commutator wear at 4-5 × IN (ordered with CLL, spares kept;
  [Drivetrain](#drivetrain)); the DCX 10 L's 25.2 mm length needs MicrasHardware's blocks reshaped
  and the `left_motor_can` zone of `spec/main2.toml` extended.
- **Drivers**: the DRV8874's tBLK and tDEG are typical values only (the overshoot bound takes 1.5 ×
  them). For the IPROPI-only alternative of Q1 (not on the board): DRV8262 IPROPI dynamics and its
  "rated current" are undefined, there are no mirror noise, VM dependence or calibration-stability
  data for either part, and the DRV8874 calibrated row rests on one typical curve. The L6205 edge
  time and transient Zth are not published (comparison only).
- **Current sensing**: the friction share of the cruise current is unknown (log it).
- **Analog rail**: no vendor model, inductor coupling or PCB parasitics in the simulation.
- **Fan**: no drone motor publishes its inductance (bounded at 0.12-14 µH at 400 kHz from the
  makers that do, and the design checked over it, [Fan](#fan)); NFP figures are from search snippets;
  the STSPIN958's supply current, dead time, RDS(on) temperature curve and limiter blanking are
  unpublished (bounded, [Fan](#fan)). For the discrete fallback (not on the board): the limiter is
  not a validated design and its 4.5-8.8 V gate supply is not designed.
- **ESP**: cmsis_dap_tcp_esp32 is not yet ported to the C5 (tested on the S3, C3 and C6, up to
  200 kB/s over Wi-Fi), and the Black Magic C5 port is young; no published detuning of a PCB antenna
  2-3 mm over a floor (the link margin covers it, ESP32 form factor); the C5-MINI-1 holds no Anatel
  (Brazil) or MIC (Japan) certificate; no C5 power-up glitch table is published (the reset states
  are, [ESP32-C5 TRM] Table 8.13-1); the SPI2 link clock is set by a bit-error test; an RDP Level 2
  mistake locks out SWD for any probe.
- **Emitter sink**: AOS publishes no AO3400A SPICE model: the sink model uses a VDMOS fitted to
  the datasheet and a third-party level-3 AO3400 model as stand-ins (emitter_sink.py).

## Calculations

The scripts are standalone Python 3 (some need numpy) and run from any directory, for example
`python3 research/next-revision/calculations/drivetrain/dcx10l_ripple.py`. Each `*_out.txt` is the
output of the script of the same name. The two ngspice models write waveform `.dat` files (tens of
MB, git-ignored) into their `out/` folder; the netlists (`.cir`), logs and summaries are kept.

| Script | Output | Computes |
|---|---|---|
| [drivetrain/motors.py](calculations/drivetrain/motors.py) | – | Motor datasheet values used by the other drivetrain scripts |
| [drivetrain/ripple.py](calculations/drivetrain/ripple.py), [ripple_exact.py](calculations/drivetrain/ripple_exact.py) | `ripple_out.txt`, `ripple_exact_out.txt` | PWM ripple, rule of thumb and exact periodic RL |
| [drivetrain/dcx10l_ripple.py](calculations/drivetrain/dcx10l_ripple.py) | `dcx10l_ripple_out.txt` | DCX 10 L 4.5 V ripple at 40-200 kHz with 0-100 µH chokes |
| [drivetrain/choke_check.py](calculations/drivetrain/choke_check.py) | `choke_check_out.txt` | Wheel ripple, choke core loss and heat, ITRIP band and reversal overshoot over 0.2-1.0 × the motor L, the choke's tolerance and DC bias |
| [drivetrain/choke_spice_loss.py](calculations/drivetrain/choke_spice_loss.py) | `choke_spice_loss_out.txt` | Choke ripple loss from Coilcraft's Document 267 SPICE models (XAL7070-473, XGL5030-472), scaled to the loss tool on the XGL5030-472 |
| [current_sense/ina241_edge.py](calculations/current_sense/ina241_edge.py) | `ina241_edge_out.txt` | INA241A2 at VS 3.3 V after 0-16.8 V common-mode edges, and the error at the phase centres (TI PSpice model in ngspice, about 2 min) |
| [drivetrain/sim.py](calculations/drivetrain/sim.py), [extra.py](calculations/drivetrain/extra.py), [duty.py](calculations/drivetrain/duty.py), [vreq.py](calculations/drivetrain/vreq.py) | `sim_out.txt`, `extra_out.txt`, `duty_out.txt`, `vreq_out.txt` | Traction limit, acceleration, thermal run budget, burst times, figure of merit, bus voltage needed |
| [drivetrain/power_stage_calc.py](calculations/drivetrain/power_stage_calc.py) | `power_stage_calc_out.txt` | Bridge loss, ripple with chokes, input-capacitor ripple, battery switch |
| [current_sense/budget.py](calculations/current_sense/budget.py) | `budget_out.txt` | Shunt range, TSC2020 artefact windows, INA241 error budget, INA228 scaling |
| [current_sense/q1_sampling.py](calculations/current_sense/q1_sampling.py) | `q1_sampling_out.txt` | What each sensor sees over a period, bias of each mean estimate, ITRIP overshoot |
| [current_sense/q1_error_table.py](calculations/current_sense/q1_error_table.py) | `q1_error_table_out.txt` | Q1 error budgets at 0.1-3 A |
| [current_sense/ina241_riso.py](calculations/current_sense/ina241_riso.py) | `ina241_riso_out.txt` | INA241A2 into R_iso + C_f with TI's PSpice model: peaking, step overshoot, ADC kickback settling over tolerance corners (ngspice, about 8 min; downloads the model) |
| [drivers/q4_drivers.py](calculations/drivers/q4_drivers.py) | `q4_drivers_out.txt` | Q4 losses, junction rise, stall and reversal currents, duty distortion |
| [drivers/area.py](calculations/drivers/area.py) | `area_out.txt` | Courtyard areas from the KiCad 10 library (reads `/usr/share/kicad/footprints/`) |
| [drivers/area_board.py](calculations/drivers/area_board.py) | `area_board_out.txt` | As-built areas; KiCad's `pcbnew` module, run with `boards/main/layout/main.kicad_pcb` as argument |
| [esp/placement.py](calculations/esp/placement.py) | `placement.png` | ESP candidate positions on the main-board-fixes layout with the MicrasHardware chassis projected; `pcbnew` and matplotlib, the board file as argument |
| [esp/link_budget.py](calculations/esp/link_budget.py) | `link_budget_out.txt` | The ESP32-C5-MINI-1's 5 GHz link margin at 1-20 m in free space |
| [drivers/jlc_query.py](calculations/drivers/jlc_query.py) | `jlc_out.txt`, `../fan/jlc_fan_out.txt` | JLCPCB parts search by MPN (online; results dated 2026-10-15) |
| [fan/fan_driver_calc.py](calculations/fan/fan_driver_calc.py) | `fan_driver_calc_out.txt` | Q3: drone motor data, duty, stall current, ripple, driver losses |
| [fan/fan_choke_check.py](calculations/fan/fan_choke_check.py) | `fan_choke_check_out.txt` | Fan ripple and L6 loss over the motor range, the limiter in a locked rotor at 400 / 100 / 50 kHz, STSPIN958 heat with bounds, the REF rule |
| [supply3v3/sim3v3.py](calculations/supply3v3/sim3v3.py), [analyze.py](calculations/supply3v3/analyze.py) | `out/summary_meas.txt`, `out/summary_slots.txt` | Averaged 3V3/VDDA droop model during the emitter pulses (ngspice, seconds) |
| [power_tree/sim_power_tree.py](calculations/power_tree/sim_power_tree.py), [analyze.py](calculations/power_tree/analyze.py) | `out/summary.txt` | Switching-level analog-rail model, cases A-F (ngspice, about 5 min per case, 6 in parallel) |
| [power_tree/calc_power_tree.py](calculations/power_tree/calc_power_tree.py) | `out/calc_power_tree.txt` | Analog-rail load, LDO heat, emitter sink, the 5V_IN programming budget, ADC noise, LC filter |
| [emitter/emitter_sink.py](calculations/emitter/emitter_sink.py) | `emitter_sink_out.txt` | main2's emitter sink with the DAC set-point and AC-coupled selectors, with TI's TLV9002 model and AO3400A stand-ins: worst-case current and margin, turn-off with a pin held high, pulse start against the DAC timing, AO3400A VGS over temperature (ngspice, about 15 min; downloads the models) |
| [emitter/ambient_light.py](calculations/emitter/ambient_light.py) | `ambient_light_out.txt` | Ambient light on the TPS601A receivers: tungsten-equivalent irradiance of contest lighting, receiver current against the ADC range |
| [power_tree/vbat_bulk.py](calculations/power_tree/vbat_bulk.py) | `vbat_bulk_out.txt` | VBAT capacitor options (MLCC DC bias, 100 kHz ripple, source impedance; the ceramics against 35 V solid-polymer aluminium bulk), hot plug and Q6 switching, regeneration with the pack pulled, TVS clamp, and in section 9 a P-FET gate clamp the board does not use (ngspice, about 5 min) |
| [power_tree/fuse_501_curves.py](calculations/power_tree/fuse_501_curves.py) | `fuse_501_curves_out.txt` | F1's time-current curves digitised from the Littelfuse 501 datasheet's vector paths (the PDF as argument; pdftocairo) |
| [power_tree/power_path_checks.py](calculations/power_tree/power_path_checks.py) | `power_path_checks_out.txt` | The pack's short circuit against F1, 5V_IN programming power (the L6981's dropout, the ADP7142, D17 against the pack, VBAT on D14's leakage per battery divider), the ADP7142's junction temperature per copper area |

The power-tree netlists of the cases A_none, A_bead, A_lc, A_lcd, A6981_lc, F and Frc lack the 1 MΩ
bleed resistor the script adds to the buck output nodes (negligible at mA loads); rerun
`sim_power_tree.py` and then `analyze.py` to regenerate them.

## Sources

Datasheets and documents as the research cites them; section, table and figure numbers in the text
refer to these editions.

| Short name | Document |
|---|---|
| [maxon p98] | [maxon catalogue Feb 2025 p98, DCX 8 M](https://www.maxongroup.com/medias/sys_master/root/9394600706078/Cataloge-Page-EN-98.pdf) |
| [maxon p100] | [maxon catalogue Feb 2025 p100, DCX 10 L](https://www.maxongroup.com/medias/sys_master/root/9394600902686/Cataloge-Page-EN-100.pdf) |
| [maxon key info] | [maxon "Key information"](https://people.ece.ubc.ca/leos/pdf/datasheets/Maxon/MaxonSpecs.pdf) |
| [maxon chokes] | [maxon "Current ripple & external motor chokes" V1.1](https://support.maxongroup.com/hc/fr/article_attachments/5266759938460) |
| [maxon DCX10L01EBKL531] | [maxon product page, DCX 10 L 4.5 V, ball bearings](https://www.maxongroup.com/maxon/view/product/motor/dcmotor/DCX/DCX10/DCX10L01EBKL531) |
| [maxon DCX10L01EBSL531] | [maxon product page, DCX 10 L 4.5 V, sleeve bearings](https://www.maxongroup.co.uk/maxon/view/product/motor/dcmotor/DCX/DCX10/DCX10L01EBSL531) |
| [maxon DC technology] | [maxon "DC motor technology – short and to the point" (2014), pp. 30-31](https://www.maxongroup.com/medias/sys_master/root/8815461597214/DC-Technology-short-and-to-the-point-14-EN-30-31.pdf) |
| [Portescap PWM] | [Portescap "Controlling Brushed DC Motors Using PWM" (2022)](https://www.portescap.com/en/newsroom/whitepapers/2022/03/controlling-brushed-dc-motors-using-pwm) |
| [Coilcraft loss data] | Coilcraft's power-inductor loss tool (coilcraft.com, behind a bot challenge) as recorded per part in [QY7/Power_toys](https://github.com/QY7/Power_toys) (`power_toys/data/coilcraft_loss_for_training`, `coilcraft_model`); Coilcraft's SPICE saturation models XAL7070-473_sat and XGL5030-472_sat as mirrored in [rothn/compact-hd-dac](https://github.com/rothn/compact-hd-dac) (`lib/sub/XAL7070.lib`, `XGL5030.lib`) |
| [Vishay PMS overview] | [Vishay Power Metal Strip product overview VMN-PL0407-1703 (2017), p7: thermal EMF](https://www.vishay.com/docs/49581/_power_metal_strip_product_overview_vmn_pl0407_1703.pdf) |
| [NTF TechCA41] | [45th All-Japan classic winner, technical sheet](https://www.ntf.or.jp/mouse/micromouse2024/Robot/AllJapan/TechCA41.html) |
| [DRV8874] | [TI DRV8874 SLVSF66A](https://www.ti.com/lit/ds/symlink/drv8874.pdf) |
| [DRV8262] | [TI DRV8262 SLVSFV5C](https://www.ti.com/lit/ds/symlink/drv8262.pdf) |
| [L6205] | [ST L6205 (Sept 2003)](https://www.st.com/resource/en/datasheet/l6205.pdf) |
| [INA241] | [TI INA241 SBOSA30D](https://www.ti.com/lit/ds/symlink/ina241a.pdf) |
| [INA228] | [TI INA228 SLYS021A](https://www.ti.com/lit/ds/symlink/ina228.pdf) |
| [WSK2512] | [Vishay WSK2512, doc 30108](https://www.vishay.com/docs/30108/wsk2512.pdf) |
| [DS13311] | [ST STM32H725 datasheet DS13311](https://www.st.com/resource/en/datasheet/stm32h725rg.pdf) |
| [RM0468] | [ST RM0468 reference manual](https://www.st.com/resource/en/reference_manual/rm0468-stm32h723733-stm32h725735-and-stm32h730-value-line-advanced-armbased-32bit-mcus-stmicroelectronics.pdf) |
| ES0491 | [ST ES0491 errata](https://www.st.com/resource/en/errata_sheet/es0491-stm32h723733-stm32h725735-and-stm32h730-device-errata-stmicroelectronics.pdf) |
| [AN2606] | [ST AN2606 Rev 70, system bootloader](https://www.st.com/resource/en/application_note/an2606-introduction-to-system-memory-boot-mode-on-stm32-mcus-stmicroelectronics.pdf) |
| [L6981] | [ST L6981 DS13554](https://www.st.com/resource/en/datasheet/l6981.pdf) |
| [STSPIN958] | [ST STSPIN958 DS14341](https://www.st.com/resource/en/datasheet/stspin958.pdf) |
| [TPS61178] | [TI TPS61178 SLVSDA7E](https://www.ti.com/lit/ds/symlink/tps61178.pdf) |
| [TPS2121] | [TI TPS2121 SLVSEA3F](https://www.ti.com/lit/ds/symlink/tps2121.pdf) |
| [TPS560430] | [TI TPS560430 SLVSE22B](https://www.ti.com/lit/ds/symlink/tps560430.pdf) |
| [TPS7A49] | [TI TPS7A49 SBVS121E](https://www.ti.com/lit/ds/symlink/tps7a49.pdf) |
| ADP7142 Rev H | read from mirrors (analog.com unreachable); secondary |
| [WS2812C-2020-V6] | [WS2812C-2020-V6 (LCSC C55109522)](https://datasheet.lcsc.com/datasheet/pdf/8c7f104c99e52e4adb687ae84e594e95.pdf?productCode=C55109522); [WS2812B-2020-V6 (C52917434)](https://datasheet.lcsc.com/datasheet/pdf/a29e59ba4bc7e47e236b4d50b6c26345.pdf?productCode=C52917434) |
| [ESP32-C5] | [Espressif ESP32-C5 Series datasheet v1.5](https://www.espressif.com/sites/default/files/documentation/esp32-c5_datasheet_en.pdf) |
| [ESP32-C5 TRM] | [Espressif ESP32-C5 Technical Reference Manual v1.1](https://www.espressif.com/sites/default/files/documentation/esp32-c5_technical_reference_manual_en.pdf) |
| [ESP32-C5-WROOM-1] | [ESP32-C5-WROOM-1/1U datasheet v1.3](https://www.espressif.com/sites/default/files/documentation/esp32-c5-wroom-1_wroom-1u_datasheet_en.pdf) |
| [ESP32-C5-MINI-1] | [ESP32-C5-MINI-1/1U datasheet v1.4](https://www.espressif.com/sites/default/files/documentation/esp32-c5-mini-1_mini-1u_datasheet_en.pdf) |
| [ESP layout] | [ESP32-C5 hardware design guidelines, PCB layout](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c5/pcb-layout-design.html) |
| [ESP schematic] | [ESP32-C5 hardware design guidelines, schematic checklist](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c5/schematic-checklist.html) |
| [ESP-Prog] | [Espressif ESP-Prog user guide, Program Interface](https://docs.espressif.com/projects/esp-dev-kits/en/latest/other/esp-prog/user_guide.html) |
| ESP certificates | [Espressif certificates](https://www.espressif.com/en/support/documents/certificates) |
| [ESP-IDF Wi-Fi performance] | [ESP-IDF Wi-Fi performance, ESP32-C5](https://docs.espressif.com/projects/esp-idf/en/latest/esp32c5/api-guides/wifi-driver/wifi-performance-and-power-save.html) |
| [SK-12D29] | [G-Switch SK-12D29-GXXX drawing (2016-05-29), LCSC C2848877](https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2108301530_G-Switch-SK-12D29-G060_C2848877.pdf) |
| [Samsung MLCC] | [Samsung product pages, DC-bias and ripple-current curves, e.g. CL32B106KBJNNN](https://product.samsungsem.com/mlcc/CL32B106KBJNNN.do) |
| [Panasonic TQC] | [Panasonic POSCAP TQC series (2023-06-30), LCSC C3018702](https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2401241128_PANASONIC-25TQC100MD3_C3018702.pdf) |
| [Kyocera-AVX TCJ] | [Kyocera-AVX TCJ series, TDS-PTNO-0027 Rev 19](https://datasheets.kyocera-avx.com/TCJ.pdf) |
| [SMAJ] | [Littelfuse SMAJ series (rev. 11/20/15), LCSC C148219](https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2304140030_Littelfuse-SMAJ18A_C148219.pdf) |
| [SMF] | [Littelfuse SMF series, LCSC C409420](https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/1912111437_Littelfuse-SMF18A_C409420.pdf) |
| Probe firmware | [bkuschak/cmsis_dap_tcp_esp32](https://github.com/bkuschak/cmsis_dap_tcp_esp32), [BareMetalTestLab/blackmagic-esp32-c5](https://github.com/BareMetalTestLab/blackmagic-esp32-c5), [OpenOCD cmsis_dap_tcp.c](https://github.com/openocd-org/openocd/blob/master/src/jtag/drivers/cmsis_dap_tcp.c) |
| SFH 4550, AN5419, TPS28225, CSD17578Q3A, TLV9001 SBOS833R | vendor datasheets; no URL recorded |

[maxon p98]: https://www.maxongroup.com/medias/sys_master/root/9394600706078/Cataloge-Page-EN-98.pdf
[maxon p100]: https://www.maxongroup.com/medias/sys_master/root/9394600902686/Cataloge-Page-EN-100.pdf
[maxon key info]: https://people.ece.ubc.ca/leos/pdf/datasheets/Maxon/MaxonSpecs.pdf
[maxon chokes]: https://support.maxongroup.com/hc/fr/article_attachments/5266759938460
[maxon DCX10L01EBKL531]: https://www.maxongroup.com/maxon/view/product/motor/dcmotor/DCX/DCX10/DCX10L01EBKL531
[maxon DCX10L01EBSL531]: https://www.maxongroup.co.uk/maxon/view/product/motor/dcmotor/DCX/DCX10/DCX10L01EBSL531
[maxon DC technology]: https://www.maxongroup.com/medias/sys_master/root/8815461597214/DC-Technology-short-and-to-the-point-14-EN-30-31.pdf
[Portescap PWM]: https://www.portescap.com/en/newsroom/whitepapers/2022/03/controlling-brushed-dc-motors-using-pwm
[Coilcraft loss data]: https://github.com/QY7/Power_toys
[Vishay PMS overview]: https://www.vishay.com/docs/49581/_power_metal_strip_product_overview_vmn_pl0407_1703.pdf
[NTF TechCA41]: https://www.ntf.or.jp/mouse/micromouse2024/Robot/AllJapan/TechCA41.html
[DRV8874]: https://www.ti.com/lit/ds/symlink/drv8874.pdf
[DRV8262]: https://www.ti.com/lit/ds/symlink/drv8262.pdf
[L6205]: https://www.st.com/resource/en/datasheet/l6205.pdf
[INA241]: https://www.ti.com/lit/ds/symlink/ina241a.pdf
[INA228]: https://www.ti.com/lit/ds/symlink/ina228.pdf
[WSK2512]: https://www.vishay.com/docs/30108/wsk2512.pdf
[DS13311]: https://www.st.com/resource/en/datasheet/stm32h725rg.pdf
[RM0468]: https://www.st.com/resource/en/reference_manual/rm0468-stm32h723733-stm32h725735-and-stm32h730-value-line-advanced-armbased-32bit-mcus-stmicroelectronics.pdf
[AN2606]: https://www.st.com/resource/en/application_note/an2606-introduction-to-system-memory-boot-mode-on-stm32-mcus-stmicroelectronics.pdf
[L6981]: https://www.st.com/resource/en/datasheet/l6981.pdf
[STSPIN958]: https://www.st.com/resource/en/datasheet/stspin958.pdf
[TPS61178]: https://www.ti.com/lit/ds/symlink/tps61178.pdf
[TPS2121]: https://www.ti.com/lit/ds/symlink/tps2121.pdf
[TPS560430]: https://www.ti.com/lit/ds/symlink/tps560430.pdf
[TPS7A49]: https://www.ti.com/lit/ds/symlink/tps7a49.pdf
[ADP7142]: https://www.analog.com/media/en/technical-documentation/data-sheets/adp7142.pdf
[Littelfuse 501]: https://www.littelfuse.com/assetdocs/fuse-501-datasheet?assetguid=c1b674fa-b4a7-46c1-a555-f089b77d5c57
[Takeyuta Lab]: https://neophile.hatenablog.com/entry/2023/08/19/143147
[JIERR MA]: https://atta.szlcsc.com/upload/public/pdf/source/20260316/D0E6F4E3E2183BCC856933993466F3DF.pdf
[WS2812C-2020-V6]: https://datasheet.lcsc.com/datasheet/pdf/8c7f104c99e52e4adb687ae84e594e95.pdf?productCode=C55109522
[WS2812C-2020-V6 V1.1]: https://www.world-semi.com/downloads/datasheets/en/ws2812c-2020-v6-2.1.pdf
[ESP32-C5]: https://www.espressif.com/sites/default/files/documentation/esp32-c5_datasheet_en.pdf
[ESP32-C5 TRM]: https://www.espressif.com/sites/default/files/documentation/esp32-c5_technical_reference_manual_en.pdf
[ESP32-C5-MINI-1]: https://www.espressif.com/sites/default/files/documentation/esp32-c5-mini-1_mini-1u_datasheet_en.pdf
[ESP32-C5-WROOM-1]: https://www.espressif.com/sites/default/files/documentation/esp32-c5-wroom-1_wroom-1u_datasheet_en.pdf
[ESP layout]: https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c5/pcb-layout-design.html
[ESP schematic]: https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c5/schematic-checklist.html
[ESP-Prog]: https://docs.espressif.com/projects/esp-dev-kits/en/latest/other/esp-prog/user_guide.html
[ESP-IDF Wi-Fi performance]: https://docs.espressif.com/projects/esp-idf/en/latest/esp32c5/api-guides/wifi-driver/wifi-performance-and-power-save.html
[SK-12D29]: https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2108301530_G-Switch-SK-12D29-G060_C2848877.pdf
[Samsung MLCC]: https://product.samsungsem.com/mlcc/CL32B106KBJNNN.do
[Panasonic TQC]: https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2401241128_PANASONIC-25TQC100MD3_C3018702.pdf
[Kyocera-AVX TCJ]: https://datasheets.kyocera-avx.com/TCJ.pdf
[SMAJ]: https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2304140030_Littelfuse-SMAJ18A_C148219.pdf
[SMF]: https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/1912111437_Littelfuse-SMF18A_C409420.pdf

The research studies behind this proposal are kept outside the repository and are cited by name
with their section: the drivetrain study (motor, battery, 4S), the driver study (motor drivers and
power stage), the driver comparison study (Q1/Q4), the current-sensing study (TSC2020 root cause,
in-line design), the 3V3 study (droop model), the power-tree study (analog rail, emitters, LEDs, USB
power path), the fan study, the ESP study (ESP32 subsystem), the non-OTG study and the
form-factor study (ESP32 packages, placement on the board and in the chassis).

## Appendix: prototype connection lists

Proposals to verify against the datasheets when entered in Zener.

### A.1 DRV8874PWPR, one per motor

- **VM** (11) to VBAT: 0.1 µF plus 4 × 10 µF X7R 50 V 1206 and the bulk, 2 × 10 µF X7R 50 V 1210.
- **VCP** (12): 100 nF 16 V to VM. **CPH/CPL** (13/14): 22 nF, VM-rated.
- **GND** (15), **PGND** (9), **PAD** to GND.
- **PMODE** (16) to GND: PH/EN mode.
- **EN/IN1** (1) to the timer PWM, **PH/IN2** (2) to the direction: right motor PA8 (TIM1_CH1)
  and PB8, left motor PC7 (TIM8_CH2) and PC6.
- **nSLEEP** (3) to Motors_Enable (PA10) with R49 100 kΩ pull-down.
- **nFAULT** (4): pull-up to 3V3_D; both drivers wire-ORed to PB2 (Motors_nFault).
- **IPROPI** (6): RIPROPI 2.0 kΩ 1 % to GND (0.9 V/A), nothing else.
- **VREF** (5): 4.7 kΩ / 20 kΩ divider from 3V3_D, 2.67 V for ITRIP 2.97 A (computed, VREF ≤ 3.6 V).
- **IMODE** (7) to GND: fixed off-time, auto-retry.
- **OUT1/OUT2** (8/10) to the motor through the WSK2512 shunt (A.3) and the XAL7070-473 47 µH
  choke.
- Firmware: PWM on EN between drive and the low-side brake (EN = 0); ADC triggers at the phase centres.
- Source: [DRV8874] Pin Functions, Tables 1, 3, 4, 6, §6.3, §7.3.3.

### A.2 DRV8262DDW, dual H-bridge (alternative)

- **VM** (2, 11, 12, 21) to VBAT: 0.01 µF X7R 50 V at VM-PGND12 and at VM-PGND34; ≥ 2-4 × 10 µF X7R
  50 V within a few mm; 2 × 10 µF X7R 50 V 1210 as bulk.
- **PGND12, PGND34, GND, PAD** to the GND plane, thermal via array under the pad (13 × 5 in the
  datasheet simulation).
- **VCP** (1): 1 µF 16 V X7R to VM. **CPH/CPL** (44/43): 0.1 µF X7R, VM-rated. **DVDD** (24): 1 µF
  10 V X7R. **VCC** (25): 3V3_D plus 0.1 µF.
- **MODE1** (28) to GND (dual H-bridge). **MODE2** (29) to GND (PH/EN; IN1 = 0 is the high-side brake,
  Table 6-3). **DECAY** (37) to GND (slow decay, needed for the HS mirror). **TOFF** (35) to GND
  (7 µs). **OCPM** (27) to GND (latched, cleared with a 20-40 µs nSLEEP pulse) or DVDD (auto-retry,
  4.1 ms).
- **IN1/IN2** (41/40) right motor PA8/PA9; **IN3/IN4** (39/38) left motor PC7/PC9.
- **nSLEEP** (42) to Motors_Enable with R49. **nFAULT** (26): 10 kΩ to 3V3_D, to PB2.
- **IPROPI1/IPROPI2** (31/30): RIPROPI 4.3 kΩ 1 % (0.91 V/A) for ITRIP only.
- **VREF1/VREF2** (34/33): 2.28-2.73 V for 2.5-3 A (computed from ITRIP × 212 µA/A × 4.3 kΩ; VREF
  ≤ 3.3 V).
- **OUT1/OUT2** (4-6 / 7-9) right motor, **OUT3/OUT4** (17-19 / 14-16) left, each through its shunt
  and choke footprint. **RSVD** (32, 36) unconnected.
- Source: [DRV8262] Tables 4-1, 6-1 to 6-4, 6-7, 6-8, §5.5, §6.5.2, §6.11.3.

### A.3 Motor current sensing

| From | To | Part / value | Note |
|---|---|---|---|
| Driver OUT1 (switching node) | Rsh force pad 1 | WSK2512 10 mΩ 1 W 4-terminal | 5 mΩ if the motor peak exceeds 7 A |
| Rsh force pad 2 | 47 µH choke → motor connector | – | Power path wide, away from the sense pair |
| Rsh sense pad (driver side) | INA241 IN+ (pin 8) | trace pair, no vias | Positive output = current from bridge to motor |
| Rsh sense pad (motor side) | INA241 IN− (pin 1) | – | No input filter (any Rs adds gain error) |
| INA241A2IDGKR VS (pin 6) | 3V3_A | 100 nF X7R 0402 at pins 6-2 | – |
| GND (pin 2), NC (pin 4) | GND | – | Pin 4 "connect to ground" |
| REF1 (pin 7) | 3V3_A | the VS pin's 100 nF, beside it | Mid-scale = VS/2, ratiometric with VDDA |
| REF2 (pin 3) | GND | – | – |
| OUT (pin 5) | R_iso 150 Ω → ADC pin (PB1 left, ADC1/2 fast; PC1 right) | C_f 1 nF C0G | Stable and settled in TI's model; sampling ≥ 0.7 µs (the ADC kickback, current_sense/ina241_riso.py); optional BAT54-class clamp |

Source: [INA241] §6.5, §7.3.1.1, pin functions; current-sensing study §8.

### A.4 VSYS, 3V3_A and emitter sink

- **VBAT → VSYS**: B5819W 40 V 1 A Schottky (C8598; about 12 µA reverse at 17 V, 25 °C, JCET
  B5817W-B5819W p2), the only part between VBAT and the regulators' input.
- **3V3_A**: VSYS → 22 Ω → 10 µF → ADP7142ACPZN3.3 (or TPS7A4901 with its FB divider, CNR/SS and
  CFF, ≥ 2.2 µF ceramic out); EN from 3V3_D. Place it away from the IMU and near the VDDA pin; run
  3V3_A as its own trace to VDDA, the INA241s and the sensor connectors.
- **VDDA pin**: 1 µF + 100 nF; FB1 → 0 Ω or a ≤ 50 mΩ bead.
- **Emitter sink**: op-amp (from 3V3_A) + N-FET (AO3400A) + 1.2 Ω 0.1 % ≤ 50 ppm/K sense
  (175 mA at 0.21 V); set-point from the DAC on PA5 (buffer off) through 200 kΩ / 20 kΩ, 0 when no
  emitter is selected; 1 kΩ sense → IN- with 1 nF C0G OUT → IN-, 200 kΩ 3V3_A → IN-; emitters from
  3V3_D through 3.3 Ω each, the AO3400A selectors with the main board's AC-coupled gates (220 Ω,
  220 nF, 22 kΩ to GND, 1N4148WS clamp).
- **LEDs**: WS2812C-2020-V6 × 2 on 3V3_D, 100 nF each, DIN from PB9 (TIM17_CH1).
- **Alternative 3V3_A**: TPS560430X3FDBVR, 12 µH, 22 µF / 10 V, CIN ≥ 4.7 µF / 50 V, CBOOT 100 nF,
  then 2.2 µH (≤ 50 mΩ, ≥ 100 mA, shielded) → 22 µF X7R/X5R 0805 ‖ (0.33 Ω + 47 µF); feedback at the
  buck output; no added series resistance. Calc: peaking +4 dB at 16 kHz, |Zout| ≤ 0.4 Ω, −22 / −41 /
  −64 dB at 100 kHz / 300 kHz / 1.1 MHz (power_tree/calc_power_tree.py §8).

Source: power-tree study §6-§9; [TPS560430] Table 1; [TPS7A49]; ADP7142 Rev H.

### A.5 Fan, STSPIN958

```text
VBAT ── VS (27-30) ── 2 × 470 nF 50 V X7R 0805 at the pins, 2 × 10 µF 50 V 1206, the bridges' VBAT bulk
VSPUMP (4) ── C33 1 µF 50 V X7R ── VBOOT (7) ; CP1 (5) ── C32 100 nF ── CP2 (6)
3V3_D ── VDD (13) ── C31 220 nF ; nSTBY (10) ── 3V3_D
MODE1 (20) = 3V3, MODE2 (19) = GND, MODE3 (18) = 3V3   (parallel half-bridge, PWM trimming, Table 8)
OFFSET (9) = GND
OUT1 (31, 32) + OUT2 (25, 26) ── FAN_OUT ──[ L6 XGL5030-472 4.7 µH ]── M3 pin 1 (fan +)
LSS1 (1, 2) + LSS2 (23, 24)  ── FAN_LSS ── M3 pin 2 (fan −) ; R31 20-25 mΩ 1206 FAN_LSS → GND (Kelvin to the pins)
PWM2/PH (12) ── GND   (load OUT→LSS: low-side recirculation on limit, Fig. 11/14)
PWM1 (11)    ── Fan_PWM (PA7, TIM14_CH1, 400 kHz)
EN/nFAULT (14) ── Fan_Enable (PB10, driven open-drain) ; R27 39 kΩ to 3V3, C30 10 nF (Table 12)
TOFF (16)    ── Fan_TOFF (PA12): limiter-active flag in PWM trimming (section 5.6.2)
REF (15)     ── R28 4.7 kΩ / R29 2.0 kΩ from 3V3 → V_REF = I_peak · R31 · 10 = 0.985 V (3.94 A)
SR (21)      ── 1-2.2 kΩ to GND
V1 (8), V2 (17) ── NC (or V1 → an ADC pin if one frees: 0.25 V/A with 25 mΩ)
GND (22), GNDPUMP (3), EPAD (33) ── GND
```

No capacitor across the fan motor. Pin numbers from the repo symbol
`components/st/STSPIN958/STSPIN958.kicad_sym` ([STSPIN958] Figure 2, Table 6).

### A.6 ESP32-C5-MINI-1

| ESP32-C5-MINI-1 (pin) | Net | Other end | Notes |
|---|---|---|---|
| 3V3 (3) | 3V3_D | L6981C33 | 22 µF + 100 nF at the module, 10 µF on its feed; 3V3 total < 145 µF |
| GND (1, 2, 42, 43, 46-48, 50-65), EPAD | GND | – | Dense GND vias along the module's ground edge and the notch |
| EN (45) | ESP_EN | R89 10 kΩ to 3V3_D, C110 1 µF to GND, J2 pin 1 | RC delay ([ESP32-C5-MINI-1] section 9) |
| GPIO28 (4, strap) | ESP_BOOT | R90 10 kΩ to 3V3_D, J2 pin 6 | Low at EN's rise enters the UART download mode (Table 4-3); no capacitor |
| TX0 / RX0 (39 / 40, GPIO11 / GPIO12) | ESP_TXD0 / ESP_RXD0 | J2 pins 3 / 5 | UART0, ROM log and download; 499 Ω on TX0 in the module (Figure 8-1) |
| GPIO0 (16) | SWDIO | H7 PA13, SWD1 | – |
| GPIO1 (17) | SWCLK | H7 PA14 through R86 22 Ω, SWD1 | Series resistor on the clock (checklist, SPI) |
| GPIO10 (22) | ESP_SCK | H7 PC10 (SPI3_SCK; UART4_TX in the fallback) through R95 22 Ω at PC10 | spi_slave_hd clock; U1RXD in the fallback |
| GPIO8 (20) | ESP_DATA | H7 PC12 (SPI3 data line, MOSI pad) through R96 220 Ω at the C5 | Half-duplex data, both directions ([RM0468] Figure 643 note 3) |
| GPIO9 (21) | ESP_CSn | H7 PC11 (GPIO chip select; UART4_RX in the fallback) through R88 100 Ω | U1TXD in the fallback |
| GPIO23 (31) | Reset | H7 NRST, SW3, C21 | Open drain only |
| GPIO24 (32) | ESP_Flow | H7 PA9 (EXTI9, pull-down) | The C5's credits |
| GPIO2-GPIO7, GPIO13-GPIO15, GPIO25-GPIO27 | – | – | Open; the straps at their defaults (Tables 4-1 to 4-7) |

Every H7 line lands on a GPIO free of any restriction ([ESP32-C5] §2.3.5, priority 2), with its
input and output off and no pull at reset ([ESP32-C5 TRM] Table 8.13-1). J2 is the ESP-Prog
Program interface: 1 EN, 2 5V_IN, 3 TX0, 4 GND, 5 RX0, 6 GPIO28 ([ESP-Prog]). SW3 and the SWD1 pads
on GND/PA13/PA14 stay as the backstop. Source: [ESP32-C5-MINI-1] Tables 3-1, 4-1 to 4-3, 6-2 to
6-5, section 9; `boards/main2/Esp.zen`.
