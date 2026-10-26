# Q1, part 2: measurement error budgets at 0.1 / 0.5 / 1 / 3 A (period-mean winding current),
# (a) 10 mOhm WSK2512 + INA241A2 + H725 16-bit ADC, phase-centre sampled
# (b) DRV8874 IPROPI (low-side mirror) into RIPROPI -> same ADC, phase-centre sampled
# (c) DRV8262 IPROPI (high-side mirror) into RIPROPI -> same ADC, phase-centre sampled
# Error = +-(gain part x I + offset part); terms combined by RSS (as in current_sense/budget.py),
# with a worst-case linear sum alongside. Temperature swing dT = 40 K (board/driver warm-up).
# Sources (all max unless "typ"):
#  INA241A2: Vos +-15 uV; dVos/dT +-150 nV/K; GERR +-0.01 %, drift +-1 ppm/K; CMRR 150 dB min;
#            ref divider +-0.01 % (VREF1=VS, VREF2=GND); en 49 nV/rtHz; BW 1.1 MHz.  SBOSA30D sec. 6.5
#  WSK2512 10 mOhm: +-0.5 % (D) or +-1 % (F); TCR +-35 ppm/K (5 mOhm-0.2 Ohm). Vishay doc 30108
#  WSK thermal EMF < 3 uV/K (Vishay Power Metal Strip overview VMN-PL0407-1703 p7, WSK2512 listed) -> 2 K mismatch
#  H725 ADC (typ, after calibration): EG +-15 LSB, INL +-13 LSB, SNR 77 dB s.e.  DS13311 Table 86
#  VDDA absolute: +-1.5 % analog rail (research/next-revision/README.md); after per-board gain cal ASSUMED +-0.2 % residual
#            drift (TPS7A20 tempco not extracted -> gap; VREFINT tracking can reduce it).
#  DRV8874: AIPROPI 450 uA/A; AERR +-30 mA (<0.4 A), +-7.5 % (0.4-1 A), +-6 % (1-2 A),
#            +-5.5 % (2-4 A), "combined effect of offset error ... and gain error".  SLVSF66A sec. 6.5, 7.3.3.2
#            Typical AIPROPI vs temperature: Fig. 8 (OUT1) / Fig. 9 (OUT2), read from the plot:
#            25 C: OUT1 445.0-446.8, OUT2 442.8-444.5 uA/A over 0.3-4 A; slope ~0.055-0.09 uA/A/K
#            (120-200 ppm/K). Offset implied by the 0.3 A vs 1 A curves at 25 C: < ~1 mA (typ).
#  DRV8262: AIPROPI 212 uA/A; AERR +-12 % (10-20 % of rated), +-7 % (20-40 %), +-4 % (40-100 %);
#            below 10 % of rated: not specified. "Rated" is not defined in the table; the features
#            list says "+-4 % sense accuracy at maximum current". Interpretations: 8 A (DDW dual
#            peak, Features) or 5 A (DDW dual RMS, sec. 5.3). No drift curve.  SLVSFV5C sec. 1, 5.5
#  RIPROPI: 1 % 0402 thick film, TCR +-100 ppm/K ASSUMED (typical for JLC basic 0402; a 0.1 %
#            25 ppm/K thin-film part removes most of this term).
import math
VS = 3.3
LSB = VS / 65536
dT = 40
rss = lambda *x: math.sqrt(sum(v * v for v in x))

def ina241(I, cal):
    k = 0.010 * 20  # V/A
    if cal == "none":
        g = rss(0.005, 35e-6 * dT, 1e-4, 1e-6 * dT, 15 * LSB / VS, 0.015)
        o = rss(15e-6 / 0.01, 150e-9 * dT / 0.01, 1e-4 * VS / 2 / k, 13 * LSB / k, 3e-6 * 2 / 0.01,
                16.8 * 10 ** (-150 / 20) / 0.01, 10 * LSB / k)
    else:  # zero cal at boot (bridge braking) + per-board gain cal (1-pt is enough: offset is zeroed)
        g = rss(0.001, 35e-6 * dT, 1e-6 * dT, 0.002)      # 0.1 % cal reference, TCR, amp drift, VDDA drift
        o = rss(150e-9 * dT / 0.01, 13 * LSB / k, 3e-6 * 2 / 0.01, 16.8 * 10 ** (-150 / 20) / 0.01)
    return g, o

def drv8874_aerr(I):
    if I < 0.4: return 0.0, 0.030
    if I < 1: return 0.075, 0.0
    if I < 2: return 0.06, 0.0
    return 0.055, 0.0

