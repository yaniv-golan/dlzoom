# Zoom Broker Deployment Guide

This document describes the CI/CD setup for the Zoom Broker Cloudflare Worker.

## Deployment Methods

### 🌐 Cloudflare Builds (Primary - Recommended)

The Worker is connected to GitHub via [Cloudflare's native Git integration](https://developers.cloudflare.com/workers/ci-cd/builds/).

#### How It Works

1. **Push to `main` branch** → Automatic production deployment
2. **Open Pull Request** → Automatic preview URL generation
3. **Build pipeline**:
   - Install dependencies (`npm ci`)
   - Run tests (`npm test`)
   - Deploy (`npx wrangler deploy`)

#### Configuration

- **Build settings** are configured in the Cloudflare Dashboard under Settings → Builds
- **Root directory**: `/zoom-broker`
- **Build command**: `npm ci && npm test && npx wrangler deploy`
- **Environment variables**: Set in Cloudflare Dashboard (secrets like `ZOOM_CLIENT_ID`, `ZOOM_CLIENT_SECRET`, `ALLOWED_ORIGIN`)

#### Monitoring Deployments

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com) → Workers & Pages → `zoom-broker`
2. Navigate to **Deployments** tab
3. View:
   - Build status (success/failure)
   - Build logs
   - Version history
   - Preview URLs (for PRs)

#### Preview URLs

Each PR automatically gets a unique preview URL like:
```
https://<version-id>.zoom-broker.<user>.workers.dev
```

**To test OAuth with previews:**
1. Add preview redirect URL to your Zoom OAuth app settings
2. Use the preview URL with `dlzoom login --auth-url https://<preview-url>`
3. Test OAuth flow before merging

### 🔧 GitHub Actions (Secondary - Quality Gates)

The `.github/workflows/js.yml` workflow runs on every push/PR:

- ✅ Runs tests (`npm test`)
- 🔒 Security scanning (Trivy)
- 📊 Uploads results to GitHub Security tab

**Note:** GitHub Actions currently runs tests only. Deployment is handled by Cloudflare Builds.

#### Optional: Deploy via GitHub Actions

If you prefer GitHub Actions over Cloudflare Builds:

1. Uncomment the `deploy` job in `.github/workflows/js.yml`
2. Add `CLOUDFLARE_API_TOKEN` to GitHub repository secrets:
   - Go to Settings → Secrets and variables → Actions
   - Create new secret: `CLOUDFLARE_API_TOKEN`
   - Get token from Cloudflare Dashboard → My Profile → API Tokens
3. Disable Cloudflare Builds in Dashboard → Settings → Builds → Disconnect

### 🖥️ Manual Deployment

For one-off deployments or emergency fixes:

```bash
cd zoom-broker
npx wrangler deploy
```

## CI/CD Configuration Reference

Use this section (and the `.cloudflare-builds` reference file) as your evergreen source of truth for keeping the Worker wired into our automation.

### Cloudflare Builds settings

| Setting | Value |
|---------|-------|
| Production branch | `main` |
| Root directory | `/zoom-broker` |
| Build command | `npm ci && npm test && npx wrangler deploy` |

Cloudflare Builds mirrors the same install/test/deploy pipeline we run locally so production pushes and preview builds behave consistently.

### Required secrets

All secrets are set in the Cloudflare Dashboard (Settings → Variables and Secrets). Required keys:

1. `ZOOM_CLIENT_ID` – Zoom OAuth Client ID
2. `ZOOM_CLIENT_SECRET` – Zoom OAuth Client Secret
3. `ALLOWED_ORIGIN` – CORS restriction (`http://localhost` for CLI use, or your production domain)

> 💡 Run `zoom-broker/scripts/setup-secrets.sh` for an interactive helper that executes the necessary `npx wrangler secret put ...` commands.

### Quality gates & testing

- Cloudflare Builds executes `npm test` before every deployment (production and preview).
- GitHub Actions (`.github/workflows/js.yml`) continues to run unit tests plus Trivy security scanning on every push/PR.
- Preview URLs reuse production secrets, enabling full OAuth flow validation before merge.

### Why Cloudflare Builds stays enabled

- **Developers:** automatic preview URLs, build logs, and fast rollbacks directly in the dashboard.
- **Reviewers:** can interact with real Workers during code review instead of relying solely on screenshots.
- **Operators:** get version history and rollback with no extra tooling while still having manual deploy as a fallback.

