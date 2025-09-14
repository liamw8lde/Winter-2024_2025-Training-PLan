# streamlit_app.py
# ------------------------------------------------------------
# Winter-Training – Viewer (Deutsch)
# Tabs: Wochenplan (KW-Ansicht), Einzelspieler, Komplettplan,
#       Kosten (17,50 €/h korrekt umgelegt), Raster (Herren 40–50–60)
# Requirements:
#  - Sidebar entfernt/ausgeblendet
#  - XLSX-Quelle fest im Code (keine Uploads/Eingaben)
#  - Passwortschutz: "TGR2025"
#  - Kosten: KEINE "Details je Einsatz"-Tabelle/CSV
#  - Farbpalette exakt lt. Vorgabe
# ------------------------------------------------------------
import io
import re
import json
import unicodedata
import requests
import pandas as pd
import streamlit as st
from datetime import date
from collections import Counter, defaultdict
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

# ---------- Seite / Layout ----------
st.set_page_config(
    page_title="Winter-Training Herren 40–50–60",
    page_icon="🎾",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Sidebar & Toggle vollständig ausblenden
st.markdown(
    """
<style>
  [data-testid="stSidebar"] { display: none !important; }
  [data-testid="stSidebarCollapsedControl"] { display: none !important; }
</style>
""",
    unsafe_allow_html=True,
)

# ---------- Security ----------
PASSWORD = "TGR2025"
if "auth_ok" not in st.session_state:
    st.session_state.auth_ok = False

if not st.session_state.auth_ok:
    st.title("Winter-Training Herren 40–50–60")
    pw = st.text_input("🔒 Passwort eingeben, um die Daten zu sehen", type="password")
    if st.button("Anmelden", use_container_width=True):
        if pw == PASSWORD:
            st.session_state.auth_ok = True
            st.rerun()
        else:
            st.error("Falsches Passwort.")
    st.stop()

# ---------- Konstanten ----------
HOURLY_RATE = 17.50  # € pro Platzstunde
SLOT_RE = re.compile(r"^([DE])(\d{2}):(\d{2})-([0-9]+)\s+PL([AB])$", re.IGNORECASE)

# Farbpalette (exakt lt. Vorgabe)
PALETTE = {
    "D20:00-120 PLA": "1D4ED8",
    "D20:00-120 PLB": "F59E0B",
    "D20:00-90 PLA":  "6D28D9",
    "D20:00-90 PLB":  "C4B5FD",
    "E18:00-60 PLA":  "10B981",
    "E19:00-60 PLA":  "14B8A6",
    "E19:00-60 PLB":  "2DD4BF",
    "E20:00-90 PLA":  "0EA5E9",
    "E20:00-90 PLB":  "38BDF8",
}

# ---------- Datenquelle ----------
# Fest verdrahtete RAW-URL (keine UI-Steuerung)
SOURCE_URL = "https://raw.githubusercontent.com/liamw8lde/Winter-2024_2025-Training-PLan/main/trainplan_FIXED.xlsx"

# ---------- Loader ----------
@st.cache_data(show_spinner=True)
def fetch_bytes(url: str) -> bytes:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.content

def _rename_like(df: pd.DataFrame, new_map: dict) -> pd.DataFrame:
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
    """Robuster Split (Umlaut/NBSP/verschiedene Trenner)."""
    s = str(value or "")
    s = s.replace("\xa0", " ")  # NBSP -> space
    # split on &, /, "vs", newlines, semicolons, em/en-dash
    s = re.sub(r"\s*[&/]\s*|\s+vs\s+|[\n;]\s*|[–—]\s*", ", ", s, flags=re.IGNORECASE)
    parts = [p.strip() for p in s.split(",") if p.strip()]
    # de-dupe preserving order
    seen, out = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p); out.append(p)
    return out

def _slot_sort_key(series: pd.Series) -> pd.Series:
    def slot_key(s):
        m = SLOT_RE.match(str(s))
        return (int(m.group(2)), int(m.group(3))) if m else (99, 99)
    return series.map(slot_key)

