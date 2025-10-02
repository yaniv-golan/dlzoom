# Contributing to dlzoom

Thank you for your interest in contributing to dlzoom! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Code Style](#code-style)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)
- [Release Process](#release-process)

## Code of Conduct

This project adheres to a code of conduct that all contributors are expected to follow:

- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on constructive feedback
- Prioritize the community's best interests

## Getting Started

### Prerequisites

- Python 3.11 or higher
- ffmpeg (for audio extraction)
- Git
- A GitHub account

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:

```bash
git clone https://github.com/YOUR_USERNAME/dlzoom.git
cd dlzoom
```

3. Add the upstream repository:

```bash
git remote add upstream https://github.com/OWNER/dlzoom.git
```

## Development Setup

### 1. Create Virtual Environment

```bash
# Create virtual environment
python3.11 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # On Linux/macOS
# or
.venv\Scripts\activate     # On Windows
```

### 2. Install Development Dependencies

```bash
# Install package in editable mode with dev dependencies
pip install -e ".[dev]"
```

This installs:
- All runtime dependencies
- Testing tools (pytest, pytest-cov)
- Linting tools (ruff, black, mypy)
- Build tools

### 3. Install ffmpeg

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows (via Chocolatey)
choco install ffmpeg
```

### 4. Set Up Zoom API Credentials (Optional)

For testing with real API calls, create a `.env` file:

```bash
ZOOM_ACCOUNT_ID=your_account_id
ZOOM_CLIENT_ID=your_client_id
ZOOM_CLIENT_SECRET=your_client_secret
```

**Note:** Most tests use mocks and don't require real credentials.

### 5. Verify Setup

```bash
# Run tests
pytest tests/ -v

# Check code style
ruff check src/ tests/
black --check src/ tests/

# Type check
mypy src/dlzoom/ --ignore-missing-imports
```

## Making Changes

### Branch Naming

Create a descriptive branch name:

```bash
git checkout -b feature/add-new-format-support
git checkout -b fix/handle-network-timeout
git checkout -b docs/update-installation-guide
```

**Prefixes:**
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation changes
- `refactor/` - Code refactoring
- `test/` - Test additions/improvements
- `chore/` - Maintenance tasks

### Development Workflow

1. **Pull latest changes:**
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Make your changes**

3. **Run tests locally:**
   ```bash
   pytest tests/ -v --cov=src/dlzoom
   ```

4. **Check code quality:**
   ```bash
   # Format code
   black src/ tests/

   # Lint code
   ruff check src/ tests/

   # Type check
   mypy src/dlzoom/ --ignore-missing-imports
   ```

5. **Commit changes** (see [Commit Messages](#commit-messages))

6. **Push to your fork:**
   ```bash
   git push origin feature/your-feature-name
   ```

## Testing

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src/dlzoom --cov-report=term-missing

# Run specific test file
pytest tests/test_cli.py -v

# Run specific test
pytest tests/test_cli.py::test_valid_meeting_id -v

# Run tests with verbose output
pytest tests/ -vv

# Stop at first failure
pytest tests/ -x
```

### Writing Tests

- Place tests in the `tests/` directory
- Name test files `test_*.py`
- Name test functions `test_*`
- Use descriptive test names that explain what is being tested
- Use pytest fixtures for common setup
- Mock external dependencies (API calls, file system, etc.)

**Example test:**

```python
import pytest
from dlzoom.cli import validate_meeting_id

def test_valid_meeting_id_accepts_numeric():
    """Test that valid numeric meeting IDs are accepted."""
    # This should not raise an exception
    validate_meeting_id(None, None, "123456789")

def test_invalid_meeting_id_rejects_too_short():
    """Test that meeting IDs shorter than 9 digits are rejected."""
    with pytest.raises(click.BadParameter):
        validate_meeting_id(None, None, "12345")
```

### Test Coverage Requirements

- New features must include tests
- Bug fixes should include regression tests
- Aim for at least 80% code coverage
- Critical paths (authentication, downloads) require 100% coverage

## Code Style

### Python Style Guide

We follow [PEP 8](https://pep8.org/) with some modifications:

- **Line length:** 88 characters (Black default)
- **Imports:** Organized with `isort` (integrated with Black)
- **Type hints:** Required for public functions
- **Docstrings:** Required for public modules, classes, and functions

### Automated Formatting

We use **Black** for code formatting:

```bash
# Format all code
black src/ tests/

# Check without modifying
black --check src/ tests/
```

### Linting

We use **Ruff** for fast Python linting:

```bash
# Check code
ruff check src/ tests/

# Auto-fix issues
ruff check --fix src/ tests/
```

### Type Checking

We use **mypy** for static type checking:

```bash
mypy src/dlzoom/ --ignore-missing-imports
```

### Pre-commit Checks

Before committing, ensure:

```bash
# 1. Format code
black src/ tests/

# 2. Lint code
ruff check --fix src/ tests/

# 3. Type check
mypy src/dlzoom/ --ignore-missing-imports

# 4. Run tests
pytest tests/ -v
```

## Commit Messages

We follow the **Conventional Commits** specification for clear commit history and automated versioning.

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- **feat:** New feature (triggers MINOR version bump)
- **fix:** Bug fix (triggers PATCH version bump)
- **docs:** Documentation changes
- **style:** Code style changes (formatting, no logic change)
- **refactor:** Code refactoring (no feature/fix)
- **test:** Adding or updating tests
- **chore:** Maintenance tasks (dependencies, build)
- **perf:** Performance improvements
- **ci:** CI/CD changes

### Examples

**New feature:**
```
feat(downloader): add support for CSV export

Implements CSV export format for recording metadata.
Users can now use --format csv to export recording info.

Closes #42
```

**Bug fix:**
```
fix(auth): handle expired OAuth tokens correctly

Previously, expired tokens caused crashes. Now they are
automatically refreshed before making API calls.

Fixes #38
```

**Breaking change:**
```
feat(api)!: change recording download API signature

BREAKING CHANGE: download_recording() now requires output_dir
parameter. Update all calls to include this parameter.

Migrating:
- Old: download_recording(meeting_id)
- New: download_recording(meeting_id, output_dir="/path")
```

**Simple fix:**
```
fix: correct typo in error message
```

### Scope

Scope is optional but recommended. Common scopes:

- `cli` - Command-line interface
- `auth` - Authentication
- `downloader` - Download functionality
- `api` - API client
- `config` - Configuration handling
- `docker` - Docker-related changes
- `docs` - Documentation
- `ci` - CI/CD workflows

## Pull Request Process

### Before Submitting

1. **Ensure all tests pass:**
   ```bash
   pytest tests/ -v
   ```

2. **Update documentation** if needed:
   - README.md for user-facing changes
   - Docstrings for API changes
   - CHANGELOG.md will be updated automatically

3. **Ensure code quality:**
   ```bash
   black src/ tests/
   ruff check src/ tests/
   mypy src/dlzoom/ --ignore-missing-imports
   ```

4. **Rebase on latest main:**
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

### Creating a Pull Request

1. **Push to your fork:**
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Open PR on GitHub** with:
   - Clear title following commit message conventions
   - Description explaining the changes
   - Reference to related issues (Fixes #123)
   - Screenshots/examples if applicable

3. **PR Description Template:**

```markdown
## Description
Brief description of what this PR does.

## Type of Change
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update

## Related Issues
Fixes #123
Relates to #456

## Testing
Describe how you tested your changes:
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing performed

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex code
- [ ] Documentation updated
- [ ] Tests added/updated
- [ ] All tests pass locally
- [ ] No new warnings introduced
```

### Review Process

- Maintainers will review your PR
- CI/CD checks must pass (tests, linting, security scans)
- Address review feedback by pushing new commits
- Once approved, a maintainer will merge your PR

### After Merging

- Your branch will be deleted automatically
- Delete your local branch:
  ```bash
  git branch -d feature/your-feature-name
  ```

- Pull the latest changes:
  ```bash
  git checkout main
  git pull upstream main
  ```

## Release Process

**For Maintainers Only**

### Semantic Versioning

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR (X.0.0):** Breaking changes
- **MINOR (0.X.0):** New features (backward-compatible)
- **PATCH (0.0.X):** Bug fixes (backward-compatible)

### CI/CD Setup Prerequisites

Before you can publish releases, configure these prerequisites:

#### 1. Docker Hub Repository

1. Create repository at https://hub.docker.com/repositories
2. Set **Name:** `dlzoom`, **Visibility:** Public
3. Note your Docker Hub username (e.g., `yourusername`)

#### 2. Docker Hub Access Token

1. Go to https://hub.docker.com/settings/security
2. Create **New Access Token** with **Read, Write, Delete** permissions
3. Save the token securely (you won't see it again)

#### 3. GitHub Secrets

Add these secrets at `https://github.com/OWNER/REPO/settings/secrets/actions`:

- **DOCKERHUB_USERNAME** - Your Docker Hub username
- **DOCKERHUB_TOKEN** - The access token from step 2

#### 4. PyPI Trusted Publishing (Test PyPI)

1. Go to https://test.pypi.org/manage/account/publishing/
2. Click **Add a new publisher**
3. Fill in:
   - **PyPI Project Name:** `dlzoom`
   - **Owner:** Your GitHub username
   - **Repository name:** `dlzoom`
   - **Workflow filename:** `release.yml`
   - **Environment name:** (leave empty)

#### 5. PyPI Trusted Publishing (Production)

**⚠️ Configure BEFORE creating your first release tag**

1. Go to https://pypi.org/manage/account/publishing/
2. Add publisher with same settings as Test PyPI
3. **Note:** Must be done before project exists on PyPI

#### 6. GitHub Workflow Permissions

1. Go to `https://github.com/OWNER/REPO/settings/actions`
2. Under **Workflow permissions:**
   - Select **Read and write permissions**
   - Check **Allow GitHub Actions to create and approve pull requests**
3. Click **Save**

#### 7. GitHub Container Registry (GHCR)

**No setup needed** - GHCR is automatically available for public repos.

Images will be published to:
- `ghcr.io/OWNER/dlzoom:latest`
- `ghcr.io/OWNER/dlzoom:VERSION`

#### What Runs When

**On Every Push to Main:**
- ✅ Tests, linting, security scans
- ✅ Build Python package and test wheel
- ✅ Publish to **Test PyPI**
- ✅ Build and scan Docker image
- ❌ Does NOT publish Docker (only on tags)

**On Pull Requests:**
- ✅ Tests, linting, security scans
- ❌ Does NOT publish anywhere

**On Version Tags (v*):**
- ✅ All CI checks
- ✅ Publish to **Production PyPI**
- ✅ Build multi-arch Docker images
- ✅ Publish to **Docker Hub** and **GHCR**
- ✅ Create **GitHub Release**

#### Common Issues

**PyPI Publish Fails: "Invalid or non-existent authentication"**
- Cause: Trusted publishing not configured
- Fix: Complete steps 4 & 5 above

**Docker Publish Fails: "denied: requested access to the resource is denied"**
- Cause: Docker Hub credentials not configured
- Fix: Complete steps 2 & 3 above

**Docker Publish to GHCR Fails: "insufficient_scope"**
- Cause: Workflow permissions not set
- Fix: Complete step 6 above

### Release Steps

1. **Ensure main is clean:**
   ```bash
   git checkout main
   git pull upstream main
   ```

2. **Run full test suite:**
   ```bash
   pytest tests/ --cov=src/dlzoom --cov-report=term-missing
   ```

3. **Update version in pyproject.toml:**
   ```toml
   [project]
   version = "0.3.0"
   ```

4. **Update CHANGELOG.md** with release notes

5. **Commit version bump:**
   ```bash
   git add pyproject.toml CHANGELOG.md
   git commit -m "chore: bump version to 0.3.0"
   git push upstream main
   ```

6. **Create and push tag:**
   ```bash
   git tag -a v0.3.0 -m "Release version 0.3.0"
   git push upstream v0.3.0
   ```

7. **GitHub Actions will automatically:**
   - Run all tests
   - Test built wheel
   - Publish to Test PyPI (on main push)
   - Publish to PyPI (on tag push)
   - Build and scan Docker image
   - Publish Docker image to Docker Hub and GHCR
   - Create GitHub Release

8. **Verify the release:**
   - Check PyPI: https://pypi.org/project/dlzoom/
   - Check Docker Hub: `https://hub.docker.com/r/YOUR_DOCKERHUB_USERNAME/dlzoom`
   - Check GHCR: `https://github.com/OWNER/dlzoom/pkgs/container/dlzoom`
   - Check GitHub Release: `https://github.com/OWNER/dlzoom/releases`

### Test PyPI Publishing

Every push to `main` automatically publishes to Test PyPI for validation:

```bash
# Test installation from Test PyPI
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ dlzoom
```

## Getting Help

- **Issues:** Report bugs or request features on GitHub Issues
- **Discussions:** Ask questions on GitHub Discussions
- **Email:** Contact maintainers (see README)

## Recognition

Contributors are recognized in:
- GitHub contributors list
- Release notes
- Project README (for significant contributions)

Thank you for contributing to dlzoom! 🎉
