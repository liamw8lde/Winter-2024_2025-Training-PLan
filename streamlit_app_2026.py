import streamlit as st
import pandas as pd
import re
import base64, json, requests, io
from datetime import date, datetime, timedelta

# ==================== CONFIGURATION ====================
st.set_page_config(page_title="Winterplan 2026", layout="wide", initial_sidebar_state="collapsed")

EDIT_PASSWORD = "tennis"  # protects editing features
PLAN_FILE = "Winterplan_2026.csv"
PREFS_FILE = "Spieler_Preferences_2026.csv"
RANK_FILE = "Player_Ranks_2026.csv"

# ==================== DATA HELPERS ====================
def postprocess_plan(df: pd.DataFrame):
    """Process plan DataFrame and add computed columns"""
    required = ["Datum", "Tag", "Slot", "Typ", "Spieler"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}. Expected: {required}")

    df = df.copy()
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
    df["S_Art"]   = t[0].fillna("")      # E/D (Einzel/Doppel)
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
        return pd.read_csv(file_path)
    except Exception as e:
        st.error(f"Error loading preferences from {file_path}: {e}")
        return None

@st.cache_data(show_spinner=False)
def load_ranks_csv(file_path):
    """Load player ranks CSV and return as dict"""
    try:
        df = pd.read_csv(file_path)
        return dict(zip(df["Spieler"], df["Rank"]))
    except Exception as e:
        st.error(f"Error loading ranks from {file_path}: {e}")
        return {}

# ==================== COSTS: court rates + allowed weekly slots ====================
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

# Global blackouts (any year)
BLACKOUT_MMDD = {(12, 24), (12, 25), (12, 31)}

def _minutes_from_slot(slot: str) -> int:
    """Extract minutes from slot code e.g. 'D20:00-120 PLA' -> 120"""
    m = re.search(r"-([0-9]+)\s+PL[AB]$", str(slot))
    return int(m.group(1)) if m else 0

def _players_per_slot(s_art: str, fallback_players_count: int | None = None, slot_typ_text: str = "") -> int:
    """Return number of players for a slot type"""
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
    """Get min and max dates from the plan DataFrame"""
    dmin = pd.to_datetime(df["Datum_dt"]).dropna().min()
    dmax = pd.to_datetime(df["Datum_dt"]).dropna().max()
    if pd.isna(dmin) or pd.isna(dmax):
        return None, None
    return dmin.date(), dmax.date()

def _dates_for_iso_week(iso_year: int, iso_week: int, iso_weekday: int):
    """Returns date for given ISO (year, week, weekday 1..7)"""
    return pd.Timestamp.fromisocalendar(iso_year, iso_week, iso_weekday).date()

def _generate_allowed_slots_calendar(df: pd.DataFrame):
    """Return list of dicts with Date, Tag, Slot, Typ, Minutes for every allowed weekly slot within season bounds."""
    start_date, end_date = _season_bounds_from_df(df)
    if not start_date or not end_date:
        return []

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
            maxw = date(y, 12, 28).isocalendar().week
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
    """Check if date is a blackout date"""
    return (d.month, d.day) in BLACKOUT_MMDD

