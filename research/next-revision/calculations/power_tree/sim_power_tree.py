#!/usr/bin/env python3
"""Micras next main board: analog 3V3_A rail architectures, switching-level behavioural ngspice model.

BEHAVIOURAL MODELS, NOT VENDOR MODELS. Everything below is built from datasheet numbers and generic
converter physics; relative comparisons are more trustworthy than absolute microvolts.

Generic peak-current-mode synchronous buck (`buck()`), cycle by cycle:
- clock + sawtooth at fSW; SR latch q (1 = high side on); inductor current is a state variable
  (node il, 1 V = 1 A) with dI/dt = (q*VIN - VOUT - R*I)/L; DCM clamp (I >= 0 while q = 0) only in PFM;
- reset when I + slope ramp >= peak command (blanking = minimum on-time), forced off-time at cycle end;
- outer loop: PI transconductance K (A/V) with zero at fz -> crossover fc ~ K/(2*pi*COUT);
- FPWM: switches every cycle, inductor current may go negative (all FPWM/FCCM/LNM parts do);
- PFM: a cycle is skipped while VOUT > VREF*(1+h); peak command clamped >= ISKIP (L6981 LCM style:
  DS13554 sec. 6.4.1, +1.8 % threshold, ISKIP 0.35 A Table 6).
- NOT modelled: switching-edge ringing, gate-drive/switching losses (efficiency taken from datasheet
  plots), real internal compensation (unknown for every part: fc chosen as fSW/20 ... fSW/14),
  PCB parasitics other than a few mOhm/nH, capacitor DC-bias (an effective value is given instead).

LDO (`ldo()`): behavioural loop calibrated in supply3v3/sim3v3.py on TPS7A20 Fig. 5-51; its PSRR is not
in the netlist (infinite there) and is added afterwards by `analyze.py` from the datasheet PSRR curve
applied to the simulated LDO input spectrum (magnitude only).

Battery node: 14.8 V (4S nominal) behind 0.1 Ohm (pack IR + wiring, assumed), with the motor-bridge
ripple on it: 100 kHz, 150 mV p-p (70 % triangle from the bulk charge/discharge, 30 % square from ESR)
plus the fan driver at 300 kHz, 50 mV p-p square. These amplitudes are ESTIMATES (see research/next-revision/README.md
sec. 2); case suffix _hv runs 300 + 100 mV p-p.

Digital 3V3_D: averaged L6981C33 model from supply3v3/sim3v3.py (K = 2*pi*4.02/3.3 A/V, DS13554 Eq.42)
carrying MCU 170 mA DC, ESP32-S3-MINI-1 Wi-Fi TX bursts 95 -> 355 mA (MINI-1 datasheet Tables 6-4/6-5;
burst pattern 400 us every 1.5 ms is an assumption, deliberately asynchronous to the 1 ms sensor frame)
and the four IR emitters (170 mA constant-current sink, firmware v1 pattern: 150 us lit every 200 us,
4 emitters + 1 dark slot per 1 ms frame, MicrasFirmware config/targets/v1/target.hpp l.409-425).
Its input current (P/(0.88*VIN)) is drawn from the battery node, so it couples into the analog
regulator's input through the 0.1 Ohm.

3V3_A loads (research/next-revision/README.md, power tree): 2 x INA241A2 2.5 mA (SBOSA30D sec. 6.5 IQ typ), VDDA ADCs 1.0 mA
continuous + 0.7 mA during wall scans (DS13311 Table 84/87 orders of magnitude), lit phototransistor
2 mA during its emitter pulse + 4 x 0.3 mA ambient, op-amp + set divider 0.3 mA.
"""
import math
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)

T_SETTLE = 2.0e-3   # data written from here
T_END = 7.0e-3      # 5 frames analysed
T0 = 1.0e-3         # emitter pattern starts (frame 0 at T0)
STEP = 20e-9        # linearised output grid


