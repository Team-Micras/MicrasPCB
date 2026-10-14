# MicrasPCB

The Micras micromouse PCBs, designed as code: circuits in [Zener](https://docs.pcb.new) (the
Diode `pcb` toolchain), layout in KiCad 10, and every check, fab output and review page built by
CI. The toolchain decision and its evidence are in
[`docs/research/PCB as code toolchain.md`](docs/research/PCB%20as%20code%20toolchain.md).

| Board | Status |
|---|---|
| `encoder`: AS5047U wheel encoder daughterboard, 2 layers, 0.8 mm | routed, all checks clean, rotations not yet verified at JLCPCB |
| `main` | not started |
| `bluetooth` | not started |

## How it fits together

```text
spec/<board>.toml ──────────────┐ outline, tab, spec-placed parts      ┌─> build/<board>/<board>_mech.json
                                 v                                      │   (MicrasHardware, micras-simulation)
boards/<board>/<board>.zen ──> pcb apply ──> layout/<board>.kicad_sch   │
components/**/*.zen             (Zener)      layout/<board>.kicad_pcb <─┘ placement + routing in KiCad
                                                     │
          make check: build · tests · sync · spec · ERC · LVS · DRC · DFM · pytest · parts
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
make check      # everything CI gates on
make review     # build/<board>/review and fab: schematic PDF, layer SVGs, renders, GLB/STEP, fab package
make fab        # build/<board>/fab: JLCPCB gerbers zip, BOM and CPL
pcb open boards/encoder/encoder.zen     # open the layout in KiCad
make parts-online   # JLCPCB stock and basic/extended status (run before ordering)
```

| Gate | Tool | Catches |
|---|---|---|
| build / fmt / sync | `pcb` | Zener errors, electrical type checks (voltage ranges, power pins), formatting, dependency drift |
| test benches | `pcb test` | datasheet requirements per component (e.g. AS5047U TEST pin grounded, VDD/VDD3V3 tied, 100 nF) |
| layout sync | `pcb layout --check` | layout no longer matches the netlist |
| spec drift | `micras-pcb mech --check` | outline or spec-placed parts moved |
| ERC | `kicad-cli sch erc` | schematic electrical rules |
| LVS | `micras-pcb lvs` | schematic and PCB connect different pads |
| DRC | `kicad-cli pcb drc` + `rules/jlcpcb.kicad_dru` | JLCPCB clearances, widths, drills, edge distances |
| DFM | `pcb dfm` + `rules/jlcpcb-pdk.toml` | geometry-level manufacturability (Diode's sourced JLCPCB PDK) |
| design tests | `pytest` | board contracts (encoder tab pinout), decoupling, single-pin nets, spec geometry |
| parts | `micras-pcb parts` | a part without an LCSC mapping |

## CI

- `.github/workflows/ci.yml`: on every push and PR, installs the pinned KiCad and Zener,
  checks that `make gen` changes nothing, runs `make check`, builds the review outputs and fab package
  (uploaded as the run's artifact).
- `.github/dependabot.yml`: weekly PRs for new GitHub Actions and Python dev-tool releases.
  KiCad and Zener stay pinned in `versions.env` and are bumped by hand, since a bump can change
  the generated files.
- JLCPCB stock is not checked in CI (it changes daily and the API is undocumented): run
  `make parts-online` before ordering.

## Working with Claude Code

`CLAUDE.md` holds the agent rules. `.claude/settings.json` adds two hooks: one rebuilds any
`.zen` file the agent edits and feeds errors back immediately; the other blocks text edits to
generated or KiCad-owned files. `.claude/skills/` vendors Diode's Zener skills (language,
component librarian, SPICE).

## Repository

```text
boards/<board>/        <board>.zen, pcb.toml, layout/ (KiCad project: .kicad_pcb is KiCad-owned, the rest generated)
components/<mfr>/<P>/  reusable Zener packages: symbol, footprint (STEP embedded), .zen, test bench, README
spec/                  mechanical single source of truth per board
parts/jlc.toml         MPN -> LCSC mapping
rules/                 JLCPCB KiCad DRC rules, DFM PDK, KiCad rule severities
tools/micras_pcb/      Python glue: mech, lvs, checks, jlc, outputs (`uv run micras-pcb --help`)
tests/                 pytest design tests
ci/                    KiCad and toolchain install, for CI and local setup
versions.env           pinned KiCad and Zener versions
docs/research/         toolchain research report and notes
```
