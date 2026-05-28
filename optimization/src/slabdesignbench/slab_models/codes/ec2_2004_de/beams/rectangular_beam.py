"""
rectangular_beam.py
===================

Rectangular concrete beam analysis per EC2-2004 + German National Annex (NA.de).

This module contains everything needed for rectangular concrete beam analysis:
- RectangularConcreteBeam dataclass (typed input)
- BeamAnalysisResult dataclass (output)
- beam_analysis() function

Assumptions:
------------
- Beam width is FIXED at 300mm (see BEAM_WIDTH_MM constant)
- This simplifies reinforcement layout and is a reasonable engineering assumption because beam width is usually tied to column width
- Future versions may add variable width if needed

Usage (from slab analysis):
---------------------------
    from slabdesignbench.slab_models.codes.ec2_2004_de.beams import (
        RectangularConcreteBeam,
        beam_analysis,
    )

    # Create beam from slab reaction forces + beam params from CSV
    beam = RectangularConcreteBeam(
        beam_span_m=span_secondary_m,
        beam_depth_mm=params["beam_depth_mm"],
        beam_q_ULS_kN_m=forces.ULS.R_supports_kN[0],
        beam_q_SLQ_kN_m=forces.SLS_quasi_permanent.R_supports_kN[0],
        beam_q_SLC_kN_m=forces.SLS_characteristic.R_supports_kN[0],
        beam_Ec_eff_MPa=Ec_eff_MPa,
        beam_w_allowed_tinf_=params["w_allowed_tinf_"],
        beam_bar_diameter_mm=params["beam_reinforcement_diameter_mm"],
        beam_reinforcement_spacing_lay_1_mm=params["beam_reinforcement_spacing_lay_1_mm"],
        beam_reinforcement_spacing_lay_2_mm=params["beam_reinforcement_spacing_lay_2_mm"],
    )

    # Run beam analysis (pass materials from slab)
    beam_result = beam_analysis(beam, materials)

Note:
-----
Unlike slab analysis (which receives dict from CSV), beam analysis receives
a typed dataclass because it's called internally from slab analysis.
Errors in beam analysis will bubble up to slab analysis and be handled
by create_error_result() there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# structuralcodes for h_0
from structuralcodes.codes import ec2_2004 as ec2

from slabdesignbench.slab_models.codes.ec2_2004_de.checks_structural import (
    as_min_crack,
    as_min_duct,
    s_min_horizontal,
    s_min_vertical,
    shear_capacity_Vrd_max,
)

# EC2+DE specific helpers
from slabdesignbench.slab_models.codes.ec2_2004_de.materials import MaterialSet

# EC2+DE time effects
from slabdesignbench.slab_models.codes.ec2_2004_de.time_effects import eps_cs_ec2
from slabdesignbench.slab_models.generic.deformations import (
    one_way_slab_deflection_integration,
    shrinkage_curvature,
)
from slabdesignbench.slab_models.generic.exceptions import SectionAnalysisError
from slabdesignbench.slab_models.generic.internal_forces import beam_forces

# Generic helpers (reused from slab)
from slabdesignbench.slab_models.generic.section_geometry import (
    build_rectangular_section,
    build_reinf_layout,
)
from slabdesignbench.slab_models.generic.section_properties import (
    compute_bending_capacity,
    compute_sls_properties,
)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def c_nom_one_way_beam(reinforcement_diameter_mm: float, fire_resistance_min: float) -> float:
    """
    Determine nominal concrete cover for one-way slabs.

    Considers:
    - Bond requirements (c_min,b = diameter)
    - Corrosion (XC1 exposure class)
    - Fire resistance (EC2-1-2 Table 5.5)

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
        30: 25,
        60: 40,
        90: 55,
    }
    center_distance_mm = STATIC_MAP_CENTER_DISTANCE[int(fire_resistance_min)]
    c_nom_1 = 10 + 10  # c_min,corrosion(XC1) + Δc_dev
    c_nom_2 = reinforcement_diameter_mm + 10  # c_min,bond + Δc_dev
    c_nom_3 = center_distance_mm - reinforcement_diameter_mm / 2  # a_fire (EC2-1-2 Tab. 5.5)
    c_nom_mm = max(c_nom_1, c_nom_2, c_nom_3)
    return c_nom_mm


# =============================================================================
# CONSTANTS
# =============================================================================

BEAM_WIDTH_MM: float = 300.0  # Fixed beam width [mm] - simplifies reinforcement layout

