"""
section_properties.py
=====================

Section property extraction and analysis wrappers.

This module provides wrappers around structuralcodes for:
- Bending capacity (M_Rd)
- SLS section properties (I_gross, I_eff, M_cr, etc.)

All wrappers convert exceptions to SectionAnalysisError,
which is caught in the main analysis() wrapper.
"""

from __future__ import annotations

from dataclasses import dataclass

from structuralcodes.sections import (
    GenericSection,
    calculate_elastic_cracked_properties,
)

from slabdesignbench.slab_models.generic.exceptions import SectionAnalysisError
from slabdesignbench.slab_models.generic.section_geometry import ReinfLayout

# =============================================================================
# DATACLASSES
# =============================================================================


@dataclass
class SLSSectionProperties:
    """
    SLS section properties (cracked and uncracked).

    Attributes
    ----------
    Iyy_gross_mm4 : float
        Gross (uncracked) second moment of area [mm⁴].
    Wy_gross_mm3 : float
        Gross (uncracked) section modulus [mm³].
    M_cr_Nmm : float
        Cracking moment [Nmm].
    Iyy_eff_mm4 : float
        Effective (cracked) second moment of area [mm⁴].
    cz_eff_mm : float
        Neutral axis from centroid (cracked section) [mm].
    Sy_reinf_mm3 : float
        First moment of area of reinforcement about cracked centroid [mm³].
    """

    Iyy_gross_mm4: float
    Wy_gross_mm3: float
    M_cr_Nmm: float
    Iyy_eff_mm4: float
    cz_eff_mm: float
    Sy_reinf_mm3: float


# =============================================================================
# ANALYSIS WRAPPERS (with error handling)
# =============================================================================


def compute_bending_capacity(section: GenericSection) -> float:
    """
    Compute bending capacity M_Rd.

    Parameters
    ----------
    section : GenericSection
        Section (typically ULS).

    Returns
    -------
    float
        Bending capacity [Nmm].

    Raises
    ------
    SectionAnalysisError
        If calculation fails.
    """
    try:
        result = section.section_calculator.calculate_bending_strength()
        return abs(result.m_y)
    except Exception as e:
        raise SectionAnalysisError(f"Bending capacity calculation failed: {e}") from e


def compute_sls_properties(
    section: GenericSection,
    layout: ReinfLayout,
    fctm_MPa: float,
    section_width_mm: float,
    section_depth_mm: float,
) -> SLSSectionProperties:
    """
    Compute SLS section properties (cracked and uncracked).

    Parameters
    ----------
    section : GenericSection
        Section with SLS materials.
    layout : ReinfLayout
        Reinforcement layout.
    fctm_MPa : float
        Mean tensile strength of concrete [MPa].
    section_width_mm : float
        Section width [mm].
    section_depth_mm : float
        Section depth [mm].

    Returns
    -------
    SLSSectionProperties
        Cracked/uncracked properties.

    Raises
    ------
    SectionAnalysisError
        If calculation fails.
    """
    try:
        # Gross properties
        gross_props = section.gross_properties
        Iyy_gross_mm4 = gross_props.iyy
        Wy_gross_mm3 = gross_props.iyy / max(gross_props.cz, section_depth_mm - gross_props.cz)
        M_cr_Nmm = Wy_gross_mm3 * fctm_MPa

        # Cracked properties
        cracked_props = calculate_elastic_cracked_properties(
            section=section,
            theta=0.0,
            return_cracked_section=False,
        )
        Iyy_eff_mm4 = cracked_props.iyy
        cz_eff_mm = cracked_props.cz

        # First moment of reinforcement about cracked centroid
        Sy_reinf_mm3 = 0.0
        for layer in layout.layers:
            if layer.active and layer.As_mm2 > 0:
                z_from_cracked = layer.z_mm - cz_eff_mm
                Sy_reinf_mm3 += layer.As_mm2 * z_from_cracked

        return SLSSectionProperties(
            Iyy_gross_mm4=Iyy_gross_mm4,
            Wy_gross_mm3=Wy_gross_mm3,
            M_cr_Nmm=M_cr_Nmm,
            Iyy_eff_mm4=Iyy_eff_mm4,
            cz_eff_mm=cz_eff_mm,
            Sy_reinf_mm3=Sy_reinf_mm3,
        )

    except AttributeError as e:
        if "exterior" in str(e):
            raise SectionAnalysisError("Cracked/gross properties failed due to invalid geometry.") from e
        raise
    except Exception as e:
        raise SectionAnalysisError(f"SLS properties calculation failed: {e}") from e
