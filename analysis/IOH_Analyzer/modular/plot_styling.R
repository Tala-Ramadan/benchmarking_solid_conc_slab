# Plot-Styling, Preset-System, Rendering und Export fuer IOHanalyzer-Benchmarks.
#
# Zentrale Architektur:
#   Preset-System (get_style_profiles):
#     Zwei Basen (native, ioh) definieren Schriftgroessen, Margins und Export-Defaults.
#     9 Plottyp-Presets erben per modifyList() nur die Deltawerte (CSS-Vererbung).
#     Jedes Preset traegt ein base_type-Feld ("native"/"ioh") fuer die
#     Annotation-Logik, da IOHanalyzer Achsentitel als Annotationen rendert.
#
#   Render-Pipeline (3-stufig):
#     build_render_config()   -> globale Konfig + Preset-Export-Keys + Overrides zusammenfuehren
#     build_styled_plots()    -> HTML-/PNG-Plotly-Objekte mit Stil-Anwendung erzeugen
#     render_styled_plot()    -> Orchestrator: druckt + speichert + Fehlerbehandlung
#
# Farbzuordnung: override_iohanalyzer_color_scheme() patcht IOHanalyzer intern
# per assignInNamespace(); der Aufruf erfolgt in main.R nach dem Modulladung.

# ============================================================================
# KONFIGURATION
# ============================================================================

# Modul-interner Zustand (vermeidet .GlobalEnv-Pollution).
.ioh_render_state <- new.env(parent = emptyenv())
.ioh_render_state$preview_hint_shown <- FALSE

# Workaround fuer IOHanalyzer-Bug: plot_general_data ordnet Farben positionell
# zu, waehrend get_color_scheme IDs alphabetisch sortiert -> Mismatch.
# Fix: Farben per Name matchen statt alphabetisch zuordnen.
# Nutzt assignInNamespace() und ist damit an die interne API von IOHanalyzer
# gebunden - bei Updates der Bibliothek pruefen.
override_iohanalyzer_color_scheme <- function(color_map) {
  if (is.null(color_map) || is.null(names(color_map))) {
    stop("color_map must be a named character vector.")
  }

  assignInNamespace("get_color_scheme", function(ids_in) {
    cols <- character(length(ids_in))
    names(cols) <- ids_in
    for (i in seq_along(ids_in)) {
      id <- ids_in[i]
      if (id %in% names(color_map)) { cols[i] <- color_map[[id]]; next }
      idx <- which(tolower(names(color_map)) == tolower(id))
      if (length(idx) > 0) { cols[i] <- color_map[[idx[1]]]; next }
      cols[i] <- "#999999"
    }
    cols
  }, ns = "IOHanalyzer")

  invisible(TRUE)
}

# Gemeinsame Einstellungen (gelten fuer beide Plot-Typen)
get_shared_style_defaults <- function() {
  list(
    font_family       = "Times New Roman",
    font_color        = "black",
    style_debug_print = FALSE
  )
}

get_style_profiles <- function() {
  # Vererbungsmodell:
  #   native / ioh  ->  Basis-Profile mit allen Schriftgroessen und Margins
  #   preset(base, tweaks)  ->  erzeugt Plottyp-Preset per modifyList(base, tweaks)
  #   Jedes Preset erbt alle Felder der Basis und ueberschreibt nur Deltas.
  #   base_type wird automatisch gesetzt ("native"/"ioh") und steuert
  #   die Annotation-Erkennung in apply_annotation_style().
  #
  # Native: fuer direkt gebaute Plots (Median-Konvergenz, Balken, Einzel-Algo).
  # IOH:    fuer IOHanalyzer-generierte Multi-Subplot-Plots (Konvergenz Multi,
  #         Violin, ECDF) - diese haben Annotationen statt echte Achsentitel.

  # ---- Basis: Native (Median-Konvergenz, Balkenplots, Einzel-Algo) ---------
  native <- list(
    font_size                 = 18,
    title_font_size           = 22,
    axis_title_size           = 22,
    axis_tick_size            = 18,
    legend_font_size          = 20,
    annotation_font_size      = 18,
    html_font_scale           = 0.85,
    png_font_scale            = 1.5,
    top_margin_title          = 150,
    top_margin_no_title       = 30,
    bottom_margin             = 90,
    left_margin               = 70,
    right_margin              = 40,
    legend_y_offset           = -0.3,
    legend_bottom_base        = 130,
    legend_font_multiplier    = 3.2
  )

  # ---- Basis: IOH (Multi-Func-Konvergenz, Violin, ECDF) -------------------
  ioh <- list(
    font_size                  = 22,
    title_font_size            = 28,
    axis_title_size            = 26,
    axis_tick_size             = 22,
    legend_font_size           = 20,
    annotation_font_size       = 22,
    annotation_axis_title_size = 20,
    annotation_subplot_size    = 18,
    html_font_scale            = 0.85,
    png_font_scale             = 1.5,
    top_margin_title           = 20,
    top_margin_no_title        = 21,
    bottom_margin              = 80,
    left_margin                = 70,
    right_margin               = 40,
    legend_y_offset            = -0.2,
    legend_bottom_base         = 95,
    legend_font_multiplier     = 2.4
  )

  preset <- function(base, tweaks = list()) {
    base_type <- if (identical(base, native)) "native" else "ioh"
    c(utils::modifyList(base, tweaks), list(base_type = base_type))
  }

  list(
    # Basis-Profile (Fallback fuer generische Nutzung)
    native = preset(native),
    ioh    = preset(ioh),

    # BM1a: Multi-Funktions-Konvergenz (alle Probleme x alle Algorithmen)
    convergence_multi = preset(ioh, list(
      legend_y_offset         = -0.25,
      axis_title_size         = 22,
      legend_font_size        = 20,
      annotation_subplot_size = 20,
      axis_tick_size          = 17,
      bottom_margin           = 0,
      png_font_scale          = 1.25,
      png_width               = 1800,
      png_height              = 1300
    )),

    # BM1b: Einzelalgorithmus-Konvergenz (Subplot-Raster)
    convergence_single = preset(native, list(
      title_font_size      = 16.5,
      axis_tick_size       = 13,
      axis_title_size      = 14.5,
      top_margin_title     = 70,
      annotation_font_size = 14.5,
      png_font_scale       = 1.25,
      png_width            = 800,
      png_height           = 600
    )),

    # BM1c: Median-Konvergenz (relativ %, ueber Probleme)
    convergence_median   = preset(native, list(
      html_font_scale    = 0.65,
      legend_bottom_base = 0,
      legend_y_offset    = -0.3,
      png_width          = 1750,
      png_height         = 1200
    )),

    # BM2/BM3: Violin/PDF-Plots (Stabilitaet, Robustheit, Mix)
    violin = preset(ioh, list(
      top_margin_title = 120,
      png_width        = 1850,
      png_height       = 1700
    )),

    # BM4a: ECDF (global + je Problem)
    ecdf = preset(ioh, list(
      legend_bottom_base = 75,
      top_margin_title   = 65,
      legend_y_offset    = -0.23,
      title_font_size    = 21,
      axis_title_size    = 20,
      axis_tick_size     = 17,
      legend_font_size   = 17,
      png_font_scale     = 1.3,
      png_width          = 1200,
      png_height         = 1000
    )),

    # BM4b: Qualitaetsbalken gruppiert (nach Algorithmus)
    quality_bar_grouped = preset(native, list(
      legend_bottom_base = 65,
      legend_y_offset    = -0.15,
      html_font_scale    = 0.75,
      bar_text_size      = 14.1,
      bar_mintext        = 14.1,
      png_width          = 2400,
      png_height         = 1400
    )),

    # BM4b: Qualitaetsbalken aggregiert (ueber alle Probleme)
    quality_bar_aggregated = preset(native, list(
      bar_text_size = 20,
      bar_mintext   = 23,
      png_width     = 1600,
      png_height    = 1000
    ))
  )
}

