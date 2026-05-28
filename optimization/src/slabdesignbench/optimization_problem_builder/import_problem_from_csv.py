"""
import_problem_from_csv.py
==========================

CSV import utilities for the optimization problem builder.

This module provides:
1. CSV readers and parsers
2. Parameter (fixed and variable) and constraint loading from CSV files
3. Problem configuration loading and merging
4. Index-to-value decoder generation

The CSV files define:
- parameter_defaults.csv: Parameter definitions (values, bounds, roles)
- constraint_defaults.csv: Constraint definitions (kind, enforcement, weights)
- problem_list.csv: Per-problem overrides and configurations
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from ioh.iohcpp import ConstraintEnforcement as CE

# =============================================================================
# CSV READERS AND PARSERS
# =============================================================================


def _req_param(params: dict, name: str) -> float:
    """
    Get a numeric parameter or fail loudly with a helpful message.

    Used in analysis functions to safely extract parameters from the decoded dict.

    Parameters
    ----------
    params : dict
        Parameter dictionary from decode().
    name : str
        Parameter name to extract.

    Returns
    -------
    float
        The parameter value as float.

    Raises
    ------
    KeyError
        If the parameter is missing.
    ValueError
        If the parameter cannot be converted to float.
    """
    try:
        val = params[name]
    except KeyError as e:
        raise KeyError(f"Required parameter '{name}' missing in params. Got keys: {list(params.keys())}") from e
    try:
        return float(val)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Parameter '{name}' must be numeric, got {val!r}") from e


def _read_rows(path: Path, expected_keys: list[str] | None = None):
    """
    Read ;-delimited CSV, skip blank lines, trim whitespace.

    More forgiving headers:
    - UTF-8 with BOM supported
    - Header names matched case/space-insensitively
    - Extra columns allowed, but all expected_keys must be present

    Parameters
    ----------
    path : Path
        Path to the CSV file.
    expected_keys : List[str] | None
        Required column names. If None, returns all columns.

    Yields
    ------
    dict
        Row as dictionary with cleaned values.

    Raises
    ------
    ValueError
        On empty/missing header, missing expected keys, or no data rows.
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        # Error check: empty file / missing header
        if reader.fieldnames is None:
            raise ValueError(f"{path}: file is empty or missing a header row.")

        raw_headers = reader.fieldnames
        # Normalize headers for matching (strip + lower)
        norm_headers = [(h or "").strip().lower() for h in raw_headers]
        # Map normalized header -> original header text
        norm_to_raw = {hn: raw_headers[i] for i, hn in enumerate(norm_headers)}

        # Header requirement: all expected_keys must be present (allow extras)
        if expected_keys is not None:
            need = [(k or "").strip().lower() for k in expected_keys]
            missing = [k for k in need if k not in norm_to_raw]
            if missing:
                raise ValueError(f"{path}: missing header columns: {missing}. Found headers: {raw_headers}")

        yielded = 0
        for row in reader:
            # Skip fully blank lines
            if not any((v or "").strip() for v in row.values()):
                continue

            if expected_keys is not None:
                # Build row using the canonical expected_keys order/names
                clean = {}
                for k in expected_keys:
                    kn = (k or "").strip().lower()
                    rk = norm_to_raw[kn]  # original header name
                    v = row.get(rk, "")
                    clean[k] = v.strip() if v is not None else ""
            else:
                # No schema provided: return normalized-key dict
                clean = {}
                for hn, rk in norm_to_raw.items():
                    v = row.get(rk, "")
                    clean[hn] = v.strip() if v is not None else ""

            yielded += 1
            yield clean

        # No data rows
        if yielded == 0:
            raise ValueError(f"{path}: no data rows found (only header and/or blank lines).")


def _to_bool(s: str, default=False) -> bool:
    """Parse string to bool. Empty string returns default."""
    return default if s == "" else s.lower() in ("1", "true", "yes", "y")


def _to_float(s: str, default=None):
    """Parse string to float. Empty string returns default."""
    return default if s == "" else float(s)


def _enf(s: str, default="HIDDEN"):
    """
    Parse string to IOH ConstraintEnforcement enum.

    Parameters
    ----------
    s : str
        One of: "NOT", "HIDDEN", "SOFT", "HARD", "OVERRIDE"
    default : str
        Default if s is empty.

    Returns
    -------
    ConstraintEnforcement
        The IOH enforcement enum value.
    """
    k = (s or default).upper()
    return {
        "NOT": CE.NOT,
        "HIDDEN": CE.HIDDEN,
        "SOFT": CE.SOFT,
        "HARD": CE.HARD,
        "OVERRIDE": CE.OVERRIDE,
    }[k]


# =============================================================================
# PARAMETER LOADING
# =============================================================================


