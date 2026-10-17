# ADP7142

Analog Devices ADP7142ACPZN3.3-R7 (LCSC C659360): 40 V, 200 mA, low-noise (11 uVrms) CMOS LDO,
fixed 3.3 V, 6-lead LFCSP 2 x 2 mm (CP-6-3). Bare part: the input and output capacitors, the EN
drive and an optional soft-start capacitor belong to the board. Evidence is in the docstring of
[`ADP7142.zen`](ADP7142.zen).

```python
ADP7142 = Module("github.com/Team-Micras/MicrasPCB/components/adi/ADP7142/ADP7142.zen")

# 3V3_A from VSYS, enabled by the digital 3V3 so it starts after VDD, SS open (380 us start-up).
ADP7142(name="U9", VIN=VSYS_FILTERED, VOUT=V3V3_A, GND=GND, EN=V3V3, SS=NotConnected())
```

Reference prefix `U`. SENSE/ADJ is tied to `VOUT` inside the package (fixed 3.3 V output); route
that net to the load as one trace. Integration rules (ADP7142 Rev. H):

- VIN and VOUT each need >= 2.2 uF X5R/X7R, >= 1.5 uF effective at the bias voltage, close to the
  pins (Table 2, p14, p20); with more than 2.2 uF on VOUT, raise CIN to match.
- EN: on above 1.30 V, off below 1.06 V (Table 1); EN takes up to 44 V whatever VIN is (Table 3).
- SS: leave open or put a capacitor to GND; never ground it (Table 5).
- Heat: PD = (VIN - 3.3 V) x ILOAD + VIN x IGND; RthJA 72.1 C/W (JEDEC 4-layer, Table 4) to
  182.8 C/W with 25 mm^2 of copper (Table 6). Keep TJ <= 125 C; solder the exposed pad to a
  ground pour with vias.

The test bench ([`test/`](test)) puts the part between an input and an output capacitor
([`ADP7142_rail.zen`](test/ADP7142_rail.zen)) and checks the pinout, the capacitors, the EN
levels, that SS is not grounded, and the junction temperature at 22.5 mA from 17.4 V.

## Pinout (Rev. H Figure 3, Table 5, LFCSP)

| Pad | Name | Symbol type | io |
|---|---|---|---|
| 1 | VOUT | power_out | `VOUT` |
| 2 | SENSE/ADJ | input | `VOUT` |
| 3 | GND | power_in | `GND` |
| 4 | EN | input | `EN` |
| 5 | SS | passive | `SS` |
| 6 | VIN | power_in | `VIN` |
| 7 (EP) | EP | power_in | `GND` |

## Footprint

`LFCSP-6-1EP_2x2mm_P0.65mm_EP1x1.6mm.kicad_mod`: KiCad's `Package_CSP` footprint generated from
ADI's CP-6-3 outline (2 x 2 mm, 0.65 mm pitch, exposed pad 1.0 x 1.6 mm, Rev. H Figure 67), pads
1-3 down the left side and 4-6 up the right side (top view, as Figure 3), exposed pad 7 with
four paste windows. KiCad's `LFCSP-6-1EP_2x2mm_P0.65mm_EP1x1.6mm.step` (2.0 x 2.0 x 0.56 mm) is
embedded (`pcb rectify check`: OK).
