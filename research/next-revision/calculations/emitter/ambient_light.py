#!/usr/bin/env python3
"""Ambient light on main2's wall receivers (TPS601A(F) on 1 kOhm, boards/main2/Sensors.zen).

The receiver is an emitter follower: collector on 3V3_A, emitter on the ADC pin with 1 kOhm to GND,
so its output is IL x 1 kOhm and can never pass 3V3_A - VCE(sat) (0.25 V typ, 0.4 V max, TPS601A(F)
datasheet 2004-02-06 p2), below VREF+ = VDDA = 3V3_A: the ADC input never leaves its range, and
ambient light only uses up the phototransistor's headroom. The firmware (MicrasFirmware
config/targets/v1/target.hpp, wall_sensors_config) takes a dark reading above 80 % of full scale as
a blind sensor and a lit one above 85 % as saturated.

How much current does contest lighting make? The datasheet rates the light current IL at
E = 0.1 mW/cm2 from a 2870 K tungsten lamp, VCE = 3 V: 100 uA min unranked, rank A 100-300 uA,
B 200-600 uA, C 400-1200 uA (p2); IL-E (p3, typ) is about 0.26 mA at 0.1 mW/cm2 and 4 mA at
1 mW/cm2 (read from the curve: IL grows as E^1.2). Its relative spectral response (p3, typ, read
from the curve) peaks at 800 nm; its directional sensitivity halves 10 degrees off axis (p1, p4).

Method:
1. A source of illuminance Ev (lux) and spectrum P(l) produces the same IL as a 2870 K lamp of
   total irradiance E_eq = integral(S P) / [integral(S P_A) / integral(P_A)], with P scaled so that
   683 lm/W x integral(V P) = Ev (V: CIE 1924 photopic luminosity function, 10 nm table). E is
   taken as the lamp's total irradiance (the thermopile convention); the other reading, irradiance
   within the detector's band, would make the part less sensitive per lux, so this is the worst case.
2. The receiver looks at a diffuse surface of luminance Lv = rho x Ev / pi (a white wall lit at Ev),
   or at a bright source filling its field of view (a window); its irradiance is L x Omega with
   Omega = integral of the directional sensitivity over the sphere: pi theta^2 / ln 2 = 0.138 sr for
   a Gaussian lobe of 10 degrees half value; 0.20 sr is used for margin.
3. IL = IL(0.1 mW/cm2) x E_eq / 0.1 mW/cm2 below 0.1 mW/cm2 (conservative: the curve is steeper than
   linear), and x (E_eq / 0.1)^1.2 above, for the typical curve and for rank C's 1.2 mA maximum.

Contest lighting: the IEEE rules say "Do not make any assumptions about the amount of sunlight,
incident light, or fluorescent light" (IEEE Region 2 MicroMouse Rules 2020, 5.4.1); the All Japan
contest lit its 2005 expert final at 1200-1500 lux with mercury arc lamps and halogen spotlights,
400-500 lux in the heats (NTF, Outline of Micromouse 2005,
https://ntf.or.jp/archives/directory/en/game/26mmdata/26-outline.html). The cases below treat all
of it as halogen (3200 K), the most infrared-rich lamp, and add daylight.

Run: python3 research/next-revision/calculations/emitter/ambient_light.py (instant, no numpy).
"""

import math

# CIE 1924 photopic V(lambda), 380-780 nm in 10 nm steps.
V = [
    0.000039, 0.00012, 0.000396, 0.00121, 0.004, 0.0116, 0.023, 0.038, 0.06, 0.09098,
    0.13902, 0.20802, 0.323, 0.503, 0.71, 0.862, 0.954, 0.99495, 0.995, 0.952,
    0.87, 0.757, 0.631, 0.503, 0.381, 0.265, 0.175, 0.107, 0.061, 0.032,
    0.017, 0.00821, 0.004102, 0.002091, 0.001047, 0.00052, 0.000249, 0.00012, 0.00006, 0.00003,
    0.000015,
]  # fmt: skip
# TPS601A(F) relative spectral response, read from p3 (typ, Ta = 25 C), %.
S_POINTS = [
    (430, 1.3), (450, 2.5), (500, 9), (550, 28), (600, 47), (650, 68), (700, 87), (750, 95),
    (800, 100), (850, 92), (900, 72), (950, 48), (1000, 25), (1050, 7), (1100, 1.5), (1115, 1.2),
]  # fmt: skip

H, C, K = 6.626e-34, 2.998e8, 1.381e-23
STEP = 1.0  # nm


def interp(points, x):
    if x <= points[0][0] or x >= points[-1][0]:
        return 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            # log-linear between read points (the chart is logarithmic)
            return math.exp(math.log(y0) + (math.log(y1) - math.log(y0)) * (x - x0) / (x1 - x0))
    return 0.0


def v_lambda(nm):
    if nm < 380 or nm > 780:
        return 0.0
    i = (nm - 380) / 10
    j = int(i)
    if j >= len(V) - 1:
        return V[-1]
    return V[j] + (V[j + 1] - V[j]) * (i - j)


def s_lambda(nm):
    return interp(S_POINTS, nm) / 100


def planck(t):
    def p(nm):
        lam = nm * 1e-9
        return 1 / (lam**5 * (math.exp(H * C / (lam * K * t)) - 1))

    return p


