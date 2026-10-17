"""Schematic placement: `boards/<board>/schematic/<sheet>.toml` positions what `pcb apply` writes.

`pcb apply` generates each sheet afresh (`make gen` deletes the schematic first), with every part
where its placer puts it and every pin tied to its net by a short stub and a label or power
symbol. `micras-pcb sch` then redraws each sheet from its placement file:

- each part goes where the file puts it (`parts`), with its rotation, mirror and field side;
- the wires the file draws (`wires`, chains of pins and points) join pins of one net, and the
  net's labels or power symbols go at the chain's free ends or at the pins it names (`taps`);
- every other pin keeps the label or power symbol pcb gave it, on a stub in the pin's direction
  (a power symbol points up for a supply and down for ground), or its no-connect flag;
- a pin pcb gave several labels (a module sheet's hierarchical and global labels of one net)
  keeps the first at the pin, and the rest are drawn in the sheet's ports column (`ports`), each
  tied to a copy of the first;
- titled frames group each function block (`block`), the paper and title block are set, and on
  the root sheet each module's sheet symbol goes where the file puts it, its pins in the file's
  order (`sheet`).

Nothing is renamed or reconnected: the tool reads which labels and power symbols pcb attached to
each pin and draws exactly those, and it fails unless KiCad's netlist of the placed schematic
equals the one of pcb's (same nets, same names, same pins). A part without a placement entry
stays where pcb put it and `micras-pcb sch --check` (in `make check`) names it.

Coordinates in the placement files are in grid units of 1.27 mm (KiCad's 50 mil schematic grid),
x right and y down from the page's top-left corner; a block's parts and wire points are relative
to the block's `at`.
"""

from __future__ import annotations

import itertools
import math
import subprocess
import tempfile
import tomllib
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import schlint, sexpr
from .checks import schematic_sheets
from .paths import BOARDS, ROOT, board_sch, board_zen
from .schematic import (
    ANGLE_OF,
    DOWN,
    GRID,
    LEFT,
    PAPER,
    RIGHT,
    UP,
    Pin,
    Sheet,
    Symbol,
    islands,
    key,
    on_segment,
    text_width,
    transform,
)
from .tools import kicad_cli, pcb

NAMESPACE = uuid.UUID("6f1c3c52-5b57-4bde-9d39-1f3d8f7a1c0e")
STUB = 2  # default stub length, grid units
PORT_WIRE = 4  # ports column: wire between a pin's first label and each further one, grid units
PORT_PITCH = 2  # ports column row pitch, grid units


def spec_dir(board: str) -> Path:
    return BOARDS / board / "schematic"


# ---------------------------------------------------------------------------------------------
# Placement files


@dataclass
class PartSpec:
    at: tuple[float, float]
    rot: int = 0
    mirror: str | None = None
    fields: str | None = None  # right, left, top, bottom, around (ref above, value below), hide
    line: str = ""


@dataclass
class SheetSymbolSpec:
    at: tuple[float, float]
    size: tuple[float, float]
    left: list[str]
    right: list[str]


@dataclass
class Spec:
    paper: str = "A4"
    portrait: bool = False
    title: str = ""
    parts: dict[str, PartSpec] = field(default_factory=dict)
    chains: list[list] = field(default_factory=list)  # tokens: pin id str, or (x, y) mm
    taps: list[str] = field(default_factory=list)
    stubs: dict[str, dict] = field(default_factory=dict)
    frames: list[tuple[str, float, float, float, float]] = field(default_factory=list)
    notes: list[tuple[str, float, float]] = field(default_factory=list)
    ports: tuple[float, float, int, str] | None = None
    sheets: dict[str, SheetSymbolSpec] = field(default_factory=dict)
    end_opts: dict = field(default_factory=dict)


def _mm(v) -> float:
    return float(v) * GRID


def _pt(v, origin=(0.0, 0.0)) -> tuple[float, float]:
    return origin[0] + _mm(v[0]), origin[1] + _mm(v[1])


def load_spec(path: Path) -> Spec:
    data = tomllib.loads(path.read_text()) if path.exists() else {}
    spec = Spec(paper=data.get("paper", "A4"), portrait=data.get("portrait", False), title=data.get("title", ""))
    blocks = [{"at": [0, 0], **{k: data[k] for k in ("parts", "wires", "taps", "stubs") if k in data}}]
    blocks += data.get("block", [])
    for b in blocks:
        origin = _pt(b.get("at", [0, 0]))
        if "size" in b:
            w, h = (_mm(v) for v in b["size"])
            spec.frames.append((b.get("title", ""), origin[0], origin[1], origin[0] + w, origin[1] + h))
        for f in b.get("frame", []):  # [x, y, w, h], relative to the block
            x, y = _pt(f[:2], origin)
            spec.frames.append((f[4] if len(f) > 4 else b.get("title", ""), x, y, x + _mm(f[2]), y + _mm(f[3])))
        for ref, v in b.get("parts", {}).items():
            if ref in spec.parts:
                raise ValueError(f"{path.name}: {ref} placed twice")
            if isinstance(v, list):
                v = {"at": v[:2], "rot": v[2] if len(v) > 2 else 0}
            spec.parts[ref] = PartSpec(
                at=_pt(v["at"], origin),
                rot=int(v.get("rot", 0)) % 360,
                mirror=v.get("mirror"),
                fields=v.get("fields"),
            )
        for chain in b.get("wires", []):
            # a table after a point holds the options of the label or power symbol drawn at that
            # point when it is a free end: label = "right"..., point = "out"
            items = []
            for t in chain:
                if isinstance(t, dict):
                    spec.end_opts[key(items[-1])] = t
                else:
                    items.append(t if isinstance(t, str) else _pt(t, origin))
            spec.chains.append(items)
        spec.taps += b.get("taps", [])
        spec.stubs.update(b.get("stubs", {}))
        for n in b.get("note", []):
            x, y = _pt(n["at"], origin)
            spec.notes.append((n["text"], x, y))
    if "ports" in data:
        p = data["ports"]
        x, y = _pt(p["at"])
        spec.ports = (x, y, int(p.get("rows", 1000)), p.get("title", ""))
    for name, s in data.get("sheet", {}).items():
        spec.sheets[name] = SheetSymbolSpec(
            _pt(s["at"]), (_mm(s["size"][0]), _mm(s["size"][1])), s.get("left", []), s.get("right", [])
        )
    return spec


