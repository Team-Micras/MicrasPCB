"""The robot's boards together: the main board with its four wall boards and two encoder boards
standing in their joints, for review (KiCad Prism shows one board at a time).

build/main/review/:
  assembly.glb / assembly.step   the three boards as one model; origin at the robot's (the wheel-axle
                                 midpoint): x = -y and y = x of the robot frame, z up
  assembly-iso-left.png / -iso-right.png / -top.png   renders, from the front-left, front-right, top
build/main/assembly/:
  main.kicad_pcb (+ .kicad_pro)  a copy of the main board, its wall joints W1-W4 and encoder slots
                                 EC1/EC2 carrying the daughterboards' STEP models
  wall.step / encoder.step       the daughterboards in their spec frames (user origin = spec origin),
  wall.glb / encoder.glb         and as glTF: the reference the export is checked against

Each daughterboard stands where the specs put it, never on a hand-copied number:
  - wall boards (spec/wall.toml frame: u right seen from the front, v up from the main board's top):
    the mid-plane over the joint centre of spec/main.toml [w1]-[w4], the front (the sensor side,
    KiCad's top) facing the joint's look direction; v 0 on the main board's top surface, so the
    header's insulator sits on it and the long pins go down through the joint's holes;
  - encoder boards (spec/encoder.toml frame: u right seen from the chip side, v 0 on the shoulder
    line): the mid-plane on the slot centre of spec/main.toml [encoder_slots], the shoulder on the
    main board's top, the tab down in the slot, the chip facing the side where spec/main.toml
    [encoder_boards] keeps room for its parts (outboard, toward the wheel's magnet).
Each placement is turned into a model offset and rotation in the footprint's own frame (the
footprint's position and turn read from the copy), so it holds wherever the joint footprint sits.

The copy is edited with micras_pcb.sexpr; the source board and the footprints stay untouched.
"""

from __future__ import annotations

import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import glb, mech, sexpr, spec
from .glb import Matrix, apply, mul
from .paths import board_pcb, build_dir, has_layout
from .tools import kicad_cli

DAUGHTERS = ("wall", "encoder")
# KiCad 10's 3D exporters put a front footprint's model 0.05 mm over the board's outer copper (the
# pads' extra thickness): every board's glTF export shows it, the parts' models sitting at the core's
# top + F.Cu + 0.05 mm. `verify` checks the assembly's export against it.
MODEL_LIFT = 0.05
TOL = 0.02  # mm: a vertex of the export against its computed place (float32 glTF in metres)

# Renders: KiCad looks down on the board's top, the robot's front up the image (robot x = KiCad -y).
# --rotate X,Y,Z turns the board about the screen's axes: the Z turn brings the front-left (+135) or
# front-right (-135) corner down the image, then -60 about X tips the image's top away from the viewer.
# Lower side lights and a camera light, so the daughterboards standing upright show their faces
# (the default top-heavy lighting leaves vertical faces dark).
LIGHTS = ["--light-camera", "0.45", "--light-side", "0.5", "--light-side-elevation", "30"]
RENDERS = {
    "iso-left": ["--rotate", "-60,0,135", "--perspective"],
    "iso-right": ["--rotate", "-60,0,-135", "--perspective"],
    "top": [],
}


# ---------------------------------------------------------------------------------------------
# frames


@dataclass(frozen=True)
class Stack:
    """A board's stackup through its thickness, in KiCad's 3D z: its exporters put the bottom of the
    layers between the outer copper at z 0."""

    f_mask: float
    f_cu: float
    inner: float
    b_cu: float
    b_mask: float

    @property
    def total(self) -> float:
        return self.f_mask + self.f_cu + self.inner + self.b_cu + self.b_mask

    @property
    def front(self) -> float:
        """The top face (KiCad's front: the wall board's sensor side, the encoder board's chip side)."""
        return self.inner + self.f_cu + self.f_mask

    @property
    def back(self) -> float:
        return -(self.b_cu + self.b_mask)

    @property
    def mid(self) -> float:
        return (self.front + self.back) / 2

    @property
    def model_plane(self) -> float:
        """Where z 0 of a front footprint's model sits."""
        return self.inner + self.f_cu + MODEL_LIFT


