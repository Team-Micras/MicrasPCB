"""The previous board revision as a committed reference, and a connectivity comparator against it.

The main board is replicated from its previous revision (Altium, converted to KiCad 10 in
`hw_debug`). `snapshot` reads that revision once and writes `boards/main/previous/board.json`,
so the checks never need `hw_debug`. `compare` proves the new board connects exactly what the
old one did, except for the changes declared in `boards/<board>/changes.toml`.

    MICRAS_PREVIOUS=~/codes/hw_debug micras-pcb previous snapshot          # (re)write board.json
    MICRAS_PREVIOUS=~/codes/hw_debug micras-pcb previous snapshot --check  # fail if it is stale
    micras-pcb previous compare main                                       # new board vs previous

Snapshot (`board.json`, format 1). The PCB's pad nets are the ground truth: the converted
schematic merges `Motor_L_Sense-` and `Motor_R_Sense-`, the PCB keeps them apart. The schematic
and the JLCPCB BOM only add part fields. Keys are in natural order (R2 before R10), floats are
rounded to 6 decimals, so a re-run on the same inputs is byte-identical.

    source    root ("hw_debug") and {relative path: sha256} of every input
    board     copper layer count and names, thickness, stackup (null: the file has none),
              aux_axis_origin, grid_origin, Edge.Cuts bounding box
    parts     per designator: lib_id, value, mpn, manufacturer, lcsc, description, sheet, side
              (top/bottom), x, y, rotation (KiCad frame, degrees), dnp, exclude_from_bom,
              in_jlc_bom, and pads {pad number: net name, or null when the pad has no net}.
              Pads without a number (U3's SOT-89 tab) are left out: nothing can connect to them.
    unnamed   footprints with an empty designator under a synthetic id ("NONAME1"...,
              numbered by position), with position, uuid and pad geometry for the layout transfer

Declared changes (`boards/<board>/changes.toml`). Changes apply in file order to the previous
board's connectivity, and the result must equal the new board's. A pad is "REF.PAD" (for example
"IC1.68"). A target is where a pad goes: "REF.PAD" (the net that pad is on at that point),
"net:NAME" (an existing net) or "new:NAME" (a net no earlier state has; the first use creates it,
later uses join it). A pad or net that does not exist is an error, so a typo cannot pass.

    [[change]]
    id = "C1"                                        # required, unique
    review = "hw_debug/schematic_review.md C1"      # optional: where the reason is written down
    summary = "MCU VBAT pin on 3V3 instead of the battery net"   # required
    move = { "IC1.1" = "IC1.68" }                    # the pad leaves its net and joins the target

    [[change]]
    id = "C2"
    summary = "VCAP1-3 and VFBSMPS tied: ST AN5419 Fig. 5 Direct SMPS"
    merge = [["IC1.7", "IC1.33", "IC1.49", "IC1.66"]]   # the nets of these pads become one
                                                        # (named after the first pad's net)

    [[change]]
    id = "M3"
    summary = "Battery divider into PA5"
    isolate = ["IC1.24"]                             # the pad leaves its net, connected to nothing
    add_parts = { R50 = { "1" = "net:VBAT", "2" = "new:VBAT_SENSE" }, R51 = { "1" = "new:VBAT_SENSE", "2" = "net:GND" } }
    remove_parts = ["U3"]                            # the part and its pads disappear
    rename_parts = { "20V" = "TP1" }                 # same part, new designator

Within one change the actions run in the order rename_parts, remove_parts, add_parts, isolate,
move, merge. An added part's pads not listed are unconnected.

    from micras_pcb import previous
    snap = previous.load("main")                        # board.json as a dict
    expected = previous.apply_changes(previous.from_snapshot(snap), previous.load_changes("main"))
    report = previous.diff(expected, previous.from_netlist(netlist.load("main")))
    report.ok, print(report)
    previous.groups(snap)                               # {frozenset{(ref, pad), ...}} multi-pad nets
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import sexpr
from .paths import BOARDS, ROOT

FORMAT = 1
PCB_FILE = "kicad/MicrasMainBoard.kicad_pcb"
BOM_FILE = "MicrasMainBoard-BOM-jlc.csv"
SCH_GLOB = "kicad/*.kicad_sch"

Pad = tuple[str, str]  # (designator, pad number)


def default_source() -> Path:
    env = os.environ.get("MICRAS_PREVIOUS")
    return Path(env).expanduser() if env else ROOT.parent / "hw_debug"


def snapshot_path(board: str = "main") -> Path:
    return BOARDS / board / "previous" / "board.json"


def changes_path(board: str) -> Path:
    return BOARDS / board / "changes.toml"


def natural_key(s: str) -> list:
    return [(0, int(t), "") if t.isdigit() else (1, 0, t) for t in re.findall(r"\d+|\D+", s)]


def _num(x: str | float) -> float:
    v = round(float(x), 6)
    return 0.0 if v == 0 else v


# ---------------------------------------------------------------------------------------------
# snapshot


def _arc_bbox(a, m, b) -> list[tuple[float, float]]:
    """Endpoints plus the circle's extreme points that lie on the arc a -> m -> b."""
    (x1, y1), (x2, y2), (x3, y3) = a, m, b
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    cx = ((x1**2 + y1**2) * (y2 - y3) + (x2**2 + y2**2) * (y3 - y1) + (x3**2 + y3**2) * (y1 - y2)) / d
    cy = ((x1**2 + y1**2) * (x3 - x2) + (x2**2 + y2**2) * (x1 - x3) + (x3**2 + y3**2) * (x2 - x1)) / d
    r = math.hypot(x1 - cx, y1 - cy)
    a1, am, a2 = (math.atan2(y - cy, x - cx) for x, y in (a, m, b))
    tau = 2 * math.pi
    ccw = (am - a1) % tau < (a2 - a1) % tau  # the mid point lies on the a1 -> a2 counter-clockwise sweep
    start, sweep = (a1, (a2 - a1) % tau) if ccw else (a2, (a1 - a2) % tau)
    pts = [a, b]
    for k in range(4):
        ang = k * math.pi / 2
        if (ang - start) % tau <= sweep:
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