def compute_player_costs(df: pd.DataFrame, df_exp: pd.DataFrame):
    """
    Compute player costs for the season.

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

# ==================== GITHUB FUNCTIONS ====================
def github_headers():
    token = st.secrets.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GitHub token missing")
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}

def github_get_file(file_path):
    """Get file content from GitHub"""
    repo = st.secrets.get("GITHUB_REPO")
    branch = st.secrets.get("GITHUB_BRANCH", "main")
    if not repo:
        raise RuntimeError("GITHUB_REPO not set in secrets")

    url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
    r = requests.get(url, headers=github_headers(), params={"ref": branch}, timeout=20)
    if r.status_code == 200:
        content_b64 = r.json().get("content", "")
        return base64.b64decode(content_b64)
    elif r.status_code == 404:
        return None
    else:
        raise RuntimeError(f"GitHub GET failed {r.status_code}: {r.text}")

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

# ==================== RENDERING FUNCTIONS ====================
def render_week(df: pd.DataFrame, year: int, week: int, ranks: dict):
    """Render a specific week's schedule with ranks"""
    wk = df[(df["Jahr"] == year) & (df["Woche"] == week)].copy()
    if wk.empty:
        st.info("📭 Keine Einträge in dieser Woche.")
        return

    wk = wk.sort_values(["Datum_dt", "Startzeit_sort", "Slot"])
    st.header(f"📅 Kalenderwoche {week}, {year}")

    for dt, day_df in wk.groupby("Datum_dt"):
        st.subheader(dt.strftime("%A, %d.%m.%Y"))
        for _, r in day_df.iterrows():
            court_emoji = "🎾" if r["S_Court"] == "A" else "🏐"
            type_emoji = "👤" if r["Typ"] == "Einzel" else "👥"

            # Parse players
            players = [p.strip() for p in str(r['Spieler']).split(",")]

            # Add rank difference info
            if r['Typ'] == "Einzel" and len(players) == 2:
                rank1 = ranks.get(players[0], "?")
                rank2 = ranks.get(players[1], "?")

                # Calculate rank difference
                if isinstance(rank1, (int, float)) and isinstance(rank2, (int, float)):
                    diff = abs(rank1 - rank2)
                    rank_info = f"  📊 {players[0]} vs {players[1]} — Rank diff: {diff}"
                else:
                    rank_info = f"  📊 {players[0]} vs {players[1]} — Rank diff: ?"

                st.markdown(f"{court_emoji} {type_emoji} **{r['Slot']}** — *{r['Typ']}*\n{rank_info}")
            else:
                # For doubles, show players and rank difference between strongest and weakest
                player_rank_values = []
                for p in players:
                    rank = ranks.get(p, None)
                    if isinstance(rank, (int, float)):
                        player_rank_values.append(rank)

                players_str = ", ".join(players)
                if len(player_rank_values) >= 2:
                    diff = max(player_rank_values) - min(player_rank_values)
                    rank_info = f"  📊 {players_str} — Rank diff: {diff}"
                    st.markdown(f"{court_emoji} {type_emoji} **{r['Slot']}** — *{r['Typ']}*\n{rank_info}")
                else:
                    st.markdown(f"{court_emoji} {type_emoji} **{r['Slot']}** — *{r['Typ']}*  \n  {r['Spieler']}")

# ==================== PASSWORD PROTECTION ====================
def check_password():
    if st.session_state.get("authenticated", False):
        return True

    with st.form("login_form"):
        st.write("🔒 Diese Funktion ist passwortgeschützt")
        password = st.text_input("Passwort", type="password")
        submitted = st.form_submit_button("Einloggen")

        if submitted:
            if password == EDIT_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ Falsches Passwort")
    return False

# ==================== MAIN APP ====================
st.title("🎾 Winterplan 2026")
st.markdown("**Trainingstermine Januar - April 2026**")

# Load data
with st.spinner("Lade 2026 Daten..."):
    df_plan, df_exp = load_plan_csv(PLAN_FILE)
    df_prefs = load_preferences_csv(PREFS_FILE)
    player_ranks = load_ranks_csv(RANK_FILE)

if df_plan is None:
    st.error(f"❌ Konnte {PLAN_FILE} nicht laden!")
    st.info(f"Bitte stelle sicher, dass {PLAN_FILE} im gleichen Ordner ist.")
    st.stop()

# Tabs
tab1, tab2, tab3, tab4 = st.tabs(["📅 Wochenplan", "👤 Spieler-Matches", "📊 Statistiken", "💰 Spieler-Kosten"])

