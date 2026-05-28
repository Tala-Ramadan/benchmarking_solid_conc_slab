from __future__ import annotations

import csv
import math
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm

from slabdesignbench.optimization_problem_builder.problem_builder import (
    build_problems_for_slab_type,
)


def _sanitize_label(text: str) -> str:
    return text.replace(" ", "_").replace("/", "-") if text else ""


def _select_problem_bundles(
    bundles: dict[str, dict],
    problem_ids: list[str] | str | int | None,
) -> dict[str, dict]:
    if problem_ids is None:
        return bundles

    if isinstance(problem_ids, (str, int)):
        requested_ids = {str(problem_ids)}
    else:
        requested_ids = {str(pid) for pid in problem_ids}

    selected = {pid: bundle for pid, bundle in bundles.items() if str(pid) in requested_ids}
    missing = requested_ids - {str(pid) for pid in selected}
    if missing:
        print(f"Warning: Problem IDs not found: {sorted(missing)}")
    return selected


def _latin_hypercube_indices(
    lb_idx: np.ndarray,
    ub_idx: np.ndarray,
    n_samples: int,
    rng: np.random.Generator,
) -> np.ndarray:
    dim = len(lb_idx)
    lhs_unit = np.empty((n_samples, dim), dtype=float)

    for dim_idx in range(dim):
        lhs_unit[:, dim_idx] = (rng.permutation(n_samples) + rng.random(n_samples)) / n_samples

    n_levels = ub_idx - lb_idx + 1
    mapped = lb_idx + np.floor(lhs_unit * n_levels).astype(int)
    mapped = np.minimum(mapped, ub_idx)
    return mapped.astype(int)

#def _build_log_norm(values: np.ndarray) -> LogNorm | None:
    finite_positive = values[np.isfinite(values) & (values > 0.0)]
    if finite_positive.size < 2:
        return None

    vmin = float(np.min(finite_positive))
    vmax = float(np.max(finite_positive))
    if not math.isfinite(vmin) or not math.isfinite(vmax) or vmin <= 0.0 or vmin == vmax:
        return None

    return LogNorm(vmin=vmin, vmax=vmax)


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return

    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _analyze_problem(
    problem_id: str,
    bundle: dict,
    n_samples: int,
    seed: int,
    output_root: Path,
) -> dict:
    problem = bundle["problem"]
    ctx = bundle["ctx"]
    decode = bundle["decode"]
    var_names = bundle["var_names"]
    label = bundle.get("label", "")
    active_constraint_names = bundle.get("active_constraint_names", [])

    lb_idx = np.array(problem.bounds.lb, dtype=int)
    ub_idx = np.array(problem.bounds.ub, dtype=int)
    rng = np.random.default_rng(seed)
    sampled_idx = _latin_hypercube_indices(lb_idx, ub_idx, n_samples=n_samples, rng=rng)

    label_safe = _sanitize_label(label)
    folder_name = f"problem_{problem_id}__{label_safe}" if label_safe else f"problem_{problem_id}"
    problem_output_dir = output_root / folder_name
    problem_output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    violated_counter: dict[str, int] = {}

    for sample_id, x_idx in enumerate(sampled_idx, start=1):
        params = decode(x_idx.tolist())
        rec = ctx.get(x_idx.tolist())
        constraint_values = rec.get("constraint_values", {}) or {}

        # Only count ACTIVE constraints (respect problem_list.csv active flag)
        violated_names = [
            name for name, value in constraint_values.items()
            if name in active_constraint_names and float(value) > 1.0
        ]
        for name in violated_names:
            violated_counter[name] = violated_counter.get(name, 0) + 1

        y = float(rec.get("y", math.nan))
        y_p = float(rec.get("y_p", math.nan))
        penalty_ratio = y_p / y if math.isfinite(y) and y != 0.0 else math.nan
        row = {
            "sample_id": sample_id,
            "problem_id": problem_id,
            "label": label,
            "span_primary_m": params.get("span_primary_m"),
            "span_secondary_m": params.get("span_secondary_m"),
            "y": y,
            "y_p": y_p,
            "penalty_ratio": penalty_ratio,
            "feasible_constraints": bool(rec.get("constraints_satisfied", False)),
            "computation_successful": bool(rec.get("computation_successful", False)),
            "max_constraint_value": max((float(v) for v in constraint_values.values()), default=math.nan),
            "n_violated_constraints": len(violated_names),
            "violated_constraints": "|".join(violated_names),
            "analysis_error": rec.get("analysis_error"),
        }
        for name in var_names:
            row[name] = params.get(name)

        rows.append(row)
        ctx.reset()

    _write_csv(problem_output_dir / "lhs_samples.csv", rows)

    feasible_rows = [row for row in rows if row["feasible_constraints"]]
    successful_rows = [row for row in rows if row["computation_successful"]]
    best_feasible_y = min((float(row["y"]) for row in feasible_rows), default=math.nan)
    best_penalized_y = min((float(row["y_p"]) for row in rows), default=math.nan)
    top_violated = sorted(violated_counter.items(), key=lambda item: item[1], reverse=True)[:5]

    # --- DEBUG: show constraint violation stats ---
    print(f"\n  === DEBUG Problem {problem_id}: constraint violation frequency ===")
    print(f"  Total samples: {len(rows)}, successful: {len(successful_rows)}, feasible: {len(feasible_rows)}")
    for cname, count in sorted(violated_counter.items(), key=lambda x: x[1], reverse=True):
        print(f"    {cname}: violated in {count}/{len(rows)} samples ({100*count/len(rows):.1f}%)")
    # Show the best sample (lowest y_p) constraint details
    best_row = min(rows, key=lambda r: float(r["y_p"]))
    best_idx = best_row["sample_id"]
    print(f"\n  Best sample (lowest y_p): sample_id={best_idx}, y={best_row['y']}, y_p={best_row['y_p']}")
    print(f"    feasible={best_row['feasible_constraints']}, n_violated={best_row['n_violated_constraints']}")
    print(f"    violated: {best_row['violated_constraints']}")
    print(f"    max_constraint_value: {best_row['max_constraint_value']}")
    # Re-evaluate the best sample to show all constraint values
    best_x_idx = sampled_idx[best_idx - 1].tolist()
    best_rec = ctx.get(best_x_idx)
    best_cv = best_rec.get("active_constraint_values", {})
    print(f"    Active constraint_values for best sample:")
    for cn, cv in sorted(best_cv.items(), key=lambda x: x[1], reverse=True):
        flag = " *** VIOLATED ***" if cv > 1.0 else ""
        print(f"      {cn}: {cv:.4f}{flag}")
    ctx.reset()
    print(f"  === END DEBUG ===\n")

    return {
        "problem_id": problem_id,
        "label": label,
        "span_primary_m": rows[0]["span_primary_m"],
        "span_secondary_m": rows[0]["span_secondary_m"],
        "n_samples": len(rows),
        "n_feasible": len(feasible_rows),
        "feasible_share": len(feasible_rows) / len(rows) if rows else math.nan,
        "n_successful": len(successful_rows),
        "successful_share": len(successful_rows) / len(rows) if rows else math.nan,
        "best_y_feasible": best_feasible_y,
        "best_y_p": best_penalized_y,
        "top_violated_constraints": "|".join(name for name, _ in top_violated),
        "output_dir": str(problem_output_dir),
    }


