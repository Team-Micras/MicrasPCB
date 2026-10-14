# HM-19

JNHuaMao HM-19 Bluetooth Low Energy 5.0 module (TI CC2640R2F) with a UART, 13.5 x 18.5 mm, 16
castellated pads, as a bare module. Evidence and datasheet references are in the docstring of
[`HM-19.zen`](HM-19.zen). Datasheet: JNHuaMao "HM Bluetooth module datasheet", Last Version V107
(2019-02); the vendor publishes no stable URL for it, so the symbol's Datasheet field is empty.

```python
load("@stdlib/interfaces.zen", "Uart")
HM19 = Module("github.com/Team-Micras/MicrasPCB/components/jnhuamao/HM-19/HM-19.zen")

HM19(name="U1", VCC=V3V3, GND=GND, UART=Uart(TX=TX, RX=RX), PIO0=KEY, PIO1=LED,
     RTS=NotConnected(), CTS=NotConnected(), KEY=NotConnected(), RESETB=NotConnected(),
     PIO2=NotConnected(), PIO3=NotConnected())
```

Reference prefix: `U`.

## Pins (V107 section 6.8)

| Pad | Name | CC2640R2F | Symbol type | io |
|---|---|---|---|---|
| 1 | UART_RTS | DIO_9 | output | `RTS` |
| 2 | UART_TX | DIO_2 | output | `UART.TX` |
| 3 | UART_CTS | DIO_0 | input | `CTS` |
| 4 | UART_RX | DIO_1 | input | `UART.RX` |
| 5, 6 | NC | debug | no_connect | |
| 7 | NC | DIO_3 | no_connect | |
| 8 | KEY "System KEY" | DIO_4 | input | `KEY` |
| 9 | VCC | VDDS | power_in | `VCC` |
| 10 | "NC or VCC" | | passive | `VCC` |
| 11 | RESETB, "Reset if low >1000ms" | RESET_N | input | `RESETB` |
| 12 | GND | | power_in | `GND` |
| 13 | PIO3 | DIO_5 | bidirectional | `PIO3` |
| 14 | PIO2 | DIO_6 | bidirectional | `PIO2` |
| 15 | PIO1 "System LED" | DIO_7 | output | `PIO1` |
| 16 | PIO0 | DIO_8 | bidirectional | `PIO0` |

`VCC` is `Power(2.1 V to 3.7 V)`: the HM-19 row of the module table (section 3). Section 1 gives
1.9-3.7 V and 50 mA.

## Requirements for the board

- Vendor schematic (section 6.5): 1 kOhm in series with UART_TX and UART_RX, 10 uF and 100 nF on
  VCC, pin 10 on VCC, the status LED with 470 Ohm on PIO1, the key from PIO0 to GND, RESETB open.
- Key: the pin table puts the system key on pin 8, the vendor schematic and the `AT+SYSK` command
  on PIO0 (pin 16). A press over 1000 ms in standby restores the factory settings (section 7).
- RESETB: the CC2640R2F RESET_N has no internal pull-up (SWRS204C); the HM-19 datasheet does not
  say whether the module adds one.
- The 7 mm above pad 1 hold the antenna (section 6.6): keep copper out from under it, or let it
  overhang the board edge.

## Footprint

`HM-19.kicad_mod` is the footprint `HM-19` of the Micras Bluetooth module (Altium
MicrasBluetoothModuleLib), pad numbers and geometry unchanged: 0.8 x 1.524 mm pads at 1.5 mm
pitch, the two rows 13.5 mm apart, the origin on the module's bottom edge 1 mm below pads 8 and
9, as in the size drawing (section 6.6).

- The embedded STEP is the Altium library's `HM-19.STEP`. `pcb rectify check` reports a 9.2 mm
  offset because the body is not centred on the pads: the antenna end extends 7 mm beyond pad 1.
  A KiCad 3D render shows the body on the pads with that end off the pad rows, as drawn in 6.6.
- The body outline is on User.15 (Altium mechanical layer). The F.CrtYd courtyard is the body
  (antenna end included) and the pads with 0.25 mm around them: x +-7.77 mm, y -18.8 to +0.3 mm.
  There is no silkscreen.
