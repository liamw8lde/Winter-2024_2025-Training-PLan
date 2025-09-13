# streamlit_app.py
# ------------------------------------------------------------
# Winter-Training – Viewer (Deutsch)
# Tabs: Wochenplan (KW-Ansicht), Einzelspieler, Komplettplan,
#       Kosten (17,50 €/h korrekt umgelegt), Raster (Herren 40–50–60)
# ------------------------------------------------------------
import io
import re
import requests
import pandas as pd
import streamlit as st
from datetime import date
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
import json

# ---------- Seite / Layout ----------
st.set_page_config(
    page_title="Winter-Training Herren 40–50–60",
    page_icon="🎾",
    layout="wide",
)

# ---------- Konstanten ----------
HOURLY_RATE = 17.50  # € pro Stunde (Platzmiete)
SLOT_RE = re.compile(r"^([DE])(\d{2}):(\d{2})-([0-9]+)\s+PL([AB])$", re.IGNORECASE)

# ---------- Datenquelle ----------
# Update: default points to the FIXED plan. Replace with your repo if needed.
GH_RAW_DEFAULT = "https://raw.githubusercontent.com/liamw8lde/Winter-2024_2025-Training-PLan/main/trainplan_FIXED.xlsx"

st.sidebar.markdown("### Datenquelle")
gh_raw_url = st.sidebar.text_input(
    "GitHub RAW URL (optional)",
    value="",
    placeholder=GH_RAW_DEFAULT,
)
uploaded = st.sidebar.file_uploader("…oder Excel-Datei hochladen (trainplan_FIXED.xlsx)", type=["xlsx"])

def _resolve_source() -> bytes:
    """Return raw bytes from uploader (preferred) or URL."""
    if uploaded is not None:
        return uploaded.read()
    url = gh_raw_url.strip() or GH_RAW_DEFAULT
    if not url.startswith("http"):
        raise ValueError("Bitte eine gültige GitHub RAW URL angeben oder eine Datei hochladen.")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.content

# ---------- Loader ----------
@st.cache_data(show_spinner=True)
def fetch_bytes() -> bytes:
    return _resolve_source()

def _rename_like(df: pd.DataFrame, new_map: dict) -> pd.DataFrame:
    """Flexible rename supporting case-insensitive lookup."""
    lower_map = {c.lower(): c for c in df.columns}
    ren = {}
    for want, candidates in new_map.items():
        for cand in candidates:
            col = lower_map.get(cand.lower())
            if col:
                ren[col] = want
                break
    return df.rename(columns=ren)

def _parse_player_list(value: str) -> list[str]:
    """
    Robust parser for 'Spieler' from our Spielplan:
    - Singles: 'A, B'
    - Doubles: 'A, B, C, D'
    Also tolerates 'A & B vs C & D' or mixed separators.
    """
    s = str(value or "").strip()
    if not s:
        return []
    # Normalize common separators to commas
    s = s.replace(" & ", ", ").replace("&", ",").replace(" vs ", ",").replace("/", ",")
    # Split by comma
    parts = [p.strip() for p in s.split(",") if p.strip()]
    # Deduplicate accidental repeats while preserving order
    seen, out = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p); out.append(p)
    return out