def vbat_source(node="vbat", hv=False):
    a100 = 0.300 if hv else 0.150
    a300 = 0.100 if hv else 0.050
    return f"""
* 4S battery 14.8 V + motor PWM ripple (100 kHz) + fan (300 kHz), assumed amplitudes
Vbatdc b0 0 14.8
Btri b1 b0 V = {0.7*a100}*(2*abs(2*(time*100e3 - floor(time*100e3 + 0.5))) - 1)/2
Bsq b2 b1 V = {0.3*a100}*((time*100e3 - floor(time*100e3)) < 0.5 ? 0.5 : -0.5)
Bfan b3 b2 V = {a300}*((time*300e3 - floor(time*300e3)) < 0.37 ? 0.5 : -0.5)
Rsrc b3 {node} 0.1
Cbat {node} 0 1u
"""


def gate_expr():
    # 1 while an emitter is lit (slots 0-3 of each 1 ms frame, 150 us each), firmware v1
    return (f"((time > {T0}) ? ( ((time-{T0}) - floor((time-{T0})/1m)*1m) < 0.8m ? "
            f"( (((time-{T0}) - floor((time-{T0})/0.2m)*0.2m) < 0.15m) ? 1 : 0 ) : 0 ) : 0)")


def scan_expr():
    # 1 during the ADC wall scan (75-150 us after each slot start, 5 slots incl. dark)
    return (f"((time > {T0}) ? ( ((((time-{T0}) - floor((time-{T0})/0.2m)*0.2m) > 75u) && "
            f"(((time-{T0}) - floor((time-{T0})/0.2m)*0.2m) < 0.15m)) ? 1 : 0 ) : 0)")


def esp_expr():
    # ESP32-S3-MINI-1: RX ~95 mA, Wi-Fi TX 355 mA; 400 us bursts every 1.5 ms (assumed pattern)
    return "(((time - floor(time/1.5m)*1.5m) > 0.3m) && ((time - floor(time/1.5m)*1.5m) < 0.7m) ? 0.355 : 0.095)"


def digital_rail(vin="vbat", out="v3d"):
    """Averaged L6981C33 (as supply3v3/sim3v3.py) + its loads; input current from vin."""
    k = 2 * math.pi * 4.02 / 3.3
    wz = 2 * math.pi * 3e3
    load = f"(0.170 + {esp_expr()} + 0.170*({gate_expr()}))"
    return f"""
* digital 3V3_D: averaged L6981C33, K={k:.3f} A/V, 58 uF eff
Bde de 0 V = 3.3 - v({out})
Bdr dr 0 V = {k:.6g}*v(de) + v(di)
Bdi 0 di I = {k*wz:.6g}*v(de) + 5e4*(v(dc) - v(dr))
Cdi di 0 1
Rdi di 0 1e9
Bdc dc 0 V = max(0, min(2.0, v(dr)))
Rdl dc dl 2k
Cdl dl 0 1n
Gdo 0 {out} dl 0 1
Cdo {out} {out}_c 58u
Rdo {out}_c 0 3m
Bdload {out} 0 I = {load}
Bdin {vin} 0 I = v({out})*{load}/(0.88*max(v({vin}),3))
.ic v(di)=0.4 v({out})=3.3
"""


