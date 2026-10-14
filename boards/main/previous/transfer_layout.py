"""Transfer the previous main board's placement, routing, zones and outline onto boards/main.

    python3 boards/main/previous/transfer_layout.py [--previous PATH] [--no-sync]

Reads the previous revision (default: $MICRAS_PREVIOUS/kicad/MicrasMainBoard.kicad_pcb, else
../hw_debug/kicad/MicrasMainBoard.kicad_pcb, the KiCad 10 conversion of the Altium PCB) and the
generated layout boards/main/layout/main.kicad_pcb, and rewrites the layout:

1. Copper and board graphics (text, span-preserving: micras_pcb.sexpr). Every track, arc, via,
   zone (fills, priorities, teardrops) and board-level graphic (Edge.Cuts outline with the
   encoder slots and USB-C peg holes, silkscreen texts and art) is copied byte for byte, with
   its net renamed to the new net that owns the pads the old net connected (found by pad
   membership, see `net_map`). The zones take the Altium pour settings the importer drops:
   teardrops become plain zones (`teardrop_to_zone`), pours keep the Altium neck width
   (`POUR_MIN_WIDTH`) and the inner-layer pours relieve through-hole pads (`INNER_PADS`). The
   Edge.Cuts lines shorter than 1 um are left out (`outline_snaps`). Then the C1 and C2 copper
   edits of `rework.py` are applied, and the inner-layer voids around the screw holes are added
   (`HOLE_VOIDS`).
2. Placement (KiCad's pcbnew module, KiCad 10). Every footprint goes to the previous board's
   designator (changes.toml renames the four test points) on the same side. A footprint that is
   the previous one (same pads) gets the same position and rotation; a stdlib generic footprint
   (KiCad R_/C_/LED_ libraries) is fitted so its pads land on the old pad centres by pad number:
   the least-squares translation for each candidate rotation (old rotation + k x 90, k x 90), the
   one with the smallest residual wins. The reference designator text takes the old one's
   position, size, layer and orientation. The LEDs D4 and D5 get their 3D model scaled to the
   fitted part's height (`LED_HEIGHT`). The screw holes H1-H4 (the previous board's unnamed
   footprints, in board.json order) go where spec/main.toml puts them, locked, as
   `micras-pcb mech main` does. The aux and grid origins are the spec's (the Altium origin) and
   the solder mask expansion the previous board's (0.02 mm). Zones are refilled.
3. `pcb layout` syncs the result, which normalises the file the way `make gen` writes it.

A plain sync keeps a placed footprint as it is: after a package's footprint changes, run
`pcb layout --sync-footprints --no-open boards/main/main.zen` before this script.

The script is a fixed point: running it on its own output changes nothing (step 1 removes the
copied items before copying them again, step 2 sets absolute values, every new item has a stable
UUID). Run `make gen` and `make check` afterwards.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import subprocess
import sys
import tomllib
import uuid
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import rework  # noqa: E402
from micras_pcb import mech, sexpr, spec  # noqa: E402

LAYOUT = ROOT / "boards/main/layout/main.kicad_pcb"
CHANGES = ROOT / "boards/main/changes.toml"
OLD_PCB = "kicad/MicrasMainBoard.kicad_pcb"

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


def previous_pcb(arg: Path | None) -> Path:
    if arg:
        return arg
    env = os.environ.get("MICRAS_PREVIOUS")
    root = Path(env).expanduser() if env else ROOT.parent / "hw_debug"
    return root / OLD_PCB


def renames() -> dict[str, str]:
    """Old designator -> new designator, from changes.toml."""
    out = {}
    for c in tomllib.loads(CHANGES.read_text()).get("change", []):
        out.update(c.get("rename_parts", {}))
    return out


def pad_nets(root: sexpr.Node) -> dict[tuple[str, str], str | None]:
    out = {}
    for fp in root.children("footprint"):
        ref = fp.prop("Reference") or ""
        for pad in fp.children("pad"):
            net = pad.child("net")
            out[(ref, pad.atoms()[0])] = net.atoms()[-1] if net is not None else None
    return out


def net_map(old_root: sexpr.Node, new_root: sexpr.Node, ren: dict[str, str]) -> dict[str, str]:
    """Old net -> the new net that holds the most of its pads.

    The only old net whose pads split is VBAT (change C1 moves IC1.1, C8.2 and C9.2 to 3V3; its
    copper there is redone by rework.c1); the only new net that gathers several old nets is VCORE
    (change C2 joins VFBSMPS and VCAP1-3). Anything else is a mismatch and stops the transfer.
    """
    old, new = pad_nets(old_root), pad_nets(new_root)
    votes: dict[str, Counter] = defaultdict(Counter)
    for (ref, num), net in old.items():
        if net is None or num == "":
            continue
        votes[net][new[(ren.get(ref, ref), num)]] += 1
    out = {o: c.most_common(1)[0][0] for o, c in votes.items()}
    splits = {o for o, c in votes.items() if len(c) > 1}
    joins = Counter(out.values())
    if splits != {"VBAT"} or {n for n, k in joins.items() if k > 1} != {"VCORE"}:
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
# The pours drop copper narrower than their Altium polygon's neck width (MicrasMainBoard.PcbDoc
# Polygons6: REMOVENECKS with NECKWIDTHTHRESHOLD 3.937 mil = 0.1 mm on all 25 pours); the importer
# sets KiCad's 0.25 mm instead.
POUR_MIN_WIDTH = defaultdict(lambda: 0.1)
# Inner-layer pours connect through-hole pads with thermal reliefs (Altium MicrasMainBoard.PcbDoc
# rule PolygonConnect: through-hole pads Relief, 4 spokes at 90 degrees, 10 mil air gap and
# 10 mil conductors; vias Direct). The rule PolygonConnect_Top/BottomLayer makes the outer pours
# Direct, as the importer sets them; the gap and spoke widths are already the zones' (0.254 mm).
INNER_LAYERS = ('(layer "In1.Cu")', '(layer "In2.Cu")')
INNER_PADS = "\t\t(connect_pads thru_hole_only\n\t\t\t(clearance 0.1)\n\t\t)\n"
TEARDROP_PRIORITY = 100  # above every pour of the previous board (max 49), as a teardrop is
_NS = uuid.UUID("3b0f6c1e-5a7d-4e8a-9c41-2f6d8e0b7a35")


def teardrop_to_zone(text: str, index: int) -> str:
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
    uid = uuid.uuid5(_NS, f"teardrop/{index}")
    return f'{head}{layer}{line}{nl}\t\t(uuid "{uid}")\n\t\t(priority {TEARDROP_PRIORITY + index})\n{tail}'


def pour_min_width(text: str) -> str:
    """A pour with the minimum width of its Altium polygon (see POUR_MIN_WIDTH)."""
    layer = re.search(r'^\t\t\(layer "([^"]+)"\)', text, re.M).group(1)
    priority = re.search(r"^\t\t\(priority (\d+)\)", text, re.M)
    width = POUR_MIN_WIDTH[(layer, int(priority.group(1)) if priority else 0)]
    if MIN_WIDTH not in text:
        raise SystemExit("pour with unexpected minimum width settings")
    return text.replace(MIN_WIDTH, f"\t\t(min_thickness {width:g})\n")


def inner_pour(text: str) -> str:
    """An inner-layer pour with thermal reliefs on through-hole pads (see INNER_PADS)."""
    if ZONE_PADS not in text:
        raise SystemExit("inner-layer zone with unexpected pad connection settings")
    return text.replace(ZONE_PADS, INNER_PADS)


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


# The inner planes keep clear of the M2 screw holes H1-H4 as on the previous board: Altium's pours
# stop 1.559 mm (In1.Cu) and 2.074 mm (In2.Cu) from each hole centre (radius of the void in the
# MicrasMainBoard.PcbDoc pour regions, the same at all four holes; the Altium CAM output agrees),
# more than KiCad's hole clearance gives (1.2 mm radius + 0.2 mm). A copper-pour keepout of that
# radius around each hole on each inner layer reproduces the voids.
HOLE_VOIDS = {"In1.Cu": 1.559, "In2.Cu": 2.074}
_VOID_SIDES = 64


def screw_hole_voids() -> list[str]:
    """Copper-pour keepouts around H1-H4 on the inner layers (see HOLE_VOIDS)."""
    s = spec.load("main")
    holes = sorted(
        (p["path"].split(".")[0], mech.robot_to_kicad(s, (p["x"], p["y"])))
        for p in mech.placements(s).values()
        if re.fullmatch(r"H\d+\.MH", p["path"])
    )
    out = []
    for ref, (cx, cy) in holes:
        for layer, radius in HOLE_VOIDS.items():
            r = radius / math.cos(math.pi / _VOID_SIDES)  # the polygon's edges touch the circle
            pts = [
                f"(xy {sexpr.fmt(round(cx + r * math.cos(a), 6))} {sexpr.fmt(round(cy + r * math.sin(a), 6))})"
                for a in (2 * math.pi * k / _VOID_SIDES for k in range(_VOID_SIDES))
            ]
            rows = "".join(f"\t\t\t\t{' '.join(pts[k : k + 4])}\n" for k in range(0, len(pts), 4))
            uid = uuid.uuid5(_NS, f"hole-void/{ref}/{layer}")
            out.append(
                f'\t(zone\n\t\t(layer "{layer}")\n\t\t(uuid "{uid}")\n\t\t(name "{ref} plane void")\n'
                "\t\t(hatch edge 0.5)\n\t\t(connect_pads\n\t\t\t(clearance 0)\n\t\t)\n\t\t(min_thickness 0.25)\n"
                "\t\t(keepout\n\t\t\t(tracks allowed)\n\t\t\t(vias allowed)\n\t\t\t(pads allowed)\n"
                "\t\t\t(copperpour not_allowed)\n\t\t\t(footprints allowed)\n\t\t)\n"
                '\t\t(placement\n\t\t\t(enabled no)\n\t\t\t(sheetname "")\n\t\t)\n'
                "\t\t(fill\n\t\t\t(thermal_gap 0.5)\n\t\t\t(thermal_bridge_width 0.5)\n\t\t)\n"
                f"\t\t(polygon\n\t\t\t(pts\n{rows}\t\t\t)\n\t\t)\n\t)\n"
            )
    return out


def copy_items(old_text: str, new_text: str, ren: dict[str, str]) -> str:
    """The new layout with the previous board's copper and board graphics in place of its own."""
    old_root, new_root = sexpr.parse(old_text), sexpr.parse(new_text)
    nets = net_map(old_root, new_root, ren)
    # drop what an earlier run copied (the generated layout has none of these)
    edits = [(*sexpr.line_span(new_text, n), "") for n in new_root.children() if n.head in COPIED]
    items = [n for n in old_root.children() if n.head in COPIED]
    snaps = outline_snaps(old_root)
    copied = []
    for i, n in enumerate(items):
        if degenerate_edge(n):
            continue
        text = old_text[sexpr.line_span(old_text, n)[0] : sexpr.line_span(old_text, n)[1]]
        text = snap_outline(text, n, snaps)
        text = NET.sub(lambda m: f"(net {sexpr.quote(nets[m.group(1)])})", text)
        if n.head == "zone" and TEARDROP in text:
            text = teardrop_to_zone(text, i)
        elif n.head == "zone":
            text = pour_min_width(text)
            if any(layer in text for layer in INNER_LAYERS):
                text = inner_pour(text)
        copied.append(text)
    copied = rework.apply(copied) + screw_hole_voids()
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
        mine = have[num]
        if len(mine) == len(pts):
            pairs += zip(sorted(mine), sorted(pts), strict=True)
        else:
            # U3: the new SOT-89 numbers its tab "2" like pin 2, the old one leaves it unnumbered;
            # pair each old pad with the nearest new pad of its number (only valid in place)
            pairs += [(min(mine, key=lambda m, q=q: math.dist(m, q)), q) for q in pts]
    dx = sum(b[0] - a[0] for a, b in pairs) / len(pairs)
    dy = sum(b[1] - a[1] for a, b in pairs) / len(pairs)
    rms = math.sqrt(sum((a[0] + dx - b[0]) ** 2 + (a[1] + dy - b[1]) ** 2 for a, b in pairs) / len(pairs))
    return rms, dx, dy