# ---------------------------------------------------------------------------------------------
# Drawing


@dataclass
class Driver:
    """A label or power symbol pcb attached to a pin, as (kind, text, shape or power library)."""

    kind: str
    text: str
    extra: str | None

    @property
    def rank(self) -> int:
        """Which label stays at the pin when it has several: a global label, then a local one."""
        return {"global_label": 0, "label": 1, "power": 2, "hierarchical_label": 3}[self.kind]


@dataclass
class Drawing:
    wires: list[tuple[tuple[float, float], tuple[float, float]]] = field(default_factory=list)
    labels: list[tuple[Driver, tuple[float, float], int]] = field(default_factory=list)  # angle
    power: list[tuple[Driver, tuple[float, float], int]] = field(default_factory=list)  # rotation
    no_connects: list[tuple[float, float]] = field(default_factory=list)
    ports: list[tuple[Driver, Driver]] = field(default_factory=list)


def _snap(v: float) -> float:
    return round(v / GRID) * GRID


def _add(p, d, n=1.0):
    return p[0] + d[0] * n, p[1] + d[1] * n


def _route(a, b, da=None, db=None) -> list[tuple[float, float]]:
    """Points of an orthogonal path from a to b: straight when aligned, else one bend, leaving a
    pin along its axis (da) or entering one along its axis (db)."""
    if key(a)[0] == key(b)[0] or key(a)[1] == key(b)[1]:
        return [a, b]
    if da is not None:
        corner = (b[0], a[1]) if da[1] == 0 else (a[0], b[1])
    elif db is not None:
        corner = (a[0], b[1]) if db[1] == 0 else (b[0], a[1])
    else:
        corner = (b[0], a[1])
    return [a, corner, b]


