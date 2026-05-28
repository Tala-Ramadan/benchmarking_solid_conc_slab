# Modul zur Erzeugung der Benchmark-Plots: BM1 (Konvergenz), BM2 (Stabilitaet),
# BM3 (Robustheit), BM4 (Ergebnisqualitaet) - alle 8 Plotvarianten zusammengefasst.
#
# Abschnitte:
#   GEMEINSAME PLOT-HELFER    - get_algorithm_color, with_linetype_warning_suppressed,
#                               render_benchmark_plot
#   BENCHMARK-TABELLEN       - print_benchmark_tables (FV/RT-Uebersicht)
#   BM1: KONVERGENZ          - BM1a (multi), BM1b (single), BM1c (median)
#   BM2 + BM3: VIOLIN-PLOTS - Stabilitaet, Robustheit, Mix
#   BM4a: ECDF              - ECDF global + je Problem
#   BM4b: BALKENPLOTS        - Ergebnisqualitaet (gruppiert + aggregiert)
#   MASTER                   - run_all_benchmarks()
#
# Jeder plot_type-String entspricht einem Preset aus plot_styling.R::get_style_profiles().
# Die render_benchmark_plot()-Aufrufe nutzen Preset-Namen; bei Bedarf koennen
# plotspezifische Overrides uebergeben werden (siehe Override-Hierarchie in plot_styling.R):
#   overrides = list(style = list(...))  -> aendert HTML + PNG gleichzeitig
#   html = list(style = list(...))       -> aendert nur HTML-Ausgabe
#   png  = list(style = list(...))       -> aendert nur PNG-Ausgabe

# ============================================================================
# GEMEINSAME PLOT-HELFER
# ============================================================================

get_algorithm_color <- function(alg_name, color_map, default = "#1f77b4") {
  match_name <- names(color_map)[tolower(names(color_map)) == tolower(alg_name)]
  if (length(match_name) > 0) {
    color_map[[match_name[1]]]
  } else {
    default
  }
}

# Warning-Suppression: nutzt suppress_plotly_linetype_warnings() aus plot_styling.R
with_linetype_warning_suppressed <- function(expr) {
  suppress_plotly_linetype_warnings(expr) # nolint: object_usage_linter.
}

render_benchmark_plot <- function(plot_obj, cfg, file_name, plot_type = "native",
                      overrides = list(),
                      html = list(),
                      png = list()) {
  render_styled_plot( # nolint: object_usage_linter.
    plot_obj,
    cfg,
    file_name,
    plot_type = plot_type,
    overrides = overrides,
    html = html,
    png = png
  )
}

# ============================================================================
# BENCHMARK-TABELLEN: FV/RT-Uebersicht je Problem
# ============================================================================

print_benchmark_tables <- function(analysis_data, selected_func_ids, print_attributes = FALSE) {
  for (func_id in selected_func_ids) {
    ds <- analysis_data[[as.character(func_id)]]$abs

    cat(sprintf("\n======== Problem %s ========\n", func_id))
    if (isTRUE(print_attributes)) {
      tryCatch(
        print(IOHanalyzer::get_parId(ds)),
        error = function(e) warning(sprintf("[Problem %s] get_parId fehlgeschlagen: %s", func_id, e$message))
      )
    }

    cat("FV-Uebersicht:\n")
    tryCatch(
      print(IOHanalyzer::get_FV_overview(ds)),
      error = function(e) warning(sprintf("[Problem %s] get_FV_overview fehlgeschlagen: %s", func_id, e$message))
    )

    cat("RT-Uebersicht:\n")
    tryCatch(
      print(IOHanalyzer::get_RT_overview(ds)),
      error = function(e) warning(sprintf("[Problem %s] get_RT_overview fehlgeschlagen: %s", func_id, e$message))
    )
  }

  invisible(NULL)
}

# ============================================================================
# BM1: KONVERGENZ (BM1a, BM1b, BM1c)
# ============================================================================

