# streamlit_app.py
# A modern viewer for your winter training plan (no editing).
# - Reads the Excel workbook you publish (Spielplan or the grid).
# - Clean filters: player, day, date range, singles/doubles.
# - "My schedule" tab + ICS download.
# - Uses Legende sheet for slot colors; has a sensible fallback palette.

import io, re, unicodedata, requests
from datetime import datetime, timedelta, date
from collections import defaultdict

import pandas as pd
import streamlit as st
from dateutil import tz

st.set_page_config(page_title="🎾 Winter-Training – Plan", layout="wide")

# ---------------------------- helpers ----------------------------

SLOT_RE = re.compile(r"^([DE])(\d{2}):(\d{2})-([0-9]+)\s+PL([AB])$", re.IGNORECASE)

def norm(s):
    s = str(s or "").strip()
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    return re.sub(r"\s+"," ",s)

def to_dt(d):
    # normalize Excel dates/strings -> pd.Timestamp(date)
    try:
        t = pd.to_datetime(d)
        # keep date only
        return pd.Timestamp(t.date())
    except Exception:
        return pd.NaT

def parse_slot(code):
    """
    D20:00-120 PLA  -> (type='D', start='20:00', minutes=120, court='PLA')
    """
    m = SLOT_RE.match(str(code or ""))
    if not m: return None
    typ = m.group(1).upper()
    hh = int(m.group(2)); mm = int(m.group(3))
    minutes = int(m.group(4))
    court = m.group(5).upper()
    return {"type": typ, "hh": hh, "mm": mm, "minutes": minutes, "court": court}

FALLBACK_COLORS = {
    'D20:00-120 PLA':'1D4ED8','D20:00-120 PLB':'F59E0B',
    'D20:30-90 PLA':'6D28D9','D20:30-90 PLB':'C4B5FD',
    'E18:00-60 PLA':'10B981','E19:00-60 PLA':'14B8A6','E19:00-60 PLB':'14B8A6',
    'E20:00-90 PLA':'0EA5E9','E20:00-90 PLB':'0EA5E9',
    'E20:30-90 PLA':'10B981','E20:30-90 PLB':'10B981'
}

def read_palette_from_legende(xls_bytes):
    try:
        df = pd.read_excel(io.BytesIO(xls_bytes), sheet_name="Legende")
    except Exception:
        return {}
    ex_col=col_col=None
    for c in df.columns:
        lc=str(c).lower()
        if ('slot' in lc) or ('beispiel' in lc) or ('code' in lc): ex_col=c
        if ('farbe' in lc) or ('hex' in lc): col_col=c
    out={}
    if ex_col and col_col:
        for _,row in df.iterrows():
            code = str(row[ex_col]).strip() if pd.notna(row[ex_col]) else ''
            colv = str(row[col_col]).strip() if pd.notna(row[col_col]) else ''
            if code and SLOT_RE.match(code):
                hex6 = colv.replace('#','').upper()
                if re.fullmatch(r"[0-9A-F]{6}", hex6 or ""):
                    out[code]=hex6
    return out

def make_badge(text, hex6):
    # small rounded color chip used in list view
    tc = "#fff" if _lum(hex6) < 0.55 else "#111"
    return f"""<span style="display:inline-block;background:#{hex6};color:{tc};
               padding:2px 8px;border-radius:12px;font-size:12px;font-weight:600">
               {text}</span>"""

def _lum(hex6):
    r=int(hex6[0:2],16)/255; g=int(hex6[2:4],16)/255; b=int(hex6[4:6],16)/255
    return 0.2126*r + 0.7152*g + 0.0722*b

def slot_to_timeslot(d: pd.Timestamp, code: str, tzname="Europe/Berlin"):
    """Return (dt_start, dt_end) aware datetimes from date + slot code."""
    p = parse_slot(code)
    if not p: return None, None
    start = datetime(d.year, d.month, d.day, p["hh"], p["mm"], tzinfo=tz.gettz(tzname))
    end   = start + timedelta(minutes=p["minutes"])
    return start, end

