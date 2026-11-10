"""JLCPCB fabrication and assembly outputs.

The Zener source names each part by MPN and manufacturer; parts/jlc.toml maps the MPN to its LCSC
number, library type (basic/extended) and placement rotation offset. Every BOM line must be
mapped, so an unsourced part fails the build instead of the order.

    micras-pcb fab encoder     # build/encoder/fab/: gerbers + drill zip, BOM and CPL CSVs
    micras-pcb parts           # check parts/jlc.toml covers every board (add --online for stock)

A board with a [panel] in its spec (the wall board, under JLCPCB's 10 x 10 mm assembly minimum) is
ordered as that panel (micras_pcb.panel): its package is the panel's gerbers, BOM and CPL, every
copy's parts named `<ref>_<n>`.

JLCPCB prints paste through every opening of the stencil it makes from the paste gerbers, so pads of
a part the team solders itself (`assembly = "hand"`) would come back with reflowed solder bumps. The
JLCPCB package's paste layers are therefore plotted from a build copy of the board (or panel) whose
hand-assembled footprints carry no paste (`without_paste`); the library footprints and the layout
stay as they are. The hand parts' own paste goes into a separate team-stencil zip, outside the
JLCPCB package, for a stencil the team orders or cuts itself.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import tomllib
import urllib.request
import zipfile
from pathlib import Path

from . import order, panel, sexpr, spec
from .paths import ROOT, SCHEMATIC_ONLY, board_pcb, board_zen, boards, build_dir, has_layout
from .tools import kicad_cli, pcb

PARTS_FILE = ROOT / "parts" / "jlc.toml"
NON_COPPER_LAYERS = ["F.Paste", "B.Paste", "F.Silkscreen", "B.Silkscreen", "F.Mask", "B.Mask", "Edge.Cuts"]
PASTE_LAYERS = ("F.Paste", "B.Paste")
_PASTE = {*PASTE_LAYERS, "*.Paste"}
_FP_GRAPHICS = ("fp_line", "fp_rect", "fp_circle", "fp_arc", "fp_poly", "fp_text", "fp_text_box")
_COPPER = re.compile(r'^\s*\(\d+ "((?:F|B|In\d+)\.Cu)" (?:signal|power|mixed|jumper)\b', re.M)


def copper_layers(board: str | Path) -> list[str]:
    """The board's copper layers from its layer table, top to bottom (F.Cu, In1.Cu, ..., B.Cu).
    `board` is a board name or a .kicad_pcb path (a panel)."""
    text = _pcb(board).read_text()
    found = _COPPER.findall(text[: text.index("(setup")])
    inner = sorted((name for name in found if name.startswith("In")), key=lambda name: int(name[2:-3]))
    return ["F.Cu", *inner, "B.Cu"]


def _pcb(board: str | Path) -> Path:
    return board if isinstance(board, Path) else board_pcb(board)


def gerber_layers(board: str | Path) -> list[str]:
    """Every layer the fab needs: all copper layers (inner planes included), mask, paste, silk, outline."""
    return [*copper_layers(board), *NON_COPPER_LAYERS]


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


def _bom_lines(board: str) -> tuple[list[tuple[dict, dict]], list[str]]:
    """Every fitted BOM line as (row, parts/jlc.toml entry). DNP members stay out (the CPL leaves
    them out too), and a line with no fitted member is dropped."""
    db, lines, errors = parts_db(), [], []
    for line in design_bom(board):
        fitted = [m for m in line["members"] if not m.get("dnp")]
        if not fitted:
            continue
        member = fitted[0]
        designators = [m["designator"] for m in fitted]
        mpn = member.get("mpn")
        entry = db.get(mpn) if mpn else None
        if entry is None:
            errors.append(f"{', '.join(designators)}: MPN {mpn!r} has no entry in parts/jlc.toml")
            continue
        row = {
            "Comment": member.get("value") or mpn,
            "Designator": ",".join(designators),
            "Footprint": member.get("package") or entry.get("package", ""),
            "LCSC Part #": entry["lcsc"],
            "MPN": mpn,
        }
        lines.append((row, entry))
    return lines, errors


def jlc_bom(board: str) -> tuple[list[dict], list[str]]:
    """The assembler's BOM: every fitted part JLCPCB places, one row per BOM line. Parts marked
    `assembly = "hand"` in parts/jlc.toml stay out (`hand_bom`)."""
    lines, errors = _bom_lines(board)
    return [row for row, entry in lines if entry.get("assembly") != "hand"], errors


def hand_bom(board: str) -> list[dict]:
    """The fitted parts the team buys and solders itself (`assembly = "hand"`), with the reason."""
    lines, _ = _bom_lines(board)
    return [{**row, "Why": entry.get("hand_why", "")} for row, entry in lines if entry.get("assembly") == "hand"]


def hand_refs(board: str) -> set[str]:
    """Designators of the fitted parts the team solders itself (`assembly = "hand"`)."""
    return {d for row in hand_bom(board) for d in row["Designator"].split(",") if d}


def without_paste(text: str, drop) -> str:
    """The .kicad_pcb text with no solder paste on the footprints whose reference `drop(ref)` accepts:
    their pads leave the paste layers, and their paste-only pads (a split exposed-pad stencil) and
    paste graphics go. Nothing else changes, so every other layer plots as before."""
    root = sexpr.parse(text)
    edits = []
    for fp in root.children("footprint"):
        if not drop(fp.prop("Reference") or ""):
            continue
        for pad in fp.children("pad"):
            layers = pad.child("layers")
            names = layers.atoms() if layers else []
            if not set(names) & _PASTE:
                continue
            if set(names) <= _PASTE:
                edits.append((*sexpr.line_span(text, pad), ""))
            else:
                kept = " ".join(sexpr.quote(n) for n in names if n not in _PASTE)
                edits.append((layers.start, layers.end, f"(layers {kept})"))
        for g in fp.children():
            layer = g.child("layer") if g.head in _FP_GRAPHICS else None
            if layer and layer.atoms() and layer.atoms()[0] in _PASTE:
                edits.append((*sexpr.line_span(text, g), ""))
    return sexpr.splice(text, edits)


def paste_copy(pcbf: Path, out: Path, drop) -> Path:
    """A copy of the board file `pcbf` in `out`, under its own name (so its gerbers keep their names
    and project id), with no paste on the footprints `drop` accepts (`without_paste`)."""
    out.mkdir(parents=True, exist_ok=True)
    dst = out / pcbf.name
    dst.write_text(without_paste(pcbf.read_text(), drop))
    pro = pcbf.with_suffix(".kicad_pro")
    if pro.is_file():
        shutil.copy(pro, out / pro.name)
    return dst


def plot_layers(pcbf: Path, layers: list[str], out: Path) -> list[Path]:
    """Gerbers of the given layers of `pcbf` into `out`, relative to the drill origin."""
    out.mkdir(parents=True, exist_ok=True)
    before = set(out.iterdir())
    subprocess.run(
        [
            kicad_cli(),
            "pcb",
            "export",
            "gerbers",
            "-l",
            ",".join(layers),
            "--use-drill-file-origin",
            "-o",
            str(out),
            str(pcbf),
        ],
        check=True,
        capture_output=True,
    )
    return sorted(f for f in out.iterdir() if f not in before and f.suffix != ".gbrjob")


def team_stencil(board: str, out: Path, hand: set[str]) -> Path | None:
    """The hand parts' paste, both faces, with the outline to align it, zipped into
    out/<board>-team-stencil.zip: the stencil the team orders or cuts for the parts it solders.
    None when no hand part has paste. `hand`: the hand parts' designators (hand_refs)."""
    work = out / "team-stencil"
    shutil.rmtree(work, ignore_errors=True)
    copy = paste_copy(board_pcb(board), work / "board", lambda ref: ref not in hand)
    files = plot_layers(copy, [*PASTE_LAYERS, "Edge.Cuts"], work / "gerbers")
    if not any(_gerber_has_apertures(f) for f in files if "Paste" in f.name):
        shutil.rmtree(work, ignore_errors=True)
        return None
    zpath = out / f"{board}-team-stencil.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.name.replace(f"{board}-", f"{board}-team-", 1))
    shutil.rmtree(work / "board", ignore_errors=True)
    return zpath


