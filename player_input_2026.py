
import os
import base64
import subprocess
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st
from datetime import datetime, date

st.set_page_config(page_title="Spieler Eingaben 2026", layout="wide")

CSV_FILE = "Spieler_Preferences_2026.csv"
REPO_DIR = Path(__file__).resolve().parent
CSV_PATH = REPO_DIR / CSV_FILE
DATE_START = date(2026, 1, 1)
DATE_END = date(2026, 4, 26)

def load_data():
    try:
        df = pd.read_csv(CSV_PATH, dtype=str)
        # Handle legacy column names for compatibility
        if "BlockedSingles" in df.columns and "BlockedDays" not in df.columns:
            df["BlockedDays"] = df["BlockedSingles"]

        # Normalize data formats for compatibility
        if "AvailableDays" in df.columns:
            # Convert comma-separated to semicolon-separated
            df["AvailableDays"] = df["AvailableDays"].str.replace(",", ";")

        if "Preference" in df.columns:
            # Normalize preference capitalization
            df["Preference"] = df["Preference"].str.replace("Nur Einzel", "nur Einzel")
            df["Preference"] = df["Preference"].str.replace("Nur Doppel", "nur Doppel")

        return df
    except FileNotFoundError:
        return pd.DataFrame(columns=[
            "Spieler","ValidFrom","ValidTo","AvailableDays","Preference",
            "BlockedRanges","BlockedDays","Notes","Timestamp"
        ])

def save_data(df):
    df.to_csv(CSV_PATH, index=False)


def _get_streamlit_secret(key, default=""):
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        # st.secrets is only available in Streamlit Cloud / deployed apps
        pass
    return default


def _get_local_git_branch():
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_DIR), "rev-parse", "--abbrev-ref", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        branch = result.stdout.strip()
        if branch and branch != "HEAD":
            return branch
    except Exception:
        pass
    return ""


def get_github_defaults():
    repo = (
        _get_streamlit_secret("GITHUB_REPO")
        or os.getenv("GITHUB_REPOSITORY")
        or os.getenv("GITHUB_REPO")
        or ""
    )
    branch = (
        _get_streamlit_secret("GITHUB_BRANCH")
        or os.getenv("GITHUB_BRANCH")
        or os.getenv("GIT_BRANCH")
        or _get_local_git_branch()
        or "main"
    )
    token = (
        _get_streamlit_secret("GITHUB_TOKEN")
        or os.getenv("GITHUB_TOKEN")
        or os.getenv("GH_TOKEN")
        or ""
    )
    path = CSV_FILE  # Always use Spieler_Preferences_2026.csv for this script
    committer_name = (
        _get_streamlit_secret("GITHUB_COMMITTER_NAME")
        or os.getenv("GITHUB_COMMITTER_NAME")
        or ""
    )
    committer_email = (
        _get_streamlit_secret("GITHUB_COMMITTER_EMAIL")
        or os.getenv("GITHUB_COMMITTER_EMAIL")
        or ""
    )

    return {
        "repo": repo,
        "branch": branch,
        "token": token,
        "path": path,
        "committer_name": committer_name,
        "committer_email": committer_email,
    }


def build_github_headers(token):
    # Strip whitespace from token to avoid authentication errors
    token = (token or "").strip()
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _normalize_github_path(path: str) -> str:
    """Return a GitHub API compatible path without leading slashes."""
    path = (path or "").strip()
    # Remove leading slashes/backslashes to avoid // in API URL
    path = path.lstrip("/\\")
    if not path:
        return CSV_FILE
    # Percent-encode special characters but keep sub-directory slashes
    return quote(path, safe="/")


