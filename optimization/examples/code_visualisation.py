"""
Code visualisation for `slabdesignbench`.

Produces:
- slab_dep.svg : dependency graph between modules in slabdesignbench
- slab_c4.svg  : "C4-style" overview with ALL modules, grouped by top-level submodule
- slab_seq_build_problem.svg        : sequence for building the optimisation problem
- slab_seq_optimisation_loop.svg    : sequence for optimisation loop

All SVGs via Graphviz. Also prints DOT sources to stdout.

Run inside your venv (where slabdesignbench is importable):

    python src/testing/code_visualisation.py
"""

from __future__ import annotations

import ast
import importlib
from collections import defaultdict
from pathlib import Path

from graphviz import Digraph

import slabdesignbench  # make sure this imports in your venv

PKG_NAME = "slabdesignbench"
PKG_DIR = Path(slabdesignbench.__file__).resolve().parent


# -----------------------------------------------------------------------------
# 1. Discover modules in the package
# -----------------------------------------------------------------------------


def iter_modules() -> dict[str, Path]:
    """
    Return {fully.qualified.module.name: file_path} for all .py files
    in the slabdesignbench package.
    """
    modules: dict[str, Path] = {}

    for path in PKG_DIR.rglob("*.py"):
        rel = path.relative_to(PKG_DIR)
        parts = rel.with_suffix("").parts  # e.g. ('core', 'problem_builder', '__init__')

        if parts and parts[-1] == "__init__":
            parts = parts[:-1]

        if not parts:
            modname = PKG_NAME
        else:
            modname = PKG_NAME + "." + ".".join(parts)

        modules[modname] = path

    return modules


# -----------------------------------------------------------------------------
# 2. Build dependency edges by static AST analysis
# -----------------------------------------------------------------------------


def _resolve_internal(name: str | None, modules_set: set[str]) -> str | None:
    """
    Map an imported name to a known internal module (or None).
    Only keep imports inside `slabdesignbench`.
    """
    if not name:
        return None

    name = name.strip()
    if not (name == PKG_NAME or name.startswith(PKG_NAME + ".")):
        return None

    candidate = name
    while candidate not in modules_set and "." in candidate:
        candidate = candidate.rsplit(".", 1)[0]

    return candidate if candidate in modules_set else None


def _resolve_relative(module: str | None, level: int, src: str, modules_set: set[str]) -> str | None:
    """
    Resolve a relative import (from .x import ...) to a fully qualified internal module.
    """
    src_parts = src.split(".")
    if src_parts[0] != PKG_NAME:
        return None

    pkg_parts = src_parts[:-1]

    if level > len(pkg_parts):
        base_parts = [PKG_NAME]
    else:
        base_parts = src_parts[: len(src_parts) - level]

    if module:
        full = ".".join(base_parts + [module])
    else:
        full = ".".join(base_parts)

    return _resolve_internal(full, modules_set)


def build_dep_edges() -> tuple[list[tuple[str, str]], set[str]]:
    """
    Build directed edges (module -> imported module) for modules under `slabdesignbench`
    via static AST parsing.
    """
    modules = iter_modules()
    modules_set = set(modules.keys())

    edges: set[tuple[str, str]] = set()

    for modname, path in modules.items():
        src = modname
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = _resolve_internal(alias.name, modules_set)
                    if target and target != src:
                        edges.add((src, target))

            elif isinstance(node, ast.ImportFrom):
                level = node.level or 0
                module = node.module

                if level == 0:
                    target = _resolve_internal(module, modules_set)
                else:
                    target = _resolve_relative(module, level, src, modules_set)

                if target and target != src:
                    edges.add((src, target))

    return sorted(edges), modules_set


# -----------------------------------------------------------------------------
# 3. Dependency graph (full module-level)
# -----------------------------------------------------------------------------


def dep_graph_to_graphviz(edges: list[tuple[str, str]]) -> Digraph:
    dot = Digraph(comment="slabdesignbench module dependencies")
    dot.attr(rankdir="LR", fontsize="10")

    for src, dst in edges:
        for name in (src, dst):
            if name.startswith(PKG_NAME + "."):
                label = name.split(".", 1)[1]
            else:
                label = name
            dot.node(name, label, shape="box")

        dot.edge(src, dst)

    return dot


# -----------------------------------------------------------------------------
# 4. "C4-style" graph: ALL modules, grouped by top-level submodule
# -----------------------------------------------------------------------------


def first_level_component(modname: str) -> str | None:
    """
    Map 'slabdesignbench.a.b.c' -> 'slabdesignbench.a' (first-level submodule).
    """
    parts = modname.split(".")
    if parts[0] != PKG_NAME or len(parts) < 2:
        return None
    return PKG_NAME + "." + parts[1]


