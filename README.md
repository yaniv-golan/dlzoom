# dlzoom

**Download Zoom cloud recordings from the command line.**

Simple CLI tool to download audio recordings and metadata from Zoom meetings using meeting IDs.

## Features

- 🎵 Download audio recordings (M4A format)
- 📝 Download transcripts, chat logs, and timelines
- 🔄 Automatic audio extraction from video files (MP4 → M4A)
- 🔐 Server-to-Server OAuth authentication
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
uvx dlzoom 123456789 --check-availability
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
  yanivgolan/dlzoom:latest \
  123456789```

**Or use GitHub Container Registry:**
```bash
docker run -it --rm \
  -v $(pwd)/recordings:/app/downloads \
  -e ZOOM_ACCOUNT_ID="your_account_id" \
  -e ZOOM_CLIENT_ID="your_client_id" \
  -e ZOOM_CLIENT_SECRET="your_secret" \
  ghcr.io/yaniv-golan/dlzoom:latest \
  123456789```

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

### 1. Get Zoom API Credentials

> **Coming in v0.3:** One-click authentication! No more manual app setup. See [Roadmap](#roadmap).

**Current method (Server-to-Server OAuth):**

1. Go to [Zoom Marketplace](https://marketplace.zoom.us/)
2. Sign in → **Develop** → **Build App**
3. Create a **Server-to-Server OAuth** app
4. Copy your credentials:
   - Account ID
   - Client ID
   - Client Secret
5. Add required scopes:
   - `recording:read:admin`
   - `meeting:read:admin`

**Why this is temporary:** This approach requires manual OAuth app creation and credential management. In v0.3, we're adding one-click OAuth authentication (like `gh auth login`) where you just authorize dlzoom in your browser and you're done!

### 2. Configure Credentials

Create a `.env` file in your working directory:

```bash
ZOOM_ACCOUNT_ID=your_account_id_here
ZOOM_CLIENT_ID=your_client_id_here
ZOOM_CLIENT_SECRET=your_client_secret_here
```

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

### 3. Download a Recording

```bash
dlzoom 123456789
```

## Usage

### Basic Commands

**Check if recording is available:**
```bash
dlzoom 123456789 --check-availability
```

**List all recordings for a meeting:**
```bash
dlzoom 123456789 --list
```

**Download recording (audio + transcript + chat + timeline):**
```bash
dlzoom 123456789
```

**Download with custom output name:**
```bash
dlzoom 123456789 --output-name "my_meeting"
```

**Download to specific directory:**
```bash
dlzoom 123456789 --output-dir ~/Downloads/zoom
```

**Wait for recording to finish processing:**
```bash
dlzoom 123456789 --wait 30
```

**Password-protected recordings:**
```bash
dlzoom 123456789 --password "meeting_password"
```

### Advanced Options

**Use config file:**
```bash
dlzoom 123456789 --config config.yaml
```

**Verbose output (see detailed logs):**
```bash
dlzoom 123456789 --verbose
```

**Debug mode (full API responses):**
```bash
dlzoom 123456789 --debug
```

**JSON output (for automation):**
```bash
dlzoom 123456789 --json
```

**Dry run (see what would be downloaded):**
```bash
dlzoom 123456789 --dry-run
```

**Custom filename template:**
```bash
dlzoom 123456789\
  --filename-template "{topic}_{start_time:%Y%m%d}"
```

**Custom folder structure:**
```bash
dlzoom 123456789\
  --folder-template "{start_time:%Y}/{start_time:%m}"
```

**Select specific recording instance (for recurring meetings):**
```bash
dlzoom 123456789 --recording-id "abc123def456"
```

### Skip Downloads

**Skip transcript download:**
```bash
dlzoom 123456789 --skip-transcript
```

**Skip chat log download:**
```bash
dlzoom 123456789 --skip-chat
```

**Skip timeline download:**
```bash
dlzoom 123456789 --skip-timeline
```

## All Options

```
dlzoom [OPTIONS] MEETING_ID

Options:
  --output-dir, -o PATH          Output directory (default: current directory)
  --output-name, -n TEXT         Base filename (default: meeting_id)
  --verbose, -v                  Show detailed operation information
  --debug, -d                    Show full API responses and trace
  --json, -j                     JSON output mode (machine-readable)
  --list, -l                     List all recordings with timestamps
  --check-availability, -c       Check if recording is ready
  --recording-id TEXT            Select specific recording by UUID
  --wait MINUTES                 Wait for recording processing (timeout)
  --skip-transcript              Skip transcript download
  --skip-chat                    Skip chat log download
  --skip-timeline                Skip timeline download
  --dry-run                      Show what would be downloaded
  --password, -p TEXT            Password for protected recordings
  --log-file PATH                Write structured log (JSONL format)
  --config PATH                  Path to config file (JSON/YAML)
  --filename-template TEXT       Custom filename template
  --folder-template TEXT         Custom folder structure template
  --from-date TEXT               Start date for batch (YYYY-MM-DD)
  --to-date TEXT                 End date for batch (YYYY-MM-DD)
  --help                         Show this message and exit
  --version                      Show version and exit
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
dlzoom 123456789 --verbose
```

### Download Specific Instance

```bash
# List all instances first
dlzoom 123456789 --list

# Download specific one
dlzoom 123456789 --recording-id "abc123def456"
```

### Automated Pipeline (JSON Output)

```bash
dlzoom 123456789 --json > recording.json
```

### Batch Processing

```bash
#!/bin/bash
for meeting_id in 111111111 222222222 333333333; do
    dlzoom $meeting_id  --output-dir ./recordings
done
```

### Wait for Recording to Process

```bash
# Wait up to 60 minutes for processing
dlzoom 123456789 --wait 60
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
dlzoom 123456789 --check-availability
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
dlzoom 123456789 --config config.yaml
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

- Python 3.8 or higher
- ffmpeg (for audio extraction)
- Zoom Server-to-Server OAuth app

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

**v0.1.0** - Initial release (2025-10-02)

See [CHANGELOG.md](CHANGELOG.md) for detailed release notes.

## Roadmap

Planned for future releases:

### v0.3 (Next) - OAuth Authentication 🚀
- 🔐 **One-click authentication** - No more manual OAuth app setup!
  ```bash
  dlzoom auth login  # Opens browser, authorize, done!
  dlzoom 123456789 # Just works
  ```
- 🔄 Automatic token refresh
- 👤 Per-user authentication (no shared credentials)
- 🔑 Secure token storage in `~/.dlzoom/credentials`
- 📱 Multiple profiles support

See [docs/OAUTH_PROPOSAL.md](docs/OAUTH_PROPOSAL.md) for detailed design.

### v0.4
- 📊 List all recordings across meetings
- 📅 Batch download by date range
- 🎨 More output formats (CSV, TSV)
- 🔐 Token encryption (system keychain)

See [PLAN.md](PLAN.md) for complete implementation plan.

## Known Limitations

### Feature Limitations
- No standalone "list all recordings" command (requires meeting ID)
- Audio quality parameter not exposed via CLI (internal only)
- No batch download by date range
- No listing of all meetings/recordings

> **Note:** These features are planned for future releases.

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
