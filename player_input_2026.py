
import streamlit as st
import pandas as pd
from datetime import datetime, date

st.set_page_config(page_title="Spieler Eingaben 2026", layout="wide")

CSV_FILE = "Spieler_Preferences_2026.csv"
DATE_START = date(2026, 1, 1)
DATE_END = date(2026, 4, 26)

def load_data():
    try:
        df = pd.read_csv(CSV_FILE, dtype=str)
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
    df.to_csv(CSV_FILE, index=False)

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

st.subheader("Zusammenfassung")
st.write(f"**Spieler:** {sel_player}")
st.write("**Blockierte Zeiträume:**", ", ".join([f"{v.strftime('%d.%m.%Y')} - {b.strftime('%d.%m.%Y')}" for v,b in blocked_ranges]) or "-")
st.write("**Blockierte Tage:**", ", ".join(d.strftime("%d.%m.%Y") for d in blocked_days) or "-")
st.write("**Verfügbarkeit:**", ", ".join(avail_days) or "-")
st.write("**Präferenz:**", pref)
st.write("**Hinweise:**", notes or "-")

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
