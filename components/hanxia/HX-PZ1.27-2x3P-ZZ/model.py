"""Build the 3D model of the HX PZ1.27-2x3P ZZ on its straddle footprint (HX-PZ1.27-2x3P-ZZ_Straddle).

The header from Hanxia's drawing (HX PZ1.27-2x3P ZZ, rev A, 2023-07-18; HX-PZ1.27-2x3P-ZZ.zen
cites each number), in the footprint's model frame: x along the rows (the footprint's x), y up the
board (KiCad's -y), z out of the board's front face; origin on the board's bottom edge at the front
face. The board, 0.79 mm, stands between the rows; its bottom edge rests on the insulator, whose
2.30 mm pins clamp it and whose 3.90 mm pins point down into the board below.

    ~/codes/MicrasHardware/.venv/bin/python -I components/hanxia/HX-PZ1.27-2x3P-ZZ/model.py OUT.step
    pcb embed-step components/hanxia/HX-PZ1.27-2x3P-ZZ/HX-PZ1.27-2x3P-ZZ_Straddle.kicad_mod OUT.step

Do not commit OUT.step: the footprint embeds it.
"""

import sys

from build123d import Box, Compound, Pos, chamfer, export_step  # noqa: F401

PITCH = 1.27  # along the rows and between them (drawing: 1.27 +-0.1; end view 1.27)
PIN = 0.40  # square pins (SQ 0.40)
UP = 2.30  # the short pins above the insulator (2.30 +-0.2): they clamp the board
DOWN = 3.90  # the long pins below it (3.90 +-0.2): into the board below
INS_L, INS_W, INS_H = 3.81, 3.40, 1.00  # insulator: DIM B for 3 positions, the end view's 3.40, 1.00 high
BOARD = 0.79  # the upright board between the rows (boards/wall stackup)
TIP = 0.08  # the pins' end chamfer


def _pin(x: float, z: float):
    p = Pos(x, (UP - INS_H - DOWN) / 2, z) * Box(PIN, INS_H + UP + DOWN, PIN)
    return chamfer(p.edges().group_by(lambda e: e.center().Y)[0] + p.edges().group_by(lambda e: e.center().Y)[-1], TIP)


def model():
    mid = -BOARD / 2  # the board's mid-plane, between the rows
    body = Pos(0, -INS_H / 2, mid) * Box(INS_L, INS_H, INS_W)
    pins = [_pin(x, mid + s * PITCH / 2) for x in (-PITCH, 0.0, PITCH) for s in (1, -1)]
    return Compound([body, *pins])


if __name__ == "__main__":
    export_step(model(), sys.argv[1])
