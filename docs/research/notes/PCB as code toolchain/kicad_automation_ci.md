# KiCad Automation, Rule-Checking, Testing and CI/CD Ecosystem (as of October 2026)

Research date: 2026-10-12. Notes cover roughly 21 search and fetch calls. Items tagged **[background, unverified]** come from the researcher's prior knowledge (cutoff mid-2026) and were NOT confirmed against a source in this session. The report writer should treat them as leads, not facts.

## 1. KiCad version and automation features (kicad-cli, IPC API, SWIG, DRC rules, variants, libraries)

### Takeaway
The current stable line is **KiCad 10.0.x**. 10.0.0 shipped on 2026-03-20, and the latest point release is 10.0.7, with RC2 on 2026-10-03 and a "10.0.7 Release" post in October 2026. kicad-cli in 10.0 is a complete headless toolchain. It covers ERC and DRC with JSON output and exit codes, jobsets, about 25 PCB export formats, render, and per-command `--variant`. The SWIG `pcbnew` Python API has been deprecated since 9.0 and is slated for removal in **KiCad 11** (expected around Feb/Mar 2027, per a non-official forum post). New automation should target kicad-cli plus the IPC API (`kicad-python`/kipy).

### Cited Findings
**Versions**
- KiCad 10.0.0 was released 2026-03-20. Related releases: 10.0.0-RC2 on 2026-03-07 and the 9.0.8 bug-fix release on 2026-03-16. — [KiCad blog: Version 10.0.0 Released](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)
- 10.0.5 was released 2026-07-22 and 10.0.6 on 2026-08-29 (bug-fix releases; users urged to upgrade). 10.0.7-RC1 was posted in Sept 2026 and 10.0.7-RC2 on 2026-10-03. A "KiCad 10.0.7 Release" post exists under /blog/2026/10/, but this session did not confirm its exact date. — [10.0.5](https://kicad.org/blog/2026/07/KiCad-10.0.5-Release/), [10.0.6](https://www.kicad.org/blog/2026/08/KiCad-10.0.6-Release/), [10.0.7-RC2](https://www.kicad.org/blog/2026/10/KiCad-Version-10.0.7-Release-Candidate-2-Available/), [10.0.7 Release](https://www.kicad.org/blog/2026/10/KiCad-10.0.7-Release/)
- A forum user reported stability problems with 10.0.5 (drag issues, graphics crash). This is anecdotal. — [KiCad forum](https://forum.kicad.info/t/kicad-10-0-5-stability-problem-and-drag-problems-and-graphic-server-crash/71491)
- JLCPCB's help article (updated July 2026) was written and verified on KiCad 10.0.3. — [JLCPCB help](https://jlcpcb.com/help/article/how-to-generate-the-bom-and-centroid-file-from-kicad)

**KiCad 10 headline features relevant to automation**
- Graphical DRC rule editor (Seth Hillbrand, Damjan Prerad). It generates rules "fully compatible with the existing Custom Rules language" (`.kicad_dru`). KiCad 10 also adds suggested fix actions for DRC errors. — [KiCad 10 release post](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)
- **Design variants** (Wayne Stambaugh, Seth Hillbrand): one project, shared schematic, different properties such as the BOM. — [KiCad 10 release post](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/); [Elektor](https://www.elektormagazine.com/news/kicad-10-release)
- Other KiCad 10 additions:
  - Symbol-editor pin table CSV import/export, useful for MCU pin sync.
  - Jumpers: internally-connected pins and pads.
  - Pin/gate swap with forward and back annotation.
  - Time-domain tuning and Tuning Profiles.
  - 3D PDF export and barcodes.
  - Importers for Allegro, PADS and gEDA/Lepton.
  - PCB Design Blocks.
  
  — [KiCad 10 release post](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/); [CNX Software](https://www.cnx-software.com/2026/03/22/kicad-10-release-dark-mode-graphical-drc-rule-editor-new-file-importers-and-more/)
- From KiCad 10, the official 3D libraries ship **STEP only** (VRML dropped). Over 78% of footprints are now generated from data. — [KiCad 10 release post](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)

**kicad-cli (10.0 docs)**
- Top-level commands are `fp`, `jobset`, `pcb`, `sch`, `sym` and `version`. — [kicad-cli docs 10.0](https://docs.kicad.org/10.0/en/cli/cli.html)
  - `jobset run` (with `--stop-on-error` and `--output` to run a single destination).
  - `pcb drc|import|render|upgrade`.
  - `pcb export`, which covers 3dpdf, brep, drill, dxf, gencad, gerbers, glb, hpgl (non-functional), ipc2581 (default rev C), ipcd356, odb, pdf, ply, pos, ps, stats, step, stl, stpz, u3d, svg, vrml and xao.
  - `sch erc` and `sch export bom|dxf|netlist|pdf|ps|python-bom|svg`.
  - `sch upgrade`, `sym export|upgrade` and `fp export svg|upgrade`.
- CI-relevant flags: — [kicad-cli docs 10.0](https://docs.kicad.org/10.0/en/cli/cli.html)
  - `--exit-code-violations`: exit 0 when clean, 5 when violations exist (ERC and DRC).
  - `--format json|report`.
  - `--severity-all|error|warning|exclusions`.
  - `pcb drc --schematic-parity`, and `--refill-zones` together with `--save-board`.
  - `--define-var/-D` to override project text variables (for example version or date stamping).
  - `--variant` on most export commands, with `${VARIANT}` usable in output paths.
  - `--check-zones` refills zones before plotting without saving.
- HPGL export is non-functional in 10.0 and will be removed. `sch export bom --include-excluded-from-bom` is deprecated and does nothing. — [kicad-cli docs 10.0](https://docs.kicad.org/10.0/en/cli/cli.html)

**Python APIs**
- SWIG PCB Python bindings: "deprecated as of KiCad 9.0 … The current plan is to remove the SWIG bindings in KiCad 11.0." The IPC API is "a stable interface … accessible from many languages including Python" and is what new plugins should use. kicad-python provides "a Pythonic interface to the IPC API." — [KiCad dev-docs: PCB Python Bindings](https://dev-docs.kicad.org/en/apis-and-binding/pcbnew/)
- A forum thread says SWIG is already gone from nightlies and that V11 is expected around Feb/Mar 2027. This is a user discussion, not an official statement. Older third-party sources claimed removal in v10, which turned out wrong. — [KiCad forum: migration schedule](https://forum.kicad.info/t/migration-schedule-from-the-old-swig-api-to-the-ipc-api/69437)
- KiCad 11 development, 2026-03-21:
  - Output jobs can be run through the IPC API.
  - `kicad-cli api-server` starts a long-running **headless** session for IPC API work.
  - kicad-python can auto-start kicad-cli.
  - All of this requires building kicad-python from source, because PyPI ships stable releases only.
  
  — [KiCad forum: Post-V10 development news](https://forum.kicad.info/t/post-v10-new-features-and-development-news/66611)
- A third-party wiki citing kipy source says the kipy schematic API exists only for KiCad 11. On 10.x there is no IPC path for schematic edits. Needs confirmation. — [adom wiki (third-party)](https://wiki.adom.inc/adom/kicad-bridge/files/capabilities.py)
- Other KiCad 11 nightly features relevant to rules: — [Post-V10 dev news](https://forum.kicad.info/t/post-v10-new-features-and-development-news/66611)
  - Custom DRC messages can contain clickable links (2026-05-23).
  - Custom DRC rules can reference an item's parent footprint (2026-06-10).
  - Pin-to-pad mapping lets symbol pin numbers differ from pad numbers (2026-06-29).

### Inferences
- For a project starting in Oct 2026, pin KiCad **10.0.x (≥10.0.5, ideally 10.0.6/10.0.7)**. KiBot also recommends ≥10.0.5 for 3D rendering (see section 2). Write custom checks against kicad-cli outputs (netlist XML, JSON DRC/ERC, BOM CSV) or plain S-expression parsing rather than SWIG. Do not use SWIG for new code because it disappears in v11.
- Commit a `.kicad_jobset` file plus a thin CI wrapper (`kicad-cli jobset run`). This gives a vendor-native fab-output pipeline without KiBot. KiBot adds richer outputs on top.
- **[background, unverified]** Jobsets (`.kicad_jobset`) and the GUI jobs manager first appeared in KiCad 9.0 (Feb 2025). Database libraries (ODBC `.kicad_dbl`) arrived in KiCad 7 and HTTP libraries (`.kicad_httplib`) in KiCad 8. All remain in 10.

### Gaps
- This session did not confirm the official KiCad 10 release notes for database or HTTP library changes, or the full kicad-cli changelog 9→10.
- The exact 10.0.7 final release date is not confirmed.
- Whether `kicad-cli api-server` was backported to 10.0.x is unconfirmed. It appears to be KiCad 11 only.

## 2. KiBot, CI actions, KiAuto, Docker images

### Takeaway
KiBot is still the de-facto "everything" CI generator. Its latest release is **v1.9.1 (2026-07-28)**, and **v1.9.0 (2026-05-12)** added KiCad 10 support along with experimental native-variant support. It runs through INTI-CMNB Docker images and the `INTI-CMNB/KiBot` GitHub Action, whose tags follow the `v2_kN` / `v2_dkN` pattern.

### Cited Findings
- KiBot v1.9.1 (2026-07-28): better support for KiCad 10 native variants and the schematic format, and faster KiCad 10 3D rendering, for which the docs recommend KiCad ≥10.0.5. — [KiBot docs](https://kibot.readthedocs.io/)
- KiBot v1.9.0 (2026-05-12): support for KiCad 10.0.1, experimental native variants, and new outputs `bom_labels`, `pcb_stats` and `kicad_site` (a Hugo KiCad site helper). The previous release was 1.8.5 (2025-11-26). — [KiBot docs](https://kibot.readthedocs.io/) (via search summary)
- The GitHub Action is `INTI-CMNB/KiBot@<tag>`. The docs example uses `@v2_k8`. Documented tags are `v2_k6`, `v2_k7`, `v2_k8` and dev tags `v2_dk6`, `v2_dk7`, `v2_dk8`. — [KiBot CI/CD usage](https://kibot.readthedocs.io/en/latest/usage_with_ci_cd.html)
  - Inputs: `config`, `dir`, `board`, `schema`, `targets`, `skip`, `variant`, `verbose`, `install3D`, `cache3D`, `quickstart`, `additional_args`.
  - The example workflow uploads artifacts with `if: always()`.
  - The CI/CD page is stale: it stops at KiCad 8.
- The KiBot repo contains `Dockerfile_k5` … `Dockerfile_k10` and `Dockerfile_dk5` … `Dockerfile_dk10`, so KiCad 10 images are built from this repo. — [GitHub INTI-CMNB/KiBot](https://github.com/INTI-CMNB/KiBot)
- Docker images follow the pattern `ghcr.io/inti-cmnb/kicadN_auto_full` (full variant includes Pandoc and Blender) and `kicadN_auto` (lighter), with `:dev` tags. — [KiBot CI/CD usage](https://kibot.readthedocs.io/en/latest/usage_with_ci_cd.html); [KiBot docs](https://kibot.readthedocs.io/)
- The GitLab CI example project is gitlab.com/set-soft/kicad-ci-test. — [KiBot CI/CD usage](https://kibot.readthedocs.io/en/latest/usage_with_ci_cd.html)
- A Japanese walkthrough covers GitHub Actions with KiBot. — [classmethod](https://dev.classmethod.jp/articles/github-actions-kicad-cicd)

### Inferences
- By pattern, KiCad 10 users would use `INTI-CMNB/KiBot@v2_k10` and `ghcr.io/inti-cmnb/kicad10_auto_full`. These names are **unconfirmed** in the docs, so check the repo's GitHub Actions tags section before pinning.
- **[background, unverified]** KiBot features beyond the above:
  - Preflights: `run_erc`, `run_drc` (with `ignore_unconnected`, `filters`), `update_xml`, `check_zone_fills`, `set_text_variables` (git hash/date stamping) and `fill_zones`.
  - Outputs: gerber, excellon, position, `bom` (internal, with KiCost/distributor columns), `ibom`, `pcbdraw`, `pcb_print`, `pdf_sch_print`, `step`, `render_3d`, `blender_export`, `kikit_present`, `panelize` (KiKit), `diff` (KiDiff-based visual diffs), `kiri` (KiRi HTML), `navigate_results`, `report`, `qr_lib`, `jlcpcb`/PCBWay templates via `import`, `compress`, `copy_files`.
  - KiAuto (also by INTI-CMNB) is the GUI-automation backend KiBot used for ERC, DRC and netlist on older KiCad versions. Its importance has dropped as kicad-cli matured.
- Treat KiBot's native-variant support as "experimental" (per 1.9.0) and verify output parity if you rely on KiCad 10 variants.

### Gaps
- No confirmed list of KiBot GitHub Action tags for KiCad 9 or 10 was found.
- No information was found on other actions (e.g., "kicad-exports", "kicad-action"), on `kicad-automation-scripts` status, or on KiAuto's latest version. My background knowledge is that `kicad-automation-scripts` (Productize) has been unmaintained since the KiCad 5 era. That is unverified.

## 3. Visual diff and review (KiRI, kidiff, KiCad native diff/merge, AllSpice, KiCanvas, others)

### Takeaway
Open-source visual diff relies on **KiRI** (SVG onion-skin per git revision; Docker image and a community GitHub Action) and on KiBot's `diff`/`kiri` outputs. **KiCad 11 nightly** gained native Diff/Merge plus a `git mergetool` CLI (merged 2026-06-18), but nothing confirms it is in 10.x. Commercial alternatives are AllSpice (object-level redlines and CI Actions) and self-hosted viewers such as KiCanvas and "KiCAD Prism".

### Cited Findings
- KiRI exports revisions of a git-versioned KiCad project to SVG and compares them with an onion-skin view. It supports KiCad ≥5 and is "relatively easy to archive the output as a build artifact." — [Hackaday on KiRI](https://hackaday.com/2023/08/21); [KiCad forum: kdiff is KiRI now](https://forum.kicad.info/t/previous-kdiff-is-kiri-now/32031)
- The community action `USA-RedDragon/kiri-github-action` is a fork of `leoheck/kiri-docker`. A non-Docker KiRI install pulls in an OCaml build environment (plotgitsch dependency). A user on WSL had to install KiCad 9 from the PPA. — [KiCad forum: KiRI problems](https://forum.kicad.info/t/kicad-revision-inspector-kiri-problems/63325); [kdiff repo](https://github.com/leoheck/kdiff)
- A forum thread specifically discusses "KiRI and KiDiff". — [KiCad forum](https://forum.kicad.info/t/kiri-and-kidiff/65987)
- **KiCad native diff/merge:** KiCad 11 dev added "Diff and Merge support … GUI and a command-line tool for use with `git mergetool`" that produces valid merged boards (2026-06-18). — [Post-V10 dev news](https://forum.kicad.info/t/post-v10-new-features-and-development-news/66611)
- KiCad doxygen documents `KIGIT_SCH_MERGE` and `CLI::GIT_MERGEDRIVER_COMMAND`. The merge driver is invoked by git through `merge.kicad-*.driver` config, resolves trivial 3-way cases, defers complex ones to the mergetool, and exits non-zero when conflicts remain. — [doxygen KIGIT_SCH_MERGE](https://docs.kicad.org/doxygen/classKIGIT__SCH__MERGE.html); [doxygen GIT_MERGEDRIVER_COMMAND](https://docs.kicad.org/doxygen/classCLI_1_1GIT__MERGEDRIVER__COMMAND.html)
- **AllSpice** (vendor claims): — [AllSpice product](https://allspice.io/product); [AllSpice Actions demos](https://hub.allspice.io/Actions-Demos)
  - Auto-generated redlines for PCB, schematic and BOM (added items green, removed red, modified yellow).
  - Object-level diffs that also flag metadata changes such as MPN.
  - PR-like design reviews and a KiCad demo repo.
  - "AllSpice Actions" CI with `.allspice.yml` or `.github/workflows`, used for automated design checks, BOM/PDF generation and test scripts.
  - An AI reviewer called "DRCY".
- **KiCanvas** is a browser-based read-only KiCad (v6+) schematic and PCB viewer with an embedding API. — [Introducing KiCanvas](https://blog.thea.codes/introducing-kicanvas/); [Hackster](https://hackster.io/news/thea-flowers-kicanvas-lets-you-view-kicad-projects-directly-in-your-browser-c610d16c558e)
- A GitLab issue asks GitLab to render KiCad files with KiCanvas. — [GitLab work item 390053](https://gitlab.com/gitlab-org/gitlab/-/work_items/390053)
- "KiCAD Prism" is a self-hosted web platform for design reviews and visualization, announced on the KiCad forum. — [KiCad forum](https://forum.kicad.info/t/kicad-prism-a-self-hosted-web-based-platform-for-design-reviews-visualization/66518/21)

### Inferences
- A practical PR pipeline uses kicad-cli or KiBot to render SVG/PDF for the base and head revisions, then runs KiRI or KiBot `diff` to produce an HTML artifact, and optionally embeds KiCanvas in a docs site for the head revision.
- **[background, unverified]** Other tools:
  - `kicad-diff` / KiDiff (INTI-CMNB, used by KiBot `diff`, bitmap XOR-style diffs).
  - `plotgitsch` (OCaml, schematic diffs; KiRI depends on it).
  - CADLAB.io, an older commercial KiCad/Eagle diff service. Its 2026 status is unknown.
  - InteractiveHtmlBom is not a diff tool; a forum post points to KiCad-Diff instead ([forum](https://forum.kicad.info/t/interactive-html-bom-plugin-for-kicad/11713?page=11)).

### Gaps
- KiRI's KiCad 10 compatibility and the current maintenance status of the kiri GitHub action were not confirmed.
- Nothing confirms whether KiCanvas parses KiCad 10 files, given the new schematic format and variants.
- CADLAB status is unknown.

## 4. Documentation and fab outputs (iBOM, PcbDraw, renders, KiKit, JLCPCB tools)

### Takeaway
The standard output set covers Gerbers, drill, pos/CPL, BOM, IPC-2581/ODB++, STEP/GLB, schematic PDF, 3D renders and iBOM. kicad-cli now produces all of it natively except iBOM, PcbDraw illustrations and panelization (KiKit). KiBot wraps everything, including KiKit and Blender renders.

### Cited Findings
- kicad-cli natively exports: — [kicad-cli docs 10.0](https://docs.kicad.org/10.0/en/cli/cli.html)
  - Gerbers, drill, pos, IPC-2581, ODB++ and IPC-D-356.
  - STEP, STEPZ, GLB, BREP, XAO, STL, PLY, U3D and 3D-PDF.
  - PCB PDF and SVG, schematic PDF and SVG.
  - BOM, netlist and stats.
  - `pcb render` for raytraced 3D images.
- InteractiveHtmlBom generates a BOM page that visually correlates components with their placement on the PCB. — [Embedded Computing](https://dev007.embeddedcomputing.com/technology/analog-and-power/pcbs-components/interactive-html-bom-plugin-for-kicad)
- KiKit is a Python library, KiCad plugin and CLI for panelizing regular and oddly shaped boards and for "automated exporting manufacturing data based on manufacturer presets." The latest PyPI file seen was 1.8.0, release date not shown. — [PyPI KiKit](https://pypi.org/project/KiKit/)
- JLCPCB's CPL needs the columns Designator, Mid X, Mid Y, Rotation and Layer, in mm. — [JLCPCB help](https://jlcpcb.com/help/article/how-to-generate-the-bom-and-centroid-file-from-kicad)
- The unmaintained `KiCad-Project-Skeleton` runs on GitHub release creation. It exports Gerbers, assembly files, schematic PDF, BOM CSV, iBOM and STEP, and replaces `%%version%%`/`%%date%%` placeholders. — [KiCad-Project-Skeleton README](https://github.com/bob-swinkels/KiCad-Project-Skeleton/blob/main/README.md)

### Inferences
- **[background, unverified]** Other output and fab tools:
  - PcbDraw (yaqwsx) produces stylized board drawings and is integrated as a KiBot output.
  - KiKit's `fab` command has presets for `jlcpcb`, `pcbway`, `oshpark` and `neodenyy1`. KiKit "present" builds a board presentation webpage.
  - "Fabrication Toolkit" (bennymeg) is a PCM plugin that generates a JLCPCB-ready zip (Gerbers, BOM, CPL with rotation corrections from `JLCPCB Rotation Offset` fields).
  - `kicad-jlcpcb-tools` (Bouni) is a PCM plugin that assigns LCSC part numbers, checks stock and basic/extended status, and generates fab files.
  - Both are GUI plugins built on SWIG pcbnew, so their KiCad 11 survival depends on IPC migration. For KiCad 10.x they should still work. Verify against each repo.
- Prefer kicad-cli or KiBot over GUI plugins in CI, because GUI plugins usually need a pcbnew session.

### Gaps
- KiKit, InteractiveHtmlBom, PcbDraw and Fabrication Toolkit releases supporting KiCad 10 were not confirmed. No KiKit 2026 release information was found.

## 5. Rule checks beyond ERC/DRC and "unit tests" for PCBs

### Takeaway
Fab-specific `.kicad_dru` rule sets for JLCPCB and PCBWay exist as community repos (labtroll, kicad-druid, ziteh). KiCad 10's graphical rule editor writes the same `.kicad_dru` language. "PCB unit tests" are an emerging niche of netlist/pytest tools (netspec, circuit-unittests, kicad-tools, lytest) plus AI and heuristic analyzers (kicad-happy). There is no dominant standard: most teams write pytest checks over the `kicad-cli sch export netlist` XML.

### Cited Findings
- **Fab rule sets:**
  - `labtroll/KiCad-DesignRules` holds JLCPCB rules for KiCad 7 in a `.kicad_dru`. Some rules differ for 1–2 layer versus 4+ layer boards. — [labtroll](https://github.com/labtroll/KiCad-DesignRules)
  - `Cimos/KiCad-CustomDesignRules` moved to **kicad-druid**, which has JLCPCB and PCBWay rule files, each with a paired test board, KiCad 8 syntax and CI linting. — [Cimos](https://github.com/Cimos/KiCad-CustomDesignRules)
  - `ziteh/kicad-design-rules` is a JLCPCB DRC file. Copy it into the project and rename it to `<project>.kicad_dru`. — [ziteh](https://github.com/ziteh/kicad-design-rules)
  - JLCPCB forum discussion. — [KiCad forum](https://forum.kicad.info/t/design-rules-for-jlcpcb/46087)
- A `.kicad_dru` file can be imported via Board Setup → Design Rules → Import Settings, or placed next to the project with the same name so KiCad auto-loads it. — [search summary of the above repos](https://github.com/labtroll/KiCad-DesignRules)
- **netspec** (pre-alpha) verifies PCB connectivity against declared intent using kicad-cli as the oracle. It provides a pytest plugin with helpers such as `assert_polarity` and needs KiCad ≥8. — [heibench/netspec](https://github.com/heibench/netspec)
- **circuit-unittests** (mithro) is a set of unit tests for schematics and PCBs. Its PCB checks are still a TODO. — [mithro/circuit-unittests](https://github.com/mithro/circuit-unittests)
- **kicad-tools** (rjwalters) parses and manipulates KiCad files. It has an `I2CPullups` block, a `MissingDecouplingCapCheck` and a bypass-cap distance check, though an issue reports false positives (65 of 90 findings on one board). It also has a `kct check`/LVS flow. — [kicad-tools](https://github.com/rjwalters/kicad-tools); [issue #5970](https://github.com/rjwalters/kicad-tools/issues/5970); [issue #5847](https://github.com/rjwalters/kicad-tools/issues/5847)
- **kicad-verify** includes a check (PCB-PARITY-001) comparing component values between schematic and PCB. — [kicad-verify PR #5](https://github.com/techmiguel/kicad-verify/pull/5)
- **pcbkit** is "PCB as Python": generate, route, check and export KiCad boards. — [bruk-io/pcbkit](https://github.com/bruk-io/pcbkit)
- **lytest** is a pytest-based regression tool for KiCad PCBs using pcbnew (SWIG, so legacy). — [PyPI lytest](https://pypi.org/project/lytest)
- Blog: "Writing test cases for PCBs". — [rfcorner.in](https://rfcorner.in/posts/writing-test-cases-for-pcbs/)
- text-to-cad PR #518 adds a review step that warns when an IC power input lacks a decoupling capacitor or the capacitor is more than 3 mm away. — [text-to-cad PR #518](https://github.com/earthtojake/text-to-cad/pull/518)
- A CMSIS-Developer-Assistant proposal treats KiCad schematics as a queryable board model (nets, MCU pins, pull-ups, straps). — [CMSIS issue #78](https://github.com/Open-CMSIS-Pack/CMSIS-Developer-Assistant/issues/78)
- **kicad-happy** (aklofas, MIT) is a suite of about 11 Claude Code skills. — [sourcepulse](https://www.sourcepulse.org/projects/28934267); [Wiznet maker test harness](https://maker.wiznet.io/Sunny_/projects/kicad-happy-test-harness/); [awesome-claude-code issue](https://github.com/hesreallyhim/awesome-claude-code/issues/1559)
  - Schematic and PCB analyzers written in pure Python with no dependencies.
  - EMC pre-compliance, SPICE and sourcing.
  - A GitHub Action for automated PR reviews; works with Claude Code, Codex and Gemini CLI.
  - Star counts are inconsistent across aggregators.
  - A related test harness turns recurring review findings into permanent assertions.
- AllSpice positions "Actions" for YAML rule-based checks and its DRCY AI agent for datasheet-aware review (vendor claim). — [AllSpice Actions demos](https://hub.allspice.io/Actions-Demos/.profile)
- KiCad 11 nightly: custom DRC rules can reference the parent footprint, and custom DRC messages can include links (for example, links to internal design-guideline docs). — [Post-V10 dev news](https://forum.kicad.info/t/post-v10-new-features-and-development-news/66611)

### Inferences
- A recommended layered check stack in CI:
  1. `kicad-cli sch erc --exit-code-violations --format json`.
  2. `kicad-cli pcb drc --schematic-parity --exit-code-violations --format json`, using a fab `.kicad_dru` (kicad-druid or labtroll) merged with project-specific rules. Examples: net-class clearances, diff-pair rules, courtyard rules.
  3. pytest over the exported netlist XML and BOM. Examples: every U* power pin has a capacitor on the same net; I2C SDA/SCL nets each have exactly one pull-up to a rail; no unconnected MCU pins without a no-connect flag; all parts have an MPN or LCSC field; DNP and variant consistency.
  4. Optional heuristic or AI review (kicad-happy-style analyzers, AllSpice DRCY).
- Using ERC/DRC JSON with checked-in exclusions, plus the exit code, gives a "no new violations" gate.
- BOM stock and lifecycle checks are usually custom scripts against distributor APIs. Options include the DigiKey/Mouser/Nexar APIs, or the free jlcsearch API for LCSC used by kicad-happy's LCSC skill (per the skill description in this environment). KiBot's BOM output can add distributor data through KiCost **[background, unverified]**.

### Gaps
- No authoritative, maintained, KiCad-10-verified "PCB unit test" framework was found. All candidates are pre-alpha or small projects.
- No sourced information on BOM lifecycle-check tools (Octopart/Nexar-based CI) was found in this session.
- kicad-druid's KiCad 10 syntax support was not verified.

## 6. Library management as code (LCSC import tools, pinning, PCM)

### Takeaway
Keep project-local symbol and footprint libs, with `sym-lib-table`/`fp-lib-table` using `${KIPRJMOD}` paths and STEP models, in git. LCSC/EasyEDA importers (JLC2KiCadLib, easyeda2kicad) populate them. JLC2KiCadLib is considered "completed" by its author, and KiCad 10 compatibility of the importers is unverified.

### Cited Findings
- JLC2KiCadLib: — [PyPI JLC2KiCadLib](https://pypi.org/project/jlc2kicadlib); [GitHub](https://github.com/Springer-Electronics/JLC2KiCad_lib)
  - Python CLI that builds a KiCad symbol, footprint and 3D model from a JLCPCB/LCSC part number; installed with pip.
  - Uses KicadModTree.
  - The author considers it "completed". Last push reported Feb 28, 2026 (aggregator).
  - CLI options differ between versions.
- The official KiCad 10 libraries add 952 symbols, 1,216 footprints and 386 3D models. Footprints and 3D models are now generated from shared data. — [KiCad 10 release post](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)
- kicad-happy's skills include LCSC, DigiKey, Mouser, element14, JLCPCB and PCBWay sourcing that writes MPNs back as symbol properties. — [openskillindex: kicad-happy](https://openskillindex.com/skills/aklofas-kicad-happy-kicad)

### Inferences
- **[background, unverified]** Other library tools and practices:
  - `easyeda2kicad` (uPesy) is a pip CLI that converts LCSC/EasyEDA parts to KiCad v6+ symbols, footprints and 3D models.
  - `kicad-jlcpcb-tools` (Bouni) is a PCM plugin with a local parts DB.
  - PCM packages can be pinned by version, but PCM has no lockfile. For reproducibility, vendor libs into the repo or use git submodules, and pin the KiCad Docker image tag in CI.
  - Database libraries (`.kicad_dbl` via ODBC, e.g., SQLite in git) and HTTP libraries suit company-wide part catalogs.
- Because KiCad 10 ships STEP-only official 3D models, CI images that render 3D need the STEP library installed. KiBot's action has `install3D`/`cache3D` inputs for this.

### Gaps
- KiCad 10 compatibility of easyeda2kicad and kicad-jlcpcb-tools was not verified (no sources found).
- No sourced KiCad 10 changes to database or HTTP libraries were found.

## 7. Repo structure templates, pre-commit, LFS, merge handling

### Takeaway
Templates exist (`nguyen-v/KDT_Hierarchical_KiBot`, `kicad-helpers`, the unmaintained `KiCad-Project-Skeleton`), and KiBot's docs give a canonical workflow. KiCad files are text S-expressions, so LFS is not needed for sources and should be reserved for large generated binaries. Merge conflicts in `.kicad_sch`/`.kicad_pcb` remain painful in 10.x. Native merge driver and mergetool support arrives in KiCad 11 (nightly since June 2026).

### Cited Findings
- `KDT_Hierarchical_KiBot` (nguyen-v) is a KiBot-based hierarchical project template. It is used, for example, by zswatch `watch-devkit-hw`. — [awesome.ecosyste.ms zswatch](https://awesome.ecosyste.ms/projects/github.com%2Fzswatch%2Fwatch-devkit-hw)
- `kicad-helpers` (PyPI, up to 0.8.1) installs a `.github/workflows/build.yml` that covers BOM updates, manufacturing files, tests and documentation. — [PyPI kicad-helpers](https://pypi.org/project/kicad-helpers/0.8.0)
- `KiCad-Project-Skeleton` (no longer maintained) runs a release-triggered workflow with version and date placeholders. — [README](https://github.com/bob-swinkels/KiCad-Project-Skeleton/blob/main/README.md)
- KiBot's example workflow triggers on `pull_request` paths `**.sch`/`**.kicad_pcb`. — [KiBot CI/CD](https://kibot.readthedocs.io/en/latest/usage_with_ci_cd.html)
- Merge pain points: a 5.99-era forum thread reported UUID churn on every save, which maintainers disputed. Another thread reports PCB files corrupted after a git merge. — [forum: UUID churn](https://forum.kicad.info/t/git-based-collaboration-conflicting-fields-uuid-version-after-every-save/30010); [forum: corrupted merge](https://forum.kicad.info/t/pcb-file-gets-corrupted-during-git-merge/30802)
- The KiCad 11 native Diff/Merge, git mergetool CLI and merge driver are covered in section 3. — [Post-V10 dev news](https://forum.kicad.info/t/post-v10-new-features-and-development-news/66611); [doxygen](https://docs.kicad.org/doxygen/classCLI_1_1GIT__MERGEDRIVER__COMMAND.html)

### Inferences
- Suggested layout (synthesized, not from one source):
  - `hw/<project>.kicad_pro|sch|pcb|dru`, plus `.kicad_jobset`.
  - `hw/lib/{symbols,footprints,3d}` with project-relative lib tables.
  - `kibot/*.kibot.yaml`.
  - `tests/` (pytest over netlist and BOM).
  - `fw/` or a submodule.
  - `.github/workflows/{pr.yml, release.yml}`.
  - `.gitignore` for `*-backups/`, `fp-info-cache`, `*.kicad_prl`, `*.lck` and `_autosave-*` **[background, unverified, but standard KiCad practice]**.
- Pre-commit hooks could run `kicad-cli sch erc`/`pcb drc` on changed files, and a `kicad-cli … upgrade` check to enforce one file-format version. No KiCad-specific pre-commit hook project was found in this session.
- Treat schematic and PCB files as "lock and serialize" assets on 10.x: one owner per sheet or board per branch, and short-lived branches. Revisit when KiCad 11's merge driver ships.

### Gaps
- The contents of the KDT_Hierarchical_KiBot workflows (release tagging, KiCad 10 support) were not fetched.
- No KiCad-specific LFS or pre-commit guidance was found. The "kicad-project-template" repos mentioned in the brief were not located.

## 8. Pin-mapping sync with firmware (STM32 / CubeMX)

### Takeaway
There is no turnkey KiCad↔CubeMX↔firmware-header sync tool. Options are small scripts: cubemx2kicad (.ioc→schematic labels), sch2header (netlist→`pindefs.h`), and CubeMX per-chip XML parsing. KiCad 10's symbol-editor pin-table CSV import/export, and the KiCad 11 pin-to-pad mapping, make a custom generator easier.

### Cited Findings
- **cubemx2kicad** (Node.js) reads a CubeMX `.ioc` and applies pin labels to matching MCU symbols in a `.kicad_sch`. Caveats: reopen the schematic afterward, it breaks alternate pin functions, and the parser is fragile. — [cubemx2kicad readme](https://git.rbts.co/rbts.co/cubemx2kicad/src/branch/main/readme.md)
- **sch2header** is a beginner Python script from a forum thread that extracts nets on a refdes to generate `pindefs.h`. A commenter advises parsing the XML netlist (export it fresh) rather than relying on a stale `.net`. — [KiCad forum](https://forum.kicad.info/t/automatically-generate-a-pindefs-h-header-file-for-include-in-firmware-project/17223)
- A blog describes a Python script using CubeMX's per-chip XML (all pins with alternate and additional functions) to produce CSV. The XML ships only inside CubeMX. — [stderr.nl](https://www.stderr.nl/2020/12/16)
- A forum thread discusses creating a schematic symbol from an STM32 configuration. — [KiCad forum](https://forum.kicad.info/t/schematic-symbol-from-stm32-configuration/65234)
- KiCad 10 adds pin table CSV import/export in the Symbol Editor and pin/gate swap with back-annotation. — [KiCad 10 release post](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)

### Inferences
- A robust CI approach:
  1. `kicad-cli sch export netlist --format kicadxml`.
  2. A Python script maps MCU refdes pins to net names and pin functions (cross-checked with the `.ioc` or CubeMX XML).
  3. Emit `board_pins.h` or a Zephyr devicetree overlay as a build artifact.
  4. Fail CI if the committed firmware header differs from the generated one, or if a net assigned to a peripheral (e.g., I2C1_SDA) lands on a pin that does not support that alternate function.

### Gaps
- No maintained, KiCad-10-tested tool for bidirectional CubeMX↔KiCad sync was found.
- No source covers generating Zephyr DTS from KiCad.
