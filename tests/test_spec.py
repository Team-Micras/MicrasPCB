"""The mechanical specs are well formed and their geometry is consistent."""

import math
import tomllib

import pytest
from micras_pcb import mech, spec
from micras_pcb.paths import ROOT

SPECS = sorted(p.stem for p in (ROOT / "spec").glob("*.toml"))


@pytest.mark.parametrize("board", SPECS)
def test_every_value_has_a_source(board):
    raw = tomllib.loads((ROOT / "spec" / f"{board}.toml").read_text())
    for section, values in raw.items():
        for key, v in values.items():
            assert isinstance(v, dict) and v.get("source"), f"{section}.{key} needs {{value, source}}"


def _ends(e):
    return e.a, e.b


def test_encoder_outline_is_closed():
    outline = mech.encoder_outline(spec.load("encoder"))
    for prev, nxt in zip(outline, outline[1:] + outline[:1]):
        assert math.dist(_ends(prev)[1], _ends(nxt)[0]) < 1e-9


def test_encoder_outline_matches_spec_extents():
    s = spec.load("encoder")
    pts = [p for e in mech.encoder_outline(s) for p in mech.sample(e, 64)]
    us, vs = [p[0] for p in pts], [p[1] for p in pts]
    assert max(us) - min(us) == pytest.approx(s["outline"]["width"], abs=1e-6)
    assert max(vs) == pytest.approx(s["outline"]["top"], abs=1e-6)
    assert min(vs) == pytest.approx(-s["tab"]["depth"], abs=1e-6)


def test_sensor_fits_on_the_board():
    s = spec.load("encoder")
    # TSSOP-14 courtyard is about 7.7 x 5.5 mm
    assert s["sensor"]["v"] + 2.75 < s["outline"]["top"]
    assert abs(s["sensor"]["u"]) + 3.85 < s["outline"]["width"] / 2
