#!/usr/bin/env bash
# Tools on top of the kicad/kicad image (CI and the devcontainer): curl/zstd, uv and the pinned
# Zener toolchain from versions.env. Run as root; installs into $HOME of the invoking user.
set -euo pipefail
cd "$(dirname "$0")/.."
. ./versions.env

if ! command -v curl >/dev/null || ! command -v zstd >/dev/null || ! command -v make >/dev/null; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq curl zstd make ca-certificates >/dev/null
fi
export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
command -v pcb >/dev/null || curl -fsSL https://raw.githubusercontent.com/diodeinc/pcb/main/install.sh | bash
pcb toolchain install "$PCB_TOOLCHAIN"
[ -n "${GITHUB_PATH:-}" ] && echo "$HOME/.local/bin" >> "$GITHUB_PATH"
kicad-cli version
pcb +"$PCB_TOOLCHAIN" --version
