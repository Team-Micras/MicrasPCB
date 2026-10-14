# OpenPad

Two bare 0.8 mm square SMD pads, 1.5 mm apart, that a person bridges with tweezers or a solder
blob: a key or strap without a part. Copper on the PCB, not a purchased part, so it is excluded
from the BOM and the placement file.

```python
OpenPad = Module("github.com/Team-Micras/MicrasPCB/components/micras/OpenPad/OpenPad.zen")

OpenPad(name="OP1", P1=KEY, P2=GND)     # designator OP1
```

| Pad | io |
|---|---|
| 1 | `P1` |
| 2 | `P2` |

Reference prefix: `OP`.

## Footprint

`OpenPad.kicad_mod` is the footprint `OPENPAD` of the Micras Bluetooth module (Altium
MicrasBluetoothModuleLib): pads with mask and paste openings, so reflow tins them, and two
silkscreen arcs around the pair. There is no 3D model (bare copper) and no courtyard.
