import matplotlib.pyplot as plt
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

# ======================================================================================================================
# CREATE CROSS SECTION
# ======================================================================================================================

# Generate concrete geometry (alternative: generate free polygon with SurfaceGeometry())
width = 1000
height = 300
diameter_reinf = 25
cover = 50
spacing = 80

geometry_rect = RectangularGeometry(
    width=width,
    height=height,
    material=concrete_ULS,
)

# Add line reinforcement (alternative: add discrete reinforcement points through add_reinforcement())
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
