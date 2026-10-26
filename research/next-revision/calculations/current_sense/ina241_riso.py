#!/usr/bin/env python3
"""INA241A2 output into R_iso + C_f and the ADC's sample capacitor, with TI's PSpice model in ngspice.

The circuit (boards/main2/Sensors.zen): U10/U11 INA241A2 on VS = 3V3_A = 3.3 V, REF1 = VS and
REF2 = GND (mid-supply output), OUT -> R_iso (R78/R79) -> ADC pin (PB1/PC1) with C_f (C102/C105) to
GND. The ADC (DS13311 Rev 5, Table 84 and Figure 45) samples through its switches onto CADC = 4 pF,
which arrives charged to another channel's voltage (up to VDDA away); the converted value is the
voltage CADC holds at the end of the sampling time. The switch resistance RADC is not published
(Figure 45 names it only), so it is swept, 50 Ohm to 1 kOhm.

Model: TI INA241A2 PSpice model (SBOMC92, "INA241A2 PSpice Model", model version A, 2022-09-29,
https://www.ti.com/lit/zip/SBOMC92, from https://www.ti.com/product/INA241A). It models the
closed-loop gain and the closed-loop output impedance against frequency, with RL and CL effects
(its header); it is not a transistor-level loop, so stability shows as peaking and ringing into the
load, not as an oscillation. The datasheet's own limit (SBOSA30D section 6.5): maximum capacitive
load 1 nF with no isolation resistor, "no sustained oscillations". Figure 6-24 gives the output
impedance (read: 0.09 Ohm to about 5 kHz, 0.25 Ohm at 10 kHz, 5 Ohm at 100 kHz, 55 Ohm at 1 MHz,
80 Ohm at 1.5 MHz, 150 Ohm at 10 MHz); the model gives 0.09, 0.32, 4.4, 42, 113 (3 MHz) and
151 Ohm, so section 3 also runs it with 2 uH || 40 Ohm in series with OUT, which brings it to 5.6,
54 and 82 Ohm at 0.1, 1 and 1.5 MHz (190 Ohm at 10 MHz).

The script downloads the model into models/ (git-ignored) on first run. ngspice runs it in PSpice
compatibility mode (ngbehavior=ps). Run: python3 ina241_riso.py (about 8 min).

Sections:
1. Small-signal response from VSENSE to OUT and to the ADC pin: DC gain, peaking, -3 dB, and the
   pin's delay behind the shunt current at the 100 kHz PWM frequency.
2. Step response, VSENSE 0 -> 5 mV (0.1 V at OUT, 0.5 A): overshoot at OUT and at the pin.
3. ADC kickback: CADC arrives 3.3 V away from the pin; the error CADC holds after a sampling time,
   as motor current (0.2 V/A), against the 1 mA budget; with TI's model and with its output
   impedance raised to Figure 6-24's.
4. The same over the tolerance corners, for 100 Ohm and the board's 150 Ohm.
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
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

VPERA = 20 * 0.010  # INA241A2 gain x 10 mOhm shunt, V/A
BUDGET = 1e-3  # A: the residual a current sample may carry (research Current sensing)


def model():
    if not LIB.exists():
        MODELS.mkdir(exist_ok=True)
        req = urllib.request.Request(URL, headers={"User-Agent": UA})
        data = urllib.request.urlopen(req, timeout=60).read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            name = next(n for n in z.namelist() if n.lower().endswith("ina241a2.lib"))
            text = z.read(name).decode("latin-1").replace("\r\n", "\n")
        LIB.write_text(text)
    return LIB


def spice(body):
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".spiceinit").write_text("set ngbehavior=ps\n")
        cir = Path(tmp) / "c.cir"
        cir.write_text(body)
        try:
            out = subprocess.run(["ngspice", "-b", "c.cir"], cwd=tmp, capture_output=True, text=True, timeout=120).stdout
        except subprocess.TimeoutExpired:
            out = ""
    return {k: float(v) for k, v in re.findall(r"^(\w+)\s+=\s+([-\d.eE+]+)", out, re.M)}


def front(riso, cf, vcm=8.0, vsense="0", cpin=5e-12, zfig=False):
    # R_iso = 0 stands for C_f straight on OUT (the datasheet's 1 nF limit case). zfig adds 2 uH || 40 Ohm
    # in series with OUT, which lifts the model's output impedance (42 Ohm at 1 MHz) to Figure 6-24's
    # (about 55 Ohm at 1 MHz, 80 Ohm at 1.5 MHz; above it a little: 190 against 150 Ohm at 10 MHz).
    iso = f"Riso out adc {riso}" if riso > 0 else "Viso out adc 0"
    if zfig:
        iso = "Lx out o2 2u\nRx out o2 40\n" + iso.replace("out adc", "o2 adc")
    return f"""* INA241A2 into R_iso + C_f