def to_ics(events, cal_name="Winter Training"):
    # events: list of dicts with start, end (aware datetimes), summary, description, location
    def dtfmt(dt): return dt.astimezone(tz.UTC).strftime("%Y%m%dT%H%M%SZ")
    out = []
    out.append("BEGIN:VCALENDAR")
    out.append("VERSION:2.0")
    out.append(f"PRODID:-//WinterTraining//streamlit//EN")
    out.append(f"X-WR-CALNAME:{cal_name}")
    for ev in events:
        out.append("BEGIN:VEVENT")
        out.append(f"DTSTART:{dtfmt(ev['start'])}")
        out.append(f"DTEND:{dtfmt(ev['end'])}")
        out.append(f"SUMMARY:{ev['summary']}")
        if ev.get("description"): out.append(f"DESCRIPTION:{ev['description']}")
        if ev.get("location"): out.append(f"LOCATION:{ev['location']}")
        out.append("END:VEVENT")
    out.append("END:VCALENDAR")
    return "\r\n".join(out).encode("utf-8")

# --------------------------- data loading ---------------------------

@st.cache_data(show_spinner=False)
def load_excel_from_source(source_type, file=None, url=None):
    if source_type == "Upload":
        xls = file.read()
        name = file.name
    else:
        r = requests.get(url)
        r.raise_for_status()
        xls = r.content
        name = url.split("/")[-1]
    # Spielplan first
    try:
        df_sp = pd.read_excel(io.BytesIO(xls), sheet_name="Spielplan")
        if {"Datum","Tag","Slot","Spieler"}.issubset(df_sp.columns):
            df_sp = df_sp.rename(columns={"Datum":"Date","Tag":"Day","Slot":"Slot","Spieler":"Players","Typ":"Typ"})
    except Exception:
        df_sp = None

    # If no Spielplan, attempt to build from grid "Herren 40–50–60"
    if df_sp is None:
        df_grid = pd.read_excel(io.BytesIO(xls), sheet_name="Herren 40–50–60", header=[1])
        # Expect first two columns = Datum, Tag
        df_grid = df_grid.rename(columns={df_grid.columns[0]:"Date", df_grid.columns[1]:"Day"})
        players = [c for c in df_grid.columns[2:]]
        rows=[]
        for _,row in df_grid.iterrows():
            d = to_dt(row["Date"])
            day = str(row["Day"])
            for p in players:
                code = str(row.get(p,"") or "").strip()
                if SLOT_RE.match(code):
                    rows.append({"Date":d, "Day":day, "Slot":code, "Players":p, "Typ":"Einzel" if code.startswith("E") else "Doppel"})
        df_sp = pd.DataFrame(rows)
    # Normalize
    df_sp["Date"] = df_sp["Date"].apply(to_dt)
    df_sp["Typ"]  = df_sp.get("Typ", pd.Series(["Doppel" if str(s).startswith("D") else "Einzel" for s in df_sp["Slot"]]))
    # Expand Players into rows
    out=[]
    for _,r in df_sp.iterrows():
        plist = [p.strip() for p in str(r["Players"]).split("/") if p.strip()]
        out.append({**r, "PlayerList": plist})
    df_sp = pd.DataFrame(out)
    return xls, df_sp, name

# ------------------------------ UI ---------------------------------

st.title("🎾 Winter-Training – Online Plan")
st.caption("Schöner Überblick für alle Spieler:innen – mit Filtern, Suche und persönlichem Kalender-Export.")

with st.sidebar:
    st.header("Datenquelle")
    source = st.radio("Wo liegt der Plan?", ["Upload", "GitHub/URL"], horizontal=True)
    file = url = None
    if source == "Upload":
        file = st.file_uploader("Excel hochladen (.xlsx)", type=["xlsx"])
    else:
        url = st.text_input("Excel URL (z.B. GitHub raw URL)")
    st.divider()
    st.header("Filter")
    picked_players = st.multiselect("Spieler auswählen (optional)", [], placeholder="Alle")
    day_filter = st.multiselect("Wochentage", ["Montag","Mittwoch","Donnerstag"], default=["Montag","Mittwoch","Donnerstag"])
    typ_filter = st.multiselect("Art", ["Einzel","Doppel"], default=["Einzel","Doppel"])
    date_from = st.date_input("Von", value=None)
    date_to   = st.date_input("Bis", value=None)

