# FUET-5030

FUET (Fusheng) FUET-5030 (LCSC C391031): 4 kHz passive electromagnetic buzzer, 5.0 x 5.0 x 3.0 mm SMD,
3 Vo-p rated (2-4 Vo-p), 110 mA max, 12 +/- 3 ohm coil, 80 dB min at 10 cm. Evidence is in the
docstring of [`FUET-5030.zen`](FUET-5030.zen).

```python
Buzzer = Module("github.com/Team-Micras/MicrasPCB/components/fuet/FUET-5030/FUET-5030.zen")

Buzzer(name="BZ1", POS=V3V3, NEG=BUZZER_SWITCH)
```

| Pad | Pin | IO |
|---|---|---|
| 1 | + | `POS` |
| 2 | - | `NEG` |
| 3 | NC (mechanical) | none: the symbol types it no_connect |

Integration notes:

- Drive it with a low-side switch on `NEG` and put a freewheeling diode across the coil (anode on
  `NEG`, cathode on `POS`), as in the datasheet's recommended driving circuit (p.4). Both are board
  circuitry.
- The coil is 12 +/- 3 ohm: at DC the current is limited only by the coil and whatever is in series,
  so size the series resistor's power for the longest tone the firmware plays.
