# AG666 Agent Watcher System

## Konzept

Das Ziel dieses Systems ist es, DevOps/Server-Automatisierung so einfach zu machen, dass jeder – auch ohne tiefes Linux- oder Docker-Wissen – komplexe Projekte per YAML, OpenDevin-Agent oder mit Claude/MCP deployen, überwachen und pflegen kann.

**Kernidee:**
Du hast einen (Root-)Server, auf dem ein sogenannter Agent Watcher läuft. Dieser überwacht einen bestimmten Ordner auf YAML-„Instructions". Sobald dort neue Anweisungen (z.B. „deploy project X", „starte Container Y", „setze ENV-Variable…") abgelegt werden, verarbeitet der Agent sie automatisch. Das ist wie ein „Automatisierungs-Gateway" für deine Server, egal ob für Deployment, Monitoring, Self-Healing oder Maintenance.

Das Ganze ist cloud-agnostisch, d.h. läuft auf jedem Linux-Server (z.B. Hetzner, DigitalOcean, AWS, lokal), solange Docker unterstützt wird.

Optional kannst du das System mit OpenDevin oder Claude/MCP in Cursor kombinieren, um per natürlicher Sprache Anweisungen zu erzeugen, Infrastruktur zu scannen und neue Deployments zu steuern.

## Systemübersicht

### Ordnerstruktur

- `/ag666/instructions` – Hier legst du YAML-Dateien mit Automatisierungs-Tasks ab.
- `/ag666/results` – Hier landen die Ergebnisse (Logs, Status, Outputs).
- `/ag666/logs` – (Optional) Für zusätzliche Logfiles des Agenten.

### agent_watcher.py

- Python-Script, das dauerhaft im Hintergrund läuft
- Überwacht instructions und verarbeitet neue YAML-Dateien automatisch
- Verhindert Doppelverarbeitung per Lock-Mechanismus
- Ergebnisse und Fehler werden sauber geloggt

### OpenDevin

- (Optional) OpenDevin ist ein KI-gestütztes DevOps/Agenten-Framework
- Kann Anweisungen, Skripte oder komplette Deployment-YAMLs generieren
- Du kannst OpenDevin lokal laufen lassen oder remote einbinden
- Alternativ: Nutzung von Claude (via Cursor MCP) zur Orchestrierung und Steuerung

### Deine Automatisierungs-Tasks

Alles, was du per Bash, Docker, Git, etc. erledigen würdest, kann in YAML beschrieben und automatisch ausgeführt werden:

- Docker-Container bauen/hochfahren
- docker-compose nutzen
- Domains/Subdomains über Reverse Proxy freischalten (Traefik/Nginx)
- ENV-Files ausrollen
- Datenbank-Backups, Monitoring, uvm.

## Schnellstart: Agent Watcher installieren

### 1. Python & Abhängigkeiten installieren

```bash
sudo apt update
sudo apt install python3 python3-pip
pip3 install pyyaml
```

### 2. Ordnerstruktur anlegen

```bash
sudo mkdir -p /ag666/instructions /ag666/results /ag666/logs
sudo chown -R <dein_user>:<dein_user> /ag666
```

### 3. Agent Watcher Script kopieren

agent_watcher.py auf den Server legen, z.B. nach `/ag666/`

Ausführbar machen:
```bash
chmod +x /ag666/agent_watcher.py
```

### 4. Agent Watcher starten

```bash
cd /ag666
python3 agent_watcher.py
```

Der Agent läuft jetzt und wartet auf YAML-Dateien im instructions-Ordner.

### 5. Eine Test-Instruktion ausführen

Lege z.B. eine Datei `test.yaml` in `/ag666/instructions` ab:

```yaml
test: hello
```

Der Agent verarbeitet die Datei automatisch und legt das Ergebnis in `/ag666/results` ab.

## Typische Workflows

**Automatisiertes Deployment:**
YAML-Instruktion für den Bau und Start eines neuen Docker-Containers einwerfen (z.B. für neue Versionen deines Projekts).

**Maintenance:**
YAML-Befehl für Backups, Log-Rotation, Updates, etc.

**Self-Service für Teams:**
Kollegen geben YAML-Tasks vor, die dann zentral ausgeführt werden.

**KI-gestützte Steuerung:**
OpenDevin oder Claude generieren aus „plain English" die nötigen YAMLs und legen sie direkt im instructions-Ordner ab.

## Beispiel: Deployment eines Projekts

```yaml
task: Deploy HRthis Backend & Frontend
steps:
  - name: Git Pull Backend
    run: git -C /root/-hrthis-deployment/browo-hrthis-backend pull
  - name: Docker Compose Build
    run: docker-compose -f /root/-hrthis-deployment/docker-compose.production.yml up -d --build
  - name: Check Traefik Status
    run: docker ps | grep traefik
  - name: HTTP Check Frontend
    run: curl -I https://hrthis.kibubot.com
  - name: HTTP Check Backend
    run: curl -I https://hrthis-api.kibubot.com
```

Das ist natürlich nur ein sehr einfaches Beispiel – alles, was du bashen kannst, kannst du so abbilden!

## Features

- 🔍 Kontinuierliche Überwachung des Verzeichnisses `/ag666/instructions`
- 🔒 Lock-Mechanismus verhindert Mehrfachverarbeitung durch Umbenennung in `.lock`
- 📄 Automatisches Parsen und Verarbeiten von YAML-Dateien
- 📊 Ergebnisse werden als YAML in `/ag666/results` gespeichert
- 🛡️ Robuste Fehlerbehandlung - Script läuft auch bei fehlerhaften Dateien weiter
- 📝 Detaillierte Logs mit Timestamps

## Sicherheit & Hinweise

⚠️ Der Agent führt alles aus, was in YAML im instructions-Ordner landet – Zugriff sollte also nur für vertrauenswürdige User/Agenten erlaubt sein!

Die Idee ist, wiederholbare, dokumentierte DevOps/Automatisierungen zu ermöglichen, ohne sich im Detail mit jedem Tool auskennen zu müssen.

## Erweiterungen & Roadmap

- Weiterentwicklung Richtung ChatOps/VoiceOps möglich (z.B. Integration mit Slack, Telegram, Discord)
- Einbindung von Monitoring, Healthchecks und Self-Healing via Agent denkbar
- Kompatibel mit jedem modernen CI/CD-Prozess

## Viel Spaß beim Automatisieren!

Fragen, Bugs oder Erweiterungswünsche gerne via Issue oder direkt an den Maintainer.