# =============================================================================
# INPUT DATACLASS
# =============================================================================


@dataclass
class RectangularConcreteBeam:
    """
    Input parameters for rectangular concrete beam analysis.

    This is a typed dataclass (not a dict) because beam analysis is called
    internally from slab analysis, not from the CSV/optimizer interface.

    Note: Beam width is FIXED at BEAM_WIDTH_MM (300mm).

    Attributes
    ----------
    Static system:
        beam_static_system_ : str
            Static system ("simply_supported" only for now).
        beam_span_m : float
            Beam span [m] (typically = slab span_secondary_m).

    Loads (from slab reactions):
        beam_q_ULS_kN_m : float
            ULS line load [kN/m] from slab reactions.
        beam_q_SLQ_kN_m : float
            SLS quasi-permanent line load [kN/m].
        beam_q_SLC_kN_m : float
            SLS characteristic line load [kN/m].

    Creep / SLS parameters:
        beam_Ec_eff_MPa : float
            Effective E-modulus [MPa] accounting for creep (from slab analysis).
        beam_w_allowed_tinf_ : float
            Deflection limit L/n (default 250 -> L/250 per EC2).

    Geometry (from CSV parameters):
        beam_depth_mm : float
            Beam depth [mm].

    Reinforcement (from CSV parameters):
        beam_bar_diameter_mm : float
            Bar diameter [mm].
        beam_reinforcement_spacing_lay_1_mm : float
            Spacing of layer 1 [mm].
        beam_reinforcement_spacing_lay_2_mm : float
            Spacing of layer 2 [mm].
        beam_reinforcement_layer_active_2_ : float
            Whether layer 2 is active (0 or 1).

    Fire resistance:
        beam_fire_resistance_min : float
            Fire resistance class [min] for cover calculation.
    """

    # Static system
    beam_static_system_: str = "simply_supported"
    beam_span_m: float = 5.0

    # Loads (from slab reactions)
    beam_q_ULS_kN_m: float = 0.0
    beam_q_SLQ_kN_m: float = 0.0
    beam_q_SLC_kN_m: float = 0.0

    # Creep-adjusted E-modulus (from slab - passed for deflection calc)
    beam_Ec_eff_MPa: float = 0.0

    # Deflection limits (from slab parameters)
    beam_w_allowed_tinf_: float = 250.0  # L/250 = default per EC2

    # Geometry (from CSV - width is fixed at BEAM_WIDTH_MM)
    beam_depth_mm: float = 500.0

    # Reinforcement (from CSV)
    beam_bar_diameter_mm: float = 16.0
    beam_reinforcement_spacing_lay_1_mm: float = 50.0
    beam_reinforcement_spacing_lay_2_mm: float = 50.0
    beam_reinforcement_layer_active_2_: float = 0.0  # 0 or 1

    # Fire resistance (inherit from slab or fixed)
    beam_fire_resistance_min: float = 90.0


# =============================================================================
# RESULT DATACLASS
# =============================================================================


@dataclass
class BeamAnalysisResult:
    """
    Output from beam analysis.

    Attributes
    ----------
    Volumes (per beam):
        Vs_total_per_beam_m3 : float
            Total steel volume per beam [m³].
        Vc_per_beam_m3 : float
            Concrete volume per beam [m³].

    Constraints:
        constraint_values : Dict[str, float]
            Utilization ratios for beam constraints.
            Values <= 1.0 mean constraint is satisfied.

    Status:
        computation_successful : bool
            True if beam analysis ran without errors.
        analysis_error : Optional[str]
            Error message if failed.
    """

    # Volumes per beam (for objective calculation in slab analysis)
    Vs_total_per_beam_m3: float = 0.0
    Vc_per_beam_m3: float = 0.0

    # Constraints
    constraint_values: dict[str, float] = field(default_factory=dict)

    # Status
    computation_successful: bool = True
    analysis_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "Vs_total_per_beam_m3": self.Vs_total_per_beam_m3,
            "Vc_per_beam_m3": self.Vc_per_beam_m3,
            "constraint_values": self.constraint_values,
            "computation_successful": self.computation_successful,
            "analysis_error": self.analysis_error,
        }


# =============================================================================
# ANALYSIS FUNCTION
# =============================================================================