def buck(n, vin, out, vref, fsw, L, R, cout, k, fz, m=0.7, mode="fpwm", iskip=0.0, h=0.018,
         ilim=1.1, ineg=-0.5, ton_min=60e-9, toff_min=100e-9, esr=5e-3, esl=0.5e-9):
    T = 1.0 / fsw
    sf_ramp = m * (vref / L) * T          # slope-compensation ramp amplitude, A over one period
    blank = ton_min / T
    toff = 1 - toff_min / T
    allow = "1" if mode == "fpwm" else f"0.5*(1+tanh(({vref*(1+h):.6g} - v({out}))*3000))"
    lo = iskip if mode == "pfm" else ineg
    # PFM diode emulation: while the high side is off, a negative inductor current is driven back to
    # zero with a 4 ns time constant (continuous expression; avoids a hard switch in the solver)
    dcm = "" if mode == "fpwm" else f" + (1-v({n}q))*{3e3*L/12e-6:.6g}*max(0, -v({n}il))"
    il_drive = f"(v({n}q)*v({vin}) - v({out}) - {R}*v({n}il)){dcm}"
    return f"""
* {n}: generic peak-current-mode buck, {mode.upper()}, fSW {fsw/1e3:.0f} kHz, L {L*1e6:.1f} uH, COUT {cout*1e6:.1f} uF eff, K {k:.2f} A/V
V{n}clk {n}clk 0 PULSE(0 1 0 1n 1n 20n {T:.6g})
V{n}rmp {n}rmp 0 PULSE(0 1 0 {T-2e-9:.6g} 1n 0 {T:.6g})
B{n}e {n}e 0 V = {vref} - v({out})
B{n}raw {n}raw 0 V = {k:.6g}*v({n}e) + v({n}vi)
B{n}pk {n}pk 0 V = max({lo}, min({ilim}, v({n}raw)))
B{n}vi 0 {n}vi I = {k*2*math.pi*fz:.6g}*v({n}e) + 2e5*(v({n}pk) - v({n}raw))
C{n}vi {n}vi 0 1
R{n}vi {n}vi 0 1e9
B{n}rst {n}rst 0 V = (v({n}rmp) > {toff:.6g}) ? 1 : ((v({n}rmp) > {blank:.6g}) ? 0.5*(1+tanh((v({n}il) + {sf_ramp:.6g}*v({n}rmp) - v({n}pk))*400)) : 0)
B{n}set {n}set 0 V = v({n}clk)*{allow}
B{n}q 0 {n}q I = 2e-3*(v({n}set)*(1-v({n}q))*(1-v({n}rst)) - v({n}rst)*v({n}q))
C{n}q {n}q 0 1p
R{n}q {n}q 0 1e9
B{n}il 0 {n}il I = {il_drive}
C{n}il {n}il 0 {L:.6g}
R{n}il {n}il 0 1e6
G{n}o 0 {out} {n}il 0 1
B{n}in {vin} 0 I = v({n}q)*v({n}il)
C{n}o {out} {n}o1 {cout:.6g}
R{n}o {n}o1 {n}o2 {esr}
L{n}o {n}o2 0 {esl}
R{n}leak {out} 0 1e6
.ic v({n}vi)=0.02 v({out})={vref} v({n}il)=0.02 v({n}q)=0
"""


def ldo(n, vin, out, vref, fu=600e3, cref=1e-6, ilim=0.3):
    k = 2 * math.pi * fu * cref
    wz = 2 * math.pi * 20e3
    return f"""
* {n}: behavioural LDO (loop as supply3v3/sim3v3.py, TPS7A20 Fig. 5-51 calibration); PSRR added in analyze.py
B{n}e {n}e 0 V = {vref} - v({out})
B{n}r {n}r 0 V = {k:.6g}*v({n}e) + v({n}i)
B{n}i 0 {n}i I = {k*wz:.6g}*v({n}e) + 5e4*(v({n}c) - v({n}r))
C{n}i {n}i 0 1
R{n}i {n}i 0 1e9
B{n}c {n}c 0 V = max(0, min({ilim}, v({n}r)))
R{n}l {n}c {n}l 100
C{n}l {n}l 0 1n
B{n}o {vin} {out} I = v({n}l) * min(1, max(0, (v({vin}) - v({out}) - 0.05) / 0.1))
.ic v({n}i)=0.01 v({out})={vref}
"""


def analog_loads(node):
    return f"""
* 3V3_A loads: 2 x INA241A2 (2 x 2.5 mA), op-amp+divider 0.3 mA, ambient photocurrents 4 x 0.3 mA,
* lit phototransistor 2 mA during the pulse, ADC 1.0 mA + 0.7 mA during scans (VDDA pin)
Iana {node} 0 6.5m
Bphoto {node} 0 I = 2m*{gate_expr()}
"""


def vdda_pin(src, r=0.02):
    return f"""
* VDDA pin: trace + 1 uF + 100 nF at the pin (AN5419 Table 2), ADC current
Rvd {src} vdda {r}
Cvd1 vdda vdda_1 1u
Rvd1 vdda_1 0 10m
Cvd2 vdda vdda_2 100n
Rvd2 vdda_2 0 20m
Badc vdda 0 I = 1.0m + 0.7m*{scan_expr()}
"""


