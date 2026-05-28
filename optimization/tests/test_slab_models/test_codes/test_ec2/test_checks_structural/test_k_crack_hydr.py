"""
Autor: Victor

unit test for k_crack_hydr(slab_depth_mm)
"""

import pytest


from slabdesignbench.slab_models.codes.ec2_2004_de.checks_structural import k_crack_hydr

#   test values below 300
def test_k_crack_hydr_min() -> None:
    result = k_crack_hydr(150)
    assert result == pytest.approx(0.8, rel=1e-6)
    result = k_crack_hydr(300)
    assert result == pytest.approx(0.8, rel=1e-6)

#   test values inbetween 300 and 800
def test_k_crack_hydr_mid() -> None:
    result = k_crack_hydr(550)
    assert result == pytest.approx(0.65, rel=1e-6)

#   test values above 800
def test_k_crack_hydr_max() -> None:
    result = k_crack_hydr(800)
    assert result == pytest.approx(0.5, rel=1e-6)
    result = k_crack_hydr(900)
    assert result == pytest.approx(0.5, rel=1e-6)