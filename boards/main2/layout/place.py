"""Place every footprint of the second main board: the floorplan, then the passives packed by their pins.

    /usr/bin/python3 boards/main2/layout/place.py      # KiCad's Python (pcbnew), from the repo root

Every part goes on the top side (the board rides 1.2 mm off the floor, MicrasHardware
Board.bottom_z). The spec places what mates with the robot (spec/main2.toml: screw holes, encoder
slots, battery switch, USB-C, wall sensors); `ANCHORS` place the other large parts by function:

- rear, open up to the battery: the ESP32-S3-MINI-1 in the rear-left corner with its antenna on the
  rear edge (research/next-revision/README.md, ESP placement), the USB-C in the middle of the rear
  edge, the battery input (J1, F1, D15, Q6) and the 3V3_D buck in the rear-right corner by SW4;
- behind the drive blocks (the only room for 7 mm parts near the motors): both motor chokes with
  their 0 Ohm options and the motor connectors;
- under the left motor (spec [drive_blocks] left_motor, parts up to 2.7 mm) the left bridge, inboard
  of the right block the right bridge, each with its bulk capacitors; the shunts on the blocks'
  bodies (parts up to 1.5 mm);
- the IMU between the encoder slots, on the axle;
- the nose: the MCU, the wall-sensor channels and emitter sink, the LEDs, the buttons; beside the
  fan hole, the fan driver (left) and the DIP switch, buzzer and 3V3_A LDO (right).

Every other part is packed next to the pins it serves (`NEAR`, else the placed pads it shares a
signal net with): the nearest free spot, in any of the four rotations, whose courtyard overlaps no
other courtyard (the MCU's own parts in 45 degree steps, along its diagonal pin rows), stays on the
board and keeps out of the drive-block zones taller parts may not enter (part heights from the 3D
models). Of the spots within reach, the one whose pads lie nearest to the pins of their own nets
wins, so a part faces the pins it serves and its tracks do not cross. Room is kept free of parts
round the MCU for its escape vias, and in front of the bridges' logic and output pins for their
tracks (`STRIPS`). Deterministic: the same board gives the same placement.
"""

from __future__ import annotations

import json
import math
import struct
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import numpy as np
import pcbnew

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from micras_pcb import mech  # noqa: E402

PCB = ROOT / "boards/main2/layout/main2.kicad_pcb"
SPEC = tomllib.loads((ROOT / "spec/main2.toml").read_text())
S = {k: {kk: vv["value"] for kk, vv in v.items()} for k, v in SPEC.items()}
OX, OY = S["kicad"]["origin_x"], S["kicad"]["origin_y"]
RES = 0.1  # mm per raster cell
STEP = 0.25  # mm between candidate positions
GAP = 0.2  # mm kept between two courtyards on the raster
ESCAPE = 2.5  # mm round the MCU's courtyard kept for its pins' escapes: only its own supply parts
VIA_RING = 1.0  # mm round the MCU's courtyard kept free of every part: a ring of escape vias
# The bridges' logic pins (DRV8874 1-6: EN, PH, nSLEEP, nFAULT, VREF, IPROPI) and their outputs
# (8 OUT1, 10 OUT2, 0.8 mm paths) leave on F.Cu only, over the B.Cu VBAT pour
# (boards/main2/layout/route.py): a strip in front of each group, as deep as given and LANES_SIDE
# past its ends, is kept free of every part for their tracks
LOGIC = ("1", "2", "3", "4", "5", "6")
LANES = 1.6  # mm past the logic pins' outer ends: four 0.2 mm tracks at 0.14 mm
OUT_LANE = 3.0  # mm past an output pin: its 0.8 mm path clear of the charge pump's capacitors
STRIPS = {ref: [(LOGIC, LANES), (("8",), OUT_LANE), (("10",), OUT_LANE)] for ref in ("IC8", "IC9")}
LANES_SIDE = 0.4  # mm
# The STM32's VCAP2 and VCAP3 pins (49, 66) take their VCORE via on their own axis, past the 3V3_D
# island round the chip (boards/main2/layout/route.py, ESCAPE_REACH): a lane that deep in front of
# each is kept free of every part (C15 and C16, beside them, took it)
MCU_LANES = {"49": 2.2, "66": 2.2}  # mm past the pin tip
MCU_LANE_HALF = 0.45  # mm each side of the pin's axis
# The bridges' bulk capacitors pack behind the bridges' logic pins (robot x < BULK_X), the VBAT
# pour's side: ahead lie the IMU and the encoders' connectors, whose signals their VBAT tracks
# would cut and whose ground their ripple current would share (owner, 2026-10-19)
BULK = {"C83", "C84", "C85", "C86", "C87", "C111", "C92", "C93", "C94", "C95", "C96", "C112"}
BULK_X = -8.6  # mm, robot frame: route.py's VBAT pour edge
# those that find no room there go anywhere but this near the IMU and the encoders' connectors
BULK_AWAY = ("IC2", "EC1", "EC2")
BULK_GAP = 5.0  # mm