get_plot_domain_defaults <- function() {
  list(
    ioh_html_mode = "raw_minimal", # IOH-HTML: reduziert (raw_minimal) | feingetunt (styled)
    y_cap_quality_bar_grouped = 325,
    y_cap_quality_bar_aggregated = 260,
    single_conv_algorithms_per_plot = 4,
    single_conv_budget_marker_width = 0.5,
    y_range_single_conv = c(25, 650),
    y_range_median_conv = c(100, 250),
    y_range_violin_abs = c(65, 550),
    y_range_violin_rel = c(90, 400),
    ecdf_x_range = c(50, 1e5)
  )
}

get_export_defaults <- function() {
  list(
    png_width = 1600,
    png_height = 1400,
    png_zoom = 2,
    png_delay = 1
  )
}

get_plot_config <- function() {
  profiles <- get_style_profiles()
  c(
    get_shared_style_defaults(),
    profiles$native,
    get_plot_domain_defaults(),
    get_export_defaults(),
    list(style_profiles = profiles)
  )
}

# ============================================================================
# INTERNE BASIS-HELPER
# ============================================================================

as_single_numeric_or_default <- function(value, default) {
  if (is.null(value)) return(default)

  # Funktionsvertrag erlaubt beliebigen Input; NA bei Konversionsfehler genuegt.
  value_num <- suppressWarnings(as.numeric(value))
  if (length(value_num) != 1L || !is.finite(value_num)) {
    default
  } else {
    value_num
  }
}

as_list_or_empty <- function(x) {
  if (is.null(x)) list() else x
}

scale_numeric_fields <- function(cfg, fields, scale_factor) {
  for (field in fields) {
    if (!is.null(cfg[[field]])) {
      cfg[[field]] <- as.numeric(cfg[[field]]) * scale_factor
    }
  }
  cfg
}

suppress_plotly_linetype_warnings <- function(expr) {
  withCallingHandlers(
    expr,
    warning = function(w) {
      if (grepl("plotly\\.js only supports 6 different linetypes", conditionMessage(w), ignore.case = TRUE)) {
        invokeRestart("muffleWarning")
      }
    }
  )
}

normalize_ioh_html_mode <- function(plot_cfg) {
  mode <- if (!is.null(plot_cfg$ioh_html_mode)) as.character(plot_cfg$ioh_html_mode) else "raw_minimal"
  mode <- tolower(mode)

  if (!mode %in% c("styled", "raw_minimal")) {
    mode <- "raw_minimal"
  }

  mode
}

apply_ioh_raw_minimal_cleanup <- function(p_in) {
  p_out <- p_in
  layout_cfg <- p_out$x$layout
  if (is.null(layout_cfg)) return(p_out)

  # Minimalansicht: Nur Achstitel-Annotationen entfernen, Subplot-Labels (F-Nummern) behalten.
  if (!is.null(layout_cfg$annotations)) {
    layout_cfg$annotations <- Filter(
      function(ann) is_ioh_subplot_label(get_annotation_text(ann)),
      layout_cfg$annotations
    )
    if (length(layout_cfg$annotations) == 0L) layout_cfg$annotations <- NULL
  }

  if (!is.null(layout_cfg$legend)) {
    layout_cfg$legend$title <- NULL
  }

  p_out$x$layout <- layout_cfg
  p_out
}

resolve_plot_cfg <- function(cfg, export_overrides = list()) {
  plot_cfg <- get_plot_config()

  if (!is.null(cfg$plot) && is.list(cfg$plot)) {
    plot_cfg <- utils::modifyList(plot_cfg, cfg$plot)
  }

  if (length(export_overrides) > 0L) {
    plot_cfg <- utils::modifyList(plot_cfg, export_overrides)
  }

  plot_cfg
}

# ============================================================================
# KOMPATIBILITAETS-HELPER FUER BENCHMARK-PIPELINE
# ============================================================================

sort_plotly_axis_keys <- function(axis_names, prefix) {
  axis_num <- as.numeric(sub(prefix, "", axis_names))
  axis_num[is.na(axis_num)] <- 1
  axis_names[order(axis_num)]
}