.include {model()}
VS vs 0 3.3
CVS vs 0 100n
VCM inn 0 {vcm}
VSN inp inn {vsense}
X1 inp inn vs out 0 vs 0 INA241A2
{iso}
Cf adc 0 {cf}
Cpin adc 0 {cpin}
"""


def ac(riso, cf):
    body = front(riso, cf, vsense="DC 0 AC 1") + """
.control
ac dec 100 1k 100meg
let go = db(v(out))
let ga = db(v(adc))
meas ac g0 find go at=1k
meas ac gpo max go
meas ac gpa max ga
let pa = 180/pi*cph(v(adc))
meas ac p100k find pa at=100k
let gref = g0 - 3
meas ac f3o when go=gref fall=last
meas ac f3a when ga=gref fall=last
.endc
.end
"""
    return spice(body)


def step(riso, cf):
    body = front(riso, cf, vsense="PULSE(0 5m 1u 10n 10n 20u 40u)") + """
.tran 1n 8u 0 1n
.control
run
meas tran vo0 find v(out) at=0.99u
meas tran vo1 find v(out) at=7.9u
meas tran omax max v(out) from=1u to=7u
meas tran amax max v(adc) from=1u to=7u
let lo = vo0 + 0.99*(vo1 - vo0)
let hi = vo0 + 1.01*(vo1 - vo0)
meas tran ta when v(adc)=lo cross=1
.endc
.end
"""
    return spice(body)


def kick(riso, cf, dv, radc, vcm=8.0, times=(0.2, 0.3, 0.45, 0.6, 0.8, 1.0), cpin=5e-12, zfig=False):
    # CADC's far plate steps by -dv at 2 us, which pulls its top plate to v(adc) - dv, as if CADC
    # arrived precharged dv below the pin, and it then shares that charge through RADC (linear, so the
    # same as switching it in; the far plate stays at a fixed voltage, AC ground). The converted value
    # is the top plate's voltage, which ends at v(adc).
    meas = "\n".join(f"meas tran e{i} find vh at={2 + t}u" for i, t in enumerate(times))
    body = (
        front(riso, cf, vcm=vcm, cpin=cpin, zfig=zfig)
        + f"""VB b 0 PWL(0 0 2u 0 2.001u {-dv})
