"""Fan path check: STSPIN958 (parallel half-bridge, PWM trimming, 400 kHz) + XGL5030-472 4.7 uH + a not
yet chosen drone-class brushed coreless motor, over the whole plausible range of the motor's
inductance and resistance; the STSPIN958's heat with bounds on its unpublished data; the REF rule.

Run: python3 fan_choke_check.py (seconds). Output: fan_choke_check_out.txt.

Sources and bounds:
- STSPIN958 (ST DS14341 Rev 1): RDS(on) 165 mOhm per switch at 25 C, two in parallel (Table 5);
  minimum PWM pulse 280 ns (Table 2); REF limiter Eq. 1, ACL 9.5-10.5 (Table 5); IOC 7 A min;
  TSD 150 C; RthJA 35.8 C/W on the JESD51 board (Table 4); SR 2 V/ns with RSR 1 kOhm (Table 7).
  Not published: the RDS(on) temperature curve, the dead time, the VS operating current, the
  limiter blanking and comparator delay. Bounds used (inference):
  * RDS(on)(T): typical as the DRV8874's (TI SLVSF66A Figures 6-7, about +25 % at 125 C, the same
    kind of integrated BCD power switch); bound by the silicon electron lattice mobility,
    RDS ~ (T/298 K)^2.33 (Arora, Hauser, Roulston, IEEE TED 29 (1982): mu_lattice ~ T^-2.33),
    1.95x at 125 C.
  * Dead time: 100 ns typical, 300 ns bound per edge, body diode 0.9 V (the DRV8874's VSD) at the
    current, two edges per period.
  * VS operating current: 7 mA typical (the DRV8874's IVM maximum), 10 mA bound.
  * Board RthJA: 35.8 C/W typical, 45 C/W bound (main2's inner planes are 0.5 oz and the board is
    smaller than the JESD51 one); board ambient 40 C.
  * Limiter: on-time at least the blanking t_b (280 ns typical = the minimum pulse, 500 ns bound),
    plus a comparator delay of 200 ns (the amplifier's settling time, Table 5) after the crossing.
- XGL5030-472 (Coilcraft Doc 1576): 4.7 uH +-20 %, DCR 24.5 mOhm max, Isat 3.1 / 4.8 / 6.7 A at
  10 / 20 / 30 % drop. DC bias: Coilcraft's saturation SPICE model of the part (XGL5030-472_sat:
  L 4.4984 uH, Is 13.0461 A, a 0.7097), relative drop applied to the -20 % part. AC loss: Coilcraft's
  power-inductor loss tool for this part (as recorded in github.com/QY7/Power_toys,
  power_toys/data/coilcraft_loss_for_training/XGL5030-472.txt): 71.6 mW x dIpp^1.99 at 0.408 MHz,
  independent of the DC current, linear in f; part temperature rise 25.3 K/W (same tool).
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
SAT = dict(L=4.4984e-6, Is=13.0461, a=0.7097)
L_NOM, TOL, DCR = 4.7e-6, 0.20, 24.5e-3
RSNS, RDS25 = 25e-3, 0.165 / 2
REF_TYP = 3.3 * 2.0 / 6.7
I_LIM = REF_TYP / (RSNS * 10)
I_LIM_HI = (3.346 * 2.0 * 1.01 / (2.0 * 1.01 + 4.7 * 0.99)) / (RSNS * 0.99 * 9.5)
I_LIM_LO = (3.284 * 2.0 * 0.99 / (2.0 * 0.99 + 4.7 * 1.01)) / (RSNS * 1.01 * 10.5)
LM_EFF = (0.12e-6, 0.5e-6, 1e-6, 3e-6, 14e-6)


def flux(i):
    return SAT["L"] * SAT["Is"] * math.tanh((abs(i) / SAT["Is"]) ** SAT["a"]) ** (1 / SAT["a"])


def l_choke(i, tol=-TOL):
    h = 1e-4
    lo = max(abs(i) - h, 1e-6)
    return L_NOM * (1 + tol) * (flux(abs(i) + h) - flux(lo)) / (abs(i) + h - lo) / SAT["L"]


def ac_loss(dipp):
    return 71.6e-3 * (F / 408e3) * dipp ** 1.99


def ripple_pp(v, d, l_tot):
    return v * d * (1 - d) * T / l_tot


print("Fan path: STSPIN958 400 kHz + XGL5030-472 + drone coreless motor")
print(f"REF limit: typ {I_LIM:.2f} A, band {I_LIM_LO:.2f}-{I_LIM_HI:.2f} A (3V3_D 3.284-3.346 V, 1 % resistors, ACL 9.5-10.5,"
      " RSNS 1 %)")
print("XGL5030-472 at -20 %, incremental L: " + ", ".join(f"{i:.0f} A {l_choke(i)*1e6:.2f} uH" for i in (0, 2, 3, 4, 5, 6, 7)))

print("\n1. Running ripple at 400 kHz (choke -20 % and biased at the running current), worst VBAT 17.4 V")
print(f"   {'motor':>4} {'Lm uH':>6} {'I A':>4} {'D':>5} {'L tot':>6} {'dIpp':>5} {'peak':>5} {'limiter':>8} {'motor W':>7} {'choke mW':>8}")
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
            print(f"   {cls:>4} {lm2*1e6:6.2f} {i:4.1f} {d:5.2f} {lt*1e6:6.2f} {pp:5.2f} {pk:5.2f} {flag:>8} {pm:7.3f} {ac_loss(pp)*1e3:8.1f}")
print("   (motor W: ripple heat at the 1.2 ohm top of the range, an upper bound; 'clips': the peak reaches the")
print("    lowest REF limit and the limiter trims the pulse, which lowers the mean current, not a fault)")
print(f"   the worst: 1S, D = 0.5 never occurs; a 2S motor at D 0.43 with the lowest L: "
      f"{ripple_pp(17.4, 0.43, 0.48e-6 + l_choke(2.5)):.2f} A pp")

print("\n2. Locked rotor (every start from rest, or a jammed fan): cycle-by-cycle limiter in PWM trimming, the")
print("   firmware commanding any duty; on-time = max(t_b, crossing) + 200 ns, then low-side recirculation until")
print("   the next period. Steady state after 600 periods, VBAT 17.4 V, I_lim at the band's top. A minimum on-time")
print("   sets a minimum mean voltage: at 400 kHz a low-resistance motor stalls above the limit and can trip the")
print("   overcurrent shutdown (IOC 7-14 A); at 100 kHz the same on-time is a quarter of the duty.")
print(f"   {'f kHz':>5} {'R ohm':>5} {'Lm uH':>6} {'t_b ns':>6} | {'mean A':>6} {'peak A':>6} {'L6 left':>7} {'vs IOC 7 A':>10}")


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
for f in (400e3, 100e3, 50e3):
    for r in (0.2, 0.5, 1.2):
        for lm in (0.12e-6, 3e-6):
            for tb in (280e-9, 500e-9, 1000e-9):
                if f == 400e3 and tb > 500e-9:
                    continue
                mean, pk = stall(f, r, lm, tb, periods=600 if f == 400e3 else 120)
                if f in worst_lo:
                    worst_lo[f] = max(worst_lo[f], pk)
                print(f"   {f/1e3:5.0f} {r:5.1f} {lm*1e6:6.2f} {tb*1e9:6.0f} | {mean:6.2f} {pk:6.2f} "
                      f"{l_choke(pk)/l_choke(0)*100:6.0f} % {'trips' if pk > 7.0 else 'below':>10}")
print(f"   worst peak at 100 kHz {worst_lo[100e3]:.2f} A (only a 1 us blanking with a 0.2 ohm motor trips), at 50 kHz"
      f" {worst_lo[50e3]:.2f} A: start the fan at 50 kHz and move to")
print("   400 kHz once it spins (Fan_TOFF no longer asserting); a fan that never stops asserting TOFF is jammed")

print("\n3. STSPIN958 heat at 400 kHz, 17.4 V, D 0.22 (1S) / 0.43 (2S), 2 V/ns edges; Tj from 40 C")


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
        p_sw = 17.4 * i * (17.4 / 2e9) * F           # rise + fall, 8.7 ns each at 2 V/ns
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
print("   inductance (section 1: 1.05 A for a 1S motor, 1.4 A for a 2S motor): 1.5x leaves the start-up and gust margin,")
print("   the second term keeps the ripple peak under the bottom of the REF band (above it the limiter trims the pulse")
print("   and the mean current falls short). VREF = I_peak x RSNS x ACL = I_peak x 0.25 V/A; R29 = R28 x VREF /")
print("   (3.3 V - VREF), R28 4.7 kOhm, the nearest E24 value at or above. The band's top (x "
      f"{I_LIM_HI/I_LIM:.3f}) stays at or below 4.8 A (L6's 20 % point):")
ipk_max = 4.8 / (I_LIM_HI / I_LIM)
print(f"   I_peak <= {ipk_max:.2f} A, so I_run <= {min(ipk_max/1.5, ipk_max*k_lo-1.05):.2f} A (1S) or {min(ipk_max/1.5, ipk_max*k_lo-1.4):.2f} A (2S);"
      " above it the research's discrete half-bridge applies.")
for cls, h in (("1S", 1.05), ("2S", 1.4)):
    for irun in (1.0, 1.5, 2.0, 2.5):
        ipk = max(1.5 * irun, (irun + h) / k_lo)
        vref = ipk * RSNS * 10
        r29 = 4.7e3 * vref / (3.3 - vref)
        print(f"   {cls} I_run {irun:3.1f} A -> I_peak {ipk:4.2f} A, VREF {vref:5.3f} V, R29 {r29/1e3:5.2f} kOhm (band top {ipk*I_LIM_HI/I_LIM:4.2f} A)")
print(f"   board: R29 2.0 kOhm -> VREF {REF_TYP:.3f} V, {I_LIM:.2f} A typ, {I_LIM_LO:.2f}-{I_LIM_HI:.2f} A: a 1S motor up to 2.5 A running")
