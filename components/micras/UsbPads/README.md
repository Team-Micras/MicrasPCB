# UsbPads

Bare USB pads: three plated holes, 1x3 at 1.27 mm, for a USB cable's D-, D+ and ground wires put
in from the top and soldered on the bottom, once, so a chip's USB 2.0 full-speed device port is reachable without a receptacle. Copper on the
PCB, not a purchased part: excluded from the BOM and the placement file. Evidence is in the
docstring of [`UsbPads.zen`](UsbPads.zen).

```python
UsbPads = Module("github.com/Team-Micras/MicrasPCB/components/micras/UsbPads/UsbPads.zen")

UsbPads(name="J3", GND=GND, DN=USB_DN, DP=USB_DP)
```

| Hole | Pin | Signal | Silkscreen (both sides) |
|---|---|---|---|
| 1 (square) | `GND` | ground | `G` |
| 2 | `DN` | USB D- | `D-` |
| 3 | `DP` | USB D+ | `D+` |

The holes carry no VBUS: the board says where the cable's 5 V goes, if anywhere. A 28-30 AWG
wire goes through a 0.65 mm hole; trim its end under the board like a through-hole lead. Route the pair as
a 90 Ohm differential pair with the chip's series resistors and ESD protection as the chip's
guidelines ask; the package holds the pads only.

## Files

- `UsbPads.kicad_sym`: KiCad 10 symbol, pins `Pin_1`-`Pin_3`, names hidden.
- `UsbPads_1x03_P1.27mm.kicad_mod`: three plated holes at 1.27 mm with `EspProgPads`' geometry (1.05
  mm pads on 0.65 mm drills: a 0.2 mm ring, 0.22 mm between pads, `rules/jlcpcb.kicad_dru`), pad 1
  square, each labelled at its right on F.Silkscreen and, mirrored, on B.Silkscreen (0.4 mm text,
  0.1 mm stroke), a courtyard 0.25 mm beside the pads, 0.235 mm past the ends. No 3D model: nothing
  is mounted.

## Test bench

[`test/test_UsbPads.zen`](test/test_UsbPads.zen): each signal on its pad, not in the BOM or the
placement file.
