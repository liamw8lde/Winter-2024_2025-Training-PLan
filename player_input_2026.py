
import streamlit as st
import pandas as pd
from datetime import datetime, date

st.set_page_config(page_title="Spieler Eingaben 2026", layout="wide")

CSV_FILE = "player_inputs_2026.csv"
DATE_START = date(2026, 1, 1)
DATE_END = date(2026, 4, 26)

def load_data():
    try:
        return pd.read_csv(CSV_FILE, dtype=str)
    except FileNotFoundError:
        return pd.DataFrame(columns=[
            "Spieler","BlockedRanges","BlockedDays","AvailableDays",
            "Preference","Notes","Timestamp"
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

all_players = sorted(df_all["Spieler"].dropna().unique().tolist())
sel_mode = st.radio("Spieler auswählen oder neu eingeben", ["Vorhandener Spieler","Neuer Spieler"])

if sel_mode == "Vorhandener Spieler" and all_players:
    sel_player = st.selectbox("Spieler", all_players)
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
        "BlockedRanges": ";".join([f"{v.strftime('%Y-%m-%d')}→{b.strftime('%Y-%m-%d')}" for (v, b) in blocked_ranges]),
        "BlockedDays": ";".join(d.strftime("%Y-%m-%d") for d in blocked_days),
        "AvailableDays": ";".join(avail_days),
        "Preference": pref,
        "Notes": notes,
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }])
    df_all = df_all[df_all["Spieler"]!=sel_player].append(new_row, ignore_index=True)
    save_data(df_all)
    st.success("Gespeichert!")
    st.dataframe(df_all[df_all["Spieler"]==sel_player])
