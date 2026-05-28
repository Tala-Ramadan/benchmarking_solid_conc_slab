#========================================================================
# Erstellt von Tala Ramadan im Rahmen der Masterarbeit
# Matrikel-Nmr.: (aus Datenschutzgründen nicht angegeben)
# Thema: Benchmarking von Optimierungsalgorithmen in Python für 
#        Deckensysteme am Beispiel einer einachsig gespannten 
#        Stahlbeton-Massivdecke
# Stand: 28.05.2026
# Inhalt: Sämtliche Module der IOHanalyzer-Auswertungen
#         main.R, data_loading.R, plot_styling.R, benchmark_plots.R,
#          feasibility_analysis.R
#========================================================================

# Haupteinstiegspunkt der modularisierten IOHanalyzer-Auswertung.
#
# Architektur:
#   main.R           ->  Konfiguration, Modulladung, Pipeline-Orchestrierung
#   data_loading.R   ->  Ordnerselektion, Datenimport, Budgetfilter, Aggregation
#   plot_styling.R   ->  Preset-basiertes Styling, Rendering, HTML/PNG-Export
#   benchmark_plots.R   ->  8 Benchmark-Plotvarianten (BM1a-c, BM2, BM3, BM2+3, BM4a-b)
#
# Pipeline:
#   1. Konfiguration laden          ->  2. Module sourcen   ->  3. Ordner selektieren
#   4. DSL laden + Budgetfilter     ->   5. Analyse-/Plotdaten aufbauen (one-pass)
#   6. Benchmark-Tabellen drucken   ->   7. Alle Plots erzeugen + exportieren
#
# Die Konfiguration bleibt absichtlich hier, damit Werte zentral angepasst
# und Auswertungen direkt gestartet werden koennen.
# Das vereinfacht iterative Durchlaeufe ohne Neustart der R-Session.

#=======================================================================
# Nutzerkonfiguration
#=======================================================================
get_default_config <- function() {
  list(
    result_to_analyse          = "",
    slab_type                  = "solid_slab_one_way_concrete",
    problem_ids                = c("1", "2", "3", "4"),
    algorithms                 = c("Pymoo_GA", "Pymoo_CMAES", "NLopt_DIRECT",
                                   "NLopt_SBPLX", "Hyperopt_TPE", "RBFOpt", "LHS"), 
    # Bitte diesen Pfad an den lokalen Speicherort des Ergebnisordners anpassen.
    logger_result_folder_path  = "C:\\Users\\Office\\logger_results_finale_Ausfuehrung_Start_260405",
    
    runtime_budget             = 1000,
    
    # ------------------------------------------------------------------
    # Benchmark plot, Tabellen und Analyse-Flags
    # ------------------------------------------------------------------
    show_Bm1_konvergenz        = FALSE,
    show_Bm1_konvergenz_single = FALSE,
    show_Bm2_stabilitaet       = FALSE,
    show_Bm3_robustheit        = FALSE,
    show_Bm2_BM3_mix           = FALSE,
    show_Bm4_ergebnisqualitaet = FALSE,
    
    feasibility_analysis       = FALSE,
    print_attributes           = FALSE,
    save_html                  = FALSE,
    save_png                   = FALSE,
    save_pdf                   = FALSE,
    
    #------------------------------------------------------------------
    # ZusÃ¤tzliche Konfigurationswerte fÃ¼r Plot-Styling, Farben, etc.
    # weitere Einstellungen kÃ¶nnen in plot_styling.R geÃ¤ndert werden.
    #------------------------------------------------------------------
    plot = list(
      # Optionen: "raw_minimal" (IOH-HTML wird nur minimal bereinigt, Subplot-Labels
      #           bleiben erhalten) oder "styled" (vollstaendiges Feintuning wird
      #           angewendet - gleiche Schriftgroessen/Farben wie PNG-Export).
      ioh_html_mode = "raw_minimal"
    ),
    my_colors = c(
      "Pymoo_GA"      = "#4DAF4A",
      "Pymoo_CMAES"   = "#814e88",
      "NLopt_DIRECT"  = "#FF7F00",
      "NLopt_SBPLX"   = "#ada512",
      "Hyperopt_TPE"  = "#E41A1C",
      "RBFOpt"        = "#377EB8",
      "LHS"           = "#6d391b"
    )
  )
}
#=======================================================================

