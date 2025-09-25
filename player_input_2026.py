import streamlit as st
import pandas as pd
import base64, json, requests, io
from datetime import date, datetime, timedelta

# =========================
# App config
# =========================
st.set_page_config(
    page_title="Spieler-Eingabe 2026",
    layout="wide",
    initial_sidebar_state="collapsed"
)

WINDOW_START = date(2026, 1, 1)
WINDOW_END   = date(2026, 4, 26)
PREFS_PATH   = st.secrets.get("GITHUB_PREFS_PATH", "Spieler_Preferences_2026.csv")

# =========================
# GitHub helpers
# =========================
def _github_headers():
    token = st.secrets.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GitHub token missing in st.secrets['GITHUB_TOKEN'].")
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

def _gh_repo_info():
    repo   = st.secrets.get("GITHUB_REPO")            # e.g. "owner/repo"
    branch = st.secrets.get("GITHUB_BRANCH", "main")  # e.g. "main"
    path   = st.secrets.get("GITHUB_PATH", "Winterplan.csv")  # plan csv (for names list)
    if not repo:
        raise RuntimeError("st.secrets['GITHUB_REPO'] must be set, e.g. 'owner/repo'.")
    return repo, branch, path

@st.cache_data(show_spinner=False)
def github_get_contents(path: str, ref: str | None = None):
    """Return (bytes, sha) for a repo file, or (None, None) if 404."""
    repo, branch, _ = _gh_repo_info()
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    params = {"ref": ref or branch}
    r = requests.get(url, headers=_github_headers(), params=params, timeout=20)
    if r.status_code == 200:
        data = r.json()
        content_b64 = data.get("content", "")
        csv_bytes = base64.b64decode(content_b64) if content_b64 else b""
        sha = data.get("sha", "")
        return csv_bytes, sha
    elif r.status_code == 404:
        return None, None
    raise RuntimeError(f"GET {path} failed {r.status_code}: {r.text}")

def github_put_contents(path: str, csv_bytes: bytes, message: str, branch_override: str | None = None):
    repo, branch, _ = _gh_repo_info()
    if branch_override:
        branch = branch_override
    # get SHA if exists
    try:
        _, sha = github_get_contents(path, ref=branch)
    except Exception:
        sha = None
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
    raise RuntimeError(f"PUT {path} failed {r.status_code}: {r.text}")

# =========================
# Load existing player names from plan CSV
# =========================
@st.cache_data(show_spinner=False)
def load_names_from_plan():
    _, _, plan_path = _gh_repo_info()
    csv_bytes, _ = github_get_contents(plan_path)
    if not csv_bytes:
        return []
    df_raw = pd.read_csv(io.BytesIO(csv_bytes), dtype=str)
    for c in ["Datum","Tag","Slot","Typ","Spieler"]:
        if c in df_raw.columns:
            df_raw[c] = df_raw[c].astype(str)
    df_raw["Spieler_list"] = df_raw["Spieler"].str.split(",").apply(
        lambda xs: [x.strip() for x in xs if str(x).strip()]
    )
    df_exp = df_raw.explode("Spieler_list").rename(columns={"Spieler_list":"Spieler_Name"})
    names = sorted(set([n for n in df_exp["Spieler_Name"].dropna().tolist() if str(n).strip()]))
    return names

# =========================
# Helpers for parsing/formatting stored values
# =========================
def parse_available_days(s: str) -> set:
    if not s or not isinstance(s, str):
        return set()
    return set([p.strip() for p in s.split(",") if p.strip()])

def parse_blocked_ranges(s: str):
    """Return list[(date_from, date_to)] from 'YYYY-MM-DD→YYYY-MM-DD;...'"""
    out = []
    if not s or not isinstance(s, str):
        return out
    for token in s.split(";"):
        token = token.strip()
        if not token or "→" not in token:
            continue
        a, b = [x.strip() for x in token.split("→", 1)]
        try:
            da = pd.to_datetime(a).date()
            db = pd.to_datetime(b).date()
            out.append((da, db))
        except Exception:
            pass
    return out

def parse_blocked_singles(s: str):
    """Return list[date] from 'YYYY-MM-DD;YYYY-MM-DD;...'"""
    out = []
    if not s or not isinstance(s, str):
        return out
    for token in s.split(";"):
        token = token.strip()
        if not token:
            continue
        try:
            out.append(pd.to_datetime(token).date())
        except Exception:
            pass
    return out

def merge_ranges(rows):
    """Merge overlapping/adjacent ranges; rows is list[(start, end)]."""
    rows = [(max(a, WINDOW_START), min(b, WINDOW_END)) for (a, b) in rows if a <= b]
    rows.sort()
    merged = []
    for a, b in rows:
        if not merged or a > merged[-1][1] + timedelta(days=1):
            merged.append((a, b))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
    return merged

