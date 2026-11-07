# EspProgPads

ESP32 flashing pads: six plated holes, 2x3 at 1.27 mm, for a USB-serial adapter's wires soldered
once (or a 2x3 1.27 mm header fitted by hand), in the order of Espressif's ESP-Prog Program
interface. Copper on the PCB, not a purchased part: excluded from the BOM and the placement file.
Evidence is in the docstring of [`EspProgPads.zen`](EspProgPads.zen).

```python
EspProgPads = Module("github.com/Team-Micras/MicrasPCB/components/micras/EspProgPads/EspProgPads.zen")

EspProgPads(name="J2", EN=ESP_EN, VDD=V5V_IN, TXD=ESP_TXD0, GND=GND, RXD=ESP_RXD0, IO0=ESP_BOOT)
```

| Pad | Pin | Signal |
|---|---|---|
| 1 (square) | `EN` | the radio's EN (reset) |
| 2 | `VDD` | the adapter's supply pin; what it feeds is the board's |
| 3 | `TXD` | the radio's UART0 TX (the adapter's RX) |
| 4 | `GND` | ground |
| 5 | `RXD` | the radio's UART0 RX (the adapter's TX) |
| 6 | `IO0` | the download-mode strap (GPIO28 on the ESP32-C5) |

Odd pads on one row, even on the other, 1 and 2 side by side (the IDC ribbon convention), so a
header in the holes takes the ESP-Prog's 1.27 mm cable pin 1 to pad 1. The board labels the pads
on its own silkscreen.

## Files

- `EspProgPads.kicad_sym`: KiCad 10 symbol, pins `Pin_1`-`Pin_6`, names hidden.
- `EspProgPads_2x03_P1.27mm.kicad_mod`: KiCad's `PinHeader_2x03_P1.27mm_Vertical` with its pads
  grown from 1.0 to 1.05 mm on the 0.65 mm drills (a 0.2 mm ring, 0.22 mm between pads,
  `rules/jlcpcb.kicad_dru`), pad 1 square. KiCad's STEP of that header is embedded
  (`pcb embed-step`): the height checks see a header fitted in the holes.

## Test bench

[`test/test_EspProgPads.zen`](test/test_EspProgPads.zen): each signal on its pad, not in the BOM
or the placement file.
