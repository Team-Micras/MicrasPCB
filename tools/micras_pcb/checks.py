"""Rule checks over the generated KiCad projects: ERC, DRC and DFM (LVS is in lvs.py).

Each check writes its JSON report to build/<board>/ and prints one line per violation. A
violation fails the check unless it is excluded in KiCad (exclusions live in the .kicad_pro, so
every exclusion is a reviewed, committed decision), or, for ERC, it is an undriven power input on
a net the board declares as supplied from off the board (boards/<board>/erc.toml, see
`external_supplies`).
"""

from __future__ import annotations

import filecmp
import json
import re
import shutil
import sqlite3
import subprocess
import tomllib

from . import sexpr
from .paths import BOARDS, ROOT, board_pcb, board_sch, board_zen, build_dir, has_layout, layout_dir
from .tools import kicad_cli, pcb

RULES = ROOT / "rules" / "jlcpcb.kicad_dru"
PDK = ROOT / "rules" / "jlcpcb-pdk.toml"
SEVERITIES = ROOT / "rules" / "kicad-severities.toml"


def _with_severities(project: dict, board_name: str, layout: bool = True) -> dict:
    """The reviewed rule severities, and the board's design-rule constraints that Zener cannot
    set ([design.<board>], written into the project's board.design_settings.rules). A
    schematic-only project takes the ERC severities alone."""
    sev = tomllib.loads(SEVERITIES.read_text())
    project.setdefault("erc", {}).setdefault("rule_severities", {}).update(sev.get("erc", {}))
    if not layout:
        return project
    board = project.setdefault("board", {}).setdefault("design_settings", {})
    board.setdefault("rule_severities", {}).update(sev.get("drc", {}))
    board.setdefault("rules", {}).update(sev.get("design", {}).get(board_name, {}))
    return project


def rules(board: str, check: bool) -> int:
    """Copy the JLCPCB DRC rules next to the project and set the reviewed rule severities in it.
    A schematic-only board gets the ERC severities and no DRC rules."""
    dst = layout_dir(board) / f"{board}.kicad_dru"
    pro = layout_dir(board) / f"{board}.kicad_pro"
    layout = has_layout(board)
    text = pro.read_text()
    want = json.dumps(_with_severities(json.loads(text), board, layout), indent=2) + "\n"
    if check:
        status = 0
        if layout and (not dst.exists() or not filecmp.cmp(RULES, dst, shallow=False)):
            print(f"{dst.relative_to(ROOT)} differs from rules/jlcpcb.kicad_dru: run `micras-pcb rules {board}`")
            status = 1
        if text != want:
            print(f"{pro.relative_to(ROOT)} differs from rules/kicad-severities.toml: run `micras-pcb rules`")
            status = 1
        return status
    if layout:
        shutil.copyfile(RULES, dst)
    if text != want:
        pro.write_text(want)
    return 0


def _violations(report: dict) -> list[dict]:
    items = list(report.get("violations", []))
    items += report.get("unconnected_items", [])
    items += [dict(v, type=v.get("type", "parity")) for v in report.get("schematic_parity", [])]
    for sheet in report.get("sheets", []):
        items += sheet.get("violations", [])
    return [v for v in items if not v.get("excluded")]


def _print(kind: str, board: str, items: list[dict]) -> None:
    for v in items:
        where = "; ".join(i.get("description", "") for i in v.get("items", []))
        print(f"  {kind} {v.get('severity', '?'):7} {v.get('type', '?')}: {v.get('description', '')}  [{where}]")
    summary = "clean" if not items else f"{len(items)} violation(s)"
    print(f"{board}: {kind} {summary}")


def external_supplies(board: str) -> dict[str, str]:
    """Nets a board declares as supplied from off the board: {net: where the supply comes from}.

    KiCad reports a power input with no power output on its net (power_pin_not_driven); a
    hand-drawn schematic silences it with a PWR_FLAG symbol, which Zener cannot place (a Zener
    part needs a footprint, and a net symbol must be a power input). boards/<board>/erc.toml
    plays that role instead, as reviewed source:

        [external_supply]
        VBAT = "3S LiPo battery on J1 pin 1"

        [passive_supply]      # supplied on the board through a part KiCad does not count as a source
        VDDA = "3V3 through the ferrite bead FB1"

    Only power_pin_not_driven on a listed net is accepted; every other violation still fails.
    """
    path = BOARDS / board / "erc.toml"
    if not path.is_file():
        return {}
    raw = tomllib.loads(path.read_text())
    unknown = set(raw) - {"external_supply", "passive_supply"}
    if unknown:
        raise ValueError(f"{path.relative_to(ROOT)}: unknown tables {sorted(unknown)}")
    return {**raw.get("external_supply", {}), **raw.get("passive_supply", {})}


def _item_net(item: dict, power_symbols: dict[str, str], nl) -> str | None:
    """The net of an ERC item "Symbol <ref> Pin <n> [...]": a power symbol's value, or the pin's net."""
    m = re.match(r"Symbol (\S+) Pin (\S+)", item.get("description", ""))
    if not m:
        return None
    ref, pin = m.groups()
    if ref in power_symbols:
        return power_symbols[ref]
    net = nl.net_of(ref, pin)
    return net.lstrip("/") if net else None


def _accept_external_supplies(board: str, items: list[dict]) -> tuple[list[dict], list[str]]:
    supplies = external_supplies(board)
    if not supplies:
        return items, []
    from . import netlist

    nl = netlist.load(board)
    names = {n.lstrip("/") for n in nl.nets}
    missing = sorted(set(supplies) - names)
    if missing:
        raise ValueError(f"boards/{board}/erc.toml: external_supply names nets the board does not have: {missing}")
    sch = sexpr.parse(board_sch(board).read_text())
    power_symbols = {
        s.prop("Reference"): s.prop("Value")
        for s in sch.children("symbol")
        if (s.prop("Reference") or "").startswith("#")
    }
    kept, accepted = [], []
    for v in items:
        nets = {_item_net(i, power_symbols, nl) for i in v.get("items", [])}
        if v.get("type") == "power_pin_not_driven" and len(nets) == 1 and (net := nets.pop()) in supplies:
            accepted.append(f"  accepted power_pin_not_driven on {net}: supplied by {supplies[net]}")
        else:
            kept.append(v)
    return kept, accepted


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
    items, accepted = _accept_external_supplies(board, _violations(json.loads(out.read_text())))
    for line in accepted:
        print(line)
    _print("ERC", board, items)
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
    _print("DRC", board, items)
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
    return r.returncode