def beam_analysis(
    beam: RectangularConcreteBeam,
    materials: MaterialSet,
) -> BeamAnalysisResult:
    """
    Analyze rectangular concrete beam per EC2-2004 + NA.de.

    Called internally from slab analysis to compute beam contributions
    to the objective function and constraints.

    Parameters
    ----------
    beam : RectangularConcreteBeam
        Typed input with all beam parameters.
    materials : MaterialSet
        Materials from slab analysis (concrete + steel, ULS + SLS).

    Returns
    -------
    BeamAnalysisResult
        Beam analysis results including volumes and constraints.
    """
    try:
        return _beam_analysis_impl(beam, materials)
    except Exception as e:
        return BeamAnalysisResult(
            Vs_total_per_beam_m3=1e12,
            Vc_per_beam_m3=1e12,
            constraint_values={
                "beam_bending_capacity_": 1e6,
                "beam_shear_VRd_max_": 1e6,
                "beam_min_width_fire_": 1e6,
                "beam_min_reinforcement_crack_": 1e6,
                "beam_min_reinforcement_duct_": 1e6,
                "beam_max_reinforcement_": 1e6,
                "beam_min_spacing_lay_1_": 1e6,
                "beam_min_spacing_lay_2_": 1e6,
                "beam_deflection_tinf_": 1e6,
            },
            computation_successful=False,
            analysis_error=str(e),
        )


