# Benchmarking von Optimierungsalgorithmen für Stahlbetondecken

Masterarbeit, TU Berlin, SoSe 2025/26

Dieses Repository enthält den vollständigen Code, die Ergebnisse und die Auswertungsskripte
zur Benchmarking-Studie von Optimierungsalgorithmen für die Bemessung von einachsig gespannten
Stahlbeton-Massivdecken nach EC2 (DIN EN 1992-1-1).
Dabei wurde das gesamte Python-Projekt bis auf die Integration der OPtimierungsalgorithmen bereitgestellt.
---

## Struktur

```
benchmarking_solid_conc_slab/
├── optimization/      # Python-Paket (slabdesignbench) + Experiment-Skripte
├── analysis/          # R-Projekt zur IOHanalyzer-Auswertung (inkl. renv)
├── results/           # Alle Ergebnisordner (logger, LHS, Querschnitte, Feasibility)
└── README.md
```

---

## 1 — Python-Umgebung einrichten

Voraussetzung: **Python 3.10–3.12** (empfohlen: 3.11)

```bash
# 1. Virtuelle Umgebung erstellen
python -m venv .venv

# 2. Aktivieren
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 3. Abhaengigkeiten installieren
pip install -r optimization/requirements.txt

# 4. Paket lokal installieren
cd optimization
pip install -e .
```

### Optimierung ausfuehren

```bash
cd optimization
python examples/run_penalized_demo.py
```

Algorithmus, Budget und Problemauswahl werden direkt im `main()`-Block
von `run_penalized_demo.py` konfiguriert (siehe Kommentare dort).

---

## 2 — R-Auswertung einrichten (IOHanalyzer)

Voraussetzung: **R 4.4.0** + RStudio (empfohlen)

Die vollstaendige Schritt-fuer-Schritt-Anleitung befindet sich in:

```
analysis/ANLEITUNG_SETUP.md
```

Kurzfassung:

```r
# 1. Arbeitsverzeichnis setzen (Pfad anpassen)
setwd("PFAD_ZUM_REPO/analysis/IOH_Analyzer")

# 2. renv aktivieren und Pakete installieren (einmalig)
source("renv/activate.R")
renv::restore()

# 3. Analyse starten
source("modular/main.R")
```

> **Hinweis:** In `modular/main.R` (Zeile 40) muss der Pfad zum
> gewuenschten `logger_results_*`-Ordner aus `results/` angepasst werden.

---

## 3 — Ergebnisse (Beispiele) 

| Ordner | Inhalt |
|---|---|
| 'results/logger_results_finale_Ausfuehrung_Start_260405/` | Finale Benchmark-Laeufe (alle Algorithmen) |
| 'results/logger_results_RBFOPT_vibr_true_gwp_n1000_primary_span_finale_Ausfuehrung_260405/` | RBFOpt-Laeufe mit GWP, n=1000 |
| 'results/logger_results_GA_DIRECT_vibr_true_gwp_n300_primary_span_only/` | GA + DIRECT, n=300 |
| 'results/logger_results_RBFOpt_Budget_setting_1500_eval/` | RBFOpt Budget-Einstellung 1500 |
| 'results/lhs_design_space_results_finale_Ausfuehrung_Start_260404/` | LHS Design-Space-Analyse |
| 'results/cross_section_plots_finale_Ausfuehrung_Start_260405/` | Querschnittsplots beste Loesungen |
| 'results/feasibility_outputs_20260415_213149_letzte_Ausfuehrung/` | Feasibility-Analyse |
| 'analysis/plot_exports/'|exzemplarische Auswertungsdiagramme fue die Konvergenzgeschwindigkeit | 
