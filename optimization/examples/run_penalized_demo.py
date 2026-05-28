from __future__ import annotations

import os
from datetime import datetime
import io
from importlib import import_module
from pathlib import Path
from contextlib import redirect_stdout

import ioh
import warnings
import nlopt
import numpy as np

# import opt. algorithms
import pymoo
import rbfopt
from hyperopt import STATUS_OK, Trials, fmin, hp, tpe
from ioh import logger 
from rbfopt.rbfopt_black_box import RbfoptBlackBox

from pymoo.algorithms.soo.nonconvex.ga import GA
from pymoo.algorithms.soo.nonconvex.cmaes import CMAES
from pymoo.core.problem import Problem
from pymoo.problems.functional import FunctionalProblem
from pymoo.optimize import minimize

import matplotlib.pyplot as plt

from slabdesignbench.optimization_problem_builder.problem_builder import (
    build_problems_for_slab_type,)

class PymooIOHProblem(Problem):
        # dabei ist "problem" das IOH-Problem, das in die pymoo-Problemdefinition eingebunden werden soll
    def __init__(self, problem):
        self.ioh_problem = problem
        super().__init__(n_var=problem.meta_data.n_variables, 
                    n_obj=1, n_ieq_constr=0, xl=problem.bounds.lb, xu=problem.bounds.ub)
      
    def _evaluate(self, X, out, *args, **kwargs):
        F = np.array([self.ioh_problem([int(round(xi)) for xi in x]) for x in X])
        out["F"] = F

# ---------------------------------------------------------------------------
# Wrapper fuer pymoo-Algorithmen (GA, CMA-ES) mit IOH-Integration.
#   GA (Genetischer Algorithmus): populationsbasiert, geeignet fuer
#     ganzzahlige/kombinatorische Suchräume, robust gegenueber Multimodalitaet.
#   CMA-ES: evolutionaere Strategie mit adaptiver Kovarianzmatrix,
#     gut fuer glatte, unimodale Probleme.
# pymoo arbeitet intern mit reellen Zahlen -> Kandidaten werden in
# PymooIOHProblem._evaluate() via np.round() auf Integer gerundet.
# Seed wird pro Run inkrementiert (default_random_seed + run_index),
# um unabhaengige, reproduzierbare Laeufe zu gewaehrleisten.
# ---------------------------------------------------------------------------
class PymooAlgorithms:

    default_random_seed = 2
    default_pop_size = 50
    default_sigma = 0.5

    def __init__(self, pymoo_algo: str, max_evaluations: int, seed : int | None = None, pop_size: int | None = None, sigma: float | None = None): 
        self.pymoo_algo = pymoo_algo
        self.name = f"Pymoo_{self.pymoo_algo}"  
        self.max_evaluations = max_evaluations
        self.seed = seed if seed is not None else self.default_random_seed
        self.pop_size = pop_size if pop_size is not None else self.default_pop_size
        self.sigma = sigma if sigma is not None else self.default_sigma
        
    def _get_pymoo_algorithm(self):
        match self.pymoo_algo:
            case "GA":
                return GA(seed=self.seed, pop_size=self.pop_size, eliminate_duplicates=True)
            case "CMAES":
                return CMAES(seed=self.seed, pop_size=self.pop_size, sigma=self.sigma)
            case _:
                raise ValueError(f"Unsupported Pymoo algoritm: '{self.pymoo_algo}'. Choose: 'GA' or 'CMAES'.")

    def __call__(self, problem):
        # an der stelle wird der Wrapper aufgerufen
        pymoo_problem = PymooIOHProblem(problem)
        #in jedem run wird eine neue Instanz des Algorithmus erstellt, damit z.B. der Zufallsseed korrekt funktioniert 
        # & Population, Generation, Fitnesswerte in verschiedenn runs nicht gespeichert werden 
        self.algorithm = self._get_pymoo_algorithm()
       
        res = minimize(
            problem=pymoo_problem, 
            algorithm=self.algorithm, 
            seed=self.seed, 
            verbose=False, 
            save_history=False, 
            return_least_infeasible=False, 
            return_nondominated_front=False, 
            termination=('n_eval', self.max_evaluations))

        x_best = [int(round(xi)) for xi in res.X] 
        f_best = float(res.F[0]) 
        problem(x_best)
        return f_best, x_best  


