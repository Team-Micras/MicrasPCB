#!/usr/bin/env python3
"""Hand calculations for the power tree (research/next-revision/README.md).

Every input number carries its source in the comment next to it. Results are calculations, not
datasheet values.
"""
import math

LSB16 = 3.3 / 65536  # V

print("=== 1. Analog-rail (3V3_A) load budget ===")
# (name, typical A, maximum A, source)
loads = [
    ("VDDA: ADC1+ADC2 16-bit single-ended BOOST=11 @25 MHz, 2 x 720 uA", 2 * 720e-6, 2 * 1440e-6,
     "DS13311 Rev 5 Table 84: per ADC, maxima guaranteed by design (note 1; note 3, BGA and one ADC, "
     "covers only fs): 720 uA SE, 1440 uA differential"),
    ("VDDA: ADC3 12-bit at 1-5 MSPS", 122e-6, 430e-6, "DS13311 Table 87 (122-350 uA SE, 430 uA diff)"),
    ("2 x INA241A2 VS", 2 * 2.5e-3, 2 * 3.2e-3, "INA241 SBOSA30D sec. 6.5: IQ 2.5 typ, 3 max 25 C, 3.2 max -40..125 C"),
    ("4 x TPS601A collector (1 kOhm load, one lit + ambient)", 2.0e-3 + 3 * 0.3e-3, 4 * 3.1e-3,
     "max = 3.1 V / 1 kOhm saturation per sensor (target.hpp l.440-448); typ = assumption"),
    ("emitter CC sink: op-amp (TLV9001 IQ 60 uA typ), 200k bias, set-point DAC on VDDA/VREF+", 0.26e-3, 0.35e-3,
     "TLV9001 IQ 60 typ, 77 max at 5.5 V (SBOS833R sec. 7.10); 200 kOhm from 3V3_A, 16 uA; DAC buffer off "
     "20 uA from VDDA + 160 uA from VREF+ = VDDA on VFQFPN68, typ (DS13311 Table 90): 0.26 mA typ, max kept"),
]
opt = ("(optional) LSM6DSV Vdd, gyro+accel high-performance", 0.65e-3, 0.65e-3, "LSM6DSV DS13476 Rev 5 Table 4 IddHP")
ityp = sum(l[1] for l in loads)
imax = sum(l[2] for l in loads)
for n, a, b, s in loads + [opt]:
    print(f"  {n:72s} typ {a*1e3:5.2f} mA  max {b*1e3:5.2f} mA   [{s}]")
print(f"  TOTAL without IMU: typ {ityp*1e3:.1f} mA, max {imax*1e3:.1f} mA; with IMU +0.65 mA")

print("\n=== 2. Architecture C: LDO from VBAT, dissipation ===")
for vin in (12.0, 14.8, 16.8, 17.4):
    for i, tag in ((ityp, "typ"), (imax + 0.65e-3, "max")):
        ignd = 0.1e-3  # TPS7A49 IGND ~49 uA at 0 mA, 800 uA at 100 mA (SBVS121E 6.5) -> ~0.1 mA at 10-25 mA (interp.)
        p_total = vin * (i + ignd) - 3.3 * i
        for rpre in (0.0, 47.0, 220.0):
            p_r = i * i * rpre
            vin_ldo = vin - (i + ignd) * rpre
            p_ldo = (vin_ldo - 3.3) * i + vin_ldo * ignd
            if rpre == 47.0 or rpre == 0.0:
                pass
        print(f"  VBAT {vin:5.1f} V, I {tag} {i*1e3:5.1f} mA: total loss {p_total*1e3:6.1f} mW; "
              f"LDO alone (47 ohm pre-R) {((vin-(i+ignd)*47-3.3)*i + (vin-(i+ignd)*47)*ignd)*1e3:6.1f} mW; "
              f"rise in HVSSOP-8 (63.4 C/W) {((vin-(i+ignd)*47-3.3)*i)*63.4:4.1f} K")
print("  (TPS7A49 RthJA 63.4 C/W DGN, 47.7 C/W DRB: SBVS121E sec. 6.4)")

print("\n=== 3. Analog buck switching ripple (analytic, capacitive part, DS13554 Eq. 3 form) ===")
cases = [
    ("TPS560430X3F 1.1 MHz, 12 uH, 22 uF (15 uF eff)", 1.1e6, 12e-6, 15e-6),
    ("L6981N33 400 kHz, 22 uH, 44 uF (35 uF eff)", 400e3, 22e-6, 35e-6),
    ("LMR43610MB3 1 MHz, 10 uH (assumed), 22 uF (15 uF eff)", 1.0e6, 10e-6, 15e-6),
]
for n, f, L, C in cases:
    for vin in (12.0, 14.8, 17.4):
        dil = 3.3 * (1 - 3.3 / vin) / (L * f)
        dv = dil / (8 * C * f)
        print(f"  {n:50s} VIN {vin:4.1f}: dIL {dil*1e3:5.0f} mA p-p, dV {dv*1e6:6.0f} uV p-p = {dv/LSB16:5.1f} LSB16")