source_modules <- function() {
  cat("\n[INIT] Lade Module...\n")
  
  # Absoluter Pfad relativ zur aufrufenden Datei ermitteln.
  # Durchlauft sys.frames() rueckwaerts auf der Suche nach $ofile (gesetzt von source()).
  # Fallback: getwd()-basierter Pfad.  Fragil bei exotischen Aufrufketten (z.B.
  # knitr, callr), aber ausreichend fuer Rscript- und RStudio-Starts.
  caller_ofile <- NULL
  for (fr in rev(sys.frames())) {
    if (!is.null(fr$ofile) && nzchar(fr$ofile)) {
      caller_ofile <- fr$ofile
      break
    }
  }
  
  if (!is.null(caller_ofile)) {
    mod_dir <- dirname(normalizePath(caller_ofile, winslash = "/", mustWork = FALSE))
  } else {
    mod_dir <- file.path(getwd(), "modular")
  }
  
  # Pruefe ob data_loading.R erreichbar ist. falls nicht, Kandidatenliste durchsuchen.
  # Notwendig wenn VS Code $ofile nicht setzt (z.B. Run-Button statt source()).
  if (!file.exists(file.path(mod_dir, "data_loading.R"))) {
    candidates <- c(
      file.path(getwd(), "modular"),
      file.path(getwd(), "IOH_Analyzer", "modular"),
      "modular",
      file.path("IOH_Analyzer", "modular")
    )
    for (cand in candidates) {
      if (file.exists(file.path(cand, "data_loading.R"))) {
        mod_dir <- normalizePath(cand, winslash = "/", mustWork = FALSE)
        break
      }
    }
  }
  
  source(file.path(mod_dir, "data_loading.R"))
  source(file.path(mod_dir, "plot_styling.R"))
  source(file.path(mod_dir, "benchmark_plots.R"))
  source(file.path(mod_dir, "feasibility_analysis.R"))
  
  cat("[INIT] Alle Module wurden erfolgreich geladen.\n")
  # invisible() gibt TRUE zurueck, unterdrueckt aber die automatische Konsolenausgabe.
  # Da source_modules() nur Seiteneffekte hat (Module laden), gibt es keinen
  # sinnvollen Rueckgabewert. invisible(TRUE) signalisiert Erfolg, ohne die
  # Konsole mit "[1] TRUE" zu verschmutzen, wenn die Funktion direkt aufgerufen wird.
  invisible(TRUE)
}

