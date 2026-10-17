"""Fan PWM driver for Micras on 4S (12.0-16.8 V, 17.4 V HV) and a generic drone-class brushed coreless fan.

Tags: [DS] datasheet, [W] vendor web listing (secondary), [A] assumption, [I] inference.
Run: python3 -I fan_driver_calc.py
"""

import math

VBUS = [12.0, 14.8, 16.8, 17.4]
VB = 16.8

# ---------------------------------------------------------------------------------------------
# 1. Drone-class coreless motors: published figures
# (name, rated V, no-load rpm, R ohm, stall A, source)
MOTORS = [
    ("NFP-D0615-1 (6x15)", 3.4, 59000, 1.0, 3.25, "[W] nfpshop NFP-D0615 listing (search snippet; page refused fetch)"),
    ("NFP-D0615-2 (6x15)", 3.4, 53000, 1.2, 2.76, "[W] same"),
    ("NFP-D0720-2184-1 (7x20)", 3.0, 49000, 0.4, 6.73, "[W] microdcmotors NFP-D0720 listing (snippet)"),
    ("NFP-D0720-2184-2 (7x20)", 3.0, 42000, 0.5, 5.54, "[W] same"),
    ("NFP-D0816-3-3.4 (8x16, KOGUMA fan)", 3.4, 53000, 0.4, 8.65, "[W] nfpmotor NFP-D0816 listing (snippet; page also lists other variants)"),
    ("Racerstar 8520 (8.5x20)", 3.7, 53500, 0.4, 10.57, "[W] racerstar.com product page"),
    ("Bitcraze 7x20 (Crazyflie upgrade)", None, None, 0.75, None, "[W] store.bitcraze.io: 0.75 ohm +-20 %, 13000 rpm/V +-15 %"),
    ("RIC-1020DT-037450 (10x20)", 3.7, 45000, 0.23, 16.4, "[W] via MicrasHardware fan_study.md"),
    ("NFP-D1020T-1437 (10x20, 2S)", 7.4, 51500, 0.5, 15.7, "[W] via fan_study.md (snippet)"),
    ("RIC-1020DT-074400 (10x20, 2S)", 7.4, 39500, 0.83, 8.9, "[W] via fan_study.md"),
]
# Faulhaber precision coreless: (name, kn rpm/V, R, L uH) [DS Faulhaber 1024 SR, 0816 SR, 0615 S datasheets]
FAULHABER = [("1024 K 003 SR", 4100, 1.36, 16.0), ("0816 K 003 SR", 4530, 5.4, 53.0), ("0615 N 1,5 S", 13800, 3.9, 12.0)]


def hdr(t):
    print("\n" + "=" * 104 + "\n" + t + "\n" + "=" * 104)


hdr("1. Drone-class coreless motors (published) and inductance scaled from Faulhaber (L ~ 1/kv^2, same turns law)")
print(f"  {'motor':38} {'V':>4} {'rpm0':>6} {'kv':>6} {'R':>5} {'Istall':>6}  L est. from 1024/0816/0615 [I]")
for name, v, rpm, R, ist, src in MOTORS:
    kv = rpm / v if v else 13000.0
    Ls = [Lr * (kn / kv) ** 2 for _, kn, _, Lr in FAULHABER]
    vs = f"{v:4.1f}" if v else "  - "
    rs = f"{rpm:6d}" if rpm else "     -"
    iss = f"{ist:6.2f}" if ist else "     -"
    print(f"  {name:38} {vs} {rs} {kv:6.0f} {R:5.2f} {iss}  {Ls[0]:4.1f} / {Ls[1]:4.1f} / {Ls[2]:4.1f} uH")
print("  Faulhaber electrical time constants L/R: " + ", ".join(f"{n} {L/R:.1f} us" for n, _, R, L in FAULHABER))
print("  -> generic fan model used below: R 0.2-1.2 ohm, L 1-10 uH (nominal 3 uH for a 1S, 8 uH for a 2S motor) [I]")

