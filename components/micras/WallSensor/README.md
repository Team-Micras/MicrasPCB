# WallSensor

The Micras wall sensor: an ams-OSRAM SFH 4550 850 nm IR LED stacked over a Toshiba TPS601A(F) NPN
phototransistor, both through-hole with their leads bent 90 degrees so they look forward over the
board edge. Datasheet ratings and citations are in the docstring of [`WallSensor.zen`](WallSensor.zen).

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
cathode) and pad 4 "E" (phototransistor emitter).

Sourcing and assembly:

- Each sensor is two purchased parts: one **SFH 4550** (ams-OSRAM) and one **TPS601A(F)** (Toshiba).
  They are formed (bend at least 2 mm from the TPS601A body) and hand-soldered, not assembled by
  JLCPCB.
- The component is therefore `skip_bom=True` and excluded from the placement file: the JLCPCB BOM
  and CPL do not list it. Order 4 + 4 parts separately for a main board.

The series resistor, the emitter switch and the phototransistor load are board circuitry.