# Hilfsfunktion: Erzeuge einzelnen Konvergenz-Subplot fuer einen Algorithmus
build_single_algo_subplot <- function(dt_runs, algo_name, budget,
                                             ax_x, ax_y, color_map,
                                             budget_marker_width = 0.5) {
  algo_color <- get_algorithm_color(algo_name, color_map)
  p_fv <- plotly::plot_ly()

  if (!is.null(dt_runs) && nrow(dt_runs) > 0) {
    run_ids  <- sort(unique(dt_runs$run))
    best_run <- get_best_run_id(dt_runs) # nolint: object_usage_linter.

    for (r in run_ids) {
      dtr <- dt_runs[dt_runs$run == r, ]
      dtr <- dtr[order(dtr$runtime), ]

      if (nrow(dtr) == 0) next

      dtr$fx_best_so_far <- cummin(dtr$`f(x)`)
      is_best <- identical(r, best_run)

      p_fv <- p_fv |>
        plotly::add_lines(
          data = dtr,
          x = ~runtime,
          y = ~fx_best_so_far,
          opacity    = if (is_best) 0.95 else 0.4,
          showlegend = FALSE,
          line       = list(color = algo_color, width = 2)
        ) |>
        plotly::add_markers(
          data = dtr[which.min(dtr$fx_best_so_far), , drop = FALSE],
          x = ~runtime,
          y = ~fx_best_so_far,
          marker = list(
            color  = algo_color,
            size   = if (is_best) 9 else 7,
            symbol = if (is_best) "diamond" else "circle",
            line   = list(width = if (is_best) 1 else 0.7, color = algo_color)
          ),
          opacity    = if (is_best) 0.8 else 0.5,
          showlegend = FALSE
        )
    }

    has_axis_range <- !is.null(ax_y$range) && length(ax_y$range) == 2 && all(is.finite(ax_y$range))
    if (isTRUE(has_axis_range) && identical(ax_y$type, "log")) {
      # Plotly erwartet bei Log-Achsen in axis$range die log10-Exponenten.
      y_seg_start <- 10^as.numeric(ax_y$range[1])
      y_seg_end <- 10^as.numeric(ax_y$range[2])
    } else if (isTRUE(has_axis_range)) {
      y_seg_start <- as.numeric(ax_y$range[1])
      y_seg_end <- as.numeric(ax_y$range[2])
    } else if (identical(ax_y$type, "log")) {
      y_seg_start <- 1
      y_seg_end <- max(dt_runs$`f(x)`, na.rm = TRUE)
    } else {
      y_seg_start <- 0
      y_seg_end <- max(dt_runs$`f(x)`, na.rm = TRUE)
    }

    # Robuster Fallback haelt den Budgetmarker auch bei degenerierten Laufdaten sichtbar.
    if (identical(ax_y$type, "log") && y_seg_start <= 0) y_seg_start <- 1
    if (!is.finite(y_seg_end) || y_seg_end <= y_seg_start) y_seg_end <- y_seg_start * 1.01

    p_fv <- p_fv |>
      plotly::add_segments(
        x = budget,
        xend = budget,
        y = y_seg_start,
        yend = y_seg_end,
        line = list(color = "black", width = as.numeric(budget_marker_width)),
        inherit = FALSE,
        showlegend = FALSE
      )
  }

  p_fv |>
    plotly::layout(
      xaxis = ax_x,
      yaxis = ax_y,
      plot_bgcolor = "#e2e3e5",
      paper_bgcolor = "white"
    )
}

# BM1a: Multi-Funktions-Konvergenz (alle Probleme x alle Algorithmen)
benchmark_1a_convergence_multi_func <- function(dsl_plot_base, cfg) {
  if (!isTRUE(cfg$show_Bm1_konvergenz)) return(invisible(NULL))

  p_convergence_multi <- tryCatch({
    with_linetype_warning_suppressed(
      IOHanalyzer::Plot.FV.Multi_Func(dsl_plot_base, scale.xlog = TRUE, scale.ylog = TRUE)
    )
  }, error = function(e) {
    warning(sprintf("Konvergenz-Plot fehlgeschlagen: %s", e$message))
    NULL
  })

  if (!is.null(p_convergence_multi)) {
    x_cfg <- list(
      title = "Funktionsauswertungen [log]",
      tickformat = ".0f",
      showline = TRUE, mirror = TRUE,
      margin = 0.05
    )
    y_cfg <- list(
      title = "Fitnesswert [kg CO<sub>2</sub>Ã¤/m<sup>2</sup>] [log]",
      type = "log",
      dtick = 2,
      exponentformat = "power",
      showexponent = "all",
      showline = TRUE, mirror = TRUE,
      margin = 0.05
    )

    p_convergence_multi <- apply_uniform_axes_to_subplots( # nolint: object_usage_linter.
      p_convergence_multi, x_cfg, y_cfg,
      y_title_first_col_only = TRUE,
      x_title_bottom_row_only = TRUE
    )
    p_convergence_multi <- adjust_subplot_annotations(p_convergence_multi) # nolint: object_usage_linter.
    p_convergence_multi <- p_convergence_multi |> plotly::layout(
      legend = list(orientation = "h")
    )
    render_benchmark_plot(
      p_convergence_multi,
      cfg,
      "plot_konvergenz_multi_func",
      plot_type = "convergence_multi"
    ) # nolint: object_usage_linter.
  }
}