def _xy(node: sexpr.Node | None) -> tuple[float, float]:
    a = node.atoms() if node else ["0", "0"]
    return float(a[0]), float(a[1])


def _edge_bbox(root: sexpr.Node) -> dict | None:
    pts: list[tuple[float, float]] = []
    for g in root.children():
        layer = g.child("layer")
        if not g.head or not g.head.startswith("gr_") or layer is None or layer.atoms() != ["Edge.Cuts"]:
            continue
        if g.head == "gr_line":
            pts += [_xy(g.child("start")), _xy(g.child("end"))]
        elif g.head == "gr_arc":
            pts += _arc_bbox(_xy(g.child("start")), _xy(g.child("mid")), _xy(g.child("end")))
        elif g.head == "gr_rect":
            pts += [_xy(g.child("start")), _xy(g.child("end"))]
        elif g.head == "gr_circle":
            (cx, cy), (ex, ey) = _xy(g.child("center")), _xy(g.child("end"))
            r = math.hypot(ex - cx, ey - cy)
            pts += [(cx - r, cy - r), (cx + r, cy + r)]
        elif g.head == "gr_poly":
            pts += [_xy(p) for p in g.child("pts").children("xy")]
        else:
            raise ValueError(f"Edge.Cuts item {g.head} not handled")
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return {"min": [_num(min(xs)), _num(min(ys))], "max": [_num(max(xs)), _num(max(ys))]}


def _board(root: sexpr.Node) -> dict:
    copper = []
    for layer in root.child("layers").children():
        a = [layer.head, *layer.atoms()]
        if a[1].endswith(".Cu"):
            copper.append({"name": a[1], "type": a[2], "user_name": a[3] if len(a) > 3 else None})
    order = {"F.Cu": -1, "B.Cu": 1_000}
    copper.sort(key=lambda c: order.get(c["name"], int(re.sub(r"\D", "", c["name"]) or 0)))
    setup = root.child("setup")
    general = root.child("general")
    thickness = general.child("thickness") if general else None
    stackup = setup.child("stackup") if setup else None
    return {
        "copper_layers": len(copper),
        "layers": copper,
        "thickness": _num(thickness.atoms()[0]) if thickness else None,
        "stackup": None
        if stackup is None
        else [
            {"name": la.atoms()[0], **{c.head: c.atoms()[0] for c in la.children() if c.atoms()}}
            for la in stackup.children("layer")
        ],
        "aux_axis_origin": [_num(v) for v in _xy(setup.child("aux_axis_origin"))],
        "grid_origin": [_num(v) for v in _xy(setup.child("grid_origin"))],
        "edge_cuts_bbox": _edge_bbox(root),
    }


