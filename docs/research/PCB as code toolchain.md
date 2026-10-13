# Code the circuit in Zener, route it in KiCad 10

The recommended MicrasPCB toolchain has three layers. **KiCad 10.0.x is the backbone**: it owns the file format, layout, ERC/DRC, fab outputs, the STEP exports MicrasHardware already uses, and the exit path if anything above it fails. **Diode's Zener language and `pcb` CLI are the schematic-as-code front end**. They generate the KiCad project, sync into it, and keep your hand-routed layout intact. **A small Python/uv glue layer** makes one spec file drive the board outline, MicrasHardware, micras-simulation's `robot.toml` and the firmware pinout check. GitHub Actions wraps all of this: `pcb test` test benches, `kicad-cli` ERC/DRC against an in-repo JLCPCB rule file, ngspice/pytest testbenches, kicad-happy AI review, and KiBot fab outputs with JLC rotation corrections. For viewing, publish a static GitHub Pages portal now (interactive schematic/PCB, iBOM, a combined PCB-plus-chassis 3D scene, visual diffs). Add KiHub's free tier for PR review if the repo is public, and build a custom "Micras 365" later. No vendor unifies ECAD, MCAD and firmware the way your ecosystem needs. Zener beats atopile for three reasons: it emits real schematics, it has the most rigorous documented layout-preservation model, and it was co-developed with Anthropic for Claude authoring. atopile's constraint solver and LCSC picker are better, but its public repo has been frozen since March 2026. The main risks are Zener's pre-1.0 churn and hosted-service dependence, and KiCad 11's removal of the SWIG Python API. Both are bounded because every artifact that matters is a standard KiCad file. Confirm the choice with a two-week pilot on one subsystem with explicit kill criteria. If Zener fails, only the schematic stage changes; the rest of the pipeline stays the same.

## KiCad 10 is the foundation every option converges on

