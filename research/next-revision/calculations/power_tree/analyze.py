#!/usr/bin/env python3
"""Metrics at VDDA for the sim_power_tree.py cases, as the ADC sees them.

- LDO cases (B, C): the datasheet PSRR magnitude curve is applied to the simulated LDO input spectrum
  (zero-phase assumption) and the result added to the simulated VDDA; the LDO's datasheet output noise
  is added in quadrature to the rms figures only (it is broadband and random).
- Windows: wall scan = 75-150 us after each 200 us slot start (4 lit + 1 dark slot per 1 ms frame,
  firmware v1 target.hpp); motor-current samples = centre-aligned 100 kHz PWM, both phase centres
  (every 5 us, at 2.5 us offset) - synchronous with the motor ripple put on the battery node.
- 1 LSB16 = 3.3 V / 65536 = 50.35 uV. For a reading at full scale, a VDDA error of x uV is x/50.35 LSB
  (code = 65536 * Vin / VDDA); at half scale it is half of that.
"""
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
LSB = 3.3 / 65536
T0 = 1.0e-3

PROBES = {
    "A": ["vdda", "v3d", "vbat", "va0"],
    "B": ["vdda", "v3d", "vbat", "v5"],
    "C": ["vdda", "v3d", "vbat", "vpre"],
    "F": ["vdda", "v3d", "vbat"],
}

# PSRR magnitude curves, dB, from the datasheets (points between are interpolated in log f).
# TPS7A20 (SBVS338H sec. 5.5, IOUT = 20 mA, VIN = VOUT + 1 V): 95 dB 100 Hz, 95 dB 1 kHz, 75 dB 10 kHz,
# 75 dB 100 kHz, 45 dB 1 MHz. Above 1 MHz: held at 45 dB (ASSUMPTION; not given).
PSRR_TPS7A20 = [(10, 95), (1e3, 95), (1e4, 75), (1e5, 75), (1e6, 45), (1e9, 45)]
# TPS7A49 (SBVS121E p1 / sec. 6.5): 72 dB at 120 Hz, >= 52 dB 10 Hz-400 kHz. Taken as 52 dB flat
# from 1 kHz to 400 kHz (conservative); above 400 kHz 40 dB (ASSUMPTION; not given).
PSRR_TPS7A49 = [(10, 72), (120, 72), (1e3, 52), (4e5, 52), (1e6, 40), (1e9, 40)]
LDO = {"B": ("v5", PSRR_TPS7A20, 7e-6), "C": ("vpre", PSRR_TPS7A49, 15.4e-6)}


def load(key):
    fam = "A" if key.startswith("A") else key[0]
    names = PROBES[fam]
    d = np.loadtxt(OUT / f"{key}.dat")
    t = d[:, 0]
    sig = {n: d[:, 1 + 2 * i] for i, n in enumerate(names)}
    return fam, t, sig


def psrr_feed(t, x, curve):
    """Output ripple = |1/PSRR(f)| x input spectrum (zero phase). Linear trend removed first, so a
    slow start-up drift does not wrap around the FFT window as a false step."""
    dt = t[1] - t[0]
    xa = x - np.polyval(np.polyfit(t, x, 1), t)
    X = np.fft.rfft(xa)
    f = np.fft.rfftfreq(len(xa), dt)
    fp = np.array([c[0] for c in curve])
    dbp = np.array([c[1] for c in curve])
    db = np.interp(np.log10(np.maximum(f, 1.0)), np.log10(fp), dbp)
    return np.fft.irfft(X * 10 ** (-db / 20), n=len(xa))


def band(t, x, fmin=None, fmax=None):
    dt = t[1] - t[0]
    X = np.fft.rfft(x - x.mean())
    f = np.fft.rfftfreq(len(x), dt)
    m = np.ones_like(f, bool)
    if fmin is not None:
        m &= f >= fmin
    if fmax is not None:
        m &= f < fmax
    return np.fft.irfft(np.where(m, X, 0), n=len(x))


def tone_amps(t, v):
    """Peak amplitude of the 100 kHz (motor), 300 kHz (fan) and switching-frequency lines (Hann window)."""
    dt = t[1] - t[0]
    w = np.hanning(len(v))
    X = np.abs(np.fft.rfft((v - v.mean()) * w)) * 2 / w.sum()
    f = np.fft.rfftfreq(len(v), dt)
    out = {}
    for name, f0 in (("a100k", 100e3), ("a300k", 300e3), ("a400k", 400e3), ("a1M1", 1.1e6)):
        m = (f > f0 * 0.97) & (f < f0 * 1.03)
        out[name] = X[m].max()
    return out


