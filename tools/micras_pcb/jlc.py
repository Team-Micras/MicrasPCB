"""JLCPCB fabrication and assembly outputs.

The Zener source names each part by MPN and manufacturer; parts/jlc.toml maps the MPN to its LCSC
number, library type (basic/extended) and placement rotation offset. Every BOM line must be
mapped, so an unsourced part fails the build instead of the order.

    micras-pcb fab encoder     # build/encoder/fab/: gerbers + drill zip, BOM and CPL CSVs
    micras-pcb parts           # check parts/jlc.toml covers every board (add --online for stock)
"""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import tomllib
import urllib.request
import zipfile
from pathlib import Path

from .paths import ROOT, SCHEMATIC_ONLY, board_pcb, board_zen, boards, build_dir, has_layout
from .tools import kicad_cli, pcb

PARTS_FILE = ROOT / "parts" / "jlc.toml"
GERBER_LAYERS = ["F.Cu", "B.Cu", "F.Paste", "B.Paste", "F.Silkscreen", "B.Silkscreen", "F.Mask", "B.Mask", "Edge.Cuts"]


def parts_db() -> dict[str, dict]:
    return tomllib.loads(PARTS_FILE.read_text())["parts"]


def design_bom(board: str) -> list[dict]:
    """The board's BOM as Zener resolves it: one entry per distinct part."""
    out = subprocess.run(
        [*pcb(), "bom", str(board_zen(board)), "-f", "json", "--offline"],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return json.loads(out.stdout)


def jlc_bom(board: str) -> tuple[list[dict], list[str]]:
    db, rows, errors = parts_db(), [], []
    for line in design_bom(board):
        member = line["members"][0]
        mpn = member.get("mpn")
        entry = db.get(mpn) if mpn else None
        if entry is None:
            errors.append(f"{', '.join(line['designators'])}: MPN {mpn!r} has no entry in parts/jlc.toml")
            continue
        rows.append(
            {
                "Comment": member.get("value") or mpn,
                "Designator": ",".join(line["designators"]),
                "Footprint": member.get("package") or entry.get("package", ""),
                "LCSC Part #": entry["lcsc"],
                "MPN": mpn,
            }
        )
    return rows, errors


def rotation_offsets(board: str) -> dict[str, float]:
    db = parts_db()
    return {
        d: float(db[m["mpn"]].get("rotation", 0))
        for line in design_bom(board)
        for m in line["members"]
        if m.get("mpn") in db
        for d in [m["designator"]]
    }


def positions(board: str, out: Path) -> list[dict]:
    raw = out / f"{board}-pos.csv"
    subprocess.run(
        [
            kicad_cli(),
            "pcb",
            "export",
            "pos",
            "--format",
            "csv",
            "--units",
            "mm",
            "--side",
            "both",
            "--use-drill-file-origin",
            "--exclude-dnp",
            "-o",
            str(raw),
            str(board_pcb(board)),
        ],
        check=True,
        capture_output=True,
    )
    with raw.open() as f:
        rows = list(csv.DictReader(f))
    raw.unlink()
    return rows


def cpl(board: str, out: Path, bom_refs: set[str]) -> Path:
    """Placement for the parts JLC assembles; board features such as the encoder tab are not in the BOM."""
    offsets = rotation_offsets(board)
    rows = []
    for r in positions(board, out):
        ref = r["Ref"]
        if ref not in bom_refs:
            continue
        rot = (float(r["Rot"]) + offsets.get(ref, 0.0)) % 360
        rows.append(
            {
                "Designator": ref,
                "Mid X": f"{float(r['PosX']):.4f}mm",
                "Mid Y": f"{float(r['PosY']):.4f}mm",
                "Layer": "Top" if r["Side"].lower() == "top" else "Bottom",
                "Rotation": f"{rot:g}",
            }
        )
    path = out / f"{board}-cpl-jlcpcb.csv"
    _write_csv(path, rows, ["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    return path


def gerbers(board: str, out: Path) -> Path:
    g = out / "gerbers"
    shutil.rmtree(g, ignore_errors=True)
    g.mkdir(parents=True)
    pcbf = str(board_pcb(board))
    subprocess.run(
        [
            kicad_cli(),
            "pcb",
            "export",
            "gerbers",
            "-l",
            ",".join(GERBER_LAYERS),
            "--subtract-soldermask",
            "--use-drill-file-origin",
            "--check-zones",
            "-o",
            str(g),
            pcbf,
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            kicad_cli(),
            "pcb",
            "export",
            "drill",
            "--format",
            "excellon",
            "--drill-origin",
            "plot",
            "--excellon-separate-th",
            "--generate-map",
            "--map-format",
            "gerberx2",
            "-o",
            str(g) + "/",
            pcbf,
        ],
        check=True,
        capture_output=True,
    )
    zpath = out / f"{board}-gerbers.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(g.iterdir()):
            z.write(f, f.name)
    return zpath


def fab(board: str) -> int:
    out = build_dir(board) / "fab"
    out.mkdir(parents=True, exist_ok=True)
    rows, errors = jlc_bom(board)
    if errors:
        print("BOM has unsourced parts:\n  " + "\n  ".join(errors))
        return 1
    if not has_layout(board):
        bom = out / f"{board}-bom-jlcpcb.csv"
        _write_csv(bom, rows, ["Comment", "Designator", "Footprint", "LCSC Part #", "MPN"])
        print(f"  {bom.relative_to(ROOT)}")
        print(f"{board}: gerbers and CPL skipped: {SCHEMATIC_ONLY}")
        return 0
    packages = {r["Ref"]: r["Package"] for r in positions(board, out)}
    for row in rows:
        row["Footprint"] = row["Footprint"] or packages.get(row["Designator"].split(",")[0], "")
    bom = out / f"{board}-bom-jlcpcb.csv"
    _write_csv(bom, rows, ["Comment", "Designator", "Footprint", "LCSC Part #", "MPN"])
    refs = {d for row in rows for d in row["Designator"].split(",")}
    produced = [gerbers(board, out), bom, cpl(board, out, refs)]
    unverified = [
        m for m, e in parts_db().items() if not e.get("rotation_verified") and any(m == r["MPN"] for r in rows)
    ]
    for p in produced:
        print(f"  {p.relative_to(ROOT)}")
    if unverified:
        print(f"note: placement rotation not yet verified in JLC's preview for: {', '.join(unverified)}")
    return 0


def check_parts(online: bool) -> int:
    """Every MPN on every board is mapped; with online, also report JLC stock and library type."""
    db, status = parts_db(), 0
    used = {}
    for b in boards():
        for line in design_bom(b):
            for m in line["members"]:
                used.setdefault(m.get("mpn"), []).append(f"{b}:{m['designator']}")
    for mpn, where in sorted(used.items(), key=lambda kv: str(kv[0])):
        if mpn not in db:
            print(f"MISSING  {mpn!r} used by {', '.join(where)}: add it to parts/jlc.toml")
            status = 1
    for mpn in sorted(set(db) - set(used)):
        print(f"unused   {mpn} ({db[mpn]['lcsc']})")
    if online:
        for mpn in sorted(m for m in used if m in db):
            e = db[mpn]
            info = jlc_lookup(e["lcsc"])
            if info is None:
                print(f"UNKNOWN  {mpn} {e['lcsc']}: JLC search returned nothing")
                status = 1
                continue
            kind = "basic" if info["type"] == "base" else "extended"
            flag = "ok      " if info["stock"] > 0 else "NO STOCK"
            if kind != e.get("type"):
                flag = "TYPE    "
                status = 1
            # Zero stock is information, not a failure: some parts are bought elsewhere and consigned.
            print(f"{flag} {mpn} {e['lcsc']}: {kind}, {info['stock']} in stock, ${info['price']:.4f} (1 pc)")
    if status == 0:
        print(f"parts/jlc.toml covers {len(used)} part(s) on {len(boards())} board(s)")
    return status


def jlc_lookup(lcsc: str) -> dict | None:
    """Stock, price and library type from JLCPCB's public parts search.

    This is the endpoint jlcpcb.com/parts uses: undocumented and unauthenticated, so it can change
    without notice. A failure here should not block a design change, only `make parts-online`.
    """
    req = urllib.request.Request(
        "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList",
        data=json.dumps({"keyword": lcsc, "currentPage": 1, "pageSize": 5}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "micras-pcb"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    for c in (data.get("data") or {}).get("componentPageInfo", {}).get("list") or []:
        if c.get("componentCode") == lcsc or lcsc in (c.get("lcscGoodsUrl") or ""):
            prices = c.get("componentPrices") or [{}]
            return {
                "stock": c.get("stockCount", 0),
                "type": c.get("componentLibraryType"),
                "price": prices[0].get("productPrice", 0.0),
            }
    return None


def _write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
