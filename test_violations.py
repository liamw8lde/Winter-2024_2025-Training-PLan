#!/usr/bin/env python3
"""Test script to check for daily and weekly violations in the current schedule"""
import pandas as pd
import re
from datetime import date

# Read the schedule
df = pd.read_csv("Winterplan_2026.csv")
df["Datum_dt"] = pd.to_datetime(df["Datum"], format="%Y-%m-%d")

# Extract all players from each row
def extract_players(spieler_str):
    """Extract individual players from comma-separated string"""
    if pd.isna(spieler_str):
        return []
    return [p.strip() for p in spieler_str.split(",")]

# Check for daily violations
print("=== CHECKING FOR DAILY VIOLATIONS (players playing more than once per day) ===\n")
daily_violations = {}
for idx, row in df.iterrows():
    d = row["Datum_dt"].date()
    players = extract_players(row["Spieler"])

    for player in players:
        # Count how many times this player appears on this date
        same_day = df[df["Datum_dt"].dt.date == d]
        count = same_day["Spieler"].str.contains(fr"\b{re.escape(player)}\b", regex=True).sum()

        if count > 1:
            if d not in daily_violations:
                daily_violations[d] = {}
            if player not in daily_violations[d]:
                daily_violations[d][player] = count

# Print daily violations
if daily_violations:
    for d, players in sorted(daily_violations.items()):
        print(f"Date: {d}")
        for player, count in players.items():
            # Get the slots where this player plays
            same_day = df[df["Datum_dt"].dt.date == d]
            slots = same_day[same_day["Spieler"].str.contains(fr"\b{re.escape(player)}\b", regex=True)][["Slot", "Typ"]].values
            print(f"  - {player}: {count} matches")
            for slot, typ in slots:
                print(f"      {slot} ({typ})")
        print()
else:
    print("No daily violations found.\n")

# Check for weekly violations
print("=== CHECKING FOR WEEKLY VIOLATIONS (players playing more than once per week) ===\n")
df["Jahr"] = df["Datum_dt"].dt.isocalendar().year
df["Woche"] = df["Datum_dt"].dt.isocalendar().week

weekly_violations = {}
for idx, row in df.iterrows():
    year = row["Jahr"]
    week = row["Woche"]
    players = extract_players(row["Spieler"])

    for player in players:
        # Count how many times this player appears in this week
        same_week = df[(df["Jahr"] == year) & (df["Woche"] == week)]
        count = same_week["Spieler"].str.contains(fr"\b{re.escape(player)}\b", regex=True).sum()

        if count > 1:
            week_key = (year, week)
            if week_key not in weekly_violations:
                weekly_violations[week_key] = {}
            if player not in weekly_violations[week_key]:
                weekly_violations[week_key][player] = count

# Print weekly violations
if weekly_violations:
    for (year, week), players in sorted(weekly_violations.items()):
        print(f"Week {week}/{year}")
        for player, count in players.items():
            # Get the dates where this player plays
            same_week = df[(df["Jahr"] == year) & (df["Woche"] == week)]
            matches = same_week[same_week["Spieler"].str.contains(fr"\b{re.escape(player)}\b", regex=True)][["Datum", "Slot", "Typ"]].values
            print(f"  - {player}: {count} matches")
            for datum, slot, typ in matches:
                print(f"      {datum} {slot} ({typ})")
        print()
else:
    print("No weekly violations found.\n")

print(f"\n=== SUMMARY ===")
print(f"Daily violations: {len(daily_violations)} days affected")
print(f"Weekly violations: {len(weekly_violations)} weeks affected")
