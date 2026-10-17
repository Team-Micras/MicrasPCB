# Footprint courtyard areas for the driver and current-sense blocks (two motors).
# Courtyard = bounding box of F.CrtYd graphics in the KiCad 10 standard library footprints
# (text-parsed). The as-built L6205D block on the current board is measured separately with
# pcbnew (area_board.py). Bulk capacitance is common to every option and listed separately.
import re
LIB = "/usr/share/kicad/footprints/"
def crtyd(path):
    s = open(path).read()
    xs, ys = [], []
    # every s-expression block that ends on layer F.CrtYd
    for blk in re.finditer(r"\((fp_line|fp_rect|fp_poly)(.*?)\(layer \"F\.CrtYd\"\)", s, re.S):
        for x, y in re.findall(r"\((?:start|end|xy) ([-\d.]+) ([-\d.]+)\)", blk.group(2)):
            xs.append(float(x)); ys.append(float(y))
    return max(xs) - min(xs), max(ys) - min(ys)
P = {
 "DRV8874 HTSSOP-16 PWP": "Package_SO/HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm_Mask2.46x2.31mm_ThermalVias",
 "DRV8262 HTSSOP-44 DDW": "Package_SO/HTSSOP-44-1EP_6.1x14mm_P0.635mm_EP5.2x14mm_Mask4.31x8.26mm_ThermalVias",
 "L6205D SO20 (SOIC-20W)": "Package_SO/SOIC-20W_7.5x12.8mm_P1.27mm",
 "INA241 VSSOP-8 DGK": "Package_SO/VSSOP-8_3x3mm_P0.65mm",
 "WSK2512 4-terminal": "Resistor_SMD/R_Shunt_Vishay_WSK2512_6332Metric_T1.19mm",
 "0402": "Capacitor_SMD/C_0402_1005Metric",
 "0603": "Capacitor_SMD/C_0603_1608Metric",
 "0805": "Capacitor_SMD/C_0805_2012Metric",
 "SOD-323": "Diode_SMD/D_SOD-323",
}
A = {}
for k, p in P.items():
    lib, fp = p.split("/")
    w, h = crtyd(f"{LIB}{lib}.pretty/{fp}.kicad_mod"); A[k] = w * h
    print(f"{k:24s} {w:5.2f} x {h:5.2f} mm = {w*h:6.1f} mm2   ({fp})")
blocks = {
 # D6/D7 1N4148W, CBOOT 220 nF 0805, CP 10 nF, RP 100R, REN 100k, CEN 10n, VS 100 nF (Table 1/2, Fig. 3/6)
 "L6205D x1 (both motors)": [("L6205D SO20 (SOIC-20W)", 1), ("SOD-323", 2), ("0805", 1), ("0402", 5)],
 # per IC (Table 1): 0.1 uF VM, 100 nF VCP, 22 nF CPH-CPL, RIPROPI, RIMODE (+ optional 10 nF IPROPI);
 # shared: VREF divider (2), nFAULT pull-up (1)
 "DRV8874 x2": [("DRV8874 HTSSOP-16 PWP", 2), ("0402", 2 * 5 + 3)],
 # Table 6-1: 2 x 0.01 uF VM, 1 uF VCP, 0.1 uF CPH-CPL (VM-rated, 0603), 1 uF DVDD, 0.1 uF VCC,
 # 2 RIPROPI, VREF divider (2, shared), nFAULT 10k
 "DRV8262 x1 (both motors)": [("DRV8262 HTSSOP-44 DDW", 1), ("0402", 9), ("0603", 1)],
}
print()
for name, items in blocks.items():
    tot = sum(A[k] * n for k, n in items)
    print(f"{name:26s} courtyard sum {tot:6.1f} mm2  (x1.5 for fan-out/vias ~ {1.5*tot:4.0f} mm2)")
ina = A["INA241 VSSOP-8 DGK"] + A["WSK2512 4-terminal"] + 3 * A["0402"]  # VS 100 nF, R_iso, C_f
print(f"INA241 chain per motor (amp + WSK2512 + 3 x 0402) {ina:5.1f} mm2; two motors {2*ina:5.1f} mm2 (x1.5 ~ {3*ina:4.0f} mm2)")
print(f"Common to all: 2-4 x 10 uF 0805 per bridge pair = {2*A['0805']:.0f}-{4*A['0805']:.0f} mm2 per bridge, plus bulk")
