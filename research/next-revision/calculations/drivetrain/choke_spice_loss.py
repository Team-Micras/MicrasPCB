"""Wheel/fan choke AC (ripple) loss cross-check from Coilcraft Document 267 SPICE models
(XAL7070 and XGL5030 tables, revised 12/14/22).

AC (ripple) loss of a Coilcraft power inductor from its Document 267 lumped SPICE model:
Z = R2 + [ (RVAR1 + j w LVAR) || (1/(j w C) + R1) || RVAR2 ],  RVAR = k sqrt(f), LVAR = k3 - k4 ln(k5 f) uH.
Triangular ripple of peak-to-peak dI at duty D: Fourier series of the current, loss = sum In_rms^2 Re(Z(nf) - R2)."""
import cmath, math

def z_ac(p, f):
    w = 2 * math.pi * f
    l = (p["k3"] - p["k4"] * math.log(p["k5"] * f)) * 1e-6
    a = p["k1"] * math.sqrt(f) + 1j * w * l
    b = p["R1"] + 1 / (1j * w * p["C"])
    c = p["k2"] * math.sqrt(f)
    return 1 / (1 / a + 1 / b + 1 / c), l

def tri_harmonics(dipp, d, nmax=41):
    # triangle rising for D, falling for 1-D, peak-to-peak dipp: Fourier amplitudes (A peak)
    out = []
    for n in range(1, nmax + 1):
        cn = dipp / (n * n * math.pi * math.pi * d * (1 - d)) * math.sin(n * math.pi * d)
        out.append((n, abs(cn)))
    return out

def loss(p, f, dipp, d=0.5):
    tot = 0.0
    for n, a in tri_harmonics(dipp, d):
        zn, _ = z_ac(p, n * f)
        tot += (a / math.sqrt(2)) ** 2 * zn.real
    return tot

XAL = dict(R1=21, R2=8.44e-2, C=15.65e-12, k1=3.26e-5, k2=2.94, k3=47, k4=0.339, k5=3.3e-3)
XGL = dict(R1=5.0, R2=2.45e-2, C=9.9e-12, k1=1.0e-5, k2=0.840, k3=4.7, k4=1e-6, k5=1e-6)

print("Coilcraft Document 267 models (XAL7070 and XGL5030 tables, rev. 12/14/22)")
for name, p, f in (("XGL5030-472", XGL, 408e3), ("XAL7070-473", XAL, 100e3)):
    z, l = z_ac(p, f)
    print(f"{name} at {f/1e3:.0f} kHz: LVAR {l*1e6:.1f} uH, ESR(AC) {z.real:.3f} ohm")
print("\nCheck against Coilcraft's loss tool for XGL5030-472 (71.6 mW x dIpp^1.99 at 0.408 MHz):")
for dipp in (1.0, 2.0, 2.76):
    print(f"  dIpp {dipp:.2f} A: model {loss(XGL, 408e3, dipp)*1e3:6.1f} mW, loss tool {71.6*dipp**1.99:6.1f} mW")
print("\nXAL7070-473 at 100 kHz (wheel choke):")
for dipp, d in ((0.5, 0.5), (1.0, 0.5), (1.113, 0.5), (1.113, 0.3)):
    print(f"  dIpp {dipp:.3f} A, D {d}: AC loss {loss(XAL, 100e3, dipp, d)*1e3:6.1f} mW")

r = loss(XGL, 408e3, 2.0) / (71.6e-3 * 2.0 ** 1.99)
print(f"\nThe small-signal model gives {r:.2f} x the loss tool on the XGL5030-472 (both scale with dIpp^2).")
print(f"Scaled by that ratio, XAL7070-473 at 1.113 A pp: {loss(XAL, 100e3, 1.113, 0.5)/r*1e3:.0f} mW (D 0.5), "
      f"{loss(XAL, 100e3, 1.113, 0.3)/r*1e3:.0f} mW (D 0.3), against the 467 mW bound choke_check.py uses.")
