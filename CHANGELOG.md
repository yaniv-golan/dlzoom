# Changelog

All notable changes to dlzoom will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1] - Unreleased

### Added

#### Meeting ID Input Enhancement
- Space-separated meeting IDs now work without quotes
  - Users can type `dlzoom download 123 4567 1111` instead of `"123 4567 1111"`
  - CLI automatically joins space-separated numeric parts into a single meeting ID
  - Maintains backward compatibility with quoted IDs and UUIDs

## [0.3.0] - 2025-11-16

### Added

#### STJ Diarization Support
- Minimal STJ diarization file generation (default ON) after timeline download
  - Emits `{output_name}_speakers.stjson` in STJ v0.6 format
  - Diarization-only segments (start/end/speaker_id, empty text)
  - Prefers `timeline_refine` over `timeline` when available
  - Privacy by default: includes only stable speaker id + display name
- CLI controls:
  - `--skip-speakers` to disable generation
  - `--speakers-mode [first|multiple]` to handle multi-user timestamps
  - `--stj-min-seg-sec` (default 1.0) to drop very short segments
  - `--stj-merge-gap-sec` (default 1.5) to merge small gaps
  - `--include-unknown` to include segments with unknown speaker
- Env toggle: `DLZOOM_SPEAKERS=0` disables generation (default is enabled)

#### Recording Scope System (S2S OAuth)
- New `--scope` option for batch downloads: `auto` (default), `account`, or `user`
  - `account` scope: Download all account recordings (requires admin permissions)
  - `user` scope: Download specific user's recordings
  - `auto` scope: Automatically detect based on OAuth token type
- New `--user-id` option: Specify Zoom user email or UUID for user-scoped downloads (S2S mode)
- New `--page-size` option: Control API pagination (default 300, max 300)
- Scope validation: CLI now validates that S2S tokens have required scopes for account-level access
- Metadata enhancement: Recording scope and user ID now included in JSON outputs

#### OAuth Broker Infrastructure
- **Automated Cloudflare Workers deployment** via GitHub Actions
  - Automatic deployment on push to `main`
  - Preview deployments for pull requests
  - Environment variable injection from GitHub secrets
- **Comprehensive broker documentation:**
  - `zoom-broker/CLOUDFLARE_SETUP.md` - Step-by-step Cloudflare integration guide
  - `zoom-broker/DEPLOYMENT.md` - Full deployment instructions
  - `zoom-broker/DEPLOYMENT_COMPARISON.md` - Manual vs automated deployment comparison
  - `zoom-broker/QUICKSTART_CICD.md` - Quick CI/CD setup guide
- **Setup automation scripts:**
  - `scripts/setup-secrets.sh` - Interactive secret configuration
  - `scripts/setup-kv.sh` - KV namespace creation and binding
  - `scripts/wrangler-local.sh` - Local development environment
  - `scripts/apply-kv-placeholders.mjs` - CI/CD wrangler config generation
- Enhanced broker security: CORS configuration validation and clearer error messages

### Changed

#### Batch Download Improvements
- Batch downloads now honor `--output-name`; when omitted they auto-append UTC timestamps (or recording UUIDs) per meeting to prevent filename collisions
- Batch downloads once again respect `--dry-run`, letting operators preview large date windows without pulling files
- Batch downloads now pass through `--wait`, so operators can pause until recordings finish processing before the download loop starts
- Batch downloads now honor `--log-file`, writing structured JSONL entries for every meeting in the range
- Batch downloads exit non-zero when any meeting fails, allowing CI/CD jobs to detect partial failures

#### Check Availability Improvements
- `--check-availability` works with `--from-date/--to-date`, returning a summary across the date window instead of silently exiting
- `--wait` failures now abort before download attempts, surfacing a clear error instead of re-fetching recordings that are still processing
- `dlzoom download --check-availability` now raises errors (non-zero exit) when Zoom cannot find the recording or the API call fails

#### Output & Metadata
- Transcript/chat/timeline downloads now avoid filename collisions and JSON output enumerates all audio/video/transcript/chat/timeline/speaker files for automation
- Metadata summaries now report the actual delivered audio file size (post-extraction) instead of the source MP4 size
- JSON outputs now include log file path when `--log-file` is specified
- Deterministic STJ output (rounded to 3 decimals) and idempotent regeneration

#### Date & Time Handling
- Date shortcuts in `dlzoom recordings --range` now use UTC consistently (previously used local timezone)
- Recording date range queries properly handle timezone boundaries

#### Other Improvements
- Respect skip cascade: `--skip-timeline` also prevents STJ generation
- Config file validation: Missing config file path now raises clear error instead of being silently ignored

### Fixed
- **Path expansion**: Tilde (`~`) in paths now properly expands on all platforms (Windows, macOS, Linux)
  - Affects `--output-dir`, `--log-file`, and config file paths