def stack(root: sexpr.Node) -> Stack:
    layers = root.child("setup").child("stackup").children("layer")
    t = {lay.atoms()[0]: float(lay.child("thickness").atoms()[0]) for lay in layers if lay.child("thickness")}
    names = [lay.atoms()[0] for lay in layers]
    inner = names[names.index("F.Cu") + 1 : names.index("B.Cu")]
    return Stack(t.get("F.Mask", 0.0), t["F.Cu"], sum(t.get(n, 0.0) for n in inner), t["B.Cu"], t.get("B.Mask", 0.0))


def upright(centre: tuple[float, float], facing: float, mid: float, top: float) -> Matrix:
    """A daughterboard's model frame (x = u, y = v, z = its KiCad 3D z) to the robot frame: standing
    on the main board's top (robot z `top`), its mid-plane through `centre`, its front facing
    `facing` degrees counter-clockwise from forward; u runs to the right seen from the front."""
    a = math.radians(facing)
    d = (math.cos(a), math.sin(a))  # the front's normal
    r = (-d[1], d[0])  # u: right seen from the front, the normal turned 90 deg counter-clockwise
    return [
        [r[0], 0.0, d[0], centre[0] - mid * d[0]],
        [r[1], 0.0, d[1], centre[1] - mid * d[1]],
        [0.0, 1.0, 0.0, top],
        [0.0, 0.0, 0.0, 1.0],
    ]


def robot_to_kicad(main: dict, st: Stack) -> Matrix:
    """The robot frame (spec/main.toml: x forward, y left, z up from the board's bottom) to KiCad's 3D
    frame of the main board (x = the sheet's x, y = minus the sheet's y, z 0 per `Stack`)."""
    ox, oy = main["kicad"]["origin_x"], main["kicad"]["origin_y"]
    return [[0.0, -1.0, 0.0, ox], [1.0, 0.0, 0.0, -oy], [0.0, 0.0, 1.0, st.back], [0.0, 0.0, 0.0, 1.0]]


def kicad_to_robot(st: Stack) -> Matrix:
    """An export with its user origin on the robot's (x = -y, y = x) back to the robot frame."""
    return [[0.0, 1.0, 0.0, 0.0], [-1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 1.0, -st.back], [0.0, 0.0, 0.0, 1.0]]


def _rz(deg: float) -> Matrix:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[c, -s, 0.0, 0.0], [s, c, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]


def _ry(deg: float) -> Matrix:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[c, 0.0, s, 0.0], [0.0, 1.0, 0.0, 0.0], [-s, 0.0, c, 0.0], [0.0, 0.0, 0.0, 1.0]]


def _rx(deg: float) -> Matrix:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[1.0, 0.0, 0.0, 0.0], [0.0, c, -s, 0.0], [0.0, s, c, 0.0], [0.0, 0.0, 0.0, 1.0]]


def _translate(x: float, y: float, z: float) -> Matrix:
    return [[1.0, 0.0, 0.0, x], [0.0, 1.0, 0.0, y], [0.0, 0.0, 1.0, z], [0.0, 0.0, 0.0, 1.0]]


def rigid_inverse(m: Matrix) -> Matrix:
    r = [[m[j][i] for j in range(3)] for i in range(3)]
    t = [-sum(r[i][k] * m[k][3] for k in range(3)) for i in range(3)]
    return [[*r[i], t[i]] for i in range(3)] + [[0.0, 0.0, 0.0, 1.0]]


def footprint_frame(fp: sexpr.Node, st: Stack) -> Matrix:
    """A front footprint's model frame to the board's KiCad 3D frame."""
    at = [float(a) for a in fp.child("at").atoms()]
    if fp.child("layer").atoms()[0] != "F.Cu":
        raise ValueError(f"{fp.prop('Reference')}: a joint footprint on the back")
    return mul(_translate(at[0], -at[1], st.model_plane), _rz(at[2] if len(at) > 2 else 0.0))


def model_matrix(rotate: tuple[float, float, float], offset: tuple[float, float, float]) -> Matrix:
    """KiCad's model transform: offset, then the model turned by Rz(-rz) Ry(-ry) Rx(-rx), degrees."""
    rx, ry, rz = rotate
    return mul(_translate(*offset), mul(_rz(-rz), mul(_ry(-ry), _rx(-rx))))


