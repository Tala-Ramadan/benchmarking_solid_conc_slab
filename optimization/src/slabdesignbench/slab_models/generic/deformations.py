"""
deformations.py
===============

Deflection calculations for structural members.

This module provides code-agnostic deflection calculations:
- Simplified method (constant EI)
- Integration method (moment-curvature based)
- Helper functions for curvature interpolation and integration

Code-specific shrinkage and creep calculations are in codes/ec2_2004_de/time_effects.py.
The results of these calculations are used here to calculate the effective modulus of concrete
and the shrinkage curvature.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

import numpy as np


class DeflectionResult(NamedTuple):
    """
    Container for two-stage SLS deflection results of a one-way slab.

    Attributes
    ----------
    w_t0_mm : float
        Instantaneous deflection (no creep, no shrinkage) [mm].
    w_tinf_mm : float
        Long-term deflection (with creep, shrinkage) [mm].
    w_increment_mm : float
        w_tinf - w_t0 (clamped ≥ 0) [mm].
    """

    w_t0_mm: float
    w_tinf_mm: float
    w_increment_mm: float


# =============================================================================
# SIMPLIFIED METHOD: Constant E*I (fully cracked) along beam length
# =============================================================================


def one_way_slab_deflection_simplified(
    system: str,
    span_m: float,
    Ed_SLQ_kN_m2: float,
    Ec_eff_MPa: float,
    Iyy_eff_mm4: float,
    slab_width_mm: float = 1000.0,
) -> float:
    """
    Simplified deflection calculation using constant EI.

    Parameters
    ----------
    system : str
        Static system identifier (only "simply_supported" implemented).
    span_m : float
        Span length [m].
    Ed_SLQ_kN_m2 : float
        Quasi-permanent load [kN/m²].
    Ec_eff_MPa : float
        Effective modulus of concrete [MPa].
    Iyy_eff_mm4 : float
        Effective (cracked) second moment of area [mm⁴].
    slab_width_mm : float
        Slab strip width [mm] (default 1000).

    Returns
    -------
    float
        Maximum deflection [mm].

    Raises
    ------
    NotImplementedError
        If system is not "simply_supported".
    """
    if system != "simply_supported":
        raise NotImplementedError("Only 'simply_supported' implemented for now.")

    # q_line [kN/m] from area load [kN/m²] over slab_width
    q_line_kN_m = Ed_SLQ_kN_m2 * slab_width_mm * 1e-3  # kN/m == N/mm
    w_max_mm = q_line_kN_m * ((span_m * 1e3) ** 4) / (76.8 * Ec_eff_MPa * Iyy_eff_mm4)

    return w_max_mm


# =============================================================================
# INTEGRATION METHOD HELPERS
# =============================================================================


def _interpolate_chi(
    M_query_Nmm: float,
    M_tab: Sequence[float],
    chi_tab: Sequence[float],
) -> float:
    """
    Linear interpolation chi(M) from tabulated moment–curvature data.

    Parameters
    ----------
    M_query_Nmm : float
        Moment value to query [Nmm].
    M_tab : Sequence[float]
        Tabulated moment values [Nmm], strictly monotonic.
    chi_tab : Sequence[float]
        Tabulated curvature values [1/mm].

    Returns
    -------
    float
        Interpolated curvature [1/mm].

    Raises
    ------
    ValueError
        If M_query is outside the tabulated range or tables are malformed.
    """
    if len(M_tab) != len(chi_tab) or len(M_tab) < 2:
        raise ValueError("M_tab and chi_tab must have same length >= 2")

    Mq = abs(M_query_Nmm)

    if Mq < M_tab[0] or Mq > M_tab[-1]:
        raise ValueError(
            f"Moment value={Mq} is outside of the moment–curvature range of the cross-section [{M_tab[0]}, {M_tab[-1]}]"
        )

    for i in range(1, len(M_tab)):
        if M_tab[i] >= Mq:
            M0, M1 = M_tab[i - 1], M_tab[i]
            c0, c1 = chi_tab[i - 1], chi_tab[i]
            t = (Mq - M0) / (M1 - M0)
            return c0 + t * (c1 - c0)

    raise RuntimeError("interpolate_chi: reached unreachable code; check M_tab monotonicity and bounds.")


def _simpson_integrate(
    x: np.ndarray,
    f: np.ndarray,
) -> float:
    """
    Composite Simpson integration ∫ f(x) dx over the whole interval.

    Parameters
    ----------
    x : np.ndarray
        X-coordinates, 1D, strictly increasing, equally spaced.
    f : np.ndarray
        Function values at x.

    Returns
    -------
    float
        Integral value.

    Raises
    ------
    ValueError
        If arrays have different lengths or number of subintervals is odd.
    """
    n = len(x)
    if n != len(f):
        raise ValueError("x and f must have same length")
    if n < 2:
        raise ValueError("Need at least two points for integration")

    h = x[1] - x[0]
    # n-1 subintervals; must be even
    if (n - 1) % 2 != 0:
        raise ValueError("Simpson requires an even number of subintervals")

    coeffs = np.ones(n)
    coeffs[1:-1:2] = 4.0  # odd indices
    coeffs[2:-1:2] = 2.0  # even internal indices

    return (h / 3.0) * np.sum(coeffs * f)


def _M_virtual_midspan_Nmm(x_mm: float, L_mm: float) -> float:
    """
    Virtual bending moment diagram for a unit load at midspan of a simply supported beam.

    Unit load P = 1 N at midspan => reactions R_A = R_B = 0.5 N.

    Parameters
    ----------
    x_mm : float
        Position along beam [mm].
    L_mm : float
        Total span [mm].

    Returns
    -------
    float
        Virtual moment M*(x) [Nmm].
    """
    half = 0.5 * L_mm
    if x_mm <= half:
        return 0.5 * x_mm
    else:
        return 0.5 * (L_mm - x_mm)


def shrinkage_curvature(
    eps_cs: float,
    Es_MPa: float,
    Ec_eff_MPa: float,
    Sy_reinf_mm3: float,
    Iyy_eff_mm4: float,
) -> float:
    """
    Shrinkage curvature calculation.

    chi_cs = eps_cs * alpha_e * S / I

    Parameters
    ----------
    eps_cs : float
        Free shrinkage strain [-] (positive by EC2 convention).
    Es_MPa : float
        Modulus of reinforcement steel [MPa].
    Ec_eff_MPa : float
        Effective modulus of concrete [MPa].
    Sy_reinf_mm3 : float
        First moment of area of reinforcement about section centroid [mm³].
    Iyy_eff_mm4 : float
        Second moment of area of (cracked) section [mm⁴].

    Returns
    -------
    float
        Shrinkage curvature χ_cs [1/mm].
    """
    alpha_e = Es_MPa / Ec_eff_MPa
    # Negative sign: negative Sy_reinf_mm3 leads to positive shrinkage in sagging direction
    return -eps_cs * alpha_e * Sy_reinf_mm3 / Iyy_eff_mm4


def _curvature_half_span(
    M_qp_half_Nmm: np.ndarray,
    cracked_half: np.ndarray,
    Ec_MPa: float,
    Iyy_gross_mm4: float,
    M_tab: Sequence[float],
    chi_tab: Sequence[float],
) -> np.ndarray:
    """
    Build curvature field κ(x) on half span for a given moment diagram and cracked mask.

    Parameters
    ----------
    M_qp_half_Nmm : np.ndarray
        Moment values on half span [Nmm].
    cracked_half : np.ndarray
        Boolean mask indicating cracked sections.
    Ec_MPa : float
        Modulus of concrete [MPa].
    Iyy_gross_mm4 : float
        Gross second moment of area [mm⁴].
    M_tab : Sequence[float]
        Tabulated moment values for cracked section [Nmm].
    chi_tab : Sequence[float]
        Tabulated curvature values for cracked section [1/mm].

    Returns
    -------
    np.ndarray
        Curvature values at each point [1/mm].
    """
    chi_y = np.zeros_like(M_qp_half_Nmm, dtype=float)

    for i, Mq in enumerate(M_qp_half_Nmm):
        if not cracked_half[i]:
            chi_y[i] = Mq / (Ec_MPa * Iyy_gross_mm4) if Mq != 0.0 else 0.0
        else:
            if Mq == 0.0:
                chi_y[i] = 0.0
            else:
                chi_y[i] = _interpolate_chi(Mq, M_tab, chi_tab)

    return chi_y


# =============================================================================
# INTEGRATION METHOD: Non-linear deflection with moment-curvature
# =============================================================================


def one_way_slab_deflection_integration(
    system: str,
    span_m: float,
    Ed_SLC_kN_m2: float,
    Ed_SLQ_kN_m2: float,
    Ec_MPa_t0: float,
    Ec_eff_MPa_tinf: float,
    M_cr_Nmm: float,
    Iyy_gross_mm4: float,
    M_tab: Sequence[float],
    chi_tab: Sequence[float],
    chi_cs_tinf_: float | None = None,
    chi_cs_t0_: float | None = None,
    slab_width_mm: float = 1000.0,
) -> DeflectionResult:
    """
    Non-linear deflection of a one-way simply supported slab using virtual work and Simpson.

    Two-stage SLS deflection:

    - w_t0_mm:
        * Cracking decided with quasi-permanent combination (M_SLQ).
        * Curvature from M_SLQ with Ec_MPa_t0 and cracked/uncracked model.
        * No creep, no shrinkage.

    - w_tinf_mm:
        * Cracking decided with characteristic combination (M_SLC).
        * Curvature from M_SLQ with Ec_eff_MPa_tinf and cracked/uncracked model.
        * Optional shrinkage curvature chi_cs_tinf added as constant term.

    Parameters
    ----------
    system : str
        Static system identifier (only "simply_supported" implemented).
    span_m : float
        Span length [m].
    Ed_SLC_kN_m2 : float
        SLS characteristic combination load [kN/m²].
    Ed_SLQ_kN_m2 : float
        SLS quasi-permanent combination load [kN/m²].
    Ec_MPa_t0 : float
        Concrete modulus at t=0 [MPa].
    Ec_eff_MPa_tinf : float
        Effective concrete modulus at t=∞ [MPa].
    M_cr_Nmm : float
        Cracking moment [Nmm].
    Iyy_gross_mm4 : float
        Gross second moment of area [mm⁴].
    M_tab : Sequence[float]
        Tabulated moment values from M-χ diagram [Nmm].
    chi_tab : Sequence[float]
        Tabulated curvature values from M-χ diagram [1/mm].
    chi_cs_tinf_ : float, optional
        Shrinkage curvature at t=∞ [1/mm].
    chi_cs_t0_ : float, optional
        Shrinkage curvature at t=0 [1/mm].
    slab_width_mm : float
        Slab strip width [mm] (default 1000).

    Returns
    -------
    DeflectionResult
        w_t0_mm, w_tinf_mm, w_increment_mm = max(w_tinf - w_t0, 0.0)

    Raises
    ------
    NotImplementedError
        If system is not "simply_supported".
    ValueError
        If moment-curvature interpolation fails (moment outside range).
    """
    if system != "simply_supported":
        raise NotImplementedError("Only 'simply_supported' is implemented for now.")

    # Simpson discretisation on half span
    n_points = len(M_tab) + 1
    if n_points < 3:
        n_points = 3

    # Ensure an even number of subintervals (n_points - 1)
    if (n_points - 1) % 2 != 0:
        n_points += 1

    L_mm = span_m * 1e3
    L_half_mm = 0.5 * L_mm
    x_half_mm = np.linspace(0.0, L_half_mm, n_points)

    # Real bending moments: characteristic and quasi-permanent
    slab_width = slab_width_mm

    def M_uniform_Nmm(q_N_mm: float, x_val_mm: float, L_val_mm: float) -> float:
        return q_N_mm * x_val_mm * (L_val_mm - x_val_mm) / 2.0

    q_SLC_N_mm = Ed_SLC_kN_m2 * 1e-3 * slab_width
    q_SLQ_N_mm = Ed_SLQ_kN_m2 * 1e-3 * slab_width

    M_SLC_half_Nmm = np.array([M_uniform_Nmm(q_SLC_N_mm, xi, L_mm) for xi in x_half_mm])
    M_SLQ_half_Nmm = np.array([M_uniform_Nmm(q_SLQ_N_mm, xi, L_mm) for xi in x_half_mm])

    # Cracked vs uncracked masks
    cracked_half_t0 = np.abs(M_SLQ_half_Nmm) >= M_cr_Nmm
    cracked_half_tinf = np.abs(M_SLC_half_Nmm) >= M_cr_Nmm

    # Curvature fields
    try:
        chi_t0_half = _curvature_half_span(
            M_qp_half_Nmm=M_SLQ_half_Nmm,
            cracked_half=cracked_half_t0,
            Ec_MPa=Ec_MPa_t0,
            Iyy_gross_mm4=Iyy_gross_mm4,
            M_tab=M_tab,
            chi_tab=chi_tab,
        )

        chi_tinf_half = _curvature_half_span(
            M_qp_half_Nmm=M_SLQ_half_Nmm,
            cracked_half=cracked_half_tinf,
            Ec_MPa=Ec_eff_MPa_tinf,
            Iyy_gross_mm4=Iyy_gross_mm4,
            M_tab=M_tab,
            chi_tab=chi_tab,
        )
    except ValueError as e:
        raise ValueError(f"[deflection_integration] {e}") from e

    # Add shrinkage curvatures
    if chi_cs_t0_ is not None:
        chi_t0_half = chi_t0_half + chi_cs_t0_

    if chi_cs_tinf_ is not None:
        chi_tinf_half = chi_tinf_half + chi_cs_tinf_

    # Virtual bending moment
    M_virtual_half_Nmm = np.array([_M_virtual_midspan_Nmm(xi, L_mm) for xi in x_half_mm])

    # Virtual work with Simpson
    integrand_t0_half = chi_t0_half * M_virtual_half_Nmm
    integrand_tinf_half = chi_tinf_half * M_virtual_half_Nmm

    delta_t0_half_mm = _simpson_integrate(x_half_mm, integrand_t0_half)
    delta_tinf_half_mm = _simpson_integrate(x_half_mm, integrand_tinf_half)

    # Symmetry: full-span deflection is 2 * half-span integral
    w_t0_mm = float(abs(2.0 * delta_t0_half_mm))
    w_tinf_mm = float(abs(2.0 * delta_tinf_half_mm))

    # Incremental deflection
    w_increment_mm = max(w_tinf_mm - w_t0_mm, 0.0)

    return DeflectionResult(
        w_t0_mm=w_t0_mm,
        w_tinf_mm=w_tinf_mm,
        w_increment_mm=w_increment_mm,
    )
