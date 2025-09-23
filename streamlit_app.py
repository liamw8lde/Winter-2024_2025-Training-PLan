import streamlit as st
import pandas as pd
import re
import base64, json, requests
from datetime import date, datetime

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

    # Extract from Slot like "D20:00-120 PLA"
    t = df["Slot"].str.extract(r"^([ED])(\d{2}:\d{2})-([0-9]+)\s+PL([AB])$")
    df["S_Art"]   = t[0].fillna("")
    df["S_Time"]  = t[1].fillna("00:00")
    df["S_Dur"]   = t[2].fillna("0")
    df["S_Court"] = t[3].fillna("")

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
# =============== RULE SOURCES (HARD where stated) =============
# ==============================================================

# ---- Jotform weekday availability ----
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

# ---- Player Ranks (1 strongest ... 6 weakest) ----
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

# ---- Global blackouts (any year) ----
BLACKOUT_MMDD = {(12, 24), (12, 25), (12, 31)}

# ---- Holidays list ----
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
    if (d.month, d.day) in BLACKOUT_MMDD:
        return True
    ranges = HOLIDAYS.get(name, [])
    return any(start <= d <= end for (start, end) in ranges)

# -------------------- Rank & protected helpers --------------------
WOMEN_SINGLE_BAN = {"Anke Ihde", "Lena Meiss", "Martina Schmidt", "Kerstin Baarck"}

def week_of(d: date):
    iso = pd.Timestamp(d).isocalendar()
    return int(iso.year), int(iso.week)

def count_week(df_plan: pd.DataFrame, name: str, d: date) -> int:
    y, w = week_of(d)
    wk = df_plan[(df_plan["Jahr"] == y) & (df_plan["Woche"] == w)]
    return int(wk["Spieler"].str.contains(fr"\b{re.escape(name)}\b", regex=True).sum())

def count_season(df_plan: pd.DataFrame, name: str) -> int:
    return int(df_plan["Spieler"].str.contains(fr"\b{re.escape(name)}\b", regex=True).sum())

def count_wed20(df_plan: pd.DataFrame, name: str) -> int:
    mask = (
        (df_plan["Tag"] == "Mittwoch") &
        (df_plan["S_Time"] == "20:00") &
        (df_plan["Spieler"].str.contains(fr"\b{re.escape(name)}\b", regex=True))
    )
    return int(mask.sum())

def count_18_19(df_plan: pd.DataFrame, name: str) -> int:
    mask = (
        (df_plan["S_Time"].isin(["18:00", "19:00"])) &
        (df_plan["Spieler"].str.contains(fr"\b{re.escape(name)}\b", regex=True))
    )
    return int(mask.sum())

def protected_player_violations(name: str, tag: str, s_time: str, typ: str,
                                df_after: pd.DataFrame, d: date):
    v = []
    # slot/time/day rules
    if name == "Patrick Buehrsch" and s_time != "18:00":
        v.append(f"{name}: nur 18:00 erlaubt.")
    if name == "Frank Petermann" and s_time not in {"19:00", "20:00"}:
        v.append(f"{name}: nur 19:00 oder 20:00 erlaubt.")
    if name == "Matthias Duddek" and s_time not in {"18:00", "19:00"}:
        v.append(f"{name}: nur 18:00 oder 19:00 (nie ≥20:00).")
    if name == "Dirk Kistner":
        if tag not in {"Montag", "Mittwoch", "Donnerstag"}:
            v.append(f"{name}: nur Mo/Mi/Do.")
        if tag == "Mittwoch" and s_time != "19:00":
            v.append(f"{name}: am Mittwoch nur 19:00.")
        if count_week(df_after, name, d) > 2:
            v.append(f"{name}: max 2/Woche überschritten.")
    if name == "Arndt Stueber" and not (tag == "Mittwoch" and s_time == "19:00"):
        v.append(f"{name}: nur Mittwoch 19:00.")
    if name in {"Thommy Grueneberg", "Thomas Grueneberg"}:
        total_after = count_season(df_after, name)
        wed20_after = count_wed20(df_after, name)
        early_after = count_18_19(df_after, name)
        if total_after > 0:
            if wed20_after / total_after > 0.30:
                v.append(f"{name}: Anteil Mi 20:00 > 30%.")
            if early_after / total_after < 0.70:
                v.append(f"{name}: Anteil 18/19 < 70%.")
    if name == "Jens Hafner" and not (tag == "Mittwoch" and s_time == "19:00"):
        v.append(f"{name}: nur Mittwoch 19:00.")
    if typ.lower().startswith("einzel") and name in WOMEN_SINGLE_BAN:
        v.append(f"{name}: Frauen dürfen kein Einzel spielen.")
    return v