def _gerber_has_apertures(path: Path) -> bool:
    """The gerber draws something: a flash, a stroke or a region."""
    return bool(re.search(r"D0?[123]\*|G36\*", path.read_text()))


def rotation_offsets(board: str) -> dict[str, float]:
    db = parts_db()
    return {
        d: float(db[m["mpn"]].get("rotation", 0))
        for line in design_bom(board)
        for m in line["members"]
        if m.get("mpn") in db
        for d in [m["designator"]]
    }


def positions(board: str | Path, out: Path) -> list[dict]:
    """KiCad's placement of the board's (or panel's) fitted parts, relative to the drill origin."""
    raw = out / f"{_pcb(board).stem}-pos.csv"
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
            str(_pcb(board)),
        ],
        check=True,
        capture_output=True,
    )
    with raw.open() as f:
        rows = list(csv.DictReader(f))
    raw.unlink()
    return rows


def jlc_rotation(kicad_rot: float, offset: float, bottom: bool) -> float:
    """The CPL rotation JLCPCB needs for a part KiCad places at `kicad_rot` (its position export:
    counterclockwise seen from the top, on either side) with the part's offset (parts/jlc.toml, the
    turn from the LCSC footprint's zero to KiCad's, seen from the top).

    Top: the two add. Bottom: JLCPCB mirrors the LCSC footprint and turns it counterclockwise as
    seen from the bottom, so a part KiCad leaves at 0 needs 180, and KiCad's turn (and the offset,
    a turn in the footprint's own frame) counts the other way. Checked in JLCPCB's placement preview
    on 2026-11-08 with the wall panel: Q1 (AO3400A) and D1 (1N4148WS) at 0 sat 180 off their pads
    and at 180 on them, and at 90 they turned counterclockwise in the bottom view."""
    return ((180 - kicad_rot - offset) if bottom else (kicad_rot + offset)) % 360


