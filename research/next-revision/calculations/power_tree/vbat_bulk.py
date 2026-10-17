#!/usr/bin/env python3
"""VBAT bulk capacitance without electrolytics, and VBAT overvoltage (research/next-revision).

Compares the VBAT capacitor options of main2 (bridges' bulk C87/C96) and quantifies the
overvoltage cases behind the TVS question. Every input number carries its source; ASSUMPTION
marks the rest. ngspice (batch mode) runs the time-domain and AC cases; the netlists go to a
temporary directory.

Run: python3 -I vbat_bulk.py   (needs ngspice on PATH)

1. Effective capacitance of the MLCC candidates at the pack voltage (Samsung DC-bias data).
2. VBAT ripple at 100 kHz: two DRV8874 bridges (interleaved or in phase) and the STSPIN958 fan
   at 400 kHz, with the pack behind its resistance and lead inductance.
3. Input LC: resonance, characteristic impedance and peak source impedance seen by the bridges
   (pack, and a bench supply on long leads); a 6 A load release.
4. Hot plug and switching: the pack plugged into J1 with SW4 off and on; SW4 closing; SW4
   opening under load (the lead-inductance kick at Q6's turn-off).
5. Regeneration into VBAT with the pack disconnected.
6. TVS clamp.
"""
import math
import os
import re
import subprocess
import tempfile

# ---------------------------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------------------------
V_NOM, V_FULL, V_HV = 14.8, 16.8, 17.4  # 4S nominal, full, full with HV cells (research Design basis)
# Pack resistance: the research's 0.5-1.5 V sag at 5 A (README Drivetrain) -> 0.1-0.3 Ohm.
R_PACK = (0.1, 0.3)
# Lead + connector inductance: ASSUMPTION. About 100 nH for a 10 cm pair of pack leads, 300 nH for
# a loose 30 cm pair, 1 uH for a bench supply on 1 m leads (with 30 mOhm of lead resistance).
L_LEAD = (100e-9, 300e-9, 1e-6)
R_BENCH = 0.03

# Samsung product-page DC-bias curves (product.samsungsem.com/mlcc/<part>.do, "DC Bias"),
# capacitance change at 14.8 / 16.8 / 17.4 V, read 2026-10-17.
DC_BIAS = {
    # part: (nominal F, package, (dC 14.8 V, dC 16.8 V, dC 17.4 V), area mm2 (L x W), height mm)
    "CL31B106KBHNNNE 10u 50V X7R 1206": (10e-6, "1206", (-0.630, -0.679, -0.691), 3.2 * 1.6, 1.6),
    "CL31A106KBHNNNE 10u 50V X5R 1206": (10e-6, "1206", (-0.741, -0.780, -0.790), 3.2 * 1.6, 1.6),
    "CL32B106KBJNNNE 10u 50V X7R 1210": (10e-6, "1210", (-0.339, -0.394, -0.410), 3.2 * 2.5, 2.5),
    "CL32A106KBJNNNE 10u 50V X5R 1210": (10e-6, "1210", (-0.249, -0.299, -0.314), 3.2 * 2.5, 2.5),
    "CL32Y106KBJ4PNE 10u 50V X7S 1210": (10e-6, "1210", (-0.302, -0.351, -0.366), 3.2 * 2.5, 2.5),
    "CL32B226KAJNNNE 22u 25V X7R 1210": (22e-6, "1210", (-0.680, -0.724, -0.733), 3.2 * 2.5, 2.5),
    "CL31A226KAHNNNE 22u 25V X5R 1206": (22e-6, "1206", (-0.803, -0.834, -0.841), 3.2 * 1.6, 1.6),
}
# Heights: Samsung thickness codes H = 1.6 mm, J = 2.5 mm (part-number key).
# ESR and ESL of the MLCCs: ASSUMPTION 5 mOhm and 1 nH per part at 100 kHz (no ESR curve on the
# Samsung page; typical of 10 uF 1206/1210 X7R parts).
MLCC_ESR, MLCC_ESL = 5e-3, 1e-9