def group_modules_by_top_level(
    modules_set: set[str],
) -> tuple[dict[str, list[str]], list[str]]:
    """
    Group all modules by their top-level submodule.

    Returns:
        groups: {top_level_mod: [full modules under it]}
        root:   list of modules directly under slabdesignbench
    """
    groups: dict[str, list[str]] = defaultdict(list)
    root: list[str] = []

    for m in modules_set:
        if m == PKG_NAME:
            root.append(m)
            continue

        top = first_level_component(m)
        if top is None:
            root.append(m)
        else:
            groups[top].append(m)

    for k in groups:
        groups[k].sort()
    root.sort()
    return groups, root


def c4_graph_modules_to_graphviz(
    groups: dict[str, list[str]],
    root_modules: list[str],
    edges: list[tuple[str, str]],
) -> Digraph:
    """
    Graphviz Digraph: top-level clusters, module nodes only.
    """
    dot = Digraph(comment="slabdesignbench C4-style overview (modules)")
    dot.attr(rankdir="LR", fontsize="10")

    if root_modules:
        with dot.subgraph(name="cluster_root") as sub:
            sub.attr(
                label=f"{PKG_NAME} (root modules)",
                style="rounded",
                color="lightgrey",
            )
            for m in root_modules:
                label = m.split(".", 1)[-1] if "." in m else m
                sub.node(m, f"{label}\n(Module)", shape="box")

    for idx, (top, mods) in enumerate(sorted(groups.items())):
        short_top = top.split(".", 1)[1]
        with dot.subgraph(name=f"cluster_{idx}") as sub:
            sub.attr(
                label=f"{short_top} (Container)",
                style="rounded",
                color="lightgrey",
            )
            for m in mods:
                short = m.split(".", 1)[1]
                sub.node(m, f"{short}\n(Module)", shape="box")

    for src, dst in edges:
        dot.edge(src, dst)

    return dot


# -----------------------------------------------------------------------------
# 5. High-level sequence diagrams using real module paths
# -----------------------------------------------------------------------------


# Each step: (sender_label, receiver_module, receiver_function)
#
# - sender_label is what you want to see as the *box* on the diagram
#   (can be "User", "run_penalized_demo", "Optimiser", etc.).
# - receiver_module is a real Python module path for slabdesignbench modules.
#   Non-slabdesignbench labels ("run_penalized_demo", "Optimiser") are treated
#   as external participants and not validated.
# - receiver_function is the function name you conceptually want to show.
#   We can optionally validate these later.

SEQUENCE_SCENARIOS: dict[str, list[tuple[str, str, str]]] = {
    "build_problem": [
        ("User", "run_penalized_demo", "main"),  # conceptual entry point
        ("run_penalized_demo", "slabdesignbench.optimization_problem_builder.problem_builder", "build_problem"),
        (
            "slabdesignbench.optimization_problem_builder.problem_builder",
            "slabdesignbench.optimization_problem_builder.import_problem_from_csv",
            "load_specs",
        ),
        (
            "slabdesignbench.optimization_problem_builder.problem_builder",
            "slabdesignbench.optimization_problem_builder.import_problem_from_csv",
            "load_input_data",
        ),
        (
            "slabdesignbench.optimization_problem_builder.problem_builder",
            "slabdesignbench.optimization_problem_builder.problem_evaluator",
            "init_cache",
        ),
        ("slabdesignbench.optimization_problem_builder.problem_builder", "run_penalized_demo", "return_problem"),
    ],
    "optimisation_loop": [
        ("run_penalized_demo", "Optimiser", "run_optimisation"),
        ("Optimiser", "slabdesignbench.optimization_problem_builder.problem_evaluator", "evaluate_design"),
        (
            "slabdesignbench.optimization_problem_builder.problem_evaluator",
            "slabdesignbench.slab_models.slab_types.solid_slab_one_way_concrete.analysis_ec2_de",
            "run_analysis",
        ),
        (
            "slabdesignbench.slab_models.slab_types.solid_slab_one_way_concrete.analysis_ec2_de",
            "slabdesignbench.slab_models.codes.ec2_2004_de.loads",
            "compute_loads",
        ),
        (
            "slabdesignbench.slab_models.slab_types.solid_slab_one_way_concrete.analysis_ec2_de",
            "slabdesignbench.slab_models.generic.internal_forces",
            "compute_internal_forces",
        ),
        (
            "slabdesignbench.slab_models.slab_types.solid_slab_one_way_concrete.analysis_ec2_de",
            "slabdesignbench.slab_models.generic.deformations",
            "compute_deformations",
        ),
        (
            "slabdesignbench.slab_models.slab_types.solid_slab_one_way_concrete.analysis_ec2_de",
            "slabdesignbench.slab_models.codes.ec2_2004_de.checks_structural",
            "check_structural_code",
        ),
        ("slabdesignbench.optimization_problem_builder.problem_evaluator", "Optimiser", "return_objective_values"),
    ],
}

