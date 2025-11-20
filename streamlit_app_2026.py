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

            # Add rank info for singles
            if r['Typ'] == "Einzel" and len(players) == 2:
                rank1 = ranks.get(players[0], "?")
                rank2 = ranks.get(players[1], "?")

                # Calculate rank difference
                if isinstance(rank1, (int, float)) and isinstance(rank2, (int, float)):
                    diff = abs(rank1 - rank2)
                    rank_info = f"  📊 Ranks: {players[0]} ({rank1}) vs {players[1]} ({rank2}) — Diff: {diff}"
                else:
                    rank_info = f"  📊 Ranks: {players[0]} ({rank1}) vs {players[1]} ({rank2})"

                st.markdown(f"{court_emoji} {type_emoji} **{r['Slot']}** — *{r['Typ']}*  \n  {r['Spieler']}\n{rank_info}")
            else:
                # For doubles, show ranks but no difference
                player_ranks = []
                for p in players:
                    rank = ranks.get(p, "?")
                    player_ranks.append(f"{p} ({rank})")

                if len(player_ranks) > 0:
                    rank_info = f"  📊 {', '.join(player_ranks)}"
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
tab1, tab2, tab3, tab4 = st.tabs(["📅 Wochenplan", "👤 Spieler-Matches", "🏆 Rankings", "📊 Statistiken"])

# ==================== TAB 1: WOCHENPLAN ====================
with tab1:
    st.header("Wochenansicht")

    # Get available weeks
    weeks = df_plan[["Jahr", "Woche"]].drop_duplicates().sort_values(["Jahr", "Woche"])
    if weeks.empty:
        st.warning("Keine Wochen gefunden")
        st.stop()

    week_options = [f"{int(row['Jahr'])}-W{int(row['Woche']):02d}" for _, row in weeks.iterrows()]

    # Week selector
    selected_week = st.selectbox(
        "Woche auswählen:",
        options=week_options,
        index=0
    )

    # Parse selected week
    match = re.match(r"(\d{4})-W(\d{2})", selected_week)
    if match:
        year = int(match.group(1))
        week = int(match.group(2))
        render_week(df_plan, year, week, player_ranks)

    # Navigation buttons
    col1, col2, col3 = st.columns([1, 2, 1])
    current_idx = week_options.index(selected_week) if selected_week in week_options else 0

    with col1:
        if current_idx > 0 and st.button("⬅️ Vorherige Woche"):
            st.session_state.week_selection = week_options[current_idx - 1]
            st.rerun()

    with col3:
        if current_idx < len(week_options) - 1 and st.button("➡️ Nächste Woche"):
            st.session_state.week_selection = week_options[current_idx + 1]
            st.rerun()

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
                    use_container_width=True,
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

