# Previous main board revision

`board.json` is a machine-readable snapshot of the previous Micras main board: every footprint
with its designator, part fields, placement and pad nets. The replicated board (`boards/main`) is
checked against it with `micras-pcb previous compare main`, which must find exactly the changes
declared in `boards/main/changes.toml`. The layout transfer reads positions from it. The format
is documented in `tools/micras_pcb/previous.py`.

Do not edit `board.json` by hand. Regenerate it from the previous revision (not in this repo):

```sh
MICRAS_PREVIOUS=~/codes/hw_debug uv run micras-pcb previous snapshot          # rewrite board.json
MICRAS_PREVIOUS=~/codes/hw_debug uv run micras-pcb previous snapshot --check  # verify it is current
```

## Provenance

The board was designed in Altium (project `MicrasMainBoard_2025-12-03T09_54_52_UTC.PrjPcb`) and
converted to KiCad 10 in `hw_debug/kicad/`. The snapshot reads the converted PCB, the converted
schematic sheets and the JLCPCB assembly BOM; `board.json` → `source.files` holds the sha256 of
each. The Altium sources the conversion came from (`hw_debug/kicad/altium_src/`):

| File | sha256 |
|---|---|
| `MicrasMainBoard.PcbDoc` | `f2d7d62c50337fe95ea44ae649c07e8b96147f4293a12db9e99630f73a9d1614` |
| `MicrasMainBoard_2025-12-03T09_54_52_UTC.PrjPcb` | `a9e4b3055b4a74063cd70dba91b5207042605c7f3e2f3229a3c3bf1bccc75e17` |
| `Main.SchDoc` | `c2fb59da2d9be2f5fdd635cbd0254249a6515304d514056936bbe76ec207b020` |
| `Regulators.SchDoc` | `3350558003c21768443a3dbdef799af688bab7b86a8b9d921243071f9214c862` |
| `Drivers.SchDoc` | `cf67d9ab4173d6286b9d2dc493dcd46abb7aeb4887dfb83e4b0b43d76922c315` |
| `Sensors.SchDoc` | `220e963cb734c40be0ee9f08b3ed4a862b9fec367c07433da45f81e37eb7b973` |
| `Peripherals.SchDoc` | `9ddb5c88e5c2bbd31c8eadab463b4bcd90b0c49a68860304e5ae7d13e32750a5` |
| `MicrasLib.SchLib` | `80904d1c25df9612c41719c4bcd9de7e75c97785ccddad63cbaf2edff07b8ff6` |
| `MicrasLib.PcbLib` | `357aed97773145c5006caf5ebd210c1d0d12287917106dbcc878c910085ce3b5` |

## What is the truth

- **Pad nets come from the PCB**, converted from the Altium PCB the boards were made from. The converted
  schematic has a conversion artifact: it merges `Motor_L_Sense-` and `Motor_R_Sense-` into one
  net. The PCB keeps them apart (R33 pad 1 on `Motor_L_Sense-`, R32 pad 1 on `Motor_R_Sense-`).
- **Part fields** (value, MPN, manufacturer, description) come from the schematic symbols; the
  Altium parameter names vary per part (`MANUFACTURER PART` or `MANUFACTURER_PART_NUMBER`,
  `MANUFACTURER` or `MANUFACTURER_NAME`).
- **LCSC numbers** come from the JLCPCB BOM (`MicrasMainBoard-BOM-jlc.csv`, Latin-1 encoded),
  which is what was assembled. It disagrees with the schematic only on C22/C23 (BOM C5137554,
  schematic C1549).

## Things to know

- 154 footprints: 144 BOM parts, 6 PCB-only test points and 4 unnamed footprints.
- The 6 test points (`20V`, `FAN_ENABLE`, `FAN_OVERCURRENT`, `FAN_PWM`, `IMU_INT1`, `IMU_INT2`)
  have no schematic symbol and are not in the BOM; their designators are net names. The `20V`
  test point's pad has no net in the converted PCB.
- The 4 unnamed footprints (`NONAME1`-`NONAME4`, numbered by position) are single 2.4 mm
  non-plated holes: the board's M2 screw holes (`hw_debug/notes_tcc.md`: holes for M2 flat-head
  screws).
- Q6 (PRPAK3x3-8L) repeats pad numbers 2 and 3; all pads with one number share a net.
- U3's SOT-89 tab is a pad without a number and without a net; pads without a number are left
  out of the snapshot.
- The file has no stackup section; its board thickness is 1.0412 mm, 4 copper layers.
- IC1 (STM32H725RGV6, VFQFPN68; DS13311 Table 8): VBAT 1, VSSSMPS 4, VLXSMPS 5, VDDSMPS 6,
  VFBSMPS 7, VDD 9/22/35/51/68, VCAP 33/49/66, exposed pad 69 (VSS). On this board pad 1 is on
  `VBAT` (review C1) and VCAP 33/49/66 and VFBSMPS 7 are on four separate nets (review C2).
