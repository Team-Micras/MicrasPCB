#!/usr/bin/env python3
"""Behavioural ngspice model of main2's wall-emitter drive (boards/main2/Sensors.zen).

The circuit: the four emitters share one constant-current sink, U12 (TLV9001) driving Q9
(AO3400A) over R83 1.2 ohm. The set-point comes from the DAC (PA5, DAC1_OUT2, output buffer off)
through R80 200 kOhm / R81 20 kOhm; R93 1 kOhm and C113 1 nF compensate the loop, R94 200 kOhm
from 3V3_A to IN- biases the op-amp off when the set-point is 0. Each emitter's selector (Q2-Q5,
AO3400A) is AC-coupled: PWM pin -> 220 ohm -> 220 nF -> gate, 22 kOhm gate to GND, 1N4148WS clamp
from GND to the gate. One selector stands for the four (the sink is shared).

Models:
- U12 TLV9001: TI's TLV9002 PSpice model (Rev. C, 2021-06-10, the dual of the same die; TI links it
  from the TLV9001 page: https://www.ti.com/product/TLV9001, https://www.ti.com/lit/zip/SBOMAL2),
  run in ngspice's PSpice mode. It carries a 0.4 mV offset of its own; an explicit +-2 mV source on
  top stands for the maximum over temperature (SBOS833R 7.10). The behavioural model the script
  first used (A0 100 dB, GBW 1 MHz, 2 V/us, 1200 Ohm output) is kept as a cross-check (section 3b).
- Q9 and the selectors, AO3400A: AOS publishes no SPICE model for it (aosmd.com product page,
  checked 2026-10-25: datasheet, marking, reliability report, package only). Two stand-ins:
  - a VDMOS fitted to the datasheet (Rev 3.1 p2-3): KP 57.2 A/V2 from Figure 2's slope between
    3 A (1.6 V) and 15 A (2.0 V), VTO set so that 175 mA needs the 1.41 V read from Figure 2 at
    25 C; it then reaches 250 uA at 1.04 V (VGS(th) 1.05 V typ, p2) and 3 A / 15 A at 1.72 / 2.18 V
    (0.1-0.2 V above Figure 2: the fit is for the low-current end). Ciss 630 pF, Crss 50 pF,
    Coss 75 pF, Rg 3 ohm (p2). A part is named by its VGS at 175 mA;
  - an AO3400 (no A) level-3 model in AOS's subcircuit format, of unknown provenance
    (https://github.com/rdmeneze/LTSpiceModels/blob/master/AO3400.mod): typical threshold only,
    with temperature dependence, and about twice the datasheet's gate capacitance (Meyer gate
    capacitance of its 1 m x 1 um channel plus 225 pF), which makes it a slow-gate corner.
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

The vendor and third-party models are downloaded into models/ (git-ignored) on first run.
Run: python3 research/next-revision/calculations/emitter/emitter_sink.py (ngspice, a few minutes).
"""

import io
import re
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODELS = HERE / "models"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
TLV_URL = "https://www.ti.com/lit/zip/SBOMAL2"
AO_URL = "https://raw.githubusercontent.com/rdmeneze/LTSpiceModels/master/AO3400.mod"


def _fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read()


def models():
    MODELS.mkdir(exist_ok=True)
    tlv, ao = MODELS / "tlv9002.lib", MODELS / "AO3400.mod"
    if not tlv.exists():
        with zipfile.ZipFile(io.BytesIO(_fetch(TLV_URL))) as z:
            name = next(n for n in z.namelist() if n.lower().endswith("tlv9002.lib"))
            tlv.write_text(z.read(name).decode("latin-1").replace("\r\n", "\n"))
    if not ao.exists():
        ao.write_text(_fetch(AO_URL).decode("latin-1").replace("\r\n", "\n"))
    return tlv, ao

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

# AO3400A VDMOS fit (datasheet Rev 3.1): KP from Figure 2, capacitances p2. VTO = VGS(175 mA) - DV175,
# DV175 from a DC sweep of this model (section 5 prints it).
FET = (
    "VDMOS(VTO={vto:.4f} KP=57.2 RS=5m RD=12m RG=3 CGS=580p CGDMAX=120p CGDMIN=30p CJO=120p "
    "IS=1e-12 KSUBTHRES=0.1 LAMBDA=0.01)"
)
DV175 = 0.0145
VGS_TYP = 1.41  # V at 175 mA, 25 C, typical part (Figure 2)
VF_MAX = 1.3e-9 * 0.0775
VF_TYP = 1.3e-9