@st.cache_data(show_spinner=False)
def load_plan(url: str) -> pd.DataFrame:
    """
    Lädt bevorzugt 'Spielplan'. Fallback: extrahiert aus 'Herren 40–50–60'.
    Gibt Spalten: Date, Day, Slot, Typ, Players, PlayerList
    """
    data = fetch_bytes(url)
    xio = io.BytesIO(data)

    # 1) Spielplan laden
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
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
        if "Typ" not in df.columns:
            df["Typ"] = df["Slot"].apply(lambda s: "Einzel" if str(s).startswith("E") else "Doppel")
        df["PlayerList"] = df["Players"].apply(_parse_player_list)
        df = df.sort_values(["Date", "Slot"], key=lambda s: _slot_sort_key(s) if s.name == "Slot" else s)
        return df[["Date", "Day", "Slot", "Typ", "Players", "PlayerList"]]
    except Exception:
        pass

    # 2) Fallback: Raster ("Herren 40–50–60")
    def try_load_grid_header(xio_obj, header_row):
        xio_obj.seek(0)
        return pd.read_excel(xio_obj, sheet_name="Herren 40–50–60", header=header_row, dtype=str)

    grid = None
    for hdr in (1, 0):  # erst header=[1] (Titelzeile), dann fallback header=0
        try:
            grid = try_load_grid_header(xio, hdr)
            break
        except Exception:
            continue
    if grid is None:
        return pd.DataFrame(columns=["Date","Day","Slot","Typ","Players","PlayerList"])

    grid = grid.rename(columns={grid.columns[0]: "Date", grid.columns[1]: "Day"})
    grid["Date"] = pd.to_datetime(grid["Date"], errors="coerce").dt.date
    player_cols = [c for c in grid.columns[2:] if c not in (None, "")]

    rows = []
    for _, r in grid.iterrows():
        dd = r["Date"]; day = r["Day"]
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
    df = df.sort_values(["Date", "Slot"], key=lambda s: _slot_sort_key(s) if s.name == "Slot" else s)
    return df[["Date", "Day", "Slot", "Typ", "Players", "PlayerList"]]

@st.cache_data(show_spinner=False)
def load_grid(url: str) -> pd.DataFrame:
    data = fetch_bytes(url)
    xio = io.BytesIO(data)

    def try_load(header_row):
        xio.seek(0)
        return pd.read_excel(xio, sheet_name="Herren 40–50–60", header=header_row, dtype=str)

    grid = None
    for hdr in (1, 0):
        try:
            grid = try_load(hdr)
            break
        except Exception:
            continue

    if grid is None or grid.shape[1] < 2:
        return pd.DataFrame(columns=["Datum", "Tag"])

    grid = grid.rename(columns={grid.columns[0]: "Datum", grid.columns[1]: "Tag"})
    grid["Datum"] = pd.to_datetime(grid["Datum"], errors="coerce").dt.strftime("%Y-%m-%d")
    player_cols = [c for c in grid.columns if c not in ("Datum", "Tag")]
    return grid[["Datum", "Tag"] + player_cols]

# ---------- Namens-Normalisierung ----------
NAME_DIACRITICS = "äöüß"

def normalize_name(s: str) -> str:
    s = (s or "").replace("\xa0", " ")
    # remove zero-width & control chars
    s = "".join(ch for ch in s if (ord(ch) >= 32 and ch not in "\u200b\u200c\u200d\uFEFF"))
    s = unicodedata.normalize("NFKD", s).lower().strip()
    s = s.replace("ä","ae").replace("ö","oe").replace("ü","ue").replace("ß","ss")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s)
    return s


def build_name_map(all_names: list[str]) -> dict:
    by_key = defaultdict(Counter)
    for n in all_names:
        by_key[normalize_name(n)][n] += 1

    def pick_display(counter: Counter) -> str:
        # bevorzugt Varianten mit ä/ö/ü/ß; sonst häufigste Schreibweise
        with_diac = [n for n in counter if any(ch in NAME_DIACRITICS for ch in n)]
        pool = with_diac or list(counter)
        return sorted(pool, key=lambda n: (-counter[n], n))[0]

    return {k: pick_display(cnt) for k, cnt in by_key.items()}

