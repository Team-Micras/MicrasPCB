#!/usr/bin/env python3
"""Behavioural ngspice model of main2's wall-emitter drive (boards/main2/Sensors.zen).

The circuit: the four emitters share one constant-current sink, U12 (TLV9001) driving Q9
(AO3400A) over R83 1.2 ohm. The set-point comes from the DAC (PA5, DAC1_OUT2, output buffer off)
through R80 200 kOhm / R81 20 kOhm; R93 1 kOhm and C113 1 nF compensate the loop, R94 200 kOhm
from 3V3_A to IN- biases the op-amp off when the set-point is 0. Each emitter's selector (Q2-Q5,
AO3400A) is AC-coupled: PWM pin -> 220 ohm -> 220 nF -> gate, 22 kOhm gate to GND, 1N4148WS clamp
from GND to the gate. One selector stands for the four (the sink is shared).

Models (assumptions, not vendor models):
- TLV9001 (SBOS833R section 7.10): A0 100 dB, GBW 1 MHz, slew 2 V/us (a slew-limited integrator),
  second pole 4.7 MHz (78 deg phase margin at G = 1), 1200 ohm open-loop output impedance
  (f = 1 MHz) in series, output clamped to the rails. The 0.85 us overload recovery is not modelled.
  Input offset: an explicit source, +-2 mV (the maximum over temperature).
- AO3400A (Rev 3.1 p2): VDMOS, VTO the threshold (0.65 / 1.05 / 1.45 V min / typ / max), KP 95 A/V2
  from gFS 33 S at 5.7 A, Ciss 630 pF, Crss 50 pF, Rg 3 ohm. VTO above 1.45 V stands for a cold
  or slow part: the datasheet gives no VGS(th) temperature curve and no VGS at 175 mA.
- SFH 4550: diode fitted to VF 1.5 V at 100 mA and 2.4 V at 1 A (datasheet p5); IS scaled by
  0.0775 for VF max (+0.2 V at 100 mA, 1.80 V at 175 mA).
- 1N4148WS: IS scaled to VF 0.715 V at 1 mA, its maximum (JCET BAV16WS/1N4148WS p1).
- DAC1_OUT2, buffer off: an ideal source behind RO 13 kOhm (10.3-16 kOhm, DS13311 Table 90) and
  10 pF, ramping in 1.7 us (settling 1.72 us at CL = 10 pF, Table 90).
- 3V3_D at 3.229 V: the L6981's 3.284 V minimum less 22 mV emitter droop and a 33 mV ESP32 dip
  (power_tree/calc_power_tree.py section 4); 50 mOhm + 20 nH, 1 uF at the emitter (C26-C29).
- GPIO high level VDD - 0.4 V (DS13311 Table 56, 8 mA; the pin's real load is about 0.3 mA).
- Firmware pattern (MicrasFirmware config/targets/v1/target.hpp, wall_sensors_config): each
  emitter lit 150 us once per 1 ms frame; the next emitter lights 50 us after one goes dark; the
  ADC scans 75-141 us after an emitter lights.

Run: python3 research/next-revision/calculations/emitter/emitter_sink.py (ngspice, about 2 min).
"""

import re
import subprocess
import tempfile
from pathlib import Path

OPAMP = """
.subckt OPA inp inn out vcc
Bgm 0 n1 I = 2m*tanh((V(inp)-V(inn))*6.283m/2m)
C1 n1 0 1n
R1 n1 0 1.6e7
D1 n1 vcc DCL
D2 0 n1 DCL
.model DCL D(IS=1e-14 N=0.05)
E2 n2 0 n1 0 1
R2 n2 n3 1k
C2 n3 0 33.9p
B3 n4 0 V = max(0.01, min(V(vcc)-0.02, V(n3)))
Ro n4 out 1200
.ends
"""

VF_MAX = 1.3e-9 * 0.0775
VF_TYP = 1.3e-9


