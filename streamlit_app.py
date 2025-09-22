import streamlit as st
import pandas as pd
import re
from datetime import date, datetime, timedelta

# -------------------- Basic config --------------------
st.set_page_config(page_title="Wochenplan", layout="wide", initial_sidebar_state="collapsed")

CSV_URL = "https://raw.githubusercontent.com/liamw8lde/Winter-2024_2025-Training-PLan/main/Winterplan.csv"
EDIT_PASSWORD = "tennis"  # protects only the "Plan bearbeiten" tab

# -------------------- Data helpers --------------------
def _postprocess(df: pd.DataFrame):
    required = ["Datum", "Tag", "Slot", "Typ", "Spieler"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}. Expected: {required}")

    for c in required:
        df[c] = df[c].astype(str).str.strip()

    df["Datum_dt"] = pd.to_datetime(df["Datum"], dayfirst=True, errors="coerce")
    iso = df["Datum_dt"].dt.isocalendar()
    df["Jahr"] = iso["year"]
    df["Woche"] = iso["week"]

    # Extract time and court from Slot like "D20:00-120 PLA"
    t = df["Slot"].str.extract(r"^([ED])(\d{2}:\d{2})-([0-9]+)\s+PL([AB])$")
    df["S_Art"] = t[0].fillna("")
    df["S_Time"] = t[1].fillna("00:00")
    df["S_Dur"] = t[2].fillna("0")
    df["S_Court"] = t[3].fillna("")

    # Sort key for times
    df["Startzeit_sort"] = pd.to_datetime(df["S_Time"], format="%H:%M", errors="coerce").dt.time

    # Exploded player view
    df["Spieler_list"] = df["Spieler"].str.split(",").apply(
        lambda xs: [x.strip() for x in xs if str(x).strip()]
    )
    df_exp = df.explode("Spieler_list").rename(columns={"Spieler_list": "Spieler_Name"})
    return df, df_exp

@st.cache_data
def load_csv(url: str):
    return pd.read_csv(url, dtype=str).pipe(_postprocess)

def week_key(df: pd.DataFrame):
    return df["Jahr"].astype(str) + "-W" + df["Woche"].astype(str).str.zfill(2)

def render_week(df: pd.DataFrame, year: int, week: int):
    wk = df[(df["Jahr"] == year) & (df["Woche"] == week)].copy()
    if wk.empty:
        st.info("Keine Einträge in dieser Woche.")
        return
    wk = wk.sort_values(["Datum_dt", "Startzeit_sort", "Slot"])
    st.header(f"Kalenderwoche {week}, {year}")
    for dt, day_df in wk.groupby("Datum_dt"):
        st.subheader(dt.strftime("%A, %Y-%m-%d"))
        for _, r in day_df.iterrows():
            st.markdown(f"- **{r['Slot']}** — *{r['Typ']}*  \n  {r['Spieler']}")

# -------------------- Load data (read-only) --------------------
try:
    df, df_exp = load_csv(CSV_URL)
except Exception as e:
    st.error(f"Datenfehler beim Laden der GitHub-CSV: {e}")
    st.stop()

# ==============================================================
# =================== RULES & CONSTRAINTS ======================
# ==============================================================

# ---- Allowed slots (STRICT) ----
ALLOWED_SLOTS = {
    "Montag": [
        ("D", "20:00", "120", "PLA", "Doppel"),
        ("D", "20:00", "120", "PLB", "Doppel"),
    ],
    "Mittwoch": [
        ("E", "18:00", "60", "PLA", "Einzel"),      # PLB at 18:00 illegal
        ("E", "19:00", "60", "PLA", "Einzel"),
        ("E", "19:00", "60", "PLB", "Einzel"),
        ("D", "20:00", "90", "PLA", "Doppel"),
        ("D", "20:00", "90", "PLB", "Doppel"),
    ],
    "Donnerstag": [
        ("E", "20:00", "90", "PLA", "Einzel"),
        ("E", "20:00", "90", "PLB", "Einzel"),
    ],
}

# ---- Women list (no singles) ----
WOMEN = {"Anke Ihde", "Lena Meiss", "Martina Schmidt", "Kerstin Baarck"}

# ---- Monday core slot (hard) ----
MON_CORE_SLOT = ("Montag", "D", "20:00", "120", "PLA", "Doppel")
MON_CORE_MANDATORY = {"Martin Lange", "Bjoern Junker"}
MON_CORE_POOL = {"Frank Petermann", "Lars Staubermann", "Peter Plaehn"}
MON_CORE_EXCLUDED = {"Mohamad Albadry"}
MON_CORE_LENA_EXCEPTION = ("Lena Meiss", "Liam Wilde")  # Lena allowed only if Liam also plays