# BM1b: Einzelalgorithmus-Konvergenzplots (Raster pro Algorithmus)
benchmark_1b_convergence_single_algo <- function(dsl_plot_base, selected_func_ids, cfg) {
  if (!isTRUE(cfg$show_Bm1_konvergenz_single)) return(invisible(NULL))

  algo_names <- sort(unique(as.character(IOHanalyzer::get_algId(dsl_plot_base))))
  algorithms_per_figure <- as.integer(as_single_numeric_or_default( # nolint: object_usage_linter.
    cfg$plot$single_conv_algorithms_per_plot, 4L))
  algorithm_groups <- split(algo_names, ceiling(seq_along(algo_names) / algorithms_per_figure))
  budget_marker_width <- as_single_numeric_or_default( # nolint: object_usage_linter.
    cfg$plot$single_conv_budget_marker_width, 0.5)
  shared_y_axis    <- TRUE
  base_font_single <- list(
    family = cfg$plot$font_family,
    color = cfg$plot$font_color,
    size = cfg$plot$font_size)
  ax_x <- list(title = "Funktionsauswertungen", type = "linear",
               showline = TRUE, linecolor = "black", linewidth = 1, mirror = TRUE,
               showgrid = TRUE, gridcolor = "white",
               zeroline = TRUE, zerolinecolor = "black", zerolinewidth = 0.15,
               automargin = FALSE,
               tickmode = "linear",
               tick0 = 0,
               dtick = 200,
               range = c(0, cfg$runtime_budget))
  y_range_raw <- cfg$plot$y_range_single_conv
  y_range_axis <- NULL
  if (!is.null(y_range_raw) && length(y_range_raw) == 2 && all(is.finite(y_range_raw)) && y_range_raw[2] > y_range_raw[1]) {
    y_range_axis <- as.numeric(y_range_raw)
  }

  ax_y <- list(title = "Fitness [kg CO<sub>2</sub>Ã¤/m<sup>2</sup>]", type = "linear",
               showline = TRUE, linecolor = "black", linewidth = 1, mirror = TRUE,
               showgrid = TRUE, gridcolor = "white",
               zeroline = FALSE,
               automargin = FALSE,
               tick0 = 0,
               dtick = 100)
  if (!is.null(y_range_axis)) ax_y$range <- y_range_axis

  for (fid in selected_func_ids) {
    for (group_idx in seq_along(algorithm_groups)) {
      algorithm_group <- unname(algorithm_groups[[group_idx]])
      grid_cfg <- compute_subplot_grid(length(algorithm_group), max_cols = 2L) # nolint: object_usage_linter.

      subplot_list   <- list()

      for (name in algorithm_group) {
        ds_algo <- subset(dsl_plot_base, algId == name & funcId == fid)# nolint: object_usage_linter.

        dt_runs <- tryCatch(
          IOHanalyzer::get_FV_sample(ds_algo, sort(unique(IOHanalyzer::get_runtimes(ds_algo))), output = "long"),
          error = function(e) NULL
        )

        subplot_list[[length(subplot_list) + 1]] <- build_single_algo_subplot(
          dt_runs           = dt_runs,
          algo_name         = name,
          budget            = cfg$runtime_budget,
          ax_x              = ax_x,
          ax_y              = ax_y,
          color_map         = cfg$my_colors,
          budget_marker_width = budget_marker_width
        )
      }

      p_problem <- plotly::subplot(
        subplot_list,
        nrows  = grid_cfg$nrows,
        shareX = FALSE,
        shareY = shared_y_axis,
        titleX = TRUE,
        titleY = TRUE,
        # Interne Abstaende zwischen den Subplots (Raster), als lokale Defaults.
        # Nicht in plot_styling.R: Diese Werte steuern Subplot-Geometrie, nicht den Gesamtplot.
        margin = c(0.03, 0.03, 0.08, 0.08)
      )

      if (isTRUE(shared_y_axis)) {
        p_problem <- apply_uniform_axes_to_subplots( # nolint: object_usage_linter.
          p_problem,
          x_cfg                   = ax_x,
          y_cfg                   = ax_y,
          y_title_first_col_only  = TRUE,
          x_title_bottom_row_only = TRUE
        )
      }

      subplot_annotations <- build_subplot_annotations( # nolint: object_usage_linter.
        p     = p_problem,
        labels = algorithm_group,
        font   = base_font_single
      )

      title_text <- paste0("Problem ", fid)

      p_problem <- p_problem |>
        plotly::layout(
          font        = base_font_single,
          showlegend  = FALSE,
          annotations = subplot_annotations,
          title       = list(
            text = title_text,
            y = 0.98,
            x = 0.5,
            xanchor = "center",
            yanchor = "top"
          )
        )

      file_suffix <- if (length(algorithm_groups) > 1L) {
        paste0("_teil_", group_idx)
      } else {
        ""
      }

      render_benchmark_plot(
        p_problem,
        cfg,
        paste0("plot_konvergenz_problem_", fid, file_suffix),
        plot_type = "convergence_single"
      ) # nolint: object_usage_linter.
    }
  }
}