def _pads(fp: sexpr.Node, ref: str) -> dict[str, str | None]:
    pads: dict[str, str | None] = {}
    for pad in fp.children("pad"):
        num = pad.atoms()[0]
        if num == "":
            continue
        net = pad.child("net")
        name = net.atoms()[-1] if net is not None and net.atoms() else None
        if num in pads and pads[num] != name:
            raise ValueError(f"{ref} pad {num} appears on two nets: {pads[num]} and {name}")
        pads[num] = name
    return {k: pads[k] for k in sorted(pads, key=natural_key)}


def _pad_geometry(pad: sexpr.Node) -> dict:
    a = pad.atoms()
    out = {"number": a[0], "type": a[1], "shape": a[2]}
    at = pad.child("at")
    out["at"] = [_num(v) for v in at.atoms()[:2]] if at else [0.0, 0.0]
    if pad.child("size"):
        out["size"] = [_num(v) for v in pad.child("size").atoms()[:2]]
    drill = pad.child("drill")
    if drill:
        out["drill"] = _num(next(v for v in drill.atoms() if v != "oval"))
    return out


def _symbol_fields(paths: list[Path]) -> dict[str, dict]:
    """Per designator: the converted schematic's part fields (Altium parameter names vary by part)."""

    def first(props: dict, *names: str) -> str | None:
        return next((props[n] for n in names if props.get(n)), None)

    out: dict[str, dict] = {}
    for path in paths:
        for sym in sexpr.parse(path.read_text()).children("symbol"):
            props = {p.atoms()[0]: (p.atoms()[1] if len(p.atoms()) > 1 else "") for p in sym.children("property")}
            ref = props.get("Reference", "")
            if not ref or ref.startswith("#"):
                continue
            flag = {h: (sym.child(h).atoms() == ["yes"]) for h in ("in_bom", "dnp") if sym.child(h)}
            fields = {
                "value": props.get("Value") or None,
                "description": props.get("Description") or None,
                "mpn": first(props, "MANUFACTURER PART", "MANUFACTURER_PART_NUMBER", "MANUFACTURER_PART"),
                "manufacturer": first(props, "MANUFACTURER", "MANUFACTURER_NAME"),
                "lcsc": first(props, "SUPPLIER PART", "LCSC PART NUMBER"),
                "dnp": flag.get("dnp", False),
                "exclude_from_bom": not flag.get("in_bom", True),
            }
            if ref in out and out[ref] != fields:  # multi-unit symbols (IC1, W1-W4) repeat their fields
                raise ValueError(f"{ref}: schematic units disagree on part fields")
            out[ref] = fields
    return out


