"""Fan path check: STSPIN958 (parallel half-bridge, PWM trimming, 400 kHz) + MPL-AL5030-4R7 4.7 uH + a not
yet chosen drone-class brushed coreless motor, over the whole plausible range of the motor's
inductance and resistance; the STSPIN958's heat with bounds on its unpublished data; the REF rule.

Run: python3 fan_choke_check.py (seconds). Output: fan_choke_check_out.txt.

Sources and bounds:
- STSPIN958 (ST DS14341 Rev 1): RDS(on) 165 mOhm per switch at 25 C, two in parallel (Table 5);
  minimum PWM pulse 280 ns (Table 2); REF limiter Eq. 1, ACL 9.5-10.5 (Table 5); overcurrent
  threshold IOC 7-14 A per power MOSFET (Table 5, section 5.7), 91.4 % of it at 17.4 V (Figure 20,
  normalized at 58 V): in parallel mode the two paralleled MOSFETs share the load current, so the
  device trips at 2 x IOC, 12.8 A at the least;
  TSD 150 C; RthJA 35.8 C/W on the JESD51 board (Table 4); SR 2 V/ns with RSR 1 kOhm (Table 7, at
  VS 58 V), about 49 % of it at 17 V (Figure 18): 1.0 V/ns here.
  Not published: the RDS(on) temperature curve, the dead time, the VS operating current, the
  limiter blanking and comparator delay. Bounds used (inference):
  * RDS(on)(T): typical as the DRV8874's (TI SLVSF66A Figures 6-7, about +25 % at 125 C, the same
    kind of integrated BCD power switch); bound by the silicon electron lattice mobility,
    RDS ~ (T/298 K)^2.33 (Arora, Hauser, Roulston, IEEE TED 29 (1982): mu_lattice ~ T^-2.33),
    1.95x at 125 C.
  * Dead time: 100 ns typical, 300 ns bound per edge, body diode 0.9 V (the DRV8874's VSD) at the
    current, two edges per period.
  * VS operating current: 7 mA typical (the DRV8874's IVM maximum), 10 mA bound.
  * Board RthJA: 35.8 C/W typical, 45 C/W bound (the main board's inner planes are 0.5 oz and the board is
    smaller than the JESD51 one); board ambient 40 C.
  * Limiter: on-time at least the blanking t_b (280 ns typical = the minimum pulse, 500 ns bound),
    plus a comparator delay of 200 ns (the amplifier's settling time, Table 5) after the crossing.
- MPL-AL5030-4R7 (MPS datasheet Rev. 1.1, 8/6/2019): 4.7 uH +-20 % at 100 kHz / 100 mA, RDC 33 typ /
  36.5 mOhm max, IR 5.3 A (40 K rise on a single-layer 35 um, 30 x 50 mm board), ISAT 8 A typ at a
  30 % drop (25 and 100 C), operating -40 to +155 C including the rise (p1 and p5 tables).
  DC bias: p2 Figure "Inductance vs. Current" (25 C curve), digitised below; its relative drop is
  applied to the -20 % part. The curve falls 20 % below 4.7 uH at 4.55 A and 30 % at 6.7 A (the table's
  8 A Isat is not on it): the 20 % point used here is 4.5 A.
  Thermal: p2 Figure "Temperature Rise vs. Current" (DC, on MPS's single-layer board), digitised
  below: with the typical RDC and copper's 0.393 %/K it gives 37 K/W at 2.5-6 A and 40 K/W at 7 A;
  40 K/W is used, the main board's four layers and planes do better.
  AC (core) loss: MPS publishes no loss model or loss tool data for the MPL-AL. Estimate: the p3
  Figure "Quality Factor vs. Frequency" (small signal), R_ac(f) = 2 pi f L / Q - RDC typ (0.14 Ohm at
  400 kHz), summed over the triangle's harmonics, times the large-signal factor the same method
  shows on the XGL5030-472 (Coilcraft's loss tool over its Document 267 small-signal model, 2.83 x;
  drivetrain/choke_spice_loss.py). Bound: twice the larger of Coilcraft's loss-tool values for its
  two composite-powder 5030 4.7 uH chokes, XGL5030-472 and XAL5030-472, at the same ripple and
  0.408 MHz (independent of the DC current, scaled linearly to 400 kHz; QY7/Power_toys
  power_toys/data/coilcraft_loss_for_training), about 4 x the estimate. MPS's own comparison of the
  MPL-AL family at 500 kHz and 1 MHz (MPS webinar "Understanding Power Inductor Parameters" pp
  28-29: MPL-AL6060-100 in an MPQ8883 buck against three market parts, efficiency at or above
  theirs at light load, where core loss dominates) is qualitative support only.
- Motor (not chosen): R 0.2-1.2 ohm (fan study's drone motors); L at 1 kHz bounded from the
  makers that publish it, scaled to kv 13,000-20,000 rpm/V by L ~ 1/kv^2 (same frame, same turns
  law): maxon DCX 10 L 1.5 V 5 uH at 7870 rpm/V (catalogue p100) -> 0.77-1.8 uH; Faulhaber 1024 K
  003 SR 16 uH at 4100 rpm/V -> 0.67-1.6 uH; Faulhaber 0816 K 003 SR 53 uH at 4530 rpm/V ->
  2.7-6.4 uH; 0615 N 1,5 S 12 uH at 13,800 rpm/V -> 5.7-13.5 uH (fan_driver_calc.py). So 0.6-14 uH,
  times the ironless drop at the PWM frequency, 0.2-1.0 (maxon chokes note p7; Portescap 2022):
  0.12-14 uH at 400 kHz. 2S motors (half the kv) have about 4x the inductance.
"""

