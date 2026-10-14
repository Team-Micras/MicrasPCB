#!/usr/bin/env bash
# PostToolUse (Edit|Write): give the agent the compiler's verdict right after it edits a source.
# Exit 2 sends stderr back to Claude, so a broken edit is fixed before anything else happens.
set -uo pipefail
file="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))')"
# Check the checkout that holds the edited file: an agent in a git worktree of this repository
# (.claude/worktrees/<name>) gets the verdict on its own tree, not on $CLAUDE_PROJECT_DIR.
root="$(git -C "$(dirname "$file")" rev-parse --show-toplevel 2>/dev/null)"
[ -n "$root" ] && [ -f "$root/versions.env" ] || root="$CLAUDE_PROJECT_DIR"
cd "$root" || exit 0
. ./versions.env
case "$file" in
  *.zen)
    out="$(pcb +"$PCB_TOOLCHAIN" fmt "$file" 2>&1 && pcb +"$PCB_TOOLCHAIN" build "$(dirname "$file")" 2>&1)" || {
      echo "pcb build failed after editing $file:" >&2
      echo "$out" | tail -40 >&2
      exit 2
    }
    case "$file" in
      */test/*|*/test_*) out="$(pcb +"$PCB_TOOLCHAIN" test "$(dirname "$file")" 2>&1)" || { echo "$out" | tail -40 >&2; exit 2; } ;;
    esac
    echo "pcb build ok. Before finishing: make gen && make check" >&2
    ;;
  */spec/*.toml|*/parts/*.toml|*/tools/micras_pcb/*.py|*/tests/*.py)
    out="$(uv run pytest -q 2>&1)" || { echo "pytest failed after editing $file:" >&2; echo "$out" | tail -40 >&2; exit 2; }
    ;;
esac
exit 0
