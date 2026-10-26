"""L6981C33 slope compensation check (DS13554 Rev 3, section 7.1 Eq. 8-13, section 8.4.2 Eq. 36-38).

For each ISLOPE hypothesis, inductor and input voltage:
  - QP (Eq. 13) against 0.4..1.33 (Eq. 38)
  - current-loop perturbation factor alpha = (Se - Sf)/(Sn + Se) (sub-harmonic stable iff |alpha| < 1),
    and a 40-cycle cycle-by-cycle iteration of a 10 mA peak-current perturbation as a check
  - phase lag of the sampling term FH (Eq. 12) at 40 kHz (fSW/10, the crossover Eq. 42 assumes)
  - ripple (Eq. 36) and peak (Eq. 39) at the 0.5 A ESP32-S3 TX load
"""
import math

VOUT, IOUT = 3.3, 0.5
FSWS = [360e3, 400e3, 440e3]
VINS = [4.3, 12.0, 17.4]
LS = [10e-6, 15e-6, 22e-6, 33e-6]
HYP = {"ISLOPE=1A (Eq. 11 literal)": 1.0, "ramp=0.45A (Table 6 IPK min 2.0-1.55)": 0.45,
       "ramp=0.5A (Table 6 IPK typ 2.3-1.8)": 0.5}
TOFF_MIN = 185e-9

def point(vin, L, fsw, islope):
    D = VOUT / vin
    D = min(D, 1 - TOFF_MIN * fsw)
    sn, sf, se = (vin - VOUT) / L, VOUT / L, islope * fsw
    mc = 1 + se / sn
    x = mc * (1 - D) - 0.5
    qp = 1 / (math.pi * x) if x > 0 else float("inf")
    alpha = (se - sf) / (sn + se)
    # cycle-by-cycle: perturbation of the valley current, propagated through one period
    e = 0.01
    for _ in range(40):
        e *= -alpha
    wn = math.pi * fsw
    w = 2 * math.pi * 40e3
    ph = math.degrees(math.atan2(w / (wn * qp), 1 - (w / wn) ** 2))
    ripple = (vin - VOUT) * D / (L * fsw)
    return D, qp, alpha, abs(e), ph, ripple, IOUT + ripple / 2

for name, isl in HYP.items():
    print(f"\n=== {name} ===")
    print(f"{'L':>6} {'fSW':>5} {'VIN':>5} {'D':>5} {'QP':>5} {'win':>4} {'alpha':>6} {'e40[A]':>8} {'FH@40k':>7} {'dIL':>5} {'ILpk':>5}")
    for L in LS:
        for fsw in FSWS:
            for vin in VINS:
                D, qp, a, e, ph, r, pk = point(vin, L, fsw, isl)
                ok = "ok" if 0.4 <= qp <= 1.33 else ("LOW" if qp < 0.4 else "HIGH")
                print(f"{L*1e6:5.0f}u {fsw/1e3:4.0f}k {vin:5.1f} {D:5.3f} {qp:5.2f} {ok:>4} {a:6.2f} {e:8.1e} {ph:6.1f}d {r:5.2f} {pk:5.2f}")

print("\n=== ST's own published configurations, ISLOPE=1A literal, fSW 400 kHz ===")
for vout, vin, L, src in [(3.3, 12, 22e-6, "Fig. 40-42 (MSS1038T-223ML)"), (3.3, 24, 22e-6, "Fig. 43-45 (MSS1038T-223ML)"),
                          (5.0, 12, 33e-6, "Fig. 37-39 (MSS1038T-333ML)"), (5.0, 24, 33e-6, "Fig. 34-36, Table 2/Table 9 (MSS1038T-333ML)")]:
    D = vout / vin
    sn = (vin - vout) / L
    mc = 1 + 400e3 / sn
    qp = 1 / (math.pi * (mc * (1 - D) - 0.5))
    print(f"VOUT {vout} VIN {vin} L {L*1e6:.0f}u: QP {qp:.2f}  [{src}]")

print("\n=== ISLOPE needed for sub-harmonic stability (Se > (Sf - Sn)/2), 22 uH, 4.3 V, 440 kHz ===")
L, vin, fsw = 22e-6, 4.3, 440e3
print(f"ISLOPE > {((VOUT/L) - (vin-VOUT)/L)/2/fsw:.3f} A")
