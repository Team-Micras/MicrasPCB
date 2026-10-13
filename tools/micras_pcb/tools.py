"""External tools, overridable through the environment (CI images and local installs differ)."""

from __future__ import annotations

import os
import shutil

from .paths import ROOT


def versions() -> dict[str, str]:
    """versions.env as a dict (KEY=VALUE lines)."""
    out = {}
    for line in (ROOT / "versions.env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def kicad_cli() -> str:
    exe = os.environ.get("KICAD_CLI") or shutil.which("kicad-cli")
    if not exe:
        raise SystemExit("kicad-cli not found: install KiCad 10 or set KICAD_CLI")
    return exe


def pcb() -> list[str]:
    """The pcb command, pinned to versions.env's toolchain."""
    exe = os.environ.get("PCB") or shutil.which("pcb")
    if not exe:
        raise SystemExit("pcb not found: install the Zener toolchain (see README) or set PCB")
    return [exe, "+" + versions()["PCB_TOOLCHAIN"]]