# =========================
# Load existing prefs (for prefilling & download)
# =========================
@st.cache_data(show_spinner=False)
def load_prefs_df():
    try:
        csv_bytes, _ = github_get_contents(PREFS_PATH)
        if not csv_bytes:
            return pd.DataFrame(columns=[
                "Spieler","ValidFrom","ValidTo","AvailableDays",
                "Preference","BlockedRanges","BlockedSingles","Notes","Timestamp"
            ])
        df = pd.read_csv(io.BytesIO(csv_bytes), dtype=str)
        # ensure all columns exist
        for c in ["Spieler","ValidFrom","ValidTo","AvailableDays","Preference",
                  "BlockedRanges","BlockedSingles","Notes","Timestamp"]:
            if c not in df.columns:
                df[c] = ""
        return df
    except Exception:
        return pd.DataFrame(columns=[
            "Spieler","ValidFrom","ValidTo","AvailableDays",
            "Preference","BlockedRanges","BlockedSingles","Notes","Timestamp"
        ])

# =========================
# UI – Form with prefill, edit, confirm, save
# =========================
st.title("Spieler-Eingabe (01.01.2026 – 26.04.2026)")
st.caption("Bitte gib deine Verfügbarkeit, Urlaubszeiträume/Einzeltage, Präferenz und Notizen an. "
           "Wenn du einen bestehenden Spieler wählst, werden seine gespeicherten Daten geladen und können bearbeitet werden.")

existing_players = load_names_from_plan()
prefs_df = load_prefs_df()
player_options = existing_players + ["Neuer Spieler …"]

# ----- selection -----
col_sel, col_dl = st.columns([2,1])
with col_sel:
    player_choice = st.selectbox(
        "Spieler", options=player_options, index=None, placeholder="— bitte wählen —"
    )

# ----- prefill if exists -----
prefill = {
    "player_name": "",
    "preference": "Keine Präferenz",
    "avail_days": set(),
    "ranges": [],          # list[(start, end)]
    "blocked_singles": [], # list[date]
    "notes": "",
}
if player_choice and player_choice != "Neuer Spieler …":
    prefill["player_name"] = str(player_choice)
    row_exist = prefs_df[prefs_df["Spieler"] == prefill["player_name"]]
    if not row_exist.empty:
        r = row_exist.iloc[0].fillna("")
        prefill["preference"] = (r.get("Preference") or "Keine Präferenz").strip() or "Keine Präferenz"
        prefill["avail_days"] = parse_available_days(r.get("AvailableDays", ""))
        prefill["ranges"] = parse_blocked_ranges(r.get("BlockedRanges", ""))
        prefill["blocked_singles"] = parse_blocked_singles(r.get("BlockedSingles", ""))
        prefill["notes"] = (r.get("Notes") or "").strip()

        # ----- download link for this player's stored row -----
        with col_dl:
            single_row_csv = row_exist.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Gespeicherte Daten herunterladen",
                data=single_row_csv,
                file_name=f"{prefill['player_name'].replace(' ','_')}_Prefs_2026.csv",
                mime="text/csv",
                help="Lädt den aktuellen gespeicherten Datensatz dieses Spielers als CSV herunter."
            )

# Keep a separate editor state so switching players refreshes properly
if "ranges_df" not in st.session_state:
    st.session_state["ranges_df"] = pd.DataFrame(columns=["von","bis"])

# Replace editor dataframe with prefilled ranges (if any)
if prefill["ranges"]:
    st.session_state["ranges_df"] = pd.DataFrame(
        [{"von": a, "bis": b} for (a, b) in prefill["ranges"]]
    )
else:
    st.session_state["ranges_df"] = pd.DataFrame(columns=["von","bis"])

