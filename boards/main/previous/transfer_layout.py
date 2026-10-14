"""Transfer the previous main board's placement, routing, zones and outline onto boards/main.

    python3 boards/main/previous/transfer_layout.py [--previous PATH] [--no-sync]

Reads the previous revision (default: $MICRAS_PREVIOUS/kicad/MicrasMainBoard.kicad_pcb, else
../hw_debug/kicad/MicrasMainBoard.kicad_pcb, the KiCad 10 conversion of the Altium PCB) and the
generated layout boards/main/layout/main.kicad_pcb, and rewrites the layout:

1. Copper and board graphics (text, span-preserving: micras_pcb.sexpr). Every track, arc, via,
   zone (fills, priorities, teardrops) and board-level graphic (Edge.Cuts outline with the
   encoder slots and USB-C peg holes, silkscreen texts and art) is copied byte for byte, with
   its net renamed to the new net that owns the pads the old net connected (found by pad
   membership, see `net_map`). Then the C1 and C2 copper edits of `rework.py` are applied.
2. Placement (KiCad's pcbnew module, KiCad 10). Every footprint goes to the previous board's
   designator (changes.toml renames the four test points) on the same side. A footprint that is
   the previous one (same pads) gets the same position and rotation; a stdlib generic footprint
   (KiCad R_/C_/LED_ libraries) is fitted so its pads land on the old pad centres by pad number:
   the least-squares translation for each candidate rotation (old rotation + k x 90, k x 90), the
   one with the smallest residual wins. The reference designator text takes the old one's
   position, size, layer and orientation. The screw holes H1-H4 go to the previous board's
   unnamed footprints (in board.json order). The aux and grid origins are the previous board's.
   Zones are refilled.
3. `pcb layout` syncs the result, which normalises the file the way `make gen` writes it.

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

from micras_pcb import sexpr  # noqa: E402

import rework  # noqa: E402

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
TEARDROP_PRIORITY = 100  # above every pour of the previous board (max 49), as a teardrop is
_NS = uuid.UUID("3b0f6c1e-5a7d-4e8a-9c41-2f6d8e0b7a35")


def teardrop_to_zone(text: str, index: int) -> str:
    """A teardrop zone as a plain copper zone of the same outline and net.

    KiCad 10 does not save a teardrop's UUID and orders zones by UUID when it writes a board, so
    every save (`pcb layout` included) shuffles teardrops: a board with teardrop zones is never
    byte-stable. As plain zones with a stable UUID they keep their copper, connect solidly to
    their pads and tracks like a teardrop (connect_pads yes, the board's 0.1 mm clearance), and
    win over the pours around them (priorities above all of them, one per teardrop: KiCad
    requires distinct priorities for intersecting zones).
    """
    if TEARDROP_PADS not in text:
        raise SystemExit("teardrop zone with unexpected pad connection settings")
    text = text.replace(TEARDROP, "").replace(TEARDROP_PADS, ZONE_PADS)
    head, layer, rest = text.partition("\t\t(layer ")
    line, nl, tail = rest.partition("\n")
    uid = uuid.uuid5(_NS, f"teardrop/{index}")
    return f'{head}{layer}{line}{nl}\t\t(uuid "{uid}")\n\t\t(priority {TEARDROP_PRIORITY + index})\n{tail}'


def copy_items(old_text: str, new_text: str, ren: dict[str, str]) -> str:
    """The new layout with the previous board's copper and board graphics in place of its own."""
    old_root, new_root = sexpr.parse(old_text), sexpr.parse(new_text)
    nets = net_map(old_root, new_root, ren)
    # drop what an earlier run copied (the generated layout has none of these)
    edits = [(*sexpr.line_span(new_text, n), "") for n in new_root.children() if n.head in COPIED]
    items = [n for n in old_root.children() if n.head in COPIED]
    copied = []
    for i, n in enumerate(items):
        text = old_text[sexpr.line_span(old_text, n)[0] : sexpr.line_span(old_text, n)[1]]
        text = NET.sub(lambda m: f"(net {sexpr.quote(nets[m.group(1)])})", text)
        if n.head == "zone" and TEARDROP in text:
            text = teardrop_to_zone(text, i)
        copied.append(text)
    copied = rework.apply(copied)
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


def place(path: Path, old_path: Path, ren: dict[str, str]) -> list[str]:
    import pcbnew

    old = pcbnew.LoadBoard(str(old_path))
    new = pcbnew.LoadBoard(str(path))
    by_ref = {fp.GetReference(): fp for fp in old.GetFootprints() if fp.GetReference()}
    holes = sorted(
        (fp for fp in old.GetFootprints() if not fp.GetReference()), key=lambda f: (f.GetPosition().y, f.GetPosition().x)
    )
    back = {v: k for k, v in ren.items()}
    report = []
    for fp in new.GetFootprints():
        ref = fp.GetReference()
        if re.fullmatch(r"H\d+", ref):
            src = holes[int(ref[1:]) - 1]
        else:
            src = by_ref[back.get(ref, ref)]
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
    pcbnew.ZONE_FILLER(new).Fill(new.Zones())
    pcbnew.SaveBoard(str(path), new)
    return report


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
        env = dict(line.split("=", 1) for line in (ROOT / "versions.env").read_text().splitlines() if "=" in line and not line.startswith("#"))
        subprocess.run(
            ["pcb", f"+{env['PCB_TOOLCHAIN'].strip()}", "layout", "--no-open", "boards/main/main.zen"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
