# Modul fuer Datenladen, Filterung und Transformation in der IOHanalyzer-Benchmark-Analyse.
#
# Kategorien:
#   1. Ordnerauswahl (get_folders_to_analyse, find_latest_folder)
#   2. Datenimport + Budgetfilter (load_dsl_with_budget_filter)
#   3. FV/PAR-Skalierung (scale_dataset_fv, create_relative_dataset)
#   4. DataSet-/Run-Auswahl (select_single_run, get_best_run_id)
#   5. Matrixoperationen (pad_column, ensure_matrix, build_rt_matrix)
#   6. DataSetList-Aggregation (assemble_dataset_list, build_best_run_dataset,
#      build_all_runs_dataset)
#   7. One-Pass-Datenerhebung (build_all_data)

# ============================================================================
# KATEGORIE 1: Ordnerauswahl
# ============================================================================

get_folders_to_analyse <- function(result_to_analyse,
                                   logger_result_folder_path,
                                   slab_type,
                                   problem_ids,
                                   algorithms) {
  if (!is.null(result_to_analyse) && nzchar(result_to_analyse)) {
    if (!dir.exists(result_to_analyse)) {
      stop(sprintf("Ordner %s existiert nicht.", result_to_analyse))
    }
    return(c(result_to_analyse))
  }

  all_folders <- list.dirs(logger_result_folder_path, full.names = TRUE, recursive = FALSE)
  if (length(all_folders) == 0) stop("Keine Ergebnisordner gefunden.")

  problem_ids_active <- problem_ids[nzchar(problem_ids)]
  has_problem_filter <- length(problem_ids_active) > 0

  find_latest_folder <- function(pattern) {
    matching_idx <- grep(pattern, basename(all_folders))
    if (length(matching_idx) == 0) return(NULL)
    matching_folders <- all_folders[matching_idx]
    if (length(matching_folders) == 1L) return(matching_folders)
    # Deterministische Regel: pro (Problem, Algorithmus)-Auswahl den neuesten Lauf verwenden.
    # Timestamp aus Ordnername parsen (Format: YYYYMMDD_HHMMSS), Fallback auf mtime.
    bn <- basename(matching_folders)
    m  <- regexpr("[0-9]{8}_[0-9]{6}$", bn)
    ts_strings <- ifelse(m > 0L, regmatches(bn, m), NA_character_)
    if (all(!is.na(ts_strings))) {
      # Lexikographischer Vergleich reicht, da YYYYMMDD_HHMMSS sortierbar ist.
      # which.max() kann nicht mit Strings umgehen, daher max() + which().
      matching_folders[which(ts_strings == max(ts_strings))[1L]]
    } else {
      matching_folders[which.max(file.info(matching_folders)$mtime)]
    }
  }

  selected_folders <- c()
  alg_list <- if (length(algorithms) > 0) algorithms else ""

  for (alg in alg_list) {
    alg_pattern <- if (alg == "") "" else paste0("__", alg, "__")

    if (has_problem_filter) {
      for (pid in problem_ids_active) {
        pattern <- paste0("^", slab_type, "__", pid, "__.*", alg_pattern)
        folder <- find_latest_folder(pattern)
        if (!is.null(folder)) {
          selected_folders <- c(selected_folders, folder)
        }
      }
    } else {
      pattern <- paste0("^", slab_type, ".*", alg_pattern)
      folder <- find_latest_folder(pattern)
      if (!is.null(folder)) {
        selected_folders <- c(selected_folders, folder)
      }
    }
  }

  unique(selected_folders)
}

# ============================================================================
# KATEGORIE 2: Datenladen und Budgetfilter
# ============================================================================

