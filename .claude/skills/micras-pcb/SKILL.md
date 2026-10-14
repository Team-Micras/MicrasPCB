---
name: micras-pcb
description: Work on the MicrasPCB boards: add or change a part, source it at JLCPCB, build or check the fab package, change mechanics, or script a KiCad file.
---

# MicrasPCB workflow

`CLAUDE.md` has the rules and the gen/check loop; this skill adds how the toolchain behaves and
where its limits are.

## Trust the gates, not your own reading

Models sound confident about circuits that would never work. Every claim about a board is
checked by a deterministic tool: `pcb build` (types, voltage ranges; `make warnings` fails on any
warning), `pcb test` (datasheet requirements), ERC, LVS, DRC, DFM and pytest. When a requirement
matters and no gate covers it, add one: a `pcb test` bench for a component's datasheet rule, a
bench in `boards/<board>/test/` for an application circuit (it instantiates the whole board and
computes values with the datasheet equations), a pytest in `tests/` for a netlist, layout or
cross-file rule (power tree, a board-to-board joint, the firmware pin map, decoupling distance,
spec geometry). Each check cites its source and names the parts in its failure message.

`boards/main/firmware.toml` is the firmware's pin map and drive settings. When MicrasFirmware
changes them, regenerate it (`MICRAS_FIRMWARE=<checkout> uv run micras-pcb firmware snapshot`);
`tests/test_firmware.py` then shows what the board must change. A board change the firmware
must follow (a new ADC pin, a new input) goes in `boards/main/firmware_changes.toml`, which the
tests apply on top of `firmware.toml` until MicrasFirmware has it; list it in the board README's
"Firmware changes".

People own three things: footprint and pin-1 checks, placement and routing, and the fab order.
Prepare these for review; never sign them off.

## Toolchain facts

- Zener (`pcb`) is pre-1.0 and renames or removes commands between releases. Use the pinned
  toolchain (`pcb +$PCB_TOOLCHAIN`, as the Makefile does) and its `--help`; do not rely on older
  examples. Version bumps go in their own PR.
- KiCad 10 has no headless layout or schematic API: the IPC API needs a running KiCad, and the
  SWIG `pcbnew` module is deprecated and goes away in KiCad 11. New tools use `kicad-cli` and
  `micras_pcb.sexpr` (span-preserving s-expression edits, so diffs stay small) rather than
  `pcbnew`; a one-off layout script may use `pcbnew`. A layout change runs only as a script the
  user approved.
- `.kicad_pcb` files do not merge in git. Do not rebase or merge across someone else's layout
  edits; ask.

## Adding a part

1. Footprint: a KiCad library footprint when one matches the datasheet package; otherwise draw it
   from the datasheet land pattern. Footprints from EasyEDA/LCSC converters have documented errors
   (reversed polarity, wrong pin numbering, mismatched pads): never take one unchecked. Embed the
   STEP and compare it with the pads.
2. Zener: `Part(mpn=..., manufacturer=...)` (or `mpn`/`manufacturer` on stdlib generics), with the
   datasheet figure or table cited for every pin and value. Follow the `librarian` skill for a new
   package.
3. `parts/jlc.toml`: one entry per MPN with `lcsc`, `type`, `rotation = 0`,
   `rotation_verified = false` and a dated `source`. Prefer JLCPCB basic parts: each extended part
   adds a loading fee per order. Look up stock and type with `make parts-online` (JLCPCB's
   undocumented parts-search endpoint; a failure there is not a design failure).

Parts that are copper on the board, such as the encoder's edge tab, use `skip_bom=True`: they
stay out of the BOM, the CPL and `parts/jlc.toml`.

## JLCPCB outputs

`make fab` writes `build/<board>/fab/`:

- `<board>-gerbers.zip`: copper, paste, silk, mask and Edge.Cuts gerbers plus Excellon drills,
  from `kicad-cli`, relative to the drill origin (the spec origin).
- `<board>-bom-jlcpcb.csv`: Comment, Designator, Footprint, `LCSC Part #`, MPN; from `pcb bom`
  and `parts/jlc.toml`. An MPN without an entry fails the build.
- `<board>-cpl-jlcpcb.csv`: Designator, Mid X, Mid Y, Layer, Rotation; KiCad's placement plus the
  part's `rotation` offset. Zener's own JLC export applies no rotation corrections, which is why
  this one exists.

KiCad and JLCPCB disagree on the zero rotation of some packages, and no database of offsets is
complete. The user checks each part once in JLCPCB's placement preview, then sets
`rotation_verified = true` (fixing `rotation` first if needed). `make fab` lists the parts still
unverified. Ordering is a manual upload: JLCPCB has no ordering API open to small teams.

## Mechanics

Origin, mechanically critical parts and the board outline come from `spec/<board>.toml`, every
value `{value, source}`. `make gen` writes them into the layout (parts locked) and exports
`build/<board>/<board>_mech.json` for MicrasHardware, micras-simulation and the firmware. The
outlines are layout geometry (the boards keep their previous revisions'), and `micras-pcb mech`
checks each has every interface feature of its spec (`spec/encoder.toml`: tab, reliefs, shoulder,
tapers, corners, extents; `spec/main.toml`: encoder slots, screw holes, USB-C peg holes, fan hole,
wheel notches, extents; `spec/bluetooth.toml`: extents, the HM-19's position). Change a mechanical number in the spec, never in the layout or in
another repo; an outline change goes in both.
