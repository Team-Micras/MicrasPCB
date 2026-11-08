# Fraction of a run the motors may spend at the traction-limited force (rest ~0 torque) before Tmax,
# from the run budget: p = (Frms_budget / F_traction)^2
import math
from sim import run_budget, MOTORS, mu, g, r, eta
for k,G in (("DCX8M_4V2",36/7),("DCX12L_4V5",3.59)):
    M=MOTORS[k]; km=M["kt"]/math.sqrt(M["R"])
    for tr in (60,120):
        P=run_budget(k,tr); Fb=2*km*math.sqrt(P)*G*eta/r
        for mass,Fd in ((0.076,1.47),(0.076,4.0),(0.130,4.0)):
            Ft=mu*(mass*g+Fd); p=min(1,(Fb/Ft)**2)
            print(f"{k} G={G:.2f} run {tr}s: Frms budget {Fb:.2f} N; m={mass*1e3:.0f} g Fd={Fd}: F_trac {Ft:.2f} N -> max time share at traction limit {p*100:.0f} %")
