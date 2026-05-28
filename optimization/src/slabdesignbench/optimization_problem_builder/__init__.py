"""
optimization_problem_builder
============================

IOH / Hyperopt side - builds optimization problems from CSV configurations.

Modules:
- import_problem_from_csv: CSV import and parameter/constraint loading
- problem_builder: IOH problem construction
- problem_evaluator: Evaluation context and caching
"""

from slabdesignbench.optimization_problem_builder.import_problem_from_csv import (
    _req_param,
    build_space,
    load_constraint_defaults,
    load_param_defaults,
    load_problems_combined,
    make_decode,
)
from slabdesignbench.optimization_problem_builder.problem_builder import (
    build_problems_for_slab,
    build_problems_for_slab_type,
)
from slabdesignbench.optimization_problem_builder.problem_evaluator import EvalContext

__all__ = [
    # CSV import
    "_req_param",
    "load_param_defaults",
    "load_constraint_defaults",
    "load_problems_combined",
    "build_space",
    "make_decode",
    # Problem building
    "build_problems_for_slab",
    "build_problems_for_slab_type",
    # Evaluation
    "EvalContext",
]
