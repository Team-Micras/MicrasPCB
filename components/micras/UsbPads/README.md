# UsbPads

Bare USB pads: three SMD pads, 1x3 at 1.27 mm, for a USB cable's D-, D+ and ground wires soldered
once, so a chip's USB 2.0 full-speed device port is reachable without a receptacle. Copper on the
PCB, not a purchased part: excluded from the BOM and the placement file. Evidence is in the
docstring of [`UsbPads.zen`](UsbPads.zen).

```python
UsbPads = Module("github.com/Team-Micras/MicrasPCB/components/micras/UsbPads/UsbPads.zen")

UsbPads(name="J3", GND=GND, DN=USB_DN, DP=USB_DP)
```

| Pad | Pin | Signal | Silkscreen |
|---|---|---|---|
| 1 | `GND` | ground | `G` |
| 2 | `DN` | USB D- | `D-` |
| 3 | `DP` | USB D+ | `D+` |

The pads carry no VBUS: the board says where the cable's 5 V goes, if anywhere. Route the pair as
a 90 Ohm differential pair with the chip's series resistors and ESD protection as the chip's
guidelines ask; the package holds the pads only.

## Files

- `UsbPads.kicad_sym`: KiCad 10 symbol, pins `Pin_1`-`Pin_3`, names hidden.
- `UsbPads_1x03_P1.27mm_SMD.kicad_mod`: three 1.0 mm square SMD pads (F.Cu, F.Mask, no paste) at
  1.27 mm, each labelled on F.Silkscreen at its right (0.4 mm text, 0.1 mm stroke), a courtyard
  0.25 mm round the pads. No 3D model: nothing is mounted.

## Test bench

[`test/test_UsbPads.zen`](test/test_UsbPads.zen): each signal on its pad, not in the BOM or the
placement file.
