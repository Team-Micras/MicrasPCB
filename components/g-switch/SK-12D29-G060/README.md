# SK-12D29-G060

G-Switch SK-12D29-G060 SPDT right-angle slide switch with a 6.0 mm black lever, through hole, as
a bare part: the main board's battery switch (SW4), rated for the 4S pack. Datasheet: G-Switch
drawing SK-12D29-GXXX (2016-05-29), LCSC C2848877. Evidence is in the docstring of
[`SK-12D29-G060.zen`](SK-12D29-G060.zen).

```python
SK12D29 = Module("github.com/Team-Micras/MicrasPCB/components/g-switch/SK-12D29-G060/SK-12D29-G060.zen")

SK12D29(name="SW4", A=NotConnected(), COM=BAT_P, B=BAT_SW_DRIVE)
```

Reference prefix: `SW`. Properties `voltage` (24 V) and `current` (1 A), the DC contact rating.

| Pin | Name | io | Notes |
|---|---|---|---|
| 1 | A | `A` | outer pin |
| 2 | COM | `COM` | centre pin, the common |
| 3 | B | `B` | outer pin |
| (unnumbered) | | | two frame legs, mechanical |

Rating: DC 24 V 1.0 A; contact resistance 50 mOhm max; 100 MOhm at DC 250 V; AC 250 V for 1 min;
-25 to +70 C; 10,000 cycles. Which lever position joins pin 2 to pin 1 is not on the drawing
(TODO: check on a sample before the silkscreen marks ON).

## Why this part

Requirement (main2, Regulators): DC rating at or above the 4S pack (16.8 V, 17.4 V with HV
cells; the switch carries only Q6's gate drive, VBAT / 200 kOhm, about 87 uA), not much bigger
than the MK-12D18-G040 it follows, a long black lever that overhangs the rear notch's edge,
mounted the same way. Candidates (drawings and LCSC listings, JLCPCB parts search 2026-10-17;
all extended parts):

| MPN | Rating | Body (L x depth x height) | Lever | Pins | LCSC, stock, price | Source |
|---|---|---|---|---|---|---|
| G-Switch MK-12D18-G040 (main board) | DC 12 V 0.5 A | 8.55 x 3.5 x 3.55 mm | 1.5 x 2.0 mm, 4.0 mm | 3 at 2.5 mm | C963202, 294, $0.15 | MK-12D18-GXXX drawing |
| **G-Switch SK-12D29-G060** | **DC 24 V 1.0 A** | **8.6 x 3.6 x 3.6 mm** | **SQ1.5, 6.0 mm, black** | **3 at 2.0 mm + 2 legs at 8.3 mm** | **C2848877, 531, $0.13** | **SK-12D29-GXXX drawing** |
| G-Switch SS-12D03-G040 | DC 24 V 1.0 A | 8.7 x 5.1 x 3.7 mm (bent pins behind the body) | SQ1.5, 4.0 mm, black | 3 at 2.5 mm | C2876027, 229, $0.08 | SS-12D03-GXXX drawing |
| USAKRO SS-12D03-G4 | DC 50 V 0.3 A | 8.7 x 5.1 x 3.7 mm | SQ1.5, 4 mm, black POM | 3 at 2.5 mm | C698225, 53, $0.05 | USAKRO SS-12D03-G4 drawing |
| G-Switch SK-12D02-G040 | DC 24 V 1.0 A | 8.6 x 4.5 x 4.7 mm | 2.0 mm wide, 4.0 mm | 3 at 2.0 mm + 2 legs at 8.2 mm | C2930976, 824, $0.13 | SK-12D02-GXXX drawing |
| HOOYA SK-12D01G3 | DC 50 V 0.5 A | 8.6 x 4.5 mm | 2.0 mm square (G3) | 3 at 2.0 mm + 2 legs | C2939332, 72, $0.10 | HOOYA product page (LCSC C2939332) |
| G-Switch SK-12D15-G040 (SMD, gull wing) | DC 50 V 0.3 A (listing) | 8.6 x 4.7 mm (listing) | 2 mm, 4 mm (listing) | SMD | C7544905, 134, $0.17 | no datasheet on LCSC |
| DEALON MK-12D18-G4 | not stated | 9.0 x 3.5 mm | white, 4 mm | 3 at 2.5 mm | C19724088, 0, $0.10 | DEALON MK-12D18-G drawing |

The SK-12D29-G060 is the only candidate with the MK-12D18's body (8.6 x 3.6 mm against 8.55 x
3.5 mm, 3.6 mm high) and a black lever at least as long, and its 24 V rating is 1.38 x the 17.4 V
HV pack (2 x its 12 V). The SS-12D03 parts keep the 2.5 mm pin pattern but their bent pins add
about 1.5 mm of depth behind the body and put the lever 2.4 mm further out from the pin row; the
50 V parts are larger or have no datasheet with the dimensions. The two frame legs anchor the
switch against the force of flipping it by hand, which the MK-12D18 took on its three pins.

**Not a drop-in.** The footprint differs: 3 pins at 2.0 mm pitch (not 2.5 mm) and two leg holes.
In the board plane the body sits where the MK-12D18's does (rear face 0.95 mm behind the pin row,
against 1.0 mm), and the lever reaches 2.2 mm further: with the pin row 2 mm further inboard the
lever tip lands where the MK-12D18-G040's did and less of the body overhangs the notch.

## Footprint

`SW-TH_SK-12D29-G060.kicad_mod`, drawn for this package from the drawing: pads 1-3 at x = -2, 0,
+2 mm (0.8 mm holes, 1.4 mm pads), the frame legs at x = +-4.15 mm (1.1 mm holes, 1.8 mm pads,
unnumbered), all on y = 0. The drawing does not dimension the holes: the diameters are scaled from
it against its 2 mm pitch and fit the 0.3 mm thick pins and legs. F.Fab: the body (y -0.95 to
2.65 mm) and the lever over its travel (to y 8.65 mm). F.CrtYd 0.25 mm around the pads, the body
and the lever's travel. Silkscreen on the rear edge and the sides, clear of the pads.

The embedded STEP `SK-12D29-G060.step` was written for this package with CadQuery from the
drawing's nominal dimensions (body 8.6 x 3.6 x 3.6 mm, lever 1.5 x 1.5 x 6.0 mm at mid-height,
pins 0.5 x 0.3 mm and legs 0.8 x 0.3 mm, 2.2 mm long). `pcb rectify check` proposes a 90 degree
turn about X, which stands the lever up; the drawing's side view lays it parallel to the board, as
the model is, so the transform stays identity.
