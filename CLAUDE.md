# MicrasPCB: agent instructions

PCBs of the Micras micromouse, designed as code. Read `README.md` for the layout of the repo.

## Sources of truth

| What | Where | Edit how |
|---|---|---|
| Circuit (parts, nets, values, design rules, stackup) | `boards/<board>/<board>.zen`, `components/**/*.zen` | Zener; see `.claude/skills/zener-language` |
| Board mechanics (outline, tab, spec-placed parts) | `spec/<board>.toml` | TOML, every value `{value, source}` |
| JLCPCB sourcing (MPN -> LCSC, rotation) | `parts/jlc.toml` | TOML |
| Fab rules, KiCad rule severities | `rules/jlcpcb.kicad_dru`, `rules/jlcpcb-pdk.toml`, `rules/kicad-severities.toml` | edit, then `make gen` |
| Placement, routing, zones | `boards/<board>/layout/<board>.kicad_pcb` | KiCad (the user), or a pcbnew script the user approved |
| Tool versions | `versions.env` | bump in its own PR |

Everything else under `boards/*/layout/` is generated: never edit `.kicad_sch`, `.kicad_pro` or
`.kicad_dru` as text (a hook blocks it). Never edit `.kicad_pcb` as text either.

## Loop

1. Change the source.
2. `make gen` regenerates the KiCad project, rules copies and spec geometry.
3. `make check` runs every gate CI runs: format, build, Zener tests, layout sync, spec drift,
   ERC, LVS, DRC, DFM, pytest, parts mapping.
4. `make review` builds `build/<board>/review/` (schematic PDF, layer SVGs, renders, GLB/STEP)
   and `build/<board>/fab/` to inspect.

After each `.zen` edit a hook runs `pcb fmt` and `pcb build` and reports failures back to you.
Do not report work as done until `make gen` leaves `git diff` clean of surprises and `make check`
passes; say which checks you could not run.

## Rules

- Hardware facts (pinouts, limits, application circuits) come from the datasheet. Cite the figure
  or table in the `.zen` docstring or a comment. Do not invent part numbers, URLs or values; if a
  fact is unknown, say so and leave a visible TODO.
- Every part on a board needs an MPN + manufacturer in Zener and an entry in `parts/jlc.toml`.
  Check stock with `make parts-online`; prefer JLCPCB *basic* parts. The `micras-pcb` skill covers
  adding parts, the JLCPCB outputs and scripting KiCad files.
- New components: `components/<manufacturer>/<NAME>/` with `pcb.toml`, `.zen`, `.kicad_sym`
  (KiCad 10 format), `.kicad_mod` with the STEP embedded (`pcb embed-step`), `README.md`, and a
  test bench in `test/` for the datasheet requirements. Follow `.claude/skills/librarian`.
- Keep topology stable across configs (zener-language skill): stable instance names keep the
  hand layout attached to the right parts.
- Mechanical numbers live in `spec/`. If MicrasHardware, micras-simulation or the firmware need a
  number, they read the exported `build/<board>/<board>_mech.json`; never copy numbers by hand.
- Placement and routing are human-led. You may propose a layout change, but run it only as a
  script the user approved, and re-run `make check` afterwards.
- Commits: gitmoji style, as in MicrasFirmware (for example `✨ Add the encoder board`).