# Floorplan: reference -> (x, y, KiCad rotation), robot frame (x forward, y left, mm).
ANCHORS = {
    # rear-left: ESP32 module, antenna rearwards on the rear edge (rotation 180)
    "U13": (-33.2, 16.6, 180),
    # behind the blocks: chokes, their 0 Ohm options, motor connectors
    "L5": (-21.4, 4.1, 0),
    "L4": (-21.4, -4.6, 0),
    "R76": (-21.2, 11.25, 90),
    "R66": (-21.5, -11.0, 90),
    "M1": (-29.6, 3.9, 0),
    "M2": (-29.6, -4.4, 0),
    # rear middle: the USB-C's ESD array, between the connector and the ESP32
    "U6": (-35.8, 4.4, 0),
    # the battery path's diode to VSYS, by the input
    "D14": (-29.3, -12.0, 180),
    # rear-right: battery input and the 3V3_D buck
    "J1": (-31.5, -21.6, 90),
    "D15": (-31.5, -16.2, 90),
    "Q6": (-25.6, -21.6, 0),
    "F1": (-23.0, -15.5, 90),
    "IC7": (-43.4, -10.6, 0),
    "L3": (-36.0, -9.6, 0),
    # under the left motor: left bridge; inboard of the right block: right bridge
    "IC9": (-10.5, 4.5, 270),
    "IC8": (-10.5, -3.0, 270),
    "R75": (-9.0, 11.25, 90),
    "R65": (-9.0, -9.6, 90),
    # on the axle, between the encoder slots
    "IC2": (0.0, 0.0, 0),
    # current amplifiers beside the wheel notches' rear corners, VS pins outwards with their 100 nF
    # (SBOSA30D 8.3.1) between them and the board's side
    "U10": (-10.7, -20.55, 0),
    "C100": (-11.45, -24.45, 90),
    "U11": (-10.7, 20.55, 180),
    "C103": (-11.45, 24.45, 90),
    # nose; the MCU turned 45 degrees, as on the previous board: its pin rows face the diagonals,
    # their escapes fan out into widening wedges and the corners of its square stay free
    "IC1": (36.0, 0.0, -135),
    "D1": (51.25, 2.2, 180),
    "D2": (51.25, -2.2, 180),
    # each button on the side of the STM32 its pin faces: the user button (PA7, pin 26) on the
    # left, reset (NRST, pin 12) on the right; the other way round, both nets circled the chip
    "SW2": (35.9, 11.6, 180),
    "SW3": (33.2, -11.9, 180),
    "U12": (45.3, -1.85, 90),
    "Q9": (45.3, 1.95, 90),
    # beside the fan hole: fan driver (left); DIP switch, buzzer, analog LDO (right)
    "M3": (22.0, 20.6, 0),
    "L6": (14.0, 20.4, 0),
    "IC6": (16.8, 12.4, 0),
    "SW1": (25.0, -20.5, 90),
    "BZ1": (14.2, -20.5, 0),
    "U8": (25.0, -12.0, 0),
}

