# IOH Analyzer — Modular Pipeline (Structure and Methodology)

## 1) Scope

This document describes the maintained modular implementation in `IOH_Analyzer/modular/*.R`.
The legacy script `IOH_Analyzer/Auswertung_IOHanalyzer_V2.R` is retained only as historical reference.

---

## 2) Execution Model

Primary entry point: `IOH_Analyzer/modular/main.R`.

When `main.R` is executed, the default workflow is:

```r
config <- get_default_config()
result <- run_benchmark_analysis(config)
```

The result object is returned invisibly. To inspect it in the console:

```r
> result <- run_benchmark_analysis(config)
> str(result$analysis_data, max.level = 2)
> result$plot_data$best_run_dataset
```

Notes:
- For iterative reruns in one R session, use `run_benchmark_analysis(cfg, load_modules = FALSE)`.
- Recursive `source()` calls of `main.R` inside `main.R` must be avoided.
- The `sys.nframe() == 0L` guard prevents auto-execution when the file is sourced from another script.

---

## 3) Pipeline Orchestration

Core sequence in `run_benchmark_analysis()`:

| Step | Action | Function |
|------|--------|----------|
| 1 | Print config summary | — |
| 1b | Override IOHanalyzer color scheme | `override_iohanalyzer_color_scheme()` |
| 2 | Select result folders | `get_folders_to_analyse()` |
| 2 | Load + budget-filter datasets | `load_dsl_with_budget_filter()` |
| 3 | Extract active problem/algorithm IDs | IOHanalyzer API |
| 3 | Print protocol block (data coverage) | — |
| 4 | Build analysis + plot data (one-pass) | `build_all_data()` |
| 4b | Print benchmark tables (FV/RT overview) | `print_benchmark_tables()` |
| 5 | Generate + export all benchmark plots | `run_all_benchmarks()` |
| 5 | Optional feasibility analysis | `run_feasibility_analysis()` |

Returned result object:

```r
list(
  dsl            = DataSetList,       # raw, unfiltered
  dsl_plot_base  = DataSetList,       # budget-trimmed, algorithm-filtered
  analysis_data  = list(...),         # per-problem abs/rel/global_min
  plot_data      = list(...),         # aggregated datasets for plots
  feasibility    = list(...) | NULL,  # feasibility output (if enabled)
  config         = list(...)          # final config used
)
```

---

## 4) Module Inventory

### 4.1 main.R (~280 lines)

Role: User configuration, module loading, pipeline orchestration, audit protocol.

| Function | Purpose |
|----------|---------|
| `get_default_config()` | Central configuration: paths, problem IDs, algorithms, flags, colors |
| `source_modules()` | Loads all 4 modules relative to `main.R` location (frame-walking fallback) |
| `run_benchmark_analysis()` | Pipeline orchestrator |

Configuration flags:

| Flag | Controls |
|------|----------|
| `show_Bm1_konvergenz` | BM1a (multi) + BM1c (median) |
| `show_Bm1_konvergenz_single` | BM1b (single-algo convergence) |
| `show_Bm2_stabilitaet` | BM2 (stability violin, abs + rel) |
| `show_Bm3_robustheit` | BM3 (robustness violin) |
| `show_Bm2_BM3_mix` | BM2+3 mix violin |
| `show_Bm4_ergebnisqualitaet` | BM4a (ECDF) + BM4b (quality bars) |
| `save_html` / `save_png` | Export control per format |
| `feasibility_analysis` | Enable/disable feasibility module |

### 4.2 data_loading.R (~395 lines)

Role: Folder selection, dataset loading, budget filtering, relative transformation, aggregation, one-pass data assembly.

7 categories with consistent numbering:

| Cat. | Section | Key functions |
|------|---------|---------------|
| 1 | Folder selection | `get_folders_to_analyse()`, `find_latest_folder()` (nested) |
| 2 | Data loading + budget filter | `load_dsl_with_budget_filter()` |
| 3 | FV/PAR scaling | `scale_dataset_fv()`, `create_relative_dataset()` |
| 4 | DataSet/Run selection | `select_single_run()`, `get_best_run_id()` |
| 5 | Matrix operations | `pad_column()`, `ensure_matrix()`, `build_rt_matrix()` |
| 6 | DataSetList aggregation | `assemble_dataset_list()`, `build_best_run_dataset()`, `build_all_runs_dataset()` |
| 7 | One-pass data assembly | `build_all_data()` |

