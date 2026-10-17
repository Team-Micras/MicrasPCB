# Next main-board revision: design

Research for the second revision of the `main` board. The design is entered in Zener as the board
[`main2`](../../boards/main2/layout/README.md) (schematic only), with the option this document
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
| **USB-C connects only to the ESP32**: no USB switch, no H7 USB | The ESP bridges the PC's USB serial data to H7 UART4 (PA11/PA12); the H7 DFU path is gone |
| The **ESP32 replaces the HM-19 module and the SWD connector** | It flashes the H7 over SWD with NRST, is the wired and Wi-Fi debug probe, and relays Wi-Fi/BLE telemetry |
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
4S LiPo 12.0-16.8 V (17.4 V HV) ─ J1 ─ Q6 HSBB3072 (slew-limited low-side switch) ─ VBAT
   [reverse polarity: keyed connector only]  [TVS: SMAJ18A recommended, owner's decision]
   VBAT ─┬─ R_bat 2 mΩ 4-terminal ─ INA228 (I²C to the ESP32)
         ├─ DRV8874 (right) ─ WSK2512 10 mΩ ─ choke footprint (47 µH or 0 Ω) ─ DCX 10 L 4.5 V   INA241A2 on the shunt
         ├─ DRV8874 (left)  ─ WSK2512 10 mΩ ─ choke footprint (47 µH or 0 Ω) ─ DCX 10 L 4.5 V   INA241A2 on the shunt
         ├─ STSPIN958, 400 kHz, REF limit ─ choke footprint (4.7-10 µH or 0 Ω) ─ fan motor
         ├─ R44/R45 100k/20k ─ PC5 (battery voltage)
         └─ Schottky 40 V ─┐
USB VBUS ─ P-FET (gate follows VBAT) ─┴─ VSYS (4.3-17.4 V)
                                          ├─ L6981C33 ─ 3V3_D: H7 VDD/VDDSMPS, ESP32-S3-MINI-1, encoders, IMU,
                                          │              WS2812C-2020-V6 ×2, IR emitters (3.3 Ω each) → AC-coupled selectors → CC sink
                                          └─ 22 Ω + 10 µF ─ ADP7142ACPZN3.3 or TPS7A4901 (EN = 3V3_D) ─ 3V3_A:
                                                 VDDA (1 µF + 100 nF), INA241A2 VS + REF1, phototransistor collectors,
                                                 emitter-sink op-amp (set-point from the DAC on PA5)
USB-C D± ─ U6 USBLC6 ─ ESP32-S3 GPIO19/20 (CMSIS-DAP + CDC + MSC)
ESP32 ─ SWDIO/SWCLK/NRST (BOOT0 optional) ─ H7;  ESP UART ─ H7 UART4 PA11/PA12 up to 5 Mbaud;  PH1 flow control
DRV8874 nFAULT ×2 wire-OR ─ PC15
```

### Power tree

- **VSYS** is one system node, `OR(VBAT, VBUS)`, ahead of both regulators, so the ESP, the H7 (for
  SWD flashing) and VDDA all run from USB alone. The battery side and the bridges are never
  back-fed: the VBAT side blocks VSYS → VBAT, and a 4S pack (≥ 12 V) is always above VBUS.
  - **Recommended for HV cells:** a 40 V, 1 A Schottky from VBAT to VSYS (loss ≈ 0.4 V × 0.13 A ≈
    50 mW at 14.8 V, computed) plus a 30 V P-FET (AO3401A class) from VBUS: drain on VBUS, source
    on VSYS, gate to VBAT through 10 kΩ with 1 MΩ to GND. With the battery present VGS ≈ +0.25 V and
    the FET is off; with it absent VGS ≈ −4.6 V and the FET is on (power-tree study §8, inference).
    B5819W (C8598) and SS14 (C2480) are JLC basic parts. The low-loss version is two LM74700-Q1
    (or MX74700T) ideal-diode controllers with N-FETs (65 V anode rating, POR rising 3.9 V max;
    SNOSD17G).
  - **TPS2121 only with non-HV cells:** 17.4 V sits 4.6 V under its 22 V recommended maximum and
    6.6 V under its 24 V absolute maximum, and no practical TVS clamps below 24 V ([TPS2121]
    §7.1, §7.3).
- **3V3_D**: the L6981C33 stays (1.5 A, 3.5-38 V, output network 30.5-145 µF at 3.3 V; [L6981]
  §8.4.3). Its LCM light-load step (+1.8 %, §6.4.1) no longer reaches the ADC, because the analog
  loads are on their own rail. The ESP adds up to 355 mA Wi-Fi TX peak and asks for a supply of at
  least 0.5 A ([ESP32-S3-MINI-1] Tables 6-2, 6-4); 10 µF + optional 22 µF at the module keeps the
  3V3 total at about 104 µF, inside the 145 µF window.
- **3V3_A**: an HV LDO fed from VSYS through **22 Ω + 10 µF**: the **ADP7142ACPZN3.3** (fixed
  3.3 V, 2.7-40 V, 44 V abs max, 11 µVrms, 68 dB at 100 kHz and 50 dB at 1 MHz, 80 µA ground
  current at 10 mA; LFCSP 72 °C/W, TSOT 170 °C/W, so the LFCSP; ADP7142 Rev H Tables 1-4) or the
  **TPS7A4901** (adjustable 1.194-33 V, 3-36 V, 15.4 µVrms, ≥ 52 dB 10 Hz-400 kHz, dropout 260 mV
  at 100 mA, ≥ 2.2 µF ceramic output; [TPS7A49] p1, §6.4, §6.5).
  - **Loads**: VDDA (the ADCs and, on VFQFPN68, VREF+), both INA241A2 VS and REF1, the four
    phototransistor collectors, the emitter-sink op-amp and its bias: **9.7 mA typical,
    22.5 mA worst case** (all receivers saturated), +0.65 mA if the IMU moves here
    (power_tree/calc_power_tree.py §1, from DS13311 Tables 84/87, SBOSA30D §6.5, SBOS833R §7.10).
  - **Heat**: about 113 mW at 10 mA from 14.8 V and 328 mW at 23 mA from 17.4 V; +7 K and +19 K in
    HVSSOP-8 (power-tree study §5). Keep the LDO away from the IMU.
  - **Input filter**: the 22 Ω keeps headroom on USB-only power, where VSYS can be 4.3 V and the LDO
    needs 3.3 V + dropout at 23 mA (power-tree study §9). The RC also keeps the 100 kHz motor ripple out
    of the LDO, whose PSRR is lower there than at kHz.
  - **Sequencing**: the LDO EN on 3V3_D, so 3V3_A starts after VDD. While VDD is below VDDmin, VDDA
    must stay below VDD + 300 mV; at power-down VDD may fall below the others only if the energy
    left is below 1 mJ (DS13311 §3.7.1, Figure 2). The ADP7142's EN turns on at 1.30 V at most and off
    at 1.06 V at least (Rev H Table 1); the TPS7A4901's thresholds: **TODO**.
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
  | Risks | the input RC must keep the 100 kHz motor ripple out (LDO PSRR is lower there); package thermal at ≈ 0.33 W (**TODO**) | must stay forced PWM; damping must be right (series damping gives a 60 LSB lit/dark shift); another switching hot loop near the analog section |

  The model's LDO case used 47 Ω; at ≤ 22 Ω the window spread, which comes from that pre-resistor,
  roughly halves (inference, power-tree study §4). At 10-20 mA the buck saves only 0.06-0.26 W, so the
  LDO is the quieter, smaller and simpler rail.
- **No 5 V rail**: the ESP is on 3V3_D, the LEDs are 3.3 V parts, the INA241 runs from 2.7 V, the
  DRV8874 and STSPIN958 regulate internally from VM, and the emitters are on 3V3_D. The `+5V` net
  shrinks to the VBUS input of the power path.
- **USB-only budget** (85 % efficiency assumed): flashing and debug 222 mA from VBUS, ESP TX peaks
  441 mA, everything including emitters and white LEDs 588 mA, against 500 mA from a USB 2.0 port.
  On USB alone the firmware keeps the emitters and LEDs off or dim and may cap TX power; BLE at
  9 dBm draws 204 mA against 340 mA at 20 dBm (power-tree study §8, [ESP32-S3-MINI-1] Table 6-5).
- **4S ratings**: C36 (16 V) becomes ≥ 25 V; SW4 (MK-12D18-G040, DC 12 V) becomes the G-Switch SK-12D29-G060
  (DC 24 V 1 A, 1.38× the 17.4 V HV pack; the same 8.6 × 3.6 mm body with a 6.0 mm black lever; three
  pins at 2.0 mm pitch and two frame legs, so a new footprint; `components/g-switch/SK-12D29-G060`);
  R44/R45 (100k/27k gives 3.57-3.70 V, above VDDA) becomes 100k/20k on PC5, 2.90 V at 17.4 V
  (firmware constant 6.0); 25 V capacitors sit at 67 % of rating on 4S (drivetrain study §4).
- **Battery switch**: Q6 HSBB3072 stays: VDS 30 V (1.79× margin at 16.8 V), VGS = VBAT/2 = 6-8.4 V,
  0.61-0.97 W at 16 A. It gives **no reverse-polarity protection**: its body diode conducts with
  the pack reversed (driver study Q6); the connector keys the polarity.
- **VBAT capacitance, no electrolytics** (calculations/power_tree/vbat_bulk.py): the board carries
  only ceramics. On VBAT the bulk does four jobs; with a 4S pack and the slew-limited Q6 the
  ceramics cover each:
  - *100 kHz ripple*: the bridges draw I·√(D(1−D)) each; the ceramics carry it (0.2-0.4 A rms per
    part, against 2.6 A for a 10 °C rise on the 1206's Samsung curve). An electrolytic adds almost
    nothing at 100 kHz: its ohm-level ESR leaves it 0.15 A.
  - *Damping the pack leads against the ceramics*: the pack's own 0.1-0.3 Ω (the 0.5-1.5 V sag at
    5 A) is above the LC's characteristic impedance (42-73 mΩ at 100-300 nH), so the source does not
    ring (Q ≤ 0.72). A bench supply on 1 m leads (1 µH, 30 mΩ) does (Q ≈ 4); keep bench leads short.
  - *Hot plug and switch-on*: Q6 sits between the pack and the capacitors. At plug-in, C58 couples
    the pack's edge onto Q6's gate, Q6 conducts at about 3 V and the ceramics charge in
    microseconds, the current limited by the pack's resistance (≈ 100 A peak from 0.1 Ω, under the
    HSBB3072's 240 A IDM), without overshoot from the pack's leads; from a bench supply on 1 m leads
    VBAT overshoots to 24 V from 17.4 V. Closing SW4 ramps VBAT over about 5 ms, and opening it
    under a 5.8 A load lets VBAT fall over tens of ms: no inductive kick on Q6.
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
  | **2 × CL32B106KBJNNNE 10 µF 50 V X7R 1210 (chosen)** | **56 µF** | **285 mV** (79 mV interleaved) | **0.37 A rms per part** | **16 mm² (2 × 3.2 × 2.5)** | **2.5 mm** | **$0.66** | **Q 0.41-0.72 on the pack; bench Q 4.2 (0.56 Ω peak); 50 V, 2.9× the HV pack** | **C138687, 79 k stock** |
  | 4 × CL32B106KBJNNNE 1210 | 81 µF | 198 mV | 0.25 A rms | 32 mm² | 2.5 mm | $1.32 | bench Q 3.5 | C138687 |
  | Panasonic 25TQC33MYF 33 µF 25 V polymer tantalum | 98 µF | 212 mV | 0.88 A rms (1.4 A rated at 100 kHz) | 31.4 mm² (7.3 × 4.3) | 1.9 mm | $0.94 | ESR 60 mΩ ≈ Z0: damps the bench too (0.24 Ω peak); 25 V, used at 70 % on the HV pack (Kyocera-AVX TCJ: 80 % of Vr ≥ 16 V up to 85 °C, less above); transients must stay ≤ 25 V (Panasonic TQC); fails short | C191808, 4.3 k stock |
  | Panasonic 25TQC100MD3 100 µF 25 V polymer tantalum | 232 µF | 183 mV | 1.0 A rms (1.6 A rated) | 31.4 mm² | 2.8 mm | $2.50 | as above (bench 0.10 Ω peak) | C3018702, 4.6 k stock |
  | Hybrid: ceramics + R-C damping leg | – | – | – | – | – | – | a damping leg needs about 4× the ceramic capacitance (≈ 130-220 µF) behind R ≈ Z0 (0.1-0.2 Ω): an electrolytic- or polymer-sized part, or 30-60 more MLCCs; a small R-C does not damp | – |

  KEMET T521 25 V polymers (T521V226M025ATE040, T521D476M025ATE065) have no JLCPCB stock; 35 V
  polymers come at 10-15 µF (Panasonic 35TQC, 120-150 mΩ) or in 4.1 mm E cases (Kyocera-AVX
  TCJE476M035). The 1210 holds twice the 1206's capacitance at 16.8 V (6.1 against 3.2 µF, Samsung
  DC-bias curves: −39 % against −68 %) in a third more area, so two per bridge bring the ripple
  inside the 300 mV of the analog-rail model's HV case at a sixth of the electrolytic's footprint
  and half its height, rated at 50 V, with no short-failure mode. What the ceramics give up: the
  damping of a bench supply on long leads, and some milliseconds of regeneration hold-up.
- **VBAT overvoltage and a TVS** (calculations/power_tree/vbat_bulk.py). The lowest ratings on VBAT
  and VSYS: the 25 V MLCCs on VSYS (C52, C53, C80), Q8 AO3401A (−30 V VDS, VSYS against an absent
  VBUS), Q6 HSBB3072 (30 V VDS, with the pack connected), then 40 V (DRV8874 VM abs max, B5819W),
  42 V (L6981 VIN), 44 V (ADP7142), 62 V (STSPIN958 VS), 85 V (INA228). Per case:
  - *Hot plug*: none from the pack (VBAT ≤ 17.4 V, Q6 VDS ≤ 3.4 V); 24.2 V from a bench supply on
    1 m leads (23.5 V with an SMAJ18A at J1).
  - *SW4 off, or Q6 turning off under load*: none; the back-EMF of a coasting DCX 10 L 4.5 V is at
    most 5.3 V at 14,300 rpm, far below the pack, so the bridges' body diodes never charge VBAT, and
    Q6's turn-off is slewed over tens of ms (no L·di/dt).
  - *Pack pulled while the firmware brakes*: each motor can push at most E²/(4R) = 1.9 W into VBAT
    at full speed (3.8 W for both; 3.2 W net of a 0.6 W logic load), from 0.64-1.07 J of kinetic
    energy (76-130 g at 4 m/s). The 56 µF of ceramics reach 25 V in 2.9 ms, 30 V in 5.2 ms and the
    DRV8874's 40 V in 11 ms (the electrolytics bought 12-47 ms); a stop lasts hundreds of ms.

  Recommendation (not on the board, the owner's decision): an **SMAJ18A** (Littelfuse; VR 18 V
  above the 17.4 V pack, VBR 20.0-22.1 V, VC 29.2 V at 13.7 A, 400 W 10/1000 µs, 3.3 W on an
  infinite heatsink; DO-214AC 4.8-5.3 × 2.4-2.8 × 1.9-2.3 mm, about 18 mm² with its pads; LCSC
  C148219, $0.11, or C908771 $0.03) from BAT_P to GND_BAT at J1. Q6 is on while the board runs, so
  it clamps VBAT too: braking regeneration at about 0.15 A and 21 V for a few hundred ms, under
  every rating above, and a bench hot plug. The SOD-123FL SMF18A (200 W, RθJA 220 °C/W; 3.9 ×
  2.0 × 1.1 mm, C409420, $0.12) has the same voltages in half the area but marginal heat capacity
  for 1 J over a stop. Without a TVS, the firmware must stop regenerative braking (coast, or EN = 0
  low-side brake, which dissipates in the motor) whenever VBAT rises above the pack's maximum.

### Drivetrain

- **Bridges**: 2 × **DRV8874PWPR**, one HTSSOP-16 per motor, next to its motor connector with its
  shunt and amplifier ([DRV8874]). Comparison with the L6205D and the DRV8262: [Q4](#q4-l6205d-vs-drv8874-vs-drv8262).
- **Mode**: PH/EN (**PMODE = GND**). The timer PWM goes on EN and the direction on PH: EN = 0 is the
  low-side brake (Table 3), so the bridge alternates drive and low-side slow decay, the low-side
  mirror sees the current continuously, and the ripple is half that of drive/coast. In PWM mode
  IN1 = IN2 = 0 is coast (Hi-Z) and IN1 = IN2 = 1 is brake (Table 4); in coast the current
  recirculates through the body diodes and IPROPI reads nothing. Same two MCU pins per motor.
- **PWM**: 100 kHz, unipolar sign-magnitude, centre-aligned. Right motor on TIM1_CH1/CH2 (PA8/PA9),
  left on TIM3_CH2/CH4 (PC7/PC9), TIM3 slaved to TIM1 over ITR and the bridges interleaved 180°,
  which roughly halves the summed input ripple. In centre-aligned mode a 180° shift moves one
  bridge's on-centre onto the other's off-centre, so a trigger at CNT = 0 and CNT = ARR still lands
  on a phase centre of each bridge (inference, untested). TIM8 is not an option for the left motor:
  it collides with LED_ARGB on TIM8_CH1 (PC6).
- **Why 100 kHz**: the DRV8874 ceiling is 100 kHz, and the INA241's PWM rejection "holds the output
  for 1 µs ... up to a PWM frequency of 125 kHz or if common-mode transient edges are separated by a
  3 µs interval or more" ([INA241] §7.3.1.1). At 200 kHz no phase reaches the 4 µs centre window
  (1 µs hold plus 1 µs settling each side) at mid duty.
- **Current limit**: ITRIP = VREF / (RIPROPI × AIPROPI), set to **2.5-3 A** with RIPROPI 2.0 kΩ 1 %
  (0.9 V/A), VREF = 2.25-2.7 V (computed; VREF 0-3.6 V, IIPROPI ≤ 3 mA; [DRV8874] §6.3, §7.3.3).
  **IMODE = GND**: fixed off-time with auto-retry, nFAULT only for real faults. The 25 µs off-time
  ends at the next input edge ("if the state of the ... control pin inputs changes during the tOFF
  time, the remainder of the tOFF time is ignored", §7.3.3.2.1), so with a 100 kHz input the
  chopping ends at the next PWM edge. Cycle-by-cycle mode (IMODE 20 kΩ or 62 kΩ, Table 6) pulses
  nFAULT low at every chop (Figure 14), which would hit the PC15 EXTI at up to 100 kHz (inference).
- **OCP**: 6 A minimum, 10 A typical, no maximum (§6.5). Unregulated at 16.8 V the motor would draw
  5.42 A at stall and 7.12 A in a full-speed reversal through a DRV8874 (drivers/q4_drivers.py), so
  ITRIP, not OCP, holds the current. During tBLK + tDEG (1.7 µs) the current overshoots ITRIP by
  0.41-0.62 A with a 47 µH choke and 0.83-2.78 A without (current_sense/q1_sampling.py): at 0.3·L
  with no choke a 3 A ITRIP reaches about 5.8 A, close to the 6 A OCP minimum.
- **Choke**: a footprint per motor for a **47 µH shielded choke**, Isat above ITRIP plus the
  overshoot (≈ 3.6 A at a 3 A ITRIP, computed), with a 0 Ω option. Fit it if the motor's measured
  inductance at 100 kHz requires it. maxon warns that the effective inductance at 50-100 kHz is only
  "30-80 %" of the 1 kHz datasheet value ([maxon chokes]). At 16.8 V and 100 kHz
  (drivetrain/dcx10l_ripple.py):

  | | Datasheet L | 0.3 · L |
  |---|---|---|
  | No choke | 0.93 A pp, 0.21 W | 2.84 A pp, 2.10 W |
  | 47 µH choke | 0.46 A pp, 0.05 W | 0.69 A pp, 0.12 W |

  The DCX 10 L continuous loss budget is about 1.28 W at its 600 s thermal limit (drivetrain/extra.py).
  Downsides of the choke: [below](#series-choke-with-a-motor-downsides).
- **Firmware limits** (drivetrain study §5): 2.5-3 A peak per motor in hardware (ITRIP), 1.0 A rms per
  motor over a 60 s run (0.86 A over 120 s) from 25 °C, ripple included, and about 5-6 A peak and
  3 A rms on the battery path. About 31 % duty at no load keeps the motor under 14,300 rpm at
  16.8 V, so the wheel speed command is capped at about 4 m/s at G ≈ 4.27 (or 4.6 m/s at 3.7:1).
  The pack sags 0.5-1.5 V at 5 A (assumed 4 × cell IR + 3.4 mΩ), so the bridges see about
  11.5-16.8 V and the duty feed-forward scales by the measured VBAT.
- **Bridge decoupling**: per bridge, 4 × 10 µF X7R 50 V 1206 within a few mm plus 2 × 10 µF X7R 50 V
  1210 as bulk, no electrolytic ([VBAT capacitance](#power-tree)); 0.1 µF at VM. The input ripple
  is I·√(D(1−D)), about 1-1.2 A rms per bridge at 2.4 A (drivetrain study §5, driver study Q6). Size the battery input, Q6, the VBAT plane and the
  bridge supply for about 6 A peak and 3-4 A rms; each motor trace for about 3 A peak and 1-1.5 A rms.
- **Motor safety in reset**: nSLEEP of both bridges on Motors_Enable (PA10) with the R49 100 kΩ
  pull-down, so the bridges sleep while the H7 is in reset or halted for SWD flashing.
- **Brush wear**: every DCX 10 L has precious-metal brushes, which maxon recommends for low
  continuous currents and advises against for start/stop and reversing duty ([maxon key info]). No
  commutator-wear data at 4-5 × the rated current is published; contest use shows the motor
  survives.

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
  injected samples ([RM0468] §28.4; [DS13311] Tables 84-86).
- **Driver mirror**: RIPROPI + VREF set the DRV8874's internal ITRIP and need no MCU pin. On the
  first prototype a DNP 0402 0 Ω from each IPROPI node to the INA241's ADC net, with the INA241
  output resistor removable, lets the bench compare both sensors on one board.
- **Battery current**: an **INA228** with a 2 mΩ 4-terminal shunt on VBAT after the switch: 20-bit,
  ±1 µV offset, ±0.05 % gain, ±20.48 A (ADCRANGE = 1; [INA228]). It is too slow for the control
  loop (50 µs minimum conversion plus I²C), and the H7 has no free I²C pins, so it sits on the ESP's
  I²C and the readings travel over UART4 (inference). The PC5 divider stays for fast duty
  feed-forward.
- **Rework test on the current board**: the INA241 pinout matches the TSC2020 MiniSO-8 except pin 4,
  which must go to ground; pin 3 is already ground, so a 3-4 solder bridge swaps IC3/IC4 for INA241A2
  (pending a check of the DGK land pattern).

### Fan

- **STSPIN958**, parallel half-bridge mode, **400 kHz** on TIM12 (ARR 687), the same three MCU pins
  as today (Fan_PWM PB15, Fan_Enable PB14, Fan_TOFF PB13). It is the only integrated single-bridge
  driver found with PWM up to 500 kHz, a cycle-by-cycle current limiter, synchronous freewheeling and
  integrated protection (OC, OT 150 °C, UVLO, EN/nFAULT) ([STSPIN958]; fan study §3).
- **Load model**: a drone-class coreless motor, R 0.2-1.2 Ω, L 1-10 µH (3 µH nominal for 1S; no
  drone motor publishes L, so it is scaled from Faulhaber data by L ∝ 1/kv²), kv 13-17k rpm/V for
  1S, operating at 1-4 A (fan study §1). A 1S motor on 16.8 V runs at D = 22 %, and a locked rotor draws
  13-50 A from 16.8 V (upper bound, battery IR excluded), so the REF limiter is also the soft start.
- **Changes**: R31 → 20-25 mΩ 1206 1 W; REF → I_peak ≈ 1.5 × the chosen motor's running current
  (3-5 A; V_REF = I_peak · R_sense · 10, e.g. 25 mΩ and 4 A give 1.0 V: R28 = 22 kΩ, R29 = 9.1 kΩ on
  3V3); RSR 5.6 kΩ → 1-2.2 kΩ (1.2-2 V/ns), which cuts the switching loss 2-3.3× at 400 kHz; C36 → at
  least 25 V, or 2 × 10 µF 50 V X7R 1206 at VS plus the shared VBAT bulk; C34/C35 470 nF → 50 V parts;
  a 4.7-10 µH shielded choke footprint (Isat ≥ I_peak, about 5 × 5 mm) with a 0 Ω option, fitted if
  the chosen motor measures below about 4 µH (fan study §5).
- **Firmware**: duty = V_cmd / VBAT, never below the 11.2 % floor set by the 280 ns minimum pulse at
  400 kHz except at 0; ramp the duty and let the REF limit absorb start-up; TOFF (limiter active for
  long periods) and EN/nFAULT are stall and fault flags.
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
  does not reach the current, and a pin held high turns its emitter off within 7.5-11 ms. The DAC
  must step with each selector (up at or after its rising edge, to 0 at or before its falling
  edge); then the pulse settles to 1 % in 7-13 µs without overshoot
  ([emitter/emitter_sink.py](calculations/emitter/emitter_sink.py); `boards/main2/Sensors.zen`).
  Kelvin-connect the 1.2 Ω and keep the emitter loop compact and away from VDDA/VSSA. Op-amp:
  TLV9001 (IQ 60 µA typ, 1 MHz, 2 V/µs; `components/ti/TLV9001`); a bench step across the 1.2 Ω
  confirms the modelled response. The emitter brightness falls −0.5 %/K (SFH 4550), so firmware
  temperature compensation is worth considering.
- **Status LEDs**: **WS2812C-2020-V6** (C55109522; WS2812B-2020-V6 C52917434 second) on 3V3_D with
  100 nF each. VDD 3.3-5.3 V, DIN VIH 0.55·VDD, so PC6 drives it directly; same GRB protocol and
  firmware ([WS2812C-2020-V6] p.1-3). Both datasheets put the 3.3 V minimum only in the feature
  text and the maximum-ratings range, and 3V3_D can dip 50-60 mV, so blue/green brightness at 3.2 V
  needs a bench check. Fallback: plain RGB LEDs on ESP GPIOs (LEDC PWM; inference).

### ESP32 and USB

- **ESP32-S3-MINI-1-N8** (15.4 × 20.5 × 2.4 mm, 8 MB flash, 39 GPIOs, pre-certified antenna)
  ([ESP32-S3-MINI-1] Table 1-1). It is the only Wi-Fi/BLE ESP32 with a general-purpose USB OTG
  controller ([ESP32-S3] §4.2.1.7), which lets the single USB-C port be a standard CMSIS-DAP v2 probe,
  a CDC serial port bridged to the H7 and a mass-storage drive at once
  ([Q2](#q2-the-compromise-of-an-esp32-without-usb-otg)).
- **USB**: USB-C D± → U6 USBLC6 → ESP GPIO19 (D−) / GPIO20 (D+); CC 5.1 kΩ Rd unchanged; SBU open.
  VBUS goes only into the power path.
- **H7 data link**: an ESP UART on the existing UART4 nets (PA11 = UART4_RX, PA12 = UART4_TX) at
  up to **5 Mbaud**, the ESP UART limit: about 500 kB/s, 40-180× the HM-19's 2.7-11.5 kB/s, enough
  for the "8 floats at 8 kHz" stream of 256 kB/s (MicrasFirmware `bluetooth_design.md` §7). PH1
  carries flow control. With a laptop on Wi-Fi the UART is the bottleneck (S3 TCP about 20 Mbit/s
  in open air, [ESP-IDF Wi-Fi performance]).
- **Flashing**: SWD with connect-under-reset (NRST), no system bootloader and no BOOT0. The H725's
  bootloader UART/SPI/I²C pins all carry motors, the buzzer, sensors or the sensor bus, and PA10 is
  Motors_Enable ([AN2606] Table 133). The H7 flash is a single 1 MB bank of eight 128 kB sectors, so
  the A/B images live in the ESP's 8 MB. The 164 kB image takes about 2.2 s to erase and 0.67 s to
  program (typical; [DS13311] Table 48), so a flash takes about 3-4 s (computed). BOOT0 control by the
  ESP is optional (R42 holds it low); SW5 and SW3 stay as manual fallbacks.
- **Debug probe**: CMSIS-DAP (ST-Link is proprietary). Base firmware espressif/esp-usb-bridge
  (CMSIS-DAP v2 bulk + CDC + MSC on S3) plus the Wi-Fi CMSIS-DAP-TCP server from
  bkuschak/cmsis_dap_tcp_esp32 ("Tested with ESP32 S3, C3, and C6 ... several STM32 development
  boards", up to 200 KB/s SRAM, ~6 MHz SWD). OpenOCD's `cmsis-dap backend tcp` is in master only (last
  tag v0.12.0, 2023). The H725 accepts SWCLK up to 71 MHz ([DS13311] Table 124). STM32CubeProgrammer
  has no path (no CMSIS-DAP support found, and no H7 USB for DFU), so `make flash` moves to OpenOCD or probe-rs;
  CubeIDE works through an external OpenOCD GDB server.
- **Recovery**: on the S3 the OTG app takes the shared PHY away from USB-Serial/JTAG; a crashed OTG
  app needs GPIO0 held low plus an EN pulse. The board therefore needs a reachable **GPIO0 pad or
  button and an EN pad or button** (non-OTG study Q2.3).
- **Placement**: the rear-left corner, antenna beyond the rear edge; see
  [ESP32 form factor](#esp32-form-factor). Espressif asks for the antenna at a board edge, 15 mm
  clearance in all directions, not mid-board, away from the bridges and the USB/UART lines
  ([ESP layout]).
- **Removed**: P1 (SWD header), U5 (SWD_VDD OR-ing), the SBU chain (Q7, F1, D13, C77, C78, R50-R55,
  U7), and the HM-19 board on the USB-C (the `bluetooth` board). The ESP takes about 316 mm², roughly
  offset by what goes (ESP study Q6).

### ESP32 form factor

**Solder the module, not the bare chip: ESP32-S3-MINI-1-N8 in the rear-left corner, its PCB antenna
overhanging the rear edge by 5.05 mm.** The module is a shielded, certified radio that needs no RF
design; the price is mechanical (a 5 mm overhang, M1 moved, the left drive block 1 mm shorter). The
SiP and chip-down options fit the same corner without mechanical change, but their antenna match
needs a VNA on the finished robot, and they have no shield and no certificate (form-factor study).

| | S3-MINI-1-N8 | S3-MINI-1U-N8 | S3-WROOM-1 / -1U | S3-PICO-1-N8R2 (SiP) | ESP32-S3FN8 chip-down | C5-MINI-1-N4 / -1U |
|---|---|---|---|---|---|---|
| Size (mm) | 15.4 × 20.5 × 2.4, antenna 5.05 | 15.4 × 15.4 × 2.4 + W.FL/MHF III | 18 × 25.5 × 3.1 / 18 × 19.2 × 3.2 | LGA56 7 × 7 × 0.96 | QFN56 7 × 7 × 0.85 | 15.4 × 21.3 × 2.4 (antenna 5.85) / 15.4 × 15.4 |
| Inside | chip, 40 MHz crystal, flash, match, antenna, shield | same, connector | same | crystal, 8 MB flash, 2 MB PSRAM, decoupling, chip-side match | 8 MB flash | as MINI-1 |
| Board adds | 10 µF + 0.1 µF, EN RC | + antenna, cable | as MINI-1 | 22 µF + 0.1 µF, EN RC, antenna π (values TBD), 50 Ω line, antenna | crystal ±10 ppm + 24 nH + load caps, 0201 CLC match + stub, antenna + CLC, about 20 passives | as MINI-1 |
| Board area | 238 mm² + 78 mm² overhang (about 430 mm² with the antenna inside and Espressif's cut-out) | 237 mm² | 459 / 346 mm² | about 110 mm² + antenna keep-out | about 170 mm² + antenna keep-out | 328 / 237 mm² |
| GPIO (need about 17) | 39 | 39 | 36 | about 38 | 45 less flash pins | 22 |
| RF certificates | FCC 2AC7Z-ESPS3MINI1, CE, IC, MIC, SRRC, KC | CE, SRRC | FCC, CE, IC, MIC, SRRC, KC | none | none | FCC 2AC7Z-ESPC5MINI1, CE / none |
| JLCPCB (all Extended), stock, qty 1 | C2913206, 3754, $4.72 | C2980299, 1139, $4.89 | C2913198, 555, $4.91 / C2980297, 1176, $4.81 | C7558093, 0, $5.01 | C2913196, 1959, $3.34 + parts | C50346179, 0, $12.54 / not listed |
| Fits this board | rear-left, with a 5 mm overhang | rear-left, no overhang | **no** (18 mm wide) | rear-left, no change | rear-left, no change | as MINI-1 / -1U |
| Design effort, RF risk | lowest; chassis detuning only | low + antenna mount; antenna can sit in open air | – | medium; untuned match | high; crystal and match too | as MINI-1; dual band |

Sources: [ESP32-S3-MINI-1] Table 1-1, Figures 10-1/10-2; [ESP32-S3-WROOM-1] Tables 1-1/1-2, Figure
10-1; [ESP32-S3-PICO-1] Overview, Figures 4-1, 5-1, 6-1; [ESP32-S3] Table 1-1, Figure 7-1;
[ESP32-C5-MINI-1] Tables 1-1/1-2, Figure 10-1; [ESP schematic] crystal and RF sections; Espressif
certificate listing; JLCPCB parts library, read 2026-10-15. There is no C5 SiP with an integrated
crystal; a chip-down C5 is a dual-band RF design.

**Placement on this board** (main-board-fixes layout and MicrasHardware, projected;
[calculations/esp/placement.png](calculations/esp/placement.png)):

```text
          front: wall sensors + H7 (analog front end; 7 mm between W2 and W3)
         ┌───────────────────────┐
         │ C2      fan Ø27 ring  │   sides: wheels, drive motors 4.6 mm from the edge,
  wheel  │▒▒▒▒ drive blocks ▒▒▒▒▒│   battery cells overhanging 27-38 mm above;
         │▒▒▒▒ (parts ≤ 1.5 mm)▒▒│   only a PICO-1 or a QFN fits under the blocks
         │[ESP] M1  U2   J1  SW4 │   rear zone x < −23: open sky, ≥ 18 mm from motors and battery
         └═══────────────────────┘
          ═══ MINI-1 antenna, x −41.55…−36.5, y 9.0…24.4
```

- The robot has no top cover, so height never decides; the drive blocks (parts ≤ 1.5 mm over
  x −21.9…13.5) and the fan's Ø27 part-free ring do. No edge meets Espressif's 15 mm keep-out in
  place: the nose is the wall-sensor front end, the sides carry the wheels, motors and battery.
- **Rear-left corner** (the L6205D's, freed): metal-free for 18 mm, open sky, 5-6 mm from the USB-C.
  A MINI-1 body at x −36.5…−21.05, y 9.0…24.4 with the antenna beyond the rear edge (feed end at the
  corner, Espressif's recommended placement) needs M1 moved (2.8 mm overlap), the left drive block's
  rear face ≥ 1 mm forward of x = −21.9, and the corner squared (0.4 mm). The in-place turning
  envelope does not grow: 48.2 mm against the nose's 55.2 mm. The MINI-1U fits the same rectangle
  without the overhang; a PICO-1 plus chip antenna fits beside M1 with no change at all.
- **Left side ahead of the wheel** (P1/U5, freed): no module fits between the edge and the fan ring
  (11.5 mm deep); a PICO-1 with a chip antenna does (C2 in the plot), 8-10 mm from the W1 can.
- Keep the DRV8874 bridges out of the rear-left corner; WROOM modules fit nowhere (18 mm wide).

If the 5 mm overhang is rejected, the MINI-1U-N8 in the same corner with an antenna in the open rear
zone is the fallback; the PICO-1 only if someone can tune the antenna with a VNA. The C5 alternative
of [Q2](#q2-the-compromise-of-an-esp32-without-usb-otg) is a C5-MINI-1 in the same place, but it is
not stocked at JLCPCB today and its -1U has no certificate. The antenna test in
[Bench measurements](#bench-measurements-before-committing) decides between the MINI-1 and the MINI-1U.

### H7 pin budget

The H725 VFQFPN68 has two unconnected pins, PC15 (reduced ±3 mA drive) and PH1. The ESP costs no new
pin: it takes SWD (PA13/PA14), NRST, optionally BOOT0, and UART4 (PA11/PA12).

| Need | Pins | Resolution |
|---|---|---|
| ESP ↔ H7 flow control | 1 | PH1. ESP → H7 attention travels in-band over UART4 (inference) |
| Motor fault | 1 | PC15, both DRV8874 nFAULT wire-ORed (open drain, slow pin is fine; IMODE = GND so it does not chatter) |
| Current inputs on fast ADC channels | 2, by swapping | No direct channel is free. Move two wall sensors onto PC0/PC1 and the currents onto two of PA6/PB1/PC4: ADC1 for one current, ADC2 for the other. Pin-neutral; **TODO**: check in CubeMX. If it fails, slow channels still work with one conversion per centre |
| IPROPI | 0 | ITRIP only; the DNP 0 Ω prototype option shares the INA241's ADC net |
| INA228 SDA, SCL, ALERT | 0 on the H7 | ESP GPIOs |
| ESP VBUS detect | 0 on the H7 | its own divider on an ESP GPIO; the ESP reports USB power over UART4, so the H7 has no VBUS divider |
| Emitter set-point DAC | 1 | PA5 (DAC1_OUT2; PA4, DAC1_OUT1, carries Wall_Sensor_3). The battery divider moves to PC5 (ADC12_INP8, slow channel, DS13311 Table 85) and Switch_0 to PH0 (a plain FT input with the internal pull-up; no HSE crystal) |

An LQFP100 package (STM32H725VG) would relieve this budget and bring out VREF+, but its I/O and
footprint are not analysed.

## Parts

New or changed parts; JLC numbers and prices as queried on 2026-10-15 (stock is not blocking).

| Block | Part | Change | Key data | Source |
|---|---|---|---|---|
| Motors | maxon DCX 10 L 4.5 V × 2 | new; order code **TODO**; length against MicrasHardware `Motor.body_l` = 20 **TODO** | 2.9 Ω, 45 µH, kt 3.52 mNm/A, 0.648 A cont., 14,300 rpm, 11 g | [maxon p100] |
| Battery | 4S 150-300 mAh: four 1S 300 mAh cells (~28 g) or a 4S pack (22-36 g) | new; IR unmeasured | non-HV charging keeps the TPS2121 option open | drivetrain study §4-§5 |
| Battery switch | HSBB3072 (Q6) | keep | 30 V VDS, VGS = VBAT/2 | repo `components/huashuo/HSBB3072` |
| Reverse polarity, TVS | none (the connector keys the polarity); TVS SMAJ18A at J1 recommended, not fitted | owner's decision | VR 18 V, VBR 20-22.1 V, VC 29.2 V at 13.7 A; C148219 $0.11 | [VBAT overvoltage](#power-tree) |
| Power path | 40 V 1 A Schottky + AO3401A-class P-FET, or 2 × LM74700-Q1/MX74700T + N-FETs; TPS2121 with non-HV cells only | replaces the TPS2121 mux for HV cells | B5819W C8598 basic; LM74700QDDFRQ1 C3236229 $1.32; MX74700T C22468156 $0.41 | power-tree study §8 |
| Digital 3V3 | L6981C33 | keep | 1.5 A, 3.5-38 V, 30.5-145 µF window; C5268096 shows 1 in stock | [L6981] |
| Analog 3V3_A | ADP7142ACPZN3.3 (LFCSP) or TPS7A4901DGNR, behind 22 Ω + 10 µF | new | 40 V / 36 V, 11 / 15.4 µVrms; C659360 $2.88 / C16430 $1.26 | ADP7142 Rev H; [TPS7A49] |
| Analog 3V3_A, alternative | TPS560430X3FDBVR + 12 µH + damped LC | documented alternative | forced PWM 1.1 MHz, 4-36 V; C2071721 $1.19 | [TPS560430] |
| Motor drivers | DRV8874PWPR × 2 | replaces L6205D | 0.2 Ω HS+LS, 6 A peak, OCP 6 A min, 100 kHz, LS IPROPI 450 µA/A; C1855818, 25,990 stock, $1.01 / $0.66 | [DRV8874] |
| Motor driver, alternative | DRV8262DDWR × 1 | if > 6 A or the stall margin proves short | 0.1 Ω, 8 A dual peak, 60 V; C22427252, $9.77 / $6.98 | [DRV8262] |
| Motor chokes | XAL7070-473MEC 47 µH shielded (Isat 4.2 A, 97 mΩ max, 7.2 × 7.5 × 7.0 mm, 1.9-2.3 g) × 2, with 0 Ω option; fan: XGL5030-472MEC 4.7 µH (5.3 × 5.5 × 3.1 mm) | new footprints; height against the chassis clearance **TODO** | 0.05-0.12 W ripple heat at 100 kHz | drivetrain study §5 |
| Motor shunts | WSK2512R0100FEA (±1 %, C3985410, 4955 stock) or WSK2512R0100DEA (±0.5 %, C1517461, 0 stock) × 2 | replaces the 40 mΩ 2-pad 2512 | 4-terminal, ±35 ppm/K | [WSK2512] |
| Current amplifiers | INA241A2IDGKR × 2 | replaces TSC2020 | ±15 µV, ±0.01 %, 1 µs hold, ≤ 125 kHz PWM; C36752877, 2 stock, $5.71-4.08 | [INA241] |
| Battery monitor | INA228 + 2 mΩ 4-terminal shunt (WSK25122L000FEA) | new | ±20.48 A, ±1 µV, ±0.05 % | [INA228] |
| Bridge decoupling | 4 × 10 µF X7R 50 V 1206 + 2 × CL32B106KBJNNNE 10 µF X7R 50 V 1210 per bridge, no electrolytic | new | 285 mV pp worst case at 100 kHz; C138687 $0.33 | calculations/power_tree/vbat_bulk.py |
| Fan driver | STSPIN958 (keep); R31 20-25 mΩ 1206; RSR 1-2.2 kΩ; C36 ≥ 25 V; C34/C35 50 V; choke footprint 4.7-10 µH | modify | 5.05-58 V, 500 kHz, 280 ns min pulse; C20033901, 0 stock, $4.23 | [STSPIN958], fan study §5 |
| Fan fallback | TPS28225DR + 2 × CSD17578Q3A + TLV3201/TLV7031 + shunt | only above ~3 A | TPS28225DR C52897 $0.85; CSD17578Q3A $0.42 | fan study §3 |
| Emitter drive | TLV9001 + AO3400A + 1.2 Ω 0.1 % sense; 3.3 Ω per emitter; AC-coupled selector gates (220 nF, 22 kΩ, 1N4148WS) | new | 175 mA (DAC set-point on PA5, 223 mA full scale) | power-tree study §6; emitter/emitter_sink.py |
| Status LEDs | WS2812C-2020-V6 × 2 | replaces WS2815C-2020 (needs 9.5-13.5 V) | 3.3-5.3 V, 5 mA per colour; C55109522 | [WS2812C-2020-V6] |
| Radio / probe | ESP32-S3-MINI-1-N8, rear-left corner, antenna beyond the rear edge (MINI-1U-N8 fallback) | replaces HM-19 and P1 | 355 mA TX peak, ≥ 0.5 A supply; C2913206, 3754 stock, $4.72 (-1U C2980299, $4.89) | [ESP32-S3-MINI-1], [ESP32 form factor](#esp32-form-factor) |
| Switches, divider | SW4 → SK-12D29-G060 (DC 24 V 1 A, 6.0 mm lever, new footprint); R44/R45 100k/20k | modify | C2848877, 531 stock, $0.13; firmware constant 6.0 | drivetrain study §4; `components/g-switch/SK-12D29-G060` |
| VDDA filter | FB1 → 0 Ω or ≤ 50 mΩ bead | modify | – | power-tree study §9 |
| Removed | TPS61178 + 1 µH + 7 capacitors; L6205D and its parts; 2 × TSC2020; 2 × 40 mΩ shunts; P1; U5; SBU chain (Q7, F1, D13, C77, C78, R50-R55, U7); WS2815C D1/D2 | remove | – | – |

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
  today's R32/R33 + IC3/IC4 + C67/C68 (drivers/area.py, area_board.py). Two ADC pins either way.
- **If only feed-forward, limiting and stall detection are wanted**, a calibrated DRV8874 IPROPI,
  centre-sampled with the sign inference, is good enough and saves about $10 and the in-line
  common-mode risk (the in-line node swings 0 ↔ 16.8 V at 90-120 V/µs). The DRV8262's IPROPI is not a
  measurement: unspecified below 0.5-0.8 A, no drift data.

### Q2. The compromise of an ESP32 without USB OTG

**Short answer: without OTG the ESP cannot be a standard USB debug probe, and the one cable gives one
serial port instead of a probe + console + drive; keep the ESP32-S3, which has OTG.** The chips
without OTG (C3, C5, C6) have only the fixed-function USB-Serial/JTAG (USJ): one CDC serial port with
fixed descriptors (`303a:1001`) plus a JTAG interface for the ESP's own CPU (non-OTG study Q2.1).

What is lost without OTG (non-OTG study Q2.5):
1. **No standard USB probe.** CMSIS-DAP v2 needs its own vendor bulk interface and v1 needs HID; USJ
   presents neither. Wired H7 debugging needs either the debugger to own the serial port (a Black
   Magic remote-protocol or GDB server on the ESP) or a host bridge program (a COBS-framed multiplex
   re-exported as localhost TCP ports). Neither path has been demonstrated end-to-end on an ESP over
   USJ. USJ's JTAG bridge to an external target is JTAG-only, and the H7's JTAG pins (PA15, PB3, PB4)
   carry encoder and IMU lines.
2. **One serial port.** The H7 console, the probe and the ESP log share one CDC; using two at once
   needs the host mux. On the S3 they are separate USB interfaces with stock tools.
3. **No mass storage, WebUSB or custom descriptors.** Drag-and-drop becomes an HTTP or Web Serial
   upload.
4. **Unknown wired throughput.** USJ has 64-byte single-buffered CDC endpoints and no published
   sustained rate; whether it carries the 256 kB/s telemetry with margin is unmeasured. The S3 OTG
   figures are "only expected to reach 6.4 Mbps" for TinyUSB (about 0.8 MB/s) and "500 KB/s at the
   maximum currently" ([ESP-FAQ USB]).

What a non-OTG chip gives back:
1. **Everything over Wi-Fi is the same on every chip**: CMSIS-DAP-TCP for OpenOCD, BMP-TCP for
   probe-rs and GDB, the telemetry relay and OTA H7 flashing.
2. **A USB port that ESP firmware cannot brick**, with automatic esptool reset and download and the
   ESP's own JTAG debugging on the same cable. On the S3 a crashed OTG app leaves the PC with nothing
   until someone holds GPIO0 and resets.
3. **On C5/C6, readable DTR/RTS and line coding**, for host-driven mode switching and a scripted H7
   reset; the C3 resets on RTS=1/DTR=0 and cannot disable it.
4. **C5 only: 5 GHz Wi-Fi 6** for crowded 2.4 GHz venues, at a 426 mA TX peak (≥ 0.6 A supply).

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

The UART to the H7 is identical on all four (5 Mbaud, 128-byte FIFO, UHCI DMA). A C5-MINI-1 is the
choice only if the team accepts a host bridge program (or treats Wi-Fi as the primary debug path),
a bench test shows USJ sustains well over 256 kB/s toward the PC, and 5 GHz matters at contests. The
C6 offers nothing over the S3 here; the C3 is the weakest.

### Q3. The fan driver

**Short answer: yes, the STSPIN958 stays, and it is the best integrated option, but reconfigured for a
drone motor on 4S: 400 kHz, a 20-25 mΩ shunt, REF at 1.5 × the running current, a faster slew rate,
a ≥ 25 V C36 and a choke footprint.** Above about 3 A continuous a discrete synchronous half-bridge
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
alternative for a motor needing more than 6 A or if the bench shows the stall margin is short.

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

A choke in series with a wheel motor (47 µH) or the fan (4.7-10 µH) trades PWM ripple against these
costs. Each footprint has a 0 Ω option, and the choke is fitted only if the measured motor inductance
requires it.

- **Size, height and mass.** A shielded part rated for the current is the largest passive near each
  motor and adds mass to a 76 g robot. The wheel choke is the XAL7070-473 (7.2 × 7.5 × 7.0 mm,
  1.9-2.3 g each), the fan's the XGL5030-472 (5.3 × 5.5 × 3.1 mm); their height against the chassis
  clearance is **TODO**.
- **Saturation current.** Isat must exceed the current limit plus the overshoot during the
  driver's blanking: ITRIP 2.5-3 A plus 0.41-0.62 A (current_sense/q1_sampling.py), so ≈ 3.6 A at a
  3 A ITRIP (computed); for the fan, Isat ≥ I_peak (3-5 A). A saturated choke loses its inductance
  exactly when the current is highest; in a fault the driver OCP (DRV8874 6 A min) still trips
  (inference).
- **DCR and core loss.** The DCR adds to the 2.9 Ω loop: each 100 mΩ costs 0.1 W at 1 A rms
  and adds 3.4 % to the loop resistance (computed). Core loss is small at 0.46-0.69 A pp ripple, but not
  quantified until a part is chosen (**TODO**).
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
  may arc more (inference); check on the bench.

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
| ESP32-C3/C6, or P4 | C3/C6: no OTG and nothing gained over the S3; P4: no radio | [Q2](#q2-the-compromise-of-an-esp32-without-usb-otg) |
| ESP ↔ H7 data over USB | One OTG controller cannot be host to the H7 and device to the PC at once; needs two switches and two USB stacks for about 2× the UART rate | ESP study Q3 |
| A USB2422 hub | Occupies PA11/PA12 as USB permanently, losing the UART4 link | ESP study Q3 |
| H7 flashing through the system bootloader UART/SPI | Its pins carry motors, the buzzer and the sensor bus; PA10 is Motors_Enable | [AN2606] Table 133 |
| A/B images in H7 flash | One 1 MB bank | [RM0468] |
| INA228 directly on the H7 | No free I²C pins | pin budget |

## Bench measurements before committing

On the current board (priority 1 first):

| Priority | Measurement | Decides | Method |
|---|---|---|---|
| 1 | Current sensor with the post-`bd1eedd` firmware (micras-lib, 2026-10-05: before it the compiler folded the DMA buffer and `get_current_raw` read a constant −2.0625 A) | Whether the in-line architecture is sound, and the size of each analog error | current-sensing study §1 steps 1-10: raw ADC at rest against a DMM at TSC OUT (1.65 V ± 7 mV); pin check; DC gain at both common modes into a 10-20 Ω power resistor; Kelvin check; scope the PWM artefact at 10-90 % duty both ways; ±40 % torque sweep; ADC2 triggered from the timer; rail-noise A/B; linearity calibration |
| 1 | Motor R and L at 1-10 kHz and at 100 kHz (the current 1020, and a DCX 10 L sample) | Whether the 47 µH chokes are fitted | LCR meter; then `drivetrain/ripple_exact.py` with the measured L |
| 1 | Candidate fan motor R, L and stall current | Fan choke fit, REF setting, STSPIN958 or the discrete half-bridge | LCR meter (or ΔIpp at a known f and D) plus a locked-rotor test |
| 2 | INA241A2 swapped onto IC3/IC4 | Whether the common-mode artefact disappears | Bridge pin 4 to pin 3, repeat steps 5-7 |
| 2 | 3V3 and VDDA droop | Validates the droop model and shows the LCM switching | AC-coupled scope triggered on an emitter gate; ADC standard deviation with emitters on/off and ADC1 running/stopped |
| 3 | 4S pack IR and sag at about 5 A | Pack choice and duty feed-forward range | Pulse load |
| 4 | Run profile (time at peak torque), downforce at the new fan voltage, tyre µ, gear efficiency | Thermal budget, ITRIP and RMS limits | Firmware logging, scale |

On breakouts and dev boards:

| Priority | Measurement | Decides | Method |
|---|---|---|---|
| 2 | DRV8874 breakout with the DCX 10 L at 16.8 V: ripple, IPROPI against a shunt (calibration stability, drift, noise), case temperature, VBAT ripple at 100 kHz | Driver choice, the IPROPI-only fallback, the analog LDO input filter | Current probe at 100 kHz, acceleration and reversal profiles |
| 3 | INA241 stability with R_iso + C_f above 1 nF | ADC input filter values | Scope at the MCU pin |
| 3 | ESP32-S3: SWD flash throughput to an H7, NRST sequencing, 3V3 droop under TX, antenna inside the chassis (DevKitM-1 at the rear-left corner, antenna overhanging, battery and motors fitted and running: RSSI and TCP at 1-20 m, robot turned in 45° steps; keep the MINI-1 if TCP ≥ 4 Mbit/s everywhere, else the MINI-1U), crash-loop recovery (PHY routing after a core reset) | Probe and OTA viability, recovery pads | ESP32-S3-USB-Bridge or a MINI-1 breakout |
| 4 | WS2812C-2020-V6 colour at 3.2 V | LED part or the GPIO-RGB fallback | Bench supply |
| 4 | USJ CDC sustained throughput (only if a C5 is considered) | S3 or C5 | C5/C6 devkit, `usb_serial_jtag_write_bytes()` loop, ≥ 8 kB TX ring, 60 s average |

On the first prototype: VDDA at the pin with the LDO on (AC-coupled, and the ADC standard deviation
per slot against the board on a lab supply), the power path on VBUS hot-plug with the battery on and
battery hot-unplug with USB on (or a `pcb sim` bench first), and the INA241 against the DNP IPROPI
path on the same board.

## Open decisions

| Decision | Options | Notes |
|---|---|---|
| Gear and top speed | 4 m/s at G ≈ 4.27 / about 4.6 m/s at 3.7:1 / 6 m/s (needs 18.7 V at 4 N, above 4S) | – |
| Battery | four 1S cells / a 4S pack; HV or non-HV charging | Non-HV keeps the TPS2121 usable |
| Wheel chokes | fit 47 µH / 0 Ω | Decided by the measured L at 100 kHz |
| Motor driver | 2 × DRV8874 (recommended) / DRV8262 | DRV8262 if more than 6 A is needed or the stall margin is short |
| Current measurement | INA241A2 + WSK2512 (recommended) / calibrated DRV8874 IPROPI only | Q1; the prototype carries both |
| Fan motor and driver | STSPIN958 (≤ ~3 A continuous) / TPS28225 half-bridge (above) | Fan motor not chosen |
| Analog LDO | ADP7142ACPZN3.3 (fixed) / TPS7A4901 (adjustable, cheaper) | Package thermal at ≈ 0.33 W |
| Power path | Schottky + P-FET / 2 × LM74700-Q1 / TPS2121 (non-HV only) | – |
| TVS on the battery input | SMAJ18A at J1 (recommended) / none, with a firmware VBAT limit on braking | Reverse polarity: the keyed connector only (owner) |
| ESP form factor | MINI-1-N8 in the rear-left corner, antenna 5 mm beyond the rear edge (recommended) / MINI-1U-N8 with an external antenna / PICO-1 + chip antenna | Overhang, M1 and the drive block against antenna tuning; antenna bench test |
| ESP chip | S3 (recommended) / C5 under the Q2 conditions | – |
| Toolchain | CMSIS-DAP through OpenOCD (master) or probe-rs | ST-Link and CubeProgrammer workflows are lost |
| Backstops | SWD test pads on PA13/PA14/NRST/GND; SW5 (BOOT0) and SW3 (NRST) | – |
| Pins | the wall/current ADC swap; or LQFP100 | CubeMX check |
| Competition | a radio-off contest mode | Contest rules on active radios not checked |

## Gaps and TODOs

- **Motors**: DCX 10 L order code; length against `Motor.body_l` = 20; effective inductance at
  100 kHz (maxon's 0.3-0.8 factor is generic); commutator life at 4-5 × IN.
- **Chokes**: XAL7070-473 (wheels) and XGL5030-472 (fan) chosen; their height against the chassis
  and their core loss are open.
- **Drivers**: neither TI part specifies a minimum output pulse; DRV8262 IPROPI dynamics and its
  "rated current" are undefined; no mirror noise, bandwidth, VM dependence or calibration-stability
  data for either; the DRV8874 calibrated row rests on one typical curve; the L6205 edge time and
  transient Zth are not published.
- **Current sensing**: the INA241's settling after a 16.8 V edge at 3.3 V supply is characterised only
  at VS = 5 V, VCM = 48 V; WSK2512 thermal EMF taken from the WSK1206 document; the friction share of
  the cruise current is unknown (log it).
- **Analog rail**: the EN thresholds and the board-level thermal limit of the ADP7142/TPS7A4901 at
  ≈ 0.33 W; the LDO temperature drift (the calibrated ±0.2 % VDDA term is an assumption); no vendor
  model, inductor coupling or PCB parasitics in the simulation; VDDA current with ADC1 and ADC2
  running on VFQFPN68 (DS13311 Table 84 is for BGA, one ADC); the arena-light phototransistor current.
- **Power path**: no 40 V Schottky checked for leakage and VF; the AO3401A VGS rating not re-read; the
  Type-C Rp advertisement not used for a higher USB budget.
- **Battery input**: the TVS decision; B02B-PASK connector rating at about 5 A; no published IR for
  4S 200-300 mAh packs; SW4's ON position (the SK-12D29 drawing does not say which lever position
  joins which pin); the HSBB3072 model in vbat_bulk.py is fitted to its datasheet table, not measured.
- **Fan**: no drone motor publishes inductance (the 1-12 µH range is inferred); NFP figures are from
  search snippets; STSPIN958 supply current, dead time and RDS(on) temperature curve unpublished; the
  discrete limiter is not a validated design; its 4.5-8.8 V gate supply is not designed.
- **ESP**: no ESP-IDF STM32H7 SWD flash routine exists (port from OpenOCD, pyOCD or Black Magic);
  no measured ESP-to-H7 SWD throughput; the MINI-1 antenna's feed end (read from
  the drawing; confirm on Espressif's footprint); the chip antennas' keep-out (option C); the MINI-1U's
  FCC/IC status and the Anatel status of the MINI-1 modules; whether
  the S3 bootloader restores the PHY routing after a core reset; contest radio rules; an RDP Level 2
  mistake locks out SWD for any probe.
- **Emitter sink**: the modelled step response (behavioural TLV9001 and AO3400A models) needs a
  bench confirmation across the 1.2 Ω; the AO3400A's VGS at 175 mA and its VGS(th) when cold are not
  in its datasheet, so the AC-coupled selectors' margin (0.25 V at -40 °C with an assumed
  VGS(th) + 0.3 V and -4 mV/K) needs Figure 2 or a measurement and a cold check; the DAC output
  resistance's drift is unknown (a gain the calibration takes in).
- **Pins**: the fast-ADC swap and the TIM3-on-ITR interleave are unverified in CubeMX; the PC7/PC9
  TIM8 alternate functions were not checked.

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
| [drivetrain/sim.py](calculations/drivetrain/sim.py), [extra.py](calculations/drivetrain/extra.py), [duty.py](calculations/drivetrain/duty.py), [vreq.py](calculations/drivetrain/vreq.py) | `sim_out.txt`, `extra_out.txt`, `duty_out.txt`, `vreq_out.txt` | Traction limit, acceleration, thermal run budget, burst times, figure of merit, bus voltage needed |
| [drivetrain/power_stage_calc.py](calculations/drivetrain/power_stage_calc.py) | `power_stage_calc_out.txt` | Bridge loss, ripple with chokes, input-capacitor ripple, battery switch |
| [current_sense/budget.py](calculations/current_sense/budget.py) | `budget_out.txt` | Shunt range, TSC2020 artefact windows, INA241 error budget, INA228 scaling |
| [current_sense/q1_sampling.py](calculations/current_sense/q1_sampling.py) | `q1_sampling_out.txt` | What each sensor sees over a period, bias of each mean estimate, ITRIP overshoot |
| [current_sense/q1_error_table.py](calculations/current_sense/q1_error_table.py) | `q1_error_table_out.txt` | Q1 error budgets at 0.1-3 A |
| [drivers/q4_drivers.py](calculations/drivers/q4_drivers.py) | `q4_drivers_out.txt` | Q4 losses, junction rise, stall and reversal currents, duty distortion |
| [drivers/area.py](calculations/drivers/area.py) | `area_out.txt` | Courtyard areas from the KiCad 10 library (reads `/usr/share/kicad/footprints/`) |
| [drivers/area_board.py](calculations/drivers/area_board.py) | `area_board_out.txt` | As-built areas; KiCad's `pcbnew` module, run with `boards/main/layout/main.kicad_pcb` as argument |
| [esp/placement.py](calculations/esp/placement.py) | `placement.png` | ESP candidate positions on the main-board-fixes layout with the MicrasHardware chassis projected; `pcbnew` and matplotlib, the board file as argument |
| [drivers/jlc_query.py](calculations/drivers/jlc_query.py) | `jlc_out.txt`, `../fan/jlc_fan_out.txt` | JLCPCB parts search by MPN (online; results dated 2026-10-15) |
| [fan/fan_driver_calc.py](calculations/fan/fan_driver_calc.py) | `fan_driver_calc_out.txt` | Q3: drone motor data, duty, stall current, ripple, driver losses |
| [supply3v3/sim3v3.py](calculations/supply3v3/sim3v3.py), [analyze.py](calculations/supply3v3/analyze.py) | `out/summary_meas.txt`, `out/summary_slots.txt` | Averaged 3V3/VDDA droop model during the emitter pulses (ngspice, seconds) |
| [power_tree/sim_power_tree.py](calculations/power_tree/sim_power_tree.py), [analyze.py](calculations/power_tree/analyze.py) | `out/summary.txt` | Switching-level analog-rail model, cases A-F (ngspice, about 5 min per case, 6 in parallel) |
| [power_tree/calc_power_tree.py](calculations/power_tree/calc_power_tree.py) | `out/calc_power_tree.txt` | Analog-rail load, LDO heat, emitter sink, USB budget, ADC noise, LC filter |
| [emitter/emitter_sink.py](calculations/emitter/emitter_sink.py) | `emitter_sink_out.txt` | main2's emitter sink with the DAC set-point and AC-coupled selectors: worst-case current and margin, turn-off with a pin held high, pulse start against the DAC timing (ngspice, about 1 min) |
| [power_tree/vbat_bulk.py](calculations/power_tree/vbat_bulk.py) | `vbat_bulk_out.txt` | VBAT capacitor options (MLCC DC bias, 100 kHz ripple, source impedance), hot plug and Q6 switching, regeneration with the pack pulled, TVS clamp (ngspice, about 5 min) |

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
| ADP7142 Rev H, LM74700-Q1 SNOSD17G | read from mirrors (analog.com unreachable); secondary |
| [WS2812C-2020-V6] | [WS2812C-2020-V6 (LCSC C55109522)](https://datasheet.lcsc.com/datasheet/pdf/8c7f104c99e52e4adb687ae84e594e95.pdf?productCode=C55109522); [WS2812B-2020-V6 (C52917434)](https://datasheet.lcsc.com/datasheet/pdf/a29e59ba4bc7e47e236b4d50b6c26345.pdf?productCode=C52917434) |
| [ESP32-S3] | [Espressif ESP32-S3 datasheet v2.2](https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf) |
| [ESP32-S3-MINI-1] | [ESP32-S3-MINI-1/1U datasheet v1.7](https://www.espressif.com/sites/default/files/documentation/esp32-s3-mini-1_mini-1u_datasheet_en.pdf) |
| [ESP32-S3-WROOM-1] | [ESP32-S3-WROOM-1/1U datasheet v1.8](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf) |
| [ESP32-S3-PICO-1] | [ESP32-S3-PICO-1 datasheet v1.2](https://www.espressif.com/sites/default/files/documentation/esp32-s3-pico-1_datasheet_en.pdf) |
| [ESP32-C5-MINI-1] | [ESP32-C5-MINI-1/1U datasheet v1.4](https://documentation.espressif.com/esp32-c5-mini-1_datasheet_en.pdf); [C5 datasheet v1.5](https://documentation.espressif.com/esp32-c5_datasheet_en.pdf); [C5-WROOM-1/1U v1.3](https://documentation.espressif.com/esp32-c5-wroom-1_wroom-1u_datasheet_en.pdf) |
| [ESP layout] | [ESP32-S3 hardware design guidelines, PCB layout](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html) |
| [ESP schematic] | [ESP32-S3 hardware design guidelines, schematic checklist](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html) |
| ESP certificates | [Espressif certificates](https://www.espressif.com/en/support/documents/certificates) |
| [ESP-FAQ USB] | [ESP-FAQ, USB](https://docs.espressif.com/projects/esp-faq/en/latest/software-framework/peripherals/usb.html) |
| [ESP-IDF Wi-Fi performance] | [ESP-IDF Wi-Fi performance, ESP32-S3](https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32s3/api-guides/wifi-driver/wifi-performance-and-power-save.html) |
| [SK-12D29] | [G-Switch SK-12D29-GXXX drawing (2016-05-29), LCSC C2848877](https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2108301530_G-Switch-SK-12D29-G060_C2848877.pdf) |
| [Samsung MLCC] | [Samsung product pages, DC-bias and ripple-current curves, e.g. CL32B106KBJNNN](https://product.samsungsem.com/mlcc/CL32B106KBJNNN.do) |
| [Panasonic TQC] | [Panasonic POSCAP TQC series (2023-06-30), LCSC C3018702](https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2401241128_PANASONIC-25TQC100MD3_C3018702.pdf) |
| [Kyocera-AVX TCJ] | [Kyocera-AVX TCJ series, TDS-PTNO-0027 Rev 19](https://datasheets.kyocera-avx.com/TCJ.pdf) |
| [SMAJ] | [Littelfuse SMAJ series (rev. 11/20/15), LCSC C148219](https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2304140030_Littelfuse-SMAJ18A_C148219.pdf) |
| [SMF] | [Littelfuse SMF series, LCSC C409420](https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/1912111437_Littelfuse-SMF18A_C409420.pdf) |
| Probe firmware | [espressif/esp-usb-bridge](https://github.com/espressif/esp-usb-bridge), [bkuschak/cmsis_dap_tcp_esp32](https://github.com/bkuschak/cmsis_dap_tcp_esp32), [windowsair/wireless-esp8266-dap](https://github.com/windowsair/wireless-esp8266-dap) |
| SFH 4550, AN5419, TPS28225, CSD17578Q3A, TLV9001 SBOS833R | vendor datasheets; no URL recorded |

[maxon p98]: https://www.maxongroup.com/medias/sys_master/root/9394600706078/Cataloge-Page-EN-98.pdf
[maxon p100]: https://www.maxongroup.com/medias/sys_master/root/9394600902686/Cataloge-Page-EN-100.pdf
[maxon key info]: https://people.ece.ubc.ca/leos/pdf/datasheets/Maxon/MaxonSpecs.pdf
[maxon chokes]: https://support.maxongroup.com/hc/fr/article_attachments/5266759938460
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
[WS2812C-2020-V6]: https://datasheet.lcsc.com/datasheet/pdf/8c7f104c99e52e4adb687ae84e594e95.pdf?productCode=C55109522
[ESP32-S3]: https://www.espressif.com/sites/default/files/documentation/esp32-s3_datasheet_en.pdf
[ESP32-S3-MINI-1]: https://www.espressif.com/sites/default/files/documentation/esp32-s3-mini-1_mini-1u_datasheet_en.pdf
[ESP32-S3-WROOM-1]: https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf
[ESP32-S3-PICO-1]: https://www.espressif.com/sites/default/files/documentation/esp32-s3-pico-1_datasheet_en.pdf
[ESP32-C5-MINI-1]: https://documentation.espressif.com/esp32-c5-mini-1_datasheet_en.pdf
[ESP layout]: https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html
[ESP schematic]: https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html
[ESP-FAQ USB]: https://docs.espressif.com/projects/esp-faq/en/latest/software-framework/peripherals/usb.html
[ESP-IDF Wi-Fi performance]: https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32s3/api-guides/wifi-driver/wifi-performance-and-power-save.html
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
- **EN/IN1** (1) to the timer PWM, **PH/IN2** (2) to the direction: right motor PA8/PA9
  (TIM1_CH1/CH2), left motor PC7/PC9 (TIM3_CH2/CH4).
- **nSLEEP** (3) to Motors_Enable (PA10) with R49 100 kΩ pull-down.
- **nFAULT** (4): pull-up to 3V3_D; both drivers wire-ORed to PC15 (Motors_nFault).
- **IPROPI** (6): RIPROPI 2.0 kΩ 1 % to GND (0.9 V/A); DNP 0402 0 Ω to the INA241's ADC net.
- **VREF** (5): divider from 3V3_D to 2.25-2.7 V for ITRIP 2.5-3 A (computed, VREF ≤ 3.6 V).
- **IMODE** (7) to GND: fixed off-time, auto-retry.
- **OUT1/OUT2** (8/10) to the motor through the WSK2512 shunt (A.3) and the choke footprint
  (47 µH or 0 Ω).
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
- **nSLEEP** (42) to Motors_Enable with R49. **nFAULT** (26): 10 kΩ to 3V3_D, to PC15.
- **IPROPI1/IPROPI2** (31/30): RIPROPI 4.3 kΩ 1 % (0.91 V/A) for ITRIP only.
- **VREF1/VREF2** (34/33): 2.28-2.73 V for 2.5-3 A (computed from ITRIP × 212 µA/A × 4.3 kΩ; VREF
  ≤ 3.3 V).
- **OUT1/OUT2** (4-6 / 7-9) right motor, **OUT3/OUT4** (17-19 / 14-16) left, each through its shunt
  and choke footprint. **RSVD** (32, 36) unconnected.
- Source: [DRV8262] Tables 4-1, 6-1 to 6-4, 6-7, 6-8, §5.5, §6.5.2, §6.11.3.

### A.3 Motor current sensing and battery monitor

| From | To | Part / value | Note |
|---|---|---|---|
| Driver OUT1 (switching node) | Rsh force pad 1 | WSK2512 10 mΩ 1 W 4-terminal | 5 mΩ if the motor peak exceeds 7 A |
| Rsh force pad 2 | choke footprint → motor connector | – | Power path wide, away from the sense pair |
| Rsh sense pad (driver side) | INA241 IN+ (pin 8) | trace pair, no vias | Positive output = current from bridge to motor |
| Rsh sense pad (motor side) | INA241 IN− (pin 1) | – | No input filter (any Rs adds gain error) |
| INA241A2IDGKR VS (pin 6) | 3V3_A | 100 nF X7R 0402 at pins 6-2 | – |
| GND (pin 2), NC (pin 4) | GND | – | Pin 4 "connect to ground" |
| REF1 (pin 7) | 3V3_A | optional 10 nF to GND | Mid-scale = VS/2, ratiometric with VDDA |
| REF2 (pin 3) | GND | – | – |
| OUT (pin 5) | R_iso 47-100 Ω → fast ADC pin (ADC1 one motor, ADC2 the other) | C_f 1-2.2 nF C0G at the MCU pin | Stability to verify; optional BAT54-class clamp; DNP 0 Ω from IPROPI on the same net |
| VBAT after Q6 → R_bat → system | INA228 IN+/IN− Kelvin; VBUS pin on the VBAT side | R_bat 2 mΩ 4-terminal 2512; VS = 3V3_D + 100 nF; A0/A1 straps | ADCRANGE = 1; SDA/SCL/ALERT to ESP GPIOs |

Source: [INA241] §6.5, §7.3.1.1, pin functions; [INA228]; current-sensing study §8.

### A.4 Power path, 3V3_A and emitter sink

- **VBAT → VSYS**: B5819W 40 V 1 A Schottky (C8598; about 12 µA reverse at 17 V, 25 °C, JCET
  B5817W-B5819W p2).
- **VBUS → VSYS**: 30 V P-FET (AO3401A class): drain VBUS, source VSYS, gate to VBAT through 10 kΩ
  with 1 MΩ to GND. The TPS2121 replaces both only with non-HV cells.
- **3V3_A**: VSYS → 22 Ω → 10 µF → ADP7142ACPZN3.3 (or TPS7A4901 with its FB divider, CNR/SS and
  CFF, ≥ 2.2 µF ceramic out); EN from 3V3_D. Place it away from the IMU and near the VDDA pin; run
  3V3_A as its own trace to VDDA, the INA241s and the sensor connectors.
- **VDDA pin**: 1 µF + 100 nF; FB1 → 0 Ω or a ≤ 50 mΩ bead.
- **Emitter sink**: op-amp (from 3V3_A) + N-FET (AO3400A) + 1.2 Ω 0.1 % ≤ 50 ppm/K sense
  (175 mA at 0.21 V); set-point from the DAC on PA5 (buffer off) through 200 kΩ / 20 kΩ, 0 when no
  emitter is selected; 1 kΩ sense → IN- with 1 nF C0G OUT → IN-, 200 kΩ 3V3_A → IN-; emitters from
  3V3_D through 3.3 Ω each, the AO3400A selectors with the main board's AC-coupled gates (220 Ω,
  220 nF, 22 kΩ to GND, 1N4148WS clamp).
- **LEDs**: WS2812C-2020-V6 × 2 on 3V3_D, 100 nF each, DIN from PC6.
- **Alternative 3V3_A**: TPS560430X3FDBVR, 12 µH, 22 µF / 10 V, CIN ≥ 4.7 µF / 50 V, CBOOT 100 nF,
  then 2.2 µH (≤ 50 mΩ, ≥ 100 mA, shielded) → 22 µF X7R/X5R 0805 ‖ (0.33 Ω + 47 µF); feedback at the
  buck output; no added series resistance. Calc: peaking +4 dB at 16 kHz, |Zout| ≤ 0.4 Ω, −22 / −41 /
  −64 dB at 100 kHz / 300 kHz / 1.1 MHz (power_tree/calc_power_tree.py §8).

Source: power-tree study §6-§9; [TPS560430] Table 1; [TPS7A49]; ADP7142 Rev H.

### A.5 Fan, STSPIN958

```text
VBAT ── VS (27-30) ── 2 × 470 nF 50 V 0603 at the pins, 2 × 10 µF 50 V 1206, the bridges' VBAT bulk
VSPUMP (4) ── C33 1 µF ── VBOOT (7) ; CP1 (5) ── C32 100 nF ── CP2 (6)
3V3_D ── VDD (13) ── C31 220 nF ; nSTBY (10) ── 3V3_D
MODE1 (20) = 3V3, MODE2 (19) = GND, MODE3 (18) = 3V3   (parallel half-bridge, PWM trimming, Table 8)
OFFSET (9) = GND
OUT1 (31, 32) + OUT2 (25, 26) ── FAN_OUT ──[ 4.7-10 µH / 0 Ω ]── M3 pin 1 (fan +)
LSS1 (1, 2) + LSS2 (23, 24)  ── FAN_LSS ── M3 pin 2 (fan −) ; R31 20-25 mΩ 1206 FAN_LSS → GND (Kelvin to the pins)
PWM2/PH (12) ── GND   (load OUT→LSS: low-side recirculation on limit, Fig. 11/14)
PWM1 (11)    ── Fan_PWM (PB15, TIM12_CH2, 400 kHz)
EN/nFAULT (14) ── Fan_Enable (PB14, driven open-drain) ; R27 39 kΩ to 3V3, C30 10 nF (Table 12)
TOFF (16)    ── Fan_TOFF (PB13): limiter-active flag in PWM trimming (section 5.6.2)
REF (15)     ── R28 / R29 divider from 3V3 → V_REF = I_peak · R31 · 10
SR (21)      ── 1-2.2 kΩ to GND
V1 (8), V2 (17) ── NC (or V1 → an ADC pin if one frees: 0.25 V/A with 25 mΩ)
GND (22), GNDPUMP (3), EPAD (33) ── GND
```

No capacitor across the fan motor. Pin numbers from the repo symbol
`components/st/STSPIN958/STSPIN958.kicad_sym` ([STSPIN958] Figure 2, Table 6).

### A.6 ESP32-S3-MINI-1

| ESP32-S3-MINI-1 | Net | Other end | Notes |
|---|---|---|---|
| 3V3 pins | 3V3_D | L6981C33 | 10 µF + 100 nF at the module, optional 22 µF; 3V3 total < 145 µF |
| GND pins, EPAD | GND | – | Dense GND vias near the antenna edge |
| EN (CHIP_PU) | ESP_EN | RC to 3V3/GND, pad or button | 10 kΩ / 1 µF ([ESP32-S3-MINI-1] section 9) |
| GPIO0 (strap) | ESP_BOOT | pad or button to GND | ROM download recovery; nothing else on it |
| GPIO19 / GPIO20 | USB_D− / USB_D+ | U6 USBLC6 → USB-C | 90 Ω differential, short, away from the antenna |
| GPIO12 (suggested) | SWCLK | H7 PA14 | SPI-capable pin for SWD acceleration |
| GPIO11 (suggested) | SWDIO | H7 PA13 | – |
| GPIO13 (suggested) | NRST | H7 NRST, SW3, C21 | Open-drain only |
| non-strap GPIO (optional) | BOOT0 | H7 BOOT0, R42 10 kΩ pull-down, SW5 | High-Z at ESP reset so R42 holds BOOT0 low |
| UART TX | PA11 (UART4_RX) | H7 | Up to 5 Mbaud |
| UART RX | PA12 (UART4_TX) | H7 | – |
| GPIO | flow control | H7 PH1 | Data-ready or credit line |
| GPIO + divider | ESP_VBUS_DET | VBUS via its own divider | USB power reported to the H7 over UART4 |
| 2 GPIO + 1 GPIO | I2C_SDA, I2C_SCL, BAT_ALERT | INA228 | – |

Avoid the strapping pins GPIO0, GPIO3, GPIO45, GPIO46 for the H7 control lines. Keep U6, SW3, the
ESP's VBUS divider (the H7 learns over UART4 that it runs from USB alone), and optional SWD pads on
PA13/PA14/NRST/GND as a backstop. Source: [ESP32-S3-MINI-1] Table 1-1, §3-4, Tables 6-2 to 6-5;
[ESP32-S3]; ESP study Q8.
