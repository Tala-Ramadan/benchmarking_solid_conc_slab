"""
beams
=====

Rectangular concrete beam analysis per EC2-2004 + German National Annex (NA.de).

This module contains everything needed for beam analysis:
- RectangularConcreteBeam (input dataclass)
- BeamAnalysisResult (output dataclass)
- beam_analysis() function

To add support for other design codes (e.g., ACI 318, EC2+UK):
1. Copy this folder to the appropriate code folder (e.g., codes/aci_318/beams/)
2. Adapt the analysis function for that code

Usage (from slab analysis):
---------------------------
    from slabdesignbench.slab_models.codes.ec2_2004_de.beams import (
        RectangularConcreteBeam,
        BeamAnalysisResult,
        beam_analysis,
    )

    beam = RectangularConcreteBeam(
        beam_span_m=span_secondary_m,
        beam_depth_mm=500.0,
        beam_width_mm=300.0,
        beam_q_ULS_kN_m=forces.ULS.R_supports_kN[0],
        ...
    )

    result = beam_analysis(beam, materials)
"""

from .rectangular_beam import (
    BEAM_WIDTH_MM,
    BeamAnalysisResult,
    RectangularConcreteBeam,
    beam_analysis,
)

__all__ = [
    "BEAM_WIDTH_MM",
    "RectangularConcreteBeam",
    "BeamAnalysisResult",
    "beam_analysis",
]
