# WS2815C-2020

Worldsemi WS2815C-2020-4P (LCSC C22371529): 12 V addressable RGB LED, single-wire data, 2.2 x 2.0 mm,
4 pads. No external parts are needed (datasheet p.1). Evidence is in the docstring of
[`WS2815C-2020.zen`](WS2815C-2020.zen).

```python
WS2815C = Module("github.com/Team-Micras/MicrasPCB/components/worldsemi/WS2815C-2020/WS2815C-2020.zen")

WS2815C(name="D1", VDD=V12, GND=GND, DI=LED_DATA, DO=D1_TO_D2)
WS2815C(name="D2", VDD=V12, GND=GND, DI=D1_TO_D2, DO=NotConnected())
```

| Pad | Pin | Function |
|---|---|---|
| 1 | DO | data out to the next LED's DI |
| 2 | GND | ground |
| 3 | DI | data in |
| 4 | VDD | supply, 9.5-13.5 V |

Integration notes:

- `VDD` is declared 9.5-13.5 V (datasheet p.3). A board that supplies anything else gets a
  `pcb build` warning, on purpose: the LEDs need that range to light.
- DI accepts 2.7 V as a high level at VDD = 12 V, so a 3.3 V MCU can drive it directly.
- Bit timing (p.4): T0H 220-380 ns, T1H 580-840 ns, T0L 900-5000 ns, T1L 600-5000 ns,
  reset >= 280 us; GRB order, MSB first.
- Moisture sensitivity level 5a: bake before reflow as the datasheet (p.6-7) describes.

Courtyard: an F.CrtYd rectangle around the body outline (User.15) and the pads, 0.25 mm, the
IPC-7351B nominal courtyard excess (KiCad Library Conventions F5.3).
