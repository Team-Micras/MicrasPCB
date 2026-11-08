# Q1, part 1: what each current sensor *sees* over one PWM period, and the bias of the
# average-current estimate, for the DCX 10 L 4.5 V at 16.8 V, 100 kHz, with the 47 uF choke.
#
# Drive pattern: sign-magnitude, slow decay through the bridge FETs that keep sensing
#   DRV8874 (low-side mirror): forward = HS1+LS2 (drive) / LS1+LS2 (brake); PH/EN mode, EN=PWM.
#   DRV8262 (high-side mirror): forward = HS1+LS2 (drive) / HS1+HS2 (brake); DECAY=0.
# Mirror visibility (DRV8874 SLVSF66A sec. 7.3.3.1 Eq. 1; DRV8262 SLVSFV5C sec. 6.5.1 Eq. 1):
#   only drain-to-source current is mirrored. Forward command, motor current i:
#     i > 0: LS2 (DRV8874) / HS1 (DRV8262) carries i D->S in BOTH drive and brake -> continuous.
#     i < 0: drive: no sensing FET conducts D->S -> reads 0;
#            brake: LS1 (DRV8874) / HS2 (DRV8262) carries |i| D->S -> reads |i|.
#   So both mirrors give the same visible waveform v(t) in this pattern.
# In-line shunt + INA241: sees signed i(t) all the time (outside the 1 us hold after each edge,
#   INA241 SBOSA30D sec. 7.3.1.1).
# Motor: R 2.9 ohm, L 45 uH (maxon cat. 2025 p100); maxon warns L_eff at 50-100 kHz is 30-80 % of
#   the 1 kHz value -> also 0.3 x L. Choke 47 uH, DCR ignored. Bridge R ~0.2 ohm ignored
#   (it only shifts the duty for a given mean current).
import math
import numpy as np

V, R, Lm, Lch, f = 16.8, 2.9, 45e-6, 47e-6, 100e3
T = 1 / f

def period(Imean, D, L, n=4000):
    """Periodic steady-state i(t) for unipolar PWM u in {V, 0}, back-EMF E set so mean(i) = Imean."""
    E = D * V - Imean * R           # average-voltage balance (exact for the periodic RL solution)
    tau, dt = L / R, T / n
    a = math.exp(-dt / tau)
    i = Imean
    for _ in range(60):             # iterate periods to steady state
        rec = np.empty(n)
        for k in range(n):
            u = V if k < D * n else 0.0
            iinf = (u - E) / R
            i = iinf + (i - iinf) * a
            rec[k] = i
    t = (np.arange(n) + 1) * dt
    return t, rec

def visible(t, i, D):
    on = t <= D * T
    v = np.where(i > 0, i, np.where(on, 0.0, -i))   # forward command
    return v

def sample(t, x, at):
    return float(np.interp(at, t, x))

rows = []
print("Bias of average-current estimates (mA) vs true period mean; forward command, D chosen per row")
print("L_eff   D    Imean  ripple_pp | inline: both-ctr  long-ctr | mirror: both-ctr long-ctr RC-avg | mirror on-ctr off-ctr (sign test)")
for kL in (1.0, 0.3):
    L = kL * Lm + Lch
    for D in (0.5, 0.3, 0.15):
        for Imean in (0.1, 0.5, 1.0, 3.0, -0.3):
            t, i = period(Imean, D, L)
            m = i.mean()
            ton_c, toff_c = D * T / 2, D * T + (1 - D) * T / 2
            inl_both = 0.5 * (sample(t, i, ton_c) + sample(t, i, toff_c))
            inl_long = sample(t, i, ton_c if D >= 0.5 else toff_c)
            v = visible(t, i, D)
            mir_on, mir_off = sample(t, v, ton_c), sample(t, v, toff_c)
            mir_both = 0.5 * (mir_on + mir_off)
            mir_long = mir_on if D >= 0.5 else mir_off
            mir_rc = v.mean()          # an RC filter on IPROPI averages the visible waveform
            # sign inference: on-centre ~0 while off-centre > 0 -> current opposes the command
            thr = 0.03                 # ~ the DRV8874 +-30 mA low-current error band
            mir_sgn = -mir_off if (mir_on < thr and mir_off > thr) else mir_both
            pp = i.max() - i.min()
            print(f"{kL:.1f}xL  {D:4.2f} {Imean:6.2f}  {pp:5.3f} A  | {1e3*(inl_both-m):8.2f} {1e3*(inl_long-m):8.2f} |"
                  f" {1e3*(mir_both-m):8.2f} {1e3*(mir_long-m):8.2f} {1e3*(mir_rc-m):8.2f} | {mir_on:6.3f} {mir_off:6.3f} | sign-inferred {1e3*(mir_sgn-m):7.2f}")
print("\nNotes: negative Imean = regenerative braking with a forward command. The mirror reads 0 at the")
print("on-centre and |I| at the off-centre, so firmware can infer the sign from the pair of samples.")

# Ripple crossing zero: smallest positive mean current for which i(t) stays > 0 (mirror continuous)
print("\nMean current below which the ripple crosses zero (mirror waveform becomes rectified):")
for kL in (1.0, 0.3):
    L = kL * Lm + Lch
    for D in (0.5, 0.3, 0.15):
        t, i = period(1.0, D, L)
        print(f"  {kL:.1f}xL D={D:4.2f}: ripple {i.max()-i.min():.3f} A pp -> zero crossing below ~{(i.mean()-i.min())*1e3:.0f} mA mean")

# DRV8874 ITRIP overshoot before regulation acts (tBLK 1.1 us + tDEG 0.6 us, SLVSF66A sec. 6.5),
# reversal from full speed: E = 14300 rpm / 2710 rpm/V = 5.28 V adds to VM.
E = 14300 / 2710
for kL, Lc in ((1.0, 47e-6), (0.3, 47e-6), (1.0, 0.0), (0.3, 0.0)):
    L = kL * Lm + Lc
    didt = (V + E) / L
    print(f"reversal di/dt with L={kL}xLds + {Lc*1e6:.0f} uH choke: {didt/1e6:.2f} A/us -> overshoot in 1.7 us {didt*1.7e-6:.2f} A above ITRIP")