def _snap(v: float) -> float:
    return round(v, 6)


# Body heights of the indicator LEDs from their datasheets. The stdlib generic's KiCad model
# (LED_0603_1608Metric.step) is 1.1 mm tall; it is scaled in z to the fitted part, so the 3D
# export (MicrasHardware's clearance checks) has the real height.
LED_MODEL_HEIGHT = 1.1
LED_HEIGHT = {
    "D4": 0.80,  # NationStar NCD0603Y2 datasheet p. 2, Outline Dimension: 0.80 mm
    "D5": 0.60,  # KENTO KT-0603R datasheet p. 1, Package (L/W/H): 1.6 x 0.8 x 0.6 mm
}


def place(path: Path, old_path: Path, ren: dict[str, str]) -> list[str]:
    import pcbnew

    old = pcbnew.LoadBoard(str(old_path))
    new = pcbnew.LoadBoard(str(path))
    by_ref = {fp.GetReference(): fp for fp in old.GetFootprints() if fp.GetReference()}
    holes = sorted(
        (fp for fp in old.GetFootprints() if not fp.GetReference()),
        key=lambda f: (f.GetPosition().y, f.GetPosition().x),
    )
    back = {v: k for k, v in ren.items()}
    s = spec.load("main")
    spec_holes = {
        p["path"].split(".")[0]: mech.robot_to_kicad(s, (p["x"], p["y"]))
        for p in mech.placements(s).values()
        if re.fullmatch(r"H\d+\.MH", p["path"])
    }
    report = []
    for fp in new.GetFootprints():
        ref = fp.GetReference()
        src = holes[int(ref[1:]) - 1] if re.fullmatch(r"H\d+", ref) else by_ref[back.get(ref, ref)]
        if fp.IsFlipped() != src.IsFlipped():
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        target = _centres(src)
        fp.SetOrientation(src.GetOrientation())
        fp.SetPosition(src.GetPosition())
        rms, _, _ = _residual(fp, target) if target else (0.0, 0.0, 0.0)
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
            fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(_snap(dx)), pcbnew.FromMM(_snap(dy))))
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
        if ref in spec_holes:
            # spec/main.toml owns the screw holes (`micras-pcb mech main` writes them the same way)
            fp.SetPosition(pcbnew.VECTOR2I(*(pcbnew.FromMM(v) for v in spec_holes[ref])))
            fp.SetLocked(True)
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
        ["pcb", f"+{env['PCB_TOOLCHAIN'].strip()}", "layout", *flags, "--no-open", "boards/main/main.zen"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--previous", type=Path, help="the previous board's .kicad_pcb")
    ap.add_argument("--no-sync", action="store_true", help="skip the final `pcb layout` sync")
    a = ap.parse_args()
    old_path = previous_pcb(a.previous)
    ren = renames()
    text = copy_items(old_path.read_text(), LAYOUT.read_text(), ren)
    LAYOUT.write_text(text)
    for line in place(LAYOUT, old_path, ren):
        print(line)
    if not a.no_sync:
        pcb_layout()
    return 0


if __name__ == "__main__":
    sys.exit(main())
