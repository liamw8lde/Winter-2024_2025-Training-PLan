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
tab1, tab2, tab3 = st.tabs(["📅 Wochenplan", "👤 Spieler-Matches", "📊 Statistiken"])

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
        index=current_idx,
        key="week_selector"
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
