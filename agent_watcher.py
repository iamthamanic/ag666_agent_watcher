#!/usr/bin/env python3
"""
AG666 Agent Watcher v3.0 - Automatisierte Task-Ausführung mit Telegram-Benachrichtigungen

Dieses Skript überwacht das Verzeichnis /ag666/instructions auf neue YAML-Dateien
und führt die darin definierten Aufgaben automatisch aus.

=== SYSTEMD SERVICE SETUP ===

1. Erstelle die Service-Datei: /etc/systemd/system/ag666-agent.service

[Unit]
Description=AG666 Agent Watcher Service
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/ag666
ExecStart=/usr/bin/python3 /ag666/agent_watcher.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ag666-agent
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target

2. Service aktivieren und starten:
   sudo systemctl daemon-reload
   sudo systemctl enable --now ag666-agent
   sudo systemctl status ag666-agent

3. Logs anschauen:
   sudo journalctl -u ag666-agent -f

=== TELEGRAM-BENACHRICHTIGUNGEN ===

Für Telegram-Benachrichtigungen benötigst du:
1. Einen Bot-Token von @BotFather in Telegram
2. Deine Chat-ID (erhältst du von @userinfobot)

Diese Werte müssen unten im Skript eingetragen werden:
- TELEGRAM_BOT_TOKEN = "dein-bot-token"
- TELEGRAM_CHAT_ID = "deine-chat-id"

Nach jeder Task-Ausführung wird automatisch eine Nachricht gesendet.

=== ERWEITERBARKEIT ===

Neue Aktionen können einfach hinzugefügt werden:
1. Neue Methode in TaskExecutor implementieren
2. Methode in self.action_registry eintragen
3. YAML-Beispiel in den Kommentaren dokumentieren

Beispiele für mögliche Erweiterungen:
- Nginx-Konfiguration ändern
- Cron-Jobs verwalten
- Pakete installieren/updaten
- Firewall-Regeln anpassen
"""

import os
import time
import yaml
import traceback
import subprocess
import shutil
import re
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from ruamel.yaml import YAML

# Telegram-Konfiguration
TELEGRAM_BOT_TOKEN = "7745997286:AAE-gFci7b7xhzsy_7VcUqt7M79KJjuN6CQ"
TELEGRAM_CHAT_ID = "5220247822"


class TelegramNotifier:
    """Klasse für Telegram-Benachrichtigungen"""
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    def send_message(self, text: str) -> bool:
        """Sendet eine Nachricht via Telegram"""
        try:
            data = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML"
            }
            response = requests.post(self.api_url, json=data, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"Fehler beim Senden an Telegram: {e}")
            return False