apply_uniform_axes_to_subplots <- function(p, x_cfg, y_cfg,
                                           y_title_first_col_only = FALSE,
                                           x_title_bottom_row_only = FALSE) {
  layout_cfg <- p$x$layout
  if (is.null(layout_cfg)) return(p)

  layout_names <- names(layout_cfg)
  x_axes <- layout_names[grepl("^xaxis[0-9]*$", layout_names)]
  y_axes <- layout_names[grepl("^yaxis[0-9]*$", layout_names)]

  anchor_to_axis_key <- function(anchor, short, long) {
    if (is.null(anchor) || !nzchar(anchor)) {
      long
    } else{
       sub(paste0("^", short), long, anchor)
    }
  }
  get_domain_start <- function(axis_key) {
    d <- layout_cfg[[axis_key]]$domain
    if (length(d) >= 1L) d[1L] else NA_real_ 
  }

  min_x_left   <- min(vapply(x_axes, get_domain_start, numeric(1)), na.rm = TRUE)
  min_y_bottom <- min(vapply(x_axes, function(x_ax) {
    y_key <- anchor_to_axis_key(layout_cfg[[x_ax]]$anchor, "y", "yaxis")
    get_domain_start(y_key)} 
    ,numeric(1)), na.rm = TRUE)

  for (ax in x_axes) {
    cfg <- x_cfg
    if (isTRUE(x_title_bottom_row_only) && is.finite(min_y_bottom)){
      if (!isTRUE(all.equal(get_domain_start(anchor_to_axis_key(layout_cfg[[ax]]$anchor, "y", "yaxis")), min_y_bottom))){
        cfg$title <- ""
      }
    }    
    cfg$matches <- if (ax != "xaxis") "x" else NULL
    p$x$layout[[ax]] <- utils::modifyList(as_list_or_empty(layout_cfg[[ax]]), cfg)
  }

  for (ay in y_axes) {
    cfg <- y_cfg
    if (isTRUE(y_title_first_col_only) && is.finite(min_x_left)) {
      if (!isTRUE(all.equal(get_domain_start(anchor_to_axis_key(layout_cfg[[ay]]$anchor, "x", "xaxis")), min_x_left))) {
        cfg$title <- ""
      }
    }
    cfg$matches <- if (ay != "yaxis") "y" else NULL
    p$x$layout[[ay]] <- utils::modifyList(as_list_or_empty(layout_cfg[[ay]]), cfg)
  }
  p
}

# ============================================================================
# IOH-SPEZIFISCHE ANNOTATIONEN
# ============================================================================

# IOHanalyzer rendert etliche Beschriftungen als Annotationen statt als echte
# Achsen- oder Plot-Titel. Diese Matcher kapseln die aktuelle Heuristik.
get_annotation_text <- function(ann) {
  if (is.null(ann$text)) "" else as.character(ann$text)
}

is_ioh_axis_annotation_text_fallback <- function(text_value) {
  # Tatsaechlich verwendete Achsenbeschriftungen (DE + EN-Originale aus IOHanalyzer).
  grepl(
    paste(
      c(
        "Function Evaluations", "Runtime", "Funktionsauswertungen",
        "Fitnesswert", "Target Value", "GWP",
        "Algorithmus", "Algorithm",
        "Anteil", "Proportion",
        "ERT", "Median"
      ),
      collapse = "|"
    ),
    text_value,
    ignore.case = TRUE
  )
}

is_ioh_bottom_axis_text_fallback <- function(text_value) {
  grepl("Function Evaluations|Funktionsauswertungen", text_value, ignore.case = TRUE)
}

detect_ioh_annotation_role <- function(ann, ann_text = NULL) {
  if (is.null(ann_text)) ann_text <- get_annotation_text(ann)

  if (is_ioh_subplot_label(ann_text)) return("subplot_label")

  # IOHanalyzer setzt Koordinaten teils als String (z.B. "paper");
  # as.numeric() erzeugt dann NA + Warnung - NA genuegt fuer die Geometriepruefung.
  x <- suppressWarnings(as.numeric(ann$x))
  y <- suppressWarnings(as.numeric(ann$y))
  xref <- if (is.null(ann$xref)) "" else as.character(ann$xref)
  yref <- if (is.null(ann$yref)) "" else as.character(ann$yref)
  textangle <- suppressWarnings(as.numeric(ann$textangle))
  is_paper <- grepl("paper", xref, ignore.case = TRUE) && grepl("paper", yref, ignore.case = TRUE)

  # Typische gemeinsame X-Achsentitel liegen im Paper-Koordinatensystem unten mittig.
  is_bottom_axis <- is.finite(x) && is.finite(y) && is_paper &&
    x >= 0.12 && x <= 0.88 && y <= 0.12

  # Typische gemeinsame Y-Achsentitel liegen links und sind oft rotiert.
  is_left_axis <- is.finite(x) && is.finite(y) && is_paper &&
    x <= 0.08 && y >= 0.10 && y <= 0.90 &&
    (!is.finite(textangle) || abs(textangle) >= 60)

  if (is_bottom_axis) return("bottom_axis")
  if (is_left_axis) return("left_axis")
  if (is_ioh_bottom_axis_text_fallback(ann_text)) return("bottom_axis_text")
  if (is_ioh_axis_annotation_text_fallback(ann_text)) return("axis_text_fallback")
  "other"
}

is_ioh_bottom_axis_annotation <- function(ann) {
  role <- detect_ioh_annotation_role(ann)
  role %in% c("bottom_axis", "bottom_axis_text")
}

is_ioh_subplot_label <- function(text_value) {
  grepl("^F[0-9]+$|^Problem\\s+[0-9]+$", text_value, ignore.case = TRUE)
}

# Positionskorrektur fuer bestehende IOHanalyzer-Annotationen
# (z. B. F10005/F10006 sowie gemeinsame Achsenbeschriftungen in Subplots).
adjust_subplot_annotations <- function(p) {
  anns <- p$x$layout$annotations

  if (is.null(anns)) return(p)

  for (k in seq_along(anns)) {
    ann <- anns[[k]]
    txt <- get_annotation_text(ann)

    if (is_ioh_subplot_label(txt)) {
      anns[[k]]$yshift <- -8
      anns[[k]]$yanchor <- "top"
    } else if (is_ioh_bottom_axis_annotation(ann)) {
      anns[[k]]$yshift <- 12
      anns[[k]]$yanchor <- "bottom"
    }
  }
  p$x$layout$annotations <- anns
  p
}

