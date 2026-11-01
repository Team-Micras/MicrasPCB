# ESP32-C5-MINI-1

Espressif ESP32-C5-MINI-1-N4 (LCSC C54951860): ESP32-C5 dual-band (2.4 and 5 GHz) Wi-Fi 6 and
Bluetooth LE 5 module with 4 MB flash and a PCB antenna, 15.4 x 21.3 x 2.4 mm, 65 pads. Bare part:
decoupling, the EN delay and the strapping pull-ups belong to the board. Evidence is in the
docstring of [`ESP32-C5-MINI-1.zen`](ESP32-C5-MINI-1.zen).

```python
ESP32_C5_MINI_1 = Module("github.com/Team-Micras/MicrasPCB/components/espressif/ESP32-C5-MINI-1/ESP32-C5-MINI-1.zen")

ESP32_C5_MINI_1(
    name="U13",
    V3V3=V3V3_D,
    GND=GND,
    EN=ESP_EN,            # RC delay 10 kOhm / 1 uF, a pad or header pin to GND
    IO28=ESP_BOOT,        # boot strap: pull it up, low at reset for the download mode
    IO11=ESP_TXD0,        # TX0 (U0TXD), 499 Ohm inside the module
    IO12=ESP_RXD0,        # RX0 (U0RXD)
    IO2=NotConnected(),   # every unused GPIO explicitly
    # ...
)
```

Reference prefix `U`. Every GPIO is an io; pass `NotConnected()` for the unused ones. IO11/IO12
are the module's TX0/RX0 (UART0, the ROM's console and download port).

## Files

- `ESP32-C5-MINI-1.kicad_sym`: KiCad 10 symbol, pin numbers as Table 3-1 of the datasheet (the
  18 NC pads are hidden no-connect pins).
- `ESP32-C5-MINI-1.kicad_mod`: the pads of Espressif's footprint from
  [espressif/kicad-libraries](https://github.com/espressif/kicad-libraries) (CC-BY-SA 4.0 with
  the KiCad libraries' design exception), checked against the datasheet's Figure 11-1 land
  pattern: 60 x 0.4 x 0.8 mm pads at 0.85 mm pitch on 14 mm rows, four 0.8 x 0.8 mm corner pads,
  a 3 x 3 grid of 1.2 mm EPAD squares at 1.65 mm (4.5 mm), the 5.85 mm antenna area of the
  21.3 mm body, and Espressif's antenna keep-out on every copper layer (no tracks, vias, pads,
  pours or footprints), 7.7-13.6 mm from the centre. Changed from Espressif's file: the antenna
  area's outline and its "Antenna Area" text are on F.Fab, not the silkscreen (on a board cut away
  under the antenna there is nothing to print them on); a pin-1 tick on the silkscreen outside the
  body, beside pad 1 (the module hides any mark under it); and the 12 thermal-via sites of Figure
  11-1 ("Via for thermal pad", in the gaps between the EPAD squares) as 0.2 mm circles on
  Cmts.User, the repo's via-site convention (boards/main2/layout/route.py thermal_sites), for the
  layout to place 0.2 mm vias there.
- Espressif's STEP (`ESP32-C5-MINI-1_V1-3_0.STEP`, linked from the datasheet's section 11.1) is
  embedded (`pcb embed-step`) at offset (-7.7, -7.7, 0), no rotation: its 15.4 x 21.3 mm body
  lands on the footprint's outline, antenna end at -13.6 mm (checked on a KiCad VRML export).

## Integration

- 3V3 at 3.0-3.6 V from a supply of at least 0.6 A (Table 6-2); 5 GHz TX peaks at 426 mA
  (Table 6-5). Figure 9-1 decouples it with 22 uF + 0.1 uF.
- EN never floating; RC delay 10 kOhm / 1 uF (section 9).
- Strapping pins (Table 4-1): GPIO28 and GPIO27 (boot mode, weak pull-ups), GPIO26, GPIO25, MTDI
  (GPIO3), MTMS (GPIO2), GPIO7. Pull GPIO28 up, no large capacitor on it (schematic checklist).
  The restriction-free GPIOs for board signals are GPIO0, GPIO1, GPIO6, GPIO8-GPIO10, GPIO23 and
  GPIO24 (chip datasheet section 2.3.5, priority 2).
- UART0 (TX0/RX0) for download and logs, wired like Espressif's ESP-Prog Program interface for a
  plug-in programmer; a series resistor on the TX line of any other UART (checklist, UART).
- The antenna: its ground point is at the pin-1 end (the pad-62 corner), its open, loaded end at
  the pin-45 end (Espressif's STEP, parts ANT-C5-MINI-1-top and ANT-C5-MINI-1-buttom; the
  datasheet v1.4 cover image; the Hardware Design Guidelines' "GND Point" figure on the
  ESP32-C5-WROOM-1's antenna, the same design mirrored). Put the antenna at the board edge with
  nothing under it, at most 2 mm from the ground-point (pin-1) side to the board's side edge, at
  least 15 mm of clearance beyond the open (pin-45) end, and the antenna end at most 1 mm inside
  the board's edge line (ESP32-C5 Hardware Design Guidelines, Keepout Zone for ESP32-C5 Module's
  Antenna). The
  MINI-1U (external antenna) has a different body (15.4 x 15.4 mm, Figure 11-2) and is not
  modelled here.

## Test bench

[`test/test_ESP32-C5-MINI-1.zen`](test/test_ESP32-C5-MINI-1.zen): the orderable part, the pinout
(every io on its own symbol pin, TX0/RX0 on GPIO11/12, EN, the boot strap IO28) and the supply
range on a 3.3 V buck rail.
