"""
Tests for time_effects module.

Tests time-dependent material properties for concrete per EC2-2004 + NA.de.
"""

import pytest
from structuralcodes.codes import ec2_2004 as ec2


def test_k_h():
    """
    Test the k_h function from EC2-2004 for different notional sizes h0_mm.

    k_h is the humidity-dependent factor for drying shrinkage.
    """
    # Test case 1: h0_mm = 100 should return 1.0
    assert ec2.k_h(100) == pytest.approx(1.0, rel=1e-6)
    # Test case 2: h0_mm = 200 should return 0.85
    assert ec2.k_h(200) == pytest.approx(0.85, rel=1e-6)
    # Test case 3: h0_mm = 300 should return 0.75
    assert ec2.k_h(300) == pytest.approx(0.75, rel=1e-6)
    # Test case 4: h0_mm = 600 should return 0.70
    assert ec2.k_h(600) == pytest.approx(0.70, rel=1e-6)