def lc_atten(f, L, C, R):
    w = 2 * math.pi * f
    z_l = complex(R, w * L)
    z_c = 1 / complex(0, w * C)
    return abs(z_c / (z_l + z_c))


print("\n  Second-stage filter attenuation |H| (ideal parts, + DCR/series R):")
for n, L, C, R in (("4.7 uH + 15 uF eff, 0.2 ohm", 4.7e-6, 15e-6, 0.2),
                   ("10 uH + 15 uF eff, 1.5 ohm total", 10e-6, 15e-6, 1.5),
                   ("0.5 uH bead + 10 uF, 0.1 ohm", 0.5e-6, 10e-6, 0.1)):
    f0 = 1 / (2 * math.pi * math.sqrt(L * C))
    q = math.sqrt(L / C) / R
    s = ", ".join(f"{f/1e3:g} kHz {20*math.log10(lc_atten(f, L, C, R)):6.1f} dB"
                  for f in (1e3, 10e3, f0, 100e3, 300e3, 400e3, 1.1e6, 2.2e6))
    print(f"  {n:34s} f0 {f0/1e3:5.1f} kHz Q {q:4.2f}: {s}")

print("\n=== 4. IR emitter constant-current sink: dissipation per supply ===")
I = 0.170          # A, firmware/Sensors.zen design current
VSENSE = 0.2       # V across the sense resistor (1.2 ohm), IR emitter sink proposal
# SFH 4550 VF at 170 mA from the diode fit to VF 1.5 V @ 0.1 A, 2.4 V @ 1 A (SFH-DS p5): RS 0.8, nVt 78.2 mV
VF_TYP = 0.0782 * math.log(I / 1.3e-9) + 0.8 * I
# max: 1.7 V @ 0.1 A max, 2.9 V @ 1 A max (SFH-DS p5) -> linear between
VF_MAX = 1.7 + (2.9 - 1.7) * (I - 0.1) / 0.9
DUTY_ONE = 0.150e-3 / 1e-3      # one emitter: 150 us per 1 ms frame (target.hpp l.409-425)
DUTY_SINK = 4 * DUTY_ONE        # shared sink: 4 emitters per frame
print(f"  VF at 170 mA: typ {VF_TYP:.3f} V (fit), max {VF_MAX:.3f} V (datasheet max points, linear)")
print(f"  duty: {DUTY_ONE*100:.0f} % per emitter, {DUTY_SINK*100:.0f} % for one shared sink")
supplies = [("3V3_D min (3.284 V - 22 mV emitter droop - 33 mV ESP dip)", 3.284 - 0.022 - 0.033),
            ("3V3_D typ", 3.30), ("5 V rail (L6981C50 typ)", 5.0),
            ("VBAT 12.0 V", 12.0), ("VBAT 14.8 V", 14.8), ("VBAT 17.4 V", 17.4)]
for n, vs in supplies:
    head_typ = vs - VF_TYP - VSENSE
    head_max = vs - VF_MAX - VSENSE
    if vs < 4:
        r = 3.3
    elif vs < 6:
        r = 15.0
    else:
        r = 53.0   # sized so the sink keeps >= 0.5 V at 11.5 V sagged with VF max
    v_r = I * r
    fet_typ = head_typ - v_r
    print(f"  {n:58s}: headroom (VF max) {head_max:5.2f} V; series R {r:4.1f} ohm; "
          f"FET {fet_typ:5.2f} V -> {fet_typ*I:5.3f} W peak, {fet_typ*I*DUTY_SINK:5.3f} W avg; "
          f"R {v_r*I:5.3f} W peak, {v_r*I*DUTY_ONE:5.3f} W avg each; supply {vs*I*DUTY_SINK:5.3f} W avg")

print("\n=== 5. Shared-ground coupling (per 1 mOhm of common return impedance) ===")
for n, di in (("emitter pulse 170 mA", 0.170), ("ESP32 TX step 95->355 mA", 0.260),
              ("MCU load step (e.g. 50 mA)", 0.050), ("one motor bridge, 2.4 A", 2.4)):
    dv = di * 1e-3
    print(f"  {n:28s}: {dv*1e6:7.1f} uV = {dv/LSB16:6.2f} LSB16 per mOhm")