def kicad_rotation(m: Matrix) -> tuple[float, float, float]:
    """The (rx, ry, rz) KiCad writes for the rotation part of `m` (`model_matrix`'s inverse)."""
    b = math.asin(max(-1.0, min(1.0, -m[2][0])))
    if abs(math.cos(b)) > 1e-9:
        c, a = math.atan2(m[2][1], m[2][2]), math.atan2(m[1][0], m[0][0])
    else:  # gimbal lock: put the whole turn about z
        c, a = 0.0, math.atan2(-m[0][1], m[1][1])
    return tuple(_tidy(-math.degrees(v)) for v in (c, b, a))


def _tidy(deg: float) -> float:
    deg = round(deg, 6)
    return 180.0 if deg == -180.0 else deg + 0.0


# ---------------------------------------------------------------------------------------------
# placements


@dataclass(frozen=True)
class Placement:
    ref: str  # the main board's joint footprint
    path: str  # its instance path (spec/main.toml)
    board: str  # the daughterboard standing on it
    centre: tuple[float, float]  # robot frame: the daughterboard's mid-plane over this point
    facing: float  # degrees counter-clockwise from forward: the direction its front faces


def chip_facing(main: dict, side: str) -> float:
    """The encoder board's chip faces the side of its slot where spec/main.toml [encoder_boards]
    keeps the room for its chip-face parts: +90 (left, +y) or -90 (right, -y)."""
    y = main["encoder_slots"]["y"] * (1 if side == "left" else -1)
    _, _, y0, y1, _ = main["encoder_boards"][side]
    return 90.0 if y1 - y > y - y0 else -90.0


def placements(main: dict, root: sexpr.Node) -> list[Placement]:
    """Every daughterboard on the main board, from the spec, with the footprint that carries it."""
    refs = {fp.prop("Path"): fp.prop("Reference") for fp in root.children("footprint")}
    out = [Placement(refs[p], p, "wall", c, look) for p, (c, look) in sorted(mech.wall_joints(main).items())]
    sides = {main["encoder_slots"]["left_path"]: "left", main["encoder_slots"]["right_path"]: "right"}
    for p, c in sorted(mech.slots(main).items()):
        out.append(Placement(refs[p], p, "encoder", c, chip_facing(main, sides[p])))
    return out


@dataclass(frozen=True)
class Model:
    placement: Placement
    to_robot: Matrix  # the daughterboard's model frame to the robot frame
    offset: tuple[float, float, float]  # KiCad's (offset (xyz ...)) and (rotate (xyz ...)) on the footprint
    rotate: tuple[float, float, float]


def models(main: dict, root: sexpr.Node, stacks: dict[str, Stack]) -> list[Model]:
    fps = {fp.prop("Path"): fp for fp in root.children("footprint")}
    st = stacks["main"]
    out = []
    for p in placements(main, root):
        to_robot = upright(p.centre, p.facing, stacks[p.board].mid, st.total)
        local = mul(rigid_inverse(footprint_frame(fps[p.path], st)), mul(robot_to_kicad(main, st), to_robot))
        offset = tuple(round(local[i][3], 6) + 0.0 for i in range(3))
        out.append(Model(p, to_robot, offset, kicad_rotation(local)))
    return out


def attach(text: str, root: sexpr.Node, added: dict[str, tuple[Path, Model]]) -> str:
    """The board text with a model on each footprint `added` names (by reference)."""
    edits = []
    for fp in root.children("footprint"):
        ref = fp.prop("Reference")
        if ref not in added:
            continue
        path, m = added[ref]
        xyz = lambda v: " ".join(sexpr.fmt(x) for x in v)  # noqa: E731
        node = (
            f"\t\t(model {sexpr.quote(str(path))}\n"
            f"\t\t\t(offset\n\t\t\t\t(xyz {xyz(m.offset)})\n\t\t\t)\n"
            f"\t\t\t(scale\n\t\t\t\t(xyz 1 1 1)\n\t\t\t)\n"
            f"\t\t\t(rotate\n\t\t\t\t(xyz {xyz(m.rotate)})\n\t\t\t)\n"
            f"\t\t)\n"
        )
        at = text.rfind("\n", 0, fp.end - 1) + 1  # the footprint's closing line
        edits.append((at, at, node))
    if len(edits) != len(added):
        raise ValueError(f"footprints missing from the board: {sorted(added)}")
    return sexpr.splice(text, edits)


# ---------------------------------------------------------------------------------------------
# checks without KiCad: the daughterboards' pads meet the joints' pads


