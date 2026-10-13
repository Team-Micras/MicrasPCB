#!/usr/bin/env bash
# PreToolUse (Edit|Write): KiCad files are generated or owned by KiCad; never edit them as text.
set -uo pipefail
file="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))')"
case "$file" in
  */layout/*.kicad_sch|*/layout/*.kicad_pro|*/layout/*.kicad_dru)
    echo "$file is generated: change the .zen source (or rules/jlcpcb.kicad_dru) and run 'make gen'." >&2
    exit 2 ;;
  */layout/*.kicad_pcb)
    echo "$file is KiCad-owned. Outline and spec-placed parts come from spec/<board>.toml ('make gen');" \
         "placement and routing change in KiCad, or through a pcbnew/IPC script the user approved." >&2
    exit 2 ;;
esac
exit 0
