# dlzoom

[![CI](https://github.com/yaniv-golan/dlzoom/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/yaniv-golan/dlzoom/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/dlzoom)](https://pypi.org/project/dlzoom/)
[![Python versions](https://img.shields.io/pypi/pyversions/dlzoom)](https://pypi.org/project/dlzoom/)
[![License: MIT](https://img.shields.io/github/license/yaniv-golan/dlzoom)](LICENSE)
[![PyPI downloads](https://img.shields.io/pypi/dm/dlzoom)](https://pypi.org/project/dlzoom/)
[![Docker pulls](https://img.shields.io/docker/pulls/yanivgolan1/dlzoom)](https://hub.docker.com/r/yanivgolan1/dlzoom)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://pre-commit.com/)

**Download Zoom cloud recordings from the command line.**

Simple CLI tool to download audio recordings and metadata from Zoom meetings using meeting IDs.

## Features

- 🎵 Download audio recordings (M4A format)
- 📝 Download transcripts, chat logs, and timelines
- 🔄 Automatic audio extraction from video files (MP4 → M4A)
- 🔐 Authentication: Hosted user OAuth (default) or Server-to-Server OAuth
- 📋 JSON output for automation
- 🎯 Support for recurring meetings and PMI
- ⏳ Wait for recording processing with `--wait`
- 🔍 Check recording availability before downloading
- 🛡️ Secure (credentials never exposed in logs)
- 🔁 Automatic retry with exponential backoff
- 💪 Production-ready with 119 tests

## Installation

Choose your preferred method:

### 🚀 Quick Try (uvx - Instant Run, No Install)

**Fastest way to try dlzoom** - requires Python 3.11+ and ffmpeg:

```bash
# Install uv first (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Run dlzoom instantly (no installation needed!)
uvx dlzoom download 123456789 --check-availability
```

### 📦 PyPI Install (Recommended for Regular Use)

```bash
# Install with pip
pip install dlzoom

# Or with uv (10-100x faster)
uv pip install dlzoom

# Or with uv tool (isolated installation)
uv tool install dlzoom
```

**Note:** Requires Python 3.11+ and ffmpeg (see below).

### 🐳 Docker (Zero Dependencies - Everything Included!)

**Best for:** Production, CI/CD, no local dependencies

```bash
# Run with Docker (includes Python + ffmpeg)
docker run -it --rm \
  -v $(pwd)/recordings:/app/downloads \
  -e ZOOM_ACCOUNT_ID="your_account_id" \
  -e ZOOM_CLIENT_ID="your_client_id" \
  -e ZOOM_CLIENT_SECRET="your_secret" \
  yanivgolan1/dlzoom:latest \
  download 123456789
```

**Or use GitHub Container Registry:**

```bash
docker run -it --rm \
  -v $(pwd)/recordings:/app/downloads \
  -e ZOOM_ACCOUNT_ID="your_account_id" \
  -e ZOOM_CLIENT_ID="your_client_id" \
  -e ZOOM_CLIENT_SECRET="your_secret" \
  ghcr.io/yaniv-golan/dlzoom:latest \
  download 123456789
```

### 🔧 From Source (Development)

```bash
# Clone the repository
git clone https://github.com/yaniv-golan/dlzoom.git
cd dlzoom

# Create virtual environment (recommended)
python3.11 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install
pip install -e .
```

### Prerequisites (for non-Docker installations)

- **Python 3.11+** (required)
- **ffmpeg** (required for audio extraction from video files)

**Install ffmpeg:**

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows (via Chocolatey)
choco install ffmpeg

# Windows (via winget)
winget install ffmpeg
```

> **Docker users:** No need to install Python or ffmpeg - everything is included!

## Quick Start

### 1. Sign In (Recommended)

Use our hosted authentication service to connect your Zoom account (no secrets required):

```bash
dlzoom login
```

This opens your browser to approve access and stores a short‑lived token locally (refreshed automatically).

Alternatively, organizational users can configure Server‑to‑Server (S2S) OAuth using environment variables or a config file.

Host your own broker (optional)
- The CLI uses a hosted sign‑in broker by default. To self‑host, deploy the worker under `zoom-broker/` (see that README), then point dlzoom to your URL via the `--auth-url` option or environment variable when logging in.

### 2. Configure S2S Credentials (Optional)

Create a `.env` file in your working directory:

```bash
ZOOM_ACCOUNT_ID=your_account_id_here
ZOOM_CLIENT_ID=your_client_id_here
ZOOM_CLIENT_SECRET=your_client_secret_here
```

> **⚠️ Security Warning**: If your project directory is in a cloud-synced folder (iCloud, Dropbox, Google Drive, etc.), your `.env` file containing credentials may be uploaded to cloud storage. Consider using environment variables instead, moving the project to a non-synced directory, or using a config file outside the project directory with `--config`.

Or set environment variables:

```bash
export ZOOM_ACCOUNT_ID="your_account_id"
export ZOOM_CLIENT_ID="your_client_id"
export ZOOM_CLIENT_SECRET="your_client_secret"
```

Or use a config file:

```bash
# config.yaml
zoom_account_id: "your_account_id"
zoom_client_id: "your_client_id"
zoom_client_secret: "your_client_secret"
log_level: "INFO"
```

#### Automatic .env loading and opt-out

- dlzoom automatically loads environment variables from a `.env` file at startup. It searches from your current working directory upwards (like `git`), and loads the first `.env` it finds.
- Loading uses `override=False`, so variables already present in your shell/environment take precedence over values in `.env`.
- To disable auto-loading (e.g., for CI or scripts that must be fully deterministic), set:

```bash
export DLZOOM_NO_DOTENV=1
```

Tips and caveats:
- Prefer explicit environment variables for automation where you don’t want a parent directory `.env` to influence behavior.
- If your project lives in a cloud‑synced folder (Dropbox, iCloud, Google Drive), treat `.env` as sensitive; consider using environment variables or a config file stored outside that folder.

### 3. Browse and Download

Browse your recordings by date:

```bash
# Last 7 days
dlzoom recordings --range last-7-days

# Specific window
dlzoom recordings --from-date 2025-01-01 --to-date 2025-01-31

# Filter by topic (user-wide mode)
dlzoom recordings --range today --topic "standup"
```

Inspect instances for a specific meeting (replaces the old `download --list`):

```bash
dlzoom recordings --meeting-id 123456789
```

Download a recording (audio + transcript + chat + timeline):

```bash
dlzoom download 123456789
```

Tip: You can paste meeting IDs directly from Zoom. Spaces are removed automatically:

```bash
dlzoom download "882 9060 9309"  # Works! Spaces are removed automatically
dlzoom download 88290609309      # Also works
```

## Usage

### Basic Commands

**Check if recording is available:**

```bash
dlzoom download 123456789 --check-availability
```

Use `dlzoom recordings --meeting-id 123456789` instead of the removed `download --list`.

**Download recording (audio + transcript + chat + timeline):**

```bash
dlzoom download 123456789
```

**Download with custom output name:**

```bash
dlzoom download 123456789 --output-name "my_meeting"
```

**Download to specific directory:**

```bash
dlzoom download 123456789 --output-dir ~/Downloads/zoom
```

**Wait for recording to finish processing:**

```bash
dlzoom download 123456789 --wait 30
```

### Advanced Options

**Use config file:**

```bash
dlzoom download 123456789 --config config.yaml
```

**Verbose output (see detailed logs):**

```bash
dlzoom download 123456789 --verbose
```

**Debug mode (full API responses):**

```bash
dlzoom download 123456789 --debug
```

**JSON output (for automation):**

```bash
dlzoom download 123456789 --json
```

### Other Commands

- Show current account:

```bash
dlzoom whoami
```

- Sign out and remove local tokens:

```bash
dlzoom logout
```

### Optional Permissions (Advanced)

dlzoom works with minimal permissions by default. You can optionally add these to improve fidelity:

**Required Scopes (Minimum):**
- `cloud_recording:read:list_user_recordings` - List your cloud recordings
- `cloud_recording:read:list_recording_files` - Access recording file details for download

**Optional Scopes (Enhanced Features):**
- `meeting:read:meeting` - Definitively mark recurring meetings by checking meeting type; without it, recurrence is inferred only within the fetched date range
- `user:read:user` - Show your name/email in `whoami` when using user tokens

All scopes use Zoom's granular scope naming (user-managed OAuth). Behavior degrades gracefully if optional scopes are not enabled.
```

**Dry run (see what would be downloaded):**

```bash
dlzoom download 123456789 --dry-run
```

**Custom filename template:**

```bash
dlzoom download 123456789\
  --filename-template "{topic}_{start_time:%Y%m%d}"
```

**Custom folder structure:**

```bash
dlzoom download 123456789\
  --folder-template "{start_time:%Y}/{start_time:%m}"
```

**Select specific recording instance (for recurring meetings):**

```bash
dlzoom download 123456789 --recording-id "abc123def456"
```

### Skip Downloads

**Skip transcript download:**

```bash
dlzoom download 123456789 --skip-transcript
```

**Skip chat log download:**

```bash
dlzoom download 123456789 --skip-chat
```

**Skip timeline download:**

```bash
dlzoom download 123456789 --skip-timeline
```

## Download Options

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
  --dry-run                      Show what would be downloaded
  --log-file PATH                Write structured log (JSONL format)
  --config PATH                  Path to config file (JSON/YAML)
  --filename-template TEXT       Custom filename template
  --folder-template TEXT         Custom folder structure template
  --help                         Show this message and exit
  --version                      Show version and exit
```

## Recordings Options

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

## Template Variables

Use in `--filename-template` and `--folder-template`:

- `{topic}` - Meeting topic
- `{meeting_id}` - Meeting ID
- `{host_email}` - Host email address
- `{start_time:%Y%m%d}` - Start time (format with strftime codes)
- `{duration}` - Meeting duration

**Examples:**

```bash
# Date-based filename
--filename-template "{start_time:%Y%m%d}_{topic}"

# Organized by date
--folder-template "{start_time:%Y}/{start_time:%m}"

# Include host
--filename-template "{host_email}_{topic}_{start_time:%Y%m%d}"
```

## Common Use Cases

### Download Latest Recording from Recurring Meeting

```bash
dlzoom download 123456789 --verbose
```

### Download Specific Instance

```bash
# List all instances first (meeting-scoped view)
dlzoom recordings --meeting-id 123456789

# Download a specific instance by UUID
dlzoom download 123456789 --recording-id "abc123def456"
```

### Automated Pipeline (JSON Output)

```bash
dlzoom download 123456789 --json > recording.json
```

### Batch Processing

```bash
#!/bin/bash
for meeting_id in 111111111 222222222 333333333; do
    dlzoom download $meeting_id --output-dir ./recordings
done
```

### Wait for Recording to Process

```bash
# Wait up to 60 minutes for processing
dlzoom download 123456789 --wait 60
```

## Troubleshooting

### Authentication Failed

```
Error: Authentication failed
```

**Solution:** Check your credentials in `.env` or environment variables.

### Meeting ID Format Invalid

```
Error: Invalid meeting ID format
```

**Solution:** Meeting IDs must be:

- 9-12 digit numbers (e.g., `123456789`)
- Or UUID format (e.g., `abc123XYZ+/=_-`)

### Recording Not Found

```
Error: Recording not found
```

**Possible causes:**

- Meeting wasn't recorded
- Recording not yet processed (use `--wait`)
- No permission to access recording
- Wrong meeting ID

**Check availability first:**

```bash
dlzoom download 123456789 --check-availability
```

### ffmpeg Not Found

```
Error: ffmpeg not found in PATH
```

**Solution:** Install ffmpeg:

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

### Rate Limit Exceeded

```
Error: Rate limit exceeded
```

**Solution:** Wait a few minutes and try again. The tool automatically retries with exponential backoff.

### Insufficient Disk Space

```
Error: Insufficient disk space
```

**Solution:** Free up space or use `--output-dir` to save to a different location.

## Configuration Files

### JSON Config

```json
{
  "zoom_account_id": "your_account_id",
  "zoom_client_id": "your_client_id",
  "zoom_client_secret": "your_client_secret",
  "output_dir": "./recordings",
  "log_level": "INFO"
}
```

### YAML Config

```yaml
zoom_account_id: "your_account_id"
zoom_client_id: "your_client_id"
zoom_client_secret: "your_client_secret"
output_dir: "./recordings"
log_level: "INFO"
```

Use with:

```bash
dlzoom download 123456789 --config config.yaml
```

## Output Files

**Audio file:**

- Format: M4A (AAC audio)
- Naming: `{meeting_id}.m4a` or custom via `--output-name`

**Transcript file:**

- Format: VTT (WebVTT)
- Naming: `{meeting_id}_transcript.vtt`

**Chat log:**

- Format: TXT
- Naming: `{meeting_id}_chat.txt`

**Timeline:**

- Format: JSON
- Naming: `{meeting_id}_timeline.json`
- Contains: Meeting events (joins, leaves, screen shares, etc.)

**Metadata:**

- Format: JSON
- Naming: `{meeting_id}_metadata.json`
- Contains: Meeting info, participants, recording details

## Requirements

- Python 3.11 or higher
- ffmpeg (for audio extraction)
- Zoom account (User OAuth via `dlzoom login`) or S2S OAuth app (optional)

Security note (tokens): On Windows, file permission enforcement for `tokens.json` is best‑effort. Treat your token file as sensitive and ensure your user profile is protected.

## Broker Origin Restriction (Optional)

For tighter security on the hosted auth service, you can restrict which origin is allowed to call the token endpoints:

- Set the `ALLOWED_ORIGIN` environment variable on your Cloudflare Worker (e.g., your CLI’s origin or a specific domain). When set, the broker sends `Access-Control-Allow-Origin: <value>` and `Vary: Origin` instead of `*`.
- See `zoom-broker/README.md` for details. If you don’t set it, the broker defaults to `*` — acceptable for CLI usage but less restrictive.

## Development

```bash
# Clone repository
git clone <repo-url>
cd dlzoom

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows

# Install in development mode
pip install -e .

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src/dlzoom --cov-report=term-missing
```

## Version

See [CHANGELOG.md](CHANGELOG.md) for detailed release notes. Current version: 0.2.0.

## Roadmap

Planned for future releases:

- 🎨 More output formats (TSV)
- 🔐 Token encryption via system keychain
- 📱 Multiple profiles support
- 📦 Optional SBOM generation in CI

## Known Limitations

### Feature Limitations

- Audio quality parameter not exposed via CLI (internal only)

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

We welcome contributions! Here's how you can help:

### Quick Start for Contributors

1. **Fork and clone** the repository
2. **Set up development environment:**

   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

3. **Run tests:**

   ```bash
   pytest tests/ -v
   ```

4. **Make your changes** and ensure tests pass
5. **Submit a pull request**

### Guidelines

- Follow [Conventional Commits](https://www.conventionalcommits.org/) for commit messages
- Add tests for new features
- Update documentation as needed
- Ensure all CI checks pass

### Commit Message Format

```
<type>(<scope>): <subject>

Examples:
feat(cli): add support for CSV export
fix(auth): handle expired OAuth tokens
docs: update installation instructions
```

**Types:**

- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation
- `test` - Tests
- `refactor` - Code refactoring
- `chore` - Maintenance

For detailed guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

Code of Conduct
- See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Security

Security is important to us. If you discover a security vulnerability:

- **Do not** open a public issue
- **Email** [yaniv@golan.name](mailto:yaniv@golan.name) with details
- See [SECURITY.md](SECURITY.md) for our security policy

### Security Features

- ✅ Credentials never logged or exposed
- ✅ Input validation (prevents injection attacks)
- ✅ Atomic file operations
- ✅ Automatic security scanning (Trivy)
- ✅ Docker images run as non-root user

## Support

For issues and questions:

- 🐛 [Report bugs](https://github.com/yaniv-golan/dlzoom/issues)
- 💡 [Request features](https://github.com/yaniv-golan/dlzoom/issues)
- 💬 [GitHub Discussions](https://github.com/yaniv-golan/dlzoom/discussions)
- 📖 [Documentation](https://github.com/yaniv-golan/dlzoom)

## Credits

Built with:

- [Click](https://click.palletsprojects.com/) / [Rich-Click](https://github.com/ewels/rich-click) - CLI framework
- [Rich](https://rich.readthedocs.io/) - Terminal output
- [Requests](https://requests.readthedocs.io/) - HTTP client
- [pytest](https://pytest.org/) - Testing framework

## Acknowledgments

Thanks to all contributors and the open source community.
## Architecture

This is a **monorepo** containing two independently deployable components:

### Repository Structure

```
dlzoom/
├── src/dlzoom/           # Python CLI (primary deliverable)
├── tests/                # Python test suite
├── zoom-broker/          # Cloudflare Worker (OAuth broker)
├── docs/                 # Documentation
│   ├── architecture.md   # Detailed architecture overview
│   └── zoom-app/         # Zoom App marketplace docs
└── pyproject.toml        # Python package configuration
```

**Components:**
- **Python CLI** (`src/dlzoom/`): Command-line tool to browse and download Zoom cloud recordings. Published to PyPI as `dlzoom`.
- **OAuth Broker** (`zoom-broker/`): Cloudflare Worker that performs OAuth code exchange and token refresh on behalf of the CLI. Optional component for user OAuth mode.

**Why a monorepo?**
- Simplified development workflow (single repo to clone, single issue tracker)
- Shared documentation and versioning strategy
- Python CLI is the primary deliverable; broker is a supporting service
- Each component remains independently deployable

📖 **See [`docs/architecture.md`](docs/architecture.md) for detailed architecture, data flows, security model, and deployment options.**
