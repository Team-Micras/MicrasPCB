# CT-1515UGRBC

CHONGTIAN CT-1515UGRBC/H-P9-MX4 (LCSC C52191310): addressable RGB LED, VDD 3-7.5 V, single-wire
WS2812-style data, 1.5 x 1.5 x 0.9 mm, 4 pads, 5 mA per colour. JLCPCB places it with Economic
PCBA (the WS2812C-2427 and WS2812C-2020 are Standard PCBA only). Evidence is in the docstring of
[`CT-1515UGRBC.zen`](CT-1515UGRBC.zen).

```python
CT1515 = Module("github.com/Team-Micras/MicrasPCB/components/chongtian/CT-1515UGRBC/CT-1515UGRBC.zen")

CT1515(name="D1", VDD=V3V3, GND=GND, DI=LED_DATA, DO=D1_TO_D2)
CT1515(name="D2", VDD=V3V3, GND=GND, DI=D1_TO_D2, DO=NotConnected())
```

| Pad | Pin | Function | Position (mm) |
|---|---|---|---|
| 1 | DI | data in | (-0.52, -0.52) |
| 2 | GND | ground | (+0.52, -0.52) |
| 3 | DO | data out to the next LED's DI | (+0.52, +0.52) |
| 4 | VDD | supply, 3-7.5 V | (-0.52, +0.52) |

The corners hold the same signals as the [WS2812C-2427](../../worldsemi/WS2812C-2427)'s
(DI top left, GND top right, DO bottom right, VDD bottom left), 1.04 mm apart instead of
2.00 x 1.30 mm.

Integration notes (datasheet A2, 2026-01-23):

- `VDD` is declared 3-7.5 V: the recommended operating range (p.3). The electrical tables are at
  4.5-5.0 V, so 3.3 V rests on that range's 3 V minimum.
- DI needs VIH = 0.7 x VDD (2.31 V at 3.3 V; p.4), so a 3.3 V MCU on the same rail drives it.
- Bit timing (p.6): T0H 0.295 us and T1H 0.595 us, each +-0.05 us; low times under 20 us with a
  bit of at least 1.2 us; reset >= 80 us. A WS2812 driver fits if its high times sit in those
  windows (the WS2812C's T0H 220-380 ns and T1H 580 ns-1 us are wider).
- 24 bits per LED, MSB first, GRB per the p.6 note; the p.6 bit drawing shows R first. If red and
  green come out swapped, change the firmware's byte order.
- One capacitor per LED on VDD (p.7, no value given) is the board's.

## Footprint

`LED-SMD_4P-L1.5-W1.5-P1.04_CT-1515UGRBC.kicad_mod`: the datasheet's recommended land pattern
(p.2): 0.50 x 0.50 mm pads, 0.54 mm apart, centres at +-0.52 mm, numbered from the p.2 top view.
Silk: a pin-1 dot left of pad 1; F.Fab: the body with its pin-1 corner cut. The LCSC/EasyEDA land
for C52191310 is the same pattern turned 90 degrees (pad 1 bottom left, 0.55 mm pads 1.00 mm
apart), so JLCPCB's CPL takes a 270 degree offset (`parts/jlc.toml`).

The embedded model is the LCSC/EasyEDA STEP for C52191310 (`LED-SMD_4P-L1.5-W1.5-BL_MHP1515ICRGBDT`,
a generic 1515 RGB body): 1.50 x 1.50 mm with corner terminals, 0.75 mm high; the footprint scales
it by 1.2 in z to the datasheet's 0.90 mm. It carries no pin-1 mark.
