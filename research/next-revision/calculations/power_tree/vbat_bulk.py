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
7. The TVS with the pack pulled under braking.
8. Q6's gate network against the STSPIN958's 0.5 V/us VS slew: plug-in (pack and bench supply),
   plug-in with USB present, SW4 closing and opening, the pack pulled under load; asserts the
   board's network keeps VBAT's slew within 0.5 V/us.
9. Q8's gate-source voltage (+-12 V) with the pack plugged under USB, a VBAT short, the pack
   pulled and SW4 opened; asserts the board's D16 keeps it inside.
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
    # The board: 4 x 1210 per bridge and the fan's two as 1210, no 1206 on VBAT.
    "ceramic: 1210 only, 4 per bridge + 2 at the fan": ([("CL32B106KBJNNNE 10u 50V X7R 1210", 10)], None),
    # The board plus one 35 V solid-polymer aluminium SMD part on VBAT (LCSC listings, JLCPCB parts
    # search 2026-10-25; JIERR MA series catalogue "ALUMINUM SOLID CAPACITORS": ESR at 100 kHz,
    # leakage <= 0.2 CV or 500 uA; Panasonic OS-CON SVPF). ESL 3 nH and the 120 Hz capacitance at
    # 100 kHz: ASSUMPTION.
    "board + 1 x MA35V47M6X6 47u 35V polymer Al": ([("CL32B106KBJNNNE 10u 50V X7R 1210", 10)],
                                                    (47e-6, 0.035, 3e-9, 1)),
    "board + 1 x MA35V100M6X8 100u 35V polymer Al": ([("CL32B106KBJNNNE 10u 50V X7R 1210", 10)],
                                                     (100e-6, 0.030, 3e-9, 1)),
    "board + 1 x 35SVPF22M 22u 35V OS-CON": ([("CL32B106KBJNNNE 10u 50V X7R 1210", 10)],
                                             (22e-6, 0.035, 3e-9, 1)),
}
# Existing VBAT ceramics on main2 (Drivers.zen): 4 x 10 uF 1206 per bridge (C83-C86, C92-C95) and
# 2 x 10 uF 1206 at the fan (C36, C99), all CL31B106KBHNNNE; the 100 nF and 470 nF parts are
# ignored here.
BASE_MLCC = [("CL31B106KBHNNNE 10u 50V X7R 1206", 10)]
# Options that replace those ten 1206 parts rather than add to them.
NO_BASE = {"ceramic: 1210 only, 4 per bridge + 2 at the fan", "board + 1 x MA35V47M6X6 47u 35V polymer Al",
           "board + 1 x MA35V100M6X8 100u 35V polymer Al", "board + 1 x 35SVPF22M 22u 35V OS-CON"}


def base(option):
    return [] if option in NO_BASE else BASE_MLCC

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
    for i, (part, n) in enumerate(base(option) + extra):
        c = ceff(part, v_index) * n
        lines.append(f"Cm{i} {node} m{i}a {c:.4e}\nRm{i} m{i}a m{i}b {MLCC_ESR / n:.4e}\nLm{i} m{i}b {gnd} {MLCC_ESL / n:.4e}")
    if bulk:
        c, esr, esl, n = bulk
        lines.append(f"Cb {node} ba {c * n:.4e}\nRb ba bb {esr / n:.4e}\nLb bb {gnd} {esl / n:.4e}")
    return "\n".join(lines) + "\n"


def total_c(option, v_index):
    extra, bulk = OPTIONS[option]
    c = sum(ceff(p, v_index) * n for p, n in base(option) + extra)
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
                    part, n = (base(o) + extra)[idx]
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


