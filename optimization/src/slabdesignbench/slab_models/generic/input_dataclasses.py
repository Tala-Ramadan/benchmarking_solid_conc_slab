"""
input_dataclasses.py
====================

Input dataclasses defining expected parameters for slab models.

Purpose:
--------
1. DOCUMENTATION: Show what parameters each slab model expects
2. VALIDATION: Check that all required parameters are present in params dict

These dataclasses are NOT passed directly to analysis functions (which receive
dicts from the CSV decoder). Instead, use `validate_params()` at the start of
analysis to verify all expected parameters exist.

Note: Beam dataclasses are in `slab_models/generic/beams/` since beams use
typed dataclass inputs (they're internal, not CSV-driven).

Usage:
------
    from slabdesignbench.slab_models.generic.input_dataclasses import (
        SolidSlabOneWayConcreteSlab,
        validate_params,
    )

    def _analysis_impl(params: dict, *, constraints: dict) -> dict:
        # Validate all expected parameters are present
        validate_params(params, SolidSlabOneWayConcreteSlab)

        # Now safe to access params["slab_depth_mm"], etc.
        ...

Field Naming Convention:
------------------------
Field names match CSV column names exactly:
- Include units in name: `slab_depth_mm`, `span_primary_m`
- Trailing underscore for unitless/categorical: `static_system_`

Class Naming Convention:
------------------------
{SlabType}{SpanningDirection}{Material}Slab (e.g., SolidSlabOneWayConcreteSlab)

Hierarchy:
----------
- Slab (abstract base)
  - ConcreteSlab (base for all concrete slabs)
    - SolidSlabOneWayConcreteSlab
    - SolidSlabTwoWayConcreteSlab (placeholder)
    - RibbedSlabOneWayConcreteSlab (placeholder)
    - FlatSlabTwoWayConcreteSlab (placeholder)
    - HPShellOneWayConcreteSlab (placeholder)
  - TimberSlab (placeholder)
  - CompositeSlab (placeholder)

Extensibility:
--------------
Each dataclass has an `extra` field (Dict) for parameters not explicitly
defined in the class. This field is NOT validated - it's for future extensions.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

# =============================================================================
# VALIDATION FUNCTION
# =============================================================================


def validate_params(params: dict, slab_type: type) -> None:
    """
    Validate that params dict contains all fields expected by the slab type.

    Call this at the start of analysis to catch missing parameters early
    with a clear error message.

    Parameters
    ----------
    params : dict
        Decoded parameters from CSV (from decode(x_idx)).
    slab_type : Type
        Dataclass type defining expected parameters
        (e.g., SolidSlabOneWayConcreteSlab).

    Raises
    ------
    KeyError
        If any expected field is missing from params.
        Error message lists all missing fields.

    Examples
    --------
    >>> validate_params(params, SolidSlabOneWayConcreteSlab)
    # Raises KeyError if params is missing e.g. 'slab_depth_mm'
    """
    # Get all field names from the dataclass (including inherited from parent classes)
    expected_fields = {f.name for f in dataclasses.fields(slab_type)}

    # Remove fields that are constants/defaults, not CSV parameters
    expected_fields.discard("extra")  # For extensibility
    expected_fields.discard("alpha_cc_")  # Constant: EC2-1-1 NA.de default (0.85), can be changed globally in dataclass

    # Find missing parameters
    provided_fields = set(params.keys())
    missing = expected_fields - provided_fields

    if missing:
        raise KeyError(
            f"Missing {len(missing)} parameter(s) for {slab_type.__name__}: {sorted(missing)}. "
            f"Check your CSV files (parameter_defaults.csv, problem_list.csv)."
        )


# =============================================================================
# SLAB BASE CLASSES
# =============================================================================


@dataclass
class Slab:
    """
    Abstract base for all slab types.

    Common parameters that apply to any slab material.
    """

    # Static system
    static_system_: str = "simply_supported"  # or "cantilever"
    span_primary_m: float = 5.0
    span_secondary_m: float = 5.0  # for two-way slabs

    # Slab geometry
    slab_depth_mm: float = 100.0
    slab_width_mm: float = 1000.0  # Analysis strip width

    # Loads
    load_category_: str = "A"  # EC0 category (A/B/C/D/E)
    live_load_kN_m2: float = 5.0
    superimposed_dead_load_kN_m2: float = 1.5

    # Criteria for code checks
    w_allowed_tinf_: float = 250.0  # L/250 ratio
    w_allowed_inc_: float = 500.0  # L/500 ratio
    vibration_f_min_Hz: float = 8.0
    fire_resistance_min: float = 90.0

    # Objective function weights: y = obj_weight_cost * y_cost + obj_weight_gwp * y_gwp
    obj_weight_cost: float = 1.0
    obj_weight_gwp: float = 0.0

    # Extensibility: additional parameters not explicitly defined (NOT validated)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConcreteSlab(Slab):
    """
    Base class for all concrete slab types.

    Adds concrete-specific parameters to the base Slab class.
    """

    # Concrete properties
    concrete_grade_MPa: float = 16.0  # fck
    alpha_cc_: float = (
        0.85  # EC2-1-1 NA.de coefficient for long-term effects (constant, not validated - can be changed globally here)
    )

    # Reinforcement geometry
    reinforcement_diameter_mm: float = 12.0
    reinforcement_spacing_lay_1_mm: float = 150.0
    reinforcement_spacing_lay_2_mm: float = 150.0
    reinforcement_spacing_lay_3_mm: float = 150.0
    # Layer 1 is always active by default
    reinforcement_layer_active_2_: float = 0.0  # 0 or 1
    reinforcement_layer_active_3_: float = 0.0  # 0 or 1

    # Cost/GWP data (comma-separated strings, parsed in analysis)
    concrete_grade_list_MPa: str = ""
    concrete_cost_eur_m3: str = ""
    concrete_gwp_kgco2e_m3: str = ""
    cost_reinf_steel_per_conc_: float = 20.0  # Ratio steel/concrete cost
    gwp_reinf_steel_per_conc_: float = 20.0  # Ratio steel/concrete GWP


# =============================================================================
# CONCRETE SLAB TYPES
# =============================================================================


@dataclass
class SolidSlabOneWayConcreteSlab(ConcreteSlab):
    """
    Solid one-way spanning concrete slab.

    Spans primarily in one direction, supported by beams.
    Includes parameters for supporting beams.

    Use with validate_params() in analysis_ec2_de.py.
    """

    # Supporting beam parameters (beam at slab edge)
    beam_depth_mm: float = 500.0
    beam_reinforcement_diameter_mm: float = 16.0
    beam_reinforcement_spacing_lay_1_mm: float = 50.0
    beam_reinforcement_spacing_lay_2_mm: float = 50.0
    beam_reinforcement_layer_active_2_: float = 0.0  # 0 or 1


@dataclass
class SolidSlabTwoWayConcreteSlab(ConcreteSlab):
    """
    Solid two-way spanning concrete slab.

    Placeholder - to be implemented.
    """

    pass


@dataclass
class RibbedSlabOneWayConcreteSlab(ConcreteSlab):
    """
    Ribbed (waffle) concrete slab.

    Placeholder - to be implemented.
    """

    rib_width_mm: float = 0.0
    rib_spacing_mm: float = 0.0


@dataclass
class FlatSlabTwoWayConcreteSlab(ConcreteSlab):
    """
    Flat slab (no beams, direct column support).

    Placeholder - to be implemented.
    """

    pass


@dataclass
class HPShellOneWayConcreteSlab(ConcreteSlab):
    """
    Hyperbolic paraboloid (HP) shell in concrete.

    Placeholder - to be implemented.
    """

    pass


# =============================================================================
# OTHER SLAB MATERIALS (PLACEHOLDERS)
# =============================================================================


@dataclass
class TimberSlab(Slab):
    """Placeholder for timber slab - future implementation."""

    pass


@dataclass
class CompositeSlab(Slab):
    """Placeholder for composite (steel-concrete) slab - future implementation."""

    pass