# ==================== TAB 1: WOCHENPLAN ====================
with tab1:
    st.header("Wochenansicht")

    # Get available weeks
    weeks = df_plan[["Jahr", "Woche"]].drop_duplicates().sort_values(["Jahr", "Woche"])
    if weeks.empty:
        st.warning("Keine Wochen gefunden")
        st.stop()

    week_options = [f"{int(row['Jahr'])}-W{int(row['Woche']):02d}" for _, row in weeks.iterrows()]

    # Initialize with current week on first load
    if "week_selection" not in st.session_state:
        # Get current week
        today = datetime.now()
        current_iso = today.isocalendar()
        current_week_str = f"{current_iso.year}-W{current_iso.week:02d}"

        # Use current week if it exists in data, otherwise use first week
        if current_week_str in week_options:
            st.session_state.week_selection = current_week_str
        else:
            st.session_state.week_selection = week_options[0]

    # Week selector - use session state
    current_idx = week_options.index(st.session_state.week_selection) if st.session_state.week_selection in week_options else 0

    selected_week = st.selectbox(
        "Woche auswählen:",
        options=week_options,
        index=current_idx
    )

    # Update session state when selectbox changes
    if selected_week != st.session_state.week_selection:
        st.session_state.week_selection = selected_week

    # Navigation buttons - directly under dropdown
    # Recalculate index based on currently selected week
    selected_idx = week_options.index(selected_week) if selected_week in week_options else 0

    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if selected_idx > 0 and st.button("⬅️ Vorherige Woche"):
            st.session_state.week_selection = week_options[selected_idx - 1]
            st.rerun()

    with col3:
        if selected_idx < len(week_options) - 1 and st.button("➡️ Nächste Woche"):
            st.session_state.week_selection = week_options[selected_idx + 1]
            st.rerun()

    # Parse selected week
    match = re.match(r"(\d{4})-W(\d{2})", selected_week)
    if match:
        year = int(match.group(1))
        week = int(match.group(2))
        render_week(df_plan, year, week, player_ranks)

# ==================== TAB 2: SPIELER-MATCHES ====================
with tab2:
    st.header("Spieler-Übersicht")

    if df_exp is not None and not df_exp.empty and df_prefs is not None:
        all_players = sorted(df_exp["Spieler_Name"].dropna().unique().tolist())

        selected_player = st.selectbox("Spieler auswählen:", options=all_players)

        if selected_player:
            # Get player matches
            player_matches = df_exp[df_exp["Spieler_Name"] == selected_player].copy()

            if not player_matches.empty:
                player_matches = player_matches.sort_values("Datum_dt")

                # Summary
                total_matches = len(player_matches)
                singles = (player_matches["Typ"] == "Einzel").sum()
                doubles = (player_matches["Typ"] == "Doppel").sum()

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Gesamt", total_matches)
                with col2:
                    st.metric("Einzel", singles)
                with col3:
                    st.metric("Doppel", doubles)

                # Display matches
                st.subheader(f"Alle Matches für {selected_player}")
                display_matches = player_matches[[
                    "Datum", "Tag", "Slot", "Typ", "Spieler"
                ]].copy()

                st.dataframe(
                    display_matches,
                    width='stretch',
                    height=400,
                    hide_index=True
                )

                # Download option
                csv_bytes = display_matches.to_csv(index=False).encode("utf-8")
                st.download_button(
                    f"📥 {selected_player}'s Matches als CSV",
                    data=csv_bytes,
                    file_name=f"{selected_player.replace(' ', '_')}_Matches_2026.csv",
                    mime="text/csv"
                )
            else:
                st.info(f"🔍 Keine Matches für {selected_player} gefunden.")
    else:
        st.warning("⚠️ Keine Spieler gefunden.")

# ==================== TAB 3: STATISTIKEN ====================
with tab3:
    st.header("Saison-Statistiken")

    if df_exp is not None and not df_exp.empty:
        # Player match counts
        player_counts = df_exp.groupby("Spieler_Name").size().sort_values(ascending=False)

        st.subheader("Matches pro Spieler")

        # Create a bar chart
        chart_data = pd.DataFrame({
            "Spieler": player_counts.index,
            "Matches": player_counts.values
        })

        st.bar_chart(chart_data.set_index("Spieler"))

        # Summary stats
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Gesamt Matches", len(df_plan))
        with col2:
            st.metric("Spieler", len(player_counts))
        with col3:
            st.metric("Durchschnitt/Spieler", f"{player_counts.mean():.1f}")
        with col4:
            min_matches = player_counts.min()
            max_matches = player_counts.max()
            st.metric("Min/Max", f"{min_matches}/{max_matches}")

        # Top 10 players
        st.subheader("Top 10 Aktivste Spieler")
        top_10 = player_counts.head(10).reset_index()
        top_10.columns = ["Spieler", "Matches"]
        top_10.index = range(1, 11)
        st.dataframe(top_10, width='stretch')

        # Players with fewest matches
        st.subheader("Spieler mit wenigsten Matches")
        bottom_10 = player_counts.tail(10).sort_values().reset_index()
        bottom_10.columns = ["Spieler", "Matches"]
        st.dataframe(bottom_10, width='stretch', hide_index=True)
    else:
        st.warning("⚠️ Keine Daten verfügbar für Statistiken.")

