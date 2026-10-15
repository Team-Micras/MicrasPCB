# INA228

Texas Instruments INA228AIDGSR (LCSC C2887910): 20-bit power, energy and charge monitor with an
I2C interface; shunt input +-163.84 mV or +-40.96 mV (ADCRANGE), common mode -0.3 to 85 V, bus
voltage input 0 to 85 V, 2.7-5.5 V supply; VSSOP-10 (DGS). Bare part: the VS bypass capacitor,
the shunt, the address straps and the pull-ups belong to the board. Evidence is in the docstring
of [`INA228.zen`](INA228.zen).

```python
INA228 = Module("github.com/Team-Micras/MicrasPCB/components/ti/INA228/INA228.zen")

# Battery monitor, high side (SLYS021A Figure 8-2): IN+ on the battery side of a 2 mOhm Kelvin shunt,
# VBUS on the battery rail, address 0x40 (A1 = A0 = GND, Table 7-2).
INA228(name="U9", VS=V3V3, GND=GND, IN_P=VBAT, IN_N=VBAT_LOAD, VBUS=VBAT, I2C=ESP_I2C, ALERT=BAT_ALERT, A0=GND, A1=GND)
Capacitor(name="C81", P1=GND, P2=V3V3, **C_100N_0402)  # VS bypass (section 9)
```

Reference prefix `U`. `VS` declares the 2.7-5.5 V operating range (section 6.3). The package
fails the build when a net with a declared voltage puts IN+ or IN- outside -0.3 to 85 V or VBUS
outside 0 to 85 V.

## Pinout (SLYS021A Table 5-1, DGS)

| Pin | Name | Symbol type | io |
|---|---|---|---|
| 1 | A1 | input | `A1` |
| 2 | A0 | input | `A0` |
| 3 | ALERT | open_collector | `ALERT` |
| 4 | SDA | bidirectional | `I2C.SDA` |
| 5 | SCL | input | `I2C.SCL` |
| 6 | VS | power_in | `VS` |
| 7 | GND | power_in | `GND` |
| 8 | VBUS | input | `VBUS` |
| 9 | IN- | input | `IN_N` |
| 10 | IN+ | input | `IN_P` |

Address (Table 7-2): A1 and A0 each on GND, VS, SDA or SCL; address = 0x40 + 4 x code(A1) +
code(A0), with GND = 0, VS = 1, SDA = 2, SCL = 3.

## Footprint

`Texas_DGS0010A_VSSOP-10_3x3mm_P0.5mm.kicad_mod`, the land pattern of TI's DGS0010A example board
layout (4221984/A, in SLYS021A): ten 1.45 x 0.3 mm pads with 0.05 mm corner radius, 0.5 mm pitch,
rows 4.4 mm apart centre to centre, pins 1-5 down the left side and 6-10 up the right side (top
view); non-solder-mask-defined (the board's mask expansion applies); paste equal to the pads (TI's
stencil example). Body 3 x 3 mm on F.Fab with the pin 1 chamfer, F.CrtYd 0.25 mm around pads and
body. The package is JEDEC MO-187 variation BA, so the embedded STEP is KiCad's
`MSOP-10_3x3mm_P0.5mm.step` (same pin 1 corner and pad order). `pcb rectify check`: OK.

## Design requirements (board side)

- VS bypass (section 9, 10.1): 0.1 uF typical, as close as possible to VS and GND.
- Shunt (10.1): Kelvin (4-wire) connection. Full scale = 40.96 mV / RSHUNT with ADCRANGE = 1
  (CONFIG bit 4), 163.84 mV / RSHUNT with ADCRANGE = 0 (the reset value): 2 mOhm gives +-20.48 A
  with ADCRANGE = 1, SHUNT_CAL = 4096 for CURRENT_LSB = 20.48 A / 2^19 (equations 2-3). TEMPCOMP
  with SHUNT_TEMPCO corrects the shunt's TCR from the die temperature (7.3.5) if the shunt sits
  next to the part.
- Input filter (8.1.4): optional; at most 100 Ohm per input plus 0.1-1 uF across IN+/IN-;
  10 Ohm per input protects against the dV/dt of a hard short.
- VBUS: on the rail that powers the load, for the power calculation (Figure 10-1 note 1).
- I2C: open-drain SDA/SCL with pull-ups; 400 kHz fast mode or 2.94 MHz high speed (7.5.1).
- ALERT: open drain, active low by default; pull-up if used, may float if unused (Figure 10-1).
- Register settings (ADCRANGE, SHUNT_CAL, limits) reset at every VS power cycle (8.2.2.2-8.2.2.4):
  firmware writes them after each power-up.