class Placer:
    def __init__(self, board: str, sheet_path: Path, text: str, spec: Spec, pin_net: dict[str, str]):
        self.board, self.path, self.spec, self.pin_net = board, sheet_path, spec, pin_net
        self.sheet = Sheet.load(sheet_path, text)
        self.problems: list[str] = []
        self.unplaced: list[str] = []
        self.counter = 0
        self.d = Drawing()
        self._read_drivers()

    # --- what pcb attached to each pin

    def _read_drivers(self) -> None:
        self.pin_drivers: dict[str, list[Driver]] = {}
        self.pin_nc: set[str] = set()
        self.sheet_pin_drivers: dict[tuple[str, str], list[Driver]] = {}
        self.label_template: dict[tuple[str, str, str | None], sexpr.Node] = {}
        self.power_template: dict[tuple[str, str], sexpr.Node] = {}
        for lb in self.sheet.labels:
            self.label_template.setdefault((lb.kind, lb.text, lb.shape), lb.node)
        for s in self.sheet.symbols:
            if s.power:
                self.power_template.setdefault((s.lib.name, s.value), s.node)
        for isl in islands(self.sheet):
            drivers = sorted((Driver(*d) for d in isl.drivers()), key=lambda d: (d.rank, d.kind, d.text))
            if len(isl.pins) > 1 and not drivers:
                # pcb leaves pins tied inside the part (jumper pin groups) bare; any other unnamed
                # multi-pin net needs a wire in the placement file.
                pass
            for p in isl.pins:
                self.pin_drivers[p.id] = drivers
                if isl.no_connect:
                    self.pin_nc.add(p.id)
            for sp in isl.sheet_pins:
                self.sheet_pin_drivers[(sp.sheet, sp.name)] = drivers

    def uid(self, what: str) -> str:
        self.counter += 1
        return str(uuid.uuid5(NAMESPACE, f"{self.board}/{self.path.name}/{what}/{self.counter}"))

    # --- placement

    def place(self) -> str:
        parts = {s.ref: s for s in self.sheet.parts()}
        for ref, s in parts.items():
            ps = self.spec.parts.get(ref)
            if ps is None:
                self.unplaced.append(ref)
                continue
            s.at, s.rot, s.mirror = ps.at, ps.rot, ps.mirror
        for ref in self.spec.parts:
            if ref not in parts:
                self.problems.append(f"{ref} is placed but not on this sheet")
        self.pins = {p.id: p for s in parts.values() for p in s.pins()}
        self.by_name: dict[str, Pin] = {}
        names: dict[tuple[str, str], list[Pin]] = {}
        for p in self.pins.values():
            names.setdefault((p.ref, p.name), []).append(p)
        self.by_name = {f"{r}.{n}": ps[0] for (r, n), ps in names.items() if len(ps) == 1}
        self._sheet_symbols()
        wired = self._chains()
        self._terminals(wired)
        self._ports()
        return self._write(parts)

    def pin(self, token: str) -> Pin:
        p = self.pins.get(token) or self.by_name.get(token)
        if p is None:
            raise ValueError(f"{self.path.name}: no pin {token} (REF.number, or REF.name when the name is unique)")
        return p

    def _sheet_symbols(self) -> None:
        self.sheet_pin_at: dict[tuple[str, str], tuple[tuple[float, float], tuple[int, int]]] = {}
        for n in self.sheet.root.children("sheet"):
            name = n.prop("Sheetname") or ""
            ss = self.spec.sheets.get(name)
            pins = [p.atoms()[0] for p in n.children("pin")]
            if ss is None:
                for p in n.children("pin"):
                    at = p.child("at").atoms()
                    out = {0: RIGHT, 180: LEFT, 90: UP, 270: DOWN}[int(float(at[2]))]
                    self.sheet_pin_at[(name, p.atoms()[0])] = ((float(at[0]), float(at[1])), out)
                self.unplaced.append(f"sheet {name}")
                continue
            listed = ss.left + ss.right
            for p in listed:
                if p not in pins:
                    self.problems.append(f"sheet {name}: no pin {p}")
            left = ss.left + [p for p in pins if p not in listed and p not in ss.right]
            x0, y0 = ss.at
            for side, names, x, out in ((0, left, x0, LEFT), (1, ss.right, x0 + ss.size[0], RIGHT)):
                for i, p in enumerate(names):
                    self.sheet_pin_at[(name, p)] = ((x, y0 + GRID * 2 * (i + 1)), out)
                if GRID * 2 * (len(names) + 1) > ss.size[1] + 1e-6:
                    self.problems.append(
                        f"sheet {name}: {len(names)} pins do not fit its {(side and 'right') or 'left'} side"
                    )

    def _chains(self) -> set[str]:
        """Draw the placement file's wires; group them with the pins they reach and find their
        free ends. Return the wired pins."""
        segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
        named: list[str] = []
        for chain in self.spec.chains:
            pts, dirs = [], []
            for t in chain:
                if isinstance(t, str):
                    p = self.pin(t)
                    pts.append(p.at)
                    dirs.append(p.out)
                    named.append(p.id)
                else:
                    pts.append(t)
                    dirs.append(None)
            for a, b, da, db in zip(pts, pts[1:], dirs, dirs[1:], strict=False):
                path = _route(a, b, da, db)
                segs += [s for s in itertools.pairwise(path) if key(s[0]) != key(s[1])]
        self.d.wires += segs
        parent: dict = {}

        def find(k):
            while parent.setdefault(k, k) != k:
                parent[k] = parent[parent[k]]
                k = parent[k]
            return k

        pin_at = {key(p.at): p.id for p in self.pins.values()}
        ends: dict = {}
        for i, (a, b) in enumerate(segs):
            for e in (a, b):
                ends.setdefault(key(e), []).append(i)
        touched: dict[str, int] = {}
        for i, (a, b) in enumerate(segs):
            for k in [*ends, *pin_at]:
                if on_segment((k[0] / 10000, k[1] / 10000), a, b):
                    parent[find(("s", i))] = find(("p", k))
                    if k in pin_at:
                        touched[pin_at[k]] = i
        self.groups: dict = {}
        for pid, i in touched.items():
            self.groups.setdefault(find(("s", i)), []).append(pid)
        for g in self.groups.values():
            g.sort(key=lambda p: named.index(p) if p in named else len(named))
        self.group_of = {p: g for g, ps in self.groups.items() for p in ps}
        for pid in named:
            if pid not in touched:
                self.problems.append(f"a wire does not reach {pid}")
        self.free_ends: list[tuple[tuple[float, float], tuple[int, int], object]] = []
        for k, idx in ends.items():
            if len(idx) != 1 or k in pin_at:
                continue
            p = (k[0] / 10000, k[1] / 10000)
            a, b = segs[idx[0]]
            if any(on_segment(p, *segs[j]) for j in range(len(segs)) if j != idx[0]):
                continue
            other = b if key(a) == k else a
            dx, dy = k[0] - key(other)[0], k[1] - key(other)[1]
            out = (int((dx > 0) - (dx < 0)), int((dy > 0) - (dy < 0)))
            g = find(("s", idx[0]))
            if g not in self.groups:
                self.problems.append(f"a wire ending at ({p[0] / GRID:g}, {p[1] / GRID:g}) reaches no pin")
                continue
            self.free_ends.append((p, out, g))
        for ps in self.groups.values():
            nets = {self.pin_net.get(p) for p in ps}
            if len(nets) > 1:
                pins = ", ".join(f"{p} ({self.pin_net.get(p)})" for p in ps)
                self.problems.append(f"a wire joins pins of different nets: {pins}")
        return set(touched)

    def _drivers_of_group(self, g: str) -> list[Driver]:
        seen, out = set(), []
        for p in self.groups[g]:
            for d in self.pin_drivers.get(p, []):
                if (d.kind, d.text, d.extra) not in seen:
                    seen.add((d.kind, d.text, d.extra))
                    out.append(d)
        return sorted(out, key=lambda d: (d.rank, d.kind, d.text))

    def _terminals(self, wired: set[str]) -> None:
        for pid, p in sorted(self.pins.items()):
            if pid in wired:
                continue
            if pid in self.pin_nc:
                self.d.no_connects.append(p.at)
                continue
            drivers = self.pin_drivers.get(pid, [])
            if drivers:
                self._attach(p.at, p.out, drivers, self.spec.stubs.get(pid, {}))
        for (sheet, name), (at, out) in sorted(self.sheet_pin_at.items()):
            drivers = self.sheet_pin_drivers.get((sheet, name), [])
            if drivers:
                self._attach(at, out, drivers, self.spec.stubs.get(f"{sheet}:{name}", {}))
        # Wired groups: their drivers at the free ends, else at the taps, else on the wire at the
        # first pin (a local label).
        for g in self.groups:
            drivers = self._drivers_of_group(g)
            if not drivers:
                continue
            ends = [(p, out) for p, out, gg in self.free_ends if gg == g]
            taps = [self.pin(t) for t in self.spec.taps]
            taps = [t for t in taps if self.group_of.get(t.id) == g]
            if ends:
                for p, out in ends:
                    self._attach(p, out, drivers, {"len": 0, **self.spec.end_opts.get(key(p), {})})
            elif taps:
                for t in taps:
                    self._attach(t.at, t.out, drivers, {"len": 0, **self.spec.stubs.get(t.id, {})})
            elif drivers[0].kind == "label":
                first = self.pins[self.groups[g][0]]
                self._attach(first.at, first.out, drivers, {"len": 0})
            else:
                pins = ", ".join(self.groups[g])
                self.problems.append(
                    f"the wire joining {pins} needs a free end or a tap for its {drivers[0].kind} {drivers[0].text}"
                )

    def _attach(self, at, out, drivers: list[Driver], opts: dict) -> None:
        """A stub from a pin (or a wire's free end) and its drivers at the stub's end."""
        first, rest = drivers[0], drivers[1:]
        self.d.ports += [(first, r) for r in rest]
        if first.kind == "power":
            natural = DOWN if first.extra == "GND" else UP
            length = opts.get("len", 0 if out == natural else STUB)
            end = _add(at, out, length * GRID)
            if length:
                self.d.wires.append((at, end))
            rot = 0
            if opts.get("point") == "out" or (out == (-natural[0], -natural[1]) and not length):
                rot = next(r for r in (0, 90, 180, 270) if transform(natural, r, None) == out)
            self.d.power.append((first, end, rot))
            return
        length = opts.get("len", STUB)
        end = _add(at, out, length * GRID)
        if length:
            self.d.wires.append((at, end))
        facing = {"right": RIGHT, "left": LEFT, "up": UP, "down": DOWN}.get(opts.get("label", ""), out)
        self.d.labels.append((first, end, ANGLE_OF[facing]))

    def _ports(self) -> None:
        """The sheet's ports column: each further label of a pin, tied by a short wire to a copy of
        the label the pin keeps (the copy connects by name)."""
        if not self.d.ports:
            return
        if self.spec.ports is None:
            self.problems.append(
                f"{len(self.d.ports)} pin(s) carry several labels: give the sheet a ports column ([ports] at = [x, y])"
            )
            return
        x, y0, rows, title = self.spec.ports
        seen, entries = set(), []
        for first, other in self.d.ports:
            k = (first.kind, first.text, other.kind, other.text)
            if k not in seen:
                seen.add(k)
                entries.append((first, other))
        entries.sort(key=lambda e: (e[1].text.lower(), e[0].text.lower()))
        left = _snap_up(max(text_width(e[0].text) for e in entries) + 2.54 + GRID)
        right = _snap_up(max(text_width(e[1].text) for e in entries) + 2.54 + GRID)
        column = left + PORT_WIRE * GRID + right + 2 * GRID
        top = y0 + (3 * GRID if title else GRID)
        for i, (first, other) in enumerate(entries):
            c, r = divmod(i, rows)
            a = (x + c * column + left, top + r * PORT_PITCH * GRID)
            b = _add(a, RIGHT, PORT_WIRE * GRID)
            self.d.wires.append((a, b))
            self.d.labels.append((first, a, 180))
            self.d.labels.append((other, b, 0))
        if title:
            cols = (len(entries) - 1) // rows + 1
            n = min(rows, len(entries))
            self.spec.frames.append((title, x, y0, x + cols * column, top + (n - 1) * PORT_PITCH * GRID + 2 * GRID))

    def paper(self) -> tuple[float, float]:
        w, h = PAPER[self.spec.paper]
        return (h, w) if self.spec.portrait else (w, h)

    # --- wires: split at every connection point inside them, junctions where three items meet

    def _anchors(self) -> list[tuple[float, float]]:
        pts = [p.at for p in self.pins.values()]
        pts += [at for at, _ in self.sheet_pin_at.values()]
        pts += [at for _, at, _ in self.d.labels] + [at for _, at, _ in self.d.power] + self.d.no_connects
        return pts

    def _finish_wires(self) -> tuple[list, list]:
        segs = []
        seen = set()
        for a, b in self.d.wires:
            if key(a) == key(b):
                continue
            k = tuple(sorted((key(a), key(b))))
            if k not in seen:
                seen.add(k)
                segs.append((a, b))
        points = self._anchors() + [e for s in segs for e in s]
        out = []
        for a, b in segs:
            inner = sorted(
                {key(p): p for p in points if on_segment(p, a, b) and key(p) not in (key(a), key(b))}.values(),
                key=lambda p: (p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2,
            )
            chain = [a, *inner, b]
            out += list(itertools.pairwise(chain))
        ends: dict = {}
        for a, b in out:
            for e in (a, b):
                ends[key(e)] = ends.get(key(e), 0) + 1
        anchors = {key(p) for p in self._anchors()}
        junctions = []
        for k, n in sorted(ends.items()):
            if n + (1 if k in anchors else 0) >= 3:
                junctions.append((k[0] / 10000, k[1] / 10000))
        return out, junctions

    # --- fields

    def _fields(self, s: Symbol, ps: PartSpec | None) -> dict[str, tuple[tuple[float, float], str]]:
        """Visible fields' positions and horizontal justification."""
        names = [
            p.atoms()[0]
            for p in s.node.children("property")
            if not (p.child("hide") and p.child("hide").atoms() == ["yes"])
            and (p.atoms()[1] if len(p.atoms()) > 1 else "").strip()
        ]
        if not names:
            return {}
        body = s.body()
        pins = s.pins()
        if body is None:
            xs, ys = [p.at[0] for p in pins], [p.at[1] for p in pins]
            body = (min(xs), min(ys), max(xs), max(ys))
        x0, y0, x1, y1 = body
        # a pin on the body's top or bottom edge draws its name across that edge
        side_pins = [p.at[1] for p in pins if p.out in (LEFT, RIGHT)]
        if side_pins and s.lib.name_offset is not None:
            y0, y1 = min(y0, min(side_pins) - 0.9), max(y1, max(side_pins) + 0.9)
        sides = {p.out for p in pins}
        side = ps.fields if ps and ps.fields else None
        if side is None:
            side = ("right" if sides <= {UP, DOWN} else "top") if len(pins) == 2 else "around"
        texts = {n: s.node.prop(n) or "" for n in names}
        w = max(text_width(v) for v in texts.values())
        pitch = 2.54
        n_lines = len(names)
        if isinstance(side, list):  # the first field's left end, grid units from the anchor
            x, y = s.at[0] + _mm(side[0]), s.at[1] + _mm(side[1])
            return {n: ((x, y + i * pitch), "left") for i, n in enumerate(names)}
        if side == "around":
            side = self._free_side(s, pins, body, w, n_lines)
        out = {}
        if side in ("right", "left"):
            cy = (y0 + y1) / 2
            for i, n in enumerate(names):
                y = _snap2(cy + (i - (n_lines - 1) / 2) * pitch)
                out[n] = ((x1 + 1.27, y), "left") if side == "right" else ((x0 - 1.27, y), "right")
        elif side in ("top", "bottom"):
            cx = (x0 + x1) / 2
            for i, n in enumerate(names):
                y = y0 - 1.905 - (n_lines - 1 - i) * pitch if side == "top" else y1 + 1.905 + i * pitch
                out[n] = ((cx, y), "center")
        else:  # top-left, top-right, bottom-left, bottom-right; or right of the top pins
            vert, _, horiz = side.partition("-")
            for i, n in enumerate(names):
                y = y0 - 1.905 - (n_lines - 1 - i) * pitch if vert == "top" else y1 + 1.905 + i * pitch
                if horiz == "left":
                    out[n] = ((x0, y), "left")
                elif horiz == "right":
                    out[n] = ((x1, y), "right")
                else:  # "top-pins": just right of the rightmost top pin
                    xp = max(p.at[0] for p in pins if p.out == UP) + 1.27
                    out[n] = ((xp, y), "left")
        return out

    @staticmethod
    def _free_side(s: Symbol, pins: list[Pin], body, w: float, n: int) -> str:
        """Above or below the body, at its left or right end, where no pin leaves that edge."""
        x0, _, x1, _ = body
        for side, out in (("top", UP), ("bottom", DOWN)):
            xs = [p.at[0] for p in pins if p.out == out]
            if not any(x0 - 1.27 <= x <= x0 + w + 1.27 for x in xs):
                return f"{side}-left"
            if not any(x1 - w - 1.27 <= x <= x1 + 1.27 for x in xs):
                return f"{side}-right"
        return "top-pins"

    # --- output

    def _write(self, parts: dict[str, Symbol]) -> str:
        text = self.sheet.text
        root = self.sheet.root
        edits: list[tuple[int, int, str]] = []
        remove = ("wire", "junction", "no_connect", "label", "global_label", "hierarchical_label", "title_block")
        remove += ("rectangle", "text")
        for n in root.children():
            if n.head in remove or (n.head == "symbol" and Sheet_is_power(self.sheet, n)):
                edits.append((*sexpr.line_span(text, n), ""))
        for n in root.children("symbol"):
            if Sheet_is_power(self.sheet, n):
                continue
            s = parts[n.prop("Reference")]
            edits.append((n.start, n.end, self._symbol_text(text, n, s)))
        for n in root.children("sheet"):
            edits.append((n.start, n.end, self._sheet_text(text, n)))
        paper = root.child("paper")
        new_paper = f'(paper "{self.spec.paper}"{" portrait" if self.spec.portrait else ""})'
        title = self.spec.title or self.path.stem
        tb = (
            f"\n\t(title_block\n\t\t(title {sexpr.quote(title)})\n"
            f"\t\t(comment 1 {sexpr.quote(f'Placed from boards/{self.board}/schematic/{self.path.stem}.toml')})\n\t)"
        )
        edits.append((paper.start, paper.end, new_paper + tb))
        items = self._items()
        end = root.child("sheet_instances")
        at = sexpr.line_span(text, end)[0] if end else text.rstrip().rfind(")")
        edits.append((at, at, items))
        return sexpr.splice(text, edits)

    def _items(self) -> str:
        out = []
        segs, junctions = self._finish_wires()
        for p in junctions:
            out.append(
                f'\t(junction\n\t\t(at {_f(p[0])} {_f(p[1])})\n\t\t(diameter 0)\n\t\t(color 0 0 0 0)\n\t\t(uuid "{self.uid("junction")}")\n\t)\n'
            )
        for p in self.d.no_connects:
            out.append(f'\t(no_connect\n\t\t(at {_f(p[0])} {_f(p[1])})\n\t\t(uuid "{self.uid("nc")}")\n\t)\n')
        for a, b in segs:
            out.append(
                f"\t(wire\n\t\t(pts\n\t\t\t(xy {_f(a[0])} {_f(a[1])}) (xy {_f(b[0])} {_f(b[1])})\n\t\t)\n"
                f'\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n\t\t(uuid "{self.uid("wire")}")\n\t)\n'
            )
        for d, at, angle in self.d.labels:
            out.append(self._label_text(d, at, angle))
        for d, at, rot in self.d.power:
            out.append(self._power_text(d, at, rot))
        for title, x0, y0, x1, y1 in self.spec.frames:
            out.append(
                f"\t(rectangle\n\t\t(start {_f(x0)} {_f(y0)})\n\t\t(end {_f(x1)} {_f(y1)})\n"
                f"\t\t(stroke\n\t\t\t(width 0.254)\n\t\t\t(type dash)\n\t\t\t(color 0 0 194 1)\n\t\t)\n"
                f'\t\t(fill\n\t\t\t(type none)\n\t\t)\n\t\t(uuid "{self.uid("frame")}")\n\t)\n'
            )
            if title:
                out.append(_text(title, x0 + 1.27, y0 + 1.27, 1.5, self.uid("title"), bold=True, justify="left top"))
        for note, x, y in self.spec.notes:
            out.append(_text(note, x, y, 1.27, self.uid("note"), justify="left top"))
        return "".join(out)

    def _label_text(self, d: Driver, at, angle: int) -> str:
        tmpl = self.label_template[(d.kind, d.text, d.extra)]
        src = self.sheet.text
        justify = "left" if angle in (0, 90) else "right"
        if d.kind == "label":
            justify += " bottom"
        edits = [(tmpl.child("at").start, tmpl.child("at").end, f"(at {_f(at[0])} {_f(at[1])} {angle})")]
        eff = tmpl.child("effects")
        edits.append((eff.start, eff.end, _effects(_font_size(eff), justify, 2)))
        u = tmpl.child("uuid")
        edits.append((u.start, u.end, f'(uuid "{self.uid("label")}")'))
        for p in tmpl.children("property"):
            pa = p.child("at")
            edits.append((pa.start, pa.end, f"(at {_f(at[0])} {_f(at[1])} 0)"))
        return "\t" + _splice_node(src, tmpl, edits) + "\n"

    def _power_text(self, d: Driver, at, rot: int) -> str:
        tmpl = self.power_template[(d.extra, d.text)]
        src = self.sheet.text
        u = self.uid("power")
        ref = "#PWR" + u.replace("-", "")
        lib = self.sheet.libs[d.extra]
        sym = Symbol(tmpl, lib, at, rot, None)
        edits = [(tmpl.child("at").start, tmpl.child("at").end, f"(at {_f(at[0])} {_f(at[1])} {rot})")]
        fa = tmpl.child("fields_autoplaced")
        if fa:
            edits.append((*_line(src, fa), ""))
        uu = tmpl.child("uuid")
        edits.append((uu.start, uu.end, f'(uuid "{u}")'))
        for p in tmpl.children("property"):
            name = p.atoms()[0]
            pa = p.child("at")
            if name == "Reference":
                # the value atom follows the name: rewrite the property's head line
                head_end = p.child("at").start
                edits.append((p.start, head_end, f'(property "Reference" "{ref}"\n\t\t\t'))
                edits.append((pa.start, pa.end, f"(at {_f(at[0])} {_f(at[1])} 0)"))
            elif name == "Value":
                fr = 90 if rot in (90, 270) else 0
                justify = ""
                if rot == 0:
                    vx, vy = sym.page(_lib_field_at(lib, "Value"))
                else:
                    tip = (0.0, 2.54) if d.extra != "GND" else (0.0, -2.54)
                    tx, ty = sym.page(tip)
                    dx, dy = (tx - at[0]) / 2.54, (ty - at[1]) / 2.54
                    if abs(dy) < 0.5:  # pointing sideways: the text beyond the tip, reading away
                        vx, vy = tx + dx * 0.762, ty
                        justify = _stored_justify("left" if dx > 0 else "right", sym, fr)
                    else:
                        vx, vy = tx, ty + dy * 1.27
                edits.append((pa.start, pa.end, f"(at {_f(round(vx, 4))} {_f(round(vy, 4))} {fr})"))
                eff = p.child("effects")
                edits.append((eff.start, eff.end, _effects(_font_size(eff), justify, 3)))
            else:
                edits.append((pa.start, pa.end, f"(at {_f(at[0])} {_f(at[1])} 0)"))
        for pin in tmpl.children("pin"):
            pu = pin.child("uuid")
            edits.append((pu.start, pu.end, f'(uuid "{self.uid("pwrpin")}")'))
        for inst in tmpl.children("instances"):
            for proj in inst.children("project"):
                for path in proj.children("path"):
                    r = path.child("reference")
                    edits.append((r.start, r.end, f'(reference "{ref}")'))
        return "\t" + _splice_node(src, tmpl, edits) + "\n"

    def _symbol_text(self, src: str, n: sexpr.Node, s: Symbol) -> str:
        ps = self.spec.parts.get(s.ref)
        edits = [(n.child("at").start, n.child("at").end, f"(at {_f(s.at[0])} {_f(s.at[1])} {s.rot})")]
        m = n.child("mirror")
        if m:
            edits.append((*_line(src, m), f"\t\t(mirror {s.mirror})\n" if s.mirror else ""))
        elif s.mirror:
            e = n.child("at").end
            edits.append((e, e, f"\n\t\t(mirror {s.mirror})"))
        fa = n.child("fields_autoplaced")
        if fa and ps is not None:
            edits.append((*_line(src, fa), ""))
        fields = self._fields(s, ps) if ps is not None else {}
        field_rot = 90 if s.rot in (90, 270) else 0
        for p in n.children("property"):
            name = p.atoms()[0]
            pa = p.child("at")
            if ps is None:
                continue
            if name in fields:
                (fx, fy), justify = fields[name]
                justify = _stored_justify(justify, s, field_rot)
                edits.append((pa.start, pa.end, f"(at {_f(round(fx, 4))} {_f(round(fy, 4))} {field_rot})"))
                eff = p.child("effects")
                edits.append((eff.start, eff.end, _effects(_font_size(eff), justify, 3)))
            else:
                edits.append((pa.start, pa.end, f"(at {_f(s.at[0])} {_f(s.at[1])} {field_rot})"))
        return _splice_node(src, n, edits)

    def _sheet_text(self, src: str, n: sexpr.Node) -> str:
        name = n.prop("Sheetname") or ""
        ss = self.spec.sheets.get(name)
        if ss is None:
            return src[n.start : n.end]
        (x, y), (w, h) = ss.at, ss.size
        edits = [
            (n.child("at").start, n.child("at").end, f"(at {_f(x)} {_f(y)})"),
            (n.child("size").start, n.child("size").end, f"(size {_f(w)} {_f(h)})"),
        ]
        for p in n.children("property"):
            pa, eff = p.child("at"), p.child("effects")
            if p.atoms()[0] == "Sheetname":
                edits.append((pa.start, pa.end, f"(at {_f(x)} {_f(round(y - 0.7112, 4))} 0)"))
                edits.append((eff.start, eff.end, _effects(_font_size(eff), "left bottom", 3, bold=True)))
            elif p.atoms()[0] == "Sheetfile":
                edits.append((pa.start, pa.end, f"(at {_f(x)} {_f(round(y + h + 0.5938, 4))} 0)"))
                edits.append((eff.start, eff.end, _effects(_font_size(eff), "left top", 3)))
        for p in n.children("pin"):
            (px, py), out = self.sheet_pin_at[(name, p.atoms()[0])]
            angle = 180 if out == LEFT else 0
            pa, eff = p.child("at"), p.child("effects")
            edits.append((pa.start, pa.end, f"(at {_f(px)} {_f(py)} {angle})"))
            edits.append((eff.start, eff.end, _effects(_font_size(eff), "left" if out == LEFT else "right", 3)))
        return _splice_node(src, n, edits)


def Sheet_is_power(sheet: Sheet, n: sexpr.Node) -> bool:
    return sheet.libs[n.child("lib_id").atoms()[0]].power


def _lib_field_at(lib, name: str) -> tuple[float, float]:
    for p in lib.node.children("property"):
        if p.atoms()[0] == name:
            a = p.child("at").atoms()
            return float(a[0]), float(a[1])
    return 0.0, 0.0


def _stored_justify(justify: str, s: Symbol, field_rot: int) -> str:
    """KiCad draws a field's justification through its symbol's transform: store the one that
    reads as `justify` on the page (pcb-kicad-sch field_autoplace.rs stored_field_justify)."""
    if justify == "center":
        return ""
    fx, fy = (1, 0) if field_rot == 0 else (0, -1)
    ax, _ = transform((fx, fy), s.rot, s.mirror)
    if ax >= 0:
        return justify
    return {"left": "right", "right": "left"}[justify]


def _font_size(eff: sexpr.Node) -> str:
    size = eff.child("font").child("size") if eff.child("font") else None
    return " ".join(size.atoms()) if size else "1.27 1.27"


def _effects(size: str, justify: str, depth: int, bold: bool = False) -> str:
    t = "\t" * depth
    b = f"\n{t}\t\t(bold yes)" if bold else ""
    j = f"\n{t}\t(justify {justify})" if justify else ""
    return f"(effects\n{t}\t(font\n{t}\t\t(size {size}){b}\n{t}\t){j}\n{t})"


def _text(text: str, x: float, y: float, size: float, uid: str, bold=False, justify="left bottom") -> str:
    return (
        f"\t(text {sexpr.quote(text)}\n\t\t(exclude_from_sim no)\n\t\t(at {_f(x)} {_f(y)} 0)\n\t\t"
        + _effects(f"{_f(size)} {_f(size)}", justify, 2, bold=bold)
        + f'\n\t\t(uuid "{uid}")\n\t)\n'
    )


def _f(v: float) -> str:
    return sexpr.fmt(round(v, 4))


def _snap_up(v: float) -> float:
    return math.ceil(v / GRID - 1e-6) * GRID


def _snap2(v: float) -> float:
    return round(v / 0.635) * 0.635


def _line(text: str, node: sexpr.Node) -> tuple[int, int]:
    return sexpr.line_span(text, node)


def _splice_node(src: str, node: sexpr.Node, edits: list[tuple[int, int, str]]) -> str:
    """The node's text with edits (absolute spans inside it) applied."""
    rel = [(a - node.start, b - node.start, r) for a, b, r in edits]
    return sexpr.splice(src[node.start : node.end], rel)


# ---------------------------------------------------------------------------------------------
# Board level


def _netlist(sch: Path) -> dict[str, frozenset[str]]:
    """{net name: pins} of KiCad's netlist of a schematic."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "n.net"
        subprocess.run(
            [kicad_cli(), "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(out), str(sch)],
            check=True,
            capture_output=True,
        )
        root = sexpr.parse(out.read_text())
    nets = {}
    for net in root.child("nets").children("net"):
        name = net.child("name").atoms()[0]
        nets[name] = frozenset(f"{n.child('ref').atoms()[0]}.{n.child('pin').atoms()[0]}" for n in net.children("node"))
    return nets


def unplaced(board: str) -> list[str]:
    """What the board's placement files leave out: a sheet without a file, a part or sheet
    symbol without an entry, an entry for a part not on its sheet, a sheet not placed."""
    out = []
    for path in schematic_sheets(board_sch(board)):
        spec_path = spec_dir(board) / f"{path.stem}.toml"
        if not spec_path.exists():
            out.append(f"{path.name} has no placement file boards/{board}/schematic/{path.stem}.toml")
            continue
        spec = load_spec(spec_path)
        sh = Sheet.load(path)
        refs = {s.ref for s in sh.parts()}
        if missing := sorted(refs - set(spec.parts), key=_refkey):
            out.append(f"{path.name}: parts without a placement: {', '.join(missing)}")
        if stale := sorted(set(spec.parts) - refs, key=_refkey):
            out.append(f"{path.name}: placements of parts not on the sheet: {', '.join(stale)}")
        names = {n.prop("Sheetname") for n in sh.root.children("sheet")}
        if missing := sorted(names - set(spec.sheets)):
            out.append(f"{path.name}: sheet symbols without a placement: {', '.join(missing)}")
        if not _placed_marker(path):
            out.append(f"{path.name} is not placed: run `make gen`")
    return out


def run(board: str, check: bool = False) -> int:
    """Place the board's generated schematic from its placement files (check: only report
    what they leave out)."""
    root = board_sch(board)
    sheets = schematic_sheets(root)
    if check:
        found = unplaced(board)
        for f in found:
            print(f"{board}: {f}")
        if not found:
            print(f"{board}: every part of {len(sheets)} sheet(s) placed")
        return 1 if found else 0
    if any(_placed_marker(p) for p in sheets):
        # placing works from what pcb writes: regenerate it, as `make gen` does
        for p in root.parent.glob("*.kicad_sch"):
            p.unlink()
        subprocess.run([*pcb(), "apply", "--no-open", str(board_zen(board))], cwd=ROOT, check=True, capture_output=True)
        sheets = schematic_sheets(root)
    before = _netlist(root)
    pin_net = {p: n for n, ps in before.items() for p in ps}
    texts, problems, left_out = {}, [], []
    for path in sheets:
        spec_path = spec_dir(board) / f"{path.stem}.toml"
        if not spec_path.exists():
            left_out.append(f"{path.name} (no {spec_path.relative_to(ROOT)})")
            continue
        placer = Placer(board, path, path.read_text(), load_spec(spec_path), pin_net)
        texts[path] = placer.place()
        problems += [f"{path.name}: {p}" for p in placer.problems]
        left_out += [f"{path.name}: {r}" for r in placer.unplaced]
    if problems:
        for p in problems:
            print(f"  {p}")
        print(
            f"{board}: schematic placement failed ({len(problems)} problem(s)); the schematic is left as pcb wrote it"
        )
        return 1
    originals = {p: p.read_text() for p in texts}
    for path, t in texts.items():
        path.write_text(t)
    after = _netlist(root)
    if after != before:
        lost = sorted(set(before.items()) - set(after.items()))
        new = sorted(set(after.items()) - set(before.items()))
        for name, pins in lost[:10]:
            print(f"  pcb's net {name}: {sorted(pins)}")
        for name, pins in new[:10]:
            print(f"  placed net {name}: {sorted(pins)}")
        for path, t in originals.items():
            path.write_text(t)
        print(f"{board}: the placed schematic's netlist differs from pcb's; the schematic is left as pcb wrote it")
        return 1
    for path in texts:
        found = schlint.problems(path)
        for f in found[:40]:
            print(f"  {path.name}: {f}")
        if len(found) > 40:
            print(f"  {path.name}: and {len(found) - 40} more overlaps")
    for u in left_out:
        print(f"  unplaced: {u}")
    print(
        f"{board}: placed {len(texts)} sheet(s), netlist unchanged"
        + (f", {len(left_out)} unplaced" if left_out else "")
    )
    return 0


def _placed_marker(path: Path) -> bool:
    return '(comment 1 "Placed from boards/' in path.read_text()


def info(board: str, sheet: str, refs: list[str]) -> int:
    """Print a generated sheet's parts for writing its placement file: each part's library
    symbol, body box and pins in grid units from its anchor (unrotated, y down), with the pin's
    direction and what pcb attached to it (p: power symbol, l: local, g: global, h: hierarchical
    label, NC: no-connect flag). Run it on the schematic as pcb wrote it (or as placed: the
    placement does not change what is attached)."""
    path = board_sch(board).parent / f"{sheet}.kicad_sch"
    sh = Sheet.load(path)
    drv: dict[str, str] = {}
    for isl in islands(sh):
        d = ",".join(sorted(f"{k[0][0]}:{k[1]}" for k in isl.drivers())) + ("NC" if isl.no_connect else "")
        for p in isl.pins:
            drv[p.id] = d
    arrow = {RIGHT: ">", LEFT: "<", UP: "^", DOWN: "v"}
    for s in sorted(sh.parts(), key=lambda s: _refkey(s.ref)):
        if refs and s.ref not in refs:
            continue
        s.at, s.rot, s.mirror = (0.0, 0.0), 0, None
        b = s.body()
        box = f"[{b[0] / GRID:g}, {b[1] / GRID:g}]..[{b[2] / GRID:g}, {b[3] / GRID:g}]" if b else "-"
        print(f"{s.ref} {s.lib.name} '{s.value}' body {box}")
        for p in s.pins():
            print(
                f"    {p.number:>4} {p.name:<16} ({p.at[0] / GRID:g}, {p.at[1] / GRID:g}) {arrow[p.out]} {drv.get(p.id, '')}"
            )
    for n in sh.root.children("sheet"):
        print(f"sheet {n.prop('Sheetname')}: {' '.join(p.atoms()[0] for p in n.children('pin'))}")
    return 0


def _refkey(ref: str):
    import re

    m = re.match(r"([A-Za-z#]+)(\d*)", ref)
    return (m.group(1), int(m.group(2) or 0)) if m else (ref, 0)
