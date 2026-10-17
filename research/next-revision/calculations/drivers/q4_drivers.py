# Q4: L6205D vs DRV8874 vs DRV8262 at the DCX 10 L 4.5 V operating points, 16.8 V, 100 kHz.
# Loss model per bridge (TI DRV8262 SLVSFV5C sec. 7.1.1.2; DRV8874 SLVSF66A eqs. 8-17):
#   P = I_rms^2 x (R_HS + R_LS)            conduction (sign-magnitude slow decay: one FET of the
#                                           static leg always on + one FET of the switching leg)
#     + VM x I x t_rf x f                  switching (rise + fall, TI eq. 12-13 / PLS2 term)
#     + 2 x VD x I x tD x f                dead-time body-diode conduction
#     + VM x IVM / n_bridges               quiescent
# Inputs (typ / max), with sources:
#  L6205 (ST L6205 datasheet Sept 2003, p5-6, Thermal data p3): RDS HS 0.34/0.40, LS 0.28/0.34 ohm
#    at 25 C; 0.53/0.59 and 0.47/0.53 at 125 C; tRISE/tFALL 40-250 ns (min/max, no typ) -> 100 ns
#    ASSUMED typ, 250 ns max; dead time 0.5-1 us (tdt), VSD 1.15 V typ at 2.8 A; IS 5 mA typ
#    (both bridges, at 48 V); Rth j-a SO20 51 C/W (6 cm2 Cu) / 77 C/W (no heatsink copper).
#  DRV8874 (SLVSF66A sec. 6.4, 6.5, Fig. 6/7): RDS HS 100/120, LS 100/120 mOhm at 25 C; ~1.25x at
#    85 C (sec. 8.2.1.2.2), ~0.125 ohm at 125 C (Fig. 6/7, read); tRISE = tFALL 150 ns; tDEAD 100 ns;
#    VSD 0.9 V; IVM 3 mA typ / 7 mA max at 24 V; RthJA 36.0 C/W (JEDEC); ZthJA(1 s) ~15 C/W,
#    ZthJA(0.1 s) ~5.5 C/W (Fig. 25, 1 oz, any copper).
#  DRV8262 DDW, dual mode (SLVSFV5C sec. 5.4, 5.5, 7.1.1.2): RDS HS 50/60, LS 50/60 mOhm at 25 C;
#    HS 75/94, LS 72/90 at 125 C; tRF 110 ns; tD 300 ns; VD 1 V; IVM 5 mA typ / 8 mA max (VCC
#    external); RthJA 22.2 C/W (JEDEC); Table 5-1 simulated board: 1.8 / 4.7 / 8.4 / 23.3 C/W at
#    0.1 s / 1 s / 10 s / DC (both bridges in one package).
V, f = 16.8, 100e3
drv = {
 "L6205D":  dict(r25=(0.34+0.28, 0.40+0.34), rhot=(0.53+0.47, 0.59+0.53), trf=(100e-9, 250e-9), td=(1.0e-6, 1.0e-6), vd=(1.15, 1.3), iq=(5e-3, 10e-3), nb=2, rth=51.0, z1=None),
 "DRV8874": dict(r25=(0.20, 0.24), rhot=(0.25, 0.30), trf=(150e-9, 150e-9), td=(100e-9, 100e-9), vd=(0.9, 0.9), iq=(3e-3, 7e-3), nb=1, rth=36.0, z1=15.0),
 "DRV8262": dict(r25=(0.10, 0.12), rhot=(0.147, 0.184), trf=(110e-9, 110e-9), td=(300e-9, 300e-9), vd=(1.0, 1.0), iq=(5e-3, 8e-3), nb=2, rth=22.2, z1=4.7),
}
# ripple adds to I_rms: 100 kHz + 47 uH choke, 0.46-0.69 A pp (drivetrain/dcx10l_ripple.py) -> +pp/sqrt(12) in quadrature
ripple_pp = 0.69
def loss(d, I, hot, k):
    R = (d["rhot"] if hot else d["r25"])[k]
    irms2 = I * I + ripple_pp ** 2 / 12
    pc = irms2 * R
    psw = V * I * d["trf"][k] * f
    pdt = 2 * d["vd"][k] * I * d["td"][k] * f
    pq = V * d["iq"][k] / d["nb"]
    return pc, psw, pdt, pq