@st.cache_data(show_spinner=False)
def load_plan() -> pd.DataFrame:
    """
    Läd bevorzugt das Blatt 'Spielplan'.
    Fallback: extrahiert aus dem Raster 'Herren 40–50–60' alle belegten Slots.
    Gibt immer Spalten zurück: Date, Day, Slot, Typ, Players, PlayerList
    """
    data = fetch_bytes()
    xio = io.BytesIO(data)

    # 1) Versuch: "Spielplan" mit unseren Spalten
    try:
        df = pd.read_excel(xio, sheet_name="Spielplan")
        df = _rename_like(
            df,
            {
                "Date": ["Datum", "Date"],
                "Day": ["Tag", "Day"],
                "Slot": ["Slot"],
                "Players": ["Spieler", "Players"],
                "Typ": ["Typ", "Art"],
            },
        )
        # Normiere Datumsfeld
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
        # Typ aus Slot herleiten, falls fehlt
        if "Typ" not in df.columns:
            df["Typ"] = df["Slot"].apply(lambda s: "Einzel" if str(s).startswith("E") else "Doppel")
        # Spieler-Liste robust parsen (Kommas etc.)
        df["PlayerList"] = df["Players"].apply(_parse_player_list)
        # Einheitlich sortieren
        def slot_key(s):
            m = SLOT_RE.match(str(s))
            return (int(m.group(2)), int(m.group(3))) if m else (99, 99)
        df = df.sort_values(["Date", "Slot"], key=lambda col: col.map(slot_key) if col.name == "Slot" else col)
        return df[["Date", "Day", "Slot", "Typ", "Players", "PlayerList"]]
    except Exception:
        pass

    # 2) Fallback aus dem Raster
    xio.seek(0)
    grid = pd.read_excel(xio, sheet_name="Herren 40–50–60", header=[1], dtype=str)
    grid = grid.rename(columns={grid.columns[0]: "Date", grid.columns[1]: "Day"})
    grid["Date"] = pd.to_datetime(grid["Date"], errors="coerce").dt.date
    player_cols = list(grid.columns[2:])

    # Sammle pro Datum/Slot alle Spieler zusammen
    rows = []
    for _, r in grid.iterrows():
        dd = r["Date"]; day = r["Day"]
        # code -> list of players in that slot (this row)
        bucket = {}
        for p in player_cols:
            code = str(r.get(p, "") or "").strip()
            if SLOT_RE.match(code):
                bucket.setdefault(code, []).append(p)
        for code, plist in bucket.items():
            rows.append(
                {
                    "Date": dd,
                    "Day": day,
                    "Slot": code,
                    "Typ": "Einzel" if code.startswith("E") else "Doppel",
                    "Players": ", ".join(plist),
                    "PlayerList": plist,
                }
            )
    df = pd.DataFrame(rows)

    def slot_key(s):
        m = SLOT_RE.match(str(s))
        return (int(m.group(2)), int(m.group(3))) if m else (99, 99)
    return df.sort_values(["Date", "Slot"], key=lambda col: col.map(slot_key) if col.name == "Slot" else col)

@st.cache_data(show_spinner=False)
def load_grid() -> pd.DataFrame:
    """
    Liest das Blatt 'Herren 40–50–60' (Kopfzeile = zweite Zeile im Excel).
    Gibt Datum/Tag + Spieler-Spalten zurück.
    """
    data = fetch_bytes()
    xio = io.BytesIO(data)
    grid = pd.read_excel(xio, sheet_name="Herren 40–50–60", header=[1], dtype=str)
    grid = grid.rename(columns={grid.columns[0]: "Datum", grid.columns[1]: "Tag"})
    grid["Datum"] = pd.to_datetime(grid["Datum"], errors="coerce").dt.strftime("%Y-%m-%d")
    player_cols = [c for c in grid.columns if c not in ("Datum", "Tag")]
    return grid[["Datum", "Tag"] + player_cols]

# ---------- Hilfen ----------
def parse_slot(code: str):
    m = SLOT_RE.match(str(code or ""))
    if not m:
        return None
    kind = m.group(1).upper()
    hh, mm = int(m.group(2)), int(m.group(3))
    dur = int(m.group(4))
    return {"kind": kind, "start": f"{hh:02d}:{mm:02d}", "minutes": dur}

def expand_per_player(df_plan: pd.DataFrame) -> pd.DataFrame:
    """Explodiert jede Spielplan-Zeile auf einzelne Spieler (mit Partner/Gegner)."""
    rows = []
    for _, r in df_plan.iterrows():
        plist = r["PlayerList"]
        for p in plist:
            others = [x for x in plist if x != p]
            rows.append(
                {
                    "Spieler": p,
                    "Datum": r["Date"],
                    "Tag": r["Day"],
                    "Typ": r["Typ"],
                    "Slot": r["Slot"],
                    "Partner/Gegner": " / ".join(others),
                }
            )
    return pd.DataFrame(rows)

def df_week_key(d: date):
    iso = pd.Timestamp(d).isocalendar()
    return int(iso.week), int(iso.year)

# Farbpalette analog "Legende"
PALETTE = {
    # Montag (Doppel, 120 min)
    "D20:00-120 PLA": "1D4ED8",
    "D20:00-120 PLB": "F59E0B",

    # Mittwoch
    "E18:00-60 PLA":  "10B981",  # Einzel
    "E19:00-60 PLA":  "14B8A6",  # Einzel
    "E19:00-60 PLB":  "14B8A6",  # Einzel
    "D20:00-90 PLA":  "6D28D9",  # Doppel
    "D20:00-90 PLB":  "C4B5FD",  # Doppel

    # Donnerstag (Einzel, 90 min)
    "E20:00-90 PLA":  "0EA5E9",
    "E20:00-90 PLB":  "0EA5E9",
}

