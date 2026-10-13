# Circuit and board-level simulation as code / in CI for a micromouse PCB (as of October 2026)

Scope: STM32 micromouse board (H-bridge motor drivers, MOSFET-pulsed IR emitters, phototransistor/photodiode + op-amp AFE, LiPo + buck/LDO, battery divider, IMU, encoders). Focus on open-source, Linux/WSL2 and CI-friendly tools. Research done 2026-10-12 with a limited tool budget (~17 searches/fetches); several sub-questions are only partly sourced and flagged in Gaps.

## SPICE engines and Python wrappers: what is maintained in 2026?

### Takeaway
ngspice is the clear default: it shipped release 46 (March 2026) and 47 (August 2026), is packaged in every Linux distro, and is what KiCad embeds. Xyce (7.10, Aug 2025) is a solid second engine. For Python glue, spicelib (1.6.x, active in 2026) is the best-maintained multi-engine wrapper; original PySpice is effectively stalled (last production release 2021) and InSpice is a 2025 fork that keeps the PySpice API alive.

### Cited Findings
- ngspice 47 released 2026-08-11: adds a `pyplot` command (plot via Python matplotlib), soft-recovery model for VDMOS power transistors, .wav I/O, small-signal noise for code models, updated PSS analysis — [ngspice news](https://ngspice.sourceforge.io/news.html)
- ngspice 46 released 2026-03-29: new `vec()`/`var()` functions, diode soft-recovery model, voltage-based truncation error correction, better FFT in `linearize`, CIDER enabled for KLU solver — [ngspice news](https://ngspice.sourceforge.io/news.html)
- ngspice 45 (2025-09-01, bug-fix 45.2 on 2025-09-06): `d_cosim` code model supports VHDL via GHDL for mixed-signal co-simulation; BSIM 4.8.3; `save nointernals` — [ngspice news](https://ngspice.sourceforge.io/news.html); [Debian NEWS 45.2](https://sources.debian.org/src/ngspice/45.2%2Bds-1/NEWS)
- ngspice 44 (2024-12-29): `d_cosim` supports Icarus Verilog; new shared-library API functions to reset ngspice or skip `.spiceinit` — [ngspice news](https://ngspice.sourceforge.io/news.html)
- KiCad 9.0.4+ testing builds were linked to ngspice 45.2 (i.e., KiCad embeds ngspice as a shared library and tracks recent releases) — [KiCad forum](https://forum.kicad.info/t/heads-up-testing-commit-91-now-uses-ngspice-45-2/63997)
- Xyce latest listed release is 7.10 (August 2025); previous 7.9 (Jan 2025). Xyce has had `.SAMPLING` Monte Carlo / Latin Hypercube since 6.10, S-parameter analysis since 6.11, `.NOISE` since 6.3, and an XDM translator for HSPICE/PSpice netlists since 7.0 — [Xyce news](https://xyce.sandia.gov/news/)
- PySpice: last production release V1.5.0 (2021-05-15), "supports Ngspice up to version 34"; author describes it as free-time maintained; Discourse forum closed for inactivity — [PySpice GitHub](https://github.com/PySpice-org/PySpice)
- InSpice: fork of PySpice by Innovoltive ("modified ... April 18, 2025"), `pip install inspice`, requires Python >= 3.12 and ngspice shared lib; supports ngspice and Xyce and shows a VACASK backend example — [InSpice GitHub](https://github.com/Innovoltive/InSpice)
- spicelib: version 1.6.4; supports LTspice (Windows/macOS native, Linux via wine), ngspice (CLI, not shared lib), QSPICE (Windows; Linux support noted as added in 1.6.4), Xyce; features SimRunner (parallel batch runs), SpiceEditor/AscEditor/QschEditor to programmatically edit netlists/schematics, Monte Carlo and worst-case analysis toolkit, RawRead for .raw files, CLI tools (ltsteps, histogram, raw_convert, rawplot, run_server) — [spicelib GitHub](https://github.com/nunobrum/spicelib); last push May 2026 per [GitTrend](https://gittrend.io/repo/nunobrum/spicelib); docs [spicelib.readthedocs.io](https://spicelib.readthedocs.io)
- PyLTSpice is now a front-end over spicelib that auto-selects LTspice — [PyPI pyltspice](https://pypi.org/project/pyltspice); [spicelib GitHub](https://github.com/nunobrum/spicelib)
- LTspice batch mode: `-b` runs in batch mode; `-Run` starts simulating a schematic opened on the command line — [spicelib LTspice simulator docs](https://spicelib.readthedocs.io/en/latest/classes/ltspice_simulator.html). The mcltspice project reports running LTspice headless under wine on Linux as its "mature" path, and that native macOS LTspice lacked command-line switches (later commit contradicts this partially) — [mcltspice repo](https://git.supported.systems/MCP/mcltspice/src/branch/macos-port/README.md)
- SKiDL 2.2.0 (2025-11-09) release notes mention SPICE netlist fixes for XSPICE components; SKiDL simulation requires separately installing PySpice — [PyPI skidl](https://pypi.org/project/skidl/); [baldengineer](https://www.baldengineer.com/?p=7907)
- circuit-synth's setup guide warns that PySpice may not recognize newer ngspice versions — [circuit-synth docs](https://circuit-synth.readthedocs.io/en/latest/SIMULATION_SETUP.html)

### Inferences
- For CI on Linux, the lowest-friction stack is: `apt install ngspice` (or a pinned container) + plain subprocess `ngspice -b` + a raw-file reader (spicelib's RawRead), or spicelib's SimRunner end to end. This avoids PySpice's shared-library version coupling.
- LTspice in CI is possible (wine + `-b`) but adds a wine layer and LTspice is freeware with a license that is not open-source; treat it as optional, useful mainly because ADI ships many models in LTspice format. QSPICE is Windows-centric; skip for CI.
- Xyce is worth having as a second engine only if you hit convergence problems or want `.SAMPLING`-based Monte Carlo natively; most micromouse circuits are tiny and ngspice is sufficient.
- InSpice is the choice if you want PySpice-style "circuit in Python objects" with a current ngspice; otherwise write netlists as text templates (Jinja/f-strings) which is simpler and diff-friendly.

### Gaps
- ahkab: not researched (no search budget); by training knowledge it has had no meaningful activity for years — treat as unmaintained, unverified for 2026.
- QSPICE licensing/Linux status beyond spicelib's note not verified.
- Exact LTspice license terms for CI use not verified.
- InSpice's latest PyPI version number and 2026 activity not confirmed.

## Simulating from KiCad schematics and code-first tools (KiCad, kicad-cli, atopile, tscircuit, SKiDL, kicad-happy)

### Takeaway
KiCad's GUI simulator embeds ngspice, but kicad-cli does not run simulations; the CI path is `kicad-cli sch export netlist --format spice` then run ngspice yourself (simulation directives placed on the schematic are carried in the netlist). tscircuit has a first-class `tsci simulate analog` CLI (ngspice or its own "spicey" engine); atopile simulation support was not confirmed. The installed kicad-happy `spice` skill auto-generates testbenches from KiCad schematic analysis, with Monte Carlo, and is a ready-made "lint by simulation" layer.

### Cited Findings
- kicad-cli can export a SPICE netlist (`kicad-cli sch netlist --format spice`, in newer versions under `sch export netlist`), which "in theory" includes the simulation command, but ngspice must be run manually; forum answer says ngspice cannot be driven from kicad-cli — [KiCad forum: Execute NGSpice by kicad-cli](https://forum.kicad.info/t/execute-ngspice-by-kicad-cli/44358)
- KiCad integrates ngspice and offers standard simulation modes (AC sweep, DC transfer, operating point, transient) — [kicad.org/discover/spice](https://kicad.org/discover/spice)
- In KiCad 10 the old `pspice` symbol library no longer exists; SPICE-specific symbols live in `Simulation_SPICE` — [KiCad forum: KiCad 10.0 pspice?](https://forum.kicad.info/t/kicad-10-0-pspice/68075)
- KiCad 10.0.6 has been released (no simulator details given) — [warp2search](https://www.warp2search.net/story/kicad-1006-released/)
- A forum user published a modified ngspice build for KiCad with adaptive timestep and solver selection; this is an individual's fork, not official — [KiCad forum](https://forum.kicad.info/t/a-new-features-that-completly-changes-simulation-experience/70885)
- tscircuit: analog simulation component with `spiceEngine` = "spicey" (default) or "ngspice", duration/timePerStep, sources with dc/sine/square/triangle, probes that do not appear on the PCB; `tsci simulate analog` generates a netlist, runs it, prints a results table — [tscircuit SPICE intro](https://docs.tscircuit.com/guides/spice-simulation/introduction); [tsci simulate](https://docs.tscircuit.com/command-line/tsci-simulate)
- kicad-happy `spice` skill (v2.2.1 installed locally): reads `analyze_schematic.py` JSON, generates testbenches for RC/LC filters, dividers, op-amp circuits (per-part behavioral models for ~100 op-amps, else ideal Aol=1e6/GBW 10 MHz), feedback networks/regulator Vout, transistor circuits (generic FET/BJT, "medium" trust), decoupling/PDN impedance, crystals; supports ngspice/LTspice/Xyce auto-detected; stdlib-only Python; Monte Carlo via `--monte-carlo N` with tolerances parsed from value strings (defaults R 5%, C 10%, L 20%) and sensitivity ranking; outputs pass/warn/fail JSON; explicitly skips comparators, regulator loop stability, level shifters — local file `/home/cosme/.claude/plugins/cache/kicad-happy/kicad-happy/2.2.1/skills/spice/SKILL.md`
- The kicad-happy `emc` skill reuses the spice backend for PDN impedance and EMI filter insertion loss (`--spice-enhanced`) — same local SKILL.md
- SKiDL can perform SPICE simulation via PySpice (separate install) — [PyPI skidl](https://pypi.org/project/skidl/)

### Inferences
- Recommended KiCad flow for CI: keep "simulation testbench" sheets or separate small `.kicad_sch` files per subcircuit (IR emitter driver, receiver AFE, battery divider + ADC RC, buck feedback), with `Sim.*` fields on symbols; CI runs `kicad-cli sch export netlist --format spice` and a Python harness appends `.meas`/analysis cards and asserts results. This keeps the simulated circuit identical to the production schematic.
- Alternative (more robust, less coupled): hand-maintained `.cir` testbenches that `.include` part models, with values pulled from the KiCad BOM/netlist by script, so a value change in the schematic propagates to tests.
- kicad-happy's spice skill is a good zero-effort first gate (dividers, filters, op-amp gain/bandwidth) but does not cover the micromouse-critical transient behaviors (IR pulse current/rise time with real MOSFET + LED models, H-bridge dynamics); those need custom testbenches.
- Code-first tools (tscircuit, SKiDL) only make sense if the schematic itself is authored there; for a KiCad project they add a second source of truth.

### Gaps
- No official KiCad 10 release notes on simulator changes were retrieved (element14 KiCad 10 SPICE article fetch timed out). Whether KiCad 10's kicad-cli gained any `sim` subcommand was not confirmed; the forum evidence (older) says no.
- atopile: no source found on SPICE simulation support as of 2026.
- InSpice/SKiDL 2.x integration not confirmed.

## Vendor SPICE model availability and encryption (TI, ADI, onsemi, Vishay, DRV8833/TB6612), IBIS

### Takeaway
Discrete parts (MOSFETs, IR LEDs, phototransistors, op-amps) usually have usable unencrypted models; integrated motor drivers like DRV8833 typically have no SPICE model at all, and encrypted PSpice models cannot be used in ngspice. Plan on behavioral models for the motor driver and regulators, and real vendor models for discretes and op-amps.

### Cited Findings
- ngspice docs: PSpice, HSPICE and many LTspice models are generally compatible, but encrypted commercial vendor models cannot be used by open-source ngspice — [ngspice model parameters page](https://ngspice.sourceforge.io/modelparams.html)
- KiCad forum: encrypted PSpice models cannot be decrypted by ngspice; they work only in Cadence-compatible tools (OrCAD, PSpice for TI, TINA) — this is a forum claim — [KiCad forum: Encrypted PSpice models](https://forum.kicad.info/t/encrypted-pspice-models/60243); [KiCad forum: PSpice/ngspice/LTspice](https://forum.kicad.info/t/simulations-pspice-ngspice-and-ltspice/15230)
- A TI E2E reply (machine-translated) says no model, encrypted or not, is available for DRV8833 — [TI E2E China](https://e2echina.ti.com/support/machine-translation/mt-motor-drivers/f/mt-motor-drivers-forum/252638/drv8833-drv8833-pspice); an older forum post suggests adapting the related DRV8832 PSpice model — [All About Circuits](https://forum.allaboutcircuits.com/threads/ic-spice.108799/)
- TI also lacks SPICE models for some power parts (e.g., TPS543820E thread) — [TI E2E](https://e2e.ti.com/support/tools/simulation-hardware-system-design-tools-group/sim-hw-system-design/f/simulation-hardware-system-design-tools-forum/1418116/tps543820e-spice-simulation-model-is-not-available)
- Community TI PSpice library dumps for KiCad exist (updated Dec 2023) — [KiCad forum](https://forum.kicad.info/t/pspice-ti-spice-library-files-updated-12-14-23/46860)
- A Debian package "spice-crypt" claims to decrypt lawfully obtained encrypted models for use in ngspice/PySpice (unverified; legal/license implications per vendor EULA) — [Debian tracker](https://tracker.debian.org/media/packages/s/spice-crypt/control-3.0.3-3)
- ngspice 46/47 added diode and VDMOS soft-recovery models, relevant to MOSFET/body-diode behavior in H-bridges — [ngspice news](https://ngspice.sourceforge.io/news.html)

### Inferences
- Commit vendor model files into the repo (`sim/models/`) with source URL + retrieval date + license note, so CI is hermetic. Check licenses before committing to a public repo.
- For the H-bridge: model DRV8833/TB6612 as behavioral switches with Rds(on) from the datasheet (+ dead time, current limit) or as two MOSFET half-bridges using a VDMOS model; the motor as R-L-backEMF. This is enough to check ripple current, decoupling ripple and bulk-cap sizing.
- For regulators without models: use averaged behavioral models (ideal source + output impedance + current limit), or build from the vendor's LTspice model if ADI makes the part (LTspice models are often plain-text).
- IBIS (STM32 GPIO IBIS from ST) is only relevant for fast-edge SI; ngspice cannot read IBIS natively (training knowledge, unverified here) — low priority for a micromouse.

### Gaps
- Did not verify current TI/onsemi/Vishay/ADI model page formats or Toshiba TB6612 model availability.
- IBIS-to-SPICE converters (e.g., KiCad's own IBIS support) not researched.

## Writing simulation tests (pytest patterns, assertions, Monte Carlo, regression, CI artifacts)

### Takeaway
Standard pattern: text netlist templates + `.meas` statements + ngspice batch run + parse results in pytest, with tolerance-band assertions and Monte Carlo/worst-case loops; publish plots/CSV as CI artifacts. spicelib provides most of the plumbing (parallel runs, raw parsing, MC/WC toolkit); kicad-happy shows a ready JSON pass/warn/fail report format.

### Cited Findings
- spicelib provides SimRunner for parallel batch runs, RawRead for waveform files, editors to change component values programmatically, and a Monte Carlo / worst-case analysis toolkit — [spicelib GitHub](https://github.com/nunobrum/spicelib)
- Xyce supports `.SAMPLING` Monte Carlo and Latin Hypercube, `.MEASURE` for DC/AC — [Xyce news](https://xyce.sandia.gov/news/)
- ngspice 47 can plot through matplotlib (`pyplot`) directly from the simulator — [ngspice news](https://ngspice.sourceforge.io/news.html)
- kicad-happy spice: Monte Carlo N trials, seedable (`--mc-seed`), normal/uniform distribution, reports distributions and component sensitivity; ~5-50 ms per sim, i.e., 100 trials ~0.5-5 s per subcircuit; structured JSON with pass/warn/fail/skip — local `/home/cosme/.claude/plugins/cache/kicad-happy/kicad-happy/2.2.1/skills/spice/SKILL.md`

### Inferences
Suggested concrete tests for this board (assertion targets are design-specific):
- Battery divider + ADC: DC op over Vbat 6.0-8.4 V (2S) -> ADC pin within 0-3.3 V with margin at 100% charge + tolerance; RC settling to <0.5 LSB within the STM32 ADC sample time (input-source-impedance check); Monte Carlo on resistor tolerance -> worst-case scaling error.
- IR emitter driver: transient with real MOSFET + IR LED model: peak LED current within LED pulse rating, rise/fall time (10-90%) below the firmware's emitter settle time, MOSFET gate drive from STM32 GPIO (3.3 V Vgs) gives Rds(on) target; average power/I²R dissipation at the duty cycle; supply droop on the emitter rail during the pulse with the chosen bulk cap.
- Receiver AFE: AC sweep of op-amp TIA/gain stage -> -3 dB bandwidth and gain within band; transient step of photocurrent -> settled within the ADC sampling delay; output swing doesn't saturate at max reflectance; noise analysis optional.
- Regulators: feedback divider Vout (DC), LDO dropout margin at minimum LiPo voltage; behavioral buck output ripple; PDN impedance of decoupling network (kicad-happy covers this).
- H-bridge + motor: start-up/stall current, bulk capacitor ripple, motor current sense filter cutoff.
- Implement as `pytest` parametrized tests; `pytest.approx` / explicit min/max bands; save `.raw`→CSV/PNG under `sim/out/` and upload as CI artifacts; golden-waveform regression by comparing key metrics (not raw samples) to a committed baseline JSON with tolerances (mirrors the baseline/tolerance approach the micras-simulation repo already uses).
- Fix random seeds for Monte Carlo in CI for determinism; run large MC counts nightly only.

### Gaps
- No public 2024-2026 blog/repo found (in budget) showing a mature pytest+ngspice hardware CI template to cite; patterns above are inferred from tool capabilities.

## Beyond SPICE: PDN, SI, thermal, EM, trace-width, firmware co-simulation, motor system models, tie-in to micras-simulation

### Takeaway
For a micromouse, most "beyond SPICE" tools are overkill: openEMS (via Antmicro's gerber2ems) handles SI/EM if ever needed, open PCB thermal tooling is immature (KiCad_Thermal_Sim estimator is the practical option), and firmware co-simulation is already covered better by the user's own micras-simulation (firmware on host HAL + MuJoCo). The highest-value tie-in is using SPICE to derive/validate the electrical parameters that micras-simulation consumes (IR emitter settle time, AFE gain/saturation, divider ratio, motor drive).

### Cited Findings
- gerber2ems (Antmicro): Python tool that takes Gerbers, drill files and stackup and runs openEMS FDTD signal-integrity simulations of PCB traces; pipeline includes net selection, slicing, ports at each trace end — [gerber2ems GitHub](https://github.com/antmicro/gerber2ems); [Antmicro blog 2024](https://antmicro.com/blog/2024/07/automated-pcb-trace-selection-for-si-simulation); [Antmicro blog 2023](https://antmicro.com/blog/2023/11/open-source-signal-integrity-analysis)
- KiCad users report older openEMS scripts being outdated for KiCad 9 — [KiCad forum](https://forum.kicad.info/t/best-workflow-to-simulate-kicad-pcb-in-openems/66410); trace impedance vs frequency example with openEMS — [tmpdir community](https://community.tmpdir.org/t/kicad-trace-impedance-over-frequency-simulation-using-openems/1441)
- Thermal: KiCad_Thermal_Sim (PoeAlex) is an MIT Python plugin, a multi-layer copper thermal estimator (not full FEM) — [ecosyste.ms entry](https://awesome.ecosyste.ms/api/v1/projects/github.com%2Fpoealex%2Fkicad_thermal_sim). FreeCAD FEM (Elmer solver) + KiCad StepUp route is weak at importing copper layers — [KiCad forum](https://forum.kicad.info/t/kicad-stepup-and-fem-thermo-mechanical-analysis/3828); [KiCad forum thermal](https://forum.kicad.info/t/thermal-analysis-using-kicad/36805)
- Renode: supports co-simulation (Verilator, SystemC TLM) — [Antmicro blog](https://antmicro.com/blog/2024/07/systemc-co-simulation-in-renode/); an academic STM32L4 digital twin extension exists — [UFU thesis](https://repositorio.ufu.br/bitstream/123456789/48815/1/CriandoG%c3%aameosDigitais.pdf); a community RP2040 Renode project plans wiring a motor model to PWM/ADC — [xiao-rp2040-renode roadmap](https://xiao-seeed-rp2040-renode.readthedocs.io/en/latest/ROADMAP/)
- ngspice can co-simulate digital HDL (Icarus Verilog since 44, GHDL VHDL since 45) via `d_cosim` — [ngspice news](https://ngspice.sourceforge.io/news.html)
- micras-simulation (user's repo): runs unmodified firmware over micras_hal's host backend against MuJoCo, headless deterministic CSV output, baselines with tolerances. Its device models include: IR wall sensors (cone emitter, Lambertian reflection, responsivity × irradiance → voltage across load resistor, clipped at saturation, and "the emitter's contribution reaches only the settled fraction of its value by the time the conversion starts"); battery "measured by an ADC through a divider" using open-circuit voltage "which the loads do not pull down"; DC motor quasi-static `i = (V - backEMF)/R` with V = duty × supply — local files `/home/cosme/codes/micras-simulation/engine/include/micras/sim/devices/wall_sensors.hpp`, `/home/cosme/codes/micras-simulation/engine/include/micras/sim/devices/power.hpp`, `/home/cosme/codes/micras-simulation/engine/src/devices/dc_motor.cpp`, `/home/cosme/codes/micras-simulation/README.md`

### Inferences
- Tie-in (high value): make the PCB repo's SPICE tests emit a small parameters JSON (IR emitter settled fraction at the firmware's ADC delay, receiver load/gain and saturation voltage, divider ratio, emitter rail droop, H-bridge effective resistance) that micras-simulation's robot description can consume or be checked against. Then a schematic change that breaks a robot-level assumption fails CI in either repo.
- Gaps in micras-simulation that SPICE could fill: no battery internal resistance/sag under motor load (Battery model uses OCV), no motor inductance/driver Rds(on), IR emitter settle time is a parameter rather than derived. A simple Thevenin battery + driver Rds(on) is enough.
- Renode/QEMU are not needed: micras-simulation already runs the real firmware against the HAL; Renode would only add value for register-level peripheral testing of the STM32 (DMA/ADC timing), at large modeling cost. SimulIDE is GUI-oriented and not CI-friendly (training knowledge).
- Motor+driver system level: Python (scipy ODE) or OpenModelica would duplicate micras-simulation's motor model; better to refine the C++ model with L and supply sag than add a Modelica stack.
- Trace width/current: an IPC-2152 calculation as a small Python script over the KiCad PCB (via kicad-python / pcbnew API or the kicad-happy PCB analyzer) for motor and battery nets is cheap and worth it; full FEM thermal is not.
- SI/EM (openEMS) is unnecessary at micromouse speeds (SPI IMU at a few MHz, no high-speed interfaces); skip unless doing a radio/antenna.

### Gaps
- Specific IPC-2152 calculator libraries in Python were not researched (no search budget); none cited.
- Renode's STM32F4 ADC/timer model coverage not verified.
- OpenModelica motor/driver libraries not researched.
- No 2026 status found for open PDN-specific tools beyond kicad-happy's PDN check.

## Practical recommendation and repo structure

### Takeaway
Worth it for a micromouse: (1) ngspice in a pinned container, (2) kicad-happy spice as an automatic first gate, (3) ~6-10 hand-written pytest testbenches for the IR emitter driver, receiver AFE, battery divider/ADC, regulator margins and H-bridge/bulk caps with Monte Carlo on tolerances, (4) a parameters export consumed by micras-simulation, (5) IPC-2152 width check script. Skip openEMS, FEM thermal, Renode, Modelica unless a specific problem appears.

### Cited Findings
- ngspice is packaged in Debian/Alpine/Arch (versions 45.x-46+) for container use — [Debian sources](https://sources.debian.org/src/ngspice/45.2%2Bds-1/NEWS); [Alpine package](https://pkgs.alpinelinux.org/package/v3.23/community/x86/ngspice); [ALT Linux (46, April 2026)](https://packages.altlinux.org/ru/sisyphus/srpms/ngspice/)
- kicad-happy spice: `simulate_subcircuits.py --analysis-dir analysis/` after `analyze_schematic.py`; missing simulator is non-fatal — local SKILL.md (path above)
- spicelib SimRunner/RawRead/MC toolkit — [spicelib GitHub](https://github.com/nunobrum/spicelib)

### Inferences
Suggested layout (in MicrasPCB repo):
```
sim/
  README.md                 # how to run, tool versions
  models/                   # vendor .lib/.mod files + SOURCES.md (URL, date, license)
    behavioral/             # DRV8833/TB6612 H-bridge, buck/LDO averaged, LiPo Thevenin
  circuits/                 # .cir testbench templates (Jinja) or exported KiCad netlists
    ir_emitter.cir.j2
    ir_receiver_afe.cir.j2
    vbat_divider_adc.cir.j2
    regulators.cir.j2
    hbridge_motor.cir.j2
  params/board.yaml         # component values (ideally generated from KiCad BOM/netlist)
  lib/spice.py              # render -> run ngspice -b -> parse .meas/.raw (spicelib RawRead)
  tests/test_*.py           # pytest assertions, MC with fixed seed, @pytest.mark.slow for big MC
  baselines/*.json          # key metrics + tolerances for regression
  export/robot_params.py    # writes params JSON for micras-simulation
  out/                      # gitignored; CSV/PNG/HTML report -> CI artifacts
.github/workflows/sim.yml   # container with pinned ngspice + kicad-cli; pytest -m "not slow"; nightly full MC
```
- Pin tool versions (ngspice, KiCad) in the container image; record versions in report metadata so results are reproducible (same principle as micras-simulation's byte-identical runs).
- Generate params from the schematic (kicad-cli netlist/BOM export -> YAML) so tests catch schematic edits; fail CI if a referenced part has no model.

### Gaps
- No primary source surveyed for "best practice" hardware sim CI layouts; layout is a recommendation derived from the tools' capabilities and the user's existing micras-simulation conventions.
