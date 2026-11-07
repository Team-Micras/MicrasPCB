# MicrasPCB

The Micras micromouse PCBs, designed as code: circuits in [Zener](https://docs.pcb.new) (the
Diode `pcb` toolchain), layout in KiCad 10, and every check, fab output and review file built by
CI.

| Board | Status |
|---|---|
| `encoder`: AS5047U wheel encoder daughterboard, 2 layers, 0.79 mm | the previous revision's placement and routing, plus pull resistors on the sensor's SPI inputs; passes every check ([open items](boards/encoder/layout/README.md#open-items)) |
| `wall`: wall-sensor daughterboard (SFH 4550 over a TPS601A, upright, with the emitter's resistor and its AC-coupled selector, joined to the main board by a 2x3 1.27 mm header straddling its bottom edge), one per sensor, 2 layers, 0.79 mm, a paddle 16.0 mm high: 4.2 mm handle, 8.4 mm blade; JLCPCB fits the SMD parts on a 4-up panel, the sensor and header are hand-soldered | placed and routed, passes every check; the main board's wall joints W1-W4 take four ([open items](boards/wall/layout/README.md#open-items)) |
| `main`: STM32H725 controller, 4S power, DRV8874 wheel bridges with INA241 current sensing, fan driver, sensors, ESP32-C5 dual-band radio and debug probe, no USB ([research/next-revision](research/next-revision/README.md)), 4 layers, 1.04 mm, 91.15 x 50 mm | placed and routed for the six-pin wall slots, the fan ring and the ESP32 flashing pads: every connection routed, passes every check ([open items](boards/main/layout/README.md#open-items)) |

The v1 main board and its HM-19 Bluetooth module, which plugged into the v1 board's USB-C port,
are at the tag `v1` (e34fb9a).

## How it fits together

```text
spec/<board>.toml ──────────────┐ outline, tab, spec-placed parts      ┌─> build/<board>/<board>_mech.json
                                 v                                      │   (MicrasHardware, micras-simulation)
boards/<board>/<board>.zen ──> pcb apply ──> micras-pcb sch ──> layout/<board>.kicad_sch
components/**/*.zen             (Zener)          ^                layout/<board>.kicad_pcb <─┘ placement + routing in KiCad
boards/<board>/schematic/*.toml ─────────────────┘ schematic placement
                                                     │
          make check: build · warnings · tests · sync · spec · sch · ERC · LVS · previous · DRC · DFM · pytest · parts
                                                     │
          make review: renders · schematic · layers · 3D · assembly · BOM · fab zip ──>  CI artifact
```

- **Zener owns the circuit.** Parts, nets, values, stackup and design rules are code, with
  datasheet evidence in docstrings and `pcb test` test benches for the datasheet requirements.
  `pcb apply` writes the KiCad schematic and syncs the netlist into the layout, keeping hand
  placement and routing (sync is idempotent: a regeneration of an unchanged design is
  byte-identical).
- **`boards/<board>/schematic/` owns how the schematic is drawn.** `pcb apply` writes each sheet
  afresh; `micras-pcb sch` then places it from one file per sheet: where each part goes and how it
  turns, which pins are wired together, the titled frame of each function block, the paper size
  and the order of each module's sheet pins. It redraws every connection with the labels and
  power symbols pcb chose and fails unless KiCad's netlist of the placed schematic equals pcb's,
  so the drawing can never change the circuit. A part without an entry is drafted from the
  netlist by the same rules a person follows (blocks by connectivity, decoupling at the supply
  pin, pulls at their pins, repeated blocks alike, the smallest paper), steered by an optional
  `SCHEMATIC_HINTS` dict in the Zener module that pcb ignores; `micras-pcb sch --draft` writes the
  drafts into the file to adopt and adjust. The `micras-pcb` skill has the file format, the rules
  and the hints.
- **`spec/` owns the mechanics.** `micras-pcb mech` writes the origin and the locked position of
  mechanically critical parts (the encoder's sensor and tab, the wall board's sensor and header,
  the main board's screw holes, battery switch, ESP32 module and wall sensors) into the
  `.kicad_pcb`, and exports the board for the other repos. The main board's and the wall board's
  Edge.Cuts outlines are the spec's (`micras-pcb mech` draws them: the main board's nose, wheel
  notches, encoder slots, fan hole, antenna and switch notches; the wall board's bottom edge,
  sides and corners), and so is the main board's silkscreen of the fan ring and the drive
  blocks' outlines; the encoder's is layout
  geometry (it keeps its previous revision's), and the spec checks its interface features (tab,
  shoulder, tapers and extents). CI fails if the layout drifts.
- **KiCad owns placement and routing**, which stay human-led.
- **`parts/jlc.toml` owns sourcing**: MPN to LCSC number, basic/extended, placement rotation.
- **The order options** come from where each is decided: finish and colours from the Zener
  stackup, the via class and the assembly service from `spec/<board>.toml` `[pcb]` (a test holds
  the via class to the layout's smallest via), and a board under JLCPCB's 10 x 10 mm assembly
  minimum is ordered as the panel its spec's `[panel]` describes (KiKit, `make fab`). Every board is
  leaded HASL. JLCPCB prints no paste on the parts the team solders itself (`assembly = "hand"`):
  their paste goes to a separate stencil file (`micras-pcb` skill, JLCPCB outputs).

### Why Zener and KiCad

- **KiCad 10 is the contract between tools.** `kicad-cli` runs ERC, DRC and every export
  headless, MicrasHardware imports the board through KiCad's STEP, and JLCPCB's assembly flow is
  built around KiCad. The committed KiCad project is a complete design on its own: without Zener,
  the boards continue in plain KiCad and only the schematic stage changes.
- **Zener writes the schematic**, the part of KiCad that is weakest as code: KiCad 10 has no
  headless schematic API, and its verbose files are a poor target for language models. Zener emits
  a real KiCad schematic to review, syncs the netlist into the layout without touching hand
  placement and routing, type-checks power nets, runs datasheet test benches, and is built to be
  written by agents (its skills are in `.claude/skills/`).
- **`tools/micras_pcb` covers the rest**: the spec-driven outline and mech export, LVS, the rule
  checks, and the JLCPCB package with its rotation offsets.

### Known limits

- **Zener is pre-1.0 and changes fast**; commands get renamed or removed between releases. The
  toolchain is pinned in `versions.env` and bumped in its own PR, where CI shows what regenerates.
- **Zener has no LCSC picker, and its JLC placement export applies no rotation corrections.**
  `parts/jlc.toml` carries the LCSC number and a per-part rotation offset, and `make fab` builds
  the JLCPCB BOM and CPL from it. JLCPCB's placement preview is the final word on each part's
  rotation (`rotation_verified`).
- **Zener labels the nets between module sheets twice**: the main board's schematic has one
  sheet per Zener module (`Project(..., layout = False)`), and pcb 0.4.81 puts
  a global label beside each sheet pin and hierarchical label
  ([diodeinc/pcb#1520](https://github.com/diodeinc/pcb/issues/1520)), so KiCad's ERC warns
  `same_local_global_label` and `multiple_net_names` on those nets. The placement keeps the global
  label at the pin and draws the hierarchical one in the sheet's ports column, wired to a copy of
  the global one (`micras-pcb sch`). Each board's
  `erc.toml` accepts these two warnings with that reason, and only them; they go away with a pcb
  release that includes [diodeinc/pcb#1522](https://github.com/diodeinc/pcb/pull/1522)
  ([known faults](boards/main/layout/README.md#known-faults)).
- **KiCad 10 has no headless layout API**: the IPC API needs a running KiCad, and the SWIG
  `pcbnew` module is deprecated and goes away in KiCad 11. The tools use `kicad-cli` and edit the
  `.kicad_pcb` s-expressions directly (`tools/micras_pcb/sexpr.py`).
- **Git cannot merge a `.kicad_pcb` safely** (KiCad 10 has no merge driver): one person edits a
  board's layout at a time.
- **Footprints from EasyEDA/LCSC have documented errors** (reversed polarity, wrong pin numbering,
  mismatched pads). Use KiCad library footprints where they exist, and check every footprint
  against the datasheet land pattern, its 3D model and JLCPCB's preview.
- **JLCPCB has no ordering API open to small teams**: order by uploading `build/<board>/fab/` by
  hand.

## Setup (Linux / WSL2)

```sh
./ci/install-kicad.sh                                                                # KiCad 10 from the PPA, see versions.env
curl -fsSL https://raw.githubusercontent.com/diodeinc/pcb/main/install.sh | bash      # Zener toolchain launcher
make setup                                                                            # uv env + pinned pcb toolchain + KiKit
```

Optional: the [Zener VS Code extension](https://docs.pcb.new/pages/vscode) shows a live
schematic preview of `.zen` files.

## Everyday commands

```sh
make gen        # regenerate KiCad files from the sources (run after every source change)
make check      # every gate CI runs, with a pass/FAIL summary
make review     # build/<board>/review and fab: schematic PDF, layer SVGs, renders, GLB/STEP, fab package,
                #   and build/main/review/assembly.*: the main board with its wall and encoder boards in place
make fab        # build/<board>/fab: JLCPCB gerbers zip (no paste on hand-soldered parts), BOM, CPL, order options
                #   (the wall board's as a 4-up panel) and the team's stencil for the hand-soldered parts
pcb open boards/encoder/encoder.zen     # open the layout in KiCad
make parts-online   # JLCPCB stock and basic/extended status (run before ordering)
make quote          # JLCPCB's bare-board price with each board's finish, colours and via class
```

`make check` runs every gate below, even after one fails, then prints a pass/FAIL line per gate
and fails if any gate failed.

| Gate | Tool | Catches |
|---|---|---|
| build | `pcb` | Zener errors, electrical type checks (power pins), formatting, dependency drift |
| warnings | `pcb build -D warnings` | a build warning: a net outside a part's declared operating range, a capacitor rated below its net |
| test | `pcb test` | datasheet requirements: per component (`components/**/test/`) and per board (`boards/<board>/test/`: application circuits, values computed with the datasheet equations) |
| layout-check | `pcb layout --check`, `micras-pcb rules/mech --check` | layout no longer matches the netlist, rules or spec drift |
| sch | `micras-pcb sch --check` | a placement entry, wire or hint naming what its sheet does not have, a sheet symbol too small for its pins, overlaps or items off the page, a placed sheet out of date with the sources; prints how many parts each sheet drafts |
| ERC | `kicad-cli sch erc` | schematic electrical rules; `boards/<board>/erc.toml` names the nets supplied from off the board (the PWR_FLAG role) and the warnings a board accepts, rule by rule with the reason |
| LVS | `micras-pcb lvs` | schematic and PCB connect different pads |
| previous | `micras-pcb previous compare <board>` | a replicated board (the encoder) connects or names anything differently from its previous revision, except the changes in `boards/<board>/changes.toml` |
| DRC | `kicad-cli pcb drc` + `rules/jlcpcb.kicad_dru` | JLCPCB clearances (copper, SMD pad to pad, hole to track), widths, drills, edge distances |
| DFM | `pcb dfm` + `rules/jlcpcb-pdk.toml` | geometry-level manufacturability (Diode's sourced JLCPCB PDK) |
| pytest | `pytest` | board contracts (encoder joint, firmware pin map), the assembly (each wall and encoder board standing where the specs put it, its pads on its joint's, clear of the main board and its parts), the fab package (every assembled board or its panel at least 10 x 10 mm, the panel's outlines, tabs and CPL, each board's via class), power tree, every schematic item on its sheet's page, no overlapping texts, bodies or wires on a sheet, every board's schematic drafted whole from its Zener source (pcb's netlist, nothing overlapping), decoupling at the pin, encoder slot fit, routing style (every track straight at a multiple of 45 degrees, no arcs, no acute corners), courtyards, paste, 3D models, part data |
| lint | `ruff` | Python lint and format |
| parts | `micras-pcb parts` | a part without an LCSC mapping |

Every board passes every gate once laid out. A schematic-only board (its root declares `Project(layout = False)`, so it has no
`.kicad_pcb`) passes the schematic gates, and LVS, DRC, DFM, the layout tests and the gerber, CPL
and 3D outputs skip it with that reason; `make fab` writes
its BOM alone. The main board's README ([known faults](boards/main/layout/README.md#known-faults))
gives the root cause of each warning that remains.

## CI

- `.github/workflows/ci.yml`: on every push and PR, installs the pinned KiCad and Zener,
  checks that `make gen` changes nothing, runs `make check`, builds the review outputs and fab package
  (uploaded as the run's artifact).
- GitHub Actions, the Python dev tools (`uv.lock`), KiCad and Zener (`versions.env`) are bumped
  by hand; a KiCad or Zener bump can change the generated files.
- JLCPCB stock is not checked in CI (it changes daily and the API is undocumented): run
  `make parts-online` before ordering.

To look at a board, download the run's artifact, or open the project in KiCad
(`pcb open boards/<board>/<board>.zen`). The boards are also viewed online in a self-hosted
[KiCad Prism](https://github.com/krishna-swaroop/KiCAD-Prism), which takes each board's layout
folder as a project and shows the board's README from it (`boards/<board>/layout/README.md`).
Each layout folder's `.prism.json` names the root schematic and the board, so Prism does not take
the first sheet in the folder (main's `DRIVERS.kicad_sch`) as the root and drop it from the viewer.
Prism shows one board at a time; the robot's boards together are in the run's artifact:
`build/main/review/assembly.glb` and `assembly.step` (the main board with the four wall boards and
both encoder boards standing in their joints, origin at the robot's) and the renders
`assembly-iso-left.png`, `assembly-iso-right.png` (from the front-left and front-right) and
`assembly-top.png`. `micras-pcb assembly` places each daughterboard from the specs on a build copy
of the main board, as a 3D model on its joint footprint, and fails if KiCad's export puts it
anywhere else.

## Working with Claude Code

`CLAUDE.md` holds the agent rules. `.claude/settings.json` adds two hooks: one rebuilds any
`.zen` file the agent edits and feeds errors back immediately; the other blocks text edits to
generated or KiCad-owned files. `.claude/skills/` holds the `micras-pcb` workflow skill (parts,
JLCPCB outputs, KiCad scripting, review gates) and Diode's Zener skills (language, component
librarian, SPICE). Agents write code and deterministic tools grade it; people own footprint and
pin-1 checks, placement and routing, and the fab order.

## Repository

```text
boards/<board>/        <board>.zen, pcb.toml, layout/ (KiCad project: .kicad_pcb is KiCad-owned, README.md is
                       the board's description, .prism.json the root files for KiCad Prism, the rest generated)
boards/<board>/schematic/  one placement file per schematic sheet (micras-pcb sch): parts, wires, frames, paper;
                       drafted entries marked auto = true
boards/<board>/previous/  snapshot of the board's previous revision (board.json) for the connectivity comparison,
                       and the script that builds its layout from that revision (transfer_layout.py): the encoder
boards/main/layout/*.py  the main board's placement, routing and silkscreen scripts (place.py, route.py, silk.py;
                       its layout README says what each does) and their 45-degree grid router (router.py)
boards/main/firmware.toml  the firmware's pin map and drive settings (from MicrasFirmware), tested against the board
boards/main/firmware_changes.toml  the firmware changes the board needs, applied on top of firmware.toml in the tests
boards/<board>/test/   Zener test benches of the board's circuit
components/<mfr>/<P>/  reusable Zener packages: symbol, footprint (STEP embedded), .zen, test bench, README
spec/                  mechanical single source of truth per board; main_chassis.json, the chassis's shadow over the
                       main board from MicrasHardware's model (tools/chassis_shadow.py, run in that repo's environment)
parts/jlc.toml         MPN -> LCSC mapping
rules/                 JLCPCB KiCad DRC rules, DFM PDK, KiCad rule severities
tools/micras_pcb/      Python glue: mech, lvs, checks, jlc, panel, order, outputs, assembly, previous, firmware, layout,
                       schematic placement and drafts (`uv run micras-pcb --help`)
tests/                 pytest design tests
research/next-revision/ the main board's design research (entered as boards/main) and its calculation scripts
ci/                    KiCad, toolchain and KiKit install, for CI and local setup
versions.env           pinned KiCad, Zener, Freerouting and KiKit versions
```