CELLSTYLE = JsCode(f"""
function(params) {{
  if (!params.value) {{ return {{}}; }}
  const v = String(params.value).trim();
  const pat = /^([DE])\\d{{2}}:\\d{{2}}-\\d+\\s+PL[AB]$/;
  if (!pat.test(v)) {{ return {{}}; }}
  const pal = {json.dumps(PALETTE)};
  const hex = pal[v] || "6B7280";  // default gray
  const bg  = "#" + hex;

  // luminance approx for text color
  const r = parseInt(hex.substr(0,2),16)/255.0;
  const g = parseInt(hex.substr(2,2),16)/255.0;
  const b = parseInt(hex.substr(4,2),16)/255.0;
  const lum = 0.2126*r + 0.7152*g + 0.0722*b;
  const fg  = (lum < 0.55) ? "white" : "black";

  return {{
    backgroundColor: bg,
    color: fg,
    fontWeight: "600",
    textAlign: "center",
    borderRight: "1px solid #eee",
  }};
}}
""")

def show_raster_aggrid(grid_df: pd.DataFrame):
    gb = GridOptionsBuilder.from_dataframe(grid_df)
    gb.configure_default_column(
        resizable=True,
        wrapText=True,
        autoHeight=True,
        cellStyle=CELLSTYLE
    )
    gb.configure_column("Datum", pinned="left", width=120)
    gb.configure_column("Tag",   pinned="left", width=110)
    for col in grid_df.columns[2:]:
        gb.configure_column(col, width=150)
    go = gb.build()
    AgGrid(
        grid_df,
        gridOptions=go,
        allow_unsafe_jscode=True,
        fit_columns_on_grid_load=False,
        height=560,
        theme="balham"
    )

# ---------- Daten laden ----------
try:
    df = load_plan()
    grid_df = load_grid()
except Exception as e:
    st.error(f"Plan konnte nicht geladen werden.\n\nFehler: {e}")
    st.stop()

per_player = expand_per_player(df)

# ---------- Tabs ----------
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "🗓️ Wochenplan",
        "👤 Einzelspieler",
        "📋 Komplettplan",
        "💶 Kosten",
        "🧱 Raster (Herren 40–50–60)",
    ]
)

# --- 🗓️ Wochenplan ---
with tab1:
    st.subheader("Wochenplan")
    if df.empty:
        st.info("Keine Einträge.")
    else:
        def slot_key(s: str):
            m = SLOT_RE.match(str(s))
            return (int(m.group(2)), int(m.group(3))) if m else (99, 99)

        df["KW"] = df["Date"].apply(lambda d: pd.Timestamp(d).isocalendar().week)
        df["Jahr"] = df["Date"].apply(lambda d: pd.Timestamp(d).isocalendar().year)
        weeks = sorted({(int(r["Jahr"]), int(r["KW"])) for _, r in df.iterrows()})

        today = pd.Timestamp.today().date()
        kw_now  = pd.Timestamp(today).isocalendar().week
        yr_now  = pd.Timestamp(today).isocalendar().year

        if "week_idx" not in st.session_state:
            if (yr_now, kw_now) in weeks:
                st.session_state.week_idx = weeks.index((yr_now, kw_now))
            else:
                future = [i for i, wk in enumerate(weeks) if wk > (yr_now, kw_now)]
                st.session_state.week_idx = future[0] if future else 0

        left, mid, right = st.columns([1, 6, 1])
        prev_disabled = st.session_state.week_idx <= 0
        next_disabled = st.session_state.week_idx >= len(weeks) - 1

        if left.button("◀️ Zurück", use_container_width=True, disabled=prev_disabled):
            st.session_state.week_idx -= 1
        if right.button("Weiter ▶️", use_container_width=True, disabled=next_disabled):
            st.session_state.week_idx += 1

        show_year, show_kw = weeks[st.session_state.week_idx]
        week_df = df[(df["Jahr"] == show_year) & (df["KW"] == show_kw)].copy()
        week_df = week_df.sort_values(["Date", "Slot"], key=lambda c: c.map(slot_key) if c.name=="Slot" else c)

        st.markdown(f"### Kalenderwoche {show_kw}, {show_year}")

        for the_date in sorted(week_df["Date"].unique()):
            day_name = week_df.loc[week_df["Date"] == the_date, "Day"].iloc[0]
            st.markdown(f"**{day_name}, {the_date:%Y-%m-%d}**")
            day_rows = week_df[week_df["Date"] == the_date]
            for _, r in day_rows.iterrows():
                # render players nicely
                plist = r["PlayerList"]
                players_text = " / ".join(plist) if plist else str(r["Players"])
                art = "Einzel" if r["Typ"] == "Einzel" else "Doppel"
                st.markdown(f"- `{r['Slot']}` — *{art}*  \n  {players_text}")
            st.divider()

