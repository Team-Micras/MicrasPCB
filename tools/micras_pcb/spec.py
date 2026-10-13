"""Mechanical specs (spec/*.toml): every value is {value, source}; tools only see the values."""

from __future__ import annotations

import tomllib

from .paths import ROOT

SPEC_DIR = ROOT / "spec"


def load(board: str) -> dict:
    """Spec values for a board, as nested dicts of plain values."""
    raw = tomllib.loads((SPEC_DIR / f"{board}.toml").read_text())
    return _values(raw, board)


def sources(board: str) -> dict:
    raw = tomllib.loads((SPEC_DIR / f"{board}.toml").read_text())
    return {f"{s}.{k}": v["source"] for s, d in raw.items() for k, v in d.items()}


def _values(raw: dict, where: str) -> dict:
    out = {}
    for key, v in raw.items():
        if isinstance(v, dict) and "value" in v:
            if not v.get("source"):
                raise ValueError(f"{where}.{key}: every spec value needs a source")
            out[key] = v["value"]
        elif isinstance(v, dict):
            out[key] = _values(v, f"{where}.{key}")
        else:
            raise ValueError(f"{where}.{key}: expected {{value, source}}")
    return out