# ---- Protected players (hard) ----
def protected_player_ok(name: str, tag: str, s_time: str) -> bool:
    if name == "Patrick Buehrsch":
        return s_time == "18:00"
    if name == "Frank Petermann":
        return s_time in {"19:00", "20:00"}
    if name == "Matthias Duddek":
        return s_time in {"18:00", "19:00"}  # never >= 20:00
    if name == "Dirk Kistner":
        if tag not in {"Montag", "Mittwoch", "Donnerstag"}:
            return False
        if tag == "Mittwoch" and s_time != "19:00":
            return False
        return True
    if name == "Arndt Stueber":
        return tag == "Mittwoch" and s_time == "19:00"
    if name in {"Thommy Grueneberg", "Thomas Grueneberg"}:
        return s_time in {"18:00", "19:00", "20:00"}
    if name == "Jens Hafner":
        return tag == "Mittwoch" and s_time == "19:00"
    return True

# ---- Jotform weekday availability (hard default unless overridden) ----
JOTFORM = {
    "Andreas Dank": {"Montag", "Mittwoch"},
    "Anke Ihde": {"Montag", "Mittwoch", "Donnerstag"},
    "Arndt Stueber": {"Mittwoch"},
    "Bernd Robioneck": {"Mittwoch", "Donnerstag"},
    "Bernd Sotzek": {"Montag", "Mittwoch"},
    "Bjoern Junker": {"Montag"},
    "Carsten Gambal": {"Montag", "Mittwoch", "Donnerstag"},
    "Dirk Kistner": {"Montag", "Mittwoch", "Donnerstag"},
    "Frank Koller": {"Mittwoch", "Donnerstag"},
    "Frank Petermann": {"Montag", "Mittwoch", "Donnerstag"},
    "Gunnar Brix": {"Montag", "Mittwoch", "Donnerstag"},
    "Heiko Thomsen": {"Mittwoch"},
    "Jan Pappenheim": {"Montag", "Mittwoch", "Donnerstag"},
    "Jens Hafner": {"Montag", "Mittwoch"},
    "Jens Krause": {"Mittwoch"},
    "Joerg Peters": {"Mittwoch"},
    "Juergen Hansen": {"Mittwoch"},
    "Kai Schroeder": {"Mittwoch"},
    "Karsten Usinger": {"Mittwoch", "Donnerstag"},
    "Kerstin Baarck": {"Montag", "Donnerstag"},
    "Lars Staubermann": {"Montag", "Donnerstag"},
    "Lena Meiss": {"Montag", "Donnerstag"},
    "Liam Wilde": {"Montag", "Donnerstag"},
    "Lorenz Kramp": {"Montag", "Mittwoch"},
    "Manfred Grell": {"Mittwoch", "Donnerstag"},
    "Markus Muench": {"Mittwoch", "Sonntag"},
    "Martin Lange": {"Montag"},
    "Martina Schmidt": {"Montag", "Mittwoch", "Donnerstag"},
    "Matthias Duddek": {"Montag", "Mittwoch", "Donnerstag"},
    "Michael Bock": {"Montag", "Mittwoch"},
    "Michael Rabehl": {"Montag", "Donnerstag"},
    "Mohamad Albadry": {"Montag"},
    "Oliver Boess": {"Mittwoch", "Donnerstag"},
    "Patrick Buehrsch": {"Mittwoch", "Donnerstag"},
    "Peter Plaehn": {"Montag"},
    "Ralf Colditz": {"Mittwoch"},
    "Sebastian Braune": {"Montag", "Donnerstag"},
    "Thomas Bretschneider": {"Donnerstag"},
    "Thomas Grueneberg": {"Mittwoch", "Donnerstag"},
    "Tobias Kahl": {"Montag", "Mittwoch"},
    "Torsten Bartel": {"Montag", "Mittwoch", "Donnerstag"},
    "Wolfgang Aleksik": {"Mittwoch"},
}

# ---- Ranks ----
RANK = {
    "Andreas Dank": 5, "Anke Ihde": 6, "Arndt Stueber": 4, "Bernd Robioneck": 4, "Bernd Sotzek": 3,
    "Bjoern Junker": 1, "Carsten Gambal": 4, "Dirk Kistner": 5, "Frank Koller": 4, "Frank Petermann": 2,
    "Gunnar Brix": 6, "Heiko Thomsen": 4, "Jan Pappenheim": 5, "Jens Hafner": 6, "Jens Krause": 2,
    "Joerg Peters": 2, "Juergen Hansen": 3, "Kai Schroeder": 4, "Karsten Usinger": 5, "Kerstin Baarck": 6,
    "Lars Staubermann": 2, "Lena Meiss": 6, "Liam Wilde": 2, "Lorenz Kramp": 4, "Manfred Grell": 4,
    "Markus Muench": 5, "Martin Lange": 2, "Martina Schmidt": 6, "Matthias Duddek": 3, "Michael Bock": 6,
    "Michael Rabehl": 6, "Mohamad Albadry": 5, "Oliver Boess": 3, "Patrick Buehrsch": 1, "Peter Plaehn": 2,
    "Ralf Colditz": 4, "Sebastian Braune": 6, "Thomas Bretschneider": 2, "Thomas Grueneberg": 2,
    "Tobias Kahl": 5, "Torsten Bartel": 5, "Wolfgang Aleksik": 6
}

