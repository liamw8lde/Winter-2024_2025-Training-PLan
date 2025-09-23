import streamlit as st
import pandas as pd
import re
import base64, json, requests, io
from datetime import date, datetime

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
(df, df_exp, current_sha), _ = data_tuple
st.session_state["csv_sha"] = current_sha
if warn:
    st.warning(warn)

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

# ---- Jotform weekday availability (treated as HARD here) ----
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
... (omitted here for brevity; keep your full RAW_HOLIDAYS block unchanged) ...
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
    # Use commit sha (valid ref for Contents API). Do NOT use content.sha (blob sha).
    new_ref = (res.get("commit") or {}).get("sha")
    if new_ref:
        st.session_state["csv_ref"] = new_ref
    else:
        # fallback: stick to branch HEAD on next reload
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
            # Candidate pool (all players, show legal/violations)
            def singles_opponent(row, out_player: str):
                players = [p for p in split_players(row["Spieler"]) if p != out_player]
                if row["Typ"].lower().startswith("einzel") and len(players) == 1:
                    return players[0]
                return None

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
                        _set_ref_after_save(res)  # <<< use commit sha only
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
                    _set_ref_after_save(res)  # <<< use commit sha only
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