import math

F = 400e3
T = 1 / F
L_NOM, TOL, DCR, DCR_TYP = 4.7e-6, 0.20, 36.5e-3, 33e-3
ISAT20, IRMS40, T_MAX = 4.5, 5.3, 155.0
RSNS, RDS25 = 25e-3, 0.165 / 2
REF_TYP = 3.3 * 2.0 / 6.7
I_LIM = REF_TYP / (RSNS * 10)
I_LIM_HI = (3.346 * 2.0 * 1.01 / (2.0 * 1.01 + 4.7 * 0.99)) / (RSNS * 0.99 * 9.5)
I_LIM_LO = (3.284 * 2.0 * 0.99 / (2.0 * 0.99 + 4.7 * 1.01)) / (RSNS * 1.01 * 10.5)
LM_EFF = (0.12e-6, 0.5e-6, 1e-6, 3e-6, 14e-6)

# MPS p2 "Inductance vs. Current", 25 C curve (A, uH), digitised from the datasheet's plot.
L_CURVE = ((0, 4.672), (0.5, 4.615), (1, 4.556), (1.5, 4.480), (2, 4.371), (2.5, 4.247), (3, 4.124),
           (3.5, 4.003), (4, 3.884), (4.5, 3.769), (5, 3.655), (5.5, 3.544), (6, 3.437), (6.5, 3.332),
           (7, 3.234), (7.5, 3.135), (8, 3.042), (9, 2.866), (10, 2.701), (11, 2.545), (12, 2.402),
           (13, 2.264), (14, 2.138), (15, 2.021))
# MPS p2 "Temperature Rise vs. Current" (A, K) and the thermal resistance used.
T_CURVE = ((2, 5.4), (2.5, 8.0), (3, 11.6), (4, 20.9), (5, 34.9), (5.3, 39.8), (6, 54.8), (7, 86.3))
RTH_L = 40.0
# MPS p3 "Quality Factor vs. Frequency" (MHz, Q), digitised.
Q_CURVE = ((0.1, 29.8), (0.2, 45.6), (0.251, 52.8), (0.314, 60.1), (0.392, 67.7), (0.439, 71.0),
           (0.491, 73.1), (0.549, 74.9), (0.687, 72.2), (0.860, 68.9), (1.076, 63.1), (1.505, 53.4),
           (2.107, 45.3), (2.948, 38.2), (4.126, 31.6), (5.775, 24.8), (8.082, 18.1), (10.11, 13.3),
           (12.65, 9.0))
# Coilcraft loss tool at 0.408 MHz, AC loss (dIpp A, mW), any DC current (Power_toys tables).
XGL_TOOL = ((0.67, 32.3), (1.34, 128.2), (2.01, 287.2), (2.68, 509.0), (3.35, 793.6), (4.02, 1140.7))
XAL_TOOL = ((0.67, 51.7), (1.34, 160.6), (2.01, 311.7), (2.68, 499.0), (3.35, 718.8), (4.02, 968.5))
# Coilcraft Document 267 small-signal model of the XGL5030-472 (drivetrain/choke_spice_loss.py).
XGL267 = dict(R1=5.0, C=9.9e-12, k1=1.0e-5, k2=0.840, k3=4.7, k4=1e-6, k5=1e-6)