# ---------- Daten laden ----------
try:
    df = load_plan(SOURCE_URL)
    grid_df = load_grid(SOURCE_URL)
except Exception as e:
    st.error(f"Plan konnte nicht geladen werden.\n\nFehler: {e}")
    st.stop()

# Build canonical display names based on what exists in the plan
_all_raw = [p for plist in df["PlayerList"] for p in plist]
NAME_MAP = build_name_map(_all_raw)

def expand_per_player(df_plan: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in df_plan.iterrows():
        plist = r["PlayerList"]
        for p in plist:
            key = normalize_name(p)
            disp = NAME_MAP.get(key, p)
            others = [x for x in plist if x != p]
            rows.append(
                {
                    "SpielerKey": key,
                    "Spieler": disp,  # display-friendly
                    "Datum": r["Date"],
                    "Tag": r["Day"],
                    "Typ": r["Typ"],
                    "Slot": r["Slot"],
                    "Partner/Gegner": " / ".join(others),
                }
            )
    return pd.DataFrame(rows)

per_player = expand_per_player(df)

# Kosten-Grundlage (einmal berechnen, mehrfach nutzen)
def build_cost_rows(df_plan: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in df_plan.iterrows():
        m = SLOT_RE.match(str(r["Slot"]))
        if not m:
            continue
        minutes = int(m.group(4))
        total = (minutes / 60.0) * HOURLY_RATE
        n = 2 if r["Typ"] == "Einzel" else 4
        share = total / n
        for p in r["PlayerList"]:
            rows.append(
                {
                    "Spieler": p,
                    "SpielerKey": normalize_name(p),
                    "Datum": r["Date"],
                    "Tag": r["Day"],
                    "Typ": r["Typ"],
                    "Slot": r["Slot"],
                    "Minuten": minutes,
                    "Kosten Slot (€)": round(total, 2),
                    "Anteil Spieler (€)": round(share, 2),
                }
            )
    return pd.DataFrame(rows)

cost_df = build_cost_rows(df)

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
        df["KW"] = df["Date"].apply(lambda d: pd.Timestamp(d).isocalendar().week)
        df["Jahr"] = df["Date"].apply(lambda d: pd.Timestamp(d).isocalendar().year)
        weeks = sorted({(int(r["Jahr"]), int(r["KW"])) for _, r in df.iterrows()})

        today = pd.Timestamp.today().date()
        kw_now = pd.Timestamp(today).isocalendar().week
        yr_now = pd.Timestamp(today).isocalendar().year

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
        week_df = week_df.sort_values(["Date", "Slot"], key=lambda s: _slot_sort_key(s) if s.name == "Slot" else s)

        st.markdown(f"### Kalenderwoche {show_kw}, {show_year}")

        for the_date in sorted(week_df["Date"].unique()):
            day_name = week_df.loc[week_df["Date"] == the_date, "Day"].iloc[0]
            st.markdown(f"**{day_name}, {the_date:%Y-%m-%d}**")
            day_rows = week_df[week_df["Date"] == the_date]
            for _, r in day_rows.iterrows():
                plist = r["PlayerList"]
                players_text = " / ".join(plist) if plist else str(r["Players"])
                art = "Einzel" if r["Typ"] == "Einzel" else "Doppel"
                st.markdown(f"- `{r['Slot']}` — *{art}*  \n  {players_text}")
            st.divider()

# --- 👤 Einzelspieler ---
with tab2:
    st.subheader("Einzelspieler – Einsätze")
    if per_player.empty:
        st.info("Keine Einsätze gefunden.")
    else:
        all_keys = sorted(per_player["SpielerKey"].unique())
        options = [NAME_MAP.get(k, k.title()) for k in all_keys]
        key_by_display = {NAME_MAP.get(k, k.title()): k for k in all_keys}

        # Try to start on "Kai Schröder" if present, else first
        default_disp = "Kai Schröder" if "Kai Schröder" in options else options[0]
        sel_disp = st.selectbox("Spieler", options=options, index=options.index(default_disp))
        sel_key = key_by_display[sel_disp]

        mine = per_player[per_player["SpielerKey"] == sel_key].copy()
        # Mini-Kosten-Übersicht (ohne Details-Tabelle)
        if not cost_df.empty:
            mc = cost_df[cost_df["SpielerKey"] == sel_key]
            a, b, c = st.columns(3)
            a.metric("Einsätze", f"{int(mc.shape[0])}")
            b.metric("Minuten", f"{int(mc['Minuten'].sum())}")
            c.metric("Summe", f"{float(mc['Anteil Spieler (€)'].sum()):,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))

        if mine.empty:
            st.info("Keine Einsätze gefunden.")
        else:
            st.dataframe(
                mine[["Datum", "Tag", "Typ", "Slot", "Partner/Gegner"]].rename(columns={"Typ": "Art"}),
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
    if cost_df.empty:
        st.info("Keine Einträge vorhanden.")
    else:
        agg = (
            cost_df.groupby(["SpielerKey"], as_index=False)
            .agg(
                Teilnahmen=("Anteil Spieler (€)", "count"),
                Minuten=("Minuten", "sum"),
                Summe=("Anteil Spieler (€)", "sum"),
            )
        )
        # hübsche Anzeige-Namen aus NAME_MAP
        agg["Spieler"] = agg["SpielerKey"].map(lambda k: NAME_MAP.get(k, k.title()))
        agg = agg[["Spieler", "Teilnahmen", "Minuten", "Summe"]].sort_values(["Summe", "Spieler"], ascending=[False, True])

        st.markdown("**Gesamt je Spieler**")
        st.dataframe(agg, use_container_width=True, hide_index=True, height=360)

        # Nur CSV der Aggregation (KEINE Detailtabelle/CSV)
        csv1 = agg.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Kosten je Spieler – CSV",
            data=csv1,
            file_name="Kosten_pro_Spieler.csv",
            mime="text/csv",
        )

# --- 🧱 Raster (Herren 40–50–60) ---
CELLSTYLE = JsCode(
    f"""
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
"""
)

def show_raster_aggrid(grid_df: pd.DataFrame):
    gb = GridOptionsBuilder.from_dataframe(grid_df)
    gb.configure_default_column(
        resizable=True,
        wrapText=True,
        autoHeight=True,
        cellStyle=CELLSTYLE,
    )
    gb.configure_column("Datum", pinned="left", width=120)
    gb.configure_column("Tag", pinned="left", width=110)
    for col in grid_df.columns[2:]:
        gb.configure_column(col, width=150)
    go = gb.build()
    AgGrid(
        grid_df,
        gridOptions=go,
        allow_unsafe_jscode=True,
        fit_columns_on_grid_load=False,
        height=560,
        theme="balham",
    )

with tab5:
    st.subheader("Herren 40–50–60 – Rasteransicht")
    st.markdown(
        "Legende:&nbsp; "
        "<span style='background:#1D4ED8;color:#fff;padding:2px 6px;border-radius:6px;'>D20:00-120 PLA</span> "
        "<span style='background:#F59E0B;color:#000;padding:2px 6px;border-radius:6px;'>D20:00-120 PLB</span> "
        "<span style='background:#6D28D9;color:#fff;padding:2px 6px;border-radius:6px;'>D20:00-90 PLA</span> "
        "<span style='background:#C4B5FD;color:#000;padding:2px 6px;border-radius:6px;'>D20:00-90 PLB</span> "
        "<span style='background:#10B981;color:#000;padding:2px 6px;border-radius:6px;'>E18:00-60 PLA</span> "
        "<span style='background:#14B8A6;color:#000;padding:2px 6px;border-radius:6px;'>E19:00-60 PLA</span> "
        "<span style='background:#2DD4BF;color:#000;padding:2px 6px;border-radius:6px;'>E19:00-60 PLB</span> "
        "<span style='background:#0EA5E9;color:#000;padding:2px 6px;border-radius:6px;'>E20:00-90 PLA</span> "
        "<span style='background:#38BDF8;color:#000;padding:2px 6px;border-radius:6px;'>E20:00-90 PLB</span> ",
        unsafe_allow_html=True,
    )
    show_raster_aggrid(grid_df)

