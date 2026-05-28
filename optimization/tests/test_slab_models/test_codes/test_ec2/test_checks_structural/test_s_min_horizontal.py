"""
Autor: Victor

unit test for s_min_horizontal(reinforcement_diameter_mm)
"""

import pytest


from slabdesignbench.slab_models.codes.ec2_2004_de.checks_structural import s_min_horizontal


# Test s_min_horizontal
def test_s_min_horizontal_Min() -> None:
    result = s_min_horizontal(8)
    assert result == pytest.approx(20.0, rel=1e-6)    # d_g= 16 mm is the assumed

def test_s_min_horizontal_Rebar() -> None:
    result = s_min_horizontal(12)
    assert result == pytest.approx(24.0, rel=1e-6)     # d_g= 16 mm is the assumed

