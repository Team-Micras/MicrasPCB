"""Power-stage calculations for the Micras motor-driver comparison.

Every datasheet number is annotated with its source. Assumptions are marked ASSUMPTION.
Run: python3 -I power_stage_calc.py
"""
import math

# ---------------------------------------------------------------------------------------------
# 1. Motor current ripple (RL load with back-EMF, PWM steady state, exact exponential solution)
# ---------------------------------------------------------------------------------------------
# maxon DCX 8 M catalog page 98 (Feb 2025 edition, "provisional data"):
#   2.4 V winding: R = 4.13 ohm, L = 0.014 mH ; 4.2 V winding: R = 12 ohm, L = 0.0411 mH
#   6 V winding: R = 29 ohm, L = 0.0941 mH
motors = {
    "DCX8M 2.4V (4.13 ohm, 14 uH)": (4.13, 14e-6),
    "DCX8M 4.2V (12 ohm, 41.1 uH)": (12.0, 41.1e-6),
    "generic 1 ohm / 20 uH (ASSUMPTION, low-R coreless)": (1.0, 20e-6),
}


def ripple_pp(v_step, r, l, f, d):
    """Peak-to-peak ripple of an RL load driven by a square wave of amplitude v_step.

    Steady state: the back-EMF and the average voltage set the DC level; the ripple only depends
    on the step amplitude, tau, the period and the duty.
    """
    tau = l / r
    t = 1.0 / f
    a = math.exp(-d * t / tau)
    b = math.exp(-(1 - d) * t / tau)
    return (v_step / r) * (1 - a) * (1 - b) / (1 - a * b)


print("=== Motor current ripple, D = 0.5 (worst case) ===")
print(f"{'motor':52s} {'VM':>5s} {'f kHz':>6s} {'tau us':>7s} {'unipolar A pp':>14s} {'bipolar A pp':>13s} {'uni Iac,rms':>11s}")
for name, (r, l) in motors.items():
    for vm in (16.8, 24.0):
        for f in (20e3, 40e3, 100e3, 200e3):
            uni = ripple_pp(vm, r, l, f, 0.5)  # sign-magnitude / slow decay: OUT toggles VM <-> 0
            bip = ripple_pp(2 * vm, r, l, f, 0.5)  # locked anti-phase: +VM <-> -VM
            print(f"{name:52s} {vm:5.1f} {f/1e3:6.0f} {l/r*1e6:7.2f} {uni:14.2f} {bip:13.2f} {uni/(2*math.sqrt(3)):11.2f}")

# Small-ripple approximation for reference (L-dominated): dI = V D (1-D) / (L f)
print("\nSmall-ripple approx. dI = VM*D*(1-D)/(L*f) for DCX8M 2.4 V at 16.8 V, 100 kHz:",
      round(16.8 * 0.25 / (14e-6 * 100e3), 2), "A pp (overestimates when T ~ tau)")

# ---------------------------------------------------------------------------------------------
# 2. Driver losses per H-bridge
# ---------------------------------------------------------------------------------------------
# Loss model (TI DRV8874 SLVSF66A eq. 12-13, DRV8962 SLVSFV6B section 8.x "PHB" formula):
#   P_cond = I^2 * (R_HS + R_LS)                (one HS and one LS always in the path: drive or
#                                                 slow decay, sign-magnitude PWM)
#   P_sw   = 0.5 * VM * I * (t_rise + t_fall) * f
#   P_dead = 2 * VD * I * t_dead * f
# Hot RDS(on): DRV8256 82 -> 125 mohm (25 -> 125 C, 1.52x), DRV8262 50 -> 75 mohm (1.5x):
# ASSUMPTION: 1.5x for parts whose 125 C value was not extracted.
HOT = 1.5

