#!/usr/bin/env python3
"""Littelfuse 501 series (F1): the Average Time Current Curves, digitised from the datasheet's own
vector paths.

Run: python3 -I fuse_501_curves.py <littelfuse 501 datasheet.pdf>   (needs pdftocairo and numpy)

The datasheet, Revised 12/14/17, is littelfuse.com's "fuse-501-datasheet" asset (research README
Sources, [Littelfuse 501]). Page 2 draws the four curves (10, 12, 15 and 20 A) as one stroked path;
pdftocairo turns the page into SVG with the path's control points intact. The axes are calibrated on
the chart's own axis path: 1 A to 1000 A over 178.55 pt (log), 0.001 s to 100 s over 231.70 pt (log).
The curves' parts above 100 s are the leader lines to their labels and are not used.
"""
import math
import os
import re
import subprocess
import sys
import tempfile

import numpy as np

pdf = sys.argv[1]
with tempfile.TemporaryDirectory() as d:
    svg = os.path.join(d, "p2.svg")
    subprocess.run(["pdftocairo", "-svg", "-f", "2", "-l", "2", pdf, svg], check=True, capture_output=True)
    s = open(svg).read()

path = [m.group(1) for m in re.finditer(r"<path([^>]*)/>", s) if "5.882263%" in m.group(1) and "C " in m.group(1)][0]
tx, ty = (float(x) for x in re.search(r'transform="matrix\(1, 0, 0, -1, ([-\d.]+), ([-\d.]+)\)"', path).groups())
d = re.search(r' d="([^"]*)"', path).group(1)


def amps(x):
    return 10 ** ((x - 371.9132) / (178.547738 / 3))


def secs(y):
    return 10 ** (-3 + (379.8108 - y) / (231.697519 / 5))


subs, cur = [], None
tok = re.findall(r"[MCL]|-?\d+\.?\d*", d)
i = 0
while i < len(tok):
    if tok[i] == "M":
        cur = (float(tok[i + 1]), float(tok[i + 2]))
        subs.append([cur])
        i += 3
    elif tok[i] == "L":
        cur = (float(tok[i + 1]), float(tok[i + 2]))
        subs[-1].append(cur)
        i += 3
    elif tok[i] == "C":
        p = [cur] + [(float(tok[i + 1 + 2 * k]), float(tok[i + 2 + 2 * k])) for k in range(3)]
        for t in np.linspace(0, 1, 60)[1:]:
            b = [(1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3]
            subs[-1].append((sum(b[k] * p[k][0] for k in range(4)), sum(b[k] * p[k][1] for k in range(4))))
        cur = p[3]
        i += 7
    else:
        i += 1
subs.sort(key=lambda a: a[0][0])
curves = {}
for name, pts in zip(["10A", "12A", "15A", "20A"], subs):
    a = np.array(pts)
    curves[name] = (amps(tx + a[:, 0]), secs(ty - a[:, 1]))

print("=== Opening current (A) at each time ===")
times = [100, 30, 10, 3, 1, 0.1, 0.01, 0.001]
print("rating " + " ".join("%8gs" % t for t in times))
for n, (cur_a, t_s) in curves.items():
    o = np.argsort(t_s)
    print("%-6s " % n + " ".join("%9.1f" % np.interp(math.log10(t), np.log10(t_s[o]), cur_a[o]) for t in times))

print("\n=== Opening time (s) at each current (inf: does not open within 100 s) ===")
currents = [25, 28, 30, 35, 40, 50, 60, 80, 100, 150]
print("rating " + " ".join("%8gA" % c for c in currents))
for n, (cur_a, t_s) in curves.items():
    o = np.argsort(cur_a)
    row = []
    for c in currents:
        if c < cur_a.min():
            row.append(float("inf"))
        else:
            t = 10 ** np.interp(math.log10(c), np.log10(cur_a[o]), np.log10(t_s[o]))
            row.append(t if t <= 100 else float("inf"))
    print("%-6s " % n + " ".join("%9.4g" % r for r in row))

print("\n=== I2t along each curve (A2s) at 1 ms (the table's melting I2t: 10.385 / 20.341 / 39.700 / 86.360) ===")
for n, (cur_a, t_s) in curves.items():
    o = np.argsort(t_s)
    print(n, "%.1f" % (np.interp(math.log10(0.001), np.log10(t_s[o]), cur_a[o]) ** 2 * 0.001))

print("\n=== F1 (12 A) against the board's budgets (boards/main2/test/test_power.zen battery_fuse) ===")
cur_a, t_s = curves["12A"]
o = np.argsort(t_s)
i100 = np.interp(2.0, np.log10(t_s[o]), cur_a[o])
print(f"opens in 100 s at {i100:.1f} A, {i100 * 0.85:.1f} A at 75 C (re-rating 0.85); a 10.1 A burst as a")
print(f"repeated pulse uses (10.1 / {i100 * 0.85:.1f})^2 = {(10.1 / (i100 * 0.85)) ** 2 * 100:.0f} % of the melting I2t at that")
print("duration, within the 22 % that withstands 100,000 pulses (Littelfuse Fuseholder Rerating, Chart II).")
