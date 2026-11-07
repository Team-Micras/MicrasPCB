"""Layout fixes of the encoder board, as a one-off pcbnew script (KiCad 10).

    python3 boards/encoder/layout/fixes.py [--no-sync]

Runs once on the layout that boards/encoder/previous/transfer_layout.py built from the previous
revision, after `make gen` has added R1-R3 (packed beside the board by the netlist sync), then
`pcb layout` syncs the result. Every coordinate is KiCad millimetres on the board's frame
(spec/encoder.toml [kicad]). The steps, in order:

1. Teardrops: delete the second SPI_MOSI teardrop at IC1 pad 4; it overlaps the first and leaves
   a copper sliver (KiCad DRC copper_sliver). Pads 1-3 have one teardrop each, as pad 4 now does.
2. Supply: the 3V3 track runs straight up from the tab pad to IC1's VDD/VDD3V3 (pins 11, 12) along
   x = 149.926, over the bottom-side Encoder_CSn track, which frees the top side above SPI_SCK
   and SPI_MOSI for their pull-downs. C1 sits on it, right of the track, as close to IC1 as the
   courtyards allow: its pad 1 is 4.0 mm from pin 11 (pad centres; 5.0 mm on the previous layout).
3. The AS5047U's SPI input pulls (DS v1-00 Figure 4 notes 1-3): R3 (SPI_MOSI) and R2 (SPI_SCK)
   above their bottom-side tracks, each with a via onto its track; R1 (Encoder_CSn to 3V3) right
   of the supply track, with a via and a bottom-side stub to the Encoder_CSn track.
4. Silkscreen: every text 0.5 mm high with a 0.125 mm stroke (SILK_TEXT, the owner's choice and
   the board's minimum): the pin labels keep their places, the IC1 and C1 designators move clear
   of the new parts, J1's stays; R1-R3 keep their designators on F.Fab only (no room on the
   silkscreen of a 9.6 mm board).

Zones are refilled before saving. New items take their UUIDs from a seeded generator, so the
chain transfer_layout.py, fixes.py, `make gen` rebuilds the committed layout byte for byte.
"""

from __future__ import annotations

import itertools
import math
import subprocess
import sys
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parents[3]
LAYOUT = ROOT / "boards/encoder/layout/encoder.kicad_pcb"

B: pcbnew.BOARD = None  # the board being edited
F, BK = pcbnew.F_Cu, pcbnew.B_Cu
LAYERS = {"F": F, "B": BK}
EPS = 1e-4  # mm: coordinate match tolerance

VIA_D, VIA_HOLE = 0.6, 0.3  # the board's vias (encoder.zen netclass)
SUPPLY_W = 0.254  # top-side tracks, as the previous layout's 3V3, A and B
SPI_W = 0.38  # bottom-side SPI tracks, as the previous layout's
TRUNK_X = 149.9261  # the 3V3 tab pad (J1 pad 5) centre line
SILK_TEXT = (0.5, 0.125)  # silkscreen text height and stroke, mm


# --- helpers -------------------------------------------------------------------------------------


def mm(v: float) -> int:
    return pcbnew.FromMM(v)


def pt(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x), mm(y))


def xy(p) -> tuple[float, float]:
    return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)


def near(a, b, eps: float = EPS) -> bool:
    return math.dist(a, b) <= eps


def net(name: str) -> pcbnew.NETINFO_ITEM:
    n = B.FindNet(name)
    if n is None:
        raise SystemExit(f"no net {name}")
    return n


def fp(ref: str) -> pcbnew.FOOTPRINT:
    f = B.FindFootprintByReference(ref)
    if f is None:
        raise SystemExit(f"no footprint {ref}")
    return f


def pad(ref: str, num: str) -> pcbnew.PAD:
    for p in fp(ref).Pads():
        if p.GetNumber() == num:
            return p
    raise SystemExit(f"no pad {ref}.{num}")


def padxy(ref: str, num: str) -> tuple[float, float]:
    return xy(pad(ref, num).GetPosition())


GRAVEYARD = []  # removed items stay referenced: their SWIG proxies do not own them


def drop(item) -> None:
    GRAVEYARD.append(item)
    B.Remove(item)


def segment(netname: str, layer: str, a, b) -> pcbnew.PCB_TRACK:
    """The one track of netname on layer from a to b (either way round)."""
    found = []
    for t in B.GetTracks():
        if t.GetClass() != "PCB_TRACK" or t.GetNetname() != netname or t.GetLayer() != LAYERS[layer]:
            continue
        s, e = xy(t.GetStart()), xy(t.GetEnd())
        if (near(s, a, 2e-3) and near(e, b, 2e-3)) or (near(s, b, 2e-3) and near(e, a, 2e-3)):
            found.append(t)
    if len(found) != 1:
        raise SystemExit(f"{netname} {layer} {a} -> {b}: {len(found)} tracks")
    return found[0]


