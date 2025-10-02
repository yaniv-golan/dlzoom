# Security Policy

## Supported Versions

We release security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Security Features

dlzoom implements several security measures to protect your credentials and data:

### 1. Credential Protection

- **Never logged:** Zoom API credentials are never written to logs
- **Secure storage:** Credentials read from environment variables or config files (not command line)
- **Masked in output:** Credentials are masked in debug output and error messages

### 2. Input Validation

- **Meeting ID validation:** Prevents path traversal and command injection attacks
- **File path sanitization:** Output paths are validated to prevent directory traversal
- **URL validation:** Recording URLs are validated before download

### 3. Network Security

- **HTTPS only:** All API communication uses HTTPS
- **Token expiration:** OAuth tokens are automatically refreshed
- **Timeout protection:** Network calls have timeout limits (30 seconds)
- **Rate limit handling:** Automatic retry with exponential backoff

### 4. File Operations

- **Atomic writes:** Files are written atomically to prevent corruption
- **Disk space checks:** Ensures sufficient disk space before downloads
- **Size validation:** Downloaded files are validated against expected sizes
- **Temporary file cleanup:** Temporary files are automatically removed

### 5. Dependency Security

- **Automated scanning:** Dependencies are scanned for vulnerabilities via Trivy
- **Regular updates:** Dependencies are kept up-to-date
- **Minimal dependencies:** Only essential dependencies are included

### 6. Docker Security

- **Non-root user:** Docker containers run as non-root user (UID 1000)
- **Minimal base image:** Uses `python:3.11-slim` for smaller attack surface
- **Multi-stage builds:** Build dependencies not included in final image
- **Regular scanning:** Docker images scanned with Trivy on every build
- **SBOM generation:** Software Bill of Materials available for images

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please follow these steps:

### 1. Do Not Disclose Publicly

**Please do not:**
- Open a public GitHub issue
- Post on social media or forums
- Discuss publicly until fixed

### 2. Report Privately

**Email:** [yaniv@golan.name](mailto:yaniv@golan.name)

**Subject:** `[SECURITY] Brief description of vulnerability`

**Include:**
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)
- Your contact information

### 3. What to Expect

**Within 24 hours:**
- Acknowledgment of your report
- Initial assessment of severity

**Within 7 days:**
- Detailed response with:
  - Confirmation or rejection of vulnerability
  - Estimated timeline for fix
  - Planned disclosure date

**Timeline:**
- **Critical vulnerabilities:** Fixed within 7 days
- **High severity:** Fixed within 30 days
- **Medium/Low severity:** Fixed in next regular release

### 4. Security Advisory Process

Once a vulnerability is confirmed and fixed:

1. **Patch released** on all supported versions
2. **Security advisory published** on GitHub Security Advisories
3. **CVE assigned** (if applicable)
4. **Credit given** to reporter (unless anonymity requested)

## Security Disclosure Policy

### Coordinated Disclosure

We follow responsible disclosure practices:

1. **Private reporting period:** 90 days
2. **Fix development:** Work with reporter to develop fix
3. **Public disclosure:** After patch is released
4. **Credit:** Reporter acknowledged in release notes

### Public Disclosure

After a fix is released, we will:

- Publish GitHub Security Advisory
- Update CHANGELOG.md with security notes
- Announce in release notes
- Update documentation if needed

## Security Best Practices for Users

### Credential Management

**✅ Do:**
- Use environment variables or config files for credentials
- Use `.env` files with restrictive permissions (600)
- Store credentials in secure password managers
- Use Server-to-Server OAuth apps (not user tokens)
- Limit OAuth app scopes to minimum required

**❌ Don't:**
- Pass credentials via command line arguments
- Commit credentials to version control
- Share credentials via email or chat
- Use overly permissive OAuth scopes
- Reuse credentials across environments

### Configuration Files

**Secure .env file:**

```bash
# Set restrictive permissions
chmod 600 .env

# Verify permissions
ls -l .env
# Should show: -rw------- (only owner can read/write)
```

**Example .env:**

```bash
ZOOM_ACCOUNT_ID=your_account_id
ZOOM_CLIENT_ID=your_client_id
ZOOM_CLIENT_SECRET=your_client_secret
```

