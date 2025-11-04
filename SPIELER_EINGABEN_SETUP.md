# Spieler Eingaben App - GitHub Authentication Setup

## Problem
Your Streamlit app at **https://spieler-eingaben.streamlit.app/** shows this error when saving:

```
GET https://api.github.com/repos/liamw8lde/Winter-2024_2025-Training-PLan/contents/Spieler_Preferences_2026.csv → 401: Bad credentials

GitHub API-Aktualisierung fehlgeschlagen. Details siehe oben.
```

This means the GitHub token configured in **Streamlit Cloud** for this app is either:
- ❌ Missing
- ❌ Invalid or expired
- ❌ Has incorrect format or permissions

## Solution: Configure Streamlit Cloud Secrets

### Step 1: Create a GitHub Personal Access Token

1. Go to: **https://github.com/settings/tokens**
2. Click **"Tokens (classic)"** in the left sidebar
3. Click **"Generate new token"** → **"Generate new token (classic)"**
4. Configure the token:
   - **Note**: `Spieler Eingaben Streamlit App`
   - **Expiration**: Choose `No expiration` or set a far future date
   - **Scopes**: Check **only** ✓ `repo` (this will auto-select all sub-scopes including Contents)
5. Scroll down and click **"Generate token"**
6. **CRITICAL**: Copy the token immediately!
   - Format looks like: `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
   - You'll only see it once - if you lose it, you must create a new one
   - Keep it secure and private

### Step 2: Configure Secrets in Streamlit Cloud

1. Go to: **https://share.streamlit.io/**
2. Sign in with your GitHub account (liamw8lde)
3. Find your app **"spieler-eingaben"** in the app list/dashboard
4. Click the **three dots (⋮)** menu next to your app
5. Select **"Settings"**
6. Click on **"Secrets"** in the left sidebar
7. In the secrets editor, paste the following (replace the token with your actual token from Step 1):

```toml
GITHUB_TOKEN = "ghp_your_actual_token_here_from_step_1"
GITHUB_REPO = "liamw8lde/Winter-2024_2025-Training-PLan"
GITHUB_BRANCH = "main"
GITHUB_COMMITTER_NAME = "Spieler Eingaben App"
GITHUB_COMMITTER_EMAIL = "spieler-eingaben@streamlit.app"
```

8. Click **"Save"**
9. The app will automatically restart (takes 10-30 seconds)

### Step 3: Verify the Fix

1. Wait for the app to restart (10-30 seconds)
2. Refresh your app: **https://spieler-eingaben.streamlit.app/**
3. Try saving player preferences again
4. You should see: ✅ "Änderungen wurden über die GitHub API gespeichert"

## Troubleshooting

### Issue 1: Still getting "401 Bad credentials"

**Possible causes:**

1. **Token format is wrong**
   - ✅ Correct: `GITHUB_TOKEN = "ghp_abc123xyz"`
   - ❌ Wrong: `GITHUB_TOKEN = ghp_abc123xyz` (missing quotes)
   - ❌ Wrong: `GITHUB_TOKEN = "your_github_personal_access_token_here"` (placeholder not replaced)
   - ❌ Wrong: Extra spaces around token

2. **Token doesn't have correct permissions**
   - Go to: https://github.com/settings/tokens
   - Find your token in the list
   - Click on it to view details
   - Verify that **`repo`** scope is checked ✓
   - If not, delete and create a new token with correct permissions

3. **Token has expired**
   - Check token expiration date at https://github.com/settings/tokens
   - Create a new token if expired

### Issue 2: "404 Not Found"

This means the repository path is incorrect:
- Verify: `GITHUB_REPO = "liamw8lde/Winter-2024_2025-Training-PLan"`
- Check that the repository exists and you have access

### Issue 3: "403 Forbidden"

This means the token doesn't have write permissions:
- Recreate the token with `repo` scope (includes write access)
- Verify you're the repository owner or have write collaborator access

### Issue 4: Error shows "Token beginnt mit: 'your...'"

This means you're still using the placeholder token:
- You must replace `your_github_personal_access_token_here` with a real token
- Follow Step 1 above to create a real GitHub token

## Testing Your Token (Before Streamlit Cloud Setup)

You can test your token using curl to verify it works:

```bash
# Test read access
curl -H "Authorization: Bearer YOUR_TOKEN_HERE" \
     https://api.github.com/repos/liamw8lde/Winter-2024_2025-Training-PLan/contents/Spieler_Preferences_2026.csv?ref=main
