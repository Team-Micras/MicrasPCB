# Wheel choke check: DCX 10 L 4.5 V + XAL7070-473 47 uH behind a DRV8874 at 100 kHz, over the whole
# plausible range of the motor's effective inductance, the choke's tolerance and its DC bias.
# Run: python3 choke_check.py (about 1 min; needs numpy). Output: choke_check_out.txt.
#
# Inputs and sources:
# - Motor: maxon DCX 10 L 4.5 V (DCX10L01EBKL531 / DCX10L01EBSL531): R 2.9 ohm, L 45.3 uH at 1 kHz,
#   2710 rpm/V, 14,300 rpm max (maxon catalogue Feb 2025 p100; the product pages give 0.0453 mH).
# - Effective motor L at the PWM frequency, k = L(f) / L(1 kHz): maxon "Current ripple & external
#   motor chokes" V1.1 p7: 30-80 % at 50-100 kHz, "calculate ... by multiplying by 0.3"; Portescap
#   "Controlling Brushed DC Motors Using PWM" (2022): "At 100 kHz ... as low as 20 % of the catalogue
#   value". Swept 0.2-1.0; the overshoot below also takes k = 0 (choke alone) as the bound.
# - Choke: Coilcraft XAL7070-473ME (Doc 856): 47 uH +-20 %, DCR 84.41 typ / 97.07 mOhm max, Isat 4.2 A
#   (30 % drop), Irms 4.1 A (40 C rise). DC bias: Coilcraft's own saturation SPICE model of the part
#   (XAL7070-473_sat: flux = L Is tanh((I/Is)^a)^(1/a), L 41.781 uH, Is 9.6419 A, a 0.6669), whose
#   incremental inductance falls 30 % at 4.2 A, matching the datasheet's Isat; its relative drop is
#   applied to the -20 % tolerance part (37.6 uH at 0 A).
# - Choke AC (core) loss: Coilcraft's power-inductor loss tool, as recorded for the XAL7070-102..682
#   (dataset github.com/QY7/Power_toys, power_toys/data/coilcraft_loss_for_training, AC loss vs DC
#   current, ripple and frequency): AC loss = C f(MHz) dIpp^2.1 mW, independent of the DC current,
#   linear in f below 0.5 MHz, with C / L(uH)^1.05 = 24.0-32.7 over the series (same core, LossCore
#   "65"). For the 47 uH part (not in the dataset) the series maximum is extrapolated and doubled:
#   C = 2 x 32.7 x 47^1.05. Thermal resistance: the 40 C rise at Irms 4.1 A with the DCR at 65 C
#   gives 24 K/W; the tool's LossRth for the series is 17-26.5 K/W; 26.5 K/W is used.
# - DRV8874 (TI SLVSF66A section 6.5): tBLK 1.1 us + tDEG 0.6 us (typical, no limits published),
#   tFALL 150 ns; AIPROPI 450 uA/A, AERR +-5.5 % at 2-4 A; IOCP 6 A min with a 3 us deglitch (tOCP).
#   ITRIP (equation 3) with VREF = 3V3_D x 20k / 24.7k: 3V3_D 3.284-3.346 V (main2.zen), 1 %
#   resistors, RIPROPI 2.0 kOhm 1 %.
# - INA241A2 linear range +7.25 / -8.15 A (Sensors.zen).
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ripple_exact import ripple  # exact periodic RL ripple, unipolar PWM

R_M, L_M = 2.9, 45.3e-6
E_MAX = 14300 / 2710                     # back-EMF at the speed limit, V
K_RANGE = (0.2, 0.3, 0.5, 0.8, 1.0)
L_NOM, TOL = 47e-6, 0.20
DCR_MAX = 97.07e-3
SAT = dict(L=41.781e-6, Is=9.6419, a=0.6669)
C_LOSS = 2 * 32.7 * 47 ** 1.05           # mW / (MHz A^2.1)
RTH_L = 26.5                             # K/W
F = 100e3


def flux(i):
    return SAT["L"] * SAT["Is"] * math.tanh((abs(i) / SAT["Is"]) ** SAT["a"]) ** (1 / SAT["a"])


def l_ratio(i):
    """Incremental inductance at DC current i over its zero-current value (Coilcraft sat model)."""
    h = 1e-4
    lo = max(abs(i) - h, 1e-6)
    l_inc = (flux(abs(i) + h) - flux(lo)) / (abs(i) + h - lo)
    return l_inc / SAT["L"]


def l_choke(i, tol=-TOL):
    return L_NOM * (1 + tol) * l_ratio(i)


def itrip_band():
    v3_lo, v3_hi = 3.284, 3.346
    vref_lo = v3_lo * 20e3 * 0.99 / (20e3 * 0.99 + 4.7e3 * 1.01)
    vref_hi = v3_hi * 20e3 * 1.01 / (20e3 * 1.01 + 4.7e3 * 0.99)
    vref_typ = 3.3 * 20 / 24.7
    a = 450e-6
    return (vref_lo / (2e3 * 1.01 * a * 1.055), vref_typ / (2e3 * a), vref_hi / (2e3 * 0.99 * a * 0.945))


