# TestPoint

Bare test pad: one 0.8 mm round SMD pad on the top copper with mask and paste openings, and a
1.2 mm silkscreen circle. Copper on the PCB, not a purchased part, so it is excluded from the BOM
and the placement file.

```python
TestPoint = Module("github.com/Team-Micras/MicrasPCB/components/micras/TestPoint/TestPoint.zen")

TestPoint(name="TP3", P1=SIGNAL)                                  # designator TP3
TestPoint(name="IMU_INT1", prefix="IMU_INT", P1=IMU_INT1)         # designator IMU_INT1
TestPoint(name="IMU_INT2", prefix="IMU_INT", P1=IMU_INT2)         # designator IMU_INT2
TestPoint(name="FAN_PWM", prefix="FAN_PWM", P1=FAN_PWM)           # designator FAN_PWM1
```

| Pad | io |
|---|---|
| 1 | `P1` |

## Designators

Config `prefix` (default `TP`) sets the reference designator prefix. pcb numbers each prefix
from 1 in instance-path order. A refdes-like instance name (`TP3`) is kept as the designator only
when the prefix is at most three letters and matches the name (`TP3` with `TP`, `INT5` with
`INT`); a longer or underscored prefix (`IMU_INT`, `FAN_PWM`) is always numbered from 1. A
functional prefix used by one test point therefore gives `<PREFIX>1`, and two test points that
share a prefix get 1 and 2 in name order.

## Footprint

`TestPoint_Pad_D0.8mm.kicad_mod` is the Altium MicrasLib footprint `TestPoint` of the Micras
main board. The paste opening tins the pad during reflow. There is no 3D model (bare copper).
