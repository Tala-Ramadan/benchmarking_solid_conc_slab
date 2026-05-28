"""
Autor: Victor

unit test for s_min_vertical(reinforcement_diameter_mm)
"""

import pytest

from slabdesignbench.slab_models.codes.ec2_2004_de.checks_structural import s_min_vertical

# Test s_min_vertical
def test_s_min_vertical_Min() -> None:
    result = s_min_vertical(10)
    assert result == pytest.approx(21.0, rel=1e-6)
    result = s_min_vertical(16)
    assert result == pytest.approx(21.0, rel=1e-6)
    result = s_min_vertical(20)
    assert result == pytest.approx(21.0, rel=1e-6)

def test_s_min_vertical_Rebar() -> None:
    result = s_min_vertical(24)
    assert result == pytest.approx(24.0, rel=1e-6)
    result = s_min_vertical(28)
    assert result == pytest.approx(28.0, rel=1e-6)
    result = s_min_vertical(40)
    assert result == pytest.approx(40.0, rel=1e-6)