def metrics(key):
    fam, t, s = load(key)
    v = s["vdda"].copy()
    noise_rms = 0.0
    if fam in LDO:
        node, curve, noise_rms = LDO[fam]
        v = v + psrr_feed(t, s[node], curve)
    hf = band(t, v, fmin=200e3)          # switching ripple and harmonics
    lf = band(t, v, fmax=200e3)          # load/line disturbances incl. 100 kHz motor ripple
    # discard 0.4 ms at both ends (FFT edge effects, residual start-up)
    keep = (t > t[0] + 0.4e-3) & (t < t[-1] - 0.4e-3)
    tones = tone_amps(t[keep], v[keep])
    t, v, hf, lf = t[keep], v[keep], hf[keep], lf[keep]
    s = {k: x[keep] for k, x in s.items()}
    ac = v - v.mean()
    r = {
        **tones,
        "mean": v.mean(),
        "pp": ac.max() - ac.min(),
        "rms": float(np.sqrt(np.mean(ac ** 2) + noise_rms ** 2)),
        "hf_pp": hf.max() - hf.min(),
        "lf_pp": lf.max() - lf.min(),
    }
    # wall-scan windows
    means, inner, lit, dark = [], [], [], []
    for fr in range(1, 6):
        for slot in range(5):
            a = T0 + fr * 1e-3 + slot * 0.2e-3 + 75e-6
            b = a + 75e-6
            m = (t >= a) & (t < b)
            if m.sum() < 10:
                continue
            w = v[m]
            means.append(w.mean())
            inner.append(w - w.mean())
            (dark if slot == 4 else lit).append(w.mean())
    inner = np.concatenate(inner)
    means = np.array(means)
    r["scan_mean_spread"] = means.max() - means.min()
    r["lit_minus_dark"] = np.mean(lit) - np.mean(dark)
    r["scan_inner_rms"] = float(np.sqrt(np.mean(inner ** 2) + noise_rms ** 2))
    # motor current samples at the PWM phase centres (every 5 us, 2.5 us offset)
    ts = np.arange(t[0] + 2.5e-6, t[-1], 5e-6)
    vs = np.interp(ts, t, v)
    r["isamp_pp"] = vs.max() - vs.min()
    # line rejection (meaningful for the *_line cases: constant loads, no digital rail)
    vb = tone_amps(t, s["vbat"])
    for name in ("a100k", "a300k"):
        r[f"rej_{name}"] = 20 * np.log10(max(r[name], 1e-12) / vb[name])
        r[f"vbat_{name}"] = vb[name]
    # 3V3_D and the analog regulator input for reference
    r["v3d_pp"] = s["v3d"].max() - s["v3d"].min()
    r["vbat_pp"] = s["vbat"].max() - s["vbat"].min()
    for n in ("va0", "v5", "vpre"):
        if n in s:
            r[f"{n}_pp"] = s[n].max() - s[n].min()
            r[f"{n}_mean"] = s[n].mean()
    return r


def fmt(x):
    return f"{x*1e6:9.1f} uV ({x/LSB:7.2f} LSB)"


if __name__ == "__main__":
    keys = sys.argv[1:] or sorted(p.stem for p in OUT.glob("*.dat"))
    rows = []
    for key in keys:
        try:
            r = metrics(key)
        except Exception as e:  # noqa: BLE001
            print(f"{key}: {e}")
            continue
        rows.append((key, r))
        print(f"== {key}")
        print(f"  VDDA mean {r['mean']:.4f} V; p-p {fmt(r['pp'])}; rms {fmt(r['rms'])}")
        print(f"  >200 kHz (switching) p-p {fmt(r['hf_pp'])};  <200 kHz p-p {fmt(r['lf_pp'])}")
        print(f"  wall scan: window-mean spread {fmt(r['scan_mean_spread'])}; lit-dark {fmt(r['lit_minus_dark'])}; "
              f"in-window rms {fmt(r['scan_inner_rms'])}")
        print(f"  motor-current sample instants: p-p {fmt(r['isamp_pp'])}")
        if key.endswith("_line"):
            print(f"  LINE REJECTION battery->VDDA: 100 kHz {r['rej_a100k']:.1f} dB (VBAT line {r['vbat_a100k']*1e3:.1f} mV), "
                  f"300 kHz {r['rej_a300k']:.1f} dB (VBAT line {r['vbat_a300k']*1e3:.1f} mV)")
        print("  lines (peak amplitude): " + ", ".join(f"{k} {r[k]*1e6:.2f} uV" for k in ("a100k", "a300k", "a400k", "a1M1")))
        extra = "  ".join(f"{k} {v*1e3:.2f} mV" if k.endswith('_pp') else f"{k} {v:.3f} V"
                          for k, v in r.items() if k[:2] in ('va', 'v5', 'vp') or k in ('v3d_pp', 'vbat_pp'))
        print(f"  {extra}")
    # compact table
    print("\n| case | VDDA p-p | rms | 100 kHz line | fSW line | scan-mean spread | lit-dark | in-window rms | I-sample p-p |")
    print("|---|---|---|---|---|---|---|---|---|")
    for key, r in rows:
        def u(x):
            return f"{x*1e6:.1f} µV / {x/LSB:.2f}"
        print(f"| {key} | {u(r['pp'])} | {u(r['rms'])} | {u(r['a100k'])} | {u(max(r['a400k'], r['a1M1']))} | "
              f"{u(r['scan_mean_spread'])} | {u(abs(r['lit_minus_dark']))} | {u(r['scan_inner_rms'])} | {u(r['isamp_pp'])} |")
