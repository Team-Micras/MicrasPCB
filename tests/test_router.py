"""boards/main/layout/router.py on small synthetic boards (tests/router_cases.py): octilinear
routes that keep the board's clearances, a gap threaded and a via pair taken where the board
needs them, no search where there is no way, the same tracks from the same board, and a search
whose heuristics never overestimate.

The router runs under KiCad's Python (pcbnew and numpy), not the project's environment:
KICAD_PYTHON names it, else /usr/bin/python3 when it has both."""

import json
import os
import shutil
import subprocess
from functools import cache
from pathlib import Path

import pytest

CASES = Path(__file__).with_name("router_cases.py")


@cache
def _python() -> str | None:
    for exe in (os.environ.get("KICAD_PYTHON"), "/usr/bin/python3", shutil.which("python3")):
        if not exe:
            continue
        ok = subprocess.run([exe, "-c", "import pcbnew, numpy"], capture_output=True, check=False)
        if ok.returncode == 0:
            return exe
    return None


needs_pcbnew = pytest.mark.skipif(_python() is None, reason="no Python with KiCad's pcbnew and numpy")


@cache
def run(case: str) -> dict:
    out = subprocess.run([_python(), str(CASES), case], capture_output=True, text=True, check=False, timeout=600)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


@needs_pcbnew
@pytest.mark.parametrize("case", ["bend", "centred", "channel", "via", "dense"])
def test_route_is_octilinear_clear_and_joins_the_net(case):
    r = run(case)
    assert r["routed"], r
    assert r["islands"] == 1, r
    assert not r["findings"], "\n".join(r["findings"])


@needs_pcbnew
def test_route_threads_the_one_gap():
    r = run("channel")
    # the wall of pads runs along y = 7.5; the route crosses it in the gap
    crossing = [seg for seg in r["routes"] if seg[0] != "via" and (seg[1][1] - 7.5) * (seg[2][1] - 7.5) <= 0]
    assert crossing, r["routes"]
    assert all(abs(min(s[1][0], s[2][0]) - r["gap_x"]) < 0.5 for s in crossing), (crossing, r["gap_x"])


@needs_pcbnew
def test_route_takes_a_via_pair_under_a_wall_of_tracks():
    r = run("via")
    assert r["vias"] == 2, r


@needs_pcbnew
def test_boxed_pad_fails_without_a_search():
    r = run("boxed")
    assert not r["routed"]
    # the free region around the source cannot reach the target: no state is expanded
    assert r["stats"]["expanded"] == 0, r["stats"]
    assert r["seconds"] < 10, r["seconds"]


@needs_pcbnew
def test_same_board_gives_the_same_tracks():
    r = run("determinism")
    assert r["same"], r


@needs_pcbnew
def test_heuristics_never_overestimate():
    rows = run("search")["costs"]
    assert any(c[0] is not None for c in rows)
    for zero, octile, geodesic in rows:
        assert octile == zero and geodesic == zero, rows


@needs_pcbnew
def test_dense_route_speed():
    # about 7 s on a busy development machine; a regression of several times fails
    assert run("dense")["seconds"] < 60


@needs_pcbnew
def test_checked_route_ends_on_the_pad_centres():
    r = run("centred")
    ends = [p for seg in r["routes"] if seg[0] != "via" for p in seg[1:]]
    for pad in r["pads"]:
        assert any(abs(e[0] - pad[0]) < 1e-3 and abs(e[1] - pad[1]) < 1e-3 for e in ends), (pad, r["routes"])
