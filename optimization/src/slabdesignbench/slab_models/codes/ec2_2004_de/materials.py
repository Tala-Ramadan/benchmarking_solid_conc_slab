"""
materials.py
============

Material creation for structural analysis per EC2-2004 + NA.de.

This module:
- Creates concrete materials (ULS with ParabolaRectangle, SLS with Sargin)
- Creates reinforcement steel materials (ULS and SLS with elastic-plastic laws)
- Provides build_materials() to create complete material sets

Default values according to EC2-2004 + NA.de:
- γ_c = 1.5 (EC2 partial factor for concrete)
- γ_s = 1.15 (EC2 partial factor for steel)
- α_cc = 0.85 (Long-term effects on concrete, NA.de)
- B500A steel: f_yk = 500 MPa, f_tk = 525 MPa, E_s = 200 GPa

Note: Material laws for concrete are only viable up to f_ck = 90 MPa.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from structuralcodes import set_design_code
from structuralcodes.materials.concrete import create_concrete
from structuralcodes.materials.constitutive_laws import (
    ElasticPlastic,
    ParabolaRectangle,
    Sargin,
)
from structuralcodes.materials.reinforcement import create_reinforcement

# =============================================================================
# MATERIALSET DATACLASS
# =============================================================================


@dataclass
class MaterialSet:
    """
    Bundle of ULS/SLS materials for analysis.

    Contains concrete and steel materials at both limit states: ULS and SLS.

    Attributes
    ----------
    concrete_ULS : Any
        Concrete material for ULS (from structuralcodes).
    concrete_SLS : Any
        Concrete material for SLS (from structuralcodes).
    steel_ULS : Any
        Reinforcement steel for ULS.
    steel_SLS : Any
        Reinforcement steel for SLS.
    """

    concrete_ULS: Any
    concrete_SLS: Any
    steel_ULS: Any
    steel_SLS: Any


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _ec2_concrete_base(
    fck: float,
    gamma_c: float = 1.5,
    alpha_cc: float = 0.85,
    design_code: str | None = "ec2_2004",
):
    """
    Create a ConcreteEC2_2004 instance with EC2/NA.de defaults.

    Used internally to extract EC2-derived parameters.
    """
    kwargs = {"fck": fck, "gamma_c": gamma_c, "alpha_cc": alpha_cc}
    if design_code is not None:
        kwargs["design_code"] = design_code
    return create_concrete(**kwargs)


# =============================================================================
# CONCRETE MATERIALS
# =============================================================================


def concrete_uls(
    fck: float,
    gamma_c: float = 1.5,
    alpha_cc: float = 0.85,
    design_code: str | None = "ec2_2004",
):
    """
    EC2:2004 concrete for ULS with ParabolaRectangle constitutive law.

    Parameters
    ----------
    fck : float
        Characteristic compressive strength [MPa].
    gamma_c : float
        Partial factor for concrete (default 1.5).
    alpha_cc : float
        Coefficient for long-term effects (default 0.85).
    design_code : str or None
        Design code identifier (default "ec2_2004").

    Returns
    -------
    concrete material
        Concrete material for ULS analysis with design strength f_cd.
    """
    base = _ec2_concrete_base(fck=fck, gamma_c=gamma_c, alpha_cc=alpha_cc, design_code=design_code)

    # Extract EC2 parameters
    fc_uls = base.fcd()  # Design strength
    eps_0 = base.eps_c2  # Strain at fc
    eps_u = base.eps_cu2  # Ultimate strain
    n_pr = base.n_parabolic_rectangular  # Exponent

    # Create parabola-rectangle law
    law_uls = ParabolaRectangle(
        fc=fc_uls,
        eps_0=eps_0,
        eps_u=eps_u,
        n=n_pr,
        name=f"ParabolaRectangle_ULS_fck{int(fck)}",
    )

    conc_uls = create_concrete(
        fck=fck,
        gamma_c=gamma_c,
        alpha_cc=alpha_cc,
        design_code=design_code,
        constitutive_law=law_uls,
    )
    return conc_uls


def concrete_sls(
    fck: float,
    alpha_cc: float = 0.85,
    design_code: str | None = "ec2_2004",
):
    """
    EC2:2004 concrete for SLS with Sargin constitutive law.

    Parameters
    ----------
    fck : float
        Characteristic compressive strength [MPa].
    alpha_cc : float
        Coefficient for long-term effects (default 0.85).
    design_code : str or None
        Design code identifier (default "ec2_2004").

    Returns
    -------
    concrete material
        Concrete material for SLS analysis with mean strength f_cm.
        No gamma_c reduction (gamma_c=1.0).
    """
    base = _ec2_concrete_base(fck=fck, gamma_c=1.5, alpha_cc=alpha_cc, design_code=design_code)

    # Extract EC2 parameters
    fc_sls = base.fcm
    eps_c1 = base.eps_c1
    eps_cu1 = base.eps_cu1
    k_sargin = base.k_sargin

    # Create Sargin law
    law_sls = Sargin(
        fc=fc_sls,
        eps_c1=eps_c1,
        eps_cu1=eps_cu1,
        k=k_sargin,
        name=f"Sargin_SLS_fck{int(fck)}",
    )

    conc_sls = create_concrete(
        fck=fck,
        gamma_c=1.0,  # SLS: no safety factor on stresses
        alpha_cc=alpha_cc,
        design_code=design_code,
        constitutive_law=law_sls,
    )
    return conc_sls


# =============================================================================
# REINFORCEMENT STEEL MATERIALS
# =============================================================================


def reinforcement_steel_uls(
    fyk: float = 500.0,
    ftk: float = 525.0,
    Es: float = 200_000.0,
    gamma_s: float = 1.15,
    eps_uk: float = 0.025,
):
    """
    B500A reinforcement for ULS with elastic-plastic constitutive law.

    Uses design strengths f_yd, f_td and a design hardening modulus E_hd.

    Parameters
    ----------
    fyk : float
        Characteristic yield strength [MPa] (default 500).
    ftk : float
        Characteristic tensile strength [MPa] (default 525).
    Es : float
        Modulus of elasticity [MPa] (default 200000).
    gamma_s : float
        Partial factor for steel (default 1.15).
    eps_uk : float
        Characteristic strain at maximum load (default 0.025).

    Returns
    -------
    steel material
        Reinforcement steel for ULS analysis.
    """
    fyd = fyk / gamma_s
    ftd = ftk / gamma_s
    eps_uyd = fyd / Es
    eps_ud = eps_uk  # Same ultimate strain at "design" level
    Ehd = (ftd - fyd) / (eps_ud - eps_uyd)

    law_uls = ElasticPlastic(
        E=Es,
        fy=fyd,
        Eh=Ehd,
        eps_su=eps_ud,
        name="elastic_plastic_steel_ULS",
    )

    steel_uls = create_reinforcement(
        fyk=fyd,
        Es=Es,
        ftk=ftd,
        epsuk=eps_ud,
        constitutive_law=law_uls,
    )
    return steel_uls


def reinforcement_steel_sls(
    fyk: float = 500.0,
    ftk: float = 525.0,
    Es: float = 200_000.0,
    eps_uk: float = 0.025,
):
    """
    B500A reinforcement for SLS with elastic-plastic constitutive law.

    Uses characteristic strengths f_yk, f_tk and characteristic hardening modulus E_hk.

    Parameters
    ----------
    fyk : float
        Characteristic yield strength [MPa] (default 500).
    ftk : float
        Characteristic tensile strength [MPa] (default 525).
    Es : float
        Modulus of elasticity [MPa] (default 200000).
    eps_uk : float
        Characteristic strain at maximum load (default 0.025).

    Returns
    -------
    steel material
        Reinforcement steel for SLS analysis.
    """
    eps_uyk = fyk / Es
    Ehk = (ftk - fyk) / (eps_uk - eps_uyk)

    law_sls = ElasticPlastic(
        E=Es,
        fy=fyk,
        Eh=Ehk,
        eps_su=eps_uk,
        name="elastic_plastic_steel_SLS",
    )

    steel_sls = create_reinforcement(
        fyk=fyk,
        Es=Es,
        ftk=ftk,
        epsuk=eps_uk,
        constitutive_law=law_sls,
    )
    return steel_sls


# =============================================================================
# BUILD MATERIALS FUNCTION
# =============================================================================


def build_materials(
    fck_MPa: float,
    alpha_cc: float,
    fyk_MPa: float = 500.0,
    ftk_MPa: float = 525.0,
    Es_MPa: float = 200000.0,
    eps_uk: float = 0.025,
    gamma_c: float = 1.5,
    gamma_s: float = 1.15,
) -> MaterialSet:
    """
    Build complete material set for ULS and SLS analysis.

    This function creates ULS and SLS concrete and steel materials with appropriate constitutive laws.


    Parameters
    ----------
    fck_MPa : float
        Characteristic compressive strength of concrete [MPa].
    alpha_cc : float
        Coefficient for long-term effects on concrete strength (EC2 + NA.de: 0.85).

    Steel parameters (for reinforcement):
    fyk_MPa : float, optional
        Characteristic yield strength of reinforcement steel [MPa].
        Default 500 (B500A/B per EC2).
    ftk_MPa : float, optional
        Characteristic tensile strength of reinforcement steel [MPa].
        Default 525 (B500A per EC2 + NA.de).
    Es_MPa : float, optional
        Modulus of elasticity of reinforcement steel [MPa].
        Default 200000.
    eps_uk : float, optional
        Characteristic strain at maximum load [-].
        Default 0.025 (2.5% for B500A).

    Safety factors:
    gamma_c : float, optional
        Partial factor for concrete in ULS (EC2: 1.5).
    gamma_s : float, optional
        Partial factor for reinforcement steel in ULS (EC2: 1.15).

    Returns
    -------
    MaterialSet
        Bundle of ULS/SLS materials (concrete and steel).
    """
    # Set design code for structuralcodes
    set_design_code("ec2_2004")

    # Create concrete materials
    concrete_ULS = concrete_uls(fck=fck_MPa, alpha_cc=alpha_cc, gamma_c=gamma_c)
    concrete_SLS = concrete_sls(fck=fck_MPa, alpha_cc=alpha_cc)

    # Create steel materials
    steel_ULS = reinforcement_steel_uls(fyk=fyk_MPa, ftk=ftk_MPa, Es=Es_MPa, gamma_s=gamma_s, eps_uk=eps_uk)
    steel_SLS = reinforcement_steel_sls(fyk=fyk_MPa, ftk=ftk_MPa, Es=Es_MPa, eps_uk=eps_uk)

    return MaterialSet(
        concrete_ULS=concrete_ULS,
        concrete_SLS=concrete_SLS,
        steel_ULS=steel_ULS,
        steel_SLS=steel_SLS,
    )
