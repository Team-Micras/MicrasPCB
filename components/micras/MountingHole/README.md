# MountingHole

Screw hole for an M2 screw: a 2.4 mm non-plated drill, no copper, no pins. Not a purchased part,
so it is excluded from the BOM and the placement file. Evidence is in the docstring of
[`MountingHole.zen`](MountingHole.zen).

```python
MountingHole = Module("github.com/Team-Micras/MicrasPCB/components/micras/MountingHole/MountingHole.zen")

MountingHole(name="H1")   # designator H1
```

## Footprint

`MountingHole_2.4mm_NPTH.kicad_mod` is the screw hole of the Micras main board (Altium
MicrasMainBoard.PcbDoc): one 2.4 mm NPTH pad with a 2.4 mm drill, so no annular copper, and the
designator on F.Fab only. There is no courtyard and no 3D model (a bare hole).

Integration notes:

- The board's `spec/<board>.toml` places each hole; the layout locks it there.
- The screw head needs a copper-free ring on both sides if the screw must not touch a net: the
  footprint has no keepout, so leave the clearance in the layout.
