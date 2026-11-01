# HC-PZ127-7.2L-2x3PS

Hong Cheng HC-PZ127-7.2L-2x3PS (LCSC C27985144): 2x03 pin header, 1.27 mm pitch, SMD vertical,
pin tips 5.5 mm over the board. Bare part. Evidence is in the docstring of
[`HC-PZ127-7.2L-2x3PS.zen`](HC-PZ127-7.2L-2x3PS.zen).

```python
HC_PZ127_2x3 = Module("github.com/Team-Micras/MicrasPCB/components/hong-cheng/HC-PZ127-7.2L-2x3PS/HC-PZ127-7.2L-2x3PS.zen")

HC_PZ127_2x3(name="J2", P1=ESP_EN, P2=V5V_IN, P3=ESP_TXD0, P4=GND, P5=ESP_RXD0, P6=ESP_BOOT)
```

Pins `P1`-`P6`: odd pins on one row, even on the other, 1 and 2 side by side (the IDC ribbon
convention), so the example is Espressif's ESP-Prog Program interface order. Reference prefix
`J`.

## Files

- `HC-PZ127-7.2L-2x3PS.kicad_sym`: KiCad 10 symbol, pins `Pin_1`-`Pin_6`, names hidden.
- `HC-PZ127-7.2L-2x3PS.kicad_mod`: the drawing's recommended layout (0.74 x 2.50 mm pads at
  1.27 mm pitch, 6.5 mm over both rows) on KiCad's `PinHeader_2x03_P1.27mm_Vertical_SMD` outline
  and silkscreen (pin 1 marked).
- KiCad's `PinHeader_2x03_P1.27mm_Vertical_SMD.step` is embedded, stretched in z by 1.2313 so the
  pin tips reach the drawing's 5.5 mm (KiCad's model: 4.47 mm). Its insulator then stands 2.0 mm
  high against the drawing's 1.5 mm: the overall height, which the layout's height checks use, is
  right; the insulator's proportions are not. A model of the exact part is not available.

## Test bench

[`test/test_HC-PZ127-7.2L-2x3PS.zen`](test/test_HC-PZ127-7.2L-2x3PS.zen): the orderable part and
each pin on its own net.
