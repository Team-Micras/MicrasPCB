# DRV8874

Brushed DC H-bridge with integrated current sense and regulation (Texas Instruments DRV8874PWPR,
**HTSSOP-16 PowerPAD**, PWP0016J), 4.5-37 V, 6 A peak, 200 mOhm high side + low side. Bare part:
the charge-pump capacitors, decoupling, RIPROPI, the VREF divider, the PMODE/IMODE straps and the
nFAULT pull-up belong to the board. Evidence and datasheet references (TI SLVSF66A) are in the
docstring of [`DRV8874.zen`](DRV8874.zen); the board-side rules are checked by
[`checks.zen`](checks.zen).

```python
DRV8874 = Module("github.com/Team-Micras/MicrasPCB/components/ti/DRV8874/DRV8874.zen")

# PH/EN mode (PMODE = GND), fixed off-time with auto retry (IMODE = GND).
DRV8874(
    name="IC5",
    VM=VBAT, GND=GND, VCP=VCP_R, CPH=CPH_R, CPL=CPL_R,
    EN_IN1=MOTOR_R_PWM, PH_IN2=MOTOR_R_DIR, NSLEEP=MOTORS_ENABLE, NFAULT=MOTORS_NFAULT,
    VREF=VREF_R, IPROPI=IPROPI_R, IMODE=GND, PMODE=GND,
    OUT1=MOTOR_R_A, OUT2=MOTOR_R_B,
)
```

Reference prefix `IC`. MPN `DRV8874PWPR` (tape and reel, Package Option Addendum), Texas
Instruments, LCSC C1855818.

## Pinout (SLVSF66A Pin Functions, p3)

| Pad | Name | Symbol type | io |
|---|---|---|---|
| 1 | EN/IN1 | input | `EN_IN1` |
| 2 | PH/IN2 | input | `PH_IN2` |
| 3 | nSLEEP | input | `NSLEEP` |
| 4 | nFAULT | open collector (open drain) | `NFAULT` |
| 5 | VREF | input | `VREF` |
| 6 | IPROPI | output (current) | `IPROPI` |
| 7 | IMODE | input (quad-level) | `IMODE` |
| 8 | OUT1 | output | `OUT1` |
| 9 | PGND | power_in | `GND` |
| 10 | OUT2 | output | `OUT2` |
| 11 | VM | power_in | `VM` |
| 12 | VCP | passive (charge-pump output) | `VCP` |
| 13 | CPH | passive (flying capacitor) | `CPH` |
| 14 | CPL | passive (flying capacitor) | `CPL` |
| 15 | GND | power_in | `GND` |
| 16 | PMODE | input (tri-level) | `PMODE` |
| 17 | PAD (thermal pad) | power_in | `GND` |

GND, PGND and PAD share the `GND` io (section 10.1: "not intended to be isolated from each
other"). `VM` declares the recommended 4.5-37 V (section 6.3); a 4S pack (17.4 V with HV cells)
stays inside it with margin to the 40 V absolute maximum.

## Footprint

`Texas_PWP0016J_HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm_Mask2.46x3.55mm.kicad_mod`, drawn from
TI's PWP0016J drawings in SLVSF66A (4223595/B):

- Land pattern (p40, Example Board Layout): 16 pads 1.5 x 0.45 mm, R0.05 mm corners, 0.65 mm
  pitch, pad centres 5.8 mm apart (x = +-2.9 mm). Thermal pad 17: 3.4 x 5.0 mm copper (note 8:
  "size of metal pad may vary due to creepage requirement"), solder-mask-defined 2.46 x 3.55 mm
  opening (a separate F.Mask aperture, as the KiCad library does), `zone_connect` solid.
- Paste: signal pads 1:1 (p41, Example Stencil Design). The thermal pad's paste is split for
  thermal vias left open (no via-in-pad process): six windows, two columns x = +-0.2 to +-1.18 mm
  by three rows y = -1.6 to -0.8, -0.4 to +0.4, +0.8 to +1.6 mm, 54 % of the 2.46 x 3.55 mm opening,
  each 0.2 mm clear of the via grid's centres. TI's p41 opening is the full 2.46 x 3.55 mm (0.125 mm
  stencil) over vias its note 9 asks filled, plugged or tented; TI SLUA271C section 4.4 asks 50-70 %
  paste coverage on an exposed pad, in windows that let it outgas.
- Thermal vias (p40; section 10.1 "A recommended land pattern for the thermal vias is provided in
  the package drawing section"): 12 vias of 0.2 mm, a 3 x 4 grid at 1.2 mm pitch (x = -1.2, 0,
  +1.2 mm; y = +-0.6, +-1.8 mm). They are drawn on **Cmts.User** as a guide, not as footprint
  pads: the layout places them as GND board vias inside pad 17. Footprint through-hole pads
  would count as 0.2 mm PTH holes in DFM (JLCPCB prefers 0.5 mm PTH, 0.2 mm vias,
  `rules/jlcpcb-pdk.toml`) and make `pcb rectify` read the footprint as mixed technology.
  Note 9 asks "vias under paste be filled, plugged or tented"; the split paste keeps them out from
  under it, so they can stay open on both sides (tenting a pad's via from the back traps air, TI
  SLUA271C section 3.4.1). Section 8.2.1.2.3 simulates the thermal vias on the same 1.2 mm grid, with an inner
  GND plane and the largest top-copper area that fits (section 10.1).
- Body 4.4 x 5.0 mm on F.Fab (p39: 4.3-4.5 x 4.9-5.1 mm), pin-1 corner chamfered; silkscreen on
  the body's top and bottom edges, the top one extended over pin 1; F.CrtYd 0.25 mm (IPC-7351B
  nominal) around pads and body (7.8 x 5.5 mm).
