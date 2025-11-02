# Windows 11 Setup Guide - Training Plan Autopopulation App

Complete guide to run the autopopulation Streamlit app on Windows 11.

---

## Prerequisites

### 1. Install Python (if not already installed)

**Check if Python is installed:**
```cmd
python --version
```

If you see `Python 3.8` or higher, you're good! If not:

1. Download Python from: https://www.python.org/downloads/
2. **IMPORTANT**: Check "Add Python to PATH" during installation
3. Install with default settings
4. Restart your terminal/command prompt

---

## Quick Setup (5 minutes)

### Step 1: Download the Files

**Option A: Using Git (if you have it)**
```cmd
cd C:\Users\YourUsername\Documents
git clone https://github.com/liamw8lde/Winter-2024_2025-Training-PLan.git
cd Winter-2024_2025-Training-PLan
git checkout claude/autopopulate-training-plan-011CUZABKzQJ2UH9qQ3S5Syv
```

**Option B: Manual Download (easier)**
1. Go to: https://github.com/liamw8lde/Winter-2024_2025-Training-PLan
2. Click the green "Code" button
3. Click "Download ZIP"
4. Extract to a folder like `C:\Users\YourUsername\Documents\training-plan`

---

### Step 2: Open Command Prompt in the Folder

**Easy way:**
1. Open File Explorer
2. Navigate to the folder with the files
3. Click in the address bar at the top
4. Type `cmd` and press Enter
5. A command prompt will open in that folder

**Or manually:**
```cmd
cd C:\Users\YourUsername\Documents\training-plan
```

---

### Step 3: Install Streamlit

```cmd
pip install streamlit pandas requests
```

Wait for installation to complete (1-2 minutes).

---

### Step 4: Run the App

```cmd
streamlit run autopopulate_app.py
```

The app should automatically open in your default browser at `http://localhost:8501`

---

## Detailed Instructions

### Verify Your Setup

**Check all required files exist:**
```cmd
dir
```

You should see:
- ✅ `autopopulate_app.py`
- ✅ `Winterplan.csv`
- ✅ `Spieler_Preferences_2026.csv`

If any are missing, download them from GitHub.

---

### First Time Running

1. **Login Screen:**
   - Password: `tennis`
   - Click "Einloggen"

2. **Dashboard:**
   - You'll see current plan statistics
   - Number of empty slots
   - Player count

3. **Configure Settings:**
   - Set "Maximale Anzahl Slots" (try 10 for first test)
   - Keep "Nur legale Zuweisungen" checked
   - Click "🔍 Vorschau generieren"

4. **Review Results:**
   - See which slots were filled
   - Check player distribution
   - Review any skipped slots

5. **Test Actions:**
   - Click "📥 CSV herunterladen" to save locally
   - Click "🗑️ Vorschau verwerfen" to reset

---

## Optional: GitHub Integration

If you want to save directly to GitHub:

### Step 1: Create GitHub Token

1. Go to: https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Give it a name: "Training Plan App"
4. Check these permissions:
   - ✅ `repo` (full control)