# BM1c: Median-Konvergenz (relativ %, ueber Probleme)
benchmark_1c_convergence_median <- function(plot_data, selected_func_ids, cfg) {
  if (!isTRUE(cfg$show_Bm1_konvergenz)) return(invisible(NULL))

  ds_median_conv <- plot_data$best_run_dataset

  if (is.null(ds_median_conv) || length(ds_median_conv) == 0) {
    warning("[Plot 1c] Keine Daten fuer den Median-Konvergenzplot verfuegbar.")
    return(invisible(NULL))
  } 
  
  p <- plotly::plot_ly()

  for (i in seq_along(ds_median_conv)) {
    alg_name <- names(ds_median_conv)[i]

    if (is.null(alg_name) || !nzchar(alg_name)) {
      alg_name <- paste0("Algo_", i)
    }

    fv <- ds_median_conv[[i]]$FV
    if (is.null(fv)) next

    fv <- ensure_matrix(fv) # nolint: object_usage_linter.
    # Benchmark-Konvention: Aggregation ueber Best-so-far-Verlaeufe je Lauf.
    fv_bsf <- apply(fv, 2, cummin)
    fv_bsf <- ensure_matrix(fv_bsf) # nolint: object_usage_linter.

    median_curve <- apply(fv_bsf, 1, function(x) {
      x <- x[is.finite(x)]
      if (length(x) == 0) NA_real_ else median(x)
    })

    algo_color <- get_algorithm_color(alg_name, cfg$my_colors)
     
    p <- p |> plotly::add_lines(x = seq_len(nrow(fv)), y = median_curve,
                           name = alg_name, line = list(color = algo_color, width = 2.5))
  }
  
  p <- p |> plotly::layout(
    xaxis = list(
      title = "Funktionsauswertungen",
      range = c(0, cfg$runtime_budget),
      showgrid = TRUE,
      gridcolor = "white",
      showline = TRUE,
      linecolor = "black",
      mirror = TRUE
    ),
    yaxis = list(title = list(
                   text     = paste0("Median Ã¼ber Probleme 1\u2013", length(selected_func_ids), ",",
                                     "\n relativ zu den besten gefundenen LÃ¶sungen je Problem"),
                   standoff = 20),
                 ticksuffix = "%",
                 range = cfg$plot$y_range_median_conv,
                 showgrid = TRUE,
                 gridcolor = "white",
                 showline = TRUE,
                 linecolor = "black",
                 mirror = TRUE),
    plot_bgcolor = "#e1e5e9",
    paper_bgcolor = "white",
    legend = list(orientation = "h", x = 0.5, xanchor = "center")
  )
  render_benchmark_plot(
    p,
    cfg,
    "plot_konvergenz_median_bester_durchlauf",
    plot_type = "convergence_median"
  ) # nolint: object_usage_linter.
}

# ============================================================================
# BM2 + BM3: STABILITAET & ROBUSTHEIT (Violin-Plots)
# ============================================================================