# ==================== TAB 3: RANKINGS ====================
with tab3:
    st.header("🏆 Spieler Rankings")

    if player_ranks:
        # Create DataFrame from ranks
        ranks_df = pd.DataFrame([
            {"Spieler": player, "Rank": rank}
            for player, rank in sorted(player_ranks.items(), key=lambda x: (x[1], x[0]))
        ])

        # Add rank labels
        rank_labels = {
            1: "🥇 Sehr stark",
            2: "🥈 Stark",
            3: "🥉 Gut",
            4: "⭐ Mittel",
            5: "⚡ Entwicklung",
            6: "🌱 Einsteiger"
        }

        ranks_df["Level"] = ranks_df["Rank"].map(rank_labels)

        # Summary stats
        st.subheader("📊 Ranking Übersicht")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Gesamt Spieler", len(ranks_df))
        with col2:
            st.metric("Durchschnitt Rank", f"{ranks_df['Rank'].mean():.1f}")
        with col3:
            rank1_count = (ranks_df["Rank"] == 1).sum()
            st.metric("Rank 1 (Stärkste)", rank1_count)
        with col4:
            rank6_count = (ranks_df["Rank"] == 6).sum()
            st.metric("Rank 6 (Einsteiger)", rank6_count)

        # Distribution chart
        st.subheader("📈 Rank Verteilung")
        rank_distribution = ranks_df["Rank"].value_counts().sort_index()
        chart_df = pd.DataFrame({
            "Rank": [f"Rank {r}" for r in rank_distribution.index],
            "Anzahl": rank_distribution.values
        })
        st.bar_chart(chart_df.set_index("Rank"))

        # Full ranking list
        st.subheader("📋 Komplette Rangliste")

        # Group by rank
        for rank in sorted(ranks_df["Rank"].unique()):
            rank_players = ranks_df[ranks_df["Rank"] == rank]
            with st.expander(f"{rank_labels.get(rank, f'Rank {rank}')} — {len(rank_players)} Spieler", expanded=(rank <= 2)):
                players_list = sorted(rank_players["Spieler"].tolist())
                st.write(", ".join(players_list))

        # Searchable table
        st.subheader("🔍 Spieler suchen")
        search = st.text_input("Spielername eingeben:", "")

        if search:
            filtered = ranks_df[ranks_df["Spieler"].str.contains(search, case=False, na=False)]
            if not filtered.empty:
                st.dataframe(
                    filtered[["Spieler", "Rank", "Level"]],
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info(f"Kein Spieler gefunden mit '{search}'")
        else:
            st.dataframe(
                ranks_df[["Spieler", "Rank", "Level"]],
                use_container_width=True,
                hide_index=True,
                height=400
            )

        # Download option
        csv_bytes = ranks_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 Rankings als CSV herunterladen",
            data=csv_bytes,
            file_name="Player_Rankings_2026.csv",
            mime="text/csv"
        )
    else:
        st.warning("⚠️ Keine Ranking-Daten verfügbar.")

    # Ranking explanation
    with st.expander("ℹ️ Ranking System Erklärung"):
        st.markdown("""
        ### Wie funktioniert das Ranking?

        **Rank 1** 🥇 - Sehr starke Spieler (stärkste Spieler)
        **Rank 2** 🥈 - Starke Spieler
        **Rank 3** 🥉 - Gute Spieler
        **Rank 4** ⭐ - Mittleres Niveau
        **Rank 5** ⚡ - Entwicklungsspieler
        **Rank 6** 🌱 - Einsteiger

        **Einzel:** Rank-Differenz zwischen 2 Spielern ≤ 2
        **Doppel:** Rank-Differenz zwischen stärkstem und schwächstem Spieler ≤ 3

        Dies sorgt für ausgeglichene und faire Matches!
        """)

    # Scheduling rules
    with st.expander("⚙️ Automatische Planungs-Regeln (aus autopopulate_2026_app.py)"):
        st.markdown("""
        ### 📋 Scheduling Constraints & Rules

        Der Trainingsplan wird automatisch mit folgenden Regeln erstellt:

        #### 🎯 Grundlegende Constraints
        - **Max 1 Match pro Tag** - Spieler können nicht mehrmals am gleichen Tag spielen
        - **Max 1 Match pro Woche** - Spieler spielen maximal einmal pro Woche
        - **Kein Zeitkonflikt** - Spieler können nicht gleichzeitig auf verschiedenen Plätzen sein

        #### 🏆 Ranking-basierte Kompatibilität
        - **Einzel:** Rank-Differenz ≤ 2 (z.B. Rank 1 kann mit Rank 1, 2, 3 spielen)
        - **Doppel:** Rank-Differenz zwischen stärkstem und schwächstem ≤ 3
        - **Singles Variety:** Gleiche 2 Spieler maximal 3x im Einzel gegeneinander (MAX_SINGLES_REPEATS = 3)

        #### 👥 Spieler-spezifische Regeln
        **Paired Players (müssen zur gleichen Zeit spielen):**
        - Lena Meiss & Kerstin Baarck (wohnen zusammen, fahren gemeinsam)

        **Partner Präferenzen (Doppel):**
        - Bjoern Junker + Martin Lange (Fahrgemeinschaft aus Schönkirchen)

        **Frauen Einzel-Verbot:**
        - Anke Ihde, Lena Meiss, Martina Schmidt, Kerstin Baarck

        **Zeit-geschützte Spieler:**
        - Patrick Buehrsch: nur 18:00
        - Frank Petermann: nur 19:00 oder 20:00
        - Matthias Duddek: nur 18:00 oder 19:00
        - Dirk Kistner: nur Mo/Mi/Do; Mittwoch nur 19:00
        - Arndt Stueber: nur Mittwoch 19:00
        - Jens Hafner: nur Mittwoch 19:00
        - Thomas Grueneberg: max 30% Mittwoch 20:00, min 70% um 18/19 Uhr

        #### 📊 Match-Limits
        **Monatliche Limits:**
        - Peter Plaehn: max 3 Matches/Monat

        **Saison-Limits:**
        - Torsten Bartel: max 3 Matches/Saison

        **Saison-Targets (Prioritäts-Boost):**
        - Thomas Grueneberg: Ziel 11 Matches ("Würde gerne einmal pro Woche spielen!")

        #### 📅 Weitere Constraints
        - **Urlaubs-/Blackout-Perioden** aus CSV (Spieler_Preferences_2026.csv)
        - **Verfügbare Wochentage** pro Spieler (AvailableDays in Preferences)
        - **Spielart-Präferenzen** (nur Einzel / nur Doppel / keine Präferenz)

        #### ⚡ Priorisierungs-System
        Der Algorithmus verwendet Priority Boosting:
        - **Target Boost:** -100 × (Ziel - aktuelle Matches) für Spieler unter ihrem Ziel
        - **Paired Boost:** -50 wenn Partner verfügbar ist
        - **Ratio Balancing:** Spieler mit weniger Matches bekommen höhere Priorität
        - **Niedrigere Werte = höhere Priorität** (mehr wahrscheinlich ausgewählt zu werden)

        ---

        **Datei:** `autopopulate_2026_app.py` (Zeilen 60-92, 331-438)
        **Quelle:** Player_Ranks_2026.csv, Spieler_Preferences_2026.csv
        """)


# ==================== TAB 4: STATISTIKEN ====================
with tab4:
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
        st.dataframe(top_10, use_container_width=True)

        # Players with fewest matches
        st.subheader("Spieler mit wenigsten Matches")
        bottom_10 = player_counts.tail(10).sort_values().reset_index()
        bottom_10.columns = ["Spieler", "Matches"]
        st.dataframe(bottom_10, use_container_width=True, hide_index=True)
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