def netlist(
    vsel=1.45,  # selector threshold
    q9=1.05,  # Q9 threshold
    v3d=3.229,
    voh=2.829,
    is_led=VF_MAX,
    ac=True,
    rpd="22k",
    cc="220n",
    period="1m",  # one selector, once per frame; "200u" stands for the four back to back
    dac_v=2.627,  # 175 mA at RO 13 kOhm
    ro="13k",
    dac_on=2,  # us after the selector's edge
    dac_off=-2,  # us after the selector's falling edge
    vos=0.0,
    stuck=False,
    tran="5.2m",
):
    if stuck:
        pwm = f"PWL(0 0 4.01m 0 4.01001m {voh})"
        dac = f"PWL(0 0 4.012m 0 4.0137m {dac_v})"
    else:
        pwm = f"PULSE(0 {voh} 10u 5n 5n 150u {period})"
        width = 150 - dac_on + dac_off
        dac = f"PULSE(0 {dac_v} {10 + dac_on}u 1.7u 0.1u {width}u {period})"
    if ac:
        gate = f"Rgs pwm drv 220\nCc drv gs {cc}\nRpd gs 0 {rpd}\nDcl 0 gs DCLAMP\n"
    else:
        gate = f"Rgs pwm gs 220\nRpd gs 0 {rpd}\n"
    return f"""* main2 emitter sink
.model SFH D(IS={is_led:.4g} N=3.03 RS=0.8 CJO=60p)
.model NSEL VDMOS(VTO={vsel} KP=95 RS=5m RD=12m RG=3 CGS=580p CGDMAX=120p CGDMIN=30p CJO=120p IS=1e-12 KSUBTHRES=0.1 LAMBDA=0.01)
.model NQ9 VDMOS(VTO={q9} KP=95 RS=5m RD=12m RG=3 CGS=580p CGDMAX=120p CGDMIN=30p CJO=120p IS=1e-12 KSUBTHRES=0.1 LAMBDA=0.01)
.model DCLAMP D(IS=0.8n N=1.752 RS=0.568 CJO=2p)
V3D raw 0 {v3d}
Rsup raw l1 0.05
Lsup l1 v3d 20n
Cloc v3d 0 1u
V3A v3a 0 3.3
Vpwm pwmi 0 {pwm}
Rpin pwmi pwm 40
Vdac dac 0 {dac}
Rdac dac pa5 {ro}
Cpin pa5 0 10p
R80 pa5 setd 200k
R81 setd 0 20k
Vos set setd {vos}
{OPAMP}
XU set inm drive v3a OPA
R93 sense inm 1k
C113 drive inm 1n
R94 v3a inm 200k
R82 drive gq 100
MQ9 sink gq sense NQ9
R83 sense 0 1.2
{gate}MSEL k gs sink NSEL
R13 v3d am 3.3
Vim am a 0
DLED a k SFH
.option method=gear reltol=1e-4
.tran 20n {tran} 0 50n
"""


def run(meas, **kw):
    with tempfile.TemporaryDirectory() as tmp:
        cir = Path(tmp) / "e.cir"
        cir.write_text(netlist(**kw) + ".control\nrun\nlet iled = i(Vim)\n" + meas + ".endc\n.end\n")
        out = subprocess.run(["ngspice", "-b", str(cir)], capture_output=True, text=True).stdout
    return {k: float(v) for k, v in re.findall(r"^(\w+)\s+=\s+([-\d.eE+]+)", out, re.M)}


WINDOW = """meas tran i75 find iled at=4.085m
meas tran i141 find iled at=4.151m
meas tran vg75 find v(gs) at=4.085m
meas tran vg141 find v(gs) at=4.151m
meas tran vsink find v(sink) at=4.151m
meas tran vdrain find v(k) at=4.151m
"""

PULSE = """meas tran ipk max iled from=2.0098m to=2.0398m
meas tran i75 find iled at=2.085m
meas tran gidle find v(gq) at=2.0099m
"""

STUCK = """meas tran t100 when iled=0.1 cross=2
meas tran t10 when iled=0.01 cross=2
meas tran t1 when iled=0.001 cross=2
"""