def ceff(part, v_index):
    c, _, dc, _, _ = DC_BIAS[part]
    return c * (1 + dc[v_index])


# Bulk parts per bridge (C87, C96):
# JVS25V100M6X4 (JIERR JVS p1-2): 100 uF 25 V, tan d 0.18 at 120 Hz (2.4 Ohm), 54 mA at 120 Hz
#   (LCSC listing). No 100 kHz ESR is given: ASSUMPTION 1 Ohm at 100 kHz.
# 25TQC33MYF (Panasonic TQC, 2023-06-30): 33 uF 25 V, D2 7.3 x 4.3 x 1.9 mm, ESR 60 mOhm max and
#   1.4 A rms at 100 kHz.
# 25TQC100MD3: 100 uF 25 V, D3L 7.3 x 4.3 x 2.8 mm, 60 mOhm, 1.6 A rms.
# Polymer capacitance at 100 kHz taken as the 120 Hz rating (no roll-off curve in the datasheet).
OPTIONS = {
    # name: (MLCC parts beyond the existing ones as (part, count), bulk (C, ESR, ESL, count))
    "electrolytic: JVS25V100M6X4 per bridge": ([], (100e-6, 1.0, 3e-9, 2)),
    "ceramic only, bulk removed": ([], None),
    "ceramic: 2 x 1210 10u 50V X7R per bridge": ([("CL32B106KBJNNNE 10u 50V X7R 1210", 4)], None),
    "ceramic: 4 x 1210 10u 50V X7R per bridge": ([("CL32B106KBJNNNE 10u 50V X7R 1210", 8)], None),
    "polymer: 25TQC33MYF per bridge": ([], (33e-6, 0.060, 2e-9, 2)),
    "polymer: 25TQC100MD3 per bridge": ([], (100e-6, 0.060, 2e-9, 2)),
}
# Existing VBAT ceramics on main2 (Drivers.zen): 4 x 10 uF 1206 per bridge (C83-C86, C92-C95) and
# 2 x 10 uF 1206 at the fan (C36, C99), all CL31B106KBHNNNE; the 100 nF and 470 nF parts are
# ignored here.
BASE_MLCC = [("CL31B106KBHNNNE 10u 50V X7R 1206", 10)]

# Loads: ITRIP 2.97 A (Drivers.zen); research 2.4 A design point; D = 0.5 is the ripple worst case.
F_BRIDGE, F_FAN = 100e3, 400e3
I_MOTOR = (2.4, 3.0)
# Fan: a 1S drone motor on 16.8 V runs at D = 22 % and about 2.5 A (research Fan).
I_FAN, D_FAN = 2.5, 0.22
I_LOGIC = 0.1  # ASSUMPTION: VSYS loads (buck + LDO) as a 0.1 A constant current from VBAT


def run(netlist):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "c.cir")
        with open(p, "w") as f:
            # Gear integration: the trapezoidal rule rings numerically on the nH-level ESL branches.
            f.write(netlist.replace(".control", ".options method=gear\n.control", 1))
        out = subprocess.run(["ngspice", "-b", p], capture_output=True, text=True, timeout=600)
    res = {}
    for m in re.finditer(r"^(\w+)\s*=\s*([-+0-9.eE]+)", out.stdout, re.M):
        res[m.group(1).lower()] = float(m.group(2))
    if not res:
        raise RuntimeError(out.stdout[-2000:] + out.stderr[-2000:])
    return res


def bank(option, v_index, node="vb", gnd="0"):
    """Capacitor branches of one option between node and gnd, as SPICE lines."""
    extra, bulk = OPTIONS[option]
    lines = []
    for i, (part, n) in enumerate(BASE_MLCC + extra):
        c = ceff(part, v_index) * n
        lines.append(f"Cm{i} {node} m{i}a {c:.4e}\nRm{i} m{i}a m{i}b {MLCC_ESR / n:.4e}\nLm{i} m{i}b {gnd} {MLCC_ESL / n:.4e}")
    if bulk:
        c, esr, esl, n = bulk
        lines.append(f"Cb {node} ba {c * n:.4e}\nRb ba bb {esr / n:.4e}\nLb bb {gnd} {esl / n:.4e}")
    return "\n".join(lines) + "\n"


