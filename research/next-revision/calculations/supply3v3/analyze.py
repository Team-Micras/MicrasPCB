#!/usr/bin/env python3
"""Per-slot metrics from sim3v3.py wrdata output: mean of each signal over the ADC scan window."""
import sys
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent / "out"
T0 = 8.0e-3

def load(key):
    d = np.loadtxt(OUT / f"{key}.dat")
    return d[:, 0], d[:, 1], d[:, 3], np.abs(d[:, 5])

def win(t, y, a, b):
    m = (t >= a) & (t <= b)
    return y[m].mean()

def report(key, two=False):
    t, v3, va, il = load(key)
    print(f"== {key}")
    rows = []
    for f in range(3):
        if two:
            starts = [T0 + f * 1e-3 + k * 0.5e-3 for k in range(2)]
            dark = None
        else:
            starts = [T0 + f * 1e-3 + k * 0.2e-3 for k in range(4)]
            dark = T0 + f * 1e-3 + 0.8e-3
        for k, s in enumerate(starts):
            a, b = s + 75e-6, s + 150e-6
            rows.append((f, k, win(t, v3, a, b), win(t, va, a, b), win(t, il, a, b)))
        if dark is not None:
            a, b = dark + 75e-6, dark + 150e-6
            rows.append((f, 'dark', win(t, v3, a, b), win(t, va, a, b), 0.0))
    for r in rows:
        f, k, a3, aa, ii = r
        ratio = ii / aa if ii else float('nan')
        print(f"  frame {f} slot {k!s:>4}: 3V3 {a3:.4f}  VDDA {aa:.4f}  I_LED {ii*1e3:7.2f} mA  I/VDDA {ratio*1e3:.4f} mA/V")
    lit = [r for r in rows if r[1] != 'dark']
    va_l = np.array([r[3] for r in lit]); il_l = np.array([r[4] for r in lit])
    ratio = il_l / va_l
    darks = [r[3] for r in rows if r[1] == 'dark']
    print(f"  VDDA in scan windows: {va_l.min():.4f}..{va_l.max():.4f} V (spread {1e3*(va_l.max()-va_l.min()):.1f} mV)")
    if darks:
        print(f"  VDDA dark-slot minus lit-slot (mean): {1e3*(np.mean(darks)-va_l.mean()):.1f} mV")
    print(f"  I_LED spread {1e3*(il_l.max()-il_l.min()):.2f} mA = {100*(il_l.max()-il_l.min())/il_l.mean():.2f} %; "
          f"I/VDDA spread {100*(ratio.max()-ratio.min())/ratio.mean():.2f} %")

if __name__ == "__main__":
    for key in sys.argv[1:]:
        report(key, two=key.endswith("_two"))