# ==============================================================
# =================== GitHub commit helpers ====================
# ==============================================================

def _github_headers():
    token = st.secrets.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GitHub token missing in st.secrets['GITHUB_TOKEN'].")
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

def _gh_repo_info():
    repo   = st.secrets.get("GITHUB_REPO")
    branch = st.secrets.get("GITHUB_BRANCH", "main")
    path   = st.secrets.get("GITHUB_PATH", "Winterplan.csv")
    if not repo:
        raise RuntimeError("st.secrets['GITHUB_REPO'] must be set, e.g. 'owner/repo'.")
    return repo, branch, path

def github_get_file_sha(branch_override=None):
    repo, branch, path = _gh_repo_info()
    if branch_override: branch = branch_override
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    params = {"ref": branch}
    r = requests.get(url, headers=_github_headers(), params=params, timeout=20)
    if r.status_code == 200:
        data = r.json()
        return data.get("sha")
    elif r.status_code == 404:
        return None
    else:
        raise RuntimeError(f"GitHub GET failed {r.status_code}: {r.text}")

def github_put_file(csv_bytes: bytes, message: str, branch_override=None):
    repo, branch, path = _gh_repo_info()
    if branch_override: branch = branch_override
    sha = github_get_file_sha(branch)
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    payload = {
        "message": message,
        "content": base64.b64encode(csv_bytes).decode("utf-8"),
        "branch": branch,
        "committer": {
            "name": st.secrets.get("GITHUB_COMMITTER_NAME", "Streamlit App"),
            "email": st.secrets.get("GITHUB_COMMITTER_EMAIL", "no-reply@example.com"),
        },
    }
    if sha:
        payload["sha"] = sha
    r = requests.put(url, headers=_github_headers(), data=json.dumps(payload), timeout=20)
    if r.status_code in (200, 201):
        return r.json()
    raise RuntimeError(f"GitHub PUT failed {r.status_code}: {r.text}")

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

def replace_player_in_row(row, old_name, new_name):
    players = split_players(row["Spieler"])
    players = [new_name if p == old_name else p for p in players]
    row["Spieler"] = join_players(players)
    return row

def swap_players_in_row(row, a_name, b_name):
    players = split_players(row["Spieler"])
    for i, p in enumerate(players):
        if p == a_name:
            players[i] = b_name
        elif p == b_name:
            players[i] = a_name
    row["Spieler"] = join_players(players)
    return row

def check_min_rules_for_row(row, d: date, df_after: pd.DataFrame):
    """Hard checks: holiday/blackout, weekday availability, protected players, women singles ban."""
    v = []
    players = split_players(row["Spieler"])
    tag = str(row["Tag"])
    s_time = str(row["S_Time"])
    typ = str(row["Typ"])
    # holiday/blackout
    for p in players:
        if is_holiday(p, d):
            v.append(f"{p}: Urlaub/Blackout am {d}.")
    # weekday availability
    for p in players:
        days = JOTFORM.get(p)
        if days is not None and tag not in days:
            v.append(f"{p}: laut Jotform nicht verfügbar an {tag}.")
    # protected + women singles
    for p in players:
        v += protected_player_violations(p, tag, s_time, typ, df_after, d)
    return sorted(set(v))

def check_min_rules_for_mask(df_after: pd.DataFrame, mask, d: date):
    v = []
    for _, r in df_after[mask].iterrows():
        v += [f"{r['Tag']} {r['Slot']}: {msg}" for msg in check_min_rules_for_row(r, d, df_after)]
    return sorted(set(v))

def singles_opponent(row, out_player: str):
    """For an 'Einzel' row, return the name of the other player."""
    players = [p for p in split_players(row["Spieler"]) if p != out_player]
    if row["Typ"].lower().startswith("einzel") and len(players) == 1:
        return players[0]
    return None