def total_c(option, v_index):
    extra, bulk = OPTIONS[option]
    c = sum(ceff(p, v_index) * n for p, n in BASE_MLCC + extra)
    return c + (bulk[0] * bulk[3] if bulk else 0.0)


print("=== 1. MLCC effective capacitance (Samsung DC-bias curves) ===")
print(f"{'part':36s} {'14.8 V':>8s} {'16.8 V':>8s} {'17.4 V':>8s} {'uF/mm2 @16.8':>13s} {'height':>7s}")
for part, (c, pkg, dc, area, h) in DC_BIAS.items():
    e = [c * (1 + x) * 1e6 for x in dc]
    print(f"{part:36s} {e[0]:6.2f}uF {e[1]:6.2f}uF {e[2]:6.2f}uF {e[1] / area:13.2f} {h:5.1f}mm")
print("Polymer tantalum: capacitance does not fall with DC bias (rated value used).")

print("\n=== 2. VBAT ripple, 16.8 V, pack 0.1 Ohm behind 100 nH, two bridges at D = 0.5 + fan ===")
print("Effective VBAT capacitance at 16.8 V (all VBAT caps on one node; 100 kHz trace impedance ignored):")
for o in OPTIONS:
    print(f"  {o:50s} {total_c(o, 1) * 1e6:6.1f} uF")


def ripple_case(option, i_m, phase, d=0.5, rp=0.1, lead=100e-9, v=V_FULL, vi=1, fan=True):
    t1 = 1 / F_BRIDGE
    on = d * t1
    lines = [f"* ripple {option}", f"Vp pk 0 {v}", f"Rp pk p1 {rp}", f"Lp p1 bp {lead}", "Rsh bp vb 2m"]
    lines.append(bank(option, vi))
    lines.append(f"I1 vb 0 PULSE(0 {i_m} 0 20n 20n {on - 20e-9:.4e} {t1:.4e})")
    lines.append(f"I2 vb 0 PULSE(0 {i_m} {phase * t1:.4e} 20n 20n {on - 20e-9:.4e} {t1:.4e})")
    if fan:
        tf = 1 / F_FAN
        lines.append(f"I3 vb 0 PULSE(0 {I_FAN} 0 10n 10n {D_FAN * tf - 10e-9:.4e} {tf:.4e})")
    lines.append(f"I4 vb 0 {I_LOGIC}")
    caps = " ".join(x.split()[0] for x in bank(option, vi).split("\n") if x.startswith("L"))
    meas = [".tran 20n 1.2m 1.0m 20n", ".control", "run",
            "meas tran vpp PP v(vb) from=1.05m to=1.2m",
            "meas tran ibat_avg AVG i(Lp) from=1.05m to=1.2m",
            "meas tran ibat_rms RMS i(Lp) from=1.05m to=1.2m"]
    for l in caps.split():
        meas.append(f"meas tran {l}_rms RMS i({l}) from=1.05m to=1.2m")
    meas += [".endc", ".end"]
    r = run("\n".join(lines + meas))
    ibat_ac = math.sqrt(max(r["ibat_rms"] ** 2 - r["ibat_avg"] ** 2, 0))
    caps_rms = {k[:-4]: v for k, v in r.items() if k.endswith("_rms") and k.startswith("l") and k != "lp_rms"}
    return r["vpp"], ibat_ac, caps_rms


