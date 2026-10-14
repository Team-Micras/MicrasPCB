# HSBB3072

HUASHUO HSBB3072 30 V 100 A N-channel MOSFET (2.4 mOhm max at VGS = 10 V), PRPAK3x3-8L, as a
bare part. Evidence and datasheet references are in the docstring of
[`HSBB3072.zen`](HSBB3072.zen). Datasheet: HUASHUO HSBB3072 Ver 3.0.

```python
HSBB3072 = Module("github.com/Team-Micras/MicrasPCB/components/huashuo/HSBB3072/HSBB3072.zen")

HSBB3072(name="Q6", G=GATE, D=GND, S=GND_BAT)
```

Reference prefix: `Q`.

## Pinout

| Symbol pin / pad | Name | Type | io | Package pins (page 1) |
|---|---|---|---|---|
| 1 (one pad) | G | input | `G` | 4 |
| 2 (three pads) | S | passive | `S` | 1, 2, 3 |
| 3 (seven pads) | D | passive | `D` | 5-8, exposed pad, two side tabs |

## Limits for the board (page 1-2)

VDS 30 V; VGS +-20 V; RDS(on) 2.4 mOhm max at 10 V, 3.8 mOhm max at 4.5 V; VGS(th) 1.0 to 2.3 V;
Ciss 2860 pF; body diode VSD 1.2 V max at 1 A; RthJA 70 C/W max on 1 in2 2 oz copper.

## Footprint

`PRPAK-8_L3.0-W3.0-P0.65-BL-EP.kicad_mod`: land pattern from the Micras Altium library
(MicrasMainBoard). The copper pads have no paste of their own (paste margin -100 mm); the
stencil apertures are the five F.Paste shapes drawn in the footprint. The embedded STEP is the
AOS AON7611 DFN 3x3 model, the same outline class but not this exact part.
`pcb rectify check` passes.
