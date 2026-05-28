"""
Autor: Victor
"""

import pytest

from slabdesignbench.slab_models.codes.ec2_2004_de.loads import self_weight_kN_m2

def test_self_weight_kN_m2():
    """
    test_self_weight_kN_m2

    default weight: 25 kN/m3
    """
    # Test case 1: h = 10 cm = 100 mm should return 2.5
    assert self_weight_kN_m2(100) == pytest.approx(2.5, rel=1e-6)
    # Test case 2: h = 15 cm = 150 mm should return 3.75
    assert self_weight_kN_m2(150) == pytest.approx(3.75, rel=1e-6)
    # Test case 3: h = 20 cm = 200 mm should return 5.0
    assert self_weight_kN_m2(200) == pytest.approx(5, rel=1e-6)