print("Loss per bridge at 16.8 V, 100 kHz, ripple 0.69 A pp included (W). typ@25C | max@hot")
print(f"{'driver':8s} {'I (A)':>6s} | {'cond':>6s} {'sw':>6s} {'dead':>6s} {'quies':>6s} {'total':>6s} | {'total max hot':>13s} | % of 0.5xVxI")
for name, d in drv.items():
    for I in (0.5, 1.0, 3.0):
        pc, ps, pd, pq = loss(d, I, False, 0)
        tot = pc + ps + pd + pq
        tmax = sum(loss(d, I, True, 1))
        pin = 0.5 * V * I  # bridge output power at D = 0.5, for scale only
        print(f"{name:8s} {I:6.1f} | {pc:6.3f} {ps:6.3f} {pd:6.3f} {pq:6.3f} {tot:6.3f} | {tmax:13.3f} | {100*tot/pin:5.1f} % typ, {100*tmax/pin:5.1f} % max")
print()
# Junction rise: run profile = both motors at 1.0 A rms continuously (firmware RMS limit over 60 s,
# reached in a 60-s run); 1 s stall at the ITRIP / firmware limit of 3 A on BOTH motors.
for name, d in drv.items():
    pk = d["nb"] if d["nb"] == 2 else 1   # bridges per package
    p_run = pk * sum(loss(d, 1.0, True, 1))
    p_stall = pk * sum(loss(d, 3.0, True, 1))
    z1 = d["z1"]
    s_stall = f"{p_stall*z1:5.0f} K (Zth 1 s {z1} C/W)" if z1 else f"<= {p_stall*d['rth']:4.0f} K (steady-state bound; no transient Zth published)"
    print(f"{name:8s} package: run 1.0 A rms both motors {p_run:5.2f} W -> +{p_run*d['rth']:4.0f} K steady (RthJA {d['rth']}) | "
          f"1 s stall at 3 A both motors {p_stall:5.2f} W -> {s_stall}")
print()
# L6205 overcurrent detection vs DCX 10 L currents (ISOVER 4 / 5.6 / 7.1 A, HS sum per bridge)
R_m = 2.9
ke_rpm = 2710
E_max = 14300 / ke_rpm
for name, Rb in (("L6205D", 0.62), ("DRV8874", 0.20), ("DRV8262", 0.10)):
    for Vb in (16.8, 12.0):
        stall = Vb / (R_m + Rb)
        rev = (Vb + E_max) / (R_m + Rb)
        print(f"{name:8s} VM {Vb:4.1f} V: unregulated stall {stall:4.2f} A, full-speed reversal {rev:4.2f} A")
print("L6205 ISOVER 4.0 / 5.6 / 7.1 A; DRV8874 IOCP 6 A min (10 A typ); DRV8262 IOCP 8 A min per FET")
print()
# Dead-time / delay duty distortion at 100 kHz (inferred: L6205 on-delay incl. dead time 1.6 us vs
# off-delay 0.6 us; DRV8874 tDEAD 100 ns, tPD 400 ns both edges; DRV8262 tD 300 ns, tPDH=tPDL 600 ns)
for name, dt in (("L6205D", 1.6e-6 - 0.6e-6), ("DRV8874", 100e-9), ("DRV8262", 300e-9)):
    print(f"{name:8s} duty distortion ~{100*dt*f:4.1f} % at 100 kHz = {dt*f*V:4.2f} V = {dt*f*V/R_m*1e3:4.0f} mA at stall (DCX 10 L 2.9 ohm)")
