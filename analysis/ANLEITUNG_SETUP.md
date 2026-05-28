# Anleitung: R-Projekt einrichten und starten

Erstellt von Tala Ramadan im Rahmen der Masterarbeit  
Stand: 10.05.2026

---

## Voraussetzungen

- R Version 4.4.0 (https://cran.r-project.org/)
- RStudio (empfohlen, https://posit.co/download/rstudio-desktop/)
- Python 3 (https://www.python.org/downloads/) — nur für PDF-Export benötigt

---

## Schritt 1 — Ergebnisordner anpassen

Öffne die Datei `IOH_Analyzer/modular/main.R` und passe Zeile 40 an:

```r
logger_result_folder_path = "C:/DEIN/PFAD/logger_results_finale_Ausfuehrung_Start_260405",
```

Ersetze `C:/DEIN/PFAD/` durch den Pfad, wo der Ordner  
`logger_results_finale_Ausfuehrung_Start_260405` auf deinem Rechner liegt.

---

## Schritt 2 — renv aktivieren und Pakete installieren

Öffne R oder RStudio und führe folgende Befehle **der Reihe nach** aus:

```r
# 1. Ins Projektverzeichnis wechseln (Pfad anpassen)
setwd("C:/DEIN/PFAD/260510_R-Projekt_vollstaendig/IOH_Analyzer")

# 2. renv aktivieren
source("renv/activate.R")

# 3. Alle benötigten Pakete installieren (einmalig, kann einige Minuten dauern)
renv::restore()
```

Wenn gefragt wird ob das Projekt aktiviert werden soll → **Y eingeben** und Enter drücken.

---

## Schritt 3 — Analyse starten

```r
# Hauptskript ausführen
source("modular/main.R")
```

Die Plots werden automatisch in einen Unterordner `plot_exports/` gespeichert,  
der neben dem `IOH_Analyzer`-Ordner erstellt wird.

---

## Schritt 4 — kaleido installieren (nur für PDF-Export)

PDF-Export erfordert das Python-Paket `kaleido`. Dieser Schritt ist nur notwendig, 
wenn `save_pdf = TRUE` in `main.R` gesetzt wird.

**4a** — Python-Paket installieren (in der Kommandozeile / Terminal, nicht in R):

```bash
pip install kaleido
```

**4b** — Python-Pfad in R verknüpfen (einmalig in R ausführen):

```r
library(reticulate)
# Prüfen ob kaleido verfügbar ist:
py_module_available("kaleido")   # sollte TRUE zurückgeben
```

Falls `FALSE`: Python-Installation angeben:

```r
use_python("C:/Users/DEIN_NAME/AppData/Local/Programs/Python/Python3xx/python.exe")
```

---

## Hinweise

- `renv::restore()` muss nur **einmalig** ausgeführt werden.
- Bei Problemen mit der Paketinstallation: `renv::status()` zeigt fehlende Pakete an.
- PNG- und PDF-Export sind standardmäßig deaktiviert (`save_png = FALSE`, `save_pdf = FALSE`).  
  Zum Aktivieren in `main.R` auf `TRUE` setzen.
- Eine detaillierte Beschreibung der Architektur findet sich in  
  `IOH_Analyzer/IOH_ANALYZER_STRUCTURE_ANALYSIS.md`.
