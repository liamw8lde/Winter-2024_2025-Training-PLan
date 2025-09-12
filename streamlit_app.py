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
GH_RAW_DEFAULT = "https://github.com/liamw8lde/Winter-2024_2025-Training-PLan/blob/main/trainplan.xlsx"  # <-- anpassen
gh_raw_url = st.sidebar.text_input(
    "GitHub RAW URL (optional)",
    value="",
    placeholder=GH_RAW_DEFAULT,
)
SOURCE_URL = gh_raw_url.strip() or GH_RAW_DEFAULT


# ---------- Loader ----------
@st.cache_data(show_spinner=True)
def fetch_bytes(url: str) -> bytes:
    if not url.startswith("http"):
        # Falls lokal geladen werden soll, kann man hier eine Datei öffnen.
        # Für Streamlit Cloud wird typischerweise die RAW-URL genutzt.
        raise ValueError("Bitte eine GitHub RAW URL angeben.")
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

    # Normalisiere PlayerList (Liste der Namen je Zeile)
    def to_list(s):
        return [x.strip() for x in str(s).split("/") if str(x).strip()]

    df["PlayerList"] = df["Players"].apply(to_list)
    # Einheitliches Sortieren (Datum, Startzeit)
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

# --- 🗓️ Wochenplan (aktuelle KW zuerst) ---
with tab1:
    st.subheader("Wochenplan (aktuelle Kalenderwoche zuerst)")
    if df.empty:
        st.info("Keine Einträge.")
    else:
        df["KW"] = df["Date"].apply(lambda d: pd.Timestamp(d).isocalendar().week)
        df["Jahr"] = df["Date"].apply(lambda d: pd.Timestamp(d).isocalendar().year)

        # Aktuelle KW ermitteln
        today = pd.Timestamp.today().date()
        kw_now = pd.Timestamp(today).isocalendar().week
        jahr_now = pd.Timestamp(today).isocalendar().year

        # verfügbare KWs (Jahr, KW) sortiert
        kws = sorted({(int(r["Jahr"]), int(r["KW"])) for _, r in df.iterrows()})
        # Vorauswahl: aktuelle KW falls vorhanden, sonst die nächste/fürheste
        if (jahr_now, kw_now) in kws:
            preselect = (jahr_now, kw_now)
        else:
            # nächste KW größer als heute oder fallback auf kleinste
            future = [x for x in kws if (x[0] > jahr_now or (x[0] == jahr_now and x[1] >= kw_now))]
            preselect = future[0] if future else kws[0]

        # Anzeige
        show_year, show_kw = preselect
        week_df = df[(df["Jahr"] == show_year) & (df["KW"] == show_kw)].copy()
        week_df = week_df[["Date", "Day", "Slot", "Typ", "Players"]].rename(
            columns={"Date": "Datum", "Day": "Tag", "Players": "Spieler"}
        )
        st.markdown(f"**Kalenderwoche {show_kw}, {show_year}**")
        st.dataframe(week_df, use_container_width=True, hide_index=True, height=420)

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

    # pro Einsatz aufsplitten
    rows = []
    for _, r in df.iterrows():
        slot = SLOT_RE.match(str(r["Slot"]))
        if not slot:
            continue
        minutes = int(slot.group(4))
        kind = slot.group(1).upper()
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
    st.dataframe(grid_df, use_container_width=True, hide_index=True, height=520)

    csv_grid = grid_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Raster als CSV herunterladen",
        data=csv_grid,
        file_name="Herren_40-50-60_Raster.csv",
        mime="text/csv",
    )