# name: (R_HS+R_LS typ 25C [ohm], hot factor, t_rise [s] or None -> slew, t_fall, slew V/us (rise, fall),
#        t_dead [s], VD [V], RthJA [C/W], note)
drivers = {
    "L6205D (current)": dict(r=0.34 + 0.28, hot=HOT, tr=100e-9, tf=100e-9, td=0.75e-6, vd=1.0, rth=51,
                             note="RDS(on) 0.34 HS + 0.28 LS typ (L6205 p5-6); tr/tf 100 ns and VD 1 V ASSUMPTION; dead time 0.5-1 us (p5); Rth 51 C/W SO20 6 cm2 (p3)"),
    "DRV8874 (x1 per motor)": dict(r=0.200, hot=HOT, tr=150e-9, tf=150e-9, td=100e-9, vd=0.9, rth=36.0,
                                   note="100+100 mohm typ (EC table), tRISE=tFALL 150 ns, tDEAD 100 ns, VSD 0.9 V, RthJA 36 C/W"),
    "DRV8256 (x1 per motor)": dict(r=0.164, hot=125/82, slew=(240, 240), td=None, vd=None, rth=29.7,
                                   note="82+82 mohm typ, 125+125 at 125 C; 240 V/us slew; dead time not extracted; RthJA 29.7 (HTSSOP)"),
    "DRV8262 dual (per bridge)": dict(r=0.100, hot=1.5, tr=110e-9, tf=110e-9, td=300e-9, vd=0.9, rth=22.2,
                                      note="50+50 mohm typ dual mode, tRF 110 ns, tD 300 ns; VD 0.9 V ASSUMPTION (not specified); RthJA 22.2 DDW"),
    "DRV8962 quad-HB (per bridge)": dict(r=0.106, hot=70/53, tr=140e-9, tf=140e-9, td=300e-9, vd=0.9, rth=22.2,
                                         note="53+53 mohm typ, 70 at 125 C; tRF 140 ns; tD 300 ns; VD ASSUMPTION"),
    "DRV8263-Q1 (x1 per motor)": dict(r=0.085, hot=HOT, slew=(130, 180), td=0.46e-6 + 0.1e-6, vd=0.8, rth=35.0,
                                      note="85 mohm HS+LS; SR LVL1 130/180 V/us rise/fall; tDEAD_HSON 0.46 + tDEAD_HSOFF 0.1 us; VSD 0.8 typ; RthJA 35"),
    "STSPIN948 (per bridge)": dict(r=0.36, hot=HOT, slew=(600, 600), td=None, vd=None, rth=27.6,
                                   note="180+180 mohm typ; SR 0.6 V/ns at RSR 5.6 k; dead time not extracted; RthJA 27.6"),
    "Discrete DRV8714 + 2x SiZF5302DT": dict(r=0.0027 * 2 + 0.002, hot=1.4, tr=30e-9, tf=30e-9, td=350e-9, vd=0.85, rth=None,
                                             note="2.7 mohm typ at VGS 10 V per FET (SiZF5302DT) + 2 mohm inline shunt ASSUMPTION; tr/tf 30 ns ASSUMPTION (IDRIVE dependent); DRV8714 handshake dead time 350 ns; VSD 0.85 V"),
}


def losses(d, vm, i, f, hot=False):
    r = d["r"] * (d["hot"] if hot else 1.0)
    p_cond = i * i * r
    if "slew" in d:
        sr_r, sr_f = d["slew"]
        tr = 0.8 * vm / (sr_r * 1e6) / 0.8  # full swing at the 10-90 % slew rate (conservative)
        tf = vm / (sr_f * 1e6)
    else:
        tr, tf = d["tr"], d["tf"]
    p_sw = 0.5 * vm * i * (tr + tf) * f
    p_dead = 2 * d["vd"] * i * d["td"] * f if d.get("td") and d.get("vd") else 0.0
    return p_cond, p_sw, p_dead


print("\n=== Driver loss per H-bridge, I = 4 A (continuous) ===")
for vm in (16.8, 24.0):
    print(f"\n-- VM = {vm} V --")
    print(f"{'driver':36s} {'f kHz':>6s} {'Pcond25':>8s} {'PcondHot':>9s} {'Psw':>6s} {'Pdead':>6s} {'Ptot(hot)':>9s} {'eff% of VM*I*0.5':>16s}")
    for name, d in drivers.items():
        for f in (20e3, 40e3, 100e3):
            pc, ps, pd = losses(d, vm, 4.0, f)
            pch, _, _ = losses(d, vm, 4.0, f, hot=True)
            tot = pch + ps + pd
            pout = vm * 0.5 * 4.0  # mechanical+copper input at D = 0.5
            print(f"{name:36s} {f/1e3:6.0f} {pc:8.2f} {pch:9.2f} {ps:6.2f} {pd:6.2f} {tot:9.2f} {100*(1-tot/(pout+tot)):16.1f}")

print("\n=== Conduction loss at the 8 A peak (short burst), per bridge, 25 C / hot ===")
for name, d in drivers.items():
    pc, _, _ = losses(d, 16.8, 8.0, 40e3)
    pch, _, _ = losses(d, 16.8, 8.0, 40e3, hot=True)
    print(f"{name:36s} {pc:6.2f} W / {pch:6.2f} W")

print("\n=== Junction rise at 4 A, 16.8 V, 40 kHz (both motors loaded), using datasheet RthJA ===")
pairs = {
    "L6205D (current)": 2,          # both bridges in one package
    "DRV8874 (x1 per motor)": 1,
    "DRV8256 (x1 per motor)": 1,
    "DRV8262 dual (per bridge)": 2,
    "DRV8962 quad-HB (per bridge)": 2,
    "DRV8263-Q1 (x1 per motor)": 1,
    "STSPIN948 (per bridge)": 2,
}
for name, n in pairs.items():
    d = drivers[name]
    pch, ps, pd = losses(d, 16.8, 4.0, 40e3, hot=True)
    p = n * (pch + ps + pd)
    print(f"{name:36s} P_pkg = {p:5.2f} W  dT = {p*d['rth']:6.1f} C  (RthJA {d['rth']} C/W, JEDEC/dsheet board)")

