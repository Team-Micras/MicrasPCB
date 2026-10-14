# GT-TC048B-H025-L1

G-Switch GT-TC048B-H025-L1 (LCSC C778165): SPST-NO tactile switch with a white oval actuator,
4.2 x 3.2 x 2.5 mm, SMD-4P, 250 gf, 50 mA at 24 VDC. Evidence is in the docstring of
[`GT-TC048B-H025-L1.zen`](GT-TC048B-H025-L1.zen).

```python
Button = Module("github.com/Team-Micras/MicrasPCB/components/g-switch/GT-TC048B-H025-L1/GT-TC048B-H025-L1.zen")

Button(name="SW2", A=GND, B=BUTTON)
```

| Pads | IO | |
|---|---|---|
| 1, 2 | `A` | joined inside the switch |
| 3, 4 | `B` | joined inside the switch |

Pressing the actuator connects `A` to `B`. Both pads of a side carry the same pin name in the symbol,
so they always land on one net.

The embedded STEP is a C&K PTS810 model: same 4.2 x 3.2 mm body and pad layout, not this part's exact
actuator.

Courtyard: an F.CrtYd rectangle around the body outline (User.15) and the pads, 0.25 mm, the
IPC-7351B nominal courtyard excess (KiCad Library Conventions F5.3).
