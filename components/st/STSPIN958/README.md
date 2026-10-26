# STSPIN958

5 A driver for brushed DC motors (STMicroelectronics STSPIN958TR, VFQFPN32 5 x 5 mm with exposed
pad), 5.05-58 V: dual half-bridge, single full-bridge or parallel half-bridge, with a current
limiter (fixed off-time or PWM trimming), two x10 sense amplifiers, overcurrent, UVLO and thermal
protection. Bare part: the charge-pump capacitors, decoupling, sense resistor, mode straps and
the EN/nFAULT network belong to the board. Evidence and datasheet references are in the
docstring of [`STSPIN958.zen`](STSPIN958.zen).

```python
STSPIN958 = Module("github.com/Team-Micras/MicrasPCB/components/st/STSPIN958/STSPIN958.zen")

# Parallel half-bridge mode: the board ties OUT1 to OUT2 and LSS1 to LSS2 (section 5.4.3).
STSPIN958(
    name="IC6",
    VS=VBAT, VDD=V3V3, GND=GND,
    VSPUMP=CBOOT_LOW, VBOOT=CBOOT_HIGH, CP1=CFLY_1, CP2=CFLY_2,
    OUT1=FAN_OUT, OUT2=FAN_OUT, LSS1=FAN_LSS, LSS2=FAN_LSS,
    V1=NotConnected(), V2=NotConnected(),
    PWM1=FAN_PWM, PWM2_PH=PH, EN_NFAULT=FAN_EN, NSTBY=V3V3,
    MODE1=V3V3, MODE2=GND, MODE3=V3V3, OFFSET=GND,
    REF=FAN_REF, TOFF=FAN_TOFF, SR=FAN_SR,
)
```

Reference prefix `IC`. MPN `STSPIN958TR` (orderable code, DS14341 Table 14), STMicroelectronics,
LCSC C20033901.

## Pinout (DS14341 Figure 2, Table 6)

| Pad | Name | Symbol type | io |
|---|---|---|---|
| 1, 2 | LSS1 | passive | `LSS1` |
| 3 | GNDPUMP | power_in | `GND` |
| 4 | VSPUMP | passive (internally connected to VS) | `VSPUMP` |
| 5 | CP1 | output | `CP1` |
| 6 | CP2 | output | `CP2` |
| 7 | VBOOT | passive (charge-pump output on CBOOT) | `VBOOT` |
| 8 | V1 | output | `V1` |
| 9 | OFFSET | input | `OFFSET` |
| 10 | nSTBY | input | `NSTBY` |
| 11 | PWM1 | input | `PWM1` |
| 12 | PWM2/PH | input | `PWM2_PH` |
| 13 | VDD | power_in | `VDD` |
| 14 | EN/nFAULT | bidirectional (input + open drain) | `EN_NFAULT` |
| 15 | REF | input | `REF` |
| 16 | TOFF | bidirectional (RC input or decay output) | `TOFF` |
| 17 | V2 | output | `V2` |
| 18 | MODE3 | input | `MODE3` |
| 19 | MODE2 | input | `MODE2` |
| 20 | MODE1 | input | `MODE1` |
| 21 | SR | input | `SR` |
| 22 | GND | power_in | `GND` |
| 23, 24 | LSS2 | passive | `LSS2` |
| 25, 26 | OUT2 | passive | `OUT2` |
| 27, 28, 29, 30 | VS | power_in | `VS` |
| 31, 32 | OUT1 | passive | `OUT1` |
| 33 | EPAD | power_in | `GND` |

Every pad is its own symbol pin. Pads with the same datasheet name share that name, so one io
reaches all of them (VS reaches 27-30, OUT1 reaches 31-32, and so on). The two half-bridges stay
separate ios: a board in parallel mode ties OUT1 to OUT2 and LSS1 to LSS2 by passing the same
net to both. The power-stage pins are passive because parallel mode shorts two outputs together.
`VS` declares 5.05-58 V and `VDD` 2.8-3.6 V (Table 2).