- **Audio file tracking**: Metadata now reflects extracted audio size, not source MP4 size
- **Cross-platform compatibility**: Resolved test failures and path handling issues on Windows

### Documentation
- Added repository banner image at top of README
- Added design plan: `docs/internal/stj-minimal-json-plan.md`
- Added STJ specification link and feature documentation
- Clarified hosted login status and security considerations
- Documented platform-specific token storage locations (macOS/Linux/Windows)
- Consolidated OAuth broker CI/CD guidance across documentation
- Updated architecture documentation with scope system details

### Infrastructure
- Added GitHub Actions workflow for automatic Cloudflare Workers deployment
- Updated SARIF upload actions to v4
- Enhanced CI testing for cross-platform compatibility
- Added environment variable configuration for broker unit tests

### Testing
- Added comprehensive test coverage for scope system (~700 lines)
- Added tests for recordings iteration and date chunking
- Added CLI check-availability test coverage
- Improved cross-platform test reliability
- Added test utilities for CLI testing (`tests/cli_test_utils.py`)


## [0.2.1] - 2025-11-13

Hotfix release.

### Changed
- docs(readme): add Shields badges for CI, PyPI, Docker, license, and downloads
- docs(auth): clarify hosted sign-in availability and provide self-host/S2S alternatives
- refactor(cli): add `main()` entrypoint for console script
- chore(zoom-broker): update `zoom-broker/wrangler.jsonc`


## [0.2.0] - 2025-11-13

User‑facing release focused on a clearer CLI, optional user OAuth, and safer downloads.

### Breaking
- Removed: `dlzoom download --list`.
  - Use: `dlzoom recordings --meeting-id <id_or_uuid>` to list instances for a meeting.
- Removed Auto-deletion of MP4 files after audio extraction

### New
- Unified CLI with subcommands: `dlzoom [recordings|download|login|logout|whoami]`.
- User OAuth login/logout using a minimal hosted broker (`dlzoom login`, `dlzoom logout`). **Note** This is inactive at the the time of the release - pending approval of the Zoom App by Zoom.
- `dlzoom recordings` command:
  - Browse by date: `--range` (today, yesterday, last-7-days, last-30-days) or `--from-date/--to-date`.
  - Meeting‑scoped listing: `--meeting-id <id_or_uuid>` with instance count and file types.
  - JSON output (`--json`), topic filter (`--topic`), and result limits (`--limit`, `--page-size`).
- Batch by date window: `dlzoom download --from-date YYYY-MM-DD --to-date YYYY-MM-DD`.
- `dlzoom whoami` to confirm auth mode (S2S vs user OAuth) and token validity.

### Improvements
- Safer download host allow‑list (HTTPS, Zoom domains only) and clearer errors.
- Stricter meeting ID/UUID normalization (handles URL/percent‑encoded UUIDs; blocks traversal).
- More robust networking (retries/backoff), filename sanitization, and structured JSON errors.
- Local metadata JSON saved with each download (meeting details, selected instance, files, notes).

### Changed
- **Behavior Change**: MP4 files are now **retained** after audio extraction (previously auto-deleted)
- Optimized `Content-Type` header - only included for POST/PUT/PATCH requests (not GET)

### Docs
- New Privacy/Terms/Support pages; expanded README and architecture overview.

### Migration
- Replace any `dlzoom download <id> --list` usage with `dlzoom recordings --meeting-id <id>`.

## [0.1.0] - 2025-10-02

### 🎉 Initial Release

First public release of dlzoom - a production-ready CLI tool for downloading Zoom cloud recordings.

### Added

#### Core Features

- Download Zoom cloud recordings via meeting ID
- Automatic audio extraction from video files (MP4 → M4A)
- Support for audio-only recordings (M4A)
- Timeline download (JSON format with meeting events)
- Transcript download (VTT format)
- Chat log download (TXT format)
- Server-to-Server OAuth authentication

#### Recording Management

- Check recording availability before downloading
- List all recordings for a meeting (recurring/PMI support)
- Wait for recording processing with timeout
- Support for password-protected recordings
- Automatic selection of most recent recording
- Manual recording selection by UUID

#### Output & Configuration

- Multiple output formats (human-readable, JSON)
- Custom output directory and filename
- Template-based filename generation
- Template-based folder structure
- Configuration via `.env`, JSON, or YAML files

#### User Experience

- Verbose and debug logging modes
- Progress bars for downloads
- Clear error messages with troubleshooting hints
- Dry-run mode to preview downloads
- Rich terminal output with colors and formatting

#### Distribution & Installation