print("\n=== 4. Hot plug and the battery switch with C58 47 nF from gate to drain only ===")
print("(the bulk options compared with that gate network; section 8 compares the gate networks)")
# HSBB3072 Ver 3.0 p2: VGS(th) 1.0/1.7/2.3 V, RDS(on) 3.8 mOhm max at 4.5 V, Ciss 2860 pF, Coss
# 1300 pF, Crss 229 pF at 15 V. VDMOS model, its DC part fitted to the typical curves (ngspice DC
# sweeps of the model against them): Fig. 1 (ID at VDS 2 V: about 45 A at VGS 3 V and 245 A at
# 4 V; model 38 and 240 A), Fig. 2 (RDS(on) at 20 A: 2.6 / 1.85 / 1.65 mOhm at VGS 4 / 6 / 10 V;
# model 2.9 / 2.0 / 1.6), Fig. 4 (Miller plateau 2.9 V at ID 20 A, VDS 15 V; model 2.82 V) and p2
# (VGS(th) 1.7 V typ at 250 uA; model 1.71 V). Cgd fitted to Fig. 7 (Crss 1600 / 640 / 380 / 225 /
# 155 / 125 / 115 pF at 0 / 5 / 10 / 15 / 20 / 25 / 30 V; the model gives 1850 / 720 / 415 / 300 /
# 235 / 200 / 170 pF, more gate coupling than the part) and Coss to Fig. 7's 4.0 / 2.1 / 1.6 /
# 1.2 nF at 0 / 5 / 10 / 15 V (model 6.3 / 2.6 / 1.8 / 1.5 nF).
Q6_MODEL = (".model QHS VDMOS(Vto=2.4 Kp=230 mtriode=1.7 Rd=0.65m Rs=0.65m Rg=1 Cgs=2.63n Cgdmax=3n "
            "Cgdmin=0.045n A=0.3 Cjo=3.5n Vj=0.8 M=0.45 Is=1e-12 Rb=5m ksubthres=0.15)")


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

print("\n=== 7. The SMAJ18A at J1 with the pack pulled under braking, Q6 on and off ===")
# No pack: J1 open. Braking pushes current into VBAT and out of the board's GND (a current source
# from GND to VBAT, no logic load: conservative). The TVS (cathode BAT_P, anode GND_BAT) closes
# the loop through Q6: its channel with SW4 on, its body diode (GND_BAT -> GND) with SW4 off.


def regen_clamp(option, sw4_on, i_regen, vi=2):
    sw = "Rsw bp drv 0.1" if sw4_on else "Rsw bp drv 1G"
    vg = 8.4 if sw4_on else 0.0
    lines = [f"* regen clamp {option}", "Rsh bp vb 2m", bank(option, vi, node="vb", gnd="0"),
             f"Ireg 0 vb {i_regen}", sw, "R43 drv g 100k", "R41 g gb 100k", "C58 g 0 47n",
             "M6 0 g gb gb QHS", Q6_MODEL, TVS,
             f".ic v(vb)=16.8 v(bp)=16.8 v(gb)=0 v(g)={vg}",
             ".tran 1u 30m 0 5u uic", ".control", "run",
             "let vq6 = 0 - v(gb)", "let vgs = v(g) - v(gb)",
             "meas tran vmax MAX v(vb) from=0 to=30m", "meas tran vend FIND v(vb) AT=29m",
             "meas tran vq6 FIND vq6 AT=29m", "meas tran vgs FIND vgs AT=29m", ".endc", ".end"]
    return run("\n".join(lines))


print(f"{'SW4 / Q6':22s} {'I regen':>8s} {'VBAT max':>9s} {'VBAT end':>9s} {'Q6 VDS':>8s} {'Q6 VGS':>7s}")
for sw4 in (True, False):
    for i_r in (0.15, 0.5, 2.0):
        r = regen_clamp("ceramic: 2 x 1210 10u 50V X7R per bridge", sw4, i_r)
        tag = "on (channel)" if sw4 else "off (body diode)"
        print(f"{tag:22s} {i_r:6.2f} A {r['vmax']:7.2f} V {r['vend']:7.2f} V {r['vq6']:6.2f} V {r['vgs']:5.2f} V")
print("Both states clamp VBAT: with SW4 off the TVS current returns to GND through Q6's body diode")
print("(GND_BAT to GND is its forward direction), adding its drop (1.2 V max at 1 A, HSBB3072 p2).")


