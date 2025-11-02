# GitHub Secrets Setup für Windows

## Problem
Der Fehler "No secrets found" bedeutet, dass Streamlit die GitHub-Zugangsdaten nicht finden kann.

## Lösung

### Schritt 1: GitHub Personal Access Token erstellen

1. Gehe zu: https://github.com/settings/tokens
2. Klicke auf **"Generate new token"** → **"Generate new token (classic)"**
3. Gib dem Token einen Namen, z.B. "Tennis Plan App"
4. Wähle die Berechtigung **"repo"** (Full control of private repositories)
5. Klicke auf **"Generate token"**
6. **WICHTIG:** Kopiere das Token SOFORT - du kannst es später nicht mehr sehen!

### Schritt 2: secrets.toml Datei bearbeiten

Die Datei `.streamlit/secrets.toml` wurde bereits im Projekt erstellt.

**Auf Windows:**
1. Öffne den Ordner `Winter-2024_2025-Training-PLan` im Explorer
2. Öffne den Unterordner `.streamlit`
3. Öffne die Datei `secrets.toml` mit Notepad oder einem Editor
4. Ersetze `your_github_personal_access_token_here` mit deinem echten Token

**Beispiel - Vorher:**
```toml
GITHUB_TOKEN = "your_github_personal_access_token_here"
GITHUB_REPO = "liamw8lde/Winter-2024_2025-Training-PLan"
GITHUB_BRANCH = "claude/autopopulate-training-plan-011CUZABKzQJ2UH9qQ3S5Syv"
```

**Beispiel - Nachher:**
```toml
GITHUB_TOKEN = "ghp_abc123XYZ789beispieltoken456DEF"
GITHUB_REPO = "liamw8lde/Winter-2024_2025-Training-PLan"
GITHUB_BRANCH = "claude/autopopulate-training-plan-011CUZABKzQJ2UH9qQ3S5Syv"
```

### Schritt 3: Streamlit App neu starten

1. Stoppe die laufende Streamlit App (Strg+C im Terminal)
2. Starte sie neu:
   ```bash
   streamlit run autopopulate_2026_app.py
   ```

### Schritt 4: Testen

1. Öffne die App im Browser
2. Generiere eine Vorschau mit Auto-Population
3. Klicke auf **"💾 Auf GitHub speichern (2026)"**
4. Du solltest nun die Erfolgsmeldung sehen!

## Sicherheit

⚠️ **WICHTIG:** Die `secrets.toml` Datei ist bereits in `.gitignore` eingetragen und wird NICHT zu GitHub hochgeladen. Dein Token bleibt privat!

## Fehlerbehebung

### Token funktioniert nicht?
- Stelle sicher, dass das Token die "repo" Berechtigung hat
- Token darf keine Leerzeichen enthalten
- Token muss in Anführungszeichen stehen

### Datei nicht gefunden?
- Versteckte Dateien im Explorer anzeigen lassen
- Oder verwende einen Code-Editor (VS Code, Notepad++) der `.streamlit` Ordner sieht

### Weiterhin Fehler?
- Prüfe, ob du dich im richtigen Projektordner befindest
- Stelle sicher, dass der Ordnername korrekt ist: `Winter-2024_2025-Training-PLan`