def interp(table, x):
    if x <= table[0][0]:
        (x0, y0), (x1, y1) = table[0], table[1]
    elif x >= table[-1][0]:
        (x0, y0), (x1, y1) = table[-2], table[-1]
    else:
        k = next(k for k in range(1, len(table)) if table[k][0] >= x)
        (x0, y0), (x1, y1) = table[k - 1], table[k]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def l_choke(i, tol=-TOL):
    """Incremental inductance of the -20 % part at the DC current i (the curve's relative drop)."""
    return L_NOM * (1 + tol) * interp(L_CURVE, abs(i)) / L_CURVE[0][1]


def harmonics(dipp, d, nmax=41):
    """Peak amplitudes of a triangle of peak-to-peak dipp, rising for D."""
    return [(n, abs(dipp / (n * n * math.pi ** 2 * d * (1 - d)) * math.sin(n * math.pi * d))) for n in range(1, nmax + 1)]


def r_ac_mpl(f):
    q = 10 ** interp(tuple((math.log10(a), math.log10(b)) for a, b in Q_CURVE), math.log10(f / 1e6))
    return max(2 * math.pi * f * L_NOM / q - DCR_TYP, 0.0)


def r_ac_xgl267(f):
    p, w = XGL267, 2 * math.pi * f
    a = p["k1"] * math.sqrt(f) + 1j * w * (p["k3"] - p["k4"] * math.log(p["k5"] * f)) * 1e-6
    b = p["R1"] + 1 / (1j * w * p["C"])
    c = p["k2"] * math.sqrt(f)
    return (1 / (1 / a + 1 / b + 1 / c)).real


def small_signal(r_ac, dipp, d, f):
    return sum((a / math.sqrt(2)) ** 2 * r_ac(n * f) for n, a in harmonics(dipp, d) if n * f <= 12.6e6)


K_LS = 71.6e-3 * 2.0 ** 1.99 / small_signal(r_ac_xgl267, 2.0, 0.5, 408e3)


def ac_loss(dipp, d=0.43):
    """Estimate: MPS's small-signal R_ac times the XGL5030-472's large-signal factor."""
    return K_LS * small_signal(r_ac_mpl, dipp, d, F)


def ac_bound(dipp):
    """Bound: twice the larger Coilcraft 5030 4.7 uH loss-tool value, at 400 kHz (dIpp^2 below the tables)."""
    tool = (max(interp(t, dipp) if dipp >= t[0][0] else t[0][1] * (dipp / t[0][0]) ** 2 for t in (XGL_TOOL, XAL_TOOL)))
    return 2 * tool * 1e-3 * F / 408e3


def l6_temp(i, pp, p_ac, board=40.0):
    rise = 0.0
    for _ in range(40):
        p_dc = (i ** 2 + pp ** 2 / 12) * DCR * (1 + 0.00393 * (board + rise - 20))
        rise = (p_dc + p_ac) * RTH_L
    return p_dc, board + rise


def ripple_pp(v, d, l_tot):
    return v * d * (1 - d) * T / l_tot


print("Fan path: STSPIN958 400 kHz + MPL-AL5030-4R7 + drone coreless motor")
print(f"REF limit: typ {I_LIM:.2f} A, band {I_LIM_LO:.2f}-{I_LIM_HI:.2f} A (3V3_D 3.284-3.346 V, 1 % resistors, ACL 9.5-10.5,"
      " RSNS 1 %)")
print("MPL-AL5030-4R7 at -20 %, incremental L: " + ", ".join(f"{i:.0f} A {l_choke(i)*1e6:.2f} uH" for i in (0, 2, 3, 4, 5, 6, 7)))
print(f"   typical part (p2 curve): {interp(L_CURVE, I_LIM_HI) / 4.7 * 100 - 100:.0f} % from 4.7 uH at the band's top {I_LIM_HI:.2f} A, "
      f"{interp(L_CURVE, IRMS40) / 4.7 * 100 - 100:.0f} % at the {IRMS40} A IR; 20 % point used: {ISAT20} A")
print("   thermal resistance from the p2 temperature-rise curve (RDC 33 mOhm typ, +0.393 %/K): " + ", ".join(
    f"{i:g} A {dt / (i * i * DCR_TYP * (1 + 0.00393 * dt)):.0f}" for i, dt in T_CURVE) + f" K/W; used {RTH_L:.0f} K/W")
