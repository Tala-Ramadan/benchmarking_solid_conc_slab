"""
time_effects.py
===============

Time-dependent material properties for concrete per EC2-2004 + NA.de.

This module handles:
- Creep: φ(t, t0) per EC2-2004 Annex B
- Shrinkage: ε_cs(t) per EC2-2004 Section 3.1.4
- Effective modulus: E_c,eff = E_cm / (1 + φ)

Note: These depend on both material properties AND geometry/environment,
which is why they are in a separate module from materials.py.

For notional size h_0, use ec2.h_0(Ac, u) directly from structuralcodes.
"""

from __future__ import annotations

import numpy as np
from structuralcodes.codes import ec2_2004 as ec2

# =============================================================================
# CREEP COEFFICIENT
# =============================================================================


def phi_creep(
    *,
    fcm_MPa: float,
    RH_percent: float,
    t0_days: float,
    t_days: float,
    h0_mm: float,
    cement_class: str = "N",
) -> float:
    """
    Compute the notional creep coefficient φ(t, t0) per EC2-1-1:2004 Annex B.

    Creep is the time-dependent increase in strain under sustained stress.

    Parameters
    ----------
    fcm_MPa : float
        Mean concrete compressive strength f_cm [MPa].
    RH_percent : float
        Ambient relative humidity [%] (e.g., 60.0 for 60%).
    t0_days : float
        Age of concrete at loading [days].
    t_days : float
        Age of concrete at time of interest [days].
    h0_mm : float
        Notional size h_0 [mm].
        Compute via ec2.h_0(Ac, u) where h_0 = 2*Ac/u.
    cement_class : {'S', 'N', 'R'}
        Cement class: 'S' (slow), 'N' (normal), 'R' (rapid).

    Returns
    -------
    float
        Creep coefficient φ(t, t0) [-].
    """
    # Strength-dependent factors (capped at 1.0 per EC2)
    alpha1 = min(ec2.alpha_1(fcm_MPa), 1.0)
    alpha2 = min(ec2.alpha_2(fcm_MPa), 1.0)
    alpha3 = min(ec2.alpha_3(fcm_MPa), 1.0)

    # Humidity / thickness effect on φ_0
    phi_RH_val = ec2.phi_RH(h0_mm, fcm_MPa, RH_percent, alpha1, alpha2)

    # Concrete strength effect on φ_0
    beta_fcm_val = ec2.beta_fcm(fcm_MPa)

    # Adjusted age at loading (t0,adj) from cement class
    alpha_cem = ec2.alpha_cement(cement_class)
    t0_adj_days = ec2.t0_adj(t0_days, alpha_cem)

    # Age-at-loading effect on φ_0
    beta_t0_val = ec2.beta_t0(t0_adj_days)

    # Notional creep coefficient φ_0
    phi_0_val = ec2.phi_0(phi_RH_val, beta_fcm_val, beta_t0_val)

    # Humidity / thickness effect on creep development
    beta_H_val = ec2.beta_H(h0_mm, fcm_MPa, RH_percent, alpha3)

    # Time-development factor β_c(t, t0)
    beta_c_val = ec2.beta_c(t0_adj_days, t_days, beta_H_val)

    # Final creep coefficient φ(t, t0)
    phi_val = ec2.phi(phi_0_val, beta_c_val)

    # structuralcodes may return a numpy scalar / array – force to float
    return float(phi_val)


# =============================================================================
# EFFECTIVE MODULUS
# =============================================================================


def effective_modulus(Ecm_MPa: float, phi: float) -> float:
    """
    Compute effective modulus of concrete accounting for creep.

    E_c,eff = E_cm / (1 + φ)

    Parameters
    ----------
    Ecm_MPa : float
        Mean modulus of elasticity of concrete [MPa].
        Typically from concrete_SLS.Ecm.
    phi : float
        Creep coefficient φ(t, t0) [-].
        From phi_creep().

    Returns
    -------
    float
        Effective modulus [MPa].
    """
    return Ecm_MPa / (1.0 + phi)


# =============================================================================
# SHRINKAGE STRAIN
# =============================================================================


def eps_cs_ec2(
    t_days: float | np.ndarray,
    t_s_days: float,
    h0_mm: float,
    RH_percent: float,
    fck_MPa: float,
    fcm_MPa: float,
    cement_class: str = "N",
) -> float | np.ndarray:
    """
    Total shrinkage strain ε_cs(t) per EC2-2004 Eq. (3.8).

    ε_cs = ε_cd(t) + ε_ca(t)

    where:
    - ε_cd: drying shrinkage (depends on RH, h0)
    - ε_ca: autogenous shrinkage (depends on fck)

    Parameters
    ----------
    t_days : float or np.ndarray
        Age of concrete [days] at which ε_cs is requested.
    t_s_days : float
        Age at start of drying (end of curing) [days].
        Typically 7 days.
    h0_mm : float
        Notional size h_0 [mm].
    RH_percent : float
        Relative humidity [%].
    fck_MPa : float
        Characteristic compressive strength [MPa].
    fcm_MPa : float
        Mean compressive strength [MPa].
    cement_class : {'S', 'N', 'R'}
        Cement class.

    Returns
    -------
    float or np.ndarray
        Total shrinkage strain ε_cs(t) [-], positive by EC2 convention.
        Returns same type as input (scalar or array).
    """
    # --- Drying shrinkage part ε_cd(t) ------------------------------------
    alpha_ds1 = ec2.alpha_ds1(cement_class)
    alpha_ds2 = ec2.alpha_ds2(cement_class)

    beta_RH = ec2.beta_RH(RH_percent)
    eps_cd0 = ec2.eps_cd_0(
        alpha_ds1=alpha_ds1,
        alpha_ds2=alpha_ds2,
        fcm=fcm_MPa,
        beta_RH=beta_RH,
        fcm_0=10,
    )

    k_h = ec2.k_h(h0_mm)
    beta_ds_t = ec2.beta_ds(t_days, t_s_days, h0_mm)
    eps_cd_t = ec2.eps_cd(beta_ds_t, k_h, eps_cd0)

    # --- Autogenous shrinkage part ε_ca(t) --------------------------------
    eps_ca_inf_val = ec2.eps_ca_inf(fck_MPa)
    beta_as_t = ec2.beta_as(t_days)
    eps_ca_t = ec2.eps_ca(beta_as_t, eps_ca_inf_val)

    # --- Total shrinkage strain ---------------------------------------------
    eps_cs_t = ec2.eps_cs(eps_cd_t, eps_ca_t)

    # Return as scalar if input was scalar
    if np.isscalar(t_days):
        return float(eps_cs_t)
    return np.asarray(eps_cs_t)