print("Bridges in phase (the worst case, and the firmware's interleave is untested) at D = 0.5, and")
print("interleaved 180 degrees at D = 0.25 (the interleaved worst case; at D = 0.5 the two cancel).")
print(f"\n{'option':50s} {'I motor':>7s} {'phase':>9s} {'VBAT pp':>8s} {'pack ac':>8s}  capacitor rms (per part)")
for o in OPTIONS:
    for i_m in I_MOTOR:
        for ph, d, tag in ((0.0, 0.5, "0, D.5"), (0.5, 0.25, "180, D.25")):
            vpp, iac, caps = ripple_case(o, i_m, ph, d)
            extra, bulk = OPTIONS[o]
            per = []
            for k, v in sorted(caps.items()):
                if k == "lb":
                    per.append(f"bulk {v / bulk[3]:.2f} A")
                else:
                    idx = int(k[2:])
                    part, n = (BASE_MLCC + extra)[idx]
                    per.append(f"{part.split()[0][:8]}x{n} {v / n:.2f} A")
            print(f"{o:50s} {i_m:5.1f} A {tag:>9s} {vpp * 1e3:6.0f}mV {iac:6.2f} A  " + ", ".join(per))
print("Target: the power-tree model assumed 150 mV pp (300 mV in its HV case) at 100 kHz on VBAT")
print("(calculations/power_tree/sim_power_tree.py), and the analog rail met its budget with it.")
print("MLCC ripple capability: CL31B106KBHNNN 2.60 A rms for a 10 C rise, 3.66 A for 20 C")
print("(Samsung product page, ripple-current curve at its 80 kHz setting).")


print("\n=== 3. Input LC: source impedance seen by the bridges (AC, 16.8 V bias) ===")


def zpeak(option, rp, lead, vi=1):
    lines = [f"* Z {option}", f"Rp 0 p1 {rp}", f"Lp p1 bp {lead}", "Rsh bp vb 2m", bank(option, vi),
             "Iin 0 vb AC 1", ".ac dec 400 1k 10meg", ".control", "run",
             "meas ac zmax MAX vm(vb) from=1k to=10meg",
             "meas ac z100k FIND vm(vb) AT=100k", ".endc", ".end"]
    r = run("\n".join(lines))
    return r["zmax"], r["z100k"]


print("Q = Z0 / (pack or lead resistance + R59): the damping by the source alone; a lossy bulk adds")
print("its own damping, which shows in |Z| max.")
print("|Z| max over 1 kHz-10 MHz: equal to the pack resistance when nothing resonates.")
print(f"{'option':50s} {'source':22s} {'f0':>8s} {'Z0':>7s} {'Q':>5s} {'|Z| max':>9s} {'|Z|100k':>8s}")
for o in OPTIONS:
    c = total_c(o, 1)
    for rp, lead, tag in ((0.1, 100e-9, "pack 0.1R, 100 nH"), (0.1, 300e-9, "pack 0.1R, 300 nH"),
                          (0.3, 100e-9, "pack 0.3R, 100 nH"), (R_BENCH, 1e-6, "bench 30m, 1 uH")):
        f0 = 1 / (2 * math.pi * math.sqrt(lead * c))
        z0 = math.sqrt(lead / c)
        extra, bulk = OPTIONS[o]
        r_series = rp + 2e-3
        q = z0 / r_series
        zm, z1 = zpeak(o, rp, lead)
        print(f"{o:50s} {tag:22s} {f0 / 1e3:6.1f}k {z0 * 1e3:5.0f}m {q:5.2f} {zm * 1e3:7.0f}mO {z1 * 1e3:6.0f}mO")


def release(option, rp, lead, i_step=6.0, v=V_HV, vi=2):
    lines = [f"* load release {option}", f"Vp pk 0 {v}", f"Rp pk p1 {rp}", f"Lp p1 bp {lead}", "Rsh bp vb 2m",
             bank(option, vi), f"Il vb 0 PWL(0 {i_step} 200u {i_step} 200.1u 0)",
             ".tran 10n 600u 0 10n", ".control", "run",
             "meas tran vmax MAX v(vb) from=200u to=600u", "meas tran vmin MIN v(vb) from=0 to=200u", ".endc", ".end"]
    r = run("\n".join(lines))
    return r["vmax"]


