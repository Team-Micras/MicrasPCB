# LSM6DSV

6-axis IMU (STMicroelectronics LSM6DSV, ordered as LSM6DSVTR on tape and reel) in the LGA-14L
2.5 x 3.0 mm package, used in connection mode 1 or 2: primary SPI / I2C / MIPI I3C interface, no
auxiliary SPI. Bare part: the 100 nF capacitors on Vdd and Vdd_IO and the SDx/SCx straps belong to
the board. Datasheet facts and citations are in the docstring of [`LSM6DSV.zen`](LSM6DSV.zen).

```python
load("@stdlib/interfaces.zen", "Spi")
LSM6DSV = Module("github.com/Team-Micras/MicrasPCB/components/st/LSM6DSV/LSM6DSV.zen")

LSM6DSV(name="IC2", VDD=V3V3, VDDIO=V3V3, GND=GND, SPI=IMU_SPI, INT1=IMU_INT1, INT2=IMU_INT2,
        SDX=GND, SCX=GND)
```

## Pins (DS13476 Rev 5, Table 2)

| Pad | Pin | io | Symbol type |
|---|---|---|---|
| 1 | SDO/SA0 | `SPI.MISO` | bidirectional |
| 2 | SDx | `SDX` (mode 1: tie to Vdd_IO or GND) | bidirectional |
| 3 | SCx | `SCX` (mode 1: tie to Vdd_IO or GND) | bidirectional |
| 4 | INT1 | `INT1` | output |
| 5 | Vdd_IO | `VDDIO` (1.08-3.6 V) | power_in |
| 6, 7 | GND | `GND` | power_in |
| 8 | Vdd | `VDD` (1.71-3.6 V) | power_in |
| 9 | INT2 | `INT2` (INT2 or DEN input) | bidirectional |
| 10 | OCS_Aux | not connected | input |
| 11 | SDO_Aux | not connected | output |
| 12 | CS | `SPI.CS` (pull-up by default) | input |
| 13 | SCL | `SPI.CLK` | input |
| 14 | SDA | `SPI.MOSI` | bidirectional |

- The symbol uses the reference prefix `IC`.
- OCS_Aux and SDO_Aux are left unconnected and soldered (Table 2 note 2), which modes 1 and 2
  allow. Mode 3 (auxiliary SPI) needs a different package entrypoint.
- Place 100 nF ceramic capacitors close to Vdd and Vdd_IO (Figure 27).

## Footprint

`LGA-14_3x2.5mm_P0.5mm.kicad_mod` is the Altium MicrasLib footprint `LSM6DSV16BXTR` of the
Micras main board. It matches the LGA-14L 2.5 x 3.0 mm, 0.5 mm pitch package of DS13476
Figure 31: pads 1-4 and 8-11 on the 2.5 mm sides at x = -/+1.15 mm, pads 5-7 and 12-14 on the
3.0 mm sides at y = +/-0.9 mm, all 0.6 x 0.3 mm over terminals of 0.475 x 0.25 mm; pad 1 top
left, numbering counter-clockwise in top view (Figure 4). The body outline is on User.13
(Altium mechanical layer).

The embedded STEP is `LSM6DSV320XTR.stp`: a 3.0 x 2.5 mm LGA body, 0.74 mm tall, while the
LSM6DSV is 0.86 mm max (Figure 31). The 3D view and STEP export show the IMU 0.12 mm lower than
the real part. `pcb rectify check`: model transform OK.

Courtyard: an F.CrtYd rectangle around the body outline (User.13) and the pads, 0.25 mm, the
IPC-7351B nominal courtyard excess (KiCad Library Conventions F5.3).