def pads(fp: sexpr.Node) -> list[tuple[str, tuple[float, float], list[str]]]:
    """(number, KiCad sheet position, layers) of each numbered pad."""
    at = [float(a) for a in fp.child("at").atoms()]
    t = math.radians(at[2] if len(at) > 2 else 0.0)
    out = []
    for pad in fp.children("pad"):
        num = pad.atoms()[0]
        if not num:
            continue
        px, py = (float(a) for a in pad.child("at").atoms()[:2])
        xy = (at[0] + px * math.cos(t) + py * math.sin(t), at[1] - px * math.sin(t) + py * math.cos(t))
        out.append((num, xy, pad.child("layers").atoms()))
    return out


def by_path(root: sexpr.Node, path: str) -> sexpr.Node:
    for fp in root.children("footprint"):
        if fp.prop("Path") == path:
            return fp
    raise KeyError(path)


def mating(main: dict, roots: dict[str, sexpr.Node], ms: list[Model], stacks: dict[str, Stack]) -> list[str]:
    """Where a daughterboard's joint pads miss the main board's: each wall header pin n (its row
    beside the face its pad is on) over the joint's hole n; each encoder tab pad n on the side of the
    slot and at the place along it of the slot's pad n."""
    problems = []
    daughters = {"wall": spec.load("wall"), "encoder": spec.load("encoder")}
    for m in ms:
        p, s = m.placement, daughters[m.placement.board]
        part = s["header"] if p.board == "wall" else s["connector"]
        joint = {n: mech.kicad_to_robot(main, xy) for n, xy, _ in pads(by_path(roots["main"], p.path))}
        a = math.radians(p.facing)
        d, r = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
        missed = []
        for n, xy, layers in pads(by_path(roots[p.board], part["path"])):
            u = xy[0] - s["kicad"]["origin_x"]
            side = 1 if "F.Cu" in layers else -1
            q = joint.get(n)
            if q is None:
                missed.append(f"pad {n} has no pad {n} on the main board")
            elif p.board == "wall":  # the header's long pins: rows half the row pitch either side of the mid-plane
                pin = apply(m.to_robot, (u, 0.0, stacks["wall"].mid + side * s["header"]["row_pitch"] / 2))
                if math.dist(pin[:2], q) > 0.05:
                    missed.append(f"pin {n} at ({pin[0]:.3f}, {pin[1]:.3f}), hole {n} at ({q[0]:.3f}, {q[1]:.3f})")
            else:
                tab = apply(m.to_robot, (u, 0.0, stacks["encoder"].mid + side * s["pcb"]["thickness"] / 2))
                along = [(v[0] - p.centre[0]) * r[0] + (v[1] - p.centre[1]) * r[1] for v in (tab, q)]
                across = (q[0] - p.centre[0]) * d[0] + (q[1] - p.centre[1]) * d[1]
                if abs(along[0] - along[1]) > 0.05 or across * side <= 0:
                    missed.append(
                        f"tab pad {n} ({'chip' if side > 0 else 'back'} face, {along[0]:+.3f} mm along the slot) "
                        f"against pad {n} ({'chip' if across > 0 else 'back'} side, {along[1]:+.3f} mm)"
                    )
        if missed:
            problems.append(
                f"{p.ref}: the {p.board} board, front facing {p.facing:+.0f} deg as the spec stands it, does not "
                f"mate with {p.ref} as the layout places it: " + "; ".join(missed)
            )
    return problems


# ---------------------------------------------------------------------------------------------
# checks on the export


STEP = 0.1  # mm: the clash checks sample each daughterboard's surface this finely


def surface(triangles, step: float = STEP) -> list[tuple[float, float, float]]:
    """Points over every triangle, no further apart than `step` along its edges."""
    out = []
    for a, b, c in triangles:
        n = max(1, math.ceil(max(math.dist(a, b), math.dist(b, c), math.dist(c, a)) / step))
        for i in range(n + 1):
            for j in range(n + 1 - i):
                s, t = i / n, j / n
                out.append(tuple(a[k] + s * (b[k] - a[k]) + t * (c[k] - a[k]) for k in range(3)))
    return out


def _bounds(points) -> tuple[tuple[float, ...], tuple[float, ...]]:
    return tuple(min(p[k] for p in points) for k in range(3)), tuple(max(p[k] for p in points) for k in range(3))


