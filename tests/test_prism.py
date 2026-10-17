"""Every board's layout folder names its root schematic and board for KiCad Prism.

Without `.prism.json`, a Prism project registered without its `.kicad_pro` takes the first
`*.kicad_sch` in the folder (sorted ignoring case) as the root, so a board whose module sheet sorts
before `<board>.kicad_sch` (main's DRIVERS) loses that sheet from the viewer.
"""

from __future__ import annotations

import json

import pytest
from micras_pcb.paths import board_sch, boards, layout_dir


@pytest.mark.parametrize("board", boards())
def test_prism_config_names_the_root_files(board: str) -> None:
    config = json.loads((layout_dir(board) / ".prism.json").read_text())
    assert config["schematic"] == board_sch(board).name
    assert config["pcb"] == f"{board}.kicad_pcb"
    assert board_sch(board).is_file()
