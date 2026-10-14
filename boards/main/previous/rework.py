"""The two copper changes of the main board against its previous revision: C1 and C2.

`transfer_layout.py` copies the previous board's copper with every net renamed to its new owner,
then calls `apply` on the copied items (their s-expression text). Coordinates are KiCad
millimetres on the previous board's frame; UUIDs of existing items are the previous board's.

C1, MCU VBAT on 3V3 (boards/main/changes.toml C1; ST AN5419 Table 2: VBAT tied to VDD when no
backup battery is used). On the previous board IC1 pad 1 (VBAT), C8 pad 2 and C9 pad 2 sit on a
short top-layer cluster, joined to the battery net through the via at (155.105, 75.582) and a
dedicated chain: bottom layer to the via at (157.010, 84.345), top layer to the via at
(160.820, 91.584), bottom layer to the via at (165.392, 96.791) on the inner-layer VBAT plane.
- The chain from that first via on is removed (tracks, vias and their teardrops): it served only
  the cluster, so no stub stays behind.
- The cluster (pad 1 track, C8/C9 tracks, the via at (155.105, 75.582) and their teardrops) goes
  to 3V3. That via now lands on the In2.Cu 3V3 plane under the MCU, which surrounds it.
- A 0.2 mm top-layer bridge joins pad 1 to pad 68 (VDD, 3V3), the next pad across the package
  corner: centre to centre, x = 153.175885 from y = 76.06729 to 77.12795. It keeps 0.2 mm from
  pads 2 and 67, the closest other pads.

C2, VFBSMPS and VCAP1-3 on one VCORE net (changes.toml C2; AN5419 Figure 5, Direct SMPS
supply: VCAP pins tied together and to VFBSMPS, 100 nF kept at each VCAP pin). The core current
of the on-chip SMPS now flows from L1, C3 and C4 to the three VCAP pins, so it gets an inner
layer route: In2.Cu (the power plane layer; In1.Cu stays a solid ground plane), 0.5 mm wide
(0.4 mm on the last 2.7 mm to VCAP1, between the Switch_3 and LED_Blue vias), routed as a tree
so the 3V3 plane still flows around it:
- VFBSMPS end: the existing via at (155.957, 73.587) next to C3/C4 (L1 side of the net).
- VCAP3 (pad 66, C5): new via at (153.980, 78.630) between the pad 66 and pad 68 tracks, with a
  0.254 mm top-layer stub to the pad 66 track at (153.763283, 78.846718). The bottom-layer
  Encoder_Right_CSn track at x = 153.498 leaves no wider spot: 0.13 mm clearance.
- VCAP2 (pad 49, C6): the existing pair of vias at (146.469, 81.929) and (144.437, 82.552).
- VCAP1 (pad 33, C7): new via at (141.749905, 75.18046) on the pad 33 to C7 track.
- In2.Cu route: from the VFBSMPS via down x = 155.957 to y = 76.9, diagonally to the VCAP3 via,
  diagonally up to (152.41, 77.06), west under the package along y = 77.06 (midway between
  the exposed pad's ground vias) to (143.63, 77.06), diagonally to the VCAP1 via; a branch from
  (148.2, 77.06) runs down to (148.2, 80.198) and diagonally to the VCAP2 via.
"""

from __future__ import annotations

import uuid

from micras_pcb import sexpr

_NS = uuid.UUID("9d3c2b71-0e54-4f7b-8a6f-c41b5e2d7a90")

# C1: the VBAT chain from the cluster's via to the inner-layer plane (previous board UUIDs).
C1_CHAIN = {
    "1e946935-155a-42f9-90a9-fb64a3a960c6",  # B.Cu (155.079, 75.607)-(155.105, 75.582)
    "8de0be82-d24a-4e7f-a837-abc456583f4b",  # B.Cu (155.079, 76.572)-(155.079, 75.607)
    "c1512f95-98a0-43c2-ab77-d4fce312dd13",  # B.Cu (155.079, 76.572)-(157.010, 78.503)
    "0cdbea6a-f9be-40b0-a639-92afcf9da716",  # B.Cu (157.010, 84.345)-(157.010, 78.503)
    "a959e30b-ad2e-484e-98c4-065c9873dc7a",  # via (157.010, 84.345)
    "0e3e478e-9c06-43fa-a199-5747941379bd",  # F.Cu (157.010, 87.774)-(157.010, 84.345)
    "ec751501-beb3-47b5-a251-73e9fa26898c",  # F.Cu (157.010, 87.774)-(160.820, 91.584)
    "ef230b91-c927-42fc-953e-cc2d0e12a782",  # via (160.820, 91.584)
    "e69a6dbc-c6a3-4e92-a170-9e23cbd41b48",  # B.Cu (160.820, 91.584)-(165.368, 96.132)
    "57462d10-7151-4dd1-b49a-81fd46c97a7a",  # B.Cu (165.368, 96.767)-(165.368, 96.132)
    "fb05de96-8f08-4d72-96ef-64f0a602e2fd",  # B.Cu (165.368, 96.767)-(165.392, 96.791)
    "bae02311-5112-4b22-9189-712f3ccd4089",  # via (165.392, 96.791), on the In2.Cu VBAT plane
}
# C1: VBAT copper inside this box (x0, y0, x1, y1) is the IC1 pad 1 / C8 / C9 cluster.
C1_CLUSTER = (152.9, 75.4, 155.8, 77.0)
C1_BRIDGE = ((153.175885, 76.06729), (153.175885, 77.12795))  # IC1 pad 1 centre -> pad 68 centre

