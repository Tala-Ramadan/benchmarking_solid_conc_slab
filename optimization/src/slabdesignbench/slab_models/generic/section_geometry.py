"""
section_geometry.py
===================

Section geometry building for concrete structures.

This module provides:
1. DATACLASSES - ReinforcementLayer, ReinfLayout
2. PURE HELPERS - Bar count, area calculations, layer positioning
3. SECTION BUILDER - build_rectangular_section()

Section types:
- Rectangular: solid_slab_one_way_concrete, solid_slab_two_way_concrete, flat_slab_one_way_concrete
- Ribbed: ribbed_slab_one_way_concrete (to be implemented)
- Shell: hp_shell_one_way_concrete (to be implemented)

Note: The section builder wraps structuralcodes, but the dataclasses and
pure helpers are code-agnostic.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from structuralcodes.geometry import RectangularGeometry, add_reinforcement_line
from structuralcodes.sections import GenericSection

from slabdesignbench.slab_models.generic.exceptions import SectionAnalysisError

# =============================================================================
# DATACLASSES
# =============================================================================


@dataclass
class ReinforcementLayer:
    """
    Single layer of reinforcement bars.

    Attributes
    ----------
    active : bool
        Whether this layer is included in the section.
    n_bars : int
        Number of bars in this layer.
    diameter_mm : float
        Bar diameter [mm].
    spacing_mm : float
        Center-to-center spacing [mm].
    z_mm : float
        Distance from section centroid to layer centroid [mm].
        Negative = below centroid (tension zone for sagging).
    As_mm2 : float
        Total area of this layer [mm²].
    """

    active: bool
    n_bars: int
    diameter_mm: float
    spacing_mm: float
    z_mm: float
    As_mm2: float


@dataclass
class ReinfLayout:
    """
    Complete reinforcement layout for a section.

    Attributes
    ----------
    layers : List[ReinforcementLayer]
        All reinforcement layers (bottom to top).
    As_total_mm2 : float
        Total reinforcement area [mm²].
    z_centroid_mm : float
        Reinforcement centroid from section centroid [mm].
    rho_s : float
        Reinforcement ratio [‰].
    d_mm : float
        Effective depth (section top to reinforcement centroid) [mm].
    """

    layers: list[ReinforcementLayer]
    As_total_mm2: float
    z_centroid_mm: float
    rho_s: float
    d_mm: float


# =============================================================================
# PURE HELPERS
# =============================================================================


def compute_bar_count(section_width_mm: float, target_spacing_mm: float) -> int:
    """
    Compute number of bars to achieve approximately the target spacing.

    Returns n_bars such that actual_spacing = width / n_bars.

    Parameters
    ----------
    section_width_mm : float
        Section width [mm].
    target_spacing_mm : float
        Target center-to-center spacing [mm].

    Returns
    -------
    int
        Number of bars (minimum 1).
    """
    if target_spacing_mm <= 0:
        return 1
    n = round(section_width_mm / target_spacing_mm)
    return max(1, int(n))


def compute_layer_area(n_bars: int, diameter_mm: float) -> float:
    """
    Compute total area of a reinforcement layer.

    Parameters
    ----------
    n_bars : int
        Number of bars.
    diameter_mm : float
        Bar diameter [mm].

    Returns
    -------
    float
        Total area [mm²].
    """
    return n_bars * math.pi * diameter_mm**2 / 4.0


def compute_layer_z(
    layer_idx: int,
    section_depth_mm: float,
    concrete_cover_mm: float,
    bar_diameter_mm: float,
    vertical_spacing_mm: float,
) -> float:
    """
    Compute z-coordinate of a layer from section centroid.

    Parameters
    ----------
    layer_idx : int
        Layer index (0 = bottommost).
    section_depth_mm : float
        Total section depth [mm].
    concrete_cover_mm : float
        Nominal cover [mm].
    bar_diameter_mm : float
        Bar diameter [mm].
    vertical_spacing_mm : float
        Vertical center-to-center distance between layers [mm].

    Returns
    -------
    float
        Distance from section centroid [mm].
        Negative = below centroid.
    """
    z_from_bottom = concrete_cover_mm + bar_diameter_mm / 2.0 + vertical_spacing_mm * layer_idx
    z_from_centroid = z_from_bottom - section_depth_mm / 2.0
    return z_from_centroid


# =============================================================================
# REINFORCEMENT LAYOUT BUILDER
# =============================================================================


def build_reinf_layout(
    section_width_mm: float,
    section_depth_mm: float,
    concrete_cover_mm: float,
    bar_diameter_mm: float,
    vertical_spacing_mm: float,
    target_spacings_mm: Sequence[float],
    layer_active_flags: Sequence[float],
) -> ReinfLayout:
    """
    Build complete reinforcement layout for a rectangular section.

    This handles all calculations: bar counts, actual spacings, areas, z-coords.

    Parameters
    ----------
    section_width_mm : float
        Section width [mm].
    section_depth_mm : float
        Section depth [mm].
    concrete_cover_mm : float
        Nominal concrete cover [mm].
    bar_diameter_mm : float
        Bar diameter (same for all layers) [mm].
    vertical_spacing_mm : float
        Vertical center-to-center spacing between layers [mm].
    target_spacings_mm : Sequence[float]
        Target horizontal spacings for each layer [mm].
    layer_active_flags : Sequence[float]
        1.0 = active, 0.0 = inactive for each layer.

    Returns
    -------
    ReinfLayout
        Complete layout with all computed properties.
    """
    layers: list[ReinforcementLayer] = []

    for i, (target_s, active_flag) in enumerate(zip(target_spacings_mm, layer_active_flags, strict=True)):
        active = bool(int(active_flag))

        # Compute bar count and actual spacing
        n_bars = compute_bar_count(section_width_mm, target_s) if active else 0
        actual_spacing = section_width_mm / n_bars if n_bars > 0 else target_s

        # Compute z-coordinate and area
        z = compute_layer_z(i, section_depth_mm, concrete_cover_mm, bar_diameter_mm, vertical_spacing_mm)
        As = compute_layer_area(n_bars, bar_diameter_mm) if active else 0.0

        layers.append(
            ReinforcementLayer(
                active=active,
                n_bars=n_bars,
                diameter_mm=bar_diameter_mm,
                spacing_mm=actual_spacing,
                z_mm=z,
                As_mm2=As,
            )
        )

    # Compute totals
    As_total = sum(lay.As_mm2 for lay in layers if lay.active)

    if As_total > 0:
        z_centroid = sum(lay.As_mm2 * lay.z_mm for lay in layers if lay.active) / As_total
    else:
        z_centroid = layers[0].z_mm if layers else 0.0

    # Effective depth: top of section to reinforcement centroid
    d_mm = section_depth_mm / 2.0 - z_centroid

    # Reinforcement ratio [‰] based on effective section
    Ac_eff = d_mm * section_width_mm
    rho_s = (As_total / Ac_eff * 1000.0) if Ac_eff > 0 else 0.0

    return ReinfLayout(
        layers=layers,
        As_total_mm2=As_total,
        z_centroid_mm=z_centroid,
        rho_s=rho_s,
        d_mm=d_mm,
    )


# =============================================================================
# RECTANGULAR SECTION BUILDER
# =============================================================================


def build_rectangular_section(
    section_width_mm: float,
    section_depth_mm: float,
    concrete_material: Any,
    steel_material: Any,
    layer_n_bars: Sequence[int],
    layer_spacings_mm: Sequence[float],
    layer_active: Sequence[bool],
    layer_z_mm: Sequence[float],
    bar_diameter_mm: float,
) -> GenericSection:
    """
    Build a rectangular section with reinforcement layers.

    Suitable for solid slabs (one-way, two-way) and flat slabs.

    Parameters
    ----------
    section_width_mm : float
        Section width [mm].
    section_depth_mm : float
        Section depth [mm].
    concrete_material : Any
        Concrete material (from materials module).
    steel_material : Any
        Steel material (from materials module).
    layer_n_bars : Sequence[int]
        Number of bars in each layer.
    layer_spacings_mm : Sequence[float]
        Spacing in each layer [mm].
    layer_active : Sequence[bool]
        Whether each layer is active.
    layer_z_mm : Sequence[float]
        Z-coordinate of each layer from section centroid [mm].
    bar_diameter_mm : float
        Bar diameter (same for all layers) [mm].

    Returns
    -------
    GenericSection
        Section ready for analysis.

    Raises
    ------
    SectionAnalysisError
        If section geometry is invalid.
    """
    try:
        # Create concrete rectangle
        geometry = RectangularGeometry(
            width=section_width_mm,
            height=section_depth_mm,
            material=concrete_material,
        )

        # Add reinforcement layers
        for _i, (n_bars, spacing, active, z) in enumerate(
            zip(layer_n_bars, layer_spacings_mm, layer_active, layer_z_mm, strict=True)
        ):
            if not active or n_bars == 0:
                continue

            # Half-width for positioning
            half_width = (n_bars - 1) / 2.0 * spacing

            geometry = add_reinforcement_line(
                geometry,
                diameter=bar_diameter_mm,
                material=steel_material,
                s=spacing,
                coords_i=(-half_width, z),
                coords_j=(+half_width, z),
            )

        return GenericSection(geometry)

    except AttributeError as e:
        if "exterior" in str(e):
            raise SectionAnalysisError(
                "Invalid geometry (GeometryCollection without .exterior). "
                "Check that reinforcement is inside the section."
            ) from e
        raise
    except Exception as e:
        raise SectionAnalysisError(f"Failed to build section: {e}") from e
