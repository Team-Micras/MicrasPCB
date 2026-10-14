# Previous encoder board revision

`board.json` is a machine-readable snapshot of the previous Micras encoder board: every footprint
with its designator, part fields, placement and pad nets. The board in `boards/encoder` is checked
against it with `micras-pcb previous compare encoder`. The format is documented in
`tools/micras_pcb/previous.py`.

Do not edit `board.json` by hand. Regenerate it from the previous revision (not in this repo; needs
`kicad-cli`):

```sh
MICRAS_PREVIOUS=~/codes/hw_debug uv run micras-pcb previous snapshot encoder          # rewrite board.json
MICRAS_PREVIOUS=~/codes/hw_debug uv run micras-pcb previous snapshot encoder --check  # verify it is current
```

## Provenance

The board was designed in Altium (project `MicrasEncoder.PrjPcb`, in `hw_debug/modules/encoder/`).
The snapshot reads the Altium files directly; `board.json` → `source.files` holds the sha256 of
each input. The other files of the project:

| File | sha256 |
|---|---|
| `MicrasEncoder.PrjPcb` | `925d44c9a0d0babf729405b271a7635fc1dbf954329e38f56dcfd2adcc75b698` |
| `EncoderLib.PcbLib` | `e69b929e6811a6cbfc8bd3f08a735cc49122f1b8dc8b379b7d7bb729aed853f9` |
| `EncoderLib.SchLib` | `13af9101e83f1d4be1106dcecb284d0303e92ab2f1de0a4d27eca9cbaecf0e95` |
| `CAMtastic1.Cam` | `29e5aa8237655becb3da436b6554917337e046c3f4f3e7164c5f6dccd63c2009` |

## What is the truth

- **Pad nets come from the PCB** (`MicrasEncoder.PcbDoc`, converted with `kicad-cli pcb import`
  on every run). The Altium netlist export (`Encoder.netlist.txt`) must group the pads the same
  way, or the snapshot fails.
- **Part fields** (value, MPN, manufacturer, description) come from the component parameters of
  `Encoder.SchDoc` (`Comment`, `Manufacturer_Part_Number`, `Manufacturer_Name`, the component
  description). The project has no JLCPCB BOM, so `lcsc` is empty.

## Things to know

- 3 footprints: IC1 (AS5047U-HTSM, `EncoderLib:SOP65P640X120-14N`), C1 (100 nF 0603, Fenghua
  0603B104K500NT, `MicrasLib:CAPC1608X90N`) and J1 (the edge tab, `EncoderLib:ENCODER_CONN`, no
  part number).
- IC1 pins 8 (W/PWM), 9 (V), 10 (U) and 14 (I/PWM) have no net; pin 5 (TEST) is on GND.
- Thickness 0.79 mm (0.70 mm core, 2 x 35 um copper, 2 x 10 um mask), 2 copper layers.
- The Edge.Cuts outline is 9.6 x 14.1 mm; each tapered side is about 750 short lines (the Altium
  outline's curve, as converted).
