# LM66100

Texas Instruments LM66100DCKR (LCSC C2869734): 1.5-5.5 V, 1.5 A ideal diode (P-channel switch with
a comparator chip enable), SC-70-6. Bare part: input and output capacitors and the CE/ST wiring
belong to the board. Evidence is in the docstring of [`LM66100.zen`](LM66100.zen).

```python
LM66100 = Module("github.com/Team-Micras/MicrasPCB/components/ti/LM66100/LM66100.zen")

# Always-on reverse current blocking: CE on VOUT (SLVSEZ8A section 8.3.2), status unused.
LM66100(name="U5", VIN=PROBE_3V3, VOUT=V3V3, GND=GND, CE=V3V3, ST=GND)
```

Reference prefix `U`. VIN, VOUT and CE are rated 6 V absolute maximum (section 6.1): the part
cannot sit on a node that can exceed that.

## Pinout (SLVSEZ8A section 5, p3)

| Pad | Name | Symbol type | io |
|---|---|---|---|
| 1 | VIN | power_in | `VIN` |
| 2 | GND | power_in | `GND` |
| 3 | ~CE | input | `CE` |
| 4 | N/C | no_connect | (none, not internally connected) |
| 5 | ST | open_collector | `ST` |
| 6 | VOUT | power_out | `VOUT` |

## Footprint

`Texas_DCK0006A_SC-70-6.kicad_mod`, the land pattern of TI's DCK0006A example board layout
(4214835/D, in SLVSEZ8A): six 0.9 x 0.4 mm pads at x = +/-1.1 mm, 0.65 mm pitch, pads 1-3 down
the left side and 4-6 up the right side (top view), non-solder-mask-defined; body 1.25 x 2.0 mm
on F.Fab (DCK0006A outline 1.1-1.4 x 1.85-2.15 mm), F.CrtYd 0.25 mm (IPC-7351B nominal) around
pads and body. The package is JEDEC MO-203 variant AB, so the embedded STEP is KiCad's
`SOT-363_SC-70-6.step` (same pin 1 corner and pad order). `pcb rectify check`: OK.