def _violations_if_added(df_plan: pd.DataFrame, name: str, tag: str, slot_time: str, slot_typ: str, d: date):
    """Return violations list for 'name' if they were added to this slot/date (simulate 'after' counts)."""
    # Simulate by appending a virtual row for counting rules (Dirk cap, 70/30, etc.)
    y, w = week_of(d)
    virtual = pd.DataFrame([{
        "Tag": tag, "S_Time": slot_time, "Typ": slot_typ, "Spieler": name,
        "Jahr": y, "Woche": w
    }])
    df_virtual = pd.concat([df_plan, virtual], ignore_index=True)

    v = []
    # holiday / blackout
    if is_holiday(name, d):
        v.append(f"{name}: Urlaub/Blackout am {d}.")
    # weekday availability
    days = JOTFORM.get(name)
    if days is not None and tag not in days:
        v.append(f"{name}: laut Jotform nicht verfügbar an {tag}.")
    # protected + women singles using virtual counts
    v += protected_player_violations(name, tag, slot_time, slot_typ, df_virtual, d)
    return sorted(set(v))

def eligible_replacements_all(df_plan: pd.DataFrame, tag: str, d: date, exclude: set,
                              slot_time: str, slot_typ: str, singles_vs: str | None):
    """
    Show ALL players (except those already in the match), but compute:
      - week/season counts
      - rank
      - violations if added to this slot (holiday/weekday/protected/women&singles)
      - if singles: also add rank-window violation when |Δrank| > 2
    Sorted by (season asc, week asc, rank asc, name).
    """
    all_players = sorted(p for p in df_exp["Spieler_Name"].dropna().unique().tolist() if str(p).strip())
    items = []
    for name in all_players:
        if name in exclude:
            continue

        # base metrics
        wk = count_week(df_plan, name, d)
        ssn = count_season(df_plan, name)
        rk = RANK.get(name, 999)

        viol = _violations_if_added(df_plan, name, tag, slot_time, slot_typ, d)

        # singles rank window marker (as a violation item if needed)
        if slot_typ.lower().startswith("einzel") and singles_vs:
            r1 = RANK.get(name); r2 = RANK.get(singles_vs)
            if r1 is None or r2 is None or abs(r1 - r2) > 2:
                viol.append(f"Singles-Rangfenster verletzt (Δ>{abs((r1 or 9) - (r2 or 9)) if (r1 and r2) else '?'})")

        items.append({
            "name": name,
            "week": wk,
            "season": ssn,
            "rank": rk,
            "violations": sorted(set(viol)),
        })
    items.sort(key=lambda x: (x["season"], x["week"], x["rank"], x["name"]))
    return items

def blank_first(options):
    return [""] + list(options)

def display_or_blank(val, blank="— bitte wählen —"):
    return blank if (val is None or val == "") else str(val)

# ---------- Password helper (simple; no form/rerun) ----------
def check_edit_password() -> bool:
    if st.session_state.get("edit_ok", False):
        return True
    st.write("🔒 Editieren erfordert ein Passwort.")
    pw = st.text_input("Passwort", type="password", key="edit_pw")
    if st.button("Login", key="edit_login_btn"):
        if pw == EDIT_PASSWORD:
            st.session_state.edit_ok = True
            st.success("Eingeloggt.")
        else:
            st.error("Falsches Passwort.")
    return st.session_state.get("edit_ok", False)