print(f"   AC loss: MPS small-signal R_ac at 400 kHz {r_ac_mpl(F):.3f} ohm (Q {2 * math.pi * F * L_NOM / (r_ac_mpl(F) + DCR_TYP):.0f}),"
      f" XGL5030-472 Document 267 model {r_ac_xgl267(408e3):.3f} ohm; large-signal factor {K_LS:.2f}")

print("\n1. Running ripple at 400 kHz (choke -20 % and biased at the running current), worst VBAT 17.4 V")
half = {"1S": 0.0, "2S": 0.0}
print(f"   {'motor':>4} {'Lm uH':>6} {'I A':>4} {'D':>5} {'L tot':>6} {'dIpp':>5} {'peak':>5} {'limiter':>8} {'motor W':>7} "
      f"{'L6 est mW':>9} {'bound mW':>8}")
for cls, vavg in (("1S", 3.7), ("2S", 7.4)):
    for lm in LM_EFF:
        lm2 = lm * (4 if cls == "2S" else 1)
        for i in (1.0, 2.5):
            d = vavg / 17.4
            lt = lm2 + l_choke(i)
            pp = ripple_pp(17.4, d, lt)
            pk = i + pp / 2
            flag = "clips" if pk > I_LIM_LO else "ok"
            pm = pp ** 2 / 12 * 1.2
            half[cls] = max(half[cls], pp / 2)
            print(f"   {cls:>4} {lm2*1e6:6.2f} {i:4.1f} {d:5.2f} {lt*1e6:6.2f} {pp:5.2f} {pk:5.2f} {flag:>8} {pm:7.3f} "
                  f"{ac_loss(pp, d)*1e3:9.1f} {ac_bound(pp)*1e3:8.1f}")
print("   (motor W: ripple heat at the 1.2 ohm top of the range, an upper bound; 'clips': the peak reaches the")
print("    lowest REF limit and the limiter trims the pulse, which lowers the mean current, not a fault)")
pp_w = ripple_pp(17.4, 0.43, 0.48e-6 + l_choke(2.5))
print(f"   the worst: 1S, D = 0.5 never occurs; a 2S motor at D 0.43 with the lowest L: {pp_w:.2f} A pp")
print(f"   L6 temperature (Rth {RTH_L:.0f} K/W), DCR {DCR*1e3:.1f} mOhm max + 0.393 %/K copper on I^2 + dIpp^2/12, AC loss at the")
print(f"   largest ripple of the table (2S, lowest L), board at 40 C; IR {IRMS40} A is the 40 K-rise rating, {T_MAX:.0f} C the")
print("   part's maximum including its rise (p1); the board's own budget is 125 C, the X7R capacitors' rating:")
for name, p_ac in (("estimate", ac_loss(pp_w)), ("bound", ac_bound(pp_w))):
    for i in (1.0, 2.5, I_LIM_HI):
        p_dc, t = l6_temp(i, pp_w, p_ac)
        print(f"   {name:>8} {i:4.2f} A: DC {p_dc*1e3:4.0f} mW + AC {p_ac*1e3:4.0f} mW -> +{t - 40:4.1f} K, {t:5.1f} C")
for limit in (125.0, T_MAX):
    p_dc, _ = l6_temp(I_LIM_HI, pp_w, 0.0, board=40.0)
    lo, hi = 0.0, 10.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if l6_temp(I_LIM_HI, pp_w, mid)[1] < limit else (lo, mid)
    print(f"   AC loss that takes L6 to {limit:.0f} C at {I_LIM_HI:.2f} A held: {lo:.2f} W, {lo / ac_bound(pp_w):.1f} x the bound, "
          f"{lo / ac_loss(pp_w):.1f} x the estimate")

# The overcurrent protection watches each power MOSFET (IOC 7 A min, Table 5) and the parallel mode
# shares the current between two of them; at 17.4 V the threshold is 91.4 % of its 58 V value (Figure 20).
OC_DEVICE_MIN = 2 * 7.0 * 0.914
print("\n2. Locked rotor (every start from rest, or a jammed fan): cycle-by-cycle limiter in PWM trimming, the")
print("   firmware commanding any duty; on-time = max(t_b, crossing) + 200 ns, then low-side recirculation until")
print("   the next period. Steady state after 600 periods, VBAT 17.4 V, I_lim at the band's top. A minimum on-time")
print("   sets a minimum mean voltage: at 400 kHz a low-resistance motor stalls far above the limit; at 100 kHz the")
print("   same on-time is a quarter of the duty. The overcurrent protection trips per MOSFET (IOC 7-14 A), so the")
print(f"   paralleled pair stops only at {OC_DEVICE_MIN:.1f}-28 A: a stall below that persists. 'driver W': the conduction")
print("   loss mean^2 x RDS(on) at 125 C (1.95 x 82.5 mOhm), a lower bound on the STSPIN958's heat (section 3).")
print(f"   {'f kHz':>5} {'R ohm':>5} {'Lm uH':>6} {'t_b ns':>6} | {'mean A':>6} {'peak A':>6} {'L6 left':>7} {'driver W':>8} "
      f"{'vs OC ' + format(OC_DEVICE_MIN, '.1f') + ' A':>11}")


