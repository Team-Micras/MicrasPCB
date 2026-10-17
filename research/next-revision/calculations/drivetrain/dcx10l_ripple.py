# DCX 10 L 4.5 V ripple vs PWM frequency and series choke, for research/next-revision/README.md.
# Reuses ripple() from ripple_exact.py (exact periodic RL, unipolar PWM, D = 0.5 worst case).
# Motor data: R 2.9 ohm, L 0.045 mH, maxon catalogue Feb 2025 p100.
# Bus 16.8 V (full 4S). Choke DCR is ignored (heat is reported in the winding only).
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ripple_exact import ripple
R, L = 2.9, 45e-6
for k in (1.0, 0.3):            # datasheet L, and maxon's 0.3 x L factor at 50-100 kHz
    for Lext in (0, 22e-6, 47e-6, 100e-6):
        row = []
        for f in (40e3, 50e3, 100e3, 200e3):
            ipp, irms = ripple(16.8, R, k * L, f, Lext=Lext)
            row.append(f"{f/1e3:.0f}k {ipp:.2f}App {irms**2*R:.2f}W")
        print(f"L={k}xLds Lext={Lext*1e6:.0f}uH | " + " | ".join(row))