def white_led(nm):
    # phosphor-converted white LED: blue pump 450 nm (20 nm FWHM) + phosphor 570 nm (120 nm FWHM);
    # an illustration: such lamps emit almost nothing above 750 nm
    g = lambda c, w: math.exp(-4 * math.log(2) * ((nm - c) / w) ** 2)  # noqa: E731
    return 0.6 * g(450, 20) + 1.0 * g(570, 120)


def integ(f, lo=300, hi=3000):
    n = int((hi - lo) / STEP)
    return sum(f(lo + i * STEP) for i in range(n + 1)) * STEP


def total(f):
    # total irradiance of a blackbody includes the far infrared: integrate to 30 um
    return integ(f, 200, 3000) + integ(f, 3000, 30000)


A = planck(2870)
R_A = integ(lambda x: s_lambda(x) * A(x)) / total(A)  # detector response per W of 2870 K light


def e_eq_per_lux(src):
    # tungsten-equivalent irradiance (mW/cm2) per lux of this source
    scale = 1 / (683 * integ(lambda x: v_lambda(x) * src(x), 380, 780))  # W/m2-units per lux
    resp = integ(lambda x: s_lambda(x) * src(x)) * scale
    return resp / R_A / 10  # W/m2 -> mW/cm2


OMEGA_GAUSS = math.pi * math.radians(10) ** 2 / math.log(2)
OMEGA = 0.20  # sr, with margin over the Gaussian lobe
IL_TYP, IL_MAX = 0.26e-3, 1.2e-3  # A at 0.1 mW/cm2 (typ curve p3; rank C max p2)
I_FS = 3.3 / 1000  # ADC full scale as receiver current through 1 kOhm
I_SAT = (3.3 - 0.4) / 1000  # the follower's ceiling at VCE(sat) max


def il(e_eq, il01):
    x = e_eq / 0.1
    return il01 * (x if x <= 1 else x**1.2)


def main():
    lux_a = 683 * integ(lambda x: v_lambda(x) * A(x), 380, 780) / total(A)
    print("== 1. The datasheet's light: 2870 K tungsten")
    print(f"   luminous efficacy {lux_a:.1f} lm/W of total radiation: 0.1 mW/cm2 = {lux_a * 1:.1f} lux")
    print(f"   share of its power the TPS601A sees (spectral response weighted): {R_A * 100:.1f} %")
    sources = {
        "tungsten 2870 K": A,
        "halogen 3200 K": planck(3200),
        "daylight (5800 K blackbody)": planck(5800),
        "white LED / fluorescent-like": white_led,
    }
    print("\n== 2. Tungsten-equivalent irradiance per 1000 lux of each source")
    k = {}
    for name, src in sources.items():
        k[name] = e_eq_per_lux(src) * 1000
        print(f"   {name:30s}: {k[name]:6.3f} mW/cm2 per 1000 lux")
    print(f"\n   field of view: Gaussian lobe {OMEGA_GAUSS:.3f} sr, {OMEGA} sr used")
    print("\n== 3. Ambient current on the receiver (typ part / rank C maximum), and as % of the ADC full scale")
    cases = [
        ("heats, 500 lux on a white wall (rho 0.9)", "halogen 3200 K", 0.9 * 500 / math.pi),
        ("final, 1500 lux on a white wall", "halogen 3200 K", 0.9 * 1500 / math.pi),
        ("3000 lux spotlit wall (2x the final)", "halogen 3200 K", 0.9 * 3000 / math.pi),
        ("10000 lux daylit wall by a window", "daylight (5800 K blackbody)", 0.9 * 10000 / math.pi),
        ("overcast sky through a window (5000 cd/m2)", "daylight (5800 K blackbody)", 5000),
        ("clear sky through a window (10000 cd/m2)", "daylight (5800 K blackbody)", 10000),
        ("1500 lux LED lighting on a white wall", "white LED / fluorescent-like", 0.9 * 1500 / math.pi),
    ]
    for label, src, lum in cases:
        ev_eq = lum * OMEGA  # lux-equivalent on the detector (cd/m2 x sr = lux)
        e = ev_eq * k[src] / 1000
        lo, hi = il(e, IL_TYP), il(e, IL_MAX)
        print(
            f"   {label:44s}: {lum:7.0f} cd/m2 -> {e * 1e3:6.2f} uW/cm2 eq; "
            f"{lo * 1e3:5.3f} / {hi * 1e3:5.3f} mA, {lo / I_FS * 100:4.1f} / {hi / I_FS * 100:4.1f} % FS"
        )
    print("\n== 4. Luminance in the field of view that makes a rank C receiver read 80 % dark (blind)")
    for src in ("halogen 3200 K", "daylight (5800 K blackbody)"):
        target = 0.8 * I_FS
        x = (target / IL_MAX) ** (1 / 1.2) * 0.1  # mW/cm2 eq
        lum = x / (k[src] / 1000) / OMEGA
        print(f"   {src:30s}: {lum:8.0f} cd/m2 (a white wall lit at {lum * math.pi / 0.9:8.0f} lux)")
    print(f"\n   receiver ceiling {I_SAT * 1e3:.1f} mA (3V3_A - VCE(sat) max over 1 kOhm), {I_SAT / I_FS * 100:.0f} % FS")


if __name__ == "__main__":
    main()
