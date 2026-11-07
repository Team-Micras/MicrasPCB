"""JLCPCB order options of each board, and a bare-board quote from them.

The options come from where each is decided: the surface finish and the mask and silkscreen
colours from the board's stackup (the Zener Board() config, which `pcb layout` writes into the
.kicad_pcb), the via class, the thickness and the assembly service from spec/<board>.toml [pcb], the
size from the outline or, for a board ordered as a panel, from spec [panel]. `micras-pcb fab`
writes them into build/<board>/fab/<board>-order.txt, the choices to make on JLCPCB's order page.

    micras-pcb quote main          # JLCPCB's bare-board price for those options (online)
"""

from __future__ import annotations

import json
import time
import urllib.request

from . import layout, panel, sexpr, spec
from .paths import board_pcb, boards, has_layout

CART = "https://cart.jlcpcb.com/api/overseas-core-platform/shoppingCart"
# KiCad's stackup finish names -> JLCPCB's order option (adornPut).
JLC_FINISH = {"ENIG": "ENIG-RoHS", "HAL SnPb": "HASL(with lead)", "HAL lead-free": "LeadFree HASL-RoHS", "OSP": "OSP"}
JLC_COLOURS = {"Green", "Red", "Yellow", "Blue", "White", "Black", "Purple"}
JLC_THICKNESS = [0.4, 0.6, 0.8, 1.0, 1.2, 1.6, 2.0]
# JLCPCB's "Min via hole size/diameter" order option, most to least common. PCB Capabilities
# (Drilling, accessed 2026-11-07): "0.1mm or 0.15mm hole size with any size via diameter, and 0.2mm
# or 0.25mm hole size with via diameter less than 0.45mm, will cost more. Please select
# corresponding via size option when placing order."
VIA_CLASSES = [
    (0.3, "0.3mm/(0.4/0.45mm)"),
    (0.25, "0.25mm/(0.35/0.4mm)"),
    (0.2, "0.2mm/(0.3/0.35mm)"),
    (0.15, "0.15mm/(0.25/0.3mm)"),
    (0.1, "0.1mm/(0.2/0.25mm)"),
]
_EPS = 1e-6


def via_class(drill: float, diameter: float) -> str:
    """JLCPCB's via option for a via: the default unless the hole is under 0.3 mm with copper
    under 0.45 mm, or under 0.2 mm; then the option of its hole size."""
    if drill >= 0.3 - _EPS or (drill >= 0.2 - _EPS and diameter >= 0.45 - _EPS):
        return VIA_CLASSES[0][1]
    for hole, name in VIA_CLASSES[1:]:
        if drill >= hole - _EPS:
            return name
    raise ValueError(f"JLCPCB makes no via with a {drill} mm hole")


def _rank(name: str) -> int:
    return [n for _, n in VIA_CLASSES].index(name)


def smallest_via(board: str) -> tuple[float, float]:
    """(drill, diameter) of the via that sets the board's via class: of the vias in the most
    demanding class, the smallest hole, then the smallest copper."""
    vias = [(v.drill, v.size) for v in layout.load(board).vias]
    worst = max(_rank(via_class(*v)) for v in vias)
    return min(v for v in vias if _rank(via_class(*v)) == worst)


def stackup(board: str) -> dict[str, str]:
    """The surface finish and the top mask and silkscreen colours of the board's stackup."""
    text = board_pcb(board).read_text()
    start = text.index("\n\t(setup")
    st = sexpr.parse(text[start : text.index("\n\t)", start) + 3]).child("stackup")
    colour = {
        layer.atoms()[0]: layer.child("color").atoms()[0] for layer in st.children("layer") if layer.child("color")
    }
    return {
        "finish": st.child("copper_finish").atoms()[0],
        "mask": colour["F.Mask"],
        "silk": colour["F.SilkS"],
    }


def panel_size(board: str) -> tuple[float, float]:
    """Width and height (mm) of the board's panel: `columns` boards and the frame round them."""
    p = panel.settings(board)
    x0, y0, x1, y1 = layout.load(board).outline_box()
    n, gap, frame = p["columns"], p["board_spacing"], p["frame_width"]
    return n * (x1 - x0) + (n - 1) * gap + 2 * (gap + frame), (y1 - y0) + 2 * (gap + frame)


