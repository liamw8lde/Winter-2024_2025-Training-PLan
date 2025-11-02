import streamlit as st
import pandas as pd
import re
import base64, json, requests, io
from datetime import date, datetime, timedelta

# ==================== PAGE CONFIG ====================
st.set_page_config(
    page_title="Training Plan 2026 Auto-Population",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.title("🎾 Training Plan 2026 Auto-Population")
st.caption("Automatically fill empty training slots for Winter 2026 season (Jan - Apr)")

# ==================== CONFIGURATION ====================
EDIT_PASSWORD = "tennis"
COURT_RATE_PER_HOUR = 17.50

# 2026 SEASON SPECIFIC
PLAN_FILE = "Winterplan_2026.csv"
PREFS_FILE = "Spieler_Preferences_2026.csv"
RANK_FILE = "Player_Ranks_2026.csv"
SEASON_START = date(2026, 1, 5)  # First Monday of January 2026
SEASON_END = date(2026, 4, 26)   # Last date in preferences

# Allowed weekly slots
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

WEEKDAY_TO_ISO = {"Montag": 1, "Mittwoch": 3, "Donnerstag": 4}
BLACKOUT_MMDD = {(12, 24), (12, 25), (12, 31)}

# Player rankings (1 = strongest, 6 = weakest) - FALLBACK if CSV fails
RANK_FALLBACK = {
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

WOMEN_SINGLE_BAN = {"Anke Ihde", "Lena Meiss", "Martina Schmidt", "Kerstin Baarck"}

# ==================== DATA LOADING ====================
@st.cache_data(show_spinner=False)
def load_plan_csv(file_path):
    """Load and process the training plan CSV"""
    try:
        df = pd.read_csv(file_path, dtype=str)
        return postprocess_plan(df)
    except Exception as e:
        st.error(f"Error loading plan from {file_path}: {e}")
        return None, None

@st.cache_data(show_spinner=False)
def load_preferences_csv(file_path):
    """Load player preferences CSV"""
    try:
        df = pd.read_csv(file_path, dtype=str)
        return df
    except Exception as e:
        st.warning(f"Could not load preferences from {file_path}: {e}")
        return pd.DataFrame()

@st.cache_data(show_spinner=False)
def load_ranks_csv(file_path):
    """Load player rankings from CSV (1=strongest, 6=weakest)"""
    try:
        df = pd.read_csv(file_path)
        rank_dict = {}
        for _, row in df.iterrows():
            name = str(row.get("Spieler", "")).strip()
            rank = row.get("Rank")
            if name and pd.notna(rank):
                rank_dict[name] = int(rank)
        return rank_dict
    except Exception as e:
        st.warning(f"Could not load ranks from {file_path}: {e}. Using fallback.")
        return RANK_FALLBACK

def postprocess_plan(df):
    """Process plan DataFrame and add computed columns"""
    required = ["Datum", "Tag", "Slot", "Typ", "Spieler"]
    for c in required:
        df[c] = df[c].astype(str).str.strip()

    # Parse dates (handle both German and ISO formats)
    s = df["Datum"].astype(str).str.strip()
    d1 = pd.to_datetime(s, format="%d.%m.%Y", errors="coerce")
    d2 = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    df["Datum_dt"] = d1.fillna(d2)

    # ISO calendar
    iso = df["Datum_dt"].dt.isocalendar()
    df["Jahr"] = iso["year"]
    df["Woche"] = iso["week"]

    # Extract slot details
    t = df["Slot"].str.extract(r"^([ED])(\d{2}:\d{2})-([0-9]+)\s+PL([AB])$")
    df["S_Art"]   = t[0].fillna("")
    df["S_Time"]  = t[1].fillna("00:00")
    df["S_Dur"]   = t[2].fillna("0")
    df["S_Court"] = t[3].fillna("")

    # Player list
    df["Spieler_list"] = df["Spieler"].str.split(",").apply(
        lambda xs: [x.strip() for x in xs if str(x).strip()]
    )

    # Exploded view
    df_exp = df.explode("Spieler_list").rename(columns={"Spieler_list": "Spieler_Name"})

    return df, df_exp

# ==================== PREFERENCE FUNCTIONS ====================
def get_available_days(df_prefs):
    """Extract available days for each player"""
    result = {}
    if df_prefs.empty:
        return result

    for _, row in df_prefs.iterrows():
        name = str(row.get("Spieler", "")).strip()
        if not name:
            continue
        days_str = str(row.get("AvailableDays", ""))
        days = set()
        for sep in [",", ";"]:
            if sep in days_str:
                days = {d.strip() for d in days_str.split(sep) if d.strip()}
                break
        else:
            if days_str.strip():
                days = {days_str.strip()}
        result[name] = days
    return result

def get_player_preferences(df_prefs):
    """Extract match type preferences"""
    result = {}
    if df_prefs.empty:
        return result

    for _, row in df_prefs.iterrows():
        name = str(row.get("Spieler", "")).strip()
        if not name:
            continue
        pref = str(row.get("Preference", "keine Präferenz")).strip()
        result[name] = pref
    return result

def parse_blocked_ranges(blocked_str):
    """Parse blocked date ranges from CSV"""
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

def parse_blocked_days(blocked_str):
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

def load_holidays(df_prefs):
    """Load all holidays from preferences CSV"""
    holidays = {}
    if df_prefs.empty:
        return holidays

    for _, row in df_prefs.iterrows():
        name = str(row.get("Spieler", "")).strip()
        if not name:
            continue

        blocked_ranges = parse_blocked_ranges(row.get("BlockedRanges", ""))
        blocked_days = parse_blocked_days(row.get("BlockedDays", ""))

        all_periods = blocked_ranges + blocked_days
        if all_periods:
            holidays[name] = holidays.get(name, []) + all_periods

    return holidays

def is_holiday(name, d, holidays_dict):
    """Check if date is a holiday for player"""
    if (d.month, d.day) in BLACKOUT_MMDD:
        return True
    ranges = holidays_dict.get(name, [])
    return any(start <= d <= end for (start, end) in ranges)

# ==================== VALIDATION FUNCTIONS ====================
def week_of(d):
    iso = pd.Timestamp(d).isocalendar()
    return int(iso.year), int(iso.week)

def count_week(df_plan, name, d):
    y, w = week_of(d)
    wk = df_plan[(df_plan["Jahr"] == y) & (df_plan["Woche"] == w)]
    return int(wk["Spieler"].str.contains(fr"\b{re.escape(name)}\b", regex=True).sum())

def count_season(df_plan, name):
    return int(df_plan["Spieler"].str.contains(fr"\b{re.escape(name)}\b", regex=True).sum())

def count_wed20(df_plan, name):
    mask = (
        (df_plan["Tag"] == "Mittwoch") &
        (df_plan["S_Time"] == "20:00") &
        (df_plan["Spieler"].str.contains(fr"\b{re.escape(name)}\b", regex=True))
    )
    return int(mask.sum())

def count_18_19(df_plan, name):
    mask = (
        (df_plan["S_Time"].isin(["18:00", "19:00"])) &
        (df_plan["Spieler"].str.contains(fr"\b{re.escape(name)}\b", regex=True))
    )
    return int(mask.sum())

def check_violations(name, tag, s_time, typ, df_after, d, available_days, preferences, holidays):
    """Check all violations for a player assignment"""
    violations = []

    # Holiday check
    if is_holiday(name, d, holidays):
        violations.append(f"{name}: Urlaub/Blackout am {d}.")

    # Weekday availability
    days = available_days.get(name)
    if days is not None and tag not in days:
        violations.append(f"{name}: nicht verfügbar an {tag}.")

    # Protected player rules
    if name == "Patrick Buehrsch" and s_time != "18:00":
        violations.append(f"{name}: nur 18:00 erlaubt.")
    if name == "Frank Petermann" and s_time not in {"19:00", "20:00"}:
        violations.append(f"{name}: nur 19:00 oder 20:00 erlaubt.")
    if name == "Matthias Duddek" and s_time not in {"18:00", "19:00"}:
        violations.append(f"{name}: nur 18:00 oder 19:00.")
    if name == "Dirk Kistner":
        if tag not in {"Montag", "Mittwoch", "Donnerstag"}:
            violations.append(f"{name}: nur Mo/Mi/Do.")
        if tag == "Mittwoch" and s_time != "19:00":
            violations.append(f"{name}: am Mittwoch nur 19:00.")
        if count_week(df_after, name, d) > 2:
            violations.append(f"{name}: max 2/Woche überschritten.")
    if name == "Arndt Stueber" and not (tag == "Mittwoch" and s_time == "19:00"):
        violations.append(f"{name}: nur Mittwoch 19:00.")
    if name in {"Thommy Grueneberg", "Thomas Grueneberg"}:
        total_after = count_season(df_after, name)
        wed20_after = count_wed20(df_after, name)
        early_after = count_18_19(df_after, name)
        if total_after > 0:
            if wed20_after / total_after > 0.30:
                violations.append(f"{name}: Anteil Mi 20:00 > 30%.")
            if early_after / total_after < 0.70:
                violations.append(f"{name}: Anteil 18/19 < 70%.")
    if name == "Jens Hafner" and not (tag == "Mittwoch" and s_time == "19:00"):
        violations.append(f"{name}: nur Mittwoch 19:00.")
    if typ.lower().startswith("einzel") and name in WOMEN_SINGLE_BAN:
        violations.append(f"{name}: Frauen dürfen kein Einzel spielen.")

    # Type preferences
    pref = preferences.get(name, "keine Präferenz")
    if pref == "nur Einzel" and typ.lower().startswith("doppel"):
        violations.append(f"{name}: möchte nur Einzel spielen.")
    elif pref == "nur Doppel" and typ.lower().startswith("einzel"):
        violations.append(f"{name}: möchte nur Doppel spielen.")

    return violations

# ==================== SLOT GENERATION ====================
def generate_allowed_slots_calendar_2026():
    """Generate all allowed slots for 2026 season"""
    out = []
    current_date = SEASON_START

    # Iterate through all dates in the season
    while current_date <= SEASON_END:
        # Get German weekday name
        weekday_iso = current_date.isoweekday()  # 1=Monday, 7=Sunday
        german_weekday = None

        if weekday_iso == 1:
            german_weekday = "Montag"
        elif weekday_iso == 3:
            german_weekday = "Mittwoch"
        elif weekday_iso == 4:
            german_weekday = "Donnerstag"

        # If this is a training day, add all slots for it
        if german_weekday and german_weekday in ALLOWED_SLOTS:
            for slot_code, typ_text in ALLOWED_SLOTS[german_weekday]:
                m = re.search(r"-([0-9]+)\s+PL[AB]$", slot_code)
                minutes = int(m.group(1)) if m else 0
                out.append({
                    "Datum": current_date,
                    "Tag": german_weekday,
                    "Slot": slot_code,
                    "Typ": typ_text,
                    "Minutes": minutes,
                })

        current_date += timedelta(days=1)

    return out

def find_empty_slots(df_plan):
    """Find all empty slots in the plan"""
    allowed = generate_allowed_slots_calendar_2026()
    used_pairs = set(zip(pd.to_datetime(df_plan["Datum_dt"]).dt.date, df_plan["Slot"]))

    empty = []
    for slot in allowed:
        pair = (slot["Datum"], slot["Slot"])
        if pair not in used_pairs:
            empty.append(slot)

    return empty

# ==================== AUTOPOPULATION ALGORITHM ====================
def select_singles_pair(candidates):
    """Select 2 players for singles with rank difference ≤ 2"""
    for i, c1 in enumerate(candidates):
        if c1["has_violations"]:
            break
        for c2 in candidates[i+1:]:
            if c2["has_violations"]:
                break
            r1 = c1["rank"]
            r2 = c2["rank"]
            if r1 != 999 and r2 != 999 and abs(r1 - r2) <= 2:
                return [c1["name"], c2["name"]]
    return None

def select_doubles_team(candidates, num_players=4):
    """Select 4 players for doubles"""
    legal = [c for c in candidates if not c["has_violations"]]
    if len(legal) >= num_players:
        return [c["name"] for c in legal[:num_players]]
    return None

def select_players_for_slot(df_plan, slot_info, all_players, available_days, preferences, holidays):
    """Select appropriate players for a slot"""
    datum = slot_info["Datum"]
    tag = slot_info["Tag"]
    slot_code = slot_info["Slot"]
    typ = slot_info["Typ"]

    time_match = re.search(r"(\d{2}:\d{2})", slot_code)
    slot_time = time_match.group(1) if time_match else "00:00"

    num_players = 4 if typ.lower().startswith("doppel") else 2

    # Score all candidates
    candidates = []
    for name in all_players:
        y, w = week_of(datum)
        wk = df_plan[(df_plan["Jahr"] == y) & (df_plan["Woche"] == w)]
        week_count = int(wk["Spieler"].str.contains(fr"\b{re.escape(name)}\b", regex=True).sum())
        season_count = int(df_plan["Spieler"].str.contains(fr"\b{re.escape(name)}\b", regex=True).sum())
        rk = RANK.get(name, 999)

        # Simulate adding player
        y, w = week_of(datum)
        virtual = pd.DataFrame([{
            "Tag": tag, "S_Time": slot_time, "Typ": typ, "Spieler": name,
            "Jahr": y, "Woche": w
        }])
        df_virtual = pd.concat([df_plan, virtual], ignore_index=True)

        viol = check_violations(name, tag, slot_time, typ, df_virtual, datum, available_days, preferences, holidays)

        candidates.append({
            "name": name,
            "week": week_count,
            "season": season_count,
            "rank": rk,
            "violations": viol,
            "has_violations": len(viol) > 0,
        })

    # Filter by type preference
    filtered = []
    for c in candidates:
        pref = preferences.get(c["name"], "keine Präferenz")
        if pref == "nur Einzel" and typ.lower().startswith("doppel"):
            continue
        if pref == "nur Doppel" and typ.lower().startswith("einzel"):
            continue
        filtered.append(c)

    # Sort: legal first, then by usage (season, week), then rank
    filtered.sort(key=lambda x: (x["has_violations"], x["season"], x["week"], x["rank"], x["name"]))

    # Select players
    if typ.lower().startswith("einzel"):
        return select_singles_pair(filtered)
    else:
        return select_doubles_team(filtered, num_players)

def autopopulate_plan(df_plan, max_slots, only_legal, all_players, available_days, preferences, holidays):
    """Main autopopulation function"""
    df_result = df_plan.copy()
    empty_slots = find_empty_slots(df_result)

    filled_count = 0
    filled_slots = []
    skipped_slots = []

    for slot_info in empty_slots:
        if max_slots and filled_count >= max_slots:
            break

        players = select_players_for_slot(
            df_result, slot_info, all_players, available_days, preferences, holidays
        )

        if players is None:
            skipped_slots.append(slot_info)
            continue

        # Check violations if only_legal
        if only_legal:
            time_match = re.search(r"(\d{2}:\d{2})", slot_info["Slot"])
            slot_time = time_match.group(1) if time_match else "00:00"

            has_violations = any(
                check_violations(p, slot_info["Tag"], slot_time, slot_info["Typ"],
                               df_result, slot_info["Datum"], available_days, preferences, holidays)
                for p in players
            )
            if has_violations:
                skipped_slots.append(slot_info)
                continue

        # Add new row
        new_row = pd.DataFrame([{
            "Datum": slot_info["Datum"].strftime("%Y-%m-%d"),
            "Tag": slot_info["Tag"],
            "Slot": slot_info["Slot"],
            "Typ": slot_info["Typ"],
            "Spieler": ", ".join(players),
        }])

        df_result = pd.concat([df_result, new_row], ignore_index=True)
        df_result, _ = postprocess_plan(df_result[["Datum", "Tag", "Slot", "Typ", "Spieler"]])

        filled_count += 1
        filled_slots.append({**slot_info, "players": players})

    return df_result, filled_slots, skipped_slots

# ==================== GITHUB FUNCTIONS ====================
def github_headers():
    token = st.secrets.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GitHub token missing")
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

def github_put_file(csv_bytes, message, file_path):
    """Save CSV to GitHub"""
    repo = st.secrets.get("GITHUB_REPO")
    branch = st.secrets.get("GITHUB_BRANCH", "main")

    if not repo:
        raise RuntimeError("GITHUB_REPO not set in secrets")

    # Get current SHA
    url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    r = requests.get(url, headers=github_headers(), params={"ref": branch}, timeout=20)
    sha = None
    if r.status_code == 200:
        sha = r.json().get("sha")

    # Upload
    payload = {
        "message": message,
        "content": base64.b64encode(csv_bytes).decode("utf-8"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=github_headers(), data=json.dumps(payload), timeout=20)
    if r.status_code in (200, 201):
        return r.json()
    raise RuntimeError(f"GitHub PUT failed {r.status_code}: {r.text}")

# ==================== MAIN APP ====================
# Password protection
def check_password():
    if st.session_state.get("authenticated", False):
        return True

    with st.form("login_form"):
        st.write("🔒 Diese App ist passwortgeschützt")
        password = st.text_input("Passwort", type="password")
        submitted = st.form_submit_button("Einloggen")

        if submitted:
            if password == EDIT_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Falsches Passwort")
    return False

if not check_password():
    st.stop()

# Load data
with st.spinner("Lade 2026 Daten..."):
    df_plan, df_exp = load_plan_csv(PLAN_FILE)
    df_prefs = load_preferences_csv(PREFS_FILE)
    RANK = load_ranks_csv(RANK_FILE)

if df_plan is None:
    st.error(f"Konnte {PLAN_FILE} nicht laden!")
    st.info(f"Bitte stelle sicher, dass {PLAN_FILE} im gleichen Ordner ist.")
    st.stop()

# Extract preferences
available_days = get_available_days(df_prefs)
preferences = get_player_preferences(df_prefs)
holidays = load_holidays(df_prefs)
all_players = sorted(df_prefs["Spieler"].dropna().unique().tolist()) if not df_prefs.empty else []

# Show rank source info
if RANK == RANK_FALLBACK:
    st.sidebar.warning(f"⚠️ Rankings from fallback (CSV not found)")
else:
    st.sidebar.success(f"✅ Rankings loaded from {RANK_FILE}")

# Initialize state
if "df_work" not in st.session_state:
    st.session_state.df_work = df_plan.copy()

# ==================== UI ====================
st.info(f"📅 **Saison:** {SEASON_START.strftime('%d.%m.%Y')} bis {SEASON_END.strftime('%d.%m.%Y')} (Januar - April 2026)")
st.markdown("---")

# Current status
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Aktueller Plan", f"{len(df_plan)} Slots")
with col2:
    st.metric("Spieler verfügbar", len(all_players))
with col3:
    empty_count = len(find_empty_slots(st.session_state.df_work))
    st.metric("Leere Slots", empty_count)
with col4:
    total_possible = len(generate_allowed_slots_calendar_2026())
    st.metric("Gesamt möglich", total_possible)

st.markdown("---")

# Find empty slots
empty_slots = find_empty_slots(st.session_state.df_work)

if empty_slots:
    st.header("📋 Leere Slots für 2026")
    st.write(f"Es gibt **{len(empty_slots)}** leere Slots, die gefüllt werden können.")

    # Show sample
    with st.expander(f"Zeige erste {min(20, len(empty_slots))} leere Slots"):
        for i, slot in enumerate(empty_slots[:20]):
            st.write(f"{i+1}. {slot['Datum']} ({slot['Tag']}) — {slot['Slot']} — {slot['Typ']}")

    st.markdown("---")

    # Settings
    st.header("⚙️ Auto-Population Einstellungen")

    col1, col2 = st.columns(2)
    with col1:
        max_slots = st.number_input(
            "Maximale Anzahl Slots zu füllen",
            min_value=1,
            max_value=len(empty_slots),
            value=min(50, len(empty_slots)),
            help="Wie viele Slots sollen automatisch gefüllt werden?"
        )
    with col2:
        only_legal = st.checkbox(
            "Nur legale Zuweisungen (keine Verstöße)",
            value=True,
            help="Wenn aktiv, werden nur Slots mit 100% regelkonformen Spielern gefüllt"
        )

    st.markdown("---")

    # Actions
    col_preview, col_reset = st.columns(2)
    with col_preview:
        if st.button("🔍 Vorschau generieren", use_container_width=True, type="primary"):
            with st.spinner("Generiere Auto-Population für 2026..."):
                df_result, filled, skipped = autopopulate_plan(
                    st.session_state.df_work,
                    max_slots,
                    only_legal,
                    all_players,
                    available_days,
                    preferences,
                    holidays
                )
                st.session_state.df_result = df_result
                st.session_state.filled_slots = filled
                st.session_state.skipped_slots = skipped
                st.rerun()

    with col_reset:
        if st.button("🔄 Plan zurücksetzen", use_container_width=True):
            st.session_state.df_work = df_plan.copy()
            st.session_state.pop("df_result", None)
            st.session_state.pop("filled_slots", None)
            st.session_state.pop("skipped_slots", None)
            st.rerun()

    # Show results if available
    if "df_result" in st.session_state:
        st.markdown("---")
        st.header("✅ Ergebnisse für 2026")

        filled = st.session_state.get("filled_slots", [])
        skipped = st.session_state.get("skipped_slots", [])

        col1, col2 = st.columns(2)
        with col1:
            st.success(f"**{len(filled)}** Slots erfolgreich gefüllt")
        with col2:
            if skipped:
                st.warning(f"**{len(skipped)}** Slots übersprungen")

        # Filled slots details
        if filled:
            with st.expander(f"✅ Gefüllte Slots ({len(filled)})"):
                for slot in filled:
                    players_str = ", ".join(slot["players"])
                    st.write(f"**{slot['Datum']}** ({slot['Tag']}) — {slot['Slot']} — {slot['Typ']}")
                    st.write(f"  → {players_str}")
                    st.write("")

        # Skipped slots details
        if skipped:
            with st.expander(f"⚠️ Übersprungene Slots ({len(skipped)})"):
                for slot in skipped:
                    st.write(f"• {slot['Datum']} ({slot['Tag']}) — {slot['Slot']} — {slot['Typ']}")

        # Statistics
        st.markdown("---")
        st.subheader("📊 Statistiken")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Vorher", len(st.session_state.df_work))
        with col2:
            st.metric("Nachher", len(st.session_state.df_result))
        with col3:
            st.metric("Hinzugefügt", len(filled), delta=f"+{len(filled)}")

        # Player distribution
        st.subheader("👥 Spieler-Verteilung 2026")
        _, df_result_exp = postprocess_plan(st.session_state.df_result[["Datum", "Tag", "Slot", "Typ", "Spieler"]])
        player_counts = df_result_exp["Spieler_Name"].value_counts().reset_index()
        player_counts.columns = ["Spieler", "Anzahl Matches"]
        st.dataframe(player_counts, use_container_width=True, height=400)

        # Save buttons
        st.markdown("---")
        col_save, col_download, col_discard = st.columns(3)

        with col_save:
            if st.button("💾 Auf GitHub speichern (2026)", use_container_width=True, type="primary"):
                try:
                    df_to_save = st.session_state.df_result[["Datum", "Tag", "Slot", "Typ", "Spieler"]]
                    csv_bytes = df_to_save.to_csv(index=False).encode("utf-8")
                    msg = f"Auto-populate {len(filled)} slots for 2026 season\n\n🤖 Generated with Claude Code"
                    github_put_file(csv_bytes, msg, PLAN_FILE)
                    st.success(f"✅ Erfolgreich auf GitHub als {PLAN_FILE} gespeichert!")
                    st.balloons()
                    # Clear state
                    st.session_state.df_work = st.session_state.df_result.copy()
                    st.session_state.pop("df_result", None)
                    st.session_state.pop("filled_slots", None)
                    st.session_state.pop("skipped_slots", None)
                except Exception as e:
                    st.error(f"Fehler beim Speichern: {e}")

        with col_download:
            df_to_save = st.session_state.df_result[["Datum", "Tag", "Slot", "Typ", "Spieler"]]
            csv_bytes = df_to_save.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 CSV herunterladen",
                data=csv_bytes,
                file_name="Winterplan_2026_autopopulated.csv",
                mime="text/csv",
                use_container_width=True
            )

        with col_discard:
            if st.button("🗑️ Vorschau verwerfen", use_container_width=True):
                st.session_state.pop("df_result", None)
                st.session_state.pop("filled_slots", None)
                st.session_state.pop("skipped_slots", None)
                st.rerun()

else:
    st.success("🎉 Keine leeren Slots für 2026 gefunden! Der Plan ist vollständig.")

# Documentation
st.markdown("---")
with st.expander("ℹ️ Saison-Informationen 2026"):
    st.markdown(f"""
    ### Winter-Saison 2026

    **Zeitraum:** {SEASON_START.strftime('%d.%m.%Y')} - {SEASON_END.strftime('%d.%m.%Y')}

    **Trainingsdateien:**
    - Plan: `{PLAN_FILE}`
    - Präferenzen: `{PREFS_FILE}`
    - Rankings: `{RANK_FILE}` (1=stärkster, 6=schwächster)

    **Trainingstage:**
    - **Montag:** 2x Doppel (20:00-22:00)
    - **Mittwoch:** 3x Einzel + 2x Doppel (18:00-21:30)
    - **Donnerstag:** 2x Einzel (20:00-21:30)

    **Gesamt pro Woche:** 7 Slots = 14 Einzel-Plätze + 12 Doppel-Plätze = 26 Spieler-Plätze/Woche

    **Saison-Statistik:**
    - Wochen: ca. 17 Wochen (Januar-April)
    - Theoretisch möglich: ~119 Slots
    - Spieler-Plätze gesamt: ~442

    **Berücksichtigt:**
    - Urlaube aus CSV (2026-01-01 bis 2026-04-26)
    - Spielerpräferenzen (nur Einzel/nur Doppel)
    - Verfügbarkeit nach Wochentagen
    - Spieler-Rankings (Einzel: Rang-Differenz ≤ 2)
    - Load Balancing für faire Verteilung
    """)

with st.expander("🏆 Spieler-Rankings"):
    st.markdown("""
    **Ranking-System:** 1 (stärkster) bis 6 (schwächster)

    **Regel für Einzel:** Rang-Differenz zwischen Spielern ≤ 2

    **Quelle:** `Player_Ranks_2026.csv` (aus audit prompt.txt)
    """)

    # Show rank distribution
    rank_counts = {}
    for player, rank in RANK.items():
        rank_counts[rank] = rank_counts.get(rank, 0) + 1

    rank_df = pd.DataFrame([
        {"Rang": 1, "Beschreibung": "Stärkster", "Anzahl Spieler": rank_counts.get(1, 0)},
        {"Rang": 2, "Beschreibung": "Sehr Stark", "Anzahl Spieler": rank_counts.get(2, 0)},
        {"Rang": 3, "Beschreibung": "Stark", "Anzahl Spieler": rank_counts.get(3, 0)},
        {"Rang": 4, "Beschreibung": "Überdurchschnittlich", "Anzahl Spieler": rank_counts.get(4, 0)},
        {"Rang": 5, "Beschreibung": "Durchschnittlich", "Anzahl Spieler": rank_counts.get(5, 0)},
        {"Rang": 6, "Beschreibung": "Schwächster", "Anzahl Spieler": rank_counts.get(6, 0)},
    ])
    st.dataframe(rank_df, use_container_width=True, hide_index=True)
