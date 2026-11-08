#!/usr/bin/env python3
"""Behavioural ngspice model of the Micras 3V3 rail during the wall-emitter pulses.

Averaged (not switching) models:
- L6981 buck: peak-current-mode converter reduced to a PI transconductance stage. The internal
  compensation sets the crossover so that fc * COUT = 4.02 / VOUT (DS13554 Eq. 42, written for
  fc = fSW/10), i.e. the mid-band transconductance K = 2*pi*4.02/VOUT A/V regardless of COUT.
  Current loop + inductor lumped into a 2 us lag; inductor current clamped to 0..2.0 A
  (no sinking in LCM, valley/peak limit ~2 A, DS13554 Table 6).
  LCM pulse skipping (+1.8 % below ~0.15-0.2 A, Fig. 17) is NOT in this model; handled separately.
- LDO: same structure, unity-gain loop frequency 600 kHz, calibrated so that 1 uF + 300 mA step in
  1 us dips ~75 mV like TPS7A20 Fig. 5-51 (Cout = 1 uF).
- SFH 4550: diode fitted to VF 1.5 V @ 100 mA and 2.4 V @ 1 A (datasheet p5): RS = 0.8 ohm,
  n*Vt = 78.2 mV, IS = 1.3 nA.
- Ferrite FB1 (600 ohm @ 100 MHz, 0.34 ohm DCR): 0.34 ohm + (1.5 uH || 600 ohm). Assumed L.
- Firmware v1 emitter pattern (MicrasFirmware config/targets/v1/target.hpp): one emitter at a
  time, lit 150 us, next end 200 us later, frame of 5 ends (4 emitters + 1 dark) = 1 ms.
  ADC scan in the last 75 us of each pulse (75-150 us after turn-on).
"""
import math
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)

T0 = 8.0e-3  # pattern start (loops settled by then)

GATE = f"""
* Emitter gate: one emitter at a time; frame 1 ms = 5 ends of 200 us; emitter lit 150 us at ends 0..3
Bgate graw 0 V = (time > {T0}) ? ( ((time-{T0}) - floor((time-{T0})/1m)*1m) < 0.8m ? ( (((time-{T0}) - floor((time-{T0})/0.2m)*0.2m) < 0.15m) ? 1 : 0 ) : 0 ) : 0
Rg graw g 1k
Cg g 0 0.1n
"""

GATE_TWO = f"""
* Older pattern: 2 emitters at once, 187.5 us at 2 kHz (Sensors.zen docstring / review)
Bgate graw 0 V = (time > {T0}) ? ( (((time-{T0}) - floor((time-{T0})/0.5m)*0.5m) < 0.1875m) ? 1 : 0 ) : 0
Rg graw g 1k
Cg g 0 0.1n
"""

MODELS = """
.model dled D(IS=1.3e-9 N=3.02 RS=0.8)
.model swm SW(RON=0.05 ROFF=1e6 VT=0.5 VH=0.05)
"""


def buck(name, out, vref, ceff_note=""):
    """Averaged current-mode buck with internal compensation per DS13554 Eq. 42."""
    k = 2 * math.pi * 4.02 / vref  # A/V at crossover, independent of COUT
    # PI zero placed at ~3 kHz (well below the 8-35 kHz crossovers of the cases below)
    wz = 2 * math.pi * 3e3
    return f"""
* {name}: averaged L6981-like buck, Vref={vref} V, K={k:.3f} A/V {ceff_note}
B{name}e {name}_e 0 V = {vref} - v({out})
B{name}r {name}_r 0 V = {k:.6g}*v({name}_e) + v({name}_i)
B{name}i 0 {name}_i I = {k*wz:.6g}*v({name}_e) + 5e4*(v({name}_c) - v({name}_r))
C{name}i {name}_i 0 1
R{name}i {name}_i 0 1e9
B{name}c {name}_c 0 V = max(0, min(2.0, v({name}_r)))
R{name}l {name}_c {name}_l 2k
C{name}l {name}_l 0 1n
G{name}o 0 {out} {name}_l 0 1
.ic v({name}_i)=0.2 v({out})={vref}
"""


