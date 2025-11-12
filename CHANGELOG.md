# Changelog

All notable changes to dlzoom will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

---

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
uvx dlzoom 123456789 --check-availability
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
## [0.2.0] - 2025-11-12

User‑facing release focused on a clearer CLI, optional user OAuth, and safer downloads.

### Breaking
- Removed: `dlzoom download --list`.
  - Use: `dlzoom recordings --meeting-id <id_or_uuid>` to list instances for a meeting.

### New
- Unified CLI with subcommands: `dlzoom [recordings|download|login|logout|whoami]`.
- User OAuth login/logout using a minimal hosted broker (`dlzoom login`, `dlzoom logout`).
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

### Docs
- New Privacy/Terms/Support pages; expanded README and architecture overview.

### Migration
- Replace any `dlzoom download <id> --list` usage with `dlzoom recordings --meeting-id <id>`.