Technical details:
- `find_latest_folder()` parses `YYYYMMDD_HHMMSS` timestamps from folder names; lexicographic `max()` + `which()` for deterministic selection; `mtime` fallback when timestamps are missing.
- `load_dsl_with_budget_filter()` performs deep-copy of DataSet objects before budget-trimming to prevent in-place mutation. The `DataSetList` class is saved before `lapply()` and restored after, since `lapply()` strips S3 classes.
- `assemble_dataset_list()` is the shared assembler used by both `build_best_run_dataset()` and `build_all_runs_dataset()`, consolidating the `cbind → RT → attribute cleanup → DataSetList construction` pipeline.

### 4.3 plot_styling.R (~1050 lines)

Role: Preset-based styling, rendering pipeline, HTML/PNG export, IOHanalyzer annotation handling.

Architecture:

```
Preset-System (get_style_profiles):
  Two bases: native (direct plotly) + ioh (IOHanalyzer-generated)
  9 plot-type presets inherit via modifyList() (CSS-style inheritance)
  Each preset carries base_type ("native"/"ioh") for annotation logic

Render-Pipeline (3 stages):
  build_render_config()  → merge global config + preset export keys + overrides
  build_styled_plots()   → apply style to HTML/PNG plotly objects
  render_styled_plot()   → orchestrator: print + save + error handling
```

| Section | Key functions |
|---------|---------------|
| Configuration | `override_iohanalyzer_color_scheme()`, `get_style_profiles()`, `get_plot_domain_defaults()`, `get_export_defaults()`, `get_plot_config()` |
| Internal helpers | `suppress_plotly_linetype_warnings()`, `resolve_plot_cfg()`, `scale_numeric_fields()` |
| Subplot helpers | `apply_uniform_axes_to_subplots()`, `compute_subplot_grid()`, `build_subplot_annotations()` |
| IOH annotations | `detect_ioh_annotation_role()`, `adjust_subplot_annotations()`, `apply_annotation_style()` |
| ECDF | `tune_ecdf_xaxis()` |
| Style application | `resolve_final_style_cfg()`, `validate_style_cfg()`, `apply_plot_style()` (margin, title, legend, axis, annotation sub-functions) |
| Export | `save_plot_file()` → `save_html_plot_file()` / `save_png_plot_file()` |
| Render pipeline | `build_render_config()`, `build_styled_plots()`, `render_styled_plot()` |

Preset validation: `build_render_config()` emits a warning listing all available presets if an unknown `plot_type` is passed — prevents silent fallback on typos.

### 4.4 benchmark_plots.R (~860 lines)

Role: All 8 benchmark plot variants plus FV/RT tables.

7 sections:

| Section | Contents |
|---------|----------|
| GEMEINSAME PLOT-HELFER | `get_algorithm_color()`, `with_linetype_warning_suppressed()`, `render_benchmark_plot()` |
| BENCHMARK-TABELLEN | `print_benchmark_tables()` |
| BM1: KONVERGENZ | `build_single_algo_subplot()`, `benchmark_1a_convergence_multi_func()`, `benchmark_1b_convergence_single_algo()`, `benchmark_1c_convergence_median()` |
| BM2 + BM3: VIOLIN-PLOTS | `plot_violin_distribution()`, `benchmark_2_stability()`, `benchmark_3_robustness()`, `benchmark_2_3_mix()` |
| BM4a: ECDF | `benchmark_4a_ecdf()` |
| BM4b: BALKENPLOTS | `add_capped_bar_labels()`, `extract_finite_fx()`, `summarize_quality_by_algorithm()`, `benchmark_4b_quality_bars()` |
| MASTER | `run_all_benchmarks()` |

Each benchmark function follows the same pattern:

```r
benchmark_X <- function(..., cfg) {
  if (!isTRUE(cfg$show_BmX_flag)) return(invisible(NULL))
  # build plotly object...
  render_benchmark_plot(p, cfg, "file_name", plot_type = "preset_name")
}
```

### 4.5 feasibility_analysis.R (~470 lines)

Role: Feasibility reconstruction from `.dat`/`.json` files, scope-level selection, overall aggregation, CSV export.

