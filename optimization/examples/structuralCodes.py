import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, Rectangle
from structuralcodes import set_design_code
from structuralcodes.geometry import (  # etc.
    RectangularGeometry,
    add_reinforcement_line,
)
from structuralcodes.materials.concrete import create_concrete
from structuralcodes.materials.constitutive_laws import (
    ElasticPlastic,
    ParabolaRectangle,
    Sargin,
)
from structuralcodes.materials.reinforcement import create_reinforcement
from structuralcodes.sections import GenericSection

# Set the active design code
set_design_code("ec2_2004")  # set acting design code for this script

# ======================================================================================================================
# MATERIAL PROPERTIES
# ======================================================================================================================

# material properties - concrete
gamma_C = 1.5
alpha_cc = 0.85
fck = 100

# material properties - steel
gamma_s = 1.15
fyk = 500
ftk = 525  # steel B500A according to EC2/NA.de NCI for 5.7 (NA.10)
Es = 200000
fyd = fyk / gamma_s
ftd = ftk / gamma_s
eps_uyk = fyk / Es
eps_uyd = fyd / Es
eps_uk = 0.025  # Steel B500A
eps_ud = 0.025  # Steel B500A
Ehk = (ftk - fyk) / (eps_uk - eps_uyk)
Ehd = (ftd - fyd) / (eps_ud - eps_uyd)

# Constitutive laws
concrete_constitutive_law_ULS = ParabolaRectangle(
    fc=fck / gamma_C,
    eps_0=-0.002,
    eps_u=-0.0035,
    n=2.0,
    name="ParabolaRectangle_acc_0.85",
)
concrete_constitutive_law_SLS = Sargin(fc=fck + 8.0, eps_c1=-0.0023, eps_cu1=-0.0035, k=2.04, name="sargin")
reinforcement_steel_constitutive_law_ULS = ElasticPlastic(
    E=Es, fy=fyd, Eh=Ehd, eps_su=eps_ud, name="elastic_plastic_steel_ULS"
)
reinforcement_steel_constitutive_law_SLS = ElasticPlastic(
    E=Es, fy=fyk, Eh=Ehk, eps_su=eps_uk, name="elastic_plastic_steel_SLS"
)

# Material definition
concrete_ULS = create_concrete(fck=fck, constitutive_law=concrete_constitutive_law_ULS)
concrete_SLS = create_concrete(fck=fck, constitutive_law="sargin")
reinforcement_ULS = create_reinforcement(
    fyk=fyd,
    Es=Es,
    ftk=ftd,
    epsuk=eps_ud,
    constitutive_law=reinforcement_steel_constitutive_law_ULS,
)
reinforcement_SLS = create_reinforcement(
    fyk=fyk,
    Es=Es,
    ftk=ftk,
    epsuk=eps_uk,
    constitutive_law=reinforcement_steel_constitutive_law_SLS,
)

print(concrete_ULS.constitutive_law)
print(concrete_SLS.constitutive_law)
print(reinforcement_ULS.constitutive_law)
print(reinforcement_SLS.constitutive_law)


# ======================================================================================================================
# CREATE CROSS SECTION
# ======================================================================================================================

# Generate concrete geometry (alternative: generate free polygon with SurfaceGeometry())
width = 1000
height = 300

geometry_rect = RectangularGeometry(
    width=width,
    height=height,
    material=concrete_ULS,
)

# Add line reinforcement (alternative: add discrete reinforcement points through add_reinforcement())

diameter_reinf = 25
cover = 50
spacing = 80
geometry_rect = add_reinforcement_line(
    geometry_rect,  # adding the second objects turns surfaceGeometry into compoundGeometry
    diameter=diameter_reinf,
    material=reinforcement_ULS,
    s=spacing,
    coords_i=(
        -width / 2 + cover + diameter_reinf / 2,
        -height / 2 + cover + diameter_reinf / 2,
    ),
    coords_j=(
        width / 2 - cover - diameter_reinf / 2,
        -height / 2 + cover + diameter_reinf / 2,
    ),
)
# Create section
section = GenericSection(geometry_rect)  # creates a section calculation tool from the geometry

# ======================================================================================================================
# SECTION PROPERTIES
# ======================================================================================================================

