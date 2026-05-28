"""
Autor: Victor

unit test for a_smax()
"""

import pytest

from slabdesignbench.slab_models.codes.ec2_2004_de.checks_structural import a_smax

# Test a_smax
def a_smax() -> None:
    result = a_smax()
    assert result == pytest.approx(0.04, rel=1e-6)
