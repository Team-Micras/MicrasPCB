# L6981

ST L6981x33DR 38 V 1.5 A synchronous buck converter with a fixed 3.3 V output, SO-8, as a bare
part (symbol, footprint, pins). The application circuit (inductor, capacitors) belongs to the
board. Evidence and datasheet references are in the docstring of [`L6981.zen`](L6981.zen).
Datasheet: ST DS13554 Rev 3.

```python
L6981 = Module("github.com/Team-Micras/MicrasPCB/components/st/L6981/L6981.zen")

L6981(name="IC7", VIN=VBAT, EN=VBAT, VOUT=V3V3, GND=GND, SW=SW, BOOT=BOOT, VCC=VCC)
L6981(name="IC7", mpn="L6981C33DR", ...)  # low-consumption variant, same pins
```

| Config | Values | Meaning |
|---|---|---|
| `mpn` | `L6981N33DR` (default), `L6981C33DR` | LNM (forced PWM, sinks current) or LCM (pulse skipping, no sinking in normal operation); Table 11, p45 |

Reference prefix: `IC`.

## Pinout (Figure 2, Table 1, p3)

| Pin | Name | Type | io | Notes |
|---|---|---|---|---|
| 1 | SW | output | `SW` | switching node |
| 2 | BOOT | passive | `BOOT` | 100 nF typ to SW |
| 3 | VCC | power_out | `VCC` | internal LDO, >= 1 uF ceramic to GND |
| 4 | VOUT/FB | input | `VOUT` | output sense and supply of the fixed versions |
| 5 | EN/CLKIN | input | `EN` | VIN compatible; CLKIN on LNM parts only |
| 6 | AGND | power_in | `GND` | |
| 7 | VIN | power_in | `VIN` | |
| 8 | PGND | power_in | `GND` | |

`VIN` is `Power(3.5 V to 38 V)` (Table 6), `VOUT` is `Power(3.284 V to 3.346 V)` (fixed 3.3 V,
TJ -40 to 125 C, Table 6-7), `VCC` is `Power(3.0 V to 3.6 V)` (Table 6).

## Design equations (section 8.4, p26-28)

| Eq. | Rule |
|---|---|
| 35 | CIN,min = IOUT / (4 VPP,max fSW), VPP about 5 % of VIN,max |
| 36-37 | dIL = VOUT / L * TOFF; Lmin = VOUT / dIL,max * (1 - Dmin) / fSW, ripple 20-40 % of IOUT |
| 38 | 0.4 <= QP <= 1.33 (QP from Eq. 13) |
| 39 | IL,PK = IOUT + dIL / 2 below the current limit (2.0-2.3 A peak, Table 6) |
| 42 | COUT,BW,min = 4.02 / ((fSW / 10) VOUT) = 30.5 uF at 400 kHz, 3.3 V |
| 43 | COUT,BW,max = 0.48e-3 / VOUT = 145 uF at 3.3 V (internal compensation limit) |

## Footprint

`SOIC127P600X175-8N.kicad_mod`: IPC-7351 SO-8 land pattern from the Micras Altium library
(MicrasMainBoard), pad numbers equal to the package pins, with the L6981N33DR STEP embedded.
`pcb rectify check` passes.

Courtyard: an F.CrtYd rectangle around the body outline (User.13) and the pads, 0.25 mm, the
IPC-7351B nominal courtyard excess (KiCad Library Conventions F5.3).
