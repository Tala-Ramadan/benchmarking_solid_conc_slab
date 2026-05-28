"""
checks_structural.py
====================

Structural code checks per EC2-2004 + German National Annex (NA.de).

This module provides functions for:
- Concrete cover (bond, corrosion, fire resistance)
- Reinforcement spacing limits (min/max)
- Minimum reinforcement (cracking, ductility)
- Maximum reinforcement
- Vibration (fundamental frequency)

All functions are specific to EC2-2004 + NA.de.
"""

import math

from structuralcodes.codes.ec2_2004 import kc_tension, w_max

# =============================================================================
# CONCRETE COVER
# =============================================================================


def c_nom(reinforcement_diameter_mm: float, fire_resistance_min: float) -> float:
    """
    Determine nominal concrete cover.

    Considers:
    - Bond requirements (c_min,b = diameter)
    - Corrosion (XC1 exposure class)
    - Fire resistance (EC2-1-2 Table 5.8)

    Assumptions:
    - Exposure class XC1
    - Aggregate size d_g = 16 mm
    - Δc_dev = 10 mm

    Parameters
    ----------
    reinforcement_diameter_mm : float
        Bar diameter [mm].
    fire_resistance_min : float
        Required fire resistance [min] (30, 60, or 90).

    Returns
    -------
    float
        Nominal cover c_nom [mm].
    """
    STATIC_MAP_CENTER_DISTANCE = {
        30: 10,
        60: 20,
        90: 30,
    }
    center_distance_mm = STATIC_MAP_CENTER_DISTANCE[fire_resistance_min]
    c_nom_1 = 10 + 10  # c_min,corrosion(XC1) + Δc_dev
    c_nom_2 = reinforcement_diameter_mm + 10  # c_min,bond + Δc_dev
    c_nom_3 = center_distance_mm - reinforcement_diameter_mm / 2  # a_fire (EC2-1-2 Tab. 5.8)
    c_nom_mm = max(c_nom_1, c_nom_2, c_nom_3)
    return c_nom_mm


# =============================================================================
# REINFORCEMENT SPACING LIMITS
# =============================================================================


def s_min_horizontal(reinforcement_diameter_mm: float) -> float:
    """
    Minimum horizontal clear spacing between bars.

    EC2-1-1, 8.2(2) + NA.de

    Note: Returns clearance (not center-to-center). Add bar diameter for center spacing.

    Parameters
    ----------
    reinforcement_diameter_mm : float
        Bar diameter [mm].

    Returns
    -------
    float
        Minimum clear spacing [mm].
    """
    # 2× diameter to allow overlap connections
    s_min_mm = max(
        reinforcement_diameter_mm * 2, 20
    )  # d_g= 16 mm is the assumed aggregate size -> s_min = d_g + 5 does not have to be considered (NA.de)
    return s_min_mm


def s_min_vertical(reinforcement_diameter_mm: float) -> float:
    """
    Minimum vertical clear spacing between layers.

    EC2-1-1, 8.2(2) + NA.de

    Parameters
    ----------
    reinforcement_diameter_mm : float
        Bar diameter [mm].

    Returns
    -------
    float
        Minimum clear spacing [mm].
    """
    s_min_mm = max(reinforcement_diameter_mm, 20, 16 + 5)
    return s_min_mm


def s_max_primary_direction(slab_depth_mm: float) -> float:
    """
    Maximum bar spacing in primary (spanning) direction.

    EC2-1-1, 9.3.1.1(3) + NA.de

    Parameters
    ----------
    slab_depth_mm : float
        Slab depth [mm].

    Returns
    -------
    float
        Maximum center-to-center spacing [mm].
    """
    if slab_depth_mm <= 150:
        return 150.0
    elif slab_depth_mm >= 250:
        return 250.0
    else:
        return float(slab_depth_mm)


def s_max_secondary_direction() -> float:
    """
    Maximum bar spacing in secondary (transverse) direction.

    EC2-1-1, 9.3.1.1(3) + NA.de

    Returns
    -------
    float
        Maximum center-to-center spacing [mm].
    """
    return 250.0


# =============================================================================
# REINFORCEMENT LIMITS
# =============================================================================


def a_smax() -> float:
    """
    Maximum reinforcement ratio.

    EC2-1-1 9.2.1.1(3) + NA.de

    Returns half of A_s,max = 0.08 A_c to enable overlapping.

    Returns
    -------
    float
        Maximum reinforcement ratio [-] (0.04 = 4%).
    """
    return 0.04


def k_crack_hydr(slab_depth_mm: float) -> float:
    """
    Factor k for crack width calculation (hydration effects).

    EC2-1-1 + NA.de

    Parameters
    ----------
    slab_depth_mm : float
        Slab depth [mm].

    Returns
    -------
    float
        Factor k [-].
    """
    if slab_depth_mm < 300:
        return 0.8
    elif slab_depth_mm > 800:
        return 0.5
    else:
        return 0.8 - (slab_depth_mm - 300) / (800 - 300) * (0.8 - 0.5)