# ---- Weekly/Season caps ----
WEEKLY_CAPS = {"Tobias Kahl": 1, "Dirk Kistner": 2, "Torsten Bartel": 1}
SEASON_CAPS = {"Torsten Bartel": 5, "Frank Petermann": 12}

# ---- Global blackouts (any year) ----
BLACKOUT_MMDD = {(12, 24), (12, 25), (12, 31)}

# ---- Holidays (authoritative) ----
RAW_HOLIDAYS = """
Andreas Dank: 2015-12-24 → 2015-12-26; 2015-12-31 → 2016-01-01.
Anke Ihde: 2025-09-25.
Arndt Stueber: 2025-10-16 → 2025-11-03; 2025-11-13 → 2025-11-24; 2025-12-11 → 2025-12-31.
Bernd Robioneck: 2025-12-01 → 2025-12-08; 2025-12-22 → 2026-01-04.
Bernd Sotzek: 2025-01-01 → 2026-01-04.
Bjoern: 2025-10-25; 2025-10-31; 2025-12-20; 2025-12-31.
Bjoern Junker: 2025-10-25 → 2025-10-31; 2025-12-20 → 2025-12-31.
Carsten Gambal: 2025-09-29 → 2025-10-10; 2025-11-12 → 2025-11-13; 2025-12-24 → 2026-01-01.
Dirk Kistner: 2025-09-18 → 2025-09-22; 2025-10-02; 2025-10-30; 2025-12-22 → 2025-12-31.
Frank Koller: 2025-10-10 → 2025-10-31; 2025-12-18 → 2026-01-05.
Frank Petermann: 2025-09-08 → 2025-09-14; 2025-10-13 → 2025-10-25; 2025-12-01 → 2025-12-07; 2025-12-24; 2025-12-31.
Gunnar Brix: 2025-09-01 → 2025-09-26; 2025-10-06 → 2025-10-11; 2025-10-20 → 2025-10-25; 2025-11-17 → 2025-11-22; 2025-12-22 → 2025-12-31.
Heiko Thomsen: 2025-09-15 → 2025-10-10; 2025-11-12; 2025-12-03; 2025-12-17; 2025-12-22 → 2025-12-26; 2025-12-31.
Jan Pappenheim: 
Jens Hafner: 2025-10-23 → 2025-11-02; 2025-12-24 → 2025-12-26.
Jens Krause: 2025-09-24 → 2025-09-24.
Joerg: 2025-12-22; 2026-01-02.
Joerg Peters: 2025-12-22 → 2026-01-02.
Juergen: 2025-12-22; 2026-01-04.
Juergen Hansen: 2025-12-22 → 2026-01-04.
Kai Schroeder: 2025-10-06 → 2025-10-12; 2025-12-01 → 2025-12-06; 2025-12-22 → 2025-12-27; 2026-01-19 → 2026-01-31.
Karsten: 2025-11-12 → 2025-11-13; 2025-12-24; 2025-12-29.
Karsten Usinger: 2025-09-01 → 2025-11-03; 2025-12-22 → 2025-12-29; 2025-12-31.
Kerstin Baarck: 2025-09-01 → 2025-10-31.
Lars Staubermann: 2025-10-06 → 2025-10-26; 2026-03-23 → 2026-04-12.
Lena Meiss: 2025-01-01 → 2025-09-20; 2025-10-01 → 2025-10-31.
Liam Wilde: 2025-12-24.
Lorenz Kramp: 2025-10-04 → 2025-10-24.
Manfred Grell: 2025-09-22; 2025-10-06.
Markus Muench: 2025-10-13 → 2025-10-19; 2025-12-22 → 2026-01-04.
Martin Lange: 2025-12-22 → 2026-01-04.
Martina Schmidt: 2025-11-08 → 2025-11-22; 2026-01-01.
Matthias Duddek: 2025-11-04 → 2025-11-10; 2025-12-24 → 2025-12-31.
Meiss: 2025-01-01 → 2025-09-20.
Michael Bock: 2025-12-20 → 2026-01-04.
Michael Rabehl: 2025-10-09 → 2025-10-12.
Mohamad Albadry: 
Muench: 2025-10-13; 2025-10-19; 2025-12-22; 2026-01-04.
Oliver Boess: 2025-09-01 → 2025-09-30; 2025-12-01 → 2025-12-07; 2025-12-24 → 2025-12-25.
Patrick Buehrsch: 2025-11-01 → 2025-11-30.
Peter Plaehn: 
Ralf Colditz: 2025-09-08 → 2025-09-30; 2025-12-22 → 2026-01-03.
Schroeder: 2025-10-06; 2025-10-12; 2025-12-01; 2025-12-06; 2025-12-22; 2025-12-27.
Sebastian Braune: 2025-10-20 → 2025-10-30; 2025-12-28 → 2026-01-06.
Stueber: 2025-10-16; 2025-10-31; 2025-11-17; 2025-11-23; 2025-12-15; 2025-12-31.
Thomas Bretschneider: 
Thomas Grueneberg: 
Tobias Kahl: 2025-09-01 → 2025-09-14; 2025-09-23 → 2025-10-09; 2025-10-20 → 2025-10-31; 2025-12-22 → 2025-12-31.
Torsten Bartel: 2025-09-15 → 2025-09-24; 2025-09-29 → 2025-10-15; 2025-10-20 → 2025-10-23; 2025-10-29 → 2025-11-19; 2025-11-24 → 2025-12-17; 2025-12-22 → 2025-12-25.
Wolfgang Aleksik: 2025-09-01 → 2025-09-16; 2025-09-18 → 2025-10-14; 2025-10-16 → 2025-10-21; 2025-10-23 → 2025-11-04; 2025-11-06 → 2025-11-11; 2025-11-13 → 2025-11-25; 2025-11-27 → 2025-12-09; 2025-12-11 → 2025-12-31.
"""