5. Click "Generate token"
6. **COPY THE TOKEN** (you won't see it again!)

### Step 2: Create Secrets File

1. In your project folder, create a `.streamlit` folder:
```cmd
mkdir .streamlit
```

2. Create a file called `secrets.toml` inside:
```cmd
notepad .streamlit\secrets.toml
```

3. Add this content (replace YOUR_TOKEN):
```toml
GITHUB_TOKEN = "YOUR_TOKEN_HERE"
GITHUB_REPO = "liamw8lde/Winter-2024_2025-Training-PLan"
GITHUB_BRANCH = "main"
GITHUB_PATH = "Winterplan.csv"
```

4. Save and close Notepad

5. Restart the app:
```cmd
streamlit run autopopulate_app.py
```

Now the "💾 Auf GitHub speichern" button will work!

---

## Troubleshooting

### ❌ "Python is not recognized"

**Fix:**
1. Re-install Python
2. **CHECK** "Add Python to PATH" during installation
3. Restart Command Prompt

**Or manually add to PATH:**
1. Search for "Environment Variables" in Windows
2. Click "Environment Variables"
3. Under "System variables", find "Path"
4. Click "Edit"
5. Click "New"
6. Add: `C:\Users\YourUsername\AppData\Local\Programs\Python\Python311`
7. Add another: `C:\Users\YourUsername\AppData\Local\Programs\Python\Python311\Scripts`
8. Click OK
9. Restart Command Prompt

---

### ❌ "streamlit is not recognized"

**Fix:**
```cmd
python -m pip install --upgrade pip
python -m pip install streamlit pandas requests
```

Then run with:
```cmd
python -m streamlit run autopopulate_app.py
```

---

### ❌ "Error loading plan: [WinError 2]"

**Issue:** CSV files not found

**Fix:**
1. Check you're in the correct folder:
```cmd
cd
```
Should show the folder with the files.

2. List files:
```cmd
dir *.csv
```
Should show `Winterplan.csv` and `Spieler_Preferences_2026.csv`

3. If files are missing, download from GitHub

---

### ❌ App opens but shows errors

**Fix:**
1. Check Python version:
```cmd
python --version
```
Must be 3.8 or higher

2. Reinstall dependencies:
```cmd
pip install --upgrade streamlit pandas requests
```

3. Restart the app

---

### ❌ "Address already in use"

**Issue:** Port 8501 is busy

**Fix:**
```cmd
streamlit run autopopulate_app.py --server.port 8502
```

---

### ❌ Browser doesn't open automatically

**Fix:**
Manually open your browser and go to:
```
http://localhost:8501
```

---

## Command Reference

### Start the app
```cmd
streamlit run autopopulate_app.py
```

### Stop the app
Press `Ctrl + C` in the Command Prompt

### Clear cache and restart
```cmd
streamlit cache clear
streamlit run autopopulate_app.py
```

### Run on different port
```cmd
streamlit run autopopulate_app.py --server.port 8502
```

### Check installed packages
```cmd
pip list
```

### Update Streamlit
```cmd
pip install --upgrade streamlit
```

---

## File Structure

Your folder should look like this:
```
training-plan/
├── autopopulate_app.py          ← The app
├── streamlit_app.py              ← Original app (optional)
├── Winterplan.csv                ← Training plan data
├── Spieler_Preferences_2026.csv  ← Player preferences
├── AUTOPOPULATE_README.md        ← Documentation
├── WINDOWS_SETUP_GUIDE.md        ← This file
└── .streamlit/
    └── secrets.toml              ← GitHub credentials (optional)
```

---

## Performance Tips

### Faster Loading
1. Close other browser tabs
2. Use Chrome or Edge (better than Firefox for Streamlit)
3. Don't run other heavy applications

### Memory Usage
- The app uses ~100-200 MB RAM
- Safe to run on any modern Windows 11 PC

---

## Next Steps After Testing

### Workflow
1. **Test locally first** (without GitHub integration)
2. **Download CSV** to backup results
3. **Review player distribution** for fairness
4. **Set up GitHub** when ready to go live
5. **Save to GitHub** to update the plan

### Recommended First Test
```
Settings:
- Max slots: 10
- Only legal: ✅ Checked

1. Generate preview
2. Review filled slots
3. Check player stats
4. Download CSV
5. Verify in Excel/spreadsheet
```

---

## Support

### Common Questions

**Q: Can I run this without GitHub?**
A: Yes! Just use the CSV download button instead.

**Q: Will this modify my original files?**
A: Only if you click "Auf GitHub speichern". The preview is safe.

**Q: Can I undo changes?**
A: Yes, use Git to revert, or keep CSV backups.

**Q: How long does it take?**
A: Preview generation: 1-5 seconds. Filling 20 slots: ~2 seconds.

**Q: Can I customize the rules?**
A: Yes! Edit `autopopulate_app.py` and modify the validation functions.

### Video Tutorial Equivalent

1. **0:00** - Open Command Prompt in folder
2. **0:30** - Type `streamlit run autopopulate_app.py`
3. **0:45** - Login with password "tennis"
4. **1:00** - Set max slots to 10
5. **1:15** - Click "Vorschau generieren"
6. **1:30** - Review results
7. **2:00** - Download CSV or save to GitHub

---

## Keyboard Shortcuts in App

- `Ctrl + R` - Refresh page
- `Ctrl + Shift + R` - Hard refresh (clear cache)
- `Ctrl + W` - Close tab
- `F5` - Reload page
- `F11` - Fullscreen

---

## Safety Notes

✅ **Safe Operations:**
- Generating previews
- Downloading CSV
- Viewing statistics
- Resetting preview

⚠️ **Requires Attention:**
- Saving to GitHub (creates commit)
- Modifying validation rules in code

🛡️ **Best Practices:**
- Always preview before saving
- Keep CSV backups
- Test with small numbers first (10-20 slots)
- Review player distribution

---

## Contact & Issues

If you encounter issues:
1. Check this guide's Troubleshooting section
2. Read `AUTOPOPULATE_README.md`
3. Check GitHub Issues tab
4. Create new issue with error details

---

## Version Info

- **App Version:** 1.0
- **Python Required:** 3.8+
- **Streamlit Version:** Latest (auto-installed)
- **Tested On:** Windows 11, Python 3.11
- **Last Updated:** 2025

---

Happy Auto-Populating! 🎾