# Wendet Schriftgroessen/Farben auf Plotly-Annotationen an.
# Das ist getrennt von adjust_subplot_annotations(), weil IOHanalyzer viele
# Beschriftungen als Annotationen statt als regulÃ¤re Achsentitel rendert.
apply_annotation_style <- function(annotations, style_cfg, plot_type = c("native", "ioh")) {
  plot_type <- match.arg(plot_type)
  if (is.null(annotations)) return(annotations)

  base_font <- list(
    family = style_cfg$font_family,
    color = style_cfg$font_color,
    size = style_cfg$annotation_font_size
  )

  lapply(annotations, function(ann) {
    ann_text <- get_annotation_text(ann)
    ann_role <- detect_ioh_annotation_role(ann, ann_text = ann_text)
    
    # Starte mit leerer Font-Liste, um alte Groessen zu ueberschreiben
    ann$font <- base_font

    # IOH-Sonderlogik: Subplot-Labels und Achstitel kommen als Annotationen
    # und brauchen separate Groessen. Fuer native Plots entfaellt diese Logik.
    if (identical(plot_type, "ioh")) {
      if (identical(ann_role, "subplot_label")) {
        ann$font$size <- style_cfg$annotation_subplot_size
      } else if (ann_role %in% c("bottom_axis", "left_axis", "bottom_axis_text", "axis_text_fallback")) {
        ann$font$size <- style_cfg$annotation_axis_title_size
      }
    } else if (identical(plot_type, "native")) {
      # Fuer alle native Annotationen (auch Subplots) verwende einheitlich annotation_font_size
      ann$font$size <- style_cfg$annotation_font_size
    }

    ann
  })
}

# ============================================================================
# ECDF-SPEZIALFALL
# ============================================================================

tune_ecdf_xaxis <- function(p, x_range = NULL) {
  x_vals <- unlist(lapply(p$x$data, function(tr) tr$x), use.names = FALSE)
  x_vals <- as.numeric(x_vals)
  x_vals <- x_vals[is.finite(x_vals) & x_vals > 0]

  has_valid_input_range <- !is.null(x_range) && length(x_range) == 2 && all(is.finite(x_range))

  if (isTRUE(has_valid_input_range)) {
    x_lo <- as.numeric(x_range[1])
    x_hi <- as.numeric(x_range[2])
  } else {
    if (length(x_vals) < 2) return(p)
    x_lo <- min(x_vals, na.rm = TRUE)
    x_hi <- max(x_vals, na.rm = TRUE)
  }

  # Log-Achse kann keine 0 oder negativen Werte enthalten.
  # Bei x_lo <= 0 auf kleinsten positiven beobachteten x-Wert klemmen (sonst 1).
  if (!is.finite(x_lo) || x_lo <= 0) {
    x_lo <- if (length(x_vals) > 0) min(x_vals, na.rm = TRUE) else 1
  }
  if (!is.finite(x_hi) || x_hi <= x_lo) {
    x_hi <- if (length(x_vals) > 0) max(x_vals, na.rm = TRUE) else NA_real_
  }

  if (!is.finite(x_lo) || !is.finite(x_hi) || x_hi <= x_lo) return(p)

  exp_lo <- floor(log10(x_lo))
  exp_hi <- ceiling(log10(x_hi))
  n_exp <- exp_hi - exp_lo + 1
  exp_step <- max(1, ceiling(n_exp / 6))
  exponents <- seq(exp_lo, exp_hi, by = exp_step)
  tick_vals <- 10^exponents
  keep <- tick_vals >= x_lo & tick_vals <= x_hi
  tick_vals <- tick_vals[keep]
  exponents <- exponents[keep]

  tick_text <- if (length(exponents) > 0) paste0("10<sup>", exponents, "</sup>") else NULL

  p |> plotly::layout(
    xaxis = list(
      title = "Fitnesswert GWP [kg CO<sub>2</sub>Ã¤/m<sup>2</sup>]",
      type  = "log",
      autorange = FALSE,
      range = log10(c(x_lo, x_hi)),
      tickmode = if (length(tick_vals) > 0) "array" else "auto",
      tickvals = if (length(tick_vals) > 0) tick_vals else NULL,
      ticktext = tick_text,
      showline   = TRUE,
      mirror     = TRUE
    )
  )
}

# ============================================================================
# SUBPLOT-RASTER UND SUBPLOT-LABELS
# ============================================================================

compute_subplot_grid <- function(n_items, max_cols = 3L) {
  n_items <- as.integer(n_items)
  max_cols <- as.integer(max_cols)

  if (!is.finite(n_items) || n_items <= 0) {
    return(list(nrows = 1L, ncols = 1L))
  }

  ncols <- min(max_cols, n_items)
  nrows <- ceiling(n_items / ncols)

  list(nrows = nrows, ncols = ncols)
}

build_subplot_annotations <- function(p, labels, font) {
  lay_tmp <- p$x$layout
  if (is.null(lay_tmp)) return(list())

  x_axes <- names(lay_tmp)[grepl("^xaxis", names(lay_tmp))]
  x_axes <- sort_plotly_axis_keys(x_axes, "xaxis")

  to_yaxis_key <- function(anchor) {
    if (is.null(anchor) || !nzchar(anchor) || identical(anchor, "y")) {
      "yaxis"
    } else {
      sub("^y", "yaxis", anchor)
    }
  }

  lapply(seq_along(labels), function(i) {
    ax_key <- if (i <= length(x_axes)) x_axes[i] else x_axes[length(x_axes)]
    y_key  <- to_yaxis_key(lay_tmp[[ax_key]]$anchor)

    x_dom <- lay_tmp[[ax_key]]$domain
    y_dom <- lay_tmp[[y_key]]$domain

    list(
      text      = labels[i],
      x         = if (length(x_dom) == 2) mean(x_dom) else 0.5,
      y         = if (length(y_dom) == 2) y_dom[2] + 0.002 else 0.95,
      xref      = "paper",
      yref      = "paper",
      xanchor   = "center",
      yanchor   = "bottom",
      showarrow = FALSE,
      font      = font
    )
  })
}

# ============================================================================
# STYLE-ABLEITUNG UND LAYOUT-ANWENDUNG
# ============================================================================

get_plot_output_dir <- function(cfg) {
  if (!is.null(cfg$plot_output_dir) && nzchar(trimws(as.character(cfg$plot_output_dir)))) {
    return(as.character(cfg$plot_output_dir))
  }
  file.path(dirname(cfg$logger_result_folder_path), "plot_exports")
}

