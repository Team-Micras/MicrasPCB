# Online Visualization & Collaboration Platforms for Open/Code-First PCB Toolchains (Altium 365-like), as of Oct 2026

Research date: 2026-10-12. About 35 search/fetch calls. Many vendor pages render prices as JS, and several pages show no dates, so some status claims carry a recency caveat. These are noted inline.

## Q1. Hosted / self-hostable platforms: status, features, pricing, KiCad compatibility, git integration

### Takeaway
For a git + KiCad workflow, the realistic hosted options in Oct 2026 are **KiHub** (new in 2026, a GitHub App, free for public repos, $19-24/contributor/month for private), **CADLAB.io** (cheap, $0 for open source and $8-12/month paid, self-hosted git integrations), and **AllSpice** (now enterprise-only from $34.8k/yr, though students and robotics clubs can ask for an arrangement). **KiCAD Prism** is the strongest open-source self-hosted "Altium 365 for KiCad" (Apache-2.0). Altium 365 Viewer reads KiCad only in beta. Flux, EasyEDA Pro, and tscircuit/atopile are separate ecosystems that do not ingest a modern KiCad project and give you a review portal around it.

### Cited Findings

**KiHub (kihub.dev), new in 2026**
- Product Hunt launch around Aug 2026. The listing says "Launched in 2026" and "Launched 2mo ago" on 2026-10-12 — [Product Hunt](https://www.producthunt.com/products/kihub)
- Review platform for KiCad projects on GitHub. "KiCad stays the editor, and GitHub stays the source of truth." A repo-scoped GitHub App opens a KiHub review per PR, and results flow back through GitHub Checks. It can compare any two branches/tags/commits without a PR. It can post one summary comment on a PR and cannot change repo files — [kihub.dev](https://kihub.dev/)
- Features: visual and semantic schematic/PCB diffs (base/head, layer and object filters), checks (ERC, DRC, schematic-to-PCB parity, BOM completeness, project policy) that can be informational or required merge gates, pinned threaded comments on a schematic sheet or PCB location with resolution state, an audit trail, BOM-change review, release readiness, and read-only links for outside reviewers — [kihub.dev](https://kihub.dev/); [Product Hunt](https://www.producthunt.com/products/kihub)
- Pricing: **Open Source plan free for public repositories**. **Team plan for private repos $24/contributor/month, or $19 billed annually**. Reviewers and read-only guests are free and unlimited. The page mentions no education tier, no self-hosting, and no 3D viewer — [kihub.dev](https://kihub.dev/)
- KiCad versions: "modern .kicad_sch/.kicad_pcb". Legacy or mixed-version projects need contact with the vendor — [kihub.dev](https://kihub.dev/)
- Public demo gallery of read-only reviews of public KiCad projects: https://app.kihub.dev/demos — [Product Hunt](https://www.producthunt.com/products/kihub)

**AllSpice Hub (allspice.io), Gitea-based**
- The current pricing page lists **enterprise tiers only**: Enterprise Core "starting at $34,800/year" (5+ designers, unlimited collaborators, API, DRCY AI credits, SSO, SOC 2 Type II), plus Premier, Strategic, and Self-Hosted at contact-sales. No free plan and no nonprofit or open-source discount are listed. The FAQ says **"robotics and electrical engineering clubs and students can get set up by scheduling time with the team"**, with no price given — [AllSpice pricing](https://allspice.io/pricing)
- Features: automatic side-by-side visual diffs of schematics, layouts, and BOMs. Supported formats are KiCad, Altium, and OrCAD, with Mentor, System Capture, and Allegro "on the way". Free, unlimited access for collaborators (firmware, mechanical, managers) — [AllSpice features](https://allspice.io/features); [allspice.io llms.txt](https://www.allspice.io/llms.txt)
- "Quick Review" diffs two design revisions without git — [AllSpice Quick Review](https://learn.allspice.io/docs/quick-review)
- A redesigned Design Review page shipped as "version one". "List of changes in a diff", hierarchical project view, and better comments are listed as future enhancements — [AllSpice New Design Review Experience](https://learn.allspice.io/new-design-review-experience)
- Demo hub includes a KiCad Arduino UNO clone — [hub.allspice.io demos](https://hub.allspice.io/AllSpice-Demos?page=2)
- Community description: "mostly a GitHub for KiCad/Altium that provided an interface for pull requests and issues and diffs" — [KiCad forum (Prism thread p.2)](https://forum.kicad.info/t/kicad-prism-a-self-hosted-web-based-platform-for-design-reviews-visualization/66518?page=2)

**CADLAB.io**
- Pricing (excl. tax): **Open Source $0** (public projects, plus 3 private projects with 1 collaborator and up to 10 schematics/layouts). **Pro $8/month annual ($10 monthly)**. **Team $9/user/month annual ($12 monthly)**. Self-hosted and Enterprise are contact-sales. No separate education plan — [CADLAB pricing](https://cadlab.io/pricing)
- Supports Altium Designer, KiCad, and Autodesk Eagle on all plans, with KiCad versions unspecified. Features: visual schematic/layout diff, interactive annotations (comments), merge requests, and integrations with cloud and self-hosted GitLab, GitHub Enterprise, Bitbucket Data Center, and Gitea — [CADLAB pricing](https://cadlab.io/pricing)
- Scans a git repo for KiCad schematic/board files and renders them. The KiCad launch blog post (undated, probably old) says schematic rendering depended on the `-cache.lib` file, which is a KiCad 5-era mechanism — [CADLAB blog](https://cadlab.io/blog/visual-version-control-kicad-officially-released)
- Git-based PCB collaboration company founded 2016 in Riga, Latvia — [CB Insights](https://www.cbinsights.com/compare/cadlabio-vs-silsync)

**KiCAD Prism (open source, self-hosted)**
- Announced on the KiCad forum on 2026-01-22. First Docker release v0.1.0-alpha on 2026-01-29. Built to replicate Altium Workspace features for KiCad — [KiCad forum](https://forum.kicad.info/t/kicad-prism-a-self-hosted-web-based-platform-for-design-reviews-visualization/66518)
- Current repo: **Apache-2.0**, about 295 stars. Stack: React frontend behind Nginx, FastAPI backend, workers for project/compare/visualization/jobset and catalog tasks, PostgreSQL. It credits ecad-viewer, KiCanvas, kicad-monkey, and iBOM. Features: import from SSH/HTTPS git remotes (monorepos supported); browse schematic, PCB, 3D, BOM, stackup, assembly views, and history; compare commits; discussions; run KiCad jobsets; component library approval/release with KLC gates and a Remote Symbol Provider; OIDC SSO and roles. `dev` branch is heading to V3.0.0-alpha. Linux AMD64 only (no ARM64 images) — [GitHub KiCAD-Prism](https://github.com/krishna-swaroop/KiCAD-Prism)
- Early design per the forum: visual diffs snapshot an older commit and run kicad-cli to produce SVGs (needs KiCad ≥7). Comments are pinned to schematic/layout locations and stored in a `comments.json` in a hidden folder in the repo, so they are version-controlled. Google login can be disabled — [KiCad forum](https://forum.kicad.info/t/kicad-prism-a-self-hosted-web-based-platform-for-design-reviews-visualization/66518)

**Altium 365 / Altium Viewer**
- Altium 365 Viewer formats: Altium, EAGLE, Gerber RS-274X/X2, ODB++, and **"KiCad (in Beta)"** (.pro, .sch, .kicad_pcb, .lib). Features: schematic/PCB/3D/BOM, cross-probing, embed HTML snippet, assembly stepping, measurements, Gerber Compare, save to Personal Space — [Altium Viewer](https://www.altium.com/altium-365/viewer)
- A KiCad zip must contain a single project — [Altium standalone viewer docs (IT)](https://www.altium.com/it/documentation/altium-365/viewers/standalone-viewer?version=4)
- NextPCB (a competitor) tested it: KiCad 9 files did not render correctly until uploaded to Personal Space (account needed). It was slower and less interactive than other options, share links expire after 48 h, and the embed link for KiCad was not found. BOM extraction has real-time pricing and comments — [NextPCB blog, updated Jun 2026](https://www.nextpcb.com/blog/top-online-kicad-viewers)
- Altium Designer has a separate KiCad **importer** that converts to Altium files. It is a desktop extension, not part of the viewer — [Altium docs](https://altium.com/jp/documentation/altium-designer/kicad-import?version=22)
- Education: students get free Altium Designer Pro licenses plus Altium 365 cloud classrooms. Educators get complimentary licenses — [Altium Education](https://www.altium.com:443/education); [Educator Center](https://altium.com/in/education/educators)
- Altium has been owned by Renesas since 2024 — [Wikipedia: Altium](https://en.wikipedia.org/wiki/Altium)

**Flux.ai**
- Plans: Explore, Build, Pro (individual), Teams (per editor/month), Enterprise (custom). The scraped page did not show dollar amounts. There is a 14-day trial. After it, a free account can only view and interact with public projects; editing private projects, exporting, and AI need a paid plan. AI is metered in "Agent Compute Units". No education discount or git integration is listed — [Flux pricing](https://www.flux.ai/pricing)
- Flux does not import full KiCad schematics, only KiCad/Eagle parts and libraries. It has built-in version history, not git — [Flux feedback](https://feedback.flux.ai/bugreports/p/kicadv60-schematic-files-sch-unable-to-import); [Flux part import tutorial](https://www.flux.ai/docs/tutorials/tutorial-add-part-library/tutorial-import-part); [Flux vs KiCad](https://www.flux.ai/p/compare/flux-vs-kicad-comparison)

**EasyEDA Pro / OSHWLab**
- EasyEDA Pro officially imports **KiCad 5.1 and 5.9** only. Copper areas are rebuilt on PCB import and can differ — [EasyEDA Pro docs](https://prodocs.easyeda.com/en/import-export/import-kicad/)
- The reverse direction is also fragile: KiCad 9.0.6's EasyEDA Pro importer broke after an EasyEDA format change. The workaround is export to Altium ASCII and then import — [KiCad GitLab #22239](https://gitlab.com/kicad/code/kicad/-/issues/22239)
- OSHWLab sharing is done via Manage Project > Share — [EasyEDA forum](https://easyeda.com/forum/topic/How-to-make-a-Project-public-and-share-the-links-to-it-9f006513b84b412580910905b0281d20)

**Upverter / CircuitMaker**
- Altium acquired Upverter in 2017 and made it free. The 2018 plan to merge CircuitMaker into Upverter was reversed in 2019 (kept separate, with interoperability) — [BrainStation](https://brainstation.io/magazine/altium-acquires-product-design-software-company-upverter); [PCD&F](https://pcdandf.com/pcdesign/index.php/news-itemid-fix/11997-a-million-users-now-with-altium-upverter-dreams-big)
- CircuitMaker's latest stable release is 2.3.0 (July 1, 2024) — [Wikipedia: CircuitMaker](https://en.wikipedia.org/wiki/CircuitMaker)
- upverter.com returned **HTTP 502** when fetched on 2026-10-12 (single observation, see Gaps)

**Cadence OrCAD X / Zuken**
- OrCAD X has Cadence OnCloud integration for data management and collaboration (2023 launch article) — [Digital Engineering 24/7](https://www.digitalengineering247.com/article/cadence-unveils-next-generation-ai-driven-orcad-x/products)
- A third-party aggregator lists OrCAD X Standard at $1,280/year, a 30-day trial, and a six-month academic trial. Professional and Professional Plus are quote-only — [FitGap](https://us.fitgap.com/products/orcad-x-platform). Not confirmed by Cadence.

**tscircuit / atopile (code-first ecosystems)**
- tscircuit.com is "the official tscircuit website, registry and playground". `tsci publish` pushes packages to registry.tscircuit.com — [npm tscircuit](https://www.npmjs.com/package/tscircuit); [registry.tscircuit.com](https://registry.tscircuit.com/)
- Direct KiCad import into tscircuit.com is "still in development". Footprints and symbols go through kicad-component.tscircuit.com or a CLI converter. tscircuit can export a KiCad library — [tscircuit docs: importing from KiCad](https://docs.tscircuit.com/guides/importing-modules-and-chips/importing-from-kicad); [exporting KiCad library](https://docs.tscircuit.com/guides/kicad/exporting-kicad-library)
- atopile offers a package registry (packages.atopile.io) and a browser workspace (app.atopile.io). The docs describe atopile as pre-release. No layout/3D web viewer is documented there — [atopile docs](https://docs.atopile.io/). Latest PyPI version seen is 0.15.7 — [PyPI Stats](https://pypistats.org/packages/atopile)

**Kitspace**
- Registry of ready-to-order open hardware projects ("we automate parts purchasing"). The project list is live (OpenDosimeter, Glasgow revC3, open-source-rover), but the site shows no dates or news. Project submission is documented in the kitspace-v2 README — [kitspace.org](https://kitspace.org/); [GitHub kitspace](https://github.com/kitspace/kitspace)
- The kitspace kicad_footprints repo was last pushed 2023-01-25 — [ecosyste.ms](https://awesome.ecosyste.ms/projects/122870)

**PCB fab online viewers**
- NextPCB HQDFM online Gerber viewer: converts KiCad PCB to Gerber, runs DFM with a free PDF report and price estimate. No schematic/3D/BOM, no embedding or link-based viewing — [NextPCB blog](https://www.nextpcb.com/blog/top-online-kicad-viewers)
- NextPCB's free online Gerber viewer accepts zipped .kicad_pcb, and one user runs it alongside a self-hosted Gitea — [KiCad forum, Sept 2025](https://forum.kicad.info/t/web-view-of-gerbers-committed-to-a-git-repo/64463)

### Inferences
- For a student/robotics team on GitHub, the best "bought" option is **KiHub's free Open Source tier**, if the repo can be public. For a private repo, CADLAB Pro/Team ($8-12/user/month) or KiHub Team ($19-24/contributor/month) are affordable. AllSpice is now priced for enterprises, so the education route is "schedule a call".
- **KiCAD Prism** is the closest open-source self-hosted Altium 365 equivalent (viewer, 3D, BOM, history diffs, comments, jobsets, library management). It needs a server (Docker Compose with Postgres), so it is not a static site.
- Altium 365 Viewer is fine for one-off sharing but not for a git/CI review loop with KiCad, given beta status, the 48 h links, and the account requirement.
- Flux, EasyEDA Pro, tscircuit, and atopile are alternative design environments, not review layers for an existing KiCad project. Of these, only tscircuit's viewers are useful building blocks (see Q2), and only for tscircuit/Circuit JSON sources.

### Gaps
- AllSpice's exact KiCad 9/10 support and any concrete student/club price were not found. The pricing page omits KiCad and diffs entirely, and the docs URL for KiCad returned 404.
- KiHub's company, self-hosting, and 3D viewer were not stated on its site. KiHub launch date: one search summary said Aug 2026, which matches "2mo ago" on Product Hunt.
- Upverter's current status: the fetch returned 502 and no shutdown announcement was found. This is inconclusive.
- I found no 2026 status for CircuitMaker beyond the July 2024 release.
- Zuken cloud collaboration was not researched (time budget). OrCAD X pricing comes from an aggregator only.
- Flux's actual dollar prices were not visible (JS-rendered).
- PCBWay and JLCPCB online viewers were not specifically verified.
- No KiCad-specific info was found for CADLAB's KiCad 8/9/10 support.

## Q2. Embeddable viewers / building blocks

### Takeaway
A static portal can be assembled from proven pieces:
- **KiCanvas** (MIT, KiCad ≥6, still "early alpha") or its actively maintained fork **ecad-viewer** (MIT, web components, adds 3D, BOM, and Altium) for interactive schematic/PCB
- **InteractiveHtmlBom** (MIT, 4.6k stars) for assembly BOM
- **kicad-cli** GLB export (KiCad ≥9) plus **model-viewer, Three.js, or Online3DViewer** (MIT, also reads STEP/3MF) for 3D
- **KiRI** (MIT) or kicad-cli SVG diffs for visual diffs
- **tracespace** for Gerbers, though it is no longer accepting changes

### Cited Findings
- **KiCanvas**: browser viewer for KiCad schematics and boards, written in TypeScript with Canvas/WebGL, MIT. **"Currently in early alpha."** It parses KiCad 6 and later only (no KiCad 5); some KiCad 7 features such as custom schematic fonts are incomplete. It has an embedding API (kicanvas.org/embedding), about 1,114 commits, 52 open issues, no GitHub releases, and is sponsor-funded — [GitHub kicanvas](https://github.com/theacodes/kicanvas); [hackster](https://hackster.io/news/thea-flowers-kicanvas-lets-you-view-kicad-projects-directly-in-your-browser-c610d16c558e)
- Reports on KiCanvas: "~90% of projects work" (Jan 2025). In Sept 2025 it rendered a GitLab-hosted project, but two other projects failed to load, and it was described as "pre alfa for a few years" — [KiCad forum Jan 2025](https://forum.kicad.info/t/web-viewing-of-kicad-files-2/57374); [KiCad forum Sept 2025](https://forum.kicad.info/t/web-view-of-gerbers-committed-to-a-git-repo/64463). NextPCB says it "only fully supports KiCad 6" and its development "appears stalled" — [NextPCB blog](https://www.nextpcb.com/blog/top-online-kicad-viewers) (a competitor's opinion)
- **ecad-viewer** (Huaqiu/HQ NextPCB fork of KiCanvas), MIT, about 91 stars:
  - PCB/schematic interactivity: net highlighting, symbol properties, sheet switching
  - **3D via Three.js** with models generated by kicad-cli-docker and compressed with gltfpack
  - BOM generated from the schematic, or from the PCB if no schematic is available
  - Altium import via a kicad-cli conversion server
  - Web components `<ecad-viewer>` (with `<ecad-source>`/`<ecad-3d-source>` children) and `<ecad-viewer-embedded url="a;b;c" is-bom="true">`
  - Aims to "maintain support for the latest KiCad file formats"
  - [GitHub ecad-viewer](https://github.com/Huaqiu-Electronics/ecad-viewer)
- NextPCB says ecad-viewer supports KiCad "up to the current release (KiCad 9 as of writing)". Weaknesses: a Chinese domain for the hosted app, some UI text in Chinese, and "pads and traces don't appear" in its 3D view — [NextPCB blog](https://www.nextpcb.com/blog/top-online-kicad-viewers). KiCAD Prism uses ecad-viewer for rendering — [KiCad forum](https://forum.kicad.info/t/kicad-prism-a-self-hosted-web-based-platform-for-design-reviews-visualization/66518)
- **InteractiveHtmlBom**: MIT, about 4.6k stars, supports KiCad, EasyEDA, Eagle, Fusion360, and Allegro. It produces a self-contained offline HTML page — [GitHub iBOM](https://github.com/openscopeproject/InteractiveHtmlBom). It is pip-installable with a `generate_interactive_bom` CLI for CI — [iBOM wiki Usage](https://github.com/openscopeproject/InteractiveHtmlBom/wiki/Usage)
- **KiRI** (KiCad Revision Inspector): MIT, web-based visual diff of schematic and layout across git commits. It steps through pages and layers with keyboard shortcuts. "Supports KiCad >= 5" (kicad-cli for KiCad 7+ schematics; layouts via Kicad-Diff/pcbnew Python). Repo tags include kicad-8, kicad-9, and kicad-10. Output can be archived as .tgz and served with `kiri-server` — [GitHub KiRI](https://github.com/leoheck/kiri)
- KiBot wraps KiRI as an output. It needs a web server (browsers block JS reading local files), and the CI checkout needs `fetch-depth: 0` — [KiBot KiRI output](https://kibot.readthedocs.io/en/latest/configuration/outputs/kiri.html); [KiBot CI/CD](https://kibot.readthedocs.io/en/v1.8.0/usage_with_ci_cd.html)
- KiBot also has a `kicanvas` output, an alpha HTML page that needs a web server — [KiBot kicanvas output](https://kibot.readthedocs.io/en/latest/configuration/outputs/kicanvas.html). KiBot's changelog lists "KiRi: interactive diff; KiCanvas: on-line schematic/PCB browser" as outputs — [safetycli KiBot changelog](https://data.safetycli.com/changelogs/kibot/)
- **3D export**: KiBot's `export_3d` output produces STEP, STL, XAO, BRep, and **GLB** via kicad-cli with **KiCad 9 or newer** — [KiBot export_3d](https://kibot.readthedocs.io/en/latest/configuration/outputs/export_3d.html)
- **KiCad 10.0.0** was released 2026-03-20: design variants, track-tuning overhaul, Allegro/PADS/gEDA importers. **3D libraries now ship STEP only, and VRML was dropped** — [KiCad blog](https://www.kicad.org/blog/2026/03/Version-10.0.0-Released/); [alternativeto](https://alternativeto.net/news/2026/3/kicad-10-released-with-track-tuning-revamp-windows-dark-mode-design-variants-and-more). KiBot added kicad-cli support for KiCad 10 "with various limitations" — [KiBot changelog v1.9.1](https://kibot.readthedocs.io/en/v1.9.1/Changelog.html)
- **Online3DViewer**: MIT, about 3.7k stars, npm `online-3d-viewer`. Imports STEP, 3MF, glTF, and more, so it can show both kicad-cli GLB and build123d/CadQuery STEP — [GitHub Online3DViewer](https://github.com/kovacsv/Online3DViewer)
- **tscircuit viewers** (React):
  - `@tscircuit/pcb-viewer`, which takes components or Circuit JSON — [pcb-viewer](https://github.com/tscircuit/pcb-viewer/wiki)
  - `@tscircuit/schematic-viewer` 2.x — [schematic-viewer](https://redirect.github.com/tscircuit/schematic-viewer)
  - `@tscircuit/3d-viewer` (`CadViewer`), with a vanilla Three.js rewrite in progress — [3d-viewer README mirror](https://ithub.global.ssl.fastly.net/tscircuit/3d-viewer); [tscircuit blog](https://blog.tscircuit.com/p/tscircuit-now-supports-a-3d-view)
  - All consume tscircuit/Circuit JSON, not KiCad files
- **tracespace view**: the Gerber viewer "appears no longer to be accepting any changes" (Sept 2025). It cannot follow GitHub raw 302 redirects — [KiCad forum](https://forum.kicad.info/t/web-view-of-gerbers-committed-to-a-git-repo/64463)
- Other viewers:
  - cho45 KiCad viewer: multi-file view and a library viewer, "ymmv" — [KiCad forum](https://forum.kicad.info/t/web-view-of-gerbers-committed-to-a-git-repo/64463)
  - eda.cn ecadViewer, the hosted ecad-viewer — [KiCad forum](https://forum.kicad.info/t/web-view-of-gerbers-committed-to-a-git-repo/64463)
  - STEMN, a historical tool, "likely no longer exists" — [KiCad forum](https://forum.kicad.info/t/web-viewing-of-kicad-files-2/57374)
- **giscus**: comments backed by GitHub Discussions, free, no database. Maps a page to a discussion by pathname/URL/title/term. Requires a **public** repo, the giscus app installed, and Discussions enabled. Can be self-hosted — [giscus.app](https://giscus.app/)

### Inferences
- For KiCad 9/10 files, **ecad-viewer is the safer interactive viewer** than upstream KiCanvas: it targets the latest formats, adds 3D and BOM, and is battle-tested inside Prism. Test against your own boards; KiCanvas may still choke on newer features (e.g. KiCad 10 variants or jumpers). Keep a kicad-cli PDF/SVG export as a fallback in all cases.
- **One 3D viewer for both PCB and mechanical:** KiCad 10 libraries are STEP-only, and build123d/CadQuery export STEP/GLB natively. A single Three.js/model-viewer/Online3DViewer page can show the PCB GLB inside the enclosure GLB, which no hosted ECAD platform found here does across ECAD and MCAD.
- Pixel diffs from kicad-cli SVGs (KiRI style) are reliable and static-hostable. Semantic "object-level" diffs (KiHub, AllSpice) are the main thing a DIY build would lack, unless you add a netlist/BOM JSON diff.

### Gaps
- KiCanvas's latest commit date and KiCad 9/10 parse coverage were not verifiable from the repo page.
- ecad-viewer's last-activity date was not visible.
- I did not verify the exact `kicad-cli pcb export glb` flags or the KiCad 10 kicad-cli changes. The KiBot docs confirm GLB with KiCad ≥9.
- Google `<model-viewer>` and 3dviewer.net were not separately fetched. Online3DViewer is the engine behind 3dviewer.net (known from training data, not verified this session).

## Q3. Examples of CI-published design portals (GitHub Pages + KiBot / KiRI / iBOM / 3D)

### Takeaway
Yes, this exists. **hugo-kicad-site** (laenzlinger) is a Hugo theme that turns KiBot CI outputs into a GitHub Pages portal:
- KiCanvas schematic/PCB, a 3D render gallery, and iBOM
- schematic/PCB and PDF diffs per release, and an interactive STEP/GLB assembly viewer
- downloads and a version picker across tagged releases

The real project **Granit** uses it. KiBot's `navigate_results` gives a simpler auto-index of all outputs. The **KDT_Hierarchical_KiBot** template is the go-to KiCad 8/9 CI template.

### Cited Findings
- KiBot "Examples and resources" lists:
  - **KDT_Hierarchical_KiBot**, a KiCad 8/9 CI/CD template — https://github.com/nguyen-v/KDT_Hierarchical_KiBot
  - the **Spora CI/CD** example — https://github.com/INTI-CMNB/kicad-ci-test-spora
  - the Λmulet controller — https://github.com/nguyen-v/amulet_controller_kibot
  - the 3devo KiBot+Actions discussion, the sschueller GitLab CI blog, **KiCi** (an opinionated GitLab CI include), and the **Hugo KiCad theme** with live demo and the Granit project
  - [KiBot examples & resources](https://kibot.readthedocs.io/en/latest/examples_and_resources.html)
- hugo-kicad-site demo layout:
  - **Board**: embedded KiCanvas schematic/PCB, 3D render gallery, interactive BOM
  - **Release**: downloads, schematic and PCB diffs, GitHub release link
  - **Assembly**: interactive 3D viewer for STEP/GLB
  - Design Notes
  - Custom Composition, with `call-partial` shortcodes for KiCanvas, gallery, iBOM, assembly, BOM, diffs, PDF diffs, and downloads
  - a link to raw KiBot outputs, a version picker for tagged releases, light/dark theme, and Ctrl-K search
  - [hugo-kicad-site demo](https://laenzlinger.github.io/hugo-kicad-site/latest/); [Granit](https://laenzlinger.github.io/granit/latest/); [repo](https://github.com/laenzlinger/hugo-kicad-site)
- KiBot `navigate_results` generates "a web page for navigating the outputs KiBot has produced", organized by each output's `category` (e.g. `PCB/fabrication/gerber`). A `navigate_results_rb` variant also exists — [KiBot navigate_results](https://kibot.readthedocs.io/en/latest/configuration/outputs/navigate_results.html)
- KiBot CI docs show a GitHub Actions workflow that uploads outputs as artifacts. Docker images are on GitHub Packages, and "full" variants include Blender for 3D renders — [KiBot CI/CD](https://kibot.readthedocs.io/en/latest/usage_with_ci_cd.html)
- A KiCad forum post says KiBot can generate KiCanvas browsing pages and cites the Spora demo — [KiCad forum KiBot thread](https://forum.kicad.info/t/kibot-fabrication-and-documentation-automation/24705)
- The krsche/kicad-template uses KiBot GitHub workflows (gerbers, PDFs, renders) and creates a GitHub Release with the outputs — [kicad-template](https://github-redirect.dependabot.com/krsche/kicad-template)
- KiKit `present` builds a project presentation page from a template — [KiBot KiKit_PresentOptions](https://kibot.readthedocs.io/en/latest/configuration/outputs/KiKit_PresentOptions.html)
- iBOM HTML must be served via GitHub Pages (raw repo view only shows text) — [KiCad forum iBOM thread](https://forum.kicad.info/t/interactive-html-bom-plugin-for-kicad/11713)

### Inferences
- Starting from **KDT_Hierarchical_KiBot (CI) + hugo-kicad-site (presentation)** probably covers about 70% of an "Altium 365-lite" for free. The missing pieces are per-PR previews, comments, live pricing, and MCAD/firmware integration.

### Gaps
- I did not verify that hugo-kicad-site supports KiCad 10 or per-PR (not just per-tag) builds.
- The Spora and KDT sites' live Pages URLs were not fetched.

## Q4. Self-built portal: architecture, stack, effort

### Takeaway
A **static site built in CI and deployed to GitHub Pages** (or Cloudflare Pages for per-PR preview URLs) is feasible and cheap. The suggested stack:
- KiBot (in its Docker image) for all KiCad outputs
- kicad-cli SVG/KiRI for diffs
- ecad-viewer or KiCanvas for interactive viewing
- iBOM for BOM
- GLB from kicad-cli plus build123d/CadQuery GLB in one Three.js/model-viewer scene
- MkDocs-Material or Hugo (hugo-kicad-site) as the shell, with firmware docs (Doxygen/Sphinx) mounted under `/firmware`
- giscus or GitHub PR comments for discussion

Live BOM pricing is the only part that needs a runtime backend: a scheduled CI job with Octopart/Nexar or distributor APIs, or a tiny serverless proxy. Estimate: about 1 week for a working MVP from existing templates, and 3-6 weeks for a polished multi-board, per-PR, diff-aware portal. These are my estimates, not sourced figures.

### Cited Findings (building blocks with verified properties)
- KiBot runs in CI on every commit. Its Docker images include Blender for renders. It provides KiRI, KiCanvas, navigate_results, iBOM, export_3d (GLB with KiCad ≥9), BOM, diff, and more — [KiBot CI/CD](https://kibot.readthedocs.io/en/latest/usage_with_ci_cd.html); [export_3d](https://kibot.readthedocs.io/en/latest/configuration/outputs/export_3d.html)
- Diff outputs need full git history (`fetch-depth: 0`) and a web server for KiRI/KiCanvas pages. GitHub Pages satisfies the latter — [KiBot KiRI output](https://kibot.readthedocs.io/en/latest/configuration/outputs/kiri.html)
- Prism's diff approach: check out the older commit and run kicad-cli SVG export per sheet/layer (KiCad ≥7) — [KiCad forum](https://forum.kicad.info/t/kicad-prism-a-self-hosted-web-based-platform-for-design-reviews-visualization/66518)
- Prism's comment approach: pinned comments stored in a JSON file in the repo, so they are version-controlled — [KiCad forum](https://forum.kicad.info/t/kicad-prism-a-self-hosted-web-based-platform-for-design-reviews-visualization/66518)
- giscus gives free, DB-less comments in GitHub Discussions but **requires a public repo** — [giscus.app](https://giscus.app/)
- ecad-viewer web components can be dropped into any static page and accept multiple files plus 3D sources — [GitHub ecad-viewer](https://github.com/Huaqiu-Electronics/ecad-viewer)
- Online3DViewer (MIT) reads STEP/glTF/3MF, which covers both KiCad and build123d/CadQuery outputs — [GitHub Online3DViewer](https://github.com/kovacsv/Online3DViewer)
- The DIY ceiling to compare against: KiHub provides semantic diffs, merge-gating checks, and pinned comments for $0 on public repos — [kihub.dev](https://kihub.dev/). KiCAD Prism provides a full self-hosted app (React/FastAPI/Postgres) under Apache-2.0 — [GitHub KiCAD-Prism](https://github.com/krishna-swaroop/KiCAD-Prism)

### Inferences (proposed architecture, my synthesis)
1. **Triggers.** GitHub Actions runs on push to main or a tag (release site) and on `pull_request` (preview site). It uses the KiBot Docker image pinned to the KiCad version in use (9 or 10), with `fetch-depth: 0`.
2. **ECAD job (KiBot):**
   - ERC/DRC reports (HTML/JSON)
   - schematic PDF/SVG and per-layer PCB SVG
   - iBOM, BOM CSV/JSON, Gerbers/drill/CPL zip, STEP and GLB, Blender renders
   - KiRI diff vs. merge-base (on PRs) or vs. the previous tag (on releases)
   - optional SPICE/ngspice reports as HTML
3. **MCAD job.** build123d/CadQuery scripts export STEP and GLB. The PCB GLB is positioned in the enclosure assembly, and both are rendered in one Three.js/`<model-viewer>`/Online3DViewer page.
4. **Firmware job.** Doxygen/Sphinx/mkdocstrings HTML goes under `/firmware/`, plus build artifacts and size reports.
5. **Site assembly.** Use Hugo with hugo-kicad-site, or MkDocs-Material with custom pages. Pages: Board (ecad-viewer/KiCanvas embed), BOM (iBOM plus a table), 3D (combined ECAD+MCAD), Diffs (KiRI), Reports (ERC/DRC/sim), Firmware, Releases (artifact zips linked to GitHub Releases), with a version switcher over `/<tag>/`, `/main/`, `/pr-<n>/`.
6. **Hosting.** GitHub Pages serves one site per repo. For per-PR previews, either push into `gh-pages` subfolders (`/pr-123/`) and clean up on PR close, or use Cloudflare Pages/Netlify preview deployments. A bot comment on the PR links to the preview and embeds the diff PNGs.
7. **Comments.** For public repos, giscus per page, keyed by pathname. For private repos, discussion stays in the GitHub PR (inline review on generated diff images posted by the bot). Prism-style pinned comments are an optional stretch: a JSON file in the repo rendered as overlays.
8. **Live BOM pricing.** A nightly scheduled workflow queries distributor APIs (Nexar/Octopart, DigiKey, Mouser, LCSC) and commits or deploys a `pricing.json` that the static BOM page reads. This keeps API keys in CI secrets with no runtime backend.
9. **Effort (rough):**
   - MVP from KDT template + hugo-kicad-site: about 3-5 dev-days
   - adding PR previews, a PR bot comment, and KiRI diffs: about 1 week
   - a combined ECAD+MCAD 3D scene, firmware docs, and pricing job: about 1-2 weeks
   - polish (multi-board monorepo, version switcher, KiCad 10 quirks): about 1-2 weeks
   - total about 3-6 person-weeks for a polished system; ongoing maintenance is mostly tracking KiCad/KiBot version bumps
10. **Recommendation.** Build the static portal for publishing and releases, because it unifies ECAD, MCAD, and firmware, which no vendor does. For review-time semantic diffs and merge gates, consider adding KiHub (free if the repo is public), or self-hosting KiCAD Prism if the repo must stay private and a server is available, rather than rebuilding those features.

### Gaps
- No sourced effort figures exist for building such portals; the estimates above are my own judgement.
- I did not verify GitHub Pages limits (site size, build minutes) or the Cloudflare Pages free-tier preview limits this session.
- I did not verify current Nexar/Octopart free-tier API quotas for live pricing.
- No public example was found that combines KiCad and build123d/CadQuery MCAD in one CI-generated site. This appears novel, but absence is not proof.
