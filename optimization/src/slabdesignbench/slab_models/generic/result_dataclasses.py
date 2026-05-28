"""
result_dataclasses.py
=====================

Dataclasses for analysis outputs.

This module defines the final output structure from analysis functions.
These are code-agnostic - any design code produces results in this format.

Also provides helper functions for penalized objective calculation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# =============================================================================
# PENALTY CONFIGURATION (adjust these to change penalty behavior globally)
# =============================================================================
PENALTY_MULTIPLIER: float = 1.0  # Multiplier for penalty sum
PENALTY_EXPONENT: float = 3.0  # Exponent: y_p = y * (1 + multiplier * sum)^exp


def compute_penalized_objective(
    y: float,
    penalties: dict[str, float],
    constraints: dict[str, dict],
    multiplier: float = PENALTY_MULTIPLIER,
    exponent: float = PENALTY_EXPONENT,
    verbose: bool = False,
) -> tuple[float, dict[str, float]]:
    """
    Compute penalized objective from base objective and penalties.

    Formula: y_p = y * (1 + multiplier * penalty_sum) ^ exponent

    Parameters
    ----------
    y : float
        Base (unpenalized) objective value.
    penalties : Dict[str, float]
        Penalty values for all constraints (0 if satisfied, >0 if violated).
    constraints : Dict[str, dict]
        Constraint metadata with 'active' flag.
    multiplier : float, optional
        Multiplier for penalty sum. Default: PENALTY_MULTIPLIER (1.0).
    exponent : float, optional
        Exponent for penalty term. Default: PENALTY_EXPONENT (3.0).
    verbose : bool, optional
        If True, print penalty sum and penalized objective.

    Returns
    -------
    y_p : float
        Penalized objective value.
    active_penalties : Dict[str, float]
        Dictionary of penalties for active constraints only.
    """
    # Filter to active constraints only
    active_penalties = {
        name: penalties[name] for name, meta in constraints.items() if meta.get("active", True) and name in penalties
    }

    # Sum penalties
    penalty_sum = sum(active_penalties.values())

    # Compute penalized objective
    y_p = y * (1.0 + multiplier * penalty_sum) ** exponent

    if verbose:
        
        print(f"penalty sum: {penalty_sum:.4f}")
        print(f"penalized objective: {y_p:.4f}")
        
        #active_constraint_names = list(active_penalties.keys())
        # Print active penalties in a formatted table
        #if active_penalties:
        #    print("\nActive constraints and penalties:")
        #    print("-" * 70)
        #    print(f"{'Constraint Name':<50} {'Penalty':>15}")
        #    print("-" * 70)
        #    for name, penalty_val in active_penalties.items():
        #        print(f"{name:<50} {penalty_val:>15.6f}")
        #    print("-" * 70)
        #else:
        #    print("\nNo active constraints with penalties.")
    return y_p, active_penalties


@dataclass
class AnalysisResult:
    """
    Final output from slab (+ beam) analysis.

    This is what analysis() returns, what gets cached by EvalContext,
    and what IOH uses for optimization.

    Attributes
    ----------
    Objective values:
        y : float
            Unpenalized objective (weighted sum of y_cost and y_gwp).
        y_p : float
            Penalized objective (y * (1 + multiplier * penalty_sum) ^ exponent).
        y_cost : float
            Cost component [€/m² or similar].
        y_gwp : float
            Global Warming Potential component [kgCO2eq/m² or similar].

    Constraints:
        constraint_values : Dict[str, float]
            Utilization ratios for each constraint.
            Values <= 1.0 mean constraint is satisfied.
        penalties : Dict[str, float]
            Penalty multipliers for each active constraint.
            0.0 if satisfied, > 0.0 if violated.

    Status:
        computation_successful : bool
            True if analysis_impl ran without errors.
            False if structuralcodes or other calculations threw an exception.
            Set in analysis() wrapper based on whether analysis_impl succeeded.
        analysis_error : Optional[str]
            Error message if computation failed (e.g., invalid geometry).
            None if computation was successful.

    Parameters:
        params : Dict[str, Any]
            Decoded parameters that were used in this analysis.
            Useful for logging and debugging.

    Debug / additional info:
        As_prov_mm2 : float
            Total provided reinforcement area [mm²].
        rho_s : float
            Reinforcement ratio [‰].

    Properties:
        constraints_satisfied : bool
            True if all ACTIVE constraint_values are <= 1.0.
    """

    # Objective values
    y: float
    y_p: float
    y_cost: float
    y_gwp: float

    # Constraints
    active_constraint_values: dict[str, float]  # Only active constraints (respect problem_list.csv active flag)
    constraint_values: dict[str, float]
    penalties: dict[str, float]

    # Status
    computation_successful: bool
    analysis_error: str | None = None

    # Parameters for logging
    params: dict[str, Any] = field(default_factory=dict)

    # Debug / additional info
    As_prov_mm2: float = 0.0
    rho_s: float = 0.0

    @property
    def constraints_satisfied(self) -> bool:
        """True if all ACTIVE constraint utilization ratios are <= 1.0."""
        if not self.active_constraint_values:
            return True
        return all(v <= 1.0 for v in self.active_constraint_values.values())


    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary format for IOHProfiler compatibility.
        """
        return {
            "y": self.y,
            "y_p": self.y_p,
            "y_cost": self.y_cost,
            "y_gwp": self.y_gwp,
            "constraint_values": self.constraint_values,
            "active_constraint_values": self.active_constraint_values,
            "penalties_": self.penalties,
            # "violations" is the key expected by EvalContext and _make_violation_reader in problem_builder.
            # It must contain non-negative raw overshoot values: max(0, utilization - 1).
            # This is identical to self.penalties (computed as value-1 for violated constraints).
            "violations": self.penalties,
            "computation_successful": self.computation_successful,
            "analysis_error": self.analysis_error,
            "params": self.params,
            "As_prov_mm2": self.As_prov_mm2,
            "rho_s": self.rho_s,
            "constraints_satisfied": self.constraints_satisfied,
        }