def drv8874(I, cal):
    k = 450e-6 * 2000  # RIPROPI 2.0 kOhm -> 0.9 V/A (3 A = 2.7 V; VREF 2.7 V for ITRIP 3 A)
    if cal == "none":
        ga, oa = drv8874_aerr(I)
        g = rss(ga, 0.01, 100e-6 * dT, 15 * LSB / VS, 0.015)
        o = rss(oa, 13 * LSB / k)
        return g, o
    # Calibrated: two-point (offset + gain) per direction, room temperature. NOT guaranteed by the
    # datasheet (no drift or repeatability spec); typical residual from Fig. 8/9:
    #   current-dependence at fixed T: +-0.2 % (25 C) .. +-0.4 % (125 C); temperature 120-200 ppm/K
    #   x 40 K = 0.5-0.8 % (use 0.8 %); offset drift ~0.02 mA/K (0.3 A curve slope excess) x 40 K;
    #   RIPROPI TCR; VDDA drift. VM dependence: no data.
    g = rss(0.004, 200e-6 * dT, 100e-6 * dT, 0.002, 0.001)
    o = rss(0.02e-3 * dT, 13 * LSB / k, 0.001)  # + ~1 mA residual offset after 2-pt (typ)
    if cal == "1pt":  # gain-only at ~1 A: the typical offset (< ~1 mA) stays; worst case is the
        o = rss(o, 0.001)  # +-30 mA band, which a 1-pt cal cannot bound
    return g, o

def drv8262(I, cal, rated):
    k = 212e-6 * 4300  # RIPROPI 4.3 kOhm -> 0.91 V/A (3 A = 2.73 V; VREF max 3.3 V)
    x = I / rated
    if cal == "none":
        if x < 0.1: return None
        ga = 0.12 if x < 0.2 else 0.07 if x < 0.4 else 0.04
        return rss(ga, 0.01, 100e-6 * dT, 15 * LSB / VS, 0.015), 13 * LSB / k
    return None  # no drift data: calibrated residual unknown

pts = [0.1, 0.5, 1.0, 3.0]
def fmt(I, go):
    if go is None: return "   n/s           "
    g, o = go
    e = g * I + o
    return f"{1e3*e:7.1f} mA {100*e/I:5.1f} %"

print("Error at the period-mean current (RSS of terms; 'n/s' = not specified by the datasheet)")
print(f"{'path':42s}" + "".join(f"{p:>20.1f} A" for p in pts))
for name, fn in [
    ("(a) INA241A2+WSK2512, uncalibrated", lambda I: ina241(I, "none")),
    ("(a) INA241A2+WSK2512, zero+gain cal", lambda I: ina241(I, "cal")),
    ("(b) DRV8874 IPROPI, uncalibrated (max)", lambda I: drv8874(I, "none")),
    ("(b) DRV8874 IPROPI, 1-pt cal (typ)", lambda I: drv8874(I, "1pt")),
    ("(b) DRV8874 IPROPI, 2-pt cal (typ)", lambda I: drv8874(I, "2pt")),
    ("(c) DRV8262 IPROPI, uncal, rated=8 A", lambda I: drv8262(I, "none", 8.0)),
    ("(c) DRV8262 IPROPI, uncal, rated=5 A", lambda I: drv8262(I, "none", 5.0)),
]:
    print(f"{name:42s}" + "".join(f"{fmt(p, fn(p)):>22s}" for p in pts))

print("\nNoise per conversion (ADC SNR 77 dB s.e. -> {:.3f} mV rms):".format(1e3 * VS / (2 * math.sqrt(2)) / 10 ** (77 / 20)))
adc = VS / (2 * math.sqrt(2)) / 10 ** (77 / 20)
amp = 49e-9 * 20 * math.sqrt(1.1e6 * math.pi / 2)
print(f"  (a) INA241A2 output noise {amp*1e3:.2f} mV rms -> {math.hypot(amp, adc)/0.2*1e3:.1f} mA rms per conversion; "
      f"/sqrt(8) per period (2 centres x JOVSE 4) {math.hypot(amp, adc)/0.2/math.sqrt(8)*1e3:.1f} mA; /sqrt(80) per 10 kHz tick {math.hypot(amp, adc)/0.2/math.sqrt(80)*1e3:.2f} mA")
print(f"  (b) DRV8874: ADC only {adc/0.9*1e3:.2f} mA rms per conversion at 0.9 V/A; mirror noise NOT specified")
print(f"  (c) DRV8262: ADC only {adc/0.91*1e3:.2f} mA rms per conversion at 0.91 V/A; mirror noise NOT specified")
print("\nRanges: (a) +7.25/-8.0 A linear, signed; (b) 0..~3 A (clamped near VREF = ITRIP), unsigned;"
      " (c) 0..~3.4 A at 4.3 kOhm and VREF <= 3.3 V, unsigned")