# C2: new vias and tracks on VCORE.
C2_VIAS = {"VCAP3": (153.98, 78.63), "VCAP1": (141.749905, 75.18046)}
C2_TRACKS = [
    # (name, layer, width, start, end)
    ("VCAP3 stub", "F.Cu", 0.254, (153.98, 78.63), (153.763283, 78.846718)),
    ("FB down", "In2.Cu", 0.5, (155.956605, 73.58709), (155.956605, 76.9)),
    ("FB to VCAP3", "In2.Cu", 0.5, (155.956605, 76.9), (153.98, 78.63)),
    ("VCAP3 up", "In2.Cu", 0.5, (153.98, 78.63), (152.41, 77.06)),
    ("trunk east", "In2.Cu", 0.5, (152.41, 77.06), (148.2, 77.06)),
    ("trunk west", "In2.Cu", 0.5, (148.2, 77.06), (143.63, 77.06)),
    ("to VCAP1", "In2.Cu", 0.4, (143.63, 77.06), (141.749905, 75.18046)),
    ("branch down", "In2.Cu", 0.5, (148.2, 77.06), (148.2, 80.198)),
    ("to VCAP2", "In2.Cu", 0.5, (148.2, 80.198), (146.468595, 81.92924)),
]


def _uid(name: str) -> str:
    return str(uuid.uuid5(_NS, name))


def _pt(p: tuple[float, float]) -> str:
    return f"{sexpr.fmt(p[0])} {sexpr.fmt(p[1])}"


def segment(name: str, layer: str, width: float, a, b, net: str) -> str:
    return (
        f"\t(segment\n\t\t(start {_pt(a)})\n\t\t(end {_pt(b)})\n\t\t(width {sexpr.fmt(width)})\n"
        f'\t\t(layer "{layer}")\n\t\t(net {sexpr.quote(net)})\n\t\t(uuid "{_uid(name)}")\n\t)\n'
    )


def via(name: str, at, net: str) -> str:
    return (
        f"\t(via\n\t\t(at {_pt(at)})\n\t\t(size 0.45)\n\t\t(drill 0.3)\n"
        f'\t\t(layers "F.Cu" "B.Cu")\n\t\t(tenting\n\t\t\t(front yes)\n\t\t\t(back yes)\n\t\t)\n'
        f'\t\t(net {sexpr.quote(net)})\n\t\t(uuid "{_uid(name)}")\n\t)\n'
    )


def _points(n: sexpr.Node) -> list[tuple[float, float]]:
    """Every coordinate of a track, via or zone outline."""
    if n.head == "zone":
        return [(float(a), float(b)) for a, b in (xy.atoms() for xy in n.child("polygon").child("pts").children("xy"))]
    return [tuple(float(v) for v in n.child(k).atoms()) for k in ("start", "end", "at") if n.child(k)]


def _layer(n: sexpr.Node) -> str | None:
    layer = n.child("layer")
    return layer.atoms()[0] if layer else None


def _net(n: sexpr.Node) -> str | None:
    net = n.child("net")
    return net.atoms()[-1] if net else None


def _inside(p, box) -> bool:
    return box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]


def _bbox(pts, grow: float):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs) - grow, min(ys) - grow, max(xs) + grow, max(ys) + grow


def apply(items: list[str]) -> list[str]:
    nodes = [sexpr.parse(t) for t in items]
    uid = [n.child("uuid").atoms()[0] if n.child("uuid") else None for n in nodes]

    # C1: drop the chain, then the teardrops that sat on it (a VBAT teardrop whose outline, grown by
    # 0.25 mm, holds an end of a dropped track on its layer or a dropped via: a teardrop starts at
    # the edge of its 0.45 mm via pad, up to 0.225 mm from the via centre where the tracks end).
    dropped = [n for n, u in zip(nodes, uid, strict=True) if u in C1_CHAIN]
    if len(dropped) != len(C1_CHAIN):
        raise SystemExit("C1: the previous board's VBAT chain is not where rework.py expects it")
    keep = [u not in C1_CHAIN for u in uid]
    for i, n in enumerate(nodes):
        if n.head != "zone" or _net(n) != "VBAT" or (n.child("priority") and int(n.child("priority").atoms()[0]) < 100):
            continue
        box = _bbox(_points(n), 0.25)
        for d in dropped:
            on_layer = d.head == "via" or _layer(d) == _layer(n)
            if on_layer and any(_inside(p, box) for p in _points(d)):
                keep[i] = False
    out = []
    renamed = 0
    for text, n, k in zip(items, nodes, keep, strict=True):
        if not k:
            continue
        if _net(n) == "VBAT" and all(_inside(p, C1_CLUSTER) for p in _points(n)):
            text = text.replace('(net "VBAT")', '(net "3V3")')
            renamed += 1
        out.append(text)
    if renamed != 17:  # 10 tracks, 1 via, 6 teardrops
        raise SystemExit(f"C1: expected 17 cluster items on VBAT, found {renamed}")
    out.append(segment("C1 bridge", "F.Cu", 0.2, *C1_BRIDGE, "3V3"))

    # C2
    for name, at in C2_VIAS.items():
        out.append(via(f"C2 {name} via", at, "VCORE"))
    for name, layer, width, a, b in C2_TRACKS:
        out.append(segment(f"C2 {name}", layer, width, a, b, "VCORE"))
    return out