def options(board: str) -> dict:
    """What to order: layers, thickness, size, finish, colours, via class, assembly."""
    pcb = spec.load(board)["pcb"]
    st = stackup(board)
    if st["finish"] not in JLC_FINISH:
        raise ValueError(f"{board}: JLCPCB offers no {st['finish']!r} finish ({', '.join(JLC_FINISH)})")
    for k in ("mask", "silk"):
        if st[k] not in JLC_COLOURS:
            raise ValueError(f"{board}: JLCPCB offers no {st[k]!r} {k}")
    p = panel.settings(board)
    if p:
        width, height = panel_size(board)
    else:
        x0, y0, x1, y1 = layout.load(board).outline_box()
        width, height = x1 - x0, y1 - y0
    drill, diameter = pcb["via_drill"], pcb["via_diameter"]
    return {
        "layers": pcb["copper_layers"],
        "thickness": min(JLC_THICKNESS, key=lambda t: abs(t - pcb["thickness"])),
        "width": round(width, 2),
        "height": round(height, 2),
        "boards_per_panel": p["columns"] if p else 1,
        "finish": st["finish"],
        "mask": st["mask"],
        "silk": st["silk"],
        "via": (drill, diameter),
        "via_class": via_class(drill, diameter),
        "assembly": pcb["assembly"],
    }


def form(board: str) -> str:
    """The choices to make on JLCPCB's order page, as text."""
    o = options(board)
    if o["boards_per_panel"] > 1:
        delivery = (
            f"Panel by Customer, {o['boards_per_panel']} boards (1 row x {o['boards_per_panel']} columns),"
            " mouse bites (the panel's gerbers)"
        )
    else:
        delivery = "Single PCB"
    assembly = {"economic": "Economic PCBA", "standard": "Standard PCBA", "none": "none"}[o["assembly"]]
    return "\n".join(
        [
            f"JLCPCB order options for {board} (spec/{board}.toml [pcb], the layout's stackup):",
            f"  Layers                    {o['layers']}",
            f"  Dimensions                {o['width']:g} x {o['height']:g} mm",
            f"  Delivery format           {delivery}",
            f"  PCB thickness             {o['thickness']:g} mm",
            f"  PCB color                 {o['mask']}",
            f"  Silkscreen                {o['silk']}",
            f"  Surface finish            {JLC_FINISH[o['finish']]}",
            f"  Min via hole size/diam.   {o['via_class']} (smallest via {o['via'][0]:g} / {o['via'][1]:g} mm)",
            f"  PCB assembly              {assembly}",
            "",
        ]
    )


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{CART}/{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "micras-pcb"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def price(o: dict, qty: int, via: str | None = None) -> dict:
    """JLCPCB's bare-board price for options `o` (JLCPCB's order calculator: undocumented and
    unauthenticated, the endpoint its order page uses; it can change without notice)."""
    services = {
        s["serviceConfigCode"]: s
        for s in _post("quereyOrderService", {"stencilLayer": o["layers"], "plateType": 1})["data"]
    }
    chosen = {"N2B": "Don't Add", "mvhc": via or o["via_class"]}
    vos = []
    for code, show in chosen.items():
        s = services[code]
        opt = next(x for x in s["configOptionListVos"] if x["configOptionShow"] == show)
        vos.append(
            {"serviceConfigAccessId": s["serviceConfigAccessId"], "configOptionAccessId": opt["configOptionAccessId"]}
        )
    goods = {
        "stencilLayer": o["layers"],
        "stencilWidth": o["width"],
        "stencilLength": o["height"],
        "stencilPly": f"{o['thickness']:.1f}",
        "stencilCounts": qty,
        "stencilNumber": 1,
        "plateType": 1,
        "cuprumThickness": 1,
        "adornPut": JLC_FINISH[o["finish"]],
        "adornColor": o["mask"],
        "charFontColor": o["silk"],
    }
    data = _post(
        "calculationGoodsCostsNew",
        {"calculationCostsType": 1, "pcbGoodsRequest": goods, "orderServiceConfigVos": vos},
    )
    tolls = (data.get("data") or {}).get("orderCountTolls")
    if not tolls:
        raise RuntimeError(f"JLCPCB's calculator answered: {data.get('message') or data}")
    return tolls


def quote(board: str, qty: int) -> int:
    """Print JLCPCB's bare-board price with the board's order options."""
    if not has_layout(board):
        print(f"{board}: no layout, nothing to quote")
        return 0
    o = options(board)
    print(form(board), end="")
    unit = "panels" if o["boards_per_panel"] > 1 else "boards"
    try:
        t = price(o, qty)
        time.sleep(1)
        base = price(o, qty, via=VIA_CLASSES[0][1]) if o["via_class"] != VIA_CLASSES[0][1] else t
    except Exception as e:  # an online lookup: report, do not fail a design change
        print(f"  quote failed: {e}")
        return 1
    total = float(t["dummyMoney"])
    print(f"  {qty} {unit}: US$ {total:.2f} bare boards, of which")
    print(f"    surface finish {JLC_FINISH[o['finish']]}  US$ {float(t.get('adornPutMoney') or 0):.2f}")
    print(f"    via class {o['via_class']}  US$ {total - float(base['dummyMoney']):.2f}")
    print("  (JLCPCB's order calculator, today's price; assembly, parts and shipping not included)")
    return 0


def quote_all(names: list[str], qty: int) -> int:
    return max((quote(b, qty) for b in names or boards()), default=0)
