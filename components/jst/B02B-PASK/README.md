# B02B-PASK

JST B02B-PASK(LF)(SN), PA series 2-pin 2.00 mm top-entry through-hole header, as a bare part.
It is the battery connector and the motor and fan connectors, so the reference prefix is a
config.

```python
B02B = Module("github.com/Team-Micras/MicrasPCB/components/jst/B02B-PASK/B02B-PASK.zen")

B02B(name="J1", P1=VBAT, P2=GND_BAT)
B02B(name="M1", prefix="M", P1=OUT_A, P2=OUT_B)
```

| Config | Values | Meaning |
|---|---|---|
| `prefix` | `J` (default), `M` | reference prefix (`J` battery, `M` motors and fan) |

| Pin | Name | io | Pad |
|---|---|---|---|
| 1 | Pin_1 | `P1` | round |
| 2 | Pin_2 | `P2` | square |

Ratings (LCSC C158050 listing): 3 A, 250 V, -25 to +85 C. TODO: confirm against the JST PA
catalogue.

Footprint `JST_PA_B02B-PASK_1x02_P2.00mm_Vertical.kicad_mod`: 1.2 mm pads on 0.7 mm holes at
2.00 mm pitch, pad 1 at the origin and pad 2 at x = -2.00 mm, from the Micras Altium library
(MicrasMainBoard), with the B02B-PASK STEP embedded. `pcb rectify check` reports a 1.89 mm z
offset for the model; a KiCad 3D render shows the housing seated on the board top and the pins
through the holes, so the transform is kept.
