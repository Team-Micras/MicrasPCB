"""Straight-line acceleration and thermal budget of a two-motor micromouse.
Assumptions (stated in research/next-revision/README.md): gear efficiency 0.9, no aero drag/rolling loss, wheel inertia neglected
except rotor reflected inertia, copper alpha 0.0039/K, two-node maxon thermal model (Cw = tw/Rth2,
Ch = tm/Rth1), bridge+shunt resistance 0.64 ohm in series (L6205 0.3 ohm typ per switch x2 + 40 mOhm shunt),
ambient 25 C. Traction F = mu (m g + Fd) shared by the two wheels.
"""
import math, sys
sys.path.insert(0, __import__("os").path.dirname(__file__))
from motors import MOTORS
g = 9.81; r = 0.011413; mu = 1.07; eta = 0.9; ALPHA = 0.0039; RBR = 0.64

def accel(m_name, G, mass, Fd, Vbus, Ilim=None, vstop=None, dt=5e-5, Rsrc=0.0, verbose=False):
    M = MOTORS[m_name]; R0, kt = M["R"], M["kt"]; J = M["J"] or 0.0
    nmax = M["nmax"]; vmax_mech = nmax/60*2*math.pi*r/G if nmax else 1e9
    vstop = min(vstop or 1e9, vmax_mech)
    Ftr = mu*(mass*g + Fd)                   # total traction force
    Tm_tr = Ftr/2*r/(G*eta)                  # motor torque per motor at the traction limit
    Itr = Tm_tr/kt
    v = 0.0; t = 0.0; Tw = 25.0; Th = 25.0
    Cw = M["tw"]/M["Rth2"] if M["tw"] else None; Ch = M["tm"]/M["Rth1"] if M["tm"] else None
    Ipk = 0; Isup_pk = 0; I2 = 0; Isup2=0; Ecu = 0; Ein = 0; Emech=0
    m_eff = mass + 2*J*(G/r)**2*eta          # reflected rotor inertia
    while v < vstop - 1e-6 and t < 5:
        w = v/r*G
        R = R0*(1+ALPHA*(Tw-25)) + RBR
        Icmd = Itr if Ilim is None else min(Itr, Ilim)
        u = Icmd*R + kt*w
        D = u/Vbus
        if D > 1: D = 1; Icmd = max(0.0,(Vbus - kt*w)/R)
        F = 2*Icmd*kt*G*eta/r
        a = F/m_eff
        Pcu = Icmd**2*R0*(1+ALPHA*(Tw-25))
        Pin = 2*D*Vbus*Icmd               # both motors, from the bus
        Isup = Pin/Vbus
        if Cw:
            Tw += dt*(Pcu - (Tw-Th)/M["Rth2"])/Cw
            Th += dt*((Tw-Th)/M["Rth2"] - (Th-25)/M["Rth1"])/Ch
        Ipk = max(Ipk, Icmd); Isup_pk = max(Isup_pk, Isup)
        I2 += Icmd**2*dt; Isup2 += Isup**2*dt; Ecu += 2*Pcu*dt; Ein += Pin*dt; Emech += F*v*dt
        v += a*dt; t += dt
    return dict(t=t, v=v, a_tr=Ftr/mass, Itr=Itr, Ipk=Ipk, Irms=math.sqrt(I2/t), Isup_pk=Isup_pk,
                Isup_rms=math.sqrt(Isup2/t), Tw=Tw, Ecu=Ecu, Ein=Ein, eff=Emech/Ein if Ein else 0, D_end=D,
                stall_I=Vbus/(R0+RBR), vmax=vmax_mech, d=None)

def run_budget(m_name, t_run, T0=25.0):
    """Constant copper loss per motor that brings the winding to Tmax at t_run (two-node model, R(T))."""
    M = MOTORS[m_name]
    if not M["tw"]: return None
    Cw = M["tw"]/M["Rth2"]; Ch = M["tm"]/M["Rth1"]
    lo, hi = 0.0, 50.0
    for _ in range(40):
        P = (lo+hi)/2; Tw = Th = T0; dt = min(0.02, M['tw']/50); t = 0; ok = True
        # P is the loss at 25 C winding; it grows with R(T) at constant current
        while t < t_run:
            p = P*(1+ALPHA*(Tw-25))
            Tw += dt*(p-(Tw-Th)/M["Rth2"])/Cw; Th += dt*((Tw-Th)/M["Rth2"]-(Th-25)/M["Rth1"])/Ch; t += dt
            if Tw > M["Tmax"]: ok = False; break
        lo, hi = (P, hi) if ok else (lo, P)
    return lo