def parse_holidays(raw: str):
    out = {}
    for line in raw.strip().splitlines():
        if not line.strip():
            continue
        name, rest = line.split(":", 1)
        name = name.strip()
        periods = []
        for chunk in re.split(r"[;.\s]+", rest.strip()):
            if not chunk:
                continue
            if "→" in chunk:
                s, e = [x.strip() for x in chunk.split("→")]
                try:
                    sd = datetime.strptime(s, "%Y-%m-%d").date()
                    ed = datetime.strptime(e, "%Y-%m-%d").date()
                    periods.append((sd, ed))
                except:
                    pass
            else:
                try:
                    d = datetime.strptime(chunk.strip(), "%Y-%m-%d").date()
                    periods.append((d, d))
                except:
                    pass
        if periods:
            out[name] = out.get(name, []) + periods
    return out

HOLIDAYS = parse_holidays(RAW_HOLIDAYS)

def is_holiday(name: str, d: date) -> bool:
    if (d.month, d.day) in {(12, 24), (12, 25), (12, 31)}:
        return True
    ranges = HOLIDAYS.get(name, [])
    return any(start <= d <= end for (start, end) in ranges)

# ---- Monday PLA core check ----
def check_monday_core(row_players: list, d: date):
    players = set(row_players)
    violations = []

    missing = [p for p in MON_CORE_MANDATORY if p not in players]
    missing_not_on_holiday = [p for p in missing if not is_holiday(p, d)]
    if missing_not_on_holiday:
        violations.append(f"mon_pla_core: Fehlend ohne Urlaub: {', '.join(missing_not_on_holiday)}")

    others = players - MON_CORE_MANDATORY
    allowed_set = MON_CORE_POOL | {MON_CORE_LENA_EXCEPTION[0], MON_CORE_LENA_EXCEPTION[1]}
    if not others.issubset(allowed_set):
        bad = others - allowed_set
        if bad:
            violations.append(f"mon_pla_core: Unzulässige Spieler: {', '.join(sorted(bad))}")

    if MON_CORE_LENA_EXCEPTION[0] in players and MON_CORE_LENA_EXCEPTION[1] not in players:
        violations.append("mon_pla_core: Lena Meiss nur erlaubt, wenn Liam Wilde mitspielt.")

    women_here = players & (WOMEN - {MON_CORE_LENA_EXCEPTION[0]})
    if women_here:
        violations.append(f"mon_pla_core: Frauen unzulässig: {', '.join(sorted(women_here))}")

    if "Mohamad Albadry" in players:
        violations.append("mon_pla_core: Mohamad Albadry unzulässig.")

    if not missing_not_on_holiday:
        pool_count = len(players & MON_CORE_POOL)
        if pool_count != 2 or len(players) != 4:
            violations.append("mon_pla_core: Belegung muss aus {Martin, Bjoern} + genau zwei aus {Frank, Lars, Peter} bestehen.")

    return violations