run_benchmark_analysis <- function(cfg = get_default_config(), load_modules = TRUE) {
  # Eingabe-Validierung: cfg muss eine Liste sein (Schutz vor versehentlicher
  # Uebergabe eines skalaren Wertes oder NULL).
  if (!is.list(cfg)) {
    stop("cfg must be a configuration list.")
  }
  
  # Module nur laden wenn noetig; load_modules = FALSE erlaubt wiederholte
  # Aufrufe in derselben Session ohne erneutes source() aller Dateien.
  if (isTRUE(load_modules)) {
    source_modules()
  }
  
  # Zustandsreset: verhindert, dass der "Preview-Hinweis" aus einem vorherigen
  # Lauf in dieser Session noch als "bereits gezeigt" gilt.
  .ioh_render_state$preview_hint_shown <- FALSE
  
  # Plot-Konfiguration zusammenfuehren: Nutzer-Overrides (cfg$plot) werden per
  # modifyList() auf die vollstaendigen Defaults aus get_plot_config() angewendet,
  # sodass nur explizit gesetzte Werte ueberschrieben werden.
  if (is.null(cfg$plot) || !is.list(cfg$plot)) {
    cfg$plot <- get_plot_config() # nolint: object_usage_linter.
  } else {
    cfg$plot <- utils::modifyList(get_plot_config(), cfg$plot) # nolint: object_usage_linter.
  }

  # ========================================================================
  # STEP 1: Load configuration
  # ========================================================================
  cat(sprintf("[CONFIG] Laufzeitbudget: %d FE\n", cfg$runtime_budget))
  cat(sprintf("[CONFIG] Anzeige-Flags -> BM1: %s, BM2: %s, BM3: %s, BM4: %s\n",
              cfg$show_Bm1_konvergenz, cfg$show_Bm2_stabilitaet,
              cfg$show_Bm3_robustheit, cfg$show_Bm4_ergebnisqualitaet))

  # ========================================================================
  # STEP 1b: Override IOHanalyzer get_color_scheme (Farb-Fix)
  # ========================================================================
  override_iohanalyzer_color_scheme(cfg$my_colors) # nolint: object_usage_linter.

  # ========================================================================
  # STEP 2: Folder selection and data loading
  # ========================================================================
  cat("\n[DATA] Waehle Ergebnisordner...\n")
  
  folder_to_analyse <- get_folders_to_analyse( # nolint: object_usage_linter.
    cfg$result_to_analyse,
    cfg$logger_result_folder_path,
    cfg$slab_type,
    cfg$problem_ids,
    cfg$algorithms
  )
  
  cat(sprintf("[DATA] %d Ordner zur Analyse gefunden\n", length(folder_to_analyse)))
  
  cat("[DATA] Lade DSL und wende Budgetfilter an...\n")
  
  data_obj <- load_dsl_with_budget_filter( # nolint: object_usage_linter.
    folder_to_analyse = folder_to_analyse,
    algorithms = cfg$algorithms,
    runtime_budget = cfg$runtime_budget
  )
  
  dsl_plot_base <- data_obj$dsl_plot_base
  load_audit <- data_obj$audit
  
  if (length(dsl_plot_base) == 0) {
    stop("No datasets loaded after filtering. Check folder paths and algorithm names.")
  }
  
  cat(sprintf("[DATA] DSL geladen: %d DataSets\n", length(dsl_plot_base)))

  # ========================================================================
  # STEP 3: Extract problem and algorithm IDs
  # ========================================================================
  selected_func_ids <- sort(unique(as.integer(IOHanalyzer::get_funcId(dsl_plot_base))))
  selected_alg_ids  <- sort(unique(as.character(IOHanalyzer::get_algId(dsl_plot_base))))

  if (length(selected_func_ids) == 0) stop("No funcId found in DSL.")
  if (length(selected_alg_ids) == 0)  stop("No algId found in DSL.")

  cat(sprintf("[DATA] Funktions-IDs: %s\n", paste(selected_func_ids, collapse = ", ")))
  cat(sprintf("[DATA] Algorithmen: %s\n", paste(selected_alg_ids, collapse = ", ")))

  # Nutzer-Config kann nicht-numerische Strings enthalten (z.B. ""); NA genuegt.
  requested_problem_ids <- suppressWarnings(as.integer(cfg$problem_ids[nzchar(as.character(cfg$problem_ids))]))
  requested_problem_ids <- requested_problem_ids[is.finite(requested_problem_ids)]

  requested_algorithms <- unique(as.character(cfg$algorithms[nzchar(as.character(cfg$algorithms))]))
  excluded_algorithms <- if (length(requested_algorithms) > 0) {
    requested_algorithms[!(tolower(requested_algorithms) %in% tolower(selected_alg_ids))]
  } else {
    character(0)
  }

  cat("\n[PROTOCOL] Datenabdeckung/Ausschluesse\n")
  if (!is.null(load_audit)) {
    cat(sprintf("  - Geladene DataSets gesamt: %d\n", load_audit$n_datasets_loaded))
    cat(sprintf("  - Nach Algorithmusfilter: %d\n", load_audit$n_datasets_after_algorithm_filter))
    cat(sprintf("  - DataSets ohne FV: %d\n", load_audit$n_datasets_missing_fv))
    cat(sprintf("  - Auf Budget gekuerzt: %d\n", load_audit$n_datasets_budget_trimmed))
    cat(sprintf("  - Ohne Werte <= Budget: %d\n", load_audit$n_datasets_over_budget_only))
  }

  cat(sprintf("  - Angefragte Problem-IDs: %s\n",
              if (length(requested_problem_ids) > 0) paste(requested_problem_ids, collapse = ", ") else "(alle)"))
  cat(sprintf("  - Verwendete Problem-IDs: %s\n", paste(selected_func_ids, collapse = ", ")))

  cat(sprintf("  - Angefragte Algorithmen: %s\n",
              if (length(requested_algorithms) > 0) paste(requested_algorithms, collapse = ", ") else "(alle)"))
  cat(sprintf("  - Verwendete Algorithmen: %s\n", paste(selected_alg_ids, collapse = ", ")))
  if (length(excluded_algorithms) > 0) {
    cat(sprintf("  - Ausgeschlossene Algorithmen: %s\n", paste(excluded_algorithms, collapse = ", ")))
    cat("    Grund: Nicht im geladenen Datensatz vorhanden oder nach Filtern keine gueltigen Samples.\n")
  }

  # ========================================================================
  # STEP 4: Build analysis and plot data (one-pass efficiency)
  # ========================================================================
  cat("\n[TRANSFORM] Erzeuge Analysedaten (one-pass: get_FV_sample nur einmal je Problem)...\n")
  
  all_data <- build_all_data(dsl_plot_base, selected_func_ids, cfg$runtime_budget) # nolint: object_usage_linter.
  analysis_data <- all_data$analysis
  plot_data <- all_data$plots

  cat(sprintf("[TRANSFORM] Analysedaten fuer %d Probleme erzeugt\n", length(analysis_data)))

  # ========================================================================
  # STEP 4b: Benchmark tables (FV/RT overview per problem)
  # ========================================================================
  print_benchmark_tables( # nolint: object_usage_linter.
    analysis_data = analysis_data,
    selected_func_ids = selected_func_ids,
    print_attributes = cfg$print_attributes
  )

  # ========================================================================
  # STEP 5: Generate all benchmark plots
  # ========================================================================
  cat("\n[PLOTS] Starte Erzeugung der Benchmark-Plots...\n")

  if (isTRUE(cfg$save_html) || isTRUE(cfg$save_png)) {
    plot_timestamp <- format(Sys.time(), "%Y%m%d_%H%M%S")
    cfg$plot_output_dir <- file.path(
      dirname(cfg$logger_result_folder_path),
      "plot_exports",
      paste0("IOHanalyzer_Benchmark_Plots_", plot_timestamp)
    )
    cat(sprintf("[PLOTS] Speichere nach: %s\n", cfg$plot_output_dir))
  }
  
  run_all_benchmarks( # nolint: object_usage_linter.
    dsl_plot_base = dsl_plot_base,
    analysis_data = analysis_data,
    plot_data = plot_data,
    selected_func_ids = selected_func_ids,
    selected_alg_ids = selected_alg_ids,
    cfg = cfg
  )

  feasibility_result <- NULL
  if (isTRUE(cfg$feasibility_analysis)) {
    cat("\n[FEASIBILITY] Starte Zulaessigkeitsanalyse...\n")
    feasibility_result <- run_feasibility_analysis( # nolint: object_usage_linter.
      folder_to_analyse = folder_to_analyse,
      cfg = cfg
    )
  }

  cat("\n[SUCCESS] Modulare Analysepipeline erfolgreich abgeschlossen.\n")
  
  # invisible() unterdrueckt die automatische Konsolenausgabe des Rueckgabeobjekts.
  # Um das Ergebnis nachtraeglich in der R-Konsole zu inspizieren:
  #   > result <- run_benchmark_analysis(config)
  #   > str(result$analysis_data, max.level = 2)
  #   > result$plot_data$best_run_dataset
  invisible(list(
    dsl = data_obj$dsl,
    dsl_plot_base = dsl_plot_base,
    analysis_data = analysis_data,
    plot_data = plot_data,
    feasibility = feasibility_result,
    config = cfg
  ))
}

# ============================================================================
# Entry point: Execute the pipeline
# ============================================================================

# Manueller Start in der R-Konsole:
# source("IOH_Analyzer/modular/main.R")
if (sys.nframe() == 0L) {
  config <- get_default_config()
  result <- run_benchmark_analysis(config)
}

cat("\n[SESSION INFO] R-Umgebung zur Reproduzierbarkeit:\n")
print(sessionInfo())