def cpl_rows(board: str, out: Path, bom_refs: set[str], pcb_file: Path | None = None) -> list[dict]:
    """Placement for the parts JLC assembles: KiCad's position and rotation with the part's rotation
    offset (parts/jlc.toml), as jlc_rotation turns them for each side. Board features such as the
    encoder tab are not in the BOM. With `pcb_file` (the board's panel), every copy's parts,
    `<ref>_<n>`, each with its part's offset."""
    offsets = rotation_offsets(board)
    rows = []
    for r in positions(pcb_file or board, out):
        ref = r["Ref"]
        part = ref
        if pcb_file is not None:
            copy = panel.split_ref(ref)
            part = copy[0] if copy else ""
        if part not in bom_refs:
            continue
        rot = jlc_rotation(float(r["Rot"]), offsets.get(part, 0.0), r["Side"].lower() != "top")
        rows.append(
            {
                "Designator": ref,
                "Mid X": f"{float(r['PosX']):.4f}mm",
                "Mid Y": f"{float(r['PosY']):.4f}mm",
                "Layer": "Top" if r["Side"].lower() == "top" else "Bottom",
                "Rotation": f"{rot:g}",
            }
        )
    return rows


def cpl(board: str, out: Path, bom_refs: set[str]) -> Path:
    """The board's CPL file (cpl_rows)."""
    path = out / f"{board}-cpl-jlcpcb.csv"
    _write_csv(path, cpl_rows(board, out, bom_refs), CPL_COLUMNS)
    return path


