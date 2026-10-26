#!/usr/bin/env python3
"""INA241A2 output after a bridge's common-mode edge, at main2's conditions, with TI's PSpice model.

The datasheet characterises the common-mode transient only at VS = 5 V with a 0-48 V step (SBOSA30D
Figure 7-1, section 7.3.1.1: the output is held for 1 us after a large dV/dt edge, then the
amplifier's bandwidth and AC CMRR take over). main2 runs it at VS = 3V3_A = 3.3 V, REF1 = VS,
REF2 = GND (mid-supply), with the shunt on the bridge output, so both inputs step 0 <-> VBAT
(16.8 V) at the DRV8874's 150 ns edges (SLVSF66A tRISE/tFALL), and the output goes through R_iso
150 Ohm to C_f 1 nF at the ADC pin (Sensors.zen).

Model: TI INA241A2 PSpice model (SBOMC92, version A, 2022-09-29, https://www.ti.com/lit/zip/SBOMC92),
fetched into models/ (git-ignored) on the first run; ngspice in PSpice compatibility mode. The model
states "ENHANCED PWM REJECTION CIRCUITRY IS NOT MODELED": it shows the edge without the 1 us hold,
which bounds the real part from above for the first microsecond, and models the AC CMRR (154 dB DC,
the frequency shaping of Figure 6-8, whose 105 dB plateau from about 10 kHz is what remains after the
edge).

1. One 0 -> 16.8 V edge, 150 ns, VSENSE 10 mV (1 A): output at the pin before, during and after.
2. 100 kHz square common mode at D 0.2 / 0.5 / 0.8, 200 us to steady state: the pin voltage at
   the centre of each phase (+0.7 us, the end of the ADC's sampling time, firmware_changes.toml
   current), as an error in mA (0.2 V/A) against the DC value.

Run: python3 ina241_edge.py (about 1 min). Output: ina241_edge_out.txt.
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
URL = "https://www.ti.com/lit/zip/SBOMC92"
LIB = MODELS / "INA241A2.lib"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
V_A = 0.2  # V per A: gain 20 x 10 mOhm


def model():
    if not LIB.exists():
        MODELS.mkdir(exist_ok=True)
        req = urllib.request.Request(URL, headers={"User-Agent": UA})
        data = urllib.request.urlopen(req, timeout=60).read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            name = next(n for n in z.namelist() if n.lower().endswith("ina241a2.lib"))
            LIB.write_text(z.read(name).decode("latin-1").replace("\r\n", "\n"))
    return LIB


def spice(body):
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".spiceinit").write_text("set ngbehavior=psa\n")
        (Path(tmp) / "c.cir").write_text(body)
        out = subprocess.run(["ngspice", "-b", "c.cir"], cwd=tmp, capture_output=True, text=True, timeout=3600).stdout
    return {k: float(v) for k, v in re.findall(r"^(\w+)\s+=\s+([-\d.eE+]+)", out, re.M)}


def front(vcm):
    return f"""* INA241A2, VS 3.3 V, mid-supply REF, VSENSE 10 mV on a moving common mode
.include {model()}
VS vs 0 3.3
VCM cm 0 {vcm}
VSEN inp cm 10m
X1 inp cm vs out 0 vs 0 INA241A2
Riso out adc 150
Cf adc 0 1n
.save v(adc)
.options method=gear
"""


with tempfile.TemporaryDirectory() as tmp:
    (Path(tmp) / ".spiceinit").write_text("set ngbehavior=psa\n")
    (Path(tmp) / "c.cir").write_text(front("0") + ".control\nop\nprint v(adc)\n.endc\n.end\n")
    out = subprocess.run(["ngspice", "-b", "c.cir"], cwd=tmp, capture_output=True, text=True, timeout=120).stdout
    v0 = float(re.search(r"v\(adc\)\s+=\s+([-\d.eE+]+)", out).group(1))

print("INA241A2 (TI PSpice model, hold not modelled), VS 3.3 V, REF mid-supply, R_iso 150 Ohm + C_f 1 nF")
print(f"DC output at the pin, 1 A (VSENSE 10 mV): {v0:.6f} V\n")

print("1. One common-mode edge 0 -> 16.8 V in 150 ns at t = 2 us, back to 0 V at t = 7 us")
edge = spice(front("PWL(0 0 2u 0 2.15u 16.8 7u 16.8 7.15u 0 12u 0)") + """.tran 2n 12u 0 2n
.control
run
meas tran vmax max v(adc) from=2u to=7u
meas tran vmin min v(adc) from=2u to=7u
meas tran a05 find v(adc) at=2.65u
meas tran a1 find v(adc) at=3.15u
meas tran a2 find v(adc) at=4.15u
meas tran a4 find v(adc) at=6.15u
meas tran f1 find v(adc) at=8.15u
meas tran f2 find v(adc) at=9.15u
meas tran f4 find v(adc) at=11.15u
.endc
.end
""")
print(f"   during the rising edge: {(edge['vmin']-v0)*1e3:+.1f} / {(edge['vmax']-v0)*1e3:+.1f} mV "
      f"({(edge['vmin']-v0)/V_A*1e3:+.0f} / {(edge['vmax']-v0)/V_A*1e3:+.0f} mA), the part's 1 us hold blanks it")
for k, t in (("a05", 0.5), ("a1", 1), ("a2", 2), ("a4", 4)):
    print(f"   {t:3.1f} us after the rising edge: {(edge[k]-v0)*1e3:+.2f} mV = {(edge[k]-v0)/V_A*1e3:+.1f} mA")
for k, t in (("f1", 1), ("f2", 2), ("f4", 4)):
    print(f"   {t:3.1f} us after the falling edge: {(edge[k]-v0)*1e3:+.2f} mV = {(edge[k]-v0)/V_A*1e3:+.1f} mA")
print(f"   AC-CMRR check: 16.8 V x 10^(-105/20) x 20 = {16.8*10**(-105/20)*20*1e3:.2f} mV, the plateau of Figure 6-8")

print("\n2. 100 kHz common-mode square 0 / 16.8 V (150 ns edges), sampled 0.7 us after each phase centre")
print("   D     mid-on mA   mid-off mA   D-weighted mean mA")
for d in (0.2, 0.5, 0.8):
    t_on = 290e-6 + d * 5e-6 + 0.7e-6
    t_off = 290e-6 + d * 10e-6 + (1 - d) * 5e-6 + 0.7e-6
    m = spice(front(f"PULSE(0 16.8 0 150n 150n {d*10e-6-150e-9:.4e} 10u)") + f""".tran 5n 300u 200u 5n
.control
run
meas tran von find v(adc) at={t_on:.4e}
meas tran voff find v(adc) at={t_off:.4e}
.endc
.end
""")
    e_on, e_off = (m["von"] - v0) / V_A * 1e3, (m["voff"] - v0) / V_A * 1e3
    print(f"   {d:.1f}   {e_on:+8.2f}   {e_off:+9.2f}   {d*e_on+(1-d)*e_off:+8.2f}")
print("   The residue is the AC-CMRR tail of each edge (about 16 us), +/- with the edge's sign: it cancels in the")
print("   duty-weighted mean of the two centres and is at most a few mA on either centre alone.")