# ---------------------------------------------------------------------------
# Wrapper fuer NLopt-Algorithmen (DIRECT, SBPLX) mit IOH-Integration.
#   DIRECT / GN_DIRECT_L: globaler, deterministischer Algorithmus
#     (Dividing Rectangles), gradientenfrei, geeignet fuer niedrig-
#     dimensionale Suchräume mit begrenztem Auswertungsbudget.
#   SBPLX / LN_SBPLX: lokale, gradientenfreie Simplexsuche (Subplex).
# NLopt erhaelt reelle Grenzen; die Zielfunktion rundet x intern auf
# Integer (siehe objective() innerhalb von __call__).
# ---------------------------------------------------------------------------
class NloptAlgorithms:
    
    def __init__(self, nlopt_algo: str, max_evaluations: int):
        self.nlopt_algo = nlopt_algo
        self.name = f"NLopt_{self.nlopt_algo}"
        self.max_evaluations = max_evaluations  

    def _get_nlopt_algorithm(self):
        match self.nlopt_algo:
            case "DIRECT":
                return nlopt.GN_DIRECT_L
            case "SBPLX":
                return nlopt.LN_SBPLX
            case _:
                raise ValueError(f"Unsupported NLopt algorithm: '{self.nlopt_algo}'. Choose: 'DIRECT' or 'SBPLX'.")   
    
    def __call__(self, problem):
        dim = problem.meta_data.n_variables
        lb = [float(problem.bounds.lb[i]) for i in range(dim)]
        ub = [float(problem.bounds.ub[i]) for i in range(dim)]

        self.algorithm = self._get_nlopt_algorithm()
        opt = nlopt.opt(self.algorithm, dim)
        opt.set_lower_bounds(lb)
        opt.set_upper_bounds(ub)

        def objective(x, grad):
            x_int = [int(round(xi)) for xi in x]
            y = problem(x_int)  # penalised objective from IOH
            return float(y)
        
        opt.set_min_objective(objective)
        opt.set_maxeval(self.max_evaluations)

        x0 = [(lo + hi) / 2.0 for lo, hi in zip(lb, ub, strict=True)]

       # try:
        x_best = opt.optimize(x0)
        f_best = float(opt.last_optimum_value())
        # except nlopt.RoundoffLimited:
        #     # If DIRECT bails out with numerical issues, still grab the best seen
        #     x_best = opt.last_optimize_result()  # may not be super helpful, but keep structure
        #     f_best = float(opt.last_optimum_value())

        # Round back to ints
        x_best_int = [int(round(xi)) for xi in x_best]
        problem(x_best_int)
        return f_best, x_best_int


