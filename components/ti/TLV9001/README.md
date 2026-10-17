# TLV9001

Texas Instruments TLV9001IDBVR (LCSC C398363): 1 MHz, 2 V/us, rail-to-rail input and output op
amp, 60 uA, 1.8-5.5 V, SOT-23-5. Bare part: the bypass capacitor and the feedback network belong
to the board. Evidence is in the docstring of [`TLV9001.zen`](TLV9001.zen).

```python
TLV9001 = Module("github.com/Team-Micras/MicrasPCB/components/ti/TLV9001/TLV9001.zen")

# IR emitter constant-current sink: set-point on IN+, sense resistor on IN-, OUT to the FET gate.
TLV9001(name="U12", VCC=V3V3_A, GND=GND, IN_P=SINK_SET, IN_N=SINK_FB, OUT=SINK_OUT)
```

Reference prefix `U`. Only the TLV9001**I**DBVR pinout is modelled: the TLV9001U in the same
DBV package has another pinout (SBOS833R Figure 6-2).

## Why this op amp

The next main board's emitter sink (research/next-revision, "IR emitters", A.4;
`boards/main2/Sensors.zen`): op amp + AO3400A + 1.2 Ohm 0.1 % sense, 175 mA (0.21 V), set-point
from the MCU's DAC, supplied from 3V3_A on a ~100 uA budget, settling within a few us of a 150 us
pulse, driving the AO3400A gate (Ciss 630 pF) through a small resistor.

| Part | GBW | Slew | IQ typ / max | VOS max (25 C) | Input range | Cap. load | LCSC (JLC, 2026-10-15) |
|---|---|---|---|---|---|---|---|
| **TLV9001** (SBOS833R) | 1 MHz | 2 V/us | 60 / 77 uA | +-1.6 mV (0.8 % of 0.204 V) | RRI, -0.1 V to V+ + 0.1 V | 500 pF drive; 1200 Ohm resistive ZO | C398363, $0.098, 39 k |
| TLV9061 (SBOS839N) | 10 MHz | 6.5 V/us | 538 / 750 uA | +-1.6 mV | RRI | PM 55 deg at G = 1 | C398358, $0.093 |
| OPA376 (SBOS406G) | 5.5 MHz | 2 V/us | 760 / 950 uA | 25 uV | RRI | see curves | C42134, $2.25 |
| MCP6001 (DS20001733L) | 1 MHz | 0.6 V/us | 100 / 170 uA | +-4.5 mV (2.2 %) | RRI, VSS - 0.3 V to VDD + 0.3 V | 45 deg PM at 500 pF | C116490, $0.32 |
| LMV321 (SLOS263Y) | 1 MHz | 1 V/us | 80 / 170 uA (2.7 V) | 7 mV (3.4 %) | 0 to VCC - 0.8 V | PM 60 deg (CL 200 pF) | C7972, $0.12 |
| OPA313 (SBOS649C) | 1 MHz | 0.5 V/us | 50 uA | 2.5 mV (1.2 %) | RRI | up to 150 pF | not queried |

The TLV9001 is the one inside the quiescent budget with the slew rate (2 V/us: 0 to 2.5 V in
about 1.3 us, plus 0.85 us overload recovery from the off state), the offset (+-1.6 mV, +-2 mV
over temperature: at most 1 % of the set-point) and the capacitive-load drive the sink needs. The
TLV9061 and OPA376 are faster or more precise but draw 5-10 times the budget; the MCP6001 and
LMV321 meet the bandwidth but their offsets (2-3 % of the set-point) and slower or similar slew
gain nothing; the OPA313 slews four times slower and drives only 150 pF.

The AO3400A's 630 pF Ciss is above the 500 pF rated drive, and Figure 7-26 gives about 30 deg
phase margin at 600 pF (G = 1). main2 closes the loop through an integrator (1 kOhm from the sense
resistor to IN-, 1 nF from OUT to IN-), which a behavioural model settles without overshoot
(research/next-revision/calculations/emitter/emitter_sink.py). TODO: confirm the step on the bench,
across the sense resistor.

## Pinout (SBOS833R Figure 6-1, Table 6-1, TLV9001 DBV)

| Pad | Name | Symbol type | io |
|---|---|---|---|
| 1 | OUT | output | `OUT` |
| 2 | V- | power_in | `GND` |
| 3 | IN+ | input | `IN_P` |
| 4 | IN- | input | `IN_N` |
| 5 | V+ | power_in | `VCC` |

## Footprint

`SOT-23-5.kicad_mod` is KiCad's `Package_TO_SOT_SMD:SOT-23-5` (JEDEC MO-178 AA, TI's DBV), the
same file as `components/ti/TLV7041`: pads 1-3 down the left side and 4-5 up the right side (top
view), as in Figure 6-1. The embedded STEP is KiCad's `SOT-23-5.step` (`pcb rectify check`: OK).
