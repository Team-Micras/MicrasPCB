"""Transfer the previous encoder board's placement, routing, zones, outline and silkscreen onto boards/encoder.

    python3 boards/encoder/previous/transfer_layout.py [--previous PATH] [--no-sync]

Reads the previous revision (default: $MICRAS_PREVIOUS/modules/encoder/MicrasEncoder.PcbDoc, else
../hw_debug/modules/encoder/MicrasEncoder.PcbDoc, converted with `kicad-cli pcb import`; PATH may
also be a .kicad_pcb conversion of it) and the generated layout
boards/encoder/layout/encoder.kicad_pcb, and rewrites the layout:

1. Copper and board graphics (text, span-preserving: micras_pcb.sexpr). Every track, via, zone and
   board-level graphic (the Edge.Cuts outline, the silkscreen texts and the bottom-side logo) is
   copied byte for byte. The board keeps the previous net names, so every net stays as it was
   (checked by pad membership, see `check_nets`). Each copied item gets a UUID derived from its
   content, since the Altium import draws new random ones on every run. Teardrops become plain
   zones of the same outline, as on the main board (boards/main/previous/transfer_layout.py
   `teardrop_to_zone`: KiCad does not save a teardrop's UUID, so a board with teardrop zones is
   never byte-stable). The pours keep the Altium neck widths (`POUR_MIN_WIDTH`). The Edge.Cuts
   line shorter than 1 um is left out (`outline_snaps`), and the board-level STEP files no
   footprint uses are dropped (`drop_unused_models`).
2. Placement (KiCad's pcbnew module, KiCad 10). IC1 and J1 use the previous footprints (same pads)
   and go where spec/encoder.toml puts them, locked, as `micras-pcb mech encoder` does: the
   previous positions, with IC1 0.04 um left, on the tab centre line. C1, a KiCad library 0603,
   is fitted so its pads land on the previous pad centres by pad number (the least-squares
   translation for each candidate rotation, the smallest residual wins). Each reference
   designator text takes the previous one's position, size, layer and orientation. The aux and
   grid origins are the spec's (the previous board's), the solder mask expansion the previous
   board's (0.02 mm). Zones are refilled.
3. `pcb layout` syncs the result, which normalises the file the way `make gen` writes it.

The script is a fixed point: running it on its own output changes nothing. Run `make gen` and
`make check` afterwards.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import re
import subprocess
import sys
import tempfile
import uuid
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))

from micras_pcb import mech, previous, sexpr, spec  # noqa: E402

BOARD = "encoder"
LAYOUT = ROOT / "boards/encoder/layout/encoder.kicad_pcb"
OLD_PCB = previous.SOURCES[BOARD].pcb

# Top-level items copied from the previous board (everything that is not a footprint).
COPIED = {
    "segment",
    "arc",
    "via",
    "zone",
    "gr_line",
    "gr_arc",
    "gr_circle",
    "gr_rect",
    "gr_poly",
    "gr_curve",
    "gr_text",
    "gr_text_box",
    "dimension",
    "target",
}
UUID = re.compile(r'\(uuid "[0-9a-f-]+"\)')
_NS = uuid.UUID("9d3c2a51-7e0b-4f6d-8a24-5c1e9b7f0d63")


def previous_text(arg: Path | None) -> str:
    if arg is None:
        env = os.environ.get("MICRAS_PREVIOUS")
        arg = (Path(env).expanduser() if env else ROOT.parent / "hw_debug") / OLD_PCB
    return previous.altium_pcb(arg) if arg.suffix.lower() == ".pcbdoc" else arg.read_text()


def pad_nets(root: sexpr.Node) -> dict[tuple[str, str], str | None]:
    out = {}
    for fp in root.children("footprint"):
        ref = fp.prop("Reference") or ""
        for pad in fp.children("pad"):
            net = pad.child("net")
            out[(ref, pad.atoms()[0])] = net.atoms()[-1] if net is not None else None
    return out


def check_nets(old_root: sexpr.Node, new_root: sexpr.Node) -> None:
    """Every previous net is the new net of the same name, pad for pad (the copper keeps its nets)."""
    old, new = pad_nets(old_root), pad_nets(new_root)
    votes: dict[str, Counter] = defaultdict(Counter)
    for pad, net in old.items():
        if net is not None:
            votes[net][new.get(pad)] += 1
    wrong = {o: dict(c) for o, c in votes.items() if set(c) != {o}}
    if wrong:
        raise SystemExit(f"previous nets land on other new nets: {wrong}")


TEARDROP = "\t\t(attr\n\t\t\t(teardrop\n\t\t\t\t(type track_end)\n\t\t\t)\n\t\t)\n"
TEARDROP_PADS = "\t\t(connect_pads\n\t\t\t(clearance 0.5)\n\t\t)\n"
ZONE_PADS = "\t\t(connect_pads yes\n\t\t\t(clearance 0.1)\n\t\t)\n"
# The importer gives every zone a 0.25 mm minimum width, which erases most of a teardrop's thin
# flare when the zone is filled. A teardrop fills with 0.1 mm instead, JLCPCB's minimum copper
# feature (rules/jlcpcb-pdk.toml jlc.copper.minimum_feature_width: 0.10 mm on 2 layers, 0.09 mm
# on 4): its body is kept, only the cusps the fab cannot etch go.
MIN_WIDTH = "\t\t(min_thickness 0.25)\n"
TEARDROP_MIN_WIDTH = "\t\t(min_thickness 0.1)\n"
# The pours drop copper narrower than their Altium polygon's neck width (MicrasEncoder.PcbDoc
# Polygons6: REMOVENECKS with NECKWIDTHTHRESHOLD 3.937 mil = 0.1 mm on the top pour, 15.748 mil
# = 0.4 mm on the bottom pour); the importer sets KiCad's 0.25 mm instead. Keyed by layer and the
# imported priority (2 - Altium POURINDEX).
POUR_MIN_WIDTH = {("F.Cu", 1): 0.1, ("B.Cu", 0): 0.4}
TEARDROP_PRIORITY = 100  # above both pours of the previous board (priorities 0 and 1), as a teardrop is


def teardrop_to_zone(text: str, uid: uuid.UUID, priority: int) -> str:
    """A teardrop zone as a plain copper zone of the same outline and net: connected solidly to its
    pad and track (connect_pads yes, the pours' 0.1 mm clearance), filled with a 0.1 mm
    minimum width, winning over the pours around it (KiCad requires distinct priorities
    for intersecting zones)."""
    if TEARDROP_PADS not in text or MIN_WIDTH not in text:
        raise SystemExit("teardrop zone with unexpected pad connection or width settings")
    text = text.replace(TEARDROP, "").replace(TEARDROP_PADS, ZONE_PADS).replace(MIN_WIDTH, TEARDROP_MIN_WIDTH)
    head, layer, rest = text.partition("\t\t(layer ")
    line, nl, tail = rest.partition("\n")
    return f'{head}{layer}{line}{nl}\t\t(uuid "{uid}")\n\t\t(priority {priority})\n{tail}'


def pour_min_width(text: str) -> str:
    """A pour with the minimum width of its Altium polygon (see POUR_MIN_WIDTH)."""
    layer = re.search(r'^\t\t\(layer "([^"]+)"\)', text, re.M).group(1)
    priority = re.search(r"^\t\t\(priority (\d+)\)", text, re.M)
    width = POUR_MIN_WIDTH[(layer, int(priority.group(1)) if priority else 0)]
    if MIN_WIDTH not in text:
        raise SystemExit("pour with unexpected minimum width settings")
    return text.replace(MIN_WIDTH, f"\t\t(min_thickness {width:g})\n")


def _edge(node: sexpr.Node) -> bool:
    layer = node.child("layer")
    return node.head.startswith("gr_") and layer is not None and layer.atoms() == ["Edge.Cuts"]


def degenerate_edge(node: sexpr.Node) -> bool:
    """An Edge.Cuts line shorter than 1 um: a duplicated outline vertex of the Altium board, which
    KiCad reports as a malformed outline (see `outline_snaps`)."""
    if node.head != "gr_line" or not _edge(node):
        return False
    (x0, y0), (x1, y1) = (map(float, node.child(k).atoms()[:2]) for k in ("start", "end"))
    return math.hypot(x1 - x0, y1 - y0) < 1e-3


def outline_snaps(root: sexpr.Node) -> dict[str, str]:
    """The degenerate Edge.Cuts lines are left out; the outline item that met one at its end meets
    the next item at the line's start instead (a move below 1 um), so the outline stays closed."""
    snaps = {}
    for n in root.children():
        if degenerate_edge(n):
            snaps[" ".join(n.child("end").atoms()[:2])] = " ".join(n.child("start").atoms()[:2])
    for b, a in snaps.items():
        while a in snaps and snaps[a] != b:
            a = snaps[a]
        snaps[b] = a
    return snaps


def snap_outline(text: str, node: sexpr.Node, snaps: dict[str, str]) -> str:
    """An Edge.Cuts item with its endpoints moved as `outline_snaps` says."""
    if not _edge(node):
        return text
    for b, a in snaps.items():
        text = text.replace(f"(start {b})", f"(start {a})").replace(f"(end {b})", f"(end {a})")
    return text


def copy_items(old_text: str, new_text: str) -> str:
    """The new layout with the previous board's copper and board graphics in place of its own."""
    old_root, new_root = sexpr.parse(old_text), sexpr.parse(new_text)
    check_nets(old_root, new_root)
    # drop what the generated layout or an earlier run holds
    edits = [(*sexpr.line_span(new_text, n), "") for n in new_root.children() if n.head in COPIED]
    items = []
    snaps = outline_snaps(old_root)
    for n in old_root.children():
        if n.head in COPIED and not degenerate_edge(n):
            a, b = sexpr.line_span(old_text, n)
            text = snap_outline(old_text[a:b], n, snaps)
            body = UUID.sub("", text)
            items.append((hashlib.sha256(body.encode()).hexdigest(), text))
    items.sort()
    seen: Counter = Counter()
    copied, teardrops = [], 0
    for digest, text in items:
        uid = uuid.uuid5(_NS, f"{digest}/{seen[digest]}")
        seen[digest] += 1
        if text.lstrip().startswith("(zone") and TEARDROP in text:
            text = teardrop_to_zone(text, uid, TEARDROP_PRIORITY + teardrops)
            teardrops += 1
        elif UUID.search(text):
            text = UUID.sub(f'(uuid "{uid}")', text, count=1)
            if text.lstrip().startswith("(zone"):
                text = pour_min_width(text)
        else:
            raise SystemExit(f"copied item without a UUID: {text[:80]}")
        copied.append(text)
    anchor = new_root.child("embedded_fonts") or new_root.children()[-1]
    at = sexpr.line_span(new_text, anchor)[0]
    edits.append((at, at, "".join(copied)))
    return sexpr.splice(new_text, edits)


def drop_unused_models(text: str) -> str:
    """The layout without board-level embedded files that no footprint model uses (a STEP left
    behind by an earlier footprint of IC1)."""
    root = sexpr.parse(text)
    used = set(re.findall(r'\(model "kicad-embed://([^"]+)"', text))
    files = root.child("embedded_files")
    if files is None:
        return text
    drop = [f for f in files.children("file") if f.child("name").atoms()[0] not in used]
    return sexpr.splice(text, [(*sexpr.line_span(text, f), "") for f in drop])


# ---------------------------------------------------------------------------------------------
# placement (pcbnew)


def _centres(fp) -> dict[str, list[tuple[float, float]]]:
    import pcbnew

    out = defaultdict(list)
    for p in fp.Pads():
        c = p.GetBoundingBox().GetCenter()
        out[p.GetNumber()].append((pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)))
    return out