def as_min_crack(
    slab_depth_mm: float,
    reinforcement_diameter_mm: float,
    c_nom_mm: float,
    fct_eff_MPa: float,
    A_ct_mm2: float,
) -> float:
    """
    Minimum reinforcement for crack control (initial cracking).

    EC2-1-1 Equation 7.1 + NA.de

    Parameters
    ----------
    slab_depth_mm : float
        Slab depth [mm].
    reinforcement_diameter_mm : float
        Bar diameter [mm].
    c_nom_mm : float
        Nominal cover [mm].
    fct_eff_MPa : float
        Effective tensile strength of concrete [MPa].
    A_ct_mm2 : float
        Area of concrete in tension zone [mm²].

    Returns
    -------
    float
        Minimum reinforcement area [mm²].
    """
    phi_smod = reinforcement_diameter_mm
    h_mm = slab_depth_mm
    h_cr_mm = h_mm
    d_mm = slab_depth_mm - (c_nom_mm + reinforcement_diameter_mm / 2)
    k_ = k_crack_hydr(slab_depth_mm)
    kc_ = kc_tension()

    # Modified reinforcement diameter (EC2-1-1 Eq. 7.7DE)
    phi_s = max(
        phi_smod * 2.9 / fct_eff_MPa,
        phi_smod * (8 * (h_mm - d_mm)) / (kc_ * k_ * h_cr_mm) * 2.9 / fct_eff_MPa,
    )

    # Allowable crack width (EC2-1-1 Tab. 7.1DE)
    w_k = w_max("XC1", "qp")

    # Allowable reinforcement stress (EC2-1-1 Tab. 7.2DE)
    sigma_s_MPa = math.sqrt(w_k * 3.48e6 / phi_s)

    as_min_crack_mm2 = kc_ * k_ * fct_eff_MPa * A_ct_mm2 / sigma_s_MPa
    return as_min_crack_mm2


def as_min_duct(
    slab_depth_mm: float,
    f_ctm_MPa: float,
    d_mm: float,
    fyk_MPa: float = 500.0,
) -> float:
    """
    Minimum reinforcement for ductility.

    EC2-1-1 9.2.1.1(1) + NA.de

    Ensures ductile failure (yielding of steel before concrete crushing).

    Parameters
    ----------
    slab_depth_mm : float
        Slab depth [mm].
    f_ctm_MPa : float
        Mean tensile strength of concrete [MPa].
    d_mm : float
        Effective depth [mm].
    fyk_MPa : float
        Characteristic yield strength of steel [MPa] (default 500).

    Returns
    -------
    float
        Minimum reinforcement area [mm²/m].
    """
    z = 0.9 * d_mm
    m_cr = f_ctm_MPa * slab_depth_mm**2 / 6 * 1000  # unit: Nmm/m
    as_min_duct = m_cr / (fyk_MPa * z)  # unit: mm²/m
    return as_min_duct


# =============================================================================
# SHEAR CAPACITY
# =============================================================================


def shear_capacity_Vrd_max(
    section_width_mm: float,
    d_mm: float,
    fck_MPa: float,
    fcd_MPa: float,
    cot_theta: float = 1.2,
) -> float:
    """
    Maximum shear capacity V_Rd,max (concrete strut crushing).

    EC2-1-1 Equation 6.9 + NA.de

    This is the upper limit of shear capacity regardless of stirrup reinforcement.
    The strut angle θ is typically between 21.8° (cot θ = 2.5) and 45° (cot θ = 1.0).

    Parameters
    ----------
    section_width_mm : float
        Section width [mm].
    d_mm : float
        Effective depth [mm].
    fck_MPa : float
        Characteristic concrete strength [MPa].
    fcd_MPa : float
        Design concrete strength [MPa].
    cot_theta : float, optional
        Cotangent of strut angle (default 2.5 = 21.8°, most efficient).

    Returns
    -------
    float
        Maximum shear capacity V_Rd,max [kN].

    Notes
    -----
    Formula (EC2-1-1 Eq. 6.9 + NA.de):
        V_Rd,max = b_w × z × ν_1 × f_cd / (cot θ + tan θ)

    where:
    - z = 0.9 × d (lever arm)
    - ν_1 = 0.75 × ν_2 (NA.de)
    - ν_2 = 1.0 for f_ck ≤ C50/60
    - ν_2 = (1.1 - f_ck / 500) for f_ck ≥ C55/67
    """
    # Strength reduction factor ν_2 (NA.de)
    if fck_MPa <= 50:
        nu_2 = 1.0
    else:
        nu_2 = 1.1 - fck_MPa / 500.0

    # ν_1 = 0.75 × ν_2 (NA.de)
    nu_1 = 0.75 * nu_2

    # Lever arm
    z_mm = 0.9 * d_mm

    # tan(θ) from cot(θ)
    tan_theta = 1.0 / cot_theta

    # V_Rd,max in N, convert to kN
    V_Rd_max_N = section_width_mm * z_mm * nu_1 * fcd_MPa / (cot_theta + tan_theta)
    V_Rd_max_kN = V_Rd_max_N / 1000.0

    return V_Rd_max_kN


# =============================================================================
# VIBRATION
# =============================================================================


def fundamental_frequency_slab_Hz(
    span_m: float,
    Ecm_MPa: float,
    Iyy_mm4: float,
    Ed_SLQ_kN_m2: float,
) -> float:
    """
    Fundamental frequency of a simply supported slab.

    Parameters
    ----------
    span_m : float
        Span length [m].
    Ecm_MPa : float
        Mean elastic modulus of concrete [MPa].
    Iyy_mm4 : float
        Second moment of area [mm⁴].
    Ed_SLQ_kN_m2 : float
        Quasi-permanent load [kN/m²].

    Returns
    -------
    float
        Fundamental frequency [Hz].
    """
    E_N_m2 = 1.1 * Ecm_MPa * 1e6  # N/m² (dynamic modulus ≈ 1.1 × Ecm)
    I_m4 = Iyy_mm4 * 1e-12  # m⁴
    L = span_m  # m
    mass = Ed_SLQ_kN_m2 * 1 * 1000 / 9.81  # kg/m

    # Simply supported first mode: f1 = (π/2) × √(EI / (m L⁴))
    return (math.pi / 2.0) * math.sqrt(E_N_m2 * I_m4 / (mass * L**4))