load_dsl_with_budget_filter <- function(folder_to_analyse, algorithms, runtime_budget) {
  dsl <- Reduce(c, lapply(folder_to_analyse, function(f) {
    # IOHanalyzer gibt Fortschrittsmeldungen und Dateiformatwarnungen aus, die bei
    # automatisierten Durchlaeufen keinen Informationswert haben.
    suppressWarnings(suppressMessages(IOHanalyzer::DataSetList(path = f, full_aggregation = FALSE)))
  }))
  if (length(dsl) == 0) stop("Keine Daten geladen. JSON- und .dat-Dateien pruefen.")

  requested_algorithms <- unique(as.character(algorithms[nzchar(as.character(algorithms))]))
  available_algorithms <- sort(unique(as.character(IOHanalyzer::get_algId(dsl))))

  missing_requested_algorithms <- if (length(requested_algorithms) > 0) {
    requested_algorithms[!(tolower(requested_algorithms) %in% tolower(available_algorithms))]
  } else {
    character(0)
  }

  dsl_plot_base <- if (length(algorithms) > 0) {
    alg_ids <- tolower(as.character(IOHanalyzer::get_algId(dsl)))
    dsl[alg_ids %in% tolower(algorithms)]
  } else dsl

  # Deep-Copy: verhindert In-Place-Mutation der originalen DataSet-Objekte in dsl.
  # Wichtig, weil das anschliessende Budget-Trimming $FV per Index veraendert.
  # lapply() strippt die DataSetList-Klasse -> nach der Kopie wiederherstellen.
  dsl_class <- class(dsl_plot_base)
  dsl_plot_base <- lapply(dsl_plot_base, function(ds) {
    ds_copy <- as.list(ds)
    ds_copy$FV <- if (!is.null(ds$FV)) ds$FV[, , drop = FALSE] else NULL
    structure(ds_copy, class = class(ds))
  })
  class(dsl_plot_base) <- dsl_class

  missing_fv_count <- 0L
  over_budget_only_count <- 0L
  budget_trimmed_count <- 0L

  for (i in seq_along(dsl_plot_base)) {
    ds <- dsl_plot_base[[i]]
    if (is.null(ds$FV)) {
      missing_fv_count <- missing_fv_count + 1L
      next
    }
    rt_vals <- as.numeric(rownames(ds$FV))
    # Fixed-Budget-Auswertung: nur Stichproben innerhalb runtime_budget sind zulaessig.
    keep_idx <- which(rt_vals <= runtime_budget)
    if (length(keep_idx) > 0) {
      if (length(keep_idx) < nrow(ds$FV)) {
        budget_trimmed_count <- budget_trimmed_count + 1L
      }
      dsl_plot_base[[i]]$FV <- ds$FV[keep_idx, , drop = FALSE]
    } else {
      # Datenstruktur konsistent halten, aber keine gueltigen In-Budget-Stichproben kennzeichnen.
      dsl_plot_base[[i]]$FV <- ds$FV[0, , drop = FALSE]
      over_budget_only_count <- over_budget_only_count + 1L
    }
  }

  audit <- list(
    requested_algorithms = requested_algorithms,
    available_algorithms = available_algorithms,
    missing_requested_algorithms = missing_requested_algorithms,
    n_datasets_loaded = length(dsl),
    n_datasets_after_algorithm_filter = length(dsl_plot_base),
    n_datasets_missing_fv = missing_fv_count,
    n_datasets_budget_trimmed = budget_trimmed_count,
    n_datasets_over_budget_only = over_budget_only_count
  )

  list(dsl = dsl, dsl_plot_base = dsl_plot_base, audit = audit)
}

# ============================================================================
# KATEGORIE 3: FV/PAR-Skalierung und relative Werte
# ============================================================================

scale_dataset_fv <- function(ds, factor) {
  # Hilfsfunktion auf niedriger Ebene: skaliert genau ein DataSet-Objekt.
  if (is.null(ds) || !is.finite(factor)) return(ds)
  if (!is.null(ds$FV) && is.numeric(ds$FV)) ds$FV <- ds$FV * factor
  if (!is.null(ds$PAR$by_FV) && is.numeric(ds$PAR$by_FV)) ds$PAR$by_FV <- ds$PAR$by_FV * factor
  if (!is.null(ds$PAR$by_RT) && is.numeric(ds$PAR$by_RT)) ds$PAR$by_RT <- ds$PAR$by_RT * factor
  ds
}

create_relative_dataset <- function(dsl_abs, ref_global, func_id) {
  # Orchestrator-Hilfsfunktion: konvertiert eine komplette DataSetList via scale_dataset_fv().
  if (length(dsl_abs) == 0) return(NULL)
  if (!is.finite(ref_global) || abs(ref_global) < .Machine$double.eps) {
    warning(sprintf("[rel] Ungueltige Referenz fuer Problem %s", as.character(func_id)))
    return(NULL)
  }
  factor <- 100 / ref_global
  for (i in seq_along(dsl_abs)) {
    dsl_abs[[i]] <- scale_dataset_fv(dsl_abs[[i]], factor)
  }
  dsl_abs
}

# ============================================================================
# KATEGORIE 4: DataSet- und Run-Auswahl
# ============================================================================

