"""The encoder board's 3V3 fork without an acute corner, as a one-off pcbnew script (KiCad 10).

    python3 boards/encoder/layout/fork.py [--no-sync]

Runs once, after fixes.py, on the layout it leaves. The previous revision's 3V3 trunk turns 45
degrees at (149.997, 102.281) and forks there into two branches that leave in the same direction:
the one to IC1 pin 11 (VDD3V3) runs on at 45 degrees and turns along y = 102.041, the one to pin 12
(VDD) turns north after 0.057 mm, at x = 150.037. They part at 45 degrees away from any pad, a
wedge that traps etchant (tests/test_layout.py, test_tracks_are_octilinear_without_acute_corners).
The branch to pin 11 now leaves the vertical of the branch to pin 12 square, at y = 102.041:
its 45 degree piece goes, its straight run to the pad starts at x = 150.037, and the vertical is
split there. Same copper otherwise, every corner 90 degrees or more. Zones are refilled before
saving and `pcb layout` syncs the result.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixes as fx

FORK = (149.9969, 102.280755)  # the trunk's 45 degree turn, where both branches start
BRANCH_X = 150.03698  # the vertical of the branch to IC1 pin 12
PIN11_Y = 102.040865  # the straight run into IC1 pin 11


def fork() -> None:
    diag = fx.segment("3V3", "F", FORK, (150.23679, PIN11_Y))
    run = fx.segment("3V3", "F", (150.23679, PIN11_Y), (151.4391, PIN11_Y))  # into IC1 pin 11
    vertical = fx.segment("3V3", "F", (BRANCH_X, 102.240675), (BRANCH_X, 101.794765))
    fx.drop(diag)
    tee = fx.split(vertical, (BRANCH_X, PIN11_Y))
    at_start = fx.near(fx.xy(run.GetStart()), (150.23679, PIN11_Y), 2e-3)
    (run.SetStart if at_start else run.SetEnd)(fx.pt(*tee))


def main() -> int:
    fx.B = pcbnew.LoadBoard(str(fx.LAYOUT))
    pcbnew.KIID.SeedGenerator(0x666F726B)  # a re-run on the same input is byte-identical
    fork()
    pcbnew.ZONE_FILLER(fx.B).Fill(fx.B.Zones())
    pcbnew.SaveBoard(str(fx.LAYOUT), fx.B)
    if "--no-sync" not in sys.argv:
        env = dict(
            line.split("=", 1)
            for line in (fx.ROOT / "versions.env").read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
        subprocess.run(
            ["pcb", f"+{env['PCB_TOOLCHAIN'].strip()}", "layout", "--no-open", "boards/encoder/encoder.zen"],
            cwd=fx.ROOT,
            check=True,
            capture_output=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
