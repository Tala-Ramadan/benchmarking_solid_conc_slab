import math
from functools import partial  # used to bind constraints into cache logger per problem
from importlib import import_module
from importlib.resources import files
from pathlib import Path

import ioh
from ioh import ProblemClass
from ioh.iohcpp import ConstraintEnforcement as CE
from ioh.iohcpp import IntegerConstraint, RealConstraint

from .import_problem_from_csv import (
    _enf,
    build_space,
    load_constraint_defaults,
    load_param_defaults,
    load_problems_combined,
    make_decode,
)
from .problem_evaluator import EvalContext

# ----------------------------------------------------------------------------------------------------------#
# Helper class to detect and process slab types and return error if slab type was not provided correctly
# ----------------------------------------------------------------------------------------------------------#

# Fallback list in case dynamic discovery fails
_VALID_FALLBACK: tuple[str, ...] = (
    "solid_slab_one_way_concrete",
    "solid_slab_two_way_concrete",
    "ribbed_slab_one_way_concrete",
    "flat_slab_one_way_concrete",
    "hp_shell_one_way_concrete",
)


def _discover_slab_types() -> list[str]:
    """
    Discover slab types by scanning the package 'slabdesignbench.slab_models.slab_types'
    for subfolders that contain an analysis module (analysis_*.py).
    If anything goes wrong, fall back to the known list above.
    """
    try:
        root = files("slabdesignbench.slab_models.slab_types")
        types: list[str] = []
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            # Check for any analysis_*.py file (e.g., analysis_ec2_de.py)
            has_analysis = any(
                f.name.startswith("analysis_") and f.name.endswith(".py") for f in entry.iterdir() if f.is_file()
            )
            if has_analysis:
                types.append(entry.name)
        return sorted(types) if types else list(_VALID_FALLBACK)
    except Exception:
        return list(_VALID_FALLBACK)


def _make_violation_reader(ctx, cname: str):
    """Return g(x) that fetches the raw violation for constraint `cname` from cache."""

    def g(x):
        # Never raise from here: IOH calls this from C++.
        try:
            r = ctx.get(x)
            v = r.get("violations", {}).get(cname, 0.0)
            v = float(v)
            # Ensure non-negative (contract: raw, non-negative violations)
            return v if v >= 0.0 and math.isfinite(v) else 0.0
        except Exception as e:
            # Last-resort guard; keep IOH running
            print(f"[violation_reader:{cname}] swallowed error: {e}")
            return 0.0

    return g


# ----------------------------------------------------------------------------------------------------------#
# Problem builder by path and slab module
# ----------------------------------------------------------------------------------------------------------#


