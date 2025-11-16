# Architecture Overview

## Repository Structure

This is a **monorepo** containing two independently deployable components:

```
dlzoom/
├── src/dlzoom/           # Python CLI (primary deliverable)
│   ├── cli.py            # Command-line interface
│   ├── zoom_client.py    # S2S OAuth client
│   ├── zoom_user_client.py  # User OAuth client
│   ├── downloader.py     # Recording download logic
│   └── ...
├── tests/                # Python test suite
├── zoom-broker/          # Cloudflare Worker (OAuth broker)
│   ├── src/index.js      # Worker entrypoint
│   └── test/
├── docs/                 # Documentation
│   ├── architecture.md   # This file
│   └── zoom-app/         # Zoom App marketplace docs
└── pyproject.toml        # Python package configuration
```

**Design Rationale:**
- Python CLI at repo root (primary deliverable, follows Python packaging conventions)
- `zoom-broker/` as self-contained subdirectory (optional component, independent deployment)
- Shared documentation in `docs/`
- This structure balances simplicity with clear separation of concerns

## Components

### 1. dlzoom CLI (Python)
**Purpose:** Command-line tool to browse, list, and download Zoom cloud recordings.

**Key Features:**
- Browse recordings by date (`dlzoom recordings`)
- Download recordings by meeting ID (`dlzoom download`)
- Two authentication modes: User OAuth (default) or S2S OAuth
- Audio extraction from video files
- JSON output for automation

**Source:** `src/dlzoom/`

### 2. OAuth Broker (Cloudflare Worker)
**Purpose:** Secure OAuth code exchange and token refresh service.

**Why Separate?**
- OAuth requires a redirect URL, which CLIs cannot provide directly
- Cloudflare Workers provide free, globally distributed HTTPS endpoints
- Keeps OAuth client secrets out of the CLI binary

**Source:** `zoom-broker/`

## Authentication Flow

### User OAuth Flow (ASCII)
```
┌─────────────┐      ┌────────────────┐      ┌─────────┐
│   dlzoom    │──1──>│  OAuth Broker  │──2──>│  Zoom   │
│  (Python)   │<─3───│  (Cloudflare)  │<─4───│  API    │
└─────────────┘      └────────────────┘      └─────────┘
```

1. User runs `dlzoom login`
2. CLI opens browser to Zoom OAuth consent page
3. User authorizes application
4. Zoom redirects to broker with authorization code
5. Broker exchanges code for access/refresh tokens
6. CLI polls broker and retrieves tokens
7. CLI stores tokens locally in the platform config dir (e.g., macOS `~/Library/Application Support/dlzoom/tokens.json`, Linux `~/.config/dlzoom/tokens.json`, Windows `%APPDATA%\dlzoom\tokens.json`)
8. CLI uses tokens to call Zoom APIs

### Server-to-Server (S2S) OAuth Flow
```
┌─────────────┐                    ┌─────────┐
│   dlzoom    │───────────────────>│  Zoom   │
│  (Python)   │<───────────────────│  API    │
└─────────────┘                    └─────────┘
```

Direct authentication using account credentials (no broker needed).

## Deployment Models

### CLI Installation
- PyPI: `pip install dlzoom`
- uvx: `uvx dlzoom` (instant run, no install)
- Docker: `docker run yanivgolan1/dlzoom`
- Source: `git clone` + `pip install -e .`

### OAuth Broker
- **Hosted (available, Marketplace review pending):** The CLI already defaults to the shared broker at `https://zoom-broker.dlzoom.workers.dev`. Until Zoom finishes Marketplace approval you still create your own user-managed OAuth app (or point the CLI at your self-hosted worker) before running `dlzoom login`.
- **Self-hosted (available now):** Deploy `zoom-broker/` to your Cloudflare account
  ```bash
  cd zoom-broker
  wrangler deploy
  ```
  Then configure CLI: `export DLZOOM_AUTH_URL=https://your-worker.workers.dev`

  **CI/CD:** The broker supports automatic deployments via Cloudflare's Git integration:
  - Push to `main` → automatic production deployment
  - Pull requests → automatic preview URL generation
  - See `zoom-broker/DEPLOYMENT.md` for complete setup guide