# Calculate the moment-curvature response
section_properties = section.section_calculator._calculate_gross_section_properties()
moment_curvature = section.section_calculator.calculate_moment_curvature()
bending_strength = section.section_calculator.calculate_bending_strength()
axial_strength = section.section_calculator.calculate_limit_axial_load()
mm_interaction_domain = section.section_calculator.calculate_mm_interaction_domain()
print("section properties: ", section_properties)
print("moment curvature relationship: ", moment_curvature)
print("bending strength: ", bending_strength)
print("axial strength: ", axial_strength)
print("nm interaction domain: ", mm_interaction_domain)
# section.section_calculator.calculate_nm_interaction_domain()
# section.section_calculator.calculate_nmm_interaction_domain()
# section.section_calculator.calculate_strain_profile()
# section.section_calculator.find_equilibrium_fixed_curvature()


# ======================================================================================================================
# PLOTS: MOMENT-CURVATURE-RELATIONSHIP
# ======================================================================================================================
# plot moment curvature plot
fig, ax = plt.subplots()
ax.plot(-moment_curvature.chi_y, -moment_curvature.m_y)
plt.xlabel("Chi_y")
plt.ylabel("M_y")
plt.show()  # <- this pops up a window and blocks until you close it

# ======================================================================================================================
# PLOTS: CROSS SECTION
# ======================================================================================================================

# --- section geometry plot driven by `geometry_rect` ---
fig, ax = plt.subplots()

# 1) Concrete outline from extents
x_min, x_max, y_min, y_max = geometry_rect.calculate_extents()

width = x_max - x_min
height = y_max - y_min

# light grey filled concrete area
concrete_patch = Rectangle(
    (x_min, y_min),  # bottom-left corner
    width,
    height,
    facecolor="lightgrey",
    edgecolor="black",
)
ax.add_patch(concrete_patch)

# (optional) outline on top, if you like it crisp:
xs = [x_min, x_max, x_max, x_min, x_min]
ys = [y_min, y_min, y_max, y_max, y_min]
ax.plot(xs, ys, "k-")

# 2) Reinforcement bars, *if* there are any
point_geoms = geometry_rect.point_geometries

for pg in point_geoms:
    circle = Circle(
        (pg.x, pg.y),
        radius=pg.diameter / 2.0,
        fill=True,
        facecolor="black",
    )
    ax.add_patch(circle)

ax.set_aspect("equal", "box")
plt.xlabel("y [mm]")
plt.ylabel("z [mm]")
plt.show()


# ======================================================================================================================
# PRINT AVAILABLE CONSTITUTIVE LAWS
# ======================================================================================================================
"""
    About the constitutive laws:
    - WARNING: alpha_cc = 1,0 in most EU countries, only german NDP sets it 0,85 -> f_cd is smaller in germany 
    - The non-linear stress-strain relationship in EC2 is based on Sargin (see Zilch (2010), p. 63)
    -> we can use Sargin for deformation calculations (see Zilch (2010), p. 10)
"""
# 3) Loop over all laws, but only plot those that work for this material
law1 = concrete_constitutive_law_ULS
law2 = concrete_constitutive_law_SLS
law3 = reinforcement_ULS.constitutive_law
law4 = reinforcement_SLS.constitutive_law

eps_neg, eps_pos = law1.get_ultimate_strain()

# concrete compression range only: [eps_neg, 0], eps_neg < 0
eps_min = eps_neg * 1.05
eps_max = 0.0

eps_c = np.linspace(eps_min, eps_max, 400)  # negative compressive strain
sig_c = law1.get_stress(eps_c)  # negative compressive stress

# flip sign for plotting: compression positive
eps_plot = -eps_c
sig_plot = -sig_c

fig, ax = plt.subplots()
ax.plot(eps_plot, sig_plot)

# axes & labels in “engineering friendly” convention
ax.axhline(0, linewidth=0.5)
ax.axvline(0, linewidth=0.5)
ax.set_xlabel(r"compressive strain $\varepsilon_c$ [-]")
ax.set_ylabel(r"compressive stress $\sigma_c$ [MPa]")
ax.set_title(f"{law1.name} (EC2-2004, fck = {fck} MPa)")
ax.grid(True)
plt.show()
