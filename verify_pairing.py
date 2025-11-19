#!/usr/bin/env python3
"""Verify that paired players (Lena Meiss and Kerstin Baarck) play at the same time"""
import pandas as pd
import re

# Read the schedule
df = pd.read_csv("Winterplan_2026.csv")
df["Datum_dt"] = pd.to_datetime(df["Datum"], format="%Y-%m-%d")

# Find all matches for Lena Meiss
lena_matches = df[df["Spieler"].str.contains(r"\bLena Meiss\b", regex=True)]
print(f"=== Lena Meiss Matches: {len(lena_matches)} ===")
for _, row in lena_matches.iterrows():
    print(f"  {row['Datum']} {row['Slot']} ({row['Typ']})")
print()

# Find all matches for Kerstin Baarck
kerstin_matches = df[df["Spieler"].str.contains(r"\bKerstin Baarck\b", regex=True)]
print(f"=== Kerstin Baarck Matches: {len(kerstin_matches)} ===")
for _, row in kerstin_matches.iterrows():
    print(f"  {row['Datum']} {row['Slot']} ({row['Typ']})")
print()

# Check if they play at the same times
print("=== PAIRING VERIFICATION ===")
violations = []

# Extract date and time for each player
lena_times = set()
for _, row in lena_matches.iterrows():
    time_match = re.search(r"(\d{2}:\d{2})", row["Slot"])
    time = time_match.group(1) if time_match else "00:00"
    lena_times.add((row["Datum"], time))

kerstin_times = set()
for _, row in kerstin_matches.iterrows():
    time_match = re.search(r"(\d{2}:\d{2})", row["Slot"])
    time = time_match.group(1) if time_match else "00:00"
    kerstin_times.add((row["Datum"], time))

print(f"Lena plays on these date/times: {len(lena_times)}")
for date, time in sorted(lena_times):
    in_kerstin = (date, time) in kerstin_times
    status = "✓" if in_kerstin else "✗"
    print(f"  {status} {date} {time} {'(Kerstin also plays)' if in_kerstin else '(Kerstin NOT playing)'}")
    if not in_kerstin:
        violations.append(f"Lena plays {date} {time} but Kerstin doesn't")

print()
print(f"Kerstin plays on these date/times: {len(kerstin_times)}")
for date, time in sorted(kerstin_times):
    in_lena = (date, time) in lena_times
    status = "✓" if in_lena else "✗"
    print(f"  {status} {date} {time} {'(Lena also plays)' if in_lena else '(Lena NOT playing)'}")
    if not in_lena:
        violations.append(f"Kerstin plays {date} {time} but Lena doesn't")

print()
print("=== SUMMARY ===")
if violations:
    print(f"⚠ VIOLATIONS FOUND: {len(violations)}")
    for v in violations:
        print(f"  - {v}")
else:
    print("✓ All matches are paired correctly!")
    print(f"  Lena and Kerstin both play at exactly the same {len(lena_times)} date/times")