def burst_time(m_name, I, T0=25.0):
    M = MOTORS[m_name]; Cw = M["tw"]/M["Rth2"]; Ch = M["tm"]/M["Rth1"]
    Tw = Th = T0; dt = 1e-4; t = 0
    while Tw < M["Tmax"] and t < 600:
        p = I**2*M["R"]*(1+ALPHA*(Tw-25))
        Tw += dt*(p-(Tw-Th)/M["Rth2"])/Cw; Th += dt*((Tw-Th)/M["Rth2"]-(Th-25)/M["Rth1"])/Ch; t += dt
    return t

if __name__ == "__main__":
    print("== Traction limit: total force, per-motor torque & current (G=36/7, eta 0.9, r 11.41 mm, mu 1.07) ==")
    for mass in (0.076, 0.100, 0.130):
        for Fd in (0.0, 1.0, 1.47, 4.0):
            Ftr = mu*(mass*g+Fd); Tm = Ftr/2*r/(36/7*eta)
            s = f"m={mass*1e3:3.0f} g Fd={Fd:4.2f} N: F={Ftr:4.2f} N a={Ftr/mass:5.1f} m/s2 Tmotor={Tm*1e3:5.2f} mNm |"
            for k in ("DCX8M_4V2","DCX8M_6V","DCX8M_12V","DCX12L_4V5","1020_v1"):
                M = MOTORS[k]; I = Tm/M["kt"]; P = I**2*M["R"]
                s += f" {k}:{I:4.2f}A/{P:4.1f}W"
            print(s)
    print()
    print("== Motor constant km = kt/sqrt(R) (mNm/sqrt(W)), copper loss per (mNm)^2 ==")
    for k,M in MOTORS.items():
        km = M["kt"]/math.sqrt(M["R"])*1e3; print(f"  {k:12} km={km:.3f} mNm/sqrtW  ->  {1/km**2:.3f} W per mNm^2")
    print()
    print("== Burst time at constant current from 25 C (and from 60 C) to Tmax ==")
    for k in ("DCX8M_4V2","DCX12L_4V5"):
        M = MOTORS[k]
        for I in (0.4, 0.6, 0.8, 1.0, 1.5, 2.0, 3.0):
            print(f"  {k} I={I:.1f} A: {burst_time(k,I):7.2f} s (from 60 C: {burst_time(k,I,60):6.2f} s)")
    print()
    print("== Run budget: max constant copper loss per motor so the winding reaches Tmax at t_run (start 25 C) ==")
    for k in ("DCX8M_4V2","DCX8M_6V","DCX12L_4V5"):
        M = MOTORS[k]; km = M["kt"]/math.sqrt(M["R"])
        for tr in (10, 30, 60, 120, 600):
            P = run_budget(k, tr); Trms = km*math.sqrt(P); Frms = 2*Trms*36/7*eta/r
            print(f"  {k} t_run={tr:6.0f}s: P={P:5.2f} W/motor -> Irms={math.sqrt(P/M['R']):.3f} A, Trms={Trms*1e3:.2f} mNm, Frms(G=36/7, 2 motors)={Frms:.2f} N")
    print()
    print("== Straight-line acceleration 0 -> min(4 m/s, speed limit), traction-limited, current limit as given ==")
    hdr = f"{'motor':11} {'G':>5} {'m g':>4} {'Fd':>4} {'Vbus':>5} {'Ilim':>5} | {'t s':>5} {'v_end':>5} {'vmax':>5} {'Itr':>5} {'Ipk':>5} {'Irms':>5} {'Isup_pk':>7} {'Isup_rms':>8} {'Tw C':>6} {'eff':>4} {'stall A':>7}"
    print(hdr)
    for k, G in (("DCX8M_4V2",36/7),("DCX8M_6V",36/7),("DCX8M_12V",36/7),("DCX12L_4V5",36/7),("DCX12L_4V5",3.5),("1020_v1",36/7)):
        for mass in (0.076, 0.100, 0.130):
            for Fd in (1.0, 4.0):
                for V in (12.0, 14.8, 16.8, 18.8, 20.0):
                    for Ilim in (None, 1.0):
                        if k=="1020_v1" and Ilim: continue
                        res = accel(k, G, mass, Fd, V, Ilim=Ilim, vstop=4.0)
                        print(f"{k:11} {G:5.2f} {mass*1e3:4.0f} {Fd:4.1f} {V:5.1f} {str(Ilim):>5} | {res['t']:5.3f} {res['v']:5.2f} {min(res['vmax'],99):5.2f} {res['Itr']:5.2f} {res['Ipk']:5.2f} {res['Irms']:5.2f} {res['Isup_pk']:7.2f} {res['Isup_rms']:8.2f} {res['Tw']:6.1f} {res['eff']:4.2f} {res['stall_I']:7.2f}")
