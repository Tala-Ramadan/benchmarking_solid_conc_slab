"""
Autor: Victor

unit test for s_max_secondary_direction()
"""

import pytest


from slabdesignbench.slab_models.codes.ec2_2004_de.checks_structural import s_max_secondary_direction

# Test s_max_secondary_direction
def test_s_max_secondary_direction() -> None:
    result = s_max_secondary_direction()
    assert result == pytest.approx(250.0, rel=1e-6)
