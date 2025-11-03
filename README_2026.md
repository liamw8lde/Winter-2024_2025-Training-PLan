# Training Plan 2026 - Quick Start Guide

Autopopulation for the **Winter 2026 season** (January - April 2026).

---

## 🚀 Quick Start

### Run the 2026 App

```bash
streamlit run autopopulate_2026_app.py
```

**Password:** `tennis`

---

## 📁 Required Files

Make sure these files are in the same folder:

- ✅ `autopopulate_2026_app.py` - The 2026-specific app
- ✅ `Winterplan_2026.csv` - 2026 training plan (starts with 3 sample entries)
- ✅ `Spieler_Preferences_2026.csv` - Player preferences for 2026

---

## 📅 Season Details

**Dates:** January 5, 2026 - April 26, 2026

**Duration:** ~17 weeks

**Training Days:**
- **Montag (Monday):** 2 Doppel slots @ 20:00-22:00
- **Mittwoch (Wednesday):** 3 Einzel + 2 Doppel @ 18:00-21:30
- **Donnerstag (Thursday):** 2 Einzel @ 20:00-21:30

**Total:** 7 slots per week × 17 weeks = ~119 slots for the season

---

## 🎯 First Test

1. **Start the app:**
   ```bash
   streamlit run autopopulate_2026_app.py
   ```

2. **Login:** Password = `tennis`

3. **You'll see:**
   - Current plan: 3 slots (starter entries)
   - Empty slots: ~116 slots available
   - Players: 43 players from preferences

4. **Configure:**
   - Max slots: Start with `20`
   - Keep "Nur legale Zuweisungen" checked ✅

5. **Preview:**
   - Click "🔍 Vorschau generieren"
   - Wait 2-3 seconds

6. **Review:**
   - Check filled slots
   - Review player distribution
   - Verify dates are all in 2026

7. **Save:**
   - Download CSV for backup
   - Or save to GitHub as `Winterplan_2026.csv`

---

## 📊 What's Different from 2025?

| Feature | 2025 App | 2026 App |
|---------|----------|----------|
| File | `autopopulate_app.py` | `autopopulate_2026_app.py` |
| Plan CSV | `Winterplan.csv` | `Winterplan_2026.csv` |
| Dates | 2025-09 to 2026-01 | 2026-01 to 2026-04 |
| Season | Fall/Winter | Winter/Spring |
| Duration | ~20 weeks | ~17 weeks |

---

## 🔧 How It Works

### Initial Plan

`Winterplan_2026.csv` starts with **3 sample entries:**

1. **2026-01-05** (Montag) - Doppel @ 20:00
2. **2026-01-07** (Mittwoch) - Einzel @ 19:00
3. **2026-04-24** (Donnerstag) - Einzel @ 20:00

These establish the season bounds (Jan 5 - Apr 24).

### Autopopulation

The app:
1. Scans all Mondays, Wednesdays, Thursdays between Jan 5 and Apr 26
2. Identifies ~116 empty slots
3. For each slot:
   - Finds eligible players (availability, no holidays)
   - Respects preferences (nur Einzel/nur Doppel)
   - Applies load balancing (least-used players first)
   - Validates all rules
4. Fills slots incrementally
5. Shows results

---

## 💾 Saving Options

### Option 1: Download CSV (Recommended for testing)
- Click "📥 CSV herunterladen"
- Saves as `Winterplan_2026_autopopulated.csv`
- Open in Excel to verify
- Manually upload to GitHub when ready

### Option 2: Direct GitHub Save
- Requires `.streamlit/secrets.toml` with GitHub token
- Click "💾 Auf GitHub speichern (2026)"
- Automatically commits to `Winterplan_2026.csv`

---

## 📈 Expected Results

For a full autopopulation (all ~116 empty slots):

**Per Player:**
- Average: ~7-8 matches over 17 weeks
- Active players (3 available days): 10-12 matches
- Limited players (1 day): 3-5 matches
- Protected players: Varies by rules

**Distribution:**
- Load balancing ensures fairness
- Players with holidays get fewer assignments
- "nur Einzel"/"nur Doppel" preferences honored

---

## ⚠️ Important Notes

### Holidays in 2026

Players with holidays in the preferences CSV:
- **Kai Schroeder:** 2026-01-19 to 2026-01-31 (blocked)
- **Lars Staubermann:** 2026-03-23 to 2026-04-12 (blocked)
- **Others:** Various ranges in BlockedRanges column

The app automatically respects these!

### Preferences

From `Spieler_Preferences_2026.csv`:
- **Anke Ihde:** nur Doppel
- **Kerstin Baarck:** nur Doppel
- **Lena Meiss:** nur Doppel
- **Martina Schmidt:** nur Doppel
- **All others:** keine Präferenz

---

## 🐛 Troubleshooting

### "Error loading plan from Winterplan_2026.csv"

**Fix:** Make sure `Winterplan_2026.csv` exists in the folder
```bash
dir Winterplan_2026.csv
```

### "Could not load preferences"

**Fix:** Verify `Spieler_Preferences_2026.csv` exists
```bash
dir Spieler_Preferences_2026.csv
```

### No slots filled / All skipped

**Possible causes:**
- Too many players on holiday
- "Only legal" mode too restrictive
- Try disabling "Nur legale Zuweisungen"

### Strange dates in results

**Check:** All dates should be between 2026-01-05 and 2026-04-26
- If not, the app may have a bug
- Verify `SEASON_START` and `SEASON_END` in the app

---

## 📝 Workflow Example

### Full Season Population

```bash
# Week 1: Test with 20 slots
streamlit run autopopulate_2026_app.py
→ Set max=20
→ Generate preview
→ Download CSV
→ Review in Excel
→ Discard preview

# Week 2: Fill 50 more
→ Set max=50
→ Generate preview
→ Review distribution
→ Save to GitHub

# Week 3: Fill remaining
→ Set max=100
→ Generate preview
→ Check for issues
→ Save to GitHub

# Final: Verify complete
→ Should show "0 empty slots"
→ Download final CSV backup
```

---

## 🎓 Tips

1. **Start Small:** Fill 10-20 slots first to test
2. **Check Distribution:** Verify no player has too many/few matches
3. **Backup Often:** Download CSV before each GitHub save
4. **Watch Holidays:** January has many blocked dates
5. **Be Patient:** 100+ slots takes 5-10 seconds to process

---

## 📞 Support

**Issues?**
1. Check this README
2. See `WINDOWS_SETUP_GUIDE.md` for installation
3. See `AUTOPOPULATE_README.md` for algorithm details

**Files:**
- 2026 App: `autopopulate_2026_app.py`
- 2026 Plan: `Winterplan_2026.csv`
- 2026 Preferences: `Spieler_Preferences_2026.csv`

---

Happy Planning for 2026! 🎾
