# Vendored skills

`zener-language`, `librarian` and `spice-sim` are copied from
[diodeinc/pcb](https://github.com/diodeinc/pcb/tree/main/skills) at commit `513ed09` (pcb v0.4.77),
MIT License, Copyright (c) Diode Computers, Inc. Refresh them when bumping `PCB_TOOLCHAIN` in
`versions.env`.

Project rules that override them live in `/CLAUDE.md` (for example: component packages go under
`components/<manufacturer>/<NAME>/` in this repo, and every part needs a `parts/jlc.toml` entry).