# Parts packed next to a given pad: reference -> (reference, pad number).
NEAR = {
    # the IMU's, between the encoder slots, before anything takes the room
    "C24": ("IC2", "8"),
    "C25": ("IC2", "5"),
    # decoupling at its pin (tests/test_layout.py DECOUPLING: nearest pad centres within 3 mm),
    # in the order they are packed: the 100 nF at each pin first, then the bulk
    # STM32 (AN5419 Table 2, Figure 5): one 100 nF per VDD pin, VDDA, VBAT, each VCAP; VDDA's
    # first, beside VDD's pin 9 on the same side
    "C10": ("IC1", "16"),
    "C12": ("IC1", "9"),
    "C13": ("IC1", "22"),
    "C14": ("IC1", "35"),
    "C15": ("IC1", "51"),
    "C16": ("IC1", "68"),
    "C8": ("IC1", "1"),
    "C7": ("IC1", "33"),
    "C6": ("IC1", "49"),
    "C5": ("IC1", "66"),
    # DRV8874 CVM1 (SLVSF66A Table 1), STSPIN958 CS and VDD (DS14341 Table 12), INA241 and
    # TLV9001 at VS
    # the bridges' charge pumps first (the flying capacitor across CPH-CPL, VCP's at VCP), then
    # VM's 100 nF beside them
    "C89": ("IC8", "13"),
    "C98": ("IC9", "13"),
    "C88": ("IC8", "12"),
    "C97": ("IC9", "12"),
    "C82": ("IC8", "11"),
    "C91": ("IC9", "11"),
    "C34": ("IC6", "28"),
    "C35": ("IC6", "29"),
    "C31": ("IC6", "13"),
    "C106": ("U12", "5"),
    "C101": ("U10", "7"),
    "C104": ("U11", "7"),
    # ADP7142 input and output (Rev H Table 2)
    "C80": ("U8", "6"),
    "C81": ("U8", "1"),
    # the rest of the STM32 supply: SMPS (pins 5-7), VDDA and VBAT 1 uF, bulk
    "L1": ("IC1", "5"),
    "C1": ("IC1", "6"),
    "C2": ("IC1", "6"),
    "C3": ("IC1", "7"),
    "C4": ("IC1", "7"),
    "C11": ("IC1", "16"),
    "R67": ("IC1", "16"),
    "C9": ("IC1", "1"),
    "C17": ("IC1", "51"),
    # bridges' bulk at VM; fan driver's bulk at VS
    "C83": ("IC8", "11"),
    "C84": ("IC8", "11"),
    "C87": ("IC8", "11"),
    "C111": ("IC8", "11"),
    "C85": ("IC8", "11"),
    "C86": ("IC8", "11"),
    "C92": ("IC9", "11"),
    "C93": ("IC9", "11"),
    "C96": ("IC9", "11"),
    "C112": ("IC9", "11"),
    "C94": ("IC9", "11"),
    "C95": ("IC9", "11"),
    "C36": ("IC6", "27"),
    "C99": ("IC6", "30"),
    # buck (DS13554: input capacitors at VIN, output at the inductor)
    "C52": ("IC7", "7"),
    "C53": ("IC7", "5"),
    "C54": ("IC7", "3"),
    "C56": ("L3", "2"),
    "C57": ("L3", "2"),
    # wall sensor channels: switch at the emitter's cathode, its resistor at the anode, the
    # receiver's load at the receiver
    "Q2": ("W1", "2"),
    "Q3": ("W2", "2"),
    "Q4": ("W3", "2"),
    "Q5": ("W4", "2"),
    "R13": ("W1", "1"),
    "R17": ("W2", "1"),
    "R21": ("W3", "1"),
    "R25": ("W4", "1"),
    "R14": ("W1", "4"),
    "R18": ("W2", "4"),
    "R22": ("W3", "4"),
    "R26": ("W4", "4"),
    "C26": ("R13", None),
    "C27": ("R17", None),
    "C28": ("R21", None),
    "C29": ("R25", None),
    # ESP, IMU, encoders, LEDs, others
    "C108": ("U13", "3"),
    "C107": ("U13", "3"),
    "C109": ("U13", "3"),
    "C69": ("EC1", None),
    "C70": ("EC1", None),
    "C71": ("EC2", None),
    "C72": ("EC2", None),
    "D5": ("D2", None),
    "R5": ("D5", None),
    "C18": ("D1", None),
    "C19": ("D2", None),
    "C79": ("SW1", None),
}

