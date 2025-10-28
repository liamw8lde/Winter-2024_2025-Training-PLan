# Training Plan Auto-Population App

A standalone Streamlit application for automatically filling empty training slots with intelligent load balancing and rule compliance.

## Features

- **Smart Player Selection**: Automatically selects players based on availability, preferences, and fairness
- **Load Balancing**: Prioritizes players with fewer appearances to ensure fair distribution
- **Rule Compliance**: Respects all constraints including:
  - Weekday availability
  - Holidays and blocked dates
  - Player preferences (nur Einzel/nur Doppel)
  - Protected player time restrictions
  - Rank windows for singles matches (Δ ≤ 2)
- **Preview Mode**: Review changes before committing
- **GitHub Integration**: Save directly to GitHub with commit messages

## Running the App

### Option 1: Local Streamlit
```bash
streamlit run autopopulate_app.py
```

### Option 2: From main app directory
```bash
cd /path/to/Winter-2024_2025-Training-PLan
streamlit run autopopulate_app.py
```

## Configuration

The app requires these files in the same directory:
- `Winterplan.csv` - Current training plan
- `Spieler_Preferences_2026.csv` - Player preferences and availability

### GitHub Secrets (for saving)

Add these to `.streamlit/secrets.toml`:
```toml
GITHUB_TOKEN = "your_github_token"
GITHUB_REPO = "username/repo"
GITHUB_BRANCH = "main"
GITHUB_PATH = "Winterplan.csv"
```

## Usage

1. **Login**: Enter password (default: "tennis")
2. **Review Empty Slots**: See how many slots need to be filled
3. **Configure Settings**:
   - Set maximum slots to fill
   - Toggle "only legal assignments" mode
4. **Generate Preview**: Click to see proposed assignments
5. **Review Results**:
   - See which slots were filled
   - Check player distribution for fairness
   - Review any skipped slots
6. **Save or Discard**:
   - Save to GitHub
   - Download as CSV
   - Discard and try different settings

## Algorithm Overview

```
1. Find Empty Slots
   └─ Compare allowed slots vs current plan

2. For Each Empty Slot:
   ├─ Get All Players
   ├─ Score Each Candidate:
   │  ├─ Check availability (weekday, holidays)
   │  ├─ Check preferences (nur Einzel/Doppel)
   │  ├─ Check protected rules
   │  ├─ Count season/week appearances
   │  └─ Calculate violations
   ├─ Filter by type preference
   ├─ Sort: Legal first → Least used → Rank
   └─ Select:
      ├─ Einzel: 2 players with rank Δ ≤ 2
      └─ Doppel: 4 legal players

3. Build New Plan
   └─ Add rows for filled slots

4. Return:
   ├─ Updated plan
   ├─ Filled slots list
   └─ Skipped slots list
```

## Data Sources

### Player Rankings (Hard-coded)
Ranks 1-6 (1 = strongest, 6 = weakest):
- Rank 1: Bjoern Junker, Patrick Buehrsch
- Rank 2: Frank Petermann, Jens Krause, Joerg Peters, Lars Staubermann, etc.
- ...
- Rank 6: Anke Ihde, Lena Meiss, Martina Schmidt, etc.

### CSV: Spieler_Preferences_2026.csv
- **Spieler**: Player name
- **AvailableDays**: Comma-separated weekdays (Montag, Mittwoch, Donnerstag)
- **Preference**: "keine Präferenz", "nur Einzel", or "nur Doppel"
- **BlockedRanges**: Date ranges (2026-01-01→2026-01-04)
- **BlockedDays**: Individual blocked dates (2026-01-15)

### Protected Player Rules
Special time restrictions:
- Patrick Buehrsch: Only 18:00
- Frank Petermann: Only 19:00 or 20:00
- Matthias Duddek: Only 18:00 or 19:00
- Dirk Kistner: Mo/Mi/Do only, Mittwoch→19:00 only, max 2/week
- Arndt Stueber: Mittwoch 19:00 only
- Thomas Grueneberg: Max 30% Wed 20:00, min 70% 18/19
- Jens Hafner: Mittwoch 19:00 only

### Women Singles Ban
These players cannot play Einzel:
- Anke Ihde
- Lena Meiss
- Martina Schmidt
- Kerstin Baarck

## Allowed Slots

### Montag (Monday)
- D20:00-120 PLA (Doppel, 2 hours)
- D20:00-120 PLB (Doppel, 2 hours)

### Mittwoch (Wednesday)
- E18:00-60 PLA (Einzel, 1 hour)
- E19:00-60 PLA (Einzel, 1 hour)
- E19:00-60 PLB (Einzel, 1 hour)
- D20:00-90 PLA (Doppel, 1.5 hours)
- D20:00-90 PLB (Doppel, 1.5 hours)

### Donnerstag (Thursday)
- E20:00-90 PLA (Einzel, 1.5 hours)
- E20:00-90 PLB (Einzel, 1.5 hours)

## Tips

- **Start Small**: Fill 10-20 slots first to test
- **Use Legal Mode**: Ensure no rule violations
- **Check Distribution**: Review player statistics for fairness
- **Preview First**: Always preview before saving
- **Download Backup**: Save CSV locally before GitHub upload

## Troubleshooting

**No slots filled?**
- Check if "only legal" is too restrictive
- Review skipped slots to see why players couldn't be assigned
- Some weeks may have too many holidays

**Unbalanced distribution?**
- Algorithm already prioritizes least-used players
- Some players have more availability (more weekdays)
- Protected rules limit some players to specific times

**GitHub save fails?**
- Check secrets.toml configuration
- Verify GitHub token has write permissions
- Ensure GITHUB_REPO format is "owner/repo"

## Development

To modify the algorithm:
1. Edit `select_players_for_slot()` for selection logic
2. Edit `check_violations()` for new rules
3. Update `RANK` dictionary for player rankings
4. Modify `ALLOWED_SLOTS` for new time slots

## License

Part of Winter-2024_2025-Training-PLan project.
