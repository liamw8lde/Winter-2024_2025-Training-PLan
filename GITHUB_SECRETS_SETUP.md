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

### ✅ "No secrets found" → Datei wurde nicht gefunden
**Lösung:** Prüfe den Dateipfad:
- `C:\users\mount\documents\Winter-2024_2025-Training-PLan\.streamlit\secrets.toml`
- Versteckte Dateien im Explorer anzeigen lassen

### ❌ "401 Bad credentials" → Token ist ungültig
**Mögliche Ursachen:**

1. **Token hat nicht die richtige Berechtigung**
   - Gehe zu https://github.com/settings/tokens
   - Klicke auf dein Token
   - Stelle sicher, dass **"repo"** angehakt ist ✓
   - Wenn nicht: Lösche das Token und erstelle ein neues

2. **Token wurde falsch kopiert**
   - Öffne `secrets.toml`
   - Prüfe die Zeile: `GITHUB_TOKEN = "ghp_..."`
   - **Richtig:** `GITHUB_TOKEN = "ghp_abc123XYZ"`
   - **Falsch:** `GITHUB_TOKEN = " ghp_abc123XYZ "` (Leerzeichen)
   - **Falsch:** `GITHUB_TOKEN = ghp_abc123XYZ` (keine Anführungszeichen)
   - **Falsch:** Mehrere Zeilen oder Zeilenumbrüche

3. **Token-Typ ist falsch**
   - Verwende **"Personal access tokens (classic)"**, NICHT "Fine-grained tokens"
   - Classic Tokens beginnen mit `ghp_`
   - Bei https://github.com/settings/tokens auf "Tokens (classic)" klicken

4. **Token ist abgelaufen**
   - GitHub Tokens können ein Ablaufdatum haben
   - Lösche das alte Token und erstelle ein neues

### Token neu erstellen (Schritt für Schritt)

1. Gehe zu: https://github.com/settings/tokens
2. Klicke auf **"Tokens (classic)"** (oben in der Leiste)
3. Klicke **"Generate new token"** → **"Generate new token (classic)"**
4. **Note:** "Tennis Plan App"
5. **Expiration:** Wähle "No expiration" oder ein Datum in der Zukunft
6. **Scopes:** Hake **nur "repo"** an (alle Unterpunkte werden automatisch angehakt)
7. Scrolle nach unten, klicke **"Generate token"**
8. **SOFORT kopieren!** Du siehst es nur einmal
9. Öffne `.streamlit\secrets.toml`
10. Ersetze die Zeile:
    ```toml
    GITHUB_TOKEN = "dein_neues_token_hier_einfügen"
    ```
11. Speichern und Streamlit neu starten

### Testen des Tokens (Optional)

Du kannst dein Token in der Kommandozeile testen:
```bash
curl -H "Authorization: Bearer ghp_deinToken" https://api.github.com/user
```
Wenn das Token funktioniert, siehst du deine GitHub-Benutzerinfos.

### Weiterhin Fehler?
- Prüfe, ob der Repository-Name korrekt ist: `liamw8lde/Winter-2024_2025-Training-PLan`
- Stelle sicher, dass du Zugriff auf das Repository hast
- Prüfe, ob der Branch existiert