def ldo(name, vin, out, vref, fu=600e3, cref=1e-6, ilim=1.0):
    k = 2 * math.pi * fu * cref
    wz = 2 * math.pi * 20e3
    return f"""
* {name}: behavioural LDO, Vref={vref} V, unity-gain ~{fu/1e3:.0f} kHz with {cref*1e6:.1f} uF, Ilim {ilim} A
B{name}e {name}_e 0 V = {vref} - v({out})
B{name}r {name}_r 0 V = {k:.6g}*v({name}_e) + v({name}_i)
B{name}i 0 {name}_i I = {k*wz:.6g}*v({name}_e) + 5e4*(v({name}_c) - v({name}_r))
C{name}i {name}_i 0 1
R{name}i {name}_i 0 1e9
B{name}c {name}_c 0 V = max(0, min({ilim}, v({name}_r)))
R{name}l {name}_c {name}_l 100
C{name}l {name}_l 0 1n
* pass element: current command, only while there is headroom (crude dropout ~150 mV)
B{name}o {vin} {out} I = v({name}_l) * min(1, max(0, (v({vin}) - v({out}) - 0.05) / 0.1))
.ic v({name}_i)=0.05 v({out})={vref}
"""


def cap(name, a, c, esr=0.003):
    return f"C{name} {a}_{name} 0 {c}\nR{name}esr {a} {a}_{name} {esr}\n"


def led_branch(supply, tag="", r=10.0):
    return f"""
* emitter: {r} ohm -> SFH 4550 -> AO3400A (switch, 50 mOhm)
Rled{tag} {supply} a{tag} {r}
Dled{tag} a{tag} k{tag} dled
Sled{tag} k{tag} k{tag}x g 0 swm
Vmeas{tag} k{tag}x 0 0
"""


def vdda_filter(src):
    return f"""
* VDDA: FB1 + C10 100 nF + C11 1 uF, ADC load 1.5 mA
Rfb {src} fb1 0.34
Lfb fb1 vdda 1.5u
Rfbp fb1 vdda 600
{cap('C11', 'vdda', '1u', 0.01)}{cap('C10', 'vdda', '100n', 0.02)}
Iadc vdda 0 1.5m
"""


def common_loads(rail, esp=False):
    s = f"""
* MCU (DS13311 Table 24: 125 mA typ SMPS ON, 550 MHz, all peripherals) + encoders 2x16 mA + IMU/amps
Imcu {rail} 0 0.17
"""
    if esp:
        # ESP32-S3 TX burst 88 -> 340 mA (datasheet Table 5-7), 1 ms burst starting at 1.35 ms
        s += f"Iesp {rail} 0 PWL(0 0.088 {T0+0.35e-3} 0.088 {T0+0.351e-3} 0.340 {T0+1.35e-3} 0.340 {T0+1.351e-3} 0.088)\n"
    return s