print("\n=== 8. Q6's gate network against the STSPIN958's 0.5 V/us VS slew (DS14341 Table 1) ===")
# The board side of every event: VBAT - GND, which is the STSPIN958's VS to GND. Its slew is
# measured as the largest change over any 1 us (the waveform resampled at 0.1 us), so a
# nanosecond ESL spike does not count as a supply ramp. Options for Q6's gate (R43/R41 100k):
GATES = {
    # name: (external gate-drain capacitance to GND, external gate-source capacitance to GND_BAT)
    "C58 47n G-D": (47e-9, 0.0),
    "(a) C58 47n G-D + 2.2u G-S": (47e-9, 2.2e-6),
    "(b) C58 47n G-S + 1n G-D": (1e-9, 47e-9),
    "(b) C58 100n G-S + 1n G-D": (1e-9, 100e-9),
}
BOARD_GATE = "(b) C58 100n G-S + 1n G-D"  # Regulators.zen: C58 100 nF G-S, C114 1 nF G-D
SLEW_MAX = 0.5e6  # V/s, DS14341 Table 1
BOARD_BANK = "ceramic: 1210 only, 4 per bridge + 2 at the fan"

# B5819W (JCET p1: VF 0.6 V max at 1 A): Schottky fitted to the typical Forward Characteristics
# at 25 C (p2: about 0.30 V at 0.1 A and 0.48 V at 1 A; the model gives 0.32 and 0.48 V).
D14_MODEL = ".model DSCH D(Is=2u N=1.1 Rs=0.11 Cjo=100p BV=40)"
# AO3401A (AOS Rev 3.1 p2): VGS(th) -0.9 V typ, Ciss 645 pF, Crss 55 pF at -15 V; ASSUMPTION:
# a square-law fit to RDS(on) 47 mOhm at -4.5 V.
Q8_MODEL = (".model QP8 VDMOS(pchan Vto=-0.9 Kp=12 Rd=10m Rs=10m Rg=8 Cgs=590p Cgdmax=250p "
            "Cgdmin=40p A=0.5 Cjo=200p Is=1e-12 Rb=20m)")
# D16, BZT52C10S (Diodes DS30093 Rev. 20, Electrical Characteristics): VZ 9.4-10.6 V at 5 mA,
# ZZT 20 Ohm; the 10.6 V maximum lets VGS go furthest.
DZ_MODEL = ".model DZ10 D(BV=10.6 IBV=5m RS=20 CJO=50p)"
# PESD5V0S1BL on +5V: VBR 5.5-9.5 V at 1 mA (Nexperia Rev 04 Table 9); the 9.5 V maximum and an
# assumed 1 Ohm slope (ASSUMPTION) let VSYS sit highest.
D8_MODEL = ".model DESD D(BV=9.5 IBV=1m RS=1 CJO=30p)"
# The 1210 50 V X7R on VSYS and LDO_IN (C52, C80, CL32B106KBJNNNE): its charge between 17 V and
# 8 V, integrated over Samsung's DC-bias curve (product.samsungsem.com/mlcc/CL32B106KBJNNN.do,
# "DC Bias"), is that of a linear 7.27 uF: each is modelled so (a nonlinear capacitor stalls
# ngspice here). C53, the 1 uF 0805 50 V X7R CL21B105KBFNNNE, likewise as 0.84 uF (its curve).
C_VSYS_EFF = 7.27e-6
C53_EFF = 0.84e-6


