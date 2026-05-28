"""
Validate LHS design-space results.

1. Statistics: feasible share, y ranges, top violated constraints
2. Re-evaluation: regenerate same LHS indices (same seed=42), re-run analysis
   for a few samples per problem, compare y/y_p/feasible against stored CSV.
"""
from __future__ import annotations

import csv
import math
from collections import Counter
from pathlib import Path

import numpy as np

from slabdesignbench.optimization_problem_builder.problem_builder import (
    build_problems_for_slab_type,
)

SLAB_TYPE = "solid_slab_one_way_concrete"
LHS_ROOT = Path.cwd() / "lhs_design_space_results" / SLAB_TYPE
LHS_SEED = 42          # same seed as the original LHS run
N_SAMPLES = 1000       # same n_samples as the original run
N_CHECK = 5            # how many samples to re-evaluate per problem
CHECK_INDICES = [0, 1, 60, 501, 1000]  # which sample rows to re-check


def _load_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _latin_hypercube_indices(lb_idx, ub_idx, n_samples, rng):
    """Same LHS generator as in analyze_design_space_lhs.py."""
    dim = len(lb_idx)
    lhs_unit = np.empty((n_samples, dim), dtype=float)
    for d in range(dim):
        lhs_unit[:, d] = (rng.permutation(n_samples) + rng.random(n_samples)) / n_samples
    n_levels = ub_idx - lb_idx + 1
    mapped = lb_idx + np.floor(lhs_unit * n_levels).astype(int)
    mapped = np.minimum(mapped, ub_idx)
    return mapped.astype(int)


def main() -> None:
    bundles = build_problems_for_slab_type(SLAB_TYPE)
    all_ok = True

    for pid, bundle in sorted(bundles.items()):
        ctx = bundle["ctx"]
        decode = bundle["decode"]
        var_names = bundle["var_names"]
        label = bundle.get("label", "")
        problem = bundle["problem"]

        label_safe = label.replace(" ", "_").replace("/", "-") if label else ""
        folder = f"problem_{pid}__{label_safe}" if label_safe else f"problem_{pid}"
        csv_path = LHS_ROOT / folder / "lhs_samples.csv"

        if not csv_path.exists():
            print(f"Problem {pid}: CSV not found at {csv_path}")
            continue

        rows = _load_csv(csv_path)
        print(f"\n{'='*70}")
        print(f"Problem {pid} ({label}) — {len(rows)} samples")
        print(f"{'='*70}")

        # --- 1. Statistics ---
        feasible = [r for r in rows if r["feasible_constraints"] == "True"]
        successful = [r for r in rows if r["computation_successful"] == "True"]
        y_succ = [float(r["y"]) for r in successful]
        yp_succ = [float(r["y_p"]) for r in successful]

        print(f"  Successful: {len(successful)}/{len(rows)}")
        print(f"  Feasible:   {len(feasible)}/{len(rows)} ({len(feasible)/len(rows)*100:.1f}%)")
        if y_succ:
            print(f"  y  range (successful): {min(y_succ):.2f} .. {max(y_succ):.2f}")
            print(f"  y_p range (successful): {min(yp_succ):.2f} .. {max(yp_succ):.2f}")
        if feasible:
            y_feas = [float(r["y"]) for r in feasible]
            print(f"  y  range (feasible):   {min(y_feas):.2f} .. {max(y_feas):.2f}")

        viol_counter = Counter()
        for r in rows:
            if r["violated_constraints"]:
                for c in r["violated_constraints"].split("|"):
                    if c.strip():
                        viol_counter[c.strip()] += 1
        if viol_counter:
            print(f"\n  Top violated constraints:")
            for name, count in viol_counter.most_common(8):
                print(f"    {name:45s} {count:4d}/{len(rows)} ({count/len(rows)*100:.1f}%)")

        # --- 2. Re-evaluate samples using same LHS seed ---
        lb_idx = np.array(problem.bounds.lb, dtype=int)
        ub_idx = np.array(problem.bounds.ub, dtype=int)
        rng = np.random.default_rng(LHS_SEED)
        sampled_idx = _latin_hypercube_indices(lb_idx, ub_idx, N_SAMPLES, rng)

        indices_to_check = [i for i in CHECK_INDICES if i < len(rows)]
        print(f"\n  Re-evaluating samples {indices_to_check} ...")

        for idx in indices_to_check:
            row = rows[idx]
            x_idx = sampled_idx[idx].tolist()

            # Decode to verify var values match CSV
            params = decode(x_idx)
            rec = ctx.get(x_idx)
            ctx.reset()

            csv_y = float(row["y"])
            csv_yp = float(row["y_p"])
            csv_feas = row["feasible_constraints"] == "True"
            csv_succ = row["computation_successful"] == "True"

            rec_y = float(rec.get("y", math.nan))
            rec_yp = float(rec.get("y_p", math.nan))
            rec_feas = bool(rec.get("constraints_satisfied", False))
            rec_succ = bool(rec.get("computation_successful", False))

            # Compare
            checks = []
            if math.isfinite(csv_y) and math.isfinite(rec_y):
                if not math.isclose(csv_y, rec_y, rel_tol=1e-6):
                    checks.append(f"y: CSV={csv_y:.4f} vs calc={rec_y:.4f}")
            if math.isfinite(csv_yp) and math.isfinite(rec_yp):
                if not math.isclose(csv_yp, rec_yp, rel_tol=1e-6):
                    checks.append(f"y_p: CSV={csv_yp:.4f} vs calc={rec_yp:.4f}")
            if csv_feas != rec_feas:
                checks.append(f"feasible: CSV={csv_feas} vs calc={rec_feas}")
            if csv_succ != rec_succ:
                checks.append(f"successful: CSV={csv_succ} vs calc={rec_succ}")

            # Also check decoded var values match
            for vn in var_names:
                csv_val = float(row[vn])
                dec_val = float(params.get(vn, math.nan))
                if math.isfinite(csv_val) and math.isfinite(dec_val):
                    if not math.isclose(csv_val, dec_val, rel_tol=1e-6):
                        checks.append(f"{vn}: CSV={csv_val} vs decode={dec_val}")

            if checks:
                all_ok = False
                print(f"    Sample {idx+1:>4d}: MISMATCH")
                for c in checks:
                    print(f"      {c}")
            else:
                print(f"    Sample {idx+1:>4d}: OK  (y={csv_y:.2f}, y_p={csv_yp:.2f}, feasible={csv_feas})")

    print(f"\n{'='*70}")
    if all_ok:
        print("VALIDATION PASSED — all re-evaluated samples match CSV values.")
    else:
        print("VALIDATION FAILED — see MISMATCH entries above.")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
