# As-built L6205D and TSC2020 blocks on the current main board:
# courtyard bounding box per footprint, with pcbnew. Usage: python3 area_board.py boards/main/layout/main.kicad_pcb
import sys, pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
tot = 0
for r in ["IC5","D6","D7","C37","C38","C39","C40","C41","C65","C66","R34","R35","R32","R33","IC3","IC4","C67","C68"]:
    fp = b.FindFootprintByReference(r)
    if not fp: print(r, "missing"); continue
    bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox() if fp.GetLayer() == pcbnew.F_Cu else fp.GetCourtyard(pcbnew.B_CrtYd).BBox()
    w, h = bb.GetWidth()/1e6, bb.GetHeight()/1e6
    print(f"{r:4s} {fp.GetFPIDAsString():50s} {w:5.2f} x {h:5.2f} = {w*h:6.1f} mm2  {fp.GetLayerName()}")
