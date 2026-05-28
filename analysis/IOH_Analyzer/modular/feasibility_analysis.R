# Zulaessigkeitsanalyse fuer plotrelevante und gesamte rohe IOH-Daten.
# Erstellt eine Detailtabelle nach Scope sowie eine Gesamtuebersicht je Algorithmus.
#
# Kategorien:
#   1. Datenparsing (.dat-Dateien lesen, Spalten erkennen, numerische Konversion)
#   2. Feasibility-Metriken (Constraint-Pruefung, Run-Zusammenfassung)
#   3. Datenbereinigung (Duplikate, letzte Zeilen, Budget-Cap)
#   4. Aggregation und Tabellenaufbau (Detail- und Gesamttabellen)
#   5. Orchestrierung (run_feasibility_analysis)

extract_problem_id_from_folder <- function(folder) {
  folder_name <- basename(folder)
  parts <- strsplit(folder_name, "__", fixed = TRUE)[[1]]
  if (length(parts) >= 2 && nzchar(parts[2])) {
    # Ordnernamen aus dem Dateisystem koennen nicht-numerische Teile enthalten.
    suppressWarnings(as.integer(parts[2]))
  } else {
    NA_integer_
  }
}

get_feasibility_constraint_columns <- function(df) {
  grep("^c__", names(df), value = TRUE)
}

get_feasibility_fitness_column <- function(df) {
  candidates <- c("raw_y", "y", "y_p")
  match <- candidates[candidates %in% names(df)]
  if (length(match) == 0) {
    stop("Keine unterstuetzte Fitnessspalte in der .dat-Datei gefunden. Erwartet: raw_y, y oder y_p.")
  }
  match[1]
}

read_ioh_dat_table <- function(dat_file) {
  raw_lines <- readLines(dat_file, warn = FALSE)
  raw_lines <- raw_lines[nzchar(trimws(raw_lines))]

  if (length(raw_lines) == 0) {
    return(data.frame())
  }

  repeated_header <- grepl("^evaluations\\s+", raw_lines)
  keep_lines <- !repeated_header
  keep_lines[1] <- TRUE
  filtered_lines <- raw_lines[keep_lines]

  utils::read.table(
    text = filtered_lines,
    header = TRUE,
    check.names = FALSE,
    stringsAsFactors = FALSE
  )
}

coerce_numeric_columns <- function(df, columns) {
  for (col in columns) {
    if (col %in% names(df)) {
      # .dat-Dateien von IOHprofiler koennen nicht-numerische Eintraege enthalten.
      df[[col]] <- suppressWarnings(as.numeric(df[[col]]))
    }
  }
  df
}

annotate_feasibility_metrics <- function(df) {
  constraint_cols <- get_feasibility_constraint_columns(df)
  if (length(constraint_cols) == 0) {
    df$feasible <- TRUE
    df$max_violation <- 0
    return(df)
  }

  df <- coerce_numeric_columns(df, constraint_cols)
  constraint_mat <- as.matrix(df[, constraint_cols, drop = FALSE])
  if (is.null(dim(constraint_mat))) {
    constraint_mat <- matrix(constraint_mat, ncol = length(constraint_cols))
    colnames(constraint_mat) <- constraint_cols
  }

  df$max_violation <- apply(constraint_mat, 1, function(row) {
    row <- row[is.finite(row)]
    if (length(row) == 0) return(0)
    max(row)
  })
  df$feasible <- df$max_violation == 0
  df
}

