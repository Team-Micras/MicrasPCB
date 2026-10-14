# XAL6030-102

Coilcraft XAL6030-102MEB 1.0 uH 20 % shielded power inductor (XAL6030, 6.5 x 6.3 mm), as a bare
part.

```python
XAL6030 = Module("github.com/Team-Micras/MicrasPCB/components/coilcraft/XAL6030-102/XAL6030-102.zen")

XAL6030(name="L2", P1=SW, P2=VBAT)
```

Reference prefix: `L`. io `P1` = pad 1, `P2` = pad 2 (non-polar).

| Property | Value | Source |
|---|---|---|
| inductance | 1.0 uH +-20 % | LCSC C2938919 listing |
| current | 23 A | LCSC listing; saturation or heating not stated |
| dcr | 5.62 mOhm | LCSC listing |

TODO: confirm Isat (and its drop definition), Irms and DCR max against the Coilcraft XAL60xx
datasheet before a check relies on them.

Footprint `XAL6030.kicad_mod`: 1.43 x 5.5 mm pads at 4.04 mm pitch,
from the Micras Altium library (MicrasMainBoard), with the XAL6030-102MEB STEP embedded.
`pcb rectify check` passes.

Courtyard: an F.CrtYd rectangle around the body outline (User.13) and the pads, 0.25 mm, the
IPC-7351B nominal courtyard excess (KiCad Library Conventions F5.3).
