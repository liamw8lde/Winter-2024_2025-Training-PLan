import io, re, unicodedata, requests
from datetime import date, datetime, timedelta
from collections import defaultdict
import pandas as pd
import streamlit as st
from dateutil import tz

st.set_page_config(page_title="🎾 Winter-Training Plan", layout="wide")

SLOT_RE = re.compile(r"^([DE])(\d{2}):(\d{2})-([0-9]+)\s+PL([AB])$", re.IGNORECASE)

# ---------- helpers ----------
def norm(s):
    s = str(s or "").strip()
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    return re.sub(r"\s+"," ",s)

def to_dt(v):
    try: return pd.to_datetime(v)
    except: return pd.NaT

def parse_slot(code):
    m = SLOT_RE.match(str(code or ""))
    if not m: return None
    return dict(kind=m.group(1), hh=int(m.group(2)), mm=int(m.group(3)), mins=int(m.group(4)), court=m.group(5))

def slot_time_str(code):
    p = parse_slot(code); 
    return f"{p['hh']:02d}:{p['mm']:02d}" if p else "?"

def minutes(code):
    p = parse_slot(code); 
    return p["mins"] if p else 0

# ---------- data loader (hard-wired GitHub RAW) ----------
GH_RAW_DEFAULT = "https://github.com/liamw8lde/Winter-2024_2025-Training-PLan/blob/main/trainplan.xlsx"  # <- change if needed

@st.cache_data(show_spinner=False)
def load_plan(url: str):
    r = requests.get(url)
    r.raise_for_status()
    data = r.content
    # Prefer Spielplan; else reconstruct from grid
    try:
        df = pd.read_excel(io.BytesIO(data), sheet_name="Spielplan")
        df = df.rename(columns={"Datum":"Date","Tag":"Day","Slot":"Slot","Spieler":"Players","Typ":"Typ"})
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
    except Exception:
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
                    rows.append({"Date":dd,"Day":day,"Slot":code,"Typ":"Einzel" if code.startswith("E") else "Doppel","Players":p})
        df = pd.DataFrame(rows)
    # expand player list
    out=[]
    for _,r in df.iterrows():
        plist = [p.strip() for p in str(r["Players"]).split("/") if p.strip()]
        out.append({**r, "PlayerList": plist})
    return pd.DataFrame(out)

# ---------- UI ----------
st.title("🎾 Winter-Training – Plan (Viewer)")
st.caption("Für Spieler:innen: Wochenplan, eigener Spielplan, kompletter Plan, Kostenübersicht.")

df = load_plan(GH_RAW_DEFAULT)

# Filters (top)
days = st.multiselect("Wochentage", ["Montag","Mittwoch","Donnerstag"], default=["Montag","Mittwoch","Donnerstag"], key="days")
kinds = st.multiselect("Art", ["Einzel","Doppel"], default=["Einzel","Doppel"], key="kinds")

df = df[df["Day"].isin(days)]
df = df[df["Typ"].isin(kinds)]
df["Start"] = df.apply(lambda r: slot_time_str(r["Slot"]), axis=1)
df = df.sort_values(["Date","Start","Slot"])

all_players = sorted({p for L in df["PlayerList"] for p in L}, key=lambda s: norm(s).lower())

tab1, tab2, tab3, tab4 = st.tabs(["📆 Wochenplan", "👤 Spieler", "📄 Kompletter Plan", "💶 Spieler-Kosten"])

# --- Wochenplan ---
with tab1:
    st.subheader("Wochenplan")
    # choose week by ISO week number
    unique_dates = sorted(df["Date"].unique())
    week_map = sorted({(pd.Timestamp(d).isocalendar().week, d) for d in unique_dates})
    if week_map:
        week_numbers = sorted({w for w,_ in week_map})
        wk = st.selectbox("Woche", week_numbers, index=0)
        week_dates = [d for w,d in week_map if w==wk]
        show = df[df["Date"].isin(week_dates)]
    else:
        show = df.head(0)
    for d, grp in show.groupby("Date"):
        st.markdown(f"### {pd.Timestamp(d).strftime('%a, %d.%m.%Y')}")
        for _,r in grp.iterrows():
            players = " · ".join(r["PlayerList"])
            st.write(f"- {r['Start']}  |  **{r['Typ']}**  |  {r['Slot']}  |  {players}")
        st.markdown("---")

# --- Spieler ---
with tab2:
    st.subheader("Einzelner Spieler")
    me = st.selectbox("Spieler wählen", all_players)
    mine = df[df["PlayerList"].apply(lambda L: me in L)]
    st.write(f"Gefundene Termine: **{len(mine)}**")
    st.dataframe(mine[["Date","Day","Start","Typ","Slot","Players"]].rename(columns={"Date":"Datum","Day":"Tag","Players":"Mitspieler"}),
                 use_container_width=True, height=420)

# --- Komplett ---
with tab3:
    st.subheader("Kompletter Plan")
    st.dataframe(df[["Date","Day","Start","Typ","Slot","Players"]].rename(columns={"Date":"Datum","Day":"Tag","Players":"Spieler"}),
                 use_container_width=True, height=700)

# --- Spieler-Kosten ---
with tab4:
    st.subheader("Spieler-Kosten (anteilig)")
    c1, c2 = st.columns(2)
    with c1:
        rate_pla = st.number_input("Kosten €/Stunde (PLA)", value=0.0, step=1.0)
    with c2:
        rate_plb = st.number_input("Kosten €/Stunde (PLB)", value=0.0, step=1.0)

    def slot_cost(code):
        p = parse_slot(code); 
        rate = rate_pla if p and p["court"]=="A" else rate_plb
        return (p["mins"]/60.0) * rate if p else 0.0

    rows=[]
    for _,r in df.iterrows():
        n_players = 2 if r["Typ"]=="Einzel" else 4
        total_cost = slot_cost(r["Slot"])
        share = total_cost / n_players if n_players else 0
        for pl in r["PlayerList"]:
            rows.append({"Spieler":pl,
                         "Datum":r["Date"],
                         "Tag":r["Day"],
                         "Typ":r["Typ"],
                         "Slot":r["Slot"],
                         "Minuten": minutes(r["Slot"]),
                         "Anteil €": round(share,2)})
    cost_df = pd.DataFrame(rows)
    if len(cost_df):
        agg = cost_df.groupby("Spieler", as_index=False).agg({"Minuten":"sum","Anteil €":"sum"})
        agg = agg.sort_values(["Anteil €","Spieler"], ascending=[False, True])
        st.markdown("**Gesamt je Spieler**")
        st.dataframe(agg, use_container_width=True, height=380)
        st.markdown("—")
        st.markdown("**Details**")
        st.dataframe(cost_df.sort_values(["Spieler","Datum","Slot"]), use_container_width=True, height=420)
    else:
        st.info("Keine Einträge gefunden.")