# ---- Week coverage check (STRICT) ----
def weekly_coverage_violations(df_week: pd.DataFrame):
    v = []
    for tag, reqs in ALLOWED_SLOTS.items():
        for (art, tm, dur, court, typ) in reqs:
            mask = (
                (df_week["Tag"] == tag) &
                (df_week["S_Art"] == art) &
                (df_week["S_Time"] == tm) &
                (df_week["S_Dur"] == dur) &
                (df_week["S_Court"] == court) &
                (df_week["Typ"] == typ)
            )
            cnt = int(mask.sum())
            if cnt != 1:
                v.append(f"weekly_coverage: {tag} {art}{tm}-{dur} {court} {typ} erscheint {cnt}× (erwartet 1×).")
    return v

# ---- Allowed slot check for a single row ----
def allowed_slot_ok(row) -> bool:
    reqs = ALLOWED_SLOTS.get(row["Tag"], [])
    return any(
        row["S_Art"] == a and row["S_Time"] == t and row["S_Dur"] == d and row["S_Court"] == c and row["Typ"] == ty
        for (a, t, d, c, ty) in reqs
    )

# ---- Global time rules ----
def global_time_violations(row):
    v = []
    if row["S_Time"] > "20:00":
        v.append("global_time: Start nach 20:00 unzulässig.")
    if row["Tag"] == "Mittwoch" and row["S_Art"] == "D":
        if not (row["S_Time"] == "20:00" and row["S_Dur"] == "90"):
            v.append("global_time: Mi-Doppel muss 20:00 für 90min sein.")
    if not allowed_slot_ok(row):
        v.append("global_time: Slot stimmt nicht exakt mit erlaubtem Code überein.")
    return v

# ---- Women singles ----
def women_singles_violation(row_players: list, row_typ: str) -> list:
    if row_typ.lower().startswith("einzel"):
        if any(p in WOMEN for p in row_players):
            return ["womens_singles: Frauen dürfen kein Einzel spielen."]
    return []

# ---- One-per-day ----
def one_per_day_violations(df_plan: pd.DataFrame, d: date):
    v = []
    day_df = df_plan[df_plan["Datum_dt"].dt.date == d]
    counts = {}
    for _, r in day_df.iterrows():
        for p in [x.strip() for x in r["Spieler"].split(",") if x.strip()]:
            counts[p] = counts.get(p, 0) + 1
    for p, c in counts.items():
        if c > 1:
            v.append(f"one_per_day: {p} ist {c}× am {d} eingetragen.")
    return v

# ---- Caps ----
def caps_violations(df_plan: pd.DataFrame, y: int, w: int):
    v = []
    week_df = df_plan[(df_plan["Jahr"] == y) & (df_plan["Woche"] == w)]
    all_rows = df_plan
    for name, cap in WEEKLY_CAPS.items():
        cnt = week_df["Spieler"].str.contains(fr"\b{re.escape(name)}\b", regex=True).sum()
        if cnt > cap:
            v.append(f"weekly_cap: {name} > {cap}/Woche ({cnt}).")
    for name, cap in SEASON_CAPS.items():
        cnt = all_rows["Spieler"].str.contains(fr"\b{re.escape(name)}\b", regex=True).sum()
        if cnt > cap:
            v.append(f"season_cap: {name} > {cap}/Saison ({cnt}).")
    return v

# ---- Jotform availability (hard default unless overridden by protected rule) ----
def availability_violations(row_tag: str, row_players: list, s_time: str):
    v = []
    for p in row_players:
        allowed_days = JOTFORM.get(p)
        if allowed_days is not None and row_tag not in allowed_days:
            v.append(f"availability: {p} ist laut Jotform nicht für {row_tag} verfügbar.")
        if not protected_player_ok(p, row_tag, s_time):
            v.append(f"protected: {p} verletzt Schutzregel ({row_tag} {s_time}).")
    return v

# ---- Singles rank window (hard) & doubles balance (advisory) ----
def rank_violations(row_players: list, typ: str):
    hard = []
    advisory = []
    ranks = [RANK.get(p) for p in row_players if p in RANK]
    if typ.lower().startswith("einzel"):
        if len(row_players) == 2 and all(r is not None for r in ranks):
            if abs(ranks[0] - ranks[1]) > 2:
                hard.append("singles_rank_window: Rangdifferenz > 2.")
    elif typ.lower().startswith("doppel"):
        if len(ranks) == 4 and all(r is not None for r in ranks):
            r = sorted(ranks)
            similar_quartet = (r[-1] - r[0] <= 2)
            two_vs_two = (r[1] - r[0] <= 1) and (r[3] - r[2] <= 1) and (r[2] - r[1] >= 2)
            if not (similar_quartet or two_vs_two):
                advisory.append("doubles_unbalanced_advisory: Rangverteilung ungünstig.")
    return hard, advisory

