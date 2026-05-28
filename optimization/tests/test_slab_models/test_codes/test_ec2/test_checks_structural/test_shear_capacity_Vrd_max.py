"""
Autor: Victor

unit test for shear_capacity_Vrd_max(
    section_width_mm: float,
    d_mm: float,
    fck_MPa: float,
    fcd_MPa: float,
    cot_theta: float = 1.2)
"""

import pytest


from slabdesignbench.slab_models.codes.ec2_2004_de.checks_structural import shear_capacity_Vrd_max

# Test shear_capacity_Vrd_max
def test_shear_capacity_Vrd_max() -> None:
    result = shear_capacity_Vrd_max(200,150,30,17)
    assert result == pytest.approx(169.303279, rel=1e-6)
    result = shear_capacity_Vrd_max(200, 150, 50, 28.33)
    assert result == pytest.approx(282.138934, rel=1e-6)
    result = shear_capacity_Vrd_max(200, 150, 60, 34)
    assert result == pytest.approx(331.834426, rel=1e-6)
    result = shear_capacity_Vrd_max(200, 150, 90, 51)
    assert result == pytest.approx(467.277049, rel=1e-6)

    result = shear_capacity_Vrd_max(1000,10,30,17)
    assert result == pytest.approx(56.434426, rel=1e-6)
    result = shear_capacity_Vrd_max(500, 150, 30, 17,0.8)
    assert result == pytest.approx(419.817073, rel=1e-6)