# ---------------------------------------------------------------------------------------------
# 3. Input (bulk) capacitor ripple current and voltage
# ---------------------------------------------------------------------------------------------
print("\n=== Bridge input ripple (per bridge I*sqrt(D(1-D))) and voltage ripple on local ceramics ===")
for i in (4.0, 8.0):
    for d in (0.25, 0.5):
        irms_one = i * math.sqrt(d * (1 - d))
        irms_two_inphase = 2 * irms_one
        print(f"I={i} A D={d}: Icap,rms one bridge {irms_one:.2f} A, two bridges in phase {irms_two_inphase:.2f} A")
for c in (10e-6, 20e-6, 44e-6):
    for f in (20e3, 40e3, 100e3):
        dv = 2 * 4.0 * 0.25 / (c * f)  # two bridges in phase, 4 A each, D = 0.5, charge balance
        print(f"C_eff = {c*1e6:4.0f} uF, f = {f/1e3:5.0f} kHz: dV pp (2 x 4 A in phase, D=0.5) = {dv:5.2f} V")

# ---------------------------------------------------------------------------------------------
# 4. IPROPI scaling
# ---------------------------------------------------------------------------------------------
print("\n=== IPROPI resistor sizing for a 3.3 V ADC ===")
# DRV8874: AIPROPI 450 uA/A, IIPROPI max 3 mA (ROC), VREF max 3.6 V
for r in (680, 820, 1000):
    print(f"DRV8874 RIPROPI {r} ohm: 1 A -> {450e-6*r:.3f} V, full scale at 3.0 V = {3.0/(450e-6*r):.2f} A,"
          f" IPROPI at 6 A = {6*450e-3:.2f} mA (<= 3 mA ROC)")
# DRV8262: AIPROPI 212 uA/A, VIPROPI < VREF max 3.3 V
for r in (1500, 1800, 2000):
    print(f"DRV8262 RIPROPI {r} ohm: 1 A -> {212e-6*r:.3f} V, full scale at 3.0 V = {3.0/(212e-6*r):.2f} A")
# ITRIP: ITRIP x AIPROPI = VREF / RIPROPI
for vref in (1.5, 2.0, 2.5):
    print(f"DRV8262 RIPROPI 1.8k, VREF {vref} V -> ITRIP = {vref/1800/212e-6:.2f} A;"
          f"  DRV8874 RIPROPI 1k, VREF {vref} V -> ITRIP = {vref/1000/450e-6:.2f} A")

# ---------------------------------------------------------------------------------------------
# 5. Battery switch gate drive at 4S (R43/R41 100k/100k divider, VGS = VBAT/2)
# ---------------------------------------------------------------------------------------------
print("\n=== HSBB3072 low-side battery switch at 4S ===")
for vb in (12.0, 14.8, 16.8):
    vgs = vb / 2
    print(f"VBAT {vb:4.1f} V -> VGS {vgs:4.1f} V (abs max +-20 V), VDS(off) = {vb} V (30 V rating, {30/vb:.2f}x margin)")
for i in (8, 12, 16):
    print(f"I = {i} A: P = I^2 * 3.8 mohm (max at VGS 4.5 V) = {i*i*3.8e-3:.2f} W ; at 2.4 mohm (VGS 10 V max) {i*i*2.4e-3:.2f} W")

# ---------------------------------------------------------------------------------------------
# 6. Motor copper loss from ripple vs. the motor's continuous rating, and series-inductor fix
# ---------------------------------------------------------------------------------------------
print("\n=== Ripple copper loss in the motor (unipolar, D = 0.5) vs. continuous rating I_nom^2 R ===")
# DCX 8 M catalog p98: nominal (max continuous) current 0.345 A (2.4 V), 0.199 A (4.2 V)
for name, (r, l, inom) in {"DCX8M 2.4V": (4.13, 14e-6, 0.345), "DCX8M 4.2V": (12.0, 41.1e-6, 0.199)}.items():
    print(f"{name}: continuous copper budget I_nom^2 R = {inom**2*r:.2f} W")
    for vm in (7.4, 11.1, 16.8, 24.0):
        row = []
        for f in (20e3, 40e3, 100e3, 200e3):
            iac = ripple_pp(vm, r, l, f, 0.5) / (2 * math.sqrt(3))
            row.append(f"{f/1e3:.0f}k: {iac**2*r:5.2f} W")
        print(f"   VM {vm:5.1f} V  " + "  ".join(row))
    for lext in (22e-6, 47e-6, 100e-6):
        row = []
        for f in (40e3, 100e3):
            pp = ripple_pp(16.8, r + 0.03, l + lext, f, 0.5)  # ASSUMPTION 30 mohm inductor DCR
            row.append(f"{f/1e3:.0f}k: {pp:4.2f} A pp, {(pp/(2*math.sqrt(3)))**2*r:4.2f} W")
        print(f"   + series {lext*1e6:.0f} uH @16.8 V  " + "  ".join(row))