with tab3:
    st.header("Plan bearbeiten – geschützter Bereich")
    if not check_edit_password():
        st.stop()

    # Working copy
    if "df_edit" not in st.session_state:
        st.session_state.df_edit = df.copy()
    df_edit = st.session_state.df_edit

    st.info(
        "Hier kannst du **1) einen Spieler in einem Match ersetzen** oder **2) zwei Spieler zwischen zwei Matches tauschen**.  "
        "Geprüft werden **Urlaub/Blackout**, **Wochentags-Verfügbarkeit (Jotform)**, **geschützte Spieler (HARD)**, "
        "**Frauen & Einzel** sowie (bei Einzel) **Rangfenster |Δrank| ≤ 2**. "
        "Die Ersatzliste zeigt jetzt **alle** Spieler; bei Verstößen steht **⛔** (Override nötig)."
    )

    # ----- Common: date selection & day view -----
    valid_days = sorted(df_edit["Datum_dt"].dropna().dt.date.unique())
    if not valid_days:
        st.warning("Keine Daten vorhanden."); st.stop()

    sel_day = st.date_input("Datum wählen", value=valid_days[-1], help="Wähle den Tag, an dem du Änderungen vornehmen willst.")
    day_df = df_edit[df_edit["Datum_dt"].dt.date.eq(sel_day)].copy()
    if day_df.empty:
        st.info("Für dieses Datum gibt es keine Einträge."); st.stop()

    # Keep original index as RowID
    day_df = day_df.copy()
    day_df["RowID"] = day_df.index
    day_df["Label"] = day_df.apply(lambda r: f"{r['Slot']} — {r['Typ']} — {r['Spieler']}", axis=1)
    id_to_label = dict(zip(day_df["RowID"], day_df["Label"]))

    # ================= 1) REPLACE =================
    st.markdown("### 1) Spieler **ersetzen** (ein Match → anderer Spieler)")
    st.caption(
        "Wähle ein Match und den **Spieler, der raus soll**. "
        "Die Liste zeigt **alle** Spieler. **✅** = legal, **⛔** = Verstoß (Override nötig). "
        "Sortierung: **Saison** ↑, **Woche** ↑, **Rang** ↑."
    )

    match_ids = [int(x) for x in day_df["RowID"].tolist()]
    sel_match_id = st.selectbox(
        "Match wählen",
        options=blank_first(match_ids),
        format_func=lambda rid: display_or_blank(id_to_label.get(rid, "")),
        key="rep_match_select",
    )

    if sel_match_id == "":
        st.write("⬆️ Bitte wähle zuerst ein Match aus.")
    else:
        sel_row = day_df[day_df["RowID"] == sel_match_id].iloc[0]
        current_players = split_players(sel_row["Spieler"])

        out_choice = st.selectbox(
            "Spieler **herausnehmen**",
            options=blank_first(current_players),
            format_func=display_or_blank,
            key="rep_out_select",
        )

        if out_choice == "":
            st.write("⬆️ Bitte wähle den zu ersetzenden Spieler.")
        else:
            singles_vs = singles_opponent(sel_row, out_choice)
            exclusions = set(current_players)  # keep out current match members only
            candidates = eligible_replacements_all(
                df_edit, sel_row["Tag"], sel_day, exclusions,
                slot_time=str(sel_row["S_Time"]), slot_typ=str(sel_row["Typ"]),
                singles_vs=singles_vs
            )

            cand_values = [c["name"] for c in candidates]
            name_to_item = {c["name"]: c for c in candidates}

            def _lab(n):
                if not n:
                    return "— bitte wählen —"
                c = name_to_item[n]
                r = RANK.get(n, "?")
                status = "✅ legal" if not c["violations"] else "⛔ Verstoß"
                return f"{n} — Woche: {c['week']} | Saison: {c['season']} | Rang: {r} | {status}"

            repl_choice = st.selectbox(
                "Ersatzspieler (alle)",
                options=blank_first(cand_values),
                format_func=_lab,
                key="rep_in_select",
            )

            if repl_choice == "":
                st.write("⬆️ Bitte wähle einen Ersatzspieler.")
            else:
                # preview state after replace
                df_after = df_edit.copy()
                mask_row = (df_after.index == sel_match_id)
                if mask_row.any():
                    df_after.loc[mask_row] = df_after.loc[mask_row].apply(
                        lambda r: replace_player_in_row(r, out_choice, repl_choice), axis=1
                    )
                # compute violations for the changed row (authoritative for enabling save)
                violations = check_min_rules_for_mask(df_after, mask_row, sel_day)

                # also show candidate-specific reasons, if any
                cand_viol = name_to_item[repl_choice]["violations"]
                if cand_viol:
                    with st.expander("Hinweise zum gewählten Ersatz (Slot-spezifisch)"):
                        for m in cand_viol:
                            st.write("•", m)

                override_ok = False
                if violations:
                    with st.expander("Regelverletzungen anzeigen"):
                        for m in violations: st.write("•", m)
                    col1, col2 = st.columns([3,1])
                    reason = col1.text_input("Override-Begründung (Pflicht bei Verstoß)", key="rep_reason")
                    override_ok = col2.checkbox("Regeln überstimmen", key="rep_override")
                    save_disabled = not override_ok or (reason.strip() == "")
                else:
                    save_disabled = False
                    reason = ""

                if st.button("✅ Änderung speichern", disabled=save_disabled, key="btn_replace_commit"):
                    st.session_state.df_edit = df_after
                    try:
                        to_save = st.session_state.df_edit[["Datum","Tag","Slot","Typ","Spieler"]]
                        csv_bytes = to_save.to_csv(index=False).encode("utf-8")
                        msg = f"Replace {out_choice} → {repl_choice} on {sel_day} ({sel_row['Slot']}) {(' | override: ' + reason) if reason else ''}"
                        github_put_file(csv_bytes, msg, branch_override=st.secrets.get("GITHUB_BRANCH", "main"))
                        st.success("Gespeichert ✅")
                    except Exception as e:
                        st.error(f"Speichern fehlgeschlagen: {e}")

    st.markdown("---")
    # ================= 2) SWAP =================
    st.markdown("### 2) **Zwei Matches**: Spieler **tauschen**")
    st.caption("Tausche je **einen** Spieler zwischen zwei Matches am selben Datum. Checks wie oben; Override möglich.")

    sel_a_id = st.selectbox(
        "Match A",
        options=blank_first(match_ids),
        format_func=lambda rid: display_or_blank(id_to_label.get(rid, "")),
        key="swap_match_a",
    )
    sel_b_id = st.selectbox(
        "Match B",
        options=blank_first(match_ids),
        format_func=lambda rid: display_or_blank(id_to_label.get(rid, "")),
        key="swap_match_b",
    )

    if not sel_a_id or not sel_b_id:
        st.write("⬆️ Bitte wähle zwei Matches aus.")
    else:
        row_a = day_df[day_df["RowID"] == sel_a_id].iloc[0]
        row_b = day_df[day_df["RowID"] == sel_b_id].iloc[0]
        players_a = split_players(row_a["Spieler"])
        players_b = split_players(row_b["Spieler"])

        pA = st.selectbox("Spieler aus Match A", options=blank_first(players_a), format_func=display_or_blank, key="swap_player_a")
        pB = st.selectbox("Spieler aus Match B", options=blank_first(players_b), format_func=display_or_blank, key="swap_player_b")

        if not pA or not pB:
            st.write("⬆️ Bitte wähle je **einen** Spieler aus beiden Matches.")
        else:
            # preview state after swap
            df_after = df_edit.copy()
            mask_a = (df_after.index == sel_a_id)
            mask_b = (df_after.index == sel_b_id)
            if mask_a.any():
                df_after.loc[mask_a] = df_after.loc[mask_a].apply(lambda r: swap_players_in_row(r, pA, pB), axis=1)
            if mask_b.any():
                df_after.loc[mask_b] = df_after.loc[mask_b].apply(lambda r: swap_players_in_row(r, pA, pB), axis=1)

            violations = check_min_rules_for_mask(df_after, (mask_a | mask_b), sel_day)

            override_ok = False
            if violations:
                with st.expander("Regelverletzungen anzeigen"):
                    for m in violations: st.write("•", m)
                col1, col2 = st.columns([3,1])
                reason_swap = col1.text_input("Override-Begründung (Pflicht bei Verstoß)", key="swap_reason")
                override_ok = col2.checkbox("Regeln überstimmen", key="swap_override")
                save_disabled = not override_ok or (reason_swap.strip() == "")
            else:
                save_disabled = False
                reason_swap = ""

            if st.button("🔁 Tausch speichern", disabled=save_disabled, key="btn_swap_commit"):
                st.session_state.df_edit = df_after
                try:
                    to_save = st.session_state.df_edit[["Datum","Tag","Slot","Typ","Spieler"]]
                    csv_bytes = to_save.to_csv(index=False).encode("utf-8")
                    msg = f"Swap {pA} ↔ {pB} on {sel_day} {(' | override: ' + reason_swap) if reason_swap else ''}"
                    github_put_file(csv_bytes, msg, branch_override=st.secrets.get("GITHUB_BRANCH", "main"))
                    st.success("Gespeichert ✅")
                except Exception as e:
                    st.error(f"Speichern fehlgeschlagen: {e}")

    # ---------- Preview & Reset ----------
    st.markdown("---")
    st.subheader("Vorschau – Tagesplan")
    preview = st.session_state.df_edit[st.session_state.df_edit["Datum_dt"].dt.date.eq(sel_day)].sort_values(
        ["Datum_dt", "Startzeit_sort", "Slot"]
    )
    st.dataframe(preview[["Datum","Tag","Slot","Typ","Spieler"]], use_container_width=True)

    if st.button("↩️ Änderungen verwerfen (Reset)"):
        st.session_state.df_edit = df.copy()
        st.rerun()