plot_violin_distribution <- function(ds, title_text, file_name, cfg,
                            y_title = "Relativer Fitnesswert [%]", 
                            y_type = "linear",
                            y_range = NULL) {
  if (is.null(ds) || length(ds) == 0) {
    warning(sprintf("[%s] Keine Daten verfuegbar. Plot wird uebersprungen.", file_name))
    return(invisible(NULL))
  }
  p <- tryCatch(
    IOHanalyzer::Plot.FV.PDF(ds, cfg$runtime_budget),
    error = function(e) {
      warning(sprintf("[%s] Plot.FV.PDF fehlgeschlagen: %s", file_name, e$message))
      NULL
    }
  )
  if (is.null(p)) return(invisible(NULL))

  yaxis_cfg <- list(title = y_title, type = y_type)
  if (!is.null(y_range) && length(y_range) == 2 && all(is.finite(y_range))) {
    yaxis_cfg$range <- as.numeric(y_range)
  }

  p <- p |> plotly::layout(
    title = list(text = title_text),
    xaxis = list(title = "Algorithmus"),
    yaxis = yaxis_cfg
  )
  render_benchmark_plot(
    p,
    cfg,
    file_name,
    plot_type = "violin"
  ) # nolint: object_usage_linter.
}

# BM2: Stabilitaet (absolut + relativ je Problem)
benchmark_2_stability <- function(analysis_data, selected_func_ids, cfg) {
  if (!isTRUE(cfg$show_Bm2_stabilitaet)) return(invisible(NULL))

  stab_modes <- list(
    list(key = "abs",
         title_prefix = "Stabilit�t absolut",
         y_title      = "Fitnesswert GWP [kg CO<sub>2</sub>�/m<sup>2</sup>]",
         y_type       = "linear",
         y_range      = cfg$plot$y_range_violin_abs,
         file_prefix  = "plot_stabilitaet_absolut"),
    list(key = "rel",
         title_prefix = "Stabilit�t relativ",
         y_title      = "Relativer Fitnesswert [%]",
         y_type       = "linear",
         y_range      = cfg$plot$y_range_violin_rel,
         file_prefix  = "plot_stabilitaet_relativ")
  )
  for (m in stab_modes) {
    for (fid in selected_func_ids) {
      plot_violin_distribution(
        ds         = analysis_data[[as.character(fid)]][[m$key]],
        title_text = paste0(m$title_prefix, ", Problem ", fid),
        file_name  = paste0(m$file_prefix, "_problem_", fid),
        cfg        = cfg,
        y_title    = m$y_title,
        y_type     = m$y_type,
        y_range    = m$y_range
      )
    }
  }
}

# BM3: Robustheit (bester Lauf aggregiert)
benchmark_3_robustness <- function(plot_data, cfg) {
  if (!isTRUE(cfg$show_Bm3_robustheit)) return(invisible(NULL))

  plot_violin_distribution(
    ds         = plot_data$best_run_dataset,
    title_text = "Robustheit (Bester Durchlauf, alle Probleme)",
    file_name  = "plot_robustheit_aggregiert",
    cfg        = cfg,
    y_range    = cfg$plot$y_range_violin_rel
  )
}

# BM2+3: Gemischte Stabilitaet/Robustheit (alle Laeufe aggregiert)
benchmark_2_3_mix <- function(plot_data, cfg) {
  if (!isTRUE(cfg$show_Bm2_BM3_mix)) return(invisible(NULL))

  plot_violin_distribution(
    ds         = plot_data$all_runs_dataset,
    title_text = "StabilitÃ¤t Ã¼ber alle Probleme & DurchlÃ¤ufe",
    file_name  = "plot_mischung_stabilitaet_robustheit",
    cfg        = cfg,
    y_range    = cfg$plot$y_range_violin_rel
  )
}

# ============================================================================
# BM4a: ECDF
# ============================================================================