# --- 👤 Einzelspieler ---
with tab2:
    st.subheader("Einzelspieler – Einsätze")
    all_players = sorted(set([p for plist in df["PlayerList"] for p in plist]))
    sel = st.selectbox("Spieler", options=all_players, index=0 if all_players else None)
    if sel:
        mine = per_player[per_player["Spieler"] == sel].copy()
        mine = mine.rename(columns={"Datum": "Datum", "Tag": "Tag", "Slot": "Slot", "Typ": "Art"})
        if mine.empty:
            st.info("Keine Einsätze gefunden.")
        else:
            st.dataframe(
                mine[["Datum", "Tag", "Art", "Slot", "Partner/Gegner"]],
                use_container_width=True,
                hide_index=True,
                height=460,
            )

# --- 📋 Komplettplan ---
with tab3:
    st.subheader("Komplettplan (alle Einträge)")
    full = df.rename(columns={"Date": "Datum", "Day": "Tag", "Players": "Spieler"})
    st.dataframe(full[["Datum", "Tag", "Slot", "Typ", "Spieler"]], use_container_width=True, hide_index=True)
    csv = full[["Datum", "Tag", "Slot", "Typ", "Spieler"]].to_csv(index=False).encode("utf-8")
    st.download_button("CSV herunterladen", data=csv, file_name="Komplettplan.csv", mime="text/csv")

# --- 💶 Kosten (17,50 €/h korrekt) ---
with tab4:
    st.subheader("Spieler-Kosten (17,50 € pro Platz-Stunde)")
    rows = []
    for _, r in df.iterrows():
        slot = SLOT_RE.match(str(r["Slot"]))
        if not slot:
            continue
        minutes = int(slot.group(4))
        total = (minutes / 60.0) * HOURLY_RATE
        n = 2 if r["Typ"] == "Einzel" else 4
        share = total / n
        for p in r["PlayerList"]:
            rows.append(
                {
                    "Spieler": p,
                    "Datum": r["Date"],
                    "Tag": r["Day"],
                    "Typ": r["Typ"],
                    "Slot": r["Slot"],
                    "Minuten": minutes,
                    "Kosten Slot (€)": round(total, 2),
                    "Anteil Spieler (€)": round(share, 2),
                }
            )
    cost_df = pd.DataFrame(rows)
    if cost_df.empty:
        st.info("Keine Einträge vorhanden.")
    else:
        agg = (
            cost_df.groupby("Spieler", as_index=False)
            .agg(
                Teilnahmen=("Anteil Spieler (€)", "count"),
                Minuten=("Minuten", "sum"),
                Summe=("Anteil Spieler (€)", "sum"),
            )
            .sort_values(["Summe", "Spieler"], ascending=[False, True])
        )
        st.markdown("**Gesamt je Spieler**")
        st.dataframe(agg, use_container_width=True, hide_index=True, height=360)

        st.markdown("—")
        st.markdown("**Details je Einsatz**")
        cost_detail = cost_df.sort_values(["Spieler", "Datum", "Slot"]).rename(columns={"Datum": "Datum", "Tag": "Tag"})
        st.dataframe(cost_detail, use_container_width=True, hide_index=True, height=420)

        csv1 = agg.to_csv(index=False).encode("utf-8")
        st.download_button("Kosten je Spieler – CSV", data=csv1, file_name="Kosten_pro_Spieler.csv", mime="text/csv")

        csv2 = cost_detail.to_csv(index=False).encode("utf-8")
        st.download_button("Kosten je Einsatz – CSV", data=csv2, file_name="Kosten_pro_Einsatz.csv", mime="text/csv")

# --- 🧱 Raster (Herren 40–50–60) ---
with tab5:
    st.subheader("Herren 40–50–60 – Rasteransicht")
    st.markdown(
        "Legende:&nbsp; "
        "<span style='background:#1D4ED8;color:#fff;padding:2px 6px;border-radius:6px;'>D20:00-120 PLA</span> "
        "<span style='background:#F59E0B;color:#000;padding:2px 6px;border-radius:6px;'>D20:00-120 PLB</span> "
        "<span style='background:#0EA5E9;color:#000;padding:2px 6px;border-radius:6px;'>E20:00-90 PLA/PLB</span> "
        "<span style='background:#10B981;color:#000;padding:2px 6px;border-radius:6px;'>E18:00-60</span> ",
        unsafe_allow_html=True
    )
    show_raster_aggrid(grid_df)

