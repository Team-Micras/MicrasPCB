"""KiKit tabs plugin: one tab on the middle of each board's top edge, none anywhere else.

KiKit loads this file itself (`--tabs "plugin; code: <this file>.TopTab; arg: <width mm>"`, from
micras_pcb.panel), in KiKit's environment on KiCad's Python: it is not imported by micras_pcb.
KiKit's own tab types put tabs on every side that faces a neighbour or the frame; the wall board
may only be held by its blade's top edge (spec/wall.toml [panel]), the edge at the top of the
board as drawn (KiCad's smallest y).
"""

from kikit.annotations import TabAnnotation
from kikit.plugin import TabsPlugin
from kikit.units import mm


class TopTab(TabsPlugin):
    def buildTabAnnotations(self, panel):
        width = float(self.userArg) * mm
        for s in panel.substrates:
            minx, miny, maxx, _ = s.bounds()
            # On the top edge, pointing into the board: KiKit grows the tab from the board outward
            # to the partition line, the frame.
            s.annotations.append(TabAnnotation(None, ((minx + maxx) / 2, miny), (0, 1), width))