def entry(gate, *, tstop, tmax, v=V_HV, rp=0.1, lead=100e-9, pack="plug", sw4="on", load_r=150.0,
          usb=False, c63=1e-6, vsys_w=0.0, fault=None, option=BOARD_BANK, vi=2, tvs=True, zener=True):
    """The battery entry, Q6 and its gate network, the VBAT bank, and the VSYS power path (D14,
    Q8 with R56/R57, C52 + C53 on VSYS, R58 + C80, C63 and D8 on +5V, the buck as a constant
    power load). Node 0 is the pack's negative terminal; the board's GND is bgnd.
    pack: "plug" (the pack lands at 1 us), "on" (connected from the start), ("unplug", t).
    sw4: "on", "off", ("close", t), ("open", t). fault: t of a VBAT-to-GND short (10 mOhm), held
    to the end (F1 opening later changes nothing for Q8: VBAT stays shorted). usb: a host's 5 V behind 0.1 Ohm with 120 uF (USB 2.0
    7.2.4.1, the downstream port's minimum) between +5V and GND."""
    cgd, cgs = GATES[gate]
    if pack == "plug":
        src = f"Vp pk 0 PWL(0 0 1u 0 1.005u {v})"
    else:
        src = f"Vp pk 0 {v}"
    # 10 Ohm across each lead's inductance (the leads' losses at tens of MHz; it keeps ngspice
    # from stalling at the contact events and leaves the ringing below 10 MHz undamped).
    lines = [f"* entry {gate}", src, f"Rp pk p1 {rp}", f"Lp p1 p2 {lead / 2}", f"Ln 0 gb {lead / 2}",
             "Rlp p1 p2 10", "Rln 0 gb 10"]
    if isinstance(pack, tuple):  # the pack's + contact (10 mOhm) opens to 1 GOhm over 10 us
        lines += [f"Rj p2 bp R='10m*exp(25.3*V(cj))'\nVcj cj 0 PWL(0 0 {pack[1]} 0 {pack[1] + 1e-5} 1)"]
    else:
        lines.append("Rj p2 bp 1m")
    if fault is not None:
        # 1 GOhm to 10 mOhm over 1 us
        lines += [f"Bs vb bgnd I=V(vb,bgnd)/(1G*exp(-25.3*V(cs)))\nVcs cs 0 PWL(0 0 {fault} 0 {fault + 1e-6} 1)"]
    lines.append("Rf bp vb 2m")
    lines += [bank(option, vi, node="vb", gnd="bgnd"), f"Rload vb bgnd {load_r}"]
    if sw4 == "on":
        lines.append("Rsw vb drv 0.1")
    elif sw4 == "off":
        lines.append("Rsw vb drv 1G")
    else:
        kind, t = sw4
        a, b = (0, 1) if kind == "close" else (1, 0)
        lines += [f"Ssw vb drv ctl 0 SWM\nVctl ctl 0 PWL(0 {a} {t} {a} {t + 1e-6} {b})",
                  ".model SWM SW(Ron=0.1 Roff=1G Vt=0.5 Vh=0.1)"]
    lines += ["R43 drv g 100k", "R41 g gb 100k", f"Cgd g bgnd {cgd}" if cgd else "",
              f"Cgs g gb {cgs}" if cgs else "", "M6 bgnd g gb gb QHS", Q6_MODEL, "Rleak bgnd gb 10Meg"]
    if tvs:
        lines.append(TVS.replace("Dtvs gb bp", "Dtvs gb vb"))  # D15 behind F1, VBAT to GND_BAT
    # Power path.
    lines += ["D14 vb vsys DSCH", D14_MODEL, f"Cc52 vsys bgnd {C_VSYS_EFF}",
              f"Cc53 vsys bgnd {C53_EFF}", "R58 vsys ldo 22",f"Cc80 ldo bgnd {C_VSYS_EFF}",
              "R56 vb pg 10k", "R57 pg bgnd 1Meg", "M8 v5 pg vsys vsys QP8", Q8_MODEL,
              f"Dz pg vsys DZ10\n{DZ_MODEL}" if zener else "",
              # C63, a 25 V X5R at 5-10 V: ASSUMPTION 40 % of its nominal left.
              f"Cc63 v5 bgnd {0.4 * c63:.3e}", "Dd8 bgnd v5 DESD", D8_MODEL, "Rdiv v5 bgnd 55k",
              "R44 vb bgnd 120k"]
    if vsys_w:
        lines.append(f"Bbuck vsys bgnd I={vsys_w}/max(V(vsys,bgnd),4)*u(V(vsys,bgnd)-4.2)")
    if usb:
        lines += ["Vusb vh bgnd 5", "Rusb vh vhc 0.1", "Lusb vhc v5 1u", "Chost vh bgnd 120u"]
    lines += [f".tran {tmax / 4:.3e} {tstop} 0 {tmax:.3e}", ".control", "run",
              "let vbd = v(vb) - v(bgnd)", "let vq6 = v(bgnd) - v(gb)", "let vgs6 = v(g) - v(gb)",
              "let vgs8 = v(pg) - v(vsys)", "let vsy = v(vsys) - v(bgnd)",
              "meas tran vboard MAX vbd", "meas tran vds MAX vq6", "meas tran vgsmax MAX vgs6",
              "meas tran ipk MAX i(Lp)", "meas tran vgs8min MIN vgs8", "meas tran vgs8max MAX vgs8",
              "meas tran vsysmax MAX vsy", "let i2 = i(Lp) * i(Lp)", "meas tran i2t INTEG i2",
              "let pq = (v(bgnd) - v(gb)) * i(Lp)", "meas tran pq6 MAX pq", "meas tran eq6 INTEG pq",
              "wrdata {WAVE} vbd", ".endc", ".end"]
    return "\n".join(x for x in lines if x)