resolve_style_profile <- function(plot_cfg, style_profile) {
  profiles <- plot_cfg$style_profiles
  base_cfg <- plot_cfg
  base_cfg$style_profiles <- NULL

  if (is.null(profiles) || !is.list(profiles) || is.null(profiles[[style_profile]])) {
    return(base_cfg)
  }

  utils::modifyList(base_cfg, profiles[[style_profile]])
}

scale_style_cfg <- function(plot_cfg, scale_factor) {
  sf <- as.numeric(scale_factor)
  if (!is.finite(sf) || sf <= 0) sf <- 1

  scaled <- plot_cfg
  scaled <- scale_numeric_fields(
    scaled,
    c(
      "font_size",
      "title_font_size",
      "axis_title_size",
      "axis_tick_size",
      "legend_font_size",
      "annotation_font_size",
      "annotation_axis_title_size",
      "annotation_subplot_size",
      "bar_text_size",
      "bar_mintext",
      "top_margin_title",
      "top_margin_no_title"
    ),
    sf
  )
  scaled
}

# Validiert die aufgeloeste Style-Konfiguration vor der Anwendung auf einen Plot.
# Prueft alle Felder, die von apply_plot_style() zwingend benoetigt werden.
# annotation_axis_title_size und annotation_subplot_size sind nur fuer IOH-basierte
# Profile relevant (base_type == "ioh"). Sie werden hier optional geprueft:
# fehlen sie bei einem IOH-Profil, gibt es eine Warnung statt einen Abbruch.
validate_style_cfg <- function(style_cfg) {
  required_numeric <- c(
    "font_size",
    "title_font_size",
    "axis_title_size",
    "axis_tick_size",
    "legend_font_size",
    "annotation_font_size",
    "top_margin_title",
    "top_margin_no_title",
    "bottom_margin",
    "left_margin",
    "right_margin",
    "png_font_scale",
    "html_font_scale"
  )

  missing <- required_numeric[!(required_numeric %in% names(style_cfg))]
  if (length(missing) > 0) {
    stop(sprintf("Style-Konfiguration unvollstaendig. Fehlende Felder: %s", paste(missing, collapse = ", ")))
  }

  invalid <- required_numeric[!vapply(required_numeric, function(k) {
    is.numeric(style_cfg[[k]]) && length(style_cfg[[k]]) == 1L && is.finite(style_cfg[[k]])
  }, logical(1))]

  if (length(invalid) > 0) {
    stop(sprintf("Style-Konfiguration enthaelt ungueltige numerische Felder: %s", paste(invalid, collapse = ", ")))
  }

  # Optionale numerische Felder: nur validieren wenn vorhanden (z.B. bar_text_size
  # und bar_mintext existieren nur in Balkenplot-Presets).
  optional_numeric <- c("bar_text_size", "bar_mintext")
  present_optional <- optional_numeric[optional_numeric %in% names(style_cfg)]
  invalid_optional <- present_optional[!vapply(present_optional, function(k) {
    is.numeric(style_cfg[[k]]) && length(style_cfg[[k]]) == 1L && is.finite(style_cfg[[k]])
  }, logical(1))]

  if (length(invalid_optional) > 0) {
    stop(sprintf("Style-Konfiguration enthaelt ungueltige optionale Felder: %s", paste(invalid_optional, collapse = ", ")))
  }

  # IOH-spezifische Felder: nur relevant wenn base_type == "ioh"
  if (identical(style_cfg$base_type, "ioh")) {
    ioh_fields <- c("annotation_axis_title_size", "annotation_subplot_size")
    missing_ioh <- ioh_fields[!(ioh_fields %in% names(style_cfg))]
    if (length(missing_ioh) > 0) {
      warning(sprintf(
        "IOH-Profil ohne Annotations-Groessen: %s. Fallback auf annotation_font_size.",
        paste(missing_ioh, collapse = ", ")
      ))
    }
  }

  invisible(TRUE)
}

resolve_final_style_cfg <- function(plot_cfg, style_profile = "native", output = c("html", "png"), verbose = NULL) {
  output <- match.arg(output)

  active_cfg <- resolve_style_profile(plot_cfg, style_profile)
  scale_factor <- if (identical(output, "png")) active_cfg$png_font_scale else active_cfg$html_font_scale
  final_cfg <- scale_style_cfg(active_cfg, scale_factor)

  validate_style_cfg(final_cfg)

  do_verbose <- if (is.null(verbose)) {
    isTRUE(plot_cfg$style_debug_print)
  } else {
    isTRUE(verbose)
  }

  if (isTRUE(do_verbose)) {
    cat(sprintf(
      "[STYLE] profile=%s output=%s font=%.1f axis_title=%.1f axis_tick=%.1f legend=%.1f margin(b/l/r)=%.0f/%.0f/%.0f\n",
      style_profile,
      output,
      final_cfg$font_size,
      final_cfg$axis_title_size,
      final_cfg$axis_tick_size,
      final_cfg$legend_font_size,
      final_cfg$bottom_margin,
      final_cfg$left_margin,
      final_cfg$right_margin
    ))
  }

  final_cfg
}

has_plot_title <- function(layout_cfg) {
  if (is.null(layout_cfg$title)) return(FALSE)

  if (is.character(layout_cfg$title)) {
    return(nzchar(trimws(layout_cfg$title)))
  }

  if (is.list(layout_cfg$title) && !is.null(layout_cfg$title$text)) {
    return(nzchar(trimws(as.character(layout_cfg$title$text))))
  }

  FALSE
}

apply_margin_style <- function(layout_cfg, style_cfg) {
  top_margin_title <- as_single_numeric_or_default(style_cfg$top_margin_title, 130)
  top_margin_no_title <- as_single_numeric_or_default(style_cfg$top_margin_no_title, 20)

  min_top_margin <- if (isTRUE(has_plot_title(layout_cfg))) top_margin_title else top_margin_no_title
  if (is.null(layout_cfg$margin)) {
    layout_cfg$margin <- list(
      t = min_top_margin,
      b = style_cfg$bottom_margin,
      l = style_cfg$left_margin,
      r = style_cfg$right_margin
    )
  }
  # Jede Seite erhaelt mindestens den Preset-Wert; bestehende groessere Werte bleiben erhalten.
  clamp_margin <- function(current, minimum) {
    if (is.null(current) || !is.finite(current) || current < minimum) minimum else current
  }
  layout_cfg$margin$t <- clamp_margin(layout_cfg$margin$t, min_top_margin)
  layout_cfg$margin$b <- clamp_margin(layout_cfg$margin$b, style_cfg$bottom_margin)
  layout_cfg$margin$l <- clamp_margin(layout_cfg$margin$l, style_cfg$left_margin)
  layout_cfg$margin$r <- clamp_margin(layout_cfg$margin$r, style_cfg$right_margin)

  layout_cfg
}

