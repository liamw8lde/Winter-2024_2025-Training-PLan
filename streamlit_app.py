# streamlit_app.py — viewer-only, no sidebar
import io, re, unicodedata, requests
from datetime import date
import pandas as pd
import streamlit as st

st.set_page_config(page_title="🎾 Winter-Training Plan", layout="wide")

# ---- CONFIG: set your RAW GitHub URL here ----
GH_RAW_DEFAULT = "https://raw.githubusercontent.com/liamw8lde/winter-2024_2025-training-plan/main/trainplan.xlsx"

SLOT_RE = re.compile(r"^([DE])(\d{2}):(\d{2})-([0-9]+)\s+PL([AB])$", re.IGNORECASE)

def norm(s):
    s = str(s or "").strip()
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    return re.sub(r"\s+"," ",s)

def parse_slot(code):
    m = SLOT_RE.match(str(code or ""))
    if not m: return None
    return {"kind": m.group(1).upper(), "hh": int(m.group(2)),
            "mm": int(m.group(3)), "mins": int(m.group(4)),
            "court": m.group(5).upper()}  # 'A' or 'B'

def slot_time_str(code):
    p = parse_slot(code);  return f"{p['hh']:02d}:{p['mm']:02d}" if p else "?"

def minutes_of(code):
    p = parse_slot(code);  return p["mins"] if p else 0

@st.cache_data(show_spinner=False)
def load_plan(url: str) -> pd.DataFrame:
    r = requests.get(url)
    if r.status_code != 200:
        raise ValueError(f"HTTP {r.status_code} for {url}")
    data = r.content
    if not data.startswith(b"PK"):
        raise ValueError("Downloaded file is not .xlsx (likely an HTML page). Use RAW link.")
    # Prefer Spielplan
    try:
        df = pd.read_excel(io.BytesIO(data), sheet_name="Spielplan")
        cols = {c.lower(): c for c in df.columns}
        df = df.rename(columns={
            cols.get("datum","Datum"): "Date",
            cols.get("tag","Tag"): "Day",
            cols.get("slot","Slot"): "Slot",
            cols.get("spieler","Spieler"): "Spieler",
            cols.get("typ","Typ"): "Typ"
        })
        df["Date"] = pd.to_datetime(df["Date"]).dt.date
        df["Players"] = df.get("Spieler","")
        if "Typ" not in df: df["Typ"] = df["Slot"].apply(lambda s: "Einzel" if str(s).startswith("E") else "Doppel")
    except Exception:
        # Fallback: grid
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
                    rows.append({"Date": dd, "Day": day, "Slot": code,
                                 "Typ": "Einzel" if code.startswith("E") else "Doppel",
                                 "Players": p})
        df = pd.DataFrame(rows)
    # expand Players -> PlayerList
    out=[]
    for _,r in df.iterrows():
        plist = [p.strip() for p in str(r["Players"]).split("/") if p.strip()]
        out.append({**r, "PlayerList": plist})
    return pd.DataFrame(out)

# ---------- UI (no sidebar) ----------
st.title("🎾 Winter-Training – Plan (Viewer)")

# Load once; show a friendly error if RAW URL is wrong
try:
    df = load_plan(GH_RAW_DEFAULT)
except Exception as e:
    st.error(f"Plan konnte nicht geladen werden: {e}")
    st.stop()

# Precompute ordering & helpers
df["Start"] = df["Slot"].apply(slot_time_str)
df = df.sort_values(["Date","Start","Slot"])
all_players = sorted({p for L in df["PlayerList"] for p in L}, key=lambda s: norm(s).lower())

tab1, tab2, tab3, tab4 = st.tabs(["📆 Wochenplan", "👤 Spieler", "📄 Kompletter Plan", "💶 Spieler-Kosten"])

# --- 📆 Wochenplan (current week by default; prev/next buttons) ---
with tab1:
    st.subheader("Wochenplan")
    def week_key(d):
        iso = pd.Timestamp(d).isocalendar()
        return (int(iso.year), int(iso.week))
    all_dates = sorted(df["Date"].unique())
    if not all_dates:
        st.info("Keine Termine im Plan."); st.stop()
    wk_to_dates = {}
    for d in all_dates:
        wk_to_dates.setdefault(week_key(d), []).append(d)
    today = date.today()
    current = week_key(today)
    if "wk_idx" not in st.session_state:
        keys = sorted(wk_to_dates.keys())
        default = current if current in wk_to_dates else (next((k for k in keys if min(wk_to_dates[k]) >= today), keys[-1]))
        st.session_state.wk_idx = keys.index(default)
    cols = st.columns([1,1,3,1,1])
    with cols[0]:
        if st.button("← Vorherige"):
            st.session_state.wk_idx = max(0, st.session_state.wk_idx - 1)
    with cols[4]:
        if st.button("Nächste →"):
            st.session_state.wk_idx = min(len(wk_to_dates)-1, st.session_state.wk_idx + 1)
    keys = sorted(wk_to_dates.keys())
    yr, wk = keys[st.session_state.wk_idx]
    st.markdown(f"**KW {wk:02d} – {yr}**")
    show = df[df["Date"].isin(sorted(wk_to_dates[(yr, wk)]))]
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
    st.dataframe(mine[["Date","Day","Start","Typ","Slot","Players"]]
                 .rename(columns={"Date":"Datum","Day":"Tag","Players":"Mitspieler"}),
                 use_container_width=True, height=420)

# --- 📄 Kompletter Plan ---
with tab3:
    st.subheader("Kompletter Plan")
    st.dataframe(df[["Date","Day","Start","Typ","Slot","Players"]]
                 .rename(columns={"Date":"Datum","Day":"Tag","Players":"Spieler"}),
                 use_container_width=True, height=700)

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
        n = 2 if r["Typ"] == "Einzel" else 4
        share = slot_cost_eur(r["Slot"]) / n if n else 0.0
        for pl in r["PlayerList"]:
            rows.append({"Spieler": pl, "Datum": r["Date"], "Tag": r["Day"],
                         "Typ": r["Typ"], "Slot": r["Slot"],
                         "Minuten": minutes_of(r["Slot"]), "Anteil €": round(share,2)})
    cost_df = pd.DataFrame(rows)
    if len(cost_df):
        agg = (cost_df.groupby("Spieler", as_index=False)
               .agg({"Minuten":"sum","Anteil €":"sum"})
               .sort_values(["Anteil €","Spieler"], ascending=[False, True]))
        st.markdown("**Gesamt je Spieler**")
        st.dataframe(agg, use_container_width=True, height=360)
        st.markdown("—")
        st.markdown("**Details**")
        st.dataframe(cost_df.sort_values(["Spieler","Datum","Slot"]),
                     use_container_width=True, height=420)
    else:
        st.info("Keine Einträge gefunden.")