# ---------------------------------------------------------------------------------------------
hdr("2. Duty on 4S, on-time per period, and what minimum pulses do")
print("  motor class: 1S (rated 3.7 V), 2S (rated 7.4 V); an idle/low setting of 1.0 V shown too")
for f in (50e3, 100e3, 200e3, 400e3, 500e3):
    T = 1 / f
    cells = []
    for v in (1.0, 3.7, 7.4):
        d = v / VB
        cells.append(f"{v:3.1f} V: D {d*100:4.1f} % = {d*T*1e9:5.0f} ns")
    res = 1 / (275.2e6 / f)  # TIM12 counts per period (fan_study: ARR 687 -> 400 kHz)
    print(f"  {f/1e3:3.0f} kHz (T {T*1e6:5.2f} us, {275.2e6/f:5.0f} timer steps = {VB*res*1e3:4.0f} mV/step): " + " | ".join(cells))
MINPULSE = {"STSPIN958 (280 ns, DS Table 2)": 280e-9}
for k, tp in MINPULSE.items():
    for f in (100e3, 200e3, 400e3, 500e3):
        print(f"  {k}: at {f/1e3:3.0f} kHz min duty {tp*f*100:4.1f} % = {tp*f*VB:4.2f} V on 16.8 V")

# ---------------------------------------------------------------------------------------------
hdr("3. Locked-rotor current from 4S (start-up / stall) and the floor set by a minimum pulse")
paths = {"0.10 ohm path (driver+wires) [A]": 0.10, "0.50 ohm path (0.45 ohm H-bridge + wires)": 0.50}
for R in (0.23, 0.4, 0.75, 1.2):
    row = [f"R {R:4.2f}:"]
    for pn, rp in paths.items():
        row.append(f"{pn.split()[0]} path {VB/(R+rp):5.1f} A")
    print("  " + "  ".join(row) + "   (battery IR not included: upper bound)")
for f in (100e3, 400e3, 500e3):
    d = 280e-9 * f
    print(f"  STSPIN958 280 ns at {f/1e3:3.0f} kHz: stalled 0.4 ohm motor at min duty draws {d*VB/(0.4+0.1):4.1f} A -> REF limiter must do the soft start")

# ---------------------------------------------------------------------------------------------
def ripple_pp(vb, d, f, L, R):
    T = 1 / f
    tau = L / R
    a, b, c = math.exp(-d * T / tau), math.exp(-(1 - d) * T / tau), math.exp(-T / tau)
    return vb / R * (1 - a) * (1 - b) / (1 - c)


hdr("4. Ripple vs PWM frequency, generic motor, 16.8 V bus (pp A / extra winding loss W)")
print("  extra loss = (dI_pp^2 / 12) * R; dI_pp ~ Vbus*D*(1-D)/(L*f) -> scales with 1/(L*f); loss with R/(L*f)^2")
for vavg, R in ((3.7, 0.4), (7.4, 0.6)):
    d = vavg / VB
    print(f"\n  {vavg} V average (D {d:.2f}), R {R} ohm:")
    for L in (1e-6, 2e-6, 3e-6, 5e-6, 10e-6):
        cells = []
        for f in (50e3, 100e3, 200e3, 400e3, 500e3, 1e6):
            pp = ripple_pp(VB, d, f, L, R + 0.1)
            cells.append(f"{f/1e3:4.0f}k {pp:5.2f}/{pp**2/12*R:5.2f}")
        print(f"    L {L*1e6:4.1f} uH: " + "  ".join(cells))
    for Lx in (4.7e-6, 10e-6, 22e-6):
        cells = []
        for f in (100e3, 200e3, 400e3):
            pp = ripple_pp(VB, d, f, 2e-6 + Lx, R + 0.1 + 0.03)
            cells.append(f"{f/1e3:4.0f}k {pp:5.2f}/{pp**2/12*R:5.2f}")
        print(f"    2 uH motor + {Lx*1e6:4.1f} uH choke: " + "  ".join(cells))