- **PyPI package** - Published to PyPI (`pip install dlzoom`)
- **uv/uvx support** - Instant run without installation (`uvx dlzoom`)
- **uv tool install** - Isolated installation (`uv tool install dlzoom`)
- **Docker image** - Multi-arch containers (amd64, arm64)
  - Published to Docker Hub: `yanivgolan1/dlzoom:latest`
  - Published to GitHub Container Registry: `ghcr.io/yaniv-golan/dlzoom:latest`
  - Includes Python 3.11 + ffmpeg (zero local dependencies)
  - Non-root user (security hardened)
  - Multi-stage build (optimized image size ~200MB)

#### CI/CD Pipeline

- **GitHub Actions CI** - Automated testing on every push/PR
  - Matrix testing: 3 OSes × 2 Python versions (3.11, 3.12)
  - Platforms: Ubuntu, macOS, Windows
  - Automated linting (ruff, black)
  - Type checking (mypy)
  - Security scanning (pip-audit + Trivy)
  - Code coverage reporting
- **GitHub Actions CD** - Automated releases
  - PyPI publishing with trusted publishing (OIDC)
  - Test PyPI publishing on every main branch push
  - Docker multi-arch builds (amd64, arm64)
  - Docker image security scanning (Trivy)
  - Automatic version tagging
  - Release asset uploads

#### Security Features

- **Credential Protection**
  - Credentials never logged or exposed
  - Masked in debug output and error messages
  - Secure storage via environment variables or config files
- **Input Validation**
  - Meeting ID validation prevents injection attacks
  - File path sanitization prevents directory traversal
  - URL validation before downloads
- **Network Security**
  - HTTPS only for all API communication
  - Token expiration handling
  - Timeout protection (30 seconds)
  - Rate limit handling with exponential backoff
- **File Operations**
  - Atomic file writes prevent corruption
  - Disk space checks before downloads
  - Size validation against expected sizes
  - Automatic temporary file cleanup
- **Dependency Security**
  - Automated Trivy scanning of Python dependencies
  - Regular dependency updates
  - Minimal dependency footprint
- **Docker Security**
  - Non-root user (UID 1000)
  - Minimal base image (python:3.11-slim)
  - Multi-stage builds
  - Regular Trivy scanning
  - SBOM generation

#### Documentation

- **README.md** - Comprehensive user documentation
- **CONTRIBUTING.md** - Contributor guidelines
  - Development setup instructions
  - Testing guidelines
  - Commit message conventions (Conventional Commits)
  - Pull request process
  - Release process for maintainers
- **SECURITY.md** - Security policy
  - Supported versions
  - Security features overview
  - Vulnerability reporting process
  - Security best practices for users
  - Disclosure policy
- **CICD_SETUP.md** - Complete CI/CD setup checklist
- **CHANGELOG.md** - Version history tracking
- **LICENSE** - MIT License

#### Testing

- Comprehensive test suite (119 tests)
- 44% code coverage
- Type hints throughout codebase
- Pytest-based testing framework
- Automated testing in CI

### Technical Details

- **Python Version**: 3.11+
- **Dependencies**: requests, rich-click, python-dotenv, rich
- **External Tools**: ffmpeg (for audio extraction)
- **Package Format**: Modern pyproject.toml (PEP 517/518)
- **Development Status**: Beta
- **License**: MIT
- **Installation Methods**: PyPI, uvx, Docker, source

### Requirements

- Python 3.11 or higher
- ffmpeg (for MP4 to M4A conversion)
- Zoom Server-to-Server OAuth credentials

### Known Limitations

- No command to list all recordings across all meetings (requires meeting ID)
- Audio quality setting not exposed via CLI (uses default/copy mode)
- No batch download by date range

### Planned for Future Releases

- OAuth Device Code Flow for simpler authentication (v0.3.0)
- Batch download by date range
- Audio quality CLI option
- More output formats (CSV, TSV)
- List all recordings across meetings

---

## Installation

### From PyPI

```bash
pip install dlzoom
```

### With uvx (no installation)

```bash
uvx dlzoom download 123456789 --check-availability
```

### Docker

```bash
docker run --rm yanivgolan1/dlzoom:latest --help
```

### From Source

```bash
git clone https://github.com/yaniv-golan/dlzoom
cd dlzoom
pip install -e .
```

---

## Release Notes

This is the first stable release of dlzoom. The tool is production-ready for:

- Downloading individual meeting recordings
- Automation and scripting (JSON output)
- Integration with transcription pipelines
- Containerized deployments

Report issues at: <https://github.com/yaniv-golan/dlzoom/issues>

[0.1.0]: https://github.com/yaniv-golan/dlzoom/releases/tag/v0.1.0
[0.2.0]: https://github.com/yaniv-golan/dlzoom/compare/v0.1.0...v0.2.0
[0.2.1]: https://github.com/yaniv-golan/dlzoom/compare/v0.2.0...v0.2.1
[0.3.0]: https://github.com/yaniv-golan/dlzoom/compare/v0.2.1...v0.3.0