apply_title_style <- function(layout_cfg, style_cfg, base_font) {
  if (is.null(layout_cfg$title)) return(layout_cfg)

  if (is.character(layout_cfg$title)) layout_cfg$title <- list(text = layout_cfg$title)
  layout_cfg$title$font <- c(base_font, list(size = style_cfg$title_font_size))
  layout_cfg$title$pad <- list(t = 20, b = 0)
  if (is.null(layout_cfg$title$y) || !is.finite(layout_cfg$title$y)) layout_cfg$title$y <- 0.96
  if (is.null(layout_cfg$title$yanchor)) layout_cfg$title$yanchor <- "top"

  layout_cfg
}

apply_legend_style <- function(layout_cfg, style_cfg, base_font) {
  if (is.null(layout_cfg$legend)) return(layout_cfg)

  layout_cfg$legend$font <- c(base_font, list(size = style_cfg$legend_font_size))
  if (!is.null(layout_cfg$legend$title)) {
    layout_cfg$legend$title$font <- c(base_font, list(size = style_cfg$legend_font_size))
  }

  if (identical(layout_cfg$legend$orientation, "h")) {
    leg_y <- as_single_numeric_or_default(style_cfg$legend_y_offset, -0.30)
    layout_cfg$legend$y <- leg_y
    layout_cfg$legend$yanchor <- "top"
    if (is.null(layout_cfg$legend$x)) layout_cfg$legend$x <- 0.5
    if (is.null(layout_cfg$legend$xanchor)) layout_cfg$legend$xanchor <- "center"

    leg_base <- as_single_numeric_or_default(style_cfg$legend_bottom_base, 120)
    leg_mult <- as_single_numeric_or_default(style_cfg$legend_font_multiplier, 3.0)
    min_bottom_margin <- max(
      layout_cfg$margin$b,
      round(leg_base + style_cfg$axis_title_size + (leg_mult * style_cfg$legend_font_size))
    )
    layout_cfg$margin$b <- min_bottom_margin
  }

  layout_cfg
}

apply_axis_style <- function(axis_cfg, style_cfg, base_font) {
  if (is.null(axis_cfg)) return(axis_cfg)

  axis_cfg$tickfont <- c(base_font, list(size = style_cfg$axis_tick_size))
  axis_cfg$automargin <- TRUE

  if (is.character(axis_cfg$title)) {
    axis_cfg$title <- list(text = axis_cfg$title)
  }
  if (is.list(axis_cfg$title)) {
    axis_cfg$title$font <- c(base_font, list(size = style_cfg$axis_title_size))
    if (is.null(axis_cfg$title$standoff) || !is.finite(axis_cfg$title$standoff)) {
      axis_cfg$title$standoff <- max(8, round(style_cfg$axis_title_size * 0.9))
    }
  }

  axis_cfg
}

apply_all_axis_styles <- function(layout_cfg, style_cfg, base_font) {
  axis_keys <- names(layout_cfg)[grepl("^(xaxis|yaxis)[0-9]*$", names(layout_cfg))]
  for (key in axis_keys) {
    layout_cfg[[key]] <- apply_axis_style(layout_cfg[[key]], style_cfg, base_font)
  }
  layout_cfg
}

# Wendet das finale Style-Profil (Schriftgroessen, Margins, Annotationen) auf einen
# Plotly-Plot an.  Wird je einmal fuer HTML und einmal fuer PNG aufgerufen.
apply_plot_style <- function(p_in, style_cfg, plot_type = "native") {
  base_font <- list(family = style_cfg$font_family, color = style_cfg$font_color)
  p_out <- p_in |> plotly::layout(font = c(base_font, list(size = style_cfg$font_size)))

  # plotly_build() mergt ausstehende layoutAttrs nach $x$layout.
  # Noetig fuer native Plots (legend, title etc. aus layout()-Aufrufen).
  # IOH-Plots sind bereits gebaut - dort ueberspringen, weil plotly_build()
  # die globale font.size in alle Annotationen propagiert und unsere
  # gezielten Groessen (annotation_subplot_size etc.) ueberschreibt.
  # Proxy: layoutAttrs > 0: "Plot wurde noch nicht gebaut".
  needs_build <- length(p_out$x$layoutAttrs) > 0L
  if (needs_build) {
    p_out <- plotly::plotly_build(p_out)
  }

  layout_cfg <- p_out$x$layout
  if (!is.null(layout_cfg)) {
    layout_cfg <- apply_margin_style(layout_cfg, style_cfg)
    layout_cfg <- apply_all_axis_styles(layout_cfg, style_cfg, base_font)
    layout_cfg <- apply_title_style(layout_cfg, style_cfg, base_font)
    layout_cfg <- apply_legend_style(layout_cfg, style_cfg, base_font)
    layout_cfg$annotations <- apply_annotation_style(layout_cfg$annotations, style_cfg, plot_type = plot_type) # nolint: object_usage_linter.

    # Prozent-Labels in Balkenplots getrennt je Output skalieren (HTML vs. PNG).
    if (!is.null(style_cfg$bar_mintext) && is.finite(as.numeric(style_cfg$bar_mintext))) {
      if (is.null(layout_cfg$uniformtext) || !is.list(layout_cfg$uniformtext)) {
        layout_cfg$uniformtext <- list()
      }
      layout_cfg$uniformtext$minsize <- as.numeric(style_cfg$bar_mintext)
    }

    p_out$x$layout <- layout_cfg
  }

  if (!is.null(style_cfg$bar_text_size) && is.finite(as.numeric(style_cfg$bar_text_size)) &&
      !is.null(p_out$x$data) && length(p_out$x$data) > 0L) {
    bar_text_size <- as.numeric(style_cfg$bar_text_size)
    for (i in seq_along(p_out$x$data)) {
      trace_i <- p_out$x$data[[i]]
      if (!is.null(trace_i$type) && identical(as.character(trace_i$type), "bar")) {
        if (is.null(trace_i$textfont) || !is.list(trace_i$textfont)) {
          trace_i$textfont <- list()
        }
        trace_i$textfont$size <- bar_text_size
        p_out$x$data[[i]] <- trace_i
      }
    }
  }

  p_out
}