print("\n  Frequency for ripple loss <= 0.1 W (R 0.4 ohm, D 0.22, worst point of 1S on 4S):")
for L in (1e-6, 2e-6, 3e-6, 5e-6, 10e-6):
    f = 20e3
    while ripple_pp(VB, 3.7 / VB, f, L, 0.5) ** 2 / 12 * 0.4 > 0.1 and f < 5e6:
        f *= 1.02
    print(f"    L {L*1e6:4.1f} uH: f >= {f/1e3:5.0f} kHz")

# ---------------------------------------------------------------------------------------------
hdr("5. Driver loss and junction rise at 1 / 2 / 4 A, 16.8 V, 1S motor at 3.7 V (D 0.22), L 3 uH, each at its chosen f")
HOT = 1.4  # [A] RDS(on) hot factor where no curve was extracted
# name, f, R_on_path (ohm, the switch carrying current during ON), R_off_path (freewheel), t_edge (s per edge),
# diode Vf during freewheel (None = synchronous), RthJA (C/W), Ipk rating text
DRV = [  # name, f, R_on path, R_off path, t_edge, Vf (None = synchronous), RthJA, rating, extra series L (H), choke DCR
    ("STSPIN958 par., SR 2 V/ns, 400k", 400e3, 0.0825, 0.0825, VB / 2e9, None, 35.8, "5 A rms [DS]", 0, 0),
    ("STSPIN958 par., SR 0.6 V/ns, 400k", 400e3, 0.0825, 0.0825, VB / 0.6e9, None, 35.8, "5 A rms [DS]", 0, 0),
    ("DRV8412 PFB mode (A||B, C||D), 400k", 400e3, 0.110, 0.110, 14e-9, None, 24.5, "6 A cont. PFB [DS]", 0, 0),
    ("DRV8874 IN/IN slow decay, 100k", 100e3, 0.200, 0.200, 150e-9, None, 36.0, "6 A peak [DS]", 0, 0),
    ("DRV8874 100k + 22 uH choke", 100e3, 0.200, 0.200, 150e-9, None, 36.0, "6 A peak [DS]", 22e-6, 0.06),
    ("DRV8256 VQFN 100k + 22 uH choke", 100e3, 0.165, 0.165, 100e-9, None, 39.0, "6.4 A peak [DS]", 22e-6, 0.06),
    ("DRV8262 single-H, 200k + 10 uH choke", 200e3, 0.050, 0.050, 110e-9, None, 22.2, "16 A peak [DS]", 10e-6, 0.03),
    ("TB67H450FNG, 400k (edges unpubl., 100 ns [A])", 400e3, 0.70, 0.70, 100e-9, None, None, "3.0 A max [DS]", 0, 0),
    ("DRV8251A, 200k", 200e3, 0.450, 0.450, 220e-9, None, None, "4.1 A peak [DS]", 0, 0),
    ("LS FET CSD17578Q3A + SS34 + UCC27517A, 400k", 400e3, 0.0094, None, 5e-9, 0.55, 60.0, "SS34 3 A avg [DS]", 0, 0),
    ("sync. TPS28225 + 2x CSD17578Q3A, 400k", 400e3, 0.0094, 0.0094, 10e-9, None, 60.0, "FET-limited", 0, 0),
]
L = 3e-6
R = 0.4
for vavg in (3.7, 7.4):
    d = vavg / VB
    print(f"\n  V_avg {vavg} V, D {d:.2f}; motor L 3 uH, R 0.4 ohm; loss = driver (+ choke DCR) / motor ripple loss")
    print(f"  {'driver':48} {'rating':>20} | {'1 A':>22} | {'2 A':>22} | {'4 A':>22}")
    for name, f, ron, roff, te, vf, rth, rating, Lx, dcr in DRV:
        cells = []
        rip = ripple_pp(VB, d, f, L + Lx, R + 0.1 + dcr) / math.sqrt(12)
        pmot = rip ** 2 * R
        for I in (1.0, 2.0, 4.0):
            i2 = I ** 2 + rip ** 2
            p = i2 * ron * HOT * d
            if roff is not None:
                p += i2 * roff * HOT * (1 - d)
            psw = VB * I * te * f
            pdio = 0.0
            if vf is not None:
                pdio = vf * I * (1 - d) + (250e-12 + 134e-12) * VB ** 2 * f / 2
            ptot = p + psw + pdio
            pch = i2 * dcr
            dt = f" +{ptot*rth:3.0f}C" if rth else ""
            cells.append(f"{ptot+pch:5.2f}{dt} /{pmot:5.2f}")
        print(f"  {name:48} {rating:>20} | " + " | ".join(f"{c:>22}" for c in cells))