def fetch_repo_default_branch(repo: str, token: str = "") -> str:
    """Return the default branch of a GitHub repository if available."""
    if not repo:
        return ""

    headers = build_github_headers(token) if token else {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        resp = requests.get(
            f"https://api.github.com/repos/{repo}",
            headers=headers,
            timeout=10,
        )
    except requests.RequestException:
        return ""

    if resp.status_code != 200:
        return ""

    try:
        return resp.json().get("default_branch", "") or ""
    except ValueError:
        return ""


def resolve_target_branch(branch: str, repo: str, token: str):
    """Return a branch name, resolving to repo default if missing."""
    steps = []
    branch = (branch or "").strip()
    if branch:
        return branch, steps

    default_branch = fetch_repo_default_branch(repo, token)
    if default_branch:
        steps.append(f"ℹ️ Kein Branch angegeben – verwende Standard-Branch '{default_branch}'.")
        return default_branch, steps

    fallback_branch = "main"
    steps.append(
        "⚠️ Kein Branch angegeben und Standard-Branch konnte nicht ermittelt werden – "
        "verwende 'main'."
    )
    return fallback_branch, steps


def update_github_file_via_api(
    token,
    repo,
    path,
    content_bytes,
    message,
    branch="main",
    committer=None,
    author=None,
):
    """Create or update a file in the GitHub repository using the REST API."""
    # Validate token before making API call
    token = (token or "").strip()
    if not token:
        return False, ["❌ Fehler: GITHUB_TOKEN ist nicht konfiguriert. Bitte Token in Streamlit Cloud Secrets hinzufügen."]

    # Check if token format looks valid
    if not (token.startswith("ghp_") or token.startswith("github_pat_") or token.startswith("gho_")):
        return False, [
            "❌ Fehler: GITHUB_TOKEN hat ungültiges Format.",
            f"   Token beginnt mit: '{token[:4]}...'",
            "   Erwartet: Token sollte mit 'ghp_' (classic), 'github_pat_' (fine-grained), oder 'gho_' beginnen."
        ]

    headers = build_github_headers(token)
    normalized_path = _normalize_github_path(path)
    base_url = f"https://api.github.com/repos/{repo}/contents/{normalized_path}"
    params = {"ref": branch} if branch else {}
    steps = []

    try:
        get_resp = requests.get(base_url, headers=headers, params=params, timeout=10)
    except requests.RequestException as exc:
        return False, [f"GET {base_url} fehlgeschlagen: {exc}"]

    sha = None
    if get_resp.status_code == 200:
        try:
            sha = get_resp.json().get("sha")
        except ValueError:
            return False, [f"Ungültige Antwort beim Lesen der bestehenden Datei: {get_resp.text}"]
        steps.append(f"✅ Aktuelle Datei gefunden (SHA {sha[:7] if sha else 'unbekannt'})")
    elif get_resp.status_code == 404:
        steps.append("ℹ️ Datei existiert noch nicht – sie wird neu erstellt.")
    elif get_resp.status_code == 401:
        error_message = get_resp.text
        try:
            error_message = get_resp.json().get("message", error_message)
        except ValueError:
            pass
        return False, [
            f"❌ GET {base_url} -> {get_resp.status_code}: {error_message}",
            "",
            "🔑 Das bedeutet: Der GitHub Token ist ungültig oder abgelaufen.",
            "",
            "✅ So beheben Sie das Problem:",
            "1. Gehen Sie zu Streamlit Cloud: https://share.streamlit.io/",
            "2. Öffnen Sie die App-Einstellungen (⋮ Menü → Settings)",
            "3. Klicken Sie auf 'Secrets'",
            "4. Erstellen Sie einen neuen GitHub Token: https://github.com/settings/tokens",
            "   - Token Type: Classic",
            "   - Scopes: Wählen Sie 'repo'",
            "5. Fügen Sie den Token zu den Secrets hinzu:",
            '   GITHUB_TOKEN = "ghp_ihr_neuer_token_hier"',
            "",
            f"📋 Aktueller Token beginnt mit: '{token[:8]}...' (Länge: {len(token)} Zeichen)"
        ]
    else:
        error_message = get_resp.text
        try:
            error_message = get_resp.json().get("message", error_message)
        except ValueError:
            pass
        return False, [f"GET {base_url} -> {get_resp.status_code}: {error_message}"]

    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("utf-8"),
    }
    if branch:
        payload["branch"] = branch
    if sha:
        payload["sha"] = sha
    if committer and committer.get("name") and committer.get("email"):
        payload["committer"] = {
            "name": committer["name"],
            "email": committer["email"],
        }
    if author and author.get("name") and author.get("email"):
        payload["author"] = {
            "name": author["name"],
            "email": author["email"],
        }

    try:
        put_resp = requests.put(base_url, headers=headers, json=payload, timeout=10)
    except requests.RequestException as exc:
        return False, steps + [f"PUT {base_url} fehlgeschlagen: {exc}"]

    if put_resp.status_code in (200, 201):
        steps.append(f"✅ Datei erfolgreich über die GitHub API aktualisiert ({put_resp.status_code}).")
        return True, steps

    error_message = put_resp.text
    try:
        error_message = put_resp.json().get("message", error_message)
    except ValueError:
        pass

    if put_resp.status_code == 401:
        steps.append(f"❌ PUT {base_url} -> {put_resp.status_code}: {error_message}")
        steps.append("")
        steps.append("🔑 Der GitHub Token ist ungültig, abgelaufen oder hat keine Schreibberechtigung.")
        steps.append("   Bitte erstellen Sie einen neuen Token mit 'repo' Berechtigung.")
    else:
        steps.append(f"❌ PUT {base_url} -> {put_resp.status_code}: {error_message}")

    return False, steps

