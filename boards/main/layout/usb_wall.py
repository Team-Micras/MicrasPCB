"""The owner's second set of layout decisions, as a one-off pcbnew script (KiCad 10).

    python3 boards/main/layout/usb_wall.py

Runs once, after refine.py, on the layout as `make gen` leaves it with the USB data lines on
plain copper (R8/R9/C22/C23 gone) and the SBU signature detector's parts (R50-R55, C77, C78,
D13, U7) placed by `pcb apply` beside the board. It reuses the helpers of fixes.py and refine.py
and the grid router (router.py). Every coordinate is KiCad millimetres on the board's frame; the
UUID prefixes name items of that starting layout. The steps, in order:

- usb: the ESD array U6 in line with D+/D-, where the fuse F1 and the TVS D8 were: the pair runs
  from U2's contacts into U6's right-hand pads (6: D+, 4: D-), leaves by its left-hand pads (1, 3)
  and drops through two vias to B.Cu, crosses under the receptacle between its shell pads, and
  returns to F.Cu through two vias in the strip R8/R9/C22/C23 leave right of U2, where it joins
  the pair to IC1 (0.2248 / 0.127 mm, 90 Ohm on this stack). U6's 3V3 pin takes the feed that
  ran to it under its body, its GND pin a via under its body. D8 moves to that strip with vias to
  the In2 +5V plane and In1; the CC2 hop under the old D+ track becomes F.Cu;
- sbu: Q7's gate leaves +5V (the gate feed from U2's VBUS via goes), F1 sits right of Q7, and the
  SBU feed from U2's SBU contacts to F1 takes the route that ran from F1 to Q7, with a new B.Cu
  leg up the strip;
- detector: U7 (TLV7041) and its reference network R52-R54, C78 between EC1 and the USB pair,
  the peak hold C77, R51, D13 below it, R55 by Q7's gate, R50 by R6 on the CC1 line;
- corner: Wall_Sensor_2 (IC1 pin 25) back on its short path over IC1's top corner, outside
  Wall_Sensor_3, past R21 (moved 0.3 mm along its axis) and between W3's pads to W3.4. PA5's
  battery node runs between them and steps under Wall_Sensor_2 through two vias and a 0.9 mm
  B.Cu jumper, in a column that the Button and Reset hops (moved right) and the LED_ARGB via
  (moved up) leave free, to the battery divider R44/R45/C59 above the corner;
router.py joins what is left unconnected (ROUTES); the reference designators of the parts this
script places go to free spots on the silkscreen (refine.py's method); then the zones are refilled,
the board saved and `pcb layout` syncs it.

    python3 boards/main/layout/usb_wall.py --no-sync     # skip the `pcb layout` sync
    python3 boards/main/layout/usb_wall.py --no-routes   # placement and hand copper only
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixes as fx
from fixes import fanout, fp, items, nudge, place, remove, renet, track, via

ROOT = Path(__file__).resolve().parents[3]
LAYOUT = ROOT / "boards/main/layout/main.kicad_pcb"

PAIR_W = 0.2248  # the USB pair's width and gap (main.zen NetClass): 90 Ohm differential on this stack
PAIR_PITCH = 0.352  # centre to centre, width + 0.127 mm gap


# --- USB: U6 in line ---------------------------------------------------------------------------------

U6_AT = (146.9, 134.78)  # pads 1-3 at x 145.75, 4-6 at x 148.05; 0.95 mm row pitch


def usb() -> None:
    # U6's branches: D+ from the receptacle to U6 and back (three vias), D- (two vias)
    remove(items(["154f05a5", "5fd1eedd", "3c5cb607", "624630d8", "34d7a668", "e0c27b35", "6924bfee"]))
    remove(items(["1863c221", "c1ef619e", "42b64da2"]))
    remove(items(["66540a2e", "c2acd2f8", "56cf8a37", "d2859418", "8d5ccf78", "8b788e80", "4f16f716"]))
    remove(items(["625f9dbc", "2badb958", "298ba32b", "ee33b964", "669b8ac1", "964e9020", "42cc43ab"]))
    remove(items(["879b5529", "455ac33d", "4c8f822a", "1328b35b"]))
    # the pair from the receptacle to where R8/R9 were, up to the coupled run to IC1
    remove(items(["526bff1b", "7b1f863b", "f19fe82e", "11b60c0e", "e89ddf73", "fbe1fd83", "2a77ad31"]))
    remove(items(["5a00a1c9", "16897436", "6567ccab", "14e718df", "6f8fc752"]))
    remove(items(["3be16814", "42f17e45", "3c91b354", "1b45b5c1", "16473045", "3dec54eb", "2058a28d"]))
    remove(items(["1c703fa6", "f9ee189a", "339926bf", "91feaa30", "1e369aae", "35e06889", "c4859710"]))
    remove(items(["28f2bae9", "9768defa"]))
    # the teardrops of R8/R9's pads, and of U2's D+/D- contacts under the receptacle-side net
    # names R8/R9 separated: the contacts' teardrops take the nets the contacts are on now
    remove(items(["75cae4ba", "99eb0527", "d7ee17ec"]))
    renet(items(["3e8110de"]), "USBD_P")
    renet(items(["c2ac36d6", "b5bf1e3d"]), "USBD_N")
    # C22/C23's ground stubs and the via under the pair's new run
    remove(items(["3e4bc375", "a6e88590", "7e5b117d", "91ab7dfa", "8d546c98"]))
    # U6's old supply and ground copper, D8's copper and the ground vias under U6's new place
    remove(items(["c8d0c556", "055d1abe", "57116510", "fd67663a", "75e3170e"]))
    remove(items(["d06f96f8", "1b8cc326", "161c9ff9", "736a4d38", "a90092a3", "b96949c6", "7a199c64"]))
    # C48's ground via and track end where D+ now runs: the C48-C51 ground run takes a via
    # between C48 and C51 instead
    remove(items(["60c7d573", "23d98e98"]))
    via("GND", 151.31, 135.34, 0.5)
    place("U6", *U6_AT, 0)

    # receptacle to U6: D+ from A6 (joined to B6 over the contacts), D- from B7 (joined to A7
    # under them), up the 1.3 mm between U6's right pads and C48, into pads 6 and 4
    dp_x, dn_x = 148.93, 148.93 - PAIR_PITCH
    track("USBD_P", "F", PAIR_W, (150.024, 137.071), (dp_x, 137.071 - (150.024 - dp_x)), (dp_x, 134.13))
    track("USBD_P", "F", PAIR_W, (dp_x, 134.13), (dp_x - 0.3, 133.83), "U6.6")
    track("USBD_N", "F", PAIR_W, (149.524, 137.071), (dn_x, 137.071 - (149.524 - dn_x)), (dn_x, 135.85))
    # U6 to the receptacle's far side: vias left of pads 1 and 3, then B.Cu down the left of U2
    # (D- on the inside of the turn) and along between its shell pads to the strip right of it
    vp, vn = (144.55, 133.95), (144.55, 135.73)
    track("USBD_P", "F", PAIR_W, "U6.1", vp)
    track("USBD_N", "F", PAIR_W, "U6.3", vn)
    via("USBD_P", *vp)
    via("USBD_N", *vn)
    xp, xn = 144.05, 144.05 + PAIR_PITCH
    yn, yp = 140.70, 140.70 + PAIR_PITCH - 0.002  # 141.05, the pair's run to IC1
    track("USBD_P", "B", PAIR_W, vp, (xp, vp[1] + 0.5), (xp, yp - 0.5), (xp + 0.5, yp), (155.65, yp), (155.9, 141.30))
    track("USBD_N", "B", PAIR_W, vn, (xn, vn[1] + (vn[0] - xn)), (xn, yn - 0.296), (xn + 0.296, yn), (155.65, yn))
    track("USBD_N", "B", PAIR_W, (155.65, yn), (155.9, 140.45))
    via("USBD_P", 155.9, 141.30)
    via("USBD_N", 155.9, 140.45)
    track("USBD_P", "F", PAIR_W, (155.9, 141.30), (156.15, yp), (159.116, 141.05))
    track("USBD_N", "F", PAIR_W, (155.9, 140.45), (156.15, yn), (159.261, 140.698))
    # U6 supply: the 3V3 feed from above runs across over pads 1 and 6 and down U6's centre line
    # to pad 5; pad 2 takes a ground via under the body
    track("3V3", "F", 0.25, (145.076, 132.429), (145.647, 133.0), (147.2, 133.0), (147.2, 134.78), "U6.5")
    track("GND", "F", 0.25, "U6.2", (146.7, 134.78))
    via("GND", 146.7, 134.78)
    # the F.Cu ground pour around U6 splits at the pair: its part towards U1 and C42 takes a via
    via("GND", 149.0, 133.4)
    # CC2 straight down on F.Cu where the old D+ track made it hop
    remove(items(["336c26bf", "0213dc4c", "c85eee9c"]))
    track("PERIPHERALS.USB_CC2", "F", 0.254, (152.438, 139.463), (152.438, 141.368))
    # D8 (VBUS TVS) in the strip right of U2: GND to C22's old ground via, +5V to the In2 plane
    place("D8", 157.25, 138.70, 180)
    track("GND", "F", 0.25, "D8.1", (158.28, 138.701))
    track("+5V", "F", 0.25, "D8.2", (156.6, 139.4))
    via("+5V", 156.6, 139.4)


# --- SBU supply ---------------------------------------------------------------------------------------

F1_AT = (167.1, 126.85)


def sbu() -> None:
    # Q7's gate feed from U2's VBUS via (B4A9) to the gate: the gate is SBU_EN_N
    remove(items(["db69dc09", "38acdbdc", "69f2cb80", "a7a9a17a", "8c69eb5e", "edcedf30", "b50c0680"]))
    remove(items(["38ef1ed8", "cc8f45a5", "170b84b4", "e424c224", "906a6e32", "e465dd9c"]))
    # F1's copper by U2, and the route's first leg along the contacts
    remove(items(["971930c1", "5eaf1388", "d4b1ed66", "a1d7cfd7", "4c88c9bf", "6ed08da0"]))
    remove(items(["65508726", "a04176dd", "67a8b926", "342f4c51", "c489f50d", "9a8be174", "10d07316", "cd943ada"]))
    remove(items(["3df5b090", "c98d5a12"]))
    # the rest of the old F1-Q7 route carries SBU_PWR from U2's contacts to F1 by Q7
    renet(items(["d1ac5255", "dfe1d262", "fb4410d4", "1e4de3f7", "8b492994", "51bbc22e"]), "PERIPHERALS.SBU_PWR")
    renet(items(["499a74d4", "40acc21f", "e39f8aa2"]), "PERIPHERALS.SBU_PWR")
    # its new leg: from the SBU2 contact's via (A8) along under the receptacle's top and up the
    # strip right of it
    track(
        "PERIPHERALS.SBU_PWR",
        "B",
        0.254,
        (151.553, 139.252),
        (152.15, 139.85),
        (155.95, 139.85),
        (155.95, 134.055),
        (156.226, 133.779),
    )
    place("F1", *F1_AT, 0)
    track("PERIPHERALS.SBU_PWR", "B", 0.254, (163.976, 126.829), (164.1, 126.95), (168.2, 126.95))
    via("PERIPHERALS.SBU_PWR", 168.2, 126.95)
    track("PERIPHERALS.SBU_PWR", "F", 0.254, "F1.2", (168.2, 126.95))
    track("PERIPHERALS.SBU_SW", "F", 0.254, "F1.1", "Q7.3")


# --- detector -------------------------------------------------------------------------------------------

# (ref, x, y, rotation): U7 and its reference divider between EC1 and the USB pair, the hold
# below them, R55 at Q7's gate, R50 by R6 where CC1 arrives
DETECTOR = [
    ("U7", 161.75, 114.4, 90),  # pins: 5 VCC top left, 4 IN- top right, 1 OUT, 2 GND, 3 IN+ bottom
    ("C78", 158.3, 113.33, 90),  # 3V3 (pad 2) top, on the 3V3 run to pin 5
    ("R52", 159.35, 113.33, -90),  # 3V3 (pad 1) top, SBU_VREF bottom
    ("R53", 158.3, 115.23, 90),  # SBU_VREF (pad 2) top, GND bottom
    ("R54", 159.35, 115.23, -90),  # SBU_VREF (pad 1) top, SBU_EN_N bottom
    ("C77", 162.45, 117.75, 90),  # SBU_DET (pad 2) top
    ("R51", 162.45, 119.65, -90),  # GND (pad 1) top, SBU_DET bottom
    ("D13", 162.45, 122.3, -90),  # cathode (pad 1, SBU_DET) top
    ("R55", 162.5, 124.6, 0),  # 3V3 left, SBU_EN_N right, above Q7's gate
    ("R50", 157.0, 142.4, 0),  # CC1 left, SBU_DET_A right
]
# pads to the In1 ground plane through a via beside them
DETECTOR_GND = [("C77", "1")]


def detector() -> None:
    for ref, x, y, rot in DETECTOR:
        place(ref, x, y, rot)
    # 3V3 along the top row to pin 5; the reference node joined beside U7 and run under its body
    # to IN+ (pin 3), clear of the USB pair
    track("3V3", "F", 0.25, "C78.2", "R52.1", (160.55, 112.82), "U7.5")
    track("PERIPHERALS.SBU_VREF", "F", 0.15, "R52.2", "R54.1")
    track("PERIPHERALS.SBU_VREF", "F", 0.15, "R53.2", "R54.1", (159.67, 114.4), (162.7, 114.4), "U7.3")
    # the comparator output to R54 and down to B.Cu for Q7's gate
    track("PERIPHERALS.SBU_EN_N", "F", 0.2, "R54.2", (160.2, 115.74), "U7.1")
    track("PERIPHERALS.SBU_EN_N", "F", 0.2, (160.2, 115.74), (160.2, 116.45))
    via("PERIPHERALS.SBU_EN_N", 160.2, 116.45)
    track("GND", "F", 0.25, "U7.2", (161.75, 116.4))
    via("GND", 161.75, 116.4)
    track("GND", "F", 0.25, "R53.1", (157.912, 116.508))  # C68's ground via
    track("GND", "F", 0.25, "C78.1", (157.85, 113.81), (157.636, 113.6), (157.636, 113.038))  # EC1.6's
    # the hold: IN- (pin 4) down the column's right side to C77, R51 and D13's cathode
    track("PERIPHERALS.SBU_DET", "F", 0.15, "U7.4", (163.2, 113.76), (163.2, 117.27), "C77.2")
    track("PERIPHERALS.SBU_DET", "F", 0.15, (163.2, 117.27), (163.2, 120.16), "R51.2", "D13.1")
    track("GND", "F", 0.25, "C77.1", "R51.1")


# --- IC1's top corner -----------------------------------------------------------------------------------

WS2_X = 143.89  # Wall_Sensor_2's step north between Wall_Sensor_1 and the battery node's escape
WS2_DIAG = 214.23  # x + y of its run up IC1's top-left side, outside the battery node's
WS2_Y = 67.33  # its run over the corner, under the Button/Reset vias, over Wall_Sensor_3
WS2_DOWN = 82.67  # x - y of its run down the top-right side, between Wall_Sensor_3 and R21.1
VIA_A, VIA_B = (147.1, 67.8), (147.1, 66.86)  # the battery node's step under Wall_Sensor_2
# the vias over the switch bus keep the JLCPCB 0.2 mm via-hole-to-track rule from Switch_0's
# B.Cu run at y 66.376: y >= 66.853


def corner() -> None:
    # Wall_Sensor_2's long way round the top edge (its escape from pin 25 stays)
    remove(items(["abb26f10", "02a0a077", "b5f2f21f", "08039798", "9ad5e96f", "ea86bb17", "47acf06e"]))
    remove(items(["5b825509", "d4074c1c", "790cadd5", "96f05df8", "51bfcc9e"]))
    # the battery node's run over the corner to R44 and its divider's copper
    remove(items(["1a8ac6d1", "c58cb5e9", "c38d1b17", "833378bd", "0af40cee", "9971364f", "0d3a9b2e"]))
    remove(items(["20ecbcb9", "c314e2c5", "c63af27b"]))
    # Switch_0 turns along the bus square instead of diagonally, which leaves room for LED_ARGB's
    # via up and left of its old place; the Button and Reset hops move right
    remove(items(["0ad27994"]))
    track("Switch_0", "B", 0.254, (145.326, 67.738), (145.326, 66.376), (146.689, 66.376))
    remove(items(["beb78ad6", "84f886c2", "973fcc42", "bbf337d1", "5128923c"]))
    remove(items(["76325e60", "7b856151", "d1599989", "3c5d3bac", "fb385348", "0c31fead", "bde4944b"]))
    remove(items(["f42c36f9", "439e674f", "c20ac00e", "118727ea", "b6f4fbf3", "b388a655"]))
    led_via = (145.85, 66.9)
    track("LED_ARGB", "F", 0.254, (144.691, 65.549), (144.691, 65.975), (145.616, 66.9), led_via)
    via("LED_ARGB", *led_via)
    track("LED_ARGB", "B", 0.254, led_via, (146.596, 67.646), (146.596, 68.811))
    track("Button", "B", 0.254, (144.621, 71.287), (148.05, 67.858), (148.05, 66.86))
    via("Button", 148.05, 66.86)
    track("Button", "F", 0.254, (148.05, 66.86), (148.05, 64.3))
    via("Button", 148.05, 64.3)
    track("Button", "B", 0.254, (148.05, 64.3), (148.344, 64.006))
    track("Reset", "F", 0.254, (148.247, 63.263), (148.63, 63.646), (148.63, 66.87))
    via("Reset", 148.63, 66.87)
    track("Reset", "B", 0.254, (148.63, 66.87), (148.63, 68.599), (149.644, 69.613))
    # R21 (W3's emitter resistor) 0.15 mm along its axis, away from the corner, and the power LED
    # D5 0.15 mm towards the front edge to keep their courtyards apart; Wall_Sensor_3's run down
    # the top-right side 0.1 mm inwards
    nudge("R21", 0.106, -0.106)
    remove(items(["8405d5d6", "7a9bb876"]))  # stubs at R21.2's via that the move leaves off the pad
    nudge("D5", 0.0, -0.15)
    remove(items(["9b841dd7", "315469c1", "64a705e7"]))
    track("Wall_Sensor_3", "F", 0.254, (147.663, 67.962), (150.138, 67.962), (153.744, 71.568), (154.718, 71.568))
    # Wall_Sensor_2: north between Wall_Sensor_1 and the battery node's escape, up the outside of
    # the battery node, over the corner, down between Wall_Sensor_3 and R21.1, between W3's pads
    # 1 and 2 to pad 4
    pts = [
        (WS2_X, 71.545),
        (WS2_X, WS2_DIAG - WS2_X),
        (WS2_DIAG - WS2_Y, WS2_Y),
        (WS2_DOWN + WS2_Y, WS2_Y),
        (WS2_DOWN + 70.248, 70.248),
        (154.445, 70.248),
        (155.655, 69.038),
        "W3.4",
    ]
    track("Wall_Sensor_2", "F", 0.15, *pts)
    # the battery node: its escape's run up to via A, the B.Cu step to via B, the divider above
    track("Battery_Voltage", "F", 0.15, (144.29, 70.77), VIA_A)
    via("Battery_Voltage", *VIA_A)
    track("Battery_Voltage", "B", 0.15, VIA_A, VIA_B)
    via("Battery_Voltage", *VIA_B)
    place("R44", 145.63, 65.45, -90)  # VBAT (pad 1, top) to the node
    place("R45", 146.57, 65.45, -90)  # GND (pad 1, top) to the node
    place("C59", 147.51, 65.45, -90)  # GND (pad 1, top) to the node
    track("Battery_Voltage", "F", 0.2, "R44.2", "R45.2", "C59.2")
    track("Battery_Voltage", "F", 0.2, "C59.2", (147.1, 66.34), VIA_B)
    track("GND", "F", 0.25, "R45.1", (146.801, 64.676), "C59.1")
    track("VBAT", "F", 0.25, "R44.1", (145.63, 64.6), (145.845, 64.385))


# --- routing --------------------------------------------------------------------------------------------

ROUTES = [
    # the detector's local nets first, short, then its supply and the long CC1 link
    ("PERIPHERALS.SBU_VREF", 0.15),
    ("PERIPHERALS.SBU_DET", 0.15),
    ("PERIPHERALS.SBU_EN_N", 0.2),
    ("3V3", 0.25),
    ("PERIPHERALS.USB_CC1", 0.2),
    ("PERIPHERALS.SBU_DET_A", 0.15),
    ("GND", 0.25),
]


def routes() -> list[str]:
    import router

    pcbnew.ZONE_FILLER(fx.B).Fill(fx.B.Zones())
    for ref, num in DETECTOR_GND:
        fanout(ref, num, "In1")
    r = router.Router(fx.B)
    failed = []
    for name, width, *clr in ROUTES:
        try:
            r.route_net(name, width, clr=clr[0] if clr else router.CLR)
        except RuntimeError as e:
            failed.append(str(e))
    return failed


# --- silkscreen -----------------------------------------------------------------------------------------

MOVED = ["U6", "D8", "F1", "R44", "R45", "C59", "R21", *[d[0] for d in DETECTOR]]


def silkscreen() -> list[str]:
    """The designators of the parts placed here, and of any part whose designator the new copper
    or outlines now cover, by refine.py's method; every other designator stays where it is and
    is an obstacle."""
    import refine

    space = refine.SilkSpace(fx.B)
    courtyards = []
    redo = list(MOVED)
    footprints = sorted(fx.B.GetFootprints(), key=lambda f: f.GetReference())
    for f in footprints:
        poly = pcbnew.SHAPE_POLY_SET(f.GetCourtyard(pcbnew.F_CrtYd))
        if poly.OutlineCount():
            poly.Deflate(fx.mm(0.25), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, fx.mm(0.01))
            courtyards.append((f.GetReference(), poly))
    for f in footprints:
        r = f.Reference()
        if f.GetReference() in MOVED or not r.IsVisible() or r.GetLayer() != pcbnew.F_SilkS:
            continue
        if space.free(r):
            space.take(r)
        else:
            redo.append(f.GetReference())
    hidden = []
    for ref in sorted(redo, key=lambda r: (refine._area(fp(r)), r)):
        f = fp(ref)
        r = f.Reference()
        r.SetLayer(pcbnew.F_SilkS)
        r.SetTextSize(pcbnew.VECTOR2I(fx.mm(refine.REF_SIZE), fx.mm(refine.REF_SIZE)))
        r.SetTextThickness(fx.mm(refine.REF_STROKE))
        r.SetKeepUpright(True)
        r.SetVisible(True)
        best = None
        for strict in (True, False):
            for (x, y), angle in refine._candidates(f, r):
                r.SetTextAngle(pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
                r.SetPosition(fx.pt(round(x, 3), round(y, 3)))
                if not space.free(r):
                    continue
                if strict and refine._over_a_body(r, courtyards):
                    continue
                best = ((round(x, 3), round(y, 3)), angle)
                break
            if best:
                break
        if best is None:
            r.SetVisible(False)
            hidden.append(ref)
            continue
        r.SetTextAngle(pcbnew.EDA_ANGLE(best[1], pcbnew.DEGREES_T))
        r.SetPosition(fx.pt(*best[0]))
        space.take(r)
    print("designators placed:", ", ".join(sorted(redo)))
    return hidden


# --- run ------------------------------------------------------------------------------------------------


def main() -> int:
    fx.B = pcbnew.LoadBoard(str(LAYOUT))
    usb()
    sbu()
    detector()
    corner()
    failed = [] if "--no-routes" in sys.argv else routes()
    hidden = silkscreen()
    if hidden:
        print("designators without a free spot (hidden):", ", ".join(hidden))
    pcbnew.ZONE_FILLER(fx.B).Fill(fx.B.Zones())
    pcbnew.SaveBoard(str(LAYOUT), fx.B)
    if failed:
        print("\n".join(failed))
        return 1
    if "--no-sync" not in sys.argv:
        env = dict(
            line.split("=", 1)
            for line in (ROOT / "versions.env").read_text().splitlines()
            if "=" in line and not line.startswith("#")
        )
        subprocess.run(
            ["pcb", f"+{env['PCB_TOOLCHAIN'].strip()}", "layout", "--no-open", "boards/main/main.zen"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
