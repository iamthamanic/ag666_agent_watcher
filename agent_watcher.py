#!/usr/bin/env python3
"""
Agent Watcher - Überwacht das Verzeichnis /ag666/instructions auf neue YAML-Dateien
und verarbeitet diese automatisch.
"""

import os
import time
import yaml
import traceback
from datetime import datetime
from pathlib import Path


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
        
        self.log(f"AgentWatcher gestartet - Überwache: {self.watch_dir}")
        self.log(f"Ergebnisse werden gespeichert in: {self.result_dir}")
    
    def log(self, message):
        """Gibt eine Log-Nachricht mit Timestamp aus."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")
    
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
        
        # YAML-Inhalt lesen und parsen
        try:
            with open(lock_file, 'r', encoding='utf-8') as f:
                content = yaml.safe_load(f)
            
            self.log(f"YAML-Inhalt von {yaml_file.name}:")
            print(f"  {content}")
            
            # Simuliere Verarbeitung
            self.log("Verarbeite Datei...")
            time.sleep(2)
            
            # Erstelle Ergebnis
            result = self.create_result(yaml_file.name, content, success=True)
            
            # Speichere Ergebnis
            self.save_result(yaml_file.stem, result)
            
        except yaml.YAMLError as e:
            self.log(f"Fehler beim Parsen der YAML-Datei {lock_file.name}: {e}")
            result = self.create_result(yaml_file.name, None, success=False, 
                                      error=f"YAML-Parse-Fehler: {str(e)}")
            self.save_result(yaml_file.stem, result)
        except Exception as e:
            self.log(f"Unerwarteter Fehler bei der Verarbeitung von {lock_file.name}: {e}")
            self.log(f"Traceback: {traceback.format_exc()}")
            result = self.create_result(yaml_file.name, None, success=False, 
                                      error=f"Verarbeitungsfehler: {str(e)}")
            self.save_result(yaml_file.stem, result)
    
    def create_result(self, filename, content, success=True, error=None):
        """
        Erstellt ein Ergebnis-Dictionary.
        
        Args:
            filename: Name der verarbeiteten Datei
            content: Inhalt der YAML-Datei (falls erfolgreich geparst)
            success: Ob die Verarbeitung erfolgreich war
            error: Fehlermeldung (falls vorhanden)
        
        Returns:
            Dictionary mit Ergebnisdaten
        """
        result = {
            'id': filename,
            'status': 'completed' if success else 'failed',
            'success': success,
            'summary': f"Datei {filename} erfolgreich verarbeitet" if success else f"Fehler bei {filename}: {error}",
            'timestamp': datetime.now().isoformat(),
        }
        
        if content and success:
            result['processed_content'] = {
                'original_keys': list(content.keys()) if isinstance(content, dict) else 'not_a_dict',
                'content_type': type(content).__name__
            }
        
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
        except Exception as e:
            self.log(f"Kritischer Fehler in der Hauptschleife: {e}")
            self.log(f"Traceback: {traceback.format_exc()}")
            raise


def main():
    """Hauptfunktion zum Starten des Agent Watchers."""
    print("=== Agent Watcher v1.0 ===")
    print("Drücke Ctrl+C zum Beenden\n")
    
    watcher = AgentWatcher()
    watcher.run()


if __name__ == "__main__":
    main()