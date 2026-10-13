# Code-first ("hardware as code") schematic/PCB tools: state as of October 2026, and fitness for a 4-layer micromouse board

Research date: 2026-10-12. GitHub numbers (stars, forks, last push, latest tag) come from the GitHub REST API on that date. PyPI and npm numbers come from their JSON registries on the same date. Anything dated before 2025 is flagged **[pre-2025, possibly outdated]**.

Reference requirements for "fitness" below: STM32 MCU (LQFP/QFN, fine pitch), 2x motor drivers, IR emitters and receivers, IMU, encoders, 1S/2S LiPo power, about 100x100 mm or smaller, about 4 layers, JLCPCB/LCSC assembly. One competition guideline (UCI micromouse) caps the board at 100x100 mm, asks for GND planes, and sets a 0.3 mm minimum trace width for its 2-layer group order — [UCI Micromouse KiCad guide](https://ieee.ics.uci.edu/micromouse/KiCad.html).

---

## 1. Which tools exist, and how mature are they in October 2026 (versions, activity, licensing, pricing)?

### Takeaway
Four tools are realistic choices in late 2026: **atopile** (largest community, best constraint/solver story, KiCad layout), **Diode's Zener/`pcb`** (fastest-moving, best KiCad layout sync, Starlark/Python syntax), **tscircuit** (very active, owns the whole flow including its own autorouter, but its KiCad output and autorouter are not yet manufacturable on dense boards), and **SKiDL** (mature, stable netlist and schematic generator, no layout features). JITX moved to Python but is proprietary, and its free tier requires open-sourcing the design under CERN-OHL-P. circuit-synth has stalled since March 2026. Faebryk has been merged into atopile. Cuflow and pcbflow are niche layout-in-code libraries. PHDL is effectively dead.

### Cited Findings

**atopile (`ato` language, YC W24)**
- GitHub `atopile/atopile`: 3,988 stars, 248 forks, MIT. Last push to the repo 2026-06-13. Last commit on `main` 2026-03-11. Latest GitHub tags are v0.14.x (v0.14.1004, 2026-02-12) — [GitHub atopile/atopile](https://github.com/atopile/atopile)
- PyPI shows 0.15.9 released 2026-09-12, with 0.15.0 on 2026-04-04, 0.14.0 on 2026-01-31, 0.12.0 on 2025-08-28 and 0.10.0 on 2025-06-26. Requires Python >=3.14,<3.15. MIT — [PyPI atopile](https://pypi.org/project/atopile/)
- **Discrepancy (flagged):** PyPI releases continue through September 2026, but public `main` has no commits after March 2026. External PRs from August to October 2026 are still open and unmerged (for example "Sexp: Fix via type token drop on round-trip", updated 2026-10-10). The docs site now says the docs "live in the editor now" at app.atopile.io. The enterprise page title reads "atopile 0.16" — [GitHub PR list](https://github.com/atopile/atopile/pulls), [docs.atopile.io](https://docs.atopile.io/), [atopile enterprise](https://atopile.io/enterprise). This could mean development moved to a private repo or a web IDE. That is not confirmed.
- The docs call atopile "pre-release" and say the language and tools "move fast" — [docs.atopile.io](https://docs.atopile.io/)
- The enterprise offering includes a web IDE, agent tooling and an on-prem platform. Per search-result summaries of that page, the core rewrite shipped in 0.14 in January 2026 — [atopile enterprise](https://atopile.io/enterprise) (only the page title was retrievable directly)
- Altium OnTrack podcast episode with the co-founders on code-first, AI-assisted PCB design, June 2026 — [Altium podcast](https://podcast.altium.com/e/code-based-pcb-design-with-ai-inside-atopile/)
- The atopile org also maintains a fork of PCBJam/pcbjam ("kicad-wasm", KiCad in the browser, GPL-3.0). Diode also forked it — [PCBJam/pcbjam](https://github.com/PCBJam/pcbjam)
- One blogger (Feb 2026) calls atopile's business model "unclear" — [eddiesamuels.com](https://eddiesamuels.com/blog/ai-pcbs/)

**Faebryk**
- `faebryk/faebryk` was archived; last push 2024-09-03, v4.0.0. Its code now lives inside atopile (`src/faebryk/` in the atopile repo, including the solver) — [GitHub faebryk](https://github.com/faebryk/faebryk), [atopile solver README path](https://github.com/atopile/atopile/tree/main/src/faebryk/core/solver) **[pre-2025 as a standalone project]**

**Diode Computers: Zener language + `pcb` CLI**
- `diodeinc/pcb`: 460 stars, 61 forks, MIT for Diode-authored code. Latest release v0.4.77 on 2026-10-13, after v0.4.75 and v0.4.76 the same week. The release cadence is close to daily — [GitHub diodeinc/pcb](https://github.com/diodeinc/pcb)
- Zener is a Starlark (strict Python subset) DSL. The `pcb` CLI is written in Rust. KiCad 10.x is required for layout. Native Windows is "experimental" (use WSL2) — [diodeinc/pcb README](https://github.com/diodeinc/pcb), [Zener spec](https://docs.pcb.new/pages/spec)
- Business model: Diode is a design and manufacturing services company in the Brooklyn Navy Yard. The tool is open source and the high-value module Registry is internal — [Diode/Anthropic blog](https://blog.diode.computer/anthropic-partnership). One blogger reports that clients pay $10k–$50k per design (secondhand, unverified) — [eddiesamuels.com](https://eddiesamuels.com/blog/ai-pcbs/)
- CI login uses a service account with `DIODE_API_URL`, `DIODE_CLIENT_ID` and `DIODE_CLIENT_SECRET`. Some registry features therefore depend on Diode's hosted service — [docs.pcb.new quickstart](https://docs.pcb.new/pages/quickstart.md)

**tscircuit (TypeScript/React)**
- `tscircuit/tscircuit`: 2,830 stars, 326 forks, MIT, pushed 2026-10-13. npm `tscircuit` is at 0.0.2849 (2026-10-13) with 314,882 downloads in the 30 days to 2026-10-11. The version is still 0.0.x — [GitHub tscircuit](https://github.com/tscircuit/tscircuit), [npm tscircuit](https://www.npmjs.com/package/tscircuit)
- `tscircuit-autorouter` (MIT, "A State of the Art MIT-licensed PCB Autorouter"): 90 stars, automated version bumps v0.0.926 (2026-09-23) through v0.0.968 (2026-10-10) — [GitHub tscircuit-autorouter](https://github.com/tscircuit/tscircuit-autorouter), [PR #2945](https://github.com/tscircuit/tscircuit-autorouter/pull/2945)
- The older `tscircuit/autorouting` repo is archived, replaced by tscircuit-autorouter — [GitHub tscircuit/autorouting](https://github.com/tscircuit/autorouting)
- The online editor is free. The project is also described as having "no full ERC/DRC yet". That third-party note is about 200 days old and may be outdated — [Elektroda](https://www.elektroda.com/news/news4169243.html)
- A February 2026 blogger called the React choice "a bold choice" for EEs, said autorouter work "seems to have stalled", and called the business model unclear. The autorouter claim is contradicted by the daily autorouter releases in Sep–Oct 2026 — [eddiesamuels.com](https://eddiesamuels.com/blog/ai-pcbs/), contradicted by [tscircuit-autorouter PRs](https://github.com/tscircuit/tscircuit-autorouter/pull/2929)

**SKiDL (Python)**
- `devbisme/skidl`: 1,691 stars, 185 forks, MIT, last push 2026-09-24. Latest release 2.3.0 on 2026-07-28, which added KiCad 10 support. 2.2.2 added schematic generation for KiCad 6–9. 2.0.0 broke backward compatibility — [SKiDL releases](https://github.com/devbisme/skidl/releases), [PyPI skidl](https://pypi.org/project/skidl/)
- Maintained mostly by a single developer (devbisme) — [GitHub devbisme/skidl](https://github.com/devbisme/skidl)

**JITX (Python; formerly Stanza)**
- JITX moved its front end from Stanza to Python, with launch planned for Q4 2025 — [JITX blog, 2025-09-30](https://blog.jitx.com/jitx-corporate-blog/whats-new-in-jitx-2025)
- PyPI `jitx` 4.4.3 (2026-10-01), "Other/Proprietary License", Python 3.12+ — [PyPI jitx](https://pypi.org/project/jitx/)
- Plans: **Free and Open** costs nothing indefinitely, but designs must be CERN-OHL-Permissive v2 ("Incompatible with Proprietary or Copyleft/GPL Designs"). It includes KiCad and Altium integration. **Enterprise** is quote-only, locally hosted, with proprietary designs and air-gapped installs — [JITX plans](https://www.jitx.com/plans)
- A Claude Code skills repo exists: `JITx-Inc/jitx-skills` (20 stars, pushed 2026-10-08) — [GitHub JITx-Inc](https://github.com/JITx-Inc/jitx-skills)

**circuit-synth (Python → KiCad, "built for Claude Code")**
- `circuit-synth/circuit-synth`: 285 stars, MIT. Latest release v0.12.1 on 2026-01-09. Last push 2026-03-08, so no activity for about 7 months — [GitHub circuit-synth](https://github.com/circuit-synth/circuit-synth), [PyPI circuit_synth](https://pypi.org/project/circuit_synth/)

**Cuflow / pcbflow (layout fully in Python)**
- `jamesbowman/cuflow`: "experimental procedural PCB layout program", 303 stars, BSD-3, pushed 2026-10-04. Outputs Gerbers, drill, BOM, PnP and renders. Used to design the Gameduino 3X Dazzler — [GitHub cuflow](https://github.com/jamesbowman/cuflow)
- `michaelgale/pcbflow`: a CuFlow-based fork, 199 stars, BSD-3, last push 2025-02-12 (stale) — [GitHub pcbflow](https://github.com/michaelgale/pcbflow)

**Other code-first or adjacent projects discovered**
- `szymontex/codeyourpcb`: "code-first PCB design. Write circuits as text, get autorouted boards, Gerber export". 45 stars, active October 2026, early stage — [GitHub codeyourpcb](https://github.com/szymontex/codeyourpcb)
- `rjwalters/kicad-tools` (`kct`): Python tools to parse, check (DRC/LVS/mfr), and autoroute KiCad files, aimed at agent-driven PCB creation. 66 stars, very active. It lists atopile, SKiDL and tscircuit as "upstream/complementary" producers — [GitHub kicad-tools](https://github.com/rjwalters/kicad-tools), [its tscircuit evaluation](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/tscircuit-evaluation.md)
- KiCad file-manipulation libraries: `kicad-skip` (231 stars, last push 2024-05) and `kiutils` (130 stars, last push 2024-07) — [kicad-skip](https://github.com/psychogenic/kicad-skip), [kiutils](https://github.com/mvnmgrx/kiutils) **[pre-2025 activity, possibly stale]**
- PySpice (871 stars, pushed 2026-09) is used by several of these tools for simulation — [GitHub PySpice](https://github.com/PySpice-org/PySpice)

**Not code-first, but adjacent (AI/autorouting)**
- **Quilter**: physics-driven AI layout. Priced per board by unrouted pins at upload. A free tier covers personal and academic use. Free-tier designs may be used to generate synthetic training data. It round-trips KiCad and Altium projects. The vendor claims validated 843-component, 8-layer designs (vendor marketing) — [Quilter TCO blog](https://www.quilter.ai/blog/redefining-value-a-tco-analysis-of-ai-pcb-design-vs-kicad-altium-fusion-and-diptrace-for-small-teams-in-2026), [Quilter vs DeepPCB vs Flux](https://www.quilter.ai/blog/the-2026-guide-to-autonomous-pcb-design-quilter-vs-deeppcb-vs-flux-ai), [Futurepedia](https://www.futurepedia.io/tool/quilter)
- A blogger reports Quilter generating about 100 candidate layouts in about 1/10 of human time on a complex SOM carrier. Quilter requires an existing schematic and footprints, so it "could pair with Diode or atopile" — [eddiesamuels.com](https://eddiesamuels.com/blog/ai-pcbs/)
- **Flux.ai**: browser GUI EDA with an "AI hardware engineer". Plans are Explore, Build, Pro, Teams (per editor) and Enterprise. AI usage is metered in "Agent Compute Units". There is a 14-day trial, and the trial for Pro requires a payment method. No code or scripting authoring is listed — [Flux pricing](https://www.flux.ai/pricing)
- One blogger calls Flux a "complete sham of a company" after a dispute with Adafruit (opinion) — [eddiesamuels.com](https://eddiesamuels.com/blog/ai-pcbs/)
- **DeepPCB**: places and routes an uploaded PCB, with keep-outs. Credit-based pricing — [eddiesamuels.com](https://eddiesamuels.com/blog/ai-pcbs/)

### Inferences
- By community size: atopile (~4.0k stars) > tscircuit (~2.8k stars, very high npm volume, much of it likely CI and bots) > SKiDL (~1.7k) > Diode pcb (~460) > Cuflow (~300) > circuit-synth (~285). By development velocity in Sep–Oct 2026: Diode and tscircuit release near-daily, SKiDL and JITX ship regularly, atopile's PyPI releases continue while its public repo has gone quiet, and circuit-synth has stalled.
- Nothing has reached 1.0 except SKiDL (2.x) and JITX (4.x, proprietary). Expect breaking changes in atopile (0.15/0.16), Zener (`pcb-version = "0.4"`) and tscircuit (0.0.x).
- The atopile repo anomaly matters for a team betting on it. Before committing, check whether the current 0.15/0.16 source is public, for example by diffing the PyPI sdist against GitHub `main`.

### Gaps
- PHDL: no current repository or activity found in GitHub search. It appears abandoned (it originated around 2011–2014 per general knowledge, not verified here).
- No authoritative atopile changelog for 0.15–0.16 was retrievable (the docs moved into the web IDE). The enterprise page only returned its title.
- JITX's Python launch date and the current docs URL (docs.jitx.com redirects) could not be confirmed. The 4.0 API docs exist at [docs.jitx.com/en/4.0](https://docs.jitx.com/en/4.0/api/jitx.board.html).
- Quilter and Flux dollar prices were not published on the pages fetched.

---

## 2. Feature-by-feature: schematic, layout, KiCad round-trip, parts sourcing, modules, constraints, tests, CI, LLM ergonomics

### Takeaway
For a real 4-layer board, the decisive feature is **how manual KiCad layout survives regeneration**. **Zener/`pcb`** has the most rigorous, documented sync model: netlist-owned metadata, KiCad-owned placement and routing, idempotent, with UUIDs preserved. **atopile** syncs into `.kicad_pcb` and has a group "Pull" mechanism for reusing module layouts. **SKiDL** and **circuit-synth** hand off a netlist or project to KiCad. **tscircuit** keeps layout in code plus `manual-edits.json` and exports to KiCad, but the export is not yet LVS-clean. **atopile** has by far the strongest equation and tolerance solver with auto part-picking from LCSC.

### Cited Findings

**atopile**
- Language features: modules, interfaces, units, tolerances, assertions. "The compiler solves constraints, picks parts, runs checks, and updates the KiCad layout." Package registry at packages.atopile.io. CLI via `pip install atopile`; VS Code/Cursor extension — [PyPI atopile](https://pypi.org/project/atopile/)
- Assertion syntax examples: `assert power.voltage within 3.3V +/- 5%`, `assert i2c.frequency within 100kHz to 400kHz`, `assert v_out is v_in * r_bottom.resistance / r_total`. Only one comparison per assert. `assert x is 3.3V` is deprecated — [atopile ato SKILL.md](https://github.com/atopile/atopile/blob/main/.claude/skills/ato/SKILL.md)
- Parts: stdlib generics (`Resistor`, `Capacitor`, `Inductor`, `Diode`, `LED`, `Fuse`) are auto-picked from value plus package constraints. Pins are set with `x.lcsc_id = "C12345"`. `parts_search` and `parts_install(create_package=true)` turn an LCSC part into a reusable wrapper package. The guidance is to "lock only high-risk parts (MCU, PMIC, RF, connectors)" — [atopile ato SKILL.md](https://github.com/atopile/atopile/blob/main/.claude/skills/ato/SKILL.md)
- Experimental language features sit behind pragmas: `#pragma experiment("FOR_LOOP")` and `("BRIDGE_CONNECT")`, plus arrays of modules (`new Sub[3]`) — [atopile ato SKILL.md](https://github.com/atopile/atopile/blob/main/.claude/skills/ato/SKILL.md)
- **Schematic:** the repo tree has no schematic generator. The only schematic-related files are an s-expression parser — [atopile repo tree](https://github.com/atopile/atopile)
- **Layout:** `ato build` generates and updates a KiCad project, and the compiler auto-installs a KiCad plugin. "Use KiCad to place-and-route the rest of your design." "atopile can do small bits of auto-layout for you, but it's not fully exposed to `ato` yet." — [atopile layout docs (0.14-era)](https://atopile.mintlify.app/atopile/essentials/6-layout)
- **Layout reuse:** a layout maps to a class or superclass that has a build (for example the `rp2040` package layout is reused for `RP2040Kit`). In KiCad you "Sync Group", select the group, then "Pull" — [atopile layout docs](https://atopile.mintlify.app/atopile/essentials/6-layout)
- The plugin's internals: a `.layouts.json` map with module address, layout path and UUID-to-address map. "Pull Group" syncs footprints (position, orientation, layer), tracks with remapped nets, and zones — [atopile kicad_plugin README](https://github.com/atopile/atopile/blob/main/src/atopile/kicad_plugin/README.md)
- There is a `layout_reuse` example in the repo, and branches named `feature/deeppcb`, `feature/board-rules`, `feature/jlcpcb_stackup_importer` and `feature/multiboard` — [atopile repo](https://github.com/atopile/atopile)
- A built-in WebGL layout viewer and editor (`atopile.layout_server`) can move, rotate and flip footprints with undo — [layout_server README](https://github.com/atopile/atopile/blob/main/src/atopile/layout_server/README.md)
- AI tooling: the repo ships `CLAUDE.md`, `AGENTS.md` and many `.claude/skills/*`. The extension includes an agent with tools (`parts_search`, `web_search`, `design_questions`, `project_edit_file`) — [atopile repo](https://github.com/atopile/atopile), [ato SKILL.md](https://github.com/atopile/atopile/blob/main/.claude/skills/ato/SKILL.md)
- Tests and CI: "checks run locally or in CI". Build outputs include BOM, fabrication and assembly data, and reports — [PyPI atopile](https://pypi.org/project/atopile/)

**Diode Zener / `pcb`**
- Modules via `Module()` and `load()`. `io()` and `config()` declare module inputs. Interfaces include `Spi`, `I2c`, `Uart`, `Usb2` and `DiffPair`. Physical units carry min/max (`Voltage(min=11, max=26)`, dimensional arithmetic). `check()`, `error()` and `warn()` are available, and `io(Power(voltage="1.8V - 3.6V"))` auto-enforces voltage ranges. There are E-series helpers (`e24()`, `e96()`) — [Zener spec](https://docs.pcb.new/pages/spec)
- `Board(name=..., layers=4, path="layout/my_board", schematic=True)` sets stackup, netclasses and design rules. Schematic placement is stored as trailing comments (`# pcb:sch R1 x=100 y=200 rot=0`) — [Zener spec](https://docs.pcb.new/pages/spec)
- **Schematic:** the VS Code extension renders a live schematic preview from `.zen` — [Zener VS Code docs](https://docs.pcb.new/pages/vscode.md). Designs "render into graphical schematics and KiCad projects" — [Diode blog](https://blog.diode.computer/anthropic-partnership)
- **Layout sync (strongest model found).** The KiCad file "retains user-authored placement, routing, zones, and graphics". The documented invariants: "Existing user placement and routing remain unchanged when their entities still exist", sync is idempotent, and the result matches the netlist exactly. Footprint identity is hierarchical path plus footprint ID. A footprint swap inherits the old placement and UUIDs, so DRC exclusions survive. `--sync-footprints` reloads library footprints while preserving placement and routing — [pcb-layout README](https://github.com/diodeinc/pcb/blob/main/crates/pcb-layout/README.md)
- **Layout fragments:** a group with `layout_path` loads placement, routing, zones and graphics from a reusable KiCad fragment, and is treated as a rigid block during parent placement — [pcb-layout README](https://github.com/diodeinc/pcb/blob/main/crates/pcb-layout/README.md)
- Packages: `pcb.toml` lists dependencies with semver. Resolution uses Go-style Minimal Version Selection. There are hardware-specific semver rules (a patch must not alter connectivity, layout or electrical behavior). `pcb sync` pins to immutable pseudo-versions — [Zener packages docs](https://docs.pcb.new/pages/packages.md)
- Registry app at registry.diode.computer has components (symbol, footprint, 3D, MPN, sourcing) and modules — [Zener registry docs](https://docs.pcb.new/pages/registry.md). The internal Registry pairs each module with "a validated layout fragment and manufacturing data". It includes Jetson and Qualcomm compute modules — [Diode blog](https://blog.diode.computer/anthropic-partnership)
- **Built-in tests:** `TestBench(...)` with check functions, run by `pcb test`. Tests can query `module.nets`, `module["Power.U1"]`, and graph path search (`graph.paths(start=("Regulator","VIN"), end="GND_GND")`) — [Zener testing docs](https://docs.pcb.new/pages/testing.md)
- Simulation: `Simulation(...)` with SPICE models from KiCad `Sim.*` properties. The blog says the model iterates on SPICE metrics (gain, bandwidth, stability) — [Zener spec](https://docs.pcb.new/pages/spec), [Diode blog](https://blog.diode.computer/anthropic-partnership)
- Part sourcing uses `Part(mpn=..., manufacturer=...)`. No explicit JLCPCB/LCSC auto-picker was found in the docs reviewed — [Zener spec](https://docs.pcb.new/pages/spec)

**tscircuit**
- The flow is TSX → Circuit JSON → schematic, routed PCB, 3D, Gerbers/BOM/PnP. Exports include KiCad, STEP, GLB and SPICE. There is panelization and import of JLCPCB parts. CLI commands are `tsci dev` and `tsci export`. The homepage example is "RP2040 motor controller", 4 layers, 42.30 × 42.32 mm — [tscircuit docs](https://docs.tscircuit.com/)
- `<board layers={1|2|4|6|8|10}>`. `allowBlindAndBuriedVias` defaults to false (full-stack vias). Autorouter presets are `'auto' | 'auto-local' | 'fanout' | 'laser_prefab' | 'auto_jumper'`, `autorouterEffortLevel` goes up to `'100x'`, and `autorouterVersion` can be pinned. `schAutoLayoutEnabled` lays out schematics automatically — [tscircuit `<board/>` docs](https://docs.tscircuit.com/elements/board)
- Automatic placement uses `pcbFlex`, `pcbGrid` and `pcbPack`. It is "in beta" and "the algorithms are changing" — [tscircuit auto-layout docs](https://docs.tscircuit.com/guides/tscircuit-essentials/automatic-pcb-layout)
- Manual edits from dragging in the viewer are saved to `manual-edits.json` (`pcb_placements`, `manual_trace_hints`, `schematic_placements`, keyed by selectors) and passed via the `manualEdits` prop — [tscircuit manual edits](https://docs.tscircuit.com/guides/tscircuit-essentials/manual-edits)
- KiCad interop is two-way at file level: `circuit-json-to-kicad` (sch, pcb, pro, mod, library) and `kicad-to-circuit-json`. `kicadts` is a typed KiCad file model. `tsci` has `generate-kicad-project` and KiCad PCM build targets. `jlcsearch` provides constraint-based JLCPCB part search — [kicad-tools tscircuit evaluation](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/tscircuit-evaluation.md)
- There are open issues on multilayer plane handling: no way to reserve an inner layer as a plane while allowing through-vias, and inner1 gets cut up by signal traces. The reporter's workaround was routing in KiCad with FreeRouting — [tscircuit issue #5372](https://github.com/tscircuit/tscircuit/issues/5372)
- Blind/buried vias were previously emitted by default on 4-layer routing ([autorouter #2156](https://github.com/tscircuit/tscircuit-autorouter/issues/2156)). The current docs now default `allowBlindAndBuriedVias` to false ([board docs](https://docs.tscircuit.com/elements/board)).
- Specctra DSN export for FreeRouting rejects the whole board if any reference designator is missing — [search summary of tscircuit issues](https://github.com/tscircuit/tscircuit/issues/4415)
- KiCad export bugs: one pour exports as 65+ GND zones ([core #2621](https://github.com/tscircuit/core/issues/2621)), silkscreen font metrics cause DRC overlaps ([cli #4719](https://github.com/tscircuit/cli/issues/4719)), and board thickness was always written as 1.6 mm until a fix ([PR #623](https://github.com/tscircuit/circuit-json-to-kicad/pull/623))
- Claude/agent skill repo `tscircuit/skill` (29 stars, pushed 2026-10-09). The docs have "How to prompt AI" and AI-context pages — [GitHub tscircuit org](https://github.com/tscircuit), [tscircuit docs](https://docs.tscircuit.com/)

**SKiDL**
- Generates netlists (`generate_netlist()`), XML for BOM, and `.kicad_pcb` via `generate_pcb()` (requires KiCad's `pcbnew` Python). Since 2.2.2 it also generates editable, hierarchical `.kicad_sch` for KiCad 6–10 with automatic placement and wire routing. Dense circuits "can fail to route", with workarounds `auto_stub` and fallback options — [SKiDL docs](https://devbisme.github.io/skidl/), [SKiDL releases](https://github.com/devbisme/skidl/releases)
- ERC via `ERC()`, custom rules via `erc_assert()`. Hierarchy via `@subcircuit`, `SubCircuit` subclass or context manager. Tags keep netlist timestamps stable. `skidl-part-search` and `search_footprints()` are available. A KiCad-to-SKiDL netlist converter exists. No layout or routing features. No AI features mentioned — [SKiDL docs](https://devbisme.github.io/skidl/)
- Pain point reported June 2025: SKiDL 2.0.1 "did not especially play well with KiCad 9.0.2", and KiCad 9 appeared unable to import netlists into the schematic editor — [KiCad forum](https://forum.kicad.info/t/does-skidl-work-with-ai/61588)
- A third-party VS Code "SKiDL IntelliSense" LSP extension exists — [VS Marketplace](https://marketplace.visualstudio.com/items?itemName=ashergarland.skidl-lsp)

**circuit-synth**
- Python generates `.kicad_pro`, `.kicad_sch`, `.kicad_pcb` and `.net`. Layout, DRC and ERC happen in KiCad. Requires KiCad 8+ and Python 3.12+. The README claims a "fully bi-directional" import of `.kicad_sch` back to Python. It rewrites `ref="C"` to `C1` in your source after KiCad numbering. JLCPCB search prefers Basic parts (`fast_jlc_search`, `jlc-fast` CLI); DigiKey and SnapEDA are also supported. It ships Claude Code agents and slash commands (`circuit-architect`, `/find-parts`, `/generate-validated-circuit`) — [circuit-synth README](https://github.com/circuit-synth/circuit-synth)
- The creator, on the KiCad dev list: generating KiCad schematics from Python is "pretty solid", while bidirectional sync was "still in progress". A KiCad maintainer said there is no plan for AI/LLM integration in KiCad itself — [KiCad devlist](https://groups.google.com/a/kicad.org/g/devlist/c/4hjJIFbBtXU)
- Companion `kicad-sch-api` and `mcp-kicad-sch-api` (an MCP server for KiCad schematic manipulation) — [GitHub circuit-synth org](https://github.com/circuit-synth), [mcp-kicad-sch-api](https://github.com/circuit-synth/mcp-kicad-sch-api)

**JITX**
- Constraint-driven autorouting: signal-integrity rules (impedance, skew, loss) are encoded as code and the router produces layouts that satisfy them. Also via-fencing, arbitrary pad stacks and pin swapping. The vendor claims 5–20x engineer-hour gains (vendor claim). AI writes JITX code and extracts components from datasheets — [JITX blog 2025](https://blog.jitx.com/jitx-corporate-blog/whats-new-in-jitx-2025)
- One user's pipeline (October 2026): JITX Python 4.4.3, jitxlib-standard 4.4.0, runtime 4.4.2, then "legacy-kicad" export, then KiCad 9.0.9 DRC. JITX routing cut unconnected nets from 147 to 39 but did not fully route. Complete headless routing was "blocked". The exported stackup thickness (1.2 mm) disagreed with what KiCad reported (1.6 mm) — [he-piantor-42 #53](https://github.com/ihsinoky/he-piantor-42/issues/53), [#45](https://github.com/ihsinoky/he-piantor-42/issues/45), [#47](https://github.com/ihsinoky/he-piantor-42/issues/47) (one team's notes, not documentation)

**Cuflow / pcbflow**
- Layout is fully procedural in Python and outputs Gerbers, drill, BOM and PnP directly. It does not center on KiCad. It can fetch STEP models by LCSC code from a BOM — [cuflow README](https://github.com/jamesbowman/cuflow)

### Inferences
- **Schematic output:** Zener (live preview plus KiCad schematic), tscircuit (auto-laid-out schematic), SKiDL (generated `.kicad_sch`) and circuit-synth (generated `.kicad_sch`) produce human-reviewable schematics. atopile does not. Reviewers read `.ato` code and the KiCad PCB ratsnest, which some EE reviewers and design reviews may find unacceptable.
- **Constraint and math depth:** atopile's solver (parameter ranges, tolerance propagation, equation solving, auto-picking from LCSC) is ahead of everything else open-source. Zener has typed units, ranges and `check()` but lighter solving. SKiDL has only ERC. For a micromouse, atopile asserts suit IR LED current-limit resistors, ADC dividers for LiPo sensing, regulator feedback dividers and motor-driver sense resistors.
- **Layout preservation:** Zener's documented invariants are the most trustworthy for heavy iteration. atopile's preservation of existing footprints is implied ("updates the KiCad layout") but its precise rules were not found documented. tscircuit stores layout intent in code plus JSON, which is ideal for diffs. Its own autorouter is not yet reliable for fine-pitch 4-layer boards with planes, so a micromouse would need the KiCad export, and that export currently has LVS and pour defects (see Q3).
- **JLCPCB/LCSC:** atopile (native LCSC picking), circuit-synth (JLC search), tscircuit (`jlcsearch`, JLC import) and Cuflow (LCSC model fetch) are LCSC-aware. Zener uses MPN and manufacturer. SKiDL uses library parts only.

### Gaps
- No documentation found on exactly how atopile 0.15/0.16 handles removed or renamed modules in an existing hand-routed `.kicad_pcb`. The 0.14 layout page is silent on this. Test empirically.
- No independent evaluation of Zener's layout sync on a large board was found.
- JITX's KiCad export fidelity and schematic output for the Python version were not documented in sources reached.
- No LLM benchmark comparing the code-generation accuracy of ato, Zener, TSX and SKiDL was found.

---

## 3. Real-world projects, community, pain points, roadmaps

### Takeaway
No public micromouse or motor-control board built end-to-end in any of these tools was found. The closest evidence is tscircuit's 4-layer RP2040 motor-controller demo, atopile's example boards, and Diode's claim of production boards "on test stands, planes, and robots". An independent October 2026 evaluation found that **every tscircuit KiCad export tested failed LVS**, and that its autorouter output is not manufacturable under real design rules.

### Cited Findings
- **atopile example projects:** NONOS (smart speaker), DSP (multi-channel DSP), Hyperion (display driver, "High refresh rate bright af LED matrix"), Cellsim (battery cell simulator). The repo also has an esp32_minimal example and an LED-badge example with layouts — [PyPI atopile](https://pypi.org/project/atopile/), [atopile/hyperion](https://github.com/atopile/hyperion), [atopile repo tree](https://github.com/atopile/atopile)
- **Diode/Zener:** about 250 reference designs drafted by Claude in about 2 weeks, reviewed by humans. Project front ends cut "from months to weeks". Boards were used "on test stands, planes, and robots" and went through environmental testing and volume production. No customers are named and no accuracy statistics are given. Roadmap: more constraints and intent in Zener, panelization, test planning, and supply-chain-aware design — [Diode/Anthropic blog](https://blog.diode.computer/anthropic-partnership)
- **tscircuit:** the docs show a 4-layer RP2040 motor controller (42.3 × 42.3 mm) — [tscircuit docs](https://docs.tscircuit.com/). Hackaday covered it in April 2025 — [Hackaday](https://hackaday.com/2025/04/30/layout-a-pcb-with-tscircuit/)
- **Independent tscircuit interop gate** (kicad-tools, measured 2026-10-01; @tscircuit/core 0.0.2031, circuit-json-to-kicad 0.0.228, KiCad 10.0): "No export is manufacturable, and none is even self-consistent — the `.kicad_sch` and the `.kicad_pcb` name the same net differently, so every one of five boards fails LVS." The QFN-32 MCU example had 66 errors, **2 copper shorts**, 19 LVS label mismatches and 26 ERC failures. Verdict: "evaluated-not-adopted". The authors judged all six upstream defects "look fixable" — [kicad-tools tscircuit evaluation](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/tscircuit-evaluation.md)
- **tscircuit autorouter benchmark** (same source, 2026-09-30, capacity-autorouter 0.0.951): it completed 9 of 16 real boards (Arduino and Antmicro) within 600 s, versus 0 of 16 for kct. However, its SimpleRouteJson input drops per-netclass track widths (everything routed at 0.1 mm), clearances, via sizes (0.3 mm default), zones and pours, and keepouts. On the Arduino Nano it had 0 unconnected but 1,247 routing-type DRC items under the real rules (499 clearance, 199 track width, 140 via diameter). Verdict: "not manufacturable as written" — [kicad-tools tscircuit evaluation](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/tscircuit-evaluation.md). Caveat: kicad-tools is itself a competing agent-PCB project. The study is one run on a loaded host.
- An open autorouter bug report involves a board with 1,072 obstacles and 260 existing traces — [autorouter issue #2668](https://github.com/tscircuit/tscircuit-autorouter/issues/2668)
- **JITX:** one keyboard project (he-piantor-42) is evaluating it as an EDA backend and hit partial routing and stackup mismatches — [issue #55](https://github.com/ihsinoky/he-piantor-42/issues/55)
- **Community ranking (weak source):** a Copilot-generated PR in a lab repo ranked SKiDL with headless KiCad first, atopile second, and tscircuit fourth ("experimental, one small daughterboard only"). It is AI-generated and not authoritative — [powder-doser PR #76](https://github.com/vertical-cloud-lab/powder-doser/pull/76)
- **Blogger synthesis (Feb–Jun 2026):** "Code-first tools still require manual routing." LLMs struggle with KiCad's verbose s-expressions (an ESP32 symbol runs to about 700 lines). The author plans to revisit Diode, atopile and JITX, and to pair Quilter with a code tool — [eddiesamuels.com](https://eddiesamuels.com/blog/ai-pcbs/)
- **SKiDL:** a long-standing comparison thread of similar projects — [SKiDL discussion #210](https://github.com/devbisme/skidl/discussions/210). There are KiCad 9 friction reports from 2025 — [KiCad forum](https://forum.kicad.info/t/does-skidl-work-with-ai/61588)
- **circuit-synth:** KiCad forum announcement thread — [KiCad forum](https://forum.kicad.info/t/circuit-synth-professional-circuit-design-python-kicad-ai/63035). Repo inactive since March 2026 — [GitHub](https://github.com/circuit-synth/circuit-synth)

### Inferences
- For a fine-pitch, 4-layer, plane-heavy robotics board, **no tool's built-in router is production-ready**. Plan on routing manually in KiCad (motor current paths, IR receiver analog lines, IMU placement near the center of rotation, and the encoders all need deliberate layout). Optionally try Quilter or FreeRouting on non-critical nets.
- The tscircuit ecosystem fixes bugs quickly (near-daily releases), so the LVS and net-naming defects may be fixed within weeks. As of 2026-10-01, it should be treated as a front end that needs verification, not a trusted path to fab.

### Gaps
- No micromouse, robot motor-controller, or STM32+IMU board built with atopile, Zener, SKiDL or tscircuit was found in public repos. A targeted GitHub code search (for example `stm32` in `*.ato` or `*.zen` files) was not performed.
- No 2025–2026 KiCon or FOSDEM talk recordings on these tools were located in this session.
- No Hacker News or Reddit 2026 threads were found by search.

---

## 4. Hybrid approaches (code for the netlist, KiCad for layout, autorouters)

### Takeaway
The dominant, lowest-risk pattern in 2026 is **code for schematic, constraints and BOM, then KiCad (10.x) for placement and routing, with a sync step that preserves manual layout**. Zener's `pcb layout` and atopile's `ato build` with the layout plugin are purpose-built for this. SKiDL and circuit-synth support it in a one-way, netlist-import style. tscircuit can export to KiCad but is "code-owns-layout" by design.

### Cited Findings
- **atopile + KiCad:** the build updates `.kicad_pcb`; the rest is placed and routed in KiCad; module layouts are reused via Sync Group / Pull — [atopile layout docs](https://atopile.mintlify.app/atopile/essentials/6-layout), [kicad_plugin README](https://github.com/atopile/atopile/blob/main/src/atopile/kicad_plugin/README.md)
- **Zener + KiCad:** netlist-authoritative metadata, KiCad-authoritative geometry, idempotent sync, and reusable layout fragments — [pcb-layout README](https://github.com/diodeinc/pcb/blob/main/crates/pcb-layout/README.md). Claude also edits KiCad boards directly to propose decoupling placement — [Diode blog](https://blog.diode.computer/anthropic-partnership)
- **SKiDL to KiCad:** a netlist or `generate_pcb()` produces the starting board; layout is left to PCBNEW. Schematic generation is for documentation and review — [SKiDL docs](https://devbisme.github.io/skidl/)
- **circuit-synth to KiCad:** a "hybrid approach" with Python for hierarchy and repeated blocks and KiCad for custom layout — [circuit-synth README](https://github.com/circuit-synth/circuit-synth)
- **tscircuit to KiCad to FreeRouting:** a user routed in KiCad with FreeRouting to get proper planes on 4 layers — [tscircuit #5372](https://github.com/tscircuit/tscircuit/issues/5372). FreeRouting cannot restrict routing to one copper layer properly — [freerouting #689](https://github.com/freerouting/freerouting/issues/689)
- **Code tool + Quilter:** Quilter takes an existing schematic and footprints and round-trips to KiCad, so it "could pair with Diode or atopile" — [eddiesamuels.com](https://eddiesamuels.com/blog/ai-pcbs/), [Quilter blog](https://www.quilter.ai/blog/the-2026-guide-to-autonomous-pcb-design-quilter-vs-deeppcb-vs-flux-ai)
- **Verification layer:** kicad-tools (`kct check --mfr jlcpcb`, LVS, `kicad-cli pcb drc --refill-zones`) can gate any upstream producer's KiCad output in CI — [kicad-tools](https://github.com/rjwalters/kicad-tools), [tscircuit evaluation](https://github.com/rjwalters/kicad-tools/blob/main/docs/research/tscircuit-evaluation.md)

### Inferences
- A suggested micromouse pipeline: (1) Zener or atopile modules per subsystem (LiPo input and protection, buck/LDO, STM32 core, 2x motor driver, IR emitter driver arrays, IR receiver front ends, IMU, encoder connectors). (2) `pcb layout` or `ato build` into a KiCad 10 project. (3) Manual 4-layer layout in KiCad (signal / GND / power / signal). (4) CI runs build, ERC/asserts or `pcb test`, `kicad-cli` DRC, and JLCPCB BOM/CPL export. Reuse layout fragments for the repeated IR emitter/receiver channels and the two motor-driver channels.
- Commit the `.kicad_pcb` alongside the code. It is the source of truth for geometry in every hybrid flow.

### Gaps
- No public, verified example of Quilter driven from atopile or Zener output was found.

---

## 5. Which is best for a team iterating heavily with AI coding agents (Claude Code) and git?

### Takeaway
**Diode's Zener/`pcb`** is the strongest fit for an AI-agent-plus-git workflow on a real board in October 2026. Its syntax is Python-like (Starlark), and it has a rigorous, idempotent KiCad layout sync, built-in `pcb test` test benches, Go-style pinned dependencies, schematic previews, and an explicit Claude collaboration. **atopile** is the close second: the best constraint solver, LCSC auto-picking, a large community and extensive agent skills. Its downsides are no schematic output and the public-repo inactivity anomaly. **SKiDL** is the conservative choice (plain Python, stable, KiCad 10) but brings no layout sync or solver. **tscircuit** is excellent for LLM ergonomics and diffs but is not yet trustworthy for a dense 4-layer fab board.

### Cited Findings
- Diode and Anthropic worked together on Claude authoring Zener. Zener was "designed to be readable by engineers and learnable by models". Claude drafts modules from datasheets plus a few examples, then runs tooling, checks and SPICE in a loop — [Diode/Anthropic blog](https://blog.diode.computer/anthropic-partnership). A third-party write-up reports a preference win for Sonnet 4.5 on a testbench (secondhand) — [gend.co](https://www.gend.co/blog/enhancing-claude-pcb-design-skills)
- The Zener repo ships `.agents` and `skills` directories, plus a published skill "zener-language" — [diodeinc/pcb](https://github.com/diodeinc/pcb), [skills.sh](https://www.skills.sh/diodeinc/pcb/zener-language)
- atopile ships `CLAUDE.md`, `AGENTS.md`, `.github/instructions/ato.instructions.md` and about 20 `.claude/skills`, plus an in-editor agent with `parts_search`, `parts_install` and `design_questions` tools — [atopile repo](https://github.com/atopile/atopile), [ato SKILL.md](https://github.com/atopile/atopile/blob/main/.claude/skills/ato/SKILL.md)
- JITX moved to Python partly because "modern AI models write Python well". It ships `jitx-skills` for Claude — [JITX blog](https://blog.jitx.com/jitx-corporate-blog/whats-new-in-jitx-2025), [jitx-skills](https://github.com/JITx-Inc/jitx-skills)
- circuit-synth is "purpose-built for Claude Code" (agents, slash commands, `CLAUDE.md`) but has been inactive since March 2026 — [circuit-synth README](https://github.com/circuit-synth/circuit-synth)
- tscircuit has an installable AI skill and says an assistant "can often install and run the tools itself" — [tscircuit docs](https://docs.tscircuit.com/)
- LLMs struggle with KiCad's raw s-expression format (very verbose), which favors compact DSLs over direct KiCad file editing — [eddiesamuels.com](https://eddiesamuels.com/blog/ai-pcbs/)
- Git friendliness of layout state: Zener stores schematic positions as trailing source comments ([Zener spec](https://docs.pcb.new/pages/spec)). tscircuit stores placements in `manual-edits.json` ([manual edits](https://docs.tscircuit.com/guides/tscircuit-essentials/manual-edits)). atopile and Zener keep geometry in `.kicad_pcb`. atopile has a branch `claude/add-kicad-gitattributes`, which suggests attention to KiCad merge handling ([atopile branches](https://github.com/atopile/atopile)).
- Zener's MVS resolution plus hardware semver ("patch must not alter connectivity, layout, or electrical behavior") makes dependency updates explicit and reviewable — [Zener packages](https://docs.pcb.new/pages/packages.md)

### Inferences
- **Diffs and merges:** all four leading tools give clean text diffs for circuit intent. Merge conflicts will concentrate in `.kicad_pcb`, which is large and UUID-heavy, in every hybrid flow. Mitigations: one owner for layout at a time, a branch-per-subsystem for code, and a KiCad-aware merge driver or gitattributes. Zener's idempotent sync and layout fragments let subsystem layouts live in separate small fragment files, which reduces conflicts.
- **LLM ergonomics ranking (judgment):** Python/Starlark (Zener, SKiDL, JITX, circuit-synth) ≈ TSX (tscircuit; very familiar to LLMs, verbose for EE concepts) > `ato` (a bespoke DSL with deprecated forms and experimental pragmas that a model can misuse; atopile compensates with extensive skills docs and compiler feedback). Fast compile/check loops (`pcb build`/`pcb test`, `ato build` with asserts) matter more than syntax familiarity for agent self-correction.
- **Recommendation for the micromouse team:**
  - Primary: **Zener/`pcb` + KiCad 10** for layout, with CI on `pcb build`, `pcb test`, `kicad-cli` DRC and BOM/CPL export.
  - Alternative: **atopile**, if the team values tolerance-solving and LCSC auto-picking over schematic output. Verify the source and release situation first.
  - Avoid as the primary path for this board: tscircuit (KiCad export LVS failures, plane handling), JITX (open-source license constraint or enterprise pricing), circuit-synth (stalled), Cuflow/pcbflow (layout-in-code is too laborious for a dense 4-layer board).
  - In every case, plan for manual 4-layer routing in KiCad.
- Version-pin every toolchain (`pcb-version`, the atopile pinned PyPI version with Python 3.14, tscircuit 0.0.x) in the repo, because all are pre-1.0 and changing quickly.

### Gaps
- No controlled benchmark of Claude Code accuracy across ato, Zener, TSX and SKiDL was found.
- No documented KiCad merge-driver recommendation from any of these vendors was found.
- Diode's dependence on its hosted registry and service-account auth for CI was not fully characterized (which features work fully offline).