| Function group | Key functions |
|----------------|---------------|
| Parsing | `read_ioh_dat_table()`, `assign_run_ids_from_evaluations()`, `coerce_numeric_columns()` |
| Annotation | `annotate_feasibility_metrics()`, `annotate_run_feasibility_summary()` |
| Filtering | `drop_last_row_per_run()`, `cap_rows_per_run_to_budget()`, `pick_min_fitness_rows()` |
| Aggregation | `collapse_detail_scopes()`, `build_plot_feasibility_detail_table()`, `build_overall_feasibility_summary()` |
| Output | `write_feasibility_outputs()`, `print_feasibility_analysis()` |
| Orchestrator | `run_feasibility_analysis()` |

---

## 5) Plot Configuration Model

Plot-specific defaults are centralized in `plot_styling.R` via `get_plot_config()`:

```
get_plot_config() = get_shared_style_defaults()
                  + native base profile
                  + get_plot_domain_defaults()   (y-ranges, bar caps, label sizes)
                  + get_export_defaults()         (png_width/height/zoom/delay)
                  + style_profiles (all 9+2 presets)
```

Integration rule:
- If `cfg$plot` is missing, defaults are injected.
- If `cfg$plot` exists, values are merged over defaults (partial overrides allowed).

Export behavior:
- HTML exports use `htmlwidgets::saveWidget(..., selfcontained = FALSE)`.
- PNG exports use `webshot2::webshot()` on a temporary HTML file, then delete the temp.
- `plot_exports/` is git-ignored to avoid repository bloat.

### 5.1) Override-Hierarchie (plotspezifische Anpassungen)

Presets in `get_style_profiles()` definieren die Basis-Stilwerte pro Plottyp. Für einzelne Plots können diese an der **Aufrufstelle** in `benchmark_plots.R` überschrieben werden, ohne das Preset selbst zu ändern:

```
Priorität (spätere Stufe gewinnt):
  1. Preset-Basis         → get_style_profiles(), z.B. convergence_single
  2. Font-Skalierung      → html_font_scale / png_font_scale (automatisch je Output)
  3. overrides$style      → überschreibt HTML + PNG gleichzeitig
  4. html$style           → überschreibt nur HTML
     png$style            → überschreibt nur PNG
```

Beispiel:
```r
render_benchmark_plot(p, cfg, "dateiname",
  plot_type = "convergence_median",
  overrides = list(style = list(legend_y_offset = -0.18)),  # HTML + PNG
  html = list(style = list(bottom_margin = 40)),             # nur HTML
  png  = list(style = list(bottom_margin = 60))              # nur PNG
)
```

Die Verarbeitung erfolgt in `build_styled_plots()` (`plot_styling.R`):
1. `resolve_final_style_cfg()` wählt Preset + Skalierungsfaktor
2. `overrides$style` wird per `modifyList()` auf **beide** Ausgaben angewendet
3. `html$style` / `png$style` werden separat nur auf die jeweilige Ausgabe angewendet

---

## 6) Color Consistency

`override_iohanalyzer_color_scheme()` patches IOHanalyzer's internal `get_color_scheme` via `assignInNamespace()`:

1. Exact name match.
2. Case-insensitive fallback.
3. Default `#999999` for unknown algorithms.

This prevents palette drift when IOHanalyzer reorders algorithm IDs internally.

---

## 7) Core Data Objects

### analysis_data (per-problem)

```r
analysis_data[[fid]] <- list(
  abs        = DataSetList,   # absolute FV values
  rel        = DataSetList,   # relative FV values (100% = best observed)
  global_min = numeric        # reference value for relative scaling
)
```

### plot_data (aggregated)

```r
plot_data <- list(
  fv_abs           = list(fid -> long table),  # absolute FV samples
  fv_rel           = list(fid -> long table),  # relative FV samples
  best_run_dataset = DataSetList,              # best run per (problem, algorithm)
  all_runs_dataset = DataSetList               # all runs across problems
)
```

Content semantics:
- `analysis_data[[fid]]$abs`: raw DataSetList for one problem, all algorithms, all runs.
- `analysis_data[[fid]]$rel`: same, but FV/PAR scaled to `100 / global_min`.
- `plot_data$best_run_dataset`: cross-problem aggregation; one best run per (problem, algorithm).
- `plot_data$all_runs_dataset`: cross-problem aggregation; all runs retained.

---

## 8) Plot-to-Data Mapping