def week_frame(df_plan: pd.DataFrame, y: int, w: int):
    return df_plan[(df_plan["Jahr"] == y) & (df_plan["Woche"] == w)]

def plan_violations(df_plan: pd.DataFrame, focus_day: date):
    v_hard = []
    v_advice = []
    mmdd = (focus_day.month, focus_day.day)
    if mmdd in BLACKOUT_MMDD:
        v_hard.append(f"blackout: {focus_day} ist gesperrt (global).")

    iso = pd.Timestamp(focus_day).isocalendar()
    y, w = int(iso.year), int(iso.week)
    week_df = week_frame(df_plan, y, w)

    v_hard += weekly_coverage_violations(week_df)
    v_hard += caps_violations(df_plan, y, w)
    v_hard += one_per_day_violations(df_plan, focus_day)

    for _, r in week_df.iterrows():
        row_players = [x.strip() for x in r["Spieler"].split(",") if x.strip()]
        v_hard += [f"{r['Tag']} {r['Slot']}: {msg}" for msg in global_time_violations(r)]
        v_hard += [f"{r['Tag']} {r['Slot']}: {msg}" for msg in women_singles_violation(row_players, r["Typ"])]
        v_hard += [f"{r['Tag']} {r['Slot']}: {msg}" for msg in availability_violations(r["Tag"], row_players, r["S_Time"])]
        hard, adv = rank_violations(row_players, r["Typ"])
        v_hard += [f"{r['Tag']} {r['Slot']}: {msg}" for msg in hard]
        v_advice += [f"{r['Tag']} {r['Slot']}: {msg}" for msg in adv]
        if (r["Tag"], r["S_Art"], r["S_Time"], r["S_Dur"], r["S_Court"], r["Typ"]) == MON_CORE_SLOT:
            v_hard += [f"{r['Tag']} {r['Slot']}: {msg}" for msg in check_monday_core(row_players, r["Datum_dt"].date())]

    return sorted(set(v_hard)), sorted(set(v_advice))

# ================ Password helper for editor tab ================
def check_edit_password() -> bool:
    if st.session_state.get("edit_ok", False):
        return True
    with st.form("edit_login"):
        st.write("🔒 Editieren erfordert ein Passwort.")
        pw = st.text_input("Passwort", type="password")
        ok = st.form_submit_button("Login")
        if ok:
            if pw == EDIT_PASSWORD:
                st.session_state.edit_ok = True
                st.rerun()
            else:
                st.error("Falsches Passwort.")
    return False

# ==============================================================
# =========================  UI  ===============================
# ==============================================================

tab1, tab2, tab3 = st.tabs(["Wochenplan", "Spieler-Matches", "Plan bearbeiten"])

with tab1:
    weeks_df = (
        df.dropna(subset=["Datum_dt"])
          .assign(WeekKey=week_key)
          .sort_values(["Jahr", "Woche", "Datum_dt"])
    )
    wk_keys = weeks_df["WeekKey"].unique().tolist()
    if not wk_keys:
        st.warning("Keine Wochen gefunden.")
    else:
        if "wk_idx" not in st.session_state:
            st.session_state.wk_idx = len(wk_keys) - 1
        col_prev, col_next = st.columns(2)
        if col_prev.button("◀️ Woche zurück"):
            st.session_state.wk_idx = max(0, st.session_state.wk_idx - 1)
        if col_next.button("Woche vor ▶️"):
            st.session_state.wk_idx = min(len(wk_keys) - 1, st.session_state.wk_idx + 1)
        st.session_state.wk_idx = max(0, min(st.session_state.wk_idx, len(wk_keys) - 1))
        sel = wk_keys[st.session_state.wk_idx]
        year = int(sel.split("-W")[0]); week = int(sel.split("-W")[1])
        render_week(df, year, week)

with tab2:
    st.header("Spieler-Matches")
    players = sorted(p for p in df_exp["Spieler_Name"].dropna().unique().tolist() if str(p).strip())
    sel_players = st.multiselect("Spieler wählen", options=players)
    if sel_players:
        pf = df_exp[df_exp["Spieler_Name"].isin(sel_players)].copy()
        pf = pf.sort_values(["Datum_dt", "Startzeit_sort", "Slot"])
        for p in sel_players:
            st.metric(p, int((pf["Spieler_Name"] == p).sum()))
        st.dataframe(pf[["Spieler_Name", "Datum", "Tag", "Slot", "Typ", "Spieler"]], use_container_width=True)
    else:
        st.info("Bitte Spieler auswählen.")

# ----------------- Plan bearbeiten (protected) -----------------
def split_players(s: str):
    return [x.strip() for x in str(s).split(",") if str(x).strip()]

def join_players(lst):
    return ", ".join(lst)

