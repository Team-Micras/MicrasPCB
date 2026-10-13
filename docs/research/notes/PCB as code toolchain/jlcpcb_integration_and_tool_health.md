# JLCPCB/LCSC integration and project health of PCB-as-code toolchains (as of 2026-10-12)

Method note: GitHub numbers below come from the authenticated GitHub REST API, queried on 2026-10-12. "Commits last 12m" means commits on the default branch since 2025-10-12. "Human committers" means distinct commit authors with no "bot" in the name, so it is approximate (for example, `actions-user` was still counted for tscircuit/core). PyPI numbers come from the `pypi.org/pypi/<pkg>/json` endpoint, queried the same day. KiCad numbers come from the GitLab API. Shallow clones of atopile, diodeinc/pcb, circuit-synth, tscircuit/docs, SKiDL and KiBot were grepped to check code-level claims. Claims marked "(code)" were read directly from source files at the linked repo.

## A1. Picking parts by LCSC C-number: symbols, footprints and 3D models; Basic/Extended awareness; stock and price lookup

### Takeaway
KiCad has the richest and most mature set of LCSC/JLCPCB tools: Bouni's kicad-jlcpcb-tools, easyeda2kicad, JLC2KiCad_lib, the CDFER Basic-parts library and KiBot's LCSC 3D-model fetch. They all use a plain `LCSC`/`LCSC Part #` symbol field. Among the code-first tools, atopile and tscircuit have the deepest native LCSC integration. atopile has `ato create part` by C-number plus an auto-picker that knows about Basic/Preferred parts. tscircuit has import by C-number, a `jlcpcb:Cxxxx` footprint prefix and a parts engine built on jlcsearch. Both depend on a hosted company service for that integration. Diode/Zener, JITX, SKiDL and Circuit-Synth are weaker or indirect.