select_single_run <- function(ds, idx) {
  if (is.null(ds)) return(ds)

  pick <- function(x, i) {
    if (is.matrix(x) || is.data.frame(x)) {
      if (ncol(x) < i) return(x)
      return(x[, i, drop = FALSE])
    }
    if (is.numeric(x)) {
      if (length(x) < i) return(x)
      return(x[i])
    }
    x
  }
  
  if (!is.null(ds$FV))  ds$FV  <- pick(ds$FV, idx)
  if (!is.null(ds$RT))  ds$RT  <- pick(ds$RT, idx)
  if (!is.null(ds$PAR$by_FV)) ds$PAR$by_FV <- pick(ds$PAR$by_FV, idx)
  if (!is.null(ds$PAR$by_RT)) ds$PAR$by_RT <- pick(ds$PAR$by_RT, idx)
  ds
}

get_best_run_id <- function(dt_runs) {
  run_ids <- sort(unique(dt_runs$run))
  best_run <- run_ids[which.min(sapply(run_ids, function(r) {
    dtr <- dt_runs[dt_runs$run == r, ]
    dtr <- dtr[order(dtr$runtime), ]
    min(cummin(dtr$`f(x)`), na.rm = TRUE)
  }))]
  best_run
}

# ============================================================================
# KATEGORIE 5: Matrixoperationen und Normalisierung der Datenstruktur
# ============================================================================

pad_column <- function(mat, target_len) {
  if (is.null(mat)) return(NULL)
  mat <- ensure_matrix(mat)

  n <- nrow(mat)
  if (n >= target_len) {
    return(mat[seq_len(target_len), , drop = FALSE])
  }
  
  # Bei Minimierungsproblemen: Zeile mit bestem (kleinstem) Fitnesswert verwenden.
  best_idx <- which.min(mat[, 1])
  fill_row <- mat[best_idx, , drop = FALSE]
  pad_rows <- fill_row[rep(1L, target_len - n), , drop = FALSE]
  rbind(mat, pad_rows)
}

ensure_matrix <- function(x) {
  if (is.null(x)) return(NULL)
  if (is.null(dim(x))) return(matrix(x, ncol = 1))
  x
}

build_rt_matrix <- function(target_len, n_cols) {
  matrix(rep(seq_len(target_len), n_cols),
         nrow = target_len,
         ncol = n_cols
  )
}

clear_aggregated_pid_attr <- function(ds) {
  attr(ds, "funcId") <- NA_integer_
  attr(ds, "DIM")    <- NA_integer_
  ds
}

# ============================================================================
# KATEGORIE 6: DataSetList-Aggregation
# ============================================================================

# Gemeinsamer Assembler: baut aus gesammelten FV-Spalten pro Algorithmus eine DataSetList.
# Wird von build_best_run_dataset() und build_all_runs_dataset() genutzt, um die
# gemeinsame cbind -> RT -> Attributbereinigung -> DataSetList-Konstruktion zu konsolidieren.
#
# Erwartet per_alg als Named List mit Eintraegen der Form:
#   list(fv_cols = list(<matrix>, ...), template = <DataSet>)
assemble_dataset_list <- function(per_alg, target_len) {
  ds_combined <- list()

  for (aid in names(per_alg)) {
    entry <- per_alg[[aid]]
    cols  <- Filter(Negate(is.null), entry$fv_cols)

    if (is.null(entry$template) || length(cols) == 0) next

    template    <- entry$template
    template$FV <- do.call(cbind, cols)
    template$RT <- build_rt_matrix(target_len, ncol(template$FV))
    template    <- clear_aggregated_pid_attr(template)

    ds_combined[[aid]] <- template
  }

  if (length(ds_combined) == 0) return(NULL)
  structure(ds_combined, class = c("DataSetList", "list"))
}

build_best_run_dataset <- function(analysis_data, func_ids, runtime) {
  target_len   <- as.integer(runtime)
  best_per_alg <- list()
  
  for (func_id in func_ids) {
    fid    <- as.character(func_id)
    ds_rel <- analysis_data[[fid]]$rel

    if (is.null(ds_rel) || length(ds_rel) == 0) next
    alg_ids <- as.character(IOHanalyzer::get_algId(ds_rel))

    for (j in seq_along(ds_rel)) {
      fv <- ds_rel[[j]]$FV

      if (is.null(fv) || !is.numeric(fv)) next
      fv <- ensure_matrix(fv)

      best_idx <- which.min(apply(fv, 2, min, na.rm = TRUE))
      aid <- alg_ids[j]

      if (is.null(best_per_alg[[aid]])) {
        best_per_alg[[aid]] <- list(fv_cols = list(), template = NULL)
      }
      if (is.null(best_per_alg[[aid]]$template)) {
        best_per_alg[[aid]]$template <- ds_rel[[j]]
      }
      best_per_alg[[aid]]$fv_cols[[length(best_per_alg[[aid]]$fv_cols) + 1]] <-
        pad_column(select_single_run(ds_rel[[j]], best_idx)$FV, target_len)
    }
  }

  assemble_dataset_list(best_per_alg, target_len)
}