Q9_FLOOR = 0.21 + 0.175 * 0.048  # sense voltage + Q9 at RDS(on) 48 mOhm max (AO3400A p2)


def main():
    print("== 1. Worst case, sample window: AC-coupled selector against a DC-coupled one")
    print(f"   3V3_D 3.229 V, VF 1.80 V, pin VDD - 0.4 V; Q9 needs its drain >= {Q9_FLOOR:.2f} V")
    for vsel in (1.05, 1.45, 1.65, 1.85, 2.05):
        dc = run(WINDOW, vsel=vsel, ac=False)
        for cc, rpd in (("220n", "22k"), ("220n", "10k"), ("470n", "10k")):
            a = run(WINDOW, vsel=vsel, ac=True, cc=cc, rpd=rpd)
            print(
                f"  Vth {vsel:4.2f} V, {cc}/{rpd}: I {a['i75'] * 1e3:6.2f}/{a['i141'] * 1e3:6.2f} mA at 75/141 us "
                f"(DC-coupled {dc['i75'] * 1e3:6.2f}/{dc['i141'] * 1e3:6.2f}); gate {a['vg75']:.2f}/{a['vg141']:.2f} V; "
                f"sink node {a['vsink']:.2f} V (drain {a['vdrain']:.2f}), margin {a['vsink'] - Q9_FLOOR:+.2f} V"
            )
    print("\n== 2. A pin held high: time from the edge until the emitter current falls below a level")
    print("   worst case for turn-off: Vth 0.65 V, pin at 3.346 V, VF typ, DAC at the 175 mA code")
    for cc, rpd in (("220n", "22k"), ("220n", "10k")):
        s = run(STUCK, vsel=0.65, v3d=3.346, voh=3.346, is_led=VF_TYP, cc=cc, rpd=rpd, stuck=True, tran="24m")
        t = {k: (s.get(k, float("nan")) - 4.01e-3) * 1e3 for k in ("t100", "t10", "t1")}
        print(f"  {cc}/{rpd}: < 100 mA at {t['t100']:.1f} ms, < 10 mA at {t['t10']:.1f} ms, < 1 mA at {t['t1']:.1f} ms")
    print("\n== 3. Pulse start: the DAC window against the selector's (four emitters back to back)")
    for q9 in (0.65, 1.45):
        for vos in (-0.002, 0.002):
            for on, off in ((2, -2), (0, 0), (-5, 5)):
                kw = dict(q9=q9, vos=vos, dac_on=on, dac_off=off, period="200u", tran="2.2m")
                r = run(PULSE, **kw)
                # time after the selector's edge until the current stays within 1 % of its value at 75 us
                band = f"abs(iled - {r['i75']:.6g}) - {0.01 * r['i75']:.6g}"
                s = run(f"let dev = {band}\nmeas tran t1 when dev=0 cross=last from=2.0098m to=2.08m\n", **kw)
                settle = (s.get("t1", 2.0098e-3) - 2.0098e-3) * 1e6
                print(
                    f"  Q9 Vth {q9:4.2f} V, VOS {vos * 1e3:+.0f} mV, DAC up {on:+d} us / down {off:+d} us: "
                    f"Q9 gate before {r['gidle']:.2f} V, peak {r['ipk'] * 1e3:4.0f} mA, at 75 us {r['i75'] * 1e3:6.2f} mA, "
                    f"within 1 % after {settle:4.1f} us"
                )
    print("\n== 4. DAC output resistance spread and full scale (pin at the 175 mA code, RO 13 kOhm)")
    for ro in ("10.3k", "13k", "16k"):
        r = run(WINDOW, ro=ro)
        print(f"  RO {ro}: {r['i75'] * 1e3:6.2f} mA")
    r = run(WINDOW, dac_v=3.3)
    print(f"  code 4095 (3.3 V): {r['i75'] * 1e3:6.1f} mA")


if __name__ == "__main__":
    main()