def parse_blocked_ranges_from_csv(blocked_ranges_str):
    """Parse BlockedRanges from CSV format: '2026-01-03→2026-01-10;2026-02-15→2026-02-20'"""
    ranges = []
    if not blocked_ranges_str or pd.isna(blocked_ranges_str):
        return ranges

    for range_str in str(blocked_ranges_str).split(";"):
        range_str = range_str.strip()
        if not range_str or "→" not in range_str:
            continue
        try:
            parts = range_str.split("→")
            if len(parts) == 2:
                v = pd.to_datetime(parts[0].strip()).date()
                b = pd.to_datetime(parts[1].strip()).date()
                if v > b:
                    v, b = b, v
                ranges.append((v, b))
        except:
            pass
    return ranges

st.title("🎾 Spieler Eingaben Winter 2026")

df_all = load_data()

# Extract player list, filtering out empty/whitespace entries
all_players = [p.strip() for p in df_all["Spieler"].dropna().astype(str).unique() if str(p).strip()]
all_players = sorted(all_players)

sel_mode = st.radio("Spieler auswählen oder neu eingeben", ["Vorhandener Spieler","Neuer Spieler"])

if sel_mode == "Vorhandener Spieler":
    if all_players:
        sel_player = st.selectbox("Spieler", all_players)
    else:
        st.warning("Keine vorhandenen Spieler gefunden. Bitte 'Neuer Spieler' wählen.")
        sel_player = ""
else:
    sel_player = st.text_input("Neuer Spielername").strip()

if not sel_player:
    st.warning("Bitte Spieler auswählen oder neuen Namen eingeben.")
    st.stop()

# Track player changes to reload data
if "current_player" not in st.session_state or st.session_state["current_player"] != sel_player:
    st.session_state["current_player"] = sel_player
    st.session_state.pop("blocked_ranges_list", None)  # Reset ranges when player changes
    st.session_state.pop("blocked_days_list", None)  # Reset days when player changes

existing = df_all[df_all["Spieler"]==sel_player]
if not existing.empty:
    prev = existing.iloc[-1]
    st.info("Vorherige Eingaben geladen – können bearbeitet werden.")
else:
    prev = {}

# Initialize blocked_ranges_list from previous data
if "blocked_ranges_list" not in st.session_state:
    # Load from previous entry if exists
    prev_ranges = parse_blocked_ranges_from_csv(prev.get("BlockedRanges", ""))
    st.session_state["blocked_ranges_list"] = prev_ranges if prev_ranges else []