class TaskExecutor:
    """
    Klasse zur Ausführung verschiedener Task-Typen.
    Neue Task-Typen können hier als Methoden hinzugefügt werden.
    
    Beispiel für neuen Task-Typ:
    1. Implementiere neue Methode (z.B. manage_nginx_config)
    2. Füge sie zu self.action_registry hinzu
    3. Dokumentiere YAML-Format in den Kommentaren
    """
    
    def __init__(self, logger):
        self.logger = logger
        # Registry für verfügbare Aktionen
        # Schlüssel: Aktionsname, Wert: Methode
        self.action_registry = {
            'update_docker_compose_ports': self.update_docker_compose_ports,
            'run_command': self.run_command,
            'edit_file': self.edit_file,
            'copy_file': self.copy_file,
            'create_file': self.create_file,
            'delete_file': self.delete_file,
            'restart_docker_container': self.restart_docker_container,
        }
    
    def retry_operation(self, func, *args, max_retries=3, sleep_time=2, **kwargs):
        """
        Führt eine Operation mit Retry-Logik aus.
        
        Args:
            func: Die auszuführende Funktion
            max_retries: Maximale Anzahl von Versuchen
            sleep_time: Wartezeit zwischen Versuchen in Sekunden
        """
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except IOError as e:
                if attempt < max_retries - 1:
                    self.logger(f"IO-Fehler bei Versuch {attempt + 1}/{max_retries}: {e}")
                    self.logger(f"Warte {sleep_time} Sekunden vor erneutem Versuch...")
                    time.sleep(sleep_time)
                else:
                    raise
    
    def execute_task(self, task_content: Dict[str, Any]) -> Tuple[bool, str, List[str]]:
        """
        Führt einen Task basierend auf seinem Inhalt aus.
        
        Args:
            task_content: Das geparste YAML-Dictionary mit dem Task
            
        Returns:
            Tuple mit (success, summary, detailed_logs)
        """
        logs = []
        
        # Prüfe ob es ein strukturierter Task mit Aktionen ist
        if 'actions' in task_content:
            # Neues strukturiertes Format mit expliziten Aktionen
            return self._execute_structured_task(task_content, logs)
        
        # Legacy-Format: Versuche aus der Beschreibung zu erkennen, was zu tun ist
        if 'task' in task_content and 'steps' in task_content:
            return self._execute_legacy_task(task_content, logs)
        
        # Einfacher Befehl
        if 'command' in task_content:
            return self._execute_simple_command(task_content, logs)
        
        return False, "Unbekanntes Task-Format", logs
    
    def _execute_structured_task(self, task_content: Dict[str, Any], logs: List[str]) -> Tuple[bool, str, List[str]]:
        """
        Führt einen strukturierten Task mit expliziten Aktionen aus.
        
        Beispiel-Format:
        ```yaml
        task: "Update Traefik Ports"
        actions:
          - type: update_docker_compose_ports
            file: /root/-hrthis-deployment/docker-compose.deploy.yml
            service: traefik
            port_mappings:
              - "8081:80"
              - "8082:443"
        ```
        """
        task_name = task_content.get('task', 'Unbenannter Task')
        logs.append(f"Starte strukturierten Task: {task_name}")
        
        actions = task_content.get('actions', [])
        if not actions:
            return False, "Keine Aktionen definiert", logs
        
        all_success = True
        for i, action in enumerate(actions):
            action_type = action.get('type')
            if not action_type:
                logs.append(f"Aktion {i+1}: Kein Typ angegeben")
                all_success = False
                continue
            
            if action_type not in self.action_registry:
                logs.append(f"Aktion {i+1}: Unbekannter Aktionstyp '{action_type}'")
                all_success = False
                continue
            
            # Führe die Aktion aus
            try:
                logs.append(f"Aktion {i+1}: Führe '{action_type}' aus")
                action_method = self.action_registry[action_type]
                success, message = action_method(action)
                logs.append(f"  → {message}")
                if not success:
                    all_success = False
                    logs.append(f"  → Fehler bei Aktion {i+1}, breche ab")
                    break
            except Exception as e:
                logs.append(f"  → Fehler: {str(e)}")
                all_success = False
                break
        
        summary = f"Task '{task_name}' {'erfolgreich' if all_success else 'fehlgeschlagen'}"
        return all_success, summary, logs
    
    def _execute_legacy_task(self, task_content: Dict[str, Any], logs: List[str]) -> Tuple[bool, str, List[str]]:
        """
        Führt einen Task im Legacy-Format aus (mit Textbeschreibungen).
        Versucht aus den Beschreibungen zu erkennen, welche Aktionen auszuführen sind.
        """
        task_name = task_content.get('task', 'Unbenannter Task')
        steps = task_content.get('steps', [])
        
        logs.append(f"Starte Legacy-Task: {task_name}")
        
        # Analysiere die Steps und versuche zu erkennen, was zu tun ist
        # Beispiel: Erkenne "Passe die Ports im traefik-Service" als Port-Update
        if any('traefik' in str(step).lower() and 'port' in str(step).lower() for step in steps):
            # Extrahiere Dateiname aus den Steps
            file_match = re.search(r'(/[^\s]+docker-compose[^\s]+\.yml)', ' '.join(str(s) for s in steps))
            if file_match:
                filename = file_match.group(1)
                logs.append(f"Erkannt als Traefik-Port-Update für Datei: {filename}")
                
                # Erstelle strukturierte Aktion
                action = {
                    'file': filename,
                    'service': 'traefik',
                    'port_mappings': ['8081:80', '8082:443']  # Aus dem Beispiel
                }
                success, message = self.update_docker_compose_ports(action)
                logs.append(f"  → {message}")
                return success, f"Task '{task_name}' {'erfolgreich' if success else 'fehlgeschlagen'}", logs
        
        # Wenn wir den Task nicht interpretieren können
        logs.append("Legacy-Task konnte nicht automatisch interpretiert werden")
        return False, f"Task '{task_name}' konnte nicht interpretiert werden", logs
    
    def _execute_simple_command(self, task_content: Dict[str, Any], logs: List[str]) -> Tuple[bool, str, List[str]]:
        """Führt einen einfachen Shell-Befehl aus."""
        command = task_content.get('command')
        logs.append(f"Führe Befehl aus: {command}")
        
        action = {'command': command}
        success, message = self.run_command(action)
        logs.append(f"  → {message}")
        
        return success, f"Befehl {'erfolgreich' if success else 'fehlgeschlagen'}", logs
    
    # === Konkrete Aktionsmethoden ===
    
    def update_docker_compose_ports(self, action: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Aktualisiert Port-Mappings in einer docker-compose.yml Datei mit ruamel.yaml.
        
        Args:
            action: Dictionary mit:
                - file: Pfad zur docker-compose.yml
                - service: Name des Services (z.B. 'traefik')
                - port_mappings: Liste neuer Port-Mappings (z.B. ['8081:80', '8082:443'])
        """
        filename = action.get('file')
        service = action.get('service')
        new_ports = action.get('port_mappings', [])
        
        if not all([filename, service, new_ports]):
            return False, "Fehlende Parameter: file, service oder port_mappings"
        
        try:
            # Backup der Originaldatei
            backup_file = f"{filename}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.retry_operation(shutil.copy2, filename, backup_file)
            self.logger(f"Backup erstellt: {backup_file}")
            
            # Verwende ruamel.yaml für strukturerhaltende Änderungen
            yaml_handler = YAML()
            yaml_handler.preserve_quotes = True
            yaml_handler.indent(mapping=2, sequence=4, offset=2)
            
            # Lade die YAML-Datei
            with open(filename, 'r', encoding='utf-8') as f:
                data = yaml_handler.load(f)
            
            # Prüfe ob Service existiert
            if 'services' not in data:
                return False, "Keine 'services' Sektion in der Datei gefunden"
            
            if service not in data['services']:
                return False, f"Service '{service}' nicht gefunden"
            
            # Aktualisiere die Ports
            self.logger(f"Aktualisiere Ports für Service '{service}'")
            data['services'][service]['ports'] = new_ports
            self.logger(f"Neue Ports gesetzt: {new_ports}")
            
            # Schreibe die Datei zurück
            with open(filename, 'w', encoding='utf-8') as f:
                yaml_handler.dump(data, f)
            
            self.logger(f"Ports für Service '{service}' erfolgreich aktualisiert.")
            return True, f"Ports für Service '{service}' erfolgreich aktualisiert"
            
        except Exception as e:
            error_msg = f"Fehler beim Aktualisieren der Ports: {str(e)}"
            self.logger(f"FEHLER: {error_msg}")
            self.logger(f"Traceback: {traceback.format_exc()}")
            return False, error_msg
    
    def restart_docker_container(self, action: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Startet einen Docker-Container neu.
        
        Args:
            action: Dictionary mit:
                - container: Name des Containers (z.B. 'traefik')
                
        Beispiel YAML:
        ```yaml
        actions:
          - type: restart_docker_container
            container: traefik
        ```
        """
        container = action.get('container')
        
        if not container:
            return False, "Kein Container-Name angegeben"
        
        try:
            self.logger(f"Starte Docker-Container '{container}' neu...")
            
            # Führe docker restart aus
            result = subprocess.run(
                f"docker restart {container}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                self.logger(f"Container '{container}' erfolgreich neugestartet")
                return True, f"Container '{container}' erfolgreich neugestartet"
            else:
                error_msg = f"Fehler beim Neustart von Container '{container}': {result.stderr}"
                self.logger(f"FEHLER: {error_msg}")
                return False, error_msg
                
        except subprocess.TimeoutExpired:
            return False, f"Timeout beim Neustart von Container '{container}'"
        except Exception as e:
            return False, f"Fehler beim Neustart: {str(e)}"
    
    def run_command(self, action: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Führt einen Shell-Befehl aus.
        
        Args:
            action: Dictionary mit:
                - command: Der auszuführende Befehl
                - timeout: Optional, Timeout in Sekunden (default: 300)
        """
        command = action.get('command')
        timeout = action.get('timeout', 300)
        
        if not command:
            return False, "Kein Befehl angegeben"
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                return True, f"Befehl erfolgreich ausgeführt. Output: {result.stdout[:200]}..."
            else:
                return False, f"Befehl fehlgeschlagen. Fehler: {result.stderr[:200]}..."
                
        except subprocess.TimeoutExpired:
            return False, f"Befehl Timeout nach {timeout} Sekunden"
        except Exception as e:
            return False, f"Fehler beim Ausführen: {str(e)}"
    
    def edit_file(self, action: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Bearbeitet eine Datei durch Suchen und Ersetzen.
        
        Args:
            action: Dictionary mit:
                - file: Dateipfad
                - search: Suchtext oder Regex
                - replace: Ersetzungstext
                - regex: Optional, ob Regex verwendet werden soll (default: False)
        """
        filename = action.get('file')
        search = action.get('search')
        replace = action.get('replace')
        use_regex = action.get('regex', False)
        
        if not all([filename, search is not None, replace is not None]):
            return False, "Fehlende Parameter: file, search oder replace"
        
        try:
            # Backup
            backup_file = f"{filename}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            self.retry_operation(shutil.copy2, filename, backup_file)
            
            def edit_operation():
                with open(filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if use_regex:
                    new_content = re.sub(search, replace, content)
                else:
                    new_content = content.replace(search, replace)
                
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(new_content)
            
            self.retry_operation(edit_operation)
            
            return True, f"Datei {filename} erfolgreich bearbeitet"
            
        except Exception as e:
            return False, f"Fehler beim Bearbeiten: {str(e)}"
    
    def copy_file(self, action: Dict[str, Any]) -> Tuple[bool, str]:
        """Kopiert eine Datei."""
        source = action.get('source')
        destination = action.get('destination')
        
        if not all([source, destination]):
            return False, "Fehlende Parameter: source oder destination"
        
        try:
            self.retry_operation(shutil.copy2, source, destination)
            return True, f"Datei von {source} nach {destination} kopiert"
        except Exception as e:
            return False, f"Fehler beim Kopieren: {str(e)}"
    
    def create_file(self, action: Dict[str, Any]) -> Tuple[bool, str]:
        """Erstellt eine neue Datei mit Inhalt."""
        filename = action.get('file')
        content = action.get('content', '')
        
        if not filename:
            return False, "Kein Dateiname angegeben"
        
        try:
            def create_operation():
                Path(filename).parent.mkdir(parents=True, exist_ok=True)
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)
            
            self.retry_operation(create_operation)
            return True, f"Datei {filename} erstellt"
        except Exception as e:
            return False, f"Fehler beim Erstellen: {str(e)}"
    
    def delete_file(self, action: Dict[str, Any]) -> Tuple[bool, str]:
        """Löscht eine Datei (mit Backup)."""
        filename = action.get('file')
        
        if not filename:
            return False, "Kein Dateiname angegeben"
        
        try:
            if os.path.exists(filename):
                # Backup vor dem Löschen
                backup_file = f"{filename}.deleted.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                self.retry_operation(shutil.move, filename, backup_file)
                return True, f"Datei {filename} gelöscht (Backup: {backup_file})"
            else:
                return False, f"Datei {filename} existiert nicht"
        except Exception as e:
            return False, f"Fehler beim Löschen: {str(e)}"


class AgentWatcher:
    def __init__(self, watch_dir="/ag666/instructions", result_dir="/ag666/results", poll_interval=5):
        """
        Initialisiert den AgentWatcher.
        
        Args:
            watch_dir: Verzeichnis, das überwacht werden soll
            result_dir: Verzeichnis für die Ergebnisdateien
            poll_interval: Wartezeit zwischen Prüfungen in Sekunden
        """
        self.watch_dir = Path(watch_dir)
        self.result_dir = Path(result_dir)
        self.poll_interval = poll_interval
        
        # Verzeichnisse erstellen, falls sie nicht existieren
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.result_dir.mkdir(parents=True, exist_ok=True)
        
        # Task Executor initialisieren
        self.task_executor = TaskExecutor(self.log)
        
        # Telegram Notifier initialisieren
        self.telegram = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        
        self.log(f"AgentWatcher v3.0 gestartet - Überwache: {self.watch_dir}")
        self.log(f"Ergebnisse werden gespeichert in: {self.result_dir}")
        self.log(f"Verfügbare Aktionen: {', '.join(self.task_executor.action_registry.keys())}")
        
        # Teste Telegram-Verbindung
        if self.telegram.send_message("🚀 AG666 Agent Watcher gestartet!"):
            self.log("Telegram-Benachrichtigungen aktiviert")
        else:
            self.log("WARNUNG: Telegram-Benachrichtigungen nicht konfiguriert oder fehlerhaft")
    
    def log(self, message):
        """Gibt eine Log-Nachricht mit Timestamp aus."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")
    
    def send_task_notification(self, task_name: str, success: bool, summary: str, error: Optional[str] = None):
        """Sendet eine Telegram-Benachrichtigung über Task-Ausführung"""
        status_emoji = "✅" if success else "❌"
        status_text = "Erfolgreich" if success else "Fehlgeschlagen"
        
        message = f"<b>{status_emoji} Task-Ausführung</b>\n\n"
        message += f"<b>Task:</b> {task_name}\n"
        message += f"<b>Status:</b> {status_text}\n"
        message += f"<b>Zusammenfassung:</b> {summary}\n"
        
        if error:
            message += f"<b>Fehler:</b> <code>{error}</code>\n"
        
        message += f"\n<b>Zeit:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        self.telegram.send_message(message)
    
    def find_new_yaml_files(self):
        """
        Findet alle YAML-Dateien ohne entsprechende .lock-Datei.
        
        Returns:
            Liste von Path-Objekten für neue YAML-Dateien
        """
        try:
            yaml_files = list(self.watch_dir.glob("*.yaml"))
            new_files = []
            
            for yaml_file in yaml_files:
                lock_file = yaml_file.with_suffix(".lock")
                if not lock_file.exists():
                    new_files.append(yaml_file)
            
            return new_files
        except Exception as e:
            self.log(f"Fehler beim Suchen von YAML-Dateien: {e}")
            return []
    
    def process_yaml_file(self, yaml_file):
        """
        Verarbeitet eine einzelne YAML-Datei.
        
        Args:
            yaml_file: Path-Objekt der zu verarbeitenden YAML-Datei
        """
        self.log(f"Neue Datei gefunden: {yaml_file.name}")
        
        # Datei sofort in .lock umbenennen
        lock_file = yaml_file.with_suffix(".lock")
        try:
            yaml_file.rename(lock_file)
            self.log(f"Datei gesperrt: {yaml_file.name} -> {lock_file.name}")
        except Exception as e:
            self.log(f"Fehler beim Sperren der Datei {yaml_file.name}: {e}")
            return
        
        task_name = yaml_file.stem
        success = False
        summary = ""
        error_msg = None
        
        # YAML-Inhalt lesen und parsen
        try:
            with open(lock_file, 'r', encoding='utf-8') as f:
                content = yaml.safe_load(f)
            
            self.log(f"YAML-Inhalt von {yaml_file.name}:")
            print(f"  {content}")
            
            # Task-Name extrahieren
            if isinstance(content, dict) and 'task' in content:
                task_name = content['task']
            
            # Führe den Task aus
            self.log("Führe Task aus...")
            success, summary, execution_logs = self.task_executor.execute_task(content)
            
            # Erstelle detailliertes Ergebnis
            result = self.create_result(
                yaml_file.name, 
                content, 
                success=success, 
                summary=summary,
                execution_logs=execution_logs
            )
            
            # Speichere Ergebnis
            self.save_result(yaml_file.stem, result)
            
        except yaml.YAMLError as e:
            error_msg = f"YAML-Parse-Fehler: {str(e)}"
            self.log(f"Fehler beim Parsen der YAML-Datei {lock_file.name}: {e}")
            result = self.create_result(yaml_file.name, None, success=False, error=error_msg)
            self.save_result(yaml_file.stem, result)
            summary = "YAML-Parse-Fehler"
            
        except Exception as e:
            error_msg = f"Verarbeitungsfehler: {str(e)}"
            self.log(f"Unerwarteter Fehler bei der Verarbeitung von {lock_file.name}: {e}")
            self.log(f"Traceback: {traceback.format_exc()}")
            result = self.create_result(yaml_file.name, None, success=False, error=error_msg)
            self.save_result(yaml_file.stem, result)
            summary = "Unerwarteter Fehler"
            
            # Bei Fehler: Lock-Datei löschen für erneuten Versuch
            try:
                if lock_file.exists():
                    lock_file.unlink()
                    self.log(f"Lock-Datei {lock_file.name} gelöscht für erneuten Versuch")
            except Exception as del_e:
                self.log(f"Fehler beim Löschen der Lock-Datei: {del_e}")
        
        # Sende Telegram-Benachrichtigung
        self.send_task_notification(task_name, success, summary, error_msg)
    
    def create_result(self, filename, content, success=True, error=None, summary=None, execution_logs=None):
        """
        Erstellt ein Ergebnis-Dictionary.
        
        Args:
            filename: Name der verarbeiteten Datei
            content: Inhalt der YAML-Datei (falls erfolgreich geparst)
            success: Ob die Verarbeitung erfolgreich war
            error: Fehlermeldung (falls vorhanden)
            summary: Zusammenfassung der Ausführung
            execution_logs: Detaillierte Logs der Ausführung
        
        Returns:
            Dictionary mit Ergebnisdaten
        """
        result = {
            'id': filename,
            'status': 'completed' if success else 'failed',
            'success': success,
            'summary': summary or (f"Datei {filename} erfolgreich verarbeitet" if success else f"Fehler bei {filename}: {error}"),
            'timestamp': datetime.now().isoformat(),
        }
        
        if execution_logs:
            result['execution_logs'] = execution_logs
        
        if content and success:
            result['processed_content'] = {
                'original_task': content.get('task', 'Unbenannt'),
                'content_type': type(content).__name__
            }
        
        if error:
            result['error'] = error
        
        return result
    
    def save_result(self, base_filename, result):
        """
        Speichert das Ergebnis als YAML-Datei.
        
        Args:
            base_filename: Basis-Dateiname (ohne Erweiterung)
            result: Ergebnis-Dictionary
        """
        result_file = self.result_dir / f"{base_filename}.yaml"
        
        try:
            with open(result_file, 'w', encoding='utf-8') as f:
                yaml.dump(result, f, default_flow_style=False, allow_unicode=True)
            self.log(f"Ergebnis gespeichert: {result_file.name}")
        except Exception as e:
            self.log(f"Fehler beim Speichern des Ergebnisses für {base_filename}: {e}")
    
    def run(self):
        """Hauptschleife des Watchers."""
        self.log(f"Starte Überwachung... (Prüfung alle {self.poll_interval} Sekunden)")
        
        try:
            while True:
                # Nach neuen YAML-Dateien suchen
                new_files = self.find_new_yaml_files()
                
                if new_files:
                    self.log(f"{len(new_files)} neue Datei(en) gefunden")
                    for yaml_file in new_files:
                        self.process_yaml_file(yaml_file)
                
                # Warte bis zur nächsten Prüfung
                time.sleep(self.poll_interval)
                
        except KeyboardInterrupt:
            self.log("Überwachung durch Benutzer beendet")
            self.telegram.send_message("🛑 AG666 Agent Watcher beendet")
        except Exception as e:
            self.log(f"Kritischer Fehler in der Hauptschleife: {e}")
            self.log(f"Traceback: {traceback.format_exc()}")
            self.telegram.send_message(f"💥 AG666 Agent Watcher abgestürzt!\n\nFehler: {str(e)}")
            raise


def main():
    """Hauptfunktion zum Starten des Agent Watchers."""
    print("=== Agent Watcher v3.0 ===")
    print("NEU: Telegram-Benachrichtigungen & Docker-Container-Restart")
    print("Drücke Ctrl+C zum Beenden\n")
    
    watcher = AgentWatcher()
    watcher.run()


if __name__ == "__main__":
    main()