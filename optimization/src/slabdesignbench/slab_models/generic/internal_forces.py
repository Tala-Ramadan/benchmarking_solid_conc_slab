"""
internal_forces.py
==================

Internal force calculations for structural members.

This module provides code-agnostic calculations for:
- Beam internal forces (bending moment, shear, reactions)
- Slab combination forces (ULS, SLS characteristic/frequent/quasi-permanent)

The load combinations themselves are code-specific (EC0, etc.) and
are computed in codes/ec2_2004_de/combinations.py. This module uses the
resulting load values to compute internal forces.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class BeamForces:
    """
    Internal forces for a 1D member under a given load case.

    Attributes
    ----------
    M_max_kNm : float
        Maximum bending moment [kNm].
    V_max_kN : float
        Maximum shear force [kN].
    R_supports_kN : Sequence[float]
        Reactions at all supports [kN], ordered left → right.
    """

    M_max_kNm: float
    V_max_kN: float
    R_supports_kN: Sequence[float]


@dataclass(frozen=True)
class BeamCombinationForces:
    """
    Internal forces for a 1D member under a given load combination.

    Attributes
    ----------
    system : str
        Static system identifier (e.g., "simply_supported").
    ULS : BeamForces
        Forces under ULS combination.
    SLS_characteristic : BeamForces
        Forces under SLS characteristic combination.
    SLS_frequent : BeamForces
        Forces under SLS frequent combination.
    SLS_quasi_permanent : BeamForces
        Forces under SLS quasi-permanent combination.
    """

    system: str
    ULS: BeamForces
    SLS_characteristic: BeamForces
    SLS_frequent: BeamForces
    SLS_quasi_permanent: BeamForces


# =============================================================================
# PER-SYSTEM BASE SOLVERS
# =============================================================================

def _simply_supported_uniform_load(
    span_m: float,
    q_kN_m2: float,
    width_m: float = 1.0,
) -> BeamForces:
    """
    Internal forces for a simply supported beam/slab strip under uniform load.

    Parameters
    ----------
    span_m : float
        Span length [m].
    q_kN_m2 : float
        Area load [kN/m²].
    width_m : float
        Tributary width [m] (default 1.0 → per-metre strip).

    Returns
    -------
    BeamForces
        Calculated internal forces.
    """
    q_line = q_kN_m2 * width_m  # kN/m
    M_max = q_line * span_m**2 / 8.0  # kNm
    R = q_line * span_m / 2.0 / width_m  # kN/m (each support)
    V_max = R  # kN
    return BeamForces(M_max_kNm=M_max, V_max_kN=V_max, R_supports_kN=(R, R))


def _cantilever_uniform_load(
    span_m: float,
    q_kN_m2: float,
    width_m: float = 1.0,
) -> BeamForces:
    """
    Internal forces for a cantilever under uniform load.

    Parameters
    ----------
    span_m : float
        Cantilever length [m].
    q_kN_m2 : float
        Area load [kN/m²].
    width_m : float
        Tributary width [m] (default 1.0 → per-metre strip).

    Returns
    -------
    BeamForces
        Calculated internal forces.

    Notes
    -----
    M_max = q * L² / 2 at the fixed support.
    V_max = q * L at the fixed support.
    """
    q_line = q_kN_m2 * width_m  # kN/m
    M_max = q_line * span_m**2 / 2.0  # kNm
    R = q_line * span_m  # kN
    V_max = R
    return BeamForces(M_max_kNm=M_max, V_max_kN=V_max, R_supports_kN=(R,))


# =============================================================================
# PUBLIC DISPATCHER
# =============================================================================


def beam_forces(
    system: str,
    span_m: float,
    ULS_kN_m2: float,
    SLC_kN_m2: float,
    SLF_kN_m2: float,
    SLQ_kN_m2: float,
    width_m: float = 1.0,
) -> BeamCombinationForces:
    """
    Compute internal forces for all combinations for a one-way slab.

    Parameters
    ----------
    system : str
        Static system identifier, e.g. "simply_supported".
        Other systems can be added later ("cantilever", "two_span_continuous", ...).
    span_m : float
        Span length [m].
    ULS_kN_m2 : float
        ULS combination load [kN/m²].
    SLC_kN_m2 : float
        SLS characteristic combination load [kN/m²].
    SLF_kN_m2 : float
        SLS frequent combination load [kN/m²].
    SLQ_kN_m2 : float
        SLS quasi-permanent combination load [kN/m²].
    width_m : float
        Tributary width [m] (default 1.0 → per-metre strip).

    Returns
    -------
    BeamCombinationForces
        Internal forces for all combinations.

    Raises
    ------
    NotImplementedError
        If the static system is not implemented.
    """
    system_norm = system.lower().replace("-", "_").replace(" ", "_")

    if system_norm == "simply_supported":
        base_solver = _simply_supported_uniform_load
    elif system_norm == "cantilever":
        base_solver = _cantilever_uniform_load
    else:
        raise NotImplementedError(f"Static system '{system}' not implemented yet for one-way slabs.")

    return BeamCombinationForces(
        system=system,
        ULS=base_solver(span_m, ULS_kN_m2, width_m),
        SLS_characteristic=base_solver(span_m, SLC_kN_m2, width_m),
        SLS_frequent=base_solver(span_m, SLF_kN_m2, width_m),
        SLS_quasi_permanent=base_solver(span_m, SLQ_kN_m2, width_m),
    )
