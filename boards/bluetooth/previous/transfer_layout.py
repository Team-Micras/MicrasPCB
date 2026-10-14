"""Transfer the previous Bluetooth module's placement, routing, zones, outline and art onto boards/bluetooth.

    python3 boards/bluetooth/previous/transfer_layout.py [--previous PATH] [--no-sync]

Reads the previous revision (default: $MICRAS_PREVIOUS/modules/bluetooth/MicrasBluetoothModule.PcbDoc,
else ../hw_debug/...), converts it with `kicad-cli pcb import --format altium` into a temporary
directory (as `micras-pcb previous snapshot bluetooth` does), and rewrites the generated
layout boards/bluetooth/layout/bluetooth.kicad_pcb:

1. Copper and board graphics (text, span-preserving: micras_pcb.sexpr). Every track, via, zone
   and board-level graphic (the Edge.Cuts outline, the bottom silkscreen logo) is copied as text,
   with its net renamed to the new net that owns the pads the old net connected (found by pad
   membership, see `net_map`), a UUID derived from its content, and zones without their fill.
   The teardrops become plain zones (`teardrop_to_zone`), the pours keep the Altium neck widths
   (`POUR_MIN_WIDTH`), and the Edge.Cuts lines shorter than 1 um are left out (`outline_snaps`).
2. Placement (KiCad's pcbnew module, KiCad 10). Every footprint goes to the previous board's
   designator on the same side. A footprint that is the previous one (same pads: U1, USB1, OP1)
   gets the same position and rotation; a stdlib generic footprint (KiCad R_/C_/LED_ libraries) is
   fitted so its pads land on the old pad centres by pad number: the least-squares translation
   for each candidate rotation (old rotation + k x 90, k x 90), the one with the smallest residual
   wins. The reference designator text takes the old one's position, size, layer and orientation.
   D1 gets its 3D model scaled to the fitted LED's height (`LED_HEIGHT`). The aux and grid
   origins and the solder mask expansion (0.02 mm) are the previous board's. Placement runs
   before the copy (step 1), on a board without copper, and the zones are filled after it.
3. `pcb layout` syncs the result, which normalises the file the way `make gen` writes it.

The board keeps the previous revision's KiCad coordinates; spec/bluetooth.toml names the plug
centre (148.501075, 115.343615) as its frame origin. The script is a fixed point: running it on
its own output changes nothing. Run `make gen` and `make check` afterwards.
"""

from __future__ import annotations

import argparse
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

from micras_pcb import previous, sexpr  # noqa: E402

LAYOUT = ROOT / "boards/bluetooth/layout/bluetooth.kicad_pcb"
OLD_PCBDOC = previous.SOURCES["bluetooth"].pcb

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
NET = re.compile(r'\(net "((?:[^"\\]|\\.)*)"\)')
UUID = re.compile(r'\(uuid "[0-9a-f-]+"\)')
UUID_EMPTY = re.compile(r'\(uuid ""\)')


def previous_pcbdoc(arg: Path | None) -> Path:
    if arg:
        return arg
    env = os.environ.get("MICRAS_PREVIOUS")
    root = Path(env).expanduser() if env else ROOT.parent / "hw_debug"
    return root / OLD_PCBDOC


def pad_nets(root: sexpr.Node) -> dict[tuple[str, str], str | None]:
    out = {}
    for fp in root.children("footprint"):
        ref = fp.prop("Reference") or ""
        for pad in fp.children("pad"):
            net = pad.child("net")
            out[(ref, pad.atoms()[0])] = net.atoms()[-1] if net is not None else None
    return out


def net_map(old_root: sexpr.Node, new_root: sexpr.Node) -> dict[str, str]:
    """Old net -> the new net that holds its pads. The board has no declared changes, so every old
    net must land on exactly one new net and no new net may gather two old ones."""
    old, new = pad_nets(old_root), pad_nets(new_root)
    votes: dict[str, Counter] = defaultdict(Counter)
    for (ref, num), net in old.items():
        if net is None or num == "":
            continue
        votes[net][new[(ref, num)]] += 1
    out = {o: c.most_common(1)[0][0] for o, c in votes.items()}
    splits = {o for o, c in votes.items() if len(c) > 1}
    joins = {n for n, k in Counter(out.values()).items() if k > 1}
    if splits or joins:
        raise SystemExit(f"unexpected net correspondence: splits {splits}, joins {joins}")
    return out