def post_filter(kind, a, b):
    """Second-stage filter from buck output a to rail b."""
    if kind == "none":
        return f"Rpf {a} {b} 5m\n"
    if kind == "bead":
        # 0603 600-ohm-class bead, low-frequency inductance assumed 0.5 uH, Rdc 0.1 ohm, + 10 uF
        return (f"Rpf {a} pf1 0.1\nLpf pf1 {b} 0.5u\nRpfp pf1 {b} 300\n"
                f"Cpf {b} pfc 10u\nRpfc pfc 0 5m\n")
    if kind == "lc":
        # 4.7 uH (DCR 0.2 ohm assumed) + 22 uF (15 uF eff) -- lightly damped (Q ~ 2.8)
        return (f"Rpf {a} pf1 0.2\nLpf pf1 {b} 4.7u\n"
                f"Cpf {b} pfc 15u\nRpfc pfc 0 5m\n")
    if kind == "lcd":
        # 10 uH (DCR 0.5 ohm assumed) + 1 ohm series damping + 22 uF (15 uF eff): Q ~ 0.55
        return (f"Rpf {a} pf1 1.5\nLpf pf1 {b} 10u\n"
                f"Cpf {b} pfc 15u\nRpfc pfc 0 5m\n")
    if kind == "lcx":
        # damped second stage (Middlebrook parallel RC damping, n = Cd/Cf = 2): 2.2 uH (DCR 50 mOhm
        # assumed) + 22 uF (15 uF eff) + damping leg 0.33 ohm + 47 uF (30 uF eff); f0 ~ 28 kHz
        return (f"Rpf {a} pf1 0.05\nLpf pf1 {b} 2.2u\n"
                f"Cpf {b} pfc 15u\nRpfc pfc 0 5m\n"
                f"Rdmp {b} pfd 0.33\nCdmp pfd 0 30u\n")
    raise KeyError(kind)