def _inverse(m: Matrix) -> Matrix:
    a = [row[:3] for row in m[:3]]
    det = (
        a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
        - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
        + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0])
    )
    inv = [
        [
            (
                a[(j + 1) % 3][(i + 1) % 3] * a[(j + 2) % 3][(i + 2) % 3]
                - a[(j + 1) % 3][(i + 2) % 3] * a[(j + 2) % 3][(i + 1) % 3]
            )
            / det
            for j in range(3)
        ]
        for i in range(3)
    ]
    t = [-sum(inv[i][k] * m[k][3] for k in range(3)) for i in range(3)]
    return [[*inv[i], t[i]] for i in range(3)] + [[0.0, 0.0, 0.0, 1.0]]


def verify(
    export: Path,
    references: dict[str, Path],
    main: dict,
    roots: dict[str, sexpr.Node],
    ms: list[Model],
    stacks: dict[str, Stack],
) -> tuple[list[str], list[str]]:
    """The assembly's glTF against the placements: (placement problems, clashes).

    Placement: each daughterboard's vertices, taken back through its computed placement, span what
    its own glTF spans (so KiCad turned and moved the model as computed). Clashes: a daughterboard
    vertex inside the main board (other than in a joint's hole or slot) or inside a main-board part's
    model box."""
    st, top = stacks["main"], stacks["main"].total
    back = kicad_to_robot(st)
    meshes = glb.GLB(export).meshes()
    ours = {m.placement.ref for m in ms}
    parts = [(mesh, mul(back, mesh.world)) for mesh in meshes if mesh.part and mesh.part not in ours]
    ref_bounds = {
        b: _bounds([v for mesh in glb.GLB(p).meshes() for v in mesh.vertices()]) for b, p in references.items()
    }
    wall, slots = spec.load("wall")["joint"], main["encoder_slots"]
    placed, clashes = [], []
    for m in ms:
        p = m.placement
        pts = [apply(back, v) for mesh in meshes if mesh.part == p.ref for v in mesh.vertices()]
        if not pts:
            placed.append(f"{p.ref}: no {p.board} board in the export")
            continue
        inv = rigid_inverse(m.to_robot)
        got, want = _bounds([apply(inv, v) for v in pts]), ref_bounds[p.board]
        worst = max(abs(g - w) for gs, ws in zip(got, want, strict=True) for g, w in zip(gs, ws, strict=True))
        if worst > TOL:
            placed.append(
                f"{p.ref}: the {p.board} board's model spans {_fmt(got)} in its own frame, its own export "
                f"{_fmt(want)} ({worst:.3f} mm off)"
            )
        if p.board == "wall":
            holes = [mech.kicad_to_robot(main, xy) for _, xy, _ in pads(by_path(roots["main"], p.path))]

            def open_(q, holes=holes):
                return any(math.dist(q[:2], h) <= wall["drill"] / 2 for h in holes)
        else:

            def open_(q, c=p.centre):
                half, rad = slots["length"] / 2 - slots["width"] / 2, slots["width"] / 2
                dx, dy = abs(q[0] - c[0]), abs(q[1] - c[1])
                return dy <= rad and (dx <= half or math.hypot(dx - half, dy) <= rad)

        tris = [tuple(apply(back, v) for v in tri) for mesh in meshes if mesh.part == p.ref for tri in mesh.triangles()]
        lo, hi = _bounds(pts)
        boxes = []
        for mesh, world in parts:
            corners = [
                apply(world, (x, y, z))
                for x in (mesh.lo[0], mesh.hi[0])
                for y in (mesh.lo[1], mesh.hi[1])
                for z in (mesh.lo[2], mesh.hi[2])
            ]
            clo, chi = _bounds(corners)
            if all(chi[k] >= lo[k] and clo[k] <= hi[k] for k in range(3)):
                boxes.append((mesh, _inverse(world), clo, chi))
        # only triangles reaching into the main board or a part's box need sampling
        near = [
            tri
            for tri in tris
            if min(v[2] for v in tri) < top
            or any(
                all(min(v[k] for v in tri) <= chi[k] and max(v[k] for v in tri) >= clo[k] for k in range(3))
                for _, _, clo, chi in boxes
            )
        ]
        samples = surface(near)
        inside = [q for q in samples if 0.01 < q[2] < top - 0.01 and not open_(q)]
        if inside:
            q = inside[0]
            clashes.append(
                f"{p.ref}: the {p.board} board reaches into the main board outside its joint, "
                f"e.g. at ({q[0]:.2f}, {q[1]:.2f}, {q[2]:.2f})"
            )
        eps = 0.01e-3  # 0.01 mm, in the part model's metres
        for mesh, to_mesh, clo, chi in boxes:
            for q in samples:
                if all(clo[k] <= q[k] <= chi[k] for k in range(3)) and all(
                    mesh.lo[k] + eps < c < mesh.hi[k] - eps for k, c in enumerate(apply(to_mesh, q))
                ):
                    clashes.append(
                        f"{p.ref}: the {p.board} board reaches into {mesh.part}'s model box at "
                        f"({q[0]:.2f}, {q[1]:.2f}, {q[2]:.2f})"
                    )
                    break
    return placed, clashes


