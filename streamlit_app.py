# streamlit_app.py
# ------------------------------------------------------------
# Winter-Training – Viewer (Deutsch)
# Tabs: Wochenplan (KW-Ansicht), Einzelspieler, Komplettplan,
#       Kosten (17,50 €/h korrekt umgelegt), Raster (Herren 40–50–60)
# Notes:
#  - Sidebar removed (hard-hidden)
#  - Datenquelle ist fest im Code verdrahtet (keine UI-Eingabe)
#  - "Details je Einsatz" in Kosten entfernt (nur Summen je Spieler + CSV)
#  - Farb-Codes gemäß Mapping, inkl. getrennten Farben für D20:00 PLA/PLB
# ------------------------------------------------------------
import io
import re
import json
import requests
import pandas as pd
import streamlit as st
from datetime import date
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

# ---------- Seite / Layout ----------
st.set_page_config(
    page_title="Winter-Training Herren 40–50–60",
    page_icon="🎾",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Sidebar hart ausblenden (inkl. Toggle)
st.markdown(
    """
    <style>
      [data-testid="stSidebar"] { display: none !important; }
      [data-testid="stSidebarCollapsedControl"] { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Konstanten ----------
HOURLY_RATE = 17.50  # € pro Stunde (Platzmiete)
SLOT_RE = re.compile(r"^([DE])(\d{2}):(\d{2})-([0-9]+)\s+PL([AB])$", re.IGNORECASE)

# ---------- Datenquelle ----------
# Hard-coded GitHub RAW URL (kein UI-Eingabefeld)
SOURCE_URL = "https://raw.githubusercontent.com/liamw8lde/Winter-2024_2025-Training-PLan/main/trainplan_FIXED.xlsx"

# ---------- Loader ----------
@st.cache_data(show_spinner=True)
def fetch_bytes(url: str) -> bytes:
    if not url.startswith("http"):
        raise ValueError("Bitte eine gültige GitHub RAW URL im Code hinterlegen.")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.content

@st.cache_data(show_spinner=False)
def load_plan(url: str) -> pd.DataFrame:
    """
    Läd bevorzugt das Blatt 'Spielplan'.
    Fallback: extrahiert aus dem Raster 'Herren 40–50–60' alle belegten Slots.
    Gibt immer Spalten zurück: Date, Day, Slot, Typ, Players, PlayerList
    """
    data = fetch_bytes(url)
    xio = io.BytesIO(data)

    # 1) Versuch: "Spielplan"
    try:
        df = pd.read_excel(xio, sheet_name="Spielplan")
        cols = {c.lower(): c for c in df.columns}
        df = df.rename(
            columns={
                cols.get("datum", "Datum"): "Date",
                cols.get("tag", "Tag"): "Day",
                cols.get("slot", "Slot"): "Slot",
                cols.get("spieler", "Spieler"): "Players",
                cols.get("typ", "Typ" if "Typ" in df.columns else cols.get("art", "Typ")): "Typ",
            }
        )
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
        if "Typ" not in df:
            df["Typ"] = df["Slot"].apply(lambda s: "Einzel" if str(s).startswith("E") else "Doppel")
    except Exception:
        # 2) Fallback aus dem Raster
        xio.seek(0)
        grid = pd.read_excel(xio, sheet_name="Herren 40–50–60", header=[1], dtype=str)
        grid = grid.rename(columns={grid.columns[0]: "Date", grid.columns[1]: "Day"})
        grid["Date"] = pd.to_datetime(grid["Date"], errors="coerce").dt.date
        players = list(grid.columns[2:])
        rows = []
        for _, r in grid.iterrows():
            dd = r["Date"]
            day = r["Day"]
            for p in players:
                code = str(r.get(p, "") or "").strip()
                if SLOT_RE.match(code):
                    rows.append(
                        {
                            "Date": dd,
                            "Day": day,
                            "Slot": code,
                            "Typ": "Einzel" if code.startswith("E") else "Doppel",
                            "Players": p,
                        }
                    )
        df = pd.DataFrame(rows)

    def to_list(s):
        return [x.strip() for x in str(s).split("/") if str(x).strip()]

    df["PlayerList"] = df["Players"].apply(to_list)

    def slot_key(s):
        m = SLOT_RE.match(str(s))
        if not m:
            return (99, 99)
        return (int(m.group(2)), int(m.group(3)))  # hh, mm

    df = df.sort_values(["Date", "Slot"], key=lambda col: col.map(slot_key) if col.name == "Slot" else col)
    return df

@st.cache_data(show_spinner=False)
def load_grid(url: str) -> pd.DataFrame:
    """
    Liest das Blatt 'Herren 40–50–60' (Kopfzeile = zweite Zeile im Excel).
    Gibt Datum/Tag + Spieler-Spalten zurück.
    """
    data = fetch_bytes(url)
    xio = io.BytesIO(data)
    grid = pd.read_excel(xio, sheet_name="Herren 40–50–60", header=[1], dtype=str)
    grid = grid.rename(columns={grid.columns[0]: "Datum", grid.columns[1]: "Tag"})
    grid["Datum"] = pd.to_datetime(grid["Datum"], errors="coerce").dt.strftime("%Y-%m-%d")
    # Spieler-Spalten in ursprünglicher Reihenfolge belassen:
    player_cols = [c for c in grid.columns if c not in ("Datum", "Tag")]
    grid = grid[["Datum", "Tag"] + player_cols]
    return grid

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

# Farbpalette analog "Legende" (gültige Slots)
PALETTE = {
    "D20:00-120 PLA": "1D4ED8",
    "D20:00-120 PLB": "F59E0B",
    "D20:00-90 PLA":  "6D28D9",
    "D20:00-90 PLB":  "C4B5FD",
    "E18:00-60 PLA":  "10B981",
    "E19:00-60 PLA":  "14B8A6",
    "E19:00-60 PLB":  "14B8A6",
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

  // quick luminance approx for text color
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
        cellStyle= CELLSTYLE
    )
    gb.configure_column("Datum", pinned="left", width=120)
    gb.configure_column("Tag",   pinned="left", width=110)

    # kleinere Spaltenbreite für Spieler-Zellen
    for col in grid_df.columns[2:]:
        gb.configure_column(col, width=150)

    go = gb.build()
    AgGrid(
        grid_df,
        gridOptions=go,
        allow_unsafe_jscode=True,   # needed for custom cellStyle
        fit_columns_on_grid_load=False,
        height=560,
        theme="balham"              # clean, kontrastreich
    )

# ---------- Daten laden ----------
try:
    df = load_plan(SOURCE_URL)
    grid_df = load_grid(SOURCE_URL)
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

# --- 🗓️ Wochenplan (Buttons, kein DataFrame) ---
with tab1:
    st.subheader("Wochenplan")

    if df.empty:
        st.info("Keine Einträge.")
    else:
        def slot_key(s: str):
            m = SLOT_RE.match(str(s))
            if not m:
                return (99, 99)
            return (int(m.group(2)), int(m.group(3)))  # hh, mm

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
                players_text = (
                    r["Players"] if "/" in str(r["Players"]) else " / ".join(r["PlayerList"])
                )
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

    # pro Einsatz aufsplitten (nur für Aggregation)
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
        # Nur Aggregation je Spieler anzeigen
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

        # Nur CSV der Aggregation anbieten
        csv1 = agg.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Kosten je Spieler – CSV",
            data=csv1,
            file_name="Kosten_pro_Spieler.csv",
            mime="text/csv",
        )

# --- 🧱 Raster (Herren 40–50–60) ---
with tab5:
    st.subheader("Herren 40–50–60 – Rasteransicht")
    # kleine Legende
    st.markdown(
        "Legende:&nbsp; "
        "<span style='background:#1D4ED8;color:#fff;padding:2px 6px;border-radius:6px;'>D20:00-120 PLA</span> "
        "<span style='background:#F59E0B;color:#000;padding:2px 6px;border-radius:6px;'>D20:00-120 PLB</span> "
        "<span style='background:#6D28D9;color:#fff;padding:2px 6px;border-radius:6px;'>D20:00-90 PLA</span> "
        "<span style='background:#C4B5FD;color:#000;padding:2px 6px;border-radius:6px;'>D20:00-90 PLB</span> "
        "<span style='background:#10B981;color:#000;padding:2px 6px;border-radius:6px;'>E18:00-60 PLA</span> "
        "<span style='background:#14B8A6;color:#000;padding:2px 6px;border-radius:6px;'>E19:00-60 PLA/PLB</span> "
        "<span style='background:#0EA5E9;color:#000;padding:2px 6px;border-radius:6px;'>E20:00-90 PLA/PLB</span> ",
        unsafe_allow_html=True
    )
    show_raster_aggrid(grid_df)