TEARDROP = "\t\t(attr\n\t\t\t(teardrop\n\t\t\t\t(type track_end)\n\t\t\t)\n\t\t)\n"
TEARDROP_PADS = "\t\t(connect_pads\n\t\t\t(clearance 0.5)\n\t\t)\n"
ZONE_PADS = "\t\t(connect_pads yes\n\t\t\t(clearance 0.1)\n\t\t)\n"
# The importer gives every zone a 0.25 mm minimum width, which erases most of a teardrop's thin
# flare when the zone is filled. A teardrop fills with 0.1 mm instead, JLCPCB's minimum copper
# feature (rules/jlcpcb-pdk.toml jlc.copper.minimum_feature_width: 0.10 mm on 2 layers, 0.09 mm
# on 4): its body is kept, only the cusps the fab cannot etch go.
MIN_WIDTH = "\t\t(min_thickness 0.25)\n"
TEARDROP_MIN_WIDTH = "\t\t(min_thickness 0.1)\n"
# The pours drop copper narrower than their Altium polygon's neck width
# (MicrasBluetoothModule.PcbDoc Polygons6, REMOVENECKS: 3.937 mil = 0.1 mm on the bottom pour and
# the top pour of POURINDEX 0, 11.811 mil = 0.3 mm on the top pour of POURINDEX 2); the importer
# sets KiCad's 0.25 mm instead. Keyed by layer and the imported priority (2 - Altium POURINDEX).
POUR_MIN_WIDTH = {("F.Cu", 2): 0.1, ("F.Cu", 0): 0.3, ("B.Cu", 1): 0.1}
TEARDROP_PRIORITY = 100  # above every pour of the previous board (max 2), as a teardrop is
_NS = uuid.UUID("9d2a6f43-1c5e-4b7a-8e0f-5a3c7d1b2e64")


def teardrop_to_zone(text: str, key: str, index: int) -> str:
    """A teardrop zone as a plain copper zone of the same outline and net.

    KiCad 10 does not save a teardrop's UUID and orders zones by UUID when it writes a board, so
    every save (`pcb layout` included) shuffles teardrops: a board with teardrop zones is never
    byte-stable. As plain zones with a stable UUID they keep their copper, connect solidly to
    their pads and tracks like a teardrop (connect_pads yes, the board's 0.1 mm clearance), fill
    with a 0.1 mm minimum width, and win over the pours around them (priorities
    above all of them, one per teardrop: KiCad requires distinct priorities for intersecting
    zones).
    """
    if TEARDROP_PADS not in text or MIN_WIDTH not in text:
        raise SystemExit("teardrop zone with unexpected pad connection or width settings")
    text = text.replace(TEARDROP, "").replace(TEARDROP_PADS, ZONE_PADS).replace(MIN_WIDTH, TEARDROP_MIN_WIDTH)
    head, layer, rest = text.partition("\t\t(layer ")
    line, nl, tail = rest.partition("\n")
    uid = uuid.uuid5(_NS, f"teardrop/{key}")
    return f'{head}{layer}{line}{nl}\t\t(uuid "{uid}")\n\t\t(priority {TEARDROP_PRIORITY + index})\n{tail}'


def pour_min_width(text: str) -> str:
    """A pour with the minimum width of its Altium polygon (see POUR_MIN_WIDTH)."""
    layer = re.search(r'^\t\t\(layer "([^"]+)"\)', text, re.M).group(1)
    priority = re.search(r"^\t\t\(priority (\d+)\)", text, re.M)
    width = POUR_MIN_WIDTH[(layer, int(priority.group(1)) if priority else 0)]
    if MIN_WIDTH not in text:
        raise SystemExit("pour with unexpected minimum width settings")
    return text.replace(MIN_WIDTH, f"\t\t(min_thickness {width:g})\n")


def _strip_fill(text: str) -> str:
    """A zone without its filled polygons (the zones are refilled after placement)."""
    node = sexpr.parse(text)
    return sexpr.splice(text, [(*sexpr.line_span(text, f), "") for f in node.children("filled_polygon")])


def strip(text: str) -> str:
    """The layout without the items `copy_items` copies (an earlier run's; the generated layout has none)."""
    root = sexpr.parse(text)
    return sexpr.splice(text, [(*sexpr.line_span(text, n), "") for n in root.children() if n.head in COPIED])


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
    """The new layout with the previous board's copper and board graphics in place of its own.

    The converter writes the items in a different order and with fresh UUIDs on every run, so
    the copied items are sorted by their content and each gets a UUID derived from it: the same
    PcbDoc always gives the same layout text.
    """
    old_root, new_root = sexpr.parse(old_text), sexpr.parse(new_text)
    nets = net_map(old_root, new_root)
    # drop what an earlier run copied (the generated layout has none of these)
    edits = [(*sexpr.line_span(new_text, n), "") for n in new_root.children() if n.head in COPIED]
    items = []
    snaps = outline_snaps(old_root)
    for n in old_root.children():
        if n.head not in COPIED or degenerate_edge(n):
            continue
        text = snap_outline(old_text[slice(*sexpr.line_span(old_text, n))], n, snaps)
        text = NET.sub(lambda m: f"(net {sexpr.quote(nets[m.group(1)])})", text)
        if n.head == "zone":
            text = _strip_fill(text)
        items.append(UUID.sub('(uuid "")', text))
    copied, seen, teardrops = [], Counter(), 0
    for text in sorted(items):
        seen[text] += 1
        key = f"{text}/{seen[text]}"
        uid = iter(str(uuid.uuid5(_NS, f"{key}/{k}")) for k in range(text.count('(uuid "")')))
        text = UUID_EMPTY.sub(lambda m, uid=uid: f'(uuid "{next(uid)}")', text)
        if text.startswith("\t(zone") and TEARDROP in text:
            text = teardrop_to_zone(text, key, teardrops)
            teardrops += 1
        elif text.startswith("\t(zone"):
            text = pour_min_width(text)
        copied.append(text)
    anchor = new_root.child("embedded_fonts") or new_root.children()[-1]
    at = sexpr.line_span(new_text, anchor)[0]
    edits.append((at, at, "".join(copied)))
    return sexpr.splice(new_text, edits)