print(f"\n6 A load release (both bridges and the fan stop at once) from the 17.4 V HV pack:")
for o in OPTIONS:
    row = []
    for rp, lead, tag in ((0.1, 100e-9, "pack 100nH"), (0.1, 300e-9, "pack 300nH"), (R_BENCH, 1e-6, "bench 1uH")):
        row.append(f"{tag} {release(o, rp, lead):5.2f} V")
    print(f"  {o:50s} " + "   ".join(row))


print("\n=== 4. Hot plug and the battery switch (Q6 HSBB3072, R43/R41 100k, C58 47 nF G-D) ===")
# HSBB3072 p2: VGS(th) 1.0/1.7/2.3 V, RDS(on) 3.8 mOhm max at 4.5 V, Ciss 2860 pF, Coss 1300 pF,
# Crss 229 pF at 15 V. VDMOS model fitted to those (ASSUMPTION: square-law kp, Cgd range).
Q6_MODEL = (".model QHS VDMOS(Vto=1.7 Kp=100 Rd=0.5m Rs=0.5m Rg=1 Cgs=2.63n Cgdmax=1.2n Cgdmin=0.12n "
            "A=0.4 Cjo=2.4n Vj=0.8 M=0.5 Is=1e-12 Rb=5m ksubthres=0.1)")


# SMAJ18A (Littelfuse SMAJ series): VBR 20.0-22.1 V at 1 mA, VC 29.2 V at 13.7 A -> about 0.6 Ohm
# of dynamic resistance above a 21 V knee (ASSUMPTION: a zener model with that knee and slope).
TVS = "Dtvs gb bp DTVS\n.model DTVS D(BV=21 IBV=1m RS=0.6 N=1 CJO=1.5n)"


def plug(option, rp, lead, sw4_on, v=V_HV, vi=2, load_r=150.0, direct=False, tvs=False):
    # Node 0 is the pack's negative terminal. J1: bp (BAT_P) and gb (GND_BAT); board GND is bgnd.
    sw = "Rsw bp drv 0.1" if sw4_on else "Rsw bp drv 1G"
    lines = [f"* hot plug {option}", f"Vp pk 0 PWL(0 0 1u 0 1.005u {v})",
             f"Rp pk p1 {rp}", f"Lp p1 bp {lead / 2}", f"Ln 0 gb {lead / 2}",
             "Rsh bp vb 2m", bank(option, vi, node="vb", gnd="bgnd"), f"Rload vb bgnd {load_r}",
             sw, "R43 drv g 100k", "R41 g gb 100k", "C58 g bgnd 47n",
             "M6 bgnd g gb gb QHS", Q6_MODEL, "Rleak bgnd gb 10Meg",
             "Rdirect bgnd gb 1m" if direct else "",
             TVS if tvs else "",
             ".tran 2n 3m 0 20n uic", ".control", "run",
             "let vbd = v(vb) - v(bgnd)", "let vq6 = v(bgnd) - v(gb)", "let vgs = v(g) - v(gb)",
             "meas tran vboard MAX vbd from=1u to=3m",
             "meas tran vds MAX vq6 from=1u to=3m", "meas tran vgsmax MAX vgs from=1u to=3m",
             "meas tran ipk MAX i(Lp) from=1u to=3m", ".endc", ".end"]
    return run("\n".join(lines))


print(f"{'option':50s} {'source':18s} {'SW4':>4s} {'board max':>10s} {'Q6 VDS max':>11s} {'I peak':>7s} {'VGS max':>8s}")
for o in ("electrolytic: JVS25V100M6X4 per bridge", "ceramic only, bulk removed",
          "ceramic: 2 x 1210 10u 50V X7R per bridge", "polymer: 25TQC33MYF per bridge"):
    for rp, lead, tag in ((0.1, 100e-9, "pack 100 nH"), (0.1, 300e-9, "pack 300 nH"), (R_BENCH, 1e-6, "bench 1 uH")):
        for sw in (False, True):
            r = plug(o, rp, lead, sw)
            print(f"{o:50s} {tag:18s} {'on' if sw else 'off':>4s} {r['vboard']:8.2f} V {r['vds']:9.2f} V {r['ipk']:5.1f} A {r['vgsmax']:6.2f} V")