annotate_run_feasibility_summary <- function(df) {
  if (is.null(df) || nrow(df) == 0) return(df)

  req_cols <- c("problem_id", "algorithm", "run", "feasible", "fitness_value", "evaluations")
  if (!all(req_cols %in% names(df))) return(df)

  split_keys <- interaction(df$problem_id, df$algorithm, df$run, drop = TRUE, lex.order = TRUE)
  groups <- split(df, split_keys)

  annotated_groups <- lapply(groups, function(group_df) {
    group_df <- group_df[order(group_df$evaluations), , drop = FALSE]

    feasible_idx <- which(!is.na(group_df$feasible) & group_df$feasible)
    n_feasible <- length(feasible_idx)
    finite_evals <- group_df$evaluations[is.finite(group_df$evaluations)]
    n_eval_in_run <- if (length(finite_evals) > 0) max(finite_evals) else NA_real_

    best_feasible_value <- NA_real_
    best_feasible_eval <- NA_real_

    if (n_feasible > 0) {
      feasible_rows <- group_df[feasible_idx, , drop = FALSE]
      finite_fitness_idx <- which(is.finite(feasible_rows$fitness_value))

      if (length(finite_fitness_idx) > 0) {
        best_group_idx <- feasible_idx[finite_fitness_idx[which.min(feasible_rows$fitness_value[finite_fitness_idx])]]
        best_feasible_value <- group_df$fitness_value[best_group_idx]
        best_feasible_eval <- group_df$evaluations[best_group_idx]
      }
    }

    group_df$feasible_count <- n_feasible
    group_df$feasible_rate <- if (!is.na(n_eval_in_run) && n_eval_in_run > 0) {
      n_feasible / n_eval_in_run
    } else {
      NA_real_
    }
    group_df$run_eval_count <- n_eval_in_run
    group_df$best_feasible_value <- best_feasible_value
    group_df$best_feasible_eval <- best_feasible_eval
    group_df
  })

  out <- do.call(rbind, annotated_groups)
  rownames(out) <- NULL
  out
}

assign_run_ids_from_evaluations <- function(df) {
  if (!("evaluations" %in% names(df))) {
    stop("Die .dat-Datei enthaelt keine Spalte 'evaluations'.")
  }
  df <- coerce_numeric_columns(df, "evaluations")
  evals <- df$evaluations
  run_starts <- evals == 1
  if (length(run_starts) == 0) {
    df$run <- integer(0)
    return(df)
  }
  if (!isTRUE(run_starts[1])) {
    run_starts[1] <- TRUE
  }
  df$run <- cumsum(run_starts)
  df
}

load_feasibility_raw_data <- function(folder_to_analyse, runtime_budget) {
  raw_rows <- list()

  for (folder in folder_to_analyse) {
    json_files <- list.files(folder, pattern = "^IOHprofiler_.*\\.json$", full.names = TRUE)
    if (length(json_files) == 0) next

    for (json_file in json_files) {
      meta <- jsonlite::fromJSON(json_file, simplifyVector = FALSE)
      if (is.null(meta$scenarios) || length(meta$scenarios) == 0) next

      scenario <- meta$scenarios[[1]]
      dat_rel_path <- scenario$path
      dat_file <- file.path(folder, dat_rel_path)
      if (!file.exists(dat_file)) next

      dt <- read_ioh_dat_table(dat_file)
      if (nrow(dt) == 0) next

      dt <- assign_run_ids_from_evaluations(dt)
      dt <- annotate_feasibility_metrics(dt)

      fitness_col <- get_feasibility_fitness_column(dt)
      dt <- coerce_numeric_columns(dt, fitness_col)
      dt$fitness_value <- dt[[fitness_col]]
      dt$algorithm <- if (!is.null(meta$algorithm$name)) as.character(meta$algorithm$name) else basename(folder)
      dt$function_id <- if (!is.null(meta$function_id)) as.integer(meta$function_id) else NA_integer_
      dt$function_name <- if (!is.null(meta$function_name)) as.character(meta$function_name) else NA_character_
      dt$problem_id <- extract_problem_id_from_folder(folder)
      dt$source_folder <- basename(folder)
      dt$source_json <- basename(json_file)
      dt$source_dat <- basename(dat_file)
      dt$within_budget <- dt$evaluations <= runtime_budget

      raw_rows[[length(raw_rows) + 1]] <- dt
    }
  }

  if (length(raw_rows) == 0) {
    return(data.frame())
  }

  raw_df <- do.call(rbind, raw_rows)
  rownames(raw_df) <- NULL
  raw_df
}

