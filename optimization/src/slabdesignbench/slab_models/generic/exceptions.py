"""
exceptions.py
=============

Custom exceptions and error handling utilities for structural analysis.

This module provides:
- SectionAnalysisError: Exception raised by analysis helpers
- create_error_result(): Creates penalized AnalysisResult for failed analyses
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class SectionAnalysisError(RuntimeError):
    """
    Fatal error in section analysis.

    Raised when:
    - Section geometry is invalid (e.g., reinforcement outside concrete)
    - Equilibrium cannot be found in StructuralCodes components
    - Moment-curvature calculation fails in StructuralCodes components
    - Other StructuralCodes errors

    Caught by analysis() wrapper, which returns a penalized objective.
    """

    pass


# =============================================================================
# ERROR RESULT CREATION
# =============================================================================


# Import here to avoid circular imports (AnalysisResult imports from this module indirectly)
def create_error_result(params: dict, constraints: dict, error_msg: str) -> dict:
    """
    Create a penalized error result when analysis fails.

    Returns an AnalysisResult with high penalty values to discourage
    the optimizer from exploring similar designs.

    Parameters
    ----------
    params : dict
        The input parameters that caused the failure.
    constraints : dict
        The constraints dict (used to create penalty entries for each).
    error_msg : str
        Description of what went wrong.

    Returns
    -------
    dict
        AnalysisResult.to_dict() with penalty values.

    Examples
    --------
    In analysis() wrapper:

        except SectionAnalysisError as e:
            return create_error_result(params, constraints, str(e))
    """
    # Import here to avoid circular import
    from slabdesignbench.slab_models.generic.result_dataclasses import AnalysisResult

    ERROR_PENALTY_Y = 1e12
    ERROR_PENALTY_CONSTRAINT = 1e2

    constraint_values: dict[str, float] = {name: ERROR_PENALTY_CONSTRAINT for name in constraints}
    active_constraint_values: dict[str, float] = {
        name: ERROR_PENALTY_CONSTRAINT for name, meta in constraints.items() if meta.get("active", True)
    }
    penalties: dict[str, float] = {name: ERROR_PENALTY_CONSTRAINT for name in constraints}

    result = AnalysisResult(
        y=ERROR_PENALTY_Y,
        y_p=ERROR_PENALTY_Y,
        y_cost=ERROR_PENALTY_Y,
        y_gwp=ERROR_PENALTY_Y,
        active_constraint_values=active_constraint_values,
        constraint_values=constraint_values,
        penalties=penalties,
        computation_successful=False,
        analysis_error=error_msg,
        params=dict(params),
    )
    return result.to_dict()
