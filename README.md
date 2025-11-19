# dlzoom

[![CI](https://github.com/yaniv-golan/dlzoom/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/yaniv-golan/dlzoom/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/dlzoom)](https://pypi.org/project/dlzoom/)
[![Python versions](https://img.shields.io/pypi/pyversions/dlzoom)](https://pypi.org/project/dlzoom/)
[![License: MIT](https://img.shields.io/github/license/yaniv-golan/dlzoom)](LICENSE)
[![PyPI downloads](https://img.shields.io/pypi/dm/dlzoom)](https://pypi.org/project/dlzoom/)
[![Docker pulls](https://img.shields.io/docker/pulls/yanivgolan1/dlzoom)](https://hub.docker.com/r/yanivgolan1/dlzoom)
[![Zoom Marketplace](https://img.shields.io/badge/Zoom_Marketplace-Approval_Pending-yellow?logo=zoom&logoColor=white)](#authentication)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://pre-commit.com/)

> **Marketplace status:** The dlzoom Zoom app is submitted and awaiting Marketplace approval. The hosted broker at `https://zoom-broker.dlzoom.workers.dev` is live today, but you must create your own Zoom OAuth app (or self-host the worker) until Zoom publishes the listing. Server-to-Server OAuth continues to work for admins/automation.

<p align="center">
  <img src="https://raw.githubusercontent.com/yaniv-golan/dlzoom/main/assets/banner.png"
       alt="dlzoom — Download Zoom cloud recordings from the command line" />
</p>

Download Zoom cloud recordings from the command line.

Built for power users and teams running custom transcription pipelines: get clean audio (M4A) and a diarization‑first minimal STJ file you can feed into your ASR of choice (e.g., Whisper) to add richer context than Zoom’s default transcription and support languages Zoom doesn’t handle well.

## Why dlzoom

- 🎯 Purpose-built for transcription workflows: audio (M4A) + minimal STJ diarization JSON by default
- 🔄 Resilient downloads: resume partials, retries with backoff, dedupe by size
- 🧰 Automation-first: JSON output, batch by date range, structured logs, file/folder templates
- 🔐 Secure by design: OAuth via broker (no client secret in CLI), S2S for admins, no secrets in logs
- 🐳 Docker image includes ffmpeg; no local deps required
- 🧪 Comprehensive tests and CI

> Authentication note
> Hosted user sign‑in (`dlzoom login`) already uses the shared broker endpoint. Until Zoom finishes Marketplace review you still bring your own Zoom OAuth app (or self‑host) before running `dlzoom login`, or use Server‑to‑Server (S2S) OAuth.

## 60‑Second Quickstart

Requires Python 3.11+ and ffmpeg (Docker users: both included in the image).

```bash
# Install uv (if missing)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Authenticate once
uvx dlzoom login
# Or for S2S automation:
# ZOOM_ACCOUNT_ID=... ZOOM_CLIENT_ID=... ZOOM_CLIENT_SECRET=... uvx dlzoom whoami

# Try dlzoom instantly (no install) after auth is configured
uvx dlzoom download 123456789 --check-availability
```

Outputs include audio (M4A), transcript (VTT), chat (TXT), timeline (JSON), metadata JSON, and a minimal STJ diarization file (`<name>_speakers.stjson`) for your ASR pipeline.

## Pick Your Auth

- I'm downloading my own recordings → User OAuth
  - Run `dlzoom login` - uses our hosted OAuth broker by default (open source, auditable code in `zoom-broker/`)
  - Until Zoom publishes the Marketplace listing, create your own Zoom OAuth app (or self-host the broker) before logging in so the hosted flow can exchange tokens.
  - Or self-host: deploy the Cloudflare Worker in `zoom-broker/` and run `dlzoom login --auth-url <your-worker-url>`
- I'm an admin or running automation/CI → Server-to-Server (S2S) OAuth
  - Set `ZOOM_ACCOUNT_ID`, `ZOOM_CLIENT_ID`, `ZOOM_CLIENT_SECRET` and run `dlzoom`.
  - Scopes: add `account:read:admin` + `cloud_recording:read:list_account_recordings:{admin|master}` (or the `:master` variant) so account-wide recording fetches work.
  - Verify scopes any time with `dlzoom whoami --json`.

Links to both flows are in Authentication below.

## Transcription & AI Workflows

- Use your preferred ASR (e.g., Whisper, cloud STT) on the M4A file.
- dlzoom also emits a minimal STJ diarization file you can use to tag speakers or structure prompts.
- Works well when you need extra context beyond Zoom’s default transcript, or for languages/dialects Zoom struggles with.

Examples:

```bash
# Download and name outputs
dlzoom download 123456789 --output-name my_meeting

# Resulting files include (when available from Zoom):
#   my_meeting.m4a (or extracted from MP4 if audio-only not provided)
#   my_meeting_transcript.vtt
#   my_meeting_chat.txt
#   my_meeting_timeline.json  # only when Zoom provides timeline blobs
#   my_meeting_speakers.stjson  # generated when timelines exist
```

Tuning diarization output:

```bash
# Disable diarization JSON entirely
dlzoom download 123456789 --skip-speakers

# Handle multi-user timestamps and include unknown speakers
dlzoom download 123456789 --speakers-mode multiple --include-unknown

# Merge and minimum-segment tuning
dlzoom download 123456789 --stj-min-seg-sec 1.0 --stj-merge-gap-sec 1.5

# Env toggle to disable generation by default
export DLZOOM_SPEAKERS=0
```

STJ spec: https://github.com/yaniv-golan/STJ/blob/main/spec/latest/stj-specification.md
Every generated STJ file includes `metadata.source.extensions.zoom` and `metadata.extensions.dlzoom`
entries so you can trace the diarization back to the exact Zoom meeting (meeting/account IDs,
scope used, host details, CLI parameters, and a scrubbed summary of the downloaded recording
files).

Speaker IDs inside the STJ file are human-friendly slugs (e.g., `yaniv-golan`), while the raw Zoom participant/user IDs are preserved under `speakers[].extensions.zoom` for lossless correlation.

## Browse and Download

```bash
# Browse last 7 days
dlzoom recordings --range last-7-days

# Specific window
dlzoom recordings --from-date 2025-01-01 --to-date 2025-01-31

# Filter by topic
dlzoom recordings --range today --topic "standup"

# Inspect instances of a specific meeting (recurring/PMI)
dlzoom recordings --meeting-id 123456789

# Download (audio + transcript + chat + timeline)
dlzoom download 123456789

# Check availability without downloading
dlzoom download 123456789 --check-availability

# This exits non-zero if Zoom cannot find the recording or Zoom returns an error.

# Wait up to 60 minutes for processing
dlzoom download 123456789 --wait 60

# Custom naming and output directory
dlzoom download 123456789 --output-name "my_meeting" --output-dir ./recordings

# Batch download with explicit name reused per meeting
dlzoom download --from-date 2024-04-01 --to-date 2024-04-07 --output-name finance_sync

# Batch download without --output-name automatically appends UTC timestamps
# (e.g., 123456789_20240401-150000) to avoid overwriting recurring meetings.
dlzoom download --from-date 2024-04-01 --to-date 2024-04-07

# Dry run
dlzoom download 123456789 --dry-run

# Non-zero exit when meeting not found or batch fails
dlzoom download 123456789 --check-availability || echo "missing"

# Tip: meeting IDs with spaces pasted from Zoom are normalized automatically
dlzoom download "882 9060 9309"
```

Date-range downloads (`--from-date/--to-date`) reuse any explicit `--output-name` you provide; otherwise they append a UTC timestamp (or the recording UUID when no timestamp is available) to prevent recurring IDs from overwriting each other. Pair `--from-date/--to-date` with `--dry-run` to preview every meeting in the range without downloading files, `--wait 30` to keep polling for in-progress recordings before the downloads begin (the CLI exits instead of attempting a doomed download if the wait times out), `--log-file ~/dlzoom.jsonl` to capture structured results for every meeting, or `--check-availability` to scan the whole window without downloading anything. If any meeting in the batch fails, `dlzoom download --from ...` exits non-zero so CI/CD jobs can detect partial failures.

Batch by date window and automate:

```bash
#!/bin/bash
for id in 111111111 222222222 333333333; do
  dlzoom download "$id" --output-dir ./recordings
done
```

JSON output for pipelines:

```bash
dlzoom download 123456789 --json > recording.json
```

The JSON payload lists every downloaded artifact (audio/video/transcripts/chats/timelines/speaker STJ files) so automation can inspect all outputs.

## Recording Scope Modes

dlzoom needs to know *which* Zoom API surface to call when enumerating or batch-downloading recordings. Use the `--scope`/`--user-id` flags on `recordings` and `download` to control this.

### Account scope (default for S2S OAuth)

- Endpoint: `GET /v2/accounts/me/recordings`
- Required scopes: `account:read:admin` **and** `cloud_recording:read:list_account_recordings:{admin|master}` (granular scopes). Classic `recording:read:admin` alone is insufficient.
- Usage:
  ```bash
  # S2S with full account visibility
  dlzoom recordings --scope account --from-date 2025-02-01 --to-date 2025-02-15 --json
  dlzoom download --from-date 2025-02-01 --to-date 2025-02-05 --scope account
  ```
- Troubleshooting 403/4711 errors:
  1. Run `dlzoom whoami --json` to inspect the token's actual scopes.
  2. Add BOTH scopes above to your S2S app and ensure your admin role exposes granular recording scopes.
  3. Try the `:master` variant if your account uses a master/sub-account hierarchy.
  4. If Zoom still hides the granular scopes, create a **General** (Unlisted) app as a fallback.

### User scope (user OAuth, or S2S fallback per user)

- Endpoint: `GET /v2/users/{userId}/recordings`
- User OAuth: `user_id="me"` resolves automatically.
- S2S fallback: pass an explicit email/UUID via `--user-id` or set `ZOOM_S2S_DEFAULT_USER`.
  ```bash
  dlzoom recordings --scope user --user-id host@example.com --from-date 2025-02-01 --to-date 2025-02-05
  dlzoom download --from-date 2025-02-01 --to-date 2025-02-05 --scope user --user-id user@example.com
  ```

## Installation

Choose your preferred method.

### 🚀 Quick Try (uvx — instant, no install)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uvx dlzoom download 123456789 --check-availability
```

### 📦 PyPI (recommended for regular use)

```bash
pip install dlzoom

# or with uv (fast)
uv pip install dlzoom

# or install as a tool (isolated)
uv tool install dlzoom
```

### 🐳 Docker (zero dependencies)

```bash
# Includes Python + ffmpeg
docker run -it --rm \
  -v $(pwd)/recordings:/app/downloads \
  -e ZOOM_ACCOUNT_ID="your_account_id" \
  -e ZOOM_CLIENT_ID="your_client_id" \
  -e ZOOM_CLIENT_SECRET="your_secret" \
  yanivgolan1/dlzoom:latest \
  download 123456789

# Or GHCR
docker run -it --rm \
  -v $(pwd)/recordings:/app/downloads \
  -e ZOOM_ACCOUNT_ID="your_account_id" \
  -e ZOOM_CLIENT_ID="your_client_id" \
  -e ZOOM_CLIENT_SECRET="your_secret" \
  ghcr.io/yaniv-golan/dlzoom:latest \
  download 123456789
```

### 🔧 From source (development)

```bash
git clone https://github.com/yaniv-golan/dlzoom.git
cd dlzoom
python3.11 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

### Prerequisites (non‑Docker)

- Python 3.11+
- ffmpeg (for audio extraction from MP4)

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows (Chocolatey)
choco install ffmpeg

# Windows (winget)
winget install ffmpeg
```

## Authentication

### User OAuth (recommended for individuals)

By default, `dlzoom login` uses our hosted OAuth broker at `https://zoom-broker.dlzoom.workers.dev`:

```bash
dlzoom login
```

**About the hosted broker:**
- **Open source**: All code is in `zoom-broker/` and auditable
- **Privacy**: Only stores session data temporarily (max 10 minutes), does not log or persist tokens
- **Generic**: Works with any Zoom OAuth app (you create your own app in Zoom Marketplace)
- **Secure**: Runs on Cloudflare Workers with automatic HTTPS

**Self-hosting (optional):**

If you prefer to run your own broker:

```bash
cd zoom-broker
npx wrangler secret put ZOOM_CLIENT_ID
npx wrangler secret put ZOOM_CLIENT_SECRET
npx wrangler secret put ALLOWED_ORIGIN
npx wrangler kv namespace create AUTH
npx wrangler deploy

# Use your broker
dlzoom login --auth-url https://<your-worker>.workers.dev
# Or set permanently: export DLZOOM_AUTH_URL=https://<your-worker>.workers.dev
```

The Worker supports automatic CI/CD via Cloudflare's Git integration (pushes to `main` auto-deploy, PRs get preview URLs). See `zoom-broker/DEPLOYMENT.md` for setup details.

### Server‑to‑Server (S2S) OAuth (admins/automation)

#### Option 1: User config file (recommended for humans)

dlzoom now auto-loads S2S credentials from your platform config directory, so S2S works from any folder (just like OAuth tokens). Create **one** config file and be done:

| Platform | Config directory | Example path |
| --- | --- | --- |
| Linux / WSL / other Unix | `~/.config/dlzoom/` | `~/.config/dlzoom/config.json` |
| macOS | `~/Library/Application Support/dlzoom/` | `~/Library/Application Support/dlzoom/config.json` |
| Windows | `%APPDATA%\dlzoom\` | `%APPDATA%\dlzoom\config.json` |

The CLI looks for `config.json`, `config.yaml`, or `config.yml` (in that order). Example JSON:

```json
{
  "zoom_account_id": "your_account_id",
  "zoom_client_id": "your_client_id",
  "zoom_client_secret": "your_client_secret",
  "zoom_s2s_default_user": "host@example.com"  // optional
}
```

Example YAML:

```yaml
zoom_account_id: your_account_id
zoom_client_id: your_client_id
zoom_client_secret: your_client_secret
```

Tips:
- Create the directory if it doesn’t exist and set restrictive permissions (`chmod 600` on macOS/Linux).
- Use JSON/YAML interchangeably—fields match their environment variable counterparts.
- Add optional defaults like `log_level`, `output_dir`, or `zoom_s2s_default_user`.

#### Option 2: Environment variables (automation / CI)

```bash
export ZOOM_ACCOUNT_ID="your_account_id"
export ZOOM_CLIENT_ID="your_client_id"
export ZOOM_CLIENT_SECRET="your_client_secret"
```

This is ideal for CI/CD. Env vars override the user config file (unless you pass an explicit `--config` path).

#### Option 3: Project overrides (.env or `--config`)

- dlzoom automatically loads the first `.env` file it finds when walking up from the current directory (without clobbering existing env vars). Set `DLZOOM_NO_DOTENV=1` to skip this behavior.
- For multiple Zoom accounts, point commands at explicit files: `dlzoom download --config ./account-b.yaml 123456789`
- Priority (highest → lowest): explicit `--config`, environment variables, user config file, project `.env`, defaults.

Optional scopes for User OAuth (improve fidelity):

- Required: `cloud_recording:read:list_user_recordings`, `cloud_recording:read:list_recording_files`
- Optional: `meeting:read:meeting` (better recurrence detection), `user:read:user` (enables `whoami` details)

## File Naming and Templates

Use `--filename-template` and `--folder-template` to structure outputs.

Variables:

- `{topic}`, `{meeting_id}`, `{host_email}`
- `{start_time:%Y%m%d}` (strftime format), `{duration}`

Examples:

```bash
dlzoom download 123456789 \
  --filename-template "{start_time:%Y%m%d}_{topic}"

dlzoom download 123456789 \
  --folder-template "{start_time:%Y}/{start_time:%m}"

dlzoom download 123456789 \
  --filename-template "{host_email}_{topic}_{start_time:%Y%m%d}"
```

## Automation (CI/CD)

Example GitHub Actions job (S2S):

```yaml
name: archive-zoom
on:
  schedule: [{ cron: '0 3 * * *' }]
  workflow_dispatch: {}
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv tool install dlzoom
      - env:
          ZOOM_ACCOUNT_ID: ${{ secrets.ZOOM_ACCOUNT_ID }}
          ZOOM_CLIENT_ID: ${{ secrets.ZOOM_CLIENT_ID }}
          ZOOM_CLIENT_SECRET: ${{ secrets.ZOOM_CLIENT_SECRET }}
        run: |
          mkdir -p recordings
          dlzoom recordings --range last-7-days -j > list.json
          dlzoom download 123456789 --output-dir recordings --json > recording.json
```

## Full CLI Reference

<details>
<summary>dlzoom download — options</summary>

```
dlzoom download [OPTIONS] MEETING_ID

Options:
  --output-dir, -o PATH          Output directory (default: current directory)
  --output-name, -n TEXT         Base filename (default: meeting_id)
  --verbose, -v                  Show detailed operation information
  --debug, -d                    Show full API responses and trace
  --json, -j                     JSON output mode (machine-readable)
  --check-availability, -c       Check if recording is ready
  --recording-id TEXT            Select specific recording by UUID
  --wait MINUTES                 Wait for recording processing (timeout)
  --skip-transcript              Skip transcript download
  --skip-chat                    Skip chat log download
  --skip-timeline                Skip timeline download
  --skip-speakers                Do not generate minimal STJ speakers file (default: generate)
  --speakers-mode [first|multiple]
                                 When multiple users are listed for a timestamp (default: first)
  --stj-min-seg-sec FLOAT        Drop segments shorter than this duration (seconds) [default: 1.0]
  --stj-merge-gap-sec FLOAT      Merge adjacent same-speaker segments within this gap (seconds) [default: 1.5]
  --include-unknown              Include segments with unknown speaker (otherwise drop)
  --dry-run                      Show what would be downloaded
  --log-file PATH                Write structured log (JSONL format)
  --config PATH                  Path to config file (JSON/YAML)
  --filename-template TEXT       Custom filename template
  --folder-template TEXT         Custom folder structure template
  --help                         Show this message and exit
  --version                      Show version and exit
```

</details>

<details>
<summary>dlzoom recordings — options</summary>

```
dlzoom recordings [OPTIONS]

User-wide mode (default):
  --from-date TEXT               Start date (YYYY-MM-DD)
  --to-date TEXT                 End date (YYYY-MM-DD)
  --range [today|yesterday|last-7-days|last-30-days]
                                 Quick date range (exclusive with --from-date/--to-date)
  --topic TEXT                   Substring filter on topic
  --limit INTEGER                Max results (0 = unlimited) [default: 1000]
  --page-size INTEGER            [Advanced] Results per API request (Zoom max 300) [default: 300]

Meeting-scoped mode (replaces `download --list`):
  --meeting-id TEXT              Exact meeting ID or UUID to list instances

Common options:
  --json, -j                     JSON output mode (silent)
  --verbose, -v                  Verbose human output
  --debug, -d                    Debug logging
  --config PATH                  Path to config file
  --help                         Show this message and exit
```

</details>

## Troubleshooting

Common errors and fixes:

- Authentication failed → Ensure your platform config file (`~/.config/dlzoom/config.json`, `~/Library/Application Support/dlzoom/config.json`, or `%APPDATA%\dlzoom\config.json`) or env vars contain `ZOOM_ACCOUNT_ID`, `ZOOM_CLIENT_ID`, `ZOOM_CLIENT_SECRET`.
- Invalid meeting ID → Paste only the ID/UUID. Spaces are fine; they’re removed automatically.
- ffmpeg not found → Install ffmpeg (or use Docker image). Needed when audio-only is unavailable and dlzoom extracts audio from MP4.

## Security & Privacy

- No secrets in logs; rigorous input validation; atomic file writes.
- User OAuth tokens stored under your OS config directory (0600): macOS `~/Library/Application Support/dlzoom/tokens.json`, Linux `~/.config/dlzoom/tokens.json`, Windows `%APPDATA%\dlzoom\tokens.json`. Override with `DLZOOM_TOKENS_PATH` if needed. S2S credentials via env or config file.
- OAuth broker: restrict CORS with `ALLOWED_ORIGIN` in production. See `zoom-broker/README.md`.
- If your working directory is cloud‑synced (iCloud/Dropbox/etc.), consider env vars instead of a `.env` file or place config outside the synced folder.

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md). Please also review our [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

Quick start for contributors:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

## Version & Roadmap

- Releases: see [CHANGELOG.md](CHANGELOG.md)
- Roadmap highlights:
  - 🎨 More output formats (TSV)
  - 🔐 Token encryption via system keychain
  - 📱 Multiple profiles support
  - 📦 Optional SBOM generation in CI

## License

MIT — see [LICENSE](LICENSE).

## Support

- 🐛 [Report bugs](https://github.com/yaniv-golan/dlzoom/issues)
- 💡 [Request features](https://github.com/yaniv-golan/dlzoom/issues)
- 💬 [GitHub Discussions](https://github.com/yaniv-golan/dlzoom/discussions)
- 📖 Documentation / Architecture: see `docs/`

## Credits

Built with:

- Click / Rich‑Click — CLI framework
- Rich — terminal output
- Requests — HTTP client
- pytest — testing framework