def run_wave(netlist):
    """run(), plus the board voltage's waveform as (t, v) lists."""
    with tempfile.TemporaryDirectory() as d:
        wave = os.path.join(d, "w.txt")
        p = os.path.join(d, "c.cir")
        # Solver options tried in turn when ngspice stalls ("Timestep too small" at a contact
        # event): rshunt adds 1 GOhm from every node to ground, reltol relaxes to 0.2 %; neither
        # changes a result beyond its printed digits.
        for opts in ("method=gear", "method=gear rshunt=1e9", "method=gear reltol=2e-3"):
            with open(p, "w") as f:
                f.write(netlist.replace("{WAVE}", wave).replace(".control", f".options {opts}\n.control", 1))
            out = subprocess.run(["ngspice", "-b", p], capture_output=True, text=True, timeout=1200)
            if not ("aborted" in out.stdout + out.stderr or "Timestep too small" in out.stdout + out.stderr):
                break
        res = {}
        for m in re.finditer(r"^(\w+)\s*=\s*([-+0-9.eE]+)", out.stdout, re.M):
            res[m.group(1).lower()] = float(m.group(2))
        if "aborted" in out.stdout + out.stderr or "Timestep too small" in out.stdout + out.stderr:
            raise RuntimeError("ngspice stopped early:\n" + out.stdout[-1500:] + out.stderr[-1500:])
        if not res or not os.path.exists(wave):
            raise RuntimeError(out.stdout[-2000:] + out.stderr[-2000:])
        t, v = [], []
        with open(wave) as f:
            for line in f:
                a = line.split()
                if len(a) >= 2:
                    t.append(float(a[0]))
                    v.append(float(a[1]))
    return res, t, v


def slew(t, v, window=1e-6, step=1e-7):
    """Largest |dV/dt| over any `window`, from the waveform resampled every `step`."""
    if not t:
        return 0.0
    n = int((t[-1] - t[0]) / step)
    out, j = [], 0
    for i in range(n + 1):
        x = t[0] + i * step
        while j < len(t) - 2 and t[j + 1] < x:
            j += 1
        t0, t1 = t[j], t[j + 1]
        out.append(v[j] + (v[j + 1] - v[j]) * ((x - t0) / (t1 - t0) if t1 > t0 else 0.0))
    k = int(round(window / step))
    return max((abs(out[i + k] - out[i]) for i in range(len(out) - k)), default=0.0) / window


def crossing(t, v, level, rising, after=0.0):
    for i in range(1, len(t)):
        if t[i] < after:
            continue
        if (v[i - 1] < level <= v[i]) if rising else (v[i - 1] > level >= v[i]):
            return t[i]
    return float("nan")