benchmark_4a_ecdf <- function(dsl_plot_base, analysis_data, selected_func_ids, cfg) {
  if (!isTRUE(cfg$show_Bm4_ergebnisqualitaet)) return(invisible(NULL))

  # Globale ECDF
  p_ecdf_global <- tryCatch({
    with_linetype_warning_suppressed(
      IOHanalyzer::Plot.FV.ECDF_Single_Func(dsl_plot_base, scale.xlog = TRUE, scale.reverse = FALSE)
    )
  }, error = function(e) {
    warning(sprintf("Globaler ECDF-Plot fehlgeschlagen: %s", e$message))
    NULL
  })
  if (!is.null(p_ecdf_global)) {
    p_ecdf_global <- p_ecdf_global |> plotly::layout(
      title = list(text = paste0("Empirische kumulative Verteilungsfunktion (ECDF) ueber alle Probleme")),
      yaxis = list(title = "Anteil der (Lauf, Zielwert)-Paare")
    )
    p_ecdf_global <- tune_ecdf_xaxis(p_ecdf_global, x_range = cfg$plot$ecdf_x_range) # nolint: object_usage_linter.
    render_benchmark_plot(
      p_ecdf_global,
      cfg,
      "plot_ecdf_aggregiert",
      plot_type = "ecdf"
    ) # nolint: object_usage_linter.
  }

  # ECDF je Problem
  for (fid in selected_func_ids) {
    fid_c <- as.character(fid)
    ds_single <- analysis_data[[fid_c]]$abs
    if (is.null(ds_single) || length(ds_single) == 0) next

    p <- tryCatch(
      with_linetype_warning_suppressed(
        IOHanalyzer::Plot.FV.ECDF_Single_Func(ds_single, scale.xlog = TRUE, scale.reverse = FALSE)
      ),
      error = function(e) {
        warning(sprintf("ECDF-Plot fuer Problem %s fehlgeschlagen: %s", fid_c, e$message))
        NULL 
      })
    if (!is.null(p)) {
      p <- p |> plotly::layout(
        title = list(text = paste0("Empirische kumulative Verteilungsfunktion (ECDF) - Problem ", fid_c)),
        yaxis = list(title = "Anteil der (Lauf, Zielwert)-Paare")
      )
      p <- tune_ecdf_xaxis(p, x_range = cfg$plot$ecdf_x_range) # nolint: object_usage_linter.
      render_benchmark_plot(
        p,
        cfg,
        paste0("plot_ecdf_problem_", fid_c),
        plot_type = "ecdf"
      ) # nolint: object_usage_linter.
    }
  }
}

# ============================================================================
# BM4b: BALKENPLOTS ERGEBNISQUALITAET
# ============================================================================

add_capped_bar_labels <- function(df, value_col, label_col, cap) {
  values <- df[[value_col]]

  df$y_display <- pmin(values, cap)
  df$is_capped <- values > cap
  df[[label_col]] <- ifelse(
    df$is_capped,
    sprintf("\u2191 %.1f%%", values),
    sprintf("%.1f%%", values)
  )
  df
}

extract_finite_fx <- function(dt_sample) {
  if (is.null(dt_sample) || nrow(dt_sample) == 0) return(numeric(0))

  dt_df <- as.data.frame(dt_sample)
  fx_col <- if ("f(x)" %in% names(dt_df)) {
    "f(x)"
  } else if ("F" %in% names(dt_df)) {
    "F"
  } else {
    return(numeric(0))
  }

  fx_vals <- dt_df[[fx_col]]
  fx_vals[is.finite(fx_vals)]
}

summarize_quality_by_algorithm <- function(quality_df, alg_ids) {
  summary_rows <- lapply(alg_ids, function(alg) {
    rel_vals <- quality_df$rel_pct[quality_df$algId_plot == alg]
    rel_vals <- rel_vals[is.finite(rel_vals)]

    if (length(rel_vals) == 0) return(NULL)

    data.frame(
      algId_plot = alg,
      median_rel_pct = median(rel_vals),
      mean_rel_pct = mean(rel_vals),
      n_problems = length(rel_vals),
      stringsAsFactors = FALSE)
  })
  Filter(Negate(is.null), summary_rows)
}