- 3D model `DRV8874PWPR_PWP0016J.step` (embedded): written for this package with CadQuery from
  the p39 nominal dimensions (body 4.4 x 5.0 mm, 1.2 mm maximum height, 0.1 mm standoff, lead
  span 6.4 mm, leads 0.24 x 0.15 mm, foot 0.6 mm, pin-1 dimple), thermal pad at its maximum
  2.46 x 3.55 mm. Neither TI (the model is behind a CAD vendor login) nor the KiCad library
  provide a PWP0016J model: the KiCad HTSSOP-16 models have other exposed-pad sizes.
  `pcb rectify check`: OK.

## Design requirements (board side)

`checks.zen` turns these into a test-bench check, `drv8874_requirements`, that a board bench
loads; `drv8874_settings` decodes each driver's PMODE/IMODE and its ITRIP band so the bench can
also assert the design's choices. The package's own bench (`test/test_DRV8874.zen`) runs it on
the Figure 19 circuit in `test/application.zen`, for each legal strap, and shows each rule
firing on a circuit that breaks it.

- Capacitors (Table 1): CVM1 0.1 uF low-ESR ceramic VM to GND plus bulk (CVM2), both VM-rated;
  CVCP 100 nF X5R/X7R 16 V VCP to VM; CFLY 22 nF X5R/X7R VM-rated CPH to CPL; all close to the
  pins (section 10.1). Section 9.1 leaves the bulk value to the system.
- Current sense (section 7.3.3): RIPROPI to GND; IPROPI = (ILS1 + ILS2) x 450 uA/A, low-side
  FETs only (reads in drive and brake, not in coast). IPROPI current at most 3 mA (section 6.3).
  An optional 10 nF on IPROPI filters transients longer than tDEG (section 7.3.3.2).
- Current regulation: ITRIP = VREF / (RIPROPI x 450 uA/A) (equation 3), VREF 0-3.6 V (section
  6.3). For example 2.0 kOhm and 2.70 V (10 kOhm / 45.3 kOhm from 3.3 V) give 3.0 A typical,
  2.81-3.22 A with AERR +-5.5 % and 1 % resistors. Disable it with IPROPI on GND and VREF above
  GND (section 7.3.3.2); PMODE Hi-Z disables it too.
- PMODE (Table 2): GND = PH/EN, 1.5-5.5 V = PWM, open = independent half-bridge. IMODE
  (Table 6): GND = fixed off-time + retry; 20 kOhm = cycle-by-cycle + retry (nFAULT pulses at
  every chop, Figure 14); 62 kOhm = cycle-by-cycle + latched; open = fixed off-time + latched.
  Both latch when nSLEEP goes high.
- nFAULT: open drain, pull-up to at most 5.5 V, at most 5 mA (section 6.3, Table 1); Figure 19
  uses 10 kOhm to VCC. Wired-OR of several drivers on one pull-up works.
- nSLEEP and the inputs have 100 kOhm pull-downs (section 6.5): a board pull-down on nSLEEP keeps
  the bridge asleep while the controller is in reset. Logic inputs 0-5.5 V; PWM up to 100 kHz.
- Protection: OCP 6 A minimum, 10 A typical, no maximum (section 6.5): set ITRIP below 6 A with
  margin for the blanking overshoot (tBLK 1.1 us + tDEG 0.6 us).
- Thermal: RthJA 36 C/W on the JEDEC board (section 6.4); the thermal pad to the ground planes
  through the via grid above.
