# ESP32 form-factor placement on the main board: the outline and the courtyards of the current
# layout, the chassis parts projected from MicrasHardware, and the candidate ESP positions.
# Usage (KiCad's pcbnew module and matplotlib):
#   git show origin/main-board-fixes:boards/main/layout/main.kicad_pcb > /tmp/main.kicad_pcb
#   python3 placement.py /tmp/main.kicad_pcb placement.png
# Robot frame (spec/main.toml): x forward, y left, mm; x_kicad = 148.5011 - y, y_kicad = 113.5036 - x.
import math, sys
import numpy as np
import pcbnew
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle

OX, OY = 148.5011, 113.5036  # spec/main.toml [kicad] origin_x, origin_y
mm = lambda v: v / 1e6
robot = lambda xk, yk: (OY - yk, OX - xk)
P = lambda x, y: (-y, x)  # plot: robot right to the right, front up

b = pcbnew.LoadBoard(sys.argv[1])
fig, ax = plt.subplots(figsize=(7.4, 11))


def rect(x0, x1, y0, y1, **kw):
    ax.add_patch(Rectangle(P(x0, y1), y1 - y0, x1 - x0, **kw))


# Outline
for d in b.GetDrawings():
    if d.GetLayerName() != "Edge.Cuts":
        continue
    sh = d.GetShape()
    if sh == pcbnew.SHAPE_T_SEGMENT:
        (x0, y0), (x1, y1) = robot(mm(d.GetStart().x), mm(d.GetStart().y)), robot(mm(d.GetEnd().x), mm(d.GetEnd().y))
        ax.plot([-y0, -y1], [x0, x1], color="k", lw=1.2)
    elif sh == pcbnew.SHAPE_T_ARC:
        c = robot(mm(d.GetCenter().x), mm(d.GetCenter().y))
        s = robot(mm(d.GetStart().x), mm(d.GetStart().y))
        m = robot(mm(d.GetArcMid().x), mm(d.GetArcMid().y))
        e = robot(mm(d.GetEnd().x), mm(d.GetEnd().y))
        cx, cy = P(*c)
        ang = lambda p: math.atan2(P(*p)[1] - cy, P(*p)[0] - cx)
        a0, am, a1 = ang(s), ang(m), ang(e)
        n = lambda a: a % (2 * math.pi)
        ts = np.linspace(a0, a0 + n(a1 - a0), 30) if n(am - a0) < n(a1 - a0) else np.linspace(a0, a0 - n(a0 - a1), 30)
        r = mm(d.GetRadius())
        ax.plot(cx + r * np.cos(ts), cy + r * np.sin(ts), color="k", lw=1.2)
    elif sh == pcbnew.SHAPE_T_CIRCLE:
        ax.add_patch(Circle(P(*robot(mm(d.GetCenter().x), mm(d.GetCenter().y))), mm(d.GetRadius()), fill=False, color="k", lw=1.2))

# Chassis, MicrasHardware micras/params.py, drive.py, fan.py, front.py (projected on the board)
rect(-21.9, 13.5, 1, 22.65, fc="#d9d9d9", ec="#888", lw=0.6, alpha=0.6)    # drive block L
rect(-18.9, 13.5, -22.65, -1, fc="#d9d9d9", ec="#888", lw=0.6, alpha=0.6)  # drive block R
ax.text(*P(-5, 13), "drive block L\nparts ≤ 1.5 mm", fontsize=6.5, ha="center", color="#555")
ax.text(*P(-5, -12), "drive block R\nparts ≤ 1.5 mm", fontsize=6.5, ha="center", color="#555")
ax.add_patch(Circle(P(17.5, 0), 13.5, fill=False, ls="--", color="#888", lw=0.8))  # fan part-free ring
ax.text(*P(23.5, 0), "fan: Ø27 part-free ring,\nmetal motor can above", fontsize=6, ha="center", color="#555")
rect(-15.75, -5.75, -7.6, 20.4, fill=False, ec="#b03030", lw=1.0, hatch="////", alpha=0.6)  # left motor can
rect(-9.0, 1.0, -20.4, 7.6, fill=False, ec="#b03030", lw=1.0, hatch="\\\\\\\\", alpha=0.6)  # right motor can
ax.text(*P(-12.5, 3), "motor cans", fontsize=6.5, ha="center", color="#b03030")
rect(-17.8, 2.2, -25.5, 25.5, fill=False, ec="#b07020", lw=1.0, ls=":")  # battery cells, 27-38 mm above
ax.text(*P(-19.5, -18), "battery cells\n27-38 mm above", fontsize=6, ha="center", va="top", color="#b07020")
for s in (1, -1):
    rect(-11.24, 11.24, 18.35 * s if s > 0 else -25, 25 if s > 0 else -18.35, fc="#f2e3b3", ec="#a08a40", lw=0.6, alpha=0.6)