def load_param_defaults(path: str | Path) -> dict[str, dict]:
    """
    Read parameter_defaults.csv and return parameter specifications.

    Returns
    -------
    Dict[str, dict]
        { name: {domain, values, lb, ub, fixed_idx, role, value_type} }

    Required CSV columns:
        name;domain;values;grid_start;grid_step;grid_count;
        default_lb;default_ub;default_fixed;role;value_type

    Notes
    -----
    - domain: 'catalog' uses 'values' as a |-separated list.
              'grid' uses start/step/count to generate values.
    - role: 'var' or 'fixed' (per default; problem_list.csv can override)
    - lb/ub/fixed_idx are 0-based indices into 'values'.
    - value_type: 'float', 'int', or 'str' (default: 'float').
    """
    path = Path(path)
    spec: dict[str, dict] = {}

    expected = [
        "name",
        "domain",
        "values",
        "grid_start",
        "grid_step",
        "grid_count",
        "default_lb",
        "default_ub",
        "default_fixed",
        "role",
        "value_type",
    ]

    for r in _read_rows(path, expected):
        name = r["name"]
        dom = (r["domain"] or "").lower()
        role = (r["role"] or "var").lower()
        if role not in ("var", "fixed"):
            raise ValueError(f"{path}: parameter '{name}' has invalid role '{role}' (use 'var' or 'fixed').")

        value_type = (r.get("value_type") or "float").strip().lower()

        if dom == "catalog":
            vals_str = (r["values"] or "").strip('"').strip()
            if not vals_str:
                raise ValueError(f"{path}: parameter '{name}' uses domain 'catalog' but has empty 'values'.")

            if value_type == "str":
                # Whole cell as ONE value (e.g., "150,157,181,...")
                vals = [vals_str]

            elif value_type == "int":
                try:
                    vals = [int(v) for v in vals_str.split("|")]
                except ValueError as e:
                    raise ValueError(f"{path}: parameter '{name}' has non-integer catalog value.") from e

            elif value_type == "float":
                try:
                    vals = [float(v) for v in vals_str.split("|")]
                except ValueError as e:
                    raise ValueError(f"{path}: parameter '{name}' has non-numeric catalog value.") from e

            else:
                raise ValueError(
                    f"{path}: parameter '{name}' has unknown value_type '{value_type}' (use 'float', 'int' or 'str')."
                )

        elif dom == "grid":
            try:
                start = float(r["grid_start"])
                step = float(r["grid_step"])
                count = int(r["grid_count"])
            except ValueError as e:
                raise ValueError(f"{path}: parameter '{name}' has invalid grid_start/step/count.") from e
            if count <= 0:
                raise ValueError(f"{path}: parameter '{name}' has non-positive grid_count={count}.")
            vals = [start + i * step for i in range(count)]

        else:
            raise ValueError(f"{path}: parameter '{name}' has unknown domain '{dom}' (use 'catalog' or 'grid').")

        L = len(vals)
        if L == 0:
            raise ValueError(f"{path}: parameter '{name}' produced an empty value list.")

        def clamp_idx(s: str, dflt: int, length: int = L) -> int:
            # Empty cell -> default; otherwise clamp to [0, length-1]
            return dflt if s == "" else max(0, min(int(float(s)), length - 1))

        lb = clamp_idx(r["default_lb"], 0)
        ub = clamp_idx(r["default_ub"], L - 1)
        if lb > ub:
            lb, ub = ub, lb

        fixed = clamp_idx(r["default_fixed"], lb)

        spec[name] = {
            "domain": dom,
            "values": vals,
            "lb": lb,
            "ub": ub,
            "fixed_idx": fixed,
            "role": role,
            "value_type": value_type,
        }

    return spec


# =============================================================================
# OPTIMIZATION SPACE BUILDING
# =============================================================================


def build_space(model: dict[str, dict]) -> tuple[list[str], list[int], list[int]]:
    """
    From a full parameter model (with roles), extract the optimization space.

    Parameters
    ----------
    model : Dict[str, dict]
        Parameter model with role assignments.

    Returns
    -------
    tuple[list[str], list[int], list[int]]
        (var_names, lb_idx_list, ub_idx_list)
    """
    var_names, lb, ub = [], [], []
    for n, m in model.items():
        if m["role"] == "var":
            var_names.append(n)
            lb.append(m["lb"])
            ub.append(m["ub"])
    return var_names, lb, ub


def make_decode(model: dict[str, dict], var_names: list[str]):
    """
    Build a decoder: decode(x_idx) -> dict of parameters.

    Merges fixed parameters with variable indices (clamped to lb/ub).
    No aliases/synonyms. Parameter names must match the CSVs exactly.

    Parameters
    ----------
    model : Dict[str, dict]
        Parameter model with role assignments.
    var_names : List[str]
        List of variable parameter names.

    Returns
    -------
    Callable[[List[int]], Dict[str, Any]]
        Decoder function.
    """
    n_vars = len(var_names)

    def decode(x_idx: list[int]) -> dict[str, Any]:
        if len(x_idx) != n_vars:
            raise ValueError(f"decode: got {len(x_idx)} indices, expected {n_vars} ({var_names}).")

        full: dict[str, Any] = {}

        # 1) Fixed parameters
        for name, m in model.items():
            if m["role"] == "fixed":
                full[name] = m["values"][m["fixed_idx"]]

        # 2) Variable parameters
        for name, k in zip(var_names, x_idx, strict=True):
            m = model[name]
            kk = max(m["lb"], min(int(k), m["ub"]))
            full[name] = m["values"][kk]

        return full

    return decode


