#!/usr/bin/env python3
"""Analyze player match distribution in the current schedule"""
import pandas as pd
import re

# Read the schedule
df = pd.read_csv("Winterplan_2026.csv")

# Count matches per player
player_counts = {}
for _, row in df.iterrows():
    players = [p.strip() for p in row["Spieler"].split(",")]
    for player in players:
        player_counts[player] = player_counts.get(player, 0) + 1

# Sort by count
sorted_players = sorted(player_counts.items(), key=lambda x: x[1])

print("=== PLAYER MATCH DISTRIBUTION ===")
print(f"Total players: {len(sorted_players)}")
print(f"Total matches in schedule: {len(df)}")
print()

# Show statistics
match_counts = [count for _, count in sorted_players]
avg_matches = sum(match_counts) / len(match_counts)
min_matches = min(match_counts)
max_matches = max(match_counts)

print(f"Average matches per player: {avg_matches:.1f}")
print(f"Min matches: {min_matches}")
print(f"Max matches: {max_matches}")
print(f"Difference: {max_matches - min_matches}")
print()

# Show players with fewest matches
print("=== PLAYERS WITH FEWEST MATCHES ===")
for player, count in sorted_players[:10]:
    print(f"{count:2d} matches: {player}")

print()
print("=== PLAYERS WITH MOST MATCHES ===")
for player, count in sorted_players[-10:]:
    print(f"{count:2d} matches: {player}")

# Check Thomas Grueneberg specifically
thomas_matches = player_counts.get("Thomas Grueneberg", 0)
print()
print(f"=== Thomas Grueneberg: {thomas_matches} matches ===")
