"""Write spec/main_chassis.json: how high a part may stand on the main board under MicrasHardware's
drive blocks, motors and wheels, from its model. tests/test_spec.py checks the spec's [drive_blocks]
zones against it.

A ray straight up from every 0.05 mm point of the board top finds the lowest material of each drive
part over it (0 where the part stands on the board). A point's allowed height is the lowest material
within Layout.clearance (0.3 mm) plus one grid step of it, less Layout.clearance, floored to 0.1 mm.
The file keeps the points of a 0.1 mm grid that allow less than OPEN mm, as runs along y.

Needs MicrasHardware's environment (build123d, OCP, numpy, scipy); MicrasHardware is only read:

    PYTHONPATH=~/codes/MicrasHardware ~/codes/MicrasHardware/.venv/bin/python tools/chassis_shadow.py
"""

import json
import subprocess
from pathlib import Path

import numpy as np
from micras import drive, fasteners, layout
from micras.params import P
from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
from scipy import ndimage

STEP, CLEAR, OPEN = 0.05, P.layout.clearance, 8.0
X = np.round(np.arange(-26.0, 15.0 + 1e-9, STEP), 4)
Y = np.round(np.arange(-25.5, 25.5 + 1e-9, STEP), 4)
OUT = Path(__file__).resolve().parents[1] / "spec/main_chassis.json"


def parts() -> dict:
    """The blocks with their screws, nuts and inserts, the motors, pinions, wheels and what turns in them."""
    out = {**drive.all_parts(), **layout.drive_side(1), **layout.drive_side(-1), **fasteners.parts()}
    return {k: v for k, v in out.items() if not k.startswith(("screw_fan_clamp", "nut_fan_clamp"))}


def lowest(shape) -> np.ndarray:
    """The part's lowest material over each grid point, above the board top (NaN: none)."""
    top, bb = P.board.top_z, shape.bounding_box()
    grid = np.full((len(X), len(Y)), np.nan)
    hit = IntCurvesFace_ShapeIntersector()
    hit.Load(shape.wrapped, 1e-6)
    z0 = bb.min.Z - 1.0
    for i in np.nonzero((bb.min.X - STEP <= X) & (bb.max.X + STEP >= X))[0]:
        for j in np.nonzero((bb.min.Y - STEP <= Y) & (bb.max.Y + STEP >= Y))[0]:
            hit.Perform(gp_Lin(gp_Pnt(float(X[i]), float(Y[j]), z0), gp_Dir(0, 0, 1)), 0.0, bb.max.Z - z0 + 1.0)
            zs = sorted({round(z0 + hit.WParameter(k), 5) for k in range(1, hit.NbPnt() + 1)})
            for a, b in zip(zs[0::2], zs[1::2], strict=False):  # in and out of the solid, in pairs
                if b > top:
                    grid[i, j] = max(a, top) - top
                    break
    return grid


def main() -> None:
    low = np.fmin.reduce([lowest(s) for s in parts().values()])
    low = np.where(np.isfinite(low), low, 99.0)
    r = CLEAR + STEP
    n = int(np.ceil(r / STEP))
    yy, xx = np.mgrid[-n : n + 1, -n : n + 1]
    near = ndimage.minimum_filter(low, footprint=(xx * STEP) ** 2 + (yy * STEP) ** 2 <= r * r + 1e-9, mode="nearest")
    tenths = np.floor((near - CLEAR) * 10 + 1e-6).clip(0)
    rows = []
    for i in range(0, len(X), 2):
        runs, j = [], 0
        while j < len(Y):
            v = tenths[i, j]
            k = j
            while k + 2 < len(Y) and tenths[i, k + 2] == v:
                k += 2
            if v < OPEN * 10:
                runs.append([float(Y[j]), float(Y[k]), int(v)])
            j = k + 2
        if runs:
            rows.append([float(X[i]), runs])
    commit = subprocess.run(
        ["git", "-C", str(Path(drive.__file__).parents[1]), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    data = {
        "source": f"MicrasHardware {commit} (micras/drive.py, layout.py, fasteners.py), tools/chassis_shadow.py",
        "frame": "robot: x forward, y left, mm; heights over the main board's top",
        "clearance": CLEAR,
        "step": 2 * STEP,
        "rows": f"[x, [[y_from, y_to, allowed height in 0.1 mm], ...]]: the grid points that allow under {OPEN} mm",
        "allowed": rows,
    }
    OUT.write_text(json.dumps(data, separators=(",", ":")).replace("]],[", "]],\n[") + "\n")


if __name__ == "__main__":
    main()