pick_min_fitness_rows <- function(df, group_cols) {
  if (is.null(df) || nrow(df) == 0) return(df)

  split_keys <- interaction(df[, group_cols, drop = FALSE], drop = TRUE, lex.order = TRUE)
  groups <- split(df, split_keys)

  picked <- lapply(groups, function(group_df) {
    finite_idx <- which(is.finite(group_df$fitness_value))
    if (length(finite_idx) == 0) {
      # Kein finiter Fitnesswert (z. B. alle Inf): Fallback auf kleinsten nicht-NA-Wert
      non_na_idx <- which(!is.na(group_df$fitness_value))
      if (length(non_na_idx) == 0) return(group_df[1L, , drop = FALSE])
      return(group_df[non_na_idx[which.min(group_df$fitness_value[non_na_idx])], , drop = FALSE])
    }
    group_df[finite_idx[which.min(group_df$fitness_value[finite_idx])], , drop = FALSE]
  })

  picked <- Filter(Negate(is.null), picked)
  if (length(picked) == 0) return(df[0, , drop = FALSE])

  out <- do.call(rbind, picked)
  rownames(out) <- NULL
  out
}

drop_last_row_per_run <- function(df) {
  if (is.null(df) || nrow(df) == 0) return(df)
  req_cols <- c("problem_id", "algorithm", "run", "evaluations")
  if (!all(req_cols %in% names(df))) return(df)

  split_keys <- interaction(df$problem_id, df$algorithm, df$run, drop = TRUE, lex.order = TRUE)
  groups <- split(df, split_keys)

  cleaned_groups <- lapply(groups, function(group_df) {
    if (nrow(group_df) <= 1) return(group_df)

    group_df <- group_df[order(group_df$evaluations), , drop = FALSE]
    group_df[-nrow(group_df), , drop = FALSE]
  })

  out <- do.call(rbind, cleaned_groups)
  if (is.null(out) || nrow(out) == 0) {
    return(df[0, , drop = FALSE])
  }
  rownames(out) <- NULL
  out
}

cap_rows_per_run_to_budget <- function(df, runtime_budget) {
  if (is.null(df) || nrow(df) == 0) return(df)
  req_cols <- c("problem_id", "algorithm", "run", "evaluations")
  if (!all(req_cols %in% names(df))) return(df)

  split_keys <- interaction(df$problem_id, df$algorithm, df$run, drop = TRUE, lex.order = TRUE)
  groups <- split(df, split_keys)

  capped_groups <- lapply(groups, function(group_df) {
    group_df <- group_df[order(group_df$evaluations), , drop = FALSE]
    group_df <- group_df[is.finite(group_df$evaluations) & group_df$evaluations <= as.numeric(runtime_budget), , drop = FALSE]
    if (nrow(group_df) <= 0) {
      return(group_df[0, , drop = FALSE])
    }
    group_df
  })

  out <- do.call(rbind, capped_groups)
  if (is.null(out) || nrow(out) == 0) {
    return(df[0, , drop = FALSE])
  }
  rownames(out) <- NULL
  out
}

resolve_active_feasibility_scopes <- function(cfg) {
  scopes <- list(
    bm2 = isTRUE(cfg$show_Bm2_stabilitaet),
    bm3 = isTRUE(cfg$show_Bm3_robustheit),
    mix = isTRUE(cfg$show_Bm2_BM3_mix),
    bm4b = isTRUE(cfg$show_Bm4_ergebnisqualitaet)
  )

  if (!any(unlist(scopes))) {
    scopes <- list(bm2 = TRUE, bm3 = TRUE, mix = TRUE, bm4b = TRUE)
  }
  scopes
}

