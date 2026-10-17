# ESP32-S3-MINI-1

Espressif ESP32-S3-MINI-1-N8 (LCSC C2913206): ESP32-S3 Wi-Fi 802.11b/g/n and Bluetooth LE 5
module with 8 MB flash and a PCB antenna, 15.4 x 20.5 x 2.4 mm, 65 pads. Bare part: decoupling,
the EN delay, strapping and USB resistors belong to the board. Evidence is in the docstring of
[`ESP32-S3-MINI-1.zen`](ESP32-S3-MINI-1.zen).

```python
ESP32_S3_MINI_1 = Module("github.com/Team-Micras/MicrasPCB/components/espressif/ESP32-S3-MINI-1/ESP32-S3-MINI-1.zen")

ESP32_S3_MINI_1(
    name="U13",
    V3V3=V3V3_D,
    GND=GND,
    EN=ESP_EN,
    USB=ESP_USB,          # GPIO20 = USB_D+, GPIO19 = USB_D-
    IO0=ESP_BOOT,         # strapping: pull it up, pad or button to GND
    IO17=ESP_TXD,         # UART1 TX
    IO18=UART_RX,         # UART1 RX
    IO1=NotConnected(),   # every unused GPIO explicitly
    # ...
)
```

Reference prefix `U`. Every GPIO is an io; pass `NotConnected()` for the unused ones. IO43/IO44
are the module's TXD0/RXD0 (UART0, which prints the ROM boot messages).

## Files

- `ESP32-S3-MINI-1.kicad_sym`: the KiCad 10 `RF_Module` library symbol (pin numbers as Table 3-1
  of the datasheet), with this package's footprint.
- `ESP32-S3-MINI-1.kicad_mod`: Espressif's footprint from
  [espressif/kicad-libraries](https://github.com/espressif/kicad-libraries) (CC-BY-SA 4.0 with the
  KiCad libraries' design exception), upgraded to KiCad 10. It matches the datasheet's Figure
  11-1 land pattern (60 x 0.4 x 0.8 mm pads at 0.85 mm pitch on 14 mm rows, four 0.8 x 0.8 mm
  corner pads, a 3 x 3 grid of 1.2 mm EPAD squares at 1.65 mm, the 5.05 mm antenna area) and
  carries the antenna keep-out on every copper layer (no tracks, vias, pads, pours or footprints).
- Espressif's STEP from the same repository is embedded (`pcb embed-step`), with Espressif's
  transform: its body box (15.4 x 20.5 mm from a corner) lands on the footprint's body outline,
  antenna end at -12.8 mm.

## Integration

- 3V3 at 3.0-3.6 V from a supply of at least 0.5 A (Table 6-2); Wi-Fi TX peaks at 355 mA
  (Table 6-4). Figure 9-1 decouples it with 22 uF + 0.1 uF.
- EN never floating; RC delay 10 kOhm / 1 uF (section 9).
- Strapping pins GPIO0, GPIO3, GPIO45, GPIO46 (Table 4-1): keep host lines off them, pull GPIO0
  up, no large capacitor on GPIO0.
- USB on GPIO19/GPIO20 with 22-33 Ohm series resistors near the module (hardware design
  guidelines, schematic checklist).
- The antenna at the board edge with nothing under it; the MINI-1U-N8 (C2980299) is the same
  module with an antenna connector instead (Figure 11-2, no keep-out), not modelled here.

## Test bench

[`test/test_ESP32-S3-MINI-1.zen`](test/test_ESP32-S3-MINI-1.zen): the orderable part, the pinout
(USB on IO19/IO20, UART0 on GPIO43/44, EN) and the supply range on a 3.3 V buck rail.
