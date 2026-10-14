# MK-12D18-G040

G-Switch MK-12D18-G040 SPDT right-angle slide switch, 4.0 mm actuator, through hole, as a bare
part. Evidence is in the docstring of [`MK-12D18-G040.zen`](MK-12D18-G040.zen). Datasheet:
G-Switch drawing MK-12D18-GXXX rev. X1.

```python
MK12D18 = Module("github.com/Team-Micras/MicrasPCB/components/g-switch/MK-12D18-G040/MK-12D18-G040.zen")

MK12D18(name="SW4", COM=VBAT, A=NotConnected(), B=GATE)
```

Reference prefix: `SW`.

## Pinout (drawing, circuit diagram)

| Pin | Name | io | Notes |
|---|---|---|---|
| 1 | A | `A` | joined to COM in position A |
| 2 | COM | `COM` | centre pin |
| 3 | B | `B` | joined to COM in position B |

Rating: DC 12 V 0.5 A / DC 6 V 1.0 A; contact resistance 100 mOhm max; -20 to +70 C.

## Footprint

`SW-TH_MK-12D18-G040.kicad_mod`: three plated 0.6 x 1.0 mm slots at 2.5 mm pitch, from the Micras
Altium library (MicrasMainBoard), with the Micras switch STEP embedded. `pcb rectify check`
passes.

Paste: none; the three pads are plated through-holes, which take no stencil paste.

Courtyard: an F.CrtYd rectangle around the body and lever outline (User.15) and the pads, 0.25 mm,
the IPC-7351B nominal courtyard excess (KiCad Library Conventions F5.3).