The Micras ecosystem already runs on KiCad 10. The old main board was designed in Altium and converted. Its `.kicad_sch` files carry `generator_version "10.0"`, and its DRC/ERC reports came from KiCad 10.0.6 ([hw_debug/kicad](file:///home/cosme/codes/hw_debug/kicad)). MicrasHardware's `tools/export_board.py` shells out to `kicad-cli pcb export step|stl|svg` and parses the `.kicad_pcb` s-expressions into `ref/board_mech.json`, which build123d consumes for clash checks and the OCP viewer ([export_board.py](file:///home/cosme/codes/MicrasHardware/tools/export_board.py)). Any toolchain that ends in a KiCad 10 project keeps that pipeline working unchanged. Anything else means rewriting it. One weakness needs fixing first. The script calls the **Windows** `kicad-cli.exe` through WSL interop, and the Linux side has no KiCad, so board import cannot run in CI today.

KiCad is also the healthiest project in this space by a wide margin. **10.0.0 shipped on 2026-03-20** after a 7,609-commit cycle, with donations routed through the Linux Foundation ([KiCad blog](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)). Point releases have come roughly monthly through **10.0.7 on 2026-10-06** ([KiCad GitLab tags](https://gitlab.com/kicad/code/kicad/-/tags)). `kicad-cli` is now a complete headless toolchain:

- ERC and DRC with JSON output and an exit code of 5 on violations.
- `--schematic-parity` and `--refill-zones` checks.
- Jobsets and per-command `--variant`.
- About 25 export formats, including Gerbers, IPC-2581, ODB++, STEP and GLB ([kicad-cli 10.0 reference](https://docs.kicad.org/10.0/en/cli/cli.html)).

Every code-first tool hands layout back to KiCad. Zener states that "KiCad 10.x is required for layouts" ([diodeinc/pcb](https://github.com/diodeinc/pcb)), atopile "updates your KiCad layout" ([atopile](https://github.com/atopile/atopile)), and tscircuit exports KiCad. The JLCPCB tooling is KiCad-centric too, and it all reduces to one plain `LCSC Part #` symbol field ([JLCPCB help](https://jlcpcb.com/help/article/how-to-generate-the-bom-and-centroid-file-from-kicad)). So choosing KiCad does not mean giving up on "as code". The real decision is what writes the schematic.

That is exactly where plain KiCad is weakest as a code platform. **KiCad 9 and 10 have no schematic IPC API.** The IPC API only talks to a running GUI, and headless operation arrives in KiCad 11 ([KiCad dev docs](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/)). The SWIG `pcbnew` bindings were deprecated in 9.0 and are slated for removal in 11.0 ([KiCad dev docs](https://dev-docs.kicad.org/en/apis-and-binding/pcbnew/)). Forum users expect that release around Feb/Mar 2027, though this is not official ([KiCad forum](https://forum.kicad.info/t/migration-schedule-from-the-old-swig-api-to-the-ipc-api/69437)). Raw KiCad files are also a poor target for language models. In the SchGen study, a model writing raw KiCad schematics produced **32.45% valid circuits and 3% functionally correct ones**. The same model writing a compact code representation reached **82% and 60.5%** ([arXiv 2605.30345](https://arxiv.org/html/2605.30345v1)). A GUI-drawn schematic is the weakest link both for "as code" and for Claude Code. A code front end is worth its risk there, and nowhere else.

One practical consequence for the old board: do not try to clean up the imported file. The converted `hw_debug` board has **1,869 DRC and 1,351 ERC violations**, most likely Altium-import artifacts such as 814 fragmented zones. The encoder and Bluetooth daughterboards exist only as Altium files ([hw_debug notes](file:///home/cosme/codes/hw_debug/kicad)). The next revision should be a clean sheet. The existing `schematic_review.md` already lists 5 critical and 15 major defects and proposes a new power tree, so it can serve as the requirements input ([schematic_review.md](file:///home/cosme/codes/hw_debug/schematic_review.md)).

## Zener is the strongest schematic-as-code layer; atopile is a frozen runner-up

### Why Zener fits Micras best

Zener is a Starlark (strict Python subset) hardware language with a Rust CLI, MIT-licensed. It covers the brief more completely than anything else. Modules take typed `io()` and `config()` inputs. Interfaces such as `Spi`, `I2c`, `Usb2` and `DiffPair` are built in. Physical quantities carry min/max ranges with dimensional arithmetic, and `io(Power(voltage="1.8V - 3.6V"))` enforces voltage ranges automatically ([Zener spec](https://docs.pcb.new/pages/spec)). `pcb test` runs `TestBench` checks that can query nets, look up components and search the circuit graph, for example finding every path from a regulator's VIN to ground ([Zener testing](https://docs.pcb.new/pages/testing.md)). A `Simulation()` block attaches SPICE models through KiCad `Sim.*` properties. Designs render as live schematic previews in VS Code and as real KiCad schematics ([Zener VS Code](https://docs.pcb.new/pages/vscode.md)). This matters because atopile has no schematic output at all.

The decisive feature for a dense 4-layer board is **layout sync**. Zener documents explicit invariants:

- Existing placement and routing survive regeneration.
- Sync is idempotent and matches the netlist exactly.
- A footprint swap inherits the old placement and UUIDs, so DRC exclusions survive.
- Reusable **layout fragments** load as rigid blocks ([pcb-layout README](https://github.com/diodeinc/pcb/blob/main/crates/pcb-layout/README.md)).

Fragments map directly onto Micras's repeated structure: four IR emitter/receiver channels and two motor channels. Dependencies resolve with Go-style minimal version selection and hardware-specific semver rules, under which a patch release may not change connectivity or layout ([Zener packages](https://docs.pcb.new/pages/packages.md)). On the AI side, Diode and Anthropic worked together on Claude authoring Zener. Claude drafted **about 250 reference designs in roughly two weeks**, iterating against SPICE and static netlist checks, while engineers kept "final review, routing strategy, signal integrity" ([Diode blog](https://blog.diode.computer/anthropic-partnership)). The repo also ships `AGENTS.md`, a published `zener-language` skill and an `llms.txt` ([diodeinc/pcb](https://github.com/diodeinc/pcb); [docs.pcb.new/llms.txt](https://docs.pcb.new/llms.txt)).

### Zener's costs

Zener's costs are real and should be stated plainly:

- **Churn.** The changelog has 155 version headings. Part-search commands were added, removed and renamed several times, with search eventually moved to "Diode API MCP endpoints" ([CHANGELOG](https://github.com/diodeinc/pcb/blob/main/CHANGELOG.md)). There were ≥100 releases in the last 12 months, reaching v0.4.77 this week ([GitHub](https://github.com/diodeinc/pcb)).
- **Hosted services.** Registry features in CI use a Diode service account (`DIODE_CLIENT_ID`/`SECRET`) ([quickstart](https://docs.pcb.new/pages/quickstart.md)), and BOM pricing goes through `api.diode.computer`.
- **Weak LCSC support.** There is no LCSC auto-picker. Parts are `Part(mpn=..., manufacturer=...)`, and its JLC CPL export only normalizes angles and has no rotation-correction database ([cpl.rs](https://github.com/diodeinc/pcb/blob/main/crates/pcb-ipc2581-tools/src/commands/cpl.rs)).
- **Small and young.** At 460 stars and 12 human committers it is a small community. Nobody has published an independent evaluation of its layout sync on a large board, and no micromouse or robot board built in it is public.

Diode is a funded YC S24 company that sells design services on top of the open tool. Reported funding figures conflict, at $11.4M versus $14.5M ([Seedtable](https://seedtable.com/companies/diode-computers/funding-rounds/seed-2025-05)). It is unlikely to vanish, but it will keep changing things under you.

### Why atopile comes second

atopile is the most capable alternative and the riskiest to depend on. Its strengths are real:

- **The best open constraint solver.** Assertions like `assert power.voltage within 3.3V +/- 5%`, tolerance propagation, and auto-picking of passives from LCSC.
- **An LCSC-aware picker.** Its data model carries `is_basic`, `is_preferred`, stock and price ([ato SKILL.md](https://github.com/atopile/atopile/blob/main/.claude/skills/ato/SKILL.md); [models.py](https://github.com/atopile/atopile/blob/main/src/faebryk/libs/picker/api/models.py)).
- **The largest community.** About 4.0k stars, plus about 20 Claude skills shipped in the repo.

The project's health, however, is opaque. **Public `main` has had no commit since 2026-03-11**, yet PyPI shipped 0.15.0 through 0.15.9 (September 12) and the website advertises 0.16. External PRs from August to October sit unmerged, and the docs have moved into a web IDE ([PyPI](https://pypi.org/project/atopile/); [GitHub](https://github.com/atopile/atopile); [docs.atopile.io](https://docs.atopile.io/)). The wheels pin Python to exactly 3.14. Open issues report a Windows wheel crash on import and `ato build` silently converting blind vias to through vias ([issues](https://github.com/atopile/atopile/issues)). The most likely explanation is that development moved somewhere private. That is an inference, not confirmed, but it means the MIT license is a weaker exit path than it looks. atopile also generates no schematic, so design review would mean reading `.ato` code and a ratsnest.

### The rest of the field

| Option | Schematic as code / output | Layout model | JLC/LCSC | AI fit | Health (Oct 2026) | Verdict |
|---|---|---|---|---|---|---|
| **Zener / `pcb` + KiCad 10** | `.zen` (Starlark); live preview + KiCad sch | KiCad owns geometry; idempotent sync; fragments | MPN-based; JLC BOM/CPL + JLC DFM "PDK"; no rotation DB | Anthropic co-design, skill, AGENTS.md, `llms.txt` | Very active, pre-1.0, high churn, partly hosted | **Recommended (pilot first)** |
| atopile + KiCad | `.ato` DSL; **no schematic** | Updates `.kicad_pcb`; group "Pull" reuse | Best: C-number import, Basic-aware auto-pick | Extensive skills, EEBench | Public repo frozen since Mar 2026; Py 3.14 only | Watch; revisit if repo resumes |
| KiCad-native schematic + automation | GUI-drawn `.kicad_sch` | Native | Richest plugin ecosystem | Analysis via kicad-happy; editing via MCP, fragile (no sch IPC) | Excellent | **Fallback** if the pilot fails |
| SKiDL + KiCad | Plain Python; generated `.kicad_sch` (KiCad 6–10) | Netlist hand-off, no sync | None native | Plain Python | Stable 2.3.0, one dominant maintainer | Conservative code fallback |
| tscircuit | TSX; auto-laid-out schematic | Code + `manual-edits.json`; own autorouter | jlcsearch, C-number import, JLC ordering | Strong (skill, `llms.txt`) | Very active, 0.0.x | Not for a fab board yet |
| JITX (Python) | Python; proprietary core | Constraint autorouting | JITX parts DB | `jitx-skills` | Active, closed | Free tier forces CERN-OHL-P; RF focus |
| circuit-synth | Python → KiCad | Hand-off | JLC search/scraper | Built for Claude Code | Stalled since Mar 2026 | Avoid |

The table draws on [code-first survey sources](https://github.com/devbisme/skidl/releases), the [JITX plans](https://www.jitx.com/plans) and the [circuit-synth repo](https://github.com/circuit-synth/circuit-synth). tscircuit's elimination rests on hard evidence. An independent October 2026 interop test found that **every one of five tscircuit KiCad exports failed LVS**. Its QFN-32 MCU example had 66 errors, including two copper shorts. The autorouter dropped per-netclass widths, clearances and pours, producing 1,247 routing DRC items on an Arduino Nano ([kicad-tools evaluation](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/tscircuit-evaluation.md)). That evaluation comes from a competing project, but the defects are specific and reproducible. tscircuit fixes bugs fast and deserves a re-check in 2027. Browser EDAs such as Flux and EasyEDA Pro are not code tools, and they cannot ingest a modern KiCad project ([Flux feedback](https://feedback.flux.ai/bugreports/p/kicadv60-schematic-files-sch-unable-to-import); [EasyEDA Pro docs](https://prodocs.easyeda.com/en/import-export/import-kicad/)).

### The pilot decides

Because Zener sits on top of KiCad, choosing it is reversible. Run a **two-week pilot** that re-implements the next-revision power tree proposed in `schematic_review.md` §4 as a Zener module: high-side P-FET with slow start, TPS61178 boost with GPIO enable and load disconnect, ideal-diode ORing into a single L6981C33 buck, and a battery divider into PA5. Give it test-bench assertions and a SPICE check. Then `pcb layout` it into KiCad, place and route it by hand, rename and swap parts, and re-sync. Adopt Zener only if all five of these hold:

1. Placement and routing survive the re-sync.
2. `pcb build`, `pcb test` and `pcb layout` run in GitHub Actions **without Diode credentials**.
3. An `LCSC Part #` property flows through to the KiCad BOM.
4. The generated schematic is readable enough to review.
5. KiBot accepts the result.

If any check fails, switch the schematic stage to KiCad-native editing, with kicad-happy for analysis and an MCP server for agent edits. Everything else in this report stays the same.

## One repo and one spec file end today's three-way drift

The biggest "as code" win is not the schematic language. It is removing hand-copied numbers. Board mechanics live in three places today, with nothing cross-checking them:

- KiCad Edge.Cuts and pads.
- The generated `board_mech.json`.
- The hand-typed `params.Board` in MicrasHardware.

They have already drifted. micras-simulation's `robot.toml` still cites `board_bottom = 0.001` from "CAD v2", but `params.Board.bottom_z` is now **1.2 mm** ([micras-dbg/robot.toml](file:///home/cosme/codes/micras-dbg/robot.toml); [params.py](file:///home/cosme/codes/MicrasHardware/micras/params.py)). The firmware's `robot.hpp` hand-enters outline lengths and wall-sensor poses ([robot.hpp](file:///home/cosme/codes/MicrasFirmware/config/targets/v1/robot.hpp)). The schematic labels PB12 `LED_Blue` while the firmware's `.ioc` calls it `LED_Red`, and the motor-sense names are swapped ([schematic_review.md m15](file:///home/cosme/codes/hw_debug/schematic_review.md)). `export_board.py` hard-codes the axle position as `AXLE_KX, AXLE_KY = 148.5011, 113.5036`.

Since the PCB *is* the robot's structural chassis, MicrasPCB should own a `spec/board.toml`. It uses the `{value, source}` provenance pattern that micras-simulation's `robot.toml` already established, and it records:

- outline, mounting holes, encoder slots, fan hole and wheel notches;
- sensor and IMU poses in the robot frame;
- stackup and thickness.

Generators and checkers flow out of that one file:

- **Edge.Cuts and mechanical footprints.** A script writes these into the `.kicad_pcb`, and a CI check fails if the board differs from the spec. The scriptable path is your own s-expression writer: extend `export_board.py`'s tokenizer, because kiutils and kicad-skip show no activity since 2024, and IPC needs a GUI until KiCad 11.
- **Board geometry for MicrasHardware.** `board_mech.json` and `params.Board` become generated data instead of hand-typed constants.
- **Simulation and firmware constants.** The generator emits micras-simulation's `[chassis]` outline and board z, plus the non-measured `robot.hpp` constants. Wheel radius and track width stay hand-set because they are measured values.

Setting the KiCad user origin at the axle midpoint and exporting with `kicad-cli pcb export step --user-origin` removes the hard-coded transforms ([kicad-cli reference](https://docs.kicad.org/10.0/en/cli/cli.html)). For pins, CI exports the netlist (`kicad-cli sch export netlist`) and compares each STM32 pin's net against the 70 `GPIO_Label` entries in `micras_v1.ioc` ([micras_v1.ioc](file:///home/cosme/codes/MicrasFirmware/cube/micras_v1.ioc)). Run that check in both repos' CI and the m15 mismatch class can no longer ship. No maintained KiCad↔CubeMX sync tool exists ([cubemx2kicad](https://git.rbts.co/rbts.co/cubemx2kicad/src/branch/main/readme.md)), so this is a small custom script.

The proposed layout is one repo for all Micras boards, matching the Team-Micras multi-repo convention:

```text
MicrasPCB/
├── CLAUDE.md, AGENTS.md        # agent rules, gates to run, "never hand-edit .kicad_pcb text"
├── pcb.toml                    # Zener workspace: pinned pcb-version, module deps (MVS)
├── pyproject.toml, uv.lock     # Python glue: checks, generators, sim harness (uv, like MicrasHardware)
├── spec/
│   ├── board.toml              # mechanical single source: outline, holes, slots, poses, stackup {value, source}
│   └── requirements.toml       # rails, currents, limits -> test benches / pytest assertions
├── modules/                    # reusable Zener modules: power/, mcu_h725/, motor_driver/, fan_driver/,
│                               #   ir_channel/, imu/, encoder_conn/, usb_c/, debug/
├── boards/
│   ├── main/        main.zen, layout/ (main.kicad_pro, .kicad_pcb, .kicad_dru), fragments/
│   ├── encoder/     encoder.zen, layout/
│   └── bluetooth/   bluetooth.zen, layout/
├── lib/                        # project-local symbols/footprints/STEP (KiCad std lib first; verified LCSC imports)
├── rules/                      # jlcpcb base .kicad_dru, stackup notes, DRC/ERC exclusion baselines
├── tests/                      # pytest: netlist rules, pinout-vs-.ioc, spec drift, LCSC completeness
├── sim/                        # models/ (+SOURCES.md), circuits/*.cir.j2, tests/, baselines/, export/
├── tools/                      # gen_edge_cuts.py, export_mech.py, check_ioc.py, gen_robot_params.py
├── kibot/main.kibot.yaml       # JLCPCB template, iBOM, PDF/SVG, STEP/GLB, renders, KiRI diff
├── site/                       # portal source (Hugo theme or MkDocs) + combined 3D page
├── docker/Dockerfile           # pinned KiCad 10.0.x + pcb + ngspice + uv; also the devcontainer
├── .claude/                    # settings.json allowlist, hooks, project skills
└── .github/workflows/          # ci.yml, sim-nightly.yml, pages.yml, release.yml, deps.yml
```

Commit the `.kicad_pcb`, because KiCad owns geometry in every hybrid flow. Treat the generated `.kicad_sch` as a build output that CI regenerates and diffs. Ignore `*-backups/`, `fp-info-cache`, `*.kicad_prl` and `*.lck`. Git LFS is unnecessary because KiCad files are text. Merging `.kicad_pcb` stays painful on 10.x. Users report boards corrupted by git merges ([KiCad forum](https://forum.kicad.info/t/pcb-file-gets-corrupted-during-git-merge/30802)), and the native diff/merge driver exists only in KiCad 11 nightlies ([Post-V10 dev news](https://forum.kicad.info/t/post-v10-new-features-and-development-news/66611)). Until then, give each board's layout one owner at a time and let fragments split the work. Keep the firmware's gitmoji convention so the org history reads consistently.

Downstream repos pin a MicrasPCB release, either as a submodule as the firmware already does with micras-lib, or as release assets. On each release tag, MicrasPCB fires a `repository_dispatch`. MicrasHardware then pulls a CI-built `board.step`, `board.glb` and `board_mech.json`, which retires its Windows-only `kicad-cli.exe` dependency. micras-simulation gets regenerated chassis parameters at the same time.

## Nine CI stages turn every commit into a verified, viewable board

The firmware's CI pattern carries over directly: Docker-generated tooling, hash-keyed caches and GitHub Actions ([ci.yaml](file:///home/cosme/codes/MicrasFirmware/.github/workflows/ci.yaml)). The base is one pinned image with KiCad 10.0.7, `pcb`, ngspice and uv. That same image serves as the devcontainer, so local runs and CI agree. Install the same KiCad 10.0.x natively inside WSL2 as well, so `pcb layout`, `kicad-cli` and the GUI all run on the Linux side. KiBot's KiCad 10 images are built from `Dockerfile_k10` in its repo ([KiBot](https://github.com/INTI-CMNB/KiBot)), but the exact `kicad10_auto_full` image tag and `v2_k10` action tag are unconfirmed in its docs, so verify them before pinning.

| Stage | Trigger | Tools | Gate |
|---|---|---|---|
| 1. Build & drift | every push/PR | `pcb build`, `pcb layout` sync, `tools/gen_edge_cuts.py` | Fail if regenerated KiCad files or Edge.Cuts differ from what is committed |
| 2. Design tests | PR | `pcb test` benches; pytest over `kicad-cli sch export netlist` XML; spec drift; `.ioc` pin check | Required |
| 3. ERC/DRC/DFM | PR | `kicad-cli sch erc` and `pcb drc --schematic-parity --refill-zones`, both `--exit-code-violations --format json`; in-repo JLC `.kicad_dru` | Required; "no new violations" against committed exclusions |
| 4. Simulation | PR (fast), nightly (Monte Carlo) | ngspice 47 + spicelib + pytest; kicad-happy `spice` | Required (fast set); nightly report |
| 5. AI review | PR | kicad-happy Action with `diff-base: true`; optional `claude-code-action` | Advisory comment |
| 6. Outputs | PR and main | KiBot: JLCPCB template, iBOM, schematic PDF, layer SVG, STEP/GLB, renders, KiRI diff | Artifacts |
| 7. Publish | main, tags, PR previews | Static portal to GitHub Pages (`/main`, `/vX.Y`, `/pr-N`); bot comment with diff images | n/a |
| 8. Release | tag `vX.Y` | Fab zip (Gerbers, drill, BOM, CPL), STEP, GitHub Release; `repository_dispatch` to MicrasHardware and micras-simulation | Manual approval |
| 9. Scheduled | nightly/weekly | LCSC stock/price check via jlcsearch; dependency-bump PRs for `pcb` and KiCad patch releases | Opens an issue or PR |

### Rule checks and tests

Stage 3 builds on KiCad's own exit codes. KiCad 10 also adds a graphical DRC rule editor that writes standard `.kicad_dru` custom rules ([KiCad 10 release](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)). No official JLCPCB rule pack exists. The popular community file targets KiCad 7 and was last touched in November 2024 ([labtroll](https://github.com/labtroll/KiCad-DesignRules)). Instead, seed a versioned in-repo `.kicad_dru` from it and cross-check against Diode's sourced JLCPCB DFM table, which pins a 0.15 mm minimum via hole (0.20 mm preferred) and was revised 2026-09-29 ([jlcpcb.toml](https://github.com/diodeinc/pcb/blob/main/crates/pcb-ipc2581-tools/pdks/jlcpcb.toml)). Two more mechanisms belong here. ERC/DRC JSON plus checked-in exclusions gives a ratchet that blocks only new violations. Domain "unit tests" go in pytest over the exported netlist:

- every IC power pin has local decoupling;
- the BOOT0 strap is correct;
- every part has an `LCSC Part #` or an explicit hand-solder flag;
- motor and battery nets meet an IPC-2152 width check.

No mature PCB unit-test framework exists. netspec and kicad-tools are pre-alpha or noisy ([netspec](https://github.com/heibench/netspec); [kicad-tools #5970](https://github.com/rjwalters/kicad-tools/issues/5970)), so write these yourself. Zener's `pcb test` covers the circuit-intent side, and pytest covers the board side.

### Simulation

Simulation should stay deliberately modest. ngspice is the maintained default, with **release 47 on 2026-08-11** ([ngspice news](https://ngspice.sourceforge.io/news.html)). spicelib (1.6.x) provides parallel runs, raw-file parsing and Monte Carlo/worst-case tooling, while PySpice has had no production release since 2021 ([spicelib](https://github.com/nunobrum/spicelib); [PySpice](https://github.com/PySpice-org/PySpice)). `kicad-cli` cannot run simulations; it only exports SPICE netlists ([KiCad forum](https://forum.kicad.info/t/execute-ngspice-by-kicad-cli/44358)). The practical setup is about 6–10 Jinja-templated testbenches whose component values are pulled from the netlist/BOM, so a schematic edit propagates into the tests:

- IR emitter pulse current and rise time against the firmware's ADC delay;
- receiver saturation;
- battery divider plus ADC settling;
- regulator feedback and dropout margins;
- H-bridge bulk-capacitor ripple.

kicad-happy's spice skill adds automatic dividers, filters and PDN checks for free. Integrated motor drivers usually ship no SPICE model, and encrypted PSpice models do not run in ngspice ([ngspice docs](https://ngspice.sourceforge.io/modelparams.html)), so model L6205/STSPIN-class drivers behaviorally from datasheet Rds(on). Then have `sim/export/` emit a parameter JSON that micras-simulation consumes. Today that simulation models the battery as open-circuit voltage with no sag, and treats the IR emitter's settled fraction as a bare parameter ([wall_sensors.hpp](file:///home/cosme/codes/micras-simulation/engine/include/micras/sim/devices/wall_sensors.hpp)). SPICE can derive both, so a schematic change that breaks a robot-level assumption fails CI. Skip openEMS, FEM thermal and Renode unless a specific problem demands them.

### Routing

Routing stays human-led. For non-critical digital nets, Freerouting **v2.5.0 (2026-10-05) raised DRC-clean completion from 30.9% to 75.0%** on its 1,157-board benchmark, and from 3.4% to 61.6% on routine 2–4-layer boards. It also gained native CLI binaries, a KiCad 10 IPC mode and an MCP server ([release notes](https://github.com/freerouting/freerouting/releases/tag/v2.5.0)). That is the maintainer's own benchmark, and it measures clearance only, not return paths. Route power loops, Kelvin current sense, the IR analog front end and the MCU's SMPS by hand. You can trial Quilter's free tier or the DeepPCB KiCad 10 plugin on a copy of the board, but neither has independent quality data ([Quilter pricing](https://www.quilter.ai/pricing); [DeepPCB plugin](https://github.com/instadeepai/deeppcb-kicad-plugin)).

## JLCPCB, the viewer and Claude Code all build on the same artifacts

### LCSC fields and rotation-corrected outputs keep JLC assembly predictable

JLCPCB matches parts on a symbol field named exactly `LCSC Part #`. Its help center, updated September 2026 for KiCad 9 and 10, calls the Fabrication Toolkit "the recommended path". It lists CPL columns of Designator, Mid X, Mid Y, Rotation and Layer, in millimetres ([JLCPCB help](https://jlcpcb.com/help/article/how-to-generate-the-bom-and-centroid-file-from-kicad)). In CI, KiBot's built-in `JLCPCB` templates apply a rotation filter plus per-part `JLCPCB Rotation Offset` fields. Its docs admit the internal database "is just a list of common cases" ([KiBot notes_position](https://github.com/INTI-CMNB/KiBot/blob/master/docs/source/notes_position.rst)). `kikit fab jlcpcb --missingError` can fail the build when a part lacks an LCSC number ([KiKit docs](https://github.com/yaqwsx/KiKit/blob/master/docs/fabrication/jlcpcb.md)). Diode's own `--format jlc` CPL does no rotation correction, so generate the CPL with KiBot from the synced `.kicad_pcb`, and always check JLC's placement preview before paying. JLCPCB's ordering API requires approval and favors established business customers ([api.jlcpcb.com](https://api.jlcpcb.com/)), so ordering remains a manual upload of the release zip.

Part selection should combine Claude with a deterministic source. The kicad-happy `lcsc` skill, already installed, queries the free, keyless jlcsearch API, and the CDFER library curates Basic/Preferred parts with daily stock updates ([CDFER](https://github.com/CDFER/JLCPCB-Kicad-Library)). atopile's code notes a one-time setup fee per unique Extended part ([models.py](https://github.com/atopile/atopile/blob/main/src/faebryk/libs/picker/api/models.py)), so prefer Basic parts for passives. Two cautions apply.

First, **the open JLC parts data has a single point of failure**. Bouni's plugin database and jlcsearch both derive from yaqwsx/jlcparts, which had two human committers in the last year and fetches data with the maintainer's personal API keys ([jlcparts workflow](https://github.com/yaqwsx/jlcparts/blob/master/.github/workflows/update_components.yaml)). Make the nightly stock check fail soft.

Second, **EasyEDA-derived footprints carry documented errors**: reversed LED polarity, extra pads, mismatched QFN pads and wrong pin numbering ([EasyEDA forum](https://www.easyeda.com/forum/topic/C390032-Polarity-reversed-00ef47654ed147ec955b06db7678d92d); [easyeda2kicad issues](https://github.com/uPesy/easyeda2kicad.py/issues)). Use KiCad standard-library footprints for the STM32, IMU, drivers and connectors. Hand-verify every imported footprint against the datasheet land pattern, the 3D overlay and the JLC preview. For the old board's hybrid assembly, where ST samples were hand-soldered, KiCad 10 design variants can produce a JLC BOM that excludes the hand-placed parts ([KiCad 10 release](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)).

### Ship a static portal now, add KiHub for review, build a Micras 365 later

No hosted product delivers the full Altium 365 experience for a git-plus-KiCad team, and none spans ECAD, MCAD and firmware.

| Option | What you get | Cost | Fit |
|---|---|---|---|
| **KiHub** (GitHub App, launched 2026) | Visual and semantic sch/PCB diffs per PR, ERC/DRC/parity/BOM checks as merge gates, pinned threaded comments | **Free for public repos**; $19–24/contributor/month private | Best review layer if the repo is public ([kihub.dev](https://kihub.dev/)) |
| KiCAD Prism (Apache-2.0, self-hosted) | Schematic/PCB/3D/BOM browser, commit compare, comments, jobsets, library approval | Server with Docker Compose + Postgres, AMD64 only | Closest open "Altium 365 for KiCad"; good if private ([GitHub](https://github.com/krishna-swaroop/KiCAD-Prism)) |
| CADLAB.io | Visual diff, annotations, merge requests | $0 open source; $8–12/month | Cheap, but KiCad version support undocumented ([pricing](https://cadlab.io/pricing)) |
| AllSpice | Object-level redlines, Actions CI, DRCY AI reviewer | From **$34,800/year**; clubs "schedule time with the team" | Enterprise-priced ([pricing](https://allspice.io/pricing)) |
| Altium 365 Viewer | Polished viewer | Free account | KiCad support "in Beta"; competitor testing found 48 h share links ([Altium](https://www.altium.com/altium-365/viewer); [NextPCB](https://www.nextpcb.com/blog/top-online-kicad-viewers)) |
| **DIY static portal** | Everything published from CI, including MCAD and firmware | GitHub Pages, free | **Recommended base** |

The DIY portal can be assembled from proven pieces:

- **Interactive schematic/PCB:** **ecad-viewer** (MIT, web components). It is a maintained KiCanvas fork that adds 3D and BOM and powers KiCAD Prism ([ecad-viewer](https://github.com/Huaqiu-Electronics/ecad-viewer)). Upstream KiCanvas is still "early alpha" ([KiCanvas](https://github.com/theacodes/kicanvas)).
- **Assembly BOM:** **InteractiveHtmlBom** (MIT, about 4.6k stars, pip CLI) ([iBOM](https://github.com/openscopeproject/InteractiveHtmlBom)).
- **Visual diffs:** **KiRI** onion-skin diffs, whose repo tags include kicad-10 ([KiRI](https://github.com/leoheck/kiri)).
- **Site shell:** **hugo-kicad-site**, which already turns KiBot outputs into a versioned Pages portal with KiCanvas, iBOM, a 3D assembly viewer and per-release diffs, as the Granit project shows ([hugo-kicad-site demo](https://laenzlinger.github.io/hugo-kicad-site/latest/)).

One page in the portal is something no vendor offers. Render the `kicad-cli` board GLB inside the build123d chassis in one Three.js/Online3DViewer scene, since Online3DViewer reads both STEP and glTF ([Online3DViewer](https://github.com/kovacsv/Online3DViewer)). Mount the firmware's existing Doxygen site and the simulation reports alongside it. Keep `kicad-cli` PDF/SVG as a fallback in case the alpha-grade viewers choke on KiCad 10 features. For discussion, giscus attaches GitHub Discussions threads to pages, but only on public repos ([giscus](https://giscus.app/)). On a private repo, discussion stays in PR threads, which the bot comment on each PR links to.

My rough effort estimates (judgement, not sourced): about a week for an MVP from the templates, and 3–6 person-weeks for a polished multi-board portal with per-PR previews. Semantic diffs and merge gates are the hard part to build, so rent them from KiHub rather than rebuild them. The "Micras 365" worth building yourself is the cross-domain view.

### Claude Code works best behind compilers and checkers

The evidence on AI hardware design argues for agents that write compact code and are graded by deterministic tools. On HWE-Bench's 300 board-level tasks, **the best model passed only 8.15%** ([arXiv 2603.18102](https://arxiv.org/abs/2603.18102)). Diode warns that models "can sound confident about circuits that would never work" ([Diode blog](https://blog.diode.computer/anthropic-partnership)). Practitioners report good results from agents for review and checks, but still route by hand ([HN](https://news.ycombinator.com/item?id=49572439)).

The integration therefore has five parts:

- **`CLAUDE.md`/`AGENTS.md`** carry the board requirements, net-class and stackup conventions, approved part sources, branch-per-change, and the rule "never hand-edit `.kicad_pcb` text".
- **Skills:** the Zener `zener-language` skill plus kicad-happy, already installed and already used on `hw_debug`. kicad-happy is pure Python, needs no KiCad and supports KiCad 5–10; its current release is v2.3.1 ([kicad-happy](https://github.com/aklofas/kicad-happy)).
- **A PostToolUse hook** runs `pcb build && pcb test` after `.zen` edits and `kicad-cli` ERC/DRC after layout edits. On new errors it exits non-zero so Claude sees and fixes them. This is the pattern kicad-verify packages ([kicad-verify](https://github.com/techmiguel/kicad-verify)).
- **The kicad-happy GitHub Action** gives PR review, optionally chained to `claude-code-action` for a datasheet-cited pass at roughly $1–3 per PR ([github-action.md](https://github.com/aklofas/kicad-happy/blob/main/github-action.md)).
- **Optional MCP:** for in-GUI layout sessions, **Konnect** is the strongest KiCad 10 option. It is a Rust plugin on the official IPC API with lazily loaded toolsets (about 2K tokens instead of 23K), but it is beta and AGPL-3.0 ([Konnect](https://github.com/mixelpixx/Konnect)).

kicad-happy's rule findings still produce false positives that get fixed release by release, so keep a waivers file in the repo so the agent stops re-raising accepted findings. Human gates remain non-negotiable for three things: footprint and pin-1 checks, critical-loop placement and routing, and fab release.

## Risks are bounded, and adoption runs in four phases

| Risk | Evidence | Mitigation | Re-evaluate when |
|---|---|---|---|
| Zener pre-1.0 churn | 155 changelog versions; search commands removed repeatedly ([CHANGELOG](https://github.com/diodeinc/pcb/blob/main/CHANGELOG.md)) | Pin `pcb-version`; bump only in dedicated CI-gated PRs; commit the `.kicad_pcb` | Each minor release |
| Diode hosted-service dependence | CI service-account login; BOM pricing via Diode API ([quickstart](https://docs.pcb.new/pages/quickstart.md)) | Pilot must pass offline; use KiCad-side BOM and LCSC tooling | Pilot exit |
| Diode pivots or folds | Startup with a services business model | Generated KiCad project is a complete exit; fall back to KiCad-native or SKiDL | n/a |
| atopile opacity | Public `main` frozen since 2026-03-11 while PyPI ships ([PyPI](https://pypi.org/project/atopile/)) | Not adopted; LCSC fields stay plain so switching later is cheap | Public repo resumes merging |
| KiCad 11 SWIG removal | Removal planned for 11.0; Bouni and Fabrication Toolkit still import `pcbnew` ([Bouni issues](https://github.com/Bouni/kicad-jlcpcb-tools/issues)) | Pin KiCad 10.0.x through 2027; prefer `kicad-cli` paths; no SWIG in custom code | KiCad 11 GA plus KiBot/KiKit support |
| KiBot on KiCad 10 | KiCad 10 support "with various limitations"; native variants experimental ([KiBot changelog](https://kibot.readthedocs.io/en/v1.9.1/Changelog.html)) | Pin version; fall back to `kicad-cli jobset run` | Each KiBot release |
| JLC parts data failure | jlcparts: 2 committers, personal API keys ([jlcparts](https://github.com/yaqwsx/jlcparts)) | Explicit LCSC fields; stock checks fail soft; LCSC official API as backup | n/a |
| Bad imported footprints | Documented EasyEDA errors | KiCad std lib first; datasheet, 3D and JLC-preview verification | Every new part |
| AI-introduced errors | HWE-Bench 8.15% best pass rate | Deterministic gates on every edit; human sign-off gates | n/a |
| `.kicad_pcb` merge conflicts | Corrupted-merge reports | Single layout owner; fragments; KiCad 11 merge driver later | KiCad 11 |

| Phase | Window (estimate) | Deliverables | Exit criterion |
|---|---|---|---|
| **0. Foundation + pilot** | Weeks 1–2 | `Team-Micras/MicrasPCB` repo; pinned Docker image and devcontainer; KiCad 10.0.7 in WSL; CLAUDE.md, hooks, kicad-happy; `spec/board.toml` with MicrasHardware's import moved onto Linux `kicad-cli`; Zener pilot of the power tree | All five pilot checks pass, or the fallback is chosen |
| **1. Schematic as code** | Weeks 3–6 | All modules in `.zen` (MCU, drivers, IR channels, IMU, USB-C with ESD, debug with NRST); `pcb test` benches from `requirements.toml`; SPICE testbenches; `.ioc` pin check; LCSC fields; portal MVP | Clean ERC; all review defects C1–C5 and M1–M15 covered by tests |
| **2. Layout** | Weeks 6–10 | Spec-driven Edge.Cuts and holes; manual placement and critical routing; IR and motor fragments; JLC `.kicad_dru`; Freerouting for leftovers; KiRI PR previews; KiHub if public; MicrasHardware/simulation dispatch | DRC clean; MicrasHardware `pytest` passes against the CI-built board |
| **3. Release & bring-up** | Weeks 10–12 | Tagged release with JLC zip; CPL checked in JLC preview; order; bring-up log feeds test baselines | Board assembled; bench data recorded |
| **4. Maturity** | 2027 | KiCad 11 migration (headless IPC, native merge driver); re-evaluate atopile and tscircuit; full "Micras 365" portal with ECAD+MCAD+firmware+sim | Pipeline green on KiCad 11 |

## Conclusion

The choice that matters most is not which code-first language wins. It is making KiCad 10 files the contract between every tool and repo, and putting one spec file upstream of the board, the chassis, the simulator and the firmware. Under that architecture, the risky, fast-moving pieces sit at the edges where they can be swapped: Zener, the AI agents, autorouters and viewers. KiCad, a plain `LCSC Part #` field, and pytest checks over exported netlists form a stable core that has outlived every startup in this space so far. The concrete defects that made the last board hard to debug were all cross-domain consistency failures that a CI check catches cheaply: a VBAT pin on the battery net, BOOT0 strapped wrong, firmware names that did not match the schematic, a board height that drifted between repos. The gain from "PCB as code" for Micras is mostly about catching those.

Two things will likely force a revisit in 2027: KiCad 11 and the code-first churn. KiCad 11 will bring headless IPC and native git merging, removing the two weakest points of the KiCad-as-platform story. By then Zener will either have stabilized toward 1.0 or proven too volatile, and atopile will either have reopened or confirmed its move to a closed web IDE. Pin versions, build the pilot with kill criteria, and keep the exit path one `git checkout` away. Then the toolchain decision stays cheap to reverse while the board work itself compounds.