### Cited Findings
**KiCad + plugins**
- Bouni's kicad-jlcpcb-tools lets you search the JLCPCB parts database and assign parts to footprints, and those parts then appear in the BOM. You can type or paste an LCSC number such as `C25804`, or a product link from lcsc.com or jlcpcb.com. It warns before assigning numbers that aren't in the downloaded library, because JLC can still assemble "LCSC-only parts it buys in through pre-order or global sourcing" — [Bouni README](https://github.com/Bouni/kicad-jlcpcb-tools)
- Bouni's plugin recognizes `LCSC`, `JLC` and `JLCPCB` assignment fields. If no field exists, a non-empty assignment creates a hidden `LCSC` field. On KiCad 10 it supports per-design-variant LCSC assignments, price/stock comparison indicators and per-variant "Correction" (rotation) review — [Bouni README](https://github.com/Bouni/kicad-jlcpcb-tools)
- Bouni's parts database is rebuilt by a GitHub workflow that runs `jlcparts_db_convert.py`. In other words, it is derived from yaqwsx's jlcparts database — [update_parts_database.yml](https://github.com/Bouni/kicad-jlcpcb-tools/blob/main/.github/workflows/update_parts_database.yml)
- JLCPCB's own KiCad help article (updated 2026-09-09) says to add a symbol field named exactly `LCSC Part #`, because "JLCPCB uses this to match each component to its parts library" (example value C125111). It covers KiCad 9 and 10 — [JLCPCB help: BOM/CPL from KiCad](https://jlcpcb.com/help/article/how-to-generate-the-bom-and-centroid-file-from-kicad)
- The Fabrication Toolkit (bennymeg) accepts many field-name aliases: `LCSC Part #`, `LCSC Part`, `LCSC PN`, `JLCPCB Part #` and others. As fallbacks it also accepts `LCSC`, `JLC` and `MPN` — [Fabrication-Toolkit README](https://github.com/bennymeg/Fabrication-Toolkit)
- easyeda2kicad.py ("Convert any LCSC components (including EasyEDA) to KiCad library") has 1,692 stars and is AGPL-3.0. v1.0.1 came out on 2026-04-06, the first PyPI release since 0.8.0 in June 2024. It received a KiCad 10 footprint-format fix (#187, closed 2026-03-31) — [GitHub](https://github.com/uPesy/easyeda2kicad.py), [PyPI](https://pypi.org/project/easyeda2kicad/)
- JLC2KiCad_lib (TousstNicolas) generates a symbol, footprint and 3D-model library from JLC/LCSC numbers. It has 485 stars, an MIT license and v1.3.2 (2026-09-11), with 10 PyPI releases in the last 12 months — [GitHub](https://github.com/TousstNicolas/JLC2KiCad_lib), [PyPI](https://pypi.org/project/JLC2KiCadLib/)
- There is a KiCad action-plugin wrapper of easyeda2kicad that imports LCSC symbols, footprints and 3D models by part number (rasmushauschild/easyeda2kicad_plugin, 57 stars, last push 2025-08-22) — [GitHub](https://github.com/rasmushauschild/easyeda2kicad_plugin)
- The CDFER JLCPCB-Kicad-Library offers matched symbols, footprints and STEP models focused on JLCPCB **Basic and Preferred** parts, "ensuring no extra setup costs". Stock and pricing are updated daily through GitHub Actions, it supports Bouni's plugin, and it installs through the KiCad PCM. The author states "I'm not affiliated or sponsored by jlcpcb". It has 592 stars, an MIT license and a single committer — [GitHub](https://github.com/CDFER/JLCPCB-Kicad-Library)
- KiBot can download EasyEDA 3D models for any component with an LCSC code (`field_lcsc_part` global option, `download_lcsc` per output) — [KiBot docs notes_3d.rst](https://github.com/INTI-CMNB/KiBot/blob/master/docs/source/notes_3d.rst)
- No JLCPCB-published ("official") KiCad PCM plugin was found. JLCPCB's help center recommends the third-party Fabrication Toolkit instead — [JLCPCB help](https://jlcpcb.com/help/article/how-to-generate-the-bom-and-centroid-file-from-kicad)

**atopile**
- `ato create part --search <term>` accepts an LCSC ID (`C\d+`) or `mfr:partnumber`. It fetches the part from atopile's components API and downloads EasyEDA symbol, footprint and 3D data (`download_easyeda_info`) (code) — [create.py](https://github.com/atopile/atopile/blob/main/src/atopile/cli/create.py), [lcsc.py](https://github.com/atopile/atopile/blob/main/src/faebryk/libs/picker/lcsc.py)
- The picker's component model includes `lcsc`, `is_basic`, `is_preferred`, `stock` and tiered `price`. The code notes that "Setup fees (e.g. $3 per unique extended part) are one-time charges" (code) — [models.py](https://github.com/atopile/atopile/blob/main/src/faebryk/libs/picker/api/models.py)
- The picker API defaults to the hosted `https://components.atopileapi.com`, which can be overridden with `ATO_SERVICES_COMPONENTS_API_URL` (code) — [config.py](https://github.com/atopile/atopile/blob/main/src/atopile/config.py)
- atopile also maintains a fork of easyeda2kicad.py (atopile/easyeda2kicad.py, pushed 2026-04-03) — [GitHub](https://github.com/atopile/easyeda2kicad.py)

**tscircuit**
- You can import JLCPCB parts by C-number or keyword from the `tsci dev` editor (File → Import → JLCPCB Parts tab, "real-time stock information") or from the tscircuit.com web UI. Imported parts become `@tsci/...` registry packages — [docs: Importing from JLCPCB](https://docs.tscircuit.com/guides/importing-modules-and-chips/importing-from-jlcpcb)
- A footprint can reference an LCSC part directly with `footprint="jlcpcb:C2040"`, which loads it from the JLCPCB/EasyEDA record — [docs: JLCPCB Footprints](https://docs.tscircuit.com/footprints/jlcpcb-footprints)
- Passives usually need no `supplierPartNumbers`: "tscircuit will use the platform parts engine to automatically search vendors for a part matching your tolerances". `supplierPartNumbers` pins exact parts — [docs: resistor](https://docs.tscircuit.com/elements/resistor), [docs: Ordering Prototypes](https://docs.tscircuit.com/guides/ordering-prototypes)
- jlcsearch (jlcsearch.tscircuit.com) is an in-stock JLCPCB search engine. Any page returns JSON when you append `.json` (for example `/resistors/list.json?resistance=1k` returns lcsc, mfr, package, stock and price). It also has an `/api/footprinter_strings/Cxxxx` endpoint — [jlcsearch README](https://github.com/tscircuit/jlcsearch), [docs: jlcsearch API](https://docs.tscircuit.com/web-apis/jlcsearch-api)
- The tscircuit/easyeda-converter repo saw 305 commits from 19 committers in the last 12 months (GitHub API) — [GitHub](https://github.com/tscircuit/easyeda-converter)

**Diode (Zener / `pcb`)**
- `pcb bom` and component-search pricing fetch "US and Global offers" through the Diode API. LCSC offers are rendered as `lcsc.com/product-detail/<id>.html` links (code). The API base is `https://api.diode.computer`, and there is a `pcb auth login` flow — [CHANGELOG](https://github.com/diodeinc/pcb/blob/main/CHANGELOG.md), [bom.rs](https://github.com/diodeinc/pcb/blob/main/crates/pcb-diode-api/src/bom.rs), [quickstart](https://github.com/diodeinc/pcb/blob/main/docs/pages/quickstart.mdx)
- The part-search surface has changed repeatedly. The changelog records `pcb component search/download` being added, then removed in favor of `pcb search`. Later, "`pcb search` is gone; search the registry through the Diode API MCP endpoints" — [CHANGELOG](https://github.com/diodeinc/pcb/blob/main/CHANGELOG.md)
- The bundled stdlib ships standard KiCad footprints (`lib/std/kicad-footprints/...`). This repo has no LCSC-to-footprint importer equivalent to `ato create part` (code) — [diodeinc/pcb](https://github.com/diodeinc/pcb)

**JITX**
- `jitxlib.parts` provides parametric queries (`ResistorQuery`, `CapacitorQuery`, `search_parts`, `dbquery`) against JITX's own parts database. LCSC appears only as a low-level key (`make_part({"vendor_part_numbers.lcsc": "C2290"})`). The docs say nothing about Basic/Extended, stock or price — [docs: jitxlib.parts](https://docs.jitx.com/en/latest/jitxlib/jitxlib.parts.html)
- parts2jitx, a third-party MIT tool, imports LCSC/KiCad/EasyEDA part data into JITX code — [AUR python-parts2jitx](https://aur.archlinux.org/packages/python-parts2jitx)

**SKiDL**
- No LCSC/JLCPCB-specific module was found in the SKiDL source. Only generated KiCad library files mention LCSC. SKiDL uses KiCad symbol libraries, and LCSC numbers would be ordinary part fields (code grep) — [devbisme/skidl](https://github.com/devbisme/skidl)

**Circuit-Synth**
- It includes `manufacturing/jlcpcb/` modules: `jlc_parts_lookup`, `smart_component_finder`, `fast_search` and a `jlc_web_scraper`. These call `https://jlcpcb.com/external/genToken` and `.../external/component/getComponentInfos`, or scrape the public search with BeautifulSoup ("WARNING: Web scraping should be used responsibly...") (code) — [jlc_web_scraper.py](https://github.com/circuit-synth/circuit-synth/blob/main/src/circuit_synth/manufacturing/jlcpcb/jlc_web_scraper.py)

**Flux.ai (reference)**
- JLCPCB's Flux guide (updated 2026-09-10) says Flux's JLCPCB-specific BOM has both `LCSC Part #` and `JLCPCB Part #` columns. It doesn't explain how Flux fills them — [JLCPCB help: Flux](https://jlcpcb.com/help/article/how-to-export-the-bom-and-centroid-file-from-flux-ai)

**AI/MCP helpers (emerging)**
- An npm package `@jlcpcb/mcp` (v0.4.0) searches JLCPCB parts with a `basic_only` filter and stock/pricing, and converts them to KiCad symbols and footprints using EasyEDA data. Its README points to `github.com/anthropics/ai-eda`, and nothing on the page shows that JLCPCB publishes or endorses it — [README via jsDelivr](https://cdn.jsdelivr.net/npm/@jlcpcb/mcp@0.4.0/README.md)

### Inferences
- In atopile and tscircuit the "LCSC part becomes footprint" path goes through EasyEDA geometry. That geometry is what JLCPCB's own placement uses, which probably reduces CPL rotation surprises. The cost is a dependence on EasyEDA footprint quality (see A4).
- KiCad's LCSC tooling is spread across several community projects. It is mature and interchangeable because everything reduces to a plain `LCSC`/`LCSC Part #` field. That makes a KiCad-based flow the lowest-risk option for a JLCPCB-assembled micromouse board.
- Only atopile clearly exposes Basic/Preferred flags inside its picker data model. Bouni's plugin and the CDFER library cover the same need on the KiCad side.

### Gaps
- I couldn't confirm whether tscircuit's auto parts engine prefers JLCPCB Basic parts. jlcsearch's README says Basic/Preferred status is "not in the optimized db.sqlite3 ... until you add it", which suggests it may not ([jlcsearch README](https://github.com/tscircuit/jlcsearch)).
- I couldn't check whether atopile's hosted picker works without an account, or what it costs at scale.
- There's no documentation that JITX or Diode distinguish JLCPCB Basic from Extended parts.
- I couldn't verify the current JLCPCB "Preferred Extended" fee rules from a primary JLCPCB page in this session. The $3 per unique Extended part fee comes from atopile's code comment and secondary articles.

## A2. Generating JLCPCB fabrication and assembly outputs (Gerbers, drill, BOM, CPL with rotation correction) and whether JLCPCB has an ordering API

### Takeaway
On KiCad, three maintained generators produce JLCPCB-ready output, each with a rotation-correction mechanism: the Fabrication Toolkit (which JLCPCB explicitly recommends), Bouni's plugin, and KiBot's `JLCPCB` template or `kikit fab jlcpcb` for CI. Among the code-first tools, Diode `pcb` has a JLC BOM/CPL exporter, atopile has a JLC BOM/CPL exporter, and tscircuit has a fabrication zip plus in-platform JLCPCB ordering. Neither Diode nor atopile applies a rotation-offset database. JLCPCB does have an ordering API, but it is gated: you apply, and approval favors established business customers with regular volume.

### Cited Findings
- JLCPCB calls the Fabrication Toolkit "the recommended path for JLCPCB orders", because its BOM and CPL need no manual editing. It also advises keeping "Apply automatic component translations" on, since that "fixes part rotations/positions for JLCPCB". Required CPL columns are Designator, Mid X, Mid Y, Rotation and Layer, in mm. Article updated 2026-09-09 — [JLCPCB help](https://jlcpcb.com/help/article/how-to-generate-the-bom-and-centroid-file-from-kicad)
- The Fabrication Toolkit applies `rotations.cf` default corrections plus per-part `FT Rotation Offset` and `FT Position Offset` fields, and `FT Layer Override`. It has a CLI (`--autoTranslate`, `--excludeDNP`, ...) and is installed as a ZIP through the PCM. It has 691 stars, an Apache-2.0 license, release 5.3.1 (2026-05-15), 20 commits and 10 committers in the last 12 months — [README](https://github.com/bennymeg/Fabrication-Toolkit), GitHub API
- Bouni's plugin generates Gerber, BOM and CPL. Its rotation corrections come from matthewlai's JLCKicadTools database and can be managed in a "Rotation manager" — [Bouni README](https://github.com/Bouni/kicad-jlcpcb-tools)
- `kikit fab jlcpcb [--assembly --schematic ...]` produces `gerbers.zip`, `bom.csv` and `pos.csv`. It supports `--field CFG1_LCSC,LCSC` for configuration variants, a `JLCPCB_IGNORE` field, `--missingError` for CI, and `JLCPCB_CORRECTION` = `X;Y;Rotation` per symbol — [KiKit docs: fabrication/jlcpcb.md](https://github.com/yaqwsx/KiKit/blob/master/docs/fabrication/jlcpcb.md)
- KiBot ships `JLCPCB`, `JLCPCB_with_THT`, `JLCPCB_stencil` and `JLCPCB_stencil_with_THT` templates, and an internal `_rot_footprint_jlcpcb` rotation filter. It reads `JLCPCB Rotation Offset`/`JLCRotOffset` and `JLCPCB Position Offset`/`JLCPosOffset` fields. Its docs note that "KiCad mirrors components on the bottom side, but JLCPCB doesn't (november 2023)" and that the internal rotation DB "is just a list of common cases" — [KiBot notes_position.rst](https://github.com/INTI-CMNB/KiBot/blob/master/docs/source/notes_position.rst), [config_templates](https://github.com/INTI-CMNB/KiBot/tree/master/kibot/resources/config_templates)
- matthewlai/JLCKicadTools, the upstream rotation DB that Bouni reuses, has 355 stars and was last pushed 2025-05-01 — [GitHub](https://github.com/matthewlai/JLCKicadTools)
- atopile's `mfg-data` build step generates manufacturing artifacts, including a "CSV BOM (for JLCPCB manufacturing)" with an `LCSC Part #` column. Its JLCPCB pick-and-place converter only renames the KiCad .pos header (`Ref,Val,Package,PosX,PosY,Rot,Side` becomes `Designator,Val,Package,Mid X,Mid Y,Rotation,Layer`) and applies no rotation-offset table (code) — [jlcpcb.py (pnp)](https://github.com/atopile/atopile/blob/main/src/faebryk/exporters/pcb/pick_and_place/jlcpcb.py), [jlcpcb.py (bom)](https://github.com/atopile/atopile/blob/main/src/faebryk/exporters/bom/jlcpcb.py)
- Diode `pcb` has `pcb ipc2581 cpl --format jlc` and `pcb ipc bom --format jlc`, plus Gerber exports in "a JLCPCB-compatible subset". Its JLC rotation function only normalizes angles to whole degrees in 0..360 and refuses parts that aren't on the top or bottom side (code) — [CHANGELOG](https://github.com/diodeinc/pcb/blob/main/CHANGELOG.md), [cpl.rs](https://github.com/diodeinc/pcb/blob/main/crates/pcb-ipc2581-tools/src/commands/cpl.rs)
- tscircuit exports a fabrication-files zip with Gerbers, BOM CSV and pick-and-place CSV. The tscircuit.com platform has an Order button that gets quotes and checks out via Stripe. "Currently, JLCPCB is the only available vendor" — [docs: Ordering Prototypes](https://docs.tscircuit.com/guides/ordering-prototypes)
- Flux exports manufacturer-specific BOM and CPL. JLCPCB says to "always use the files marked `JLCPCB`, and ignore everything else". Flux has no direct order integration, so you upload files manually — [JLCPCB help: Flux](https://jlcpcb.com/help/article/how-to-export-the-bom-and-centroid-file-from-flux-ai)
- JLCPCB's API offering: you apply through your account manager or by emailing support@jlcpcb.com. Approval depends on review of "past orders, your company, and your business situation". There are two tiers: a Pricing API, and an Ordering API (Gerber upload, ordering, tracking) aimed at partners with experienced developers and regular monthly volume. The developer portal api.jlcpcb.com ("JLCAPI") lists PCB, stencil, 3D-printing and components APIs. A direct fetch of the help article returned HTTP 404 during this session, so these details come from search-index snippets of those pages — [api.jlcpcb.com](https://api.jlcpcb.com/), [JLCPCB API help article](https://api.jlcpcb.com/help/article/jlcpcb-online-api-available-now)

### Inferences
- For a hobby or student micromouse team, "one-click ordering" in practice means: generate the files with Fabrication Toolkit, KiBot or KiKit, then upload them. The JLCPCB Ordering API is not a realistic option for a low-volume individual. tscircuit's platform checkout is the only end-to-end "order from the tool" path among the candidates.
- atopile and Diode outputs might still need manual rotation checks in JLCPCB's placement preview. atopile parts come from EasyEDA (probably JLC-aligned). Diode uses KiCad-library footprints, which per KiBot and Fabrication Toolkit docs often need rotation corrections. Neither tool has a correction database. The CPL can be post-processed, or the board can be run through KiBot/KiKit, because both tools produce a `.kicad_pcb`.

### Gaps
- I couldn't fully verify whether tscircuit's pick-and-place applies JLC rotation corrections.
- I didn't find documentation of JITX's JLCPCB BOM/CPL output format (the docs list ODB++ export and an export plugin module).
- The exact current wording and eligibility of JLCPCB's API terms could not be re-fetched (404).

## A3. JLCPCB design rules and stackups as code

### Takeaway
No single maintained "official" JLCPCB rule pack exists for KiCad. The community `.kicad_dru` (labtroll) targets KiCad 7 and is stale, and the community JLC stackup board files are auto-generated and unverified. The code-first tools have stronger built-in JLC knowledge. Diode ships a versioned, sourced JLCPCB DFM "PDK" (updated 2026-09-29). JITX ships JLC04161H-1080/-7628 and JLC06161H-7628 stackups with rules and vias. atopile's stdlib references JLC stackups such as `JLC041612_3313`.

### Cited Findings
- labtroll/KiCad-DesignRules provides "JLCPCB Design Rules for KiCad 7.0" as a `JLCPCB.kicad_dru` file that you copy and rename to the project name. It has 369 stars, no license, and its last push was 2024-11-29 (no commits in the last 12 months) — [GitHub](https://github.com/labtroll/KiCad-DesignRules)
- gsuberland/jlcpcb_autogenerated_stackups provides empty `.kicad_pcb` files that you import through Board Setup → Import settings ("Board layers and physical stackup"). They were "generated automatically from the stackup specs on JLCPCB's website" and "have not been manually tested for validity or accuracy". It has 133 stars, and its last push was 2025-05-20 — [GitHub](https://github.com/gsuberland/jlcpcb_autogenerated_stackups)
- JLCPCB's impedance calculator assumes Nan Ya NP-155F core for 4–8 layer boards. Users should select the matching material when ordering — [JLCPCB Impedance Calculator guide](https://jlcpcb.com/help/article/user-guide-to-the-jlcpcb-impedance-calculator)
- In an EEVblog thread, a user found that JLC04161H-7628 gave 85 Ω differential at 4 mil gap and 8.09 mil width. Another user noted that 7628 prepreg is about twice the thickness assumed in an app note — [EEVblog](https://www.eevblog.com/forum/manufacture/jlc-pcb-stackup-layer-spacing)
- Diode's `pcb` bundles `pdks/jlcpcb.toml` (id `jlcpcb-rigid-fr4`, revision `advisory-mask-2026-09-29`). It sources the public JLCPCB capability table (accessed 2026-09-01) and encodes rules such as minimum via hole 0.15 mm (preferred 0.20 mm), minimum NPTH 0.50 mm, and a 0.10 mm advisory soldermask web. It runs as IPC-2581-based DFM checks (code) — [jlcpcb.toml](https://github.com/diodeinc/pcb/blob/main/crates/pcb-ipc2581-tools/pdks/jlcpcb.toml), [CHANGELOG](https://github.com/diodeinc/pcb/blob/main/CHANGELOG.md)
- JITX's `jitxlib.jlcpcb` contains `JLC04161H_1080`, `JLC04161H_7628`, `JLC06161H_7628`, `materials`, `rules` and `vias` — [JITX docs](https://docs.jitx.com/en/latest/jitxlib/jitxlib.jlcpcb.html)
- atopile's docs landing page shows a sample referencing stackup `ELEC::JLCPCB::JLC041612_3313`. The repo also has branches `feature/jlcpcb_stackup_importer`, `feature/add_dru_file_format` and `feature/board-rules` — [docs.atopile.io](https://docs.atopile.io/), [branches](https://github.com/atopile/atopile/branches)
- An open atopile issue (2026-10-04) reports "`ato build` silently converts blind/micro vias to through vias". It has no maintainer reply yet — [atopile issues](https://github.com/atopile/atopile/issues)

### Inferences
- A KiCad micromouse project would still need to keep its own `.kicad_dru` and stackup checked against JLCPCB's capability page. Treat the community files as starting points only. A small, versioned in-repo `.kicad_dru` is a cheap form of "rules as code" that also works if any of the PCB-as-code tools emits the KiCad board.
- Diode's PDK is the most rigorous JLC rules-as-code artifact found. It is tied to Diode's IPC-2581 pipeline, though.

### Gaps
- I didn't find a JLCPCB-published KiCad `.kicad_dru` or stackup file.
- I didn't verify whether KiBot or KiKit ship a JLC DRC preset (none was seen in the template list).

## A4. Quality of footprints imported from LCSC/EasyEDA

### Takeaway
EasyEDA/LCSC footprints are mostly community-contributed and unchecked. There are documented cases of reversed polarity, pin-count mismatches, oversized holes, wrong pin numbering, QFN pad mismatches and rotation errors. Every converter (easyeda2kicad, JLC2KiCad, atopile, tscircuit) inherits these problems, so each imported footprint should be checked against the datasheet.

### Cited Findings
- EasyEDA forum threads report LED footprints with reversed polarity, a footprint with three pads for a two-pin symbol (C390032), a connector with holes that are far too large, and a part whose JLCPCB rotation was wrong while the EasyEDA rotation was right. Users note that EasyEDA does not check user-contributed parts — [EasyEDA forum C390032](https://www.easyeda.com/forum/topic/C390032-Polarity-reversed-00ef47654ed147ec955b06db7678d92d), [EasyEDA forum: Harmful error in datasheets and footprints](https://easyeda.com/forum/topic/Harmful-error-in-datasheets-and-footprints-991224a6ea9d49fb9c475a15f16dc32c), [EasyEDA forum: footprint error C478453](https://www.easyeda.com/forum/topic/Error-in-footprint-part-C478453-57a402930711419b9a0d4e81148dd0a1)
- easyeda2kicad issue history includes "UFQFPN (QFN) footprint pads do not match source exactly" (#168), "Wrong pin numbering" (#179), "Symbol text orientation wrong" (#207, open) and a "broken 3d model import" fix (#133) — [easyeda2kicad issues](https://github.com/uPesy/easyeda2kicad.py/issues)
- KiCad bug #21238: an EasyEDA-exported footprint (LCSC C34388683) failed to parse in KiCad 9.0.2 — [KiCad GitLab](https://gitlab.com/kicad/code/kicad/-/issues/21238)
- jlcsearch computes a `copper_iou` score when it maps an LCSC footprint to a tscircuit footprinter string (example 0.992). This is a way to measure footprint matching automatically — [jlcsearch README](https://github.com/tscircuit/jlcsearch)
- atopile has an open issue on "Duplicate UUIDs across instances of the same part" (2026-08-05, no replies) — [atopile issues](https://github.com/atopile/atopile/issues)

### Inferences
- For a micromouse, the riskiest imported footprints are the IMU (LGA/QFN), the motor driver (QFN/HTSSOP with exposed pad), the IR emitter/receiver polarity, and connectors. Verify these by hand regardless of toolchain, or use KiCad standard-library footprints with a rotation correction. Checks: datasheet overlay, 3D-model check, and JLCPCB placement preview.

### Gaps
- There's no quantitative error-rate study of EasyEDA/LCSC footprints.

## A5. Parts-data infrastructure: jlcparts, jlcsearch, LCSC/JLCPCB APIs

### Takeaway
Most of the open JLCPCB parts ecosystem depends on one upstream: yaqwsx/jlcparts. It fetches data with JLCPCB and LCSC API credentials held as repo secrets, three times a day, and in the last 12 months had only 2 human committers. Bouni's plugin database and tscircuit's jlcsearch are both built from it. LCSC's official API needs an approved key. jlcsearch provides a no-key JSON API.

### Cited Findings
- jlcparts' update workflow runs on cron 3×/day (03:00, 11:00, 19:00 UTC). It uses secrets `LCSC_KEY`, `LCSC_SECRET`, `JLCPCB_APP_ID`, `JLCPCB_ACCESS_KEY` and `JLCPCB_SECRET_KEY`, runs `jlcparts fetchdb` and `jlcparts updatepreferred`, and publishes to yaqwsx.github.io/jlcparts — [update_components.yaml](https://github.com/yaqwsx/jlcparts/blob/master/.github/workflows/update_components.yaml)
- jlcparts has 838 stars and an MIT license. In the last 12 months it had 693 commits and 2 human committers (yaqwsx, LukeShu). It is funded only by a Ko-fi link — GitHub API, [README](https://github.com/yaqwsx/jlcparts)
- jlcsearch's README: "It all starts with the jlcparts project, which compiles a massive 11GB sqlite3 database of everything JLCPCB has to offer". jlcsearch rebuilds that into a database under 2 GB nightly at 05:00 UTC, "after the upstream jlcparts refresh" — [jlcsearch README](https://github.com/tscircuit/jlcsearch)
- jlcsearch has 36 stars, 225 forks and 297 open issues/PRs, with 99 commits from 5 committers in the last 12 months — GitHub API
- LCSC's official API needs a key plus nonce, timestamp and SHA-1 signature, and you get the key by applying for a user ID at LCSC. Its agent page lists KeywordSearch, category, cart and ordering APIs — [LCSC API docs](https://www.lcsc.com/docs/index.html), [LCSC agent APIs](https://www.lcsc.com/agent)

### Inferences
- If jlcparts stops, or its maintainer's API keys are revoked, Bouni's in-plugin search and tscircuit's jlcsearch would both go stale together. That is a real single point of failure. atopile (its own components API) and Diode (its own API) use separate company-run pipelines, which brings a different risk: dependence on the vendor.

### Gaps
- I couldn't confirm whether atopile's components API is itself derived from jlcparts.

## B1. Release cadence and activity (last 12 months, to 2026-10-12)

### Takeaway
KiCad (10.0.0 released 2026-03-20, point releases about monthly, latest 10.0.7 on 2026-10-06) is by far the healthiest base. Diode `pcb` and tscircuit are the most active code-first projects, though both are pre-1.0 with very high churn. atopile is a warning case: its public GitHub repo has been nearly frozen since March 2026 while PyPI releases continued. Circuit-Synth looks stalled. SKiDL is steady, low-volume and run by one maintainer.

### Cited Findings
| Project | Stars | License | Latest release | Releases (12m) | Default-branch commits (12m) | Human committers (12m) | Last push |
|---|---|---|---|---|---|---|---|
| KiCad (GitLab) | 1,094 (GitLab mirror) | GPL | 10.0.7, 2026-10-06 | 10.0.0–10.0.7 | v10 cycle: 7,609 commits | "hundreds of developers..." | 2026-10-13 |
| KiBot | 753 | AGPL-3.0 | v1.9.1, 2026-07-28 | 3 | 463 | 4 | 2026-10-08 |
| KiKit | 2,041 | MIT | v1.8.1, 2026-08-05 | 2 | 45 | 5 | 2026-10-09 |
| Bouni kicad-jlcpcb-tools | 2,105 | MIT | 2026.04.03 (2026-04-23) | 3 | 354 | 14 | 2026-10-13 |
| Fabrication-Toolkit | 691 | Apache-2.0 | 5.3.1, 2026-05-15 | 3 | 20 | 10 | 2026-09-29 |
| easyeda2kicad.py | 1,692 | AGPL-3.0 | v1.0.1, 2026-04-06 | 1 | 86 | 4 | 2026-04-08 |
| jlcparts | 838 | MIT | (none, continuous) | – | 693 | 2 | 2026-10-13 |
| atopile | 3,988 | MIT | GitHub v0.14.1004 (2026-02-12); PyPI 0.15.9 (2026-09-12) | GitHub 6 / PyPI 22 | 108 (last main commit 2026-03-11) | 6 | 2026-06-13 |
| tscircuit (meta repo) | 2,830 | MIT | tags only, v0.0.2849 | continuous npm | ≥4,000 (mostly automated bumps) | 11 | 2026-10-13 |
| tscircuit/core | 60 | MIT | v0.0.2136 | continuous | 2,985 | ~33 | 2026-10-13 |
| SKiDL | 1,691 | MIT | 2.3.0, 2026-07-28 | 5 | 196 | 9 | 2026-09-24 |
| Circuit-Synth | 285 | MIT | v0.12.1, 2026-01-09 | 16 GH / 33 PyPI | 357 | 4 | 2026-03-08 (last commit) |
| Diode `pcb` | 460 | MIT | v0.4.77, 2026-10-13 | ≥100 (≥200 since 2025-09-19) | 1,604 | 12 | 2026-10-13 |
| JITX (`jitx` on PyPI) | n/a (closed core) | proprietary core | 4.4.3, 2026-10-01 | 13 | n/a | n/a | n/a |

Sources: GitHub API for each repo ([KiBot](https://github.com/INTI-CMNB/KiBot), [KiKit](https://github.com/yaqwsx/KiKit), [Bouni](https://github.com/Bouni/kicad-jlcpcb-tools), [Fabrication-Toolkit](https://github.com/bennymeg/Fabrication-Toolkit), [easyeda2kicad](https://github.com/uPesy/easyeda2kicad.py), [jlcparts](https://github.com/yaqwsx/jlcparts), [atopile](https://github.com/atopile/atopile), [tscircuit](https://github.com/tscircuit/tscircuit), [tscircuit/core](https://github.com/tscircuit/core), [SKiDL](https://github.com/devbisme/skidl), [circuit-synth](https://github.com/circuit-synth/circuit-synth), [diodeinc/pcb](https://github.com/diodeinc/pcb)); [KiCad GitLab tags](https://gitlab.com/kicad/code/kicad/-/tags); [PyPI atopile](https://pypi.org/project/atopile/); [PyPI jitx](https://pypi.org/project/jitx/); [PyPI circuit-synth](https://pypi.org/project/circuit-synth/); [PyPI skidl](https://pypi.org/project/skidl/)

- KiCad 10.0.0 was released 2026-03-20. "Our annual development cycle continues to provide regular major releases". The v10 cycle had 7,609 unique commits, "a notable increase from Version 9". Donations go through The Linux Foundation — [KiCad blog](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)
- KiCad 10 point releases: 10.0.5 (2026-07-21), 10.0.6 (2026-08-28), 10.0.7 (2026-10-06) — [KiCad GitLab tags](https://gitlab.com/kicad/code/kicad/-/tags)
- **atopile anomaly.** The last commit on public `main` is 2026-03-11, and the public tags end at v0.14.1004. PyPI meanwhile published 0.15.0–0.15.9 (0.15.9 on 2026-09-12, wheels for cp314 only, `requires_python >=3.14,<3.15`). Issues and PRs opened Aug–Oct 2026 have 0 or 1 comments, and external PRs remain unmerged — GitHub API, [PyPI](https://pypi.org/project/atopile/), [issues](https://github.com/atopile/atopile/issues)
- atopile.io's headline is now "atopile 0.16 — Design electronics with code". docs.atopile.io says "pre-release atopile is under heavy development" and that docs ship inside the (web) editor — [atopile.io](https://atopile.io/), [docs.atopile.io](https://docs.atopile.io/)
- atopile's enterprise page, as indexed by search, describes a core rewrite shipped in 0.14 (January 2026), a Web IDE, agents, an on-prem platform, 3.9k stars and "685 pull requests opened in July alone". I could not fetch the page body directly, and the July PR count does not match the public repo — [atopile enterprise](https://atopile.io/enterprise)
- atopile and Diode both forked PCBJam, a KiCad WebAssembly port. atopile's fork README: "remove all features that are not related to PCB design", "bidirectional sync support", and it is used in "the atopile web-IDE" — [atopile/pcbjam](https://github.com/atopile/pcbjam), [diodeinc/pcbjam](https://github.com/diodeinc/pcbjam)
- Circuit-Synth: the last commit (2026-03-08) only added a dependency. Before that came v0.12.1 on 2026-01-09. PyPI shows a burst of 33 releases from Nov 2025 to Jan 2026, then nothing — GitHub API, [PyPI](https://pypi.org/project/circuit-synth/)
- SKiDL 2.3.0 (2026-07-28) added `KICAD10` support. Its HISTORY shows steady KiCad-version tracking, with KICAD9 added earlier — [SKiDL HISTORY.md](https://github.com/devbisme/skidl/blob/master/HISTORY.md)
- JITX 4.0.0 is "Initial release of the Python driven version of JITX" (replacing the Stanza-based product). 4.4.0 added layout capture in Python. 4.0.0 was yanked on PyPI — [JITX release notes](https://docs.jitx.com/en/latest/release-notes.html), [piwheels jitx](https://www.piwheels.org/project/jitx/)

### Inferences
- atopile's PyPI release stream continuing while the public repo is frozen strongly suggests that main development moved to a non-public repo or branch around March 2026. This is an inference, not confirmed. If so, the "open-source, MIT" exit path for atopile is much weaker in practice than the license suggests: community PRs aren't merged and the source of the shipped 0.15.x wheels isn't visible.
- tscircuit's raw commit counts are inflated by automated version-bump commits. Its broad contributor base (33+ in core) looks like bounty-driven work and is probably less stable than a core team.

### Gaps
- I have no official statement from atopile explaining the repo freeze. Looking at atopile's Discord or a direct inquiry is recommended.
- I didn't count KiCad's unique contributors for the last 12 months.
- Discord/forum size figures were not gathered for any project.

## B2. Funding, company backing and business model

### Takeaway
KiCad is backed by a nonprofit and donations (Linux Foundation) and has no commercial lock-in. Each code-first tool is a small venture-backed or bootstrapped startup with a hosted-service business model: atopile, tscircuit, Diode, JITX and Flux. Funding data for most of them comes from aggregators and partly conflicts. Flux and Diode are the best funded.

### Cited Findings
- **KiCad**: donations go through The Linux Foundation, a 501(c)(6) — [KiCad blog](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/)
- **atopile**: Tracxn reports $500K over 1 round from 1 investor. Latka estimates $1.1M ARR and 7 employees and calls it "Bootstrapped". Both are aggregator estimates. Fondo published an "atopile launches" post that search tools date to 2026-02-09 — [Tracxn](https://tracxn.com/d/companies/atopile/__V3d2i6LS7EtUe9K6mWF-Qgv6TmwxT-6SNQZZBnau4Ew), [Latka](https://getlatka.com/companies/atopile.io), [Fondo](https://fondo.com/blog/atopile-launches). atopile offers an enterprise product (Web IDE, agents, on-prem) — [atopile enterprise](https://atopile.io/enterprise)
- **tscircuit**: Tracxn and PitchBook list only Boost VC (seed, PitchBook date 2024-01-01, amount undisclosed). Founder: Severin "Seve" Ibarluzea — [Tracxn](https://tracxn.com/d/companies/tscircuit/__yM3mzwwUYAKrnLjmobBSous9TmlZrkn1G9iYPxM4lP0/funding-and-investors), [PitchBook](https://pitchbook.com/profiles/company/706716-37). Revenue model: the platform includes paid fabrication ordering through Stripe checkout — [docs](https://docs.tscircuit.com/guides/ordering-prototypes)
- **Diode Computers**: YC Summer 2024, founded 2024, New York. Funding reports conflict: an $11.4M Series A led by a16z ([yespress](https://yespress.io/diode-computers-inc)) versus a $14.5M round announced 2025-05-06 ([Seedtable](https://seedtable.com/companies/diode-computers/funding-rounds/seed-2025-05)). It offers a design and manufacturing service alongside the open-source toolchain. Diode worked with Anthropic on Claude generating Zener reference designs — [gend.co blog](https://www.gend.co/blog/enhancing-claude-pcb-design-skills)
- **JITX**: $12M Series A led by Sequoia (Sept 2022), with YC, FundersClub and Liquid 2 — [JITX blog](https://www.jitx.com/blog/series-a-announcement). Tracxn shows no newer round (total $12.1M) — [Tracxn](https://tracxn.com/d/companies/jitx/__jUTcWraTa5nR56YOnxXEEaiw6oGovUPkYsPD_tauVow/funding-and-investors). Latka estimates $2.7M revenue and 25 staff in 2023 (aggregator) — [Latka](https://getlatka.com/companies/jitx.com/competitors). The `jitxcore` package license is "Other/Proprietary License" — [pypi.jitx.com](https://pypi.jitx.com/jitx/unstable/jitxcore/0.1.3.dev24+g7b24237)
- **Flux.ai**: about $37M announced 2026-02-27 (Series B led by 8VC plus an earlier $10M seed) — [SiliconANGLE](https://siliconangle.com/2026/02/27/flux-nabs-37m-automate-printed-circuit-board-development-ai/). This conflicts with a "$30M Series B led by APC" report — [TBPN digest](https://www.tbpndigest.com/story/2026-03-02/flux-raises-30m-series-b-led-by-apc-to-build-ai-hardware-engineer-for-pcb-design). Tracxn lists $49M total over 3 rounds — [Tracxn](https://tracxn.com/d/companies/flux-ai/__DgsqcxsjLsm7cUHAQiGcPjtiZwIU_vAHmJznT8TYkS8). On 2026-09-24 Flux launched AI "PCB to prototype" enclosure features — [Manila Times/GlobeNewswire](https://www.manilatimes.net/2026/09/24/tmt-newswire/globenewswire/flux-launches-new-ai-capabilities-to-take-hardware-designs-from-pcb-to-prototype/2432222)
- **SKiDL**: hosted under the personal account of maintainer devbisme. No company backing was found — [GitHub](https://github.com/devbisme/skidl)
- **Circuit-Synth**: the organization is circuit-synth, and the primary author in commits is Shane Mattner. No funding was found — [GitHub](https://github.com/circuit-synth/circuit-synth)
- **KiCad JLC helpers** (Bouni, bennymeg, yaqwsx, CDFER): community and volunteer projects. jlcparts asks for Ko-fi support, and CDFER states no JLCPCB affiliation — [jlcparts](https://github.com/yaqwsx/jlcparts), [CDFER](https://github.com/CDFER/JLCPCB-Kicad-Library)

### Inferences
- A startup's commercial incentive (web IDE, agents, hosted parts APIs, ordering margins) is exactly what produces lock-in pressure and pivots. The atopile repo freeze and Diode's repeated CLI-surface changes fit this pattern.

### Gaps
- I couldn't confirm the funding figures from primary announcements for atopile, tscircuit or Diode.
- I found no current pricing for JITX, or for atopile's enterprise and hosted offerings.

## B3. Breaking changes, bus factor and abandonment risk

### Takeaway
KiCad's core is low-risk. However, the planned removal of the SWIG Python API in KiCad 11 threatens the JLC-output plugins (Bouni, Fabrication Toolkit) and possibly KiKit/KiBot internals, and only Bouni has started an IPC-API port issue. Among the code-first tools: Diode has the highest churn (about 200 pre-1.0 releases and repeated command removals). atopile has a major-rewrite history and is now opaque. tscircuit sits at 0.0.x versions. Circuit-Synth has effectively stalled. SKiDL and jlcparts have a bus factor of about 1–2.

### Cited Findings
- KiCad's developer docs say the SWIG bindings were deprecated in 9.0 and "the current plan is to remove the SWIG bindings in KiCad 11.0" (an earlier target was 10.0). Forum users report SWIG is already removed in v11 nightlies and Python is no longer bundled — [KiCad dev docs](https://dev-docs.kicad.org/en/apis-and-binding/pcbnew/), [KiCad forum](https://forum.kicad.info/t/migration-schedule-from-the-old-swig-api-to-the-ipc-api/69437)
- Bouni's plugin still uses `import pcbnew` (SWIG). An issue opened 2026-10-12, "KiCad 11 support: a board-access layer first, then an IPC backend", is open. In Sept–Oct 2026 the plugin also needed fixes for SWIG 4.5 and Python 3.14 (`SwigPyIterator` has no attribute `next`) — [Bouni issues](https://github.com/Bouni/kicad-jlcpcb-tools/issues)
- The Fabrication Toolkit imports `pcbnew` in `plugins/plugin.py`, `utils.py` and `config.py`, and no `kipy` (IPC) usage was found — [Fabrication-Toolkit](https://github.com/bennymeg/Fabrication-Toolkit)
- KiKit recently hit KiCad 10 SWIG breakages too: `SwigPyIterator` (2026-09) and "ZONE.Duplicate() missing 1 positional argument - KiCad 10.0.5" (2026-07). Both are closed — [KiKit issues](https://github.com/yaqwsx/KiKit/issues)
- Diode `pcb` changelog: 155 version headings, with search commands added, removed and renamed several times. It also has a migration command (`pcb migrate`) that rewrites registry references from GitHub to DiodeHub — [CHANGELOG](https://github.com/diodeinc/pcb/blob/main/CHANGELOG.md)
- atopile: "core rewrite ships in atopile 0.14 in January 2026" ([enterprise](https://atopile.io/enterprise)). The 0.15 wheels pin Python 3.14 exactly. Open issue: "win_amd64 wheel crashes on import with 0xC000001D (illegal instruction)" (2026-09-06, 0 comments) — [PyPI](https://pypi.org/project/atopile/), [issues](https://github.com/atopile/atopile/issues)
- tscircuit packages are still versioned 0.0.x (tscircuit v0.0.2849, core v0.0.2136) — GitHub tags
- Single-maintainer components: jlcparts (2 committers), CDFER library (1), JLC2KiCad_lib (2), SKiDL (1 dominant maintainer; 9 committers in 12m) — GitHub API

### Inferences
- If the micromouse PCB is done in 2026–early 2027 on KiCad 10, the SWIG-removal risk is manageable: pin KiCad 10.0.x and use KiBot or KiKit in a container. KiBot and KiKit lean more on `kicad-cli`, but this was not fully verified. Moving to KiCad 11 may temporarily break the GUI JLC plugins.
- Diode's toolchain is unlikely to be abandoned soon (well funded, very active) but likely to keep breaking user workflows. atopile has the highest "uncertain direction" risk among the funded tools. Circuit-Synth has the highest abandonment risk.

### Gaps
- I have no data on whether KiBot or KiKit have concrete IPC-API migration plans for KiCad 11.

## B4. Lock-in and exit path (can you continue in plain KiCad if the tool dies?)

### Takeaway
KiCad is the common escape hatch. atopile and Diode generate or round-trip real `.kicad_pcb` layouts, so layout work survives the tool, although the source of truth (`.ato`/`.zen`) does not. tscircuit can export KiCad PCB, schematic and project files through a young converter. Circuit-Synth and SKiDL emit KiCad schematics and netlists. JITX exits mainly through Altium compatibility and ODB++. Flux has no native KiCad project export, so leaving means a netlist or Gerber rebuild.

### Cited Findings
- atopile describes itself as "layout that works natively with KiCad". Its transformer writes and deduplicates designators in the KiCad PCB layout — [PyPI description](https://pypi.org/project/atopile/), [commit log](https://github.com/atopile/atopile/commits/main)
- Diode's `pcb` CLI "builds those designs, manages dependencies, and generates KiCad layout files". The repo includes `pcb-kicad`, `pcb-kicad-sch` and `pcb-layout` crates — [gend.co](https://www.gend.co/blog/enhancing-claude-pcb-design-skills), [diodeinc/pcb crates](https://github.com/diodeinc/pcb/tree/main/crates)
- tscircuit's `circuit-json-to-kicad` exposes `CircuitJsonToKicadPcbConverter`, `CircuitJsonToKicadSchConverter` and `CircuitJsonToKicadProConverter`. In a mid-2026 community thread, multi-layer via handling was still being worked on. Separately, `tsci export -f kicad-library` exports symbols, footprints and 3D models. The converter repo has 8 stars and was pushed 2026-10-11 — [community thread](https://community.tscircuit.com/thread/1521548245896134697), [docs: exporting KiCad library](https://docs.tscircuit.com/guides/kicad/exporting-kicad-library), [circuit-json-to-kicad](https://github.com/tscircuit/circuit-json-to-kicad)
- Circuit-Synth is "fully bi-directional": you can import existing `.kicad_sch` into Python and export back, and it does back-annotation of reference designators — [README](https://github.com/circuit-synth/circuit-synth)
- SKiDL generates KiCad netlists and schematics (KiCad 6–10), and has `netlist_to_skidl` for reverse conversion — [HISTORY.md](https://github.com/devbisme/skidl/blob/master/HISTORY.md)
- JITX's docs list `jitx.compat.altium` and `jitx.plugin.export`, and the release notes mention ODB++ export. KiCad is not mentioned on the docs landing page — [JITX docs](https://docs.jitx.com/en/latest/), [release notes](https://docs.jitx.com/en/latest/release-notes.html)
- Flux's `.flx` project "is not automatically a KiCad ... native project file", so migration is a netlist-based rebuild. Source: Quilter, a competitor, so it may be biased — [Quilter blog](https://www.quilter.ai/blog/migrate-from-flux-ai-pcb-export). A Flux community page suggests exporting a netlist plus Gerbers for KiCad — [Flux project page](https://www.flux.ai/vasy_skral/lora-load-cell-manager~51)

### Inferences
- From an exit-path view, the safest pairing is "code-first front end that writes standard KiCad files, plus LCSC fields stored as plain symbol fields". The KiCad-side JLC tools (KiBot, Fabrication Toolkit, Bouni) then keep working if the front end dies. atopile, Diode and SKiDL fit this. tscircuit fits partially, given converter maturity.

### Gaps
- Round-trip fidelity of atopile, Diode or tscircuit KiCad output (zones, net classes, custom rules) was not tested here.
- I couldn't confirm whether JITX currently exports KiCad projects.

## B5. Notable adopters (2025–2026)

### Takeaway
Public evidence of named production adopters is thin for every code-first tool. Most visible use is by the vendors themselves: atopile's own hardware repos, Diode's reference designs, and tscircuit tutorials. KiCad plus JLCPCB is the de facto standard for hobby, student and open-hardware STM32 boards, including micromouse projects.

### Cited Findings
- atopile's organization hosts its own hardware projects, for example `hyperion` ("High refresh rate bright af LED matrix", pushed 2026-08-06), `ai-pin` and `hivehaus` — [atopile org](https://github.com/atopile)
- Diode maintains `diodeinc/kicad`, "Kicad library reference designs ready to share" (18 stars, updated 2026-04) — [GitHub](https://github.com/diodeinc/kicad)
- Adafruit's blog (2026-05-07) covered making electronics with tscircuit via Codex — [Adafruit blog](https://blog.adafruit.com/2026/05/07/making-electronics-with-tscircuit-via-codex-no-kicad-altium-eagle/)
- The micromouse "Mushak" (STM32F405RG, VL6180x ToF, DRV8833) was drawn in KiCad 6 and shared on PCBWay — [PCBWay project](https://www.pcbway.com/project/shareproject/Mushak_A_half_size_micromouse_f1889e61.html). Phil's Lab STM32 KiCad tutorials cover JLCPCB assembly — [fedevel](https://fedevel.com/blog/kicad-stm32-usb-buck-converter-pcb-design-and-jlcpcb-assembly-update-phils-lab-11)
- Commercial PCB houses support KiCad 10 natively, for example AISLER ("KiCad 10 is live and 100% supported by AISLER") — [AISLER community](https://community.aisler.net/t/kicad-10-is-live-and-100-supported-by-aisler/5567)

### Inferences
- No evidence was found of a micromouse or comparable small-robot board built in atopile, tscircuit, Diode or JITX. Choosing one of them means being an early adopter.

### Gaps
- No verified list of named companies using atopile, tscircuit, Diode or JITX in production in 2025–2026 was found. Vendor case studies and Discord showcases were not searched exhaustively.