def scenario(key):
    """key = <case>[_hv][_line]. _line: line-rejection test (constant 9 mA analog load, no digital
    rail, no emitter/scan steps), so the 100/300 kHz lines at VDDA come only from the battery ripple."""
    line = key.endswith("_line")
    k = key.replace("_line", "")
    hv = k.endswith("_hv")
    k = k.replace("_hv", "")
    al, vp = analog_loads, vdda_pin
    if line:
        al = lambda node: f"Iana {node} 0 8m\n"          # noqa: E731
        vp = lambda src, r=0.02: (f"Rvd {src} vdda {r}\nCvd1 vdda vdda_1 1u\nRvd1 vdda_1 0 10m\n"  # noqa: E731
                                        f"Cvd2 vdda vdda_2 100n\nRvd2 vdda_2 0 20m\nIadc vdda 0 1m\n"
                                        f"Vd3 v3d 0 3.3\n")
    body = vbat_source(hv=hv) + ("" if line else digital_rail())
    probes = ["v(vdda)", "v(v3d)", "v(vbat)"]
    # TPS560430X3F-like: 1.1 MHz, L 12 uH, COUT 22 uF (TPS560430 Table 1), 15 uF eff assumed;
    # fc chosen 55 kHz (internal compensation not published) -> K = 2*pi*55k*15u
    tps560 = dict(fsw=1.1e6, L=12e-6, R=0.35, cout=15e-6, k=2*math.pi*55e3*15e-6, fz=10e3,
                  ilim=1.1, ineg=-0.5, ton_min=60e-9, toff_min=100e-9)
    if k.startswith("A_"):
        filt = k.split("_", 1)[1]
        mode = "fpwm"
        if filt.startswith("pfm"):
            mode, filt = "pfm", filt.replace("pfm", "") or "lc"
            filt = filt.strip("-") or "lc"
        p = dict(tps560)
        if mode == "pfm":
            p.update(iskip=0.25)   # PFM version: minimum peak current assumed 0.25 A (not published)
        body += buck("ab", "vbat", "va0", 3.3, mode=mode, **p)
        body += post_filter(filt, "va0", "va")
        body += al("va") + vp("va")
        probes += ["v(va0)"]
        title = f"(A) analog buck {mode.upper()} (TPS560430X3F-like) + post-filter '{filt}'"
    elif k.startswith("A6981_"):
        # L6981N33 (LNM forced PWM, DS13554 sec. 6.4.2), 400 kHz, 22 uH, 44 uF nominal -> 35 uF eff,
        # internal compensation fc*COUT = 4.02/VOUT (Eq. 42) -> K = 7.65 A/V
        body += buck("ab", "vbat", "va0", 3.3, fsw=400e3, L=22e-6, R=0.4, cout=35e-6,
                     k=2*math.pi*4.02/3.3, fz=3e3, ilim=2.0, ineg=-1.5, ton_min=85e-9, toff_min=185e-9)
        filt = k.split("_", 1)[1]
        body += post_filter(filt, "va0", "va")
        body += al("va") + vp("va")
        probes += ["v(va0)"]
        title = f"(A) analog buck L6981N33-like LNM 400 kHz + post-filter '{filt}'"
    elif k == "B":
        # 5 V buck L6981C50-like (LCM = PFM, ISKIP 0.35 A, +1.8 %), 400 kHz, 22 uH, 35 uF eff
        body += buck("b5", "vbat", "v5", 5.0, fsw=400e3, L=22e-6, R=0.4, cout=35e-6,
                     k=2*math.pi*4.02/5.0, fz=3e3, mode="pfm", iskip=0.35, ilim=2.0, ineg=0,
                     ton_min=85e-9, toff_min=185e-9)
        body += ldo("la", "v5", "va", 3.3, ilim=0.3)
        body += "Cla va va_c 2.2u\nRla va_c 0 5m\n"
        body += al("va") + vp("va")
        probes += ["v(v5)"]
        title = "(B) 5 V PFM buck (L6981C50-like) -> TPS7A20-class LDO -> 3V3_A"
    elif k == "C":
        # HV LDO (TPS7A49-class) from the battery through an RC pre-filter 47 ohm + 10 uF
        body += "Rpre vbat vpre 47\nCpre vpre vpre_c 10u\nRprec vpre_c 0 5m\n.ic v(vpre)=14.35 v(vpre_c)=14.35\n"
        body += ldo("la", "vpre", "va", 3.3, ilim=0.15, fu=300e3, cref=10e-6)
        body += "Cla va va_c 10u\nRla va_c 0 5m\n"
        body += al("va") + vp("va")
        probes += ["v(vpre)"]
        title = "(C) TPS7A49-class LDO from VBAT behind 47 ohm + 10 uF"
    elif k == "F":
        # VDDA from the digital rail through today's bead (FB1) + an extra 10 uF
        body += post_filter("bead", "v3d", "va")
        body += al("va") + vp("va")
        title = "(F) 3V3_A = 3V3_D through ferrite bead + 10 uF (no second regulator)"
    elif k == "Frc":
        body += "Rrc v3d va 4.7\nCrc va va_c 47u\nRrcc va_c 0 5m\n"
        body += al("va") + vp("va")
        title = "(F') 3V3_A = 3V3_D through 4.7 ohm + 47 uF RC"
    else:
        raise KeyError(key)
    return title, body, probes


def run(key):
    title, body, probes = scenario(key)
    net = f"""* {title}
{body}
.options method=gear reltol=1e-4 abstol=1e-9 vntol=1e-7 itl4=200
.control
  set noaskquit
  tran {STEP} {T_END} {T_SETTLE} 5n uic
  linearize {' '.join(probes)}
  wrdata {key}.dat {' '.join(probes)}
.endc
.end
"""
    path = OUT / f"{key}.cir"
    path.write_text(net)
    res = subprocess.run(["ngspice", "-b", path.name], cwd=OUT, capture_output=True, text=True, timeout=3600)
    (OUT / f"{key}.log").write_text(res.stdout + res.stderr)
    return key, title, res.returncode


CASES = ["A_none", "A_bead", "A_lc", "A_lcd", "A_lcx", "A_pfm-lcx", "A6981_lcx", "B", "C", "F", "Frc",
         "A_lcx_hv", "B_hv", "C_hv"]

if __name__ == "__main__":
    keys = sys.argv[1:] or CASES
    with ProcessPoolExecutor(max_workers=6) as ex:
        for key, title, rc in ex.map(run, keys):
            print(f"{key:12s} rc={rc}  {title}")
