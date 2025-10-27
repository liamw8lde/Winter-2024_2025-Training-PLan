
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

def parse_ranges(ranges_df):
    clean = []
    for _, r in ranges_df.iterrows():
        if not r["von"] or not r["bis"]:
            continue
        try:
            v = pd.to_datetime(r["von"]).date()
            b = pd.to_datetime(r["bis"]).date()
            if v > b:
                v, b = b, v
            clean.append((v, b))
        except:
            pass
    return clean

st.title("🎾 Spieler Eingaben Winter 2026")

df_all = load_data()

# Extract player list, filtering out empty/whitespace entries
all_players = [p.strip() for p in df_all["Spieler"].dropna().astype(str).unique() if str(p).strip()]
all_players = sorted(all_players)

# Debug info (can be removed later)
if all_players:
    st.sidebar.success(f"✓ {len(all_players)} Spieler gefunden")
    st.sidebar.write("Spieler:", ", ".join(all_players))
else:
    st.sidebar.warning("Keine Spieler gefunden")
    st.sidebar.write(f"CSV geladen: {len(df_all)} Zeilen")
    if not df_all.empty:
        st.sidebar.write("Erste Zeile Spieler-Spalte:", df_all["Spieler"].iloc[0] if len(df_all) > 0 else "leer")

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

existing = df_all[df_all["Spieler"]==sel_player]
if not existing.empty:
    prev = existing.iloc[-1]
    st.info("Vorherige Eingaben geladen – können bearbeitet werden.")
else:
    prev = {}

st.subheader("Urlaub / Abwesenheit")
st.caption("• Datumsspannen als Tabelle  • Einzeltage als Mehrfachauswahl")

if "ranges_df" not in st.session_state:
    st.session_state["ranges_df"] = pd.DataFrame(columns=["von","bis"])
ranges_df = st.data_editor(
    st.session_state["ranges_df"],
    num_rows="dynamic",
    column_config={"von":"Von (YYYY-MM-DD)","bis":"Bis (YYYY-MM-DD)"}
)
blocked_ranges = parse_ranges(ranges_df)

blocked_days = st.multiselect(
    "Einzeltage blockieren",
    options=pd.date_range(DATE_START, DATE_END).date,
    default=[],
    format_func=lambda d: d.strftime("%Y-%m-%d")
)

st.subheader("Verfügbarkeit")
avail_days = st.multiselect(
    "Wochentage an denen du kannst",
    options=["Montag","Mittwoch","Donnerstag"],
    default=prev.get("AvailableDays","").split(";") if prev.get("AvailableDays") else []
)

pref = st.radio(
    "Bevorzugt",
    ["keine Präferenz","nur Einzel","nur Doppel"],
    index=["keine Präferenz","nur Einzel","nur Doppel"].index(prev.get("Preference","keine Präferenz")) if prev.get("Preference") else 0
)

notes = st.text_area("Zusätzliche Hinweise", value=prev.get("Notes",""))

st.subheader("Zusammenfassung")
st.write(f"**Spieler:** {sel_player}")
st.write("**Blockierte Zeiträume:**", ", ".join([f"{v}→{b}" for v,b in blocked_ranges]) or "-")
st.write("**Blockierte Tage:**", ", ".join(d.strftime("%Y-%m-%d") for d in blocked_days) or "-")
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
