# Skills

| Skill | Use it to |
|---|---|
| `micras-pcb` | work on this repo: parts and JLCPCB sourcing, fab outputs, mechanics, KiCad scripting, review gates |
| `zener-language` | read or edit Zener `.zen` sources and package APIs |
| `librarian` | create or repair a component package |
| `spice-sim` | add or run an ngspice test bench with `pcb sim` |

`micras-pcb` is this project's own. `zener-language`, `librarian` and `spice-sim` are copied from
[diodeinc/pcb](https://github.com/diodeinc/pcb/tree/main/skills) at commit `e7525c1` (pcb v0.4.81),
MIT License, Copyright (c) Diode Computers, Inc. Refresh them when bumping `PCB_TOOLCHAIN` in
`versions.env`.

Project rules that override them live in `/CLAUDE.md` (for example: component packages go under
`components/<manufacturer>/<NAME>/` in this repo, and every part needs a `parts/jlc.toml` entry).
