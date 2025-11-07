#!/usr/bin/env python3
"""Analyze singles match variety - check for repeated pairings"""
import pandas as pd
from collections import Counter

# Read the schedule
df = pd.read_csv("Winterplan_2026.csv")

# Filter for singles matches only
singles = df[df["Typ"] == "Einzel"].copy()

print("=== SINGLES MATCH VARIETY ANALYSIS ===")
print(f"Total singles matches: {len(singles)}")
print()

# Count pairings
pairings = []
for _, row in singles.iterrows():
    players = sorted([p.strip() for p in row["Spieler"].split(",")])
    if len(players) == 2:
        pair = tuple(players)
        pairings.append(pair)

pairing_counts = Counter(pairings)

# Show most frequent pairings
print("=== MOST FREQUENT SINGLES PAIRINGS ===")
for (p1, p2), count in sorted(pairing_counts.items(), key=lambda x: x[1], reverse=True)[:20]:
    print(f"{count:2d} times: {p1} vs {p2}")

print()

# Check specific players
players_to_check = ["Liam Wilde", "Thomas Bretschneider", "Thomas Grueneberg", "Patrick Buehrsch"]
print("=== OPPONENT VARIETY FOR SPECIFIC PLAYERS ===")
for player in players_to_check:
    player_matches = singles[singles["Spieler"].str.contains(fr"\b{player}\b", regex=True)]
    opponents = []
    for _, row in player_matches.iterrows():
        players_in_match = [p.strip() for p in row["Spieler"].split(",")]
        opponent = [p for p in players_in_match if p != player]
        if opponent:
            opponents.append(opponent[0])

    if opponents:
        opponent_counts = Counter(opponents)
        print(f"\n{player} ({len(opponents)} singles matches):")
        for opp, count in sorted(opponent_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {count} times vs {opp}")
