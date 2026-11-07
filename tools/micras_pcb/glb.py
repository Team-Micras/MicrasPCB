"""Read the meshes of a KiCad glTF binary (kicad-cli pcb export glb): node names, world matrices and
vertices, in KiCad's 3D millimetres (x right, y up the sheet, z up from the board), not glTF's
metres with y up."""

from __future__ import annotations

import json
import struct
from array import array
from dataclasses import dataclass
from pathlib import Path

Matrix = list[list[float]]  # 4 x 4, row-major, column vectors

# glTF (metres, y up, z toward the viewer) to KiCad 3D (mm, z up, y up the sheet): x, -z, y.
GLTF_TO_KICAD: Matrix = [[1000.0, 0, 0, 0], [0, 0, -1000.0, 0], [0, 1000.0, 0, 0], [0, 0, 0, 1]]


def mul(a: Matrix, b: Matrix) -> Matrix:
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def apply(m: Matrix, p) -> tuple[float, float, float]:
    return tuple(m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + m[i][3] for i in range(3))


def _local(node: dict) -> Matrix:
    if "matrix" in node:
        m = node["matrix"]  # column-major
        return [[m[j * 4 + i] for j in range(4)] for i in range(4)]
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    sx, sy, sz = node.get("scale", [1, 1, 1])
    tx, ty, tz = node.get("translation", [0, 0, 0])
    r = [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]
    return [[r[i][0] * sx, r[i][1] * sy, r[i][2] * sz, t] for i, t in enumerate((tx, ty, tz))] + [[0, 0, 0, 1]]


@dataclass
class Mesh:
    part: str  # the reference of the footprint node it hangs from, "" for the board's own meshes
    world: Matrix  # mesh coordinates to KiCad 3D mm
    lo: tuple[float, float, float]  # mesh-coordinate bounds (glTF's accessor min / max)
    hi: tuple[float, float, float]
    _glb: GLB
    _primitives: list[dict]

    def vertices(self) -> list[tuple[float, float, float]]:
        """Every vertex, in KiCad 3D mm."""
        out = []
        for p in self._primitives:
            flat = self._glb.floats(p["attributes"]["POSITION"])
            out += [apply(self.world, flat[i : i + 3]) for i in range(0, len(flat), 3)]
        return out

    def triangles(self) -> list[tuple[tuple[float, float, float], ...]]:
        """Every triangle's corners, in KiCad 3D mm."""
        out = []
        for p in self._primitives:
            if p.get("mode", 4) != 4:
                continue
            flat = self._glb.floats(p["attributes"]["POSITION"])
            v = [apply(self.world, flat[i : i + 3]) for i in range(0, len(flat), 3)]
            idx = self._glb.indices(p["indices"]) if "indices" in p else range(len(v))
            out += [(v[idx[i]], v[idx[i + 1]], v[idx[i + 2]]) for i in range(0, len(idx) - 2, 3)]
        return out


class GLB:
    def __init__(self, path: Path):
        data = Path(path).read_bytes()
        n = struct.unpack("<I", data[12:16])[0]
        self.gltf = json.loads(data[20 : 20 + n])
        rest = data[20 + n :]
        self.bin = rest[8 : 8 + struct.unpack("<I", rest[:4])[0]] if len(rest) >= 8 else b""

    def floats(self, accessor: int) -> array:
        a = self.gltf["accessors"][accessor]
        view = self.gltf["bufferViews"][a["bufferView"]]
        if a["componentType"] != 5126 or a["type"] != "VEC3" or view.get("byteStride", 12) != 12:
            raise ValueError(f"accessor {accessor}: not packed float VEC3")
        start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        out = array("f")
        out.frombytes(self.bin[start : start + 12 * a["count"]])
        return out

    def indices(self, accessor: int) -> array:
        a = self.gltf["accessors"][accessor]
        view = self.gltf["bufferViews"][a["bufferView"]]
        code, size = {5121: ("B", 1), 5123: ("H", 2), 5125: ("I", 4)}[a["componentType"]]
        start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        out = array(code)
        out.frombytes(self.bin[start : start + size * a["count"]])
        return out

    def meshes(self) -> list[Mesh]:
        nodes, out = self.gltf["nodes"], []
        stack = [(i, GLTF_TO_KICAD, "") for i in self.gltf["scenes"][self.gltf.get("scene", 0)]["nodes"]]
        while stack:
            i, m, part = stack.pop()
            node = nodes[i]
            m = mul(m, _local(node))
            name = node.get("name") or ""
            if not part and name and not name.startswith("=>"):
                part = name
            if "mesh" in node:
                prims = self.gltf["meshes"][node["mesh"]]["primitives"]
                los = [self.gltf["accessors"][p["attributes"]["POSITION"]]["min"] for p in prims]
                his = [self.gltf["accessors"][p["attributes"]["POSITION"]]["max"] for p in prims]
                lo = tuple(min(v[k] for v in los) for k in range(3))
                hi = tuple(max(v[k] for v in his) for k in range(3))
                out.append(Mesh(part, m, lo, hi, self, prims))
            stack += [(c, m, part) for c in node.get("children", [])]
        return out