def stall(f, r, lm, tb, n=250, periods=600):
    tp = 1 / f
    rt_on = r + RDS25 * 1.95 + DCR + RSNS
    rt_off = r + RDS25 * 1.95 + DCR
    i, acc, pk, dt = 0.0, 0.0, 0.0, tp / n
    for period in range(periods):
        t, on, crossed = 0.0, True, None
        for _ in range(n):
            lt = lm + l_choke(i)
            if on:
                i += (17.4 - rt_on * i) / lt * dt
                if crossed is None and i >= I_LIM_HI:
                    crossed = t
                if crossed is not None and t >= max(tb, crossed) + 200e-9:
                    on = False
            else:
                i += -rt_off * i / lt * dt
            t += dt
            if period >= periods - 50:
                acc += i
                pk = max(pk, i)
    return acc / (50 * n), pk


worst_lo = {100e3: 0.0, 50e3: 0.0}
peaks_50_short = []
stall_400 = []
for f in (400e3, 100e3, 50e3):
    for r in (0.2, 0.5, 1.2):
        for lm in (0.12e-6, 3e-6):
            for tb in (280e-9, 500e-9, 1000e-9):
                if f == 400e3 and tb > 500e-9:
                    continue
                mean, pk = stall(f, r, lm, tb, periods=600 if f == 400e3 else 120)
                if f in worst_lo:
                    worst_lo[f] = max(worst_lo[f], pk)
                if f == 50e3 and tb <= 500e-9:
                    peaks_50_short.append(pk)
                if f == 400e3:
                    stall_400.append((mean, pk, mean**2 * RDS25 * 1.95))
                print(f"   {f/1e3:5.0f} {r:5.1f} {lm*1e6:6.2f} {tb*1e9:6.0f} | {mean:6.2f} {pk:6.2f} "
                      f"{l_choke(pk)/l_choke(0)*100:6.0f} % {mean**2 * RDS25 * 1.95:8.1f} "
                      f"{'trips' if pk > OC_DEVICE_MIN else 'below':>11}")
below = [m for m in stall_400 if m[1] <= OC_DEVICE_MIN]
print(f"   at 400 kHz a stall holds {min(m[0] for m in stall_400):.1f}-{max(m[0] for m in stall_400):.1f} A mean, "
      f"{min(m[2] for m in stall_400):.1f}-{max(m[2] for m in stall_400):.1f} W of conduction loss in the driver; only peaks")
print(f"   above {OC_DEVICE_MIN:.1f} A can trip the overcurrent protection (and only if the part's IOC sits low), and every case")
print(f"   peaking below it ({max(m[0] for m in below):.1f} A mean, {max(m[2] for m in below):.1f} W at the worst) persists: the driver"
      " cycles through its")
print(f"   thermal shutdown and L6 runs far past its {ISAT20} A 20 % point.")
print(f"   Worst peak at 100 kHz {worst_lo[100e3]:.2f} A, at 50 kHz {worst_lo[50e3]:.2f} A (a 1 us blanking")
print(f"   with a 0.2 ohm motor; up to 500 ns of blanking the 50 kHz peaks stay at {min(peaks_50_short):.1f}-{max(peaks_50_short):.1f} A,"
      f" L6 keeping {l_choke(max(peaks_50_short)) / l_choke(0) * 100:.0f} %")
print("   of its inductance): start the fan at 50 kHz and move to 400 kHz once it spins (Fan_TOFF no longer low);")
print("   at 400 kHz, Fan_TOFF low in most periods over 1-2 ms is a jam: back to 50 kHz or Fan_Enable low; a fan that")
print("   keeps Fan_TOFF low at 50 kHz is jammed")

print("\n3. STSPIN958 heat at 400 kHz, 17.4 V, D 0.22 (1S) / 0.43 (2S), 1.0 V/ns edges; Tj from 40 C")


