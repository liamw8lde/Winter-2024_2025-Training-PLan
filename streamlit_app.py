import streamlit as st
import pandas as pd

# ---------- Simple password gate ----------
PASSWORD = "TGR2025"

def check_password() -> bool:
    if "auth_ok" in st.session_state and st.session_state.auth_ok:
        return True
    with st.sidebar:
        st.subheader("🔒 Zugang")
        pw = st.text_input("Passwort eingeben", type="password", help="Hint: TGR + Jahr")
        if st.button("Login"):
            if pw == PASSWORD:
                st.session_state.auth_ok = True
                st.rerun()
            else:
                st.error("Falsches Passwort.")
    return False

st.set_page_config(page_title="Wochenplan", layout="wide")

# Stop early if not authenticated
if not check_password():
    st.stop()

# Optional logout
with st.sidebar:
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()

# ---------- Styles ----------
CUSTOM_CSS = '''<style>
:root {
  --bg: #0f1117; --panel: #151a23; --muted: #9aa4b2; --text: #e6e9ef;
  --accent: #96e6a1; --badge-bg: #12351c; --badge-edge: #2f6b3c; --divider: #242c36;
}
[class^="stAppViewContainer"] { background: var(--bg); }
h1,h2,h3,h4,h5,h6, p, li, span, div, label { color: var(--text); }
small, .muted { color: var(--muted) !important; }
.page-title { margin: 10px 0 8px 0; }
.kalenderwoche { font-size: 1.4rem; font-weight: 700; margin-top: 2px; }
.day-block { background: transparent; padding: 8px 0 18px 0; border-bottom: 1px solid var(--divider); }
.day-title { font-weight: 700; font-size: 1.1rem; margin: 12px 0 12px 0; }
.match-item { margin: 10px 0; list-style: none; }
.rowline { display: flex; align-items: center; gap: 10px; }
.badge { display: inline-flex; align-items: center; gap: 8px; padding: 4px 10px; border-radius: 10px;
  font-weight: 600; letter-spacing: 0.02em; background: var(--badge-bg); border: 1px solid var(--badge-edge);
  color: var(--accent); font-size: 0.85rem; }
.badge .court { background: #0e2215; border: 1px solid var(--badge-edge); padding: 2px 6px; border-radius: 6px;
  font-size: 0.75rem; color: var(--accent); }
.type { font-style: italic; color: var(--text); }
.players { margin-left: 28px; color: var(--text); }

/* Buttons */
.navbar { display:flex; gap:10px; align-items:center; margin: 10px 0 6px 0; }
.navbtn > button { background: var(--panel) !important; color: var(--text) !important; border: 1px solid var(--divider) !important; }
hr { border: none; border-top: 1px solid var(--divider); margin: 16px 0; }

/* Fix streamlit selects/multiselect white-on-white */
div[data-baseweb="select"] > div { background: var(--panel) !important; color: var(--text) !important; }
div[data-baseweb="select"] input { color: var(--text) !important; }
div[data-baseweb="select"] svg { fill: var(--text) !important; }
div[data-baseweb="select"] div[aria-selected="true"] { background: #0e2215 !important; color: var(--accent) !important; }
</style>'''
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ---------- Data helpers ----------
def _postprocess(df: pd.DataFrame):
    expected = ["Datum", "Tag", "Slot", "Typ", "Spieler"]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise ValueError(f"Fehlende Spalten: {', '.join(missing)}; erwartet: {expected}")
    for c in expected:
        df[c] = df[c].astype(str).str.strip()
    df["Datum_dt"] = pd.to_datetime(df["Datum"], dayfirst=True, errors="coerce")
    iso = df["Datum_dt"].dt.isocalendar()
    df["Jahr"] = iso["year"]; df["Woche"] = iso["week"]
    slot_re = df["Slot"].str.extract(r"^([ED])(\d{2}:\d{2})-([0-9]+)\s+PL([AB])$", expand=True)
    df["S_Art"] = slot_re[0].fillna("")
    df["S_Time"] = slot_re[1].fillna("00:00")
    df["S_Dur"] = slot_re[2].fillna("0")
    df["S_Court"] = slot_re[3].fillna("")
    try:
        df["Startzeit_sort"] = pd.to_datetime(df["S_Time"], format="%H:%M", errors="coerce").dt.time
    except Exception:
        df["Startzeit_sort"] = None
    df["Spieler_list"] = df["Spieler"].str.split(",").apply(lambda xs: [x.strip() for x in xs if str(x).strip()])
    df_exp = df.explode("Spieler_list").rename(columns={"Spieler_list":"Spieler_Name"})
    return df, df_exp