def scenario(key):
    """Return (title, netlist body)."""
    gate = GATE_TWO if key.endswith("_two") else GATE
    k = key.replace("_two", "")
    body = ""
    if k in ("a", "a_esp"):
        title = "(a) today: L6981C33, ~72 uF nominal (58 uF effective assumed) on 3V3, emitters on 3V3"
        body += buck("bk", "v3", 3.3, "(COUT 58 uF eff)")
        # bulk at the buck and MCU, scattered, lumped: 2x22 + 10 + 4.7 + 4.7 + 1 uF caps (eff 80 %)
        body += cap("Cb", "v3", "58u", 0.003)
        # sensor branch through ~50 mm of trace: 50 mOhm + 40 nH; 4 x 1 uF at the sensors
        body += "Rtr v3 vs 0.05\nLtr vs vsx 40n\nRtrx vsx vsn 1m\n"
        body += cap("Cs", "vsn", "4u", 0.005)
        body += led_branch("vsn")
        body += vdda_filter("v3")
        body += common_loads("v3", esp=(k == "a_esp"))
    elif k == "b1":
        title = "(b1) bulk at the Eq. 43 limit: 145 uF effective on 3V3"
        body += buck("bk", "v3", 3.3)
        body += cap("Cb", "v3", "145u", 0.002)
        body += "Rtr v3 vs 0.05\nLtr vs vsx 40n\nRtrx vsx vsn 1m\n"
        body += cap("Cs", "vsn", "4u", 0.005)
        body += led_branch("vsn")
        body += vdda_filter("v3")
        body += common_loads("v3")
    elif k == "b2":
        title = "(b2) emitter reservoir: 3V3 -> 1 ohm -> 100 uF (eff) local bank -> emitters"
        body += buck("bk", "v3", 3.3)
        body += cap("Cb", "v3", "58u", 0.003)
        body += "Rtr v3 vs 0.05\nLtr vs vsx 40n\nRiso vsx vsn 1.0\n"
        body += cap("Cs", "vsn", "100u", 0.003)
        body += led_branch("vsn")
        body += vdda_filter("v3")
        body += common_loads("v3")
    elif k == "b3":
        title = "(b3) (a) + VDDA from 3V3 through 10 ohm + 10 uF (RC instead of bead)"
        body += buck("bk", "v3", 3.3)
        body += cap("Cb", "v3", "58u", 0.003)
        body += "Rtr v3 vs 0.05\nLtr vs vsx 40n\nRtrx vsx vsn 1m\n"
        body += cap("Cs", "vsn", "4u", 0.005)
        body += led_branch("vsn")
        body += "Rrc v3 vdda 10\n" + cap("C11", "vdda", "10u", 0.005) + cap("C10", "vdda", "100n", 0.02)
        body += "Iadc vdda 0 1.5m\n"
        body += common_loads("v3")
    elif k == "c":
        title = "(c) buck 5 V (44 uF eff) -> 1 A LDO 3.3 V (10 uF) -> whole board incl. emitters"
        body += buck("bk", "v5", 5.0)
        body += cap("Cb5", "v5", "30u", 0.003)
        body += ldo("ld", "v5", "v3", 3.3, fu=600e3, cref=1e-6, ilim=1.0)
        body += cap("Cl", "v3", "10u", 0.003) + cap("Cb", "v3", "20u", 0.003)
        body += "Rtr v3 vs 0.05\nLtr vs vsx 40n\nRtrx vsx vsn 1m\n"
        body += cap("Cs", "vsn", "4u", 0.005)
        body += led_branch("vsn")
        body += vdda_filter("v3")
        body += common_loads("v3")
    elif k == "d":
        title = ("(d) separate rails: buck 3V3 digital; 5 V buck -> TPS7A20-class LDO 3V3A for VDDA + "
                 "sensors; emitters from 5 V through constant-current sinks (170 mA)")
        body += buck("bk", "v3", 3.3)
        body += cap("Cb", "v3", "58u", 0.003)
        body += common_loads("v3", esp=True)
        body += buck("b5", "v5", 5.0)
        body += cap("Cb5", "v5", "30u", 0.003)
        body += ldo("la", "v5", "va", 3.3, fu=600e3, cref=1e-6, ilim=0.3)
        body += cap("Ca", "va", "2.2u", 0.005)
        # analog loads: 2 x TSC2020, phototransistors (~3 mA), IMU ~1 mA
        body += "Iana va 0 6m\n"
        # VDDA straight from 3V3A with 1 uF + 100 nF at the pin (short trace)
        body += "Rva va vdda 0.05\n" + cap("C11", "vdda", "1u", 0.01) + cap("C10", "vdda", "100n", 0.02)
        body += "Iadc vdda 0 1.5m\n"
        # constant-current sink: I = 170 mA when gate on, with headroom check
        body += "Rtr v5 vs 0.05\nLtr vs vsx 40n\nRtrx vsx vsn 1m\n" + cap("Cs", "vsn", "4u", 0.005)
        body += ("Dled vsn a dled\n"
                 "Vmeas a ax 0\n"
                 "Bcc ax 0 I = 0.170*v(g)*min(1, max(0, v(ax)/0.3))\n")
    else:
        raise KeyError(key)
    return title, gate + MODELS + body


