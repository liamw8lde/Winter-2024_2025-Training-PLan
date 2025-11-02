
import os
import subprocess
from pathlib import Path

import pandas as pd
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


def run_git_command(command, env=None):
    """Execute a git command within the repository directory."""
    try:
        result = subprocess.run(
            command,
            cwd=REPO_DIR,
            capture_output=True,
            text=True,
            check=True,
            env=None if env is None else {**os.environ, **env},
        )
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as exc:
        output = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        return False, output
    except FileNotFoundError as exc:
        return False, str(exc)


def has_csv_changes():
    success, output = run_git_command(["git", "status", "--porcelain", CSV_FILE])
    if not success:
        return None, output
    has_changes = any(line.strip() for line in output.splitlines())
    return has_changes, output


def commit_csv_changes(commit_message, env=None):
    """Stage the CSV file and create a commit."""
    outputs = []

    success, message = run_git_command(["git", "add", CSV_FILE])
    outputs.append((success, message))
    if not success:
        return False, outputs

    success, message = run_git_command(["git", "commit", "-m", commit_message], env=env)
    outputs.append((success, message))
    return success, outputs


def get_current_branch():
    success, output = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if success:
        return output.strip()
    return None


def get_git_identity():
    """Return configured git user name and email (empty strings if unset)."""
    name_success, name_out = run_git_command(["git", "config", "user.name"])
    email_success, email_out = run_git_command(["git", "config", "user.email"])

    name = name_out.strip() if name_success and name_out else ""
    email = email_out.strip() if email_success and email_out else ""
    return name, email


def set_git_identity(name, email):
    """Configure git user name and email locally for the repository."""
    outputs = []

    success, message = run_git_command(["git", "config", "user.name", name])
    outputs.append((success, message))
    if not success:
        return False, outputs

    success, message = run_git_command(["git", "config", "user.email", email])
    outputs.append((success, message))
    return success, outputs


def ensure_git_askpass_script():
    script_path = REPO_DIR / "git_askpass.sh"
    script_path.write_text("#!/bin/sh\nprintf '%s' \"$GITHUB_TOKEN\"\n", encoding="utf-8")
    script_path.chmod(0o700)
    return script_path


def push_csv_changes(remote="origin", branch=None):
    outputs = []
    if branch is None:
        branch = get_current_branch()
    if not branch:
        outputs.append((False, "Aktueller Git-Branch konnte nicht ermittelt werden."))
        return False, outputs

    push_env = {"GIT_TERMINAL_PROMPT": "0"}
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        script_path = ensure_git_askpass_script()
        push_env.update({
            "GIT_ASKPASS": str(script_path),
            "GITHUB_TOKEN": token,
        })

    success, message = run_git_command(["git", "push", remote, branch], env=push_env)
    outputs.append((success, message))
    return success, outputs

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
new_range = st.date_input(
    "Wähle Start- und Enddatum",
    value=(),
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
    value=None,
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

st.subheader("Git-Status")
st.caption("🔐 Beim Speichern wird automatisch ein Git-Commit erstellt und zu GitHub gepusht.")
is_git_repo = (REPO_DIR / ".git").exists()

if not is_git_repo:
    st.info(
        "Es wurde kein Git-Repository gefunden. Die Daten werden nur lokal gespeichert."
    )
else:
    current_name, current_email = get_git_identity()

    if "git_user_name" not in st.session_state:
        st.session_state["git_user_name"] = current_name or ""
    if "git_user_email" not in st.session_state:
        st.session_state["git_user_email"] = current_email or ""

    if current_name and current_email:
        st.success(f"Git-Identität erkannt: {current_name} <{current_email}>")
    else:
        st.warning(
            "Git-Benutzername oder E-Mail fehlen. Bitte unten ausfüllen, damit Commits funktionieren."
        )

    st.text_input(
        "Git-Benutzername",
        value=st.session_state.get("git_user_name", ""),
        key="git_user_name",
        help="Name, der in Git-Commits erscheinen soll."
    )
    st.text_input(
        "Git-E-Mail",
        value=st.session_state.get("git_user_email", ""),
        key="git_user_email",
        help="E-Mail-Adresse für Git-Commits.",
    )

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

    if is_git_repo:
        change_state, status_output = has_csv_changes()
        if change_state is None:
            st.error("Git-Status konnte nicht geprüft werden.")
            if status_output:
                st.code(status_output)
        elif change_state:
            identity_outputs = []
            resolved_name, resolved_email = get_git_identity()
            identity_success = bool(resolved_name and resolved_email)

            provided_name = st.session_state.get("git_user_name", "").strip()
            provided_email = st.session_state.get("git_user_email", "").strip()

            if not identity_success and provided_name and provided_email:
                identity_success, identity_outputs = set_git_identity(provided_name, provided_email)
                if identity_success:
                    resolved_name, resolved_email = provided_name, provided_email
                    st.session_state["git_user_name"] = provided_name
                    st.session_state["git_user_email"] = provided_email
            elif not identity_success:
                st.error("Bitte Git-Benutzername und E-Mail angeben, um Commits zu erstellen.")

            for idx, (step_success, message) in enumerate(identity_outputs, start=1):
                status = "✅" if step_success else "❌"
                if message:
                    st.write(f"{status} Git-Konfiguration:")
                    st.code(message)
                else:
                    st.write(f"{status} Git-Konfigurationsschritt {idx} ausgeführt.")

            if not identity_success:
                st.info("CSV gespeichert, aber Git-Commit wurde übersprungen.")
            else:
                commit_env = {
                    "GIT_AUTHOR_NAME": resolved_name,
                    "GIT_AUTHOR_EMAIL": resolved_email,
                    "GIT_COMMITTER_NAME": resolved_name,
                    "GIT_COMMITTER_EMAIL": resolved_email,
                }

                commit_success, commit_outputs = commit_csv_changes(default_commit_message, env=commit_env)
                for idx, (step_success, message) in enumerate(commit_outputs, start=1):
                    status = "✅" if step_success else "❌"
                    if message:
                        st.write(f"{status} Git-Ausgabe:")
                        st.code(message)
                    else:
                        st.write(f"{status} Befehl {idx} ausgeführt.")

                if commit_success:
                    push_success, push_outputs = push_csv_changes()
                    for push_success_single, message in push_outputs:
                        status = "✅" if push_success_single else "❌"
                        if message:
                            st.write(f"{status} Git Push:")
                            st.code(message)
                        else:
                            st.write(f"{status} Push ausgeführt.")
                    if push_success:
                        st.success("Änderungen wurden committet und zu GitHub gepusht.")
                    else:
                        st.error("Commit erstellt, aber Push nach GitHub ist fehlgeschlagen.")
                else:
                    st.error("Git-Commit fehlgeschlagen. Siehe Ausgaben oben für Details.")
        else:
            st.info("Keine Änderungen für Git erkannt.")
    else:
        st.info("CSV gespeichert. Kein Git-Commit ausgeführt, da kein Repository erkannt wurde.")
