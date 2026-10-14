# GT-USB-7010ASV

USB Type-C receptacle, USB 2.0 only, 16 contacts, horizontal SMD with four through-hole shell tabs
(G-Switch GT-USB-7010ASV, LCSC C2988369). Bare connector: CC pull-downs, D+/D- series parts and
VBUS protection belong to the board. Ratings and citations are in the docstring of
[`GT-USB-7010ASV.zen`](GT-USB-7010ASV.zen).

```python
load("@stdlib/interfaces.zen", "Usb2")
GT_USB_7010ASV = Module("github.com/Team-Micras/MicrasPCB/components/g-switch/GT-USB-7010ASV/GT-USB-7010ASV.zen")

GT_USB_7010ASV(name="U2", VBUS=V5, GND=GND, SHIELD=GND, CC1=CC1, CC2=CC2, SBU1=SBU1, SBU2=SBU2,
               USB=Usb2("USB_C"))
```

## Pins (drawing pin table)

| Pad | Contacts | Pin | io | Symbol type |
|---|---|---|---|---|
| A4B9 | A4, B9 | VBUS | `VBUS` | power_out |
| B4A9 | B4, A9 | VBUS | `VBUS` | passive |
| A1B12 | A1, B12 | GND | `GND` | passive |
| B1A12 | B1, A12 | GND | `GND` | passive |
| A5 | A5 | CC1 | `CC1` | bidirectional |
| B5 | B5 | CC2 | `CC2` | bidirectional |
| A6, B6 | A6, B6 | D+ | `USB.D.P` | bidirectional |
| A7, B7 | A7, B7 | D- | `USB.D.N` | bidirectional |
| A8 | A8 | SBU1 | `SBU1` | bidirectional |
| B8 | B8 | SBU2 | `SBU2` | bidirectional |
| 1, 2, 3, 4 | shell tabs | SHIELD | `SHIELD` | passive |

- The symbol uses the reference prefix `U`.
- VBUS: one pad is power_out so the VBUS net has a source for KiCad ERC; the second is passive
  because two power outputs on one net are an ERC conflict.
- Both D+ contacts and both D- contacts are separate pads; the package ties each pair to one io.

## Footprint

`USB-C_G-Switch_GT-USB-7010ASV.kicad_mod` is the footprint `USB-C-SMD_G-SWITCH_GT-USB-7010ASV`
of the Micras main board (Altium MicrasLib), pad names unchanged. It follows the drawing's
recommended PCB layout: 0.3 x 1.24 mm signal pads and 0.6 x 1.24 mm VBUS/GND pads at y = -2.4 mm,
shell tabs as plated oval slots 8.64 mm apart (front pair 1.0 x 2.1 mm pad, 0.6 x 1.7 mm slot;
rear pair 1.0 x 1.8 mm pad, 0.6 x 1.4 mm slot, 4.18 mm behind).

- The two 0.65 mm housing-peg holes of the recommended layout (5.78 mm apart, at y = -1.28 mm)
  are drawn on F.Fab and User.1 but are not drilled by the footprint: the board outline must cut
  them (Edge.Cuts circles).
- The embedded STEP is `USB4105-GF-A-060--3DModel-STEP-56544.STEP`, a GCT USB4105 16-pin
  receptacle, not a G-Switch model: the 3D view and STEP export approximate the connector.
- Body outline graphics are on User.15 (Altium mechanical layer).
- Paste: the copper pads carry no paste layer; the stencil apertures are the F.Paste shapes
  drawn in the footprint, one over each SMD pad. The shell tabs are plated slots without paste.
- `pcb rectify check`: model transform OK.

Courtyard: an F.CrtYd rectangle around the body outline (User.15) and the pads, 0.5 mm, the
connector courtyard excess of KiCad Library Conventions F5.3.
