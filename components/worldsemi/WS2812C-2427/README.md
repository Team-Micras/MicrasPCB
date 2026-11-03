# WS2812C-2427

Worldsemi WS2812C-2427-V6 (LCSC C55109524): 3.3-5.3 V addressable RGB LED, single-wire data,
2.7 x 2.4 x 1.1 mm, 4 pads, 5 mA per colour. The same IC, bit timing and IO names as
[`WS2812C-2020`](../WS2812C-2020) in a larger package, so a board swaps between the two by
changing only the `Module()` path; the footprint and pad numbering differ, so the layout needs
re-routing. Evidence is in the docstring of [`WS2812C-2427.zen`](WS2812C-2427.zen).

```python
WS2812C = Module("github.com/Team-Micras/MicrasPCB/components/worldsemi/WS2812C-2427/WS2812C-2427.zen")

WS2812C(name="D1", VDD=V3V3, GND=GND, DI=LED_DATA, DO=D1_TO_D2)
WS2812C(name="D2", VDD=V3V3, GND=GND, DI=D1_TO_D2, DO=NotConnected())
```

| Pad | Pin | Function | Position (mm) |
|---|---|---|---|
| 1 | DI | data in | (-1.00, -0.65) |
| 2 | VDD | supply, 3.3-5.3 V | (-1.00, +0.65) |
| 3 | DO | data out to the next LED's DI | (+1.00, +0.65) |
| 4 | GND | ground | (+1.00, -0.65) |

Integration notes (WS2812C-2427-V6 V1.0):

- `VDD` is declared 3.3-5.3 V (p.3). The datasheet gives 3.3 V only as the bottom of that range
  and in the feature text; its tables are at 5 V. The p.6 curve keeps each channel's 5 mA sink
  at full current from 0.4 V across it, so a channel holds full current while its LED's VF is at
  most VDD - 0.4 V.
- A 100 nF capacitor on VDD per LED (p.5 typical application) is the board's.
- DI needs VIH = 0.55 x VDD (1.82 V at 3.3 V) and VIL = 0.3 x VDD (p.3), so a 3.3 V MCU on the
  same rail drives it directly.
- Bit timing (p.4): T0H 220-380 ns, T1H 580 ns-1 us, T0L and T1L 580 ns-1 us, reset > 280 us;
  GRB order, MSB first. Identical to the WS2812C-2020-V6: no firmware change.
- The pin numbering is the p.2 pin table and top view; the p.5 application drawing's numbers
  contradict it and are not used.
- Moisture sensitivity level 2a (4 weeks floor life, p.7), not the 2020's 5a.

## Footprint

`LED-SMD_4P-L2.7-W2.4-P1.30_WS2812C-2427-V6.kicad_mod`: the datasheet has no recommended land
pattern, so the lands are derived from the p.2 bottom view (terminals 0.75 x 0.40 mm, 1.20 mm
apart across, 1.30 mm pitch): 0.90 x 0.50 mm pads at x +-1.00, y +-0.65 mm, i.e. 0.10 mm toe,
0.05 mm heel and 0.05 mm side extension. LCSC/EasyEDA has no CAD data for C55109524; its land for
the WS2812C-2427 (C4154872) puts 1.00 x 0.60 mm pads at x +-1.05. Silk: body top and
bottom edges and a pin-1 dot; F.Fab shows the body with its cut corner at pad 4 (GND), as on the
part.

The embedded model is the LCSC/EasyEDA STEP of the WS2812C-2427 (C4154872), the package the V6
was upgraded from (p.9): 2.70 x 2.40 x 1.12 mm, lens d2.0, terminals 0.75 x 0.40 mm at
y +-0.65 mm with 1.20 mm between them, cut corner over pad 4, all matching p.2. Offset z +0.57 mm
puts the terminal bottoms on the board. `pcb rectify check --strict`: OK.