def netlist(
    vsel=1.80,  # selector VGS at 175 mA (the fit); a maximum-threshold part at 25 C
    q9=1.41,  # Q9 VGS at 175 mA (the fit), or "l3" for the level-3 AO3400 model
    opamp="ti",  # "ti" (TLV9002 PSpice model) or "behav"
    temp=25,
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
    tlv, ao = models()
    if opamp == "ti":
        amp = f".include {tlv}\nXU set inm v3a 0 drive TLV9002\n"
    else:
        amp = f"{OPAMP}\nXU set inm drive v3a OPA\n"
    if q9 == "l3":
        q9dev, q9model = "XQ9 sink gq sense AO3400", f".include {ao}"
    else:
        q9dev, q9model = "MQ9 sink gq sense NQ9", ".model NQ9 " + FET.format(vto=q9 - DV175)
    return f"""* main2 emitter sink
.temp {temp}
.model SFH D(IS={is_led:.4g} N=3.03 RS=0.8 CJO=60p)
.model NSEL {FET.format(vto=vsel - DV175)}
{q9model}
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
{amp}R93 sense inm 1k
C113 drive inm 1n
R94 v3a inm 200k
R82 drive gq 100
{q9dev}
R83 sense 0 1.2
{gate}MSEL k gs sink NSEL
R13 v3d am 3.3
Vim am a 0
DLED a k SFH
.option method=gear reltol=1e-3
.tran 20n {tran} 0 50n
"""


def run(meas, **kw):
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".spiceinit").write_text("set ngbehavior=ps\n")
        cir = Path(tmp) / "e.cir"
        cir.write_text(netlist(**kw) + ".control\nrun\nlet iled = i(Vim)\n" + meas + ".endc\n.end\n")
        try:
            out = subprocess.run(["ngspice", "-b", "e.cir"], cwd=tmp, capture_output=True, text=True, timeout=600).stdout
        except subprocess.TimeoutExpired:
            out = ""
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
    print("   selector named by its VGS at 175 mA: 1.41 V typ / 1.80 V max part at 25 C / 1.94 V max part at")
    print("   -40 C (Figure 2 read and extrapolated, Sensors.zen), then beyond, to show where the margin ends")
    for vsel in (1.41, 1.80, 1.94, 2.10, 2.30):
        dc = run(WINDOW, vsel=vsel, ac=False)
        for cc, rpd in (("220n", "22k"), ("220n", "10k")):
            a = run(WINDOW, vsel=vsel, ac=True, cc=cc, rpd=rpd)
            print(
                f"  VGS {vsel:4.2f} V, {cc}/{rpd}: I {a['i75'] * 1e3:6.2f}/{a['i141'] * 1e3:6.2f} mA at 75/141 us "
                f"(DC-coupled {dc['i75'] * 1e3:6.2f}/{dc['i141'] * 1e3:6.2f}); gate {a['vg75']:.2f}/{a['vg141']:.2f} V; "
                f"sink node {a['vsink']:.2f} V (drain {a['vdrain']:.2f}), margin {a['vsink'] - Q9_FLOOR:+.2f} V"
            )
    print("\n== 2. A pin held high: time from the edge until the emitter current falls below a level")
    print("   worst case for turn-off: a minimum-threshold selector (VGS(th) 0.65 V, VGS 175 mA 1.01 V),")
    print("   pin at 3.346 V, VF typ, DAC at the 175 mA code")
    for cc, rpd in (("220n", "22k"), ("220n", "10k")):
        st = run(STUCK, vsel=1.01, v3d=3.346, voh=3.346, is_led=VF_TYP, cc=cc, rpd=rpd, stuck=True, tran="24m")
        t = {k: (st.get(k, float("nan")) - 4.01e-3) * 1e3 for k in ("t100", "t10", "t1")}
        print(f"  {cc}/{rpd}: < 100 mA at {t['t100']:.1f} ms, < 10 mA at {t['t10']:.1f} ms, < 1 mA at {t['t1']:.1f} ms")

    def pulse(**kw):
        r = run(PULSE, **kw)
        # time after the selector's edge until the current stays within 1 % of its value at 75 us
        band = f"abs(iled - {r['i75']:.6g}) - {0.01 * r['i75']:.6g}"
        st = run(f"let dev = {band}\nmeas tran t1 when dev=0 cross=last from=2.0098m to=2.08m\n", **kw)
        return r, (st.get("t1", 2.0098e-3) - 2.0098e-3) * 1e6

    print("\n== 3. Pulse start with TI's TLV9002 model: the DAC window against the selector's (four emitters")
    print("   back to back). Q9 by its VGS at 175 mA: 1.01 V (VGS(th) 0.65 V min part), 1.41 V typ, 1.94 V")
    print("   (VGS(th) 1.45 V max part at -40 C); the level-3 AO3400 at -40 / 25 / 85 C")
    for q9, temp in ((1.01, 25), (1.41, 25), (1.94, 25), ("l3", -40), ("l3", 25), ("l3", 85)):
        for vos in (-0.002, 0.002):
            for on, off in ((2, -2), (0, 0), (-5, 5)):
                kw = dict(q9=q9, temp=temp, vos=vos, dac_on=on, dac_off=off, period="200u", tran="2.2m")
                r, settle = pulse(**kw)
                qn = f"L3 {temp:+3d} C" if q9 == "l3" else f"VGS {q9:4.2f} V"
                print(
                    f"  Q9 {qn}, VOS {vos * 1e3:+.0f} mV, DAC up {on:+d} us / down {off:+d} us: "
                    f"Q9 gate before {r['gidle']:.2f} V, peak {r['ipk'] * 1e3:4.0f} mA, at 75 us {r['i75'] * 1e3:6.2f} mA, "
                    f"within 1 % after {settle:4.1f} us"
                )
    print("\n== 3b. Cross-check: the behavioural op-amp, typical Q9, VOS 0")
    for on, off in ((2, -2), (0, 0), (-5, 5)):
        r, settle = pulse(opamp="behav", q9=1.41, dac_on=on, dac_off=off, period="200u", tran="2.2m")
        print(
            f"  DAC up {on:+d} us / down {off:+d} us: peak {r['ipk'] * 1e3:4.0f} mA, at 75 us {r['i75'] * 1e3:6.2f} mA, "
            f"within 1 % after {settle:4.1f} us"
        )
    print("\n== 4. DAC output resistance spread and full scale (pin at the 175 mA code, RO 13 kOhm)")
    for ro in ("10.3k", "13k", "16k"):
        r = run(WINDOW, ro=ro)
        print(f"  RO {ro}: {r['i75'] * 1e3:6.2f} mA")
    r = run(WINDOW, dac_v=3.3)
    print(f"  code 4095 (3.3 V): {r['i75'] * 1e3:6.1f} mA")
    print("\n== 5. AO3400A VGS at 175 mA and at 250 uA, VDS 5 V: the fit (no temperature model) and the level-3 AO3400")
    tlv, ao = models()
    deck = f"""* AO3400 VGS
.include {ao}
.model FIT {FET.format(vto=VGS_TYP - DV175)}
VD d 0 5
VG g 0 1
X1 d g 0 AO3400
VD2 d2 0 5
M2 d2 g 0 FIT
.control
foreach t -40 25 125
  set temp=$t
  dc VG 0.5 2.6 0.001
  let i1 = -i(VD)
  let i2 = -i(VD2)
  meas dc l3a when i1=250e-6
  meas dc l3b when i1=0.175
  meas dc fa when i2=250e-6
  meas dc fb when i2=0.175
end
.endc
.end
"""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "v.cir").write_text(deck)
        out = subprocess.run(["ngspice", "-b", "v.cir"], cwd=tmp, capture_output=True, text=True, timeout=300).stdout
    vals = re.findall(r"^(l3a|l3b|fa|fb)\s+=\s+([-\d.eE+]+)", out, re.M)
    for k, temp in enumerate((-40, 25, 125)):
        v = dict(vals[4 * k : 4 * k + 4])
        print(
            f"  {temp:+4d} C: level-3 AO3400 {float(v['l3a']):.3f} V at 250 uA, {float(v['l3b']):.3f} V at 175 mA"
            + (f"; fit {float(v['fa']):.3f} / {float(v['fb']):.3f} V" if temp == 25 else "")
        )
    print("  Figure 2 (AO3400A Rev 3.1, typical part): 1.41 V at 25 C and 1.19 V at 125 C at 175 mA (read)")


if __name__ == "__main__":
    main()
