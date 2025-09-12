# streamlit_app.py
# Viewer-only app for the winter training plan:
# - Tabs: Weekly plan, single player, complete plan, player costs
# - Robust loader: prefers "Spielplan" sheet, falls back to grid "Herren 40–50–60"
# - Hard-wired GitHub RAW URL with optional override in sidebar

import io
import re
import unicodedata
import requests
from collections import defaultdict
from datetime import date

import pandas as pd
import streamlit as st
from dateutil import tz

st.set_page_config(page_title="🎾 Winter-Training Plan", layout="wide")

# ---------- config ----------
# Hard-wired RAW link (lowercase repo path to match your deployment)
GH_RAW_DEFAULT = "https://raw.githubusercontent.com/liamw8lde/winter-2024_2025-training-plan/main/trainplan.xlsx"

# ---------- helpers ----------
SLOT_RE = re.compile(r"^([DE])(\d{2}):(\d{2})-([0-9]+)\s+PL([AB])$", re.IGNORECASE)

def norm(s):
    s = str(s or "").strip()
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    return re.sub(r"\s+"," ",s)

def parse_slot(code):
    """D20:00-120 PLA -> {'kind':'D','hh':20,'mm':0,'mins':120,'court':'A'}"""
    m = SLOT_RE.match(str(code or ""))
    if not m:
        return None
    return {
        "kind": m.group(1).upper(),
        "hh": int(m.group(2)),
        "mm": int(m.group(3)),
        "mins": int(m.group(4)),
        "court": m.group(5).upper(),  # 'A' or 'B' from PLA/PLB
    }

def slot_time_str(code):
    p = parse_slot(code)
    return f"{p['hh']:02d}:{p['mm']:02d}" if p else "?"

def minutes_of(code):
    p = parse_slot(code)
    return p["mins"] if p else 0

@st.cache_data(show_spinner=False)
def load_plan_from_url(url: str) -> pd.DataFrame:
    """Load plan as a normalized dataframe with columns:
       Date (datetime.date), Day, Slot, Typ, Players (string), PlayerList (list[str])"""
    r = requests.get(url)
    if r.status_code != 200:
        raise ValueError(f"Couldn't fetch plan (HTTP {r.status_code}). Check the RAW URL and that the file exists on 'main'.")
    data = r.content
    # Excel .xlsx (zip) usually starts with 'PK'
    if not data.startswith(b"PK"):
        raise ValueError("Downloaded file isn’t an .xlsx (likely an HTML page / 404). Use the RAW link from GitHub.")

    # Prefer "Spielplan"
    try:
        df = pd.read_excel(io.BytesIO(data), sheet_name="Spielplan")
        # Flexible header rename
        cols_low = {c.lower(): c for c in df.columns}
        def pick(*names):
            for n in names:
                if n in cols_low: return cols_low[n]
            return None

        c_date = pick("datum","date")
        c_day  = pick("tag","day")
        c_slot = pick("slot")
        c_typ  = pick("typ","art")
        c_play = pick("spieler","players")

        if not all([c_date, c_day, c_slot, c_play]):
            raise ValueError("Spielplan sheet missing required columns.")

        df = df.rename(columns={
            c_date: "Date", c_day: "Day", c_slot: "Slot",
            c_typ: "Typ" if c_typ else "Typ",
            c_play: "Players",
        })
        # Type normalize
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        if "Typ" not in df:
            df["Typ"] = df["Slot"].apply(lambda s: "Einzel" if str(s).startswith("E") else "Doppel")
    except Exception:
        # Fallback: rebuild from grid
        grid = pd.read_excel(io.BytesIO(data), sheet_name="Herren 40–50–60", header=[1])
        grid = grid.rename(columns={grid.columns[0]:"Date", grid.columns[1]:"Day"})
        players = list(grid.columns[2:])
        rows=[]
        for _,row in grid.iterrows():
            dd = pd.to_datetime(row["Date"]).date()
            day = str(row["Day"])
            for p in players:
                code = str(row.get(p,"") or "").strip()
                if SLOT_RE.match(code):
                    rows.append({
                        "Date": dd,
                        "Day": day,
                        "Slot": code,
                        "Typ": "Einzel" if code.startswith("E") else "Doppel",
                        "Players": p
                    })
        df = pd.DataFrame(rows)

    # Expand Players column → PlayerList
    out=[]
    for _,r in df.iterrows():
        plist = [p.strip() for p in str(r["Players"]).split("/") if p.strip()]
        out.append({**r, "PlayerList": plist})
    return pd.DataFrame(out)

# ---------- UI ----------
st.title("🎾 Winter-Training – Plan (Viewer)")
st.caption("Für Spieler:innen: Wochenplan, eigener Spielplan, kompletter Plan, Kostenübersicht.")

with st.sidebar:
    st.header("Datenquelle")
    override = st.text_input("GitHub RAW URL (optional)", value=GH_RAW_DEFAULT)
    st.caption("Wenn leer gelassen, wird die Standard-URL aus dem Code verwendet.")
    st.divider()
    st.header("Filter")
    days = st.multiselect("Wochentage", ["Montag","Mittwoch","Donnerstag"], default=["Montag","Mittwoch","Donnerstag"])
    kinds = st.multiselect("Art", ["Einzel","Doppel"], default=["Einzel","Doppel"])

