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
- Routing style, for people and layout scripts alike: every track a straight segment at a multiple
  of 45 degrees (end within 1 um of the 45-degree line), no arc tracks, and no two segments of a
  net meeting at an interior angle below 90 degrees outside a pad or via (an acid trap).
  `test_tracks_are_octilinear_without_acute_corners` in `tests/test_layout.py` names every
  offending segment and corner.
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

## Schematic placement

`make gen` writes each board's schematic afresh with `pcb apply`, then `micras-pcb sch` places it
from `boards/<board>/schematic/<sheet>.toml` (one file per sheet: `<board>.toml` for the root,
`<MODULE>.toml` for a module sheet). The tool moves pcb's parts, redraws every connection and
fails unless KiCad's netlist of the placed schematic equals pcb's (nets, names, pins), so a
placement file can only change how the circuit is drawn. Never edit the `.kicad_sch`; change the
placement file and run `uv run micras-pcb sch <board>` (it regenerates pcb's output itself and
takes a few seconds), or `make gen`.

Units are grid steps of 1.27 mm, x right and y down from the page's top-left corner; part anchors
and wire points are integers, so every pin lands on KiCad's grid.

```toml
paper = "A3"                        # smallest standard size that holds the sheet comfortably
title = "Motor and fan drivers"     # the title block's title
ports = { at = [12, 150], rows = 12, title = "Sheet ports" }  # module sheets, see below

[[block]]                           # one function block: a titled frame, its parts and wires
title = "Fan driver: STSPIN958"
at = [10, 12]                       # frame's top-left corner, and the origin of what follows
size = [136, 86]                    # frame size (or frame = [[x, y, w, h, "title"], ...])
parts.IC6 = [64, 46]                # [x, y] or [x, y, rotation]
parts.C31 = { at = [52, 20], rot = 180, mirror = "x", fields = "left" }
wires = [
    ["IC6.13", [60, 18], [52, 18], "C31.2"],   # pins (REF.number, or REF.name if unique) and points
    [[60, 18], [60, 16]],                      # a free end: the net's power symbol or label goes here
    [[92, 38], [92, 34], { label = "right" }], # options for the free end before them
]
taps = ["IC6.15"]                   # a wired net's label at this pin, along its wire
stubs."IC6.12" = { point = "out" }  # per pin: len (stub, grid steps), label = "right"|"left"|"up"|"down",
                                    # point = "out" (power symbol along the pin, not up/down)
```

- A pin not in any wire keeps what pcb attached: a stub (2 steps, none for a power symbol already
  pointing its way) and its label or power symbol; supplies point up, grounds down. No-connect
  flags stay at the pin.
- A wire chain joins pins of one net (the tool refuses two nets), routing each step straight or
  with one bend that leaves and enters pins along their axis; give corner points for anything
  else. A wired net's labels or power symbols go at the chain's free ends, else at its `taps`,
  else (a local label) along the wire at its first pin; a power or global label needs a free end.
- `fields`: `right`, `left` (two-pin parts standing up: default right), `top`, `bottom` (lying
  down: default top), `top-left`, `top-right`, `bottom-left`, `bottom-right`, or `[dx, dy]` from
  the anchor; ICs default to a free corner above or below the body.
- A pin pcb gave several labels (on a module sheet, a hierarchical and a global label of one net,
  diodeinc/pcb#1520) keeps one at the pin; each further label goes to the sheet's `ports` column,
  wired to a copy of the first.
- The root sheet places each module's sheet symbol: `[sheet.DRIVERS] at = [x, y]`,
  `size = [w, h]`, `left = [pin names in order]`, `right = [...]` (unlisted pins go left).

Conventions: one titled block per function (power input, each regulator, each bridge with its
shunt, the MCU with its decoupling and clock, each sensor channel, connectors); signal flow left
to right, supplies up, ground down; decoupling capacitors beside the pins they serve, wired to
them; pulls at their pins; blocks talk through labels, wires stay inside a block; no wire
crossings. Two-pin parts need about 17 steps of width for their value text.

To write or fix a sheet: `uv run micras-pcb sch --info <SHEET> <board> [REF...]` prints each
part's body box and pins (grid steps from the anchor, unrotated) with what pcb attached; after
placing, `micras-pcb sch` lists every overlap on the placed sheets (texts, bodies, wires, page
border, title block; `tests/test_placement.py` fails on any), and
`kicad-cli sch export svg -o <dir> boards/<board>/layout/<board>.kicad_sch` renders each sheet to
look at. `make check` fails while a part has no placement (`micras-pcb sch --check`): a new part
appears where pcb put it until its sheet's file places it.

## Mechanics

Origin, mechanically critical parts and the board outline come from `spec/<board>.toml`, every
value `{value, source}`. `make gen` writes them into the layout (parts locked) and exports
`build/<board>/<board>_mech.json` for MicrasHardware, micras-simulation and the firmware. The
outlines are layout geometry (the boards keep their previous revisions'), and `micras-pcb mech`
checks each has every interface feature of its spec (`spec/encoder.toml`: tab, reliefs, shoulder,
tapers, corners, extents; `spec/main.toml`: encoder slots, screw holes, USB-C peg holes, fan hole,
wheel notches, extents; `spec/bluetooth.toml`: extents, the HM-19's position). Change a mechanical number in the spec, never in the layout or in
another repo; an outline change goes in both.