sanitize_plot_file_name <- function(file_name) {
  gsub("[^A-Za-z0-9_-]", "_", file_name)
}

# ---------------------------------------------------------------------------
# Kaleido-Backend: erzeugt PNG/PDF/SVG direkt aus plotly-JSON via Python-kaleido.
# Erfordert: reticulate + Python-kaleido (pip install kaleido).
# Gibt TRUE bei Erfolg zurueck, FALSE bei Fehler / fehlenden Abhaengigkeiten.
# ---------------------------------------------------------------------------
kaleido_available <- function() {
  requireNamespace("reticulate", quietly = TRUE) &&
    tryCatch({
      reticulate::py_module_available("kaleido")
    }, error = function(e) FALSE)
}

kaleido_export <- function(p, out_file, width = 1600, height = 1400, scale = 2) {
  if (!kaleido_available()) return(FALSE)

  json_str <- plotly::plotly_json(p, FALSE)
  out_path <- normalizePath(out_file, winslash = "/", mustWork = FALSE)

  # Plotly-JSON in Temp-Datei schreiben, damit Python den Pfad mit Forwardslashes liest.
  tmp_json <- tempfile(fileext = ".json", tmpdir = normalizePath(tempdir(), winslash = "/"))
  writeLines(json_str, tmp_json)
  tmp_json_fwd <- normalizePath(tmp_json, winslash = "/", mustWork = TRUE)

  tryCatch({
    reticulate::py_run_string(sprintf(
      "import kaleido, json, asyncio\nwith open('%s') as f:\n    fig = json.load(f)\nasyncio.run(kaleido.write_fig(fig, path='%s', opts={'width': %d, 'height': %d, 'scale': %d}))",
      tmp_json_fwd, out_path, as.integer(width), as.integer(height), as.integer(scale)
    ))
    file.exists(out_file)
  }, error = function(e) {
    warning(sprintf("Kaleido-Export fehlgeschlagen (%s): %s", basename(out_file), e$message))
    FALSE
  }, finally = {
    unlink(tmp_json)
  })
}

save_html_plot_file <- function(p_html, out_dir, safe_name, suppress_warning_fn) {
  out_file_html <- file.path(out_dir, paste0(safe_name, ".html"))
  suppress_warning_fn(htmlwidgets::saveWidget(p_html, out_file_html, selfcontained = FALSE))
  out_file_html
}

save_png_plot_file <- function(p_png, out_dir, safe_name, plot_cfg, suppress_warning_fn) {
  out_file_png <- file.path(out_dir, paste0(safe_name, ".png"))

  if (!requireNamespace("webshot2", quietly = TRUE)) {
    warning("PNG-Export uebersprungen: Paket 'webshot2' fehlt (install.packages('webshot2')).")
    return(out_file_png)
  }

  out_file_html_png <- file.path(out_dir, paste0(safe_name, "__png_render_tmp.html"))
  suppress_warning_fn(htmlwidgets::saveWidget(p_png, out_file_html_png, selfcontained = FALSE))

  html_abs <- normalizePath(out_file_html_png, winslash = "/", mustWork = TRUE)
  html_uri <- paste0("file:///", html_abs)

  invisible(utils::capture.output(suppressMessages(webshot2::webshot(
    url = html_uri,
    file = out_file_png,
    vwidth = as.integer(plot_cfg$png_width),
    vheight = as.integer(plot_cfg$png_height),
    zoom = as.numeric(plot_cfg$png_zoom),
    delay = as.numeric(plot_cfg$png_delay)
  ))))

  if (file.exists(out_file_html_png)) {
    unlink(out_file_html_png)
  }

  out_file_png
}

save_pdf_plot_file <- function(p_pdf, out_dir, safe_name, plot_cfg) {
  out_file_pdf <- file.path(out_dir, paste0(safe_name, ".pdf"))

  if (!kaleido_export(p_pdf, out_file_pdf,
                      width = plot_cfg$png_width, height = plot_cfg$png_height,
                      scale = plot_cfg$png_zoom)) {
    warning("PDF-Export uebersprungen: kaleido (reticulate + Python) nicht verfuegbar.")
  }

  out_file_pdf
}

save_plot_file <- function(p_html, p_png, cfg, file_name, plot_cfg, suppress_warning_fn) {
  out_dir <- get_plot_output_dir(cfg)
  dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

  safe_name <- sanitize_plot_file_name(file_name)

  out_file_html <- if (isTRUE(cfg$save_html)) {
    save_html_plot_file(p_html, out_dir, safe_name, suppress_warning_fn)
  }
  out_file_png <- if (isTRUE(cfg$save_png) && !is.null(p_png)) {
    save_png_plot_file(p_png, out_dir, safe_name, plot_cfg, suppress_warning_fn)
  }
  out_file_pdf <- if (isTRUE(cfg$save_pdf) && !is.null(p_png)) {
    save_pdf_plot_file(p_png, out_dir, safe_name, plot_cfg)
  }

  list(html = out_file_html, png = out_file_png, pdf = out_file_pdf)
}

# ============================================================================
# RENDERING / EXPORT
# ============================================================================

# Zentraler Einstiegspunkt fuer alle Benchmark-Plots.
# benchmark_plots.R ruft diese Funktion ueber render_benchmark_plot() auf.
#
# Ablauf (aufgeteilt in 3 Stufen):
#   build_render_config()  -> Plot-Konfig + Overrides zusammenfuehren
#   build_styled_plots()   -> HTML- und PNG-Plotly-Objekte erzeugen
#   render_styled_plot()   -> Orchestrator: drucken, speichern, Fehlerbehandlung
#
# Override-Hierarchie (spaetere Stufe gewinnt):
#   1. Preset-Basis        get_style_profiles() -> z.B. convergence_single
#   2. Font-Skalierung     html_font_scale / png_font_scale (automatisch je Output)
#   3. overrides$style     -> ueberschreibt HTML + PNG gleichzeitig
#   4. html$style           -> ueberschreibt nur HTML
#      png$style            -> ueberschreibt nur PNG
#
# Beispiel (nur an der Aufrufstelle in benchmark_plots.R):
#   render_benchmark_plot(p, cfg, "name", plot_type = "convergence_median",
#     overrides = list(style = list(legend_y_offset = -0.18)),
#     html = list(style = list(bottom_margin = 40)),
#     png  = list(style = list(bottom_margin = 60))
#   )

