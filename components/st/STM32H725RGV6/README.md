# STM32H725RGV6

Arm Cortex-M7 MCU (STMicroelectronics STM32H725RGV6: 550 MHz, 1 MB flash, 564 KB RAM) in the
VFQFPN68 8x8 mm package. Bare part: decoupling, the SMPS inductor, reset/boot straps and clocks
belong to the board. Datasheet facts and citations are in the docstring of
[`STM32H725RGV6.zen`](STM32H725RGV6.zen).

```python
STM32H725RGV6 = Module("github.com/Team-Micras/MicrasPCB/components/st/STM32H725RGV6/STM32H725RGV6.zen")

STM32H725RGV6(
    name="IC1",
    VDD=V3V3, VDDSMPS=V3V3, VDDA=V3V3, VBAT=V3V3,
    VLXSMPS=SMPS_LX,
    VFBSMPS=VCORE, VCAP1=VCORE, VCAP2=VCORE, VCAP3=VCORE,
    GND=GND, NRST=NRST, BOOT0=BOOT0,
    PA13=SWDIO, PA14=SWCLK,
    PC15=NotConnected(),  # every GPIO io is required: pass NotConnected() for unused pins
    ...
)
```

## Pins

Pin numbers are the VFQFPN68 pads (DS13311 Rev 5, Table 8 and Figure 4).

| Pad | Pin | io | Symbol type |
|---|---|---|---|
| 1 | VBAT | `VBAT` (1.2-3.6 V) | power_in |
| 9, 22, 35, 51, 68 | VDD | `VDD` (1.62-3.6 V) | power_in |
| 6 | VDDSMPS | `VDDSMPS` (1.62-3.6 V, = VDD) | power_in |
| 16 | VDDA | `VDDA` (1.62-3.6 V with ADC/COMP) | power_in |
| 5 | VLXSMPS | `VLXSMPS` (SMPS switching node) | power_out |
| 7 | VFBSMPS | `VFBSMPS` (VCORE, 0.95-1.40 V) | power_out |
| 33, 49, 66 | VCAP1, VCAP2, VCAP3 | `VCAP1`, `VCAP2`, `VCAP3` (VCORE) | power_in |
| 8, 21, 34, 50, 67, 69 (exposed pad) | VSS | `GND` | power_in |
| 15 | VSSA | `GND` | power_in |
| 4 | VSSSMPS | `GND` | power_in |
| 12 | NRST | `NRST` | bidirectional |
| 63 | BOOT0 | `BOOT0` | input |
| 2, 3 | PC14-OSC32_IN, PC15-OSC32_OUT | `PC14`, `PC15` | bidirectional |
| 10, 11 | PH0-OSC_IN, PH1-OSC_OUT | `PH0`, `PH1` | bidirectional |
| 17-20, 23-26, 43-48, 52, 53 | PA0-PA15 | `PA0`-`PA15` | bidirectional |
| 29-32, 36-39, 58-62, 64, 65 | PB0-PB10, PB12-PB15 | `PB0`-`PB15` | bidirectional |
| 13, 14, 27, 28, 40-42, 54-56 | PC0, PC1, PC4-PC7, PC9-PC12 | `PC0`-`PC12` | bidirectional |
| 57 | PD2 | `PD2` | bidirectional |

GPIO pads in detail: PA0 17, PA1 18, PA2 19, PA3 20, PA4 23, PA5 24, PA6 25, PA7 26, PA8 43,
PA9 44, PA10 45, PA11 46, PA12 47, PA13 48 (SWDIO), PA14 52 (SWCLK), PA15 53; PB0 29, PB1 30,
PB2 31, PB3 58, PB4 59, PB5 60, PB6 61, PB7 62, PB8 64, PB9 65, PB10 32, PB12 36, PB13 37,
PB14 38, PB15 39; PC0 13, PC1 14, PC4 27, PC5 28, PC6 40, PC7 41, PC9 42, PC10 54, PC11 55,
PC12 56.

The datasheet calls all three core pins VCAP; the package numbers them VCAP1-3 in pad order, as
AN5419 Figure 5 does, so a board can decouple and check each one.

VDD33USB, VDD50USB, VDDLDO, VREF+/VREF- and PDR_ON have no VFQFPN68 pad. The VFQFPN68 variant
is SMPS only ("DCDC only", DS13311 page 1).

## Direct SMPS supply (AN5419 Rev 3, Figure 5 and Table 2)

With no LDO on this package, the core runs from the SMPS in the Direct SMPS supply. What a board
must provide, and what the board checks test:

- VDDSMPS on the same supply as VDD (1.62-3.6 V), with 10 uF at the pin (or 2 x 10 uF, 10 uF +
  100 nF, 10 uF + 4.7 uF).
- A 2.2 uH inductor (DCR 110 mOhm, Isat 1.7 A) from VLXSMPS to VCORE, as close as possible to
  VLXSMPS, and 2 x 10 uF (ESR 5 mOhm) on the VCORE side of the inductor. The 220 pF on VLXSMPS
  is for LQFP/BGA packages only.
- VFBSMPS on VCORE.
- VCAP1, VCAP2 and VCAP3 all on VCORE ("All VCAP connected together"), with 100 nF close to each
  VCAP pin.
- VDD: 100 nF per VDD pin plus one 4.7 uF. VDDA: 1 uF + 100 nF (may connect to VDD through a
  ferrite bead). VBAT: 1 uF + 100 nF, or tied to VDD when no backup supply is used.

The symbol types make KiCad ERC see this wiring: VFBSMPS (power_out) drives the VCORE net and
the VCAP pins (power_in) must be on it. A VCAP pin on its own net with only a capacitor is an
undriven power input.

## Footprint

`QFN-68-1EP_8x8mm_P0.4mm_EP6.5x6.5mm.kicad_mod` is the Altium MicrasLib footprint
`QFN40P800X800X100-69N-D` of the Micras main board, with its STEP (`STM32H725RGV6.stp`)
embedded. Pads 1-68 are 0.95 x 0.2 mm at 0.4 mm pitch, centred 3.95 mm from the package centre;
pad 69 is the 6.5 x 6.5 mm exposed pad, with a single full-size paste opening. The body
outline is on User.13 (Altium mechanical layer).
`pcb rectify check`: model transform OK.

Courtyard: an F.CrtYd rectangle around the body outline (User.13) and the pads, 0.25 mm, the
IPC-7351B nominal courtyard excess (KiCad Library Conventions F5.3).