print("  1 oz copper sheet resistance ~0.5 mOhm/square (general; 35 um Cu, 1.72e-8 ohm m)")
print(f"  -> {1.72e-8/35e-6*1e3:.2f} mOhm/sq")

print("\n=== 6. USB-only power budget (battery absent) ===")
mcu = 0.125 + 0.032 + 0.001   # DS13311 Table 24 125 mA typ (SMPS, 550 MHz) + 2 x AS5047U 16 mA + IMU
esp_pk, esp_rx = 0.355, 0.095  # ESP32-S3-MINI-1 Tables 6-4/6-5 (Wi-Fi TX peak 355 mA; RX ~93-97 mA)
emit = I * DUTY_SINK
ana = ityp
leds = 2 * 0.012 * 3            # 2 RGB LEDs at ~12 mA/colour full white (assumption pending the LED choice)
for tag, esp, em in (("flash/debug (no emitters, ESP RX)", esp_rx, 0.0),
                     ("ESP TX peak, no emitters", esp_pk, 0.0),
                     ("everything incl. emitters + LEDs white", esp_pk, emit)):
    i33 = mcu + esp + em + ana + (leds if 'LEDs' in tag else 0)
    for eta in (0.85,):
        i5 = 3.3 * i33 / (eta * 4.6)
        print(f"  {tag:42s}: 3V3 {i33*1e3:5.0f} mA -> VBUS {i5*1e3:5.0f} mA at eta {eta}, VSYS 4.6 V")
print("  USB 2.0 port: 500 mA after configuration; Type-C 'Default USB Power' = USB 2.0 500 mA / USB 3.x 900 mA")

print("\n=== 7. Noise floors the rail must stay below ===")
enob = 12.2   # DS13311 Table 86: typical ENOB 12.2 bits single-ended (16-bit ADC, BGA characterisation)
q_rms = 3.3 / 2 ** enob / math.sqrt(12)
print(f"  ADC own noise at ENOB {enob}: {q_rms*1e6:.0f} uV rms = {q_rms/LSB16:.1f} LSB16 rms")
en = 49e-9    # INA241A2 input noise density, nV/rtHz (SBOSA30D sec. 6.5)
g = 20
for name, enbw in (("INA241 alone, 1.1 MHz one-pole (ENBW = pi/2 x 1.1 MHz)", math.pi / 2 * 1.1e6),
                   ("with R_iso 100 ohm + C_f 2.2 nF (723 kHz) in series, ENBW ~ 0.6 MHz", 0.6e6)):
    v = en * g * math.sqrt(enbw)
    print(f"  {name}: {v*1e3:.2f} mV rms = {v/LSB16:.0f} LSB16 rms = {v/0.2*1e3:.1f} mA rms (10 mOhm x 20)")
print("  Rail error on a current reading with REF1 = VS = VDDA (ratiometric mid-scale): "
      "error = (G*R*I / VDDA) x dVDDA -> at 1 A: 0.2 V/3.3 V = 6 % of the rail error")

print("\n=== 8. Recommended damped post-filter (2.2 uH/50 mOhm, 15 uF eff, damping 0.33 ohm + 30 uF eff) ===")
L, RL, Cf, Rd, Cd = 2.2e-6, 0.05, 15e-6, 0.33, 30e-6
peak_h, peak_z = (0, 0), (0, 0)
for f in [10 ** (2 + 5 * i / 1999) for i in range(2000)]:
    w = 2 * math.pi * f
    zl = complex(RL, w * L)
    zc = 1 / complex(0, w * Cf) if f > 0 else 1e12
    zd = Rd + 1 / complex(0, w * Cd)
    zsh = 1 / (1 / zc + 1 / zd)
    h = abs(zsh / (zl + zsh))
    zout = abs(1 / (1 / zl + 1 / zsh))  # source (buck output) taken as ideal 0 ohm
    if h > peak_h[0]:
        peak_h = (h, f)
    if zout > peak_z[0]:
        peak_z = (zout, f)
print(f"  |H| peak {20*math.log10(peak_h[0]):+.1f} dB at {peak_h[1]/1e3:.1f} kHz; |Zout| peak {peak_z[0]*1e3:.0f} mOhm at {peak_z[1]/1e3:.1f} kHz")
for f in (1e5, 3e5, 1.1e6, 2.2e6):
    w = 2 * math.pi * f
    zl = complex(RL, w * L); zsh = 1 / (complex(0, w * Cf) + 1 / (Rd + 1 / complex(0, w * Cd)))
    print(f"  attenuation at {f/1e3:g} kHz: {20*math.log10(abs(zsh/(zl+zsh))):.1f} dB")