def _bom(path: Path) -> dict[str, dict]:
    """The JLCPCB BOM: Altium writes it in Latin-1 (± and µ are single bytes), with a blank second line."""
    rows = csv.DictReader(io.StringIO(path.read_bytes().decode("latin-1")))
    out: dict[str, dict] = {}
    for row in rows:
        if not (row.get("Designator") or "").strip():
            continue
        for ref in row["Designator"].split(","):
            out[ref.strip()] = {"lcsc": row["Supplier Part"].strip() or None, "description": row["Description"]}
    return out


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_snapshot(source: Path) -> dict:
    pcb_path, bom_path = source / PCB_FILE, source / BOM_FILE
    sch_paths = sorted(p for p in source.glob(SCH_GLOB) if p.name != ".kicad_sch")
    inputs = [pcb_path, bom_path, *sch_paths]
    for p in inputs:
        if not p.is_file():
            raise FileNotFoundError(p)
    root = sexpr.parse(pcb_path.read_text())
    sym = _symbol_fields(sch_paths)
    bom = _bom(bom_path)

    parts: dict[str, dict] = {}
    unnamed: list[dict] = []
    for fp in root.children("footprint"):
        ref = fp.prop("Reference") or ""
        at = fp.child("at").atoms()
        layer = fp.child("layer").atoms()[0]
        place = {
            "side": {"F.Cu": "top", "B.Cu": "bottom"}[layer],
            "x": _num(at[0]),
            "y": _num(at[1]),
            "rotation": _num(at[2]) if len(at) > 2 else 0.0,
        }
        if not ref:
            unnamed.append(
                {
                    "lib_id": fp.atoms()[0] if fp.atoms() else "",
                    "uuid": fp.child("uuid").atoms()[0],
                    **place,
                    "pads": [_pad_geometry(p) for p in fp.children("pad")],
                }
            )
            continue
        if ref in parts:
            raise ValueError(f"designator {ref} appears twice on the PCB")
        attr = set(fp.child("attr").atoms()) if fp.child("attr") else set()
        s = sym.get(ref, {})
        b = bom.get(ref, {})
        sheet = fp.child("sheetname")
        parts[ref] = {
            "lib_id": fp.atoms()[0],
            "value": s.get("value") or fp.prop("Value") or None,
            "mpn": s.get("mpn"),
            "manufacturer": s.get("manufacturer"),
            "lcsc": b.get("lcsc") or s.get("lcsc"),
            "description": s.get("description") or b.get("description"),
            "sheet": sheet.atoms()[0] if sheet else None,
            **place,
            "dnp": "dnp" in attr or s.get("dnp", False),
            "exclude_from_bom": "exclude_from_bom" in attr or s.get("exclude_from_bom", False),
            "in_jlc_bom": ref in bom,
            "in_schematic": ref in sym,
            "pads": _pads(fp, ref),
        }
    missing = sorted(set(bom) - set(parts), key=natural_key)
    if missing:
        raise ValueError(f"BOM designators missing from the PCB: {missing}")
    unnamed.sort(key=lambda u: (u["y"], u["x"]))
    return {
        "format": FORMAT,
        "source": {
            "root": source.name,
            "files": {p.relative_to(source).as_posix(): _sha256(p) for p in inputs},
        },
        "board": _board(root),
        "parts": {r: parts[r] for r in sorted(parts, key=natural_key)},
        "unnamed": {f"NONAME{i}": u for i, u in enumerate(unnamed, 1)},
    }


def dumps(snapshot: dict) -> str:
    return json.dumps(snapshot, indent=1, ensure_ascii=False) + "\n"


def load(board: str = "main", path: Path | None = None) -> dict:
    return json.loads((path or snapshot_path(board)).read_text())


def snapshot(source: Path | None = None, board: str = "main", check: bool = False) -> int:
    source = (source or default_source()).resolve()
    out = snapshot_path(board)
    text = dumps(build_snapshot(source))
    if check:
        if not out.is_file() or out.read_text() != text:
            print(f"{out.relative_to(ROOT)} is stale: run micras-pcb previous snapshot")
            return 1
        print(f"{out.relative_to(ROOT)} matches {source}")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    snap = json.loads(text)
    print(f"wrote {out.relative_to(ROOT)}: {len(snap['parts'])} parts, {len(snap['unnamed'])} unnamed footprints")
    return 0


# ---------------------------------------------------------------------------------------------
# connectivity


@dataclass
class Connectivity:
    """A board's connectivity: its parts and every net (name -> pads), unconnected pads included."""

    parts: set[str]
    nets: dict[str, frozenset[Pad]]

    def net_of(self) -> dict[Pad, str]:
        return {p: name for name, pads in self.nets.items() for p in pads}


def from_snapshot(snap: dict) -> Connectivity:
    nets: dict[str, set[Pad]] = {}
    for ref, part in snap["parts"].items():
        for num, net in part["pads"].items():
            nets.setdefault(net if net is not None else f"unconnected-({ref}-Pad{num})", set()).add((ref, num))
    return Connectivity(set(snap["parts"]), {k: frozenset(v) for k, v in nets.items()})


def from_netlist(nl) -> Connectivity:
    """From a micras_pcb.netlist.Netlist (the generated schematic, as LVS reads it)."""
    nets = {name: frozenset((p.ref, p.pin) for p in pins) for name, pins in nl.nets.items()}
    return Connectivity(set(nl.parts), nets)


def groups(x: Connectivity | dict) -> set[frozenset[Pad]]:
    """The multi-pad nets as sets of (ref, pad); names and unconnected pads drop out."""
    conn = x if isinstance(x, Connectivity) else from_snapshot(x)
    return {g for g in conn.nets.values() if len(g) > 1}


# ---------------------------------------------------------------------------------------------
# declared changes


class ChangeError(ValueError):
    pass


ACTIONS = ("rename_parts", "remove_parts", "add_parts", "isolate", "move", "merge")
KEYS = {"id", "summary", "review", *ACTIONS}