build_all_runs_dataset <- function(analysis_data, func_ids, runtime) {
  target_len  <- as.integer(runtime)
  all_per_alg <- list()
  
  for (func_id in func_ids) {
    fid <- as.character(func_id)
    ds_rel <- analysis_data[[fid]]$rel

    if (is.null(ds_rel) || length(ds_rel) == 0) next
    alg_ids <- as.character(IOHanalyzer::get_algId(ds_rel))

    for (j in seq_along(ds_rel)) {
      fv <- ds_rel[[j]]$FV

      if (is.null(fv) || !is.numeric(fv)) next
      fv <- ensure_matrix(fv)

      aid <- alg_ids[j]

      if (is.null(all_per_alg[[aid]])) {
        all_per_alg[[aid]] <- list(fv_cols = list(), template = NULL)
      }
      if (is.null(all_per_alg[[aid]]$template)) {
        all_per_alg[[aid]]$template <- ds_rel[[j]]
      }
      all_per_alg[[aid]]$fv_cols[[length(all_per_alg[[aid]]$fv_cols) + 1]] <- pad_column(fv, target_len)
    }
  }

  assemble_dataset_list(all_per_alg, target_len)
}

# ============================================================================
# KATEGORIE 7: Effiziente Datenerhebung in einem Durchlauf
# ============================================================================

build_all_data <- function(dsl_input, func_ids, runtime) {
  func_ids_all <- as.integer(IOHanalyzer::get_funcId(dsl_input))
  analysis     <- list()
  # Plot-Tabellen (fv_abs/fv_rel) und aggregierte DataSetLists bedienen unterschiedliche Benchmarks.
  plots        <- list(fv_abs = list(), fv_rel = list())

  for (func_id in func_ids) {
    fid <- as.character(func_id)
    ds_abs <- dsl_input[func_ids_all == func_id]

    dt_abs <- tryCatch(
      IOHanalyzer::get_FV_sample(ds_abs, runtime, output = "long"), 
      error = function(e) {
        warning(sprintf("[TRANSFORM] FV-Sample (absolut) fehlgeschlagen fuer Problem %s: %s",
                        fid, e$message))
        NULL
      })
    plots$fv_abs[[fid]] <- dt_abs

    global_min <- NA_real_
    if (!is.null(dt_abs) && nrow(dt_abs) > 0 && "f(x)" %in% names(dt_abs))
      # min(na.rm=TRUE) warnt bei reinem NA-Vektor; Ergebnis ist dann Inf und
      # wird durch die nachfolgende is.finite()-Pruefung in create_relative_dataset() abgefangen.
      global_min <- suppressWarnings(min(dt_abs[["f(x)"]], na.rm = TRUE))

    # Relative Skalierung normiert jedes Problem auf den beobachteten besten absoluten Wert.
    ds_rel <- create_relative_dataset(ds_abs, global_min, func_id)

    dt_rel <- tryCatch(
      IOHanalyzer::get_FV_sample(ds_rel, runtime, output = "long"), 
      error = function(e) {
        warning(sprintf("[TRANSFORM] FV-Sample (relativ) fehlgeschlagen fuer Problem %s: %s",
                        fid, e$message))
        NULL
      })
    plots$fv_rel[[fid]] <- dt_rel

    analysis[[fid]] <- list(abs = ds_abs, rel = ds_rel, global_min = global_min)
  }

  cat(sprintf("[TRANSFORM] Relative Skalierung (min_rel) fuer %d Probleme bestimmt: %s\n",
              length(func_ids), paste(func_ids, collapse = ", ")))

  plots$best_run_dataset <- build_best_run_dataset(analysis, func_ids, runtime)
  plots$all_runs_dataset  <- build_all_runs_dataset(analysis, func_ids, runtime)

  list(analysis = analysis, plots = plots)
}