# ---------------------------------------------------------------------------
# Wrapper fuer Hyperopt-TPE (Tree Parzen Estimator) mit IOH-Integration.
# TPE ist ein sequentiell-modellbasiertes Bayes'sches Optimierungsverfahren:
#   Es approximiert p(x|y < y*) und p(x|y >= y*) durch zwei Dichtemodelle
#   und schlaegt Kandidaten mit hohem Verhaeltnis l(x)/g(x) vor.
# Suchraum: ganzzahlig via hp.quniform (Float mit Schrittweite 1.0).
# Seed (rstate) steuert den Zufallsgenerator fuer reproduzierbare Laeufe.
# ---------------------------------------------------------------------------
class HyperoptAlgorithms:
    default_random_seed = 2

    def __init__(self,  hyperopt_algo: str, max_evaluations: int, seed: int | None = None):  
        self.hyperopt_algo = hyperopt_algo
        self.name = f"Hyperopt_{self.hyperopt_algo}"
        self.max_evaluations = max_evaluations
        self.seed = seed if seed is not None else self.default_random_seed
    
    def _get_hyperopt_algorithm(self):
        match self.hyperopt_algo:
            case "TPE":
                return tpe.suggest
        #    case "RAND":
        #        return rand.suggest
            case _:
                raise ValueError(f"Unsupported Hyperopt algorithm: '{self.hyperopt_algo}'. Choose: 'TPE'.") # or 'RAND'

    def __call__(self, problem):
        # Dimension and bounds from IOH problem
        n = int(problem.meta_data.n_variables)
        lb = problem.bounds.lb
        ub = problem.bounds.ub

        # Hyperopt search space: integer grid via quniform
        space = {f"x{i}": hp.quniform(f"x{i}", float(lb[i]), float(ub[i]), 1.0) for i in range(n)}

        def objective(params):
            # Hyperopt passes floats from quniform; map to ints
            x_int = [int(round(params[f"x{i}"])) for i in range(n)]
            y = problem(x_int)  # penalised objective from IOH
            return {"loss": float(y), "status": STATUS_OK}

        trials = Trials()
        self.algorithm = self._get_hyperopt_algorithm()

        best = fmin(
            fn=objective,
            space=space,
            algo=self.algorithm,
            max_evals=self.max_evaluations,
            trials=trials,
            rstate=np.random.default_rng(self.seed),
        )

        # Reconstruct best point as ordered list
        x_best = [int(round(best[f"x{i}"])) for i in range(n)]
        f_best = float(min(trials.losses()))

        # Keep IOH internal state consistent
        problem(x_best)
        return f_best, x_best


# ---------------------------------------------------------------------------
# Adaptiert ein IOH-Problem zur RbfoptBlackBox-Schnittstelle.
# var_type = "R" (reell) fuer alle Variablen, da RBFOpt keine nativen
# Integer-Typen unterstuetzt. evaluate() rundet x auf naechste Integer
# vor der IOH-Auswertung.
# ---------------------------------------------------------------------------
class IohRbfOptBlackBox(RbfoptBlackBox):
    def __init__(self, problem): #problem = IOH problem
        self.problem = problem
        #Dimension & bounds from IOH
        self.dim = int(problem.meta_data.n_variables)
        self.var_lower = [float(problem.bounds.lb[i]) for i in range(self.dim)]
        self.var_upper = [float(problem.bounds.ub[i]) for i in range(self.dim)]       
        self.var_type = ["R"] * self.dim  # All treated as real; we’ll round to int in evaluate()
        self.var_name = [f"x{i}" for i in range(self.dim)]  # Optional: names
            
        super().__init__()

    def get_dimension(self):
        return self.dim 
            
    def get_var_lower(self):
        return self.var_lower

    def get_var_upper(self):
        return self.var_upper

    def get_var_type(self):
        return self.var_type

    def get_var_name(self):
        return self.var_name    

    def evaluate(self, x):
        """RBFOpt evaluation hook: map to IOH problem."""
        # RBFOpt passes floats; IOH problem expects ints.
        x_int = [int(round(xi)) for xi in x]
        y = self.problem(x_int)  # this calls your penalised objective
        return float(y)

# ---------------------------------------------------------------------------
# RBFOpt: Surrogate-basierte Optimierung mit Radialen Basisfunktionen.
# Baut iterativ ein RBF-Metamodell der Zielfunktion auf und optimiert
# dessen Verbesserungspotenzial (Exploration + Exploitation).
# Benoetigt externen MINLP-Solver bonmin.exe aus dem solvers/-Ordner
# (sowie libipoptfort.dll im selben Verzeichnis).
# ga_base_population_size: Groesse der GA-Population im internen RBF-Schritt.
# ---------------------------------------------------------------------------
class RbfoptSearch:
    default_random_seed = 2
    default_ga_pop_size = 50

    def __init__(self, max_evaluations: int, seed: int | None = None, ga_pop_size: int | None = None):
        self.name = "RBFOpt"
        self.max_evaluations = max_evaluations
        self.seed = seed if seed is not None else self.default_random_seed
        self.ga_pop_size = ga_pop_size if ga_pop_size is not None else self.default_ga_pop_size
        self._solvers_dir = Path(__file__).parent.parent / "solvers"

    def __call__(self, problem):
        self.settings = rbfopt.RbfoptSettings(
            max_evaluations=self.max_evaluations,
            rand_seed=self.seed,
            ga_base_population_size=self.ga_pop_size,
            print_solver_output=False,
            minlp_solver_path=str(self._solvers_dir / "bonmin.exe"),
        )
        rbfopt_bb_problem = IohRbfOptBlackBox(problem)
        alg = rbfopt.RbfoptAlgorithm(self.settings, rbfopt_bb_problem)
     
        # Best design and value from RBFOpt 
        f_best, x_best, *_ = alg.optimize()
        x_best_int = [int(round(xi)) for xi in x_best]
        
        # Keep IOH internal state consistent
        problem(x_best_int)
        return float(f_best), x_best_int


