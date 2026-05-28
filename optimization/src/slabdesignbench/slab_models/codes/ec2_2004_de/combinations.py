"""
combinations.py
===============

Load combination functions per EN 1990 + German National Annex.

This module provides functions for:
- ULS fundamental combination (STR/GEO)
- SLS characteristic combination
- SLS frequent combination
- SLS quasi-permanent combination

Note: Currently supports single variable action only.
Multi-action combinations can be added later.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

__all__ = [
    "uls_fundamental",
    "sls_characteristic",
    "sls_frequent",
    "sls_quasi_permanent",
]


# =============================================================================
# HELPER
# =============================================================================


def _scalar(x: Any) -> float:
    """
    Coerce scalars or 1-element sequences to float.

    Raises ValueError on longer sequences (multi-action not supported).
    """
    if isinstance(x, Sequence) and not isinstance(x, (str, bytes)):
        if len(x) == 0:
            raise ValueError("Empty sequence not allowed for scalar parameter.")
        if len(x) > 1:
            raise ValueError("Only a single live load is supported; got multiple values.")
        return float(x[0])
    return float(x)


# =============================================================================
# ULS COMBINATION
# =============================================================================


def uls_fundamental(
    Gk1: float,
    Gk2: float,
    Qk: float,
    *,
    gamma_G: float = 1.35,
    gamma_Q: float = 1.50,
) -> float:
    """
    ULS (STR/GEO) fundamental combination with single variable action.

    Ed = γ_G × (Gk1 + Gk2) + γ_Q × Qk

    Parameters
    ----------
    Gk1 : float
        Permanent action 1 (e.g., self-weight) [kN/m²].
    Gk2 : float
        Permanent action 2 (e.g., superimposed dead load) [kN/m²].
    Qk : float
        Variable action (live load) [kN/m²].
    gamma_G : float
        Partial factor for permanent actions (default 1.35).
    gamma_Q : float
        Partial factor for variable actions (default 1.50).

    Returns
    -------
    float
        Design load Ed [kN/m²].
    """
    G = float(Gk1) + float(Gk2)
    q = _scalar(Qk)
    return gamma_G * G + gamma_Q * q


# =============================================================================
# SLS COMBINATIONS
# =============================================================================


def sls_characteristic(
    Gk1: float,
    Gk2: float,
    Qk: float,
) -> float:
    """
    SLS characteristic combination with single variable action.

    Ed = (Gk1 + Gk2) + Qk

    Parameters
    ----------
    Gk1 : float
        Permanent action 1 [kN/m²].
    Gk2 : float
        Permanent action 2 [kN/m²].
    Qk : float
        Variable action [kN/m²].

    Returns
    -------
    float
        Service load Ed [kN/m²].
    """
    G = float(Gk1) + float(Gk2)
    q = _scalar(Qk)
    return G + q


def sls_frequent(
    Gk1: float,
    Gk2: float,
    Qk: float,
    *,
    psi1: float,
) -> float:
    """
    SLS frequent combination with single variable action.

    Ed = (Gk1 + Gk2) + ψ_1 × Qk

    Parameters
    ----------
    Gk1 : float
        Permanent action 1 [kN/m²].
    Gk2 : float
        Permanent action 2 [kN/m²].
    Qk : float
        Variable action [kN/m²].
    psi1 : float
        Frequent value factor ψ_1.

    Returns
    -------
    float
        Service load Ed [kN/m²].
    """
    G = float(Gk1) + float(Gk2)
    q = _scalar(Qk)
    p1 = _scalar(psi1)
    return G + p1 * q


def sls_quasi_permanent(
    Gk1: float,
    Gk2: float,
    Qk: float,
    *,
    psi2: float,
) -> float:
    """
    SLS quasi-permanent combination with single variable action.

    Ed = (Gk1 + Gk2) + ψ_2 × Qk

    Parameters
    ----------
    Gk1 : float
        Permanent action 1 [kN/m²].
    Gk2 : float
        Permanent action 2 [kN/m²].
    Qk : float
        Variable action [kN/m²].
    psi2 : float
        Quasi-permanent value factor ψ_2.

    Returns
    -------
    float
        Service load Ed [kN/m²].
    """
    G = float(Gk1) + float(Gk2)
    q = _scalar(Qk)
    p2 = _scalar(psi2)
    return G + p2 * q