benchmark_4b_quality_bars <- function(dsl_plot_base, selected_func_ids, selected_alg_ids, cfg) {
  if (!isTRUE(cfg$show_Bm4_ergebnisqualitaet)) return(invisible(NULL))

  y_cap_grouped <- as_single_numeric_or_default( # nolint: object_usage_linter.
    cfg$plot$y_cap_quality_bar_grouped,
    as_single_numeric_or_default(cfg$plot$y_cap_quality_bar, 250) # nolint: object_usage_linter.
  )
  y_cap_aggregated <- as_single_numeric_or_default( # nolint: object_usage_linter.
    cfg$plot$y_cap_quality_bar_aggregated, y_cap_grouped)

  quality_all_rows <- list()

  for (target_quality_func_id in selected_func_ids) {
    ds_quality <- subset(dsl_plot_base, funcId == target_quality_func_id)# nolint: object_usage_linter.

    if (length(ds_quality) == 0) next

    runtime_quality <- cfg$runtime_budget
    if (!is.finite(runtime_quality)) next

    problem_quality_rows <- list()
    for (alg in selected_alg_ids) {
      ds_alg <- subset(ds_quality, algId == alg)# nolint: object_usage_linter.
      if (length(ds_alg) == 0) next

      dt_alg <- tryCatch(
        IOHanalyzer::get_FV_sample(ds_alg, runtime_quality, output = "long"),
        error = function(e) NULL)

      fx_vals <- extract_finite_fx(dt_alg)

      if (length(fx_vals) == 0) next
      best_alg <- min(fx_vals)

      if (is.finite(best_alg)) {
        problem_quality_rows[[length(problem_quality_rows) + 1]] <- data.frame(
          funcId_plot = as.character(target_quality_func_id),
          algId_plot = alg, best_value = best_alg,
          runtime_quality = runtime_quality, stringsAsFactors = FALSE)
      }
    }

    if (length(problem_quality_rows) > 0) {
      quality_df <- do.call(rbind, problem_quality_rows)

      ref_best <- min(quality_df$best_value, na.rm = TRUE)

      if (is.finite(ref_best) && abs(ref_best) >= .Machine$double.eps) {
        quality_df$rel_pct <- 100 * quality_df$best_value / ref_best
        quality_all_rows[[length(quality_all_rows) + 1]] <- quality_df
      }
    }
  }

  if (length(quality_all_rows) == 0) {
    warning("Balkenplot zur Ergebnisqualitaet konnte nicht erstellt werden (keine FV-Werte verfuegbar).")
    return(invisible(NULL))
  }

  quality_all_df <- do.call(rbind, quality_all_rows)

  # Algorithmen sortieren: gut -> schlecht nach mittlerer relativer Abweichung.
  alg_perf_df <- stats::aggregate(rel_pct ~ algId_plot, data = quality_all_df, FUN = mean)
  alg_perf_df <- alg_perf_df[order(alg_perf_df$rel_pct, decreasing = FALSE), , drop = FALSE]
  alg_order_ids <- as.character(alg_perf_df$algId_plot)
  alg_order_labels <- alg_order_ids

  quality_all_df$alg_text <- as.character(quality_all_df$algId_plot)
  quality_all_df$alg_text <- factor(quality_all_df$alg_text, levels = alg_order_labels)

  quality_all_df$problem_label <- paste("Problem", quality_all_df$funcId_plot)
  prob_order <- paste("Problem", as.character(selected_func_ids))
  quality_all_df$problem_label <- factor(quality_all_df$problem_label, levels = prob_order)

  quality_all_df <- add_capped_bar_labels(quality_all_df, "rel_pct", "bar_label", y_cap_grouped)

  # ---- Gruppierter Balkenplot: X = Algorithmen, Farbe = Problem ----
  problem_palette_base <- c("#6BAED6", "#FDCDAC", "#B2DF8A", "#edb78e", "#FB9A99", "#CAB2D6")
  problem_colors <- setNames(
    grDevices::colorRampPalette(problem_palette_base)(length(prob_order)),
    prob_order
  )

  p_quality_bar <- plotly::plot_ly(
    data   = quality_all_df,
    x      = ~alg_text,
    y      = ~y_display,
    type   = "bar",
    color  = ~problem_label,
    colors = problem_colors,
    text   = ~bar_label,
    textposition = "outside",
    textfont = list(color = "black"),
    hovertemplate = paste0("%{customdata}",
      ", relativer Wert:%{meta:.1f}%<extra></extra>"),
    customdata = ~problem_label,
    meta = ~rel_pct
  ) |> plotly::layout(
    barmode = "group",
    xaxis   = list(title = "Algorithmus"),
    yaxis   = list(
      title = "Relative Ergebnisqualitaet [%]",
      range = c(0, y_cap_grouped),
      tickmode = "linear", tick0 = 0, dtick = 50),
    uniformtext = list(mode = "show"),
    showlegend = TRUE,
    legend  = list(
      title = list(text = "Problem"),
      orientation = "h", xanchor = "center", x = 0.5)
  )

  render_benchmark_plot(
    p_quality_bar,
    cfg,
    "plot_ergebnisqualitaet_balken_bester_durchlauf",
    plot_type = "quality_bar_grouped"
  ) # nolint: object_usage_linter.

  # ---- Aggregierter Plot: ein Balken pro Algorithmus (Mittel ueber Probleme) ----
  quality_summary_rows <- summarize_quality_by_algorithm(quality_all_df, selected_alg_ids)

  if (length(quality_summary_rows) > 0) {
    quality_summary_df <- do.call(rbind, quality_summary_rows)

    quality_summary_df$alg_text <- as.character(quality_summary_df$algId_plot)

    quality_summary_df$alg_text <- factor(
      quality_summary_df$alg_text, 
      levels = alg_order_labels)
    quality_summary_df <- quality_summary_df[order(quality_summary_df$alg_text), , drop = FALSE]

    quality_summary_df <- add_capped_bar_labels(
      quality_summary_df, "mean_rel_pct", "bar_label", y_cap_aggregated
    )

    quality_summary_df$hover_text <- paste0(
      "Mittelwert:", sprintf("%.1f%%,", quality_summary_df$mean_rel_pct),
      " Median:", sprintf("%.1f%%,", quality_summary_df$median_rel_pct),
      " Anzahl Probleme:", quality_summary_df$n_problems)

    p_quality_bar_all <- plotly::plot_ly()

    for (alg in alg_order_ids) {
      row <- quality_summary_df[quality_summary_df$algId_plot == alg, , drop = FALSE]
      if (nrow(row) == 0) next
      row <- row[1, , drop = FALSE]
      
      clr <- get_algorithm_color(alg, cfg$my_colors, default = "#888888")
      lbl <- as.character(alg)

      p_quality_bar_all <- p_quality_bar_all |> plotly::add_trace(
        type = "bar",
        x = list(lbl), y = list(row$y_display),
        text = list(row$bar_label), hovertext = list(row$hover_text),
        textposition = "outside", hoverinfo = "text",
        textfont = list(color = "black"),
        marker = list(color = clr, opacity = 0.7),
        name = lbl, showlegend = FALSE
      )
    }
    p_quality_bar_all <- p_quality_bar_all |> plotly::layout(
      xaxis = list(title = "Algorithmus"),
      yaxis = list(title = "Mittelwert der ErgebnisqualitÃ¤t [%]",
                   range = c(0, y_cap_aggregated), tickmode = "linear", tick0 = 0, dtick = 50),
      showlegend = FALSE,
      uniformtext = list(mode = "show"))

    render_benchmark_plot(
      p_quality_bar_all,
      cfg,
      "plot_ergebnisqualitaet_balken_aggregiert",
      plot_type = "quality_bar_aggregated"
    ) # nolint: object_usage_linter.
  }
}

