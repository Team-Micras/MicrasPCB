"""Repository layout: one place that knows where each board's files live."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARDS = ROOT / "boards"
BUILD = ROOT / "build"


def boards() -> list[str]:
    return sorted(p.parent.name for p in BOARDS.glob("*/pcb.toml"))


def has_layout(board: str) -> bool:
    """A board without a .kicad_pcb is schematic only: its .zen declares Project(layout = False),
    so `pcb apply` writes the schematic and no layout (placement and routing not started)."""
    return board_pcb(board).is_file()


def layout_boards() -> list[str]:
    return [b for b in boards() if has_layout(b)]


SCHEMATIC_ONLY = "schematic only, no layout yet (its .zen declares Project(layout = False))"


def board_zen(board: str) -> Path:
    return BOARDS / board / f"{board}.zen"


def layout_dir(board: str) -> Path:
    return BOARDS / board / "layout"


def board_pcb(board: str) -> Path:
    return layout_dir(board) / f"{board}.kicad_pcb"


def board_sch(board: str) -> Path:
    return layout_dir(board) / f"{board}.kicad_sch"


def build_dir(board: str) -> Path:
    d = BUILD / board
    d.mkdir(parents=True, exist_ok=True)
    return d
