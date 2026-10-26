#!/usr/bin/env python3
"""Battery input, power path and analog LDO numbers of main2 (boards/main2/Regulators.zen).

Run: python3 -I power_path_checks.py   (no dependencies)

1. The pack's short-circuit current against F1's 150 A interrupting rating.
2. VBAT on USB alone: D14's and Q6's leakage against the battery divider, and Q8's gate.
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

print("\n=== 2. VBAT on USB alone (pack absent, or fitted with SW4 off) ===")
# D14 B5819W reverse current, typical (JCET B5817W-B5819W p2, read at 1-5 V): 25 C 5-6 uA, 75 C
# 55-64 uA, 100 C 0.42-0.59 mA. Log-interpolated at VR about 2.5 V.
LEAK = {25: 5.5e-6, 75: 58e-6, 100: 480e-6}


def d14_leak(t):
    if t <= 75:
        a, b = 25, 75
    else:
        a, b = 75, 100
    return LEAK[a] * (LEAK[b] / LEAK[a]) ** ((t - a) / (b - a))


def q6_idss(t):
    # HSBB3072 p2: IDSS 1 uA max at 25 C and 5 uA at 55 C (VDS 24 V); ASSUMPTION: the same x5 per
    # 30 K above 55 C.
    return 1e-6 * 5 ** ((t - 25) / 30)


R56, R57 = 10e3, 1e6
VBUS_MIN = 4.4
for r44, r45, tag in ((100e3, 20e3, "100k/20k"), (10e3, 2e3, "10k/2k")):
    r_sink = 1 / (1 / (r44 + r45) + 1 / (R56 + R57))
    print(f"  divider {tag}: VBAT to GND {r_sink / 1e3:.1f} kOhm")
    for t in (25, 40, 50, 60, 70, 85):
        i = d14_leak(t) + q6_idss(t)
        v = i * r_sink
        vgs = v * R57 / (R56 + R57) - VBUS_MIN
        state = "on" if vgs <= -1.8 else ("marginal" if vgs <= -1.3 else "OFF (body diode)")
        print(f"    {t:3d} C: leakage {i * 1e6:6.1f} uA -> VBAT {min(v, VBUS_MIN):5.2f} V{'+' if v > VBUS_MIN else ' '}, "
              f"Q8 VGS {max(vgs, -VBUS_MIN) if v <= VBUS_MIN else 0.0:6.2f} V at VBUS 4.4 V: {state}")
print("  Q8 on: VGS at least 0.5 V beyond its -1.3 V maximum threshold (AO3401A p2).")

print("\n=== 3. ADP7142 junction temperature at the worst case ===")
VIN, IL, IGND = 17.4, 22.5e-3, 190e-6  # VSYS max; research 3V3_A worst case; Rev K Table 1
PD = (VIN - 3.24) * IL + VIN * IGND
print(f"  PD = ({VIN} - 3.24) x {IL * 1e3} mA + {VIN} x {IGND * 1e6:.0f} uA = {PD:.3f} W")
for tag, th in (("Table 6, 25 mm2 (minimum traces)", 182.8), ("Table 6, 100 mm2", 142.6),
                ("Figures 53-54, the 500 mm2 line", 143.0), ("Table 6, 500 mm2", 83.9),
                ("Table 4, JEDEC 4-layer", 72.1), ("Table 6, 1000 mm2", 71.7)):
    print(f"  {tag:34s} {th:6.1f} C/W: +{PD * th:4.1f} K, TJ {85 + PD * th:5.1f} C at 85 C ambient; "
          f"125 C up to {125 - PD * th:5.1f} C ambient")