## Security Architecture

### Credential Storage
- **User OAuth tokens:** Stored in the platform-specific config directory (macOS `~/Library/Application Support/dlzoom/tokens.json`, Linux `~/.config/dlzoom/tokens.json`, Windows `%APPDATA%\dlzoom\tokens.json`) with mode 0600. Override via `DLZOOM_TOKENS_PATH`.
- **S2S credentials:** Environment variables or config file (never logged)

### Token Refresh
- Broker handles token refresh transparently
- CLI automatically refreshes expired tokens before API calls
- Refresh tokens stored securely, never exposed in logs

### Broker Isolation
- Broker has no persistent storage (stateless)
- Tokens exchanged in-memory only
- Each user's tokens isolated by unique session ID

## Data Flow

### Recordings Download
1. User: `dlzoom download 123456789`
2. CLI authenticates with Zoom API
3. CLI fetches recording metadata
4. CLI downloads video/audio files
5. CLI extracts audio (if needed) using ffmpeg
6. CLI saves files + metadata locally

### Recordings Browse
1. User: `dlzoom recordings --range last-7-days`
2. CLI authenticates with Zoom API
3. CLI paginates through recordings API
4. CLI filters by date/topic (if specified)
5. CLI displays results (table or JSON)

### Recording Fetching Modes

`dlzoom recordings` and `dlzoom download --from/--to` operate in two scopes depending on the token type:

- **Account scope (default for S2S OAuth)**
  - Endpoint: `GET /v2/accounts/me/recordings`
  - Requires both `account:read:admin` and `cloud_recording:read:list_account_recordings:{admin|master}` scopes.
  - Date ranges are chunked into calendar months to satisfy Zoom's 30-day limit. Pagination is handled per month window.
  - JSON output includes `scope="account"` and the `account_id` so downstream automation knows how the data was fetched.

- **User scope (user OAuth or S2S fallback per user)**
  - Endpoint: `GET /v2/users/{userId}/recordings`
  - User OAuth can use `user_id="me"`. S2S callers must pass an explicit email/UUID via `--user-id` or configure `ZOOM_S2S_DEFAULT_USER`.

During the initial rollout we briefly exposed a `DLZOOM_LEGACY_S2S_MODE` escape hatch for S2S tenants that had not added the granular scopes yet. That compatibility switch has been removed—S2S deployments must either grant the account-level scopes or operate in `--scope user` with an explicit email/UUID.

## Technology Stack

| Component | Languages/Frameworks | Key Dependencies |
|-----------|---------------------|------------------|
| CLI | Python 3.11+ | `rich-click`, `requests`, `rich`, `platformdirs` |
| OAuth Broker | JavaScript (Node 20) | Cloudflare Workers API |
| Testing | Python, JavaScript | `pytest`, `vitest` |
| CI/CD | GitHub Actions | Ruff, mypy, black, Trivy, Gitleaks |

## Development Workflow

### Local Development
```bash
# Python CLI
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest

# JavaScript Broker
cd zoom-broker
npm install
npm test
npm run dev  # Local Cloudflare Worker
```

### CI/CD Pipeline
- **Python CI:** Linting (ruff, mypy), formatting (black), tests (pytest), security (Trivy)
- **JS CI:** Tests (vitest), security (Trivy for Node dependencies)
- **Secret Scanning:** Gitleaks
- **Release:** Automated PyPI publish, Docker builds, SBOM generation

## Self‑Hosting

The CLI will default to a hosted broker when it is available. Until then, you can:

1. Deploy `zoom-broker/` to their own Cloudflare account
2. Point the CLI to their broker URL:
   ```bash
   export DLZOOM_AUTH_URL=https://your-worker.workers.dev
   ```

This provides full control over the OAuth flow and ensures no third-party handles tokens.