def run(key):
    title, body = scenario(key)
    led_i = "i(Vmeas)"
    extra = (" v(v5)" if " v5 " in body or "v(v5)" in body else "") + (" v(va)" if " va " in body else "")
    # sample instants: emitter 1 (2nd pulse) of the 2nd frame: on at T0+1.2m
    ton = T0 + 2.2e-3 if "two" not in key else T0 + 2.0e-3
    rail = "v3"
    meas = f"""
.control
  set noaskquit
  tran 0.1u {T0+3e-3} {T0-0.5e-3} 0.1u uic
  meas tran v3_pre FIND v(v3) AT={ton - 1e-6}
  meas tran v3_min MIN v(v3) FROM={ton} TO={ton + 150e-6}
  meas tran v3_75 FIND v(v3) AT={ton + 75e-6}
  meas tran v3_150 FIND v(v3) AT={ton + 149e-6}
  meas tran vdda_pre FIND v(vdda) AT={ton - 1e-6}
  meas tran vdda_min MIN v(vdda) FROM={ton} TO={ton + 150e-6}
  meas tran vdda_max MAX v(vdda) FROM={ton} TO={ton + 200e-6}
  meas tran vdda_75 FIND v(vdda) AT={ton + 75e-6}
  meas tran vdda_150 FIND v(vdda) AT={ton + 149e-6}
  meas tran iled_75 FIND {led_i} AT={ton + 75e-6}
  meas tran iled_150 FIND {led_i} AT={ton + 149e-6}
  meas tran v3_ppall PP v(v3) FROM={T0+1e-3} TO={T0+3e-3}
  meas tran vdda_ppall PP v(vdda) FROM={T0+1e-3} TO={T0+3e-3}
  wrdata {key}.dat v(v3) v(vdda) {led_i}{extra}
.endc
"""
    if key == "d":
        meas = meas.replace("v(v3)", "v(v3)")
    net = f"* {title}\n{body}\n{meas}\n.end\n"
    path = OUT / f"{key}.cir"
    path.write_text(net)
    res = subprocess.run(["ngspice", "-b", path.name], cwd=OUT, capture_output=True, text=True, timeout=600)
    txt = res.stdout + res.stderr
    vals = dict(re.findall(r"^(\w+)\s*=\s*([-+0-9.eE]+)", txt, re.M))
    (OUT / f"{key}.log").write_text(txt)
    return title, {k: float(v) for k, v in vals.items()}, txt


if __name__ == "__main__":
    keys = sys.argv[1:] or ["a", "a_two", "a_esp", "b1", "b2", "b3", "c", "d"]
    for key in keys:
        title, v, txt = run(key)
        print(f"\n== {key}: {title}")
        if not v:
            print(txt[-3000:])
            continue
        def mv(x):
            return f"{x*1e3:7.1f} mV"
        try:
            print(f"  3V3   before {v['v3_pre']:.4f} V  min in pulse {v['v3_min']:.4f} V "
                  f"(droop {mv(v['v3_pre']-v['v3_min'])}); at 75 us {mv(v['v3_pre']-v['v3_75'])}, "
                  f"at 150 us {mv(v['v3_pre']-v['v3_150'])}; p-p over frames {mv(v['v3_ppall'])}")
            print(f"  VDDA  before {v['vdda_pre']:.4f} V  min {v['vdda_min']:.4f} max {v['vdda_max']:.4f} "
                  f"(droop {mv(v['vdda_pre']-v['vdda_min'])}, overshoot {mv(v['vdda_max']-v['vdda_pre'])}); "
                  f"drop at 75 us {mv(v['vdda_pre']-v['vdda_75'])}, at 150 us {mv(v['vdda_pre']-v['vdda_150'])}; "
                  f"p-p {mv(v['vdda_ppall'])}")
            i75, i150 = abs(v['iled_75']), abs(v['iled_150'])
            print(f"  I_LED at 75 us {i75*1e3:.2f} mA, at 150 us {i150*1e3:.2f} mA "
                  f"(change in scan window {100*(i150-i75)/i75:+.2f} %)")
            r75 = i75 / v['vdda_75']
            r150 = i150 / v['vdda_150']
            print(f"  reading proxy I_LED/VDDA change across scan window {100*(r150-r75)/r75:+.3f} %")
        except KeyError as e:
            print("missing", e, sorted(v))