@st.cache_data
def load_csv(path_or_buf):
    return pd.read_csv(path_or_buf, dtype=str).pipe(_postprocess)

def week_key(df):
    return df["Jahr"].astype(str) + "-W" + df["Woche"].astype(str).str.zfill(2)

def make_badge(row):
    time = f"{row['S_Art']}{row['S_Time']}–{row['S_Dur']}"
    court = f"PL{row['S_Court']}" if row["S_Court"] else ""
    return f'<span class="badge">{time} <span class="court">{court}</span></span>'

def render_week_view(df, year, week):
    wk = df[(df["Jahr"]==year) & (df["Woche"]==week)].copy()
    if wk.empty:
        st.info("Keine Einträge in dieser Woche."); return
    wk = wk.sort_values(["Datum_dt","Startzeit_sort","Slot"])
    st.markdown('<div class="page-title"><h1>Wochenplan</h1></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="kalenderwoche">Kalenderwoche {int(week)}, {int(year)}</div>', unsafe_allow_html=True)
    for dt, day_df in wk.groupby("Datum_dt"):
        day_str = dt.strftime("%A, %Y-%m-%d")
        st.markdown(f'<div class="day-block"><div class="day-title">{day_str}</div>', unsafe_allow_html=True)
        for _, r in day_df.iterrows():
            badge_html = make_badge(r)
            type_html = f'<span class="type">— {r["Typ"]}</span>'
            top = f'<div class="rowline">• {badge_html} {type_html}</div>'
            players_html = f'<div class="players">{r["Spieler"]}</div>'
            st.markdown(f'<div class="match-item">{top}{players_html}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

# ---------- Data source (GitHub raw default, upload optional) ----------
st.sidebar.header("📄 Datenquelle")
default_path = "https://raw.githubusercontent.com/liamw8lde/Winter-2024_2025-Training-PLan/main/winter_training.csv"
uploaded = st.sidebar.file_uploader("CSV hochladen (Spalten: Datum, Tag, Slot, Typ, Spieler)", type=["csv"])
use = st.sidebar.radio("Quelle wählen", ["GitHub-Datei", "Upload"], index=0 if uploaded is None else 1)

try:
    if use == "Upload" and uploaded is not None:
        df, df_exp = load_csv(uploaded)
        src = "Upload"
    else:
        df, df_exp = load_csv(default_path)
        src = "GitHub-Datei"
except Exception as e:
    st.error(f"Datenfehler: {e}"); st.stop()

st.sidebar.success(f"Quelle: {src}")

# ---------- Tabs ----------
tab1, tab2 = st.tabs(["📆 Wochenplan", "🧍 Spieler-Matches"])

with tab1:
    weeks_df = (
        df.dropna(subset=["Datum_dt"])
          .assign(WeekKey=week_key)
          .sort_values(["Jahr","Woche","Datum_dt"])
    )
    week_keys = weeks_df["WeekKey"].unique().tolist()
    if not week_keys:
        st.warning("Keine Wochen gefunden.")
    else:
        if "wk_idx" not in st.session_state:
            st.session_state.wk_idx = 0
        c1, c2, c3 = st.columns([1,1,8])
        with c1:
            if st.button("◀ Woche zurück", use_container_width=True):
                st.session_state.wk_idx = max(0, st.session_state.wk_idx - 1)
        with c2:
            if st.button("Woche vor ▶", use_container_width=True):
                st.session_state.wk_idx = min(len(week_keys)-1, st.session_state.wk_idx + 1)
        st.session_state.wk_idx = max(0, min(st.session_state.wk_idx, len(week_keys)-1))
        sel_key = week_keys[st.session_state.wk_idx]
        y = int(sel_key.split("-W")[0]); w = int(sel_key.split("-W")[1])
        render_week_view(df, y, w)

with tab2:
    st.subheader("🧍 Spieler-Matches")
    players = sorted([p for p in df_exp["Spieler_Name"].dropna().unique().tolist() if str(p).strip()])
    sel_players = st.multiselect("Spieler wählen", options=players, max_selections=5)
    if sel_players:
        pf = df_exp[df_exp["Spieler_Name"].isin(sel_players)].copy()
        pf = pf.sort_values(["Datum_dt","Startzeit_sort","Slot"])
        cols = st.columns(min(len(sel_players), 5))
        for i, p in enumerate(sel_players):
            cnt = int((pf["Spieler_Name"] == p).sum())
            cols[i].metric(p, f"{cnt} Matches")
        st.dataframe(pf[["Spieler_Name","Datum","Tag","Slot","Typ","Spieler"]], use_container_width=True, hide_index=True)
    else:
        st.info("Bitte Spieler auswählen.")
