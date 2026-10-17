# 918-118A2021Y40006

USB Type-C plug, USB 2.0, 16 contacts, vertical SMD, 8.65 mm tall (Shenzhen Jingtuojin
Electronic, LCSC brand "Jing Extension of the Electronic Co.", LCSC C399938), as a bare
connector. Ratings and citations are in the docstring of
[`918-118A2021Y40006.zen`](918-118A2021Y40006.zen). Drawing: 918-118A2021Y40006 rev A0
(2019-11-23).

```python
load("@stdlib/interfaces.zen", "DiffPair", "Usb2")
PLUG = Module("github.com/Team-Micras/MicrasPCB/components/jing-extension/918-118A2021Y40006/918-118A2021Y40006.zen")

PLUG(name="USB1", VBUS=NotConnected(), GND=GND, SHELL=GND, CC1=NotConnected(), CC2=NotConnected(),
     SBU1=SBU, SBU2=SBU, USB=Usb2(D=DiffPair(P=DP, N=DN)))
```

Reference prefix: `USB`.

## Contacts (drawing, recommended P.C.B. layout)

| Pads | Contact | Symbol type | io |
|---|---|---|---|
| 1, 8, 9, 16 | G | passive | `GND` |
| 2, 7, 10, 15 | V (VBUS) | passive | `VBUS` |
| 3 | CC1 | bidirectional | `CC1` |
| 11 | CC2 | bidirectional | `CC2` |
| 4, 12 | D+ | bidirectional | `USB.D.P` |
| 5, 13 | D- | bidirectional | `USB.D.N` |
| 6 | SUB1 (SBU1) | bidirectional | `SBU1` |
| 14 | SUB2 (SBU2) | bidirectional | `SBU2` |
| 17, 18 | shell fixing legs | passive | `SHELL` |

The drawing's rows read "G V SUB1 D- D+ CC1 V G" (pads 8 to 1) and "G V CC2 D+ D- SUB2 V G"
(pads 9 to 16). Each row carries D+ and D-, so a board that joins the two D+ pads and the two D-
pads (and SBU1 with SBU2) mates the same way in both plug orientations.

## Footprint

`USB-C-SMD_918-118A2021Y40006.kicad_mod` is the footprint of the same name on the Micras
Bluetooth module (Altium MicrasBluetoothModuleLib), pad numbers and geometry unchanged: two rows
of eight 0.4 x 0.79 mm pads at 0.8 mm pitch, 2.54 mm apart, and the two fixing legs in plated
0.6 x 1.8 mm oval slots (1.0 x 2.3 mm pads) 7.96 mm apart, as in the recommended layout.

- The embedded STEP is the Altium library's `USB-C-SMD_TC-005.step`; `pcb rectify check`: model
  transform OK.
- The F.CrtYd courtyard is the pads and fixing legs with 0.25 mm around them (+-4.75 x +-1.92
  mm), which also covers the 8.25 x 2.40 mm shell. The footprint has no silkscreen or fab outline.
