"""Build the 3D model of the upright wall sensor (WallSensor_SFH4550_TPS601A_Upright.kicad_mod).

The SFH 4550 and the TPS601A(F) with straight leads, each seated with its flange on the front face
of the upright wall-sensor board, in the footprint's model frame: x right (u), y up (v), z out of
the front face, origin on the TPS601A axis. The bodies are MicrasHardware's (micras/leds.py, from
the datasheets; its docstring cites the drawings); only the leads differ from its bent-lead
sensor_model(). Pin 1 (the SFH 4550 cathode, the TPS601A emitter) is at x = -1.27, the
footprint's pads 2 and 4.

    MICRAS_HARDWARE=~/codes/MicrasHardware \\
        ~/codes/MicrasHardware/.venv/bin/python -I components/micras/WallSensor/upright_model.py OUT.step
    pcb embed-step components/micras/WallSensor/WallSensor_SFH4550_TPS601A_Upright.kicad_mod OUT.step

Do not commit OUT.step: the footprint embeds it.
"""

import os
import sys
from math import cos, radians, sin
from pathlib import Path

sys.path.insert(0, str(Path(os.environ["MICRAS_HARDWARE"]).expanduser()))

from build123d import Box, Circle, Compound, Location, Plane, Pos, Rectangle, Rot, export_step, extrude  # noqa: E402
from micras import leds  # noqa: E402

LED_ABOVE = 6.1  # SFH 4550 axis above the TPS601A axis (WallSensor.zen, upright mount)
BOARD = 0.79  # the wall board (spec/wall.toml pcb.thickness)
LEAD_OUT = 1.0  # leads trimmed 1.0 mm beyond the back face
# The part frame of micras/leds.py: x along the optical axis, y left, z up, origin on the axis at the
# seating plane; to the model frame: (x, y, z) -> (y, z, x), a proper rotation.
TO_MODEL = Location(Plane((0, 0, 0), x_dir=(0, 0, 1), z_dir=(0, 1, 0)))


def _straight(section, pitch, overlap, length):
    """Two straight leads at y = +-pitch/2 from overlap inside the body back to length behind the seat."""
    out = None
    for y in (-pitch / 2, pitch / 2):
        leg = extrude(section(Plane((overlap, y, 0), x_dir=(0, 1, 0), z_dir=(-1, 0, 0))), overlap + length)
        out = leg if out is None else out + leg
    return out


def emitter():
    e = leds.SFH4550
    rf, rb, t = e.flange_d / 2, e.body_d / 2, e.flange_t
    a = radians(45)
    body = leds._lathe(
        [(0, 0), (0, rf), (t, rf), (t, rb), (e.dome, rb)], (e.dome + rb * sin(a), rb * cos(a)), e.length
    )
    body -= Pos(t / 2, -e.flat - rf, 0) * Box(t + 0.02, 2 * rf, 2 * rf)  # flange flat, cathode side (-y)
    length = BOARD + LEAD_OUT
    body += _straight(lambda pl: pl * Rectangle(e.lead, e.lead), e.pitch, t / 2, length)
    # the wider lead section (dambar) from 1.0 mm behind the seat, past the 0.79 mm board
    for y in (-e.pitch / 2, e.pitch / 2):
        body += Pos(-(e.stub[0] + length) / 2, y, 0) * Box(length - e.stub[0], e.stub_w, e.lead)
    return leds._single(body, "SFH4550")


def receiver():
    r = leds.TPS601A
    rf, rb, t, R = r.flange_d / 2, r.can_d / 2, r.flange_t, r.lens_r
    cx = r.length - R
    a = radians(45)
    body = leds._lathe([(0, 0), (0, rf), (t, rf), (t, rb), (r.can_h, rb)], (cx + R * sin(a), R * cos(a)), r.length)
    reach = r.tab_reach + 0.3
    body += Rot(180 - r.tab_angle, 0, 0) * Pos(t / 2, rf + r.tab_reach - reach / 2, 0) * Box(t, reach, r.tab_w)
    body += _straight(lambda pl: pl * Circle(r.lead / 2), r.pitch, t / 2, BOARD + LEAD_OUT)
    return leds._single(body, "TPS601A")


def model():
    kids = []
    for part, up in ((emitter(), LED_ABOVE), (receiver(), 0.0)):
        k = TO_MODEL * Pos(0, 0, up) * part
        k.label, k.color = part.label, part.color
        kids.append(k)
    return Compound(children=kids, label="WALL_SENSOR_UPRIGHT")


if __name__ == "__main__":
    export_step(model(), sys.argv[1])
