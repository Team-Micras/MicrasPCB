# PWM current ripple, maxon rule of thumb (MotorChokeCalculation V1.1, 2022-07-05, p7):
# IPP = VCC / (4 Ltot fPWM) for 3-level/unipolar PWM (worst case at D = 0.5),
# effective inductance at 50-100 kHz ~ 0.3 x datasheet (1 kHz) value.
# 2-level (bipolar / locked anti-phase) worst case = VCC/(Ltot fPWM) at D=0.5.
import math
windings = {  # DCX 8 M, maxon catalogue Feb 2025 p98: (Vnom, R ohm, L mH, Inom A)
    "DCX8M 2.4V": (2.4, 4.13, 0.014, 0.345),
    "DCX8M 4.2V": (4.2, 12.0, 0.0411, 0.199),
    "DCX8M 6V":   (6.0, 29.0, 0.0941, 0.13),
    "DCX8M 9V":   (9.0, 54.3, 0.183, 0.0949),
    "DCX8M 12V":  (12., 92.2, 0.276, 0.0728),
    "DCX12L 4.5V":(4.5, 1.94, 0.071, 0.851),  # 2022 catalogue p98
}
print(f"{'winding':12} {'V':>5} {'f kHz':>6} | {'Ipp(L)':>7} {'Ipp(0.3L)':>9} {'Irms(0.3L)':>10} {'Pripple W':>9} {'Ipp/1.5In':>9}")
for name,(vn,R,LmH,In) in windings.items():
    for V in (14.8, 16.8, 20.0):
        for f in (20e3, 50e3, 100e3, 200e3, 400e3):
            L = LmH*1e-3
            ipp = V/(4*L*f); ipp3 = V/(4*0.3*L*f)
            irms = ipp3/(2*math.sqrt(3))  # triangular ripple rms
            p = irms**2*R
            print(f"{name:12} {V:5.1f} {f/1e3:6.0f} | {ipp:7.2f} {ipp3:9.2f} {irms:10.3f} {p:9.3f} {ipp3/(1.5*In):9.1f}")
    print()
# Continuous copper-loss budget (hot) for comparison: In^2 * R * (1+0.0039*75)
for name,(vn,R,LmH,In) in windings.items():
    print(name, "continuous loss budget ~", round(In**2*R*(1+0.0039*(100-25)),3), "W")
