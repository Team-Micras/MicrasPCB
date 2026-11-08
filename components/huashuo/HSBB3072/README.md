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
(MicrasMainBoard). The copper pads carry no paste layer; the stencil apertures are the five
F.Paste shapes drawn in the footprint. The embedded STEP is the
AOS AON7611 DFN 3x3 model, the same outline class but not this exact part.
`pcb rectify check` passes.

Courtyard: an F.CrtYd rectangle around the body outline (User.15) and the pads, 0.25 mm, the
IPC-7351B nominal courtyard excess (KiCad Library Conventions F5.3).

`paste` (config, default `"whole"`): `"split"` takes
`PRPAK-8_L3.0-W3.0-P0.65-BL-EP_SplitPaste.kicad_mod`, the same land with the drain paste split for
thermal vias left open in the exposed pad: the source leads' apertures as drawn, the drain leads'
and side tabs' apertures on their own, and the 2.6 x 2.0 mm pad in four windows (61 % of it)
round a 0.4 mm cross that holds four via sites, 0.2 mm circles on Cmts.User, where the layout
places its vias (TI SLUA271C (QFN and SON PCB Attachment) section 4.4: exposed-pad paste in windows covering 50-70 % of the pad, which lets it outgas; section 3.4.1: a smaller via loses less solder, and tenting a pad's via from the back traps air).