print("  Schottky share at 4 A, 1S duty: {:.1f} W -> SS34 (RthJA 70 C/W [DS]) +{:.0f} C".format(0.55 * 4 * (1 - 3.7 / VB), 0.55 * 4 * (1 - 3.7 / VB) * 70))
print("  Peak current = I + dI_pp/2 must stay under the driver's OCP/limit: e.g. DRV8874 with no choke at 2 A, 3 uH:")
pp = ripple_pp(VB, 3.7 / VB, 100e3, 3e-6, 0.5)
print(f"    {2 + pp/2:4.1f} A peak against IOCP 6 A min")

# ---------------------------------------------------------------------------------------------
hdr("6. Area estimate (component courtyards, mm^2) [A: typical courtyards, not a layout]")
CY = {"0402": 1.4, "0603": 2.6, "0805": 4.6, "1206": 8.0, "2512": 30.0, "SOT-23-5": 9.5, "SOT-23": 9.0,
      "VFQFPN32 5x5": 36.0, "HTSSOP-44 14x8.1": 125.0, "HTSSOP-16": 38.0, "VQFN-24 4x4": 22.0, "HSOP-8": 38.0,
      "SON3x3": 13.0, "SOIC-8": 33.0, "DFN2x2": 6.0, "SMA": 18.0, "L5x5": 30.0, "SOT-223": 46.0}
designs = {
    "STSPIN958 parallel (IC, 1206 shunt, 2x10uF 1206, 2x470n 0603, 4C+4R 0402)":
        ["VFQFPN32 5x5", "1206", "1206", "1206", "0603", "0603"] + ["0402"] * 8,
    "DRV8412 (IC, 12 V LDO SOT-223 + 2 C, 4 x 100 nF BST, PVDD 10uF+100n, VREG/VDD/GVDD caps, ROC)":
        ["HTSSOP-44 14x8.1", "SOT-223", "0805", "0805", "1206"] + ["0402"] * 10,
    "DRV8874 (IC, VM 10uF 1206 + 100n, CP 2 C, RIPROPI, VREF 2 R)":
        ["HTSSOP-16", "1206", "0402", "0402", "0402", "0402", "0402", "0402"],
    "DRV8256 VQFN (IC, VM 10uF + 100n, CP 2 C, RIPROPI, VREF 2 R)":
        ["VQFN-24 4x4", "1206", "0402", "0402", "0402", "0402", "0402", "0402"],
    "LS FET + SS34 + UCC27517A (FET SON3x3, SMA, driver, 2 C, gate R, pulldown)":
        ["SON3x3", "SMA", "SOT-23-5", "0402", "0603", "0402", "0402"],
    "  + current limit (1206 shunt, TLV3201 SOT-23-5, 4 R/C)":
        ["SON3x3", "SMA", "SOT-23-5", "0402", "0603", "0402", "0402", "1206", "SOT-23-5", "0402", "0402", "0402", "0402"],
    "sync. TPS28225 SOIC-8 + 2 FET SON3x3 + Cbst + VDD C + 2x10uF 1206 + EN R":
        ["SOIC-8", "SON3x3", "SON3x3", "0402", "0603", "1206", "1206", "0402"],
    "optional series choke for L < 3 uH (4.7-10 uH, Isat > I_limit, ~5x5)": ["L5x5"],
}
for k, parts in designs.items():
    print(f"  {sum(CY[p] for p in parts):6.0f} mm2, {len(parts):2d} parts  {k}")