@dataclass
class Change:
    id: str
    summary: str
    review: str | None = None
    rename_parts: dict[str, str] = field(default_factory=dict)
    remove_parts: list[str] = field(default_factory=list)
    add_parts: dict[str, dict[str, str]] = field(default_factory=dict)
    isolate: list[str] = field(default_factory=list)
    move: dict[str, str] = field(default_factory=dict)
    merge: list[list[str]] = field(default_factory=list)


def parse_changes(text: str) -> list[Change]:
    raw = tomllib.loads(text)
    extra = set(raw) - {"change"}
    if extra:
        raise ChangeError(f"unknown top-level keys {sorted(extra)}: use [[change]] tables")
    out, seen = [], set()
    for i, c in enumerate(raw.get("change", []), 1):
        where = f"change #{i} ({c.get('id', 'no id')})"
        unknown = set(c) - KEYS
        if unknown:
            raise ChangeError(f"{where}: unknown keys {sorted(unknown)}")
        if not c.get("id") or not c.get("summary"):
            raise ChangeError(f"{where}: needs id and summary")
        if c["id"] in seen:
            raise ChangeError(f"{where}: duplicate id")
        seen.add(c["id"])
        if not any(c.get(a) for a in ACTIONS):
            raise ChangeError(f"{where}: no action (one of {', '.join(ACTIONS)})")
        if any(not isinstance(g, list) or len(g) < 2 for g in c.get("merge", [])):
            raise ChangeError(f"{where}: merge takes lists of at least two pads")
        out.append(Change(**c))
    return out


def load_changes(board: str, path: Path | None = None) -> list[Change]:
    path = path or changes_path(board)
    return parse_changes(path.read_text()) if path.is_file() else []


def _pad(spec: str, where: str) -> Pad:
    ref, dot, num = spec.partition(".")
    if not dot or not ref or not num:
        raise ChangeError(f"{where}: {spec!r} is not a pad (REF.PAD)")
    return ref, num


def apply_changes(conn: Connectivity, changes: list[Change]) -> Connectivity:
    """The connectivity the new board must have: conn with every change applied, in order."""
    parts = set(conn.parts)
    nets: dict[str, set[Pad]] = {k: set(v) for k, v in conn.nets.items()}
    where_is = {p: n for n, pads in nets.items() for p in pads}
    known_nets = set(nets)  # "net:" may only name these; "new:" may not
    created: set[str] = set()

    def need_pad(spec: str, where: str) -> Pad:
        p = _pad(spec, where)
        if p not in where_is:
            raise ChangeError(f"{where}: unknown pad {spec}")
        return p

    def drop(p: Pad) -> str | None:
        old = where_is.pop(p, None)
        if old is not None:
            nets[old].discard(p)
            if not nets[old]:
                del nets[old]
        return old

    def put(p: Pad, net: str):
        drop(p)
        nets.setdefault(net, set()).add(p)
        where_is[p] = net

    def target(spec: str, where: str) -> str:
        kind, colon, name = spec.partition(":")
        if colon and kind == "net":
            if name not in nets:
                raise ChangeError(f"{where}: unknown net {name!r}")
            return name
        if colon and kind == "new":
            if name in known_nets and name not in created:
                raise ChangeError(f"{where}: new:{name} exists on the previous board, use net:{name}")
            created.add(name)
            return name
        return where_is[need_pad(spec, where)]

    def isolate(p: Pad):
        put(p, f"unconnected-({p[0]}-Pad{p[1]})")

    for c in changes:
        w = f"change {c.id}"
        for old, new in c.rename_parts.items():
            if old not in parts:
                raise ChangeError(f"{w}: rename of unknown part {old}")
            if new in parts:
                raise ChangeError(f"{w}: rename target {new} already exists")
            parts.remove(old)
            parts.add(new)
            for p in [p for p in where_is if p[0] == old]:
                put((new, p[1]), drop(p))
        for ref in c.remove_parts:
            if ref not in parts:
                raise ChangeError(f"{w}: removal of unknown part {ref}")
            parts.remove(ref)
            for p in [p for p in where_is if p[0] == ref]:
                drop(p)
        for ref, pads in c.add_parts.items():
            if ref in parts:
                raise ChangeError(f"{w}: added part {ref} already exists")
            parts.add(ref)
            for num, spec in pads.items():
                put((ref, num), target(spec, f"{w} {ref}.{num}"))
        for spec in c.isolate:
            isolate(need_pad(spec, w))
        for spec, dest in c.move.items():
            p = need_pad(spec, w)
            put(p, target(dest, w))
        for group in c.merge:
            pads = [need_pad(s, w) for s in group]
            keep = where_is[pads[0]]
            for other in {where_is[p] for p in pads[1:]} - {keep}:
                for p in list(nets[other]):
                    put(p, keep)
    return Connectivity(parts, {k: frozenset(v) for k, v in nets.items()})


