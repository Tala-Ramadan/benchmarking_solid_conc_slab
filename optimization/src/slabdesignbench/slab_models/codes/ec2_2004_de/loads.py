"""
loads.py
========

Load calculations per EC0 + German National Annex.

This module provides:
- Self-weight calculation for concrete elements
- ψ-factors per EN 1991-1-1 (building categories)
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "self_weight_kN_m2",
    "PsiFactors",
    "PSI_BY_CATEGORY",
]


# =============================================================================
# SELF-WEIGHT
# =============================================================================


def self_weight_kN_m2(slab_depth_mm: float, density_kN_m3: float = 25.0) -> float:
    """
    Permanent action from structural self-weight.

    Parameters
    ----------
    slab_depth_mm : float
        Slab depth [mm].
    density_kN_m3 : float
        Unit weight of concrete [kN/m³] (default 25.0 for normal-weight concrete).

    Returns
    -------
    float
        Self-weight [kN/m²].
    """
    return density_kN_m3 * (slab_depth_mm / 1000.0)


# =============================================================================
# ψ-FACTORS (EN 1991-1-1)
# =============================================================================


@dataclass(frozen=True)
class PsiFactors:
    """
    ψ-factors for load combinations.

    Attributes
    ----------
    psi0 : float
        Combination factor ψ_0.
    psi1 : float
        Frequent value factor ψ_1.
    psi2 : float
        Quasi-permanent value factor ψ_2.
    """

    psi0: float
    psi1: float
    psi2: float


# EN 1991-1-1 recommended ψ-factors (common building categories)
PSI_BY_CATEGORY = {
    "A": PsiFactors(psi0=0.7, psi1=0.5, psi2=0.3),  # Residential
    "B": PsiFactors(psi0=0.7, psi1=0.5, psi2=0.3),  # Office
    "C": PsiFactors(psi0=0.7, psi1=0.7, psi2=0.6),  # Assembly
    "D": PsiFactors(psi0=0.7, psi1=0.7, psi2=0.6),  # Shopping
    "E": PsiFactors(psi0=1.0, psi1=0.9, psi2=0.8),  # Storage
}
