"""Check results per board (build/<board>/checks.json), for the portal and PR comments."""

from __future__ import annotations

import json

from .paths import build_dir


def record(board: str, check: str, ok: bool, summary: str) -> None:
    path = build_dir(board) / "checks.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data[check] = {"ok": ok, "summary": summary}
    path.write_text(json.dumps(data, indent=1) + "\n")


def load(board: str) -> dict:
    path = build_dir(board) / "checks.json"
    return json.loads(path.read_text()) if path.exists() else {}
