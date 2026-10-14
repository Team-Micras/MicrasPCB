# Previous Bluetooth module revision

`board.json` is a machine-readable snapshot of the previous Micras Bluetooth module: every
footprint with its designator, part fields, placement and pad nets. The board in
`boards/bluetooth` is checked against it with `micras-pcb previous compare bluetooth`. The format
is documented in `tools/micras_pcb/previous.py`.

Do not edit `board.json` by hand. Regenerate it from the previous revision (not in this repo; needs
`kicad-cli`):

```sh
MICRAS_PREVIOUS=~/codes/hw_debug uv run micras-pcb previous snapshot bluetooth          # rewrite board.json
MICRAS_PREVIOUS=~/codes/hw_debug uv run micras-pcb previous snapshot bluetooth --check  # verify it is current
```

## Provenance

The module was designed in Altium (project `MicrasBluetoothModule.PrjPcb`, in
`hw_debug/modules/bluetooth/`). The snapshot reads the Altium files directly; `board.json` →
`source.files` holds the sha256 of each input:

- `MicrasBluetoothModule.PcbDoc`, converted to KiCad 10 by `kicad-cli pcb import --format altium`
  on each run: placement, pad nets, layer stack, outline;
- `MicrasBluetoothModule.SchDoc`: part fields (value, part number, manufacturer, LCSC number,
  description) from the component parameters;
- `MicrasBluetoothModule.netlist.txt`, the netlist extracted from the SchDoc: it must group the
  pads as the converted PCB does.

The other files of the project:

| File | sha256 |
|---|---|
| `MicrasBluetoothModule.PrjPcb` | `095e011ce1d11925b446d9c60bc70742cac91124559aeba2a51a7d01f4b6a847` |

The library files (`MicrasBluetoothModuleLib.PcbLib`, `.SchLib`) are not in `hw_debug`; the
footprints of the converted PCB are the library's, and the component packages take them from
there.

## What is the truth

- **Pad nets come from the PCB.** The extracted netlist agrees with it on every net.
- **Part fields** come from the SchDoc. Parts from the LCSC library (C1, D1, USB1) name their
  fields `Manufacturer Part`, `Manufacturer` and `Supplier Part`; parts from the Altium library
  (R1-R3, C2) `Manufacturer_Part_Number` and `Manufacturer_Name`. There is no JLCPCB BOM, so
  `in_jlc_bom` is false throughout and only C1, D1 and USB1 carry an LCSC number.

## Things to know

- 9 footprints: U1 (HM-19), USB1 (USB-C plug), R1-R3, C1, C2, D1 on the top side; OP1, the open
  pad of the key, on the bottom side.
- U1 has no part number in the SchDoc. R3's manufacturer field says KEMET; its part number
  RC0603FR-07680RL is a YAGEO resistor.
- 2 copper layers, 0.79 mm (0.7 mm FR-4 core, 35 um copper, 10 um mask per side), from the
  PcbDoc layer stack.
- The pad nets match the design review's reading of the module
  (`hw_debug/review_research/04_sensors_peripherals.md` section 9): HM-19 UART_TX (pin 2)
  through R1 to both plug D- contacts, UART_RX (pin 4) through R2 to both D+, 3V3 from both SBU
  contacts, VBUS, CC1/CC2 and RESETB unconnected.
