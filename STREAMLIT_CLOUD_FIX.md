# Streamlit Cloud GitHub Authentication Fix

## Problem
Your Streamlit app at https://winterplan.streamlit.app/ is showing this error:
```
Laden fehlgeschlagen für ref main. Fehler: GitHub contents GET failed 401:
{ "message": "Bad credentials", "documentation_url": "https://docs.github.com/rest", "status": "401" }
```

This means the GitHub token configured in **Streamlit Cloud** is either:
- ❌ Missing
- ❌ Invalid or expired
- ❌ Missing required permissions

## Solution: Configure Streamlit Cloud Secrets

### Step 1: Create a GitHub Personal Access Token

1. Go to: https://github.com/settings/tokens
2. Click **"Tokens (classic)"** in the left sidebar
3. Click **"Generate new token"** → **"Generate new token (classic)"**
4. Configure the token:
   - **Note**: `Winterplan Streamlit App`
   - **Expiration**: Choose `No expiration` or set a far future date
   - **Scopes**: Check **only** `repo` (this will auto-select all sub-scopes)
5. Scroll down and click **"Generate token"**
6. **IMPORTANT**: Copy the token immediately! Format: `ghp_xxxxxxxxxxxxxxxxxxxx`
   - You'll only see it once
   - Keep it secure

### Step 2: Configure Secrets in Streamlit Cloud

1. Go to: https://share.streamlit.io/
2. Sign in with your GitHub account
3. Find your app **"winterplan"** in the dashboard
4. Click the **three dots (⋮)** menu on your app
5. Select **"Settings"**
6. Click on **"Secrets"** in the left sidebar
7. In the secrets editor, paste the following (replace `YOUR_TOKEN_HERE` with your actual token):

```toml
GITHUB_TOKEN = "ghp_your_actual_token_here"
GITHUB_REPO = "liamw8lde/Winter-2024_2025-Training-PLan"
GITHUB_BRANCH = "main"
GITHUB_COMMITTER_NAME = "Winterplan App"
GITHUB_COMMITTER_EMAIL = "winterplan@streamlit.app"
```

8. Click **"Save"**

### Step 3: Verify the Fix

1. The app will automatically restart
2. Wait 10-30 seconds for the restart
3. Refresh your app: https://winterplan.streamlit.app/
4. The error should be gone!

## Troubleshooting

### Error still appears: "401 Bad credentials"

**Check 1: Token Format**
- Token must start with `ghp_`
- No extra spaces or quotes inside the string
- Example: `GITHUB_TOKEN = "ghp_abc123XYZ"`

**Check 2: Token Permissions**
1. Go to https://github.com/settings/tokens
2. Find your token in the list
3. Click on it to view details
4. Verify that `repo` scope is checked ✓
5. If not, delete the token and create a new one with correct permissions

**Check 3: Token Expiration**
- Check if your token has expired
- Create a new token if needed

### Error: "404 Not Found"

This means the repository settings are incorrect:
- Verify `GITHUB_REPO = "liamw8lde/Winter-2024_2025-Training-PLan"`
- Make sure you have access to this repository

### Error: "403 Forbidden"

This means the token doesn't have write permissions:
- Recreate the token with `repo` scope
- If you're not the repository owner, ask the owner to give you write access

## Testing Your Token (Optional)

You can test your token using curl before adding it to Streamlit Cloud:

```bash
curl -H "Authorization: Bearer ghp_yourtoken" \
     https://api.github.com/repos/liamw8lde/Winter-2024_2025-Training-PLan/contents/Winterplan.csv?ref=main
```

If successful, you'll see JSON data about the file. If failed, you'll see an error message.

## Security Notes

⚠️ **IMPORTANT SECURITY INFORMATION:**

1. **Never commit tokens to Git**: The `.streamlit/secrets.toml` file is in `.gitignore` and should never be committed
2. **Streamlit Cloud secrets are secure**: Secrets stored in Streamlit Cloud are encrypted and not visible in your code
3. **Token permissions**: Only grant `repo` scope, nothing more
4. **Rotate tokens regularly**: Consider regenerating your token every 6-12 months
5. **Revoke old tokens**: Delete unused tokens from https://github.com/settings/tokens

## Local Development vs. Streamlit Cloud

**Important distinction:**

- **Local development**: Uses `.streamlit/secrets.toml` file in your project
- **Streamlit Cloud**: Uses secrets configured in the Streamlit Cloud dashboard

The local file is NOT used by Streamlit Cloud. You must configure secrets in both places:
- Local: Edit `.streamlit/secrets.toml` (already fixed)
- Cloud: Configure via Streamlit Cloud dashboard (follow steps above)

## Need Help?

If you're still experiencing issues:

1. Check Streamlit Cloud logs:
   - Go to your app dashboard
   - Click on your app
   - Check the "Logs" section for error details

2. Verify your app settings:
   - Repository: `liamw8lde/Winter-2024_2025-Training-PLan`
   - Branch: `main`
   - Main file path: `streamlit_app.py`

3. Check the GitHub API directly:
   - Visit: https://api.github.com/repos/liamw8lde/Winter-2024_2025-Training-PLan
   - If this loads, your repository is public and accessible
