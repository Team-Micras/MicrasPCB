import math
from motors import MOTORS
from sim import accel, run_budget, burst_time, mu, g, r, eta
from ripple_exact import ripple
# figure of merit
FOM = {  # name: (kt mNm/A, R ohm, nmax rpm, mass g)  sources in drivetrain/motors.py and research/next-revision/README.md
 "DCX 6 M 4.5V": (2.34,20.8,17300,2.4), "DCX 8 M 4.2V": (3.36,12,17300,4.4), "DCX 10 S 4.5V": (3.2,9.72,14300,6.3),
 "DCX 10 L 4.5V": (3.52,2.9,14300,11), "DCX 12 L 4.5V": (4.83,1.94,12000,16),
 "Faulhaber 0816 003SR": (2.11,5.4,16000,4.5), "Faulhaber 1024 003SR": (2.33,1.36,15000,10.8),
 "Faulhaber 1224 006SR": (4.11,4.6,16000,13.5), "Faulhaber 1717 003SR": (1.98,1.07,16000,18),
 "Faulhaber 1717 006SR": (3.96,4.31,16000,18), "Faulhaber 2224 003SR": (3.47,0.564,9000,46),
 "maxon ECX SPEED 8 M HP 12V (BLDC)": (3.62,8.38,50000,6), "Faulhaber 0824 B 012B (BLDC)": (3.0,10.7,90000,5.2),
 "Faulhaber 1028 B 012B (BLDC)": (3.38,4.37,79000,9.4), "Micras v1 1020 (estimate)": (5.0,15.4,None,None),
}
print("motor | km mNm/sqrtW | km/mass | G for 4 m/s at nmax | km*G (wheel-force FoM) | Pcu both motors for 2.37 N / 5.08 N at that G (W)")
for k,(kt,R,n,m) in FOM.items():
    km = kt/math.sqrt(R)
    if n:
        G = n/60*2*math.pi*r/4.0
        P = [2*((F/2*r/(G*eta))*1e3/km)**2 for F in (2.37,5.08)]
        print(f"{k} | {km:.2f} | {km/m:.3f} | {G:.2f} | {km*G:.1f} | {P[0]:.2f} / {P[1]:.2f}")
    else:
        print(f"{k} | {km:.2f} | - | - | {km*36/7:.1f} (at 36/7) | -")
print()
G10 = 14300/60*2*math.pi*r/4.0
print("DCX10L G for 4 m/s:", round(G10,2))
for k in ("DCX10L_4V5","DCX10L_6V"):
    M = MOTORS[k]; km = M["kt"]/math.sqrt(M["R"])
    for tr in (60,120,600):
        P = run_budget(k,tr); Fb = 2*km*math.sqrt(P)*G10*eta/r
        print(f"{k} run {tr}s: P {P:.2f} W/motor, Irms {math.sqrt(P/M['R']):.2f} A, Frms budget {Fb:.2f} N; share at traction (76 g, 1.47 N) {min(1,(Fb/2.37)**2)*100:.0f} %, (76 g, 4 N) {min(1,(Fb/5.08)**2)*100:.0f} %, (130 g, 4 N) {min(1,(Fb/5.64)**2)*100:.0f} %")
    for I in (1,2,3,4):
        print(f"  {k} burst at {I} A: {burst_time(k,I):.2f} s from 25 C, {burst_time(k,I,60):.2f} s from 60 C")
print()
print(f"{'motor':11} {'G':>5} {'m g':>4} {'Fd':>4} {'Vbus':>5} {'Ilim':>5} | t_to_4m/s  Itr  Ipk  Irms  Ibus_pk Ibus_rms  Tw  eff stall")
for k in ("DCX10L_4V5","DCX10L_6V"):
    for mass in (0.076,0.100,0.130):
        for Fd in (1.47,4.0):
            for V in (12.0,14.8,16.8,18.8):
                for Il in (None,2.0):
                    s = accel(k, G10, mass, Fd, V, Ilim=Il, vstop=4.0)
                    print(f"{k:11} {G10:5.2f} {mass*1e3:4.0f} {Fd:4.2f} {V:5.1f} {str(Il):>5} | {s['t']:.3f} {s['Itr']:.2f} {s['Ipk']:.2f} {s['Irms']:.2f} {s['Isup_pk']:.2f} {s['Isup_rms']:.2f} {s['Tw']:.1f} {s['eff']:.2f} {s['stall_I']:.2f}")
print()
E = 3.52e-3*14300*2*math.pi/60
for V in (14.8,16.8,18.8,20):
    print(f"DCX10L_4V5 Vbus {V}: stall {V/(2.9+0.64):.2f} A, reversal at nmax {(V+E)/(2.9+0.64):.2f} A, EMF at nmax {E:.2f} V, no-load speed at Vbus {2710*V:.0f} rpm, duty cap for nmax ~{14300/2710/V*100:.0f} %")
for k,R,L in (("DCX10L 4.5V",2.9,45e-6),("DCX10L 6V",6.4,78e-6)):
    for Lk in (0.3,1.0):
        for V in (14.8,16.8):
            row=[]
            for f in (20e3,50e3,100e3):
                ipp,irms = ripple(V,R,Lk*L,f)
                row.append(f"{f/1e3:.0f}k {ipp:.2f}App {irms:.3f}Arms {irms**2*R:.2f}W")
            print(f"{k} L={Lk}xLds V={V}: "+" | ".join(row))
for Lext in (22e-6,47e-6,100e-6):
    ipp,irms = ripple(16.8,2.9,0.3*45e-6,100e3,Lext=Lext)
    print(f"DCX10L 4.5V 16.8 V 100 kHz 0.3xL + {Lext*1e6:.0f} uH choke: {ipp:.2f} App, {irms:.3f} Arms, {irms**2*2.9:.3f} W")