if (source == "Upload" and file) or (source == "GitHub/URL" and url):
    try:
        xls_bytes, df_sp, source_name = load_excel_from_source(source, file=file, url=url)
    except Exception as e:
        st.error(f"Konnte Datei nicht laden: {e}")
        st.stop()

    # palette
    palette = {**FALLBACK_COLORS, **read_palette_from_legende(xls_bytes)}
    # players list for sidebar (update options)
    all_players = sorted(sorted({p for lst in df_sp["PlayerList"] for p in lst}), key=lambda s:norm(s).lower())
    if not picked_players:
        with st.sidebar:
            st.session_state.setdefault("players_loaded", True)
            st.multiselect("Spieler auswählen (optional)", all_players, key="players_dummy", disabled=True)

    # Apply filters
    df = df_sp.copy()
    if picked_players:
        df = df[df["PlayerList"].apply(lambda L: any(p in L for p in picked_players))]
    if day_filter:
        df = df[df["Day"].isin(day_filter)]
    if typ_filter:
        df = df[df["Typ"].isin(typ_filter)]
    if date_from:
        df = df[df["Date"] >= pd.Timestamp(date_from)]
    if date_to:
        df = df[df["Date"] <= pd.Timestamp(date_to)]

    # ---------- TABS ----------
    tab1, tab2, tab3, tab4 = st.tabs(["📅 Übersicht", "👤 Mein Spielplan", "🎨 Legende", "📄 Tabelle"])

    with tab1:
        st.subheader("Übersicht")
        # Group by date, render nice list with colored slot badges
        for d, grp in df.sort_values(["Date","Slot"]).groupby("Date"):
            st.markdown(f"### {d.date().strftime('%a, %d.%m.%Y')}")
            for _,r in grp.iterrows():
                slot = r["Slot"]
                hex6 = palette.get(slot, "6B7280")
                badge = make_badge(slot, hex6)
                players = " · ".join(r["PlayerList"])
                st.markdown(f"{badge} &nbsp; **{r['Typ']}** — {players}", unsafe_allow_html=True)
            st.markdown("---")

    with tab2:
        st.subheader("Mein Spielplan")
        me = st.selectbox("Spieler auswählen", all_players)
        me_df = df_sp[df_sp["PlayerList"].apply(lambda L: me in L)].sort_values(["Date","Slot"])
        st.write(f"Gefundene Termine: **{len(me_df)}**")
        # upcoming
        today = pd.Timestamp(date.today())
        upcoming = me_df[me_df["Date"] >= today].head(6)
        if len(upcoming):
            st.markdown("**Nächste Spiele**")
            for _,r in upcoming.iterrows():
                slot = r["Slot"]; typ = r["Typ"]; day = r["Day"]; d = r["Date"].date().strftime("%a, %d.%m.%Y")
                start, end = slot_to_timeslot(r["Date"], slot)
                hhmm = start.strftime("%H:%M") if start else "?"
                st.write(f"- {d} · {day} · {hhmm} · {typ} · {slot}")
        # ICS export
        if st.button("📥 Als Kalender (.ics) exportieren"):
            events=[]
            for _,r in me_df.iterrows():
                start, end = slot_to_timeslot(r["Date"], r["Slot"])
                if start and end:
                    others = [p for p in r["PlayerList"] if p != me]
                    events.append({
                        "start": start, "end": end,
                        "summary": f"{r['Typ']} – {r['Slot']}",
                        "description": f"Gegner/Mitspieler: {', '.join(others)}",
                        "location": "Halle"
                    })
            ics = to_ics(events, cal_name=f"Winter Training – {me}")
            st.download_button("💾 iCal herunterladen", data=ics,
                               file_name=f"winter_training_{norm(me).replace(' ','_')}.ics",
                               mime="text/calendar")

        st.markdown("—")
        st.dataframe(me_df[["Date","Day","Slot","Typ","Players"]].rename(columns={"Date":"Datum","Day":"Tag","Players":"Spieler"}),
                     use_container_width=True, height=380)

    with tab3:
        st.subheader("Farblegende")
        leg_rows = []
        for code, hex6 in sorted(palette.items()):
            leg_rows.append({"Slot": code, "Farbe": f"#{hex6}"})
        leg = pd.DataFrame(leg_rows)
        st.dataframe(leg, use_container_width=True, height=380)
        # visual chips
        st.markdown("#### Vorschau")
        chip_html = " ".join(make_badge(k, v) for k,v in sorted(palette.items()))
        st.markdown(chip_html, unsafe_allow_html=True)

    with tab4:
        st.subheader(f"Gesamttabelle – Quelle: {source_name}")
        df_show = df_sp[["Date","Day","Slot","Typ","Players"]].rename(columns={"Date":"Datum","Day":"Tag","Players":"Spieler"})
        st.dataframe(df_show.sort_values(["Datum","Slot"]), use_container_width=True, height=600)

else:
    st.info("🔼 Bitte lade die Excel hoch **oder** gib die GitHub-Raw-URL an, dann erscheinen die Ansichten hier.")
