import streamlit as st
import pandas as pd
import re
import base64, json, requests, io
from datetime import date, datetime, timedelta

# -------------------- Basic config --------------------
st.set_page_config(page_title="Wochenplan", layout="wide", initial_sidebar_state="collapsed")

EDIT_PASSWORD = "tennis"  # protects only the "Plan bearbeiten" tab

# -------------------- Reload helpers --------------------
def reload_from_source(force_branch: bool = True):
    """Reload CSV via Contents API (by ref). If force_branch, jump to HEAD of branch."""
    ref = st.secrets.get("GITHUB_BRANCH", "main") if force_branch else st.session_state.get("csv_ref")
    st.session_state["csv_ref"] = ref
    st.cache_data.clear()
    st.session_state.pop("df_edit", None)
    st.session_state.pop("wk_idx", None)
    st.rerun()

# -------------------- Data helpers --------------------
def _postprocess(df: pd.DataFrame):
    required = ["Datum", "Tag", "Slot", "Typ", "Spieler"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}. Expected: {required}")

    for c in required:
        df[c] = df[c].astype(str).str.strip()

    # Robust date parsing: DE (dd.mm.yyyy) first, then ISO (yyyy-mm-dd)
    s = df["Datum"].astype(str).str.strip()
    d1 = pd.to_datetime(s, format="%d.%m.%Y", errors="coerce")
    d2 = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    df["Datum_dt"] = d1.fillna(d2)

    iso = df["Datum_dt"].dt.isocalendar()
    df["Jahr"] = iso["year"]
    df["Woche"] = iso["week"]

    # Extract from Slot like "D20:00-120 PLA"
    t = df["Slot"].str.extract(r"^([ED])(\d{2}:\d{2})-([0-9]+)\s+PL([AB])$")
    df["S_Art"]   = t[0].fillna("")      # E/D (Einzel/Doppel)
    df["S_Time"]  = t[1].fillna("00:00")
    df["S_Dur"]   = t[2].fillna("0")     # minutes as string
    df["S_Court"] = t[3].fillna("")

    df["Startzeit_sort"] = pd.to_datetime(df["S_Time"], format="%H:%M", errors="coerce").dt.time

    # Exploded player view
    df["Spieler_list"] = df["Spieler"].str.split(",").apply(
        lambda xs: [x.strip() for x in xs if str(x).strip()]
    )
    df_exp = df.explode("Spieler_list").rename(columns={"Spieler_list": "Spieler_Name"})
    return df, df_exp

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

# ==============================================================
# =================== GitHub helpers (API) =====================
# ==============================================================

def _github_headers():
    token = st.secrets.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GitHub token missing in st.secrets['GITHUB_TOKEN'].")
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

def _gh_repo_info():
    repo   = st.secrets.get("GITHUB_REPO")            # e.g. "owner/repo"
    branch = st.secrets.get("GITHUB_BRANCH", "main")   # e.g. "main"
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

def github_get_contents(ref: str | None = None):
    """
    Fetch CSV bytes + file SHA from GitHub Contents API for a given ref (branch or commit sha).
    """
    repo, branch, path = _gh_repo_info()
    use_ref = ref or branch
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    params = {"ref": use_ref}
    r = requests.get(url, headers=_github_headers(), params=params, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"GitHub contents GET failed {r.status_code}: {r.text}")
    data = r.json()
    if "content" not in data:
        raise RuntimeError("GitHub contents response missing 'content'.")
    content_b64 = data["content"]
    csv_bytes = base64.b64decode(content_b64)
    sha = data.get("sha", "")
    return csv_bytes, sha

@st.cache_data(show_spinner=False)
def load_csv_by_ref(ref: str):
    """
    Deterministic loader: given a ref (branch or commit sha), fetch and parse.
    Cache key = ref.
    """
    csv_bytes, sha = github_get_contents(ref)
    df_raw = pd.read_csv(io.BytesIO(csv_bytes), dtype=str)
    df_pp, df_exp = _postprocess(df_raw)
    return df_pp, df_exp, sha

def _safe_load_by_ref_with_fallback(ref: str, branch: str):
    """Try the requested ref once; on failure, fall back to branch HEAD and warn."""
    try:
        return load_csv_by_ref(ref), None
    except Exception as e:
        if ref != branch:
            try:
                data = load_csv_by_ref(branch)
                return data, f"Ref `{ref}` fehlgeschlagen, auf `{branch}` (HEAD) zurückgefallen."
            except Exception as e2:
                return None, f"Laden fehlgeschlagen: ref `{ref}` und Branch `{branch}`. Fehler: {e2}"
        return None, f"Laden fehlgeschlagen für ref `{ref}`. Fehler: {e}"

# -------------------- Load data (by ref/sha, not raw CDN) --------------------
default_ref = st.secrets.get("GITHUB_BRANCH", "main")
current_ref = st.session_state.get("csv_ref", default_ref)

data_tuple, warn = _safe_load_by_ref_with_fallback(current_ref, default_ref)
if data_tuple is None:
    st.error(warn or "Unbekannter Ladefehler.")
    st.stop()

df, df_exp, current_sha = data_tuple
st.session_state["csv_sha"] = current_sha
if warn:
    st.warning(warn)

# -------------------- Load player preferences from CSV --------------------
@st.cache_data(show_spinner=False)
def load_player_preferences():
    """Load player preferences from Spieler_Preferences_2026.csv"""
    try:
        prefs_df = pd.read_csv("Spieler_Preferences_2026.csv", dtype=str)
        return prefs_df
    except Exception as e:
        st.warning(f"Could not load player preferences: {e}. Using fallback.")
        return pd.DataFrame()

df_preferences = load_player_preferences()