def _residual(fp, target: dict[str, list[tuple[float, float]]]) -> tuple[float, float, float]:
    """Least-squares translation (dx, dy) moving fp's pad centres onto target, and the rms residual."""
    have = _centres(fp)
    if set(have) != set(target):
        return math.inf, 0.0, 0.0
    pairs = [pair for num, pts in target.items() for pair in zip(sorted(have[num]), sorted(pts), strict=True)]
    dx = sum(b[0] - a[0] for a, b in pairs) / len(pairs)
    dy = sum(b[1] - a[1] for a, b in pairs) / len(pairs)
    rms = math.sqrt(sum((a[0] + dx - b[0]) ** 2 + (a[1] + dy - b[1]) ** 2 for a, b in pairs) / len(pairs))
    return rms, dx, dy


def place(path: Path, old_path: Path) -> list[str]:
    import pcbnew

    old = pcbnew.LoadBoard(str(old_path))
    new = pcbnew.LoadBoard(str(path))
    by_ref = {fp.GetReference(): fp for fp in old.GetFootprints()}
    s = spec.load(BOARD)
    spec_placed = {p["path"].split(".")[0]: (mech._place_xy(s, p), p["rotation"]) for p in mech.placements(s).values()}
    report = []
    for fp in new.GetFootprints():
        ref = fp.GetReference()
        src = by_ref[ref]
        if fp.IsFlipped() != src.IsFlipped():
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        target = _centres(src)
        fp.SetOrientation(src.GetOrientation())
        fp.SetPosition(src.GetPosition())
        rms = _residual(fp, target)[0]
        if rms > 1e-4:
            # a generic footprint: fit position and rotation to the old pads
            old_rot = src.GetOrientation().AsDegrees()
            best = None
            for ang in sorted({(old_rot + 90 * k) % 360 for k in range(4)}):
                fp.SetPosition(pcbnew.VECTOR2I(0, 0))
                fp.SetOrientation(pcbnew.EDA_ANGLE(ang, pcbnew.DEGREES_T))
                r, dx, dy = _residual(fp, target)
                if best is None or r < best[0] - 1e-9:
                    best = (r, ang, dx, dy)
            r, ang, dx, dy = best
            if not math.isfinite(r):
                raise SystemExit(f"{ref}: no rotation fits its pads onto the previous footprint's")
            fp.SetOrientation(pcbnew.EDA_ANGLE(ang, pcbnew.DEGREES_T))
            fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(round(dx, 6)), pcbnew.FromMM(round(dy, 6))))
            rms = _residual(fp, target)[0]
            report.append(f"{ref}: fitted at rotation {ang:g}, pad residual {rms * 1000:.1f} um rms")
        # reference designator text as on the previous board
        nf, of = fp.Reference(), src.Reference()
        nf.SetLayer(of.GetLayer())
        nf.SetAttributes(of)
        nf.SetPosition(of.GetPosition())
        nf.SetVisible(of.IsVisible() and bool(of.GetText()))
        if ref in spec_placed:
            # spec/encoder.toml owns the sensor and the tab (`micras-pcb mech encoder` writes them the same way)
            (x, y), rot = spec_placed[ref]
            if abs(rot - fp.GetOrientation().AsDegrees()) % 360 > 1e-6:
                raise SystemExit(f"{ref}: spec rotation {rot}, previous board {fp.GetOrientation().AsDegrees()}")
            moved = pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)) - fp.GetPosition()
            fp.SetPosition(fp.GetPosition() + moved)
            fp.SetLocked(True)
            report.append(
                f"{ref}: spec position, {math.hypot(*(pcbnew.ToMM(v) for v in (moved.x, moved.y))) * 1e3:.2f} um from the previous one"
            )
    ds = new.GetDesignSettings()
    k = s["kicad"]
    origin = pcbnew.VECTOR2I(pcbnew.FromMM(k["aux_origin_x"]), pcbnew.FromMM(k["aux_origin_y"]))
    ds.SetAuxOrigin(origin)
    ds.SetGridOrigin(origin)
    ds.m_SolderMaskExpansion = old.GetDesignSettings().m_SolderMaskExpansion
    pcbnew.ZONE_FILLER(new).Fill(new.Zones())
    pcbnew.SaveBoard(str(path), new)
    return report


def pcb_layout(*flags: str) -> None:
    """`pcb layout` on the board with the pinned toolchain (versions.env)."""
    env = dict(
        line.split("=", 1)
        for line in (ROOT / "versions.env").read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    subprocess.run(
        ["pcb", f"+{env['PCB_TOOLCHAIN'].strip()}", "layout", *flags, "--no-open", "boards/encoder/encoder.zen"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--previous", type=Path, help="the previous board: MicrasEncoder.PcbDoc or a .kicad_pcb conversion")
    ap.add_argument("--no-sync", action="store_true", help="skip the final `pcb layout` sync")
    a = ap.parse_args()
    old_text = previous_text(a.previous)
    LAYOUT.write_text(drop_unused_models(copy_items(old_text, LAYOUT.read_text())))
    with tempfile.TemporaryDirectory() as tmp:
        old_path = Path(tmp) / "previous.kicad_pcb"
        old_path.write_text(old_text)
        for line in place(LAYOUT, old_path):
            print(line)
    if not a.no_sync:
        pcb_layout()
    return 0


if __name__ == "__main__":
    sys.exit(main())