Radc adc cs {radc}
Cadc cs b 4p
.tran 0.5n 6u 0 0.5n
.control
run
let vh = v(cs)
meas tran vfin find v(adc) at=5.9u
{meas}
let err = abs(vh - vfin)
meas tran tset when err={BUDGET * VPERA} cross=last from=2.001u
.endc
.end
"""
    )
    r = spice(body)
    errs = [(r[f"e{i}"] - r["vfin"]) / VPERA for i in range(len(times))]
    return errs, (r.get("tset", 2e-6) - 2e-6) * 1e6


CASES = [  # (R_iso, C_f), all 0402: C_f straight on OUT, then R_iso + C_f pairs
    (0, 1e-9),
    (100, 1e-9),
    (120, 1e-9),
    (150, 1e-9),
    (180, 1e-9),
    (220, 1e-9),
    (150, 680e-12),
    (220, 470e-12),
    (100, 2.2e-9),
]
CHOSEN = (150, 1e-9)
T_MIN = 0.7  # us: the firmware's minimum sampling time (boards/main2/firmware_changes.toml, adc)
TIMES = (0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7, 0.8, 1.0)


def name(riso, cf):
    return f"{'direct' if riso == 0 else f'{riso} Ohm'} + {cf * 1e9:g} nF"


def row(errs):
    return "".join(f"{e * 1e3:+7.2f}" for e in errs)


def main():
    print("== 1. Small signal, VSENSE -> OUT and -> ADC pin (5 pF pin), VS 3.3 V, VCM 8 V")
    for riso, cf in [(0, 0)] + CASES:
        r = ac(riso, cf if cf else 1e-15)
        print(
            f"  {name(riso, cf) if cf else 'no load':18s}: DC {r['g0']:5.2f} dB; peaking OUT {r['gpo'] - r['g0']:+5.2f} dB, "
            f"pin {r['gpa'] - r['g0']:+5.2f} dB; -3 dB OUT {r['f3o'] / 1e6:5.2f} MHz, pin {r['f3a'] / 1e6:5.2f} MHz; "
            f"pin delay {-r['p100k'] / 360 / 100e3 * 1e9:3.0f} ns (100 kHz)"
        )
    print("\n== 2. Step VSENSE 0 -> 5 mV (OUT +0.1 V): overshoot")
    for riso, cf in [(0, 0)] + CASES:
        r = step(riso, cf if cf else 1e-15)
        d = r["vo1"] - r["vo0"]
        print(
            f"  {name(riso, cf) if cf else 'no load':18s}: overshoot OUT {(r['omax'] - r['vo1']) / d * 100:5.1f} %, "
            f"pin {(r['amax'] - r['vo1']) / d * 100:5.1f} %"
        )
    print("\n== 3. ADC kickback: CADC arrives 3.3 V below the pin (the worst case; linear, so +3.3 V mirrors it)")
    print("   error CADC holds after each sampling time, mA of motor current at 0.2 V/A; RADC 200 Ohm, VCM 8 V;")
    print("   'settled' = from when on the error stays under 1 mA. TI's model, then with Figure 6-24's")
    print("   output impedance (zfig)")
    print("   " + " " * 22 + "".join(f"{t:>5.2f}us" for t in TIMES) + "  settled")
    for zfig in (False, True):
        for riso, cf in CASES[1:]:
            errs, ts = kick(riso, cf, 3.3, 200, times=TIMES, zfig=zfig)
            print(f"  {'zfig ' if zfig else 'model'} {name(riso, cf):16s}" + row(errs) + f"  {ts:5.2f} us")
    print("\n== 4. Tolerance corners, both output impedances: C_f +-5 % (C0G), RADC 50 / 1000 Ohm (not")
    print("   published), pin + trace 2 / 10 pF, VCM 0 / 16.8 V; worst error at each sampling time, worst settling")
    worst_all = {}
    for riso in (100, CHOSEN[0]):
        worst_t, worst = 0.0, [0.0] * len(TIMES)
        for zfig in (False, True):
            for cf in (0.95e-9, 1.05e-9):
                for radc in (50, 1000):
                    for cpin in (2e-12, 10e-12):
                        for vcm in (0.0, 16.8):
                            errs, ts = kick(riso, cf, 3.3, radc, vcm=vcm, times=TIMES, cpin=cpin, zfig=zfig)
                            worst_t = max(worst_t, ts)
                            worst = [max(w, abs(e)) for w, e in zip(worst, errs)]
        worst_all[riso] = worst
        print(f"  {riso:3d} Ohm + 1 nF        " + "".join(f"{w * 1e3:7.2f}" for w in worst) + f"  {worst_t:5.2f} us")
    k = TIMES.index(T_MIN)
    print(
        f"\n   at the firmware's {T_MIN} us: {worst_all[100][k] * 1e3:.2f} mA with 100 Ohm, "
        f"{worst_all[CHOSEN[0]][k] * 1e3:.2f} mA with {CHOSEN[0]} Ohm (budget {BUDGET * 1e3:.0f} mA)"
    )


if __name__ == "__main__":
    main()