# Set this to True once you've aligned function names with reality
CHECK_FUNCTIONS = False


def validate_scenarios() -> None:
    """
    Validate that all receiver modules in SEQUENCE_SCENARIOS that belong
    to slabdesignbench actually exist. Optionally also validate functions.
    """
    for scen_name, steps in SEQUENCE_SCENARIOS.items():
        for _sender_label, recv_mod, recv_func in steps:
            # Only enforce for slabdesignbench.* modules
            if recv_mod.startswith(PKG_NAME):
                try:
                    mod = importlib.import_module(recv_mod)
                except ImportError as e:
                    raise ImportError(f"Scenario '{scen_name}': cannot import module '{recv_mod}'") from e

                if CHECK_FUNCTIONS and not hasattr(mod, recv_func):
                    raise AttributeError(f"Scenario '{scen_name}': module '{recv_mod}' has no function '{recv_func}'")


def sequence_to_graphviz(
    steps: list[tuple[str, str, str]],
    title: str,
) -> Digraph:
    """
    "Sequence-like" diagram in Graphviz:

    - participants (sender labels and receiver modules) as nodes left to right
    - directed edges with labels '1. module.func()', '2. module.func()', ...
    """
    dot = Digraph(comment=title)
    dot.attr(rankdir="LR", fontsize="10")

    # preserve order of first appearance for participants
    participants: list[str] = []
    for sender_label, recv_mod, _ in steps:
        if sender_label not in participants:
            participants.append(sender_label)
        if recv_mod not in participants:
            participants.append(recv_mod)

    for p in participants:
        # label: last bit for slabdesignbench modules, literal for others
        if p.startswith(PKG_NAME) and "." in p:
            label = p.split(".")[-1]
        else:
            label = p
        dot.node(p, label, shape="box")

    for idx, (sender_label, recv_mod, recv_func) in enumerate(steps, start=1):
        # show short module name in edge label
        if recv_mod.startswith(PKG_NAME) and "." in recv_mod:
            short_mod = recv_mod.split(".")[-1]
        else:
            short_mod = recv_mod
        label = f"{idx}. {short_mod}.{recv_func}()"
        dot.edge(sender_label, recv_mod, label=label)

    return dot


# -----------------------------------------------------------------------------
# 6. Optional helper: inspect real functions per module
# -----------------------------------------------------------------------------


def print_functions_per_module() -> None:
    """
    Debug helper: print all top-level functions in each slabdesignbench module.
    Call from __main__ once if you want to copy real function names
    into SEQUENCE_SCENARIOS, then comment it out again.
    """
    modules = iter_modules()
    for modname, path in sorted(modules.items()):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        fnames = [node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if fnames:
            print(f"\n{modname}:")
            for f in sorted(fnames):
                print(f"  - {f}")


# -----------------------------------------------------------------------------
# 7. Main
# -----------------------------------------------------------------------------


if __name__ == "__main__":
    # Static structure
    dep_edges, modules_set = build_dep_edges()
    print(f"Found {len(modules_set)} modules, {len(dep_edges)} internal dependency edges.")

    dep_dot = dep_graph_to_graphviz(dep_edges)
    dep_dot.render("slab_dep", format="svg", cleanup=True)
    print("Generated slab_dep.svg")

    print("\n=== DOT: slabdesignbench dependency graph ===")
    print(dep_dot.source)

    groups, root_modules = group_modules_by_top_level(modules_set)
    print(f"\nC4-level groups: {len(groups)} top-level containers, {len(root_modules)} root modules.")

    c4_dot = c4_graph_modules_to_graphviz(groups, root_modules, dep_edges)
    c4_dot.render("slab_c4", format="svg", cleanup=True)
    print("Generated slab_c4.svg")

    print("\n=== DOT: slabdesignbench C4-style graph (modules) ===")
    print(c4_dot.source)

    # Uncomment once if you want to see actual functions per module
    # print_functions_per_module()

    # High-level sequence diagrams with validated module names
    print("\nValidating sequence scenarios (modules only)...")
    validate_scenarios()
    print("All slabdesignbench module names in scenarios are valid.\n")

    for name, steps in SEQUENCE_SCENARIOS.items():
        print(f"Building sequence scenario '{name}' with {len(steps)} steps...")
        seq_dot = sequence_to_graphviz(steps, title=f"slabdesignbench sequence: {name}")
        out_name = f"slab_seq_{name}"
        seq_dot.render(out_name, format="svg", cleanup=True)
        print(f"Generated {out_name}.svg")

        print(f"\n=== DOT: sequence graph '{name}' ===")
        print(seq_dot.source)