def overshoot(i0, v, k, t_resp, n=2000):
    """Current reached t_resp after the current sits at i0 at the start of a drive pulse during a
    full-speed reversal: di/dt = (V + E) / (k L_M + L_choke(i)), the choke at -20 %."""
    i, dt = i0, t_resp / n
    for _ in range(n):
        i += (v + E_MAX) / (k * L_M + l_choke(i)) * dt
    return i


print("Wheel choke check: DCX 10 L 4.5 V (R 2.9 ohm, L 45.3 uH at 1 kHz) + XAL7070-473, DRV8874 at 100 kHz")
print(f"Choke model: L at -20 % = {L_NOM*(1-TOL)*1e6:.1f} uH at 0 A; incremental L relative to 0 A:")
print("  " + ", ".join(f"{i:.1f} A {l_ratio(i)*100:.0f} %" for i in (1.0, 2.0, 3.0, 3.6, 4.2, 5.0, 6.0)))

print("\n1. Ripple at D = 0.5 (worst), 100 kHz; motor ripple loss Irms^2 x 2.9 ohm; choke AC loss")
print("   choke corners: 'nom' = 47 uH at 0 A, 'min' = -20 % and biased at 3 A (ITRIP)")
print(f"   {'V':>5} {'k':>4} {'choke':>5} {'L tot uH':>8} {'dIpp A':>7} {'motor W':>8} {'choke AC mW':>11}")
worst = None
for v in (12.0, 16.8, 17.4):
    for k in K_RANGE:
        for name, lch in (("nom", L_NOM), ("min", l_choke(3.0))):
            ipp, irms = ripple(v, R_M, k * L_M, F, Lext=lch)
            pac = C_LOSS * (F / 1e6) * ipp ** 2.1
            print(f"   {v:5.1f} {k:4.1f} {name:>5} {(k*L_M+lch)*1e6:8.1f} {ipp:7.3f} {irms**2*R_M:8.3f} {pac:11.1f}")
            if worst is None or ipp > worst[0]:
                worst = (ipp, irms ** 2 * R_M, pac, v, k, name)
ipp_w, pm_w, pac_w, v_w, k_w, n_w = worst
print(f"   worst: {ipp_w:.3f} A pp, {pm_w:.3f} W in the motor, {pac_w:.0f} mW choke AC loss (V {v_w}, k {k_w}, {n_w})")
print(f"   against the DCX 10 L's continuous loss budget of about 1.28 W (extra.py): {pm_w/1.28*100:.0f} % at the worst corner;")
print(f"   ripple rms {math.sqrt(pm_w/R_M):.2f} A. maxon's no-choke-needed rule (Ipp < 1.5 x IN = {1.5*0.648:.2f} A, p7) holds at"
      f" every point but V {v_w}, k {k_w}, '{n_w}'")

print("\n2. Choke temperature (Rth 26.5 K/W), DCR at 97.07 mOhm max + 0.393 %/K copper")
for irms_run, label in ((1.0, "run limit 1.0 A rms (60 s)"), (0.86, "run limit 0.86 A rms (120 s)"), (2.5, "2.5 A rms (beyond the run limits)")):
    t_rise = 0.0
    for _ in range(20):
        p_dc = irms_run ** 2 * DCR_MAX * (1 + 0.00393 * (t_rise + 25 - 20))
        t_rise = (p_dc + pac_w / 1e3) * RTH_L
    print(f"   {label:34}: DC {p_dc*1e3:5.0f} mW + AC {pac_w:3.0f} mW -> +{t_rise:4.1f} K")

lo, typ, hi = itrip_band()
print(f"\n3. ITRIP band (equation 3, tolerances, AERR -5.5/+5.5 %): {lo:.2f} / {typ:.2f} / {hi:.2f} A")
print("   Overshoot above ITRIP during a full-speed reversal at 17.4 V (V + E = "
      f"{17.4+E_MAX:.1f} V), current at ITRIP max when the pulse starts:")
print(f"   {'k':>4} | " + " | ".join(f"t {t*1e6:.2f} us" for t in (1.7e-6, 1.85e-6, 2.55e-6)) + "   (t = tBLK + tDEG; + tFALL; x 1.5)")
peak_w = 0.0
for k in (0.0,) + K_RANGE:
    cells = []
    for t in (1.7e-6, 1.85e-6, 2.55e-6):
        pk = overshoot(hi, 17.4, k, t)
        peak_w = max(peak_w, pk)
        cells.append(f"{pk-hi:4.2f} -> {pk:4.2f} A")
    print(f"   {k:4.1f} | " + " | ".join(cells))
print(f"   worst peak {peak_w:.2f} A: {6.0-peak_w:.2f} A below the 6 A OCP minimum (which also needs 3 us above")
print(f"   it, tOCP); inside the INA241's +7.25 / -8.15 A; the choke keeps {l_ratio(peak_w)*100:.0f} % of its inductance")
print(f"   there (soft saturation; the datasheet Isat is the 70 % point, 4.2 A)")
print(f"   at the datasheet timing (1.7 us) and the maxon factor 0.3: {overshoot(hi, 17.4, 0.3, 1.7e-6)-hi:.2f} A;"
      f" at the typical ITRIP, 16.8 V, nominal choke at 0 A bias: "
      f"{(16.8+E_MAX)/(0.3*L_M+L_NOM)*1.7e-6:.2f} A")