collapse_detail_scopes <- function(detail_df) {
  if (is.null(detail_df) || nrow(detail_df) == 0) {
    return(detail_df)
  }

  # Nur stabile ID-Spalten als Gruppen-Schluessel verwenden.
  # Metriken wie best_feasible_value/best_feasible_eval koennen NA sein
  # (z. B. wenn ein Algorithmus nie eine zulaessige Loesung gefunden hat).
  # interaction() + split() werfen NA-Gruppen stillschweigend weg, weshalb
  # alle anderen Spalten als Schluessel zu falschen Nullen im Detail-CSV fuehren.
  id_cols <- intersect(c("problem_id", "algorithm", "run", "evaluations_nmr"), names(detail_df))
  split_keys <- interaction(detail_df[, id_cols, drop = FALSE], drop = TRUE, lex.order = TRUE)
  groups <- split(detail_df, split_keys)

  collapsed <- lapply(groups, function(group_df) {
    row <- group_df[1, , drop = FALSE]
    row$scope <- paste(unique(as.character(group_df$scope)), collapse = " | ")
    row
  })

  out <- do.call(rbind, collapsed)
  rownames(out) <- NULL
  out
}

build_plot_feasibility_detail_table <- function(raw_budget_df, cfg) {
  if (is.null(raw_budget_df) || nrow(raw_budget_df) == 0) {
    return(data.frame())
  }

  detail_parts <- list()
  run_best_rows <- pick_min_fitness_rows(raw_budget_df, c("problem_id", "algorithm", "run"))
  active_scopes <- resolve_active_feasibility_scopes(cfg)

  if (isTRUE(active_scopes$bm2) && nrow(run_best_rows) > 0) {
    bm2_rows <- run_best_rows
    bm2_rows$scope <- "BM2_run_best"
    detail_parts[[length(detail_parts) + 1]] <- bm2_rows
  }

  if (isTRUE(active_scopes$mix) && nrow(run_best_rows) > 0) {
    mix_rows <- run_best_rows
    mix_rows$scope <- "BM2+3Mix_run_best"
    detail_parts[[length(detail_parts) + 1]] <- mix_rows
  }

  if (isTRUE(active_scopes$bm3) && nrow(run_best_rows) > 0) {
    bm3_rows <- pick_min_fitness_rows(run_best_rows, c("problem_id", "algorithm"))
    if (nrow(bm3_rows) > 0) {
      bm3_rows$scope <- "BM3_best_run"
      detail_parts[[length(detail_parts) + 1]] <- bm3_rows
    }
  }

  if (isTRUE(active_scopes$bm4b)) {
    bm4_rows <- pick_min_fitness_rows(raw_budget_df, c("problem_id", "algorithm"))
    if (nrow(bm4_rows) > 0) {
      bm4_rows$scope <- "BM4b_best_value"
      detail_parts[[length(detail_parts) + 1]] <- bm4_rows
    }
  }

  if (length(detail_parts) == 0) {
    return(data.frame())
  }

  detail_df <- do.call(rbind, detail_parts)
  rownames(detail_df) <- NULL

  keep_cols_map <- c(
    scope = "scope",
    problem_id = "problem_id",
    algorithm = "algorithm",
    run = "run",
    eval_nmr_min_fitness = "evaluations",
    min_fitness_value = "fitness_value",
    feasible = "feasible",
    max_violation = "max_violation",
    feasible_count = "feasible_count",
    run_eval_count = "run_eval_count",
    feasible_rate = "feasible_rate",
    eval_nmr_min_feasible = "best_feasible_eval",
    min_feasible_value = "best_feasible_value",
    function_name = "function_name"
  )

  keep_cols_map <- keep_cols_map[unname(keep_cols_map) %in% names(detail_df)]
  detail_df <- detail_df[, unname(keep_cols_map), drop = FALSE]
  names(detail_df) <- names(keep_cols_map)
  detail_df <- collapse_detail_scopes(detail_df)
  detail_df <- detail_df[order(detail_df$problem_id, detail_df$algorithm, detail_df$run), , drop = FALSE]
  rownames(detail_df) <- NULL
  detail_df
}