# -------------------- Top controls --------------------
col_reload, col_ref = st.columns([1.5, 6])
with col_reload:
    if st.button("🔄 Daten neu laden (HEAD)", help="Neu laden direkt vom Branch-HEAD (ohne CDN-Lag)"):
        reload_from_source(force_branch=True)
with col_ref:
    st.caption(f"Aktuelle CSV-Ref: `{st.session_state.get('csv_ref', default_ref)}` | SHA: `{st.session_state.get('csv_sha','')[:7]}`")

# ==============================================================
# =============== RULE SOURCES (HARD where stated) =============
# ==============================================================

# ---- Dynamic player availability and holidays from CSV ----
def get_available_days_from_csv(df_prefs):
    """Extract available days for each player from preferences CSV"""
    jotform = {}
    if df_prefs.empty:
        return {}

    for _, row in df_prefs.iterrows():
        name = str(row.get("Spieler", "")).strip()
        if not name:
            continue
        days_str = str(row.get("AvailableDays", ""))
        # Handle both comma and semicolon separators
        days = set()
        for sep in [",", ";"]:
            if sep in days_str:
                days = {d.strip() for d in days_str.split(sep) if d.strip()}
                break
        else:
            if days_str.strip():
                days = {days_str.strip()}
        jotform[name] = days
    return jotform

def get_player_preferences_from_csv(df_prefs):
    """Extract player type preferences (nur Einzel/nur Doppel/keine Präferenz)"""
    prefs = {}
    if df_prefs.empty:
        return {}

    for _, row in df_prefs.iterrows():
        name = str(row.get("Spieler", "")).strip()
        if not name:
            continue
        pref = str(row.get("Preference", "keine Präferenz")).strip()
        prefs[name] = pref
    return prefs

def parse_blocked_ranges_from_csv(blocked_str):
    """Parse blocked date ranges like '2026-01-01→2026-01-04' from CSV"""
    periods = []
    if not blocked_str or pd.isna(blocked_str) or str(blocked_str).strip() == "":
        return periods

    for chunk in str(blocked_str).split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "→" in chunk:
            try:
                s, e = [x.strip() for x in chunk.split("→", 1)]
                sd = datetime.strptime(s, "%Y-%m-%d").date()
                ed = datetime.strptime(e, "%Y-%m-%d").date()
                periods.append((sd, ed))
            except Exception:
                pass
    return periods

def parse_blocked_days_from_csv(blocked_str):
    """Parse individual blocked days from CSV"""
    periods = []
    if not blocked_str or pd.isna(blocked_str) or str(blocked_str).strip() == "":
        return periods

    for chunk in str(blocked_str).split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            d = datetime.strptime(chunk, "%Y-%m-%d").date()
            periods.append((d, d))
        except Exception:
            pass
    return periods

def load_holidays_from_csv(df_prefs):
    """Load all holidays from preferences CSV"""
    holidays = {}
    if df_prefs.empty:
        return {}

    for _, row in df_prefs.iterrows():
        name = str(row.get("Spieler", "")).strip()
        if not name:
            continue

        blocked_ranges = parse_blocked_ranges_from_csv(row.get("BlockedRanges", ""))
        blocked_days = parse_blocked_days_from_csv(row.get("BlockedDays", ""))

        all_periods = blocked_ranges + blocked_days
        if all_periods:
            holidays[name] = holidays.get(name, []) + all_periods

    return holidays

# Load dynamic data from CSV (with fallback to old hard-coded values)
JOTFORM = get_available_days_from_csv(df_preferences)
PLAYER_TYPE_PREFERENCES = get_player_preferences_from_csv(df_preferences)
HOLIDAYS_FROM_CSV = load_holidays_from_csv(df_preferences)