# ============================================================================
# MASTER: Alle Benchmark-Plots ausfuehren
# ============================================================================

run_all_benchmarks <- function(dsl_plot_base, analysis_data, plot_data, 
                               selected_func_ids, selected_alg_ids, cfg) {
  cat("\n========== BENCHMARK-PLOTS ==========\n")
  n_problems <- length(selected_func_ids)

  if (isTRUE(cfg$show_Bm1_konvergenz)) {
    cat(sprintf("[BM1a] Konvergenz Multi-Func\n"))
    benchmark_1a_convergence_multi_func(dsl_plot_base, cfg)
  }
  if (isTRUE(cfg$show_Bm1_konvergenz_single)) {
    cat(sprintf("[BM1b] Einzelalgorithmus-Konvergenz - %d Probleme\n", n_problems))
    benchmark_1b_convergence_single_algo(dsl_plot_base, selected_func_ids, cfg)
  }
  if (isTRUE(cfg$show_Bm1_konvergenz)) {
    cat(sprintf("[BM1c] Median-Konvergenz\n"))
    benchmark_1c_convergence_median(plot_data, selected_func_ids, cfg)
  }

  if (isTRUE(cfg$show_Bm2_stabilitaet)) {
    cat(sprintf("[BM2]  Stabilitaet (abs + rel) - %d Probleme\n", n_problems))
    benchmark_2_stability(analysis_data, selected_func_ids, cfg)
  }
  if (isTRUE(cfg$show_Bm3_robustheit)) {
    cat("[BM3]  Robustheit (aggregiert)\n")
    benchmark_3_robustness(plot_data, cfg)
  }
  if (isTRUE(cfg$show_Bm2_BM3_mix)) {
    cat("[BM2+3] Mix Stabilitaet/Robustheit\n")
    benchmark_2_3_mix(plot_data, cfg)
  }

  if (isTRUE(cfg$show_Bm4_ergebnisqualitaet)) {
    cat(sprintf("[BM4a] ECDF - aggregiert + %d Probleme\n", n_problems))
    benchmark_4a_ecdf(dsl_plot_base, analysis_data, selected_func_ids, cfg)
    cat("[BM4b] Ergebnisqualitaet (gruppiert + aggregiert)\n")
    benchmark_4b_quality_bars(dsl_plot_base, selected_func_ids, selected_alg_ids, cfg)
  }

  if (isTRUE(cfg$save_html) || isTRUE(cfg$save_png)) {
    cat(sprintf("[EXPORT] Plots gespeichert nach: %s\n",
                get_plot_output_dir(cfg))) # nolint: object_usage_linter.
  }
  cat("========== ALLE BENCHMARKS ABGESCHLOSSEN ==========\n\n")
}