def main() -> None:
    # =========================================================================
    # CONFIGURATION
    # =========================================================================
    slab_type = "solid_slab_one_way_concrete"
    problem_ids_to_run: list[str] | None = None  # e.g. ["1", "2"] or None for all
    n_samples_per_problem = 1500
    seed = 42
    run_tag = (
        f"{datetime.now():%Y%m%d_%H%M%S}"
        f"__vibration_false__gwp_only__seed_{seed}__n_{n_samples_per_problem}__primary_span_only"
    )
    output_root = Path.cwd() / "lhs_design_space_results" / slab_type / run_tag

    # =========================================================================
    # BUILD PROBLEMS & ANALYZE DESIGN SPACE
    # =========================================================================
    bundles = build_problems_for_slab_type(slab_type)
    selected_bundles = _select_problem_bundles(bundles, problem_ids_to_run)

    if not selected_bundles:
        raise ValueError("No problems selected for LHS design-space analysis.")

    output_root.mkdir(parents=True, exist_ok=True)
    summary_rows = []

    print(f"Running LHS design-space analysis for slab_type={slab_type}")
    print(f"Problems: {list(selected_bundles.keys())}")
    print(f"Samples per problem: {n_samples_per_problem}")
    print(f"Seed: {seed}")
    print(f"Output root: {output_root}")

    for problem_id, bundle in selected_bundles.items():
        summary = _analyze_problem(
            problem_id=problem_id,
            bundle=bundle,
            n_samples=n_samples_per_problem,
            seed=seed,
            output_root=output_root,
        )
        summary_rows.append(summary)
        print(
            f"Problem {problem_id}: feasible={summary['n_feasible']}/{summary['n_samples']} "
            f"({summary['feasible_share']:.1%}) | best feasible y={summary['best_y_feasible']:.4f} "
            f"| best y_p={summary['best_y_p']:.4f}"
        )

    _write_csv(output_root / "lhs_summary.csv", summary_rows)
    print("Done. Summary written to lhs_summary.csv")


if __name__ == "__main__":
    main()