def swap_players_in_row(row, a_name, b_name):
    players = split_players(row["Spieler"])
    for i, p in enumerate(players):
        if p == a_name:
            players[i] = b_name
        elif p == b_name:
            players[i] = a_name
    row["Spieler"] = join_players(players)
    return row

with tab3:
    st.header("Plan bearbeiten – geschützter Bereich")
    if not check_edit_password():
        st.stop()

    if "df_edit" not in st.session_state:
        st.session_state.df_edit = df.copy()

    df_edit = st.session_state.df_edit

    # Choose day
    valid_days = sorted(df_edit["Datum_dt"].dropna().dt.date.unique())
    if not valid_days:
        st.warning("Keine Daten vorhanden."); st.stop()
    sel_day = st.date_input("Tag auswählen", value=valid_days[-1])
    day_df = df_edit[df_edit["Datum_dt"].dt.date.eq(sel_day)].copy()
    if day_df.empty:
        st.info("Für diesen Tag gibt es keine Einträge."); st.stop()

    # Pick two matches
    day_df = day_df.reset_index(drop=True)
    day_df["Label"] = day_df.apply(lambda r: f"{r['Slot']} — {r['Typ']} — {r['Spieler']}", axis=1)
    idx_a = st.selectbox("Match A", options=day_df.index.tolist(), format_func=lambda i: day_df.loc[i, "Label"])
    idx_b = st.selectbox("Match B", options=day_df.index.tolist(), format_func=lambda i: day_df.loc[i, "Label"])

    row_a = day_df.loc[idx_a]
    row_b = day_df.loc[idx_b]

    pA = st.selectbox("Spieler aus Match A", split_players(row_a["Spieler"]))
    pB = st.selectbox("Spieler aus Match B", split_players(row_b["Spieler"]))

    # Enforce same type; court equality optional
    same_type_required = True
    same_court_required = False

    # ---- Build hypothetical plan after swap ----
    df_after = df_edit.copy()
    mask_a = (
        (df_after["Datum_dt"] == row_a["Datum_dt"]) &
        (df_after["Slot"] == row_a["Slot"]) &
        (df_after["Typ"] == row_a["Typ"]) &
        (df_after["Spieler"] == row_a["Spieler"])
    )
    mask_b = (
        (df_after["Datum_dt"] == row_b["Datum_dt"]) &
        (df_after["Slot"] == row_b["Slot"]) &
        (df_after["Typ"] == row_b["Typ"]) &
        (df_after["Spieler"] == row_b["Spieler"])
    )
    if mask_a.any():
        df_after.loc[mask_a] = df_after.loc[mask_a].apply(lambda r: swap_players_in_row(r, pA, pB), axis=1)
    if mask_b.any():
        df_after.loc[mask_b] = df_after.loc[mask_b].apply(lambda r: swap_players_in_row(r, pA, pB), axis=1)

    # ---- Rules summary ABOVE the button ----
    with st.expander("Regeln (HARD/STRICT) – Übersicht", expanded=True):
        st.markdown(
            """
- **Allowed slots (STRICT):** nur die vorgegebenen Slots (Wochentag + Code + Platz + Dauer) sind gültig.  
- **Weekly coverage (STRICT):** jede erlaubte Slot-Kombi muss **genau 1× pro ISO-Woche** vorkommen.
- **Global time (HARD):** kein Start **nach 20:00**; Mi-Doppel **20:00 / 90 min**; Slot muss exakt passen.
- **Protected Players (HARD):** z. B. Patrick **nur 18:00**, Jens Hafner **nur Mi 19:00**, Arndt **nur Mi 19:00**, Dirk mit Sonderregeln (Mo/Mi/Do; Mi nur 19:00; max 2/Woche), etc.
- **Women & Singles (HARD):** Anke, Lena, Martina, Kerstin **kein Einzel**.
- **Mo Kernslot D20:00–120 PLA (HARD):** immer **Martin Lange** & **Bjoern Junker** (außer Urlaub); die anderen 2 nur aus {Frank Petermann, Lars Staubermann, Peter Plaehn}.  
  Keine Frauen (Ausnahme: **Lena nur mit Liam**), **Mohamad nie**, keine externen Ersatzspieler.
- **One-per-day (HARD):** niemand spielt **mehr als 1× pro Datum**.
- **Caps (HARD):** z. B. Tobias Kahl ≤1/Woche; Dirk ≤2/Woche; Torsten Bartel ≤1/Woche & ≤5/Saison; Frank Petermann ≤12/Saison.
- **Holidays/Blackouts (HARD):** 24.12/25.12/31.12 gesperrt; Urlaube gemäß Liste. Mo-PLA-Kernslot: Urlaubsausnahme für Kern-Vier (Caps gelten trotzdem).
- **Ranks:** Einzel **|Δrank| ≤ 2 (HARD)**; Doppel-Balance Hinweis (advisory).
            """
        )

    # ---- Validate full ruleset for the week containing sel_day ----
    def per_row_checks(r):
        v = []
        # keep swapped rows within type/court constraints relative to their original rows
        # (simple guard; full legality is handled by global checks)
        if same_type_required and r["Typ"] not in {row_a["Typ"], row_b["Typ"]}:
            v.append("swap_rule: Unterschiedlicher Match-Typ.")
        if same_court_required and r["S_Court"] not in {row_a["S_Court"], row_b["S_Court"]}:
            v.append("swap_rule: Unterschiedlicher Platz (PLA/PLB).")
        return v

    hard, advice = plan_violations(df_after, sel_day)
    rowA_after = df_after[mask_a].iloc[0]
    rowB_after = df_after[mask_b].iloc[0]
    hard += [f"{rowA_after['Tag']} {rowA_after['Slot']}: {m}" for m in per_row_checks(rowA_after)]
    hard += [f"{rowB_after['Tag']} {rowB_after['Slot']}: {m}" for m in per_row_checks(rowB_after)]

    # ---- Violations above the button ----
    if hard:
        st.error("Regelverletzungen:")
        for m in sorted(set(hard)):
            st.write("•", m)
    if advice:
        st.warning("Hinweise (advisory):")
        for m in sorted(set(advice)):
            st.write("•", m)

    # ========== OVERRIDE CONTROLS ==========
    st.markdown("---")
    override_mode = st.toggle("🔧 Regeln übersteuern (Admin)", value=False, help="Nur verwenden, wenn die Abweichung dokumentiert werden soll.")
    override_reason = ""
    override_confirm = False
    if override_mode:
        override_reason = st.text_area("Begründung für die Übersteuerung (Pflicht)", placeholder="Warum ist dieser Tausch trotz Regelverletzung notwendig?")
        override_confirm = st.checkbox("Ich bestätige die bewusste Regel-Übersteuerung und akzeptiere die Konsequenzen.", value=False)

    # Enabled if: (no hard + confirm) OR (override on + reason + confirm)
    confirm_no_override = st.checkbox("Ich bestätige, dass die obigen Regeln eingehalten werden.", value=not bool(hard) and not override_mode)
    can_swap_without_override = (not hard) and confirm_no_override and not override_mode
    can_swap_with_override = override_mode and bool(override_reason.strip()) and override_confirm
    btn_disabled = not (can_swap_without_override or can_swap_with_override)

    if st.button("🔁 Spieler tauschen", disabled=btn_disabled):
        if override_mode and not can_swap_without_override:
            if "override_log" not in st.session_state:
                st.session_state["override_log"] = []
            st.session_state["override_log"].append({
                "timestamp": pd.Timestamp.utcnow().isoformat(),
                "date": str(sel_day),
                "match_A_before": f"{row_a['Tag']} {row_a['Slot']} — {row_a['Typ']} — {row_a['Spieler']}",
                "match_B_before": f"{row_b['Tag']} {row_b['Slot']} — {row_b['Typ']} — {row_b['Spieler']}",
                "player_swap": f"{pA} ↔ {pB}",
                "hard_violations": sorted(set(hard)),
                "advisories": sorted(set(advice)),
                "reason": override_reason.strip(),
            })
        st.session_state.df_edit = df_after
        st.success(f"Getauscht: {pA} ↔ {pB}")

    if st.session_state.get("override_log"):
        with st.expander("📜 Override-Audit (letzte 10)", expanded=False):
            for entry in st.session_state["override_log"][-10:][::-1]:
                st.markdown(
                    f"- **{entry['timestamp']}** — {entry['date']} — {entry['player_swap']}  \n"
                    f"  Grund: _{entry['reason']}_  \n"
                    f"  Hard: {len(entry['hard_violations'])} | Hinweise: {len(entry['advisories'])}"
                )

    # Preview edited day + export/reset
    st.subheader("Vorschau – Tagesplan nach Tausch")
    preview = df_after[df_after["Datum_dt"].dt.date.eq(sel_day)].sort_values(["Datum_dt","Startzeit_sort","Slot"])
    st.dataframe(preview[["Datum","Tag","Slot","Typ","Spieler"]], use_container_width=True)

    c1, c2 = st.columns(2)
    if c1.button("↩️ Änderungen verwerfen (Reset)"):
        st.session_state.df_edit = df.copy()
        st.rerun()
    csv_bytes = df_after[["Datum","Tag","Slot","Typ","Spieler"]].to_csv(index=False).encode("utf-8")
    c2.download_button("⬇️ Geänderten Plan als CSV herunterladen", data=csv_bytes,
                       file_name="winter_training_updated.csv", mime="text/csv")
