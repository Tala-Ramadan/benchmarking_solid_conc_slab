"""
generic
=======

Code-agnostic mechanics and helper modules.

Modules:
- input_dataclasses: Parameter definitions for slab/beam types
- result_dataclasses: Analysis output structures
- exceptions: Custom exceptions for analysis errors
- internal_forces: Beam forces and slab combination forces
- deformations: Deflection calculations (code-agnostic parts)
- section_geometry: Section building (dataclasses, builders)
- section_properties: Section property extraction (I, A, M_cr, etc.)
"""

from slabdesignbench.slab_models.generic.exceptions import SectionAnalysisError
from slabdesignbench.slab_models.generic.result_dataclasses import AnalysisResult

__all__ = [
    "SectionAnalysisError",
    "AnalysisResult",
]