# Placement order of the packed parts that need a spot first (large or tied to one pad).
FIRST = ["U10", "U11", "Q8", "Q1", "R83", "D3", "R3", "R31"]

# Nets that do not pull a part towards a pad: supplies and ground reach everywhere through planes.
RAILS = {"GND", "GND_BAT", "3V3_D", "3V3_A", "VBAT", "VDDA"}


def to_kicad(x, y):
    return OX - y, OY - x


def to_robot(kx, ky):
    return OY - ky, OX - kx


def iu(v):
    return pcbnew.FromMM(v)


# ---------------------------------------------------------------------------------------------
# heights from the 3D models


def heights(board_file: Path) -> dict[str, float]:
    """Height of each part's 3D model above the board top (mm), from a KiCad GLB export."""
    with tempfile.TemporaryDirectory() as d:
        glb = Path(d) / "b.glb"
        subprocess.run(
            ["kicad-cli", "pcb", "export", "glb", "-f", "--no-board-body", "-o", str(glb), str(board_file)],
            check=True,
            capture_output=True,
        )
        b = glb.read_bytes()
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20 : 20 + n])
    nodes, acc = j["nodes"], j["accessors"]

    def mat(nd):
        if "matrix" in nd:
            return np.array(nd["matrix"]).reshape(4, 4).T
        m = np.eye(4)
        x, y, z, w = nd.get("rotation", [0, 0, 0, 1])
        r = np.array(
            [
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
            ]
        )
        m[:3, :3] = r @ np.diag(nd.get("scale", [1, 1, 1]))
        m[:3, 3] = nd.get("translation", [0, 0, 0])
        return m

    top: dict[str, float] = {}

    def walk(i, m, ref):
        nd = nodes[i]
        m = m @ mat(nd)
        name = nd.get("name") or ""
        if ref is None and name and not name.startswith("=>"):
            ref = name
        if "mesh" in nd and ref:
            for prim in j["meshes"][nd["mesh"]]["primitives"]:
                a = acc[prim["attributes"]["POSITION"]]
                lo, hi = a["min"], a["max"]
                c = np.array([[x, y, z, 1] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
                top[ref] = max(top.get(ref, -1.0), float((m @ c.T)[1].max()))  # glTF: y up, metres
        for c in nd.get("children", []):
            walk(c, m, ref)

    for r in j["scenes"][j.get("scene", 0)]["nodes"]:
        walk(r, np.eye(4), None)
    t = S["pcb"]["thickness"]
    return {ref: round(v * 1000 - t, 3) for ref, v in top.items()}


# ---------------------------------------------------------------------------------------------
# rasters (KiCad frame: column = x, row = y)

KX0, KY0 = OX - 25.5, OY - S["outline"]["front"] - 0.5
NX, NY = int(51.0 / RES), int((S["outline"]["front"] - S["outline"]["rear"] + 1.0) / RES)


def cell(kx, ky):
    return round((kx - KX0) / RES), round((ky - KY0) / RES)


def fill(polys: list[np.ndarray], shape=(NY, NX), origin=(KX0, KY0)) -> np.ndarray:
    """Even-odd fill of closed polygons (KiCad mm) on a raster of cell centres."""
    m = np.zeros(shape, bool)
    xs = origin[0] + (np.arange(shape[1]) + 0.5) * RES
    for poly in polys:
        if len(poly) < 3:
            continue
        lo, hi = poly.min(0), poly.max(0)
        r0 = max(int((lo[1] - origin[1]) / RES) - 1, 0)
        r1 = min(int((hi[1] - origin[1]) / RES) + 2, shape[0])
        a, b = poly, np.roll(poly, -1, 0)
        for r in range(r0, r1):
            yc = origin[1] + (r + 0.5) * RES
            cross = (a[:, 1] > yc) != (b[:, 1] > yc)
            if not cross.any():
                continue
            xi = a[cross, 0] + (yc - a[cross, 1]) * (b[cross, 0] - a[cross, 0]) / (b[cross, 1] - a[cross, 1])
            xi.sort()
            for x0, x1 in zip(xi[::2], xi[1::2], strict=False):
                m[r] ^= (xs >= x0) & (xs < x1)
    return m


def board_mask() -> np.ndarray:
    """Cells inside the outline and outside its holes, one cell in from every edge."""
    loops, cur, start = [], [], None
    for e in mech.main2_outline(S):  # loop after loop, each element following the last
        start = start or e.a
        cur += [to_kicad(*p) for p in mech.sample(e, 24)]
        if math.dist(e.b, start) < 1e-6:
            loops.append(np.array(cur))
            cur, start = [], None
    m = fill(loops)
    e = m.copy()
    e[1:] &= m[:-1]
    e[:-1] &= m[1:]
    e[:, 1:] &= m[:, :-1]
    e[:, :-1] &= m[:, 1:]
    return e


def zone_masks() -> list[tuple[float, np.ndarray]]:
    """The chassis zones, grown by GAP: a courtyard keeps clear of a zone it may not enter."""
    out = []
    for _name, (x0, x1, y0, y1, h) in mech.keepout_zones(S):
        x0, x1, y0, y1 = x0 - GAP, x1 + GAP, y0 - GAP, y1 + GAP
        corners = [to_kicad(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        out.append((h, fill([np.array(corners)])))
    return out


# ---------------------------------------------------------------------------------------------
# footprints


def courtyard(f) -> list[np.ndarray]:
    f.BuildCourtyardCaches()
    ps = f.GetCourtyard(pcbnew.F_CrtYd)
    if ps.IsEmpty():
        bb = f.GetBoundingBox(False)
        x0, y0, x1, y1 = (pcbnew.ToMM(v) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()))
        return [np.array([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])]
    out = []
    for i in range(ps.OutlineCount()):
        o = ps.Outline(i)
        out.append(np.array([(pcbnew.ToMM(o.CPoint(k).x), pcbnew.ToMM(o.CPoint(k).y)) for k in range(o.PointCount())]))
    return out


def set_at(f, x, y, rot):
    kx, ky = to_kicad(x, y)
    f.SetOrientationDegrees(rot)
    f.SetPosition(pcbnew.VECTOR2I(iu(kx), iu(ky)))


def local_mask(f, rot):
    """The courtyard's cells for this rotation, relative to the footprint origin's cell."""
    old_pos, old_rot = f.GetPosition(), f.GetOrientationDegrees()
    f.SetOrientationDegrees(rot)
    f.SetPosition(pcbnew.VECTOR2I(iu(KX0 + 100), iu(KY0 + 100)))  # on a cell corner
    polys = courtyard(f)
    allp = np.concatenate(polys)
    lo, hi = allp.min(0), allp.max(0)
    c0 = math.floor((lo[0] - KX0) / RES), math.floor((lo[1] - KY0) / RES)
    c1 = math.ceil((hi[0] - KX0) / RES), math.ceil((hi[1] - KY0) / RES)
    shape = (c1[1] - c0[1], c1[0] - c0[0])
    m = fill(polys, shape, (KX0 + c0[0] * RES, KY0 + c0[1] * RES))
    f.SetOrientationDegrees(old_rot)
    f.SetPosition(old_pos)
    origin_cell = (round(100 / RES), round(100 / RES))
    return m, (c0[0] - origin_cell[0], c0[1] - origin_cell[1])


def grow(m: np.ndarray, d: float) -> np.ndarray:
    """The cells within about d mm of m: 4- and 8-neighbour steps in turn, near a round growth."""
    for k in range(round(d / RES)):
        g = m.copy()
        g[1:] |= m[:-1]
        g[:-1] |= m[1:]
        g[:, 1:] |= m[:, :-1]
        g[:, :-1] |= m[:, 1:]
        if k % 2:
            g[1:, 1:] |= m[:-1, :-1]
            g[:-1, :-1] |= m[1:, 1:]
            g[1:, :-1] |= m[:-1, 1:]
            g[:-1, 1:] |= m[1:, :-1]
        m = g
    return m


def stamp(occ, m, off, cx, cy):
    x0, y0 = cx + off[0], cy + off[1]
    occ[y0 : y0 + m.shape[0], x0 : x0 + m.shape[1]] |= m


def fits(free, m, off, cx, cy):
    x0, y0 = cx + off[0], cy + off[1]
    if x0 < 0 or y0 < 0 or y0 + m.shape[0] > free.shape[0] or x0 + m.shape[1] > free.shape[1]:
        return False
    return not (m & ~free[y0 : y0 + m.shape[0], x0 : x0 + m.shape[1]]).any()


def mcu_lanes(fps) -> np.ndarray:
    """The lanes in front of the STM32's VCAP pins (MCU_LANES), along each pin's axis."""
    f = fps["IC1"]
    c = f.GetPosition()
    cx, cy = pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)
    polys = []
    for num, depth in MCU_LANES.items():
        p = f.FindPadByNumber(num)
        q = p.GetPosition()
        ax, ay = pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)
        sz = p.GetSize()
        half = pcbnew.ToMM(max(sz.x, sz.y)) / 2
        t = math.radians(p.GetOrientationDegrees()) + (0 if sz.x >= sz.y else math.pi / 2)
        u = (math.cos(t), -math.sin(t))
        if u[0] * (ax - cx) + u[1] * (ay - cy) < 0:
            u = (-u[0], -u[1])
        v = (-u[1], u[0])
        a0, a1 = half, half + depth
        polys.append(
            np.array(
                [
                    (ax + u[0] * d + v[0] * s_, ay + u[1] * d + v[1] * s_)
                    for d, s_ in ((a0, -MCU_LANE_HALF), (a1, -MCU_LANE_HALF), (a1, MCU_LANE_HALF), (a0, MCU_LANE_HALF))
                ]
            )
        )
    return fill(polys)


def lanes(fps) -> np.ndarray:
    """The strips kept for the bridges' pins' tracks (STRIPS), out from each group's pads."""
    m = np.zeros((NY, NX), bool)
    for ref, (nums, depth) in ((r, g) for r, gs in STRIPS.items() for g in gs):
        f = fps[ref]
        pads = [p for p in f.Pads() if p.GetNumber() in nums]
        pts = []
        for p in pads:
            bb = p.GetBoundingBox()
            pts += [
                (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop())),
                (pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())),
            ]
        (x0, y0), (x1, y1) = np.min(pts, 0), np.max(pts, 0)
        c = f.GetPosition()
        cx, cy = pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)
        # outwards: the side of the row away from the chip's centre, along the pins (a pin
        # taller than wide runs in y, its row in x)
        bb = pads[0].GetBoundingBox()
        if bb.GetHeight() > bb.GetWidth():
            x0, x1 = x0 - LANES_SIDE, x1 + LANES_SIDE
            y0, y1 = (y0 - depth, y1) if (y0 + y1) / 2 < cy else (y0, y1 + depth)
        else:
            y0, y1 = y0 - LANES_SIDE, y1 + LANES_SIDE
            x0, x1 = (x0 - depth, x1) if (x0 + x1) / 2 < cx else (x0, x1 + depth)
        m |= fill([np.array([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])])
    return m