# ==================== TAB 4: SPIELER-KOSTEN ====================
with tab4:
    st.header("💰 Spieler-Kosten (Saison)")

    if not check_password():
        st.stop()

    st.caption("Gerichtsgebühr: **17,50 €/h**. Einzel = 2 Spieler, Doppel = 4 Spieler. "
               "Ungenutzte Slots (auch an 24.12/25.12/31.12) werden proportional zu den **gespielten Minuten** verteilt.")

    if df_plan is not None and df_exp is not None:
        per_player_df, totals, allowed_calendar = compute_player_costs(df_plan, df_exp)

        c1, c2, c3 = st.columns(3)
        c1.metric("Summe direkte Kosten", f"{totals['direct_cost_total']:.2f} €")
        c2.metric("Summe ungenutzte Plätze", f"{totals['unused_cost_total']:.2f} €")
        c3.metric("Gesamt verrechnet", f"{totals['charged_total']:.2f} €")

        st.subheader("Kosten pro Spieler (Saison)")
        st.dataframe(per_player_df, width="stretch", hide_index=True)

        # Downloads
        st.download_button(
            "📥 CSV herunterladen (Spieler-Kosten)",
            data=per_player_df.to_csv(index=False).encode("utf-8"),
            file_name="spieler_kosten_2026.csv",
            mime="text/csv"
        )

        # WhatsApp copy section
        st.markdown("---")
        st.subheader("📱 WhatsApp Text (zum Kopieren)")

        # Build WhatsApp-friendly text
        whatsapp_lines = ["🎾 *Wintertraining 2026 - Kostenabrechnung*", ""]
        whatsapp_lines.append(f"📊 *Zusammenfassung:*")
        whatsapp_lines.append(f"• Direkte Kosten: {totals['direct_cost_total']:.2f} €")
        whatsapp_lines.append(f"• Ungenutzte Plätze: {totals['unused_cost_total']:.2f} €")
        whatsapp_lines.append(f"• Gesamt: {totals['charged_total']:.2f} €")
        whatsapp_lines.append("")
        whatsapp_lines.append("💰 *Kosten pro Spieler:*")

        # Sort by name for WhatsApp message
        sorted_players = per_player_df.sort_values("Spieler")
        for _, row in sorted_players.iterrows():
            whatsapp_lines.append(f"• {row['Spieler']}: {row['Gesamt (€)']:.2f} €")

        whatsapp_lines.append("")
        whatsapp_lines.append("_Bitte überweisen auf das Vereinskonto._")

        whatsapp_text = "\n".join(whatsapp_lines)

        st.text_area(
            "Text kopieren und in WhatsApp einfügen:",
            value=whatsapp_text,
            height=400,
            help="Markiere den gesamten Text und kopiere ihn (Strg+A, Strg+C)"
        )

        with st.expander("📋 Details: Kalender der erlaubten Slots (genutzt/ungenutzt)"):
            if isinstance(allowed_calendar, pd.DataFrame) and not allowed_calendar.empty:
                show_df = allowed_calendar.copy()
                show_df["Datum"] = pd.to_datetime(show_df["Datum"]).dt.strftime("%Y-%m-%d")
                show_df["court_cost"] = show_df["court_cost"].round(2)
                st.dataframe(show_df.sort_values(["Datum", "Tag", "Slot"]), width="stretch", hide_index=True)
            else:
                st.info("Kein Slot-Kalender generiert (fehlende Saisondaten).")
    else:
        st.warning("⚠️ Keine Daten verfügbar für Kostenberechnung.")

# ==================== SIDEBAR INFO ====================
with st.sidebar:
    st.header("ℹ️ Saison-Info")
    st.markdown("""
    ### Winter-Saison 2026
    **Zeitraum:** Januar - April 2026

    **Trainingsdateien:**
    - Plan: `Winterplan_2026.csv`
    - Präferenzen: `Spieler_Preferences_2026.csv`

    **Trainingstage:**
    - **Montag:** 2x Doppel (20:00)
    - **Mittwoch:** 3x Einzel + 2x Doppel
    - **Donnerstag:** 2x Einzel (20:00)
    """)

    if df_plan is not None and not df_plan.empty:
        st.divider()
        st.metric("Matches geplant", len(df_plan))
        if df_exp is not None:
            st.metric("Aktive Spieler", df_exp["Spieler_Name"].nunique())