# Stufe 1: Plot-Konfiguration zusammenfuehren.
# Mergt globale Config, Preset-Export-Keys und uebergebene Overrides.
build_render_config <- function(cfg, plot_type, overrides = list(),
                                html = list(), png = list()) {
  plot_cfg <- resolve_plot_cfg(cfg,
    export_overrides = if (length(overrides$export) > 0L) overrides$export else list())

  # Export-Keys (png_width/height/zoom/delay) aus dem aktiven Profil uebernehmen
  active_profile <- plot_cfg$style_profiles[[plot_type]]
  if (is.null(active_profile)) {
    warning(sprintf(
      "Unbekannter plot_type '%s'. Verfuegbar: %s. Fallback auf Basis-Stil.",
      plot_type, paste(names(plot_cfg$style_profiles), collapse = ", ")))
  }
  if (!is.null(active_profile)) {
    export_keys <- intersect(names(active_profile), c("png_width", "png_height", "png_zoom", "png_delay"))
    if (length(export_keys) > 0L) {
      plot_cfg[export_keys] <- active_profile[export_keys]
    }
  }

  if (length(overrides$config) > 0L) {
    plot_cfg <- utils::modifyList(plot_cfg, overrides$config)
  }

  list(plot_cfg = plot_cfg, html = html, png = png, overrides = overrides)
}

# Stufe 2: HTML- und optional PNG-Plotly-Objekte erzeugen.
# Wendet Profil-Skalierung, Validierung und Style auf das Roh-Plot-Objekt an.
build_styled_plots <- function(plot_obj, render_cfg, plot_type, cfg, file_name = NULL) {
  plot_cfg  <- render_cfg$plot_cfg
  html      <- render_cfg$html
  png       <- render_cfg$png
  overrides <- render_cfg$overrides

  html_plot_cfg <- if (length(html$config) > 0L) {
    utils::modifyList(plot_cfg, html$config)
  } else {
    plot_cfg
  }

  html_cfg <- resolve_final_style_cfg(html_plot_cfg, style_profile = plot_type, output = "html")

  needs_png <- isTRUE(cfg$save_png) && !is.null(file_name)
  png_cfg <- if (isTRUE(needs_png)) {
    png_plot_cfg <- if (length(png$config) > 0L) {
      utils::modifyList(plot_cfg, png$config)
    } else {
      plot_cfg
    }
    resolve_final_style_cfg(png_plot_cfg, style_profile = plot_type, output = "png")
  } else {
    NULL
  }

  # Per-Plot-Overrides: ueberschreiben die Profil-Defaults direkt.
  if (length(overrides$style) > 0L) {
    html_cfg <- utils::modifyList(html_cfg, overrides$style)
    if (isTRUE(needs_png)) png_cfg <- utils::modifyList(png_cfg, overrides$style)
  }
  if (length(html$style) > 0L) {
    html_cfg <- utils::modifyList(html_cfg, html$style)
  }
  if (isTRUE(needs_png) && length(png$style) > 0L) {
    png_cfg <- utils::modifyList(png_cfg, png$style)
  }

  # Annotation-Basistyp (native/ioh) aus dem Profil ableiten
  base_type <- if (!is.null(html_cfg$base_type)) html_cfg$base_type else "native"
  ioh_html_mode <- normalize_ioh_html_mode(plot_cfg)
  is_ioh_preview_mode <- identical(base_type, "ioh") && identical(ioh_html_mode, "raw_minimal")

  p_html <- if (isTRUE(is_ioh_preview_mode)) {
    apply_ioh_raw_minimal_cleanup(plot_obj)
  } else {
    suppress_plotly_linetype_warnings(
      apply_plot_style(plot_obj, html_cfg, plot_type = base_type)
    )
  }
  p_png <- if (isTRUE(needs_png)) {
    png_base <- if (!is.null(png_cfg$base_type)) png_cfg$base_type else "native"
    suppress_plotly_linetype_warnings(
      apply_plot_style(plot_obj, png_cfg, plot_type = png_base)
    )
  } else {
    NULL
  }

  list(
    html = p_html,
    png = p_png,
    plot_cfg = plot_cfg,
    is_ioh_preview_mode = is_ioh_preview_mode
  )
}

# Stufe 3: Orchestrator - druckt den HTML-Plot und speichert HTML/PNG bei Bedarf.
render_styled_plot <- function(plot_obj, cfg, file_name = NULL,
                     plot_type = c("native", "ioh",
                                   "convergence_multi", "convergence_single",
                                   "convergence_median", "violin",
                                   "ecdf",
                                   "quality_bar_grouped", "quality_bar_aggregated"),
                     overrides = list(),
                     html = list(),
                     png = list()) {
  plot_type <- match.arg(plot_type)

  render_cfg   <- build_render_config(cfg, plot_type, overrides, html, png)
  styled_plots <- build_styled_plots(plot_obj, render_cfg, plot_type, cfg, file_name)

  if (isTRUE(styled_plots$is_ioh_preview_mode) &&
      !isTRUE(.ioh_render_state$preview_hint_shown)) {
    cat("[Hinweis] IOH-Preview aktiv (raw_minimal): HTML reduziert, PNG bleibt feingetunt.\n")
    .ioh_render_state$preview_hint_shown <- TRUE
  }

  suppress_plotly_linetype_warnings(print(styled_plots$html))

  if ((isTRUE(cfg$save_html) || isTRUE(cfg$save_png) || isTRUE(cfg$save_pdf)) && !is.null(file_name)) {
    tryCatch(
      {
        save_plot_file(
          styled_plots$html, styled_plots$png, cfg, file_name,
          styled_plots$plot_cfg, suppress_plotly_linetype_warnings
        )
        cat(sprintf("[Gespeichert] %s\n", sanitize_plot_file_name(file_name)))
      },
      error = function(e) {
        warning(sprintf(
          "Plot konnte nicht gespeichert werden (%s): %s",
          file_name,
          e$message
        ))
      }
    )
  }

  invisible(styled_plots$html)
}