def heat(i, d, pp, worst, rth):
    tj = 80.0
    for _ in range(50):
        if worst:
            k = (max(tj, 25) + 273.15) / 298.15
            hot = k ** 2.33
            tdt, iq = 300e-9, 10e-3
        else:
            hot = 1 + 0.25 * (tj - 25) / 100
            tdt, iq = 100e-9, 7e-3
        i2 = i ** 2 + pp ** 2 / 12
        p_cond = i2 * RDS25 * hot                    # one switch path conducts at any time
        p_sw = 17.4 * i * (17.4 / 1e9) * F           # rise + fall, 17.4 ns each at 1.0 V/ns
        p_dt = 2 * tdt * F * 0.9 * i
        p_q = 17.4 * iq
        p = p_cond + p_sw + p_dt + p_q
        tj = 40 + p * rth
        if tj > 175:
            break
    return p, tj, p_cond, p_sw, p_dt, p_q


for i in (1.0, 2.5, I_LIM_HI):
    for d in (0.22, 0.43):
        pp = ripple_pp(17.4, d, 0.12e-6 + l_choke(i))
        a = heat(i, d, pp, False, 35.8)
        b = heat(i, d, pp, True, 45.0)
        print(f"   {i:4.2f} A D {d:.2f}: typical {a[0]:4.2f} W -> Tj {a[1]:5.1f} C | bound {b[0]:4.2f} W "
              f"(cond {b[2]:.2f}, sw {b[3]:.2f}, dead {b[4]:.2f}, VS {b[5]:.2f}) -> Tj {b[1]:5.1f} C")
print("   (Tj above 150 C: the thermal shutdown stops the driver; the bound case needs the limiter holding the top of")
print("    its band continuously, a stall, which the firmware ends from Fan_TOFF)")
print("   C33 (X7R, 125 C) sits on the board beside the pad, at most Tj - P x RthJB (17.4 C/W) below the junction")
p, tj = heat(2.5, 0.43, ripple_pp(17.4, 0.43, 0.12e-6 + l_choke(2.5)), True, 45.0)[:2]
print(f"   at 2.5 A bound: Tj {tj:.0f} C, board at the pad about {tj - p*17.4:.0f} C")

print("\n4. REF for the chosen motor. I_run: its running current at the highest duty the fan will use.")
k_lo = I_LIM_LO / I_LIM
print(f"   I_peak = max(1.5 x I_run, (I_run + h) / {k_lo:.3f}), h the ripple half-amplitude at the lowest plausible")
print(f"   inductance (section 1: {half['1S']:.2f} A for a 1S motor, {half['2S']:.2f} A for a 2S motor): 1.5x leaves the start-up and gust margin,")
print("   the second term keeps the ripple peak under the bottom of the REF band (above it the limiter trims the pulse")
print("   and the mean current falls short). VREF = I_peak x RSNS x ACL = I_peak x 0.25 V/A; R29 = R28 x VREF /")
print("   (3.3 V - VREF), R28 4.7 kOhm, the nearest E24 value at or above. The band's top (x "
      f"{I_LIM_HI/I_LIM:.3f}) stays at or below {ISAT20} A (L6's 20 % point):")
ipk_max = ISAT20 / (I_LIM_HI / I_LIM)
print(f"   I_peak <= {ipk_max:.2f} A, so I_run <= {min(ipk_max/1.5, ipk_max*k_lo-half['1S']):.2f} A (1S) or {min(ipk_max/1.5, ipk_max*k_lo-half['2S']):.2f} A (2S);"
      " above it the research's discrete half-bridge applies.")
for cls, h in (("1S", half["1S"]), ("2S", half["2S"])):
    for irun in (1.0, 1.5, 2.0, 2.5):
        ipk = max(1.5 * irun, (irun + h) / k_lo)
        vref = ipk * RSNS * 10
        r29 = 4.7e3 * vref / (3.3 - vref)
        top = ipk * I_LIM_HI / I_LIM
        over = f", above L6's {ISAT20} A 20 % point" if top > ISAT20 else ""
        print(f"   {cls} I_run {irun:3.1f} A -> I_peak {ipk:4.2f} A, VREF {vref:5.3f} V, R29 {r29/1e3:5.2f} kOhm (band top {top:4.2f} A{over})")
print(f"   board: R29 2.0 kOhm -> VREF {REF_TYP:.3f} V, {I_LIM:.2f} A typ, {I_LIM_LO:.2f}-{I_LIM_HI:.2f} A: a 1S motor up to 2.5 A running")
