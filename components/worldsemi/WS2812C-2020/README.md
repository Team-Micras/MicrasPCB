# WS2812C-2020

Worldsemi WS2812C-2020-V6 (LCSC C55109522): 3.3-5.3 V addressable RGB LED, single-wire data,
2.2 x 2.0 x 0.84 mm, 4 pads, 5 mA per colour. The 3.3 V successor of the main board's
WS2815C-2020-4P (12 V) for a board without a 12 V or 5 V rail. Evidence is in the docstring of
[`WS2812C-2020.zen`](WS2812C-2020.zen).

```python
WS2812C = Module("github.com/Team-Micras/MicrasPCB/components/worldsemi/WS2812C-2020/WS2812C-2020.zen")

WS2812C(name="D1", VDD=V3V3, GND=GND, DI=LED_DATA, DO=D1_TO_D2)
WS2812C(name="D2", VDD=V3V3, GND=GND, DI=D1_TO_D2, DO=NotConnected())
```

| Pad | Pin | Function |
|---|---|---|
| 1 | DO | data out to the next LED's DI |
| 2 | GND | ground |
| 3 | DI | data in |
| 4 | VDD | supply, 3.3-5.3 V |

Integration notes (WS2812C-2020-V6 V1.0):

- `VDD` is declared 3.3-5.3 V (p.2). The datasheet gives 3.3 V only as the bottom of that range
  and in the feature text; its tables are at 5 V. V1.1 p5's curve keeps each channel's 5 mA
  sink at full current from 0.4 V across it, so a channel holds full current while its LED's VF
  is at most VDD - 0.4 V: at 3.3 V that is the knee for green (boards/main2 Peripherals.zen).
- A 100 nF capacitor on VDD per LED (p.5 typical application) is the board's.
- DI needs VIH = 0.55 x VDD (1.82 V at 3.3 V), so a 3.3 V MCU on the same rail drives it directly.
- Bit timing (p.3-4): T0H 220-380 ns, T1H 580 ns-1 us, T0L and T1L 580 ns-1 us, reset >= 280 us;
  GRB order, MSB first. The low times are capped at 1 us, tighter than the WS2815C's 5 us: the
  firmware's bit period must stay within 0.8-2 us.
- V1.0 calls DI and DO interchangeable (p.2 pin table); V1.1 drops that wording, so wire DI to DO.
- Moisture sensitivity level 5a: bake before reflow as p.8 describes.

## Footprint

`LED-SMD_4P-L2.2-W2.0-P1.00_WS2812C-2020-V6.kicad_mod`: the LCSC/EasyEDA land of C55109522, the
same pads as `components/worldsemi/WS2815C-2020` (0.8 x 0.8 mm at x +-0.865, y +-0.55 mm; the
datasheet's solder-pad drawing gives 0.7 x 0.7 mm pads with the same outer edges), the polarity
bar on the DO/GND side. LCSC has no 3D model for C55109522: the embedded model is the
WS2815C-2020 body (2.22 x 2.01 x 0.97 mm), scaled to 0.8643 in z in the footprint so it stands
0.84 mm high, the WS2812C-2020-V6 height (p.2). `pcb rectify check`: OK.
