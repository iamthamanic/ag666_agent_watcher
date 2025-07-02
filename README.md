# AG666 Agent Watcher

Ein robustes Python-Script zur automatischen Überwachung und Verarbeitung von YAML-Dateien.

## Features

- 🔍 Kontinuierliche Überwachung des Verzeichnisses `/ag666/instructions`
- 🔒 Lock-Mechanismus verhindert Mehrfachverarbeitung durch Umbenennung in `.lock`
- 📄 Automatisches Parsen und Verarbeiten von YAML-Dateien
- 📊 Ergebnisse werden als YAML in `/ag666/results` gespeichert
- 🛡️ Robuste Fehlerbehandlung - Script läuft auch bei fehlerhaften Dateien weiter
- 📝 Detaillierte Logs mit Timestamps

## Installation

```bash
pip install pyyaml
```

## Verwendung

```bash
python3 agent_watcher.py
```

Das Script erstellt die benötigten Verzeichnisse automatisch beim ersten Start.

## Workflow

1. YAML-Datei in `/ag666/instructions` ablegen
2. Script erkennt neue Datei und benennt sie sofort in `.lock` um
3. Datei wird geparst und verarbeitet
4. Ergebnis wird in `/ag666/results` mit gleichem Namen gespeichert

## Ergebnis-Format

Jede Ergebnisdatei enthält:
- `id`: Dateiname
- `status`: completed/failed
- `success`: true/false
- `summary`: Zusammenfassung der Verarbeitung
- `timestamp`: Zeitstempel der Verarbeitung