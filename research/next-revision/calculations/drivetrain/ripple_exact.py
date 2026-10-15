# Exact periodic RL ripple (unipolar/3-level PWM, synchronous bridge so current may reverse),
# D = 0.5 worst case. Ripple RMS heat in winding R. Also external series choke needed.
import math
import numpy as np
W = {  # name: (R ohm, L_datasheet H, Inom A)  maxon catalogue DCX 8 M Feb 2025 p98; DCX 12 L Apr 2022 p98
 "DCX8M 2.4V": (4.13, 14.0e-6, 0.345), "DCX8M 4.2V": (12.0, 41.1e-6, 0.199),
 "DCX8M 6V": (29.0, 94.1e-6, 0.13), "DCX8M 9V": (54.3, 183e-6, 0.0949),
 "DCX8M 12V": (92.2, 276e-6, 0.0728), "DCX12L 4.5V": (1.94, 71e-6, 0.851),
 "1020 (Micras v1)": (15.4, 8e-6, None),  # L unknown: 8 uH is the MicrasHardware fan-motor guess, NOT measured
}
def ripple(V, R, L, f, D=0.5, Lext=0.0, n=4000):
    L = L + Lext; T = 1/f; tau = L/R
    # periodic steady state of di/dt = (u - E - R i)/L, E chosen so mean u = E (zero mean current): u in {V,0}
    E = D*V
    # simulate a few periods
    dt = T/n; i = 0.0; rec = []
    for k in range(int(30*n) if tau > 2*T else 6*n):
        t = (k % n)*dt
        u = V if t < D*T else 0.0
        a = math.exp(-dt/tau); iinf = (u-E)/R
        i = iinf + (i-iinf)*a
        if k >= (int(30*n) if tau > 2*T else 6*n) - n: rec.append(i)
    rec = np.array(rec); rec -= rec.mean()
    return rec.max()-rec.min(), math.sqrt((rec**2).mean())
if __name__ == "__main__":
    print("Exact RL ripple at D=0.5 (worst case). Pr = Irms^2 R (heat with zero torque).")
    for name,(R,L,In) in W.items():
        for Leff_k in (0.3, 1.0):
            for V in (14.8, 16.8, 20.0):
                row=[]
                for f in (20e3, 50e3, 100e3, 400e3):
                    ipp, irms = ripple(V, R, Leff_k*L, f)
                    row.append(f"{f/1e3:.0f}k: {ipp:5.2f}App {irms:5.3f}Arms {irms**2*R:6.2f}W")
                print(f"{name:16} L={Leff_k:.1f}xLds V={V:4.1f} | " + " | ".join(row))
        print()
    print("External choke (total, both legs) for ripple heat <= 0.06 W (10% of DCX8M continuous ~0.61 W), 100 kHz, 20 V, Leff=0.3 Lds:")
    for name in ("DCX8M 4.2V","DCX8M 6V","DCX8M 12V"):
        R,L,In = W[name]
        for Lext in (0, 22e-6, 47e-6, 100e-6, 220e-6, 470e-6):
            for f in (50e3, 100e3):
                ipp, irms = ripple(20.0, R, 0.3*L, f, Lext=Lext)
                print(f"  {name} Lext={Lext*1e6:5.0f}uH f={f/1e3:.0f}k Ipp={ipp:.3f} Irms={irms:.3f} P={irms**2*R:.3f} W")
