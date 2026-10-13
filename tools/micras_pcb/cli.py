"""micras-pcb: one entry point for the repo's generators and checks (see README)."""

from __future__ import annotations

import argparse
import sys

from . import checks, jlc, lvs, mech, outputs, site
from .paths import boards


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="micras-pcb")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def board_cmd(name: str, help: str, check: bool = False):
        p = sub.add_parser(name, help=help)
        p.add_argument("boards", nargs="*", help="board names (default: all)")
        if check:
            p.add_argument("--check", action="store_true", help="verify only; fail on drift (CI)")
        return p

    board_cmd("mech", "apply spec/<board>.toml to the layout and export <board>_mech.json", check=True)
    board_cmd("rules", "copy rules/jlcpcb.kicad_dru next to each board's project", check=True)
    board_cmd("erc", "KiCad ERC on the generated schematic")
    board_cmd("drc", "KiCad DRC with the JLCPCB rules and zone refill")
    board_cmd("lvs", "connectivity of the generated schematic vs the PCB")
    board_cmd("dfm", "Diode DFM against the JLCPCB PDK")
    board_cmd("fab", "JLCPCB gerbers, drill, BOM and CPL into build/<board>/fab")
    board_cmd("outputs", "review outputs: schematic PDF/SVG, layer SVGs, 3D renders, GLB/STEP")
    sub.add_parser("site", help="static design portal in build/site (after outputs and fab)")
    p = sub.add_parser("parts", help="check parts/jlc.toml covers every board")
    p.add_argument("--online", action="store_true", help="also query JLCPCB stock and library type")

    a = ap.parse_args(argv)
    if a.cmd == "parts":
        return jlc.check_parts(a.online)
    if a.cmd == "site":
        return site.run()
    status = 0
    for b in a.boards or boards():
        print(f"== {a.cmd} {b}")
        if a.cmd == "mech":
            status |= mech.run(b, a.check)
        elif a.cmd == "rules":
            status |= checks.rules(b, a.check)
        elif a.cmd == "erc":
            status |= checks.erc(b)
        elif a.cmd == "lvs":
            status |= lvs.run(b)
        elif a.cmd == "drc":
            status |= checks.drc(b)
        elif a.cmd == "dfm":
            status |= checks.dfm(b)
        elif a.cmd == "fab":
            status |= jlc.fab(b)
        elif a.cmd == "outputs":
            status |= outputs.run(b)
    return status


if __name__ == "__main__":
    sys.exit(main())