# ---------------------------------------------------------------------------------------------
# comparison


def _fmt_pads(pads) -> str:
    return " ".join(f"{r}.{n}" for r, n in sorted(pads, key=lambda p: (natural_key(p[0]), natural_key(p[1]))))


@dataclass
class Report:
    only_expected: list[str] = field(default_factory=list)  # parts the new board lacks
    only_actual: list[str] = field(default_factory=list)  # parts the new board adds
    splits: list[tuple[str, dict[str, frozenset[Pad]]]] = field(default_factory=list)
    joins: list[tuple[str, dict[str, frozenset[Pad]]]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.only_expected or self.only_actual or self.splits or self.joins)

    def lines(self) -> list[str]:
        out = [f"  part missing from the new board: {r}" for r in self.only_expected]
        out += [f"  part only on the new board (declare it in changes.toml): {r}" for r in self.only_actual]
        for name, dist in self.splits:
            out.append(f"  split: expected net {name} lands on {len(dist)} new nets:")
            out += [f"      {new}: {_fmt_pads(pads)}" for new, pads in dist.items()]
        for name, dist in self.joins:
            out.append(f"  joined: new net {name} joins pads of {len(dist)} expected nets:")
            out += [f"      {old}: {_fmt_pads(pads)}" for old, pads in dist.items()]
        return out

    def __str__(self) -> str:
        return "\n".join(self.lines())


def _distribution(pads, net_of: dict[Pad, str], multi: set[str], absent: str) -> dict[str, frozenset[Pad]]:
    dist: dict[str, set[Pad]] = {}
    for p in pads:
        name = net_of.get(p)
        label = absent if name is None else name if name in multi else f"{name} (unconnected)"
        dist.setdefault(label, set()).add(p)
    return {k: frozenset(dist[k]) for k in sorted(dist, key=natural_key)}


def diff(expected: Connectivity, actual: Connectivity) -> Report:
    """Every way actual connects pads differently from expected, in net names a human can act on.

    A split: the pads of one expected net end up on several new nets (or unconnected). A join: one
    new net holds pads of several expected nets (or pads expected unconnected). A pad that moved
    from net A to net B shows as a split of A and a join of B.
    """
    rep = Report(
        only_expected=sorted(expected.parts - actual.parts, key=natural_key),
        only_actual=sorted(actual.parts - expected.parts, key=natural_key),
    )
    exp_groups, act_groups = groups(expected), groups(actual)
    exp_net, act_net = expected.net_of(), actual.net_of()
    exp_multi = {n for n, g in expected.nets.items() if len(g) > 1}
    act_multi = {n for n, g in actual.nets.items() if len(g) > 1}
    for name in sorted(exp_multi, key=natural_key):
        g = expected.nets[name]
        if g in act_groups:
            continue
        dist = _distribution(g, act_net, act_multi, "(pad absent on the new board)")
        if len(dist) > 1:
            rep.splits.append((name, dist))
    for name in sorted(act_multi, key=natural_key):
        g = actual.nets[name]
        if g in exp_groups:
            continue
        dist = _distribution(g, exp_net, exp_multi, "(pad absent on the previous board)")
        if len(dist) > 1:
            rep.joins.append((name, dist))
    return rep


def compare(board: str) -> int:
    from . import netlist

    snap = load(board)
    changes = load_changes(board)
    expected = apply_changes(from_snapshot(snap), changes)
    actual = from_netlist(netlist.load(board))
    rep = diff(expected, actual)
    if not rep.ok:
        print(rep)
    n = len(changes)
    summary = "FAILED" if not rep.ok else f"same connectivity ({len(groups(actual))} nets)"
    print(f"{board}: previous revision + {n} declared change{'s' if n != 1 else ''}: {summary}")
    return 0 if rep.ok else 1