def build_problems_for_slab(slab_dir: Path, slab_module) -> dict[str, dict]:
    """
    Build all IOH problems for a slab type directory and its analysis module.

    - CSV-driven: parameter_defaults.csv, constraint_defaults.csv, problem_list.csv
    - One EvalContext per problem (per-problem_ID), binding that problem's constraints into analysis()
    - IOH constraints log *raw* violations from the cache (default: HIDDEN/1/1 unless overridden)
    """

    slab_dir = Path(slab_dir)  # slab-specific folder that contains the three .csv files with all info for problem setup
    params_csv = slab_dir / "parameter_defaults.csv"
    constr_csv = slab_dir / "constraint_defaults.csv"
    problem_list_csv = slab_dir / "problem_list.csv"

    PDEF = load_param_defaults(params_csv)  # Dict of all parameters with value lists, bounds, fixed values
    CDEF = load_constraint_defaults(constr_csv)  # Dict of constraint defaults
    PROBLEMS = load_problems_combined(
        PDEF, CDEF, problem_list_csv
    )  # Dict[problem_ID] with problem-specific problem definitions from problem_list.csv

    problems: dict[str, dict] = {}  # container that saves problem definitions

    for problem_ID, info in PROBLEMS.items():
        # problem_ID = the problem ID
        # info = the per-problem config dict for that problem_ID
        # typical shape of PROBLEMS:
        # PROBLEMS = {
        #   "1": {
        #     "model": {                 # per-problem parameter model (roles/bounds/fixed already overlaid)
        #       "t_mm":   {"values": [...], "lb": 0, "ub": 5, "fixed_idx": 2, "role": "var",   "domain": "catalog"},
        #       "span_m": {"values": [...], "lb": 0, "ub": 8, "fixed_idx": 4, "role": "fixed", "domain": "grid"},
        #       # ...
        #     },...
        var_names, lb_idx, ub_idx = build_space(info["model"])  # extract var names and var bounds for this problem
        if not (len(var_names) == len(lb_idx) == len(ub_idx)):
            raise ValueError(
                f"problem {problem_ID}: mismatch in space: "
                f"len(var_names)={len(var_names)}, len(lb_idx)={len(lb_idx)}, len(ub_idx)={len(ub_idx)}"  # catch malformed .CSV
            )

        n_vars = len(var_names)
        if n_vars == 0:
            raise ValueError(
                f"problem {problem_ID}: no variables (all fixed) — cannot build a 0-dim IOH problem."
            )  # catch problems with 0 vars

        # log attributes of constraints to determine in analysis functions which constraints are activated/returned
        constraints_log = {
            name: {
                "active": c.get("active", True),
                "enforced": c.get("enforced", CE.HIDDEN),  # may already be enum; normalised below
                "weight": float(c.get("weight", 1)),
                "exponent": float(c.get("exponent", 1)),
                "kind": c.get("kind", "real"),
            }
            for name, c in info["constraints"].items()
        }

        # create decode, constraint list -> cache logger to store results from slab-specific analysis function
        decode = make_decode(info["model"], var_names)  # create a decide(x_idx) for this problem
        # bind constraints for this problem:
        analysis_fn = partial(slab_module.analysis, constraints=constraints_log)
        # slab-specific analysis(params) must return {"y","y_p","violations":{...}, ...}
        ctx = EvalContext(decode, analysis_fn)  # builds a cache for that specific problem - no cross-instance reuse!

        # --- IOH constraints: log *raw violations* from cache; default to HIDDEN/1/1 ---
        constraints = []
        for name, conf in info["constraints"].items():
            if not conf.get("active", True):
                continue
            # Build the 1-arg reader that pulls violations[name] from cache
            g = _make_violation_reader(ctx, name)

            # Effective logging settings (users can override via problem_list.csv if they insist)
            enforced = conf.get("enforced", CE.HIDDEN)
            try:
                enforced = _enf(enforced)  # accept enum/str/bool
            except Exception:
                enforced = CE.HIDDEN

            weight = float(conf.get("weight", 1.0) or 1.0)
            exponent = float(conf.get("exponent", 1.0) or 1.0)

            ctor = IntegerConstraint if conf.get("kind", "real") == "integer" else RealConstraint
            constraints.append(
                ctor(
                    g,
                    enforced=enforced,  # HIDDEN by default → logging only
                    weight=weight,  # 1.0 default → neutral
                    exponent=exponent,  # 1.0 default → neutral
                )
            )

        def objective_idx(x, _ctx=ctx, _n=n_vars, _problem_ID=problem_ID):  # n_vars = len(var_names)
            # Never raise from inside IOH callback; return a huge value if something is off.
            try:
                if len(x) != _n:
                    # mismatch can happen if an algorithm passes stale dimension;
                    # keep IOH alive and signal "awful" fitness
                    print(f"[objective:{_problem_ID}] len(x)={len(x)} != expected {_n} → returning +inf")
                    return float("inf")
                rec = _ctx.get(x)
                return float(rec.get("y_p", float("inf")))
            except Exception as e:
                print(f"[objective:{_problem_ID}] swallowed error: {e} → returning +inf")
                return float("inf")

        # --- Wrap IOH problem and set integer index bounds ---
        p = ioh.wrap_problem(
            function=objective_idx,
            name=f"{slab_dir.name}_problem_{problem_ID}",
            problem_class=ProblemClass.INTEGER,
            dimension=n_vars,
            lb=0,
            ub=1,  # temporary bounds for problem wrapping; overwrite below
            constraints=constraints,
        )
        # assign actual bounds arrays to IOH problem (no bound arrays possible in problem wrapper)
        p.bounds.lb = lb_idx
        p.bounds.ub = ub_idx

        active_constraint_names = [name for name, conf in info["constraints"].items() if conf.get("active", True)]
        ctx.ensure_constraints(active_constraint_names)
        ctx.ensure_params(var_names)

        problems[problem_ID] = {  # a dict that collects all problem-specific relevant information
            "problem": p,
            "var_names": var_names,
            "constraints": constraints_log,
            "decode": decode,
            "label": info["label"],
            "ctx": ctx,
            "active_constraint_names": active_constraint_names,  # list of active constraints for debugging/information
        }

    return problems


# ----------------------------------------------------------------------------------------------------------#
# Interface to call function build_problems_for_slab with slab type as the only input
# ----------------------------------------------------------------------------------------------------------#
# the definition of optimization problems is still defined in the slab-specific .csv tables!


def build_problems_for_slab_type(slab_type: str) -> dict[str, dict]:
    """
    Build all problems for a given slab type string.

    Valid types are discovered dynamically by scanning
    'slabdesignbench.slab_models.slab_types' for subfolders with an analysis module.
    If the provided slab_type is invalid, a clear error lists all valid options.
    """
    valid = _discover_slab_types()
    if slab_type not in valid:
        raise ValueError(f"Unknown slab_type '{slab_type}'. Valid options: {', '.join(valid)}")

    # Import the slab package (its __init__.py must expose `analysis`)
    mod_path = f"slabdesignbench.slab_models.slab_types.{slab_type}"
    slab_module = import_module(mod_path)

    # Locate packaged CSV folder for this slab type
    slab_dir = files("slabdesignbench.slab_models.slab_types") / slab_type

    # Delegate to the original builder
    return build_problems_for_slab(slab_dir, slab_module)
