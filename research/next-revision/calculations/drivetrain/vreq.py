# Bus voltage needed to hold the traction-limited force at top speed: V = ke*w + I*(R_hot + R_bridge)
import math
from motors import MOTORS
g=9.81; r=0.011413; mu=1.07; eta=0.9; RBR=0.64
for k in ("DCX8M_4V2","DCX8M_6V","DCX8M_12V","DCX12L_4V5"):
    M=MOTORS[k]
    for vtop in (3.0, 4.0):
        G = M["nmax"]/60*2*math.pi*r/vtop  # highest ratio that still reaches vtop at nmax
        w = vtop/r*G
        for mass,Fd in ((0.076,1.47),(0.076,4.0),(0.130,4.0)):
            F = mu*(mass*g+Fd); T = F/2*r/(G*eta); I = T/M["kt"]
            Rh = M["R"]*(1+0.0039*(80-25))
            V = M["kt"]*w + I*(Rh+RBR)
            # plugging/reversal worst case at top speed with full bus reversed, no current limit:
            print(f"{k:11} vtop={vtop} G={G:4.2f} m={mass*1e3:.0f}g Fd={Fd}: T={T*1e3:5.2f} mNm I={I:4.2f} A, EMF={M['kt']*w:5.2f} V, V_needed={V:5.1f} V")
    print()
# Uncontrolled reversal current at top speed (EMF adds to the bus): (Vbus + EMF)/(R+RBR)
for k in ("DCX8M_4V2","DCX8M_6V","DCX12L_4V5","1020_v1"):
    M=MOTORS[k]; E = M["kt"]*(M["nmax"] or 18000)*2*math.pi/60
    for V in (14.8,16.8,18.8,20.0):
        print(f"{k:11} Vbus={V}: stall {V/(M['R']+RBR):5.2f} A, reversal at nmax {(V+E)/(M['R']+RBR):5.2f} A (EMF {E:.2f} V)")
