# TSC2020

Bidirectional current-sense amplifier, fixed gain 20 V/V, input common mode -4 to 100 V
independent of the supply (STMicroelectronics TSC2020IYST, MiniSO8). Bare part: the VCC bypass
capacitor and the reference source belong to the board. Evidence and datasheet references are in
the docstring of [`TSC2020.zen`](TSC2020.zen).

```python
TSC2020 = Module("github.com/Team-Micras/MicrasPCB/components/st/TSC2020/TSC2020.zen")

# Split supply (Figure 56): VREF1 on VCC, VREF2 on GND, output centred on VCC/2.
TSC2020(name="IC4", VCC=V3V3, GND=GND, IN_P=SENSE_P, IN_N=SENSE_N, VREF1=V3V3, VREF2=GND, OUT=CURRENT)
```

Reference prefix `IC`. MPN `TSC2020IYST`, STMicroelectronics, LCSC C27345609.

## Pinout (DS14393 Rev 7 Table 1, SO8/MiniSO8 column)

| Pin | Name | Symbol type | io |
|---|---|---|---|
| 1 | IN- | input | `IN_N` |
| 2 | GND | power_in | `GND` |
| 3 | VREF2 | input | `VREF2` |
| 4 | NC | no_connect | (left open) |
| 5 | OUT | output | `OUT` |
| 6 | VCC | power_in | `VCC` |
| 7 | VREF1 | input | `VREF1` |
| 8 | IN+ | input | `IN_P` |

`VCC` declares the 2.7-5.5 V operating range (Table 3). The TSSOP8 variants (TSC2020IPT,
TSC2020IYPT) use another pin numbering (Table 1) and do not fit this symbol.

## Footprint

`SOP65P490X110-8N.kicad_mod`: MiniSO8 (MSOP-8) 3 x 3 mm, 0.65 mm pitch, from the Micras Altium
library (MicrasLib), with its STEP model (`TSC2020IYST.stp`) embedded. `pcb rectify check`: OK.
Package dimensions: Table 7.

Courtyard: an F.CrtYd rectangle around the body outline (User.13) and the pads, 0.25 mm, the
IPC-7351B nominal courtyard excess (KiCad Library Conventions F5.3).

## Design requirements (board side)

- Output (equation 3): VOUT = (IN+ - IN-) x 20 + (VREF1 + VREF2) / 2. Gain error 0.3 % max over
  VOUT 100 mV to VCC - 100 mV (Table 4).
- VCC bypass (section 5.11, p.31): 100 nF between VCC and GND, as close as possible to the pins.
- VREF (section 5.11): driven by a low-impedance source, optional 10 nF bypass; buffer a resistor
  divider (Figure 58).
- Common mode (Table 3): IN+ and IN- from -4 to 100 V; differential at most +-70 V (Table 2).
- Input filter (section 5.8): not required; filter the output instead, and keep any input resistor
  at 10 ohm or lower.
- Output load (Table 4, section 5.9): at most 1 nF directly; larger loads need a series resistor
  (Figure 66).
- Layout (section 5.12): Kelvin connection to shunts below 1 ohm, IN+/IN- routed as a matched
  pair without vias.