# =============================================================================
# CONSTRAINT LOADING
# =============================================================================


def load_constraint_defaults(path: str | Path) -> dict[str, dict]:
    """
    Read constraint_defaults.csv and return constraint specifications.

    Returns
    -------
    Dict[str, dict]
        { name: {kind, enforced, weight, exponent, active_default} }
    """
    path = Path(path)
    spec: dict[str, dict] = {}
    expected = ["name", "kind", "enforced", "weight", "exponent", "active_default"]

    for r in _read_rows(path, expected):
        spec[r["name"]] = {
            "kind": (r["kind"] or "").lower(),
            "enforced": _enf(r["enforced"] or "SOFT"),
            "weight": _to_float(r["weight"], 1.0),
            "exponent": _to_float(r["exponent"], 1.0),
            "active_default": _to_bool(r["active_default"], True),
        }
    return spec


# =============================================================================
# PROBLEM LOADING AND MERGING
# =============================================================================


def load_problems_combined(
    param_defaults: dict[str, dict],
    constr_defaults: dict[str, dict],
    problem_list_csv: str | Path,
) -> dict[str, dict]:
    """
    Read problem_list.csv and overlay per-problem configuration onto defaults.

    Parameters
    ----------
    param_defaults : Dict[str, dict]
        Parameter defaults from load_param_defaults().
    constr_defaults : Dict[str, dict]
        Constraint defaults from load_constraint_defaults().
    problem_list_csv : str | Path
        Path to problem_list.csv.

    Returns
    -------
    Dict[str, dict]
        {
            problem_id: {
                "model": merged parameter model (roles + lb/ub/fixed_idx adjusted),
                "constraints": { name: {kind, enforced, weight, exponent, active} },
                "label": str,
            },
            ...
        }
    """
    problem_list_csv = Path(problem_list_csv)
    expected = [
        "problem_id",
        "type",
        "name",
        "role",
        "lb_idx",
        "ub_idx",
        "fixed_idx",
        "active",
        "enforced",
        "weight",
        "exponent",
        "label",
    ]
    rows = list(_read_rows(problem_list_csv, expected))

    by_problem: dict[str, dict] = {}
    # Initialize per-problem copy of parameter defaults
    for r in rows:
        problem_ID = r["problem_id"]
        by_problem.setdefault(
            problem_ID,
            {
                "model": {k: v.copy() for k, v in param_defaults.items()},
                "constraints": {},
                "label": r["label"],
            },
        )

    for r in rows:
        problem_ID, typ, name = (
            r["problem_id"],
            (r["type"] or "").lower(),
            r["name"],
        )
        info = by_problem[problem_ID]

        if typ == "param":
            if name not in info["model"]:
                raise KeyError(f"{problem_list_csv}: problem {problem_ID} refers to unknown parameter '{name}'.")
            m = info["model"][name]
            role = (r["role"] or m["role"]).lower()
            if role not in ("var", "fixed"):
                raise ValueError(f"{problem_list_csv}: problem {problem_ID}, param '{name}' has invalid role '{role}'.")
            m["role"] = role

            L = len(m["values"])

            def clamp(s, d, length: int = L):
                return d if s == "" else max(0, min(int(float(s)), length - 1))

            if role == "var":
                m["lb"] = clamp(r["lb_idx"], m["lb"])
                m["ub"] = clamp(r["ub_idx"], m["ub"])
                if m["lb"] > m["ub"]:
                    m["lb"], m["ub"] = m["ub"], m["lb"]
            else:
                m["fixed_idx"] = clamp(r["fixed_idx"], m["fixed_idx"])

        elif typ == "constraint":
            if name not in constr_defaults:
                raise KeyError(f"{problem_list_csv}: problem {problem_ID} refers to unknown constraint '{name}'.")
            base = constr_defaults[name].copy()
            base["active"] = _to_bool(r["active"], base["active_default"])
            if r["enforced"]:
                prev = base["enforced"].name if hasattr(base["enforced"], "name") else "SOFT"
                base["enforced"] = _enf(r["enforced"], prev)
            if r["weight"]:
                base["weight"] = float(r["weight"])
            if r["exponent"]:
                base["exponent"] = float(r["exponent"])
            info["constraints"][name] = base

        if r["label"]:
            info["label"] = r["label"]

    return by_problem
