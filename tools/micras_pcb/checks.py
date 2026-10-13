"""Rule checks over the generated KiCad projects: ERC, DRC and DFM (LVS is in lvs.py).

Each check writes its JSON report to build/<board>/ and prints one line per violation. A
violation fails the check unless it is excluded in KiCad (exclusions live in the .kicad_pro, so
every exclusion is a reviewed, committed decision).
"""

from __future__ import annotations

import filecmp
import json
import shutil
import sqlite3
import subprocess

from . import status
from .paths import ROOT, board_pcb, board_sch, board_zen, build_dir, layout_dir
from .tools import kicad_cli, pcb

RULES = ROOT / "rules" / "jlcpcb.kicad_dru"
PDK = ROOT / "rules" / "jlcpcb-pdk.toml"


def rules(board: str, check: bool) -> int:
    dst = layout_dir(board) / f"{board}.kicad_dru"
    if check:
        if not dst.exists() or not filecmp.cmp(RULES, dst, shallow=False):
            print(f"{dst.relative_to(ROOT)} differs from rules/jlcpcb.kicad_dru: run `micras-pcb rules {board}`")
            return 1
        return 0
    shutil.copyfile(RULES, dst)
    return 0


def _violations(report: dict) -> list[dict]:
    items = list(report.get("violations", []))
    items += report.get("unconnected_items", [])
    items += [dict(v, type=v.get("type", "parity")) for v in report.get("schematic_parity", [])]
    for sheet in report.get("sheets", []):
        items += sheet.get("violations", [])
    return [v for v in items if not v.get("excluded")]


def _print(kind: str, board: str, items: list[dict], ok: bool) -> None:
    for v in items:
        where = "; ".join(i.get("description", "") for i in v.get("items", []))
        print(f"  {kind} {v.get('severity', '?'):7} {v.get('type', '?')}: {v.get('description', '')}  [{where}]")
    summary = "clean" if not items else f"{len(items)} violation(s)"
    print(f"{board}: {kind} {summary}")
    status.record(board, kind, ok, summary)


def erc(board: str) -> int:
    out = build_dir(board) / "erc.json"
    subprocess.run(
        [
            kicad_cli(),
            "sch",
            "erc",
            "--format",
            "json",
            "--severity-error",
            "--severity-warning",
            "-o",
            str(out),
            str(board_sch(board)),
        ],
        check=True,
        capture_output=True,
    )
    items = _violations(json.loads(out.read_text()))
    _print("ERC", board, items, not items)
    return 1 if items else 0


def drc(board: str) -> int:
    out = build_dir(board) / "drc.json"
    subprocess.run(
        [
            kicad_cli(),
            "pcb",
            "drc",
            "--format",
            "json",
            "--refill-zones",
            "--severity-error",
            "--severity-warning",
            "-o",
            str(out),
            str(board_pcb(board)),
        ],
        check=True,
        capture_output=True,
    )
    items = _violations(json.loads(out.read_text()))
    ok = not any(v.get("severity") == "error" for v in items)
    _print("DRC", board, items, ok)
    return 0 if ok else 1


def dfm(board: str) -> int:
    """Diode's geometry DFM against the JLCPCB PDK (catches what KiCad's DRC does not model)."""
    out = build_dir(board) / "dfm.sqlite"
    r = subprocess.run(
        [*pcb(), "dfm", str(board_zen(board)), "--pdk", str(PDK), "-o", str(out), "--offline"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    (build_dir(board) / "dfm.json").write_text(r.stdout)
    try:
        report = json.loads(r.stdout)
    except json.JSONDecodeError:
        print(r.stdout.strip() or r.stderr.strip())
        return r.returncode or 1
    with sqlite3.connect(out) as db:
        for (msg,) in db.execute("select message from findings"):
            print(f"  DFM {msg}")
    s = report["summary"]
    summary = (
        f"{report['verdict']} ({s['rules_passed']} passed, {s['rules_failed']} failed, "
        f"{s['rules_warned']} warned; PDK {report['pdk']['revision']})"
    )
    print(f"{board}: DFM {summary}")
    status.record(board, "DFM", r.returncode == 0, summary)
    return r.returncode
