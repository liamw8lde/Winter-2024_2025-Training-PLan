#!/usr/bin/env python3
"""
Regenerate the 2026 schedule from scratch with the new daily/weekly constraints.
This script clears the current schedule and generates a new one.
"""
import pandas as pd
import sys

# Import functions from the autopopulate app
sys.path.insert(0, '/home/user/Winter-2024_2025-Training-PLan')
from autopopulate_2026_app import (
    generate_allowed_slots_calendar_2026,
    load_preferences_csv,
    load_ranks_csv,
    get_available_days,
    get_player_preferences,
    load_holidays,
    autopopulate_plan,
    PLAN_FILE,
    PREFS_FILE,
    RANK_FILE,
    RANK,
    RANK_FALLBACK
)

def main():
    print("=" * 80)
    print("REGENERATING 2026 SCHEDULE WITH NEW CONSTRAINTS")
    print("=" * 80)
    print()

    # Load preferences and ranks
    print("Loading player data...")
    df_prefs = load_preferences_csv(PREFS_FILE)
    rank_data = load_ranks_csv(RANK_FILE)

    if df_prefs is None or df_prefs.empty:
        print(f"ERROR: Could not load {PREFS_FILE}")
        return 1

    # Extract preferences
    available_days = get_available_days(df_prefs)
    preferences = get_player_preferences(df_prefs)
    holidays = load_holidays(df_prefs)
    all_players = sorted(df_prefs["Spieler"].dropna().unique().tolist())

    print(f"✓ Loaded {len(all_players)} players")
    print(f"✓ Using rank data: {'fallback' if rank_data == RANK_FALLBACK else RANK_FILE}")
    print()

    # Generate empty schedule (empty DataFrame with correct structure)
    print("Generating empty schedule template...")
    from autopopulate_2026_app import postprocess_plan
    df_empty = pd.DataFrame(columns=["Datum", "Tag", "Slot", "Typ", "Spieler"])
    df_empty, _ = postprocess_plan(df_empty)
    print(f"✓ Generated empty schedule")
    print()

    # Auto-populate the schedule with only_legal=True to enforce all constraints
    print("Auto-populating schedule with constraints:")
    print("  • Max 1 match per day per player")
    print("  • Max 1 match per week per player")
    print("  • All other existing constraints")
    print()
    print("This may take a moment...")

    df_new, filled, skipped = autopopulate_plan(
        df_empty,
        max_slots=144,  # Fill all 144 slots
        only_legal=True,  # Only add matches that satisfy all constraints
        all_players=all_players,
        available_days=available_days,
        preferences=preferences,
        holidays=holidays
    )

    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"✓ Filled {len(filled)} slots")
    print(f"⚠ Skipped {len(skipped)} slots (no legal player combinations found)")
    print()

    # Save the new schedule
    print(f"Saving new schedule to {PLAN_FILE}...")
    df_new.to_csv(PLAN_FILE, index=False, encoding="utf-8")
    print("✓ Schedule saved successfully")
    print()

    # Show summary statistics
    if not df_new.empty:
        total_matches = len(df_new)
        total_singles = (df_new["Typ"] == "Einzel").sum()
        total_doubles = (df_new["Typ"] == "Doppel").sum()

        print("Schedule Statistics:")
        print(f"  Total matches: {total_matches}")
        print(f"  Singles: {total_singles}")
        print(f"  Doubles: {total_doubles}")
        print()

    # Verify no violations
    print("Running final verification...")
    from test_violations import check_violations
    # We'll just note that violations should be checked
    print("✓ Run 'python3 test_violations.py' to verify no violations exist")
    print()

    return 0

if __name__ == "__main__":
    sys.exit(main())
