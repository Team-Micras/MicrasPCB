# 1N4148W

Hongjiacheng (R+O) 1N4148W (LCSC C7420318): fast switching diode, 100 V, 150 mA, trr 4 ns, SOD-123.
Evidence is in the docstring of [`1N4148W.zen`](1N4148W.zen).

```python
Diode1N4148W = Module("github.com/Team-Micras/MicrasPCB/components/hongjiacheng/1N4148W/1N4148W.zen")

Diode1N4148W(name="D3", A=BUZZER_SWITCH, K=V3V3)
```

| Pad | Pin |
|---|---|
| 1 | A (anode) |
| 2 | K (cathode, marked by the silkscreen bar) |

Why not the stdlib `Rectifier` generic: it has no `mpn`/`manufacturer` config, so its offline BOM
line has no MPN for `parts/jlc.toml` to map, and its KiCad `D_SOD-123` footprint numbers the cathode
pad 1, the reverse of this footprint.

Courtyard: an F.CrtYd rectangle around the body outline (User.15) and the pads, 0.25 mm, the
IPC-7351B nominal courtyard excess (KiCad Library Conventions F5.3).
