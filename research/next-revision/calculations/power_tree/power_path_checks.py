#!/usr/bin/env python3
"""Battery input, power path and analog LDO numbers of main2 (boards/main2/Regulators.zen).

Run: python3 -I power_path_checks.py   (no dependencies)

1. The pack's short-circuit current against F1's 150 A interrupting rating.
2. 5V_IN programming power (no pack): VSYS through D17, the L6981's dropout, the ADP7142, D17
   against the pack, and VBAT floating on D14's leakage, per battery divider (R44/R45 choice).
3. The ADP7142's junction temperature at its worst-case dissipation, per copper area.
Every input carries its source; ASSUMPTION marks the rest.
"""
import math

print("=== 1. Pack short circuit against F1 (Littelfuse 501: 150 A at 32 VDC, note 1) ===")
# Cells in series carry one current: I = n VCELL / (n RCELL + R_ext) <= VCELL / RCELL.
V_CELL = 4.35  # a full HV cell (research Design basis: 17.4 V for 4S)
# Takeyuta Lab (neophile.hatenablog.com/entry/2023/08/19/143147): 1S cells of 100-220 mAh, AC meter.
CELLS = {"sea jump 180 mAh": 52.82e-3, "Dualsky ECO 150 mAh": 60.08e-3, "sea jump 220 mAh": 72.94e-3,
         "U-K 100 mAh": 73.39e-3, "Hyperion G3 130 mAh": 75.27e-3, "BLLRC 150 mAh": 90.0e-3}
R_EXT = 3.11e-3 + 2 * 10e-3 + 8.4e-3  # F1 cold (Revised 12/14/17), J1 2 x 10 mOhm max (JST PA), 2 x 50 mm 24 AWG
for name, r in CELLS.items():
    print(f"  {name:22s} {r * 1e3:5.1f} mOhm: {V_CELL / r:5.1f} A bound, {4 * V_CELL / (4 * r + R_EXT):5.1f} A with "
          f"F1, J1 and the leads")
print(f"  150 A needs RCELL below {V_CELL / 150 * 1e3:.1f} mOhm (no external resistance).")

print("\n=== 2. 5V_IN programming power (pack absent) ===")
# D17 and D14 are B5819W (JCET B5817W-B5819W): VF 0.6 V max at 1 A (p1); typical curves (p2): VF
# 0.30 V at 0.1 A and 0.48 V at 1 A at 25 C (log-interpolated between); reverse current at 1/5/17 V
# about 5/6/12 uA at 25 C, 55/64/110 uA at 75 C, 0.42/0.59/0.92 mA at 100 C.
def vf_typ(i):
    return 0.30 + (0.48 - 0.30) * math.log10(i / 0.1)


LEAK_5V = {25: 6e-6, 75: 64e-6, 100: 0.59e-3}   # at VR about 5 V
LEAK_17V = {25: 12e-6, 75: 110e-6, 100: 0.92e-3}


def leak(table, t):
    a, b = (25, 75) if t <= 75 else (75, 100)
    return table[a] * (table[b] / table[a]) ** ((t - a) / (b - a))


# 5V_IN loads (calc_power_tree.py section 6): 3V3_D 203 mA (C5 UART flashing), 273 mA (H7 SWD
# flashing, C5 Wi-Fi RX), 586 mA (C5 5 GHz TX peak); 3V3_A 9.7 mA typical, 22.5 mA worst.
CASES = (("C5 UART flashing", 0.203), ("H7 SWD flashing, C5 RX", 0.273), ("C5 TX peak", 0.586))
ETA = 0.85  # ASSUMPTION, as calc_power_tree.py section 6
# L6981 (DS13554 Rev 3): DMAX = 1 - TOFF_MIN x fSW, TOFF_MIN 185 ns typ (no maximum given), fSW 440 kHz
# max (Table 6); Eq. 45 D = (VOUT + (RDSON_LS + DCR) IOUT) / (VIN - (RDSON_HS - RDSON_LS) IOUT), with
# RDSON 0.175 / 0.125 Ohm typ (Table 6) +20 % for temperature (section 9's advice) and L3's DCR
# 130 mOhm max (YSPIA0645-220M); VOUT 3.346 V, the fixed output's maximum (Table 6). VIN 3.5 V min.
DMAX = 1 - 185e-9 * 440e3
RHS, RLS, DCR, VOUT = 0.175 * 1.2, 0.125 * 1.2, 0.130, 3.346
print(f"  L6981 DMAX = 1 - 185 ns x 440 kHz = {DMAX:.4f}")
for vin_port, tag in ((4.75, "high-power port 4.75 V"), (4.40, "low-power port 4.40 V")):
    print(f"  5V_IN at {tag} (USB 2.0 Table 7-7, the minimum at the connector):")
    for name, i33 in CASES:
        i5 = 3.3 * i33 / (ETA * (vin_port - 0.5)) + 9.7e-3
        vsys_t, vsys_w = vin_port - vf_typ(i5), vin_port - 0.6
        need = (VOUT + (RLS + DCR) * i33) / DMAX + (RHS - RLS) * i33
        print(f"    {name:24s}: 5V_IN {i5 * 1e3:4.0f} mA, D17 {vf_typ(i5):.2f} V typ / 0.60 V max -> VSYS "
              f"{vsys_t:.2f} / {vsys_w:.2f} V; the buck regulates from {need:.2f} V: margin "
              f"{vsys_t - need:+.2f} / {vsys_w - need:+.2f} V")