| Plot | Source object | Content |
|------|--------------|---------|
| BM1a (multi convergence) | `dsl_plot_base` | All problems, all algorithms, all runs |
| BM1b (single-algo convergence) | `dsl_plot_base` subsets | One problem per figure, one algorithm per subplot |
| BM1c (median convergence) | `plot_data$best_run_dataset` | Median over best-run trajectories across problems |
| BM2 stability (abs) | `analysis_data[[fid]]$abs` | One problem, all algorithms, all runs |
| BM2 stability (rel) | `analysis_data[[fid]]$rel` | Same, relatively scaled |
| BM3 robustness | `plot_data$best_run_dataset` | Best run per (problem, algorithm), cross-problem |
| BM2+3 mix | `plot_data$all_runs_dataset` | All runs, cross-problem |
| BM4a ECDF global | `dsl_plot_base` | All problems, all algorithms, all runs |
| BM4a ECDF per-problem | `analysis_data[[fid]]$abs` | One problem, absolute values |
| BM4b quality bars | `dsl_plot_base` | One scalar per (problem, algorithm) at budget |

BM4b relative scaling: each algorithm's best FV value is expressed as percentage of the best value across all algorithms for that problem (`ref_best = min`). 100% = best algorithm.

Aggregation summary:
- **Unaggregated (all runs):** `dsl_plot_base`, `analysis_data[[fid]]$abs/rel`, `plot_data$fv_abs/fv_rel`
- **Best-run per problem:** `plot_data$best_run_dataset`
- **All runs cross-problem:** `plot_data$all_runs_dataset`

---

## 9) Budget Methodology and Audit Reporting

`load_dsl_with_budget_filter()` returns both filtered datasets and an audit structure.
The `[PROTOCOL]` output reports:

- Loaded DataSet count
- Algorithm filter impact
- Missing FV sets
- Budget-trimmed sets
- Sets with no samples inside `runtime_budget`
- Requested vs. used problem IDs and algorithms

Fixed-budget principle:
- Samples beyond `runtime_budget` are excluded.
- Empty in-budget datasets are retained structurally.
- Short trajectories are padded for aligned aggregation (`pad_column()`).

---

## 10) Feasibility Methodology

Feasibility analysis is optional (`cfg$feasibility_analysis`).

Definition:
- A row is feasible iff all `c__*` constraint columns equal zero.
- `max_violation` is the row-wise maximum over available constraint columns.

Robust parsing:
- Repeated `.dat` headers are removed before table parsing.
- Runs are reconstructed by detecting `evaluations == 1` resets.
- Optional budget capping is applied before aggregate summaries.

`pick_min_fitness_rows()` selection rule:
- Selects the row with the minimum finite `fitness_value` per group.
- Falls back to minimum non-NA value if no finite value exists.
- Retains the first row if all values are NA.

`collapse_detail_scopes()` groups by stable ID columns only (`problem_id`, `algorithm`, `run`, `evaluations_nmr`), excluding metric columns that may contain NA for never-feasible algorithms.

Outputs:
- `IOH_Analyzer/feasibility_outputs_YYYYMMDD_HHMMSS/`
- `feasibility_detail_plot_scopes.csv`
- `feasibility_overall_by_algorithm.csv`

---

## 11) Benchmark Mapping

| ID | Plot type | Preset key |
|----|-----------|------------|
| BM1a | Multi-function convergence | `convergence_multi` |
| BM1b | Single-algo convergence (subplot grid) | `convergence_single` |
| BM1c | Median convergence (best-run, relative) | `convergence_median` |
| BM2 | Stability violin (abs + rel) | `violin` |
| BM3 | Robustness violin (best-run) | `violin` |
| BM2+3 | Mix violin (all runs) | `violin` |
| BM4a | ECDF (global + per-problem) | `ecdf` |
| BM4b | Quality bars (grouped + aggregated) | `quality_bar_grouped`, `quality_bar_aggregated` |

---

## 12) Adding a New Plot

See `IOH_Analyzer/modular/ANLEITUNG_NEUER_PLOT.md` for a step-by-step guide.

Summary: 4 steps across 3 files:

1. `main.R`: Add `show_BmX_*` flag in `get_default_config()`
2. `plot_styling.R`: Add preset in `get_style_profiles()`
3. `benchmark_plots.R`: Write plot function using `render_benchmark_plot()`
4. `benchmark_plots.R`: Wire into `run_all_benchmarks()`

Preset typos are caught at runtime with a warning listing all available presets.
