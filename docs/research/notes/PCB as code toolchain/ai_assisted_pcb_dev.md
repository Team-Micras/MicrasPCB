# AI-Assisted PCB/Electronics Development Workflows and Tooling (state as of October 2026)

Scope: which toolchains and practices make PCB design work well with AI coding agents such as Claude Code (agents reading and writing the design, running checks, reviewing, routing), and what automation exists. Research date: 2026-10-12. GitHub star counts and push dates were read live from the GitHub API on that date.

---

## 1. MCP servers and agent tooling for EDA (KiCad MCP, kicad-happy, atopile, tscircuit, Flux, JITX, circuit-synth, Diode/Zener, case studies)

### Takeaway
The KiCad agent ecosystem is large but fragmented, and nearly all of it is community-built. The most mature pieces are **kicad-happy**, a read-only analysis and review plugin for Claude Code and Codex, and the **mixelpixx KiCAD-MCP-Server / Konnect** family, which does read/write editing, placement, routing and ERC/DRC. Code-first languages (atopile, Diode's Zener, tscircuit) now ship agent features of their own. atopile runs EEBench, an EE agent benchmark, and Diode has published a partnership with Anthropic. Every serious source still requires a human to review the schematic and to own routing on complex boards.

### Cited Findings

**KiCad MCP servers (all unofficial, community projects)**
- **mixelpixx/KiCAD-MCP-Server**: about 2,667 stars, last push 2026-10-01, created 2025-04. Python/TypeScript, MIT, needs KiCad 9.0+. Its tools cover project setup, schematic editing, component placement, routing, DRC/ERC, export, custom symbol/footprint generation, a JLCPCB parts catalog, Freerouting integration, and "visual feedback" snapshots. — [GitHub README](https://github.com/mixelpixx/KiCAD-MCP-Server)
- **mixelpixx/Konnect** is the successor: about 955 stars, created 2026-07-05, last push 2026-10-12, labelled **beta**. It is a single Rust binary that runs as a native KiCad 10 plugin and uses KiCad's official IPC API (protobuf over NNG), not the SWIG bindings. It has 228 tools in 21 on-demand toolsets plus bundled Claude skills and agents. It edits `.kicad_sch` through its own S-expression engine with atomic writes and UUID preservation. It is AGPL-3.0, with commercial licences for businesses. — [Konnect README](https://github.com/mixelpixx/Konnect)
- Konnect's README states the problems it was built to fix. The original server's call path crossed "four language and serialization boundaries". SWIG is "a dead end" that KiCad is deprecating, with "a zone-fill call that can segfault the backend". Exposing all 228 tools "costs roughly 23K tokens of context on every listing", so Konnect loads a ~2K-token starter kit and pulls in other toolsets on demand. — [Konnect README](https://github.com/mixelpixx/Konnect)
- **Seeed-Studio/kicad-mcp-server**: about 147 stars, last push 2026-09-28. It focuses on analysis: schematic and PCB analysis, "100% accurate pin-level connection tracking", ERC/DRC through headless `kicad-cli`, pin/pinmux analysis, device-tree and test-code generation, and a parts registry (PartReel, 21,000+ parts). Full PCB analysis needs it installed into KiCad's bundled Python (pcbnew). Without that it falls back to text parsing. — [GitHub README](https://github.com/Seeed-Studio/kicad-mcp-server)
- **oaslananka/kicad-mcp-pro**: about 124 stars, version 4.3.0, on PyPI/npm and in the official MCP Registry. By default it starts a bounded profile of "24 read-only review tools". Write mode (`build`) and a human-gated `release` mode must be turned on explicitly. The README is unusually candid. SI/PI/EMC/thermal tools are "first-order, closed-form estimates (typically ~5–10% accuracy)". It drives about **76.6%** of KiCad's programmatic surface. Its own end-to-end task-outcome evidence "intentionally reports `insufficient_evidence`". — [GitHub README](https://github.com/oaslananka/kicad-mcp-pro)
- **lamaalrajih/kicad-mcp** (about 525 stars) has had no push since 2025-10-17, so it is effectively stale. — GitHub API, [repo](https://github.com/lamaalrajih/kicad-mcp)
- Smaller or newer servers include ProductOfAmerica/mcp-server-kicad ("100+ tools", 13 stars), Greg3001/kicad-claude-mcp ("105 tools" including Freerouting, SPICE and panelization, 5 stars, last push May 2026), blwfish/kicad-mcp (71 tools, 24 stars), Finerestaurant/kicad-mcp-python (IPC API, stale since July 2025), Netlist-Studio/kicad-mcp (KiCad 9 IPC), and ShamanAndrey/kicad-mcp-layer (KiCad 10: kicad-cli, IPC and lossless file edits). A GitHub search for "kicad mcp" returns 25+ repos. — [GitHub search results](https://github.com/search?q=kicad+mcp&type=repositories); [Greg3001](https://github.com/Greg3001/kicad-claude-mcp); [ProductOfAmerica](https://github.com/ProductOfAmerica/mcp-server-kicad)
- DooJinWon/kicad-mcp-server's README says the repo has no fabricated-board demonstration and no published end-to-end validation report. — [GitHub](https://github.com/DooJinWon/kicad-mcp-server) (via search snippet)
- **Structural limit: KiCad's schematic editor has no IPC API in KiCad 9 or 10.** The official add-on docs say the IPC API works only with a running GUI and that schematic coverage is planned for later. Third-party MCP authors report that KiCad 10's schematic protobuf defines types but zero commands. Schematic editing by agents therefore means editing `.kicad_sch` files directly, while PCB edits can go live through IPC. — [KiCad dev docs](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/) (search snippet); a [KiCad project status slide](https://www.nextpcb.com/uploads/attach/blog/1.%20Seth%20Hillbrand%20-%20KiCad%20Project%20Status.pdf) lists schematic IPC as a v10 item, which conflicts with this.
- A July 2026 commit in another KiCad MCP project notes that KiCad 10's `kicad-cli` has no Specctra (DSN/SES) subcommands, and that pcbnew SES import needs a display. A fully headless KiCad-plus-Freerouting round trip therefore still needs workarounds. — [git.supported.systems commit](https://git.supported.systems/MCP/kicad-mcp/commits/commit/963206d548001071bf0553767d0de744a941d0f5/src/mckicad/utils) (search snippet)

**kicad-happy (aklofas)**
- About 1,379 stars, created 2026-03-09, last release v2.3.1 on 2026-10-06, MIT. It installs as a Claude Code plugin with `/plugin marketplace add aklofas/kicad-happy` and also supports Codex, Copilot CLI, Google Antigravity and opencode. It ships as a GitHub Action, and its scripts are pure Python 3.10+ with "zero required dependencies… no KiCad installation needed". It supports KiCad 5–10. — [GitHub README](https://github.com/aklofas/kicad-happy)
- It has 11 skills: kicad (schematic/PCB/Gerber/PDF analysis, DFM), spice (auto-generated testbenches for detected subcircuits, Monte Carlo, ngspice/LTspice/Xyce), emc (44 rule checks; FCC/CISPR/CISPR 25/MIL-STD-461G), datasheets (structured extraction with per-MPN cache and quality scoring), bom, digikey, mouser, lcsc, element14, jlcpcb, pcbway. It has 40 domain detectors, including motor drivers, BMS and sensors, plus derating, thermal and lifecycle/EOL checks, and a "fab release gate". — [GitHub README](https://github.com/aklofas/kicad-happy)
- Validation: it is regression-tested against 5,800+ open-source KiCad repos (6,845 schematics with 100% parse success, 3,498 PCBs at 99.9%), with 808K+ regression assertions and 30,646 SPICE subcircuit simulations. Its LLM-review findings are "promoted to machine-checkable assertions". Note that these figures measure parse and run success and regression stability. They do **not** measure precision or recall against real design bugs. — [GitHub README](https://github.com/aklofas/kicad-happy)
- It is **read and analyse only**. It does not edit schematics or route. Recent releases are mostly false-positive fixes, for example v2.3.0's "CP-003 touch-pad clearance… reported 0.0 mm on most boards and fired on test points". That points to an active project whose rule-based findings still produce false positives. — [GitHub README release notes](https://github.com/aklofas/kicad-happy)

**atopile**
- About 3,988 stars. The GitHub `main` branch was last committed 2026-03-11, and that included a "UI: agent" PR (#1788). PyPI releases continued to 0.15.9 on 2026-09-12, and the website now announces "atopile 0.16 — the code-native electronics design platform. Build, validate, and ship hardware from one browser workspace." — GitHub API; [PyPI JSON](https://pypi.org/pypi/atopile/json); [atopile.io](https://atopile.io/)
- atopile's enterprise page, as summarised in search results because the page is JS-rendered and could not be fetched directly, says engineers and AI agents work from the same source with the compiler checking each change. It lists "Web IDE, agents and on-prem platform" as current and the 0.14 core rewrite as January 2026. — [atopile.io/enterprise](https://atopile.io/enterprise) (search snippet only; unverified)
- The language is declarative `.ato` with units, tolerances and **assertions**. The compiler "solves constraints, picks parts, runs checks, and updates your KiCad layout". Example projects include "AI-Pin — Vibe-coded Humane Pin". — [atopile README](https://github.com/atopile/atopile)
- **EEBench**, "by atopile", is an EE agent benchmark. Agents submit atopile `.ato` design bundles. Grading is deterministic, from build results, simulation at worst-case tolerance corners, and BOM constraints: "No human graders. No LLM-as-judge." Score = 0.65 × technical + 0.35 × cost-efficiency against a reference BOM. Layout is **out of scope** for V1, and the task pack is held out. — [EEBench methodology](https://eebench.org/methodology.html)
- An aggregator snapshot of the EEBench leaderboard (2026-10-08, 41 models) shows Claude Opus 5.5 at 75.0%, GPT-6 Astra 69.3%, Claude Sonnet 5.5 67.2%, Claude Haiku 5.5 67.1%, Claude Opus 5 61.6%, Claude Sonnet 4.6 20.4% and Claude Haiku 4.5 3.5%. This is unverified: it comes from a third-party aggregator, it lists some models twice (Opus 5.5 at 75.0% and 68.9%), and the official eebench.org leaderboard did not render when fetched. — [BenchLM EEBench page](https://benchlm.ai/benchmarks/eebench)
- A Shyft tool profile says atopile has no AI agent support. atopile's own pages contradict this, so the profile is outdated. — [shyft.ai](https://shyft.ai/tools/atopile) (search snippet)

**Diode Computers / Zener (`pcb` CLI)**
- Zener is a Starlark-based (Python-subset) language for schematics. The `pcb` CLI builds designs, manages packages and generates KiCad 10 layout files. The repo has about 460 stars, MIT licence, and release v0.4.77 on 2026-10-13, so it is very active. It ships an `AGENTS.md`, and its docs publish an `llms.txt`. — [diodeinc/pcb README](https://github.com/diodeinc/pcb); [docs.pcb.new/llms.txt](https://docs.pcb.new/llms.txt)
- **Diode × Anthropic partnership post** ("Teaching Claude To Design Circuit Boards That Ship"):
  - Claude, given datasheets, Zener examples and docs, produced about **250 reference designs in roughly two weeks** (sensors, MCUs, switching power stages, analog chains).
  - Verification loop: automatic SPICE per module (Claude iterates on gain, bandwidth and stability results), static netlist checks (floating pins, miswired rails), and pipeline checks before human review.
  - Claude also reshapes KiCad symbols to house standards and proposes decoupling-cap placement by parsing board files.
  - Engineers still own "final review, routing strategy, signal integrity, and system-level tradeoffs". Models "can sound confident about circuits that would never work."
  - No formal benchmark was published, and the Registry of validated blocks is internal.
  - Source: [Diode blog](https://blog.diode.computer/anthropic-partnership)

**tscircuit**
- About 2,830 stars, active daily. It is a TypeScript/React (TSX) framework, MIT. The homepage says it "works with any AI agent" with no special installation. Claude Code and Codex are supported through `tscircuit/skill`, which bundles SKILL.md, CLI.md, SYNTAX.md, WORKFLOW.md, BUS_LANES.md and a pre-fab CHECKLIST.md. The homepage claims "sub-second routing on 4-layer boards" with a local autorouter and "LLM-compatible tweaking", and claims "state-of-the-art physically-validated electronics generation" with no benchmark given. It exports KiCad, DSN, Gerbers and BOM, with automatic part selection from supplier availability. No MCP server is mentioned. — [tscircuit.com](https://tscircuit.com/); [tscircuit/skill](https://github.com/tscircuit/skill); [GitHub](https://github.com/tscircuit/tscircuit)

**circuit-synth**
- A Python-defined-circuits project with Claude Code agents (circuit-architect, simulation-expert, component-search, FMEA) and slash commands, plus bi-directional KiCad import and export. It has about 285 stars but **no commits since 2026-03-08**, so it is likely stalled. — [GitHub README](https://github.com/circuit-synth/circuit-synth); GitHub API

**Flux.ai (Copilot / agent)**
- The Spring 2026 update (March 2026) describes an agent that turns goals into a plan (parts research, schematic, layout, checks), runs ERC and DRC *during* execution, and adapts its plan. It also says Auto-Layout routing "converges faster" with fewer vias. Neither claim comes with quantified metrics, and KiCad import/export is not mentioned. — [Flux blog](https://www.flux.ai/p/blog/spring-2026-updates-faster-ai-better-layouts-smarter-sourcing)
- User sentiment is poor. A Trustpilot capture showed about 79% one-star reviews, with complaints about credits consumed with little usable output and a copilot that "could not actually place components". — [Trustpilot](https://www.trustpilot.com/review/flux.ai?page=5) (search summary)

**JITX**
- JITX is now pitched as "Python-based design for high frequency boards". Its pitch: "AI writes the code. HFSS validates. Runs on your hardware." It gives one example: optimizing a 56 GHz PCIe-gen7 BGA launch to −30 dB return loss in 5 HFSS simulations. No KiCad export is mentioned and no public pricing is given. It targets enterprise RF and high-speed work, not hobby or robotics boards. — [jitx.com](https://www.jitx.com/)

**Case studies and anecdotes**
- In the HN thread "Can AI design circuit boards yet?", practitioners report:
  - Claude plus KiCad APIs works, but needs "a fair amount of PCB design knowledge".
  - Repeated review passes keep finding issues.
  - One user gets good results from Claude Code plus Konnect for design reviews and final checks "but still routes by hand".
  - Footprint orientation and pin 1 must be checked by eye.
  - Source: [HN item 49572439](https://news.ycombinator.com/item?id=49572439)
- Atomic14 ("Vibing a PCB – surprisingly good", July 2025) used atopile plus Claude for an ESP32-S3 dev board. — [atomic14.com](https://www.atomic14.com/2025/07/12/vibing-hardware)
- MakeUseOf says Claude with KiCad-MCP removes friction, but the author would not fabricate a board without checking the AI's work. — [MakeUseOf](https://www.makeuseof.com/pcb-design-easier-thanks-to-claude/)
- EEVblog opinions are mixed ("Very slow and not impressive, but clearly a lot of potential"). — [EEVblog forum](https://www.eevblog.com/forum/eda/claude-code-for-pcb-design/)

### Inferences
- For a team already on KiCad, the lowest-risk high-value combination today is **kicad-happy for review and analysis** plus **one write-capable MCP**, with Konnect preferred for KiCad 10. kicad-mcp-pro is a more conservative choice because of its read-only default and human-gated release mode. Agent-driven *schematic* editing in KiCad stays the fragile part until a schematic IPC API exists, which third-party reports place at KiCad 11.
- Tool sprawl is a real context cost (Konnect's ~23K tokens for its full tool list). Prefer servers with lazy toolset loading, or prefer skills plus CLI calls.
- Code-first languages (atopile, Zener, tscircuit) are where vendors invest in agent-native workflows (EEBench, the Diode–Anthropic work, the tscircuit skill). None of them claims autonomous routing of complex boards.

### Gaps
- No independent, quantitative comparison of the KiCad MCP servers on real tasks was found. kicad-mcp-pro explicitly says it lacks one.
- atopile's exact agent-feature launch date and the 0.16 release notes could not be fetched (JS-rendered pages). The GitHub `main` inactivity since March 2026 and the continuing PyPI releases are not reconciled; development may have moved to a non-public branch or repo.
- The official EEBench leaderboard values could not be retrieved directly.
- No verified, published case of a fully Claude-designed *dense* board that was fabricated and worked first time was found.

---

## 2. AI and automated placement and routing (Freerouting, tscircuit, Quilter, DeepPCB, Flux, Cadence/Siemens, JITX)

### Takeaway
Autorouting improved sharply in 2026. **Freerouting v2.5.0** (Oct 2026) went from 30.9% to 75.0% DRC-clean completion on a 1,157-board benchmark, has a KiCad 10 IPC mode, native CLI binaries, and an MCP/A2A server. **DeepPCB** has an open KiCad 10 plugin, and **Quilter** imports and exports KiCad with physics-aware checks. For a dense mixed-signal robotics board, the evidence still supports **human placement and critical-net routing, with autorouting for the remainder**, then DRC plus review.

### Cited Findings

**Freerouting**
- Version v2.5.0 was released 2026-10-05. The project has about 2,085 stars and is actively developed by one maintainer funded by sponsorship.
- On **PCBench**, 1,157 real open-source boards, with v2.4.1 → v2.5.0 under identical timeouts:
  - Clean (0 DRC) completion 30.9% → **75.0%**; fully routed 51.9% → 75.4%.
  - Tier B (560 routine 2–4-layer boards): clean 3.4% → **61.6%**.
  - Tier C (122 dense 6+ layer boards): clean 14.8% → **49.2%**.
  - Timeouts unchanged at 6.7%.
- New in v2.5.0: GraalVM native CLI binaries with no JRE, a KiCad 10+ IPC extension mode with fallback to DSN/SES, and a deterministic post-route optimizer.
- Source: [Freerouting v2.5.0 release notes](https://github.com/freerouting/freerouting/releases/tag/v2.5.0)
- v2.3.0 (Aug 2026) added a "dedicated Model Context Protocol server (JSON-RPC, SSE, WebSocket) and public A2A agent card", an SMD fanout pre-pass for dense all-SMD boards, and an experimental KiCad JSON/API mode. **"DSN remains the default and recommended production workflow."** — [Freerouting v2.3.0 release](https://github.com/freerouting/freerouting/releases/tag/v2.3.0)
- CLI usage: `java -jar freerouting.jar -de board.dsn -do board.ses -inc GND,VCC`. The `-inc` flag ignores net classes, for example planes. Integrations include KiCad, Autodesk Fusion, EasyEDA, tscircuit and pcb-rnd. — [Freerouting README](https://github.com/freerouting/freerouting)
- PCBench is the maintainer's own benchmark, and the "clean" metric counts clearance violations. It does not measure SI or EMC quality, return paths, or whether a human would accept the routing.

**DeepPCB (InstaDeep)**
- The KiCad plugin was published on GitHub in May 2026 (instadeepai/deeppcb-kicad-plugin, 66 stars, last push 2026-10-08). It targets KiCad 10.0+ and routes inside KiCad. The PCM listing was pending, so installation is manual. — [DeepPCB site](https://deeppcb.ai/kicad-autorouter-alternative/); [GitHub](https://github.com/instadeepai/deeppcb-kicad-plugin)
- Vendor claim: across 27,721 KiCad boards, 95.6% reached 95%+ completion. Not independently verified. — [deeppcb.ai](https://deeppcb.ai/kicad-autorouter-alternative/)
- According to a competitor's (Quilter's) comparison, DeepPCB uses RL with self-play. The public tier is limited to 1,000 components, 2,200 pins, 1,200 airwires and 8 layers, with pay-as-you-go compute credits and cloud-only use. Its public checks are geometric DRC, with no circuit-aware checks such as bypass-loop or ground continuity under diff pairs. — [Quilter guide](https://www.quilter.ai/blog/the-2026-guide-to-autonomous-pcb-design-quilter-vs-deeppcb-vs-flux-ai) (vendor-biased)

**Quilter**
- Imports and exports KiCad, Altium, Cadence Allegro/OrCAD and Siemens Xpedition, with "no proprietary formats".
- Pricing is per project, by **unrouted pin count**; pre-routed pins are not billed. Iterations within a project are unlimited. The BOM must stay within 10% of the original upload. No dollar figures are published ("Talk to Sales"). A free version exists, with limits not stated.
- Self-hosting needs Kubernetes and NVIDIA GPUs.
- Source: [Quilter pricing](https://www.quilter.ai/pricing)
- Vendor claims:
  - Physics-aware checks covering bypass-cap placement, switching-converter layout, diff-pair integrity including plane continuity, IPC trace width and crystal placement; Simbeor field-solver integration.
  - Multiple candidates, each with a physics scorecard, plus a hybrid mode (you pre-route about 20%).
  - "Project Speedrun": an 843-component, 8-layer board needed 38.5 h of human cleanup against a 428 h manual quote.
  - Source: [Quilter guide](https://www.quilter.ai/blog/the-2026-guide-to-autonomous-pcb-design-quilter-vs-deeppcb-vs-flux-ai) (self-reported)

**Flux Auto-Layout**
- The published examples are 2- and 4-layer boards with 40–100 components. Flux's own docs say it is "not designed to fully autoroute every class of board without your input". It costs about 375 credits for a 4-layer/40-component board and about 1,250 for a 2-layer/100-component board. It is cloud-only. — [Quilter guide](https://www.quilter.ai/blog/the-2026-guide-to-autonomous-pcb-design-quilter-vs-deeppcb-vs-flux-ai) (competitor-written); [Flux blog](https://www.flux.ai/p/blog/introducing-ai-auto-layout)

**tscircuit autorouter**
- The homepage claims "sub-second routing on 4-layer boards", running locally. No independent quality data exists. The older `tscircuit/autorouting` benchmark repo has been inactive since 2025-08. — [tscircuit.com](https://tscircuit.com/); GitHub API

**Big EDA vendors**
- Cadence Allegro X AI launched in April 2023. It automates placement, metal pour and critical-net routing on small-to-medium boards, with a vendor claim of more than 10× turnaround reduction. — [PCD&F](https://pcdandf.com/pcdesign/index.php/current/17202-cadence-introduces-allegro-x-ai-accelerating-pcb-design-with-more-than-10x-reduction-in-turnaround-time)
- I found no reliable 2026 primary-source detail on Siemens Xpedition AI. The only mention was a third-party blog citing a "Fuse EDA AI Agent". — [atlaspcb blog](https://atlaspcb.com/blog/ai-powered-eda-pcb-design-autonomous-agents-2026) (low-reliability)

**Benchmarks / academia**
- PCB-Bench (ICLR 2026) covers placement and routing, and PCBWorld (arXiv 2607.05915) provides an engine-grounded PCB design environment. I read only snippets of both. — [PCBWorld arXiv](https://arxiv.org/pdf/2607.05915)

### Inferences
- For a dense mixed-signal robotics board (motor drivers, current sense, IMU/encoders, MCU, possibly RF), this sequence fits the evidence:
  1. A human places parts and hand-routes power loops, the switching nodes of the gate drivers and buck converters, Kelvin current-sense, analog front-ends, crystal and RF.
  2. Freerouting (local, free, CLI- and MCP-scriptable) or DeepPCB handles the remaining digital nets.
  3. DRC, then kicad-happy EMC/PCB review.
  Quilter is the only tool claiming circuit-aware placement and routing. It is worth a free-tier trial on a copy of the board, but its claims are self-reported.
- Freerouting is now the most agent-friendly router: an open benchmark, a deterministic optimizer, native CLI, MCP, and a KiCad IPC mode. Agents can call it in a closed loop with `kicad-cli pcb drc`.

### Gaps
- No independent head-to-head of Freerouting v2.5, DeepPCB and Quilter on the same boards was found.
- No data was found on autorouter quality for mixed-signal concerns: return paths, analog/digital partitioning, motor-current loops.
- Quilter's actual prices and free-tier limits are not public.
- I found no 2026 primary sources on Celus or Cadstrom. A search returned nothing relevant.

---

## 3. How file formats affect AI-friendliness (KiCad S-expressions vs code-first DSLs)

### Takeaway
Raw KiCad files are readable and parseable, which is why kicad-happy can analyse them without KiCad. They are a poor *generation* target for LLMs: verbose, full of UUIDs and coordinates, and expensive in tokens. Peer-reviewed-style evidence (SchGen, PCBSchemaGen) shows large gains when LLMs write a compact code representation that is then checked by a deterministic verifier. Code-first DSLs also give clean diffs and compiler or assertion feedback, which is what closes the loop for an agent.

### Cited Findings
- **SchGen (arXiv 2605.30345)** reports that raw KiCad schematic files are "dominated by verbose, tool-specific, and version-specific metadata", causing formatting errors and "extra high token consumption".
  - A model fine-tuned on raw KiCad got **32.45% valid circuits**, 9.11% netlist Jaccard and 3% expert-verified functional correctness. The same model using a compact code representation (relative placement, pin-name wiring) got **82%, 49.08% and 60.5%**.
  - Frontier models prompted with raw KiCad text produced only 3.95–10.53% valid circuits.
  - "Valid" means the code runs and KiCad ERC reports zero critical errors. Validity is not functional correctness.
  - Limitations: a mostly SparkFun dataset, no advanced PCB constraints, and a 20B base model.
  - Source: [arXiv 2605.30345](https://arxiv.org/html/2605.30345v1)
- **PCBSchemaGen (arXiv 2602.00510)** treats schematic generation as code synthesis with a deterministic verifier, on PCBBench (62 tasks) and Open-Schematics-Eval (165 tasks). It reports that an open-weight 31B model passes 81.3% of PCBBench tasks with its framework. — [arXiv 2602.00510](https://arxiv.org/abs/2602.00510) (search snippet)
- **HWE-Bench (arXiv 2603.18102, March 2026)** has 300 board-level tasks from GitHub and OSHWLab across 8 domains, backed by 2,914 datasheets, and verifies with static ERC plus circuit simulation. The **best model passed only 8.15%**. The authors conclude models "lack physical intuition". — [arXiv 2603.18102](https://arxiv.org/abs/2603.18102)
- **CircuitLM (arXiv 2601.04505)** uses multi-agent generation from NL prompts, checked by deterministic ERC on 100 prompts. — [arXiv](https://arxiv.org/html/2601.04505v2) (snippet)
- **PCB-QA (arXiv 2606.23704)** has 480 QA pairs from 8 open-hardware projects and compares text-converted PCB formats with native files. A reported 93% accuracy figure is questioned by a third-party review. — [arXiv](https://arxiv.org/html/2606.23704); [Pith review](https://pith.science/paper/2606.23704)
- kicad-happy argues that KiCad's "clean, human-readable S-expressions" are what make agent *analysis* possible, unlike Altium and OrCAD binaries. It works by parsing the files into structured JSON first, not by feeding raw files to the model. — [kicad-happy README](https://github.com/aklofas/kicad-happy)
- Konnect edits `.kicad_sch` with atomic writes, "UUID preservation, and round-trip tests". This implies naive text edits by agents risk corrupting files. — [Konnect README](https://github.com/mixelpixx/Konnect)
- Code-first claims:
  - circuit-synth: `git diff` shows "changed R1 from 10k to 4.7k", and LLMs "can read and write circuit-synth code directly". — [circuit-synth README](https://github.com/circuit-synth/circuit-synth)
  - Zener: designs are "version-controlled, code-reviewed, and refactored", and Starlark's closeness to Python gives Claude "a good base". — [Diode blog](https://blog.diode.computer/anthropic-partnership)
  - atopile: assertions and units let the compiler check agent changes, and EEBench grades agents on `.ato` output. — [atopile README](https://github.com/atopile/atopile); [EEBench methodology](https://eebench.org/methodology.html)
- All three code-first tools still hand off to **KiCad for layout**:
  - Zener: "KiCad 10.x is required for layouts". — [diodeinc/pcb](https://github.com/diodeinc/pcb)
  - atopile "updates your KiCad layout". — [atopile](https://github.com/atopile/atopile)
  - tscircuit exports KiCad and DSN. — [tscircuit.com](https://tscircuit.com/)
  The `.kicad_pcb` remains the layout artifact in every flow.
- LLM-oriented documentation: Zener docs publish an `llms.txt`, tscircuit publishes a repomix-packed `llms.txt` of its docs, and docs.atopile.io/llms.txt returned empty. — [docs.pcb.new/llms.txt](https://docs.pcb.new/llms.txt); [docs.tscircuit.com/llms.txt](https://docs.tscircuit.com/llms.txt); checked by curl on 2026-10-12

### Inferences
- The best split for agent co-development: **schematic and intent in code** (atopile `.ato` or Zener `.zen`, which have assertions, parametric part picking and small diffs), and **layout in KiCad**, with agents doing analysis and scripted operations rather than raw-text edits of `.kicad_pcb`.
- If the project stays pure KiCad, agents should work through a parser layer (kicad-happy JSON, an MCP server, or kicad-cli netlist/ERC/DRC JSON). They should not read or write raw S-expressions wholesale.
- Merging `.kicad_sch` and `.kicad_pcb` in git remains painful. Code-first schematics avoid this for the schematic, but layout merges remain a manual, single-owner affair.

### Gaps
- No measured token counts were found for typical KiCad files against equivalent DSL source. SchGen used compression proxies, not token counts.
- No study was found that directly compares atopile, Zener and tscircuit on LLM authoring accuracy. EEBench uses atopile only.

---

## 4. AI for component selection, datasheets, symbols and footprints

### Takeaway
Agent-accessible parametric search is mature through APIs: DigiKey, Mouser, element14, LCSC/jlcsearch (free, no key) and Nexar/Octopart, available as kicad-happy skills or as MCP servers. Datasheet-to-structured-spec extraction exists, with kicad-happy's datasheets skill and Diode's pipeline. **Automatic, trustworthy footprint generation from datasheets is not solved.** Available tools are semi-automatic (LLM extracts the pin table, a human verifies) or in private beta.

### Cited Findings
- kicad-happy distributor skills:
  - DigiKey (OAuth client ID/secret), Mouser (API key), element14 (free key), LCSC through the free jlcsearch community API with no key. They fall back to web search without keys.
  - Datasheet sync reports a "96% success rate across 240+ manufacturers", with each PDF "verified against the expected part number".
  - Extraction produces per-MPN JSON (pinouts, ratings, electrical characteristics, SPICE coefficients), scored on a "five-dimension quality rubric". Findings are tagged `confidence: datasheet-backed`.
  - Source: [kicad-happy README](https://github.com/aklofas/kicad-happy)
- `tscircuit/jlcsearch` (36 stars, active) finds JLCPCB parts by design constraints (resistance, capacitance, tolerance). — [GitHub](https://github.com/tscircuit/jlcsearch)
- Nexar/Octopart MCP servers include LukeL99/nexar-mcp (parametric find_capacitors, find_resistors, get_datasheet and others, needing Nexar credentials), SpectraSynq/mcp-nexar and Farad-Labs/nexar-mcp (Docker MCP gateway). tmpk13/eparts-search-mcp searches DigiKey, LCSC and Mouser together. — [Glama: nexar-mcp](https://glama.ai/mcp/servers/@LukeL99/nexar-mcp); [playbooks.com](https://playbooks.com/mcp/farad-labs/nexar-mcp) (registry listings; maintenance not verified)
- Konnect includes a local 2.5M-part JLCPCB catalog search, and kicad-mcp-pro defaults to the JLCPCB public catalog, with Nexar, DigiKey and Mouser available when credentials are set. — [Konnect README](https://github.com/mixelpixx/Konnect); [kicad-mcp-pro README](https://github.com/oaslananka/kicad-mcp-pro)
- atopile does "automatic parametric picking of discrete components" from constraints in the code. — [atopile README](https://github.com/atopile/atopile)
- Diode: Claude builds a configurable reference module from a machine-readable datasheet plus examples, and reshapes downloaded KiCad symbols to house standards. — [Diode blog](https://blog.diode.computer/anthropic-partnership)
- Symbol and footprint generation:
  - The KiCad forum describes a Claude Code skill that generates symbol libraries from datasheets on top of the existing kipart spec, with the LLM filling pin tables. — [KiCad forum](https://forum.kicad.info/t/llm-prompt-to-generate-symbol-pin-table-from-datasheet/71370)
  - "FootprintAI" is in private beta, and its only source is its developer. — [CadCrowd profile](https://www.cadcrowd.com/profile/267105-vikasag98)
  - datasheet-cli has a pinout-to-symbol pipeline. — [docs.rs](https://docs.rs/crate/datasheet-cli/0.1.2)
  - mixelpixx KiCAD-MCP-Server and Seeed's server can create custom symbols and footprints or download them from registries. — [mixelpixx README](https://github.com/mixelpixx/KiCAD-MCP-Server); [Seeed README](https://github.com/Seeed-Studio/kicad-mcp-server)
  - The overall verdict of the search is that fully automatic datasheet-to-footprint generation is early-stage. — search summary of the sources above
- Practitioners stress checking footprint orientation and the pin-1 silkscreen against the datasheet by eye. — [HN thread](https://news.ycombinator.com/item?id=49572439)

### Inferences
- Use the agent for parametric search, stock and price checks, and *datasheet cross-checks* of pinouts, where it is strong. Treat any agent-generated footprint as untrusted until checked against the datasheet land pattern, a 3D model overlay and a printed 1:1 check. Prefer KiCad library, vendor or LCSC/EasyEDA-sourced footprints.
- LCSC/jlcsearch needs no API key, which makes it the easiest closed-loop sourcing source for agents if JLCPCB assembly is the target.

### Gaps
- No accuracy numbers were found for LLM pinout extraction or footprint generation.
- No primary-source information was found on DigiKey or Mouser official MCP servers. Only community servers were found.

---

## 5. AI design review: tools and how reliable

### Takeaway
Agent-based schematic and PCB review is the most mature and most useful AI capability today. Deterministic analyzers combined with LLM interpretation and datasheet citations (kicad-happy, AllSpice DRCY, CADY) work as a strong first pass. No vendor publishes precision or recall, and benchmarks of *generation* show LLMs still miss physics, so review should augment human review, not replace it.

### Cited Findings
- **kicad-happy** provides power tree with feedback-divider Vout, ESD audit per connector, I2C rise time, CAN termination, derating, thermal junction estimates, 44-rule EMC with SPICE-verified PDN, and a fab release gate. Its README example is a robot controller board (184 components), which flagged unprotected motor outputs and connectors. — [kicad-happy README](https://github.com/aklofas/kicad-happy)
- Its **GitHub Action** (`aklofas/kicad-happy@v1`) triggers on `*.kicad_sch` / `*.kicad_pcb` changes and posts a commit status plus a PR comment. `diff-base: true` gives a "Changes from Base" review. It can chain with `anthropics/claude-code-action` for a natural-language review at "~$1-3 per PR via API, 5-10 min"; the sample prompt has Claude verify the top 3–5 IC pinouts against datasheets. — [kicad-happy github-action.md](https://github.com/aklofas/kicad-happy/blob/main/github-action.md)
- Its own changelog shows false positives being fixed regularly, for example a touch-pad clearance check that "reported 0.0 mm on most boards" and "GP-001 via-antipad… false positives from the field". — [kicad-happy README](https://github.com/aklofas/kicad-happy)
- **AllSpice DRCY** is an AI review agent on AllSpice Hub, working on parsed native files (Altium, Cadence). Each finding carries a circuit snippet and a datasheet page or table citation. A CAIS 2026 demo describes a multi-agent, pin-by-pin datasheet analysis with multi-run consensus for reliability, run as a CI action on design reviews. No accuracy benchmarks are published. — [AllSpice blog](https://www.allspice.io/post/using-ai-in-schematic-design-reviews-what-we-learned-and-what-surprised-us); [CAIS 2026 demo](https://caisconf.org/program/2026/demos/drcy-hardware-review/); [allspice.io/ai-agent](https://allspice.io/ai-agent)
- **CADY** is a schematic analyzer: a datasheet-reading model plus a rules engine. It has a SiliconExpert integration for lifecycle, RoHS/REACH and availability. It is listed by Altair and Altium (Altium page says "Coming Soon"). It has raised about $5M. — [SiliconExpert](https://www.siliconexpert.com/cady/); [Altair](https://altair.com/cady); [CB Insights](https://www.cbinsights.com/company/cady)
- **kicad-mcp-pro** frames itself as "a professional first-pass design and review assistant, not an automated sign-off authority". — [README](https://github.com/oaslananka/kicad-mcp-pro)
- **techmiguel/kicad-verify** (new, October 2026, 1 star) is a verification gate for KiCad 10. It catches reversed diodes, wrong regulators, LED/base current errors, stale Gerbers and CPL/drill errors, and has an "evidence-checked independent reviewer". It ships Claude Code hooks: a dev gate after every edit and a fab gate in CI. — [GitHub](https://github.com/techmiguel/kicad-verify) (via search summary)
- Reliability evidence on the generation side: HWE-Bench's best model passes 8.15%, and Diode warns that models "can sound confident about circuits that would never work". — [arXiv 2603.18102](https://arxiv.org/abs/2603.18102); [Diode blog](https://blog.diode.computer/anthropic-partnership)
- Practitioners on HN: "repeated review passes help, since the agent keeps finding issues". — [HN](https://news.ycombinator.com/item?id=49572439)

### Inferences
- The most reliable pattern pairs deterministic analysis (kicad-cli ERC/DRC, kicad-happy analyzers, SPICE) as the source of truth with an LLM layer that interprets results, cross-checks datasheets and must cite evidence. Multi-run or independent-reviewer consensus (as in DRCY and kicad-verify) reduces hallucinated findings.
- Expect false positives. Budget time to triage findings, and record accepted waivers in the repo so the agent stops re-raising them.

### Gaps
- No published precision or recall exists for kicad-happy, DRCY or CADY on seeded-bug datasets.
- No independent comparison of AI review tools was found.

---

## 6. Recommended practices for agent-co-developed hardware repos (CLAUDE.md/AGENTS.md, skills, hooks, requirements → assertions, CI bots)

### Takeaway
Emerging practice (late September to October 2026 templates, plus the Diode and atopile workflows) converges on a few elements:
- An agent instruction file that defines rules and a branch/PR flow.
- Deterministic gates (`kicad-cli` ERC/DRC/netlist diffs, compiler assertions, SPICE) run by hooks after every edit and again in CI.
- Requirements captured as machine-checkable constraints.
- A PR review bot.
Most templates are brand-new, low-star projects, so treat them as patterns to copy rather than dependencies.

### Cited Findings
- **rashuky/kicad-ai-template** (KiCad 10, created 2026-09-25) has a CLAUDE.md requiring branch-per-change, edit-a-copy, verify, then PR. Verification uses netlist and ERC diffs, BOM checks, lint, rendering, and an independent review agent, with `kicad-cli` as "ground truth". `.claude/settings.json` allowlists `kicad-cli` and the check scripts. It uses Konnect plus the kschlint MCP. — [GitHub](https://github.com/rashuky/kicad-ai-template) (search summary)
- **techmiguel/kicad-verify** runs a dev gate after every edit (Claude Code hook) that blocks on confirmed defects, plus a CI fab gate, with `/pcb-verify`, `/pcb-review` and `/pcb-release` skills. — [GitHub](https://github.com/techmiguel/kicad-verify)
- **Diode663/kicad-claude-skills** generates schematics and placement from Python, verified against kicad-cli netlist, ERC and DRC (KiCad 10). **virajrungta/pcb-claude-plugin** goes from idea to manufacturable KiCad PCB with `/pcb:review`. **fradser use-kicad-cli** is a skill telling the agent to check `-h` rather than guess flags. — [Diode663](https://github.com/Diode663/kicad-claude-skills); [pcb-claude-plugin](https://github.com/virajrungta/pcb-claude-plugin); [claudeskills.info](https://claudeskills.info/skills/fradser/dotclaude/use-kicad-cli/)
- **Diode** shows the code-first variant of the requirements → constraints → checks chain. Customer discussions become a structured spec, the spec is assembled from validated Registry blocks, each module gets SPICE test benches, then static netlist checks, then human sign-off. Zener's docs have a "Testing" page (test benches, circuit graphs), and the repo has an `AGENTS.md`. — [Diode blog](https://blog.diode.computer/anthropic-partnership); [docs.pcb.new/llms.txt](https://docs.pcb.new/llms.txt); [diodeinc/pcb](https://github.com/diodeinc/pcb)
- **atopile**: "Requirements — capture specs with units, tolerances, and assertions" then component selection then design capture then layout then checks in CI. — [atopile README](https://github.com/atopile/atopile)
- **CI review bot**: the kicad-happy Action, optionally followed by claude-code-action, as described in section 5. — [kicad-happy github-action.md](https://github.com/aklofas/kicad-happy/blob/main/github-action.md)
- **Prompts practitioners give agents**: check JLCPCB design rules, list LCSC part numbers, verify stock, pass DRC, build the schematic in logical blocks, and run repeated review passes. — [HN](https://news.ycombinator.com/item?id=49572439)
- **Tool-surface hygiene**: Konnect's lazy toolsets (about 2K instead of 23K tokens) and kicad-mcp-pro's read-only default with human-gated release mode. — [Konnect](https://github.com/mixelpixx/Konnect); [kicad-mcp-pro](https://github.com/oaslananka/kicad-mcp-pro)
- **Headless limits to plan around**: no schematic IPC API in KiCad 10, and no Specctra export in `kicad-cli` (KiCad 10). — see section 1 sources

### Inferences
Suggested setup for a KiCad-based robotics board repo, synthesised from the sources above:
1. **AGENTS.md / CLAUDE.md** containing:
   - Board requirements: rails, currents, motor and driver specs, sensor interfaces, fab house rules (for example JLCPCB 4-layer).
   - Net-class and stackup conventions, and "never hand-edit `.kicad_pcb` text; use MCP/IPC or scripts".
   - Branch-per-change, and a list of approved part sources.
2. **Skills**: kicad-happy (review, BOM, SPICE, EMC, datasheets), plus a kicad-cli skill.
3. **PostToolUse hook** on `*.kicad_sch` / `*.kicad_pcb` edits. It runs `kicad-cli sch erc --format json` and `kicad-cli pcb drc --format json --schematic-parity`, plus a netlist diff against the last commit. On new errors it exits non-zero so the agent sees them. The kicad-verify pattern does this.
4. **Requirements → constraints → assertions**:
   - If adopting atopile or Zener for the schematic, encode rail voltages and tolerances as assertions or test benches.
   - If staying in KiCad, keep a `requirements.yaml` checked by a script against kicad-happy JSON output (power-tree Vout, decoupling count, ESD coverage).
5. **CI**: kicad-happy Action with `diff-base: true`, an optional Claude review job, Freerouting CLI for non-critical nets, then DRC as a required status.
6. **Human gates**: footprint and pin-1 verification, critical-loop placement and routing, and fab release sign-off.

### Gaps
- No published, tested reference implementation of a Claude Code PostToolUse hook running kicad-cli ERC/DRC was found beyond kicad-verify's description. The kicad-verify and rashuky template repos were seen only through search summaries, and both are under three weeks old.
- No evidence was found on how well requirements-to-assertion workflows hold up on large mixed-signal boards.
