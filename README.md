# MicrasPCB

The Micras micromouse PCBs, designed as code: circuits in [Zener](https://docs.pcb.new) (the
Diode `pcb` toolchain), layout in KiCad 10, and every check, fab output and review file built by
CI.

| Board | Status |
|---|---|
| `encoder`: AS5047U wheel encoder daughterboard, 2 layers, 0.8 mm | routed, all checks clean, rotations not yet verified at JLCPCB |
| `main`: STM32H725 controller, power, motor and fan drivers, sensors, 4 layers, 1.04 mm | circuit done, same connectivity as the previous revision plus two declared changes; placement and routing not yet transferred; fails the design checks where that revision has faults ([known faults](boards/main/README.md#known-faults)) |
| `bluetooth` | not started |

## How it fits together

```text
spec/<board>.toml ──────────────┐ outline, tab, spec-placed parts      ┌─> build/<board>/<board>_mech.json
                                 v                                      │   (MicrasHardware, micras-simulation)
boards/<board>/<board>.zen ──> pcb apply ──> layout/<board>.kicad_sch   │
components/**/*.zen             (Zener)      layout/<board>.kicad_pcb <─┘ placement + routing in KiCad
                                                     │
          make check: build · warnings · tests · sync · spec · ERC · LVS · previous · DRC · DFM · pytest · parts
                                                     │
          make review: renders · schematic · layers · 3D · BOM · fab zip ──>  CI artifact
```

- **Zener owns the circuit.** Parts, nets, values, stackup and design rules are code, with
  datasheet evidence in docstrings and `pcb test` test benches for the datasheet requirements.
  `pcb apply` writes the KiCad schematic and syncs the netlist into the layout, keeping hand
  placement and routing (sync is idempotent: a regeneration of an unchanged design is
  byte-identical).
- **`spec/` owns the mechanics.** `micras-pcb mech` writes the Edge.Cuts outline, the origin and
  the locked position of mechanically critical parts (the encoder's sensor and tab) into the
  `.kicad_pcb`, and exports them for the other repos. CI fails if the layout drifts.
- **KiCad owns placement and routing**, which stay human-led.
- **`parts/jlc.toml` owns sourcing**: MPN to LCSC number, basic/extended, placement rotation.

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
make setup                                                                            # uv env + pinned pcb toolchain
```

Optional: the [Zener VS Code extension](https://docs.pcb.new/pages/vscode) shows a live
schematic preview of `.zen` files.

## Everyday commands

```sh
make gen        # regenerate KiCad files from the sources (run after every source change)
make check      # every gate CI runs, with a pass/FAIL summary
make review     # build/<board>/review and fab: schematic PDF, layer SVGs, renders, GLB/STEP, fab package
make fab        # build/<board>/fab: JLCPCB gerbers zip, BOM and CPL
pcb open boards/encoder/encoder.zen     # open the layout in KiCad
make parts-online   # JLCPCB stock and basic/extended status (run before ordering)
```

`make check` runs every gate below, even after one fails, then prints a pass/FAIL line per gate
and fails if any gate failed.

| Gate | Tool | Catches |
|---|---|---|
| build | `pcb` | Zener errors, electrical type checks (power pins), formatting, dependency drift |
| warnings | `pcb build -D warnings` | a build warning: a net outside a part's declared operating range, a capacitor rated below its net |
| test | `pcb test` | datasheet requirements: per component (`components/**/test/`) and per board (`boards/<board>/test/`: application circuits, values computed with the datasheet equations) |
| layout-check | `pcb layout --check`, `micras-pcb rules/mech --check` | layout no longer matches the netlist, rules or spec drift |
| ERC | `kicad-cli sch erc` | schematic electrical rules; `boards/<board>/erc.toml` names the nets supplied from off the board (the PWR_FLAG role) |
| LVS | `micras-pcb lvs` | schematic and PCB connect different pads |
| previous | `micras-pcb previous compare main` | the main board connects anything differently from its previous revision, except the changes in `boards/main/changes.toml` |
| DRC | `kicad-cli pcb drc` + `rules/jlcpcb.kicad_dru` | JLCPCB clearances (copper, SMD pad to pad, hole to track), widths, drills, edge distances |
| DFM | `pcb dfm` + `rules/jlcpcb-pdk.toml` | geometry-level manufacturability (Diode's sourced JLCPCB PDK) |
| pytest | `pytest` | board contracts (encoder joint, firmware pin map), power tree, decoupling at the pin, encoder slot fit, courtyards, paste, 3D models, part data |
| lint | `ruff` | Python lint and format |
| parts | `micras-pcb parts` | a part without an LCSC mapping |

The main board fails several of these by design: it replicates its previous revision, faults
included, and [`boards/main/README.md`](boards/main/README.md#known-faults) gives the root cause of
every failure.

## CI

- `.github/workflows/ci.yml`: on every push and PR, installs the pinned KiCad and Zener,
  checks that `make gen` changes nothing, runs `make check`, builds the review outputs and fab package
  (uploaded as the run's artifact).
- `.github/dependabot.yml`: weekly PRs for new GitHub Actions and Python dev-tool releases.
  KiCad and Zener stay pinned in `versions.env` and are bumped by hand, since a bump can change
  the generated files.
- JLCPCB stock is not checked in CI (it changes daily and the API is undocumented): run
  `make parts-online` before ordering.

To look at a board, download the run's artifact, or open the project in KiCad
(`pcb open boards/<board>/<board>.zen`). A self-hosted [KiCad Prism](https://github.com/krishna-swaroop/KiCAD-Prism)
is the planned online viewer; there is none yet.

## Working with Claude Code

`CLAUDE.md` holds the agent rules. `.claude/settings.json` adds two hooks: one rebuilds any
`.zen` file the agent edits and feeds errors back immediately; the other blocks text edits to
generated or KiCad-owned files. `.claude/skills/` holds the `micras-pcb` workflow skill (parts,
JLCPCB outputs, KiCad scripting, review gates) and Diode's Zener skills (language, component
librarian, SPICE). Agents write code and deterministic tools grade it; people own footprint and
pin-1 checks, placement and routing, and the fab order.

## Repository

```text
boards/<board>/        <board>.zen, pcb.toml, layout/ (KiCad project: .kicad_pcb is KiCad-owned, the rest generated)
boards/main/previous/  snapshot of the previous main board revision (board.json) for the connectivity comparison
boards/main/firmware.toml  the firmware's pin map and drive settings (from MicrasFirmware), tested against the board
boards/<board>/test/   Zener test benches of the board's circuit
components/<mfr>/<P>/  reusable Zener packages: symbol, footprint (STEP embedded), .zen, test bench, README
spec/                  mechanical single source of truth per board
parts/jlc.toml         MPN -> LCSC mapping
rules/                 JLCPCB KiCad DRC rules, DFM PDK, KiCad rule severities
tools/micras_pcb/      Python glue: mech, lvs, checks, jlc, outputs, previous, firmware, layout (`uv run micras-pcb --help`)
tests/                 pytest design tests
ci/                    KiCad and toolchain install, for CI and local setup
versions.env           pinned KiCad and Zener versions
```