# ---- Fallback: Old hard-coded Jotform data (only if CSV fails) ----
JOTFORM_FALLBACK = {
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

# Use CSV data if available, otherwise fall back
if not JOTFORM:
    JOTFORM = JOTFORM_FALLBACK

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

# ---- Holidays list (FULL, no placeholders) ----
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
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        # ignore comment/placeholder/malformed lines safely
        if line.startswith("#") or line.startswith("//"):
            continue
        if ":" not in line:
            continue

        name, rest = line.split(":", 1)
        name = name.strip()
        rest = rest.strip()
        if not name or not rest:
            continue

        periods = []
        # split by ';' or '.'; keep arrows '→' inside chunks
        for chunk in re.split(r"[;.]+" , rest):
            chunk = chunk.strip(" .;")
            if not chunk:
                continue
            if "→" in chunk:
                s, e = [x.strip() for x in chunk.split("→", 1)]
                try:
                    sd = datetime.strptime(s, "%Y-%m-%d").date()
                    ed = datetime.strptime(e, "%Y-%m-%d").date()
                    periods.append((sd, ed))
                except Exception:
                    pass
            else:
                # single date
                try:
                    d = datetime.strptime(chunk, "%Y-%m-%d").date()
                    periods.append((d, d))
                except Exception:
                    pass

        if periods:
            out[name] = out.get(name, []) + periods
    return out

HOLIDAYS = parse_holidays(RAW_HOLIDAYS)

def is_holiday(name: str, d: date) -> bool:
    if (d.month, d.day) in BLACKOUT_MMDD:
        return True
    # Merge old hard-coded holidays with CSV holidays (CSV takes priority)
    csv_ranges = HOLIDAYS_FROM_CSV.get(name, [])
    old_ranges = HOLIDAYS.get(name, [])
    all_ranges = csv_ranges if csv_ranges else old_ranges
    return any(start <= d <= end for (start, end) in all_ranges)

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

    # Check player type preferences from CSV
    pref = PLAYER_TYPE_PREFERENCES.get(name, "keine Präferenz")
    if pref == "nur Einzel" and typ.lower().startswith("doppel"):
        v.append(f"{name}: möchte nur Einzel spielen.")
    elif pref == "nur Doppel" and typ.lower().startswith("einzel"):
        v.append(f"{name}: möchte nur Doppel spielen.")

    return v

# ==============================================================
# =========== COSTS: court rates + allowed weekly slots =========
# ==============================================================

COURT_RATE_PER_HOUR = 17.50  # €
# Allowed weekly slots (strict) with human 'Typ'
ALLOWED_SLOTS = {
    "Montag": [
        ("D20:00-120 PLA", "Doppel"),
        ("D20:00-120 PLB", "Doppel"),
    ],
    "Mittwoch": [
        ("E18:00-60 PLA",  "Einzel"),
        ("E19:00-60 PLA",  "Einzel"),
        ("E19:00-60 PLB",  "Einzel"),
        ("D20:00-90 PLA",  "Doppel"),
        ("D20:00-90 PLB",  "Doppel"),
    ],
    "Donnerstag": [
        ("E20:00-90 PLA",  "Einzel"),
        ("E20:00-90 PLB",  "Einzel"),
    ],
}
# Map German weekday -> ISO weekday index (Mon=1 ... Sun=7 for isocalendar)
WEEKDAY_TO_ISO = {"Montag": 1, "Mittwoch": 3, "Donnerstag": 4}

def _minutes_from_slot(slot: str) -> int:
    # e.g. "D20:00-120 PLA" -> 120
    m = re.search(r"-([0-9]+)\s+PL[AB]$", str(slot))
    return int(m.group(1)) if m else 0

def _players_per_slot(s_art: str, fallback_players_count: int | None = None, slot_typ_text: str = "") -> int:
    # Prefer E/D code; fall back to text; then to passed count
    if s_art == "E":
        return 2
    if s_art == "D":
        return 4
    if slot_typ_text.lower().startswith("einzel"):
        return 2
    if slot_typ_text.lower().startswith("doppel"):
        return 4
    return max(1, fallback_players_count or 2)

def _season_bounds_from_df(df: pd.DataFrame):
    dmin = pd.to_datetime(df["Datum_dt"]).dropna().min()
    dmax = pd.to_datetime(df["Datum_dt"]).dropna().max()
    if pd.isna(dmin) or pd.isna(dmax):
        return None, None
    return dmin.date(), dmax.date()

def _dates_for_iso_week(iso_year: int, iso_week: int, iso_weekday: int):
    # returns date for given ISO (year, week, weekday 1..7)
    return pd.Timestamp.fromisocalendar(iso_year, iso_week, iso_weekday).date()

from datetime import date as _date

def _generate_allowed_slots_calendar(df: pd.DataFrame):
    """Return list of dicts with Date, Tag, Slot, Typ, Minutes for every allowed weekly slot within season bounds."""
    start_date, end_date = _season_bounds_from_df(df)
    if not start_date or not end_date:
        return []

    # compute inclusive range of (year, week)
    start_iso = pd.Timestamp(start_date).isocalendar()
    end_iso   = pd.Timestamp(end_date).isocalendar()
    start_key = (int(start_iso.year), int(start_iso.week))
    end_key   = (int(end_iso.year), int(end_iso.week))

    def week_iter(yw_start, yw_end):
        """Yield successive (iso_year, iso_week) from start to end inclusive."""
        y, w = yw_start
        y_end, w_end = yw_end
        while True:
            yield y, w
            if (y, w) == (y_end, w_end):
                break
            # number of ISO weeks in year y = week-number of Dec 28th (a guaranteed ISO week in that year)
            maxw = _date(y, 12, 28).isocalendar().week
            if w < maxw:
                w += 1
            else:
                y += 1
                w = 1

    out = []
    for y, w in week_iter(start_key, end_key):
        for tag, slot_list in ALLOWED_SLOTS.items():
            iso_wd = WEEKDAY_TO_ISO[tag]
            dt = _dates_for_iso_week(y, w, iso_wd)
            if dt < start_date or dt > end_date:
                continue
            for slot_code, typ_text in slot_list:
                out.append({
                    "Datum": dt,
                    "Tag": tag,
                    "Slot": slot_code,
                    "Typ": typ_text,
                    "Minutes": _minutes_from_slot(slot_code),
                })
    return out

def _is_blackout(d: date) -> bool:
    return (d.month, d.day) in BLACKOUT_MMDD

def compute_player_costs(df: pd.DataFrame, df_exp: pd.DataFrame):
    """
    Returns:
      per_player_df (Name, minutes, direct_cost, unused_share, total) rounded,
      totals_dict for UI, and the full breakdown tables if needed
    """
    # 1) Direct costs from used rows
    used = df.copy()
    used["Minutes"] = pd.to_numeric(used["S_Dur"], errors="coerce").fillna(0).astype(int)
    used["players_in_slot"] = used.apply(
        lambda r: _players_per_slot(r["S_Art"], fallback_players_count=len(r["Spieler_list"]), slot_typ_text=r["Typ"]),
        axis=1
    )
    used["court_cost"] = used["Minutes"] / 60.0 * COURT_RATE_PER_HOUR
    used["per_player_cost"] = used["court_cost"] / used["players_in_slot"]

    # per-player minutes and direct costs
    exploded = df_exp.merge(
        used[["Datum", "Tag", "Slot", "Minutes", "players_in_slot"]],
        left_on=["Datum", "Tag", "Slot"],
        right_on=["Datum", "Tag", "Slot"],
        how="left"
    )
    exploded["Minutes"] = exploded["Minutes"].fillna(0)
    # Each player's minutes for a slot = full slot minutes (not divided)
    per_player_minutes = exploded.groupby("Spieler_Name")["Minutes"].sum()

    used_cost_per_row = used[["Datum", "Tag", "Slot", "per_player_cost"]]
    exploded_cost = df_exp.merge(used_cost_per_row, on=["Datum", "Tag", "Slot"], how="left")
    exploded_cost["per_player_cost"] = exploded_cost["per_player_cost"].fillna(0.0)
    per_player_direct = exploded_cost.groupby("Spieler_Name")["per_player_cost"].sum()

    # Ensure all players present
    all_players = sorted(p for p in df_exp["Spieler_Name"].dropna().unique().tolist() if str(p).strip())
    minutes_series = per_player_minutes.reindex(all_players, fill_value=0)
    direct_series  = per_player_direct.reindex(all_players,  fill_value=0.0)

    # 2) Unused court costs
    allowed_calendar = pd.DataFrame(_generate_allowed_slots_calendar(df))
    if allowed_calendar.empty:
        total_unused_cost = 0.0
    else:
        # Mark which allowed (date,slot) pairs are present in used df
        used_pairs = set(zip(pd.to_datetime(df["Datum_dt"]).dt.date, df["Slot"]))
        allowed_calendar["is_used"] = allowed_calendar.apply(
            lambda r: (r["Datum"], r["Slot"]) in used_pairs, axis=1
        )
        allowed_calendar["court_cost"] = allowed_calendar["Minutes"] / 60.0 * COURT_RATE_PER_HOUR
        total_unused_cost = float(allowed_calendar.loc[~allowed_calendar["is_used"], "court_cost"].sum())

    # 3) Distribute unused cost by total minutes played
    total_minutes_all = float(minutes_series.sum())
    if total_minutes_all > 0:
        unused_share = minutes_series.astype(float) / total_minutes_all * total_unused_cost
    else:
        unused_share = minutes_series.astype(float) * 0.0

    # 4) Assemble per-player table
    per_player = pd.DataFrame({
        "Spieler": minutes_series.index,
        "Minuten": minutes_series.values.astype(int),
        "Direkte Kosten (€)": direct_series.values.astype(float),
        "Anteil ungenutzte Plätze (€)": unused_share.values.astype(float),
    })
    per_player["Gesamt (€)"] = per_player["Direkte Kosten (€)"] + per_player["Anteil ungenutzte Plätze (€)"]

    # Round for display
    per_player["Direkte Kosten (€)"] = per_player["Direkte Kosten (€)"].round(2)
    per_player["Anteil ungenutzte Plätze (€)"] = per_player["Anteil ungenutzte Plätze (€)"].round(2)
    per_player["Gesamt (€)"] = per_player["Gesamt (€)"].round(2)

    # Totals for UI
    total_direct = float(per_player["Direkte Kosten (€)"].sum())
    total_charged = float(per_player["Gesamt (€)"].sum())

    totals = {
        "unused_cost_total": round(total_unused_cost, 2),
        "direct_cost_total": round(total_direct, 2),
        "charged_total": round(total_charged, 2),
    }
    return per_player.sort_values(["Gesamt (€)", "Spieler"]), totals, allowed_calendar

# ==============================================================
# ============== AUTOPOPULATION ALGORITHM ======================
# ==============================================================

def get_all_players_from_csv():
    """Get list of all players from preferences CSV, falling back to plan if needed"""
    if not df_preferences.empty:
        players = df_preferences["Spieler"].dropna().unique().tolist()
        return sorted([str(p).strip() for p in players if str(p).strip()])
    # Fallback to players in current plan
    return sorted(p for p in df_exp["Spieler_Name"].dropna().unique().tolist() if str(p).strip())

def find_empty_slots(df_plan: pd.DataFrame):
    """Find all allowed slots that are not yet filled in the plan"""
    allowed_calendar = pd.DataFrame(_generate_allowed_slots_calendar(df_plan))
    if allowed_calendar.empty:
        return []

    # Create set of (date, slot) pairs that exist in the plan
    used_pairs = set(zip(pd.to_datetime(df_plan["Datum_dt"]).dt.date, df_plan["Slot"]))

    # Find empty slots
    empty_slots = []
    for _, row in allowed_calendar.iterrows():
        pair = (row["Datum"], row["Slot"])
        if pair not in used_pairs:
            empty_slots.append({
                "Datum": row["Datum"],
                "Tag": row["Tag"],
                "Slot": row["Slot"],
                "Typ": row["Typ"],
                "Minutes": row["Minutes"],
            })

    return empty_slots

def select_players_for_slot(df_plan: pd.DataFrame, slot_info: dict, prefer_balanced: bool = True):
    """
    Select appropriate players for a given empty slot using load balancing.

    Args:
        df_plan: Current plan DataFrame
        slot_info: Dict with Datum, Tag, Slot, Typ info
        prefer_balanced: If True, prioritize least-used players

    Returns:
        List of player names or None if unable to fill
    """
    datum = slot_info["Datum"]
    tag = slot_info["Tag"]
    slot_code = slot_info["Slot"]
    typ = slot_info["Typ"]

    # Extract time from slot code (e.g., "D20:00-120 PLA" -> "20:00")
    time_match = re.search(r"(\d{2}:\d{2})", slot_code)
    slot_time = time_match.group(1) if time_match else "00:00"

    # Determine how many players we need
    num_players = 4 if typ.lower().startswith("doppel") else 2

    # Get all eligible players
    all_players = get_all_players_from_csv()
    candidates = []

    for name in all_players:
        y, w = week_of(datum)
        wk = df_plan[(df_plan["Jahr"] == y) & (df_plan["Woche"] == w)]
        week_count = int(wk["Spieler"].str.contains(fr"\b{re.escape(name)}\b", regex=True).sum())
        season_count = int(df_plan["Spieler"].str.contains(fr"\b{re.escape(name)}\b", regex=True).sum())
        rk = RANK.get(name, 999)

        # Check violations
        viol = _violations_if_added(df_plan, name, tag, slot_time, typ, datum)

        candidates.append({
            "name": name,
            "week": week_count,
            "season": season_count,
            "rank": rk,
            "violations": viol,
            "has_violations": len(viol) > 0,
        })

    # Filter by player preference (nur Einzel/nur Doppel)
    filtered_candidates = []
    for c in candidates:
        pref = PLAYER_TYPE_PREFERENCES.get(c["name"], "keine Präferenz")
        if pref == "nur Einzel" and typ.lower().startswith("doppel"):
            continue
        if pref == "nur Doppel" and typ.lower().startswith("einzel"):
            continue
        filtered_candidates.append(c)

    # Sort by violations (legal first), then by usage (season, week), then rank
    if prefer_balanced:
        filtered_candidates.sort(key=lambda x: (x["has_violations"], x["season"], x["week"], x["rank"], x["name"]))
    else:
        filtered_candidates.sort(key=lambda x: (x["has_violations"], x["rank"], x["name"]))

    # Select players
    if typ.lower().startswith("einzel"):
        # Einzel: need 2 players with rank difference ≤ 2
        return _select_singles_pair(filtered_candidates)
    else:
        # Doppel: need 4 players
        return _select_doubles_team(filtered_candidates, num_players)

def _select_singles_pair(candidates):
    """Select 2 players for singles match with rank difference ≤ 2"""
    # Try to find legal pairs first
    for i, c1 in enumerate(candidates):
        if c1["has_violations"]:
            break  # Only consider legal players for first pass
        for c2 in candidates[i+1:]:
            if c2["has_violations"]:
                break
            r1 = c1["rank"]
            r2 = c2["rank"]
            if r1 != 999 and r2 != 999 and abs(r1 - r2) <= 2:
                return [c1["name"], c2["name"]]

    # If no legal pair found, return None
    return None

def _check_doubles_balance(players_with_ranks):
    """
    Check if 4 players satisfy HARD doubles balance constraints.

    Args:
        players_with_ranks: List of (name, rank) tuples for 4 players

    Returns:
        (is_valid, reason) tuple - is_valid is True if constraints satisfied

    HARD Constraints:
    - Strongest player (r1) must be rank ≤ 3
    - Rank spread (r4 - r1) must be ≤ 3
    - Must satisfy balanced pairing patterns
    """
    if len(players_with_ranks) != 4:
        return False, "Need exactly 4 players"

    # Extract ranks and sort
    ranks = [r for (name, r) in players_with_ranks]

    # Check for unknown ranks
    if any(r == 999 or r is None for r in ranks):
        return False, "Unknown ranks present"

    # Sort ranks: r1 ≤ r2 ≤ r3 ≤ r4
    sorted_ranks = sorted(ranks)
    r1, r2, r3, r4 = sorted_ranks

    # HARD: Strongest player must be rank ≤ 3
    if r1 > 3:
        return False, f"Strongest player rank {r1} > 3 (must be 1, 2, or 3)"

    # HARD: Max rank spread is 3
    spread = r4 - r1
    if spread > 3:
        return False, f"Rank spread {spread} > 3 (range {r1}-{r4})"

    # HARD: Check balanced pairing patterns
    # Pattern (i): Similar quartet - all within 2 ranks
    similar_quartet = (r4 - r1) <= 2

    # Pattern (ii): Two-strong vs two-weak
    two_vs_two = (
        (r2 - r1) <= 1 and  # Top pair close together
        (r4 - r3) <= 1 and  # Bottom pair close together
        (r3 - r2) >= 2      # Gap between pairs
    )

    if not (similar_quartet or two_vs_two):
        return False, f"Unbalanced pairing: ranks {sorted_ranks} don't match required patterns"

    return True, "OK"

def _select_doubles_team(candidates, num_players):
    """
    Select 4 players for doubles match with HARD rank balance constraints.

    Tries to find a combination of 4 legal players that satisfies:
    - Strongest player (r1) ≤ 3
    - Rank spread (r4 - r1) ≤ 3
    - Balanced pairing patterns
    """
    legal = [c for c in candidates if not c["has_violations"]]

    if len(legal) < num_players:
        return None

    # Try combinations starting with least-used players
    # Start with the first 4, then try sliding window
    for i in range(len(legal) - num_players + 1):
        team = legal[i:i + num_players]
        players_with_ranks = [(c["name"], c["rank"]) for c in team]

        # Check if this team satisfies balance constraints
        is_valid, _ = _check_doubles_balance(players_with_ranks)

        if is_valid:
            return [c["name"] for c in team]

    # If no valid combination found, return None
    return None

def autopopulate_plan(df_plan: pd.DataFrame, max_slots: int = None, only_legal: bool = True):
    """
    Autopopulate empty slots in the training plan.

    Args:
        df_plan: Current plan DataFrame
        max_slots: Maximum number of slots to fill (None = fill all)
        only_legal: If True, only fill slots where all players are legal (no violations)

    Returns:
        Updated DataFrame with new assignments
    """
    df_result = df_plan.copy()
    empty_slots = find_empty_slots(df_result)

    filled_count = 0
    filled_slots = []
    skipped_slots = []

    for slot_info in empty_slots:
        if max_slots and filled_count >= max_slots:
            break

        players = select_players_for_slot(df_result, slot_info, prefer_balanced=True)

        if players is None or (only_legal and any(_violations_if_added(df_result, p, slot_info["Tag"],
                                                   re.search(r"(\d{2}:\d{2})", slot_info["Slot"]).group(1),
                                                   slot_info["Typ"], slot_info["Datum"]) for p in players)):
            skipped_slots.append(slot_info)
            continue

        # Add new row to plan
        new_row = {
            "Datum": slot_info["Datum"].strftime("%Y-%m-%d"),
            "Tag": slot_info["Tag"],
            "Slot": slot_info["Slot"],
            "Typ": slot_info["Typ"],
            "Spieler": ", ".join(players),
        }

        # Append to dataframe
        new_row_df = pd.DataFrame([new_row])
        df_result = pd.concat([df_result, new_row_df], ignore_index=True)

        # Reprocess to update computed columns
        df_result, _ = _postprocess(df_result[["Datum", "Tag", "Slot", "Typ", "Spieler"]])

        filled_count += 1
        filled_slots.append({**slot_info, "players": players})

    return df_result, filled_slots, skipped_slots

# ==============================================================
# =========================  UI  ===============================
# ==============================================================

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Wochenplan", "Spieler-Matches", "Plan bearbeiten", "Spieler-Kosten", "Auto-Population"])

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
        st.dataframe(pf[["Spieler_Name", "Datum", "Tag", "Slot", "Typ", "Spieler"]], width="stretch")
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
    v = []
    players = split_players(row["Spieler"])
    tag = str(row["Tag"]); s_time = str(row["S_Time"]); typ = str(row["Typ"])
    for p in players:
        if is_holiday(p, d):
            v.append(f"{p}: Urlaub/Blackout am {d}.")
    for p in players:
        days = JOTFORM.get(p)
        if days is not None and tag not in days:
            v.append(f"{p}: laut Jotform nicht verfügbar an {tag}.")
    for p in players:
        v += protected_player_violations(p, tag, s_time, typ, df_after, d)
    return sorted(set(v))

def check_min_rules_for_mask(df_after: pd.DataFrame, mask, d: date):
    v = []
    for _, r in df_after[mask].iterrows():
        v += [f"{r['Tag']} {r['Slot']}: {msg}" for msg in check_min_rules_for_row(r, d, df_after)]
    return sorted(set(v))

def singles_opponent(row, out_player: str):
    players = [p for p in split_players(row["Spieler"]) if p != out_player]
    if row["Typ"].lower().startswith("einzel") and len(players) == 1:
        return players[0]
    return None

def _violations_if_added(df_plan: pd.DataFrame, name: str, tag: str, slot_time: str, slot_typ: str, d: date):
    # Simulate counts after adding the player (for weekly caps/ratios in protected rules)
    y, w = week_of(d)
    virtual = pd.DataFrame([{
        "Tag": tag, "S_Time": slot_time, "Typ": slot_typ, "Spieler": name,
        "Jahr": y, "Woche": w
    }])
    df_virtual = pd.concat([df_plan, virtual], ignore_index=True)

    v = []
    if is_holiday(name, d):
        v.append(f"{name}: Urlaub/Blackout am {d}.")
    days = JOTFORM.get(name)
    if days is not None and tag not in days:
        v.append(f"{name}: laut Jotform nicht verfügbar an {tag}.")
    v += protected_player_violations(name, tag, slot_time, slot_typ, df_virtual, d)
    return sorted(set(v))

def eligible_replacements_all(df_plan: pd.DataFrame, tag: str, d: date, exclude: set,
                              slot_time: str, slot_typ: str, singles_vs):
    all_players = sorted(p for p in df_exp["Spieler_Name"].dropna().unique().tolist() if str(p).strip())
    items = []
    for name in all_players:
        if name in exclude:
            continue
        # metrics
        y, w = week_of(d)
        wk = df_plan[(df_plan["Jahr"] == y) & (df_plan["Woche"] == w)]
        week_count = int(wk["Spieler"].str.contains(fr"\b{re.escape(name)}\b", regex=True).sum())
        season_count = int(df_plan["Spieler"].str.contains(fr"\b{re.escape(name)}\b", regex=True).sum())
        rk = RANK.get(name, 999)
        viol = _violations_if_added(df_plan, name, tag, slot_time, slot_typ, d)
        if slot_typ.lower().startswith("einzel") and singles_vs:
            r1 = RANK.get(name); r2 = RANK.get(singles_vs)
            if r1 is None or r2 is None or abs(r1 - r2) > 2:
                viol.append("Singles-Rangfenster verletzt (Δ>2)")
        items.append({
            "name": name,
            "week": week_count,
            "season": season_count,
            "rank": rk,
            "violations": sorted(set(viol))
        })
    # Least-used first, then week count, then rank, then name
    items.sort(key=lambda x: (x["season"], x["week"], x["rank"], x["name"]))
    return items

def blank_first(options):
    return [""] + list(options)

def display_or_blank(val, blank="— bitte wählen —"):
    return blank if (val is None or val == "") else str(val)

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

# Helper: set ref after save (use COMMIT sha only)
def _set_ref_after_save(res: dict):
    new_ref = (res.get("commit") or {}).get("sha")
    if new_ref:
        st.session_state["csv_ref"] = new_ref
    else:
        st.session_state["csv_ref"] = st.secrets.get("GITHUB_BRANCH", "main")

with tab3:
    st.header("Plan bearbeiten – geschützter Bereich")
    if not check_edit_password():
        st.stop()

    # Working copy for previews
    if "df_edit" not in st.session_state:
        st.session_state.df_edit = df.copy()
    df_edit = st.session_state.df_edit

    st.info(
        "Hier kannst du **1) einen Spieler in einem Match ersetzen** oder **2) zwei Spieler zwischen zwei Matches tauschen**.  "
        "Checks: **Urlaub/Blackout**, **Wochentags-Verfügbarkeit (Jotform)**, **geschützte Spieler (HARD)**, "
        "**Frauen & Einzel**, **Rangfenster (Einzel)**. "
        "Ersatzliste zeigt **alle** Spieler: **✅ legal** / **⛔ Verstoß** (Override nötig)."
    )

    # Export (for ChatGPT / backup)
    with st.expander("📤 Plan exportieren (CSV/JSON)"):
        export_df = st.session_state.get("df_edit", df)[["Datum","Tag","Slot","Typ","Spieler"]]
        csv_text = export_df.to_csv(index=False)
        st.download_button("CSV herunterladen", data=csv_text.encode("utf-8"),
                           file_name="Winterplan.csv", mime="text/csv")
        st.text_area("CSV (kopieren & in ChatGPT einfügen)", csv_text, height=200)
        json_text = export_df.to_dict(orient="records")
        st.download_button("JSON herunterladen", data=json.dumps(json_text, ensure_ascii=False, indent=2).encode("utf-8"),
                           file_name="Winterplan.json", mime="application/json")

    # ----- Date selection -----
    valid_days = sorted(df_edit["Datum_dt"].dropna().dt.date.unique())
    if not valid_days:
        st.warning("Keine Daten vorhanden."); st.stop()

    sel_day = st.date_input("Datum wählen", value=valid_days[-1])
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
    st.caption("Sortierung: **Saison** ↑, **Woche** ↑, **Rang** ↑. **⛔** zeigt Gründe im Expander.")

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
            exclusions = set(current_players)  # exclude only current match members
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
                # preview after replace
                df_after = df_edit.copy()
                mask_row = (df_after.index == sel_match_id)
                if mask_row.any():
                    df_after.loc[mask_row] = df_after.loc[mask_row].apply(
                        lambda r: replace_player_in_row(r, out_choice, repl_choice), axis=1
                    )

                # authoritative violations for changed row
                violations = check_min_rules_for_mask(df_after, mask_row, sel_day)

                # candidate-specific reasons (simulated add)
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
                        res = github_put_file(csv_bytes, msg, branch_override=st.secrets.get("GITHUB_BRANCH", "main"))
                        new_ref = (res.get("commit") or {}).get("sha")
                        st.session_state["csv_ref"] = new_ref or st.secrets.get("GITHUB_BRANCH", "main")
                        st.success("Gespeichert ✅")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Speichern fehlgeschlagen: {e}")

    st.markdown("---")
    # ================= 2) SWAP =================
    st.markdown("### 2) **Zwei Matches**: Spieler **tauschen**")
    st.caption("Tausche je **einen** Spieler zwischen zwei Matches am selben Datum. Override möglich.")

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
                    res = github_put_file(csv_bytes, msg, branch_override=st.secrets.get("GITHUB_BRANCH", "main"))
                    new_ref = (res.get("commit") or {}).get("sha")
                    st.session_state["csv_ref"] = new_ref or st.secrets.get("GITHUB_BRANCH", "main")
                    st.success("Gespeichert ✅")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Speichern fehlgeschlagen: {e}")

    # ---------- Preview & Reset ----------
    st.markdown("---")
    st.subheader("Vorschau – Tagesplan")
    preview = st.session_state.df_edit[st.session_state.df_edit["Datum_dt"].dt.date.eq(sel_day)].sort_values(
        ["Datum_dt", "Startzeit_sort", "Slot"]
    )
    st.dataframe(preview[["Datum","Tag","Slot","Typ","Spieler"]], width="stretch")

    if st.button("↩️ Änderungen verwerfen (Reset)"):
        st.session_state.df_edit = df.copy()
        st.rerun()

# ============================ TAB 4: KOSTEN ============================
with tab4:
    st.header("Spieler-Kosten (Saison)")
    st.caption("Gerichtsgebühr: **17,50 €/h**. Einzel = 2 Spieler, Doppel = 4 Spieler. "
               "Ungenutzte Slots (auch an 24.12/25.12/31.12) werden proportional zu den **gespielten Minuten** verteilt.")

    per_player_df, totals, allowed_calendar = compute_player_costs(df, df_exp)

    c1, c2, c3 = st.columns(3)
    c1.metric("Summe direkte Kosten", f"{totals['direct_cost_total']:.2f} €")
    c2.metric("Summe ungenutzte Plätze", f"{totals['unused_cost_total']:.2f} €")
    c3.metric("Gesamt verrechnet", f"{totals['charged_total']:.2f} €")

    st.subheader("Kosten pro Spieler (Saison)")
    st.dataframe(per_player_df, width="stretch")

    # Downloads
    st.download_button(
        "CSV herunterladen (Spieler-Kosten)",
        data=per_player_df.to_csv(index=False).encode("utf-8"),
        file_name="spieler_kosten.csv",
        mime="text/csv"
    )

    with st.expander("Details: Kalender der erlaubten Slots (genutzt/ungenutzt)"):
        if isinstance(allowed_calendar, pd.DataFrame) and not allowed_calendar.empty:
            show_df = allowed_calendar.copy()
            show_df["Datum"] = pd.to_datetime(show_df["Datum"]).dt.strftime("%Y-%m-%d")
            show_df["court_cost"] = show_df["court_cost"].round(2)
            st.dataframe(show_df.sort_values(["Datum", "Tag", "Slot"]), width="stretch")
        else:
            st.info("Kein Slot-Kalender generiert (fehlende Saisondaten).")

# ============================ TAB 5: AUTO-POPULATION ============================
with tab5:
    st.header("Auto-Population: Leere Slots automatisch füllen")
    st.caption("Nutzt CSV-Präferenzen, Verfügbarkeit, Urlaube und Load-Balancing, um leere Slots fair zu füllen.")

    if not check_edit_password():
        st.stop()

    # Initialize working copy
    if "df_autofill" not in st.session_state:
        st.session_state.df_autofill = df.copy()

    df_autofill = st.session_state.df_autofill

    # Find empty slots
    empty_slots = find_empty_slots(df_autofill)

    st.subheader("Leere Slots")
    st.write(f"**{len(empty_slots)}** leere Slots gefunden.")

    if empty_slots:
        # Show sample of empty slots
        with st.expander(f"Zeige die ersten {min(10, len(empty_slots))} leeren Slots"):
            sample_slots = empty_slots[:10]
            for slot in sample_slots:
                st.write(f"- {slot['Datum']} ({slot['Tag']}) — {slot['Slot']} — {slot['Typ']}")

        st.markdown("---")
        st.subheader("Auto-Population Einstellungen")

        col1, col2 = st.columns(2)
        with col1:
            max_slots = st.number_input(
                "Max. Anzahl Slots zu füllen",
                min_value=1,
                max_value=len(empty_slots),
                value=min(10, len(empty_slots)),
                help="Anzahl der Slots, die automatisch gefüllt werden sollen"
            )
        with col2:
            only_legal = st.checkbox(
                "Nur legale Zuweisungen (keine Regelverstöße)",
                value=True,
                help="Wenn aktiviert, werden nur Slots gefüllt, bei denen alle Spieler keine Regelverstöße haben"
            )

        st.markdown("---")

        # Preview mode
        if st.button("🔍 Vorschau generieren (ohne Speichern)", key="btn_autofill_preview"):
            with st.spinner("Generiere Auto-Population..."):
                df_result, filled_slots, skipped_slots = autopopulate_plan(
                    df_autofill, max_slots=max_slots, only_legal=only_legal
                )
                st.session_state.df_autofill_result = df_result
                st.session_state.filled_slots = filled_slots
                st.session_state.skipped_slots = skipped_slots

        # Show results
        if "df_autofill_result" in st.session_state:
            filled = st.session_state.get("filled_slots", [])
            skipped = st.session_state.get("skipped_slots", [])

            st.success(f"✅ **{len(filled)}** Slots erfolgreich gefüllt!")
            if skipped:
                st.warning(f"⚠️ **{len(skipped)}** Slots übersprungen (keine geeigneten Spieler gefunden)")

            # Show filled slots
            if filled:
                with st.expander(f"✅ Gefüllte Slots anzeigen ({len(filled)})"):
                    for slot in filled:
                        players_str = ", ".join(slot["players"])
                        st.write(f"- **{slot['Datum']}** ({slot['Tag']}) — {slot['Slot']} — {slot['Typ']}  \n  → {players_str}")

            # Show skipped slots
            if skipped:
                with st.expander(f"⚠️ Übersprungene Slots anzeigen ({len(skipped)})"):
                    for slot in skipped:
                        st.write(f"- {slot['Datum']} ({slot['Tag']}) — {slot['Slot']} — {slot['Typ']}")

            st.markdown("---")
            st.subheader("Vorschau des aktualisierten Plans")

            # Show statistics comparison
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Vorher: Slots", len(df_autofill))
            with col2:
                st.metric("Nachher: Slots", len(st.session_state.df_autofill_result))
            with col3:
                st.metric("Hinzugefügt", len(filled), delta=len(filled))

            # Show player statistics
            st.subheader("Spieler-Verteilung nach Auto-Population")
            df_result_exp = st.session_state.df_autofill_result.explode("Spieler_list").rename(columns={"Spieler_list": "Spieler_Name"})
            player_counts = df_result_exp["Spieler_Name"].value_counts().reset_index()
            player_counts.columns = ["Spieler", "Anzahl Matches"]
            st.dataframe(player_counts, width="stretch")

            # Save button
            st.markdown("---")
            if st.button("💾 Plan speichern und auf GitHub hochladen", key="btn_autofill_save"):
                try:
                    df_to_save = st.session_state.df_autofill_result[["Datum", "Tag", "Slot", "Typ", "Spieler"]]
                    csv_bytes = df_to_save.to_csv(index=False).encode("utf-8")
                    msg = f"Auto-populated {len(filled)} slots using load balancing and preferences"
                    res = github_put_file(csv_bytes, msg, branch_override=st.secrets.get("GITHUB_BRANCH", "main"))
                    new_ref = (res.get("commit") or {}).get("sha")
                    st.session_state["csv_ref"] = new_ref or st.secrets.get("GITHUB_BRANCH", "main")
                    st.success("✅ Plan erfolgreich gespeichert!")
                    st.cache_data.clear()
                    # Clear autofill state
                    st.session_state.pop("df_autofill", None)
                    st.session_state.pop("df_autofill_result", None)
                    st.session_state.pop("filled_slots", None)
                    st.session_state.pop("skipped_slots", None)
                    st.rerun()
                except Exception as e:
                    st.error(f"Speichern fehlgeschlagen: {e}")

            # Reset button
            if st.button("↩️ Vorschau verwerfen", key="btn_autofill_reset"):
                st.session_state.pop("df_autofill_result", None)
                st.session_state.pop("filled_slots", None)
                st.session_state.pop("skipped_slots", None)
                st.rerun()

    else:
        st.info("🎉 Keine leeren Slots gefunden! Der Plan ist vollständig.")

    # Documentation
    with st.expander("ℹ️ Wie funktioniert Auto-Population?"):
        st.markdown("""
        **Auto-Population-Algorithmus:**

        1. **Leere Slots identifizieren:** Findet alle erlaubten Slots, die noch nicht im Plan sind
        2. **Spieler-Kandidaten bewerten:**
           - Prüft Verfügbarkeit (Wochentag, Urlaube)
           - Prüft Präferenzen (nur Einzel/nur Doppel)
           - Prüft geschützte Spieler-Regeln
           - Zählt bisherige Einsätze (Woche & Saison)
        3. **Load Balancing:** Priorisiert Spieler mit weniger Einsätzen
        4. **Regelkonformität:**
           - Einzel: Rang-Unterschied ≤ 2
           - Doppel: 4 verfügbare Spieler
        5. **Zuweisung:** Füllt Slots mit am wenigsten genutzten, legalen Spielern

        **Datenquellen:**
        - `Spieler_Preferences_2026.csv`: Verfügbarkeit, Präferenzen, Urlaube
        - `RANK`: Spieler-Rankings
        - Geschützte Regeln: Spezielle Zeitfenster für bestimmte Spieler
        """)