**Add to .gitignore:**

```bash
# Credentials
.env
credentials.json
config.yaml
*.key
*.pem
```

### Docker Security

**Run as non-root:**

```bash
# dlzoom Docker images already run as non-root (UID 1000)
docker run --rm yanivgolan1/dlzoom:latest --help
```

**Use specific version tags:**

```bash
# ✅ Good: Specific version
docker run --rm yanivgolan1/dlzoom:0.1.0 --help

# ❌ Avoid: latest tag (changes without notice)
docker run --rm yanivgolan1/dlzoom:latest --help
```

**Mount volumes read-only when possible:**

```bash
# Mount config as read-only
docker run --rm \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  -v $(pwd)/downloads:/app/downloads \
  -e ZOOM_ACCOUNT_ID="$ZOOM_ACCOUNT_ID" \
  yanivgolan1/dlzoom:0.1.0 123456789```

### Network Security

**Use HTTPS proxies only:**

```bash
# If using a proxy, ensure it's HTTPS
export HTTPS_PROXY=https://proxy.example.com:8080
```

**Verify TLS certificates:**

```bash
# dlzoom verifies TLS certificates by default
# Don't disable certificate verification in production
```

### File System Security

**Use dedicated download directory:**

```bash
# Create dedicated directory with appropriate permissions
mkdir -p ~/zoom-recordings
chmod 700 ~/zoom-recordings

# Download to dedicated directory
dlzoom 123456789 --output-dir ~/zoom-recordings
```

**Clean up temporary files:**

```bash
# dlzoom automatically cleans up temporary files
# But periodically check /tmp for orphaned files
```

## Security Scanning

### Automated Scans

Our CI/CD pipeline runs multiple security scans:

#### 1. Dependency Scanning
- **Tool:** Trivy (filesystem scan)
- **Frequency:** Every push/PR
- **Scope:** Python dependencies in requirements
- **Results:** Uploaded to GitHub Security tab

#### 2. Docker Image Scanning
- **Tool:** Trivy (container scan)
- **Frequency:** Every build
- **Scope:** OS packages, Python dependencies, misconfigurations
- **Results:** Uploaded to GitHub Security tab

#### 3. Code Scanning
- **Tool:** GitHub CodeQL (planned)
- **Frequency:** Every push/PR
- **Scope:** Source code vulnerabilities
- **Results:** GitHub Security tab

### Viewing Security Scan Results

**GitHub Security Tab:**

1. Go to repository: https://github.com/yaniv-golan/dlzoom
2. Click **Security** tab
3. View **Dependabot alerts** and **Code scanning alerts**

**Local Scanning:**

```bash
# Scan Python dependencies
pip install pip-audit
pip-audit

# Scan Docker image
docker build -t dlzoom:test .
docker run --rm aquasec/trivy image dlzoom:test
```

## Vulnerability Response

### Critical Vulnerabilities

**Definition:**
- Remote code execution
- Authentication bypass
- Credential exposure
- Data loss

**Response:**
- Immediate assessment (< 24 hours)
- Emergency patch (< 7 days)
- Public advisory and CVE

### High Severity Vulnerabilities

**Definition:**
- Local privilege escalation
- Denial of service
- Information disclosure
- CSRF/XSS (if applicable)

**Response:**
- Assessment within 48 hours
- Patch within 30 days
- Security advisory

### Medium/Low Severity

**Definition:**
- Minor information disclosure
- Non-exploitable bugs
- Defense-in-depth improvements

**Response:**
- Included in next regular release
- Documented in CHANGELOG

## Security Contacts

- **Primary:** [yaniv@golan.name](mailto:yaniv@golan.name)
- **GitHub Security:** https://github.com/yaniv-golan/dlzoom/security

## PGP Key

**Coming soon:** PGP public key for encrypted vulnerability reports.

## Security Hall of Fame

We recognize security researchers who responsibly disclose vulnerabilities:

*No vulnerabilities reported yet.*

---

**Last Updated:** 2025-10-02

Thank you for helping keep dlzoom secure! 🔒
