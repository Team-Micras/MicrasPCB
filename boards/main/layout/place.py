"""Place every footprint of the main board: the floorplan, then the passives packed by their pins.

    /usr/bin/python3 boards/main/layout/place.py      # KiCad's Python (pcbnew), from the repo root

Every part goes on the top side (the board rides 1.2 mm off the floor, MicrasHardware
Board.bottom_z). The spec places what mates with the robot or the outline (spec/main.toml: screw
holes, encoder slots, wall slots, battery switch, ESP32 module, the STM32); `ANCHORS` place the other
large parts by function:

- rear, open up to the battery: the ESP32-C5-MINI-1 in the rear-right corner (spec [u13]), its
  antenna over the board's notch there (spec [antenna_notch]); the battery input (J1, F1, D15, Q6)
  in the rear-left corner by SW4; the flashing pads J2 on the rear edge behind the right motor
  connector, 10.5 mm from the antenna's open end (at least 10);
- behind the drive blocks (the only room for 5-7.7 mm parts near the motors): both motor chokes and
  the motor connectors, the chokes' pads clear of the drive blocks' outlines on the silkscreen;
- the bridges inside the drive blocks' zones between the wheels, each with its shunt and its
  current amplifier (zones up to 2.1 and 3.7 mm); the bulk capacitors where 2.5 mm parts fit (the
  tab, behind the blocks, outside the fan ring);
- the IMU between the encoder slots, on the axle;
- the nose: the MCU (spec [ic1]) with its capacitors in its 2.5 mm room, the LED row at the front
  edge, the emitter sink and the user button (left pocket), the DIP switch, reset and the SWD header
  (right pocket); in front of the wheels, the fan driver (left), and the 3V3_D buck and the buzzer
  (right). Inside the fan ring (spec [fan_ring]) only parts up to its max_part_height.

`HAND` fixes the STM32's capacitors and SMPS inductor, the parts the routing kept round the bridges,
the fan driver, the IMU and the encoders, as ANCHORS fix theirs.

Every other part is packed next to the pins it serves (`NEAR`, else the placed pads it shares a
signal net with): the nearest free spot, in any of the four rotations, whose courtyard overlaps no
other courtyard (the MCU's own parts in 45 degree steps, along its diagonal pin rows), stays on the
board, keeps out of the drive-block zones and the fan ring taller parts may not enter (part
heights from the 3D models) and keeps its pads off the spec's silkscreen lines. Of the spots within reach, the one whose pads lie nearest to the pins of their own nets
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
from micras_pcb import mech, sexpr  # noqa: E402

PCB = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "boards/main/layout/main.kicad_pcb"
SPEC = tomllib.loads((ROOT / "spec/main.toml").read_text())
S = {k: {kk: vv["value"] for kk, vv in v.items()} for k, v in SPEC.items()}
OX, OY = S["kicad"]["origin_x"], S["kicad"]["origin_y"]
RES = 0.1  # mm per raster cell
SILK_MARGIN = 0.15  # mm past the test's clearance (the raster's error)
CASE_UNDER = 3.0  # mm: the parts a sensor's case (sleeves round the lenses, no base) may stand over
FINGER = {"SW1", "SW2", "SW3"}  # the switches: under no sensor case and in no view, for a finger
SENSOR_ZONES: list[np.ndarray] = []  # the cases' and corridors' cells (zone_masks())
VIEW_MARGIN = 0.5  # mm under a sensor's view corridor
STEP = 0.25  # mm between candidate positions
GAP = 0.2  # mm kept between two courtyards on the raster
ESCAPE = 2.5  # mm round the MCU's courtyard kept for its pins' escapes: only its own supply parts
VIA_RING = 1.0  # mm round the MCU's courtyard kept free of every part: a ring of escape vias
# The bridges' logic pins (DRV8874 1-6: EN, PH, nSLEEP, nFAULT, VREF, IPROPI) and their outputs
# (8 OUT1, 10 OUT2, 0.8 mm paths) leave on F.Cu only, over the B.Cu VBAT pour
# (boards/main/layout/route.py): a strip in front of each group, as deep as given and LANES_SIDE
# past its ends, is kept free of every part for their tracks
LOGIC = ("1", "2", "3", "4", "5", "6")
LANES = 1.6  # mm past the logic pins' outer ends: four 0.2 mm tracks at 0.14 mm
OUT_LANE = 3.0  # mm past an output pin: its 0.8 mm path clear of the charge pump's capacitors
STRIPS = {ref: [(LOGIC, LANES), (("8",), OUT_LANE), (("10",), OUT_LANE)] for ref in ("IC8", "IC9")}
LANES_SIDE = 0.4  # mm
# A lane in front of an STM32 pin, kept free of every part for its via on its own axis: none, the
# VCAP pins' capacitors (C5, C6) sit radially on their pins' normals and take their VCORE vias
MCU_LANES: dict[str, float] = {}  # pin -> mm past the pin tip
MCU_LANE_HALF = 0.45  # mm each side of the pin's axis
# The bridges' bulk capacitors pack behind the bridges' logic pins (robot x < BULK_X), the VBAT
# pour's side: ahead lie the IMU and the encoders' connectors, whose signals their VBAT tracks
# would cut and whose ground their ripple current would share (owner, 2026-10-19)
BULK = {"C83", "C84", "C87", "C111", "C92", "C93", "C96", "C112"}
BULK_X = -8.6  # mm, robot frame: route.py's VBAT pour edge
# those that find no room there go anywhere but this near the IMU and the encoders' connectors
BULK_AWAY = ("IC2", "EC1", "EC2")
BULK_GAP = 5.0  # mm

# Floorplan: reference -> (x, y, KiCad rotation), robot frame (x forward, y left, mm).
ANCHORS = {
    # behind the drive blocks (the only room for 5-7.7 mm parts near the motors): the right choke L4
    # against the right block's zones, the left one L5 behind it to the left, its pads clear of the
    # left block's outline (spec silkscreen); the motor connectors behind each choke
    "L4": (-21.4, -1.95, 0),
    "M2": (-33.73, -3.72, 180),
    "L5": (-26.4, 6.4, 0),
    "M1": (-33.73, 3.59, 180),
    # rear-left, beside SW4: the battery connector, its fuse and switch packed at its pins (NEAR)
    "J1": (-28.83, 21.25, 90),
    # the flashing pads on the rear edge behind M2, reachable from the robot's rear, pin 1 10.5 mm
    # from the antenna's open end (at least 10)
    "J2": (-27.51, -5.0, 270),
    # the current amplifiers beside their shunts, inside the drive blocks' zones (1.34 mm parts)
    "U10": (-16.5, -9.5, 0),
    "U11": (-15.85, 10.4, 0),
    # the bridges, the right one clear of the left block's outline at y 0 (spec silkscreen)
    "IC9": (-10.5, 4.5, 270),
    "IC8": (-10.5, -3.35, 270),
    # the shunts along x; R75 turned so its OUT1 pad faces IC9 (front) and its own pad the choke L5 (rear),
    # neither force lead under the part; R65's OUT1 pad behind, its own pad in front
    "R75": (-9.0, 11.25, -90),
    "R65": (-9.0, -9.6, 90),
    # on the axle, between the encoder slots (owner, 2026-11-03)
    "IC2": (0.0, 0.0, 0),
    # the front LED row, 5.9 mm behind the committed board's (the front edge moved 53.5 -> 47.6), in
    # its arrangement (owner, 2026-11-03): D1, D2, D5, R5 as on that board, D4/R4 at their v1 spots
    "D1": (45.35, 1.8, 0),
    "D2": (45.35, -1.8, 0),
    "D5": (45.35, -5.4, -90),
    "R5": (45.35, -6.85, -90),
    "D4": (45.35, 5.4, -90),
    "R4": (45.35, 6.85, 90),
    # the nose's left pocket, in front of W1 under its case (parts up to 3.0 mm): the emitter sink
    # (Wall_Emitter_Set leaves the STM32's front-left face)
    "U12": (39.5, 15.0, 90),
    # beside the fan hole, in front of the left wheel: the fan driver turned so its power side (OUT1,
    # VS, OUT2) faces the board's edge and its logic pins the fan hole (DS14341 Fig. 23), its VS
    # capacitors in front of the VS pins, its choke behind it, its connector in front
    "IC6": (20.7, 17.5, 90),
    "C34": (19.0, 22.95, -90),
    "C35": (22.4, 22.95, 90),
    "M3": (28.65, 21.4, 90),
    "L6": (14.0, 20.5, 0),
    # in front of the right wheel: the 3V3_D buck's inductor (beside the STM32, which it feeds; the
    # buck itself in HAND) and the DIP switch at the side edge, out of the sensors' cases and views for
    # a finger (pins 2, 3, 10, 11 on the STM32's front-right face); the buttons are packed out of them
    # too (FINGER)
    "L3": (14.03, -20.85, 0),
    "SW1": (26.97, -20.5, 90),
    # the buttons beside IC1, each on the side of the STM32 its pin faces (the user button, PA3 pin 20,
    # left; reset, NRST pin 12, right), out of the fan ring and the sensors' cases and views
    "SW2": (28.325, 13.81, 180),
    "SW3": (28.0, -13.5, 180),
    # the buzzer in the nose's right pocket, under W4's case (sleeves round the lenses: parts up to 3.0 mm)
    "BZ1": (38.5, -19.8, 0),
    # the SWD header on the rear edge behind M2, beside J2 (SWDIO and SWCLK run to U13 there anyway)
    "SWD1": (-41.96, 12.61, 90),
    # two of the bridges' VBAT bulk capacitors (2.5 mm) at the nose's corners beside W2/W3, under the
    # sensors' views: the only room left for them (the rest pack behind the drive blocks and in the tab)
    "C112": (43.3, 9.85, 180),
    "C96": (43.3, -9.95, 180),
    # the 3V3_A LDO's input capacitor in the last 2.5 mm spot by the right wheel, the LDO at it
    "C80": (12.4, -15.0, 90),
    # the ESP32's 22 uF and 100 nF in front of the module, within 15.5 mm of its 3V3 pin (pin 3, on
    # its edge row); the module decouples its chip itself (datasheet Figure 8-1)
    "C109": (-20.2, -19.3, 0),
    "C108": (-20.3, -22.0, 0),
}

# Parts fixed by hand: the STM32's capacitors, each on its pin's face in the 2.5 mm room between the
# chip and the wall slots (spec [ic1] block) or the fan hole, at least 1 mm off its pins for their
# escape vias (VIA_RING): the 100 nF radial (one pad on the pin's normal) or along the face,
# VDDSMPS's 10 uF (C1) and 4.7 uF (C2), VFBSMPS's 10 uF (C3 by the right vertex, C4 by the rear
# tip, past the 3V3_D island on In2's VCORE band); and the parts the routing kept round the
# bridges (their charge pumps and VM capacitors) and the IMU and encoders.
HAND = {
    # the SMPS inductor along the front-right face in the capacitor row (LX pad on pin 5's axis, VCORE pad on
    # VFBSMPS pin 7's), VDDSMPS's 4.7 uF past the right vertex, the row's other capacitors slid along it
    "L1": (35.772, -5.063, -45),
    "C8": (33.884, -6.979, 135),
    "C2": (34.015, -8.234, 135),
    "C12": (37.667, -3.338, -45),
    "C1": (32.845, -9.405, -135),
    "C3": (30.724, -8.202, 135),
    "C10": (38.919, -1.945, -45),
    # VDDA's 1 uF beside C10, off the tip's front-left so Wall_Sensor_2 crosses LED_ARGB's lane there on F.Cu
    "C11": (39.85, -2.7, 135),
    "C102": (40.385, -0.715, -45),
    "C13": (37.738, 3.125, -135),
    "C7": (33.955, 6.908, 45),
    "C14": (30.045, 7.114, 45),
    "C6": (26.686, 3.755, 45),
    "C15": (25.944, 3.012, 45),
    "C5": (29.338, -6.392, 135),
    "C16": (30.045, -7.113, 135),
    "C4": (26.75, -4.37, 135),
    # each bridge's VM, VCP and CPH-CPL capacitors in a column behind its rear pins, under the 1.0 mm OUT2 path
    "C82": (-15.44, -2.47, 90),
    "C88": (-15.38, -3.41, -90),
    "C89": (-15.4, -4.85, 0),
    "C91": (-15.44, 5.38, 90),
    "C97": (-15.38, 4.44, -90),
    "C98": (-15.4, 3.0, 0),
    "C103": (-18.12, 8.55, 180),
    # the right bridge's references in front of its logic pins, out of OUT1's path round them
    "R61": (-3.09, -0.8, 90),
    "R86": (-19.55, -13.5, 180),
    # the fan driver: pump and boot capacitors at the rear pins, the sense resistor at the LSS pins 23-24
    # (DS14341 section 8), the reference divider and the enable pull-up inside the fan ring (0.35 mm parts)
    "C32": (16.6, 17.0, -90),
    "C33": (15.8, 15.3, 90),
    "R31": (25.22, 16.33, 0),
    "R30": (26.9, 17.5, 0),
    "R27": (23.75, 10.2, 90),
    "R28": (21.3, 11.2, 0),
    "R29": (22.3, 11.0, 0),
    "C99": (33.1, 10.5, 180),
    # the 3V3_D buck turned so its SW pin (1) is the corner nearest L3's SW pad, the SW node a short F.Cu
    # path with no via (DS13554 Fig. 32: L1 at U1's SW pin); BOOT's and VCC's capacitors under the
    # SW/BOOT/VCC row, the 22 uF C56 between them and the board's edge on L3's output; the input
    # capacitor C53 on the VIN row, across VIN (pin 7) and PGND (pin 8) (DS13554 Fig. 32-33: the input
    # capacitor's ground at PGND), inside the fan ring (its 1.25 mm sets [fan_ring] max_part_height);
    # the 3V3_A LDO's output capacitor C81 beside it, toward the fan hole, within reach of U8's VOUT pins
    "IC7": (20.31, -17.5, 180),
    "C55": (19.03, -21.8, -90),
    "C54": (20.98, -21.8, -90),
    "C56": (19.1, -23.38, -90),
    "C53": (19.04, -12.79, 90),
    "C81": (17.7, -10.33, 0),
    # the battery switch's gate-source capacitor, its GND_BAT pad up on the pour's side of the gate chain
    "C58": (-33.0, 14.6, 0),
    # the current sense dividers off the fan hole's lanes, the left by the fan driver and the right
    # behind the SMPS row; VBAT's 1 uF past the left vertex; BOOT0's pull-down and NRST's filter by
    # the rear-right face (the lanes round the hole take the room at the rear tip)
    "R79": (17.8, 12.4, 90),
    # the left current's ADC filter capacitor beside its R_iso (R79): the front-left pad row's strip and
    # the face outside it are full (layout README, Front-left face)
    "C105": (18.31, 11.2, 90),
    # the 3V3_A LDO's soft-start capacitor at its SS pin, outside the fan ring's silk line
    "C115": (10.75, -12.75, 90),
    "R78": (22.0, -11.0, 90),
    "C17": (31.0, 8.0, 45),
    "R42": (26.163, -7.319, 135),
    "C60": (26.884, -8.04, -45),
    "C21": (28.4, -9.8, 90),
    # the ESP32-C5's EN RC and BOOT pull-up off the rear, where the right motor's paths pass under J2
    "R89": (-20.0, -15.6, 180),
    "C110": (-23.9, -7.5, 0),
    "R90": (-16.7, -23.7, 270),
    "C24": (-0.8, -2.9, 180),
    "C25": (-2.6, 0.6, 90),
    "C69": (-0.7, -4.5, 90),
    "C70": (1.3, -4.5, 90),
    "C71": (0.0, 4.4, 90),
    "R73": (-4.7, 4.1, 180),
    "R63": (-3.9, -3.4, 180),
    "R64": (-3.3, -1.8, 90),
    "R71": (-8.1, 7.9, -90),
    "R60": (5.4, -0.2, -90),
}

# Parts packed next to a given pad: reference -> (reference, pad number).
NEAR = {
    # in the order they are packed: the parts tied to one pin first
    "L1": ("IC1", "5"),
    "C102": ("IC1", "14"),
    "C11": ("IC1", "16"),
    "C34": ("IC6", "28"),
    "C35": ("IC6", "29"),
    "C99": ("IC6", "30"),
    "F1": ("J1", "1"),
    "Q6": ("J1", "2"),
    "D15": ("F1", "2"),
    # buck (DS13554: input capacitors at VIN, output at the inductor), its supply diodes
    "C53": ("IC7", "5"),
    "C52": ("IC7", "7"),
    "C54": ("IC7", "3"),
    "C55": ("IC7", "2"),
    "C56": ("L3", "2"),
    "C57": ("L3", "2"),
    "D14": ("C52", "2"),
    "D17": ("C53", "2"),
    # INA241 at VS (SBOSA30D 8.3.1)
    "C100": ("U10", "6"),
    "C103": ("U11", "6"),
    # the emitter sink: the switch at the op-amp's output, its shunt at the switch
    "Q9": ("U12", "1"),
    "R83": ("Q9", "2"),
    "C106": ("U12", "5"),
    "C105": ("R79", "2"),
    # the buzzer's driver at the buzzer
    "Q1": ("BZ1", "2"),
    "D3": ("BZ1", "2"),
    "R3": ("Q1", "3"),
    "R1": ("Q1", "1"),
    "R2": ("Q1", "1"),
    "U8": ("C80", "2"),
    "C81": ("U8", "1"),
    "R58": ("C80", "2"),
    "C107": ("U13", "3"),
    # the IMU's
    "C24": ("IC2", "8"),
    "C25": ("IC2", "5"),
    # DRV8874 CVM1 (SLVSF66A Table 1), STSPIN958 VDD (DS14341 Table 12), TLV9001 at VS; the bridges'
    # charge pumps first (the flying capacitor across CPH-CPL, VCP's at VCP), then VM's 100 nF
    "C89": ("IC8", "13"),
    "C98": ("IC9", "13"),
    "C88": ("IC8", "12"),
    "C97": ("IC9", "12"),
    "C82": ("IC8", "11"),
    "C91": ("IC9", "11"),
    "C31": ("IC6", "13"),
    # the rest of the STM32 supply: VDDA filter, VBAT 1 uF, bulk
    "R67": ("IC1", "16"),
    "C9": ("IC1", "1"),
    # bridges' bulk at VM; fan driver's bulk at VS
    "C83": ("IC8", "11"),
    "C84": ("IC8", "11"),
    "C87": ("IC8", "11"),
    "C111": ("IC8", "11"),
    "C92": ("IC9", "11"),
    "C93": ("IC9", "11"),
    "C96": ("IC9", "11"),
    "C112": ("IC9", "11"),
    "C36": ("IC6", "27"),
    # ESP, IMU, encoders, LEDs, others
    "C69": ("EC1", None),
    "C70": ("EC1", None),
    "C71": ("EC2", None),
    "C72": ("EC2", None),
    "C18": ("D1", None),
    "C19": ("D2", None),
}

# Placement order of the packed parts that need a spot first (large or tied to one pad).
FIRST = ["R83", "R31"]

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
    for e in mech.main_outline(S):  # loop after loop, each element following the last
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
    """The chassis zones, grown by GAP: a courtyard keeps clear of a zone it may not enter; and the
    fan ring (spec [fan_ring]), where parts stay at or below its max_part_height."""
    out = []
    for _name, (x0, x1, y0, y1, h) in mech.keepout_zones(S):
        x0, x1, y0, y1 = x0 - GAP, x1 + GAP, y0 - GAP, y1 + GAP
        corners = [to_kicad(x, y) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        out.append((h, fill([np.array(corners)])))
    r = S["fan_ring"]["diameter"] / 2 + GAP
    ring = [to_kicad(S["fan_hole"]["x"] + r * math.cos(a), r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 96)]
    out.append((S["fan_ring"]["max_part_height"], fill([np.array(ring)])))
    # the wall sensors' printed cases (parts up to CASE_UNDER under them) and their view corridors
    # (parts below the corridor's lower edge, less VIEW_MARGIN, at the corridor's far end on the
    # board): tests/test_wall_joint.py draws both, tests/test_main_layout.py checks the parts
    sys.path.insert(0, str(ROOT))
    import tests.test_wall_joint as tw  # noqa: PLC0415

    axis = tomllib.loads((ROOT / "spec/wall.toml").read_text())["sensor"]["v"]["value"]
    tan = math.tan(math.radians(tw.VIEW_HALF_DEG))
    for face, a in tw._sensors().values():
        case = tw._case(face, a)
        c = np.mean(case, 0)
        grown = [(x + GAP * (x - c[0]) / math.dist((x, y), c), y + GAP * (y - c[1]) / math.dist((x, y), c)) for x, y in case]
        out.append((CASE_UNDER, fill([np.array([to_kicad(x, y) for x, y in grown])])))
        SENSOR_ZONES.append(out[-1][1])
        d, n = (math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a))
        tip = (face[0] + tw.LED_TIP * d[0], face[1] + tw.LED_TIP * d[1])
        for r0, r1 in ((0.0, 3.0), (3.0, 6.0), (6.0, 12.0)):  # in steps, each at its far end's limit
            w0, w1 = tw.BODY_R + r0 * tan + GAP, tw.BODY_R + r1 * tan + GAP
            pts = [(tip[0] + r * d[0] + s * w * n[0], tip[1] + r * d[1] + s * w * n[1]) for r, w, s in ((r0, w0, -1), (r1, w1, -1), (r1, w1, 1), (r0, w0, 1))]
            out.append((axis - tw.BODY_R - r1 * tan - VIEW_MARGIN, fill([np.array([to_kicad(x, y) for x, y in pts])])))
            SENSOR_ZONES.append(out[-1][1])
    return out


def silk_near() -> np.ndarray:
    """The cells a pad may not cover: within SILK_PAD (and the raster's margin) of the spec's
    silkscreen lines (the fan ring, the drive blocks' outlines: mech.main_silk), which no pad may sit
    under (tests/test_main_layout.py test_spec_silkscreen_keeps_off_every_pad)."""
    m = np.zeros((NY, NX), bool)
    for e in mech.main_silk(S, sexpr.parse(PCB.read_text())):
        if isinstance(e, mech.Line):
            n = max(1, int(math.dist(e.a, e.b) / (RES / 2)))
            pts = [(e.a[0] + (e.b[0] - e.a[0]) * k / n, e.a[1] + (e.b[1] - e.a[1]) * k / n) for k in range(n + 1)]
        else:
            pts = mech.sample(e, 800)
        for x, y in pts:
            c = cell(*to_kicad(x, y))
            if 0 <= c[0] < NX and 0 <= c[1] < NY:
                m[c[1], c[0]] = True
    return grow(m, mech.SILK_PAD + SILK_MARGIN)


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
    pp = []
    for p in f.Pads():
        poly = p.GetEffectivePolygon(pcbnew.F_Cu)
        for i in range(poly.OutlineCount()):
            o = poly.Outline(i)
            pp.append(np.array([(pcbnew.ToMM(o.CPoint(k).x), pcbnew.ToMM(o.CPoint(k).y)) for k in range(o.PointCount())]))
    pads = None  # the pads' cells on the courtyard's raster: they keep off the spec's silkscreen
    if pp:
        pads = np.zeros(shape, bool)
        for q in pp:
            pads |= fill([q], shape, (KX0 + c0[0] * RES, KY0 + c0[1] * RES))
    f.SetOrientationDegrees(old_rot)
    f.SetPosition(old_pos)
    origin_cell = (round(100 / RES), round(100 / RES))
    return m, (c0[0] - origin_cell[0], c0[1] - origin_cell[1]), pads


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


def fits(free, m, off, cx, cy, pads=None, silk=None):
    x0, y0 = cx + off[0], cy + off[1]
    if x0 < 0 or y0 < 0 or y0 + m.shape[0] > free.shape[0] or x0 + m.shape[1] > free.shape[1]:
        return False
    if (m & ~free[y0 : y0 + m.shape[0], x0 : x0 + m.shape[1]]).any():
        return False
    return silk is None or pads is None or not (pads & silk[y0 : y0 + m.shape[0], x0 : x0 + m.shape[1]]).any()


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
    placed.update(HAND)

    for f in fps.values():
        if f.IsFlipped():
            f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    for ref, (x, y, r) in placed.items():
        set_at(fps[ref], x, y, r)

    inside = board_mask()
    zones = zone_masks()
    silk = silk_near()
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
        if ref in FINGER:
            for zm in SENSOR_ZONES:
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
                        m, off, pads = masks[(ref, rot)]
                        if not fits(free, m, off, cx, cy, pads, silk):
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
        m, off, _pads = masks[(ref, rot)]
        stamp(occ, m, off, cx, cy)

    board.Save(str(PCB))
    print(f"placed {len(placed)} footprints; not placed: {unplaced or 'none'}")
    return 0 if not unplaced else 1


if __name__ == "__main__":
    sys.exit(main())