print("With an SMAJ18A from BAT_P to GND_BAT at J1:")
for o in ("ceramic only, bulk removed", "ceramic: 2 x 1210 10u 50V X7R per bridge"):
    for rp, lead, tag in ((0.1, 100e-9, "pack 100 nH"), (R_BENCH, 1e-6, "bench 1 uH")):
        r = plug(o, rp, lead, True, tvs=True)
        print(f"{o:50s} {tag:18s} {'on':>4s} {r['vboard']:8.2f} V {r['vds']:9.2f} V {r['ipk']:5.1f} A {r['vgsmax']:6.2f} V")
print("Reference, Q6 shorted (a plain switch or no switch: the pack lands straight on the capacitors):")
for o in ("electrolytic: JVS25V100M6X4 per bridge", "ceramic only, bulk removed",
          "ceramic: 2 x 1210 10u 50V X7R per bridge", "polymer: 25TQC33MYF per bridge"):
    for rp, lead, tag in ((0.1, 100e-9, "pack 100 nH"), (R_BENCH, 1e-6, "bench 1 uH")):
        r = plug(o, rp, lead, True, direct=True)
        print(f"{o:50s} {tag:18s} {'-':>4s} {r['vboard']:8.2f} V {'-':>11s} {r['ipk']:5.1f} A")


def switch_event(option, closing, rp=0.1, lead=100e-9, v=V_HV, vi=2, load_r=3.0):
    # Pack connected; SW4 closes at 1 ms (closing) or opens at 1 ms after running (opening).
    if closing:
        sw = "Ssw bp drv ctl 0 SWM\nVctl ctl 0 PWL(0 0 1m 0 1.001m 1)"
        init, tstop = "", "40m"
    else:
        sw = "Ssw bp drv ctl 0 SWM\nVctl ctl 0 PWL(0 1 1m 1 1.001m 0)"
        init, tstop = "", "120m"
    lines = [f"* switch {option}", f"Vp pk 0 {v}", f"Rp pk p1 {rp}", f"Lp p1 bp {lead / 2}", f"Ln 0 gb {lead / 2}",
             "Rsh bp vb 2m", bank(option, vi, node="vb", gnd="bgnd"), f"Rload vb bgnd {load_r}",
             sw, ".model SWM SW(Ron=0.1 Roff=1G Vt=0.5 Vh=0.1)", "R43 drv g 100k", "R41 g gb 100k",
             "C58 g bgnd 47n", "M6 bgnd g gb gb QHS", Q6_MODEL, "Rleak bgnd gb 10Meg",
             f".tran 1u {tstop} 0 2u", ".control", "run",
             "let vbd = v(vb) - v(bgnd)", "let vq6 = v(bgnd) - v(gb)",
             f"meas tran vboard MAX vbd from=0.9m to={tstop}",
             f"meas tran vds MAX vq6 from=0.9m to={tstop}",
             f"meas tran ipk MAX i(Lp) from=0.9m to={tstop}",
             "meas tran t10 WHEN vbd=1.74 RISE=1" if closing else "meas tran t10 WHEN vbd=15.66 FALL=1",
             "meas tran t90 WHEN vbd=15.66 RISE=1" if closing else "meas tran t90 WHEN vbd=1.74 FALL=1",
             ".endc", ".end"]
    return run("\n".join(lines))


print("\nSW4 closing (pack plugged, 3 Ohm load) and SW4 opening under a 5.8 A load (3 Ohm at 17.4 V),")
print("pack 0.1 Ohm behind 100 nH:")
for o in ("ceramic only, bulk removed", "ceramic: 2 x 1210 10u 50V X7R per bridge"):
    c = switch_event(o, True)
    s = switch_event(o, False)
    rise = (c.get("t90", float("nan")) - c.get("t10", float("nan")))
    fall = (s.get("t90", float("nan")) - s.get("t10", float("nan")))
    print(f"  {o:50s} close: board max {c['vboard']:5.2f} V, 10-90 % in {rise * 1e3:5.2f} ms, "
          f"inrush {c['ipk']:5.2f} A | open: Q6 VDS max {s['vds']:5.2f} V, board max {s['vboard']:5.2f} V, "
          f"fall {fall * 1e3:5.2f} ms")


