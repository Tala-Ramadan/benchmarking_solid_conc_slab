"""
Autor: Victor

unit test for min_ductl(
    slab_depth_mm: float,
    f_ctm_MPa: float,
    d_mm: float,
    fyk_MPa: float = 500.0)
"""

import pytest

from slabdesignbench.slab_models.codes.ec2_2004_de.checks_structural import as_min_duct

# Test as_min_duct
def test_as_min_duct() -> None:
    result = as_min_duct(200,3,150)
    assert result == pytest.approx(296.296296, rel=1e-6)
    result = as_min_duct(100, 5, 150)
    assert result == pytest.approx(123.456790, rel=1e-6)
    result = as_min_duct(150, 1, 50)
    assert result == pytest.approx(166.666666, rel=1e-6)
    result = as_min_duct(300, 10, 150)
    assert result == pytest.approx(2222.222222, rel=1e-6)