# ---------------------------------------------------------------------------------------------
# placement (pcbnew)


def _centres(fp) -> dict[str, list[tuple[float, float]]]:
    import pcbnew

    out = defaultdict(list)
    for p in fp.Pads():
        if p.GetNumber() == "":
            continue
        c = p.GetBoundingBox().GetCenter()
        out[p.GetNumber()].append((pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)))
    return out


def _residual(fp, target: dict[str, list[tuple[float, float]]]) -> tuple[float, float, float]:
    """Least-squares translation (dx, dy) moving fp's pad centres onto target, and the rms residual."""
    have = _centres(fp)
    if not target or set(have) != set(target):
        return math.inf, 0.0, 0.0
    pairs = []
    for num, pts in target.items():
        pairs += zip(sorted(have[num]), sorted(pts), strict=True)
    dx = sum(b[0] - a[0] for a, b in pairs) / len(pairs)
    dy = sum(b[1] - a[1] for a, b in pairs) / len(pairs)
    rms = math.sqrt(sum((a[0] + dx - b[0]) ** 2 + (a[1] + dy - b[1]) ** 2 for a, b in pairs) / len(pairs))
    return rms, dx, dy


# Body height of the indicator LED from its datasheet. The stdlib generic's KiCad model
# (LED_0603_1608Metric.step) is 1.1 mm tall; it is scaled in z to the fitted part, so the 3D
# export (MicrasHardware's clearance checks) has the real height.
LED_MODEL_HEIGHT = 1.1
LED_HEIGHT = {
    "D1": 0.55,  # ROHM SMLD12BN1W datasheet p. 1, Dimensions: 1.6 x 0.8 mm (t = 0.55 mm)
}


def place(path: Path, old_path: Path) -> list[str]:
    import pcbnew

    old = pcbnew.LoadBoard(str(old_path))
    new = pcbnew.LoadBoard(str(path))
    by_ref = {fp.GetReference(): fp for fp in old.GetFootprints()}
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
            for ang in sorted({(old_rot + 90 * k) % 360 for k in range(4)} | {90.0 * k for k in range(4)}):
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
        if ref in LED_HEIGHT:
            models = fp.Models()
            for k in range(len(models)):  # by index: iterating yields copies
                m = models[k]
                scale = m.m_Scale
                scale.z = round(LED_HEIGHT[ref] / LED_MODEL_HEIGHT, 6)
                m.m_Scale = scale
        # reference designator text as on the previous board
        nf, of = fp.Reference(), src.Reference()
        nf.SetLayer(of.GetLayer())
        nf.SetAttributes(of)
        nf.SetPosition(of.GetPosition())
        nf.SetVisible(of.IsVisible() and bool(of.GetText()))
    ds = new.GetDesignSettings()
    ods = old.GetDesignSettings()
    ds.SetAuxOrigin(ods.GetAuxOrigin())
    ds.SetGridOrigin(ods.GetGridOrigin())
    ds.m_SolderMaskExpansion = ods.m_SolderMaskExpansion
    pcbnew.SaveBoard(str(path), new)
    return report


def fill(path: Path) -> None:
    import pcbnew

    board = pcbnew.LoadBoard(str(path))
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(path), board)


def pcb_layout(*flags: str) -> None:
    """`pcb layout` on the board with the pinned toolchain (versions.env)."""
    env = dict(
        line.split("=", 1)
        for line in (ROOT / "versions.env").read_text().splitlines()
        if "=" in line and not line.startswith("#")
    )
    subprocess.run(
        ["pcb", f"+{env['PCB_TOOLCHAIN'].strip()}", "layout", *flags, "--no-open", "boards/bluetooth/bluetooth.zen"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--previous", type=Path, help="the previous board's MicrasBluetoothModule.PcbDoc")
    ap.add_argument("--no-sync", action="store_true", help="skip the final `pcb layout` sync")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        old_path = Path(tmp) / "previous.kicad_pcb"
        old_path.write_text(previous.altium_pcb(previous_pcbdoc(a.previous)))
        # Place first, on a board without copper: KiCad gives a via the net of a pad it lands on
        # when it loads a board, so copper copied onto unplaced footprints would pick up wrong nets.
        LAYOUT.write_text(strip(LAYOUT.read_text()))
        for line in place(LAYOUT, old_path):
            print(line)
        LAYOUT.write_text(copy_items(old_path.read_text(), LAYOUT.read_text()))
        fill(LAYOUT)
    if not a.no_sync:
        pcb_layout()
    return 0


if __name__ == "__main__":
    sys.exit(main())