# ADP7142 (Rev K): Table 1's dropout limits (60 mV max at 10 mA, 420 mV at 200 mA) are specified at
# VOUT = 5 V; for the 3.3 V part only Figure 22's typical curve exists, read at about 20 mV at
# 10 mA and 30 mV at 22.5 mA (linear between). +-1.8 % is specified from VIN = VOUT + 1 V.
# LDO_IN = VSYS - 22 Ohm x load.
for vsys, il, tag in ((4.75 - vf_typ(0.25), 9.7e-3, "typical"), (3.8, 22.5e-3, "worst")):
    ldo_in = vsys - 22 * il
    vdo = 0.020 + (0.030 - 0.020) * (il - 0.010) / 0.0125
    out = min(3.3, ldo_in - vdo)
    print(f"  ADP7142 {tag}: VSYS {vsys:.2f} V, {il * 1e3:.1f} mA -> LDO_IN {ldo_in:.2f} V, dropout "
          f"{vdo * 1e3:.0f} mV typ (Figure 22) -> 3V3_A about {out:.2f} V, not guaranteed below VOUT + 1 V")
print("  D17 with the pack in (VSYS 11.4-17.4 V, 24.2 V clamp; 5V_IN 0-5.25 V): VR up to 24.2 V, 61 % of 40 V; "
      "reverse current into 5V_IN " + ", ".join(f"{t} C {leak(LEAK_17V, t) * 1e6:.0f} uA" for t in (25, 50, 85)))
print("  D17 dissipation at the TX peak: "
      f"{(3.3 * 0.586 / (ETA * 4.25) + 9.7e-3) * vf_typ(0.55):.2f} W against Pd 0.5 W (p1)")

# VBAT with only 5V_IN: D14 reverse-biased by VSYS (about 4.4 V); its leakage flows into VBAT, whose
# DC sink is the battery divider (the DRV8874s' 1 uA sleep current and D15's leakage ignored, which
# only pull VBAT lower). VBAT cannot rise above VSYS. DRV8874 UVLO rising 4.3-4.6 V (SLVSF66A 6.5);
# STSPIN958 VS turn-on 5.05 V max (DS14341 Table 5). Per divider, also PC5 at the 24.2 V clamp
# against PC5's 4.0 V absolute maximum (a TT_ha pin, DS13311 Rev 5 Table 10; no positive injection,
# Table 11) and VDDA (3.24 V min).
VSYS_5V = 4.4
for r44, r45 in ((10e3, 2e3), (100e3, 20e3), (200e3, 22e3), (20e3, 2e3)):
    ratio = (r44 + r45) / r45
    lo = (r44 * 0.99 + r45 * 1.01) / (r45 * 1.01)  # 1 % parts, the lowest ratio
    sink = r44 + r45
    floats = ", ".join(f"{t} C {min(leak(LEAK_5V, t) * sink, VSYS_5V):.2f} V" for t in (25, 50, 70, 85))
    print(f"  {r44 / 1e3:g}k/{r45 / 1e3:g}k (ratio {ratio:.2f}, Thevenin {r44 * r45 / sink / 1e3:.2f} kOhm, "
          f"{17.4 / sink * 1e3:.2f} mA from the pack): PC5 {17.4 / ratio:.2f} V at 17.4 V, {24.2 / lo:.2f} V at the "
          f"24.2 V clamp; VBAT on 5V_IN alone: {floats}")
# With the pack fitted and SW4 off, Q6's off-state leakage flows pack -> VBAT -> divider -> GND ->
# Q6 -> GND_BAT and adds to D14's. HSBB3072 specifies IDSS only at 25 C (1 uA max, p2). ASSUMPTION: 0.5 V of
# VBAT is allowed for it at 85 C, and the leakage that would bring VBAT to the DRV8874's 4.3 V UVLO
# minimum is printed.
d14_85 = leak(LEAK_5V, 85) * 22e3
print(f"  20k/2k, pack in, SW4 off, 85 C: D14 {d14_85:.2f} V + Q6 0.5 V (23 uA, allowed) = {d14_85 + 0.5:.2f} V; "
      f"the 4.3 V UVLO minimum is reached at {(4.3 - d14_85) / 22e3 * 1e6:.0f} uA of Q6 leakage")
print("\n=== 3. ADP7142 junction temperature at the worst case ===")
VIN, IL, IGND = 17.4, 22.5e-3, 190e-6  # VSYS max; research 3V3_A worst case; Rev K Table 1
PD = (VIN - 3.24) * IL + VIN * IGND
print(f"  PD = ({VIN} - 3.24) x {IL * 1e3} mA + {VIN} x {IGND * 1e6:.0f} uA = {PD:.3f} W")
for tag, th in (("Table 6, 25 mm2 (minimum traces)", 182.8), ("Table 6, 100 mm2", 142.6),
                ("Figures 53-54, the 500 mm2 line", 143.0), ("Table 6, 500 mm2", 83.9),
                ("Table 4, JEDEC 4-layer", 72.1), ("Table 6, 1000 mm2", 71.7)):
    print(f"  {tag:34s} {th:6.1f} C/W: +{PD * th:4.1f} K, TJ {85 + PD * th:5.1f} C at 85 C ambient; "
          f"125 C up to {125 - PD * th:5.1f} C ambient")
