# Quick Start: Cloudflare Builds CI/CD

⚡ **5-minute setup for automatic deployments**

## Prerequisites Checklist
- [ ] Cloudflare account
- [ ] Worker already deployed once manually
- [ ] GitHub repository access
- [ ] Zoom OAuth app credentials

## Setup Steps

### 1. Connect to GitHub (2 minutes)

1. Go to https://dash.cloudflare.com → **Workers & Pages** → `zoom-broker`
2. Click **Settings** → **Builds** → **Connect**
3. Choose GitHub, authorize, select your repo
4. Configure:
   - **Production branch:** `main`
   - **Root directory:** `/zoom-broker`
   - **Build command:** `npm ci && npm test && npx wrangler deploy`
5. Click **Save and Deploy**

### 2. Set Secrets (2 minutes)

Go to **Settings** → **Variables and Secrets**, add:

| Secret | Value |
|--------|-------|
| `ZOOM_CLIENT_ID` | From Zoom Marketplace app |
| `ZOOM_CLIENT_SECRET` | From Zoom Marketplace app |
| `ALLOWED_ORIGIN` | `http://localhost` (or your domain) |

**⚠️ Security:** Must set `ALLOWED_ORIGIN` to prevent unauthorized access.

### 3. Verify (1 minute)

1. Push a commit to `main`
2. Check **Deployments** tab for build status
3. Test: `curl https://zoom-broker.<user>.workers.dev/health`

## That's It! 🎉

Now every push to `main` automatically deploys, and every PR gets a preview URL.

## Common Commands

```bash
# View deployment logs
# → Dashboard → Workers & Pages → zoom-broker → Logs

# Rollback to previous version
# → Dashboard → Deployments → Select version → Rollback

# Update secrets
npx wrangler secret put ZOOM_CLIENT_ID

# Manual deploy (if needed)
cd zoom-broker && npx wrangler deploy
```

## Testing PRs with Preview URLs

1. Create a feature branch and PR
2. Find preview URL in **Deployments** tab
3. Test with: `dlzoom login --auth-url https://<preview-url>`
4. Merge when ready → Auto-deploys to production

## Need Help?

- **Detailed setup:** See [CLOUDFLARE_SETUP.md](CLOUDFLARE_SETUP.md)
- **Deployment guide:** See [DEPLOYMENT.md](DEPLOYMENT.md)
- **Build settings reference:** See [.cloudflare-builds](.cloudflare-builds)

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Build fails "Worker name mismatch" | Dashboard name must match `"name": "zoom-broker"` in `wrangler.jsonc` |
| Worker returns 500 | Check secrets are set in Dashboard → Settings → Variables and Secrets |
| OAuth fails on preview | Add `https://*.zoom-broker.<user>.workers.dev/callback` to Zoom app |

## Resources

- [Cloudflare Builds Docs](https://developers.cloudflare.com/workers/ci-cd/builds/)
- [Dashboard](https://dash.cloudflare.com)
- GitHub Actions workflow: `.github/workflows/js.yml`
