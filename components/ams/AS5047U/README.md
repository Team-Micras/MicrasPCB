# AS5047U

14-bit on-axis magnetic rotary position sensor (ams OSRAM AS5047U-HTSM, TSSOP-14), wired for
**3.3 V supply mode**: VDD and VDD3V3 tied, one 100 nF X7R decoupling capacitor, TEST to GND.
Evidence and datasheet references are in the docstring of [`AS5047U.zen`](AS5047U.zen).

```python
load("@stdlib/interfaces.zen", "Spi")
AS5047U = Module("github.com/Team-Micras/MicrasPCB/components/ams/AS5047U/AS5047U.zen")

AS5047U(name="ENCODER", VDD=V3V3, GND=GND, SPI=Spi("SPI"), A=ENC_A, B=ENC_B)
```

Integration notes:

- The SPI host must keep CSn, CLK and MOSI driven (datasheet note 1).
- Place the package centred on the magnet axis: the Hall array is at the package centre,
  0.306 mm below the package top.
- Footprint and STEP are the KiCad library TSSOP-14_4.4x5mm_P0.65mm (JEDEC MO-153 AB-1), which
  matches the datasheet's package outline (Figure 60). The STEP is embedded in the footprint.
