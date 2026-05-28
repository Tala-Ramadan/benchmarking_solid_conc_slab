from pprint import pprint

import numpy as np

from slabdesignbench.optimization_problem_builder.problem_builder import (
    build_problems_for_slab_type,
)

# mypy: disable-error-code=import-untyped

slab_type = "solid_slab_one_way_concrete"
problem_bundle = build_problems_for_slab_type(slab_type)


def pad_x_idx(x_idx, var_names):
    """
    Ensure x_idx has same length as var_names.
    If shorter, pad with zeros (e.g. for new beam variables).
    If longer, truncate.
    """
    x_list = list(x_idx)
    n = len(var_names)
    if len(x_list) < n:
        x_list = x_list + [0] * (n - len(x_list))
    elif len(x_list) > n:
        x_list = x_list[:n]
    return np.array(x_list, dtype=int)


def eval_point(pid, bundle_entry, x_idx_raw):
    """
    Evaluate one design point and return selected outputs / parameters.
    All data taken from AnalysisResult.to_dict() (the rec) plus params.
    """
    ctx = bundle_entry["ctx"]
    var_names = bundle_entry["var_names"]

    x_idx = pad_x_idx(x_idx_raw, var_names)

    # This is your "results database" for that x: AnalysisResult.to_dict()
    rec = ctx.get(x_idx)

    params = rec.get("params")
    if params is None:
        params = ctx.decode(x_idx)

    return {
        "pid": pid,
        "x_raw": list(x_idx_raw),
        "x_used": x_idx.tolist(),
        "y_cost": rec.get("y_cost"),
        "y_gwp": rec.get("y_gwp"),
        "slab_depth_mm": params.get("slab_depth_mm"),
        "concrete_grade_fck": params.get("concrete_grade_fck") or params.get("concrete_grade_MPa"),
        "rho_s": rec.get("rho_s"),
    }


# pid -> list of design points to check (PIDs as STRINGS to match problem_bundle)
# Format: [slab_depth_mm, concrete_grade, reinf_spacing_1, reinf_spacing_2, reinf_spacing_3,
#          layer_active_2, layer_active_3, reinf_diameter,
#          beam_depth, beam_reinf_diameter, beam_spacing_1, beam_spacing_2, beam_layer_active_2]
design_points = {
    "1": [[2, 8, 4, 16, 0, 0, 0, 11, 4, 3, 5, 5, 0]],  # beam: 400mm, d16, spacing ~34mm
    "2": [[25, 2, 24, 5, 0, 1, 0, 1, 6, 4, 4, 4, 0]],  # beam: 500mm, d20, spacing ~40mm
    "11": [[2, 8, 4, 16, 0, 0, 0, 11, 4, 3, 5, 5, 0]],
    "12": [[25, 2, 24, 5, 0, 1, 0, 1, 6, 4, 4, 4, 0]],
    "111": [[13, 8, 10, 26, 0, 0, 0, 0, 5, 3, 5, 5, 0]],  # beam: 450mm, d16, spacing ~34mm
    "112": [[26, 1, 1, 7, 0, 1, 0, 0, 6, 4, 4, 4, 0]],
}

results = []

print("Available PIDs in problem_bundle:", list(problem_bundle.keys()))

for pid, b in problem_bundle.items():
    if pid not in design_points:
        continue

    for x in design_points[pid]:
        res = eval_point(pid, b, x)
        results.append(res)

        print(f"\n=== pid {pid}, design point (raw) {res['x_raw']} -> (used) {res['x_used']} ===")
        print(
            f"y_cost={res['y_cost']}, "
            f"y_gwp={res['y_gwp']}, "
            f"slab_depth_mm={res['slab_depth_mm']}, "
            f"concrete_grade_fck={res['concrete_grade_fck']}, "
            f"rho_s={res['rho_s']}"
        )

print("\n--- summary ---")
pprint(results)