class LatinHypercubeSampling:
    """Latin Hypercube Sampling as a baseline method."""

    default_random_seed = 2

    def __init__(self, max_evaluations: int, seed: int | None = None):
        self.name = "LHS"
        self.max_evaluations = max_evaluations
        self.seed = seed if seed is not None else self.default_random_seed

    def _generate_lhs_samples(
        self,
        lb_idx: np.ndarray,
        ub_idx: np.ndarray,
        rng: np.random.Generator,
    ) -> np.ndarray:
        """Generate Latin Hypercube Samples in integer index space."""
        dim = len(lb_idx)
        lhs_unit = np.empty((self.max_evaluations, dim), dtype=float)

        for dim_idx in range(dim):
            lhs_unit[:, dim_idx] = (
                rng.permutation(self.max_evaluations) + rng.random(self.max_evaluations)
            ) / self.max_evaluations

        n_levels = ub_idx - lb_idx + 1
        mapped = lb_idx + np.floor(lhs_unit * n_levels).astype(int)
        mapped = np.minimum(mapped, ub_idx)
        return mapped.astype(int)

    def __call__(self, problem):
        """
        Generate Latin Hypercube samples and evaluate them.
        Returns the best found value and the corresponding index vector.
        """
        lb_idx = np.array(problem.bounds.lb, dtype=int)
        ub_idx = np.array(problem.bounds.ub, dtype=int)

        rng = np.random.default_rng(self.seed)
        sampled_idx = self._generate_lhs_samples(lb_idx, ub_idx, rng=rng)

        best_y = float("inf")
        best_x = None

        for x_idx in sampled_idx:
            y = problem(x_idx.tolist())
            if y < best_y:
                best_y = y
                best_x = x_idx.tolist()

        # Ensure IOH internal state is updated with best solution
        if best_x is not None:
            problem(best_x)

        return best_y, best_x