for (x, y) in [(36.72, 21.5), (47.57, 10.19), (47.57, -10.19), (36.72, -21.5)]:
    ax.add_patch(Circle(P(x, y), 4.0, fc="#c0c0ff", ec="#5050a0", lw=0.6, alpha=0.6))
ax.text(*P(47.6, 0), "wall-sensor\ncaps, TO-18 cans", fontsize=6, ha="center", color="#5050a0")

# Board parts: removed in the next revision (green) and kept (grey); courtyard boxes
removed = {"P1", "U5", "U7", "Q7", "F1", "D13", "C77", "C78", "R50", "R51", "R52", "R53", "R54", "R55",
           "U1", "L2", "C48", "C49", "C50", "C51", "IC5", "D6", "D7", "C37", "C38", "C39", "C40", "C41",
           "C65", "C66", "R34", "R35", "IC3", "IC4", "R32", "R33"}
label = {"IC1", "U2", "J1", "SW4", "M1", "M2", "M3", "C36", "IC6", "IC7", "L3", "BZ1", "Q6", "U4",
         "SW1", "SW2", "SW3", "SW5", "U6", "P1", "U5", "L2", "U1", "C37", "Q7", "U7"}
for fp in b.GetFootprints():
    ref = fp.GetReference()
    try:
        bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        if bb.GetWidth() == 0:
            raise ValueError
    except Exception:
        bb = fp.GetBoundingBox(False)
    (xa, ya), (xb, yb) = robot(mm(bb.GetLeft()), mm(bb.GetTop())), robot(mm(bb.GetRight()), mm(bb.GetBottom()))
    x0, x1, y0, y1 = min(xa, xb), max(xa, xb), min(ya, yb), max(ya, yb)
    c = "#2e8b2e" if ref in removed else "#909090"
    rect(x0, x1, y0, y1, fill=False, ec=c, lw=0.9 if ref in removed else 0.4)
    if ref in label:
        ax.text(*P((x0 + x1) / 2, (y0 + y1) / 2), ref, fontsize=5.5, ha="center", va="center", color=c)


def cand(x0, x1, y0, y1, color, ls="-", lw=2.0):
    rect(x0, x1, y0, y1, fill=False, ec=color, lw=lw, ls=ls)


# A: S3-MINI-1 in the rear-left corner, antenna (5.05 mm) beyond the rear edge, feed end at the corner
cand(-41.55, -21.05, 9.0, 24.4, "#1f5fbf")
rect(-41.55, -36.5, 9.0, 24.4, fc="#1f5fbf", alpha=0.25, ec="none")
ax.text(*P(-39.0, 16.7), "A antenna, overhangs 5.05", fontsize=6.5, ha="center", va="center", color="#1f5fbf")
ax.text(*P(-24.6, 16.7), "A: S3-MINI-1 / B: MINI-1U body", fontsize=6.5, ha="center", va="center", color="#1f5fbf", weight="bold")
# C: PICO-1 (or chip-down) + chip antenna in the same corner, antenna along the rear edge
cand(-35.5, -26.5, 13.0, 22.0, "#c0392b", lw=1.6)
rect(-36.5, -32.5, 12.0, 24.0, fc="#c0392b", alpha=0.25, ec="#c0392b", lw=0.8)
ax.text(*P(-29.0, 17.5), "C: PICO-1\n+ π match", fontsize=6.5, ha="center", va="center", color="#c0392b", weight="bold")
# C2: alternative on the left side, front of the wheel (freed P1/U5 area)
cand(14.0, 24.0, 14.5, 21.0, "#c0392b", ls="--", lw=1.4)
rect(16.0, 28.0, 21.0, 25.0, fc="#c0392b", alpha=0.2, ec="#c0392b", lw=0.8, ls="--")
ax.text(*P(19.0, 17.8), "C2", fontsize=7, ha="center", va="center", color="#c0392b", weight="bold")

ax.set_aspect("equal")
ax.set_xlim(-30, 30)
ax.set_ylim(-45, 57)
ax.set_xlabel("robot y (mm): left ← → right")
ax.set_xticks(range(-30, 31, 10), [str(-t) for t in range(-30, 31, 10)])
ax.set_ylabel("robot x (mm), front up")
ax.set_title("Main board (main-board-fixes): chassis projection and ESP32 positions\n"
             "green = removed in the next revision; A/B/C = rear-left corner; C2 = alternative", fontsize=9)
ax.grid(True, lw=0.3, alpha=0.4)
fig.tight_layout()
fig.savefig(sys.argv[2], dpi=150)
