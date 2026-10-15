"""Review outputs for a board, uploaded by CI with the fab package as the run artifact.

build/<board>/review/:
  <board>-schematic.pdf / .svg   generated schematic
  <board>-<layer>.svg            copper, mask and silk layers, page fitted to the board
  <board>-top.png / -bottom.png / -iso.png   3D renders
  <board>.glb / <board>.step     3D models in the spec frame (drill origin = spec origin)

A schematic-only board (no layout yet) gets the schematic alone.
"""

from __future__ import annotations

import shutil
import subprocess

from .paths import SCHEMATIC_ONLY, board_pcb, board_sch, build_dir, has_layout
from .tools import kicad_cli

LAYER_SVGS = {
    "top": "F.Cu,F.Mask,F.Silkscreen,Edge.Cuts",
    "bottom": "B.Cu,B.Mask,B.Silkscreen,Edge.Cuts",
}
RENDERS = {"top": [], "bottom": ["--side", "bottom"], "iso": ["--rotate", "-45,0,45", "--perspective"]}


def run(board: str) -> int:
    out = build_dir(board) / "review"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    cli, pcbf, sch = kicad_cli(), str(board_pcb(board)), str(board_sch(board))

    def k(*args):
        subprocess.run([cli, *args], check=True, capture_output=True)

    k("sch", "export", "pdf", "-o", str(out / f"{board}-schematic.pdf"), sch)
    k("sch", "export", "svg", "-o", str(out), sch)
    (out / f"{board}.svg").rename(out / f"{board}-schematic.svg")
    if not has_layout(board):
        print(f"{board}: layer SVGs, renders and 3D models skipped: {SCHEMATIC_ONLY}")
        _list(board, out)
        return 0
    for name, layers in LAYER_SVGS.items():
        k(
            "pcb",
            "export",
            "svg",
            "--mode-single",
            "--fit-page-to-board",
            "--exclude-drawing-sheet",
            "--check-zones",
            *(["--mirror"] if name == "bottom" else []),
            "-l",
            layers,
            "-o",
            str(out / f"{board}-{name}.svg"),
            pcbf,
        )
    for name, extra in RENDERS.items():
        k(
            "pcb",
            "render",
            "--quality",
            "high",
            "--background",
            "opaque",
            "-w",
            "1600",
            "-h",
            "1200",
            "--zoom",
            "0.9",
            *extra,
            "-o",
            str(out / f"{board}-{name}.png"),
            pcbf,
        )
    k(
        "pcb",
        "export",
        "glb",
        "--drill-origin",
        "--include-tracks",
        "--include-pads",
        "--include-zones",
        "--include-silkscreen",
        "--include-soldermask",
        "-f",
        "-o",
        str(out / f"{board}.glb"),
        pcbf,
    )
    k("pcb", "export", "step", "--drill-origin", "-f", "-o", str(out / f"{board}.step"), pcbf)
    _list(board, out)
    return 0


def _list(board: str, out) -> None:
    for f in sorted(out.iterdir()):
        print(f"  {f.relative_to(build_dir(board).parent.parent)}")
