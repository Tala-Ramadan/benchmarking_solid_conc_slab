"""
ec2_2004_de
===========

EC2-2004 + German National Annex (NA.de) specific implementations.

Modules:
- materials: Material creation (concrete, reinforcement steel) with EC2+NA.de defaults
- loads: Self-weight and load calculations
- combinations: Load combination functions (ULS, SLS)
- time_effects: Creep and shrinkage per EC2 Annex B
- checks_structural: Structural code checks (cover, spacing, reinforcement limits, etc.)
"""

from slabdesignbench.slab_models.codes.ec2_2004_de.materials import (
    MaterialSet,
    build_materials,
)

__all__ = [
    "MaterialSet",
    "build_materials",
]
