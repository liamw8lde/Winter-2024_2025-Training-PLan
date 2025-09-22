import streamlit as st
import pandas as pd
import re
import base64, json, requests
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

    # Extract from Slot like "D20:00-120 PLA"
    t = df["Slot"].str.extract(r"^([ED])(\d{2}:\d{2})-([0-9]+)\s+PL([AB])$")
    df["S_Art"] = t[0].fillna("")
    df["S_Time"] = t[1].fillna("00:00")
    df["S_Dur"] = t[2].fillna("0")
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
# =============== ONLY THE NEEDED RULE SOURCES =================
# ==============================================================

# ---- Jotform weekday availability (treated as HARD now) ----
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

# ---- Global blackouts (any year) ----
BLACKOUT_MMDD = {(12, 24), (12, 25), (12, 31)}

# ---- Holidays (authoritative list) ----
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

def swap_players_in_row(row, a_name, b_name):
    players = split_players(row["Spieler"])
    for i, p in enumerate(players):
        if p == a_name:
            players[i] = b_name
        elif p == b_name:
            players[i] = a_name
    row["Spieler"] = join_players(players)
    return row

def check_min_rules_for_row(row, d: date):
    """
    Only two checks (HARD):
      1) holiday / blackout
      2) weekday availability
    Return list of violation strings.
    """
    v = []
    players = split_players(row["Spieler"])
    tag = str(row["Tag"])
    # 1) Holiday
    for p in players:
        if is_holiday(p, d):
            v.append(f"{p}: Urlaub/Blackout am {d}.")
    # 2) Weekday availability
    for p in players:
        days = JOTFORM.get(p)
        if days is not None and tag not in days:
            v.append(f"{p}: laut Jotform nicht verfügbar an {tag}.")
    return v

def check_min_rules_for_swap(df_plan: pd.DataFrame, mask_rows, d: date):
    v = []
    rows = df_plan[mask_rows]
    for _, r in rows.iterrows():
        v += [f"{r['Tag']} {r['Slot']}: {msg}" for msg in check_min_rules_for_row(r, d)]
    return sorted(set(v))

# --------------------------- UI ---------------------------
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

    # ---- Build hypothetical plan after swap (two rows) ----
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

    # ---- Minimal rule check: holidays + weekday availability for the two affected rows ----
    masks_two = mask_a | mask_b
    violations = check_min_rules_for_swap(df_after, masks_two, sel_day)

    if violations:
        st.error("Regelverletzungen (nur Urlaub & Wochentag):")
        for m in violations:
            st.write("•", m)

    # ---- Swap button: disabled if violations exist ----
    if st.button("🔁 Spieler tauschen & auf GitHub speichern", disabled=bool(violations)):
        # Commit swap to editable DataFrame
        st.session_state.df_edit = df_after

        # Save to GitHub main
        try:
            to_save = st.session_state.df_edit[["Datum","Tag","Slot","Typ","Spieler"]]
            csv_bytes = to_save.to_csv(index=False).encode("utf-8")
            msg = f"Swap {pA} ↔ {pB} on {sel_day} via Streamlit"
            res = github_put_file(csv_bytes, msg, branch_override=st.secrets.get("GITHUB_BRANCH", "main"))
            sha = res.get("commit", {}).get("sha", "")[:7]
            st.success(f"Gespeichert auf GitHub (main) ✅ Commit {sha}")
        except Exception as e:
            st.error(f"GitHub-Speicherung fehlgeschlagen: {e}")

    # Preview edited day
    st.subheader("Vorschau – Tagesplan nach Tausch")
    preview = df_after[df_after["Datum_dt"].dt.date.eq(sel_day)].sort_values(["Datum_dt","Startzeit_sort","Slot"])
    st.dataframe(preview[["Datum","Tag","Slot","Typ","Spieler"]], use_container_width=True)

    # Optional reset
    if st.button("↩️ Änderungen verwerfen (Reset)"):
        st.session_state.df_edit = df.copy()
        st.rerun()