def track(netname: str, layer: str, width: float, *pts) -> None:
    """A chain of straight segments through pts (each an (x, y) or a 'ref.pad' string)."""
    q = [padxy(*p.split(".", 1)) if isinstance(p, str) else p for p in pts]
    for a, b in itertools.pairwise(q):
        if math.dist(a, b) < 1e-6:
            continue
        t = pcbnew.PCB_TRACK(B)
        t.SetStart(pt(*a))
        t.SetEnd(pt(*b))
        t.SetWidth(mm(width))
        t.SetLayer(LAYERS[layer])
        t.SetNet(net(netname))
        B.Add(t)


def via(netname: str, x: float, y: float) -> None:
    v = pcbnew.PCB_VIA(B)
    v.SetPosition(pt(x, y))
    v.SetWidth(mm(VIA_D))
    v.SetDrill(mm(VIA_HOLE))
    v.SetLayerPair(F, BK)
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetNet(net(netname))
    v.SetFrontTentingMode(pcbnew.TENTING_MODE_TENTED)
    v.SetBackTentingMode(pcbnew.TENTING_MODE_TENTED)
    B.Add(v)


def split(t: pcbnew.PCB_TRACK, at: tuple[float, float]) -> tuple[float, float]:
    """Split a straight track at the point of it nearest to `at` (within 2 um), so a via or a
    branch there lands on track ends; returns that point."""
    s, e = xy(t.GetStart()), xy(t.GetEnd())
    dx, dy = e[0] - s[0], e[1] - s[1]
    k = ((at[0] - s[0]) * dx + (at[1] - s[1]) * dy) / (dx * dx + dy * dy)
    on = (round(s[0] + k * dx, 6), round(s[1] + k * dy, 6))
    if not 0 < k < 1 or math.dist(on, at) > 2e-3:
        raise SystemExit(f"{at} is not on the {t.GetNetname()} track {s} -> {e}")
    t.SetEnd(pt(*on))
    track(t.GetNetname(), "F" if t.GetLayer() == F else "B", pcbnew.ToMM(t.GetWidth()), on, e)
    return on


def zone_by_uuid(prefix: str) -> pcbnew.ZONE:
    found = [z for z in B.Zones() if z.m_Uuid.AsString().startswith(prefix)]
    if len(found) != 1:
        raise SystemExit(f"zone {prefix}: {len(found)} matches")
    return found[0]


def place(ref: str, x: float, y: float, rot: float) -> None:
    f = fp(ref)
    if f.IsFlipped():
        raise SystemExit(f"{ref} is on the bottom side")
    f.SetOrientation(pcbnew.EDA_ANGLE(rot, pcbnew.DEGREES_T))
    f.SetPosition(pt(x, y))


# --- steps ---------------------------------------------------------------------------------------


def teardrops() -> None:
    # the two SPI_MOSI teardrops between IC1 pad 4 and its track; keep the one shaped like
    # pads 1-3's (from the pad edge, x = 146.298, to the track)
    extra = zone_by_uuid("23a41d79")
    keep = zone_by_uuid("34f8138f")
    for z in (extra, keep):
        if z.GetNetname() != "SPI_MOSI" or z.GetLayer() != F or z.GetAssignedPriority() < 100:
            raise SystemExit(f"zone {z.m_Uuid.AsString()} is not an SPI_MOSI teardrop on F.Cu")
    drop(extra)


def supply() -> None:
    # the previous route: up x = 149.176 through C1 pad 1, then 45 degrees to IC1 pins 11/12
    drop(segment("3V3", "F", (149.926, 108.988), (149.176, 108.238)))
    drop(segment("3V3", "F", (149.176, 108.238), (149.176, 103.102)))
    diag = segment("3V3", "F", (149.176, 103.102), (149.997, 102.281))
    # C1's teardrops on that track
    drop(zone_by_uuid("1c81e9bc"))
    drop(zone_by_uuid("6440b083"))
    # the new route: straight up from the tab pad to the same 45 degree run into pins 11/12
    tab_track = segment("3V3", "F", (149.926, 110.877), (149.926, 108.988))
    tab_end = min(xy(tab_track.GetStart()), xy(tab_track.GetEnd()), key=lambda q: q[1])
    s, e = xy(diag.GetStart()), xy(diag.GetEnd())
    pins_end = s if s[1] < e[1] else e
    top = (TRUNK_X, round(pins_end[1] + (pins_end[0] - TRUNK_X), 6))
    if not near(tab_end, (TRUNK_X, 108.987795), 1e-6):
        raise SystemExit(f"the 3V3 track leaves the tab pad at {tab_end}")
    diag.SetStart(pt(*top))
    diag.SetEnd(pt(*pins_end))
    track("3V3", "F", SUPPLY_W, tab_end, top)