def run_experiment(
    problem_bundle: dict[str, dict],
    algorithm,
    n_runs: int,
    slab_type: str,
    problem_ids: list[str] | None = None,
    plot_cross_section_mode: str = "none",
):
    """
    Run optimization experiments on one or more problems.

    Parameters
    ----------
    problem_bundle : dict
        Dictionary of problem bundles from build_problems_for_slab_type.
    algorithm : callable
        Optimizer with .name attribute and __call__(problem) method.
    n_runs : int
        Number of independent runs per problem.
    slab_type : str
        Slab type name (used in folder naming).
    problem_ids : list[str] | None
        List of problem IDs to run. If None, runs all problems in bundle.
    plot_cross_section_mode : str
        "none", "best", or "all" - whether to plot cross-section after runs.
    """
    out_root = Path(os.getcwd()) / "logger_results"
    out_root.mkdir(parents=True, exist_ok=True)

    # Timestamp for this experiment session
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    plot_mode = str(plot_cross_section_mode).strip().lower()
    if plot_mode not in {"none", "best", "all"}:
        raise ValueError(
            f"Invalid plot_cross_section_mode '{plot_cross_section_mode}'. Choose: 'none', 'best', or 'all'."
        )

    analysis_plot_setter = None
    try:
        analysis_module = import_module(f"slabdesignbench.slab_models.slab_types.{slab_type}.analysis_ec2_de")
        analysis_plot_setter = getattr(analysis_module, "set_plot_cross_section_mode", None)
    except Exception:
        analysis_plot_setter = None

    if analysis_plot_setter is not None:
        analysis_plot_setter("all" if plot_mode == "all" else "none")


    # Filter problems if specific IDs requested
    if problem_ids is not None:
        selected_bundles = {pid: problem_bundle[pid] for pid in problem_ids if pid in problem_bundle}
        missing = set(problem_ids) - set(selected_bundles.keys())
        if missing:
            print(f"Warning: Problem IDs not found: {missing}")
    else:
        selected_bundles = problem_bundle

    n_problems = len(selected_bundles)
    print(f"\n{'=' * 60}")
    print(f"Running {n_problems} problem(s) with {algorithm.name}")
    print(f"Slab type: {slab_type}")
    print(f"Runs per problem: {n_runs}")
    print(f"Output root: {out_root.resolve()}")
    print(f"{'=' * 60}\n")

    results_summary = []

    for i, (pid, b) in enumerate(selected_bundles.items(), 1):
        p = b["problem"]
        ctx = b["ctx"]
        decode = b.get("decode")
        var_names = b["var_names"]
        constraint_names = b["active_constraint_names"]
        label = b.get("label", "")

        ctx.ensure_constraints(constraint_names)
        ctx.ensure_params(var_names)

        # Sanitize label for folder name (replace spaces/special chars)
        label_safe = label.replace(" ", "_").replace("/", "-") if label else ""

        # Create unique folder name: slab_type__problem_id__label__algorithm__timestamp
        if label_safe:
            folder_name = f"{slab_type}__{pid}__{label_safe}__{algorithm.name}__{timestamp}"
        else:
            folder_name = f"{slab_type}__{pid}__{algorithm.name}__{timestamp}"

        print(f"\n[{i}/{n_problems}] Problem: {pid} ({label})")
        print(f"    Folder: {folder_name}")

            
        triggers = [
            ioh.logger.trigger.Always(), 
            ioh.logger.trigger.Each(1),
            ] 
                
        log = ioh.logger.Analyzer(
            root=str(out_root),
            folder_name=folder_name,
            algorithm_name=algorithm.name,
            store_positions=False,
            triggers=triggers
            )
        
        log.watch(ctx, "y")
        log.watch(ctx, "y_p")
        log.watch(ctx, "misses")
        log.watch(ctx, "hits")
         

        for c in constraint_names:
            log.watch(ctx, f"c__{c}")

        for v in var_names:
            log.watch(ctx, f"var__{v}")

        p.attach_logger(log)
        
        best_of_runs = float("inf")
        best_x_of_runs = None

        for run in range(n_runs):
            if hasattr(algorithm, 'seed'):
             algorithm.seed = algorithm.default_random_seed + run
            algorithm(p)
            run_best = p.state.current_best.y
            print(f"    Run {run + 1}/{n_runs} - best: {run_best:.3f}")

            if run_best < best_of_runs:
                best_of_runs = run_best
                best_x_of_runs = list(p.state.current_best.x)

            ctx.reset()
            p.reset()

        p.detach_logger()
        log.close()

        if plot_mode == "best" and best_x_of_runs is not None and analysis_plot_setter is not None:
            analysis_plot_setter("all")
            try:
                p(best_x_of_runs)
            finally:
                analysis_plot_setter("none")

            # Save cross-section plot for this problem.
            # On headless servers (no GUI), plt.show() will fail;
            # use plt.savefig() instead. On a local machine with a
            # display, you can replace plt.savefig() with plt.show().
            warnings.filterwarnings("ignore", message="FigureCanvasAgg is non-interactive")
            plot_dir = Path(os.getcwd()) / "cross_section_plots"
            plot_dir.mkdir(parents=True, exist_ok=True)
            plot_path = plot_dir / f"cross_section__{pid}__{algorithm.name}__{timestamp}.png"
            plt.savefig(plot_path, dpi=150, bbox_inches="tight")
            plt.close("all")
            print(f"    Plot saved: {plot_path}")

        results_summary.append(
            {
                "problem_id": pid,
                "label": label,
                "best_y": best_of_runs,
                "best_x": best_x_of_runs,
                "folder": folder_name,
            }
        )

    # Print summary
    print(f"\n{'=' * 70}")
    print("EXPERIMENT SUMMARY")
    print(f"{'=' * 70}")
    for res in results_summary:
        label_str = f" ({res['label']})" if res["label"] else ""
        print(
            f"  Problem {res['problem_id']:5s}{label_str:30s} | best y = {res['best_y']:.4f} "
        )
    print(f"{'=' * 70}\n")

    return results_summary


