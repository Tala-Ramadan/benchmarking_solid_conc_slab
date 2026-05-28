"""
Autor: Victor

unit tests for s_max_primary_direction(slab_depth_mm)
"""

import pytest

from slabdesignbench.slab_models.codes.ec2_2004_de.checks_structural import s_max_primary_direction

#   test values below limit
def test_s_max_primary_direction_min() -> None:
    result = s_max_primary_direction(100)
    assert result == pytest.approx(150.0, rel=1e-6)
    result = s_max_primary_direction(150)
    assert result == pytest.approx(150.0, rel=1e-6)

#   test inbetween values
def test_s_max_primary_direction_mid() -> None:
    result = s_max_primary_direction(200)
    assert result == pytest.approx(200.0, rel=1e-6)

#   test values above limit
def test_s_max_primary_direction_max() -> None:
    result = s_max_primary_direction(250)
    assert result == pytest.approx(250.0, rel=1e-6)
    result = s_max_primary_direction(300)
    assert result == pytest.approx(250.0, rel=1e-6)