def parts() -> None:
    # C1 (100 nF): pad 1 on the supply track, pad 2 to the right in the GND pour; its courtyard
    # 0.1 mm below IC1's
    place("C1", TRUNK_X + 0.775, 105.73, 0)
    # the stitching via beside C1's GND pad moves 0.15 mm out (0.22 mm from the pad)
    stitch = [
        t for t in B.GetTracks() if t.GetClass() == "PCB_VIA" and near(xy(t.GetPosition()), (152.30114, 105.553605))
    ]
    if len(stitch) != 1:
        raise SystemExit("GND via at (152.301, 105.554) not found")
    stitch[0].SetPosition(pt(152.45114, 105.553605))
    # R3 (SPI_MOSI) and R2 (SPI_SCK) pull-downs: pad 2 (GND) up, in the pour; pad 1 down, to a via
    # on the bottom-side track
    place("R3", 147.047, 105.9, 90)
    place("R2", 148.6, 105.9, 90)
    # R1 (Encoder_CSn pull-up): pad 1 (3V3) up, beside the supply track; pad 2 down, to a via
    place("R1", 150.75, 107.55, 270)


def routes() -> None:
    # SPI_MOSI: a via on the bottom-side track below R3, straight up to R3 pad 1
    at = split(segment("SPI_MOSI", "B", (147.047, 110.847), (147.047, 102.05)), (147.0466, 107.2))
    via("SPI_MOSI", *at)
    track("SPI_MOSI", "F", SUPPLY_W, "R3.1", at)
    # SPI_SCK: a via on the bottom-side track below R2, 45 degrees up to R2 pad 1
    at = split(segment("SPI_SCK", "B", (148.949, 110.85), (148.949, 100.778)), (148.94912, 107.2))
    via("SPI_SCK", *at)
    r2 = padxy("R2", "1")
    track("SPI_SCK", "F", SUPPLY_W, r2, (r2[0], at[1] - (at[0] - r2[0])), at)
    # 3V3 to R1 pad 1, from the supply track
    r1 = padxy("R1", "1")
    branch = split(segment("3V3", "F", (TRUNK_X, 108.988), (TRUNK_X, 102.352)), (TRUNK_X, r1[1]))
    track("3V3", "F", SUPPLY_W, branch, r1)
    # Encoder_CSn: R1 pad 2 down to a via, then on the bottom side to the Encoder_CSn track
    csn_via = (150.75, 108.85)
    track("Encoder_CSn", "F", SUPPLY_W, "R1.2", csn_via)
    via("Encoder_CSn", *csn_via)
    at = split(segment("Encoder_CSn", "B", (149.932, 110.871), (149.932, 100.122)), (149.93212, csn_via[1]))
    track("Encoder_CSn", "B", SUPPLY_W, csn_via, at)


def size(t) -> None:
    h, stroke = SILK_TEXT
    t.SetTextSize(pcbnew.VECTOR2I(mm(h), mm(h)))
    t.SetTextThickness(mm(stroke))


def label(ref: str, x: float, y: float, angle: float) -> None:
    """A footprint's designator on the silkscreen, centred on (x, y), at SILK_TEXT."""
    t = fp(ref).Reference()
    t.SetVisible(True)
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    t.SetTextAngle(pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    size(t)
    t.SetPosition(pt(x, y))


def silkscreen() -> None:
    # IC1 above the package on the board's centre line, C1 below its GND pad, J1 where it is; the
    # pin labels (board texts) where they are. R1-R3 keep their designators on F.Fab only: beside
    # an 0402 here a 0.5 mm label cannot keep the 0.1 mm silkscreen clearance to the parts' own
    # outlines.
    label("IC1", 148.5011, 98.75, 0)
    label("C1", 151.95, 106.85, 0)
    size(fp("J1").Reference())
    for d in B.GetDrawings():
        if d.GetClass() == "PCB_TEXT" and d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            size(d)
    for r in ("R1", "R2", "R3"):
        fp(r).Reference().SetVisible(False)


# --- run -------------------------------------------------------------------------------------------


def main() -> int:
    global B
    B = pcbnew.LoadBoard(str(LAYOUT))
    # new items take UUIDs from a seeded generator, so a re-run on the same input is byte-identical
    pcbnew.KIID.SeedGenerator(0x6E636F64)
    teardrops()
    supply()
    parts()
    routes()
    silkscreen()
    pcbnew.ZONE_FILLER(B).Fill(B.Zones())
    pcbnew.SaveBoard(str(LAYOUT), B)
    if "--no-sync" not in sys.argv:
        env = dict(
            line.split("=", 1)
            for line in (ROOT / "versions.env").read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
        subprocess.run(
            ["pcb", f"+{env['PCB_TOOLCHAIN'].strip()}", "layout", "--no-open", "boards/encoder/encoder.zen"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