# Initialize blocked_days_list from previous data
if "blocked_days_list" not in st.session_state:
    # Load from previous entry if exists
    prev_days = []
    if prev.get("BlockedDays"):
        try:
            parsed_days = [pd.to_datetime(d.strip()).date() for d in str(prev.get("BlockedDays")).split(";") if d.strip()]
            # Filter to only include dates within valid range
            prev_days = [d for d in parsed_days if DATE_START <= d <= DATE_END]
        except:
            pass
    st.session_state["blocked_days_list"] = prev_days if prev_days else []

st.subheader("Urlaub / Abwesenheit")
st.caption("📅 Wähle Zeiträume im Kalender aus")

# Display existing date ranges and allow removal
if st.session_state["blocked_ranges_list"]:
    st.write("**Gewählte Zeiträume:**")
    ranges_to_remove = []
    for i, (start, end) in enumerate(st.session_state["blocked_ranges_list"]):
        col1, col2 = st.columns([4, 1])
        with col1:
            st.write(f"{i+1}. {start.strftime('%d.%m.%Y')} bis {end.strftime('%d.%m.%Y')}")
        with col2:
            if st.button("❌", key=f"remove_{i}"):
                ranges_to_remove.append(i)

    # Remove marked ranges
    for i in sorted(ranges_to_remove, reverse=True):
        st.session_state["blocked_ranges_list"].pop(i)
        st.rerun()

# Add new date range
st.write("**Neuen Zeitraum hinzufügen:**")
st.caption("ℹ️ Wähle Start- und Enddatum im Kalender aus, dann auf '➕ Zeitraum hinzufügen' klicken")
today = date.today()
default_date = today if DATE_START <= today <= DATE_END else DATE_START
new_range = st.date_input(
    "Wähle Start- und Enddatum",
    value=(default_date, default_date),
    min_value=DATE_START,
    max_value=DATE_END,
    key="new_range_input"
)

if st.button("➕ Zeitraum hinzufügen"):
    if isinstance(new_range, tuple) and len(new_range) == 2:
        start_date, end_date = new_range
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        st.session_state["blocked_ranges_list"].append((start_date, end_date))
        st.success(f"Zeitraum {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')} hinzugefügt!")
        st.rerun()
    else:
        st.warning("Bitte wähle sowohl Start- als auch Enddatum aus.")

blocked_ranges = st.session_state["blocked_ranges_list"]

# Single blocked days
st.write("**Einzelne Tage blockieren:**")

# Display existing blocked days and allow removal
if st.session_state["blocked_days_list"]:
    st.write("Gewählte Tage:")
    days_to_remove = []
    for i, day in enumerate(sorted(st.session_state["blocked_days_list"])):
        col1, col2 = st.columns([4, 1])
        with col1:
            st.write(f"{i+1}. {day.strftime('%d.%m.%Y (%A)')}")
        with col2:
            if st.button("❌", key=f"remove_day_{i}"):
                days_to_remove.append(day)

    # Remove marked days
    for day in days_to_remove:
        st.session_state["blocked_days_list"].remove(day)
        st.rerun()

# Add new single day
st.caption("ℹ️ Wähle ein Datum im Kalender aus, dann auf '➕ Tag hinzufügen' klicken")
new_day = st.date_input(
    "Wähle einen einzelnen Tag",
    value=default_date,
    min_value=DATE_START,
    max_value=DATE_END,
    key="new_day_input"
)

if st.button("➕ Tag hinzufügen"):
    if new_day:
        if new_day not in st.session_state["blocked_days_list"]:
            st.session_state["blocked_days_list"].append(new_day)
            st.success(f"Tag {new_day.strftime('%d.%m.%Y (%A)')} hinzugefügt!")
            st.rerun()
        else:
            st.warning("Dieser Tag ist bereits in der Liste.")
    else:
        st.warning("Bitte wähle ein Datum aus.")

blocked_days = st.session_state["blocked_days_list"]

st.subheader("Verfügbarkeit")
# Get previous available days and filter to valid options
valid_days = ["Montag","Mittwoch","Donnerstag"]
prev_avail_days = []
if prev.get("AvailableDays"):
    parsed_days = [d.strip() for d in prev.get("AvailableDays","").split(";") if d.strip()]
    prev_avail_days = [d for d in parsed_days if d in valid_days]