slews = {}
print("Plug-in (pack 0.1 Ohm at 17.4 V; bench supply 30 mOhm on 1 m leads at 17.4 and 24 V); VBAT")
print("slew is VBAT - GND (the STSPIN958's VS), Q6 VGS its peak; 150 Ohm on VBAT, no USB:")
print(f"{'gate':28s} {'source':20s} {'SW4':>4s} {'VBAT slew':>10s} {'I peak':>7s} {'I2t':>9s} {'Q6 VGS':>7s} {'Q6 VDS':>7s} {'board max':>9s}")
for g in GATES:
    for rp, lead, v, tag in ((0.1, 100e-9, V_HV, "pack 100 nH"), (0.1, 300e-9, V_HV, "pack 300 nH"),
                             (R_BENCH, 1e-6, V_HV, "bench 1 uH 17.4 V"), (R_BENCH, 1e-6, 24.0, "bench 1 uH 24 V")):
        for sw in ("off", "on"):
            r, t, w = run_wave(entry(g, tstop=0.3e-3, tmax=20e-9, rp=rp, lead=lead, v=v, sw4=sw))
            s = slew(t, w)
            slews[(g, tag, "plug", sw)] = s
            print(f"{g:28s} {tag:20s} {sw:>4s} {s / 1e6:7.3f}V/us {r['ipk']:5.1f} A {r['i2t']:7.4f}A2s {r['vgsmax']:5.2f} V "
                  f"{r['vds']:5.2f} V {r['vboard']:7.2f} V")

print("\nSW4 closing at 1 ms and opening at 1 ms under a 3 Ohm load (5.8 A at 17.4 V), pack 0.1 Ohm on")
print("100 nH: the delay to 10 % (closing) or from 90 % (opening) of VBAT, the 10-90 % time, the slew,")
print("the inrush peak and Q6's peak power (VDS x ID):")
print(f"{'gate':28s} {'event':6s} {'delay':>9s} {'10-90 %':>9s} {'VBAT slew':>10s} {'I peak':>7s} {'Q6 peak':>8s} {'Q6 energy':>10s}")
for g in GATES:
    big = GATES[g][1] > 1e-6
    for ev in ("close", "open"):
        tstop = (0.6 if big else 0.06) if ev == "close" else (1.2 if big else 0.08)
        net = entry(g, tstop=tstop, tmax=1e-6, pack="on", sw4=(ev, 1e-3), load_r=3.0)
        r, t, w = run_wave(net)
        hi, lo = 0.9 * V_HV, 0.1 * V_HV
        if ev == "close":
            t10, t90 = crossing(t, w, lo, True, 1e-3), crossing(t, w, hi, True, 1e-3)
            delay, edge = t10 - 1e-3, t90 - t10
        else:
            t90, t10 = crossing(t, w, hi * 0.95, False, 1e-3), crossing(t, w, lo, False, 1e-3)
            delay, edge = t90 - 1e-3, t10 - t90
        s = slew(t, w, step=2e-7)
        slews[(g, "pack 100 nH", ev, "-")] = s
        print(f"{g:28s} {ev:6s} {delay * 1e3:6.2f} ms {edge * 1e3:6.3f} ms {s / 1e6:7.3f}V/us {r['ipk']:5.2f} A "
              f"{r['pq6']:6.1f} W {r['eq6'] * 1e3:7.2f} mJ")
print("Q6's SOA (HSBB3072 Fig. 8, TC = 25 C, single pulse): about 410 W for 100 us and 130 W for 1 ms.")
r = run_wave(entry(BOARD_GATE, tstop=5e-3, tmax=0.2e-6, sw4="on"))[0]
print(f"{BOARD_GATE}: plug-in with SW4 on, the whole turn-on (5 ms, 150 Ohm load): F1 carries "
      f"{r['ipk']:.2f} A peak, I2t {r['i2t'] * 1e3:.2f} mA2s.")

print("\nPack pulled at 1 ms with SW4 on, under 3 Ohm (5.8 A) and 1.5 Ohm (11.6 A, both bridges and the fan")
print("at their limits): VBAT discharges into the load, whatever the gate network:")
for g in GATES:
    for rl in (3.0, 1.5):
        r, t, w = run_wave(entry(g, tstop=1.6e-3, tmax=0.1e-6, pack=("unplug", 1e-3), load_r=rl))
        s = slew(t, w)
        slews[(g, f"unplug {rl}", "unplug", "on")] = s
        print(f"  {g:28s} {rl:4.1f} Ohm: VBAT slew {s / 1e6:6.3f} V/us, board max {r['vboard']:5.2f} V")