## Footprint

`QFN50P500X500X100-33N-D.kicad_mod`: VFQFPN32 5 x 5 mm, 0.5 mm pitch, 3.8 x 3.8 mm exposed pad,
from the Micras Altium library (MicrasLib), with its STEP model (`STSPIN958.stp`) embedded.
`pcb rectify check`: OK. The land differs slightly from the recommended footprint (Figure 25:
0.80 x 0.25 mm pads, 4.06 mm inner span): its pads are 0.80 x 0.30 mm centred 2.5 mm from the
package centre (4.2 mm inner span). The exposed pad matches (3.80 mm).

`paste` (config, default `"whole"`): `"split"` takes
`QFN50P500X500X100-33N-D_SplitPaste.kicad_mod`, the same land (Figure 25 gives no stencil) with
the exposed pad's paste in four 1.09 x 1.7 mm windows (51 % of the pad) clear of three 0.36 mm
lanes at x = -1.45, 0, +1.45 mm that hold nine via sites, 0.2 mm circles on Cmts.User, where the
layout places its vias (TI SLUA271C (QFN and SON PCB Attachment) section 4.4: exposed-pad paste in windows covering 50-70 % of the pad, which lets it outgas; section 3.4.1: a smaller via loses less solder, and tenting a pad's via from the back traps air).

Courtyard: an F.CrtYd rectangle around the body outline (User.13) and the pads, 0.25 mm, the
IPC-7351B nominal courtyard excess (KiCad Library Conventions F5.3).

## Design requirements (board side)

- Mode straps (Table 8): MODE1/2/3 tied to GND or VDD (or left open: internal pull-ups), never
  changed in operation. H L H = parallel half-bridge with PWM trimming.
- Parallel mode (section 5.4.3): OUT1 = OUT2 and LSS1 = LSS2.
- PWM2/PH in parallel mode (sections 5.6.1.2, 5.6.2.2, Figures 11 and 14): PH = 0 -> low side
  on during the limiter decay, drawn with the load between OUT and LSS; PH = 1 -> output high-Z,
  drawn with the load between VS and OUT. In PWM trimming the device resumes when PWM1 goes low
  (PH = 0) or high (PH = 1). A check can compare PH with the load connection.
- Current limit (section 5.6, equation 1): VREF = I_peak x RSENSE x ACL + VAMPoffset, ACL 10 V/V
  (9.5-10.5, Table 5), VAMPoffset 0 (OFFSET low) or VDD/2 (OFFSET high). REF 0.1 V to VDD
  (Table 2). Overcurrent protection trips at 7-14 A (Table 5).
- VS (section 8, Table 12): two 470 nF low-ESR ceramics at the VS pins plus bulk (220 uF);
  dVS/dt at most 0.5 V/us (Table 1).
- VDD (section 8): 220 nF low-ESR ceramic at the pin.
- Charge pump (section 8, Table 2): 100 nF CP1-CP2 and 1 uF VBOOT-VSPUMP, both rated 16 V.
  VSPUMP may also be shorted to VS (Table 6, Figure 4).
- Sense resistor (Table 12, section 8): 50 mohm / 3 W from LSS to GND, next to the pins, same
  layer. VLSS -0.6 to +1 V (Table 2).
- EN/nFAULT (Table 12): 39 kohm pull-up, 10 nF to GND. VIH(EN) 2.55 V (Table 5).
- SR (Table 7): 1 k / 2.2 k / 5.6 k / 10 kohm -> 2 / 1.2 / 0.6 / 0.3 V/ns.
- TOFF (section 5.6): ROFF/COFF to GND in fixed off-time mode; digital decay output in PWM
  trimming mode.
- Logic inputs are 5 V tolerant except MODE1-3 and OFFSET, which must stay at or below VDD
  (Table 1, Table 2).