# ----- FORM -----
with st.form("player_input"):
    colA, colB = st.columns([2,2])

    with colA:
        player_name = ""
        if player_choice == "Neuer Spieler …":
            player_name = st.text_input("Neuer Spielername").strip()
        elif player_choice:
            st.text_input("Spieler (ausgewählt)", value=prefill["player_name"], disabled=True)
            player_name = prefill["player_name"]

    with colB:
        preference = st.selectbox(
            "Einzel/Doppel Präferenz",
            options=["Keine Präferenz", "Nur Einzel", "Nur Doppel"],
            index=["Keine Präferenz", "Nur Einzel", "Nur Doppel"].index(prefill["preference"])
            if prefill["preference"] in {"Keine Präferenz","Nur Einzel","Nur Doppel"} else 0
        )

    st.markdown("**Wochentags-Verfügbarkeit** (mehrere möglich)")
    c1, c2, c3 = st.columns(3)
    avail_days = set()
    if c1.checkbox("Montag", value=("Montag" in prefill["avail_days"])): avail_days.add("Montag")
    if c2.checkbox("Mittwoch", value=("Mittwoch" in prefill["avail_days"])): avail_days.add("Mittwoch")
    if c3.checkbox("Donnerstag", value=("Donnerstag" in prefill["avail_days"])): avail_days.add("Donnerstag")

    st.markdown("**Urlaub/Abwesenheit**")
    st.caption("• Datumsspannen als Tabelle  • Einzeltage als Mehrfachauswahl  • Alle Daten müssen zwischen 01.01.2026 und 26.04.2026 liegen.")

    ranges_df = st.data_editor(
        st.session_state["ranges_df"],
        num_rows="dynamic",
        column_config={
            "von": st.column_config.DateColumn("von", min_value=WINDOW_START, max_value=WINDOW_END),
            "bis": st.column_config.DateColumn("bis", min_value=WINDOW_START, max_value=WINDOW_END),
        },
        width="stretch",
        key="ranges_editor"
    )

    all_days = pd.date_range(WINDOW_START, WINDOW_END, freq="D").date.tolist()
    blocked_singles = st.multiselect(
        "Blockierte Einzeltage",
        options=all_days,
        default=prefill["blocked_singles"],
        format_func=lambda d: pd.to_datetime(d).strftime("%Y-%m-%d")
    )

    notes = st.text_area(
        "Notizen (z.B. 'nicht vor 19:00', 'Mittwoch 18:00 gesperrt')",
        value=prefill["notes"]
    )

    # Build draft + summary (validate after submit)
    def _clean_ranges(df_ranges: pd.DataFrame):
        rows = []
        for _, r in df_ranges.fillna("").iterrows():
            v, b = r.get("von"), r.get("bis")
            if not v or not b:
                continue
            v = pd.to_datetime(v).date()
            b = pd.to_datetime(b).date()
            if v > b:
                v, b = b, v
            v = max(v, WINDOW_START)
            b = min(b, WINDOW_END)
            if v <= b:
                rows.append((v, b))
        return merge_ranges(rows)

    ranges_clean = _clean_ranges(ranges_df)
    singles_clean = sorted(set([d for d in blocked_singles if WINDOW_START <= d <= WINDOW_END]))

    st.subheader("Zusammenfassung")
    day_str = ", ".join(sorted(avail_days)) if avail_days else "—"
    ranges_str = "; ".join([f"{v} → {b}" for (v, b) in ranges_clean]) if ranges_clean else "—"
    singles_str = "; ".join(pd.to_datetime(singles_clean).strftime("%Y-%m-%d").tolist()) if singles_clean else "—"
    st.markdown(
        f"**Spieler:** {player_name or '—'}\n\n"
        f"**Zeitraum:** {WINDOW_START} → {WINDOW_END}\n\n"
        f"**Verfügbar:** {day_str}\n\n"
        f"**Präferenz:** {preference}\n\n"
        f"**Blockierte Zeitspannen:** {ranges_str}\n\n"
        f"**Blockierte Einzeltage:** {singles_str}\n\n"
        f"**Notizen:** {notes.strip() or '—'}"
    )

    confirmed = st.form_submit_button("✅ Bestätigen & Speichern")

# Save on confirm
if confirmed:
    errors = []
    if not player_name:
        errors.append("Bitte Spieler auswählen oder neuen Namen eingeben.")
    if errors:
        for e in errors:
            st.error(e)
    else:
        now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        row = {
            "Spieler": player_name,
            "ValidFrom": WINDOW_START.strftime("%Y-%m-%d"),
            "ValidTo": WINDOW_END.strftime("%Y-%m-%d"),
            "AvailableDays": ",".join(sorted(avail_days)) if avail_days else "",
            "Preference": preference,
            "BlockedRanges": ";".join([f"{v.strftime('%Y-%m-%d')}→{b.strftime('%Y-%m-%d')}" for (v, b) in ranges_clean]),
            "BlockedSingles": ";".join([pd.to_datetime(d).strftime("%Y-%m-%d") for d in singles_clean]),
            "Notes": notes.strip(),
            "Timestamp": now_iso,
        }

        # Replace old row (if any), then append
        if not prefs_df.empty and "Spieler" in prefs_df.columns:
            prefs_df = prefs_df[prefs_df["Spieler"] != player_name]
        prefs_df = pd.concat([prefs_df, pd.DataFrame([row])], ignore_index=True)

        try:
            csv_bytes = prefs_df[list(row.keys())].to_csv(index=False).encode("utf-8")
            _ = github_put_contents(
                path=PREFS_PATH,
                csv_bytes=csv_bytes,
                message=f"Prefs 2026 update: {player_name}",
                branch_override=st.secrets.get("GITHUB_BRANCH", "main")
            )
            st.success("Einstellungen gespeichert ✅")
            st.subheader("Gespeicherte Einstellungen (Vorschau)")
            st.dataframe(prefs_df[prefs_df["Spieler"] == player_name], width="stretch")
        except Exception as e:
            st.error(f"Speichern fehlgeschlagen: {e}")

st.markdown("---")
st.caption("Hinweis: Diese App speichert nur deine Eingaben für 01.01.2026–26.04.2026. "
           "Sie ändert **nicht** automatisch den Winter-Trainingsplan.")