## Deployment Checklist

### Initial Setup (One-time)

- [ ] Verify `wrangler.jsonc` has `"name": "zoom-broker"` (must match dashboard name)
- [ ] Provision KV namespaces and create your local Wrangler config:
  ```bash
  cd zoom-broker
  ./scripts/setup-kv.sh
  ```
  This script creates both production and preview KV namespaces (or lets you plug in existing IDs) and writes `.wrangler.local.jsonc` with the real IDs while leaving `wrangler.jsonc` untouched. Use `./scripts/wrangler-local.sh <command>` (which automatically sets `WRANGLER_CONFIG`) for any local Wrangler commands. Never commit the local file.
- [ ] Set secrets in Cloudflare Dashboard:
  ```bash
  npx wrangler secret put ZOOM_CLIENT_ID
  npx wrangler secret put ZOOM_CLIENT_SECRET
  npx wrangler secret put ALLOWED_ORIGIN  # e.g., http://localhost
  ```
- [ ] Connect repository in Cloudflare Dashboard (Settings → Builds → Connect)
- [ ] Configure Zoom OAuth app redirect URL: `https://zoom-broker.<user>.workers.dev/callback`

### Before Each Release

- [ ] All tests pass locally (`npm test`)
- [ ] Security scan clean (`npm audit`)
- [ ] PR reviewed and approved
- [ ] Preview URL tested with actual OAuth flow
- [ ] Changelog updated with user-facing changes

### After Deployment

- [ ] Verify production URL responds: `curl https://zoom-broker.<user>.workers.dev/health`
- [ ] Test OAuth flow with `dlzoom login --auth-url https://zoom-broker.<user>.workers.dev`
- [ ] Check Cloudflare Dashboard logs for errors
- [ ] Monitor error rate in Cloudflare Analytics

## Rollback Procedure

If a deployment causes issues:

### Option 1: Via Cloudflare Dashboard (Fastest)

1. Go to Workers & Pages → `zoom-broker` → Deployments
2. Find the last working version
3. Click **Rollback to this deployment**

### Option 2: Via Git

1. Revert the problematic commit:
   ```bash
   git revert <commit-sha>
   git push origin main
   ```
2. Cloudflare Builds will automatically deploy the reverted version

### Option 3: Manual Deploy Previous Version

1. Checkout previous working commit:
   ```bash
   git checkout <previous-commit>
   cd zoom-broker
   npx wrangler deploy
   ```

## Troubleshooting

### Build Fails with "Worker name mismatch"

**Problem**: Dashboard name doesn't match `wrangler.jsonc`

**Solution**:
- Either rename Worker in dashboard to match `wrangler.jsonc`
- Or update `"name"` in `wrangler.jsonc` to match dashboard (requires commit)

### Preview URLs Return 404

**Possible causes:**
- Build is still in progress (check Deployments tab)
- Build failed (check build logs)
- Preview URL expired (recreate by pushing new commit)

### OAuth Fails on Preview URL

**Problem**: Zoom redirect URL not configured for preview domain

**Solution**: Add preview redirect URL to Zoom OAuth app settings (can have multiple redirect URLs)

### Secrets Not Available in Build

**Problem**: Environment variables/secrets not set in Cloudflare Dashboard

**Solution**: Secrets must be set via Dashboard or `wrangler secret put`, not in `wrangler.jsonc`

## Security Notes

- ⚠️ **Never commit secrets** to `wrangler.jsonc` or source code
- ✅ Always set `ALLOWED_ORIGIN` to restrict CORS (default `*` is development-only)
- ✅ Secrets are encrypted at rest in Cloudflare
- ✅ Preview URLs use the same secrets as production (be careful with testing)
- ✅ Regularly rotate `ZOOM_CLIENT_SECRET` and redeploy

## Links

- [Cloudflare Builds Documentation](https://developers.cloudflare.com/workers/ci-cd/builds/)
- [Wrangler Configuration](https://developers.cloudflare.com/workers/wrangler/configuration/)
- [Workers Secrets Management](https://developers.cloudflare.com/workers/configuration/secrets/)
- [Cloudflare Dashboard](https://dash.cloudflare.com)
