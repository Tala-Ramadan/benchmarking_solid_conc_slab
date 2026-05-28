"""
Autor: Victor

unit tests for c_nom_one_way()
"""

import pytest

from slabdesignbench.slab_models.codes.ec2_2004_de.checks_structural import c_nom

# Korrosionsschnutz (nur XC1) maßgebend
def test_c_nom_one_way_XC1() -> None:
    result = c_nom(6, 60)
    assert result == pytest.approx(20.0, rel=1e-6)
    result = c_nom(8, 60)
    assert result == pytest.approx(20.0, rel=1e-6)

# Verbund maßgebend
def test_c_nom_one_way_Bond() -> None:
    result = c_nom(20, 30)
    assert result == pytest.approx(30.0, rel=1e-6)
    result = c_nom(28, 30)
    assert result == pytest.approx(38.0, rel=1e-6)
    result = c_nom(40, 30)
    assert result == pytest.approx(50.0, rel=1e-6)

# Brandschutz maßgebend
def test_c_nom_one_way_Fire() -> None:
    result = c_nom(6, 90)
    assert result == pytest.approx(27.0, rel=1e-6)
    result = c_nom(10, 90)
    assert result == pytest.approx(25.0, rel=1e-6)
    result = c_nom(12, 90)
    assert result == pytest.approx(24.0, rel=1e-6)

def test_c_nom_one_way_Wrong_fire_input() -> None:
    with pytest.raises(KeyError):
        result = c_nom(10, 10)
    with pytest.raises(KeyError):
        result = c_nom(10, 20)
