# AS5047U

14-bit on-axis magnetic rotary position sensor (ams OSRAM AS5047U-HTSM, TSSOP-14), wired for
**3.3 V supply mode**: VDD and VDD3V3 tied, TEST to GND, U/V/W and I/PWM open. Bare part: the
100 nF decoupling capacitor of Figure 11 belongs to the board. Evidence and datasheet references
are in the docstring of [`AS5047U.zen`](AS5047U.zen).

```python
load("@stdlib/interfaces.zen", "Spi")
AS5047U = Module("github.com/Team-Micras/MicrasPCB/components/ams/AS5047U/AS5047U.zen")

AS5047U(name="IC1", VDD=V3V3, GND=GND, SPI=Spi("SPI"), A=ENC_A, B=ENC_B)
Capacitor(name="C1", value="100nF", package="0603", P1=V3V3, P2=GND)
```

Reference prefix `IC`. MPN `AS5047U-HTSM`, ams OSRAM, LCSC C2153630.

Integration notes:

- 100 nF from the tied VDD/VDD3V3 node to GND (Figure 11, 3.3 V operation).
- The SPI host must keep CSn, CLK and MOSI driven (datasheet note 1).
- Place the package centred on the magnet axis: the Hall array is at the package centre,
  0.306 mm below the package top.

## Footprint

`SOP65P640X120-14N.kicad_mod`: TSSOP-14 4.4 x 5.0 mm, 0.65 mm pitch (IPC-7351 name), pads
1.475 x 0.45 mm on 5.876 mm row centres, from the Micras Altium EncoderLib (the footprint of IC1
on the MicrasEncoder board). Its STEP (`AS5047P-ATSM.step`, the library's TSSOP-14 model) is
embedded: 6.4 x 5.0 mm over the leads, 1.2 mm high, the E, D and A max of DS Figure 60;
`pcb rectify check`: OK. Silkscreen on F.SilkS; the
4.4 x 5.0 mm body outline with its pin 1 chamfer on F.Fab; the courtyard on F.CrtYd, a
7.85 x 5.6 mm rectangle (the library's, 0.25 mm beyond the pads and 0.3 mm beyond the body:
at least the IPC-7351B nominal courtyard excess).