def gerbers(board: str | Path, out: Path, hand: set[str] = frozenset()) -> Path:
    """Gerbers and Excellon drills of the board (or panel) zipped into out/<name>-gerbers.zip. The
    paste layers leave out the footprints named in `hand` (the parts the team solders itself)."""
    g = out / "gerbers"
    shutil.rmtree(g, ignore_errors=True)
    g.mkdir(parents=True)
    pcbf = str(_pcb(board))
    subprocess.run(
        [
            kicad_cli(),
            "pcb",
            "export",
            "gerbers",
            "-l",
            ",".join(gerber_layers(board)),
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
    if hand:
        copy = paste_copy(Path(pcbf), out / "jlc-paste" / "board", lambda ref: ref in hand)
        for f in plot_layers(copy, list(PASTE_LAYERS), out / "jlc-paste" / "gerbers"):
            shutil.move(f, g / f.name)
        shutil.rmtree(out / "jlc-paste")
    zpath = out / f"{_pcb(board).stem}-gerbers.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(g.iterdir()):
            z.write(f, f.name)
    return zpath


BOM_COLUMNS = ["Comment", "Designator", "Footprint", "LCSC Part #", "MPN"]
CPL_COLUMNS = ["Designator", "Mid X", "Mid Y", "Layer", "Rotation"]


def panel_package(board: str, out: Path, rows: list[dict], refs: set[str], hand: set[str]) -> list[Path]:
    """The panel's gerbers, BOM and CPL: every BOM line's parts on each of the panel's boards, and no
    paste on any copy of the hand parts (`hand`)."""
    n = panel.settings(board)["columns"]
    pcbf = panel.build(board, out / "panel")
    bom = out / f"{board}-panel-bom-jlcpcb.csv"
    copies = [
        {
            **row,
            "Designator": ",".join(panel.copy_ref(d, k) for d in row["Designator"].split(",") for k in range(n)),
        }
        for row in rows
    ]
    _write_csv(bom, copies, BOM_COLUMNS)
    placed = cpl_rows(board, out, refs, pcbf)
    want = sorted(panel.copy_ref(d, k) for d in refs for k in range(n))
    got = sorted(r["Designator"] for r in placed)
    if got != want:
        raise RuntimeError(f"{board}: the panel places {got}, its BOM {want}")
    cpl = out / f"{board}-panel-cpl-jlcpcb.csv"
    _write_csv(cpl, placed, CPL_COLUMNS)
    copies_hand = {panel.copy_ref(d, k) for d in hand for k in range(n)}
    return [gerbers(pcbf, out, copies_hand), bom, cpl]


def fab(board: str) -> int:
    out = build_dir(board) / "fab"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    rows, errors = jlc_bom(board)
    if errors:
        print("BOM has unsourced parts:\n  " + "\n  ".join(errors))
        return 1
    if not has_layout(board):
        bom = out / f"{board}-bom-jlcpcb.csv"
        _write_csv(bom, rows, BOM_COLUMNS)
        print(f"  {bom.relative_to(ROOT)}")
        print(f"{board}: gerbers and CPL skipped: {SCHEMATIC_ONLY}")
        return 0
    packages = {r["Ref"]: r["Package"] for r in positions(board, out)}
    for row in rows:
        row["Footprint"] = row["Footprint"] or packages.get(row["Designator"].split(",")[0], "")
    refs = {d for row in rows for d in row["Designator"].split(",")}
    hand_rows = hand_bom(board)
    hand_set = {d for row in hand_rows for d in row["Designator"].split(",") if d}
    for row in hand_rows:
        row["Footprint"] = row["Footprint"] or packages.get(row["Designator"].split(",")[0], "")
    hand = out / f"{board}-hand-assembly.csv"
    _write_csv(hand, hand_rows, [*BOM_COLUMNS, "Why"])
    if panel.settings(board):
        produced = [*panel_package(board, out, rows, refs, hand_set), hand]
    else:
        bom = out / f"{board}-bom-jlcpcb.csv"
        _write_csv(bom, rows, BOM_COLUMNS)
        produced = [gerbers(board, out, hand_set), bom, cpl(board, out, refs), hand]
    stencil = team_stencil(board, out, hand_set)
    if stencil:
        produced.append(stencil)
    form = out / f"{board}-order.txt"
    form.write_text(order.form(board))
    produced.append(form)
    unverified = [
        m for m, e in parts_db().items() if not e.get("rotation_verified") and any(m == r["MPN"] for r in rows)
    ]
    for p in produced:
        print(f"  {p.relative_to(ROOT)}")
    if spec.load(board)["pcb"]["assembly"] == "none":
        print(f"note: {board} is not ordered with JLCPCB assembly (spec/{board}.toml pcb.assembly)")
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