avail_days = st.multiselect(
    "Wochentage an denen du kannst",
    options=valid_days,
    default=prev_avail_days
)

pref_options = ["keine Präferenz","nur Einzel","nur Doppel"]
prev_pref = prev.get("Preference", "keine Präferenz")
# Get index safely, default to 0 if not found
try:
    pref_index = pref_options.index(prev_pref) if prev_pref in pref_options else 0
except ValueError:
    pref_index = 0

pref = st.radio(
    "Bevorzugt",
    pref_options,
    index=pref_index
)

notes = st.text_area("Zusätzliche Hinweise", value=prev.get("Notes",""))

github_defaults = get_github_defaults()

st.subheader("Zusammenfassung")
st.write(f"**Spieler:** {sel_player}")
st.write(
    "**Blockierte Zeiträume:**",
    ", ".join(
        [f"{v.strftime('%d.%m.%Y')} - {b.strftime('%d.%m.%Y')}" for v, b in blocked_ranges]
    )
    or "-",
)
st.write("**Blockierte Tage:**", ", ".join(d.strftime("%d.%m.%Y") for d in blocked_days) or "-")
st.write("**Verfügbarkeit:**", ", ".join(avail_days) or "-")
st.write("**Präferenz:**", pref)
st.write("**Hinweise:**", notes or "-")

default_commit_message = (
    f"Update Präferenzen für {sel_player}" if sel_player else "Update Spielerpräferenzen"
)

if st.button("✅ Bestätigen und Speichern"):
    new_row = pd.DataFrame([{
        "Spieler": sel_player,
        "ValidFrom": DATE_START.strftime("%Y-%m-%d"),
        "ValidTo": DATE_END.strftime("%Y-%m-%d"),
        "AvailableDays": ";".join(avail_days),
        "Preference": pref,
        "BlockedRanges": ";".join([f"{v.strftime('%Y-%m-%d')}→{b.strftime('%Y-%m-%d')}" for (v, b) in blocked_ranges]),
        "BlockedDays": ";".join(d.strftime("%Y-%m-%d") for d in blocked_days),
        "Notes": notes,
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }])
    df_all = pd.concat([df_all[df_all["Spieler"]!=sel_player], new_row], ignore_index=True)
    save_data(df_all)
    st.success("Gespeichert!")
    st.dataframe(df_all[df_all["Spieler"]==sel_player])

    repo_name = (github_defaults.get("repo") or "").strip()
    branch_name_input = (github_defaults.get("branch") or "")
    repo_path = (github_defaults.get("path") or CSV_FILE).strip() or CSV_FILE
    committer_name = (github_defaults.get("committer_name") or "").strip()
    committer_email = (github_defaults.get("committer_email") or "").strip()
    token_value = (github_defaults.get("token") or "").strip()

    committer_payload = None
    if committer_name and committer_email:
        committer_payload = {"name": committer_name, "email": committer_email}

    branch_name, branch_resolution_steps = resolve_target_branch(
        branch_name_input,
        repo_name,
        token_value,
    ) if repo_name else (branch_name_input.strip() or "main", [])

    if repo_name and token_value:
        csv_payload = df_all.to_csv(index=False).encode("utf-8")
        success, api_steps = update_github_file_via_api(
            token_value,
            repo_name,
            repo_path,
            csv_payload,
            default_commit_message,
            branch=branch_name,
            committer=committer_payload,
            author=committer_payload,
        )
        api_steps = branch_resolution_steps + api_steps
        if success:
            st.success("Änderungen wurden über die GitHub API gespeichert.")
        else:
            for step in api_steps:
                st.write(step)
            st.error("GitHub API-Aktualisierung fehlgeschlagen. Details siehe oben.")
    else:
        st.info("CSV gespeichert. GitHub wurde nicht aktualisiert, da Repository oder Token fehlen.")
