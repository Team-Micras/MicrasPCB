# TLV7041

Texas Instruments TLV7041DBVR (LCSC C702122): nanopower comparator, 1.6-6.5 V, open-drain
output, internal hysteresis, SOT-23-5. Bare part: the output pull-up and the bypass capacitor
belong to the board. Evidence is in the docstring of [`TLV7041.zen`](TLV7041.zen).

```python
TLV7041 = Module("github.com/Team-Micras/MicrasPCB/components/ti/TLV7041/TLV7041.zen")

TLV7041(name="U7", VCC=V3V3, GND=GND, IN_P=REF, IN_N=SENSE, OUT=OUT_N)
```

Reference prefix `U`. The inputs take up to 7 V whatever the supply (SLVSE13J section 5.1), and
during power-on reset the output stays high impedance (section 6.4).

## Pinout (SLVSE13J Table 4-1, SOT-23)

| Pad | Name | Symbol type | io |
|---|---|---|---|
| 1 | OUT | open_collector | `OUT` |
| 2 | V- | power_in | `GND` |
| 3 | IN+ | input | `IN_P` |
| 4 | IN- | input | `IN_N` |
| 5 | V+ | power_in | `VCC` |

## Footprint

`SOT-23-5.kicad_mod` is KiCad's `Package_TO_SOT_SMD:SOT-23-5` (JEDEC MO-178 AA, TI's DBV):
pads 1-3 down the left side and 4-5 up the right side (top view), as in Table 4-1. The embedded
STEP is KiCad's `SOT-23-5.step`.
