# WallSensor

The Micras wall sensor: an ams-OSRAM SFH 4550 850 nm IR LED stacked over a Toshiba TPS601A(F) NPN
phototransistor, both through-hole and bare (no casing), with their leads bent 90 degrees so they
look forward. Datasheet ratings, package dimensions and citations are in the docstring of
[`WallSensor.zen`](WallSensor.zen).

```python
WallSensor = Module("github.com/Team-Micras/MicrasPCB/components/micras/WallSensor/WallSensor.zen")

WallSensor(name="W1", LED_A=EMITTER_R, LED_K=EMITTER_SWITCH, PT_C=V3V3, PT_E=WALL_SENSE_0)
```

| Pad | IO | Device lead |
|---|---|---|
| 1 | `LED_A` | SFH 4550 anode |
| 2 | `LED_K` | SFH 4550 cathode (marked lead) |
| 3 | `PT_C` | TPS601A collector (TPS601A pin 2) |
| 4 | `PT_E` | TPS601A emitter (TPS601A pin 1) |

The footprint's pad numbers are not the manufacturers' lead numbers (the SFH 4550 land pattern calls
the cathode pad 1; the TPS601A numbers its emitter 1). Fit the leads by function as in the table.
The silkscreen draws a diode between pads 1 and 2 with its bar at pad 2, labels pad 2 "C" (LED
cathode) and pad 4 "E" (phototransistor emitter) to the right of the pads, outlines the lead area
behind the bodies (4.83 mm wide) and the two bodies in plan, 0.15 mm outside their largest
datasheet outline. The bodies reach 6.28 mm (LED lens tip, nominal) in front of the footprint
origin, the pads 6.38 mm behind it.

| Layer | Draws |
|---|---|
| F.CrtYd | both bodies at their largest (LED 9.0 mm long, 5.9 mm flange; TPS601A flange and key tab) and the pads, plus 0.25 mm: 6.93 mm in front of the origin to 6.64 mm behind it, 6.4 mm wide (6.77 mm at the TPS601A flange, whose key tab points to the pad 2/4 side) |
| User.13 | the two bodies at nominal size |
| 3D | `WALL_SENSOR_STACKED.STEP`: the SFH 4550 (axis 9.75 mm above the board) over the TPS601A (axis 3.25 mm), nominal size, from MicrasHardware `micras/leds.py` |

The TPS601A leads bend 2.0 mm behind its flange, the minimum of the datasheet (p.2, Precaution 2);
the SFH 4550 leads bend 2.55 mm behind its flange. A sensor sits fully on the board when its
courtyard is inside the outline with the 0.20 mm edge clearance of `rules/jlcpcb.kicad_dru`.

Sourcing and assembly:

- Each sensor is two purchased parts: one **SFH 4550** (ams-OSRAM) and one **TPS601A(F)** (Toshiba).
  They are formed (bend at least 2 mm from the TPS601A body) and hand-soldered, not assembled by
  JLCPCB.
- The component is therefore `skip_bom=True` and excluded from the placement file: the JLCPCB BOM
  and CPL do not list it. Order 4 + 4 parts separately for a main board.

The series resistor, the emitter switch and the phototransistor load are board circuitry.