```

**Expected result if token is valid:**
- You'll see JSON data with file information
- Status code: 200 OK

**If token is invalid:**
- You'll see: `{"message": "Bad credentials", ...}`
- Status code: 401

## Security Best Practices

⚠️ **IMPORTANT:**

1. **Never commit tokens to Git**
   - The `.streamlit/secrets.toml` file is in `.gitignore`
   - Local secrets file is only for local testing
   - Production uses Streamlit Cloud dashboard

2. **Streamlit Cloud secrets are encrypted**
   - Secrets are stored securely
   - Not visible in code or logs
   - Only accessible to your app at runtime

3. **Minimal permissions**
   - Only grant `repo` scope
   - Don't grant admin, delete, or other unnecessary scopes

4. **Token rotation**
   - Regenerate tokens every 6-12 months
   - Delete old/unused tokens from https://github.com/settings/tokens

5. **Access control**
   - Only authorized users should have access to Streamlit Cloud app settings
   - Review who has access to your GitHub repository

## Different Apps = Different Secrets

**Important:** This repository has multiple Streamlit apps:

1. **Winterplan App** (`streamlit_app.py`)
   - URL: https://winterplan.streamlit.app/
   - Needs secrets configured separately

2. **Spieler Eingaben 2026 App** (`player_input_2026.py`)
   - URL: https://spieler-eingaben.streamlit.app/
   - This is the app you're fixing now
   - Needs its own secrets configuration

Each deployed app on Streamlit Cloud needs its own secrets configuration, even if they're from the same repository. Make sure you're configuring secrets for the correct app!

## Local Development vs. Streamlit Cloud

**Key difference:**

- **Local development**:
  - Uses `.streamlit/secrets.toml` file in your project folder
  - File is on your computer only
  - Good for testing before deployment

- **Streamlit Cloud (Production)**:
  - Uses secrets configured in Streamlit Cloud dashboard
  - Does NOT read the local `.streamlit/secrets.toml` file
  - You must configure separately via web interface

The local file is NOT used by deployed apps. You need to configure in both places:
- ✅ Local: Edit `.streamlit/secrets.toml` (for local testing)
- ✅ Cloud: Configure via Streamlit Cloud dashboard (for production)

## Need More Help?

### Check Streamlit Cloud Logs

1. Go to: https://share.streamlit.io/
2. Click on your "spieler-eingaben" app
3. Look at the **"Logs"** section
4. Check for error messages or authentication failures

### Verify App Configuration

Make sure your app settings are correct:
- **Repository**: `liamw8lde/Winter-2024_2025-Training-PLan`
- **Branch**: `main`
- **Main file path**: `player_input_2026.py`

### Test GitHub API Access

Visit this URL in your browser to verify the repository is accessible:
- https://api.github.com/repos/liamw8lde/Winter-2024_2025-Training-PLan

If this loads with repository information, the repo is accessible.

### Contact Support

If you're still stuck:
- Streamlit Community Forum: https://discuss.streamlit.io/
- GitHub Token Help: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token

---

## What the Code Changes Fixed

The latest update to `player_input_2026.py` includes:

1. ✅ **Token whitespace handling**: Automatically strips extra spaces from tokens
2. ✅ **Token format validation**: Checks if token starts with valid prefix (`ghp_`, `github_pat_`, `gho_`)
3. ✅ **Better error messages**: Shows clear instructions when 401 errors occur
4. ✅ **Diagnostic information**: Displays token prefix and length (without exposing full token)

These improvements will help you diagnose configuration issues more easily!
