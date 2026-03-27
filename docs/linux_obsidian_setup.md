# Linux Obsidian Setup — OpenClaw Sprint 7

This runbook sets up Obsidian with the Local REST API on a Ubuntu/Debian-based Linux x86_64 system (ThinkPad W540).

---

## Prerequisites

- Linux x86_64 (Ubuntu 20.04+, Debian, Fedora, etc.)
- `curl`, `wget`, `python3` in `$PATH`
- `OPENCLAW_WORKSPACE` already configured (run `bash setup.sh` first)

---

## Step 1: Download and Install Obsidian AppImage

> **Why `curl + python3` instead of bare `wget "...*.AppImage"`?**
> Shell glob patterns (`*`) do **not expand inside quoted strings** — `wget "...Obsidian-*.AppImage"` downloads a file literally named `Obsidian-*.AppImage`. The method below resolves the current release URL via the GitHub API at runtime.

```bash
# Resolve the latest Obsidian AppImage download URL via GitHub API
APPIMAGE_URL=$(curl -s https://api.github.com/repos/obsidianmd/obsidian-releases/releases/latest \
  | python3 -c "
import sys, json
assets = json.load(sys.stdin)['assets']
appimages = [a['browser_download_url'] for a in assets
             if a['name'].endswith('.AppImage') and 'arm' not in a['name']]
print(appimages[0])
")

echo "Downloading: $APPIMAGE_URL"
wget "$APPIMAGE_URL" -O ~/obsidian.AppImage
chmod +x ~/obsidian.AppImage
```

---

## Step 2: First Run — Create Your Vault

```bash
~/obsidian.AppImage
```

1. In the Obsidian welcome screen, choose **"Create new vault"**
2. Set vault name to `OpenClaw` (or any name you prefer)
3. For location, choose `~/obsidian-vault/` (or a path of your choice)
4. Click **"Create"**

---

## Step 3: Set `OBSIDIAN_VAULT_PATH` Environment Variable

```bash
# Add to your ~/.bashrc (or ~/.profile)
echo 'export OBSIDIAN_VAULT_PATH="$HOME/obsidian-vault"' >> ~/.bashrc
source ~/.bashrc
```

Then bootstrap the Johnny.Decimal folder structure:

```bash
# This is safe to re-run — creates missing folders, leaves existing ones unchanged
python3 openclaw_skills/obsidian_vault_bootstrap.py "$OBSIDIAN_VAULT_PATH"
```

Expected output:
```
[VAULT] Created 8 folder(s): 00 - INBOX, 00 - INBOX/openclaw, 10 - PROJECTS, ...
[VAULT] Johnny.Decimal structure ready at: /home/alexey/obsidian-vault
```

---

## Step 4: Install the Local REST API Plugin

The Local REST API plugin (`coddingtonbear/obsidian-local-rest-api`) provides a REST interface on `http://127.0.0.1:27123`.

### In Obsidian:

1. Open **Settings → Community Plugins**
2. Disable Safe Mode (if prompted)
3. Click **Browse**
4. Search for `Local REST API`
5. Click **Install**, then **Enable**
6. Go to **Settings → Local REST API**
7. Copy the API key displayed in the settings panel

> **Note:** By default the plugin generates a random API key and requires it for all requests. An empty key returns `401 Unauthorized` on every call.

---

## Step 5: Configure `OBSIDIAN_API_KEY`

```bash
# Add to ~/.bashrc
echo 'export OBSIDIAN_API_KEY="<paste-your-key-here>"' >> ~/.bashrc
source ~/.bashrc
```

**Never commit this key to version control.** It is a secret that grants full vault read/write access.

---

## Step 6: Verify the Integration

```bash
# Basic connectivity test (requires Obsidian to be running)
curl -s \
  -H "Authorization: Bearer $OBSIDIAN_API_KEY" \
  http://127.0.0.1:27123/vault/

# Expected: JSON array of files, e.g. ["00 - INBOX/", "10 - PROJECTS/", ...]
# If you see 401: check that $OBSIDIAN_API_KEY matches the key in Obsidian settings.
# If connection refused: Obsidian is not running.
```

Using OpenClaw:

```bash
# Check health via the bridge
python3 - <<'EOF'
import os, sys
sys.path.insert(0, 'openclaw_skills')
from obsidian_bridge import ObsidianBridge
result = ObsidianBridge().check_obsidian_health()
print(result)
EOF
```

Expected: `{'status': 'ok', 'url': 'http://127.0.0.1:27123', 'latency_ms': <N>}`

---

## Step 7: Re-run OpenClaw setup (optional)

```bash
OBSIDIAN_VAULT_PATH="$OBSIDIAN_VAULT_PATH" bash setup.sh
```

This runs all 7 setup steps including the vault bootstrap and Obsidian health check.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Connection refused` on `curl` | Obsidian is not running | Launch Obsidian first |
| `401 Unauthorized` | Wrong or missing API key | Check `$OBSIDIAN_API_KEY` vs plugin settings |
| `ValueError: OBSIDIAN_API_KEY is required` | Env var not set | Run `export OBSIDIAN_API_KEY=...` |
| `ValueError: base_url must resolve to loopback` | `OBSIDIAN_BASE_URL` set to a remote host | Use `http://127.0.0.1:27123` only |
| Port already in use | Another service on 27123 | Change port in Local REST API settings and update `OBSIDIAN_BASE_URL` |
| Plugin not found | Community plugins not enabled | Settings → Community plugins → Disable Safe Mode |

---

## Optional Hardening: HTTPS on Port 27124

The Local REST API plugin also supports HTTPS on port 27124 using a self-signed certificate. This eliminates the risk of a local process reading the API key from unencrypted HTTP traffic on the loopback interface.

To enable:
1. In Local REST API plugin settings, enable **"Enable HTTPS"**
2. Download the self-signed certificate CA from the plugin settings
3. Update `OBSIDIAN_BASE_URL`:
   ```bash
   export OBSIDIAN_BASE_URL="https://127.0.0.1:27124"
   ```
4. Add the CA cert path to your `ObsidianBridge` (custom ssl context in `urllib.request`) — document as a future Sprint 8 hardening task.

---

## Environment Variable Reference

| Variable | Default | Required | Description |
|---|---|---|---|
| `OBSIDIAN_API_KEY` | — | **Yes** | Bearer token from Local REST API plugin settings |
| `OBSIDIAN_BASE_URL` | `http://127.0.0.1:27123` | No | Must be loopback — enforced at `ObsidianBridge()` construction |
| `OBSIDIAN_VAULT_PATH` | — | No (for bootstrap only) | Absolute path to vault root directory |
| `VAULT_INGEST_MAX_BYTES` | `50000` | No | Max note size for vector ingestion (default: 50KB) |