print("\n=== 5. Regeneration into VBAT with the pack disconnected ===")
# DCX 10 L 4.5 V: kt 3.52 mNm/A, 2.9 Ohm (maxon p100); 14,300 rpm limit; drivetrain model loop
# resistance adds RBR 0.64 Ohm (calculations/drivetrain/sim.py); choke 97 mOhm max (XAL7070-473).
kt, R_LOOP = 3.52e-3, 2.9 + 0.64 + 0.097
w_max = 14300 * 2 * math.pi / 60
e_max = kt * w_max
p_motor = e_max ** 2 / (4 * R_LOOP)  # the most power a motor can push into the bus (I = E / 2R)
print(f"Back-EMF at 14,300 rpm: {e_max:.2f} V, far below the 12-17.4 V pack: a coasting motor never")
print(f"charges VBAT through the body diodes. Only active braking pumps energy into VBAT (the bridge")
print(f"boosts): at most E^2 / (4 R) = {p_motor:.2f} W per motor, {2 * p_motor:.2f} W for both, at full speed.")
for m in (0.076, 0.100, 0.130):  # robot mass range of calculations/drivetrain/sim.py
    j = 0.151e-7  # rotor inertia (maxon p100)
    e_kin = 0.5 * m * 4.0 ** 2 + 2 * 0.5 * j * w_max ** 2
    print(f"  {m * 1e3:3.0f} g at 4 m/s: kinetic energy {e_kin:.2f} J (motor and bridge losses ignored: an upper bound)")
p_load = 0.6  # ASSUMPTION: MCU + ESP from the buck and the LDO with the emitters and fan off
p_net = 2 * p_motor - p_load
print(f"Net charging power with {p_load} W of logic load: {p_net:.1f} W. Time for VBAT to climb from 16.8 V:")
print(f"{'option':50s} {'to 25 V':>8s} {'to 30 V':>8s} {'to 40 V':>8s}")
for o in OPTIONS:
    # energy between 16.8 V and Vx, with the MLCC capacitance at the higher voltages from the curves
    # (17.4 V point, conservative: the MLCCs lose more above it)
    c = total_c(o, 2)
    row = []
    for vx in (25.0, 30.0, 40.0):
        t = 0.5 * c * (vx ** 2 - 16.8 ** 2) / p_net
        row.append(f"{t * 1e3:6.1f}ms")
    print(f"{o:50s} " + " ".join(row))
print("A stop from 4 m/s lasts hundreds of ms: no capacitor bank absorbs it. Either the firmware")
print("stops regenerative braking (coast or low-side brake, EN = 0) when VBAT rises above the pack's")
print("maximum, or a TVS takes the energy.")

print("\n=== 6. TVS clamp on the battery input (BAT_P to GND_BAT, at J1) ===")
# Littelfuse SMAJ series datasheet: SMAJ18A VR 18 V, VBR 20.0-22.1 V at 1 mA, VC 29.2 V at
# IPP 13.7 A (10/1000 us), 400 W; SMF18A (SOD-123FL, 200 W): VR 18 V, VBR 20.0-22.1 V,
# VC 29.2 V at 6.9 A.
i_clamp = p_net / 21.0
print(f"Regen clamp current about {i_clamp:.2f} A at about 21 V: the TVS sits near VBR (20-22.1 V),")
print(f"far below VC 29.2 V at 13.7 A; {p_net:.1f} W for a few hundred ms ({0.83:.2f} J at most).")
print("Hot plug: the TVS also holds Q6's VDS (30 V absolute maximum) below 30 V.")