def _beam_analysis_impl(
    beam: RectangularConcreteBeam,
    materials: MaterialSet,
) -> BeamAnalysisResult:
    """
    Implementation of beam analysis.

    Note: Beam width is fixed at BEAM_WIDTH_MM (300mm).
    """
    # Use fixed beam width
    beam_width_mm = BEAM_WIDTH_MM

    # =========================================================================
    # GEOMETRY & REINFORCEMENT LAYOUT
    # =========================================================================
    concrete_cover_mm = c_nom_one_way_beam(
        beam.beam_bar_diameter_mm,
        beam.beam_fire_resistance_min,
    )
    vertical_spacing_mm = s_min_vertical(beam.beam_bar_diameter_mm) + beam.beam_bar_diameter_mm

    layer_active_flags = [1.0, beam.beam_reinforcement_layer_active_2_]
    target_spacings_mm = [
        beam.beam_reinforcement_spacing_lay_1_mm,
        beam.beam_reinforcement_spacing_lay_2_mm,
    ]

    layout = build_reinf_layout(
        section_width_mm=beam_width_mm,
        section_depth_mm=beam.beam_depth_mm,
        concrete_cover_mm=concrete_cover_mm,
        bar_diameter_mm=beam.beam_bar_diameter_mm,
        vertical_spacing_mm=vertical_spacing_mm,
        target_spacings_mm=target_spacings_mm,
        layer_active_flags=layer_active_flags,
    )

    d_mm = layout.d_mm
    As_bot_mm2 = layout.As_total_mm2

    # =========================================================================
    # ULS SECTION
    # =========================================================================
    section_ULS = build_rectangular_section(
        section_width_mm=beam_width_mm,
        section_depth_mm=beam.beam_depth_mm,
        concrete_material=materials.concrete_ULS,
        steel_material=materials.steel_ULS,
        layer_n_bars=[lay.n_bars for lay in layout.layers],
        layer_spacings_mm=[lay.spacing_mm for lay in layout.layers],
        layer_active=[lay.active for lay in layout.layers],
        layer_z_mm=[lay.z_mm for lay in layout.layers],
        bar_diameter_mm=beam.beam_bar_diameter_mm,
    )

    # =========================================================================
    # SLS SECTION
    # =========================================================================
    section_SLS = build_rectangular_section(
        section_width_mm=beam_width_mm,
        section_depth_mm=beam.beam_depth_mm,
        concrete_material=materials.concrete_SLS,
        steel_material=materials.steel_SLS,
        layer_n_bars=[lay.n_bars for lay in layout.layers],
        layer_spacings_mm=[lay.spacing_mm for lay in layout.layers],
        layer_active=[lay.active for lay in layout.layers],
        layer_z_mm=[lay.z_mm for lay in layout.layers],
        bar_diameter_mm=beam.beam_bar_diameter_mm,
    )

    # =========================================================================
    # INTERNAL FORCES
    # =========================================================================
    forces = beam_forces(
        system=beam.beam_static_system_,
        span_m=beam.beam_span_m,
        ULS_kN_m2=beam.beam_q_ULS_kN_m,
        SLC_kN_m2=beam.beam_q_SLC_kN_m,
        SLF_kN_m2=beam.beam_q_SLQ_kN_m,
        SLQ_kN_m2=beam.beam_q_SLQ_kN_m,
        width_m=1.0,  # Forces per meter of beam
    )
    M_ULS_kNm = forces.ULS.M_max_kNm
    V_ULS_kN = forces.ULS.V_max_kN

    # =========================================================================
    # CONSTRAINT: ULS BENDING CAPACITY
    # =========================================================================
    M_Rd_Nmm = compute_bending_capacity(section_ULS)
    const_bending_capacity_ = (M_ULS_kNm * 1e6) / M_Rd_Nmm

    # =========================================================================
    # CONSTRAINT: ULS SHEAR (V_Rd,max)
    # =========================================================================
    V_Rd_max_kN = shear_capacity_Vrd_max(
        section_width_mm=beam_width_mm,
        d_mm=d_mm,
        fck_MPa=materials.concrete_ULS.fck,
        fcd_MPa=materials.concrete_ULS.fcd(),
        cot_theta=1.2,
    )
    const_shear_Vrd_max_ = V_ULS_kN / V_Rd_max_kN

    # =========================================================================
    # CONSTRAINT: FIRE RESISTANCE (MIN BEAM WIDTH)
    # =========================================================================
    # EC2-1-2 Tab. 5.5: min beam width for fire resistance class
    MIN_WIDTH_FIRE_MAP = {30: 80, 60: 120, 90: 150}
    min_width_fire_mm = MIN_WIDTH_FIRE_MAP[int(beam.beam_fire_resistance_min)]
    const_min_width_fire_ = min_width_fire_mm / beam_width_mm

    # =========================================================================
    # CONSTRAINT: MIN REINFORCEMENT (CRACK WIDTH)
    # =========================================================================
    As_min_crack_mm2 = as_min_crack(
        slab_depth_mm=beam.beam_depth_mm,
        reinforcement_diameter_mm=beam.beam_bar_diameter_mm,
        c_nom_mm=concrete_cover_mm,
        fct_eff_MPa=0.5 * materials.concrete_SLS.fctm,
        A_ct_mm2=beam.beam_depth_mm * beam_width_mm,
    )
    const_as_min_crack_ = (As_min_crack_mm2 / 2) / As_bot_mm2

    # =========================================================================
    # CONSTRAINT: MIN REINFORCEMENT (DUCTILITY)
    # =========================================================================
    As_min_duct_mm2 = as_min_duct(
        slab_depth_mm=beam.beam_depth_mm,
        f_ctm_MPa=materials.concrete_SLS.fctm,
        d_mm=d_mm,
    )
    const_as_min_duct_ = As_min_duct_mm2 / As_bot_mm2

    # =========================================================================
    # CONSTRAINT: MAX REINFORCEMENT
    # =========================================================================
    As_max_mm2 = 0.08 * beam.beam_depth_mm * beam_width_mm
    As_prov_mm2 = As_bot_mm2 + As_min_crack_mm2 / 2
    const_as_max_ = As_prov_mm2 / As_max_mm2

    # =========================================================================
    # CONSTRAINT: MIN REINFORCEMENT SPACING
    # =========================================================================
    const_s_min = []
    s_min_req_mm = s_min_horizontal(beam.beam_bar_diameter_mm)
    for lay in layout.layers:
        if not lay.active:
            const_s_min.append(1.0)
        else:
            const_s_min.append(s_min_req_mm / lay.spacing_mm)

    # =========================================================================
    # CONSTRAINT: DEFLECTION (t_inf - integration method with shrinkage)
    # =========================================================================
    sls_props = compute_sls_properties(
        section=section_SLS,
        layout=layout,
        fctm_MPa=materials.concrete_SLS.fctm,
        section_width_mm=beam_width_mm,
        section_depth_mm=beam.beam_depth_mm,
    )
    Iyy_gross_mm4 = sls_props.Iyy_gross_mm4
    Iyy_eff_mm4 = sls_props.Iyy_eff_mm4
    M_cr_Nmm = sls_props.M_cr_Nmm
    Sy_reinf_mm3 = sls_props.Sy_reinf_mm3

    # Notional size h0 for beam (3-sided drying: bottom + 2 sides)
    Ac_mm2 = beam_width_mm * beam.beam_depth_mm
    u_mm = beam_width_mm + 2 * beam.beam_depth_mm  # Exposed perimeter (3-sided)
    h0_mm = ec2.h_0(Ac_mm2, u_mm)

    # Shrinkage strain and curvature at t=∞ (50 years, RH=50%)
    eps_cs_tinf = float(
        eps_cs_ec2(
            t_days=50 * 365,
            t_s_days=7.0,
            h0_mm=h0_mm,
            RH_percent=50.0,
            fck_MPa=materials.concrete_SLS.fck,
            fcm_MPa=materials.concrete_SLS.fcm,
            cement_class="N",
        )
    )
    chi_cs_tinf = shrinkage_curvature(
        eps_cs=eps_cs_tinf,
        Es_MPa=materials.steel_SLS.Es,
        Ec_eff_MPa=beam.beam_Ec_eff_MPa,
        Sy_reinf_mm3=Sy_reinf_mm3,
        Iyy_eff_mm4=Iyy_eff_mm4,
    )

    # Moment-curvature diagram for cracked section
    try:
        mc_diagram = section_SLS.section_calculator.calculate_moment_curvature(
            theta=0.0,
            chi_first=1e-8,
            num_pre_yield=10,
            num_post_yield=10,
        )
        M_tab_Nmm = [float(-m) for m in mc_diagram.m_y]
        chi_tab = [float(-c) for c in mc_diagram.chi_y]
    except StopIteration as e:
        raise SectionAnalysisError("Beam M-χ did not converge") from e
    except AttributeError as e:
        if "exterior" in str(e):
            raise SectionAnalysisError("Beam M-χ invalid geometry") from e
        raise
    except Exception as e:
        raise SectionAnalysisError(f"Beam M-χ failed: {e}") from e

    # Deflection via integration (including shrinkage)
    try:
        deflection_result = one_way_slab_deflection_integration(
            system=beam.beam_static_system_,
            span_m=beam.beam_span_m,
            Ed_SLC_kN_m2=beam.beam_q_SLC_kN_m,
            Ed_SLQ_kN_m2=beam.beam_q_SLQ_kN_m,
            Ec_MPa_t0=materials.concrete_SLS.Ecm,
            Ec_eff_MPa_tinf=beam.beam_Ec_eff_MPa,
            M_cr_Nmm=M_cr_Nmm,
            Iyy_gross_mm4=Iyy_gross_mm4,
            M_tab=M_tab_Nmm,
            chi_tab=chi_tab,
            chi_cs_tinf_=chi_cs_tinf,
            chi_cs_t0_=None,  # Not needed - only checking w_tinf
            slab_width_mm=1000.0,  # 1m width (line load already per meter)
        )
        w_tinf_mm = deflection_result.w_tinf_mm
    except ValueError as e:
        raise SectionAnalysisError(f"Beam deflection integration failed: {e}") from e

    w_allowed_tinf_mm = beam.beam_span_m * 1e3 / beam.beam_w_allowed_tinf_
    const_deflection_tinf_ = w_tinf_mm / w_allowed_tinf_mm

    # =========================================================================
    # VOLUMES (for objective calculation in slab analysis)
    # =========================================================================
    As_top_mm2 = As_min_crack_mm2 / 2
    As_total_mm2 = As_bot_mm2 + As_top_mm2

    Vs_total_per_beam_m3 = As_total_mm2 * 1e-6 * beam.beam_span_m
    Vc_per_beam_m3 = (beam.beam_depth_mm * beam_width_mm) * 1e-6 * beam.beam_span_m - Vs_total_per_beam_m3

    # =========================================================================
    # RETURN RESULT
    # =========================================================================
    constraint_values = {
        "beam_bending_capacity_": const_bending_capacity_,
        "beam_shear_VRd_max_": const_shear_Vrd_max_,
        "beam_min_width_fire_": const_min_width_fire_,
        "beam_min_reinforcement_crack_": const_as_min_crack_,
        "beam_min_reinforcement_duct_": const_as_min_duct_,
        "beam_max_reinforcement_": const_as_max_,
        "beam_min_spacing_lay_1_": const_s_min[0],
        "beam_min_spacing_lay_2_": const_s_min[1],
        "beam_deflection_tinf_": const_deflection_tinf_,
    }

    return BeamAnalysisResult(
        Vs_total_per_beam_m3=Vs_total_per_beam_m3,
        Vc_per_beam_m3=Vc_per_beam_m3,
        constraint_values=constraint_values,
        computation_successful=True,
        analysis_error=None,
    )
