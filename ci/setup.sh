#!/usr/bin/env bash
# Tools on top of KiCad (CI and local setup): curl/zstd/make, uv and the pinned Zener toolchain
# from versions.env. CI installs uv with astral-sh/setup-uv first; this script then skips it.
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
