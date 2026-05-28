"""
analysis_ec2_de.py
==================

Solid one-way spanning concrete slab analysis.

Design code: EC2-2004 + German National Annex (NA.de)

Other national annexes can be implemented by creating additional
analysis files (e.g., analysis_ec2_uk.py for United Kingdom).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle

# structuralcodes
from structuralcodes.codes import ec2_2004 as ec2

# IOH / optimization problem builder utilities
from slabdesignbench.optimization_problem_builder.import_problem_from_csv import (
    _req_param,
)
from slabdesignbench.slab_models.codes.ec2_2004_de.beams import (
    RectangularConcreteBeam,
    beam_analysis,
)
from slabdesignbench.slab_models.codes.ec2_2004_de.checks_structural import (
    as_min_crack,
    as_min_duct,
    c_nom,
    fundamental_frequency_slab_Hz,
    s_max_primary_direction,
    s_min_horizontal,
    s_min_vertical,
    shear_capacity_Vrd_max,
)
from slabdesignbench.slab_models.codes.ec2_2004_de.combinations import (
    sls_characteristic,
    sls_frequent,
    sls_quasi_permanent,
    uls_fundamental,
)
from slabdesignbench.slab_models.codes.ec2_2004_de.loads import (
    PSI_BY_CATEGORY,
    self_weight_kN_m2,
)

# EC2+DE specific modules
from slabdesignbench.slab_models.codes.ec2_2004_de.materials import build_materials
from slabdesignbench.slab_models.codes.ec2_2004_de.time_effects import (
    eps_cs_ec2,
    phi_creep,
)
from slabdesignbench.slab_models.generic.deformations import (
    one_way_slab_deflection_integration,
    shrinkage_curvature,
)

# Generic modules (code-agnostic)
from slabdesignbench.slab_models.generic.exceptions import (
    SectionAnalysisError,
    create_error_result,
)
from slabdesignbench.slab_models.generic.input_dataclasses import (
    SolidSlabOneWayConcreteSlab,
    validate_params,
)
from slabdesignbench.slab_models.generic.internal_forces import beam_forces
from slabdesignbench.slab_models.generic.result_dataclasses import (
    AnalysisResult,
    compute_penalized_objective,
)
from slabdesignbench.slab_models.generic.section_geometry import (
    build_rectangular_section,
    build_reinf_layout,
)
from slabdesignbench.slab_models.generic.section_properties import (
    compute_bending_capacity,
    compute_sls_properties,
)


def analysis(params: dict, constraints: dict) -> dict:
    """
    Wrapper that centralises all StructuralCodes errors for this problem.

    Anything thrown by StructuralCodes or our helpers becomes
    a `SectionAnalysisError` and is handled here.
    """
    try:
        return _analysis_impl(params, constraints=constraints)

    except SectionAnalysisError as e:
        # Centralised handling: mark this design as unusable
        # Note: avoid Unicode chars (like χ) in print for Windows compatibility
        print(f"[analysis] SectionAnalysisError: {str(e).encode('ascii', 'replace').decode()}")
        return create_error_result(params, constraints, str(e))

    except Exception as e:
        # Safety net for anything not properly caught
        print(f"[analysis] Unexpected error: {e}")
        return create_error_result(params, constraints, f"Unexpected error: {e}")

# =============================================================================
# PLOTTING MODE (for optional cross-section visualization)
# =============================================================================
_PLOT_CROSS_SECTION_MODE = "none"

def set_plot_cross_section_mode(mode: str) -> None:
    mode_norm = str(mode).strip().lower()
    if mode_norm not in {"none", "all", "best"}:
        raise ValueError(f"Unsupported plot mode '{mode}'. Choose 'none', 'all', or 'best'.")
    global _PLOT_CROSS_SECTION_MODE
    _PLOT_CROSS_SECTION_MODE = mode_norm
    
# =============================================================================
# MODULE-LEVEL CONSTANTS (mappings from CSV codes to values)
# =============================================================================
STATIC_SYSTEM_MAP = {0.0: "simply_supported", 1.0: "cantilever"}
LOAD_CATEGORY_MAP = {0.0: "A", 1.0: "B", 2.0: "C", 3.0: "D", 4.0: "E"}
MIN_DEPTH_FIRE_MAP = {
    30.0: 60,
    60.0: 80,
    90.0: 100,
}  # fire resistance [min] -> min slab depth [mm] EC2-1-2 Tab. 5.8

# Note: alpha_cc_ is defined as a constant in SolidSlabOneWayConcreteSlab dataclass
# Access it via: SolidSlabOneWayConcreteSlab.__dataclass_fields__['alpha_cc_'].default

def _parse_float_list(s: str) -> list[float]:
    """Parse comma-separated string into list of floats."""
    return [float(x.strip()) for x in s.split(",") if x.strip()]


def _build_cost_gwp_maps(params: dict) -> tuple[dict[float, float], dict[float, float]]:
    """
    Build concrete cost and GWP lookup maps from CSV parameters.

    Returns
    -------
    cost_map : dict[float, float]
        Maps concrete grade (MPa) -> cost (EUR/m³)
    gwp_map : dict[float, float]
        Maps concrete grade (MPa) -> GWP (kgCO2e/m³)
    """
    grades = _parse_float_list(params["concrete_grade_list_MPa"])
    costs = _parse_float_list(params["concrete_cost_eur_m3"])
    gwps = _parse_float_list(params["concrete_gwp_kgco2e_m3"])

    if len(grades) != len(costs):
        raise ValueError(
            f"concrete_grade_list_MPa has {len(grades)} entries, "
            f"concrete_cost_eur_m3 has {len(costs)} – lengths must match."
        )
    if len(grades) != len(gwps):
        raise ValueError(
            f"concrete_grade_list_MPa has {len(grades)} entries, "
            f"concrete_gwp_kgco2e_m3 has {len(gwps)} – lengths must match."
        )

    return dict(zip(grades, costs, strict=True)), dict(zip(grades, gwps, strict=True))



def _analysis_impl(params: dict, *, constraints: dict) -> dict:
    """
    Main analysis implementation for solid one-way concrete slab according to EC2-2004 + German National Annex (NA.de).
    """

    # =========================================================================
    # VALIDATE INPUT PARAMETERS
    # =========================================================================
    validate_params(params, SolidSlabOneWayConcreteSlab)

    # =========================================================================
    # FREQUENTLY USED PARAMETERS (extracted for readability)
    # =========================================================================
    slab_depth_mm = _req_param(params, "slab_depth_mm")
    slab_width_mm = _req_param(params, "slab_width_mm")
    span_primary_m = _req_param(params, "span_primary_m")
    reinforcement_diameter_mm = _req_param(params, "reinforcement_diameter_mm")

    static_system_ = STATIC_SYSTEM_MAP[_req_param(params, "static_system_")]
    load_category_ = LOAD_CATEGORY_MAP[_req_param(params, "load_category_")]
    fire_resistance_min_ = _req_param(params, "fire_resistance_min")
    min_depth_fire_mm = MIN_DEPTH_FIRE_MAP[fire_resistance_min_]

    # Cost/GWP lookup maps
    concrete_cost_map, concrete_gwp_map = _build_cost_gwp_maps(params)

    # =========================================================================
    # MATERIALS
    # =========================================================================
    fck_MPa = _req_param(params, "concrete_grade_MPa")
    # Get alpha_cc_ from dataclass default (constant, can be changed globally in input_dataclasses.py)
    alpha_cc_ = params.get(
        "alpha_cc_",
        SolidSlabOneWayConcreteSlab.__dataclass_fields__["alpha_cc_"].default,
    )

    materials = build_materials(fck_MPa=fck_MPa, alpha_cc=alpha_cc_)

    # Determine E_eff_MPa for creep
    Ac_mm2 = slab_width_mm * slab_depth_mm
    u_mm = slab_width_mm  # Assumption: only the bottom surface dries
    h0_mm = ec2.h_0(Ac_mm2, u_mm)
    phi_c_ = phi_creep(
        fcm_MPa=materials.concrete_SLS.fcm,
        RH_percent=50.0,
        t0_days=28.0,
        t_days=50 * 365.0,
        h0_mm=h0_mm,
        cement_class="N",
    )
    Ec_eff_MPa = materials.concrete_SLS.Ecm / (1.0 + phi_c_)
    # =========================================================================
    # LOAD COMBINATIONS
    # =========================================================================
    Gk1_kN_m2 = self_weight_kN_m2(slab_depth_mm)
    Gk2_kN_m2 = float(params["superimposed_dead_load_kN_m2"])
    Qk_kN_m2 = float(params["live_load_kN_m2"])

    psi_cat_ = params.get("psi_category", load_category_)
    psi_ = PSI_BY_CATEGORY[psi_cat_]

    Ed_ULS_kN_m2 = uls_fundamental(Gk1_kN_m2, Gk2_kN_m2, Qk_kN_m2)
    Ed_SLC_kN_m2 = sls_characteristic(Gk1_kN_m2, Gk2_kN_m2, Qk_kN_m2)
    Ed_SLF_kN_m2 = sls_frequent(Gk1_kN_m2, Gk2_kN_m2, Qk_kN_m2, psi1=psi_.psi1)
    Ed_SLQ_kN_m2 = sls_quasi_permanent(Gk1_kN_m2, Gk2_kN_m2, Qk_kN_m2, psi2=psi_.psi2)

    # =========================================================================
    # SECTION DEFINITION - REINFORCEMENT LAYOUT
    # =========================================================================
    concrete_cover_mm = c_nom(reinforcement_diameter_mm, fire_resistance_min_)
    vertical_spacing_mm = s_min_vertical(reinforcement_diameter_mm) + reinforcement_diameter_mm

    layer_active_flags = [
        1.0,
        _req_param(params, "reinforcement_layer_active_2_"),
        _req_param(params, "reinforcement_layer_active_3_"),
    ]
    target_spacings_mm = [
        _req_param(params, "reinforcement_spacing_lay_1_mm"),
        _req_param(params, "reinforcement_spacing_lay_2_mm"),
        _req_param(params, "reinforcement_spacing_lay_3_mm"),
    ]

    layout = build_reinf_layout(
        section_width_mm=slab_width_mm,
        section_depth_mm=slab_depth_mm,
        concrete_cover_mm=concrete_cover_mm,
        bar_diameter_mm=reinforcement_diameter_mm,
        vertical_spacing_mm=vertical_spacing_mm,
        target_spacings_mm=target_spacings_mm,
        layer_active_flags=layer_active_flags,
    )

    # Extract values for downstream use
    As_bot_mm2 = layout.As_total_mm2
    rho_s_bot_ = layout.rho_s
    slab_d_mm = layout.d_mm

    # =========================================================================
    # SECTION DEFINITION - ULS & SLS
    # =========================================================================
    section_ULS_ = build_rectangular_section(
        section_width_mm=slab_width_mm,
        section_depth_mm=slab_depth_mm,
        concrete_material=materials.concrete_ULS,
        steel_material=materials.steel_ULS,
        layer_n_bars=[lay.n_bars for lay in layout.layers],
        layer_spacings_mm=[lay.spacing_mm for lay in layout.layers],
        layer_active=[lay.active for lay in layout.layers],
        layer_z_mm=[lay.z_mm for lay in layout.layers],
        bar_diameter_mm=reinforcement_diameter_mm,
    )

    section_SLS_ = build_rectangular_section(
        section_width_mm=slab_width_mm,
        section_depth_mm=slab_depth_mm,
        concrete_material=materials.concrete_SLS,
        steel_material=materials.steel_SLS,
        layer_n_bars=[lay.n_bars for lay in layout.layers],
        layer_spacings_mm=[lay.spacing_mm for lay in layout.layers],
        layer_active=[lay.active for lay in layout.layers],
        layer_z_mm=[lay.z_mm for lay in layout.layers],
        bar_diameter_mm=reinforcement_diameter_mm,
    )

    # =========================================================================
    # INTERNAL FORCES
    # =========================================================================
    forces = beam_forces(
        system=static_system_,
        span_m=span_primary_m,
        ULS_kN_m2=Ed_ULS_kN_m2,
        SLC_kN_m2=Ed_SLC_kN_m2,
        SLF_kN_m2=Ed_SLF_kN_m2,
        SLQ_kN_m2=Ed_SLQ_kN_m2,
        width_m=slab_width_mm / 1000,
    )
    M_ULS_kNm = forces.ULS.M_max_kNm
    V_ULS_kN = forces.ULS.V_max_kN
    q_beam_ULS_kN_m = forces.ULS.R_supports_kN[0]
    q_beam_SLQ_kN_m = forces.SLS_quasi_permanent.R_supports_kN[0]
    q_beam_SLC_kN_m = forces.SLS_characteristic.R_supports_kN[0]

    # =========================================================================
    # COMPUTE CONSTRAINTS - ULS BENDING
    # =========================================================================
    M_Rd_Nmm = compute_bending_capacity(section_ULS_)
    const_bending_capacity_ = (M_ULS_kNm * 1e6) / M_Rd_Nmm

    # =========================================================================
    # COMPUTE CONSTRAINTS - ULS SHEAR
    # =========================================================================
    V_Rd_max_kN = shear_capacity_Vrd_max(
        section_width_mm=slab_width_mm,
        d_mm=slab_d_mm,
        fck_MPa=fck_MPa,
        fcd_MPa=materials.concrete_ULS.fcd(),
        cot_theta=1.2,
    )
    const_shear_VRd_max_ = V_ULS_kN / V_Rd_max_kN

    # =========================================================================
    # COMPUTE CONSTRAINTS - FIRE
    # =========================================================================
    const_min_depth_fire_ = min_depth_fire_mm / slab_depth_mm

    # =========================================================================
    # COMPUTE CONSTRAINTS - MIN REINFORCEMENT (CRACK WIDTH)
    # =========================================================================
    As_min_crack_mm2 = as_min_crack(
        slab_depth_mm=slab_depth_mm,
        reinforcement_diameter_mm=reinforcement_diameter_mm,
        c_nom_mm=concrete_cover_mm,
        fct_eff_MPa=0.5 * materials.concrete_SLS.fctm,
        A_ct_mm2=slab_depth_mm * slab_width_mm,
    )
    const_as_min_crack_ = (As_min_crack_mm2 / 2) / As_bot_mm2

    # =========================================================================
    # COMPUTE CONSTRAINTS - MIN REINFORCEMENT (DUCTILITY)
    # =========================================================================
    As_min_duct_mm2 = as_min_duct(
        slab_depth_mm=slab_depth_mm,
        f_ctm_MPa=materials.concrete_SLS.fctm,
        d_mm=slab_d_mm,
    )
    const_as_min_duct_ = As_min_duct_mm2 / As_bot_mm2

    # =========================================================================
    # COMPUTE CONSTRAINTS - MAX REINFORCEMENT
    # =========================================================================
    As_max_mm2 = 0.08 * slab_depth_mm * slab_width_mm
    As_prov_mm2 = As_bot_mm2 + As_min_crack_mm2 / 2
    const_as_max_ = As_prov_mm2 / As_max_mm2

    # =========================================================================
    # COMPUTE CONSTRAINTS - MIN REINFORCEMENT SPACING
    # =========================================================================
    const_s_min_ = []
    s_min_req_mm = s_min_horizontal(reinforcement_diameter_mm)
    for lay in layout.layers:
        if not lay.active:
            const_s_min_.append(1.0)
        else:
            const_s_min_.append(s_min_req_mm / lay.spacing_mm)

    # =========================================================================
    # COMPUTE CONSTRAINTS - MAX REINFORCEMENT SPACING
    # =========================================================================
    const_s_max_ = []
    s_max_req_mm = s_max_primary_direction(slab_depth_mm)
    for lay in layout.layers:
        if not lay.active:
            const_s_max_.append(0.0)
        else:
            const_s_max_.append(lay.spacing_mm / s_max_req_mm)

    # =========================================================================
    # COMPUTE CONSTRAINTS - DEFLECTION
    # =========================================================================
    sls_props = compute_sls_properties(
        section=section_SLS_,
        layout=layout,
        fctm_MPa=materials.concrete_SLS.fctm,
        section_width_mm=slab_width_mm,
        section_depth_mm=slab_depth_mm,
    )
    Iyy_gross_mm4 = sls_props.Iyy_gross_mm4
    Iyy_eff_mm4 = sls_props.Iyy_eff_mm4
    M_cr_Nmm = sls_props.M_cr_Nmm
    Sy_reinf_mm3 = sls_props.Sy_reinf_mm3

    eps_cs_t_inf_ = float(
        eps_cs_ec2(
            t_days=50 * 365,
            t_s_days=7.0,
            h0_mm=h0_mm,
            RH_percent=50.0,
            fck_MPa=fck_MPa,
            fcm_MPa=materials.concrete_SLS.fcm,
            cement_class="N",
        )
    )
    chi_cs_t_inf_ = shrinkage_curvature(
        eps_cs=eps_cs_t_inf_,
        Es_MPa=materials.steel_SLS.Es,
        Ec_eff_MPa=Ec_eff_MPa,
        Sy_reinf_mm3=Sy_reinf_mm3,
        Iyy_eff_mm4=Iyy_eff_mm4,
    )
    eps_cs_t0_ = float(
        eps_cs_ec2(
            t_days=30.0,
            t_s_days=7.0,
            h0_mm=h0_mm,
            RH_percent=80.0,
            fck_MPa=fck_MPa,
            fcm_MPa=materials.concrete_SLS.fcm,
            cement_class="N",
        )
    )
    chi_cs_t0_ = shrinkage_curvature(
        eps_cs=eps_cs_t0_,
        Es_MPa=materials.steel_SLS.Es,
        Ec_eff_MPa=materials.concrete_SLS.Ecm,
        Sy_reinf_mm3=Sy_reinf_mm3,
        Iyy_eff_mm4=Iyy_gross_mm4,
    )

    try:
        moment_curvature_diagram_ = section_SLS_.section_calculator.calculate_moment_curvature(
            theta=0.0,
            chi_first=1e-8,
            num_pre_yield=2,
            num_post_yield=2,
        )
    except StopIteration as e:
        raise SectionAnalysisError("Moment–curvature did not converge") from e
    except AttributeError as e:
        if "exterior" in str(e):
            raise SectionAnalysisError("Invalid geometry in moment–curvature (GeometryCollection).") from e
        raise
    except Exception as e:
        raise SectionAnalysisError(f"Moment–curvature calculation failed: {e}") from e

    M_tab_Nmm = [float(-m) for m in moment_curvature_diagram_.m_y]
    chi_tab_ = [float(-c) for c in moment_curvature_diagram_.chi_y]

    try:
        w_max_integration_mm = one_way_slab_deflection_integration(
            system="simply_supported",
            span_m=span_primary_m,
            Ed_SLC_kN_m2=Ed_SLC_kN_m2,
            Ed_SLQ_kN_m2=Ed_SLQ_kN_m2,
            Ec_MPa_t0=materials.concrete_SLS.Ecm,
            Ec_eff_MPa_tinf=Ec_eff_MPa,
            M_cr_Nmm=M_cr_Nmm,
            Iyy_gross_mm4=Iyy_gross_mm4,
            M_tab=M_tab_Nmm,
            chi_tab=chi_tab_,
            chi_cs_tinf_=chi_cs_t_inf_,
            chi_cs_t0_=chi_cs_t0_,
            slab_width_mm=1000.0,
        )
        _w_t0_mm = w_max_integration_mm.w_t0_mm
        w_tinf_mm = w_max_integration_mm.w_tinf_mm
        w_inc_mm = w_max_integration_mm.w_increment_mm
    except ValueError as e:
        raise SectionAnalysisError(f"Deflection integration failed (M outside M–χ range): {e}") from e

    w_allowed_ratio_tinf_ = _req_param(params, "w_allowed_tinf_")
    w_allowed_ratio_inc_ = _req_param(params, "w_allowed_inc_")
    w_allowed_tinf_mm = span_primary_m * 1e3 / w_allowed_ratio_tinf_
    w_allowed_inc_mm = span_primary_m * 1e3 / w_allowed_ratio_inc_
    const_deflection_tinf_ = w_tinf_mm / w_allowed_tinf_mm
    const_deflection_inc_ = w_inc_mm / w_allowed_inc_mm

    # =========================================================================
    # COMPUTE CONSTRAINTS - VIBRATION
    # =========================================================================
    f1_Hz = fundamental_frequency_slab_Hz(
        span_m=span_primary_m,
        Ecm_MPa=materials.concrete_SLS.Ecm,
        Iyy_mm4=Iyy_gross_mm4,
        Ed_SLQ_kN_m2=Ed_SLQ_kN_m2,
    )
    f_min_Hz = _req_param(params, "vibration_f_min_Hz")
    const_vibration_ = f_min_Hz / f1_Hz

    # =========================================================================
    # COMPUTE CONSTRAINTS - REINFORCEMENT OUTSIDE CROSS-SECTION
    # =========================================================================
    # Check if any active layer extends beyond section depth
    a_lay_2_mm = (2 * concrete_cover_mm + reinforcement_diameter_mm + vertical_spacing_mm) * layer_active_flags[1]
    a_lay_3_mm = (2 * concrete_cover_mm + reinforcement_diameter_mm + vertical_spacing_mm * 2) * layer_active_flags[2]
    a_max_mm = max(a_lay_2_mm, a_lay_3_mm)
    const_s_outside_ = a_max_mm / slab_depth_mm

    # =========================================================================
    # BEAM ANALYSIS (supporting beam at slab edge)
    # =========================================================================
    span_secondary_m = _req_param(params, "span_secondary_m")

    beam = RectangularConcreteBeam(
        beam_static_system_="simply_supported",
        beam_span_m=span_secondary_m,
        beam_q_ULS_kN_m=q_beam_ULS_kN_m,
        beam_q_SLQ_kN_m=q_beam_SLQ_kN_m,
        beam_q_SLC_kN_m=q_beam_SLC_kN_m,
        beam_Ec_eff_MPa=Ec_eff_MPa,
        beam_w_allowed_tinf_=_req_param(params, "w_allowed_tinf_"),
        beam_depth_mm=_req_param(params, "beam_depth_mm"),
        beam_bar_diameter_mm=_req_param(params, "beam_reinforcement_diameter_mm"),
        beam_reinforcement_spacing_lay_1_mm=_req_param(params, "beam_reinforcement_spacing_lay_1_mm"),
        beam_reinforcement_spacing_lay_2_mm=_req_param(params, "beam_reinforcement_spacing_lay_2_mm"),
        beam_reinforcement_layer_active_2_=_req_param(params, "beam_reinforcement_layer_active_2_"),
        beam_fire_resistance_min=fire_resistance_min_,
    )

    beam_result = beam_analysis(beam, materials)

    if not beam_result.computation_successful:
        raise SectionAnalysisError(f"Beam analysis failed: {beam_result.analysis_error}")

    # =========================================================================
    # COMPUTE OBJECTIVE FUNCTION
    # =========================================================================
    # slab volume calculation
    As_top_mm2 = As_min_crack_mm2 / 2
    As_top_total_mm3 = As_top_mm2 * 2 * (slab_width_mm / 1e3) * 1e3
    As_bot_total_mm3 = As_bot_mm2 * 1.2 * 1.15 * (slab_width_mm / 1e3) * 1e3
    Vs_slab_total_m3_m2 = (As_top_total_mm3 + As_bot_total_mm3) * 1e-9
    Vc_slab_m3_m2 = (slab_depth_mm * slab_width_mm * 1000) * 1e-9 - Vs_slab_total_m3_m2

    # beam volume calculation
    Vs_beam_total_m3_m2 = 0.0
    Vc_beam_m3_m2 = 0.0
    Vs_beam_total_m3_m2 = 2 * beam_result.Vs_total_per_beam_m3 / (span_primary_m * span_secondary_m)
    Vc_beam_m3_m2 = beam_result.Vc_per_beam_m3 / (span_primary_m * span_secondary_m)

    # cost and gwp input values
    cost_concrete_eur_m3 = concrete_cost_map[fck_MPa]
    cost_concrete_C30_eur_m3 = concrete_cost_map[30.0]
    cost_reinf_steel_eur_m3 = cost_concrete_C30_eur_m3 * _req_param(params, "cost_reinf_steel_per_conc_")

    gwp_concrete_kgco2e_m3 = concrete_gwp_map[fck_MPa]
    gwp_concrete_C30_kgco2e_m3 = concrete_gwp_map[30.0]
    gwp_reinf_steel_eur_m3 = gwp_concrete_C30_kgco2e_m3 * _req_param(params, "gwp_reinf_steel_per_conc_")

    # Slab + beam cost/GWP per m² of floor area
    y_cost = cost_concrete_eur_m3 * (Vc_slab_m3_m2 + 2 * Vc_beam_m3_m2) + cost_reinf_steel_eur_m3 * (
        Vs_slab_total_m3_m2 + 2 * Vs_beam_total_m3_m2
    )
    y_gwp = gwp_concrete_kgco2e_m3 * (Vc_slab_m3_m2 + 2 * Vc_beam_m3_m2) + gwp_reinf_steel_eur_m3 * (
        Vs_slab_total_m3_m2 + 2 * Vs_beam_total_m3_m2
    )

    y = _req_param(params, "obj_weight_cost") * y_cost + _req_param(params, "obj_weight_gwp") * y_gwp

    # =========================================================================
    # COMPUTE PENALIZED OBJECTIVE FUNCTION
    # =========================================================================
    # Slab constraints
    constraint_values = {
        "w_allowed_tinf_": const_deflection_tinf_,
        "w_allowed_inc_": const_deflection_inc_,
        "bending_capacity_": const_bending_capacity_,
        "shear_VRd_max_": const_shear_VRd_max_,
        "min_slab_depth_fire_": const_min_depth_fire_,
        "min_reinforcement_crack_": const_as_min_crack_,
        "min_reinforcement_ductility_": const_as_min_duct_,
        "max_reinforcement": const_as_max_,
        "max_reinforcement_spacing_lay_1": const_s_max_[0],
        "max_reinforcement_spacing_lay_2": const_s_max_[1],
        "max_reinforcement_spacing_lay_3": const_s_max_[2],
        "min_reinforcement_spacing_lay_1": const_s_min_[0],
        "min_reinforcement_spacing_lay_2": const_s_min_[1],
        "min_reinforcement_spacing_lay_3": const_s_min_[2],
        "reinforcement_outside_cross_section": const_s_outside_,
        "vibration_f_min_Hz": const_vibration_,
    }

    # Merge beam constraints
    constraint_values.update(beam_result.constraint_values)
    active_constraint_values = {
        name: value for name, value in constraint_values.items()
        if constraints.get(name, {}).get("active", True)
    }
    penalties_ = {name: (0.0 if value <= 1.0 else float(value-1)) for name, value in constraint_values.items()}

    y_p, active_penalties_ = compute_penalized_objective(
        y=y,
        penalties=penalties_,
        constraints=constraints,
        verbose=True,
    )

    # =========================================================================
    # PLOT CROSS-SECTION (optional)
    # =========================================================================
    if _PLOT_CROSS_SECTION_MODE == "all":
        fig, ax = plt.subplots()
        # Section extents (centered at origin per RectangularGeometry convention)
        x_min, x_max = -slab_width_mm / 2, slab_width_mm / 2
        y_min, y_max = -slab_depth_mm / 2, slab_depth_mm / 2
        concrete_patch = Rectangle(
            (x_min, y_min),
            slab_width_mm,
            slab_depth_mm,
            facecolor="lightgrey",
            edgecolor="black",
        )
        ax.add_patch(concrete_patch)
        xs = [x_min, x_max, x_max, x_min, x_min]
        ys = [y_min, y_min, y_max, y_max, y_min]
        ax.plot(xs, ys, "k-")

        # Plot reinforcement bars from layout
        for lay in layout.layers:
            if not lay.active or lay.n_bars == 0:
                continue
            half_width = (lay.n_bars - 1) / 2.0 * lay.spacing_mm
            for bar_idx in range(lay.n_bars):
                x_bar = -half_width + bar_idx * lay.spacing_mm
                circle = Circle(
                    (x_bar, lay.z_mm),
                    radius=reinforcement_diameter_mm / 2.0,
                    fill=True,
                    facecolor="black",
                )
                ax.add_patch(circle)

        ax.set_aspect("equal", "box")
        plt.xlabel("y [mm]")
        plt.ylabel("z [mm]")
        textstr = (
            f"y_cost   = {y_cost:.2f} €/m²\n"
            f"y_gwp   = {y_gwp:.2f} kgCO2/m2\n"
            f"y_total   = {y:.2f}\n"
            f"y_p = {y_p:.2f}\n"
            f"h = {slab_depth_mm:.0f} mm\n"
            f"f_ck = {materials.concrete_SLS.fck:.0f} MPa\n"
            f"roh_s_bot_ = {rho_s_bot_:.1f} ‰"
        )
        fig.canvas.draw()
        ylab = ax.yaxis.get_label()
        bbox = ylab.get_window_extent()
        bbox_fig = bbox.transformed(fig.transFigure.inverted())
        x = bbox_fig.x0 + 0.65
        y_pos = bbox_fig.y0 + 0.4
        fig.text(
            x,
            y_pos,
            textstr,
            ha="right",
            va="center",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
            fontsize=12,
        )
        plt.show(block=False)
        plt.pause(0.1)  # Brief pause to render


    # =========================================================================
    # RETURN RESULTS
    # =========================================================================
    result = AnalysisResult(
        y=y,
        y_p=y_p,
        y_cost=y_cost,
        y_gwp=y_gwp,
        active_constraint_values=active_constraint_values,
        constraint_values=constraint_values,
        penalties=active_penalties_,
        computation_successful=True,
        analysis_error=None,
        params=dict(params),
        As_prov_mm2=As_prov_mm2,
        rho_s=rho_s_bot_,
    )
    return result.to_dict()