def _fmt(b) -> str:
    return "u {:.3f}..{:.3f}, v {:.3f}..{:.3f}, z {:.3f}..{:.3f}".format(
        *(x for pair in zip(*b, strict=True) for x in pair)
    )


# ---------------------------------------------------------------------------------------------
# build


def _origin(s: dict) -> str:
    return f"{s['kicad']['origin_x']}x{s['kicad']['origin_y']}mm"


def build(work: Path, out: Path | None = None, full: bool = True) -> dict:
    """Write the board copy and the daughterboards' models into `work`; export the assembly (glTF,
    and with `full` the STEP and renders, into `out`) and check it. Returns what it found."""
    cli = kicad_cli()

    def k(*args):
        subprocess.run([cli, *args], check=True, capture_output=True)

    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    out = out or work
    out.mkdir(parents=True, exist_ok=True)
    main = spec.load("main")
    texts = {b: board_pcb(b).read_text() for b in ("main", *DAUGHTERS)}
    roots = {b: sexpr.parse(t) for b, t in texts.items()}
    stacks = {b: stack(r) for b, r in roots.items()}
    references, steps = {}, {}
    for b in DAUGHTERS:
        steps[b], references[b] = work / f"{b}.step", work / f"{b}.glb"
        origin = ["--user-origin", _origin(spec.load(b)), "-f"]
        k("pcb", "export", "step", *origin, "-o", str(steps[b]), str(board_pcb(b)))
        k("pcb", "export", "glb", *origin, "-o", str(references[b]), str(board_pcb(b)))
    ms = models(main, roots["main"], stacks)
    copy = work / "main.kicad_pcb"
    copy.write_text(attach(texts["main"], roots["main"], {m.placement.ref: (steps[m.placement.board], m) for m in ms}))
    pro = board_pcb("main").with_suffix(".kicad_pro")
    if pro.is_file():
        shutil.copy(pro, work / pro.name)
    robot = ["--user-origin", _origin(main), "-f"]
    gltf = out / "assembly.glb"
    looks = ["--include-tracks", "--include-pads", "--include-zones", "--include-silkscreen", "--include-soldermask"]
    k("pcb", "export", "glb", *robot, *(looks if full else []), "-o", str(gltf), str(copy))
    if full:
        k("pcb", "export", "step", *robot, "-o", str(out / "assembly.step"), str(copy))
        for name, extra in RENDERS.items():
            k(
                "pcb",
                "render",
                "--quality",
                "high",
                "--background",
                "opaque",
                "-w",
                "1600",
                "-h",
                "1200",
                "--zoom",
                "0.9",
                *LIGHTS,
                *extra,
                "-o",
                str(out / f"assembly-{name}.png"),
                str(copy),
            )
    placed, clashes = verify(gltf, references, main, roots, ms, stacks)
    return {"models": ms, "placed": placed, "clashes": clashes, "mating": mating(main, roots, ms, stacks)}


def run() -> int:
    missing = [b for b in ("main", *DAUGHTERS) if not has_layout(b)]
    if missing:
        print(f"assembly skipped: no layout for {', '.join(missing)}")
        return 0
    out = build_dir("main") / "review"
    found = build(build_dir("main") / "assembly", out)
    for m in found["models"]:
        p = m.placement
        print(
            f"  {p.ref} {p.board:7s} at ({p.centre[0]:.2f}, {p.centre[1]:.2f}), front facing {p.facing:+.0f} deg: "
            f"offset {m.offset}, rotate {m.rotate}"
        )
    for f in sorted(out.glob("assembly*")):
        print(f"  {f.relative_to(out.parents[2])}")
    for kind in ("mating", "clashes"):
        for line in found[kind]:
            print(f"warning: {line}")
    for line in found["placed"]:
        print(f"FAIL: {line}")
    return 1 if found["placed"] else 0