build_overall_feasibility_summary <- function(raw_budget_df) {
  if (is.null(raw_budget_df) || nrow(raw_budget_df) == 0) {
    return(data.frame())
  }

  alg_split <- split(raw_budget_df, raw_budget_df$algorithm)
  summary_rows <- lapply(names(alg_split), function(alg) {
    alg_df <- alg_split[[alg]]
    n_total <- nrow(alg_df)
    n_feasible <- sum(alg_df$feasible, na.rm = TRUE)
    data.frame(
      algorithm = alg,
      n_total = n_total,
      n_feasible = n_feasible,
      feasible_rate = if (n_total > 0) n_feasible / n_total else NA_real_,
      stringsAsFactors = FALSE
    )
  })

  summary_df <- do.call(rbind, summary_rows)
  rownames(summary_df) <- NULL
  summary_df[order(summary_df$algorithm), , drop = FALSE]
}

write_feasibility_outputs <- function(detail_df,
                                      overall_df,
                                      output_dir = file.path(
                                        "IOH_Analyzer",
                                        paste0("feasibility_outputs_", format(Sys.time(), "%Y%m%d_%H%M%S"))
                                      )) {
  if (!dir.exists(output_dir)) {
    dir.create(output_dir, recursive = TRUE)
  }

  files <- list(
    detail = file.path(output_dir, "feasibility_detail_plot_scopes.csv"),
    overall = file.path(output_dir, "feasibility_overall_by_algorithm.csv")
  )

  # CSV (Komma-Trenner, Punkt als Dezimalzeichen) verwenden, um Locale-Probleme
  # in LibreOffice/Excel zu vermeiden (z. B. Fehlinterpretation von 0.131).
  utils::write.csv(detail_df, files$detail, row.names = FALSE)
  utils::write.csv(overall_df, files$overall, row.names = FALSE)

  files
}

print_feasibility_analysis <- function(detail_df, overall_df, runtime_budget, output_files = NULL) {
  cat("\n[FEASIBILITY] Analyse der Zulaessigkeit bis Runtime-Budget\n")
  cat(sprintf("  - Runtime-Budget: %d\n", runtime_budget))
  active_scopes <- if (!is.null(detail_df) && nrow(detail_df) > 0) {
    paste(unique(as.character(detail_df$scope)), collapse = " | ")
  } else {
    "(keine)"
  }
  cat(sprintf("  - Scopes: %s\n", active_scopes))

  if (!is.null(output_files)) {
    cat("\n[FEASIBILITY] Ergebnisse als CSV gespeichert:\n")
    cat(sprintf("  - Detail (Plot-Scopes): %s\n", output_files$detail))
    cat(sprintf("  - Gesamt: %s\n", output_files$overall))
  }

  if (!is.null(overall_df) && nrow(overall_df) > 0) {
    cat("\n[FEASIBILITY] Gesamttabelle pro Algorithmus\n")
    print(overall_df, row.names = FALSE)
  } else {
    cat("\n[FEASIBILITY] Keine Overall-Daten bis Budget verfuegbar.\n")
  }

  invisible(NULL)
}

run_feasibility_analysis <- function(folder_to_analyse, cfg) {
  raw_df <- load_feasibility_raw_data(
    folder_to_analyse = folder_to_analyse,
    runtime_budget = cfg$runtime_budget
  )

  if (nrow(raw_df) == 0) {
    warning("Zulaessigkeitsanalyse uebersprungen: Es konnten keine rohen .dat-Zeilen geladen werden.")
    return(invisible(list(raw = raw_df, detail = data.frame(), overall = data.frame())))
  }

  raw_budget_df <- drop_last_row_per_run(raw_df)
  raw_budget_df <- cap_rows_per_run_to_budget(raw_budget_df, cfg$runtime_budget)
  raw_budget_df <- annotate_run_feasibility_summary(raw_budget_df)
  detail_df <- build_plot_feasibility_detail_table(raw_budget_df, cfg)
  overall_df <- build_overall_feasibility_summary(raw_budget_df)
  output_files <- write_feasibility_outputs(detail_df = detail_df, overall_df = overall_df)

  print_feasibility_analysis(detail_df, overall_df, cfg$runtime_budget, output_files)

  invisible(list(
    raw = raw_df,
    raw_budget = raw_budget_df,
    detail = detail_df,
    overall = overall_df,
    output_files = output_files
  ))
}