print("\nPlug-in with USB already powering the board (SW4 on): the pack's - lands on GND_BAT, Q6 decides")
print("when VBAT rises; VSYS sits on USB until then:")
for g in GATES:
    big = GATES[g][1] > 1e-6
    r, t, w = run_wave(entry(g, tstop=0.4 if big else 0.03, tmax=0.5e-6, sw4="on", usb=True, vsys_w=0.5))
    s = slew(t, w, step=2e-7)
    slews[(g, "usb", "plug", "on")] = s
    print(f"  {g:28s} VBAT slew {s / 1e6:6.3f} V/us, Q6 VGS max {r['vgsmax']:5.2f} V, Q8 VGS "
          f"{r['vgs8min']:6.2f} to {r['vgs8max']:5.2f} V")

bad = {k: s for k, s in slews.items() if k[0] == BOARD_GATE and s > SLEW_MAX}
assert not bad, f"{BOARD_GATE}: VBAT slews above 0.5 V/us in {bad}"
print(f"\n{BOARD_GATE} (the board): every case above keeps VBAT within 0.5 V/us "
      f"(largest {max(s for k, s in slews.items() if k[0] == BOARD_GATE) / 1e6:.3f} V/us).")
print("Q6 stays off at plug-in and ramps VBAT over 0.4 ms, so the pack's or a bench supply's lead")
print("inductance never rings against the VBAT bank at plug-in: a bulk part's damping shows only in")
print("section 3 (load release, source impedance).")


print("\n=== 9. Q8 (AO3401A) gate-source, +-12 V absolute maximum (AOS p1) ===")
# Q8's gate follows VBAT through R56 10k; its source is VSYS, held by C52/C53/C80 behind D14. When
# VBAT falls faster than VSYS, VGS goes negative until Q8 conducts and dumps VSYS into +5V (C63,
# D8, the ESP's 55k divider, or a USB host's 120 uF).
print(f"{'case':58s} {'C63':>6s} {'D8':>4s} {'D16':>4s} {'Q8 VGS min':>11s} {'VSYS max':>9s}")
q8 = {}
cases = [
    ("pack plugged with USB present, SW4 on", dict(tstop=0.03, tmax=0.5e-6, usb=True, vsys_w=0.5)),
    ("VBAT shorted to GND, no USB, 0 W", dict(tstop=3e-3, tmax=0.1e-6, pack="on", fault=1e-3)),
    ("VBAT shorted to GND, no USB, 0.5 W on VSYS", dict(tstop=3e-3, tmax=0.1e-6, pack="on", fault=1e-3, vsys_w=0.5)),
    ("VBAT shorted to GND, USB present", dict(tstop=3e-3, tmax=0.1e-6, pack="on", fault=1e-3, usb=True)),
    ("pack pulled under 1.5 Ohm (11.6 A), no USB, 0 W", dict(tstop=3e-3, tmax=0.1e-6, pack=("unplug", 1e-3), load_r=1.5)),
    ("SW4 opened under 3 Ohm (5.8 A), no USB, 0 W", dict(tstop=0.03, tmax=0.5e-6, pack="on", sw4=("open", 1e-3), load_r=3.0)),
]
for name, kw in cases:
    for c63, d8, zener in ((10e-6, True, False), (10e-6, False, False), (1e-6, False, False),
                           (1e-6, True, True), (1e-6, False, True)):
        net = entry(BOARD_GATE, c63=c63, zener=zener, **kw)
        if not d8:
            net = net.replace("Dd8 bgnd v5 DESD", "")
        r, _, _ = run_wave(net)
        q8[(name, c63, d8, zener)] = r["vgs8min"]
        print(f"{name:58s} {c63 * 1e6:4.0f}uF {'yes' if d8 else 'no':>4s} {'yes' if zener else 'no':>4s} "
              f"{r['vgs8min']:9.2f} V {r['vsysmax']:7.2f} V")
worst = min(v for k, v in q8.items() if k[3])
assert worst >= -12.0, f"Q8 VGS reaches {worst:.2f} V with D16"
print(f"With D16 (the board) Q8's VGS stays at or above {worst:.2f} V, inside +-12 V, with or without D8.")