# Load data
try:
    df = load_plan_from_url(override or GH_RAW_DEFAULT)
except Exception as e:
    st.error(f"Plan konnte nicht geladen werden: {e}")
    st.stop()

# Apply filters + computed start time
df = df[df["Day"].isin(days)]
df = df[df["Typ"].isin(kinds)]
df["Start"] = df["Slot"].apply(slot_time_str)
df = df.sort_values(by=["Date","Start","Slot"])

all_players = sorted({p for L in df["PlayerList"] for p in L}, key=lambda s: norm(s).lower())

tab1, tab2, tab3, tab4 = st.tabs(["📆 Wochenplan", "👤 Spieler", "📄 Kompletter Plan", "💶 Spieler-Kosten"])

# --- 📆 Wochenplan ---
with tab1:
    st.subheader("Wochenplan")
    # Choose ISO week; default to first upcoming week if present
    unique_dates = sorted(df["Date"].unique())
    today = date.today()
    weeks = sorted({(pd.Timestamp(d).isocalendar().week, d) for d in unique_dates})
    week_numbers = sorted({w for w,_ in weeks})

    # pick index: upcoming if possible
    idx = 0
    for i, (w, d) in enumerate(sorted(weeks)):
        if d >= today:
            idx = i
            break
    # Build selectbox options as "KW xx"
    week_label_map = {}
    for w in week_numbers:
        week_label_map[w] = f"KW {w:02d}"
    picked_week = st.selectbox("Woche", options=week_numbers, index=min(idx, len(week_numbers)-1),
                               format_func=lambda w: week_label_map.get(w, f"KW {w:02d}"))
    week_dates = [d for w, d in weeks if w == picked_week]

    show = df[df["Date"].isin(week_dates)]
    for d, grp in show.groupby("Date"):
        st.markdown(f"### {pd.Timestamp(d).strftime('%a, %d.%m.%Y')}")
        for _,r in grp.iterrows():
            players = " · ".join(r["PlayerList"])
            st.write(f"- {r['Start']}  |  **{r['Typ']}**  |  {r['Slot']}  |  {players}")
        st.markdown("---")

# --- 👤 Spieler ---
with tab2:
    st.subheader("Einzelner Spieler")
    me = st.selectbox("Spieler wählen", all_players)
    mine = df[df["PlayerList"].apply(lambda L: me in L)]
    st.write(f"Gefundene Termine: **{len(mine)}**")
    st.dataframe(
        mine[["Date","Day","Start","Typ","Slot","Players"]]
            .rename(columns={"Date":"Datum","Day":"Tag","Players":"Mitspieler"}),
        use_container_width=True,
        height=420
    )

# --- 📄 Kompletter Plan ---
with tab3:
    st.subheader("Kompletter Plan")
    st.dataframe(
        df[["Date","Day","Start","Typ","Slot","Players"]]
            .rename(columns={"Date":"Datum","Day":"Tag","Players":"Spieler"}),
        use_container_width=True,
        height=700
    )

# --- 💶 Spieler-Kosten ---
with tab4:
    st.subheader("Spieler-Kosten (anteilig)")
    c1, c2 = st.columns(2)
    with c1:
        rate_pla = st.number_input("Kosten €/Stunde (PLA)", value=0.0, step=1.0)
    with c2:
        rate_plb = st.number_input("Kosten €/Stunde (PLB)", value=0.0, step=1.0)

    def slot_cost_eur(code: str) -> float:
        p = parse_slot(code)
        if not p: return 0.0
        rate = rate_pla if p["court"] == "A" else rate_plb
        return (p["mins"] / 60.0) * float(rate)

    rows=[]
    for _,r in df.iterrows():
        n_players = 2 if r["Typ"] == "Einzel" else 4
        total = slot_cost_eur(r["Slot"])
        share = total / n_players if n_players else 0.0
        for pl in r["PlayerList"]:
            rows.append({
                "Spieler": pl,
                "Datum": r["Date"],
                "Tag": r["Day"],
                "Typ": r["Typ"],
                "Slot": r["Slot"],
                "Minuten": minutes_of(r["Slot"]),
                "Anteil €": round(share, 2)
            })
    cost_df = pd.DataFrame(rows)

    if len(cost_df):
        agg = (cost_df.groupby("Spieler", as_index=False)
               .agg({"Minuten":"sum","Anteil €":"sum"})
               .sort_values(["Anteil €","Spieler"], ascending=[False, True]))
        st.markdown("**Gesamt je Spieler**")
        st.dataframe(agg, use_container_width=True, height=380)
        st.markdown("—")
        st.markdown("**Details**")
        st.dataframe(cost_df.sort_values(["Spieler","Datum","Slot"]),
                     use_container_width=True, height=420)
    else:
        st.info("Keine Einträge gefunden.")