def main():
    # =========================================================================
    # CONFIGURATION
    # =========================================================================
    slab_type = "solid_slab_one_way_concrete"

    # Which problems to run (None = all problems in problem_list.csv)
    problem_ids_to_run:list[str] | None = None  #= ["4"]
    
    #| None = None  # e.g. = ["1", "2"] or None for all
    
    # Algorithm settings
    max_evaluations_ = 1500
    n_runs_ = 1
    # Verfuegbare Algorithmen (einzeln oder als Tupel fuer Sequenz):
    #   Pymoo:    "Pymoo_GA"       Genetischer Algorithmus (populationsbasiert)
    #             "Pymoo_CMAES"    CMA-ES (evolutionaere Strategie)
    #   NLopt:    "NLopt_DIRECT"   Globale Suche, deterministisch (Dividing Rectangles)
    #             "NLopt_SBPLX"    Lokale Simplexsuche (Subplex)
    #   Hyperopt: "Hyperopt_TPE"   Bayes'sche Optimierung (Tree Parzen Estimator)
    #   RBFOpt:   "RBFOpt"         Surrogate-Optimierung (Radiale Basisfunktionen)
    #   Baseline: "LHS"            Latin Hypercube Sampling (keine Optimierung)
    algo_names_ = ("RBFOpt",) # Options: ("Pymoo_GA",), ("Pymoo_GA", "RBFOpt"), ...
    plot_cross_section_mode_ = "none"  # Options: "none", "best", "all"

    # =========================================================================
    # BUILD PROBLEMS & RUN
    # =========================================================================
    bundles = build_problems_for_slab_type(slab_type)

    print(f"Available problems: {list(bundles.keys())}")

    def build_algorithm(algo_name: str):
        if algo_name.startswith("Pymoo_"):
            pymoo_algo_name = algo_name.replace("Pymoo_", "")
            return PymooAlgorithms(pymoo_algo=pymoo_algo_name, max_evaluations=max_evaluations_, seed=None, pop_size=None, sigma=None)  
        elif algo_name.startswith("NLopt_"):
            nlopt_algo_name = algo_name.replace("NLopt_", "")
            return NloptAlgorithms(nlopt_algo=nlopt_algo_name, max_evaluations=max_evaluations_) 
        elif algo_name.startswith("Hyperopt_"):
            hyperopt_algo_name = algo_name.replace("Hyperopt_", "")
            return HyperoptAlgorithms(hyperopt_algo=hyperopt_algo_name, max_evaluations=max_evaluations_, seed=None)
        elif algo_name == "RBFOpt":
            return RbfoptSearch(max_evaluations=max_evaluations_, seed=None, ga_pop_size=None)
        elif algo_name == "LHS":
            return LatinHypercubeSampling(max_evaluations=max_evaluations_, seed=None)
        else:
            raise ValueError(f"Unknown algorithm: {algo_name}")

    for algo_name in algo_names_:
        algo = build_algorithm(algo_name)
        run_experiment(
            bundles,
            algo,
            n_runs=n_runs_,
            slab_type=slab_type,
            problem_ids=problem_ids_to_run,
            plot_cross_section_mode=plot_cross_section_mode_,
        )

        
if __name__ == "__main__":
    # pr = cProfile.Profile()
    # pr.enable()

    main()

    # pr.disable()
    # s = io.StringIO()
    # ps = pstats.Stats(pr, stream=s).sort_stats("cumtime")
    # ps.print_stats(30)
    # print(s.getvalue())
