"""
solid_slab_one_way_concrete
===========================

Solid one-way spanning concrete slab analysis.

This slab type:
- Spans primarily in one direction
- Supported by beams or walls
- Rectangular cross-section with bottom reinforcement

Design code: EC2-2004 + German National Annex (NA.de)
"""

from slabdesignbench.slab_models.slab_types.solid_slab_one_way_concrete.analysis_ec2_de import (
    analysis,
)

__all__ = ["analysis"]
