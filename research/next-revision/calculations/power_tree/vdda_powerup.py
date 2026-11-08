"""Power-up sequencing VDDA (3V3_A, ADP7142 U8, EN on 3V3_D) against VDD (3V3_D, L6981C33 IC7).

Rule (DS13311 Rev 5 section 3.7.1, Figure 2): while VDD < VDDmin (1.62 V, Table 13), VDDA must
stay below VDD + 300 mV.

VDD: the L6981 ramps its reference linearly from 0 to 3.3 V in TSS = 1.0 / 1.3 / 1.6 ms
(DS13554 Rev 3 Table 6, section 6.2 Figure 6).
VDDA: the ADP7142's EN (on 3V3_D) crosses its rising threshold 1.15 / 1.22 / 1.30 V (Rev K
Table 1); its output then follows Figure 48 (VOUT = 3.3 V curve, SS open, digitised here,
time from the EN step). The datasheet gives the start-up time as typical only (380 us to 90 %,
Table 1 note 3, no limits), so the curve is also run 30 % faster and slower.
With CSS on SS, Figure 49 / Eq. 8: SS time = 380 us + 0.6 V x CSS / 1.15 uA; modelled as the same
delay then a linear ramp to 90 % at that time (Figure 49's curves are close to linear).
"""

def interp(x, xs, ys):
    if x <= xs[0]:
        return ys[0]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            return ys[i-1] + (ys[i]-ys[i-1]) * (x-xs[i-1]) / (xs[i]-xs[i-1])
    return ys[-1]

def linspace(a, b, n):
    return [a + (b-a)*i/(n-1) for i in range(n)]

FIG48 = [(0.0, 0.0), (0.060, 0.0), (0.095, 0.95), (0.145, 1.75), (0.195, 2.25), (0.245, 2.60),
         (0.295, 2.82), (0.395, 3.08), (0.495, 3.20), (0.700, 3.28), (2.0, 3.30)]
t48 = [p[0] for p in FIG48]; v48 = [p[1] for p in FIG48]
VDDMIN = 1.62

def vdda(t_rel, speed=1.0, css=0.0):
    if t_rel <= 0:
        return 0.0
    if css == 0.0:
        return interp(t_rel * speed, t48, v48)
    t90 = 0.380 + 0.6 * css / 1.15e-6 * 1e3  # ms
    if t_rel < 0.06:
        return 0.0
    return min(3.3, 0.9 * 3.3 * (t_rel - 0.06) / (t90 - 0.06))

def worst(css=0.0):
    rows = []
    for tss in (1.0, 1.3, 1.6):
        for en in (1.15, 1.22, 1.30):
            for speed in (0.7, 1.0, 1.3):
                slope = 3.3 / tss  # V/ms
                t_en = en / slope
                t_min = VDDMIN / slope
                ts = linspace(t_en, t_min, 400)
                margin = min(s * slope + 0.3 - vdda(s - t_en, speed, css) for s in ts)
                rows.append((margin, tss, en, speed))
    return sorted(rows)

for css in (0.0, 1e-9, 2.2e-9, 10e-9):
    rows = worst(css)
    typ = [r for r in rows if r[1] == 1.3 and r[2] == 1.22 and r[3] == 1.0][0]
    print(f"CSS {css*1e9:4.1f} nF: typical margin (VDD + 0.3 V - VDDA, VDD < 1.62 V) {typ[0]:+.2f} V;"
          f" worst {rows[0][0]:+.2f} V at TSS {rows[0][1]} ms, EN {rows[0][2]} V, LDO speed x{rows[0][3]}")
    bad = [r for r in rows if r[0] < 0]
    print(f"   corners violating: {len(bad)} of {len(rows)}" + ("" if not bad else ": " + ", ".join(f"(TSS {b[1]}, EN {b[2]}, x{b[3]}: {b[0]:+.2f} V)" for b in bad[:8])))

# Robustness of the 1 nF fix to the unpublished spread of ISS (1.15 uA typical only): ISS x3 is
# the same as CSS / 3, with X7R's -10 % tolerance and -15 % over temperature on top.
rows = worst(1e-9 * 0.9 * 0.85 / 3)
print(f"CSS 1 nF with ISS x3 and CSS -24 %: worst margin {rows[0][0]:+.2f} V (TSS {rows[0][1]} ms, EN {rows[0][2]} V)")