def main():
    board = pcbnew.LoadBoard(str(PCB))
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    by_path = {f.GetFieldText("Path"): f for f in board.GetFootprints()}
    h = heights(PCB)

    placed: dict[str, tuple[float, float, int]] = {}
    for sec in S.values():
        if isinstance(sec, dict) and "path" in sec and "x" in sec:
            f = by_path[sec["path"]]
            placed[f.GetReference()] = (sec["x"], sec["y"], sec["rotation"])
    for path, (x, y) in mech.slots(S).items():
        placed[by_path[path].GetReference()] = (x, y, 0)
    placed.update(ANCHORS)

    for f in fps.values():
        if f.IsFlipped():
            f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    for ref, (x, y, r) in placed.items():
        set_at(fps[ref], x, y, r)

    inside = board_mask()
    zones = zone_masks()
    occ = np.zeros_like(inside)
    for ref in placed:
        for poly in courtyard(fps[ref]):
            occ |= fill([poly])

    mcu = fill(courtyard(fps["IC1"]))
    ring = grow(mcu, VIA_RING) | lanes(fps) | mcu_lanes(fps)
    escape = grow(mcu, ESCAPE)
    rear = np.zeros_like(inside)
    rear[max(0, round((OY - BULK_X - KY0) / RES)) :] = True
    away = np.zeros_like(inside)
    for ref in BULK_AWAY:
        for poly in courtyard(fps[ref]):
            away |= fill([poly])
    away = ~grow(away, BULK_GAP)

    def free_for(ref, area=None):
        # other courtyards grown by GAP: the raster samples cell centres, so it would miss an
        # overlap thinner than a cell
        grown = occ.copy()
        for _ in range(round(GAP / RES)):
            g = grown.copy()
            g[1:] |= grown[:-1]
            g[:-1] |= grown[1:]
            g[:, 1:] |= grown[:, :-1]
            g[:, :-1] |= grown[:, 1:]
            grown = g
        free = inside & ~grown & ~ring
        if NEAR.get(ref, (None,))[0] != "IC1":
            free &= ~escape
        if area is not None:
            free &= area
        hh = h.get(ref, 0.0)
        for zh, zm in zones:
            if hh > zh + 1e-6:
                free &= ~zm
        return free

    def pad_xy(p):
        q = p.GetPosition()
        return pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)

    def targets(ref):
        """Pads of placed parts this part should sit by, each (x, y, net)."""
        f = fps[ref]
        if ref in NEAR:
            other, pad = NEAR[ref]
            if other not in placed:
                return []  # waits for its part
            if not pad:
                return [(*pad_xy(fps[other].Pads()[0]), None)]
            # the pin, and the part's other pins on this part's signal nets
            nets = {p.GetNetname() for p in f.Pads() if p.GetNetname() and p.GetNetname() not in RAILS}
            pads = [p for p in fps[other].Pads() if p.GetNumber() == pad or p.GetNetname() in nets]
            return [(*pad_xy(p), p.GetNetname()) for p in pads if p.GetNetname()]
        nets = {p.GetNetname() for p in f.Pads() if p.GetNetname() and p.GetNetname() not in RAILS}
        out = []
        for r in placed:
            if r == ref:
                continue
            for p in fps[r].Pads():
                if p.GetNetname() in nets:
                    out.append((*pad_xy(p), p.GetNetname()))
        return out

    order = [r for r in [*NEAR, *FIRST] if r in fps and r not in placed]
    order = list(dict.fromkeys(order))
    rest = sorted(
        (r for r in fps if r not in placed and r not in order),
        key=lambda r: (-sum(1 for p in fps[r].Pads()), r),
    )
    pending = order + rest
    masks: dict[tuple[str, int], tuple] = {}
    unplaced = []
    while pending:
        # the next part: the first in order with a target among the placed parts
        ref = next((r for r in pending if targets(r)), pending[0])
        pending.remove(ref)
        f = fps[ref]
        tg = targets(ref)
        if not tg:
            unplaced.append(ref)
            continue
        if ref in NEAR and NEAR[ref][1] is None:
            o = fps[NEAR[ref][0]].GetPosition()
            tx, ty = pcbnew.ToMM(o.x), pcbnew.ToMM(o.y)
        else:
            tx, ty = np.mean([t[:2] for t in tg], 0)
        pin = None
        if ref in NEAR and NEAR[ref][1] is not None:
            q = next(q for q in fps[NEAR[ref][0]].Pads() if q.GetNumber() == NEAR[ref][1])
            if any(p.GetNetname() == q.GetNetname() for p in f.Pads()):
                pin = (pad_xy(q), q.GetNetname())
        # a bulk capacitor behind the bridges if it fits there, else away from the IMU
        frees = [free_for(ref, rear), free_for(ref, away)] if ref in BULK else [free_for(ref)]
        for free in frees:
            best, first = None, None
            for radius in np.arange(0, 50, STEP):
                if first is not None and radius > first + 2.0:
                    break  # the cheapest spot within 2 mm of the nearest free one
                n = max(8, int(2 * math.pi * radius / STEP)) if radius else 1
                for k in range(n):
                    a = 2 * math.pi * k / n
                    cx, cy = cell(tx + radius * math.cos(a), ty + radius * math.sin(a))
                    for rot in range(0, 360, 45 if NEAR.get(ref, (None,))[0] == "IC1" else 90):
                        if (ref, rot) not in masks:
                            masks[(ref, rot)] = local_mask(f, rot)
                        m, off = masks[(ref, rot)]
                        if not fits(free, m, off, cx, cy):
                            continue
                        first = radius if first is None else first
                        # cost: the part's signal pads to their targets, then the distance moved
                        set_at(f, *to_robot(KX0 + cx * RES, KY0 + cy * RES), rot)
                        cost = radius * 0.25
                        if pin is not None:
                            # a part tied to a pin: its pad on the pin's net, nearest to the pin
                            cost += min(math.dist(pad_xy(p), pin[0]) for p in f.Pads() if p.GetNetname() == pin[1])
                        # each signal pad to the nearest target on its own net (any, if none): a
                        # part turns so its pads face their own pins, and its tracks do not cross
                        for p in f.Pads():
                            if p.GetNetname() and p.GetNetname() not in RAILS:
                                own = [t[:2] for t in tg if t[2] == p.GetNetname()] or [t[:2] for t in tg]
                                cost += min(math.dist(pad_xy(p), t) for t in own)
                        if best is None or cost < best[0] - 1e-9:
                            best = (cost, cx, cy, rot)
            if best is not None:
                break
        if best is None:
            unplaced.append(ref)
            continue
        _, cx, cy, rot = best
        x, y = to_robot(KX0 + cx * RES, KY0 + cy * RES)
        placed[ref] = (round(x, 3), round(y, 3), rot)
        set_at(f, *placed[ref])
        m, off = masks[(ref, rot)]
        stamp(occ, m, off, cx, cy)

    board.Save(str(PCB))
    print(f"placed {len(placed)} footprints; not placed: {unplaced or 'none'}")
    return 0 if not unplaced else 1


if __name__ == "__main__":
    sys.exit(main())
